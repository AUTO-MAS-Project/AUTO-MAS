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
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

import psutil

from app.utils import ProcessManager, get_logger
from app.utils.io import read_dict_file, write_file
from app.utils.mirrorchyan import (
    check_mirrorchyan_update,
    compare_mirrorchyan_versions,
)

logger = get_logger("MaaEnd 更新接管")

_UPDATE_SESSION_TIMEOUT = 30 * 60
_PROCESS_STOP_TIMEOUT = 8
_LOG_MARKERS_SUCCESS = ("更新安装完成", "update installation completed")
_LOG_MARKERS_FAILURE = (
    "更新安装失败",
    "打开安装程序失败",
    "兜底更新也失败",
    "update installation failed",
)


class MaaEndUpdateError(RuntimeError):
    """MaaEnd 更新接管未能确认更新完成。"""


def _read_interface_update_info(root_path: Path) -> tuple[str, str]:
    interface = read_dict_file(root_path / "interface.json", format=".json5")
    version = str(interface.get("version") or "").strip()
    resource_id = str(interface.get("mirrorchyan_rid") or "").strip()
    if not version:
        raise MaaEndUpdateError("interface.json 未声明 version")
    if not resource_id:
        raise MaaEndUpdateError("interface.json 未声明 mirrorchyan_rid")
    return version, resource_id


def _get_update_channel(config: dict[str, object]) -> str:
    settings = config.get("settings", {})
    if not isinstance(settings, dict):
        raise MaaEndUpdateError("MXU 配置中的 settings 不是对象")
    mirror_settings = settings.get("mirrorChyan", {})
    if not isinstance(mirror_settings, dict):
        raise MaaEndUpdateError("MXU 配置中的 Mirror酱设置不是对象")
    # 频道校验统一交给通用 Mirror酱检查工具。
    return str(mirror_settings.get("channel") or "stable").strip().lower()


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
    # 当前 MXU 每次启动生成 debug/YYYY-MM-DD-N.log；兼容旧的 MXU-*.log。
    files = set((root_path / "debug").glob("????-??-??-*.log"))
    for directory in (
        root_path,
        root_path / "debug",
        root_path / "logs",
        root_path / "log",
        root_path / "cache" / "logs",
    ):
        files.update(
            path
            for path in directory.glob("*.log")
            if path.name.casefold().startswith("mxu-")
        )
    return sorted(files)


def _read_new_mxu_logs(root_path: Path, offsets: dict[Path, int]) -> str:
    """读取本轮新增完整行，保留重启前日志和跨次写入的半行。"""
    chunks = []
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
                chunks.append(content[:end].decode("utf-8", errors="replace"))
        except FileNotFoundError:
            continue  # MXU 可能在清理旧日志。
    return "\n".join(chunks).casefold()


async def _run_update_session(
    root_path: Path,
    target_version: str,
    on_status: Callable[[str], None] | None,
) -> str:
    executable = root_path / "MaaEnd.exe"
    config_path = root_path / "config" / "mxu-MaaEnd.json"
    process_manager = ProcessManager()
    deadline = time.monotonic() + _UPDATE_SESSION_TIMEOUT

    def status(message: str) -> None:
        logger.info(message)
        if on_status is not None:
            on_status(message)

    status("正在准备 MaaEnd 更新会话")
    await _stop_mxu(executable)
    log_offsets = {path: path.stat().st_size for path in _mxu_log_files(root_path)}
    with _pause_auto_run(config_path):
        try:
            launched_at = time.time()
            await process_manager.open_process(executable, cwd=root_path)
            first_process = process_manager.process
            if first_process is None:
                raise MaaEndUpdateError("MaaEnd 更新进程未启动")

            status("MaaEnd 正在检查并安装更新")
            installation_complete = False
            while time.monotonic() < deadline:
                # 安装结果写在旧进程日志中，必须从启动起持续读取，不能只读重启后的最新文件。
                new_text = await asyncio.to_thread(
                    _read_new_mxu_logs, root_path, log_offsets
                )
                if any(marker in new_text for marker in _LOG_MARKERS_FAILURE):
                    raise MaaEndUpdateError("MXU 日志报告更新失败")
                installation_complete |= any(
                    marker in new_text for marker in _LOG_MARKERS_SUCCESS
                )
                if first_process.returncode is not None and installation_complete:
                    processes = await asyncio.to_thread(
                        _find_executable_processes, executable
                    )
                    for process in processes:
                        with suppress(psutil.NoSuchProcess):
                            if (
                                process.pid != first_process.pid
                                and process.create_time() >= launched_at
                            ):
                                break
                    else:
                        await asyncio.sleep(0.5)
                        continue

                    # 临时复用上游日志；MXU 提供更新退出码后替换此判断。
                    installed_version, _ = _read_interface_update_info(root_path)
                    if (
                        compare_mirrorchyan_versions(installed_version, target_version)
                        < 0
                    ):
                        raise MaaEndUpdateError(
                            f"MXU 安装已完成，但 PI 版本未达到 {target_version}（当前 {installed_version}）"
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


async def check_and_update_maaend(
    root_path: Path,
    *,
    on_status: Callable[[str], None] | None = None,
) -> str | None:
    """启动 MaaEnd 自动代理前检查并接管需要的 MXU 更新。

    返回 ``None`` 表示无需更新；需要更新时返回最终安装的
    PI 版本号。
    """

    current_version, resource_id = _read_interface_update_info(root_path)
    config_path = root_path / "config" / "mxu-MaaEnd.json"
    mxu_config = read_dict_file(config_path, format=".json5")
    channel = _get_update_channel(mxu_config)

    if on_status is not None:
        on_status(f"正在检查 MaaEnd 更新（{channel}）")
    update = await check_mirrorchyan_update(
        resource_id,
        current_version,
        channel=channel,
        user_agent="MXU",
    )
    logger.info(
        f"Mirror酱 版本检查: 本地 {current_version}，"
        f"远端 {update.latest_version}，"
        f"频道 {channel}，需更新={update.has_update}"
    )
    if not update.has_update:
        if on_status is not None:
            on_status("MaaEnd 已是最新版本，准备运行任务")
        return None

    if on_status is not None:
        on_status(f"检测到 MaaEnd 新版本 {update.latest_version}，正在接管 MXU 更新")
    return await _run_update_session(root_path, update.latest_version, on_status)
