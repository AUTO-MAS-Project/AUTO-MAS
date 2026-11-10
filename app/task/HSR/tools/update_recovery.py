# Copyright © 2025-2026 AUTO-MAS Team
# SPDX-License-Identifier: AGPL-3.0-or-later
"""HSR 双引擎失败事务回滚的单次交互，不允许跳过不安全的日志。"""

import asyncio
from pathlib import Path
from uuid import uuid4

from app.core import Dispatcher, Publisher
from app.core.ws import protocol

from .update.apply import journal_path

_TIMEOUT_SECONDS = 120


async def ask_rollback_recovery(
    task_id: str,
    root: Path,
    *,
    engine: str,
    managed_name: str,
    failure: str,
) -> str:
    if engine not in ("M7A", "SRA"):
        raise ValueError("HSR 恢复引擎无效")
    journal = journal_path(root)
    if journal.is_symlink() or not journal.is_file():
        raise RuntimeError("HSR 原回滚记录不存在或不安全，保留现场并停止")

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
        protocol.ID_TASK_MANAGER, protocol.HSR_ROLLBACK_DECISION, receive
    )
    try:
        sent = await Publisher.send(
            id=protocol.ID_TASK_MANAGER,
            type=protocol.HSR_ROLLBACK_PROMPT,
            data={
                "requestId": request_id,
                "taskId": task_id,
                "managedName": managed_name,
                "installPath": str(root.resolve()),
                "engine": engine,
                "failure": failure[:500],
            },
        )
        if not sent:
            raise RuntimeError("HSR 回滚失败，需连接 MAS 主界面选择再次尝试")
        try:
            choice = await asyncio.wait_for(future, timeout=_TIMEOUT_SECONDS)
        except TimeoutError as error:
            raise RuntimeError("HSR 恢复选择超时；安装备份保留") from error
        if choice == "stop":
            raise RuntimeError("用户取消 HSR 安装回滚")
        if journal.is_symlink() or not journal.is_file():
            raise RuntimeError("HSR 回滚记录已丢失，不能确认安全")
        return choice
    finally:
        unregister()
        try:
            await Publisher.send(
                id=protocol.ID_TASK_MANAGER,
                type=protocol.HSR_ROLLBACK_CLOSED,
                data={"requestId": request_id},
            )
        except Exception:
            pass
