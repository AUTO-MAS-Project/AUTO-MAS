"""游戏中心内置安全 provider。

这些 provider 只执行安装检查、启动、关闭，以及把安装/更新安全交给官方
启动器。它们不下载、不删除、不覆盖游戏文件。
"""

from __future__ import annotations

import asyncio
import configparser
import ctypes
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal

import psutil

from app.models.game_center import StoredGame
from app.plugins.emulator_compat import get_emulator_service
from app.services.game_center import (
    GameCenterError,
    GameCenterService,
    GameCheckResult,
    GameProgressCallback,
    GameProgressEvent,
    GameProvider,
    GameProviderDescriptor,
)
from app.services.game_presets import BUILTIN_GAME_PRESETS, GamePreset

_PACKAGE_RE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")
_VERSION_RE = re.compile(r"^\s*versionName=(\S+)\s*$", re.MULTILINE)
_BUILTIN_OWNER = "host:game-center:builtins"
_MIHOYO_LAUNCHER_REGISTRY_KEY = r"Software\miHoYo\HYP\1_1"
_MIHOYO_LAUNCHER_REGISTRY_VALUE = "InstallPath"
_OFFICIAL_LAUNCHER_NAMES: dict[str, tuple[str, ...]] = {
    "mihoyo_pc": ("HoYoPlay.exe", "launcher.exe"),
    "hypergryph_pc": ("Hypergryph Launcher.exe", "launcher.exe"),
}


def _preset_for(game: StoredGame) -> GamePreset | None:
    key = game.Info.PresetKey or ""
    return BUILTIN_GAME_PRESETS.get(key)


def _resolve_pc_executable(game: StoredGame) -> Path:
    raw_path = (game.Data.InstallPath or "").strip()
    if not raw_path:
        raise GameCenterError(400, "未配置 PC 游戏路径")
    install_path = Path(raw_path).expanduser()
    if install_path.is_file():
        return install_path.resolve()

    preset = _preset_for(game)
    if preset is None or not preset.executable:
        raise GameCenterError(400, "自定义 PC 游戏必须选择可执行文件")
    candidates = [install_path / preset.executable]
    candidates.extend(
        install_path / relative / preset.executable
        for relative in preset.relative_directories
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise GameCenterError(
        400,
        f"游戏可执行文件不存在: {preset.executable}",
    )


def _read_local_version(executable: Path) -> str:
    """从常见 config.ini 中读取本地版本；读取失败不伪造版本。"""

    candidates = (
        executable.parent / "config.ini",
        executable.parent.parent / "config.ini",
    )
    for candidate in candidates:
        if not candidate.is_file():
            continue
        parser = configparser.ConfigParser()
        try:
            parser.read(candidate, encoding="utf-8-sig")
        except (OSError, UnicodeError, configparser.Error):
            continue
        for section in ("General", "general", "game", "Game"):
            if parser.has_option(section, "game_version"):
                return parser.get(section, "game_version").strip()
            if parser.has_option(section, "version"):
                return parser.get(section, "version").strip()
        for name in ("game_version", "version"):
            value = parser.defaults().get(name, "").strip()
            if value:
                return value
    return ""


def _launcher_directories(game: StoredGame) -> list[Path]:
    raw_path = (game.Data.InstallPath or "").strip()
    directories: list[Path] = []
    if raw_path:
        configured = Path(raw_path).expanduser()
        configured = configured.parent if configured.is_file() else configured
        directories.extend((configured, configured.parent))

    if game.Info.Provider == "mihoyo_pc" and os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                _MIHOYO_LAUNCHER_REGISTRY_KEY,
            ) as key:
                install_path, _ = winreg.QueryValueEx(
                    key,
                    _MIHOYO_LAUNCHER_REGISTRY_VALUE,
                )
            if install_path:
                directories.insert(0, Path(str(install_path)).expanduser())
        except (ImportError, OSError):
            pass

    unique: list[Path] = []
    seen: set[str] = set()
    for directory in directories:
        normalized = os.path.normcase(str(directory))
        if normalized not in seen:
            seen.add(normalized)
            unique.append(directory)
    return unique


def _find_official_launcher(game: StoredGame) -> Path:
    preferred_names = _OFFICIAL_LAUNCHER_NAMES.get(game.Info.Provider)
    if preferred_names is None:
        raise GameCenterError(400, "当前 provider 没有受信任的官方启动器白名单")

    for directory in _launcher_directories(game):
        for name in preferred_names:
            candidate = directory / name
            if candidate.is_file():
                return candidate.resolve()
    raise GameCenterError(
        400,
        "未找到官方启动器，请先安装启动器或把游戏路径指向启动器管理的目录",
    )


def _open_official_launcher(game: StoredGame) -> None:
    launcher = _find_official_launcher(game)
    try:
        subprocess.Popen(
            [str(launcher)],
            cwd=str(launcher.parent),
            shell=False,
        )
    except OSError as exc:
        raise GameCenterError(500, f"打开官方启动器失败: {exc}") from exc


def _parse_launch_args(raw: str | None) -> list[str]:
    if not raw or not raw.strip():
        return []
    text = raw.strip()
    if os.name == "nt":
        argc = ctypes.c_int()
        command_line_to_argv = ctypes.windll.shell32.CommandLineToArgvW
        command_line_to_argv.argtypes = [
            ctypes.c_wchar_p,
            ctypes.POINTER(ctypes.c_int),
        ]
        command_line_to_argv.restype = ctypes.POINTER(ctypes.c_wchar_p)
        argv = command_line_to_argv(text, ctypes.byref(argc))
        if not argv:
            raise GameCenterError(400, "启动参数格式错误")
        try:
            return [argv[index] for index in range(argc.value)]
        finally:
            ctypes.windll.kernel32.LocalFree(argv)
    try:
        return shlex.split(text, posix=True)
    except ValueError as exc:
        raise GameCenterError(400, f"启动参数格式错误: {exc}") from exc


class PcGameProvider(GameProvider):
    """PC 游戏的本地安全 provider。"""

    def __init__(self, descriptor: GameProviderDescriptor) -> None:
        self.descriptor = descriptor
        self._launched: dict[str, subprocess.Popen[Any]] = {}

    async def check(self, game: StoredGame) -> GameCheckResult:
        try:
            executable = _resolve_pc_executable(game)
        except GameCenterError as exc:
            if exc.code == 400:
                return GameCheckResult(installed=False)
            raise
        version = await asyncio.to_thread(_read_local_version, executable)
        return GameCheckResult(
            local_version=version,
            latest_version=version,
            needs_update=False,
            installed=True,
        )

    async def install_or_update(
        self,
        game: StoredGame,
        progress: GameProgressCallback,
        cancel_event: asyncio.Event,
    ) -> Literal["handed_off"]:
        """把安装或更新安全交给官方启动器，不直接覆盖游戏目录。"""

        if cancel_event.is_set():
            raise asyncio.CancelledError
        await progress(
            GameProgressEvent(
                phase="handoff",
                percent=25.0,
                message="正在打开官方启动器",
            )
        )
        await asyncio.to_thread(_open_official_launcher, game)
        if cancel_event.is_set():
            raise asyncio.CancelledError
        await progress(
            GameProgressEvent(
                phase="handoff",
                percent=100.0,
                message="已打开官方启动器，请在启动器内完成安装或更新",
            )
        )
        return "handed_off"

    async def launch(self, game: StoredGame) -> None:
        executable = _resolve_pc_executable(game)
        arguments = _parse_launch_args(game.Data.LaunchArgs)

        def start() -> subprocess.Popen[Any]:
            return subprocess.Popen(
                [str(executable), *arguments],
                cwd=str(executable.parent),
                shell=False,
            )

        try:
            self._launched[game.game_id] = await asyncio.to_thread(start)
        except OSError as exc:
            raise GameCenterError(500, f"启动游戏失败: {exc}") from exc

    async def close(self, game: StoredGame) -> None:
        executable = _resolve_pc_executable(game)
        launched = self._launched.pop(game.game_id, None)
        await asyncio.to_thread(
            self._close_exact_executable,
            executable,
            launched,
        )

    @staticmethod
    def _close_exact_executable(
        executable: Path,
        launched: subprocess.Popen[Any] | None,
    ) -> None:
        target = os.path.normcase(str(executable.resolve()))
        processes: dict[int, psutil.Process] = {}
        if launched is not None and launched.poll() is None:
            try:
                processes[launched.pid] = psutil.Process(launched.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        for process in psutil.process_iter(["pid", "exe"]):
            try:
                raw_exe = process.info.get("exe")
                if raw_exe and os.path.normcase(str(Path(raw_exe).resolve())) == target:
                    processes[process.pid] = process
            except (OSError, psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        for process in processes.values():
            try:
                process.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        _, alive = psutil.wait_procs(list(processes.values()), timeout=5)
        for process in alive:
            try:
                process.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue


async def _run_adb(adb_path: str, arguments: list[str]) -> str:
    try:
        process = await asyncio.create_subprocess_exec(
            adb_path,
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.wait()
        raise GameCenterError(504, "ADB 操作超时") from exc
    except OSError as exc:
        raise GameCenterError(500, f"无法执行 ADB: {exc}") from exc
    output = stdout.decode("utf-8", errors="replace")
    error = stderr.decode("utf-8", errors="replace").strip()
    if process.returncode != 0:
        raise GameCenterError(500, f"ADB 操作失败: {error or output.strip()}")
    return output


def _device_field(device: Any, name: str) -> Any:
    if isinstance(device, dict):
        return device.get(name)
    return getattr(device, name, None)


class AdbApkGameProvider(GameProvider):
    """通过现有模拟器服务和 ADB 管理已安装安卓游戏。"""

    descriptor = GameProviderDescriptor(
        name="adb_apk",
        display_name="模拟器 ADB（安全模式）",
        platforms=frozenset({"emulator"}),
        capabilities=frozenset({"check", "launch", "close"}),
    )

    @staticmethod
    def _package_name(game: StoredGame) -> str:
        preset = _preset_for(game)
        package = (game.Data.PackageName or "").strip()
        if not package and preset is not None:
            package = preset.package_name
        if not _PACKAGE_RE.fullmatch(package):
            raise GameCenterError(400, "未配置合法的安卓包名")
        return package

    @staticmethod
    def _adb_path(game: StoredGame) -> str:
        explicit = (game.Data.AdbPath or "").strip()
        if explicit:
            path = Path(explicit).expanduser()
            if not path.is_file():
                raise GameCenterError(400, f"ADB 文件不存在: {path}")
            return str(path.resolve())
        discovered = shutil.which("adb")
        if discovered is None:
            raise GameCenterError(400, "未配置 ADB 路径，且 PATH 中未找到 adb")
        return discovered

    async def _resolve_device(
        self,
        game: StoredGame,
        *,
        start_if_offline: bool,
    ) -> str:
        emulator_id = (game.Data.EmulatorId or "").strip()
        emulator_index = (game.Data.EmulatorIndex or "").strip() or "0"
        if not emulator_id or emulator_id == "-":
            raise GameCenterError(400, "未关联模拟器配置")
        service = get_emulator_service()

        async def find_online() -> str:
            status = await service.status(emulator_id)
            devices = status.get(emulator_id, {}) if isinstance(status, dict) else {}
            device = devices.get(emulator_index)
            if device is None and len(devices) == 1:
                device = next(iter(devices.values()))
            if device is None or _device_field(device, "status") != 0:
                return ""
            return str(_device_field(device, "adb_address") or "").strip()

        serial = await find_online()
        if serial or not start_if_offline:
            if not serial:
                raise GameCenterError(409, "关联模拟器实例当前不在线")
            return serial

        await service.operate("open", emulator_id, emulator_index)
        for _ in range(60):
            await asyncio.sleep(1)
            serial = await find_online()
            if serial:
                return serial
        raise GameCenterError(504, "等待模拟器实例上线超时")

    async def check(self, game: StoredGame) -> GameCheckResult:
        package = self._package_name(game)
        adb_path = self._adb_path(game)
        serial = await self._resolve_device(game, start_if_offline=False)
        output = await _run_adb(
            adb_path,
            ["-s", serial, "shell", "dumpsys", "package", package],
        )
        match = _VERSION_RE.search(output)
        version = match.group(1) if match else ""
        return GameCheckResult(
            local_version=version,
            latest_version=version,
            needs_update=False,
            installed=bool(match),
        )

    async def launch(self, game: StoredGame) -> None:
        package = self._package_name(game)
        adb_path = self._adb_path(game)
        serial = await self._resolve_device(game, start_if_offline=True)
        await _run_adb(
            adb_path,
            [
                "-s",
                serial,
                "shell",
                "monkey",
                "-p",
                package,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ],
        )

    async def close(self, game: StoredGame) -> None:
        package = self._package_name(game)
        adb_path = self._adb_path(game)
        serial = await self._resolve_device(game, start_if_offline=False)
        await _run_adb(
            adb_path,
            ["-s", serial, "shell", "am", "force-stop", package],
        )


def register_builtin_game_providers(service: GameCenterService) -> None:
    """把宿主内置 provider 幂等注册到指定服务。"""

    descriptors = (
        GameProviderDescriptor(
            name="local.pc",
            display_name="本地 PC 可执行文件",
            platforms=frozenset({"pc"}),
            capabilities=frozenset({"check", "launch", "close"}),
        ),
        GameProviderDescriptor(
            name="mihoyo_pc",
            display_name="米哈游 PC（官方启动器安全模式）",
            platforms=frozenset({"pc"}),
            capabilities=frozenset(
                {"check", "install_or_update", "launch", "close"}
            ),
        ),
        GameProviderDescriptor(
            name="hypergryph_pc",
            display_name="鹰角 PC（官方启动器安全模式）",
            platforms=frozenset({"pc"}),
            capabilities=frozenset(
                {"check", "install_or_update", "launch", "close"}
            ),
        ),
    )
    for descriptor in descriptors:
        service.register_provider(
            PcGameProvider(descriptor),
            owner=_BUILTIN_OWNER,
        )
    service.register_provider(
        AdbApkGameProvider(),
        owner=_BUILTIN_OWNER,
    )


__all__ = [
    "AdbApkGameProvider",
    "PcGameProvider",
    "register_builtin_game_providers",
]
