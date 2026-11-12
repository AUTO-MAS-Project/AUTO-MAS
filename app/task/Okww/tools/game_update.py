#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""让官方启动器检查、下载与应用鸣潮更新，不解释游戏私有资源清单。"""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.services import wuthering_waves
from app.task.proxy_helpers import kill_pids
from app.utils import ProcessManager, get_logger

from . import launcher_start

logger = get_logger("鸣潮官方更新")


async def update_game_via_launcher(
    launcher_path: Path,
    *,
    client_path: Path | None = None,
    quality: str | None = None,
    on_progress: Callable[[str], Awaitable[None]],
) -> str | None:
    """等待官方启动器就绪；不启动游戏，结束时清理本次拉起的启动器。"""
    if not launcher_path.is_file() or launcher_path.name.lower() != "launcher.exe":
        raise RuntimeError("请先导入有效的鸣潮官方启动器以检查游戏更新")
    selected_quality = wuthering_waves.read_wuthering_waves_launcher_selection(
        launcher_path
    )
    if (
        quality is not None
        and selected_quality is not None
        and quality != selected_quality
    ):
        raise RuntimeError(
            "启动参数与启动器资源档位不同，请先在官方启动器切换到对应档位"
        )
    install_dir = wuthering_waves.resolve_wuthering_waves_install_dir(launcher_path)
    if client_path is None:
        # 更新中断时客户端可能尚未落盘，仍须让启动器完成更新或修复。
        client_path = install_dir / "Client/Binaries/Win64/Client-Win64-Shipping.exe"
    if not client_path.resolve().is_relative_to(install_dir.resolve()):
        raise RuntimeError("游戏客户端与官方启动器指向不同安装，请重新选择对应的启动器")
    if await asyncio.to_thread(
        launcher_start.find_client_pids, client_path, launcher_path
    ):
        raise RuntimeError("鸣潮正在运行，请关闭游戏后再检查更新")

    existing_pids = set(
        await asyncio.to_thread(launcher_start.find_launcher_pids, launcher_path)
    )
    manager = ProcessManager()
    loop = asyncio.get_running_loop()

    def push_log(line: str) -> None:
        # 等待交付完成，后台线程结束后不会有晚到日志污染下一个账号。
        asyncio.run_coroutine_threadsafe(on_progress(line), loop).result()

    try:
        await on_progress("正在通过官方启动器检查鸣潮更新...")
        if not await asyncio.to_thread(
            launcher_start.has_launcher_window, launcher_path
        ):
            await manager.open_process(launcher_path)
        await launcher_start.async_start_game_via_launcher(
            launcher_path, on_log=push_log, update_only=True
        )
        final_quality = wuthering_waves.read_wuthering_waves_launcher_selection(
            launcher_path
        )
        if final_quality != selected_quality:
            raise RuntimeError(
                "更新期间资源档位已改变，请确认启动器档位与客户端路径后重试"
            )
        await on_progress("官方启动器已就绪，鸣潮更新检查完成")
        return final_quality
    finally:
        # 只清理本次启动的进程，保留用户原先打开的启动器。
        try:
            await manager.kill()
        finally:
            current_pids = await asyncio.to_thread(
                launcher_start.find_launcher_pids, launcher_path
            )
            failed = await kill_pids(
                pid for pid in current_pids if pid not in existing_pids
            )
            if failed:
                logger.warning("有 {} 个鸣潮启动器进程未能关闭，请手动确认", failed)
