#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from __future__ import annotations
import asyncio
import weakref
from datetime import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class LogRecord:

    content: list[str] = field(default_factory=list)
    status: str = "未开始监看日志"


@dataclass
class UserItem:

    user_id: str  # 用户ID
    name: str  # 用户名称
    status: str  # 用户执行状态
    log_record: dict[datetime, LogRecord] = field(
        default_factory=dict
    )  # 用户本次代理的全部日志记录
    _task_item_ref: Optional[weakref.ReferenceType[TaskItem]] = None

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        # 监听所有字段变化
        if name in ("user_id", "name", "status") and self._task_item_ref is not None:
            ti = self._task_item_ref()
            if ti is not None:
                asyncio.create_task(ti.on_change())

    @property
    def result(self) -> str:
        """用户代理情况的简要结果"""
        if not self.log_record:
            return "未开始运行"
        return " | ".join(
            [
                f"{t.strftime('%H:%M')} - {log.status}"
                for t, log in self.log_record.items()
            ]
        )


@dataclass
class ScriptItem:

    script_id: str  # 脚本ID
    name: str  # 脚本名称
    status: str  # 脚本执行状态
    user_list: List[UserItem] = field(default_factory=list)  # 用户信息列表
    current_index: int = -1  # 当前执行的用户索引，-1 表示未开始
    log: str = ""  # 脚本执行日志
    _task_item_ref: Optional[weakref.ReferenceType[TaskItem]] = None

    def __setattr__(self, name, value):
        super().__setattr__(name, value)

        # 如果 user_list 被整体替换，重新绑定
        if name == "user_list" and self.task_info is not None:
            for user in self.user_list:
                object.__setattr__(user, "_task_item_ref", self._task_item_ref)

        if name not in ("_task_item_ref",) and self.task_info is not None:
            asyncio.create_task(self.task_info.on_change())

    @property
    def task_info(self) -> Optional[TaskItem]:
        """返回绑定到此 ScriptItem 的父 TaskItem"""
        if self._task_item_ref is None:
            return None
        return self._task_item_ref()

    @property
    def result(self) -> str:
        """脚本代理情况的简要结果"""

        if not self.user_list:
            return "用户未加载"
        return "\n".join([f"{user.name}：{user.result}" for user in self.user_list])


@dataclass
class TaskItem(ABC):
    """任务信息基类，管理任务的信息和脚本列表"""

    mode: str  # 任务模式
    task_id: str  # 任务唯一标识符
    queue_id: str | None  # 执行的队列ID
    script_id: str | None  # 执行的脚本ID
    user_id: str | None  # 执行的用户ID
    script_list: List[ScriptItem] = field(default_factory=list)  # 脚本信息列表
    current_index: int = -1  # 当前执行的脚本索引，-1 表示未开始

    def __setattr__(self, name, value):
        super().__setattr__(name, value)

        # 如果 script_list 被整体替换，重新绑定
        if name == "script_list":
            for item in self.script_list:
                self._bind_task_item(item)

    def _bind_task_item(self, item: ScriptItem):
        """绑定 TaskItem 及其内部所有 UserItem 到当前 TaskItem"""
        ti_ref = weakref.ref(self)
        object.__setattr__(item, "_task_item_ref", ti_ref)
        # 绑定 user_list 中的每个 UserItem
        for user in item.user_list:
            object.__setattr__(user, "_task_item_ref", ti_ref)

    @abstractmethod
    async def on_change(self):
        """统一回调入口"""
        raise NotImplementedError("子类必须实现 on_change")

    @property
    def asdict(self) -> list:
        """将 TaskItem 转换为字典形式"""
        return [
            {
                "name": script_item.name,
                "status": script_item.status,
                "userList": [
                    {
                        "name": user_item.name,
                        "status": user_item.status,
                    }
                    for user_item in script_item.user_list
                ],
            }
            for script_item in self.script_list
        ]

    @property
    def result(self) -> str:
        """任务执行情况的简要结果"""

        if not self.script_list:
            return "任务未加载"
        return "\n\n\n".join(
            [
                f"{script.name}：\n\n"
                f"    已完成用户数：{sum(1 for user in script.user_list if user.status == '完成')}；未完成用户数：{sum(1 for user in script.user_list if user.status != '完成')}\n\n"
                f"    {script.result.replace('\n', '\n    ')}"
                for script in self.script_list
            ]
        )


@dataclass
class TaskExecuteBase(ABC):
    task: asyncio.Task | None = None
    _task_group: asyncio.TaskGroup | None = None
    accomplish: asyncio.Event = field(default_factory=asyncio.Event)

    @abstractmethod
    async def main_task(self): ...
    @abstractmethod
    async def final_task(self): ...
    @abstractmethod
    async def on_crash(self, e): ...

    async def _execute_task(self, parent_tg: asyncio.TaskGroup):
        self._task_group = parent_tg
        try:
            await self.main_task()
        except Exception as e:
            await self.on_crash(e)
            raise
        finally:
            self._task_group = None
            try:
                await asyncio.shield(self.final_task())
            except Exception as e:
                await self.on_crash(e)
            finally:
                self.accomplish.set()

    def spawn(self, child: TaskExecuteBase) -> asyncio.Task:
        if self._task_group is None:
            raise RuntimeError("子任务必须在主任务中启动")
        return self._task_group.create_task(child._execute_task(self._task_group))

    def execute(self):
        if self.task is not None and not self.task.done():
            raise RuntimeError("任务已在运行")

        if self._task_group is not None:
            raise RuntimeError("execute() 仅可由顶层任务调用，子任务请使用 spawn()")

        async def _root_coro():
            async with asyncio.TaskGroup() as tg:
                self.task = tg.create_task(self._execute_task(tg))

        self.task = asyncio.create_task(_root_coro())

    def cancel(self) -> bool:
        if self.task is None or self.task.done():
            return False
        return self.task.cancel()
