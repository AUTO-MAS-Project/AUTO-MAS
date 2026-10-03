#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


import asyncio
import os
import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path

import psutil

from app.utils import ProcessManager, get_logger
from app.utils.io import read_dict_file, write_file
from app.utils.mirrorchyan import compare_mirrorchyan_versions

logger = get_logger("MaaEnd 更新接管")

_UPDATE_SESSION_TIMEOUT = 30 * 60
_PROCESS_STOP_TIMEOUT = 8
_PROCESS_RESTART_TIMEOUT = 30
_LOG_FILE_NAME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}-[1-9][0-9]*\.log")
_LOG_TARGET_VERSION = re.compile(
    r"(?:发现新版本|检测到待安装更新|已保存待安装更新信息):\s*(\S+)"
)
_LOG_DOWNLOAD = ("开始下载更新:", "更新下载完成")
_LOG_DOWNLOAD_READY = ("已保存待安装更新信息:", "检测到待安装更新:")
_LOG_SUCCESS = "更新安装完成"
_LOG_FAILURE = ("更新安装失败", "打开安装程序失败")
_LOG_CHECK_FAILURE = (
    "更新下载失败",
    "更新下载出错",
    "检查更新失败:",
    "更新检查返回错误:",
    "GitHub 下载链接获取失败",
    "下载失败:",
    "保存待安装更新信息失败:",
)


class MaaEndUpdateError(RuntimeError):
    """MaaEnd 更新接管未能确认更新完成。"""


@dataclass
class _UpdateProgress:
    """按本轮日志顺序保留 MXU 最后报告的更新结果。"""

    state: str = "idle"
    target_version: str | None = None

    def read(self, lines: list[str]) -> None:
        for line in lines:
            if match := _LOG_TARGET_VERSION.search(line):
                candidate = match.group(1)
                if (
                    self.target_version is None
                    or compare_mirrorchyan_versions(candidate, self.target_version) > 0
                ):
                    self.target_version = candidate
            if any(message in line for message in _LOG_FAILURE):
                self.state = "install_failed"
            elif _LOG_SUCCESS in line:
                self.state = "complete"
            elif "开始安装更新:" in line:
                self.state = "installing"
            elif "开始下载更新:" in line:
                self.state = "downloading"
            elif self.state not in {"installing", "complete", "install_failed"}:
                if "下载已被用户取消" in line:
                    self.state = "cancelled"
                elif any(message in line for message in _LOG_CHECK_FAILURE):
                    if self.state != "cancelled":
                        self.state = "failed"
                elif any(message in line for message in _LOG_DOWNLOAD_READY):
                    self.state = "ready"
                elif "更新下载完成" in line:
                    # 此行先于待安装信息落盘，尚不能关闭下载进程。
                    self.state = "downloaded"
                elif "更新检查完成:" in line and "有更新=false" in line:
                    self.state = "current"


def _read_installed_version(root_path: Path, target_version: str | None) -> str:
    interface = read_dict_file(root_path / "interface.json", format=".json5")
    version = str(interface.get("version") or "").strip()
    if not version:
        raise MaaEndUpdateError("interface.json 未声明 version")
    if target_version and compare_mirrorchyan_versions(version, target_version) < 0:
        raise MaaEndUpdateError(f"MaaEnd 更新未达到 {target_version}（当前 {version}）")
    return version


@contextmanager
def _pause_auto_run(config_path: Path) -> Iterator[None]:
    """临时关闭自动执行；退出时只还原此字段，保留 MXU 写入的其它设置。"""
    config = read_dict_file(config_path, format=".json5")
    had_settings = "settings" in config
    settings = config.setdefault("settings", {})
    if not isinstance(settings, dict):
        raise MaaEndUpdateError("MXU 配置中的 settings 不是对象")
    if settings.get("autoRunOnLaunch") is False:
        yield
        return

    original = settings.copy()
    settings["autoRunOnLaunch"] = False
    write_file(config_path, config)
    try:
        yield
    finally:
        config = read_dict_file(config_path, format=".json5")
        settings = config.setdefault("settings", {})
        if not isinstance(settings, dict):
            raise MaaEndUpdateError("MXU 配置中的 settings 不是对象")
        # 外侧修改过自动执行设置时，不覆盖该修改。
        if settings.get("autoRunOnLaunch", False) is False:
            if "autoRunOnLaunch" in original:
                settings["autoRunOnLaunch"] = original["autoRunOnLaunch"]
            else:
                settings.pop("autoRunOnLaunch", None)
            if not had_settings and not settings:
                config.pop("settings", None)
            write_file(config_path, config)


def _find_executable_processes(executable: Path) -> list[psutil.Process]:
    expected = os.path.normcase(os.path.abspath(executable))
    return [
        process
        for process in psutil.process_iter(["exe"])
        if process.info["exe"]
        and os.path.normcase(os.path.abspath(process.info["exe"])) == expected
    ]


def _terminate_processes(processes: list[psutil.Process]) -> None:
    active: list[psutil.Process] = []
    for process in processes:
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            process.terminate()
            active.append(process)
    if not active:
        return
    _, alive = psutil.wait_procs(active, timeout=_PROCESS_STOP_TIMEOUT)
    for process in alive:
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            process.kill()
    if alive:
        _, alive = psutil.wait_procs(alive, timeout=_PROCESS_STOP_TIMEOUT)
    if alive:
        raise MaaEndUpdateError("MaaEnd 进程未能退出")


async def _stop_mxu(executable: Path) -> None:
    processes = await asyncio.to_thread(_find_executable_processes, executable)
    await asyncio.to_thread(_terminate_processes, processes)
    if await asyncio.to_thread(_find_executable_processes, executable):
        raise MaaEndUpdateError("无法关闭 MaaEnd 更新会话")


def _mxu_log_files(root_path: Path) -> list[Path]:
    # MXU 前端日志：debug/YYYY-MM-DD-N.log，每次启动新建文件。
    return sorted(
        (
            path
            for path in (root_path / "debug").glob("*.log")
            if _LOG_FILE_NAME.fullmatch(path.name) and path.is_file()
        ),
        key=lambda path: (
            path.stem.rsplit("-", 1)[0],
            int(path.stem.rsplit("-", 1)[1]),
        ),
    )


def snapshot_mxu_logs(root_path: Path) -> dict[Path, int]:
    """启动首阶段前记录日志位置，避免历史下载记录触发更新。"""
    offsets: dict[Path, int] = {}
    for path in _mxu_log_files(root_path):
        with suppress(FileNotFoundError):
            offsets[path] = path.stat().st_size
    return offsets


def _read_new_mxu_logs(root_path: Path, offsets: dict[Path, int]) -> list[str]:
    """读取本轮新增完整行，保留重启前日志和跨次写入的半行。"""
    lines: list[str] = []
    for path in _mxu_log_files(root_path):
        try:
            with path.open("rb") as log_file:
                offset = offsets.get(path, 0)
                if os.fstat(log_file.fileno()).st_size < offset:
                    offset = 0
                log_file.seek(offset)
                content = log_file.read()
                end = content.rfind(b"\n") + 1
                offsets[path] = offset + end
                lines.extend(content[:end].decode("utf-8").splitlines())
        except FileNotFoundError:
            continue  # MXU 可能在清理旧日志。
    return lines


async def _run_update_session(
    root_path: Path,
    target_version: str | None,
    on_status: Callable[[str], None] | None,
) -> str | None:
    executable = root_path / "MaaEnd.exe"
    config_path = root_path / "config" / "mxu-MaaEnd.json"
    process_manager = ProcessManager()
    deadline = time.monotonic() + _UPDATE_SESSION_TIMEOUT

    def status(message: str) -> None:
        logger.info(message)
        if on_status is not None:
            on_status(message)

    status("正在准备 MaaEnd 更新会话")
    # 只在原进程自然退出后启动，不能中止仍在下载或安装的会话。
    if await asyncio.to_thread(_find_executable_processes, executable):
        raise MaaEndUpdateError("MaaEnd 原进程尚未退出，无法启动独立更新会话")
    log_offsets = await asyncio.to_thread(snapshot_mxu_logs, root_path)
    with _pause_auto_run(config_path):
        try:
            launched_at = time.time()
            await process_manager.open_process(executable, cwd=root_path)
            first_process = process_manager.process
            if first_process is None:
                raise MaaEndUpdateError("MaaEnd 更新进程未启动")

            status("MaaEnd 正在检查并安装更新")
            progress = _UpdateProgress(target_version=target_version)
            exited_at: float | None = None
            while time.monotonic() < deadline:
                await process_manager.hide_window()
                # 安装结果写在旧进程日志中，必须从启动起持续读取，不能只读重启后的最新文件。
                lines = await asyncio.to_thread(
                    _read_new_mxu_logs, root_path, log_offsets
                )
                progress.read(lines)
                if progress.state == "install_failed":
                    raise MaaEndUpdateError("MXU 日志报告更新失败")
                if progress.state in {"failed", "cancelled"}:
                    status("MaaEnd 下载失败或已取消，本轮跳过更新")
                    return None
                if progress.state == "downloading":
                    # 已下载的更新包失效时，不在阶段之间重新等待下载。
                    status("MaaEnd 需要重新下载更新包，本轮跳过更新")
                    return None
                # 首阶段可能已经完成更新；由 MXU 的检查结果确认，无需再安装一次。
                if progress.state == "current":
                    installed_version = _read_installed_version(
                        root_path, progress.target_version
                    )
                    status(f"MaaEnd 已是最新版本 {installed_version}")
                    return installed_version
                if first_process.returncode is not None:
                    if exited_at is None:
                        exited_at = time.monotonic()
                    processes = await asyncio.to_thread(
                        _find_executable_processes, executable
                    )
                    for process in processes:
                        with suppress(psutil.NoSuchProcess):
                            if (
                                process.pid != first_process.pid
                                and process.create_time() >= launched_at
                            ):
                                process_manager.target_process = process
                                await process_manager.hide_window()
                                break
                    else:
                        if time.monotonic() - exited_at >= _PROCESS_RESTART_TIMEOUT:
                            raise MaaEndUpdateError(
                                "MaaEnd 更新进程已退出，未能确认重启完成"
                            )
                        await asyncio.sleep(0.5)
                        continue

                    if progress.state != "complete":
                        await asyncio.sleep(0.5)
                        continue
                    # 临时复用上游日志；MXU 提供更新退出码后替换此判断。
                    installed_version = _read_installed_version(
                        root_path, progress.target_version
                    )
                    status(f"MaaEnd 已更新到 {installed_version}")
                    return installed_version
                await asyncio.sleep(0.5)
            raise MaaEndUpdateError("等待 MaaEnd 安装完成并重启超时")
        finally:
            # 关闭更新 GUI 后才恢复启动设置，避免新进程读到自动执行配置。
            try:
                await process_manager.kill()
            finally:
                await _stop_mxu(executable)


async def update_maaend_after_stage(
    root_path: Path,
    log_offsets: dict[Path, int],
    *,
    process: asyncio.subprocess.Process | None = None,
    on_status: Callable[[str], None] | None = None,
) -> str | None:
    """首阶段结束后按本轮下载日志插入更新，返回更新后的版本。

    未下载完成时返回 ``None``，由调用方关闭原进程并继续任务；
    仅已下载的更新包继续沿用 MXU 原生安装和重启流程。
    """
    lines = await asyncio.to_thread(_read_new_mxu_logs, root_path, log_offsets)
    if not any(
        message in line
        for line in lines
        for message in (
            *_LOG_DOWNLOAD,
            *_LOG_DOWNLOAD_READY,
            "开始安装更新:",
            _LOG_SUCCESS,
            *_LOG_FAILURE,
        )
    ):
        return None

    def status(message: str) -> None:
        logger.info(message)
        if on_status is not None:
            on_status(message)

    progress = _UpdateProgress()
    progress.read(lines)
    if progress.state == "downloading":
        status("首阶段结束时 MaaEnd 更新包尚未下载完成，本轮跳过更新")
        return None
    deadline = time.monotonic() + _UPDATE_SESSION_TIMEOUT
    status("首阶段检测到 MaaEnd 更新，正在确认安装结果")
    while True:
        if progress.state == "install_failed":
            raise MaaEndUpdateError("MXU 日志报告安装失败，已停止后续任务")
        if progress.state in {"failed", "cancelled"}:
            status("MaaEnd 下载失败或已取消，本轮跳过更新")
            return None
        if progress.state == "downloading":
            status("MaaEnd 需要重新下载更新包，本轮跳过更新")
            return None
        if progress.state in {"complete", "current"}:
            installed_version = _read_installed_version(
                root_path, progress.target_version
            )
            status(f"首阶段已完成 MaaEnd 更新：{installed_version}")
            return installed_version

        processes = await asyncio.to_thread(
            _find_executable_processes, root_path / "MaaEnd.exe"
        )
        if not processes and (process is None or process.returncode is not None):
            if progress.state == "downloaded":
                status("MaaEnd 已退出但未确认保存待安装更新，本轮跳过更新")
                return None
            # 仅为已就绪的更新接续原生安装，不重新下载未完成的更新包。
            return await _run_update_session(
                root_path=root_path,
                target_version=progress.target_version,
                on_status=on_status,
            )
        if time.monotonic() >= deadline:
            raise MaaEndUpdateError("等待 MaaEnd 原进程完成安装超时")
        await asyncio.sleep(0.5)
        progress.read(
            await asyncio.to_thread(_read_new_mxu_logs, root_path, log_offsets)
        )
