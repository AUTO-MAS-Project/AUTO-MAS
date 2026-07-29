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
from typing import Dict, Literal

from .config import Config
from .ws import MainConnection, Publisher, protocol
from app.plugins import PluginEventFactory, PluginEventNames
from .script_types import script_type_registry
from app.services import System
from app.models.task import TaskItem, ScriptItem, UserItem, TaskExecuteBase
from app.models.schema import (
    TaskRuntimeSnapshot,
    TaskRuntimeSnapshotItem,
    WSTaskCompletedData,
    WSTaskCreatedData,
    WSTaskInfoUpdatedData,
    WSTaskLogUpdatedData,
    WSTaskNoticeData,
    WSPowerSignData,
)
from app.utils import get_logger


logger = get_logger("业务调度")


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
            data=WSTaskInfoUpdatedData(task_info=self.asdict),
        )
        if self.current_index != -1:
            await Publisher.send(
                id=self.task_id,
                type=protocol.TASK_LOG_UPDATED,
                data=WSTaskLogUpdatedData(
                    log=self.script_list[self.current_index].log
                ),
            )

        await self._emit_task_progress()
        await self._emit_task_log()


class Task(TaskExecuteBase):

    def __init__(self, task_info: TaskInfo):
        super().__init__()
        self.task_info = task_info
        self.is_closing = False
        self._exit_result = "success"
        self._exit_error: str | None = None

    def _resolve_script_provider(self, script_uid: uuid.UUID):
        """解析脚本对应的 provider，兼容插件脚本。"""
        from app.models.plugin_script_config import PluginScriptConfig
        from .script_types import (
            build_legacy_fallback_provider_by_script_config,
        )

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

    async def main_task(self):

        await self.prepare()
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

            if Config.ScriptConfig[current_script_uid].is_locked:
                script_item.status = "跳过"
                logger.info(f"跳过任务: {current_script_uid}, 脚本已被其他任务锁定")
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="warning",
                        message=f"任务 {script_item.name} 已被其他任务调度器锁定",
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

        MainTimer.schedule_game_sign_for_task()

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
        self._cleanup_tasks: set[asyncio.Task[None]] = set()
        self._stop_all_lock = asyncio.Lock()
        self._stopping_all = False
        self._startup_queue_started = False
        self._startup_queue_running = False

    @staticmethod
    def _queue_script_ids(queue_id: uuid.UUID) -> list[uuid.UUID]:
        """返回队列中实际引用的脚本 ID。"""

        return [
            uuid.UUID(script_id)
            for queue_item in Config.QueueConfig[queue_id].QueueItem.values()
            if (
                script_id := str(queue_item.get("Info", "ScriptId") or "").strip()
            )
            and script_id != "-"
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

    def get_runtime_snapshot(self) -> TaskRuntimeSnapshot:
        """返回当前运行任务的 HTTP 初始快照。"""

        tasks: list[TaskRuntimeSnapshotItem] = []
        for task_uid, task_info in list(self.task_info.items()):
            log = ""
            if 0 <= task_info.current_index < len(task_info.script_list):
                log = task_info.script_list[task_info.current_index].log
            handler = self.task_handler.get(task_uid)
            tasks.append(
                TaskRuntimeSnapshotItem(
                    taskId=str(task_uid),
                    mode=task_info.mode,
                    queueId=task_info.queue_id,
                    scriptId=task_info.script_id,
                    userId=task_info.user_id,
                    stopping=bool(handler and handler.is_closing),
                    task_info=task_info.asdict,
                    log=log,
                )
            )
        return TaskRuntimeSnapshot(tasks=tasks)

    def _schedule_clean_task(self, task_uid: uuid.UUID) -> None:
        """创建并持有任务收尾协程，结束后统一移出集合。"""

        task = asyncio.create_task(self.clean_task(task_uid))
        self._cleanup_tasks.add(task)

        def _on_done(done_task: asyncio.Task[None]) -> None:
            self._cleanup_tasks.discard(done_task)
            if done_task.cancelled():
                return
            exc = done_task.exception()
            if exc is not None:
                logger.error(
                    f"任务收尾异常({task_uid}): {type(exc).__name__}: {exc}"
                )

        task.add_done_callback(_on_done)

    async def add_task(
        self,
        mode: Literal["AutoProxy", "ManualReview", "ScriptConfig"],
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

        uid = uuid.UUID(id)

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
            task_uid = uuid.uuid4()
            queue_id = uid
            script_uid = None
            user_uid = None
        elif uid in Config.ScriptConfig:
            task_uid = uuid.uuid4()
            queue_id = None
            script_uid = uid
            user_uid = None
        else:
            raise ValueError(f"任务 {uid} 无法找到对应脚本配置")

        target_script_ids = (
            self._queue_script_ids(queue_id)
            if queue_id is not None
            else [script_uid] if script_uid is not None else []
        )
        await self._validate_task_capabilities(mode, target_script_ids)

        if script_uid is not None and Config.ScriptConfig[script_uid].is_locked:
            raise RuntimeError(
                f"任务 {Config.ScriptConfig[script_uid].get('Info', 'Name')} 已在运行"
            )

        logger.info(f"创建任务: {task_uid}, 模式: {mode}")
        task_info = TaskInfo(
            mode=mode,
            task_id=str(task_uid),
            queue_id=str(queue_id) if queue_id else None,
            script_id=str(script_uid) if script_uid else None,
            user_id=str(user_uid) if user_uid else None,
            resume_from_script_id=resume_from_script_id,
        )
        task_handler = Task(task_info)

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
        self.task_info[task_uid] = task_info
        self.task_handler[task_uid] = task_handler
        try:
            task_handler.execute()
        except Exception:
            self.task_info.pop(task_uid, None)
            self.task_handler.pop(task_uid, None)
            raise
        self._schedule_clean_task(task_uid)

        return task_uid

    async def clean_task(self, task_uid: uuid.UUID) -> None:

        await self.task_handler[task_uid].accomplish.wait()
        power_enabled = bool(self.task_info[task_uid].mode != "ScriptConfig")
        self.task_info.pop(task_uid, None)
        self.task_handler.pop(task_uid, None)

        if (
            power_enabled
            and not self._stopping_all
            and len(self.task_handler) == 0
            and Config.power_sign != "NoAction"
        ):
            logger.info(f"所有任务已结束，准备执行电源操作: {Config.power_sign}")
            # 倒计时进度由电源任务经 power.countdown.updated 持续推送
            await System.start_power_task()

    async def stop_task(self, task_id: str) -> None:
        """
        中止任务

        :param task_id: 任务ID
        """

        logger.info(f"中止任务: {task_id}")

        if task_id == "ALL":
            async with self._stop_all_lock:
                self._stopping_all = True
                Config.power_sign = "NoAction"
                try:
                    task_item_list = list(self.task_handler.values())
                    for task_item in task_item_list:
                        if not task_item.is_closing:
                            task_item.cancel()
                            task_item.is_closing = True
                            await task_item.accomplish.wait()
                    cleanup_tasks = [
                        task for task in self._cleanup_tasks if not task.done()
                    ]
                    if cleanup_tasks:
                        await asyncio.gather(*cleanup_tasks)
                finally:
                    # final_task 可能重新写入 AfterAccomplish，主动停止全部任务时必须丢弃。
                    Config.power_sign = "NoAction"
                    self._stopping_all = False
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
                        await TaskManager.add_task(
                            "AutoProxy",
                            str(uid),
                            new_task_info={
                                "queueId": str(uid),
                                "taskName": f"队列 - {queue.get('Info', 'Name')}",
                                "taskType": "启动时代理",
                            },
                        )
                    except (RuntimeError, ValueError) as error:
                        logger.error(f"启动时队列 {uid} 无法创建任务：{error}")
                        continue
        finally:
            self._startup_queue_running = False

        logger.success("启动时任务开始运行")


TaskManager = _TaskManager()
