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
    MaaFWConfig,
    BetterGIConfig,
)

from .queue_cycle import (
    CycleEntry,
    collect_cycle_entries,
    due_entries,
    format_cycle_time,
    is_empty_cycle_time,
    is_script_success,
    next_after_finish,
    next_after_start,
    parse_cycle_time,
    sort_for_preview,
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
    WSTaskCyclePreviewData,
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
from app.runtime_tasks import RuntimeTasks
from app.utils import LazyProxy, get_logger
import app.task as task

System = LazyProxy("app.services", "System")

# 脚本配置类名 → 脚本类型键（与 ScriptCreateIn.type 词表一致）
_SCRIPT_TYPE_BY_CLASS = {cls.__name__: key for key, cls in CLASS_BOOK.items()}

logger = get_logger("业务调度")

# 循环队列没有条目可跑时的空转间隔
CYCLE_IDLE_SLEEP_SECONDS = 60
# 单次等待上限。墙钟跳变（夏令时、NTP 校时）最多让一轮迟到这么久，
# 而不会因为一次超长 sleep 无限期挂起，详见 app/core/queue_cycle.py 的说明。
CYCLE_MAX_SLEEP_SECONDS = 300
# 全部到点条目都被别的任务占用时的重试间隔
CYCLE_RETRY_SLEEP_SECONDS = 30
# 运行期间刷新预览的间隔
CYCLE_PREVIEW_REFRESH_SECONDS = 5
# 预览展示的条目数
CYCLE_PREVIEW_SIZE = 4
# 循环会一直跑下去，每个用户只保留最近这么多条历史日志，避免内存无限增长
CYCLE_LOG_RECORD_KEEP_COUNT = 50


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
        self._owner_keys.setdefault(owner, {}).setdefault(script_uid, set()).update(
            keys
        )
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
            data=WSTaskInfoUpdatedData(
                task_info=self.asdict,
                cycleNextList=[
                    WSTaskCyclePreviewData(**item) for item in self.cycle_next_list
                ],
            ),
        )
        if self.current_index != -1:
            await Publisher.send(
                id=self.task_id,
                type=protocol.TASK_LOG_UPDATED,
                data=WSTaskLogUpdatedData(log=self.script_list[self.current_index].log),
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

    def _build_task_item(
        self,
        script_item: ScriptItem,
        script_config,
        *,
        script_uid: uuid.UUID,
        reservation_owner: str,
        src_root_path: Path | None,
    ):
        """按脚本类型构造对应的脚本调度器，类型不支持时返回 None。

        顺序执行与循环运行共用这一份分派，新增脚本类型只需改这里。
        """

        if isinstance(script_config, MaaConfig):
            return task.MaaManager(script_item)
        if isinstance(script_config, SrcConfig):
            if src_root_path is None:
                raise RuntimeError("SRC 路径占用未初始化")
            return task.SrcManager(
                script_item,
                reserved_src_root_path=src_root_path,
                reserve_src_root=lambda root_path, script_uid=script_uid, owner=reservation_owner: (
                    self.script_reservations.try_acquire(
                        script_uid,
                        owner,
                        src_root_path=root_path,
                    )
                ),
            )
        if isinstance(script_config, GeneralConfig):
            return task.GeneralManager(script_item)
        if isinstance(script_config, OkwwConfig):
            return task.OkwwManager(script_item)
        if isinstance(script_config, OkNteConfig):
            return task.OkNteManager(script_item)
        if isinstance(script_config, MaaEndConfig):
            return task.MaaEndManager(script_item)
        if isinstance(script_config, M9AConfig):
            return task.M9AManager(script_item)
        if isinstance(script_config, HSRConfig):
            return task.HSRManager(script_item)
        if isinstance(script_config, BetterGIConfig):
            return task.BetterGIManager(script_item)
        if isinstance(script_config, MaaFWConfig):
            return task.MaaFWEmbeddedManager(script_item)
        return None

    async def _run_cycle_task(self) -> None:
        """循环运行：按各队列项自己的周期，持续调度整个队列。

        与顺序执行的区别只在「什么时候跑哪一项」，真正跑脚本的那一步共用
        ``_build_task_item``；每一轮对脚本适配器而言就是一次普通的自动代理。
        """

        if self.task_info.queue_id is None:
            raise RuntimeError("循环运行必须指定队列")

        queue_uid = uuid.UUID(self.task_info.queue_id)
        Config.running_cycle_queue_ids.add(queue_uid)
        logger.info(f"循环队列开始运行: {queue_uid}")
        try:
            while True:
                await self._run_cycle_round(queue_uid)
        finally:
            Config.running_cycle_queue_ids.discard(queue_uid)
            self.task_info.cycle_next_list = []
            logger.info(f"循环队列停止运行: {queue_uid}")

    async def _run_cycle_round(self, queue_uid: uuid.UUID) -> None:
        """跑一轮：推算 → 落盘首次推算结果 → 等待或执行。"""

        queue = Config.QueueConfig[queue_uid]
        now = datetime.now()
        entries = collect_cycle_entries(queue, Config.ScriptConfig, now)

        # 首次推算的结果要落盘，重启后才不会当成「立刻可跑」重来一遍。
        # 只在还是空值哨兵时写：已经排过期的每轮重写一遍纯属白费写盘。
        for entry in entries:
            queue_item = queue.QueueItem[uuid.UUID(entry.queue_item_id)]
            stored = parse_cycle_time(queue_item.get("Schedule", "NextRunAt"))
            if is_empty_cycle_time(stored) and entry.next_run_at > now:
                await queue_item.set(
                    "Schedule", "NextRunAt", format_cycle_time(entry.next_run_at)
                )

        await self._publish_cycle_preview(entries)

        if not entries:
            await asyncio.sleep(CYCLE_IDLE_SLEEP_SECONDS)
            return

        pending = due_entries(entries)
        if not pending:
            await self._sleep_until(min(entry.next_run_at for entry in entries))
            return

        await self._run_due_entries(queue_uid, entries, pending)

    async def _sleep_until(self, target: datetime) -> None:
        """睡到目标时刻，单次不超过上限。

        上限是防时钟跳变的：睡醒后调用方会用当前时间重新推算，跳变最多让这一轮
        迟到一个上限的时间。
        """

        delay = (target - datetime.now()).total_seconds()
        await asyncio.sleep(max(1.0, min(delay, CYCLE_MAX_SLEEP_SECONDS)))

    async def _run_due_entries(
        self,
        queue_uid: uuid.UUID,
        entries: list[CycleEntry],
        pending: list[CycleEntry],
    ) -> None:
        """按队列顺序跑完这一轮所有到点的条目。

        被占用或没跑成的条目留到下一轮：本轮结束后外层会用新时间重新推算，预览也
        跟着刷新。一轮里一个都没跑成就先退避，不管是被占用还是别的原因，都不让
        循环空转。
        """

        results = [
            await self._run_cycle_entry(queue_uid, entry, entries) for entry in pending
        ]
        if not any(result == "success" for result in results):
            await asyncio.sleep(CYCLE_RETRY_SLEEP_SECONDS)

    async def _run_cycle_entry(
        self,
        queue_uid: uuid.UUID,
        entry: CycleEntry,
        entries: list[CycleEntry],
    ) -> Literal["success", "failed", "blocked"]:
        """跑一个队列项。

        Returns:
            ``blocked`` 表示脚本被别的任务占用、本轮没跑；``failed`` 表示跑了但没成功。
        """

        queue = Config.QueueConfig[queue_uid]
        queue_item = queue.QueueItem[uuid.UUID(entry.queue_item_id)]
        script_uid = uuid.UUID(entry.script_id)
        script_item = self.task_info.script_list[entry.index]

        # collect 时已过滤掉被删的脚本，这里只防它在本轮中途被删。
        if script_uid not in Config.ScriptConfig:
            script_item.status = "异常"
            logger.warning(f"循环跳过: {script_uid} 对应脚本已被删除")
            return "failed"

        script_config = Config.ScriptConfig[script_uid]
        src_root_path = _get_src_root_path(script_config)
        reservation_owner = self.task_info.task_id

        # 与顺序执行同一套原子占用，不再自己判 is_locked 轮询。
        if script_config.is_locked or not self.script_reservations.try_acquire(
            script_uid, reservation_owner, src_root_path=src_root_path
        ):
            script_item.status = "等待"
            logger.info(f"循环等待: {entry.script_name} 已被其他任务占用")
            return "blocked"

        started_at = datetime.now()
        success = False
        # 循环要跑上几天，单个条目出错只算这一轮失败，不能把整个循环带崩；
        # 用户主动停止走的是 CancelledError，不在这里拦。
        try:
            await queue_item.set(
                "Data", "LastCycleStartedAt", format_cycle_time(started_at)
            )
            # 先按开始时间排下一轮：万一这轮崩了，下次运行时间也不会停在过去。
            if queue_item.get("Schedule", "IntervalAnchor") == "start":
                await queue_item.set(
                    "Schedule",
                    "NextRunAt",
                    format_cycle_time(next_after_start(queue_item, started_at)),
                )

            task_item = self._build_task_item(
                script_item,
                script_config,
                script_uid=script_uid,
                reservation_owner=reservation_owner,
                src_root_path=src_root_path,
            )
            if task_item is None:
                script_item.status = "异常"
                logger.error(f"不支持的脚本类型: {type(script_config).__name__}")
            else:
                self.task_info.current_index = entry.index
                script_item.status = "运行"
                logger.info(f"循环任务开始: {script_uid}")

                await self._spawn_with_preview(task_item, entry, entries)

                self._trim_cycle_log_records(script_item)
                success = is_script_success(
                    script_item.status,
                    (user.status for user in script_item.user_list),
                )
        except Exception as e:
            script_item.status = "异常"
            logger.exception(f"循环任务出现异常: {entry.script_name}: {e}")
        finally:
            self.script_reservations.release(script_uid, reservation_owner)

        # 成败都要把下次运行时间推到未来，否则失败的条目会立刻再被挑中。
        finished_at = datetime.now()
        await queue_item.set(
            "Data", "LastCycleFinishedAt", format_cycle_time(finished_at)
        )
        if queue_item.get("Schedule", "IntervalAnchor") == "start":
            # 跑得比间隔还久时往后顺延，别一结束就立刻再来一轮。
            next_run_at = next_after_start(queue_item, started_at, after=finished_at)
        else:
            next_run_at = next_after_finish(queue_item, finished_at)
        await queue_item.set("Schedule", "NextRunAt", format_cycle_time(next_run_at))

        if not success:
            logger.warning(f"循环任务未成功: {entry.script_name}")
        return "success" if success else "failed"

    async def _spawn_with_preview(
        self,
        task_item: TaskExecuteBase,
        entry: CycleEntry,
        entries: list[CycleEntry],
    ) -> None:
        """跑子任务，期间定期刷新预览，让「还有多久轮到下一个」保持准确。

        子任务必须直接 ``await``：用户停止时取消要顺着这个 await 传到子任务，
        换成 ``asyncio.wait`` 之类的间接等待，取消就只会停到循环这一层，正在跑的
        脚本还会继续。所以定时刷新放在旁路任务里，跑完就撤。
        """

        child = self.spawn(task_item)
        refresher = RuntimeTasks.spawn(
            self._refresh_preview_while_running(entries, entry),
            name=f"cycle-preview:{self.task_info.task_id}",
        )
        try:
            await child
        finally:
            if refresher is not None:
                refresher.cancel()

    async def _refresh_preview_while_running(
        self, entries: list[CycleEntry], running: CycleEntry
    ) -> None:
        while True:
            await asyncio.sleep(CYCLE_PREVIEW_REFRESH_SECONDS)
            await self._publish_cycle_preview(entries, running=running)

    async def _publish_cycle_preview(
        self, entries: list[CycleEntry], running: CycleEntry | None = None
    ) -> None:
        """把待运行条目写进任务快照，由 on_change 随任务信息一起下发。"""

        preview: list[dict] = []
        for entry in sort_for_preview(entries):
            preview.append(
                {
                    "queueItemId": entry.queue_item_id,
                    "scriptId": entry.script_id,
                    "scriptName": entry.script_name,
                    "nextRunAt": format_cycle_time(entry.next_run_at),
                    "isDue": entry.is_due,
                    "isRunning": running is not None
                    and entry.queue_item_id == running.queue_item_id,
                }
            )

        # 正在跑的那个排到最前，用户第一眼看到的是当前进度。
        preview.sort(key=lambda item: not item["isRunning"])
        self.task_info.cycle_next_list = preview[:CYCLE_PREVIEW_SIZE]
        # TaskItem 自己的字段改了不会像脚本状态那样自动发布，得显式排一次。
        self.task_info.schedule_on_change()

    def _trim_cycle_log_records(self, script_item: ScriptItem) -> None:
        """裁剪用户历史日志，循环跑上几天也不会把内存撑爆。"""

        trimmed = 0
        for user_item in script_item.user_list:
            excess = len(user_item.log_record) - CYCLE_LOG_RECORD_KEEP_COUNT
            if excess <= 0:
                continue
            for log_time in sorted(user_item.log_record)[:excess]:
                user_item.log_record.pop(log_time, None)
                trimmed += 1

        if trimmed:
            logger.debug(
                f"循环清理历史日志: {script_item.name} 清理 {trimmed} 条, "
                f"保留最近 {CYCLE_LOG_RECORD_KEEP_COUNT} 条"
            )

    async def _run_main_task(self):

        # 循环运行不参与签到与顺序执行那套流程，单独走自己的调度。
        if self.task_info.is_cycle:
            await self.prepare()
            await self._run_cycle_task()
            return

        # MAS 调度触发的签到先完成，结果随本次脚本完成通知汇总；手动签到按钮不经过此处。
        if self.task_info.mode == "AutoProxy":
            from app.core.timer import MainTimer

            sign_source = {
                "scheduled_task": "task_scheduled",
                "manual_task": "task_manual",
                "startup_task": "task_startup",
            }.get(self.task_info.trigger_source, "task_manual")
            self.task_info.game_sign_results = await MainTimer.try_game_sign_for_task(
                source=sign_source
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

                task_item = self._build_task_item(
                    script_item,
                    script_config,
                    script_uid=current_script_uid,
                    reservation_owner=reservation_owner,
                    src_root_path=src_root_path,
                )
                if task_item is None:
                    script_item.status = "异常"
                    self._record_error(
                        f"不支持的脚本类型: {type(script_config).__name__}"
                    )
                    logger.error(f"不支持的脚本类型: {type(script_config).__name__}")
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

        # 循环任务只会被用户主动停止，此时不该再执行队列的「完成后操作」——
        # 那会把关机之类的动作接在一次手动停止后面。
        if (
            not self.is_closing
            and not self.task_info.is_cycle
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
            if (script_id := str(queue_item.get("Info", "ScriptId") or "").strip())
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
            # 循环队列不走定时唤起，与 timed_start 口径一致
            if queue.get("Info", "CycleEnabled"):
                continue
            if not queue.get("Info", "TimeEnabled"):
                continue
            if not any(
                time_set.get("Info", "Enabled") and time_set.get("Info", "Days")
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
                    isCycle=task_info.is_cycle,
                    queueId=task_info.queue_id,
                    scriptId=task_info.script_id,
                    userId=task_info.user_id,
                    stopping=bool(handler and handler.is_closing),
                    scripts=handler.script_identities if handler else [],
                    task_info=task_info.asdict,
                    cycleNextList=[
                        WSTaskCyclePreviewData(**item)
                        for item in task_info.cycle_next_list
                    ],
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
                logger.error(f"任务收尾异常({task_uid}): {type(exc).__name__}: {exc}")

        clean_task.add_done_callback(_on_done)

    async def add_task(
        self,
        mode: Literal["AutoProxy", "ScriptConfig", "Update", "CycleRun"],
        id: str,
        new_task_info: dict | None = None,
        resume_from_script_id: str | None = None,
        trigger_source: TaskTriggerSource = "manual_task",
    ) -> uuid.UUID:
        """
        添加任务, 根据 id 值搜索实际指向的任务配置

        Args:
            mode (str): 任务模式; CycleRun 只接受循环队列
            id (str): 任务项对应的配置 ID
            new_task_info (dict): 新任务项信息. Defaults to {}.
            trigger_source: MAS 任务触发来源，API 手动启动默认 manual_task。

        Returns:
            uuid.UUID: 任务 UID
        """

        uid = uuid.UUID(id)

        # CycleRun 只是「怎么排」的差别，脚本仍按自动代理执行；各脚本适配器
        # 只认 AutoProxy，所以模式在这里就翻译掉，循环与否记在 is_cycle 上。
        is_cycle = mode == "CycleRun"
        exec_mode: Literal["AutoProxy", "ScriptConfig", "Update"] = (
            "AutoProxy" if is_cycle else mode
        )

        if is_cycle:
            if uid not in Config.QueueConfig:
                raise ValueError(f"循环运行的任务 {uid} 必须是调度队列")
            if not Config.QueueConfig[uid].get("Info", "CycleEnabled"):
                raise ValueError(
                    f"队列 {Config.QueueConfig[uid].get('Info', 'Name')} 不是循环队列"
                )
            if uid in Config.running_cycle_queue_ids:
                raise RuntimeError(
                    f"循环队列 {Config.QueueConfig[uid].get('Info', 'Name')} 已在运行"
                )

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
            else [script_uid]
            if script_uid is not None
            else []
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
                mode=exec_mode,
                task_id=str(task_uid),
                queue_id=str(queue_id) if queue_id else None,
                script_id=str(script_uid) if script_uid else None,
                user_id=str(user_uid) if user_uid else None,
                resume_from_script_id=resume_from_script_id,
                trigger_source=trigger_source,
                is_cycle=is_cycle,
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

        try:
            await asyncio.sleep(10)

            if not MainConnection.is_connected:
                logger.info("主 WebSocket 已断开，启动时任务等待下次连接后运行")
                return

            # 必须在等待之后取值：若在等待前取，冷启动恰好落在跨日前 10 秒时，
            # 比较和写入的都是前一天，会漏跑新的一天或在同一天跑两次。
            curday = datetime.now().strftime("%Y-%m-%d")

            self._startup_queue_started = True
            logger.info("开始运行启动时任务")
            for uid, queue in Config.QueueConfig.items():
                # 循环队列启动后会一直跑下去，任务模式与文案都要跟着换
                is_cycle = bool(queue.get("Info", "CycleEnabled"))
                start_mode = "CycleRun" if is_cycle else "AutoProxy"
                task_type = "启动时循环" if is_cycle else "启动时代理"

                StartUpMode = queue.get("Info", "StartUpMode")
                if StartUpMode == "Always":
                    logger.info(f"启动时需要运行的队列：{uid}")
                    # 单个队列创建失败（脚本被锁/已在运行）不中断其余启动队列；
                    # 失败时不写 LastStartupTime，下次启动仍可重试。
                    try:
                        await TaskManager.add_task(
                            start_mode,
                            str(uid),
                            new_task_info={
                                "queueId": str(uid),
                                "taskName": f"队列 - {queue.get('Info', 'Name')}",
                                "taskType": task_type,
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
                        logger.info(f"队列 {uid} 已在今日运行过，跳过该次运行")
                        continue

                    logger.info(f"启动时需要运行的队列：{uid}")
                    try:
                        await TaskManager.add_task(
                            start_mode,
                            str(uid),
                            new_task_info={
                                "queueId": str(uid),
                                "taskName": f"队列 - {queue.get('Info', 'Name')}",
                                "taskType": task_type,
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
