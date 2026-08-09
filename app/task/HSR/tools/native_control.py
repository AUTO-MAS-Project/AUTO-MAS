"""HSR 原生配置与脚本直控的旧 dev 兼容层。

插件版 HSR 把原生配置器/CLI 抽象成了宿主插件服务。旧 dev 没有 Plugin V2
substrate，因此这里保留同一组小而稳定的领域对象，直接复用旧的
``ConfigBase``、``ProcessManager`` 和 SRA/M7A runner。所有配置读取都带有
旧字段回退，插件新增的 ``Control``/``Direct`` 分组不存在时仍按托管模式运行。
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from .m7a_runtime import M7ARunner
from .sra_runtime import (
    SRAProcessRegistry,
    get_sra_app_data_dir,
    resolve_sra_profile,
    run_sra_config,
)

HSREngine = Literal["SRA", "M7A"]


@dataclass(frozen=True, slots=True)
class HSRNativeConfigOption:
    id: str
    label: str
    path: str

    def asdict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HSRNativeControlSnapshot:
    engine: HSREngine
    configurator_ready: bool
    direct_run_ready: bool
    configurator_reason: str
    direct_run_reason: str
    launcher_path: str
    selected_config: str
    configs: tuple[HSRNativeConfigOption, ...] = ()
    running: bool = False
    pid: int | None = None

    def asdict(self) -> dict[str, Any]:
        data = asdict(self)
        data["configs"] = [item.asdict() for item in self.configs]
        return data


@dataclass(frozen=True, slots=True)
class HSRRunResult:
    status: Literal["completed", "failed", "incomplete", "skipped"]
    summary: str = ""
    error: str = ""
    returncode: int = 0
    native_result: Any = None

    @property
    def success(self) -> bool:
        return self.status == "completed"

    @classmethod
    def from_native(
        cls,
        result: Any,
        *,
        default_summary: str,
        default_error: str,
    ) -> "HSRRunResult":
        if bool(getattr(result, "success", False)):
            return cls(
                status="completed",
                summary=str(getattr(result, "output", "") or default_summary),
                returncode=int(getattr(result, "returncode", 0) or 0),
                native_result=result,
            )
        return cls(
            status="failed",
            error=str(getattr(result, "error", "") or default_error),
            returncode=int(getattr(result, "returncode", 0) or 0),
            native_result=result,
        )


def _config_value(config: Any, group: str, key: str, default: Any = None) -> Any:
    """Read both ConfigBase and dict-like models without leaking secrets."""

    if config is None:
        return default
    if isinstance(config, dict):
        section = config.get(group)
        if isinstance(section, dict):
            value = section.get(key, default)
            return default if value is None else value
        return default
    try:
        value = config.get(group, key)
    except (AttributeError, KeyError, TypeError):
        section = getattr(config, group, None)
        if isinstance(section, dict):
            value = section.get(key, default)
        else:
            value = getattr(section, key, default)
    return default if value is None else value


def _script_path(config: Any, engine: HSREngine) -> str:
    group = "SRA" if engine == "SRA" else "M7A"
    value = _config_value(config, group, "Path", None)
    if value in (None, ""):
        value = _config_value(config, "Info", f"{engine}Path", "")
    return str(value or "").strip()


def resolve_script_path(config: Any, engine: HSREngine) -> str:
    """Public path resolver shared by old HSR manager/tools and API adapters."""

    return _script_path(config, engine)


def resolve_user_control(
    user_config: Any,
    *,
    script_config: Any | None = None,
) -> "HSRUserControlSettings":
    """Resolve per-user managed/direct mode, accepting old ConfigBase records."""

    raw_mode = str(_config_value(user_config, "Control", "Mode", "managed"))
    mode: Literal["managed", "direct"] = (
        "direct" if raw_mode.strip().lower() == "direct" else "managed"
    )
    engines: tuple[HSREngine, ...] = tuple(
        engine
        for engine in ("SRA", "M7A")
        if bool(_config_value(user_config, "Control", engine, False))
    )  # type: ignore[assignment]
    try:
        timeout_minutes = int(
            _config_value(script_config, "Control", "TimeoutMinutes", 120)
        )
    except (TypeError, ValueError):
        timeout_minutes = 120
    timeout_minutes = max(1, min(timeout_minutes, 1440))
    return HSRUserControlSettings(
        mode=mode,
        engines=engines,
        timeout_seconds=timeout_minutes * 60,
    )


@dataclass(frozen=True, slots=True)
class HSRDirectControlSettings:
    enabled: bool
    engine: HSREngine
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class HSRUserControlSettings:
    mode: Literal["managed", "direct"]
    engines: tuple[HSREngine, ...]
    timeout_seconds: int


def get_user_direct_config(user_config: Any, engine: HSREngine) -> str:
    """Return one imported native snapshot without logging its contents."""

    value = _config_value(user_config, "Direct", f"{engine}Config", "")
    return str(value or "")


def resolve_direct_control(config: Any) -> HSRDirectControlSettings:
    raw_engine = str(_config_value(config, "Control", "Engine", "SRA")).upper()
    engine: HSREngine = "M7A" if raw_engine == "M7A" else "SRA"
    try:
        timeout_minutes = int(_config_value(config, "Control", "TimeoutMinutes", 120))
    except (TypeError, ValueError):
        timeout_minutes = 120
    timeout_minutes = max(1, min(timeout_minutes, 1440))
    return HSRDirectControlSettings(
        enabled=bool(_config_value(config, "Control", "Direct", False)),
        engine=engine,
        timeout_seconds=timeout_minutes * 60,
    )


class HSRConfiguratorProcessSession:
    """Own exactly one native configurator process."""

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self._process = process
        self._closed = False

    @property
    def pid(self) -> int | None:
        return self._process.pid

    @property
    def running(self) -> bool:
        return self._process.returncode is None

    async def wait(self) -> int:
        return int(await self._process.wait())

    async def close(self) -> None:
        if self._closed:
            return
        if self.running:
            try:
                self._process.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                try:
                    self._process.kill()
                except ProcessLookupError:
                    pass
                await self._process.wait()
        self._closed = True


async def open_configurator_process(
    executable: str | Path,
    *,
    cwd: str | Path,
) -> HSRConfiguratorProcessSession:
    executable_path = Path(executable)
    if not executable_path.is_file():
        raise FileNotFoundError(f"原生配置器不存在：{executable_path}")
    process = await asyncio.create_subprocess_exec(str(executable_path), cwd=str(Path(cwd)))
    return HSRConfiguratorProcessSession(process)


class SRADirectControlSession:
    def __init__(self, executable: Path, config_path: Path, temporary, log) -> None:
        self._executable = executable
        self._config_path = config_path
        self._temporary = temporary
        self._log = log
        self._process_registry = SRAProcessRegistry()
        self._closed = False

    async def run(self, timeout_seconds: int) -> HSRRunResult:
        result = await run_sra_config(
            self._executable,
            self._config_path,
            timeout=timeout_seconds,
            process_registry=self._process_registry,
            log_callback=self._log,
        )
        return HSRRunResult.from_native(
            result,
            default_summary="SRA 原生配置执行完成",
            default_error="SRA 原生配置执行失败",
        )

    async def cancel(self) -> None:
        await self._process_registry.terminate_current_process()

    async def close(self) -> None:
        if self._closed:
            return
        await self.cancel()
        await self._process_registry.clear()
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None
        self._closed = True


class SRANativeControlProvider:
    engine: HSREngine = "SRA"

    def _root(self, script_config: Any) -> Path:
        return Path(_script_path(script_config, "SRA"))

    def inspect(self, script_config: Any) -> HSRNativeControlSnapshot:
        raw_root = _script_path(script_config, "SRA")
        root = self._root(script_config)
        launcher = root / "SRA.exe"
        cli = root / "SRA-cli.exe"
        config_root = get_sra_app_data_dir() / "configs"
        configs = tuple(
            HSRNativeConfigOption(path.stem, path.stem, str(path))
            for path in sorted(config_root.glob("*.json"), key=lambda item: item.name.casefold())
            if path.is_file()
        ) if config_root.is_dir() else ()
        selected_id, selected_profile = resolve_sra_profile(
            script_config,
            config_root=config_root,
        )
        selected_path = next((item for item in configs if item.id == selected_id), None)
        if not raw_root:
            configurator_reason = "请先设置 SRA 路径"
            direct_reason = configurator_reason
        else:
            configurator_reason = "" if launcher.is_file() else f"SRA 路径中未找到 SRA.exe：{launcher}"
            if not cli.is_file():
                direct_reason = f"SRA 路径中未找到 SRA-cli.exe：{cli}"
            elif not configs:
                direct_reason = "SRA 尚无原生配置，请先打开 SRA 完成配置"
            elif selected_path is None or selected_profile != Path(selected_path.path):
                direct_reason = f"SRA 原生配置不存在或已更名：{selected_id}"
            else:
                direct_reason = ""
        return HSRNativeControlSnapshot(
            engine="SRA",
            configurator_ready=not configurator_reason,
            direct_run_ready=not direct_reason,
            configurator_reason=configurator_reason,
            direct_run_reason=direct_reason,
            launcher_path=str(launcher),
            selected_config=selected_id,
            configs=configs,
        )

    def export_config(self, script_config: Any) -> tuple[Path, str]:
        snapshot = self.inspect(script_config)
        if not snapshot.direct_run_ready:
            raise RuntimeError(snapshot.direct_run_reason)
        selected = next(item for item in snapshot.configs if item.id == snapshot.selected_config)
        content = Path(selected.path).read_text(encoding="utf-8-sig")
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError(f"SRA 原生配置顶层必须是对象：{selected.path}")
        return Path(selected.path), content

    async def open_configurator(self, *, script_config: Any, log) -> HSRConfiguratorProcessSession:
        snapshot = self.inspect(script_config)
        if not snapshot.configurator_ready:
            raise RuntimeError(snapshot.configurator_reason)
        log("正在打开 SRA 原生配置器")
        root = self._root(script_config)
        return await open_configurator_process(root / "SRA.exe", cwd=root)

    async def open_direct_session(self, *, script_config: Any, config_content: str, session_id: str, log) -> SRADirectControlSession:
        root = self._root(script_config)
        executable = root / "SRA-cli.exe"
        if not executable.is_file():
            raise FileNotFoundError(f"SRA 路径中未找到 SRA-cli.exe：{executable}")
        try:
            parsed = json.loads(config_content)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"SRA 用户快照不是有效 JSON：{exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("SRA 用户快照顶层必须是对象")
        safe_id = re.sub(r"[^A-Za-z0-9_-]+", "-", session_id).strip("-") or "user"
        temporary = tempfile.TemporaryDirectory(prefix=f"automas-sra-{safe_id[:32]}-")
        config_path = Path(temporary.name) / "config.json"
        config_path.write_text(config_content, encoding="utf-8")
        log("SRA 将原样执行当前用户导入的隔离配置快照；MAS 只负责外部进程生命周期")
        return SRADirectControlSession(executable, config_path, temporary, log)


class M7ADirectControlSession:
    def __init__(self, root: Path, config_content: str, session_id: str, log) -> None:
        self._source_root = root
        self._config_content = config_content
        self._session_id = session_id
        self._log = log
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self._runner: M7ARunner | None = None
        self._closed = False

    def _create_isolated_root(self) -> Path:
        try:
            config = yaml.safe_load(self._config_content) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"三月七助手用户快照不是有效 YAML：{exc}") from exc
        if not isinstance(config, dict):
            raise ValueError("三月七助手用户快照顶层必须是对象")
        safe_id = re.sub(r"[^A-Za-z0-9_-]+", "-", self._session_id).strip("-") or "user"
        self._temporary = tempfile.TemporaryDirectory(prefix=f"automas-m7a-{safe_id[:32]}-")
        isolated_root = Path(self._temporary.name)
        try:
            for source in self._source_root.iterdir():
                if source.name.casefold() == "config.yaml":
                    continue
                target = isolated_root / source.name
                if source.is_dir():
                    try:
                        target.symlink_to(source.resolve(), target_is_directory=True)
                    except OSError:
                        shutil.copytree(source, target)
                elif source.is_file():
                    shutil.copy2(source, target)
            (isolated_root / "config.yaml").write_text(self._config_content, encoding="utf-8")
        except Exception:
            self._temporary.cleanup()
            self._temporary = None
            raise
        return isolated_root

    async def run(self, timeout_seconds: int) -> HSRRunResult:
        isolated_root = self._create_isolated_root()
        self._runner = M7ARunner(isolated_root, log_callback=self._log)
        self._log("三月七助手将从隔离启动目录原样读取当前用户 config.yaml；MAS 只负责外部进程生命周期")
        result = await self._runner.run_task("main", timeout=timeout_seconds)
        return HSRRunResult.from_native(
            result,
            default_summary="三月七助手原生配置执行完成",
            default_error="三月七助手原生配置执行失败",
        )

    async def cancel(self) -> None:
        if self._runner is not None:
            await self._runner.terminate_current_process()

    async def close(self) -> None:
        if self._closed:
            return
        await self.cancel()
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None
        self._closed = True


class M7ANativeControlProvider:
    engine: HSREngine = "M7A"

    def _root(self, script_config: Any) -> Path:
        return Path(_script_path(script_config, "M7A"))

    def inspect(self, script_config: Any) -> HSRNativeControlSnapshot:
        raw_root = _script_path(script_config, "M7A")
        root = self._root(script_config)
        launcher = root / "March7th Launcher.exe"
        executable = root / "March7th Assistant.exe"
        config_path = root / "config.yaml"
        if not raw_root:
            configurator_reason = "请先设置三月七助手路径"
            direct_reason = configurator_reason
        else:
            configurator_reason = "" if launcher.is_file() else f"三月七助手路径中未找到 March7th Launcher.exe：{launcher}"
            if not executable.is_file():
                direct_reason = f"三月七助手路径中未找到 March7th Assistant.exe：{executable}"
            elif not config_path.is_file():
                direct_reason = f"三月七助手原生配置不存在：{config_path}，请先打开配置器"
            else:
                direct_reason = ""
        configs = (HSRNativeConfigOption("config.yaml", "config.yaml", str(config_path)),) if config_path.is_file() else ()
        return HSRNativeControlSnapshot(
            engine="M7A",
            configurator_ready=not configurator_reason,
            direct_run_ready=not direct_reason,
            configurator_reason=configurator_reason,
            direct_run_reason=direct_reason,
            launcher_path=str(launcher),
            selected_config="config.yaml" if configs else "",
            configs=configs,
        )

    def export_config(self, script_config: Any) -> tuple[Path, str]:
        snapshot = self.inspect(script_config)
        if not snapshot.direct_run_ready:
            raise RuntimeError(snapshot.direct_run_reason)
        path = self._root(script_config) / "config.yaml"
        content = path.read_text(encoding="utf-8-sig")
        parsed = yaml.safe_load(content) or {}
        if not isinstance(parsed, dict):
            raise ValueError(f"三月七助手原生配置顶层必须是对象：{path}")
        return path, content

    async def open_configurator(self, *, script_config: Any, log) -> HSRConfiguratorProcessSession:
        snapshot = self.inspect(script_config)
        if not snapshot.configurator_ready:
            raise RuntimeError(snapshot.configurator_reason)
        log("正在打开三月七助手原生配置器")
        root = self._root(script_config)
        return await open_configurator_process(root / "March7th Launcher.exe", cwd=root)

    async def open_direct_session(self, *, script_config: Any, config_content: str, session_id: str, log) -> M7ADirectControlSession:
        root = self._root(script_config)
        executable = root / "March7th Assistant.exe"
        if not executable.is_file():
            raise FileNotFoundError(f"三月七助手路径中未找到 March7th Assistant.exe：{executable}")
        if not config_content.strip():
            raise ValueError("当前用户尚未导入三月七助手 config.yaml 快照")
        return M7ADirectControlSession(root, config_content, session_id, log)


def native_provider(engine: str):
    normalized = str(engine or "").strip().upper()
    if normalized == "SRA":
        return SRANativeControlProvider()
    if normalized == "M7A":
        return M7ANativeControlProvider()
    raise ValueError(f"不支持的 HSR 原生引擎：{engine!r}")


__all__ = [
    "HSRConfiguratorProcessSession",
    "HSRDirectControlSettings",
    "HSREngine",
    "HSRNativeConfigOption",
    "HSRNativeControlSnapshot",
    "HSRRunResult",
    "HSRUserControlSettings",
    "M7ADirectControlSession",
    "M7ANativeControlProvider",
    "SRADirectControlSession",
    "SRANativeControlProvider",
    "get_user_direct_config",
    "native_provider",
    "open_configurator_process",
    "resolve_direct_control",
    "resolve_script_path",
    "resolve_user_control",
]
