# Copyright © 2025-2026 AUTO-MAS Team
# SPDX-License-Identifier: AGPL-3.0-or-later
"""MAA 资源覆盖中断后的用户决定：禁止直接忽略半更新。"""

import asyncio
from pathlib import Path
from uuid import uuid4

from app.core import Dispatcher, Publisher
from app.core.ws import protocol

from . import resource_update

_TIMEOUT_SECONDS = 120


async def ask_resource_recovery(
    task_id: str,
    root: Path,
    *,
    managed_name: str,
    takeover_enabled: bool,
) -> tuple[str, bytes]:
    marker = root / ".automas-resource-update.json"
    snapshot = await asyncio.to_thread(marker.read_bytes)
    target = resource_update.verify_resource_recovery_marker(root, snapshot)
    current = await asyncio.to_thread(resource_update.read_resource_clock, root)

    request_id = uuid4().hex
    future: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    def receive(envelope) -> None:
        data = envelope.data
        if (
            data.get("taskId") == task_id
            and data.get("requestId") == request_id
            and data.get("action") in ("retry", "stop")
            and not future.done()
        ):
            future.set_result(data["action"])

    unregister = Dispatcher.register(
        protocol.ID_TASK_MANAGER, protocol.MAA_RESOURCE_RECOVERY_DECISION, receive
    )
    try:
        sent = await Publisher.send(
            id=protocol.ID_TASK_MANAGER,
            type=protocol.MAA_RESOURCE_RECOVERY_PROMPT,
            data={
                "requestId": request_id,
                "taskId": task_id,
                "managedName": managed_name,
                "installPath": str(root.resolve()),
                "takeoverEnabled": takeover_enabled,
                "installedVersion": current.isoformat() if current else "未知",
                "targetVersion": target,
            },
        )
        if not sent:
            raise resource_update.MaaUpdateUnsafeError(
                "MAA 资源更新不完整，请连接 MAS 主界面选择修复"
            )
        try:
            action = await asyncio.wait_for(future, _TIMEOUT_SECONDS)
        except TimeoutError as error:
            raise resource_update.MaaUpdateUnsafeError(
                "MAA 资源修复选择超时，标记未修改"
            ) from error
        if action == "stop":
            raise resource_update.MaaUpdateUnsafeError(
                "用户取消 MAA 资源修复，未修改原安装"
            )
        resource_update.verify_resource_recovery_marker(root, snapshot)
        return action, snapshot
    finally:
        unregister()
        try:
            await Publisher.send(
                id=protocol.ID_TASK_MANAGER,
                type=protocol.MAA_RESOURCE_RECOVERY_CLOSED,
                data={"requestId": request_id},
            )
        except Exception:
            pass
