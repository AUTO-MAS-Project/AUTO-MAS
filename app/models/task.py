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
    status: str = "-"


@dataclass
class UserItem:

    user_id: str
    name: str
    status: str
    log_record: dict[datetime, LogRecord] = field(default_factory=dict)
    _task_item_ref: Optional[weakref.ReferenceType[TaskItem]] = None

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        # 监听所有字段变化
        if name in ("user_id", "name", "status") and self._task_item_ref is not None:
            ti = self._task_item_ref()
            if ti is not None:
                asyncio.create_task(ti.on_change())


@dataclass
class ScriptItem:

    script_id: str
    name: str
    status: str
    task_handler: TaskExecuteBase | None = None
    user_list: List[UserItem] = field(default_factory=list)
    current_index: int = -1
    log: str = ""
    result: str = "暂无"
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


@dataclass
class TaskItem(ABC):

    mode: str
    task_id: str
    queue_id: str | None
    script_id: str | None
    user_id: str | None
    task_handler: TaskExecuteBase | None = None
    script_list: List[ScriptItem] = field(default_factory=list)
    current_index: int = -1

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


@dataclass
class TaskExecuteBase(ABC):
    """任务执行基类"""

    task: asyncio.Task | None = None
    accomplish: asyncio.Event = field(default_factory=asyncio.Event)

    @abstractmethod
    async def main_task(self):
        """脚本任务主体"""
        raise NotImplementedError("子类必须实现 main_task 方法")

    @abstractmethod
    async def final_task(self):
        """脚本任务收尾工作"""
        raise NotImplementedError("子类必须实现 final_task 方法")

    @abstractmethod
    async def on_crash(self, e: Exception):
        """脚本任务崩溃处理"""
        raise NotImplementedError("子类必须实现 on_crash 方法")

    async def do_main_task(self):
        """执行脚本任务"""

        self.accomplish.clear()
        try:
            await self.main_task()
        except Exception as e:
            await self.on_crash(e)
            raise e

    async def do_final_task(self):
        """执行收尾工作"""
        try:
            await self.final_task()
        except Exception as e:
            await self.on_crash(e)
        finally:
            self.accomplish.set()

    async def execute(self):
        """执行子任务"""

        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.do_main_task())
            self.task.add_done_callback(
                lambda t: asyncio.create_task(self.do_final_task())
            )
        else:
            raise RuntimeError("任务已在运行中")

        return self.task
