"""旧专项方法名适配；执行、取消与收尾共用来源 TaskBase。"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from app.core import BackgroundTaskManager, Publisher
from app.core.background_tasks import BackgroundTaskGroup, BackgroundTaskHandle
from app.core.ws import protocol
from app.models.schema import WSTaskNoticeData
from app.models.task import TaskMode
from app.task.lifecycle import TaskBase
from app.utils import get_logger

if TYPE_CHECKING:
    from app.models.schema import TaskRequirements
    from app.models.task import TaskItem, TaskUserItem
    from app.task.context import TaskContext
    from app.task.history_core import TaskHistorySession

logger = get_logger("旧专项运行回调")


@dataclass
class LegacyUserState:
    """[兼容旧专项] 旧专项私有通知与维护素材；新代码不依赖此状态或扩充公共任务树。

    旧专项的维护判断和通知素材，不属于公共任务树。"""

    maintenance_skipped: bool = False
    push_log: list[tuple[str, str] | tuple[str, str, float | None]] = field(
        default_factory=list
    )
    push_log_mode: str = "汇总"

    async def append_push_log(self, value) -> None:
        """[兼容旧专项] 旧通知素材追加接口；新代码将通知素材交通知业务层处理。"""
        self.push_log.append(value)


class LegacyCallbacks:
    """[兼容旧专项] 旧同步／线程回调提交桥；新代码在所属执行协程提交，背景工作用 BackgroundTaskManager。

    旧专项同步/线程回调的提交桥；写入与 commit 在同一消费者内执行。"""

    def __init__(self) -> None:
        """[兼容旧专项] 仅初始化旧回调桥；新执行树不创建独立的运行态提交消费者。"""
        try:
            self.loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = None
        self.pending: deque[Coroutine[Any, Any, Any]] = deque()
        self.task: BackgroundTaskHandle[None] | None = None
        self._group: BackgroundTaskGroup | None = None
        self.errors: list[Exception] = []
        self.closed = False

    def submit(self, operation: Coroutine[Any, Any, Any]) -> None:
        """[兼容旧专项] 旧回调排队接口；新执行树在产生暂存的同一协程中提交。"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self.loop is None:
            self.loop = loop
        if self.closed or self.loop is None or self.loop.is_closed():
            operation.close()
            return
        if loop is not self.loop:
            self.loop.call_soon_threadsafe(self.submit, operation)
            return
        self.pending.append(operation)
        if self.task is None:
            if self._group is None:
                from uuid import uuid4

                try:
                    self._group = BackgroundTaskManager.register_group(
                        # 消费者退出到 done 回调之间，允许接纳下一批；业务始终串行。
                        f"legacy-callback:{uuid4()}",
                        max_running=2,
                        max_retained=2,
                    )
                except RuntimeError:
                    self.closed = True
            if self._group is not None:
                self.task = self._group.spawn(self._consume, retain_result=False)
            if self.task is None:
                while self.pending:
                    self.pending.popleft().close()

    async def _consume(self) -> None:
        """[兼容旧专项] 仅消费旧回调队列；新执行树直接 await 下层并就地提交。"""
        try:
            while self.pending:
                try:
                    await self.pending.popleft()
                except Exception as error:
                    if len(self.errors) < 32:
                        self.errors.append(error)
                    logger.opt(exception=error).error("运行态回调提交失败")
        finally:
            while self.pending:
                self.pending.popleft().close()
            self.task = None

    async def drain(self) -> None:
        """[兼容旧专项] 仅等待旧回调桥结清；新执行树使用 TaskBase 的完整生命周期等待。"""
        while self.task is not None:
            current = self.task
            await current.wait_done()
            # 启动前取消时消费者尚未进入 finally，也必须释放未开始的操作。
            if self.task is current:
                self.task = None
                while self.pending:
                    self.pending.popleft().close()

    async def close(self) -> None:
        """[兼容旧专项] 仅关闭旧回调桥；新背景资源使用 BackgroundTaskManager 的任务组生命周期。"""
        await self.drain()
        self.closed = True
        if self._group is not None:
            await BackgroundTaskManager.unregister_group(self._group)


def maintenance_requirements(target_id: str) -> TaskRequirements:
    """[兼容旧专项] 仅解析旧专项手动更新目标；新任务直接构造标准要求树。

    旧专项更新的目标识别留在适配层，不增加公开调度模式。"""
    from uuid import UUID

    from app.core import Config

    target = UUID(target_id)
    script = Config.ScriptConfig.get(target)
    user_id = "default"
    if script is None:
        script = next(
            (
                entry
                for entry in Config.ScriptConfig.values()
                if target in entry.UserData
            ),
            None,
        )
        user_id = str(target)
    if script is None or type(script).__name__ not in {
        "BetterGIConfig",
        "MaaEndConfig",
        "OkwwConfig",
    }:
        raise ValueError("该目标不支持手动更新")
    return {0: {"uid": str(script.uid), "children": {0: {"uid": user_id}}}}


class _LegacyExecution(TaskBase):
    """[兼容旧专项] 旧方法名到来源 TaskBase 的桥；新执行器直接继承 TaskBase。"""

    def __init__(self, owner):
        """[兼容旧专项] 仅关联旧执行器；新执行树直接初始化 TaskBase 子类。"""
        super().__init__()
        self.owner = owner

    async def main_task(self):
        """[兼容旧专项] 仅桥接旧 _run_main_task；新执行器直接实现 TaskBase.main_task。"""
        await self.owner._run_main_task()

    async def final_task(self):
        """[兼容旧专项] 仅桥接旧收尾和回调排空；新执行器直接实现 TaskBase.final_task。"""
        try:
            await self.owner.callbacks.drain()
            await self.owner._finalize_task()
        finally:
            await self.owner.callbacks.drain()

    async def on_crash(self, exc):
        """[兼容旧专项] 仅桥接旧异常处理；新执行器直接实现 TaskBase.on_crash。"""
        try:
            await self.owner.on_crash(exc)
        except Exception as error:
            await super().on_crash(error)


class TaskExecuteBase(ABC):
    """[兼容旧专项] 仅供已有 task 专项继承；新 L2/L3/L4 执行器使用来源 TaskBase。"""

    task_info: TaskItem
    history: TaskHistorySession

    def __init__(self):
        """[兼容旧专项] 仅装配旧专项执行桥与私有状态；新执行树使用 TaskBase 和显式上下文。"""
        self.execution = _LegacyExecution(self)
        self.config_locks = {}
        self.context: TaskContext | None = None
        self._stopped_manually = False
        self._log_progress = {}
        self.callbacks = LegacyCallbacks()
        self.maintenance = False
        self._user_states: dict[UUID, LegacyUserState] = {}

    def user_state(self, user: TaskUserItem) -> LegacyUserState:
        """[兼容旧专项] 只读取旧专项私有素材；新代码不依赖此状态容器。"""
        return self._user_states.setdefault(user.uid, LegacyUserState())

    @property
    def execution_mode(self) -> TaskMode | Literal["Update"]:
        """[兼容旧专项] 将 ScriptView／隐藏更新转换成旧模式；新代码直接使用 TaskMode。"""
        if self.maintenance:
            return "Update"
        mode = self.task_info.mode
        return TaskMode.SCRIPT_CONFIG if mode == TaskMode.SCRIPT_VIEW else mode

    async def send_notice(
        self, *, level: Literal["info", "warning", "error"], message: str
    ) -> None:
        """[兼容旧专项] 旧专项通知便捷入口；新代码使用所属业务层的既有通知能力。"""
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level=level, message=message),
        )

    @property
    def task(self):
        """[兼容旧专项] 旧底层 asyncio Task 别名；新执行树通过 TaskBase 生命周期操作。"""
        return self.execution._task

    @property
    def accomplish(self):
        """[兼容旧专项] 旧完成事件别名；新执行器使用自己的 TaskBase.accomplish。"""
        return self.execution.accomplish

    @property
    def stopped_manually(self):
        """[兼容旧专项] 旧停止标记读取；新执行树使用 TaskBase.cancelled。"""
        return (
            self._stopped_manually
            or self.execution.cancelled
            or getattr(getattr(self, "task_info", None), "status", None) == "cancelled"
        )

    @stopped_manually.setter
    def stopped_manually(self, value):
        """[兼容旧专项] 旧停止标记写入；新代码通过 TaskBase.stop() 请求中止。"""
        self._stopped_manually = value

    @abstractmethod
    async def main_task(self):
        """[兼容旧专项] 旧专项主流程扩展点；新执行器直接实现 TaskBase.main_task。"""
        ...

    @abstractmethod
    async def final_task(self):
        """[兼容旧专项] 旧专项收尾扩展点；新执行器直接实现 TaskBase.final_task。"""
        ...

    @abstractmethod
    async def on_crash(self, exc):
        """[兼容旧专项] 旧专项异常扩展点；新执行器直接实现 TaskBase.on_crash。"""
        ...

    async def _run_main_task(self):
        """[兼容旧专项] 旧主流程转接名；新代码直接实现 TaskBase.main_task。"""
        await self.main_task()

    async def _finalize_task(self):
        """[兼容旧专项] 旧收尾转接名；新代码直接实现 TaskBase.final_task。"""
        await self.final_task()

    async def _execute_task(self, parent_tg=None):
        """[兼容旧专项] 旧运行入口，parent_tg 仅保留签名；新代码使用 TaskBase.run() 或父层 spawn()。"""
        await self.execution.run()

    async def _run_final_task(self):
        """[兼容旧专项] 旧收尾等待入口；新代码通过 TaskBase.run()/stop() 等待完整生命周期。"""
        await self.execution._wait_finalizer()

    async def spawn(self, child):
        """[兼容旧专项] 旧子任务上下文转接；新层级通过 TaskBase.spawn() 派发并显式传入上下文。"""
        child.callbacks = self.callbacks
        child._user_states = self._user_states
        child.maintenance = self.maintenance
        child.history = self.history
        if self.context is not None:
            script = getattr(child, "script_info", None)
            user = (
                script.user_list[script.current_index]
                if script is not None and script.current_index >= 0
                else None
            )
            child.context = self.context.with_params(
                user.info.params if user else self.context.params
            )
        script = getattr(self, "script_info", None)
        if script is not None and script.status == "等待":
            await script.set_state(status="运行")
        await self.execution.spawn(child.execution)

    def execute(self):
        """[兼容旧专项] 旧启动方法名；新顶层执行器使用 TaskBase.start()。"""
        self.execution.start()

    async def stop(self):
        """[兼容旧专项] 旧停止接口；新执行器直接使用 TaskBase.stop()。"""
        self.stopped_manually = True
        self._on_finalize_cancel_requested()
        await self.execution.stop()

    def _on_finalize_cancel_requested(self):
        """[兼容旧专项] 旧专项取消钩子；新执行树在所属层响应取消并由 final_task 收尾。"""
        pass

    def is_log_stalled(self, latest_time, minutes, key="default"):
        """[兼容旧专项] 旧专项日志停滞判断；新执行树的超时策略归相应业务层。"""
        now = time.monotonic()
        previous, since = self._log_progress.get(key, (None, now))
        if previous != latest_time:
            since = now
        self._log_progress[key] = (latest_time, since)
        return now - since > minutes * 60
