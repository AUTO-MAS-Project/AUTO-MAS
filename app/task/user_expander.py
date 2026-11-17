"""L3：使用已锁托管配置，逐用户持锁并等待 L4 完整收尾。"""

from __future__ import annotations

import asyncio
from abc import abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from app.config import LockTicket
from app.models.config import ScriptConfigType, ScriptEntry, UserConfigType, UserEntry
from app.models.task import LogRecord, TaskMode, TaskScriptItem, TaskUserItem
from app.task.context import TaskContext
from app.task.lifecycle import TaskBase
from app.utils.common.process.scope import process_finalizer_scope

if TYPE_CHECKING:
    from app.task.history_core import TaskHistorySession
    from app.task.mode_worker import ModeWorker


class _UserLookup(Protocol):
    def get(self, uid: UUID | str) -> UserConfigType | UserEntry | None:
        """按用户标识查询配置条目，兼容旧专项和插件用户模型，不存在时返回 None。"""
        ...


class UserExpander[ScriptConfigT: ScriptConfigType | ScriptEntry](TaskBase):
    history: TaskHistorySession

    def __init__(self, script: TaskScriptItem, config: ScriptConfigT) -> None:
        """绑定托管运行节点及已锁脚本配置，建立 L3 参数上下文并初始化用户锁和准备阶段状态。"""
        super().__init__()
        self.script_info = script
        root = script.task_info
        if root is None:
            raise ValueError("托管运行节点未绑定任务根")
        self.task_info = root
        self.context = TaskContext().with_params(script.info.params)
        self.script_config = config
        self._user_config: UserConfigType | UserEntry | None = None
        self._user_ticket: LockTicket | None = None
        self._entered = False

    def user_collection(self, script: ScriptConfigT) -> _UserLookup:
        # 插件配置接入位置：由真实插件声明提供公开配置访问，不推断私有格式。
        """按脚本配置类型取得用户集合，统一插件 users 与旧专项 UserData 的访问入口。"""
        return script.users if isinstance(script, ScriptEntry) else script.UserData

    def resolve_user(self, user: TaskUserItem) -> UserConfigType | UserEntry | None:
        """从当前脚本中重新查找用户，并核对任务创建时的配置身份，删除或替换后返回 None。"""
        entry = self.user_collection(self.script_config).get(user.info.user_id)
        return (
            entry
            if entry is not None
            and (user._config_ref is None or user._config_ref() is entry)
            else None
        )

    def can_run_user(self, entry: UserConfigType | UserEntry) -> bool:
        """按运行模式及新旧用户配置的启用条件，判断当前用户是否应进入实际执行。"""
        if isinstance(entry, UserEntry):
            return self.task_info.mode != TaskMode.AUTO_PROXY or entry.info.enabled
        return self.task_info.mode != TaskMode.AUTO_PROXY or (
            entry.Info.Status and entry.Info.RemainedDay != 0
        )

    async def record_user_state(
        self, user: TaskUserItem, *, status: str, reason: str
    ) -> None:
        await user.add_log_record(
            datetime.now().astimezone(),
            LogRecord(status=reason, content=[reason + "\n"]),
        )
        await user.set_state(status=status)

    async def main_task(self) -> None:
        """检查并准备托管，逐用户确认配置并取得排他锁，构造并等待 L4 完整收尾后再释放用户锁。"""
        await self.script_info.set_state(status="运行")
        self._entered = True
        reason = await self.check()
        if reason:
            raise ValueError(reason)
        # 游戏接入位置：取得托管锁后、派发用户前订阅游戏/设备；资源由真实提供方负责。
        await self.prepare()
        for user in self.script_info.users.values():
            if self.task_info.info.status == "cancelled":
                raise asyncio.CancelledError
            self.script_info.current.index = user.uid
            await self.script_info.commit()
            if user.info.user_id != "default":
                last_wait_message = None
                while True:
                    # 先确认存在再尝试取锁；等待后重新查找，不持旧对象无限等待。
                    entry = self.resolve_user(user)
                    if entry is None:
                        await self.record_user_state(
                            user, status="异常", reason="用户配置已删除或替换"
                        )
                        break
                    ticket = await entry.try_lock_x(cascade=True)
                    if ticket is not None:
                        self._user_config = entry
                        self._user_ticket = ticket
                        break
                    from app.core.task_manager import TaskManager

                    holders = TaskManager.describe_lock_holders(entry, cascade=True)
                    name = (
                        entry.info.name
                        if isinstance(entry, UserEntry)
                        else entry.Info.Name
                    )
                    message = f"等待用户配置「{name}」的 X 锁，当前占用：{holders}。"
                    if message != last_wait_message:
                        self.script_info.current.log = (
                            self.script_info.current.log + message + "\n"
                        )
                        await self.script_info.commit()
                        last_wait_message = message
                    await asyncio.sleep(1)
                if self._user_ticket is None:
                    continue
            try:
                if self._user_config is not None:
                    if self.resolve_user(user) is not self._user_config:
                        await self.record_user_state(
                            user, status="异常", reason="用户配置已删除或替换"
                        )
                        continue
                    if not self.can_run_user(self._user_config):
                        await self.record_user_state(
                            user, status="跳过", reason="用户已禁用或剩余天数不足"
                        )
                        continue
                worker = self.build_worker(user, self._user_config)
                if (
                    worker.expander is not self
                    or worker.user_info is not user
                    or worker.user_config is not self._user_config
                ):
                    raise ValueError("插件执行器未绑定当前用户及已锁配置")
                await self.spawn(worker)
            finally:
                await self._release_user_lock()

    async def _release_user_lock(self) -> None:
        if self._user_ticket is not None:
            assert self._user_config is not None
            await self._user_config.unlock(self._user_ticket)
            self._user_ticket = None
            self._user_config = None

    async def check(self) -> str | None:
        """插件托管级检查。"""
        return None

    async def prepare(self) -> None:
        """插件托管级准备；本协程暂存必须在返回前提交。"""

    @abstractmethod
    def build_worker(
        self, user: TaskUserItem, config: UserConfigType | UserEntry | None
    ) -> ModeWorker:
        """按真实插件能力与当前模式构造 L4。"""
        raise NotImplementedError

    async def finish(self) -> None:
        """插件恢复及必要保存；不替脚本生成结果。"""

    async def on_crash(self, exc: BaseException) -> None:
        try:
            await self.script_info.set_log(str(exc))
            await self.script_info.set_state(status="异常")
        except Exception as failure:
            await super().on_crash(failure)
        await super().on_crash(exc)

    async def final_task(self) -> None:
        """在进程停止确认范围内完成当前层级恢复、保存及状态提交。"""
        with process_finalizer_scope():
            try:
                if self._entered:
                    await self.finish()
            finally:
                # 游戏释放位置：插件恢复后归还订阅；托管锁仍由 L2 持有至本层收尾结束。
                try:
                    await self.script_config.commit()
                finally:
                    await self._release_user_lock()
            await self.script_info.set_state(
                status="已取消"
                if self.cancelled
                else "异常"
                if self.error
                or any("异常" in u.status for u in self.script_info.users.values())
                else "完成"
            )
