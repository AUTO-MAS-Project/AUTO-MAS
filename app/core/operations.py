"""宿主拥有 Trigger 命令的身份、取消、收尾与有限运行记录。"""

from __future__ import annotations

import asyncio
import inspect
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable, Iterable
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID, uuid4

from blinker import Signal

from app.config import (
    ConfigAggregateError,
    ConfigEntry,
    ConfigNode,
    NodeState,
    UiVisibility,
    config_manager,
)
from app.models.operation import OperationInfo
from app.task.base import TaskBase
from app.utils import get_logger
from app.utils.constants import UTC8

logger = get_logger("宿主操作")


class OperationUnavailable(RuntimeError):
    """宿主正在退出、插件正在释放，或命令目标已失效。"""


class _TriggerTask(TaskBase):
    ended = Signal()

    def __init__(
        self,
        dispatcher: OperationDispatcher,
        entry: ConfigEntry,
        *,
        info: OperationInfo,
        group: str,
        field: str,
        value: object,
    ) -> None:
        super().__init__()
        self.dispatcher: OperationDispatcher = dispatcher
        self.entry: ConfigEntry = entry
        self.info: OperationInfo = info
        self.group: str = group
        self.field: str = field
        self.value: object = value

    async def main_task(self) -> None:
        self.dispatcher.check_target(self.entry)
        self.info.state = "running"
        handler = getattr(
            self.entry, type(self.entry)._cfg_trigger_specs[(self.group, self.field)]
        )
        mode = type(self.entry)._cfg_trigger_modes[(self.group, self.field)][0]
        result = handler() if mode == "bool" else handler(self.value)
        if inspect.isawaitable(result):
            await result


class OperationDispatcher:
    """复用 TaskBase 收尾；终态可查询，运行记录仅保留最近 history_limit 条。"""

    def __init__(
        self,
        *,
        resolve_node: Callable[[UUID], ConfigNode | None],
        resolve_owner: Callable[[ConfigEntry], UUID | None],
        publish: Callable[[OperationInfo], Awaitable[None]] | None = None,
        history_limit: int = 200,
    ) -> None:
        self._resolve_node = resolve_node
        self._resolve_owner = resolve_owner
        self._history_limit = history_limit
        self._publish = publish
        self._records: OrderedDict[UUID, OperationInfo] = OrderedDict()
        self._finished: deque[UUID] = deque()
        self._running: dict[UUID, _TriggerTask] = {}
        self._blocked: dict[UUID, int] = {}
        self._closing = False
        _TriggerTask.ended.connect(self._finish)

    def check_target(self, entry: ConfigEntry) -> None:
        if self._closing or entry.deleted or entry.activation_state != NodeState.ACTIVE:
            raise OperationUnavailable("operation_unavailable")
        if self._resolve_node(entry.uid) is not entry:
            raise OperationUnavailable("operation_target_changed")
        owner = self._resolve_owner(entry)
        if owner is not None and owner in self._blocked:
            raise OperationUnavailable("operation_owner_stopping")

    def submit(
        self, entry: ConfigEntry, *, group: str, field: str, value: object
    ) -> UUID:
        self.check_target(entry)
        for uid, task in self._running.items():
            if task.entry is entry and task.group == group and task.field == field:
                if task.value == value and task.info.state in ("queued", "running"):
                    return uid
                raise OperationUnavailable("operation_already_running")
        if entry._ui_visibility(group, field) in (
            UiVisibility.HIDE,
            UiVisibility.DISABLE,
        ):
            raise OperationUnavailable("operation_not_editable")
        asyncio.get_running_loop()
        info = OperationInfo(
            operationId=uuid4(),
            configUid=entry.uid,
            field=f"{group}.{field}",
            owner=self._resolve_owner(entry),
            createdAt=datetime.now(UTC8),
            cancellable=getattr(
                getattr(entry, type(entry)._cfg_trigger_specs[(group, field)]),
                "__trigger_cancellable__",
                True,
            ),
        )
        task = _TriggerTask(
            self, entry, info=info, group=group, field=field, value=value
        )
        self._records[info.operationId] = info
        self._running[info.operationId] = task
        task.start()
        return info.operationId

    def get(self, uid: UUID) -> OperationInfo | None:
        info = self._records.get(uid)
        return info.model_copy(deep=True) if info is not None else None

    def list(self, *, config_uid: UUID | None = None) -> list[OperationInfo]:
        return [
            info.model_copy(deep=True)
            for info in reversed(self._records.values())
            if config_uid is None or info.configUid == config_uid
        ]

    async def cancel(self, uid: UUID) -> OperationInfo:
        task = self._running.get(uid)
        if task is None:
            info = self.get(uid)
            if info is None:
                raise KeyError(uid)
            return info
        if task._task is asyncio.current_task():
            raise OperationUnavailable("operation_cannot_cancel_itself")
        if not task.info.cancellable:
            raise OperationUnavailable("operation_not_cancellable")
        if task.info.state in ("queued", "running"):
            task.info.state = "cancelling"
            await task.stop()
        else:
            await task.accomplish.wait()
        return task.info.model_copy(deep=True)

    async def _finish(self, task: _TriggerTask) -> None:
        uid = task.info.operationId
        if self._running.get(uid) is not task:
            return
        task.info.state = (
            "failed" if task.error else "cancelled" if task.cancelled else "succeeded"
        )
        task.info.errorCode = type(task.error).__name__ if task.error else None
        task.info.completedAt = datetime.now(UTC8)
        if self._publish is not None:
            try:
                await self._publish(task.info.model_copy(deep=True))
            except Exception as exc:
                logger.warning(f"操作结果推送失败: {uid}: {type(exc).__name__}")
        self._running.pop(uid)
        self._finished.append(uid)
        while len(self._finished) > self._history_limit:
            self._records.pop(self._finished.popleft())

    @asynccontextmanager
    async def pause_owners(self, owners: Iterable[UUID]):
        """先停止所属命令再进入插件锁；回调 finally 可正常访问插件管理器。"""
        selected = set(owners)
        for owner in selected:
            self._blocked[owner] = self._blocked.get(owner, 0) + 1
        try:
            current = asyncio.current_task()
            tasks = [
                task
                for task in self._running.values()
                if task.info.owner in selected and task._task is not current
            ]
            await asyncio.gather(
                *(
                    self.cancel(task.info.operationId)
                    if task.info.cancellable
                    else task.accomplish.wait()
                    for task in tasks
                )
            )
            yield
        finally:
            for owner in selected:
                self._blocked[owner] -= 1
                if not self._blocked[owner]:
                    del self._blocked[owner]

    async def shutdown(self) -> None:
        self._closing = True
        tasks = tuple(self._running.values())
        await asyncio.gather(
            *(
                self.cancel(task.info.operationId)
                if task.info.cancellable
                else task.accomplish.wait()
                for task in tasks
            )
        )

    async def start(
        self, *, config_uid: UUID, group: str, field: str, value: bool | str
    ) -> UUID:
        entry = self._resolve_node(config_uid)
        if (
            not isinstance(entry, ConfigEntry)
            or (group, field) not in type(entry)._cfg_trigger_specs
        ):
            raise OperationUnavailable("operation_target_not_found")
        self.check_target(entry)
        if entry.is_locked:
            raise OperationUnavailable("operation_target_locked")
        patch = type(entry).model_validate({group: {field: value}})
        try:
            ids = await entry.update(patch)
        except ConfigAggregateError as exc:
            raise OperationUnavailable("operation_config_rejected") from exc
        if not ids:
            raise OperationUnavailable("operation_not_accepted")
        return ids[0]


def _find_node(uid: UUID) -> ConfigNode | None:
    pending = list(config_manager.iter_persist_roots())
    while pending:
        node = pending.pop()
        if node.uid == uid:
            return node
        pending.extend(node.iter_children())
    return None


def _plugin_owner(entry: ConfigEntry) -> UUID | None:
    from app.core.plugin_manager import Plugin

    for record in Plugin.list_plugins():
        if record._config is entry.root:
            return record.uid
    node: ConfigNode | None = entry
    while node is not None:
        for uid, decl in Plugin.game_types.items():
            if isinstance(node, (decl.game_class, decl.device_class)):
                return uid
        for uid, decl in Plugin.script_types.items():
            types = (decl.entry_type, decl.user_type)
            if decl.plan_entry_type is not None:
                types += (decl.plan_entry_type,)
            if isinstance(node, types):
                return uid
        node = node.parent
    return None


async def _publish(info: OperationInfo) -> None:
    from app.core.ws import Publisher, protocol

    await Publisher.send(id="Operations", type=protocol.OPERATION_UPDATED, data=info)


Operations = OperationDispatcher(
    resolve_node=_find_node, resolve_owner=_plugin_owner, publish=_publish
)
