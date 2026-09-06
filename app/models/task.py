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


from __future__ import annotations

import asyncio
import time
import weakref
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Literal, Optional

from app.runtime_tasks import RuntimeTasks

TaskTriggerSource = Literal[
    "scheduled_task",
    "manual_task",
    "startup_task",
]


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
    push_log: list[tuple[str, str, float]] = field(
        default_factory=list
    )  # 用户本次代理采集的推送日志，元素为 (日志类型, 格式化文本, 采集时间戳)
    push_log_mode: str = field(
        default="汇总"
    )  # 节点详情推送模式（关闭/逐条/汇总），由 AutoProxy 从用户配置注入
    _task_item_ref: Optional[weakref.ReferenceType[TaskItem]] = None

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        # 监听所有字段变化
        if name in ("user_id", "name", "status") and self._task_item_ref is not None:
            ti = self._task_item_ref()
            if ti is not None:
                ti.schedule_on_change()

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
            self.task_info.schedule_on_change()

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
        return "\n".join([f"{user.name}: {user.result}" for user in self.user_list])


@dataclass
class TaskItem(ABC):
    """任务信息基类，管理任务的信息和脚本列表"""

    # 脚本执行模式。循环运行不占用这个字段：各脚本适配器都按 mode 分派任务类
    # （METHOD_BOOK）并有近百处 == "AutoProxy" 的分支，循环里的每一轮本就是自动
    # 代理，写成 "CycleRun" 会让所有适配器 KeyError 或走错分支。循环与否见 is_cycle。
    mode: Literal["AutoProxy", "ScriptConfig", "Update"]  # 任务模式
    task_id: str  # 任务唯一标识符
    queue_id: str | None  # 执行的队列ID
    script_id: str | None  # 执行的脚本ID
    user_id: str | None  # 执行的用户ID
    script_list: List[ScriptItem] = field(default_factory=list)  # 脚本信息列表
    current_index: int = -1  # 当前执行的脚本索引，-1 表示未开始
    resume_from_script_id: str | None = None  # 可选：从指定脚本ID开始执行（仅队列任务）
    is_cycle: bool = False  # 是否为循环运行任务（按队列项各自的周期持续运行）
    cycle_next_list: List[dict] = field(
        default_factory=list, repr=False
    )  # 循环运行的待运行条目预览
    trigger_source: TaskTriggerSource = "manual_task"  # MAS 任务触发来源
    game_sign_results: list[dict] = field(default_factory=list, repr=False)
    game_sign_summary_consumed: bool = field(default=False, repr=False)
    _change_task: asyncio.Task[None] | None = field(
        default=None, init=False, repr=False, compare=False
    )
    _change_dirty: bool = field(default=False, init=False, repr=False, compare=False)

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

    def schedule_on_change(self) -> None:
        """合并高频字段变化，并由应用任务注册表持有异步通知。"""

        self._change_dirty = True
        if self._change_task is not None and not self._change_task.done():
            return

        async def _flush_changes() -> None:
            try:
                while self._change_dirty:
                    self._change_dirty = False
                    await self.on_change()
            finally:
                self._change_task = None

        self._change_task = RuntimeTasks.spawn(
            _flush_changes(), name=f"task-state-change:{self.task_id}"
        )
        if self._change_task is None:
            # teardown 已开始时不再发布状态；RuntimeTasks 已关闭协程对象。
            self._change_dirty = False

    @property
    def is_queue_task(self) -> bool:
        """任务是否由计划队列发起；否则为用户单独运行的脚本任务"""
        return self.queue_id is not None

    @property
    def target_user_id(self) -> str | None:
        """单独运行时指定的用户ID；未指定或非自动代理时为 None。

        必须带上模式判断：ScriptConfig 与 Update 模式会把 user_id 写成
        "Default" 或被编辑的用户，那是「配置谁」而不是「只代理谁」。
        """
        return self.user_id if self.mode == "AutoProxy" else None

    def is_target_user(self, user_id: str) -> bool:
        """用户是否属于本次运行范围。

        只用于收窄展示与执行用的 user_list，各脚本适配器持有的用户配置副本必须
        保持完整——它们在收尾时会整表写回，裁剪副本会抹掉同脚本其它用户的配置。

        Args:
            user_id (str): 待判定的用户ID。

        Returns:
            bool: 未指定单独运行的用户时恒为 True。
        """

        target = self.target_user_id
        return target is None or user_id == target

    @property
    def asdict(self) -> list:
        """将 TaskItem 转换为字典形式"""
        return [
            {
                "script_id": script_item.script_id,
                "name": script_item.name,
                "status": script_item.status,
                "userList": [
                    {
                        "user_id": user_item.user_id,
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
    wait_for_finalizer_on_cancel = False

    # 外部手动停止（TaskManager 中止）时置位，供收尾逻辑区分自然结束与手动中止
    stopped_manually: bool = False

    task: asyncio.Task | None = None
    _task_group: asyncio.TaskGroup | None = None
    accomplish: asyncio.Event = field(default_factory=asyncio.Event)

    # 日志停滞判定的内部状态，按阶段分桶：{key: (上次推进的 latest_time, 单调读数)}
    # 不加类型注解，避免被 @dataclass 收作字段。
    _log_progress = None

    def is_log_stalled(
        self, latest_time: datetime, minutes: float, key: str = "default"
    ) -> bool:
        """日志是否已停滞超过给定分钟数。

        不能直接用 ``datetime.now() - latest_time``：两端都是墙钟，系统时钟
        跳变（夏令时切换、NTP 校时）会让差值凭空增加一小时，把正常运行的
        任务误判为超时。这里只用 ``latest_time`` 判断“是否有推进”，实际计时
        交给单调时钟。

        Args:
            latest_time (datetime): 最近一条日志的时间戳。
            minutes (float): 允许的最长无新日志时间，单位分钟。
            key (str): 阶段标识。同一任务的不同阶段（如资源下载与正式运行）
                各自独立计时，避免阶段切换时互相干扰。

        Returns:
            bool: 超过阈值返回 True。
        """

        if self._log_progress is None:
            self._log_progress = {}

        now = time.monotonic()
        previous = self._log_progress.get(key)
        if previous is None or previous[0] != latest_time:
            self._log_progress[key] = (latest_time, now)
            return False
        return now - previous[1] > minutes * 60

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
        except asyncio.CancelledError:
            self.stopped_manually = True
            raise
        except Exception as e:
            await self.on_crash(e)
        finally:
            self._task_group = None
            try:
                if self.wait_for_finalizer_on_cancel:
                    await self._run_final_task()
                else:
                    try:
                        await asyncio.shield(self.final_task())
                    except Exception as e:
                        await self.on_crash(e)
            finally:
                self.accomplish.set()

    async def _run_final_task(self) -> None:
        """推迟外层取消，直到收尾协程真正结束。"""

        finalizer = asyncio.create_task(self.final_task())
        current_task = asyncio.current_task()
        if current_task is None:
            raise RuntimeError("无法获取当前任务")

        # main_task 的取消正在当前 finally 中传播；先清除计数，避免它反复
        # 打断对独立 finalizer 的等待。原 CancelledError 会在 finally 后继续传播。
        while current_task.cancelling():
            current_task.uncancel()

        cancellation: asyncio.CancelledError | None = None

        while not finalizer.done():
            try:
                await asyncio.shield(finalizer)
            except asyncio.CancelledError as e:
                if finalizer.cancelled():
                    raise
                cancellation = e
                while current_task.cancelling():
                    current_task.uncancel()
            except Exception:
                break

        try:
            finalizer.result()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await self.on_crash(e)

        if cancellation is not None:
            raise cancellation

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

        root_task = asyncio.create_task(_root_coro())
        root_task.add_done_callback(lambda _: self.accomplish.set())
        self.task = root_task

    def cancel(self) -> bool:
        if self.task is None or self.task.done():
            return False
        return self.task.cancel()
