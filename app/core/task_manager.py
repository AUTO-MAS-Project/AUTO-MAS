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
import os
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Literal

from .config import (
    Config,
    MaaConfig,
    SrcConfig,
    GeneralConfig,
    MaaEndConfig,
    M9AConfig,
    OkwwConfig,
    OkNteConfig,
    HSRConfig,
)

# 延迟加载 System，避免 app.services 初始化期间触发循环导入；
# 绑定为模块级 LazyProxy（真实对象引用），函数体裸名 System 才能经
# LOAD_GLOBAL 正常解析（模块级 __getattr__ 只管属性访问、管不到裸名）。
from .ws import MainConnection, Publisher, protocol
from app.models.config import CLASS_BOOK
from app.models.schema import (
    TaskRuntimeSnapshot,
    TaskRuntimeSnapshotItem,
    WSPowerSignData,
    WSTaskCompletedData,
    WSTaskCreatedData,
    WSTaskInfoUpdatedData,
    WSTaskLogUpdatedData,
    WSTaskNoticeData,
    WSTaskScriptIdentityData,
)
from app.models.task import (
    ScriptItem,
    TaskExecuteBase,
    TaskItem,
    TaskTriggerSource,
    UserItem,
)
from app.utils import LazyProxy, get_logger
import app.task as task

System = LazyProxy("app.services", "System")

# 脚本配置类名 → 脚本类型键（与 ScriptCreateIn.type 词表一致）
_SCRIPT_TYPE_BY_CLASS = {cls.__name__: key for key, cls in CLASS_BOOK.items()}

logger = get_logger("业务调度")


class _ScriptTaskReservations:
    """为脚本任务提供原子、带所有者的进程内占用。"""

    def __init__(self) -> None:
        self._owners: dict[tuple[str, str], str] = {}
        self._owner_keys: dict[str, dict[uuid.UUID, set[tuple[str, str]]]] = {}
        self._src_root_paths: dict[str, Path] = {}

    @staticmethod
    def _resource_keys(
        script_uid: uuid.UUID,
        src_root_path: Path | None,
    ) -> set[tuple[str, str]]:
        keys = {("script", str(script_uid))}
        if src_root_path is not None:
            keys.add(("src-root", _normalize_src_root_path(src_root_path.resolve())))
        return keys

    def try_acquire(
        self,
        script_uid: uuid.UUID,
        owner: str,
        *,
        src_root_path: Path | None = None,
    ) -> bool:
        resolved_root_path = (
            src_root_path.resolve() if src_root_path is not None else None
        )
        keys = self._resource_keys(script_uid, resolved_root_path)
        if any(self._owners.get(key) not in (None, owner) for key in keys):
            return False

        root_key = next((key for key in keys if key[0] == "src-root"), None)
        if root_key is not None and resolved_root_path is not None:
            root_path = _normalize_src_root_path(resolved_root_path)
            for key, existing_owner in self._owners.items():
                if key[0] != "src-root" or existing_owner == owner:
                    continue
                existing_src_root_path = self._src_root_paths.get(key)
                if existing_src_root_path is None:
                    continue
                existing_root_path = _normalize_src_root_path(existing_src_root_path)
                if (
                    root_path == existing_root_path
                    or _is_relative_src_root(root_path, existing_root_path)
                    or _is_relative_src_root(existing_root_path, root_path)
                ):
                    return False

        for key in keys:
            self._owners[key] = owner
        self._owner_keys.setdefault(owner, {}).setdefault(script_uid, set()).update(keys)
        if root_key is not None and resolved_root_path is not None:
            self._src_root_paths[root_key] = resolved_root_path
        return True

    def release(self, script_uid: uuid.UUID, owner: str) -> bool:
        script_key = ("script", str(script_uid))
        if self._owners.get(script_key) != owner:
            return False
        keys = self._owner_keys.get(owner, {}).pop(script_uid, set())
        for key in keys:
            key_still_reserved = any(
                key in other_keys
                for other_keys in self._owner_keys.get(owner, {}).values()
            )
            if not key_still_reserved and self._owners.get(key) == owner:
                self._owners.pop(key)
            if key[0] == "src-root":
                if not key_still_reserved:
                    self._src_root_paths.pop(key, None)
        if not self._owner_keys.get(owner):
            self._owner_keys.pop(owner, None)
        return True


def _normalize_src_root_path(path: Path) -> str:
    return os.path.normcase(str(path)).casefold()


def _is_relative_src_root(path: Path | str, parent: Path | str) -> bool:
    path = str(path)
    parent = str(parent)
    return path.startswith(parent + os.sep)


def _get_src_root_path(script_config: object) -> Path | None:
    """返回需要跨配置互斥的 SRC 安装根目录。"""

    if not isinstance(script_config, SrcConfig):
        return None
    return Path(script_config.get("Info", "Path"))


class TaskInfo(TaskItem):

    async def on_change(self):
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


class Task(TaskExecuteBase):

    def __init__(
        self,
        task_info: TaskInfo,
        script_identities: list[WSTaskScriptIdentityData],
        script_reservations: _ScriptTaskReservations | None = None,
    ):
        super().__init__()
        self.task_info = task_info
        self.script_identities = script_identities
        self.script_reservations = script_reservations or _ScriptTaskReservations()
        self.is_closing = False
        self._exit_result = "success"
        self._exit_error: str | None = None

    def _record_error(self, error: str) -> None:
        """保留任务遇到的首个错误，供完成事件提供机器可读结果。"""
        if self._exit_result == "success":
            self._exit_result = "error"
            self._exit_error = error

    def cancel(self) -> bool:
        """记录显式取消结果，覆盖尚未进入脚本执行阶段的任务。"""
        cancelled = super().cancel()
        if cancelled and self._exit_result == "success":
            self._exit_result = "cancelled"
            self._exit_error = "任务执行被取消"
        return cancelled

    async def prepare(self):

        # 使用创建任务时冻结的脚本标识，确保执行内容与 task.created/快照一致
        script_ids = [identity.scriptId for identity in self.script_identities]

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
        from app.services.telemetry import (
            observe_span,
            record_count,
            record_distribution,
        )

        attributes = {
            "mode": self.task_info.mode,
            "trigger": self.task_info.trigger_source,
        }
        started_at = time.perf_counter()
        outcome = "success"

        try:
            with observe_span(
                name="AUTO-MAS task",
                op="auto_mas.task.run",
                attributes=attributes,
                force_transaction=True,
            ):
                await self._run_main_task()
                outcome = self._exit_result
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except Exception:
            outcome = "error"
            raise
        finally:
            metric_attributes = {**attributes, "outcome": outcome}
            record_count("auto_mas.task.runs", attributes=metric_attributes)
            record_distribution(
                "auto_mas.task.duration",
                (time.perf_counter() - started_at) * 1000,
                unit="millisecond",
                attributes=metric_attributes,
            )

    async def _run_main_task(self):

        # MAS 调度触发的签到先完成，结果随本次脚本完成通知汇总；手动签到按钮不经过此处。
        if self.task_info.mode == "AutoProxy":
            from app.core.timer import MainTimer

            sign_source = {
                "scheduled_task": "task_scheduled",
                "manual_task": "task_manual",
                "startup_task": "task_startup",
            }.get(self.task_info.trigger_source, "task_manual")
            self.task_info.game_sign_results = (
                await MainTimer.try_game_sign_for_task(source=sign_source)
            )

        await self.prepare()

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
                self._record_error(f"脚本 {current_script_uid} 已被删除")
                logger.info(f"跳过任务: {current_script_uid}, 该任务对应脚本已被删除")
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error",
                        message=f"任务 {script_item.name} 对应脚本已被删除",
                    ),
                )
                continue

            # 原子占用脚本，避免两个调度器同时通过布尔锁前置检查。
            reservation_owner = self.task_info.task_id
            script_config = Config.ScriptConfig[current_script_uid]
            src_root_path = _get_src_root_path(script_config)
            if not self.script_reservations.try_acquire(
                current_script_uid,
                reservation_owner,
                src_root_path=src_root_path,
            ):
                script_item.status = "跳过"
                logger.info(
                    f"跳过任务: {current_script_uid}, 该任务已被其他任务调度器锁定"
                )
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="warning",
                        message=f"任务 {script_item.name} 已被其他任务调度器锁定",
                    ),
                )
                continue

            try:
                if script_config.is_locked:
                    script_item.status = "跳过"
                    logger.info(f"跳过任务: {current_script_uid}, 该任务配置已被锁定")
                    await Publisher.send(
                        id=self.task_info.task_id,
                        type=protocol.TASK_NOTICE,
                        data=WSTaskNoticeData(
                            level="warning",
                            message=f"任务 {script_item.name} 已被锁定",
                        ),
                    )
                    continue

                # 标记为运行中
                script_item.status = "运行"
                logger.info(f"任务开始: {current_script_uid}")

                if isinstance(script_config, MaaConfig):
                    task_item = task.MaaManager(script_item)
                elif isinstance(script_config, SrcConfig):
                    if src_root_path is None:
                        raise RuntimeError("SRC 路径占用未初始化")
                    task_item = task.SrcManager(
                        script_item,
                        reserved_src_root_path=src_root_path,
                        reserve_src_root=lambda root_path,
                        script_uid=current_script_uid,
                        owner=reservation_owner: self.script_reservations.try_acquire(
                            script_uid,
                            owner,
                            src_root_path=root_path,
                        ),
                    )
                elif isinstance(script_config, GeneralConfig):
                    task_item = task.GeneralManager(script_item)
                elif isinstance(script_config, OkwwConfig):
                    task_item = task.OkwwManager(script_item)
                elif isinstance(script_config, OkNteConfig):
                    task_item = task.OkNteManager(script_item)
                elif isinstance(script_config, MaaEndConfig):
                    task_item = task.MaaEndManager(script_item)
                elif isinstance(script_config, M9AConfig):
                    task_item = task.M9AManager(script_item)
                elif isinstance(script_config, HSRConfig):
                    task_item = task.HSRManager(script_item)
                else:
                    script_item.status = "异常"
                    self._record_error(
                        f"不支持的脚本类型: {type(script_config).__name__}"
                    )
                    logger.error(
                        f"不支持的脚本类型: {type(script_config).__name__}"
                    )
                    await Publisher.send(
                        id=self.task_info.task_id,
                        type=protocol.TASK_NOTICE,
                        data=WSTaskNoticeData(level="error", message="脚本类型不支持"),
                    )
                    continue

                # 运行任务
                await self.spawn(task_item)
            finally:
                self.script_reservations.release(current_script_uid, reservation_owner)

    async def final_task(self) -> None:

        logger.info(f"任务结束: {self.task_info.task_id}")

        await Publisher.send(
            id=str(self.task_info.task_id),
            type=protocol.TASK_COMPLETED,
            data=WSTaskCompletedData(
                result=self.task_info.result,
                outcome=self._exit_result,
                error=self._exit_error,
                task_info=self.task_info.asdict,
            ),
        )

        if (
            not self.is_closing
            and self.task_info.mode == "AutoProxy"
            and self.task_info.queue_id is not None
        ):

            if Config.power_sign == "NoAction":
                Config.power_sign = Config.QueueConfig[
                    uuid.UUID(self.task_info.queue_id)
                ].get("Info", "AfterAccomplish")
                await Publisher.send(
                    id=protocol.ID_MAIN,
                    type=protocol.POWER_SIGN_UPDATED,
                    data=WSPowerSignData(signal=Config.power_sign),
                )

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
        self._script_reservations = _ScriptTaskReservations()
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

    @staticmethod
    def _script_identity(script_id: uuid.UUID) -> WSTaskScriptIdentityData:
        """构造脚本静态身份，类型键与 ScriptCreateIn.type 词表一致。"""

        class_name = type(Config.ScriptConfig[script_id]).__name__
        return WSTaskScriptIdentityData(
            scriptId=str(script_id),
            scriptType=_SCRIPT_TYPE_BY_CLASS.get(class_name, class_name),
        )

    def _scheduled_script_identities(self) -> list[WSTaskScriptIdentityData]:
        """返回存在有效定时配置的队列脚本身份。"""

        identities: dict[uuid.UUID, WSTaskScriptIdentityData] = {}
        for queue_id, queue in Config.QueueConfig.items():
            if not queue.get("Info", "TimeEnabled"):
                continue
            if not any(
                time_set.get("Info", "Enabled")
                and time_set.get("Info", "Days")
                for time_set in queue.TimeSet.values()
            ):
                continue

            for script_id in self._queue_script_ids(queue_id):
                if script_id not in Config.ScriptConfig:
                    continue
                identities.setdefault(script_id, self._script_identity(script_id))

        return list(identities.values())

    def get_runtime_snapshot(self) -> TaskRuntimeSnapshot:
        """返回任务运行状态与定时队列的 HTTP 初始快照。"""

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
                    scripts=handler.script_identities if handler else [],
                    task_info=task_info.asdict,
                    log=log,
                )
            )
        return TaskRuntimeSnapshot(
            tasks=tasks,
            scheduledScripts=self._scheduled_script_identities(),
        )

    def _schedule_clean_task(self, task_uid: uuid.UUID) -> None:
        """创建并持有任务收尾协程，结束后统一移出集合。"""

        clean_task = asyncio.create_task(self.clean_task(task_uid))
        self._cleanup_tasks.add(clean_task)

        def _on_done(done_task: asyncio.Task[None]) -> None:
            self._cleanup_tasks.discard(done_task)
            if done_task.cancelled():
                return
            exc = done_task.exception()
            if exc is not None:
                logger.error(
                    f"任务收尾异常({task_uid}): {type(exc).__name__}: {exc}"
                )

        clean_task.add_done_callback(_on_done)

    async def add_task(
        self,
        mode: Literal["AutoProxy", "ScriptConfig", "Update"],
        id: str,
        new_task_info: dict | None = None,
        resume_from_script_id: str | None = None,
        trigger_source: TaskTriggerSource = "manual_task",
    ) -> uuid.UUID:
        """
        添加任务, 根据 id 值搜索实际指向的任务配置

        Args:
            mode (str): 任务模式
            id (str): 任务项对应的配置 ID
            new_task_info (dict): 新任务项信息. Defaults to {}.
            trigger_source: MAS 任务触发来源，API 手动启动默认 manual_task。

        Returns:
            uuid.UUID: 任务 UID
        """

        uid = uuid.UUID(id)

        if mode in ("ScriptConfig", "Update"):
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

        # 创建时冻结任务脚本身份，供 task.created 通知与运行时快照复用
        target_script_ids = (
            self._queue_script_ids(queue_id)
            if queue_id is not None
            else [script_uid] if script_uid is not None else []
        )
        script_identities = [
            self._script_identity(script_id)
            for script_id in target_script_ids
            if script_id in Config.ScriptConfig
        ]

        reservation_owner = str(task_uid)
        reservation_acquired = False
        if script_uid is not None:
            script_config = Config.ScriptConfig[script_uid]
            if script_config.is_locked or not self._script_reservations.try_acquire(
                script_uid,
                reservation_owner,
                src_root_path=_get_src_root_path(script_config),
            ):
                raise RuntimeError(f"任务 {script_config.get('Info', 'Name')} 已在运行")
            reservation_acquired = True

        try:
            logger.info(
                f"创建任务: {task_uid}, 模式: {mode}, 触发来源: {trigger_source}"
            )
            self.task_info[task_uid] = TaskInfo(
                mode=mode,
                task_id=str(task_uid),
                queue_id=str(queue_id) if queue_id else None,
                script_id=str(script_uid) if script_uid else None,
                user_id=str(user_uid) if user_uid else None,
                resume_from_script_id=resume_from_script_id,
                trigger_source=trigger_source,
            )
            self.task_handler[task_uid] = Task(
                self.task_info[task_uid],
                script_identities,
                self._script_reservations,
            )
            await Publisher.send(
                id=protocol.ID_TASK_MANAGER,
                type=protocol.TASK_CREATED,
                data=WSTaskCreatedData(
                    taskId=str(task_uid),
                    mode=mode,
                    scripts=script_identities,
                    queueId=str(queue_id) if queue_id else None,
                    taskName=new_task_info.get("taskName") if new_task_info else None,
                    taskType=new_task_info.get("taskType") if new_task_info else None,
                ),
            )
            self.task_handler[task_uid].execute()
            self._schedule_clean_task(task_uid)
        except BaseException:
            if reservation_acquired and script_uid is not None:
                self._script_reservations.release(script_uid, reservation_owner)
            self.task_handler.pop(task_uid, None)
            self.task_info.pop(task_uid, None)
            raise

        return task_uid

    async def clean_task(self, task_uid: uuid.UUID) -> None:

        task_info = self.task_info[task_uid]
        try:
            await self.task_handler[task_uid].accomplish.wait()
        finally:
            if task_info.script_id is not None:
                self._script_reservations.release(
                    uuid.UUID(task_info.script_id), task_info.task_id
                )

        power_enabled = bool(task_info.mode != "ScriptConfig")
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
                # 主动停止全部任务时，禁止触发队列完成后的电源操作
                Config.power_sign = "NoAction"
                try:
                    if System.power_task is not None and not System.power_task.done():
                        await System.cancel_power_task()

                    task_item_list = list(self.task_handler.values())
                    for task_item in task_item_list:
                        if not task_item.is_closing:
                            task_item.cancel()
                            task_item.is_closing = True
                            await task_item.accomplish.wait()
                    cleanup_tasks = [
                        cleanup for cleanup in self._cleanup_tasks if not cleanup.done()
                    ]
                    if cleanup_tasks:
                        await asyncio.gather(*cleanup_tasks)
                finally:
                    # final_task 可能重新写入 AfterAccomplish，主动停止全部任务时必须丢弃。
                    Config.power_sign = "NoAction"
                    self._stopping_all = False
            await Publisher.send(
                id=protocol.ID_MAIN,
                type=protocol.POWER_SIGN_UPDATED,
                data=WSPowerSignData(signal=Config.power_sign),
            )
        else:
            uid = uuid.UUID(task_id)
            if uid not in self.task_handler:
                # 任务已经结束时，中止操作仍视为成功。
                logger.info(f"任务 {task_id} 已结束，无需中止")
                return
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
        curday = datetime.now().strftime("%Y-%m-%d")

        try:
            await asyncio.sleep(10)

            if not MainConnection.is_connected:
                logger.info("主 WebSocket 已断开，启动时任务等待下次连接后运行")
                return

            self._startup_queue_started = True
            logger.info("开始运行启动时任务")
            for uid, queue in Config.QueueConfig.items():

                StartUpMode = queue.get("Info", "StartUpMode")
                if StartUpMode == "Always":
                    logger.info(f"启动时需要运行的队列：{uid}")
                    # 单个队列创建失败（脚本被锁/已在运行）不中断其余启动队列；
                    # 失败时不写 LastStartupTime，下次启动仍可重试。
                    try:
                        await TaskManager.add_task(
                            "AutoProxy",
                            str(uid),
                            new_task_info={
                                "queueId": str(uid),
                                "taskName": f"队列 - {queue.get('Info', 'Name')}",
                                "taskType": "启动时代理",
                            },
                            trigger_source="startup_task",
                        )
                    except (RuntimeError, ValueError) as error:
                        logger.error(f"启动时队列 {uid} 无法创建任务：{error}")
                        continue
                    await queue.set("Data", "LastStartupTime", curday)

                elif StartUpMode == "DailyFirst":
                    # 检查 DailyFirst 模式是否已在今日运行过
                    if queue.get("Data", "LastStartupTime") == curday:
                        logger.info(
                            f"队列 {uid} 已在今日运行过，跳过该次运行"
                        )
                        continue

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
                            trigger_source="startup_task",
                        )
                    except (RuntimeError, ValueError) as error:
                        logger.error(f"启动时队列 {uid} 无法创建任务：{error}")
                        continue
                    await queue.set("Data", "LastStartupTime", curday)
                
        finally:
            self._startup_queue_running = False

        logger.success("启动时任务开始运行")


TaskManager = _TaskManager()
