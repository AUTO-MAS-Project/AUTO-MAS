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
from datetime import datetime

from .config import (
    Config,
    MaaConfig,
    SrcConfig,
    GeneralConfig,
    MaaEndConfig,
    M9AConfig,
    OkwwConfig,
    HSRConfig,
)
from app.services import System
from app.models.task import TaskItem, ScriptItem, UserItem, TaskExecuteBase
from app.utils import get_logger
from app.task import (
    MaaManager,
    SrcManager,
    GeneralManager,
    MaaEndManager,
    M9AManager,
    OkwwManager,
    HSRManager,
)
from app.utils.constants import POWER_SIGN_MAP
from .queue_cycle import (
    QueueCycleEntry,
    calculate_next_after_finish,
    calculate_next_after_start,
    collect_waiting_cycle_entries,
    collect_queue_cycle_entries,
    format_cycle_time,
    is_cycle_script_success,
    pick_next_cycle_entry,
)


logger = get_logger("业务调度")

CYCLE_RETRY_SLEEP_SECONDS = 30
CYCLE_RUNNING_PREVIEW_REFRESH_SECONDS = 5
CYCLE_EMPTY_QUEUE_SLEEP_SECONDS = 60
CYCLE_LOG_RECORD_KEEP_COUNT = 50
CYCLE_ERROR_STATUS = "异常"
CYCLE_WAIT_STATUS = "等待"
CYCLE_SCRIPT_RUN_MODE = "AutoProxy"


class TaskInfo(TaskItem):

    async def on_change(self):
        data = {"task_info": self.asdict}
        if (
            self.mode == "CycleRun"
            or self.cycle_next is not None
            or self.cycle_next_list
        ):
            data["cycleNext"] = self.cycle_next
            data["cycleNextList"] = self.cycle_next_list
        await Config.send_websocket_message(
            id=self.task_id,
            type="Update",
            data=data,
        )
        if self.current_index != -1:
            await Config.send_websocket_message(
                id=self.task_id,
                type="Update",
                data={"log": self.script_list[self.current_index].log},
            )


class Task(TaskExecuteBase):

    def __init__(self, task_info: TaskInfo):
        super().__init__()
        self.task_info = task_info
        self.is_closing = False

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
        if self.task_info.mode == "CycleRun":
            await self._run_cycle_task()
            return

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

        # 依次运行任务
        for self.task_info.current_index in range(
            start_index, len(self.task_info.script_list)
        ):
            script_item = self.task_info.script_list[self.task_info.current_index]
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

            if isinstance(Config.ScriptConfig[current_script_uid], MaaConfig):
                task_item = MaaManager(script_item)
            elif isinstance(Config.ScriptConfig[current_script_uid], SrcConfig):
                task_item = SrcManager(script_item)
            elif isinstance(Config.ScriptConfig[current_script_uid], GeneralConfig):
                task_item = GeneralManager(script_item)
            elif isinstance(Config.ScriptConfig[current_script_uid], OkwwConfig):
                task_item = OkwwManager(script_item)
            elif isinstance(Config.ScriptConfig[current_script_uid], MaaEndConfig):
                task_item = MaaEndManager(script_item)
            elif isinstance(Config.ScriptConfig[current_script_uid], M9AConfig):
                task_item = M9AManager(script_item)
            elif isinstance(Config.ScriptConfig[current_script_uid], HSRConfig):
                task_item = HSRManager(script_item)
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
            await self.spawn(task_item)

    async def _run_cycle_task(self):
        if self.task_info.queue_id is None:
            raise RuntimeError("循环运行必须选择队列")

        queue_uid = uuid.UUID(self.task_info.queue_id)
        Config.running_cycle_queue_ids.add(queue_uid)
        logger.info(f"循环运行队列启动: {queue_uid}")
        try:
            await self._run_cycle_loop(queue_uid)
        finally:
            Config.running_cycle_queue_ids.discard(queue_uid)

    async def _run_cycle_loop(self, queue_uid: uuid.UUID) -> None:
        while True:
            now = datetime.now()
            queue = Config.QueueConfig[queue_uid]
            entries = collect_queue_cycle_entries(queue, Config.ScriptConfig, now)

            for entry in entries:
                queue_item = queue.QueueItem[uuid.UUID(entry.queue_item_id)]
                if (
                    queue_item.get("Schedule", "NextRunAt")
                    == "2000-01-01 00:00:00"
                    and entry.next_run_at > now
                ):
                    await queue_item.set(
                        "Schedule", "NextRunAt", format_cycle_time(entry.next_run_at)
                    )

            next_entry = pick_next_cycle_entry(entries)
            await self._set_cycle_preview(entries)

            if not entries:
                await asyncio.sleep(CYCLE_EMPTY_QUEUE_SLEEP_SECONDS)
                continue

            due_entries = [entry for entry in entries if entry.is_due]
            if not due_entries:
                wait_seconds = max(1, int((next_entry.next_run_at - now).total_seconds()))
                await asyncio.sleep(wait_seconds)
                continue

            pending = sorted(due_entries, key=lambda item: item.index)
            while pending:
                entry = pending.pop(0)
                script_uid = uuid.UUID(entry.script_id)
                script_item = self.task_info.script_list[entry.index]
                self.task_info.current_index = entry.index
                await self._set_cycle_preview(entries, entry)

                if Config.ScriptConfig[script_uid].is_locked:
                    script_item.status = CYCLE_WAIT_STATUS
                    logger.info(
                        f"循环队列脚本冲突，进入等待序列: {entry.script_name} ({entry.script_id})"
                    )
                    await self.task_info.on_change()
                    pending.append(entry)

                    has_runnable_pending = any(
                        not Config.ScriptConfig[
                            uuid.UUID(pending_entry.script_id)
                        ].is_locked
                        for pending_entry in pending
                    )
                    if not has_runnable_pending:
                        await asyncio.sleep(CYCLE_RETRY_SLEEP_SECONDS)
                    continue

                queue_item = queue.QueueItem[uuid.UUID(entry.queue_item_id)]
                started_at = datetime.now()
                await self._set_cycle_preview(entries, entry, is_running=True)
                await queue_item.set(
                    "Data", "LastCycleStartedAt", format_cycle_time(started_at)
                )
                if queue_item.get("Schedule", "IntervalAnchor") == "start":
                    await queue_item.set(
                        "Schedule",
                        "NextRunAt",
                        format_cycle_time(
                            calculate_next_after_start(queue_item, started_at)
                        ),
                    )

                run_success = False
                try:
                    run_success = await self._run_cycle_script(
                        queue_uid, entry, script_uid, script_item
                    )
                except Exception as e:
                    script_item.status = CYCLE_ERROR_STATUS
                    logger.exception(
                        f"循环队列脚本运行异常: {entry.script_name} ({entry.script_id}) {e}"
                    )
                    await Config.send_websocket_message(
                        id=self.task_info.task_id,
                        type="Info",
                        data={
                            "Error": f"循环任务 {entry.script_name} 运行异常: {type(e).__name__}: {str(e)}"
                        },
                    )
                else:
                    self._trim_cycle_log_records(script_item)

                finished_at = datetime.now()
                await queue_item.set(
                    "Data", "LastCycleFinishedAt", format_cycle_time(finished_at)
                )

                if run_success:
                    if queue_item.get("Schedule", "IntervalAnchor") == "start":
                        await queue_item.set(
                            "Schedule",
                            "NextRunAt",
                            format_cycle_time(
                                calculate_next_after_start(
                                    queue_item,
                                    started_at,
                                    after=finished_at,
                                )
                            ),
                        )
                    elif queue_item.get("Schedule", "IntervalAnchor") == "finish":
                        await queue_item.set(
                            "Schedule",
                            "NextRunAt",
                            format_cycle_time(
                                calculate_next_after_finish(queue_item, finished_at)
                            ),
                        )
                    await self._refresh_cycle_preview(queue_uid)
                    continue

                script_item.status = CYCLE_ERROR_STATUS
                logger.warning(
                    f"循环队列脚本失败，跳过: {entry.script_name} ({entry.script_id})"
                )
                if queue_item.get("Schedule", "IntervalAnchor") == "start":
                    await queue_item.set(
                        "Schedule",
                        "NextRunAt",
                        format_cycle_time(
                            calculate_next_after_start(
                                queue_item,
                                started_at,
                                after=finished_at,
                            )
                        ),
                    )
                elif queue_item.get("Schedule", "IntervalAnchor") == "finish":
                    await queue_item.set(
                        "Schedule",
                        "NextRunAt",
                        format_cycle_time(
                            calculate_next_after_finish(queue_item, finished_at)
                        ),
                    )
                await self._refresh_cycle_preview(queue_uid)

    def _make_cycle_next_payload(
        self, entry: QueueCycleEntry, *, is_running: bool = False
    ) -> dict:
        return {
            "queueItemId": entry.queue_item_id,
            "scriptId": entry.script_id,
            "scriptName": entry.script_name,
            "nextRunAt": format_cycle_time(entry.next_run_at),
            "isDue": entry.is_due,
            "isRunning": is_running,
        }

    async def _set_cycle_preview(
        self,
        entries: list[QueueCycleEntry],
        active_entry: QueueCycleEntry | None = None,
        *,
        is_running: bool = False,
    ) -> None:
        preview: list[dict] = []
        used_queue_item_ids: set[str] = set()

        if active_entry is not None and is_running:
            preview.append(
                self._make_cycle_next_payload(active_entry, is_running=True)
            )
            used_queue_item_ids.add(active_entry.queue_item_id)

        due_entries = sorted(
            (entry for entry in entries if entry.is_due),
            key=lambda item: item.index,
        )
        future_entries = sorted(
            (entry for entry in entries if not entry.is_due),
            key=lambda item: (item.next_run_at, item.index),
        )

        for entry in [*due_entries, *future_entries]:
            if entry.queue_item_id in used_queue_item_ids:
                continue
            preview.append(self._make_cycle_next_payload(entry))
            used_queue_item_ids.add(entry.queue_item_id)
            if len(preview) >= 4:
                break

        self.task_info.cycle_next_list = preview[:4]
        self.task_info.cycle_next = (
            self.task_info.cycle_next_list[0]
            if self.task_info.cycle_next_list
            else None
        )
        await self.task_info.on_change()

    async def _refresh_cycle_preview(self, queue_uid: uuid.UUID) -> None:
        queue = Config.QueueConfig[queue_uid]
        entries = collect_queue_cycle_entries(queue, Config.ScriptConfig, datetime.now())
        await self._set_cycle_preview(entries)

    def _trim_cycle_log_records(self, script_item: ScriptItem) -> None:
        trimmed_count = 0
        for user_item in script_item.user_list:
            remove_count = len(user_item.log_record) - CYCLE_LOG_RECORD_KEEP_COUNT
            if remove_count <= 0:
                continue

            for log_time in sorted(user_item.log_record)[:remove_count]:
                user_item.log_record.pop(log_time, None)
                trimmed_count += 1

        if trimmed_count:
            logger.debug(
                f"循环队列清理用户历史日志: {script_item.name} "
                f"清理 {trimmed_count} 条，保留最近 {CYCLE_LOG_RECORD_KEEP_COUNT} 条"
            )

    async def _refresh_cycle_preview_while_running(
        self, queue_uid: uuid.UUID, active_entry: QueueCycleEntry
    ) -> None:
        queue = Config.QueueConfig[queue_uid]
        entries = collect_queue_cycle_entries(queue, Config.ScriptConfig, datetime.now())
        for entry in collect_waiting_cycle_entries(entries, active_entry):
            self.task_info.script_list[entry.index].status = CYCLE_WAIT_STATUS
        await self._set_cycle_preview(entries, active_entry, is_running=True)

    async def _run_cycle_script(
        self,
        queue_uid: uuid.UUID,
        active_entry: QueueCycleEntry,
        script_uid: uuid.UUID,
        script_item: ScriptItem,
    ) -> bool:
        script_item.status = "运行"
        logger.info(f"循环队列脚本开始: {script_uid}")

        script_config = Config.ScriptConfig[script_uid]
        if isinstance(script_config, MaaConfig):
            task_item = MaaManager(script_item)
        elif isinstance(script_config, SrcConfig):
            task_item = SrcManager(script_item)
        elif isinstance(script_config, GeneralConfig):
            task_item = GeneralManager(script_item)
        elif isinstance(script_config, OkwwConfig):
            task_item = OkwwManager(script_item)
        elif isinstance(script_config, MaaEndConfig):
            task_item = MaaEndManager(script_item)
        elif isinstance(script_config, M9AConfig):
            task_item = M9AManager(script_item)
        elif isinstance(script_config, HSRConfig):
            task_item = HSRManager(script_item)
        else:
            raise RuntimeError(f"不支持的脚本类型: {type(script_config).__name__}")

        origin_mode = self.task_info.mode
        self.task_info.mode = CYCLE_SCRIPT_RUN_MODE
        try:
            child_task = self.spawn(task_item)
            while not task_item.accomplish.is_set():
                try:
                    await asyncio.wait_for(
                        task_item.accomplish.wait(),
                        timeout=CYCLE_RUNNING_PREVIEW_REFRESH_SECONDS,
                    )
                except asyncio.TimeoutError:
                    await self._refresh_cycle_preview_while_running(
                        queue_uid, active_entry
                    )
            await child_task
        finally:
            self.task_info.mode = origin_mode

        return is_cycle_script_success(
            script_item.status,
            (user.status for user in script_item.user_list),
        )

    async def final_task(self) -> None:

        logger.info(f"任务结束: {self.task_info.task_id}")
        if self.task_info.mode == "CycleRun" and self.task_info.queue_id is not None:
            Config.running_cycle_queue_ids.discard(uuid.UUID(self.task_info.queue_id))

        await Config.send_websocket_message(
            id=str(self.task_info.task_id),
            type="Signal",
            data={"Accomplish": self.task_info.result},
        )

        if self.task_info.mode == "AutoProxy" and self.task_info.queue_id is not None:

            if Config.power_sign == "NoAction":
                Config.power_sign = Config.QueueConfig[
                    uuid.UUID(self.task_info.queue_id)
                ].get("Info", "AfterAccomplish")
                await Config.send_websocket_message(
                    id="Main", type="Update", data={"PowerSign": Config.power_sign}
                )

    async def on_crash(self, e: Exception) -> None:
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
        self.running_queue_ids: set[uuid.UUID] = set()
        self.running_cycle_queue_ids: set[uuid.UUID] = set()

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

        uid = uuid.UUID(id)
        if mode not in ("AutoProxy", "ManualReview", "ScriptConfig", "CycleRun"):
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

        if script_uid is not None and Config.ScriptConfig[script_uid].is_locked:
            raise RuntimeError(
                f"任务 {Config.ScriptConfig[script_uid].get('Info', 'Name')} 已在运行"
            )

        logger.info(f"创建任务: {task_uid}, 模式: {mode}")
        if queue_id is not None and (
            queue_id in self.running_cycle_queue_ids
            or (mode == "CycleRun" and queue_id in self.running_queue_ids)
        ):
            raise RuntimeError(
                f"队列 {Config.QueueConfig[queue_id].get('Info', 'Name')} 正在运行"
            )

        if new_task_info:
            new_task_info["newTask"] = str(task_uid)
            new_task_info["mode"] = mode
            await Config.send_websocket_message(
                id="TaskManager", type="Signal", data=new_task_info
            )
        self.task_info[task_uid] = TaskInfo(
            mode=mode,
            task_id=str(task_uid),
            queue_id=str(queue_id) if queue_id else None,
            script_id=str(script_uid) if script_uid else None,
            user_id=str(user_uid) if user_uid else None,
            resume_from_script_id=resume_from_script_id,
        )
        self.task_handler[task_uid] = Task(self.task_info[task_uid])
        if queue_id is not None:
            self.running_queue_ids.add(queue_id)
            if mode == "CycleRun":
                self.running_cycle_queue_ids.add(queue_id)
                Config.running_cycle_queue_ids.add(queue_id)
        try:
            self.task_handler[task_uid].execute()
        except Exception:
            if queue_id is not None:
                self.running_queue_ids.discard(queue_id)
                self.running_cycle_queue_ids.discard(queue_id)
                Config.running_cycle_queue_ids.discard(queue_id)
            self.task_info.pop(task_uid, None)
            self.task_handler.pop(task_uid, None)
            raise
        asyncio.create_task(self.clean_task(task_uid))

        return task_uid

    async def clean_task(self, task_uid: uuid.UUID) -> None:

        await self.task_handler[task_uid].accomplish.wait()
        task_info = self.task_info[task_uid]
        power_enabled = bool(task_info.mode not in ("ScriptConfig", "CycleRun"))
        if task_info.queue_id is not None:
            queue_uid = uuid.UUID(task_info.queue_id)
            self.running_queue_ids.discard(queue_uid)
            self.running_cycle_queue_ids.discard(queue_uid)
            Config.running_cycle_queue_ids.discard(queue_uid)
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
                mode = "CycleRun" if queue.get("Info", "CycleEnabled") else "AutoProxy"
                task_type = "启动时循环" if mode == "CycleRun" else "启动时代理"
                logger.info(f"启动时需要运行的队列：{uid}")
                await TaskManager.add_task(
                    mode,
                    str(uid),
                    new_task_info={
                        "queueId": str(uid),
                        "taskName": f"队列 - {queue.get('Info', 'Name')}",
                        "taskType": task_type,
                    },
                )

        logger.success("启动时任务开始运行")


TaskManager = _TaskManager()
