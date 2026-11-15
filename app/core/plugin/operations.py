"""插件命令的身份、准入、归属协调与历史；实际执行归背景任务组。"""

from __future__ import annotations

import asyncio
import inspect
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.config import ConfigEntry, ConfigNode, NodeState, UiVisibility, config_manager
from app.core.background_tasks import (
    BackgroundTaskGroup,
    BackgroundTaskHandle,
    BackgroundTaskManager,
    BackgroundTaskRegistry,
    BackgroundTaskState,
    TaskOutcome,
)
from app.models.schema import OperationInfo
from app.plugin.config import PluginCommandEntry
from app.utils import get_logger

logger = get_logger("宿主操作")


class OperationUnavailable(RuntimeError):
    """命令未受理，或取消不符合命令策略。"""


@dataclass
class _Execution:
    entry: ConfigEntry
    group: str
    field: str
    value: object
    info: OperationInfo
    handle: BackgroundTaskHandle[None]
    task: asyncio.Task | None = None
    completed: asyncio.Event = dataclass_field(default_factory=asyncio.Event)


class OperationDispatcher:
    """业务记录可重复查询，后台结果仅由本对象提取；满额直接拒绝。"""

    def __init__(
        self,
        *,
        resolve_node: Callable[[UUID], ConfigNode | None],
        resolve_owner: Callable[[ConfigEntry], UUID | None],
        publish: Callable[[OperationInfo], Awaitable[None]] | None = None,
        history_limit: int = 200,
    ) -> None:
        """绑定配置节点查找、插件归属和状态发布能力，初始化执行记录、历史上限与停机状态。"""
        self._resolve_node = resolve_node
        self._resolve_owner = resolve_owner
        self._publish = publish
        self._history_limit = history_limit
        self._records: OrderedDict[UUID, OperationInfo] = OrderedDict()
        self._finished: deque[UUID] = deque()
        self._running: dict[UUID, _Execution] = {}
        self._blocked: dict[UUID, int] = {}
        self._group: BackgroundTaskGroup | None = None
        self._background: BackgroundTaskRegistry | None = None
        self._closing = False

    def initialize(
        self,
        *,
        max_running: int,
        background: BackgroundTaskRegistry = BackgroundTaskManager,
    ) -> None:
        """宿主显式装配，模块导入不申请任务组。"""
        if self._group is not None:
            raise RuntimeError("Operations 已初始化")
        self._background = background
        self._group = background.register_group(
            "operations", max_running=max_running, max_retained=max_running
        )

    def check_target(self, entry: ConfigEntry) -> None:
        """确认插件配置仍已激活且身份未被删除或替换，供受理和实际执行前共同检查。"""
        if not isinstance(entry, PluginCommandEntry):
            raise OperationUnavailable("operation_target_not_found")
        if entry.deleted or entry.activation_state != NodeState.ACTIVE:
            raise OperationUnavailable("operation_unavailable")
        if self._resolve_node(entry.uid) is not entry:
            raise OperationUnavailable("operation_target_changed")

    def submit(
        self, entry: ConfigEntry, *, group: str, field: str, value: object
    ) -> UUID:
        """校验触发器可执行性并去重同一请求，将处理函数提交为背景任务，返回可查询的操作标识。"""
        self.check_target(entry)
        if self._closing:
            raise OperationUnavailable("operation_unavailable")
        owner = self._resolve_owner(entry)
        if owner is not None and owner in self._blocked:
            raise OperationUnavailable("operation_owner_stopping")
        if (group, field) not in type(entry)._cfg_trigger_specs:
            raise OperationUnavailable("operation_target_not_found")
        for uid, execution in self._running.items():
            if execution.entry is entry and (execution.group, execution.field) == (
                group,
                field,
            ):
                if execution.value == value and execution.info.state in (
                    "queued",
                    "running",
                ):
                    return uid
                raise OperationUnavailable("operation_already_running")
        if entry._ui_visibility(group, field) in (
            UiVisibility.HIDE,
            UiVisibility.DISABLE,
        ):
            raise OperationUnavailable("operation_not_editable")
        if self._group is None:
            raise OperationUnavailable("operation_not_initialized")
        handler = getattr(entry, type(entry)._cfg_trigger_specs[(group, field)])
        info = OperationInfo(
            operationId=uuid4(),
            configUid=entry.uid,
            field=f"{group}.{field}",
            owner=owner,
            createdAt=datetime.now(timezone.utc),
            cancellable=getattr(handler, "__trigger_cancellable__", True),
        )

        async def execute() -> None:
            """在真正执行前再次检查目标身份，标记运行状态并调用同步或异步触发器处理函数。"""
            execution = self._running[info.operationId]
            execution.task = asyncio.current_task()
            self.check_target(entry)
            info.state = "running"
            mode = type(entry)._cfg_trigger_modes[(group, field)][0]
            result = handler() if mode == "bool" else handler(value)
            if inspect.isawaitable(result):
                await result

        handle = self._group.spawn(execute)
        if handle is None:
            raise OperationUnavailable("operation_busy")
        self._records[info.operationId] = info
        self._running[info.operationId] = _Execution(
            entry, group, field, value, info, handle
        )
        handle.add_done_callback(lambda done: self._finish(info.operationId, done))
        return info.operationId

    def _finish(self, uid: UUID, handle: BackgroundTaskHandle[None]) -> None:
        """收集执行结果并安排终态通知；操作等待覆盖通知尝试完成后才释放归属和容量。"""
        execution = self._running[uid]
        outcome = handle.group.try_take(handle)
        assert isinstance(outcome, TaskOutcome)
        state = outcome.state
        info = execution.info
        info.state = (
            "succeeded"
            if state == BackgroundTaskState.SUCCEEDED
            else "cancelled"
            if state == BackgroundTaskState.CANCELLED
            else "failed"
        )
        info.errorCode = type(outcome.error).__name__ if outcome.error else None
        info.completedAt = datetime.now(timezone.utc)
        if self._publish is not None:
            snapshot = info.model_copy(deep=True)

            async def publish() -> None:
                """尝试发布操作终态，通知失败只记录日志，不改变已经确定的业务结果。"""
                assert self._publish is not None
                try:
                    await self._publish(snapshot)
                except Exception:
                    logger.exception(f"插件操作终态通知失败: {uid}")

            # 原执行的运行位和结果位已释放；同一回调内用它承接通知，关闭前先等全部操作。
            assert self._group is not None
            notification = self._group.spawn(publish, retain_result=False)
            assert notification is not None
            notification.add_done_callback(lambda _: self._complete(uid))
        else:
            self._complete(uid)

    def _complete(self, uid: UUID) -> None:
        """在执行与终态通知均结束后解除在途登记，唤醒等待者并维护有界操作历史。"""
        execution = self._running.pop(uid)
        self._finished.append(uid)
        while len(self._finished) > self._history_limit:
            self._records.pop(self._finished.popleft())
        execution.completed.set()

    def get(self, uid: UUID) -> OperationInfo | None:
        """按标识返回操作记录的独立副本，避免调用方修改中心内部状态。"""
        info = self._records.get(uid)
        return info.model_copy(deep=True) if info is not None else None

    def list(self, *, config_uid: UUID | None = None) -> list[OperationInfo]:
        """按操作登记顺序倒序返回在途及已结束记录的副本，可限定目标配置节点。"""
        return [
            info.model_copy(deep=True)
            for info in reversed(self._records.values())
            if config_uid is None or info.configUid == config_uid
        ]

    async def cancel(self, uid: UUID) -> OperationInfo:
        """取消允许取消的运行操作并等待收尾，已结束时返回原记录；拒绝自我取消和不可取消操作。"""
        execution = self._running.get(uid)
        if execution is None:
            info = self.get(uid)
            if info is None:
                raise KeyError(uid)
            return info
        if execution.task is asyncio.current_task():
            raise OperationUnavailable("operation_cannot_cancel_itself")
        if execution.info.state in ("succeeded", "failed", "cancelled"):
            await execution.completed.wait()
            return execution.info.model_copy(deep=True)
        if not execution.info.cancellable:
            raise OperationUnavailable("operation_not_cancellable")
        execution.info.state = "cancelling"
        execution.handle.cancel()
        await execution.completed.wait()
        return execution.info.model_copy(deep=True)

    @asynccontextmanager
    async def pause_owners(self, owners: Iterable[UUID]):
        """在上下文内阻止指定插件的新操作，取消或等待其现有操作收尾，退出时解除本层阻止。"""
        selected = set(owners)
        for owner in selected:
            self._blocked[owner] = self._blocked.get(owner, 0) + 1
        try:
            current = asyncio.current_task()
            executions = [
                item
                for item in self._running.values()
                if item.info.owner in selected and item.task is not current
            ]
            await asyncio.gather(
                *(
                    self.cancel(item.info.operationId)
                    if item.info.cancellable
                    else item.completed.wait()
                    for item in executions
                )
            )
            yield
        finally:
            for owner in selected:
                self._blocked[owner] -= 1
                if not self._blocked[owner]:
                    del self._blocked[owner]

    def seal(self) -> None:
        """拒绝受理新插件命令，已受理操作继续执行并完成终态通知。"""
        self._closing = True

    async def shutdown(self) -> None:
        """关闭受理，取消或等待所有在途操作结束，然后注销操作背景任务组。"""
        self.seal()
        await asyncio.gather(
            *(
                self.cancel(item.info.operationId)
                if item.info.cancellable
                else item.completed.wait()
                for item in tuple(self._running.values())
            )
        )
        if self._background is not None and self._group is not None:
            await self._background.unregister_group(self._group)

    async def start(
        self, *, config_uid: UUID, group: str, field: str, value: bool | str
    ) -> UUID:
        """从配置标识定位并校验触发器输入，拒绝锁定或无效目标后提交操作并返回标识。"""
        entry = self._resolve_node(config_uid)
        if (
            not isinstance(entry, PluginCommandEntry)
            or (group, field) not in type(entry)._cfg_trigger_specs
        ):
            raise OperationUnavailable("operation_target_not_found")
        self.check_target(entry)
        if entry.is_locked:
            raise OperationUnavailable("operation_target_locked")
        patch = type(entry).model_validate({group: {field: value}})
        validated = patch.__dict__[group].__dict__[field]
        idle = type(entry)._cfg_trigger_modes[(group, field)][2]
        if validated == idle:
            raise OperationUnavailable("operation_not_accepted")
        return self.submit(entry, group=group, field=field, value=validated)


def _find_node(uid: UUID) -> ConfigNode | None:
    """遍历已登记的持久化配置树，按唯一标识查找实际配置节点。"""
    pending = list(config_manager.iter_persist_roots())
    while pending:
        node = pending.pop()
        if node.uid == uid:
            return node
        pending.extend(node.iter_children())
    return None


def _plugin_owner(entry: ConfigEntry) -> UUID | None:
    """从插件记录、专属配置及游戏或脚本声明中确定配置节点所属插件，未归属插件时返回 None。"""
    from app.core.plugin import Plugin
    from app.models.config import PluginRecord

    if isinstance(entry, PluginRecord):
        return entry.uid
    for record in Plugin.list_plugins():
        if record._config is entry.root:
            return record.uid
    node: ConfigNode | None = entry
    while node is not None:
        for uid, decl in Plugin.game_types.items():
            if isinstance(node, (decl.game_class, decl.device_class)):
                return uid
        for uid, decl in Plugin.script_types.items():
            types = (decl.script_type, decl.user_type)
            if decl.plan_type is not None:
                types += (decl.plan_type,)
            if isinstance(node, types):
                return uid
        node = node.parent
    return None


async def _publish(info: OperationInfo) -> None:
    """通过宿主 WebSocket 发布后台操作状态，通知前端刷新对应操作。"""
    from app.core.ws import Publisher

    await Publisher.send(id="Operations", type="operation.updated", data=info)


Operations = OperationDispatcher(
    resolve_node=_find_node, resolve_owner=_plugin_owner, publish=_publish
)
