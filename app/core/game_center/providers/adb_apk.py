#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""ADB APK 安装方式 Provider

通过 adb 向模拟器安装 / 更新 / 启动安卓游戏包。

本模块同时提供 adb 工具函数 (resolve_adb_path / run_adb), 不单独建立 adb.py。
"""

from __future__ import annotations

import asyncio
import re
import shutil
from contextlib import suppress
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

from app.utils import get_logger
from app.utils.constants import CREATION_FLAGS
from app.utils.downloader import download_file

from ..base import GameProvider, LatestInfo, ProgressEvent

logger = get_logger("ADB APK 安装")

# APK 下载目录 (相对运行目录)
_APK_DIR = Path.cwd() / "data" / "game_center" / "apk"

# adb install 结果中的常见失败码
_INSTALL_FAILED_VERSION_DOWNGRADE = "INSTALL_FAILED_VERSION_DOWNGRADE"


class AdbFileNotFoundException(Exception):
    """找不到 adb.exe"""


# ---------------------------------------------------------------------------
# ADB 工具函数
# ---------------------------------------------------------------------------


async def resolve_adb_path(config: Any) -> str:
    """解析 adb.exe 路径。

    优先级:

    1. config 的 Data_AdbPath (用户显式指定)
    2. LDPlayer 同目录的 adb.exe (参考 app/utils/emulator/ldplayer.py)
    3. MuMu 的 shell/adb.exe (参考 app/utils/emulator/mumu.py)
    4. shutil.which("adb")

    找不到则抛 AdbFileNotFoundException。

    Args:
        config: GameConfig 实例, 提供 Data.AdbPath / Data.EmulatorId。

    Returns:
        adb.exe 的完整路径字符串。
    """

    # 1. 用户显式指定的 adb 路径
    custom = config.get("Data", "AdbPath")
    if custom:
        custom_path = Path(custom)
        if custom_path.is_file():
            return str(custom_path)
        logger.warning(f"配置的 AdbPath 不存在: {custom}")

    # 2/3. 从关联模拟器推断 adb.exe 位置
    emulator_id = config.get("Data", "EmulatorId")
    if emulator_id and emulator_id != "-":
        try:
            from app.core.emulator_manager import EmulatorManager

            device = await EmulatorManager.get_emulator_instance(emulator_id)
            exe_path = Path(device.emulator_path)
            etype = device.config.get("Info", "Type")

            # 按模拟器类型构造候选路径, 命中即返回
            candidates: list[Path] = []
            if etype == "mumu":
                # MuMu 的 adb 通常在 shell/ 子目录; 若 Path 指向 MuMuManager.exe
                # (本身在 shell/), 则同目录也命中
                candidates.append(exe_path.parent / "shell" / "adb.exe")
                candidates.append(exe_path.parent / "adb.exe")
            else:
                # LDPlayer 的 dnconsole.exe 与 adb.exe 同目录; 通用类型同理
                candidates.append(exe_path.parent / "adb.exe")

            for candidate in candidates:
                if candidate.is_file():
                    return str(candidate)
        except Exception as e:
            logger.warning(f"从模拟器 {emulator_id} 推断 adb 路径失败: {e}")

    # 4. 系统 PATH 兜底
    found = shutil.which("adb")
    if found:
        return found

    raise AdbFileNotFoundException(
        "无法找到 adb.exe, 请在游戏配置中设置 AdbPath, 或确保已配置可用模拟器"
    )


async def run_adb(adb_path: str, args: list[str], timeout: float = 60.0) -> str:
    """异步执行 adb 命令并返回 stdout。

    Args:
        adb_path: adb.exe 路径
        args: adb 参数列表 (不含 adb 本身)
        timeout: 超时秒数

    Returns:
        stdout 文本 (utf-8, 忽略解码错误)。非零返回码时不抛异常,
        仅以 warning 记录 stderr, 由调用方按输出内容判断结果。

    Raises:
        AdbFileNotFoundException: adb 可执行文件不存在。
        RuntimeError: 命令超时。
    """

    try:
        proc = await asyncio.create_subprocess_exec(
            adb_path,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=CREATION_FLAGS,
        )
    except FileNotFoundError as e:
        raise AdbFileNotFoundException(f"adb 可执行文件不存在: {adb_path}") from e

    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        with suppress(ProcessLookupError):
            proc.kill()
        await proc.wait()
        raise RuntimeError(f"adb 命令超时: adb {' '.join(args)}")

    stdout = stdout_b.decode("utf-8", errors="ignore") if stdout_b else ""
    stderr = stderr_b.decode("utf-8", errors="ignore") if stderr_b else ""

    if proc.returncode != 0:
        logger.warning(
            f"adb 命令返回非零 (code={proc.returncode}): "
            f"adb {' '.join(args)} | stderr={stderr.strip()!r}"
        )

    return stdout


def _device_is_ready(devices_output: str, serial: str) -> bool:
    """检查 adb devices 输出中指定 serial 是否处于 device 就绪状态。

    解析 ``adb devices`` 的输出, 排除 offline / unauthorized。
    """

    for line in devices_output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == serial and parts[1] == "device":
            return True
    return False


def _parse_install_result(out: str) -> tuple[bool, str]:
    """解析 ``adb install`` 的输出, 返回 (是否成功, 消息)。"""

    low = out.lower()
    if "success" in low:
        return True, "Success"

    # 提取 Failure [CODE] 中的错误码
    match = re.search(r"Failure\s*\[([^\]]+)\]", out)
    if match:
        return False, match.group(1)

    if "failure" in low:
        return False, out.strip()

    return False, (out.strip() or "未知结果")


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class AdbApkProvider(GameProvider):
    """ADB APK 安装方式 Provider。

    依赖 GameConfig 的 Data.EmulatorId / Data.EmulatorIndex / Data.AdbPath,
    以及 GamePreset 的 package_name / params (version_strategy, apk_url, version_api)。
    """

    # -- 配置访问 -----------------------------------------------------------

    @property
    def package_name(self) -> Optional[str]:
        """安卓包名, 优先取预设, 回退到 config。"""

        if self.preset and self.preset.package_name:
            return self.preset.package_name
        return self.config.get("Data", "PackageName") or None

    async def _get_device_address(self) -> str:
        """通过 EmulatorManager 获取关联模拟器设备的 ADB 序列号。

        Returns:
            adb serial, 如 ``emulator-5554`` 或 ``127.0.0.1:16384``。

        Raises:
            RuntimeError: 未配置模拟器 / 获取不到设备信息或地址。
        """

        emulator_id = self.config.get("Data", "EmulatorId")
        if not emulator_id or emulator_id == "-":
            raise RuntimeError("未配置关联模拟器 (Data.EmulatorId)")

        emulator_index = self.config.get("Data", "EmulatorIndex") or "0"

        from app.core.emulator_manager import EmulatorManager

        device = await EmulatorManager.get_emulator_instance(emulator_id)
        info = await device.getInfo(emulator_index)

        # 索引未命中时回退到首个可用设备
        if emulator_index not in info:
            if not info:
                raise RuntimeError(
                    f"模拟器 {emulator_id} 未返回设备 {emulator_index} 的信息, "
                    f"请确认模拟器已启动"
                )
            emulator_index = next(iter(info))

        address = info[emulator_index].adb_address
        if not address or address == "Unknown":
            raise RuntimeError(
                f"无法获取模拟器 {emulator_id} 设备 {emulator_index} 的 ADB 地址"
            )
        return address

    async def _ensure_connected(
        self, adb_path: str, serial: str, retries: int = 3
    ) -> None:
        """确保 ADB 设备已连接就绪, 必要时对网络设备执行 adb connect。

        参考 app/utils/OCR/OCRtool.py:423 的连接检查模式, 并增加重试。

        Raises:
            RuntimeError: 重试后设备仍未就绪。
        """

        for attempt in range(1, retries + 1):
            devices_out = await run_adb(adb_path, ["devices"], timeout=10.0)
            if _device_is_ready(devices_out, serial):
                logger.info(f"设备 {serial} 已连接")
                return

            # 网络设备 (host:port) 尝试 adb connect
            if ":" in serial:
                try:
                    connect_out = await run_adb(
                        adb_path, ["connect", serial], timeout=15.0
                    )
                    logger.debug(f"adb connect {serial}: {connect_out.strip()}")
                except Exception as e:
                    logger.warning(
                        f"adb connect {serial} 失败 (第{attempt}/{retries}次): {e}"
                    )

                # connect 后再次确认
                devices_out = await run_adb(adb_path, ["devices"], timeout=10.0)
                if _device_is_ready(devices_out, serial):
                    logger.info(f"设备 {serial} 连接成功")
                    return
            else:
                # 非网络设备 (如 emulator-XXXX) 无法 adb connect,
                # 仅等待设备自动上线
                logger.debug(f"设备 {serial} 非网络设备, 等待自动上线...")

            if attempt < retries:
                await asyncio.sleep(1.0)

        raise RuntimeError(
            f"设备 {serial} 未就绪, 请确认模拟器已启动且 ADB 已连接 "
            f"(重试 {retries} 次后仍失败)"
        )

    # -- GameProvider ABC ---------------------------------------------------

    async def is_installed(self) -> bool:
        """判断游戏包是否已安装 (通过本地版本号推断)。"""

        return bool(await self.check_local_version())

    async def check_local_version(self) -> str:
        """通过 adb dumpsys 获取已安装应用的 versionName, 未安装返回空串。

        命令等价: ``adb -s <device> shell dumpsys package <package>`` 后
        在 Python 侧解析 ``versionName=`` 行 (跨平台, 不依赖 findstr/grep)。
        """

        package = self.package_name
        if not package:
            return ""

        adb_path = await resolve_adb_path(self.config)
        serial = await self._get_device_address()
        await self._ensure_connected(adb_path, serial)

        out = await run_adb(
            adb_path,
            ["-s", serial, "shell", "dumpsys", "package", package],
            timeout=30.0,
        )

        for line in out.splitlines():
            line = line.strip()
            if line.startswith("versionName="):
                return line.split("=", 1)[1].strip()

        return ""

    async def check_latest(self) -> LatestInfo:
        """查询最新版本。

        - arknights: GET version_api, 取 clientVersion, 与本地版本比对。
        - reverse1999: 无版本 API, HEAD apk_url 取 Last-Modified/ETag,
          返回 LatestInfo(version="latest", needs_update=True)。
        """

        strategy = self.preset.params.get("version_strategy") if self.preset else None

        if strategy == "arknights":
            api_url = self.preset.params.get("version_api")
            if not api_url:
                raise RuntimeError("预设缺少 version_api")

            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(api_url)
                resp.raise_for_status()
                data = resp.json()

            version = str(data.get("clientVersion", ""))

            # 本地版本获取失败 (如设备离线) 时视为需要更新
            try:
                local = await self.check_local_version()
            except Exception as e:
                logger.warning(f"获取本地版本失败, 视为需要更新: {e}")
                local = ""

            needs_update = bool(version) and (not local or local != version)
            return LatestInfo(version=version, needs_update=needs_update, raw=data)

        if strategy == "reverse1999":
            apk_url = self.preset.params.get("apk_url")
            if not apk_url:
                raise RuntimeError("预设缺少 apk_url")

            async with httpx.AsyncClient(
                timeout=15.0, follow_redirects=True
            ) as client:
                resp = await client.head(apk_url)
                resp.raise_for_status()

            raw = {
                "last_modified": resp.headers.get("Last-Modified", ""),
                "etag": resp.headers.get("ETag", ""),
                "content_length": resp.headers.get("Content-Length", ""),
            }
            # 无版本 API, 无法精确比对, 默认标记需要更新
            return LatestInfo(version="latest", needs_update=True, raw=raw)

        raise RuntimeError(f"未知的 version_strategy: {strategy!r}")

    async def install_or_update(
        self,
        progress_cb: Callable[[ProgressEvent], Any],
        cancel_event: asyncio.Event,
    ) -> None:
        """下载 APK 并通过 adb 安装/更新。

        下载阶段回调 ProgressEvent(phase="download"), 安装阶段回调
        ProgressEvent(phase="install") / phase="done"。
        """

        package = self.package_name
        if not package:
            raise RuntimeError("未配置包名 (preset.package_name)")

        apk_url = self.preset.params.get("apk_url") if self.preset else None
        if not apk_url:
            raise RuntimeError("预设缺少 apk_url")

        apk_dir = _APK_DIR
        apk_path = apk_dir / f"{package}.apk"

        # ---- 下载阶段 ----
        def _download_progress(downloaded: int, total: int, speed: float) -> None:
            if cancel_event and cancel_event.is_set():
                return
            percent = (downloaded / total * 100.0) if total else 0.0
            progress_cb(
                ProgressEvent(
                    phase="download",
                    percent=percent,
                    downloaded=downloaded,
                    total=total,
                    speed=speed,
                )
            )

        logger.info(f"开始下载 APK: {apk_url} -> {apk_path}")
        await download_file(
            apk_url,
            apk_path,
            progress=_download_progress,
            cancel_event=cancel_event,
        )

        # 下载被取消时 download_file 会抛 CancelledError, 此处仅处理安装阶段取消
        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError("安装前任务被取消")

        # ---- 安装阶段 ----
        progress_cb(
            ProgressEvent(phase="install", percent=0.0, message="连接设备...")
        )
        adb_path = await resolve_adb_path(self.config)
        serial = await self._get_device_address()
        await self._ensure_connected(adb_path, serial)

        progress_cb(
            ProgressEvent(
                phase="install",
                percent=50.0,
                message=f"安装 {apk_path.name}...",
            )
        )
        out = await run_adb(
            adb_path,
            ["-s", serial, "install", "-r", str(apk_path)],
            timeout=300.0,
        )

        success, message = _parse_install_result(out)
        if not success:
            if _INSTALL_FAILED_VERSION_DOWNGRADE in message:
                raise RuntimeError(
                    "安装失败: 版本降级 (INSTALL_FAILED_VERSION_DOWNGRADE), "
                    "请先卸载旧版本或使用更新版本"
                )
            raise RuntimeError(f"APK 安装失败: {message}")

        progress_cb(
            ProgressEvent(phase="done", percent=100.0, message="安装成功")
        )
        logger.success(f"APK 安装成功: {package}")

    async def launch(self) -> None:
        """通过 adb monkey 启动游戏。"""

        package = self.package_name
        if not package:
            raise RuntimeError("未配置包名 (preset.package_name)")

        adb_path = await resolve_adb_path(self.config)
        serial = await self._get_device_address()
        await self._ensure_connected(adb_path, serial)

        logger.info(f"启动游戏: {serial} / {package}")
        await run_adb(
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
            timeout=30.0,
        )

    # -- 额外方法 (不在 ABC 中) ---------------------------------------------

    async def install_local_apk(
        self,
        apk_path: str | Path,
        progress_cb: Optional[Callable[[ProgressEvent], Any]] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> None:
        """安装本地 APK 文件到关联设备。

        Args:
            apk_path: 本地 APK 文件路径
            progress_cb: 可选进度回调
            cancel_event: 可选取消事件 (连接前检查)
        """

        apk_file = Path(apk_path)
        if not apk_file.is_file():
            raise FileNotFoundError(f"APK 文件不存在: {apk_path}")

        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError("安装前任务被取消")

        if progress_cb:
            progress_cb(
                ProgressEvent(phase="install", percent=0.0, message="连接设备...")
            )

        adb_path = await resolve_adb_path(self.config)
        serial = await self._get_device_address()
        await self._ensure_connected(adb_path, serial)

        if progress_cb:
            progress_cb(
                ProgressEvent(
                    phase="install",
                    percent=50.0,
                    message=f"安装 {apk_file.name}...",
                )
            )

        out = await run_adb(
            adb_path,
            ["-s", serial, "install", "-r", str(apk_file)],
            timeout=300.0,
        )

        success, message = _parse_install_result(out)
        if not success:
            if _INSTALL_FAILED_VERSION_DOWNGRADE in message:
                raise RuntimeError(
                    "安装失败: 版本降级 (INSTALL_FAILED_VERSION_DOWNGRADE), "
                    "请先卸载旧版本或使用更新版本"
                )
            raise RuntimeError(f"APK 安装失败: {message}")

        if progress_cb:
            progress_cb(
                ProgressEvent(phase="done", percent=100.0, message="安装成功")
            )
        logger.success(f"本地 APK 安装成功: {apk_file.name}")
