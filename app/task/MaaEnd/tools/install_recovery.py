# Copyright © 2025-2026 AUTO-MAS Team
# SPDX-License-Identifier: AGPL-3.0-or-later
"""MaaEnd/MXU 损坏本体的明确修复询问；事务仍由 script_install 自行恢复。"""

import asyncio
from pathlib import Path
from uuid import uuid4

from app.core import Dispatcher, Publisher
from app.core.ws import protocol
from app.services import script_install

from . import script_update

_TIMEOUT_SECONDS = 120


async def ask_install_recovery(
    task_id: str,
    root: Path,
    *,
    managed_name: str,
    takeover_enabled: bool,
) -> tuple[str, bytes]:
    identity = script_install.record_path(root, "program-identity.json")
    if identity.is_symlink() or not identity.is_file():
        raise script_install.InstallUnsafeError(
            "MaaEnd 架构记录缺失或不安全，请使用官方安装器修复"
        )
    snapshot = await asyncio.to_thread(identity.read_bytes)
    script_update.verify_repair_identity(root, snapshot)
    try:
        current = str((await asyncio.to_thread(script_update.read_install, root))[0])
    except (OSError, ValueError):
        current = "未知"

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
        protocol.ID_TASK_MANAGER, protocol.MAAEND_INSTALL_DECISION, receive
    )
    try:
        sent = await Publisher.send(
            id=protocol.ID_TASK_MANAGER,
            type=protocol.MAAEND_INSTALL_PROMPT,
            data={
                "requestId": request_id,
                "taskId": task_id,
                "managedName": managed_name,
                "installPath": str(root.resolve()),
                "takeoverEnabled": takeover_enabled,
                "installedVersion": current,
                "targetVersion": "所选通道官方完整包",
            },
        )
        if not sent:
            raise script_install.InstallUnsafeError(
                "MaaEnd 原生安装需要修复，请打开 MAS 主界面确认"
            )
        try:
            action = await asyncio.wait_for(future, _TIMEOUT_SECONDS)
        except TimeoutError as error:
            raise script_install.InstallUnsafeError(
                "MaaEnd 安装修复超时，原状态未修改"
            ) from error
        if action == "stop":
            raise script_install.InstallUnsafeError("用户取消 MaaEnd 修复")
        script_update.verify_repair_identity(root, snapshot)
        return action, snapshot
    finally:
        unregister()
        try:
            await Publisher.send(
                id=protocol.ID_TASK_MANAGER,
                type=protocol.MAAEND_INSTALL_PROMPT_CLOSED,
                data={"requestId": request_id},
            )
        except Exception:
            pass
