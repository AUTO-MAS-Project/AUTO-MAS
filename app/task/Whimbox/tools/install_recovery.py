#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""奇想盒未完成 pip 安装的单次交互选择；无前端或超时均不修改现场。"""

import asyncio
from pathlib import Path
from uuid import uuid4

from app.core import Dispatcher, Publisher
from app.core.ws import protocol

from .update import WhimboxUpdateUnsafeError, installed_version, pending_marker

_TIMEOUT_SECONDS = 120


async def ask_install_recovery(
    task_id: str,
    root: Path,
    *,
    managed_name: str,
    takeover_enabled: bool,
) -> tuple[str, bytes]:
    marker = pending_marker(root)
    if marker.is_symlink() or not marker.is_file():
        raise WhimboxUpdateUnsafeError("奇想盒安装标记不是普通文件，拒绝恢复")
    snapshot = await asyncio.to_thread(marker.read_bytes)
    if len(snapshot) > 512:
        raise WhimboxUpdateUnsafeError("奇想盒安装记录无效，不能自动恢复")
    try:
        target = snapshot.decode("utf-8").strip()[:64] or "未知"
    except UnicodeDecodeError:
        target = "未知"
    try:
        installed = str(await installed_version(root))
    except Exception:
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
        protocol.ID_TASK_MANAGER, protocol.WHIMBOX_INSTALL_DECISION, receive
    )
    try:
        sent = await Publisher.send(
            id=protocol.ID_TASK_MANAGER,
            type=protocol.WHIMBOX_INSTALL_PROMPT,
            data={
                "requestId": request_id,
                "taskId": task_id,
                "managedName": managed_name,
                "installPath": str(root.resolve()),
                "takeoverEnabled": takeover_enabled,
                "installedVersion": installed,
                "targetVersion": target,
            },
        )
        if not sent:
            raise WhimboxUpdateUnsafeError(
                "奇想盒上次安装未完成；请连接 MAS 主界面后选择恢复方式"
            )
        try:
            action = await asyncio.wait_for(future, timeout=_TIMEOUT_SECONDS)
        except TimeoutError as error:
            raise WhimboxUpdateUnsafeError(
                "奇想盒安装恢复选择超时；未修改安装状态"
            ) from error
        if action == "stop":
            raise WhimboxUpdateUnsafeError("已取消奇想盒安装恢复；未修改安装状态")
        if (
            marker.is_symlink()
            or not marker.is_file()
            or await asyncio.to_thread(marker.read_bytes) != snapshot
        ):
            raise WhimboxUpdateUnsafeError("奇想盒安装标记在选择期间发生变化")
        return action, snapshot
    finally:
        unregister()
        try:
            await Publisher.send(
                id=protocol.ID_TASK_MANAGER,
                type=protocol.WHIMBOX_INSTALL_PROMPT_CLOSED,
                data={"requestId": request_id},
            )
        except Exception:
            pass
