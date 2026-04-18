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


import asyncio
import uuid
from typing import Dict, Literal, cast

from app.models import GeneralConfig, MaaConfig, MaaEndConfig, SrcConfig
from app.models.task import TaskItem, ScriptItem, UserItem, TaskExecuteBase
from app.services import System
from app.utils import get_logger
from app.utils.constants import POWER_SIGN_MAP
from .config import Config
from .plugins import PluginEventFactory, PluginEventNames


logger = get_logger("业务调度")


def _resolve_queue_name(queue_id: str | None) -> str | None:
    """根据 queue_id 解析队列名，失败时返回 None"""
    if not queue_id:
        return None

    try:
        return Config.QueueConfig[uuid.UUID(queue_id)].get("Info", "Name")
    except Exception:
        return None


def _build_script_summaries(script_list: list[ScriptItem]) -> list[dict[str, str]]:
    """构建脚本摘要，供任务事件复用"""
    return [
        {
            "script_id": item.script_id,
            "script_name": item.name,
            "status": item.status,
        }
        for item in script_list
    ]


def _resolve_final_script(task_info: TaskItem) -> ScriptItem | None:
    """获取任务结束时最能代表结果的脚本项"""
    if 0 <= task_info.current_index < len(task_info.script_list):
        return task_info.script_list[task_info.current_index]
    if task_info.script_list:
        return task_info.script_list[-1]
    return None


class TaskInfo(TaskItem):
    def _has_meaningful_current_log(self) -> bool:
        """判断当前脚本日志里是否有有效内容"""
        if not (0 <= self.current_index < len(self.script_list)):
            return False

        return bool(self.script_list[self.current_index].log.strip())

    async def _emit_task_progress(self) -> None:
        """发送 task.progress 事件，避免重复广播相同快照"""
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
        """发送 task.log 事件，带上当前脚本日志"""
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

    async def emit_task_progress(self) -> None:
        """公开的任务进度事件发送入口"""
        await self._emit_task_progress()

    async def emit_task_log(self) -> None:
        """公开的任务日志事件发送入口"""
        await self._emit_task_log()

    async def on_change(self):
        """任务状态变化后推送 WebSocket 增量更新并广播插件事件"""

        await Config.send_websocket_message(
            id=self.task_id,
            type="Update",
            data={"task_info": self.asdict},
        )
        if self.current_index != -1:
            await Config.send_websocket_message(
                id=self.task_id,
                type="Update",
                data={"log": self.script_list[self.current_index].log},
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

    def _build_script_event_data(self) -> Dict[str, str | None]:
        """附加到 script.* 事件里的任务上下文"""
        return {
            "queue_id": self.task_info.queue_id,
            "queue_name": _resolve_queue_name(self.task_info.queue_id),
        }

    async def _emit_task_start(self) -> None:
        """发送 task.start 事件"""
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
        """发送 task.exit 事件"""
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
        """根据任务模式解析脚本清单并初始化运行项"""

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
        """串行执行任务中每个脚本项"""

        await self.prepare()
        await self._emit_task_start()
        await self.task_info.emit_task_progress()

        logger.info(
            f"开始运行任务: {self.task_info.task_id}, 模式: {self.task_info.mode}"
        )

        from app.task import MaaManager, SrcManager, GeneralManager, MaaEndManager

        # 依次运行任务
        for self.task_info.current_index, script_item in enumerate(
            self.task_info.script_list
        ):
            current_script_uid = uuid.UUID(script_item.script_id)

            # 检查任务对应脚本是否仍存在
            if current_script_uid not in Config.ScriptConfig:
                script_item.status = "异常"
                logger.info(f"跳过任务: {current_script_uid}, 该任务对应脚本已被删除")
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={"Error": f"任务 {script_item.name} 对应脚本已被删除"},
                )
                continue

            # 检查任务是否已被其他任务调度器锁定
            if Config.ScriptConfig[current_script_uid].is_locked:
                script_item.status = "跳过"
                logger.info(
                    f"跳过任务: {current_script_uid}, 该任务已被其他任务调度器锁定"
                )
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={"Warning": f"任务 {script_item.name} 已被其他任务调度器锁定"},
                )
                continue

            # 标记为运行中
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

            if isinstance(Config.ScriptConfig[current_script_uid], MaaConfig):
                task_item = MaaManager(script_item)
            elif isinstance(Config.ScriptConfig[current_script_uid], SrcConfig):
                task_item = SrcManager(script_item)
            elif isinstance(Config.ScriptConfig[current_script_uid], GeneralConfig):
                task_item = GeneralManager(script_item)
            elif isinstance(Config.ScriptConfig[current_script_uid], MaaEndConfig):
                task_item = MaaEndManager(script_item)
            else:
                logger.error(
                    f"不支持的脚本类型: {type(Config.ScriptConfig[current_script_uid]).__name__}"
                )
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={"Error": "脚本类型不支持"},
                )
                continue

            # 运行任务
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
                current_status = cast(str, script_item.status)
                result_event = (
                    PluginEventNames.SCRIPT_SUCCESS
                    if current_status == "完成"
                    else PluginEventNames.SCRIPT_ERROR
                )
                result_error = None
                if result_event == PluginEventNames.SCRIPT_ERROR:
                    result_error = "脚本状态非完成"
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
        """任务收尾：上报结果并处理电源动作信号"""

        logger.info(f"任务结束: {self.task_info.task_id}")

        await Config.send_websocket_message(
            id=str(self.task_info.task_id),
            type="Signal",
            data={"Accomplish": self.task_info.result},
        )

        await self.task_info.emit_task_progress()
        await self._emit_task_exit()

        if self.task_info.mode == "AutoProxy" and self.task_info.queue_id is not None:
            if Config.power_sign == "NoAction":
                Config.power_sign = Config.QueueConfig[
                    uuid.UUID(self.task_info.queue_id)
                ].get("Info", "AfterAccomplish")
                await Config.send_websocket_message(
                    id="Main", type="Update", data={"PowerSign": Config.power_sign}
                )

    async def on_crash(self, e: Exception) -> None:
        """任务异常回调：记录日志并向前端推送错误信息"""
        if self._exit_result == "success":
            self._exit_result = "error"
            self._exit_error = f"{type(e).__name__}: {e}"

        logger.exception(f"任务 {self.task_info.task_id} 出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"任务出现异常: {type(e).__name__}: {str(e)}"},
        )


class _TaskManager:
    """业务调度器"""

    def __init__(self):
        super().__init__()

        self.task_info: Dict[uuid.UUID, TaskInfo] = {}
        self.task_handler: Dict[uuid.UUID, Task] = {}
        self._mutex = asyncio.Lock()
        self._background_tasks: set[asyncio.Task[None]] = set()

    def _track_background_task(self, task: asyncio.Task[None]) -> None:
        """跟踪后台任务，避免异常静默与任务泄漏。"""

        self._background_tasks.add(task)

        def _done(done_task: asyncio.Task[None]) -> None:
            self._background_tasks.discard(done_task)
            if done_task.cancelled():
                return
            exc = done_task.exception()
            if exc is not None:
                done_task.get_loop().call_exception_handler(
                    {
                        "message": "TaskManager 后台任务执行失败",
                        "exception": exc,
                        "task": done_task,
                    }
                )

        task.add_done_callback(_done)

    async def add_task(
        self,
        mode: Literal["AutoProxy", "ManualReview", "ScriptConfig"],
        id: str,
        new_task_info: dict[str, str] | None = None,
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

        async with self._mutex:
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

            if script_uid is not None and Config.ScriptConfig[script_uid].is_locked:
                raise RuntimeError(
                    f"任务 {Config.ScriptConfig[script_uid].get('Info', 'Name')} 已在运行"
                )

            logger.info(f"创建任务: {task_uid}, 模式: {mode}")
            if new_task_info:
                new_task_info["newTask"] = str(task_uid)
                await Config.send_websocket_message(
                    id="TaskManager", type="Signal", data=new_task_info
                )
            self.task_info[task_uid] = TaskInfo(
                mode=mode,
                task_id=str(task_uid),
                queue_id=str(queue_id) if queue_id else None,
                script_id=str(script_uid) if script_uid else None,
                user_id=str(user_uid) if user_uid else None,
            )
            self.task_handler[task_uid] = Task(self.task_info[task_uid])
            self.task_handler[task_uid].execute()
            self._track_background_task(asyncio.create_task(self.clean_task(task_uid)))

            return task_uid

    async def clean_task(self, task_uid: uuid.UUID) -> None:
        await self.task_handler[task_uid].accomplish.wait()
        power_enabled = bool(self.task_info[task_uid].mode != "ScriptConfig")
        self.task_info.pop(task_uid, None)
        self.task_handler.pop(task_uid, None)

        if (
            power_enabled
            and len(self.task_handler) == 0
            and Config.power_sign != "NoAction"
        ):
            logger.info(f"所有任务已结束，准备执行电源操作: {Config.power_sign}")
            await Config.send_websocket_message(
                id="Main",
                type="Message",
                data={
                    "type": "Countdown",
                    "title": f"{POWER_SIGN_MAP[Config.power_sign]}倒计时",
                    "message": f"程序将在倒计时结束后执行 {POWER_SIGN_MAP[Config.power_sign]} 操作",
                },
            )
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

        await asyncio.sleep(10)

        logger.info("开始运行启动时任务")
        for uid, queue in Config.QueueConfig.items():
            if queue.get("Info", "StartUpEnabled"):
                logger.info(f"启动时需要运行的队列：{uid}")
                await TaskManager.add_task(
                    "AutoProxy",
                    str(uid),
                    new_task_info={
                        "queueId": str(uid),
                        "taskName": f"队列 - {queue.get('Info', 'Name')}",
                        "taskType": "启动时代理",
                    },
                )

        logger.success("启动时任务开始运行")


TaskManager = _TaskManager()
