#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
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


import uuid
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Literal

from app.plugins import PluginEventFactory, PluginEventNames
from .ws import MainConnection, Publisher, protocol
from app.services import System
from app.models.task import TaskItem, ScriptItem, UserItem, TaskExecuteBase
from app.models.schema import (
    WSPowerSignData,
    WSTaskCompletedData,
    WSTaskCreatedData,
    WSTaskNoticeData,
)
from app.utils import get_logger
from .queue_cycle import (
    QueueCycleEntry,
    calculate_next_cycle_after_run,
    calculate_next_cycle_run,
    format_cycle_datetime,
    is_cycle_script_success,
)


logger = get_logger("业务调度")

CYCLE_IDLE_POLL_SECONDS = 30
CYCLE_LEASE_RETRY_SECONDS = 5

# task.log.updated 推送保留的日志尾部窗口（字符数）。
# - 日志最新内容在尾部，前端日志页整条覆盖显示，需要远大于插件事件
#   2000 字符 tail 的合理回看窗口；
# - WS 应用层单条消息上限为 4MB（protocol.DEFAULT_MAX_MESSAGE_BYTES），
#   超限消息会被发布器整条拒发，前端日志会静默停更。512K 字符即使全部
#   是 3~4 字节的 UTF-8 字符（CJK/emoji），序列化后也不超过约 2MB，
#   相对 4MB 上限留有充足余量。
TASK_LOG_PUSH_TAIL_CHARS = 512 * 1024


def build_task_log_push_payload(log_text: str | None) -> dict:
    """构造 task.log.updated 的推送 payload；超长日志仅保留尾部。

    截断时附加 ``truncated`` 与 ``log_total_length``（原始字符数）字段。
    前端消费端（frontend/src/views/scheduler/useSchedulerLogic.ts 的
    handleUpdateMessage）只读取 ``data.log``，多余字段会被忽略。
    """

    text = log_text or ""
    if len(text) <= TASK_LOG_PUSH_TAIL_CHARS:
        return {"log": text}
    return {
        "log": text[-TASK_LOG_PUSH_TAIL_CHARS:],
        "truncated": True,
        "log_total_length": len(text),
    }


class TaskRuntimeUnavailableError(RuntimeError):
    """The selected configuration runtime cannot safely dispatch tasks yet."""


class _ConfigSelectorProxy:
    """Resolve host Config only when task code actually needs it.

    FastAPI imports this module while it assembles routers.  Importing
    ``.config`` here used to construct the ConfigBase graph even when the
    process had selected Config v2 authoritative mode.  The proxy preserves
    the existing ``Config.foo`` call sites, including assignments, without
    choosing a configuration runtime during module import.
    """

    @staticmethod
    def _target():
        from app.core import Config as selected_config

        return selected_config

    def __getattr__(self, name: str):
        return getattr(self._target(), name)

    def __setattr__(self, name: str, value: object) -> None:
        setattr(self._target(), name, value)


Config = _ConfigSelectorProxy()


async def _ensure_task_runtime_available() -> None:
    """Reject authoritative dispatch until its selected runtime is initialized."""

    from app.configuration import (
        CONFIG_V2_MODE,
        CONFIG_V2_MODE_AUTHORITATIVE,
    )

    if (
        CONFIG_V2_MODE == CONFIG_V2_MODE_AUTHORITATIVE
        and not Config.initialized
    ):
        raise TaskRuntimeUnavailableError(
            "Config v2 authoritative task dispatch is unavailable before "
            "the native configuration runtime is initialized"
        )


async def _set_many_with_expected(
    entry,
    changes: list[tuple[str, str, object]],
    *,
    expected: list[tuple[str, str, object]],
) -> None:
    """Atomically apply a legacy/v2 config update with CAS semantics.

    Legacy ``ConfigBase`` exposes ``expected=`` directly. Native Config v2
    accepts a grouped mapping instead, so compare and stage the update while
    holding its global transaction lock. This prevents another writer from
    interleaving between the comparison and commit.
    """

    from app.configuration import (
        CONFIG_V2_MODE,
        CONFIG_V2_MODE_AUTHORITATIVE,
        config_manager,
    )

    if CONFIG_V2_MODE != CONFIG_V2_MODE_AUTHORITATIVE:
        await entry.set_many(changes, expected=expected)
        return

    grouped: dict[str, dict[str, object]] = {}
    for group, field, value in changes:
        grouped.setdefault(group, {})[field] = value

    async with config_manager.transaction():
        conflicts: list[tuple[str, str, object, object]] = []
        for group, field, wanted in expected:
            actual = entry.get(group, field)
            if actual != wanted:
                conflicts.append((group, field, wanted, actual))
        if conflicts:
            detail = ", ".join(
                f"{group}.{field}: expected {wanted!r}, got {actual!r}"
                for group, field, wanted, actual in conflicts
            )
            raise RuntimeError(f"配置 CAS 冲突: {detail}")
        await entry.set_many(grouped)


def _resolve_queue_name(queue_id: str | None) -> str | None:
    """根据 queue_id 解析队列名，解析失败时返回 None。"""
    if not queue_id:
        return None

    try:
        return Config.QueueConfig[uuid.UUID(queue_id)].get("Info", "Name")
    except Exception:
        return None


def _build_script_summaries(script_list: list[ScriptItem]) -> list[dict[str, str]]:
    """构建脚本摘要数组，供任务事件复用。"""
    return [
        {
            "script_id": item.script_id,
            "script_name": item.name,
            "status": item.status,
        }
        for item in script_list
    ]


def _resolve_final_script(task_info: TaskItem) -> ScriptItem | None:
    """获取任务结束时可代表当前任务状态的脚本项。"""
    if 0 <= task_info.current_index < len(task_info.script_list):
        return task_info.script_list[task_info.current_index]
    if task_info.script_list:
        return task_info.script_list[-1]
    return None


class TaskInfo(TaskItem):

    def _has_meaningful_current_log(self) -> bool:
        """判断当前脚本日志是否包含有效内容。"""
        if not (0 <= self.current_index < len(self.script_list)):
            return False

        log_text = self.script_list[self.current_index].log
        if not isinstance(log_text, str):
            return False

        return bool(log_text.strip())

    async def _emit_task_progress(self) -> None:
        """发送 task.progress 事件，避免重复发送相同快照。"""
        if 0 <= self.current_index < len(self.script_list):
            if not self._has_meaningful_current_log():
                return

        progress_data = PluginEventFactory.build_task_progress_data(
            self,
            queue_name=_resolve_queue_name(self.queue_id),
        )
        signature = repr(progress_data)
        if getattr(self, "_last_progress_signature", None) == signature:
            return

        self._last_progress_signature = signature
        await PluginEventFactory.emit_event_async(
            event=PluginEventNames.TASK_PROGRESS,
            source="core.task_manager",
            data=progress_data,
        )

    async def _emit_task_log(self) -> None:
        """发送 task.log 事件，提供当前脚本日志内容。"""
        if not (0 <= self.current_index < len(self.script_list)):
            return
        if not self._has_meaningful_current_log():
            return

        script_item = self.script_list[self.current_index]
        log_text = script_item.log or ""
        signature = (self.current_index, log_text)
        if getattr(self, "_last_log_signature", None) == signature:
            return

        self._last_log_signature = signature
        tail_chars = 2000
        is_truncated = len(log_text) > tail_chars
        await PluginEventFactory.emit_event_async(
            event=PluginEventNames.TASK_LOG,
            source="core.task_manager",
            data={
                "task_id": self.task_id,
                "mode": self.mode,
                "queue_id": self.queue_id,
                "queue_name": _resolve_queue_name(self.queue_id),
                "script_id": script_item.script_id,
                "script_name": script_item.name,
                "script_status": script_item.status,
                "current_script_index": self.current_index,
                "log": log_text,
                "log_tail": log_text[-tail_chars:],
                "log_length": len(log_text),
                "truncated_for_tail": is_truncated,
            },
        )

    async def on_change(self):
        """任务状态变更时，同步推送前端并广播插件事件。"""
        await Publisher.send(
            id=self.task_id,
            type=protocol.TASK_INFO_UPDATED,
            data=self.ws_data,
        )
        if self.current_index != -1:
            await Publisher.send(
                id=self.task_id,
                type=protocol.TASK_LOG_UPDATED,
                data=build_task_log_push_payload(
                    self.script_list[self.current_index].log
                ),
            )

        await self._emit_task_progress()
        await self._emit_task_log()


class Task(TaskExecuteBase):

    def __init__(self, task_info: TaskInfo, *, lease_manager=None):
        super().__init__()
        self.task_info = task_info
        self._lease_manager = lease_manager
        self.is_closing = False
        self._exit_result = "success"
        self._exit_error: str | None = None
        self._cycle_script_items: dict[str, ScriptItem] = {}
        self._active_cycle_run_ids: dict[str, str] = {}

    def _resolve_script_provider(self, script_uid: uuid.UUID):
        """解析脚本对应的 provider，兼容插件脚本。"""
        from app.configuration import (
            CONFIG_V2_MODE,
            CONFIG_V2_MODE_AUTHORITATIVE,
        )
        from .script_types import (
            build_legacy_fallback_provider_by_script_config,
            script_type_registry,
        )

        if CONFIG_V2_MODE == CONFIG_V2_MODE_AUTHORITATIVE:
            script_type_registry.bootstrap()
            return script_type_registry.get(Config.get_script_type_key(script_uid))

        from app.models.plugin_script_config import PluginScriptConfig

        script_config = Config.ScriptConfig[script_uid]

        if isinstance(script_config, PluginScriptConfig):
            type_key = str(script_config.get("Meta", "PluginTypeKey") or "").strip()
            if type_key:
                return script_type_registry.get(type_key)

        try:
            return script_type_registry.get_by_script_config(script_config)
        except KeyError:
            provider = build_legacy_fallback_provider_by_script_config(script_config)
            if provider is not None:
                return provider
            raise

    def _build_script_event_data(self) -> Dict[str, str | None]:
        """附加到 script.* 事件的任务上下文。"""
        return {
            "queue_id": self.task_info.queue_id,
            "queue_name": _resolve_queue_name(self.task_info.queue_id),
        }

    async def _emit_task_start(self) -> None:
        """发送 task.start 事件，提供插件所需的任务标识和可操作入口。"""
        scripts = _build_script_summaries(self.task_info.script_list)
        primary_script = scripts[0] if len(scripts) == 1 else None

        await PluginEventFactory.emit_event_async(
            event=PluginEventNames.TASK_START,
            source="core.task_manager",
            data={
                "task_id": self.task_info.task_id,
                "mode": self.task_info.mode,
                "queue_id": self.task_info.queue_id,
                "queue_name": _resolve_queue_name(self.task_info.queue_id),
                "script_id": self.task_info.script_id,
                "user_id": self.task_info.user_id,
                "script_total": len(self.task_info.script_list),
                "scripts": scripts,
                "primary_script_id": (
                    primary_script.get("script_id") if primary_script else None
                ),
                "primary_script_name": (
                    primary_script.get("script_name") if primary_script else None
                ),
                "actions": {
                    "stop_task": {
                        "api": "/api/dispatch/stop",
                        "method": "POST",
                        "body": {"taskId": self.task_info.task_id},
                    },
                    "stop_all_tasks": {
                        "api": "/api/dispatch/stop",
                        "method": "POST",
                        "body": {"taskId": "ALL"},
                    },
                },
            },
        )

    async def _emit_task_exit(self) -> None:
        """发送 task.exit 事件，告知任务最终结果。"""
        scripts = _build_script_summaries(self.task_info.script_list)
        final_script = _resolve_final_script(self.task_info)

        await PluginEventFactory.emit_event_async(
            event=PluginEventNames.TASK_EXIT,
            source="core.task_manager",
            data={
                "task_id": self.task_info.task_id,
                "mode": self.task_info.mode,
                "queue_id": self.task_info.queue_id,
                "queue_name": _resolve_queue_name(self.task_info.queue_id),
                "script_id": self.task_info.script_id,
                "user_id": self.task_info.user_id,
                "scripts": scripts,
                "final_script_id": (
                    final_script.script_id if final_script is not None else None
                ),
                "final_script_name": (
                    final_script.name if final_script is not None else None
                ),
                "final_script_status": (
                    final_script.status if final_script is not None else None
                ),
                "result": self._exit_result,
                "error": self._exit_error,
                "summary": self.task_info.result,
            },
        )

    async def prepare(self):

        if self.task_info.mode == "CycleRun":
            if self.task_info.queue_id is None:
                raise RuntimeError("循环运行必须选择队列")
            await self._collect_cycle_entries(
                uuid.UUID(self.task_info.queue_id),
                datetime.now(),
            )
            logger.success(
                f"循环任务 {self.task_info.task_id} 检索完成，"
                f"包含 {len(self.task_info.script_list)} 个脚本项"
            )
            return

        # 初始化任务列表
        script_ids = (
            [
                queue_item.get("Info", "ScriptId")
                for queue_item in Config.QueueConfig[
                    uuid.UUID(self.task_info.queue_id)
                ].QueueItem.values()
                if queue_item.get("Info", "ScriptId") != "-"
            ]
            if self.task_info.script_id is None
            else [self.task_info.script_id]
        )

        self.task_info.script_list = [
            ScriptItem(
                script_id=script_id,
                status="等待",
                name=Config.ScriptConfig[uuid.UUID(script_id)].get("Info", "Name"),
                user_list=[
                    UserItem(user_id=str(uuid.uuid4()), name="暂未加载", status="等待")
                ],
            )
            for script_id in script_ids
        ]

        logger.success(
            f"任务 {self.task_info.task_id} 检索完成，包含 {len(self.task_info.script_list)} 个脚本项"
        )

    async def _recover_interrupted_cycle_run(
        self,
        queue_item,
        *,
        item_key: str,
        now: datetime,
    ) -> None:
        """将不属于当前 Task 的 running 状态收敛为 failed，保留已消费的 NextRunAt。"""

        if queue_item.get("Data", "CycleState") != "running":
            return
        run_id = str(queue_item.get("Data", "CycleRunId") or "")
        if run_id and self._active_cycle_run_ids.get(item_key) == run_id:
            return

        revision = queue_item.get("Data", "CycleRevision")
        timestamp = format_cycle_datetime(now)
        try:
            await _set_many_with_expected(
                queue_item,
                [
                    ("Data", "LastCycleFinishedAt", timestamp),
                    ("Data", "CycleState", "failed"),
                    ("Data", "CycleRevision", revision + 1),
                    ("Data", "CycleResult", "interrupted"),
                    (
                        "Data",
                        "CycleError",
                        "宿主在循环运行期间中断；已保留 NextRunAt 防止立即重复",
                    ),
                    ("Data", "CycleUpdatedAt", timestamp),
                ],
                expected=[
                    ("Data", "CycleRunId", run_id),
                    ("Data", "CycleState", "running"),
                    ("Data", "CycleRevision", revision),
                ],
            )
        except RuntimeError as error:
            logger.warning(f"循环队列项 {item_key} 中断恢复 CAS 冲突: {error}")

    async def _collect_cycle_entries(
        self,
        queue_uid: uuid.UUID,
        now: datetime,
    ) -> list[QueueCycleEntry]:
        """按父级 QueueItem 顺序收集候选，并同步可展示的首次运行时间。"""

        if queue_uid not in Config.QueueConfig:
            raise RuntimeError("循环队列已被删除")

        queue = Config.QueueConfig[queue_uid]
        entries: list[QueueCycleEntry] = []
        script_items: list[ScriptItem] = []
        active_item_ids: set[str] = set()

        for parent_index, (queue_item_uid, queue_item) in enumerate(
            queue.QueueItem.items()
        ):
            script_id = str(queue_item.get("Info", "ScriptId") or "").strip()
            if script_id in {"", "-"}:
                continue
            try:
                script_uid = uuid.UUID(script_id)
            except ValueError:
                logger.warning(f"循环队列项 {queue_item_uid} 的脚本 ID 无效")
                continue
            if script_uid not in Config.ScriptConfig:
                logger.warning(f"循环队列项 {queue_item_uid} 引用的脚本已删除")
                continue

            item_key = str(queue_item_uid)
            active_item_ids.add(item_key)
            script_config = Config.ScriptConfig[script_uid]
            script_item = self._cycle_script_items.get(item_key)
            if script_item is None or script_item.script_id != script_id:
                script_item = ScriptItem(
                    script_id=script_id,
                    status="等待",
                    name=script_config.get("Info", "Name"),
                    user_list=[
                        UserItem(
                            user_id=str(uuid.uuid4()),
                            name="暂未加载",
                            status="等待",
                        )
                    ],
                )
                self._cycle_script_items[item_key] = script_item
            else:
                script_item.name = script_config.get("Info", "Name")
            script_index = len(script_items)
            script_items.append(script_item)

            if not queue_item.get("Schedule", "Enabled"):
                continue
            await self._recover_interrupted_cycle_run(
                queue_item,
                item_key=item_key,
                now=now,
            )

            next_run_at = calculate_next_cycle_run(
                now=now,
                mode=queue_item.get("Schedule", "Mode"),
                days=queue_item.get("Schedule", "Days"),
                time_text=queue_item.get("Schedule", "Time"),
                interval_minutes=queue_item.get(
                    "Schedule", "IntervalMinutes"
                ),
                interval_anchor=queue_item.get(
                    "Schedule", "IntervalAnchor"
                ),
                next_run_at=queue_item.get("Schedule", "NextRunAt"),
                last_started_at=queue_item.get(
                    "Data", "LastCycleStartedAt"
                ),
                last_finished_at=queue_item.get(
                    "Data", "LastCycleFinishedAt"
                ),
            )
            persisted_next = queue_item.get("Schedule", "NextRunAt")
            if (
                persisted_next == "2000-01-01 00:00:00"
                and next_run_at > now
            ):
                await queue_item.set(
                    "Schedule",
                    "NextRunAt",
                    format_cycle_datetime(next_run_at),
                )

            entries.append(
                QueueCycleEntry(
                    parent_index=parent_index,
                    script_index=script_index,
                    queue_item_id=item_key,
                    script_id=script_id,
                    script_name=script_item.name,
                    next_run_at=next_run_at,
                )
            )

        for item_key in set(self._cycle_script_items) - active_item_ids:
            self._cycle_script_items.pop(item_key, None)
        self.task_info.script_list = script_items
        return entries

    @staticmethod
    def _cycle_preview_payload(
        entry: QueueCycleEntry,
        *,
        now: datetime,
        is_running: bool = False,
    ) -> dict[str, object]:
        return {
            "queueItemId": entry.queue_item_id,
            "scriptId": entry.script_id,
            "scriptName": entry.script_name,
            "nextRunAt": format_cycle_datetime(entry.next_run_at),
            "isDue": entry.next_run_at <= now,
            "isRunning": is_running,
        }

    async def _set_cycle_state(
        self,
        entries: list[QueueCycleEntry],
        *,
        now: datetime,
        active: QueueCycleEntry | None = None,
        waiting_reason: str | None = None,
    ) -> None:
        """发布最多四项预览；已到期项始终按父级顺序排列。"""

        due = sorted(
            (entry for entry in entries if entry.next_run_at <= now),
            key=lambda entry: entry.parent_index,
        )
        future = sorted(
            (entry for entry in entries if entry.next_run_at > now),
            key=lambda entry: (entry.next_run_at, entry.parent_index),
        )
        ordered = [*due, *future]
        if active is not None:
            ordered = [
                active,
                *(
                    entry
                    for entry in ordered
                    if entry.queue_item_id != active.queue_item_id
                ),
            ]

        preview = [
            self._cycle_preview_payload(
                entry,
                now=now,
                is_running=(
                    active is not None
                    and entry.queue_item_id == active.queue_item_id
                ),
            )
            for entry in ordered[:4]
        ]
        self.task_info.cycle_queue_id = self.task_info.queue_id
        self.task_info.cycle_current_item_id = (
            active.queue_item_id if active is not None else None
        )
        self.task_info.cycle_next_list = preview
        self.task_info.cycle_next_run_at = (
            str(preview[0]["nextRunAt"]) if preview else None
        )
        self.task_info.cycle_waiting_reason = waiting_reason
        await self.task_info.on_change()

    async def _run_cycle_script(
        self,
        queue_uid: uuid.UUID,
        entry: QueueCycleEntry,
    ) -> bool | None:
        """运行一个到期项；租约冲突返回 None，调用方稍后重试。"""

        if self._lease_manager is None:
            raise RuntimeError("循环任务未绑定租约管理器")

        task_uid = uuid.UUID(self.task_info.task_id)
        script_uid = uuid.UUID(entry.script_id)
        try:
            await self._lease_manager._acquire_script_leases(
                task_uid,
                [script_uid],
            )
        except Exception as error:
            self.task_info.script_list[entry.script_index].status = "等待"
            logger.warning(
                f"循环队列项 {entry.queue_item_id} 暂不可执行，本轮跳过: "
                f"{type(error).__name__}: {error}"
            )
            await self._set_cycle_state(
                await self._collect_cycle_entries(queue_uid, datetime.now()),
                now=datetime.now(),
                active=entry,
                waiting_reason=f"{type(error).__name__}: {error}",
            )
            return None

        try:
            queue_item = Config.QueueConfig[queue_uid].QueueItem[
                uuid.UUID(entry.queue_item_id)
            ]
            script_item = self.task_info.script_list[entry.script_index]
            started_at = datetime.now()
            started_text = format_cycle_datetime(started_at)
            previous_next_run = queue_item.get("Schedule", "NextRunAt")
            previous_revision = queue_item.get("Data", "CycleRevision")
            run_id = str(uuid.uuid4())
            provisional_next_run = calculate_next_cycle_after_run(
                mode=queue_item.get("Schedule", "Mode"),
                days=queue_item.get("Schedule", "Days"),
                time_text=queue_item.get("Schedule", "Time"),
                interval_minutes=queue_item.get(
                    "Schedule", "IntervalMinutes"
                ),
                interval_anchor=queue_item.get(
                    "Schedule", "IntervalAnchor"
                ),
                started_at=started_at,
                finished_at=started_at,
            )
            # 在产生外部脚本副作用前一次提交“已开始 + 已消费 due”；
            # 即使随后进程崩溃，重启也不会立即重复同一到期项。
            await _set_many_with_expected(
                queue_item,
                [
                    ("Data", "LastCycleStartedAt", started_text),
                    ("Data", "CycleRunId", run_id),
                    ("Data", "CycleState", "running"),
                    ("Data", "CycleRevision", previous_revision + 1),
                    ("Data", "CycleResult", ""),
                    ("Data", "CycleError", ""),
                    ("Data", "CycleUpdatedAt", started_text),
                    (
                        "Schedule",
                        "NextRunAt",
                        format_cycle_datetime(provisional_next_run),
                    ),
                ],
                expected=[
                    ("Data", "CycleRevision", previous_revision),
                    ("Schedule", "NextRunAt", previous_next_run),
                ],
            )
            self._active_cycle_run_ids[entry.queue_item_id] = run_id
            script_item.status = "运行"
            await self._set_cycle_state(
                await self._collect_cycle_entries(queue_uid, started_at),
                now=started_at,
                active=entry,
            )

            script_event_data = self._build_script_event_data()
            await PluginEventFactory.emit_script_event_async(
                event=PluginEventNames.SCRIPT_START,
                source="core.task_manager",
                task_id=self.task_info.task_id,
                script_id=entry.script_id,
                script_name=entry.script_name,
                mode=self.task_info.mode,
                status=script_item.status,
                data=script_event_data,
            )
        except BaseException:
            self._active_cycle_run_ids.pop(entry.queue_item_id, None)
            await self._lease_manager._release_script_leases(
                task_uid,
                [script_uid],
            )
            raise

        cancelled = False
        run_error: str | None = None
        success = False
        try:
            capability = await Config.get_script_record_capability(script_uid)
            if not capability.available:
                raise RuntimeError(
                    capability.unavailable_reason or "脚本当前不可用"
                )
            if "AutoProxy" not in (capability.supported_modes or ()):
                raise RuntimeError("脚本不支持循环运行所需的 AutoProxy 模式")
            provider = self._resolve_script_provider(script_uid)
            await self.spawn(provider.create_manager(script_item))
        except asyncio.CancelledError:
            cancelled = True
            run_error = "任务已取消"
            script_item.status = "取消"
            raise
        except Exception as error:
            run_error = f"{type(error).__name__}: {error}"
            script_item.status = "异常"
            logger.exception(
                f"循环队列脚本 {entry.script_name} 运行异常: {error}"
            )
        finally:
            finished_at = datetime.now()
            finished_text = format_cycle_datetime(finished_at)
            if not cancelled:
                success = (
                    run_error is None
                    and is_cycle_script_success(
                        script_item.status,
                        (user.status for user in script_item.user_list),
                    )
                )
                if not success and run_error is None:
                    run_error = "脚本状态未完成"
                    script_item.status = "异常"
            final_state = (
                "cancelled"
                if cancelled
                else "succeeded"
                if success
                else "failed"
            )
            final_result = (
                "cancelled"
                if cancelled
                else "success"
                if success
                else "error"
            )
            next_run_at = provisional_next_run
            if not cancelled:
                next_run_at = calculate_next_cycle_after_run(
                    mode=queue_item.get("Schedule", "Mode"),
                    days=queue_item.get("Schedule", "Days"),
                    time_text=queue_item.get("Schedule", "Time"),
                    interval_minutes=queue_item.get(
                        "Schedule", "IntervalMinutes"
                    ),
                    interval_anchor=queue_item.get(
                        "Schedule", "IntervalAnchor"
                    ),
                    started_at=started_at,
                    finished_at=finished_at,
                )
            try:
                await _set_many_with_expected(
                    queue_item,
                    [
                        ("Data", "LastCycleFinishedAt", finished_text),
                        ("Data", "CycleState", final_state),
                        (
                            "Data",
                            "CycleRevision",
                            previous_revision + 2,
                        ),
                        ("Data", "CycleResult", final_result),
                        ("Data", "CycleError", run_error or ""),
                        ("Data", "CycleUpdatedAt", finished_text),
                        (
                            "Schedule",
                            "NextRunAt",
                            format_cycle_datetime(next_run_at),
                        ),
                    ],
                    expected=[
                        ("Data", "CycleRunId", run_id),
                        ("Data", "CycleState", "running"),
                        (
                            "Data",
                            "CycleRevision",
                            previous_revision + 1,
                        ),
                        (
                            "Schedule",
                            "NextRunAt",
                            format_cycle_datetime(provisional_next_run),
                        ),
                    ],
                )
            finally:
                self._active_cycle_run_ids.pop(entry.queue_item_id, None)
                await self._lease_manager._release_script_leases(
                    task_uid,
                    [script_uid],
                )

        result_event = (
            PluginEventNames.SCRIPT_SUCCESS
            if success
            else PluginEventNames.SCRIPT_ERROR
        )
        await PluginEventFactory.emit_script_event_async(
            event=result_event,
            source="core.task_manager",
            task_id=self.task_info.task_id,
            script_id=entry.script_id,
            script_name=entry.script_name,
            mode=self.task_info.mode,
            status=script_item.status,
            error=run_error,
            result=result_event,
            data=script_event_data,
        )
        await PluginEventFactory.emit_script_event_async(
            event=PluginEventNames.SCRIPT_EXIT,
            source="core.task_manager",
            task_id=self.task_info.task_id,
            script_id=entry.script_id,
            script_name=entry.script_name,
            mode=self.task_info.mode,
            status=script_item.status,
            error=run_error,
            result=result_event,
            data=script_event_data,
        )
        return success

    async def _run_cycle_task(self) -> None:
        if self.task_info.queue_id is None:
            raise RuntimeError("循环运行必须选择队列")
        queue_uid = uuid.UUID(self.task_info.queue_id)
        await self._emit_task_start()
        logger.info(f"循环运行队列启动: {queue_uid}")

        while True:
            if queue_uid not in Config.QueueConfig:
                raise RuntimeError("循环队列已被删除")
            if not Config.QueueConfig[queue_uid].get("Info", "CycleEnabled"):
                logger.info(f"循环队列 {queue_uid} 已关闭循环开关，结束任务")
                return

            now = datetime.now()
            entries = await self._collect_cycle_entries(queue_uid, now)
            due_entries = sorted(
                (
                    entry
                    for entry in entries
                    if entry.next_run_at <= now
                ),
                key=lambda entry: entry.parent_index,
            )
            if not due_entries:
                await self._set_cycle_state(
                    entries,
                    now=now,
                    waiting_reason=(
                        "没有启用且有效的循环队列项"
                        if not entries
                        else "等待下一次运行"
                    ),
                )
                wait_seconds = CYCLE_IDLE_POLL_SECONDS
                if entries:
                    wait_seconds = min(
                        CYCLE_IDLE_POLL_SECONDS,
                        max(
                            1,
                            int(
                                (
                                    min(
                                        entry.next_run_at
                                        for entry in entries
                                    )
                                    - now
                                ).total_seconds()
                            ),
                        ),
                    )
                await asyncio.sleep(wait_seconds)
                continue

            ran_any = False
            for entry in due_entries:
                self.task_info.current_index = entry.script_index
                result = await self._run_cycle_script(queue_uid, entry)
                if result is not None:
                    ran_any = True
            if not ran_any:
                await asyncio.sleep(CYCLE_LEASE_RETRY_SECONDS)

    async def main_task(self):

        await self.prepare()
        if self.task_info.mode == "CycleRun":
            await self._run_cycle_task()
            return
        await self._emit_task_start()
        await self.task_info._emit_task_progress()

        logger.info(
            f"开始运行任务: {self.task_info.task_id}, 模式: {self.task_info.mode}"
        )

        # 可选：从指定脚本开始执行（仅队列任务）
        start_index = 0
        if (
            getattr(self.task_info, "resume_from_script_id", None)
            and self.task_info.queue_id is not None
        ):
            resume_id = str(self.task_info.resume_from_script_id)
            for idx, item in enumerate(self.task_info.script_list):
                if item.script_id == resume_id:
                    start_index = idx
                    break
            else:
                logger.warning(
                    f"未找到 resume_from_script_id={resume_id}，将从队列首项开始执行"
                )

        for i in range(start_index):
            self.task_info.script_list[i].status = "跳过"

        for self.task_info.current_index, script_item in enumerate(
            self.task_info.script_list
        ):
            if self.task_info.current_index < start_index:
                continue

            current_script_uid = uuid.UUID(script_item.script_id)

            if current_script_uid not in Config.ScriptConfig:
                script_item.status = "异常"
                logger.info(f"跳过任务: {current_script_uid}, 对应脚本已被删除")
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error",
                        message=f"任务 {script_item.name} 对应脚本已被删除",
                    ),
                )
                continue

            try:
                provider = self._resolve_script_provider(current_script_uid)
            except KeyError:
                logger.error(
                    f"不支持的脚本类型: {type(Config.ScriptConfig[current_script_uid]).__name__}"
                )
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(level="error", message="脚本类型不支持"),
                )
                continue

            capability = await Config.get_script_record_capability(current_script_uid)
            if not capability.available:
                script_item.status = "异常"
                reason = capability.unavailable_reason or "脚本当前不可用"
                logger.error(f"脚本类型 {provider.type_key} 当前不可用: {reason}")
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(level="error", message=reason),
                )
                continue

            if self.task_info.mode not in (capability.supported_modes or ()):
                script_item.status = "异常"
                logger.error(
                    f"脚本类型 {provider.type_key} 不支持任务模式 {self.task_info.mode}"
                )
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error",
                        message=f"脚本类型 {provider.type_key} 不支持任务模式 {self.task_info.mode}",
                    ),
                )
                continue

            script_item.status = "运行"
            logger.info(f"任务开始: {current_script_uid}")
            script_event_data = self._build_script_event_data()
            await PluginEventFactory.emit_script_event_async(
                event=PluginEventNames.SCRIPT_START,
                source="core.task_manager",
                task_id=self.task_info.task_id,
                script_id=str(current_script_uid),
                script_name=script_item.name,
                mode=self.task_info.mode,
                status=script_item.status,
                data=script_event_data,
            )

            task_item = provider.create_manager(script_item)

            try:
                await self.spawn(task_item)
            except asyncio.CancelledError:
                error_text = "CancelledError: 任务执行被取消"
                self._exit_result = "cancelled"
                self._exit_error = error_text
                await PluginEventFactory.emit_script_event_async(
                    event=PluginEventNames.SCRIPT_CANCELLED,
                    source="core.task_manager",
                    task_id=self.task_info.task_id,
                    script_id=str(current_script_uid),
                    script_name=script_item.name,
                    mode=self.task_info.mode,
                    status=script_item.status,
                    error=error_text,
                    result=PluginEventNames.SCRIPT_CANCELLED,
                    data=script_event_data,
                )
                await PluginEventFactory.emit_script_event_async(
                    event=PluginEventNames.SCRIPT_EXIT,
                    source="core.task_manager",
                    task_id=self.task_info.task_id,
                    script_id=str(current_script_uid),
                    script_name=script_item.name,
                    mode=self.task_info.mode,
                    status=script_item.status,
                    error=error_text,
                    result=PluginEventNames.SCRIPT_CANCELLED,
                    data=script_event_data,
                )
                raise
            except Exception as e:
                error_text = f"{type(e).__name__}: {e}"
                self._exit_result = "error"
                self._exit_error = error_text
                await PluginEventFactory.emit_script_event_async(
                    event=PluginEventNames.SCRIPT_ERROR,
                    source="core.task_manager",
                    task_id=self.task_info.task_id,
                    script_id=str(current_script_uid),
                    script_name=script_item.name,
                    mode=self.task_info.mode,
                    status=script_item.status,
                    error=error_text,
                    result=PluginEventNames.SCRIPT_ERROR,
                    data=script_event_data,
                )
                await PluginEventFactory.emit_script_event_async(
                    event=PluginEventNames.SCRIPT_EXIT,
                    source="core.task_manager",
                    task_id=self.task_info.task_id,
                    script_id=str(current_script_uid),
                    script_name=script_item.name,
                    mode=self.task_info.mode,
                    status=script_item.status,
                    error=error_text,
                    result=PluginEventNames.SCRIPT_ERROR,
                    data=script_event_data,
                )
                raise
            else:
                result_event = (
                    PluginEventNames.SCRIPT_SUCCESS
                    if script_item.status == "完成"
                    else PluginEventNames.SCRIPT_ERROR
                )
                result_error = None
                if result_event == PluginEventNames.SCRIPT_ERROR:
                    result_error = "脚本状态未完成"
                    self._exit_result = "error"
                    self._exit_error = result_error

                await PluginEventFactory.emit_script_event_async(
                    event=result_event,
                    source="core.task_manager",
                    task_id=self.task_info.task_id,
                    script_id=str(current_script_uid),
                    script_name=script_item.name,
                    mode=self.task_info.mode,
                    status=script_item.status,
                    error=result_error,
                    result=result_event,
                    data=script_event_data,
                )
                await PluginEventFactory.emit_script_event_async(
                    event=PluginEventNames.SCRIPT_EXIT,
                    source="core.task_manager",
                    task_id=self.task_info.task_id,
                    script_id=str(current_script_uid),
                    script_name=script_item.name,
                    mode=self.task_info.mode,
                    status=script_item.status,
                    error=result_error,
                    result=result_event,
                    data=script_event_data,
                )

    async def final_task(self) -> None:

        logger.info(f"任务结束: {self.task_info.task_id}")

        await Publisher.send(
            id=str(self.task_info.task_id),
            type=protocol.TASK_COMPLETED,
            data=WSTaskCompletedData(
                result=self.task_info.result,
                task_info=self.task_info.asdict,
            ),
        )

        await self.task_info._emit_task_progress()
        await self._emit_task_exit()

        if self.task_info.mode == "AutoProxy" and self.task_info.queue_id is not None:

            if Config.power_sign == "NoAction":
                Config.power_sign = Config.QueueConfig[
                    uuid.UUID(self.task_info.queue_id)
                ].get("Info", "AfterAccomplish")
                await Publisher.send(
                    id=protocol.ID_MAIN,
                    type=protocol.POWER_SIGN_UPDATED,
                    data=WSPowerSignData(signal=Config.power_sign),
                )

        # 任务结束时触发游戏签到
        from app.core.timer import MainTimer

        task = asyncio.create_task(MainTimer.try_game_sign_for_task())

        def _on_task_done(t):
            if not t.cancelled():
                e = t.exception()
                if e:
                    logger.error("任务触发的游戏签到执行异常", exc_info=e)

        task.add_done_callback(_on_task_done)

    async def on_crash(self, e: Exception) -> None:
        """处理任务异常并记录退出状态。"""
        if self._exit_result == "success":
            self._exit_result = "error"
            self._exit_error = f"{type(e).__name__}: {e}"

        logger.exception(f"任务 {self.task_info.task_id} 出现异常: {e}")
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(
                level="error",
                message=f"任务出现异常: {type(e).__name__}: {str(e)}",
            ),
        )


class _TaskManager:
    """业务调度器"""

    def __init__(self):
        super().__init__()

        self.task_info: Dict[uuid.UUID, TaskInfo] = {}
        self.task_handler: Dict[uuid.UUID, Task] = {}
        self._startup_queue_started = False
        self._startup_queue_running = False
        self._script_lease_guard = asyncio.Lock()
        self._script_leases: dict[uuid.UUID, uuid.UUID] = {}
        self._queue_leases: dict[uuid.UUID, uuid.UUID] = {}

    @staticmethod
    def _queue_script_ids(
        queue_id: uuid.UUID,
        *,
        enabled_only: bool = False,
    ) -> list[uuid.UUID]:
        """返回队列中实际引用的脚本 ID。"""

        return [
            uuid.UUID(script_id)
            for queue_item in Config.QueueConfig[queue_id].QueueItem.values()
            if (
                script_id := str(queue_item.get("Info", "ScriptId") or "").strip()
            )
            and script_id != "-"
            and (
                not enabled_only
                or queue_item.get("Schedule", "Enabled")
            )
        ]

    async def _validate_task_capabilities(
        self,
        mode: Literal["AutoProxy", "ManualReview", "ScriptConfig"],
        script_ids: list[uuid.UUID],
    ) -> None:
        """在创建任务前校验所有目标脚本的逐记录能力。"""

        for script_id in script_ids:
            if script_id not in Config.ScriptConfig:
                raise ValueError(f"任务引用的脚本 {script_id} 不存在")
            script = Config.ScriptConfig[script_id]
            capability = await Config.get_script_record_capability(script_id)
            script_name = script.get("Info", "Name") or str(script_id)
            if not capability.available:
                reason = capability.unavailable_reason or "脚本当前不可用"
                raise RuntimeError(f"脚本 {script_name} 当前不可用: {reason}")
            if mode not in (capability.supported_modes or ()):
                raise RuntimeError(f"脚本 {script_name} 不支持任务模式 {mode}")

    async def _acquire_script_leases(
        self,
        task_uid: uuid.UUID,
        script_ids: list[uuid.UUID],
    ) -> None:
        """Atomically reserve every script referenced by one task."""

        unique_ids = list(dict.fromkeys(script_ids))
        async with self._script_lease_guard:
            for script_id in unique_ids:
                owner = self._script_leases.get(script_id)
                if owner is not None and owner != task_uid:
                    raise RuntimeError(
                        f"脚本 {script_id} 已由任务 {owner} 占用"
                    )
                if Config.ScriptConfig[script_id].is_locked and owner != task_uid:
                    raise RuntimeError(
                        f"脚本 {script_id} 已被其他运行时锁定"
                    )

            registered: list[uuid.UUID] = []
            acquired: list[uuid.UUID] = []
            try:
                for script_id in unique_ids:
                    self._script_leases[script_id] = task_uid
                    registered.append(script_id)
                    await Config.ScriptConfig[script_id].lock()
                    acquired.append(script_id)
            except BaseException:
                for script_id in reversed(acquired):
                    await Config.ScriptConfig[script_id].unlock()
                for script_id in reversed(registered):
                    if self._script_leases.get(script_id) == task_uid:
                        self._script_leases.pop(script_id, None)
                raise

    async def _release_script_leases(
        self,
        task_uid: uuid.UUID,
        only_script_ids: list[uuid.UUID] | None = None,
    ) -> None:
        """Release only leases owned by ``task_uid`` and sweep residual locks."""

        async with self._script_lease_guard:
            allowed = (
                set(only_script_ids) if only_script_ids is not None else None
            )
            script_ids = [
                script_id
                for script_id, owner in self._script_leases.items()
                if owner == task_uid
                and (allowed is None or script_id in allowed)
            ]
            for script_id in reversed(script_ids):
                script = (
                    Config.ScriptConfig[script_id]
                    if script_id in Config.ScriptConfig
                    else None
                )
                if script is not None and script.is_locked:
                    await script.unlock()
                if self._script_leases.get(script_id) == task_uid:
                    self._script_leases.pop(script_id, None)

    async def _acquire_queue_lease(
        self,
        task_uid: uuid.UUID,
        queue_uid: uuid.UUID,
    ) -> None:
        """同一父队列只允许一个生产任务，空队列也不能绕过互斥。"""

        async with self._script_lease_guard:
            owner = self._queue_leases.get(queue_uid)
            if owner is not None and owner != task_uid:
                raise RuntimeError(f"队列 {queue_uid} 已由任务 {owner} 占用")
            self._queue_leases[queue_uid] = task_uid

    async def _release_queue_lease(self, task_uid: uuid.UUID) -> None:
        async with self._script_lease_guard:
            for queue_uid, owner in list(self._queue_leases.items()):
                if owner == task_uid:
                    self._queue_leases.pop(queue_uid, None)

    @asynccontextmanager
    async def queue_edit(self, queue_uid: uuid.UUID):
        """阻止运行任务与队列结构/API 编辑交错。"""

        async with self._script_lease_guard:
            owner = self._queue_leases.get(queue_uid)
            if owner is not None:
                raise RuntimeError(
                    f"队列 {queue_uid} 正由任务 {owner} 运行，请先停止任务"
                )
            yield

    async def add_task(
        self,
        mode: Literal["AutoProxy", "ManualReview", "ScriptConfig", "CycleRun"],
        id: str,
        new_task_info: dict | None = None,
        resume_from_script_id: str | None = None,
    ) -> uuid.UUID:
        """
        添加任务, 根据 id 值搜索实际指向的任务配置

        Args:
            mode (str): 任务模式
            id (str): 任务项对应的配置 ID
            new_task_info (dict): 新任务项信息. Defaults to {}.

        Returns:
            uuid.UUID: 任务 UID
        """

        await _ensure_task_runtime_available()
        uid = uuid.UUID(id)
        if mode not in {
            "AutoProxy",
            "ManualReview",
            "ScriptConfig",
            "CycleRun",
        }:
            raise ValueError(f"不支持的任务模式: {mode}")

        if mode == "ScriptConfig":
            if uid in Config.ScriptConfig:
                task_uid = uuid.uuid4()
                queue_id = None
                script_uid = uid
                user_uid = "Default"
            else:
                for script_id, script in Config.ScriptConfig.items():
                    if uid in script.UserData:
                        task_uid = uuid.uuid4()
                        queue_id = None
                        script_uid = script_id
                        user_uid = uid
                        break
                else:
                    raise ValueError(f"任务 {uid} 无法找到对应脚本配置")
        elif uid in Config.QueueConfig:
            if mode == "CycleRun" and not Config.QueueConfig[uid].get(
                "Info", "CycleEnabled"
            ):
                raise RuntimeError("该队列未开启循环模式")
            task_uid = uuid.uuid4()
            queue_id = uid
            script_uid = None
            user_uid = None
        elif uid in Config.ScriptConfig:
            if mode == "CycleRun":
                raise RuntimeError("循环运行只能选择调度队列")
            task_uid = uuid.uuid4()
            queue_id = None
            script_uid = uid
            user_uid = None
        else:
            raise ValueError(f"任务 {uid} 无法找到对应脚本配置")

        target_script_ids = (
            self._queue_script_ids(
                queue_id,
                enabled_only=mode == "CycleRun",
            )
            if queue_id is not None
            else [script_uid] if script_uid is not None else []
        )
        try:
            if queue_id is not None:
                await self._acquire_queue_lease(task_uid, queue_id)
            capability_mode = (
                "AutoProxy" if mode == "CycleRun" else mode
            )
            await self._validate_task_capabilities(
                capability_mode,
                target_script_ids,
            )
            if mode != "CycleRun":
                await self._acquire_script_leases(
                    task_uid,
                    target_script_ids,
                )

            logger.info(f"创建任务: {task_uid}, 模式: {mode}")
            if new_task_info:
                await Publisher.send(
                    id=protocol.ID_TASK_MANAGER,
                    type=protocol.TASK_CREATED,
                    data=WSTaskCreatedData(
                        taskId=str(task_uid),
                        queueId=new_task_info.get("queueId"),
                        taskName=new_task_info.get("taskName"),
                        taskType=new_task_info.get("taskType"),
                    ),
                )
            self.task_info[task_uid] = TaskInfo(
                mode=mode,
                task_id=str(task_uid),
                queue_id=str(queue_id) if queue_id else None,
                script_id=str(script_uid) if script_uid else None,
                user_id=str(user_uid) if user_uid else None,
                resume_from_script_id=resume_from_script_id,
            )
            self.task_handler[task_uid] = Task(
                self.task_info[task_uid],
                lease_manager=self,
            )
            self.task_handler[task_uid].execute()
            asyncio.create_task(self.clean_task(task_uid))
        except BaseException:
            self.task_info.pop(task_uid, None)
            self.task_handler.pop(task_uid, None)
            await self._release_script_leases(task_uid)
            await self._release_queue_lease(task_uid)
            raise

        return task_uid

    async def clean_task(self, task_uid: uuid.UUID) -> None:
        power_enabled = False
        try:
            await self.task_handler[task_uid].accomplish.wait()
            power_enabled = bool(
                self.task_info[task_uid].mode
                not in {"ScriptConfig", "CycleRun"}
            )
        finally:
            await self._release_script_leases(task_uid)
            await self._release_queue_lease(task_uid)
            self.task_info.pop(task_uid, None)
            self.task_handler.pop(task_uid, None)

        if (
            power_enabled
            and len(self.task_handler) == 0
            and Config.power_sign != "NoAction"
        ):
            logger.info(f"所有任务已结束，准备执行电源操作: {Config.power_sign}")
            # System 逐秒发布 power.countdown.updated，避免新旧倒计时重复显示。
            await System.start_power_task()

    async def stop_task(self, task_id: str) -> None:
        """
        中止任务

        :param task_id: 任务ID
        """

        logger.info(f"中止任务: {task_id}")

        if task_id == "ALL":
            task_item_list = list(self.task_handler.values())
            for task_item in task_item_list:
                if not task_item.is_closing:
                    task_item.cancel()
                    task_item.is_closing = True
                    await task_item.accomplish.wait()
        else:
            uid = uuid.UUID(task_id)
            if uid not in self.task_handler:
                raise ValueError("未找到对应任务")
            if self.task_handler[uid].is_closing:
                raise RuntimeError("任务已在中止中")
            self.task_handler[uid].cancel()
            self.task_handler[uid].is_closing = True
            logger.info(f"等待任务 {task_id} 结束...")
            await self.task_handler[uid].accomplish.wait()
            logger.info(f"任务 {task_id} 已结束")

    async def start_startup_queue(self):
        """开始运行启动时运行的调度队列"""

        await _ensure_task_runtime_available()
        if self._startup_queue_started:
            logger.info("启动时任务已触发，跳过重复运行")
            return
        if self._startup_queue_running:
            logger.info("启动时任务正在等待运行，跳过重复触发")
            return

        self._startup_queue_running = True

        try:
            await asyncio.sleep(10)

            if not MainConnection.is_connected:
                logger.info("主 WebSocket 已断开，启动时任务等待下次连接后运行")
                return

            self._startup_queue_started = True
            logger.info("开始运行启动时任务")
            for uid, queue in Config.QueueConfig.items():

                if queue.get("Info", "StartUpEnabled"):
                    logger.info(f"启动时需要运行的队列：{uid}")
                    try:
                        mode = (
                            "CycleRun"
                            if queue.get("Info", "CycleEnabled")
                            else "AutoProxy"
                        )
                        await TaskManager.add_task(
                            mode,
                            str(uid),
                            new_task_info={
                                "queueId": str(uid),
                                "taskName": f"队列 - {queue.get('Info', 'Name')}",
                                "taskType": (
                                    "启动时循环"
                                    if mode == "CycleRun"
                                    else "启动时代理"
                                ),
                            },
                        )
                    except (RuntimeError, ValueError) as error:
                        logger.error(f"启动时队列 {uid} 无法创建任务：{error}")
                        continue
        finally:
            self._startup_queue_running = False

        logger.success("启动时任务开始运行")


TaskManager = _TaskManager()
