#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""BetterGI 未确认本体安装的交互恢复。

等待选择时持有专项原有安装锁；没有前端、超时、取消或连接丢失都不默认放行。
本模块只收集一次显式决定，实际清除标记及重新安装仍由专项执行并复核。
"""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from app.core import Dispatcher, Publisher
from app.core.ws import protocol
from app.services import script_install
from app.utils import get_logger

from . import program_update

logger = get_logger("BetterGI 安装恢复")
_PROMPT_TIMEOUT_SECONDS = 120


async def ask_install_recovery(
    task_id: str,
    root: Path,
    *,
    channel: str,
    takeover_enabled: bool,
) -> tuple[str, bytes]:
    """返回 (retry/skip, 原标记字节)，让后续操作对同一份安装记录做乐观校验。"""
    marker = script_install.workspace(root) / "bgi-install.json"
    snapshot = await asyncio.to_thread(marker.read_bytes)
    if len(snapshot) > 64 * 1024:
        raise script_install.InstallUnsafeError("BetterGI 安装标记异常，请手动检查安装状态")
    try:
        content = json.loads(snapshot)
        target = str(content.get("target", "未知"))[:64] if isinstance(content, dict) else "未知"
    except (ValueError, UnicodeDecodeError):
        target = "未知"

    try:
        installed = str(await asyncio.to_thread(program_update.read_version, root))
    except (OSError, ValueError, ImportError, IndexError, KeyError):
        installed = "未知"

    request_id = uuid4().hex
    future: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    def receive(envelope) -> None:
        data = envelope.data
        if (
            data.get("requestId") == request_id
            and data.get("taskId") == task_id
            and data.get("action") in ("retry", "skip", "stop")
            and not future.done()
        ):
            future.set_result(data["action"])

    unregister = Dispatcher.register(
        protocol.ID_TASK_MANAGER, protocol.BETTERGI_INSTALL_DECISION, receive
    )
    try:
        sent = await Publisher.send(
            id=protocol.ID_TASK_MANAGER,
            type=protocol.BETTERGI_INSTALL_PROMPT,
            data={
                "requestId": request_id,
                "taskId": task_id,
                "channel": channel,
                "takeoverEnabled": takeover_enabled,
                "installedVersion": installed,
                "targetVersion": target,
            },
        )
        if not sent:
            raise script_install.InstallUnsafeError(
                "BetterGI 上次安装未确认；未连接主界面，无法获取恢复选择，请打开 MAS 界面重试"
            )
        logger.warning(
            f"BetterGI 安装未确认，等待用户选择：当前={installed}，"
            f"原目标={target}，通道={channel}，自动接管={takeover_enabled}"
        )
        try:
            action = await asyncio.wait_for(future, timeout=_PROMPT_TIMEOUT_SECONDS)
        except TimeoutError as error:
            raise script_install.InstallUnsafeError(
                "BetterGI 安装恢复选择超时，本次任务已停止；未修改安装标记"
            ) from error
        if action == "stop":
            raise script_install.InstallUnsafeError(
                "用户取消 BetterGI 安装恢复，本次任务已停止；未修改安装标记"
            )
        if not marker.is_file() or await asyncio.to_thread(marker.read_bytes) != snapshot:
            raise script_install.InstallUnsafeError(
                "BetterGI 安装状态在等待选择时发生变化，本次任务已停止，请重新检查"
            )
        logger.warning(f"用户选择 BetterGI 安装恢复操作：{action}")
        return action, snapshot
    finally:
        unregister()
        # 让超时、手动停止及任务取消的旧弹窗失效；迟到回复不会再被接受。
        try:
            await Publisher.send(
                id=protocol.ID_TASK_MANAGER,
                type=protocol.BETTERGI_INSTALL_PROMPT_CLOSED,
                data={"requestId": request_id},
            )
        except Exception:
            logger.warning("发送 BetterGI 安装恢复弹窗关闭通知失败")
