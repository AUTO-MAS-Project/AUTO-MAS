# Copyright © 2025-2026 AUTO-MAS Team
# SPDX-License-Identifier: AGPL-3.0-or-later

"""SRC 上次 Git + 原生依赖安装未完成的单次明确选择。"""

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
    marker = script_install.workspace(root) / "src-install.json"
    if marker.is_symlink() or not marker.is_file():
        raise script_install.InstallUnsafeError("SRC 安装恢复记录不是普通文件")
    snapshot = await asyncio.to_thread(marker.read_bytes)
    if len(snapshot) > 64 * 1024:
        raise script_install.InstallUnsafeError("SRC 安装记录过大，拒绝恢复")
    try:
        target = program_update.validate_install_marker(root, snapshot)[:12]
    except script_install.InstallUnsafeError:
        target = "未知"
    try:
        deploy = await asyncio.to_thread(program_update.read_deploy, root)
        git = program_update.git_executable(root, deploy)
        current = (
            await program_update.command(git, "rev-parse", "HEAD", cwd=root)
        )[:12]
    except Exception:
        current = "未知"

    request_id = uuid4().hex
    future: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    def receive(envelope) -> None:
        data = envelope.data
        if (
            data.get("taskId") == task_id
            and data.get("requestId") == request_id
            and data.get("action") in ("retry", "skip", "stop")
            and not future.done()
        ):
            future.set_result(data["action"])

    unregister = Dispatcher.register(
        protocol.ID_TASK_MANAGER, protocol.SRC_INSTALL_DECISION, receive
    )
    try:
        sent = await Publisher.send(
            id=protocol.ID_TASK_MANAGER,
            type=protocol.SRC_INSTALL_PROMPT,
            data={
                "requestId": request_id,
                "taskId": task_id,
                "managedName": managed_name,
                "installPath": str(root.resolve()),
                "takeoverEnabled": takeover_enabled,
                "installedVersion": current,
                "targetVersion": target,
            },
        )
        if not sent:
            raise script_install.InstallUnsafeError(
                "SRC 上次安装尚未确认；请连接 MAS 主界面后选择恢复方式"
            )
        try:
            action = await asyncio.wait_for(future, _TIMEOUT_SECONDS)
        except TimeoutError as error:
            raise script_install.InstallUnsafeError(
                "SRC 恢复选择超时；原安装标记保持不变"
            ) from error
        if action == "stop":
            raise script_install.InstallUnsafeError(
                "用户取消 SRC 安装恢复；原安装标记保持不变"
            )
        if (
            marker.is_symlink()
            or not marker.is_file()
            or await asyncio.to_thread(marker.read_bytes) != snapshot
        ):
            raise script_install.InstallUnsafeError(
                "SRC 安装记录在等待确认时发生变化，拒绝旧请求"
            )
        return action, snapshot
    finally:
        unregister()
        try:
            await Publisher.send(
                id=protocol.ID_TASK_MANAGER,
                type=protocol.SRC_INSTALL_PROMPT_CLOSED,
                data={"requestId": request_id},
            )
        except Exception:
            pass
