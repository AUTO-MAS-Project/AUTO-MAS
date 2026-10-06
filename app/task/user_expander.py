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

#   Contact: DLmaster_361@163.com

"""用户展开层：``UserExpander``（设计 §2.3 / §5.5）。

四层任务的第三层：对单个热态脚本算出运行用户集合，逐条加 X（级联），
再逐用户 spawn ``ModeWorker``。插件只实现 ``check`` / ``prepare``。
``prepare`` 只允许写运行集合内的用户（框架不强制）。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, ClassVar
from uuid import UUID

from app.config import DeletedNodeError
from app.models.task import TaskMode
from app.task.base import TaskBase
from app.task.mode_worker import MODE_WORKERS, ModeWorker
from app.task.params import is_selected
from app.utils import get_logger

if TYPE_CHECKING:
    from app.config import LockTicket
    from app.models.config import ScriptEntry, UserEntry
    from app.models.task import TaskItem, TaskScriptItem
    from app.plugin.base.game import DeviceHandle, GameControl
    from app.task.context import TaskContext

logger = get_logger("用户展开")

__all__ = ["UserExpander"]


class UserExpander(TaskBase):
    """单脚本入口：算运行集合、逐条用户锁、逐用户派 Worker。"""

    supported_modes: ClassVar[tuple[TaskMode, ...]] = (
        TaskMode.AUTO_PROXY,
        TaskMode.MANUAL_REVIEW,
        TaskMode.SCRIPT_CONFIG,
    )
    mode_workers: ClassVar[dict[TaskMode, type[ModeWorker]]] = MODE_WORKERS

    def __init__(
        self,
        *,
        task_context: TaskContext | None = None,
        script_item: TaskScriptItem | None = None,
        script_entry: ScriptEntry | None = None,
        game: tuple[GameControl, LockTicket, DeviceHandle | None] | None = None,
    ) -> None:
        super().__init__()
        self.task_context = task_context
        self.script_item = script_item
        self.script_entry = script_entry
        self.game = game
        self._user_tickets: list[tuple[UserEntry, LockTicket]] = []
        self._check_result: str = "Pass"

    @property
    def task_item(self) -> TaskItem | None:
        """经 ScriptItem → scripts Collection → TaskItem 取上层任务条目。"""
        from app.models.task import TaskItem

        script = self.script_item
        if script is None:
            return None
        scripts_col = script.parent
        if scripts_col is None:
            return None
        parent = scripts_col.parent
        return parent if isinstance(parent, TaskItem) else None

    async def check(self) -> str:
        """返回 ``Pass`` 或用户可读错误串。"""
        return "Pass"

    async def prepare(self) -> None:
        """专项资源准备；插件覆盖。不加锁、不建用户列表。"""

    def expand_users(
        self, *, mode: TaskMode, enabled_user_ids: list[str]
    ) -> list[str]:
        """按 §5.5 真值表收窄运行用户 uid 列表。只读，不加锁。"""
        ctx = self.task_context
        task = self.task_item
        queue_id = ctx.queue_id if ctx is not None else (
            task.info.queue_id if task is not None else None
        )
        script_id = ctx.script_id if ctx is not None else (
            task.info.script_id if task is not None else None
        )
        user_id = ctx.user_id if ctx is not None else (
            task.info.user_id if task is not None else None
        )
        has_q, has_s, has_u = (
            is_selected(queue_id),
            is_selected(script_id),
            is_selected(user_id),
        )
        if mode == TaskMode.SCRIPT_CONFIG:
            return [str(user_id)] if has_u else []
        entry = self.script_entry
        if (
            has_q
            and has_s
            and has_u
            and entry is not None
            and str(entry.uid) == str(script_id)
        ):
            return enabled_user_ids[enabled_user_ids.index(str(user_id)) :]
        if not has_q and has_u:
            return [str(user_id)]
        return enabled_user_ids

    async def on_crash(self, exc: BaseException) -> None:
        try:
            logger.exception(f"用户展开层崩溃：{exc}")
        except Exception:
            pass

    async def main_task(self) -> None:
        from app.models.task import TaskUserItem

        self._check_result = await self.check()
        if self._check_result != "Pass":
            if self.script_item is not None:
                self.script_item.info.status = f"check_fail:{self._check_result}"
                await self.script_item.commit()
            return

        entry = self.script_entry
        if entry is None:
            raise RuntimeError("UserExpander 缺少 script_entry")
        ctx = self.task_context
        mode: TaskMode = ctx.mode if ctx is not None else TaskMode.AUTO_PROXY
        if mode not in self.supported_modes:
            raise RuntimeError(f"脚本不支持模式 {mode}")
        worker_cls = self.mode_workers.get(mode)
        if worker_cls is None:
            raise RuntimeError(f"模式 {mode} 未登记 ModeWorker 类")

        # 先只读算出运行集合，再逐条加锁（集合节点不加锁）
        enabled = [
            str(uid)
            for uid, user in entry.users.items()
            if getattr(user.info, "enabled", True)
        ]
        user_ids = self.expand_users(mode=mode, enabled_user_ids=enabled)

        # ScriptConfig 与用户列表无关：跳过用户锁，前端可改 users
        if mode != TaskMode.SCRIPT_CONFIG:
            locked: list[str] = []
            for uid_s in user_ids:
                uid = UUID(uid_s)
                if uid not in entry.users:
                    continue
                user = entry.users[uid]
                while True:
                    try:
                        ticket = await user.try_lock_x(cascade=True)
                    except (KeyError, DeletedNodeError):
                        ticket = None
                        break
                    if ticket is not None:
                        self._user_tickets.append((user, ticket))
                        locked.append(uid_s)
                        break
                    if uid not in entry.users:
                        break
                    await asyncio.sleep(1)
            user_ids = locked

        await self.prepare()

        if self.script_item is None:
            return

        for old in list(self.script_item.users.keys()):
            self.script_item.users.remove(old)
        for uid_s in user_ids:
            uid = UUID(uid_s)
            live = entry.users.get(uid)
            name = live.info.name if live is not None else uid_s
            self.script_item.users.add(
                TaskUserItem,
                uid=uid,
                payload={"info": {"name": name, "status": "pending"}},
            )
        await self.script_item.users.commit()

        for uid_s in user_ids:
            uid = UUID(uid_s)
            if uid not in entry.users:
                continue
            self.script_item.current.index = uid
            await self.script_item.commit()
            await self.spawn(
                worker_cls(
                    user_entry=entry.users[uid],
                    script_item=self.script_item,
                    script_entry=entry,
                )
            )

        self.script_item.current.index = None
        await self.script_item.commit()
        await self._release()

    async def _release(self) -> None:
        """提交在途写入后逐条解锁；可重复调用。"""
        while self._user_tickets:
            user, ticket = self._user_tickets.pop()
            try:
                await user.commit()
            except Exception:
                logger.exception(f"用户 {user.uid} 收尾 commit 失败")
            try:
                await user.unlock(ticket)
            except Exception:
                logger.exception(f"用户 {user.uid} 解锁失败")

    async def final_task(self) -> None:
        if self._check_result != "Pass":
            return
        await self._release()
