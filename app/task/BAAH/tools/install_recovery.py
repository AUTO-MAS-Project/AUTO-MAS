# Copyright © 2025-2026 AUTO-MAS Team
# SPDX-License-Identifier: AGPL-3.0-or-later
"""BAAH 损坏安装恢复：只能明确重装，绝不忽略未知文件完整性。"""

import asyncio
from pathlib import Path
from uuid import uuid4

from app.core import Dispatcher, Publisher
from app.core.ws import protocol
from app.services import script_install

from . import program_update

_TIMEOUT_SECONDS = 120


async def ask_install_recovery(
    task_id: str,
    root: Path,
    *,
    managed_name: str,
    takeover_enabled: bool,
) -> tuple[str, bytes]:
    receipt = script_install.record_path(root, "installed.json")
    if receipt.is_symlink() or not receipt.is_file():
        raise script_install.InstallUnsafeError("BAAH 校验回执缺失或不安全，拒绝自动修复")
    snapshot = await asyncio.to_thread(receipt.read_bytes)
    program_update.verify_recovery_receipt(root, snapshot)
    try:
        current = str(await asyncio.to_thread(program_update.read_version, root))
    except (OSError, ValueError, TypeError, KeyError):
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
        protocol.ID_TASK_MANAGER, protocol.BAAH_INSTALL_DECISION, receive
    )
    try:
        sent = await Publisher.send(
            id=protocol.ID_TASK_MANAGER,
            type=protocol.BAAH_INSTALL_PROMPT,
            data={
                "requestId": request_id,
                "taskId": task_id,
                "managedName": managed_name,
                "installPath": str(root.resolve()),
                "takeoverEnabled": takeover_enabled,
                "installedVersion": current,
                "targetVersion": "官方通道最新完整包",
            },
        )
        if not sent:
            raise script_install.InstallUnsafeError(
                "BAAH 安装需要修复，请打开 MAS 主界面选择重新安装"
            )
        try:
            action = await asyncio.wait_for(future, _TIMEOUT_SECONDS)
        except TimeoutError as error:
            raise script_install.InstallUnsafeError(
                "BAAH 修复确认超时，未修改安装文件"
            ) from error
        if action == "stop":
            raise script_install.InstallUnsafeError("用户取消 BAAH 安装修复")
        program_update.verify_recovery_receipt(root, snapshot)
        return action, snapshot
    finally:
        unregister()
        try:
            await Publisher.send(
                id=protocol.ID_TASK_MANAGER,
                type=protocol.BAAH_INSTALL_PROMPT_CLOSED,
                data={"requestId": request_id},
            )
        except Exception:
            pass
