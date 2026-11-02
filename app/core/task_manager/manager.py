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
import os
import time
import uuid
from collections import OrderedDict
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, Iterable, Literal

import app.core.notify.report as _notification_report
from app.config import ConfigEntry

# 延迟加载 System，避免 app.services 初始化期间触发循环导入；
# 绑定为模块级 LazyProxy（真实对象引用），函数体裸名 System 才能经
# LOAD_GLOBAL 正常解析（模块级 __getattr__ 只管属性访问、管不到裸名）。
from app.core import (
    Config,
    GameMaintenance,
    History,
    MainConnection,
    Notify,
    Publisher,
    RuntimeTasks,
)
from app.core.desktop_guard import ensure_desktop_available
from app.core.task_manager.cycle import (
    SUCCESS_USER_STATUSES,
    CycleEntry,
    collect_cycle_entries,
    due_entries,
    format_cycle_time,
    format_next_run,
    is_empty_cycle_time,
    is_script_success,
    next_after_finish,
    next_after_start,
    parse_cycle_time,
    sort_for_preview,
)
from app.core.ws import protocol
from app.models.config import CLASS_BOOK, UserConfigType
from app.models.game_maintenance import MaintenanceWindow
from app.models.notification.report import UserReportText
from app.models.schema import (
    HistoryAttachmentInput,
    HistoryWrite,
    TaskRuntimeSnapshot,
    TaskRuntimeSnapshotItem,
    TaskStatusOut,
    WSPowerSignData,
    WSTaskCompletedData,
    WSTaskCreatedData,
    WSTaskCyclePreviewData,
    WSTaskInfoUpdatedData,
    WSTaskLogUpdatedData,
    WSTaskNoticeData,
    WSTaskScriptFinishedData,
    WSTaskScriptIdentityData,
    WSTaskScriptStartedData,
)
from app.models.task import (
    ScriptItem,
    TaskExecuteBase,
    TaskItem,
    TaskTriggerSource,
    UserItem,
)
from app.services import execute_script_task
from app.task.history_core import UserHistoryDependencies, save_user_history
from app.task.registration import ManagerBuildContext, ManagerFactory
from app.utils import LOG_TYPE_ERROR, LazyProxy, get_logger
from app.utils.common.log_box.results import LogEntry

System = LazyProxy("app.services", "System")

if TYPE_CHECKING:
    from app.core.notify.coordinator import (
        TaskReportCoordinator as TaskReportCoordinator,
    )

# 脚本配置类名 → 脚本类型键（与 ScriptCreateIn.type 词表一致）
_SCRIPT_TYPE_BY_CLASS = {cls.__name__: key for key, cls in CLASS_BOOK.items()}
_script_observation_tasks: set[asyncio.Task[bool]] = set()


def _publish_script_observation(
    *,
    message_type: str,
    data: WSTaskScriptStartedData,
    after: asyncio.Task[bool] | None = None,
) -> asyncio.Task[bool] | None:
    """有界、可丢弃的本地统计消息，不进入脚本的执行或收尾等待链。"""

    if len(_script_observation_tasks) >= 32:
        return None

    async def send() -> bool:
        if after is not None and not await asyncio.shield(after):
            return False
        return await Publisher.send(
            id=protocol.ID_TASK_MANAGER, type=message_type, data=data
        )

    pending = RuntimeTasks.spawn(send(), name="script-run-observation")
    if pending is not None:
        _script_observation_tasks.add(pending)
        pending.add_done_callback(_script_observation_tasks.discard)
    return pending


# 最近完成任务的状态留存：任务一结束就会从运行快照摘掉，凭 taskId 单点查询
# 只能靠这里回读终态，所以留一个有限窗口（条数上限 + 留存时长）。
_RECENT_RESULTS_MAX = 200
_RECENT_RESULTS_TTL_SECONDS = 1800


logger = get_logger("业务调度")

# 循环队列没有条目可跑时的空转间隔
CYCLE_IDLE_SLEEP_SECONDS = 60
# 单次等待上限。用户点「立即运行一次」或改了周期，要等这一觉睡完才会被注意到；
# 墙钟跳变（夏令时、NTP 校时）也最多让一轮迟到这么久，详见 app/core/task_manager/cycle.py。
CYCLE_MAX_SLEEP_SECONDS = 30
# 全部到点条目都被别的任务占用时的重试间隔
CYCLE_RETRY_SLEEP_SECONDS = 30
# 运行期间刷新预览的间隔
CYCLE_PREVIEW_REFRESH_SECONDS = 5
# 预览展示的条目数
CYCLE_PREVIEW_SIZE = 4


class _ScriptTaskReservations:
    """为脚本任务提供原子、带所有者的进程内占用。"""

    def __init__(self) -> None:
        self._owners: dict[tuple[str, str], str] = {}
        self._owner_keys: dict[str, dict[uuid.UUID, set[tuple[str, str]]]] = {}
        self._reserved_root_paths: dict[tuple[str, str], Path] = {}

    @staticmethod
    def _resource_keys(
        script_uid: uuid.UUID,
        root_paths: tuple[Path, ...],
        emulator_key: str | None,
    ) -> set[tuple[str, str]]:
        keys = {("script", str(script_uid))}
        for root_path in root_paths:
            keys.add(("install-root", _normalize_src_root_path(root_path)))
        if emulator_key is not None:
            keys.add(("emulator", emulator_key))
        return keys

    def try_acquire(
        self,
        script_uid: uuid.UUID,
        owner: str,
        *,
        root_paths: Iterable[Path] = (),
        emulator_key: str | None = None,
    ) -> bool:
        resolved_root_paths = tuple(path.resolve() for path in root_paths)
        keys = self._resource_keys(script_uid, resolved_root_paths, emulator_key)
        if any(self._owners.get(key) not in (None, owner) for key in keys):
            return False

        # 父子目录同样算同一个安装目录：所有安装根键参与同一次包含判定。
        for key, existing_owner in self._owners.items():
            if key[0] != "install-root" or existing_owner == owner:
                continue
            existing_src_root_path = self._reserved_root_paths.get(key)
            if existing_src_root_path is None:
                continue
            existing_root_path = _normalize_src_root_path(existing_src_root_path)
            for root_path in resolved_root_paths:
                root_path_key = _normalize_src_root_path(root_path)
                if (
                    root_path_key == existing_root_path
                    or _is_relative_src_root(root_path_key, existing_root_path)
                    or _is_relative_src_root(existing_root_path, root_path_key)
                ):
                    return False

        for key in keys:
            self._owners[key] = owner
        self._owner_keys.setdefault(owner, {}).setdefault(script_uid, set()).update(
            keys
        )
        for root_path in resolved_root_paths:
            root_key = ("install-root", _normalize_src_root_path(root_path))
            self._reserved_root_paths[root_key] = root_path
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
            if key[0] == "install-root" and not key_still_reserved:
                self._reserved_root_paths.pop(key, None)
        if not self._owner_keys.get(owner):
            self._owner_keys.pop(owner, None)
        return True


def _normalize_src_root_path(path: Path) -> str:
    return os.path.normcase(str(path)).casefold()


def _is_relative_src_root(path: Path | str, parent: Path | str) -> bool:
    path = str(path)
    # 父目录是盘根时归一后带尾分隔符（"c:\\"），不先去掉就会拼出双分隔符而判不出子目录。
    parent = str(parent).rstrip(os.sep)
    return path.startswith(parent + os.sep)


def _exclusive_resources(
    script_config: ConfigEntry,
) -> tuple[tuple[Path, ...], str | None]:
    """规范化专项声明；不解释专项字段或读取上游资源文件。"""
    resources = Config.get_script_task_resources(script_config)
    if resources.emulator is None:
        return resources.root_paths, None
    emulator_id, index = resources.emulator
    if str(emulator_id or "") in ("", "-") or str(index or "") in ("", "-"):
        return resources.root_paths, None
    return resources.root_paths, f"{emulator_id}:{index}"


@dataclass(eq=False)
class _ReplayRequest:
    """本轮已发起保存的回放，失败日志写完后据此补齐原因与历史关联。"""

    script: ScriptItem
    user: UserItem | None
    explicit_reason: bool
    reason: str
    history_paths: list[str]


@dataclass
class TaskInfo(TaskItem):
    _change_task: asyncio.Task[None] | None = field(
        default=None, init=False, repr=False, compare=False
    )
    _change_dirty: bool = field(default=False, init=False, repr=False, compare=False)

    community_sign_notification: "TaskReportCoordinator | None" = field(
        default=None, init=False, repr=False
    )
    replay_cancelled: bool = field(default=False, init=False, repr=False)
    _replay_runs: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _replay_seen: set[tuple[str, str]] = field(
        default_factory=set, init=False, repr=False
    )

    _history_capture_tasks: dict[tuple[str, str], asyncio.Task[Path]] = field(
        default_factory=dict, init=False, repr=False
    )
    _history_capture_files: dict[tuple[str, str], Path] = field(
        default_factory=dict, init=False, repr=False
    )

    def schedule_on_change(self) -> None:
        """合并高频字段变化，并由应用任务注册表持有异步通知。"""

        self._change_dirty = True
        if self._change_task is not None and not self._change_task.done():
            return

        async def _flush_changes() -> None:
            try:
                while self._change_dirty:
                    self._change_dirty = False
                    await self.on_change()
            finally:
                self._change_task = None

        self._change_task = RuntimeTasks.spawn(
            _flush_changes(), name=f"task-state-change:{self.task_id}"
        )
        if self._change_task is None:
            # teardown 已开始时不再发布状态；RuntimeTasks 已关闭协程对象。
            self._change_dirty = False

    def get_script_user_configs(
        self, script_id: str
    ) -> Iterable[tuple[uuid.UUID, UserConfigType]]:
        return Config.ScriptConfig[uuid.UUID(script_id)].UserData.items()

    async def get_active_maintenance(self, game: str) -> MaintenanceWindow | None:
        return await GameMaintenance.get_active(game, proxy=Config.proxy)

    async def send_notice(
        self, *, level: Literal["info", "warning", "error"], message: str
    ) -> None:
        await Publisher.send(
            id=self.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level=level, message=message),
        )

    def begin_script_run(self, script: ScriptItem) -> None:
        previous = self._replay_runs.get(script.script_id)
        self._replay_seen = {key for key in self._replay_seen if key[0] != previous}
        self._replay_runs[script.script_id] = uuid.uuid4().hex
        script.user_list = []
        script.current_index = -1
        script.status = "等待"

    def on_status_changed(
        self, item: UserItem | ScriptItem, previous: str | None, status: str
    ) -> None:
        # 已执行用户在自己的收尾中显式采集；预检与共享故障没有用户历史归属。
        if status != "异常" or self.mode != "AutoProxy" or self.replay_cancelled:
            return
        script = (
            item
            if isinstance(item, ScriptItem)
            else next(
                (
                    script
                    for script in self.script_list
                    if any(user is item for user in script.user_list)
                ),
                None,
            )
        )
        if script is None:
            return
        if isinstance(item, UserItem):
            return
        run = self._replay_runs.get(script.script_id)
        if any(key[0] == run for key in self._history_capture_tasks) or any(
            key[0] == run and key[1] != "diagnostic" for key in self._replay_seen
        ):
            return
        self._request_unassigned_replay(script, reason="无对应用户执行轮次的任务异常")

    def begin_user_history_capture(
        self, script: ScriptItem, user: UserItem, *, failed: bool
    ) -> None:
        """专项确认最终失败后及时请求缓冲；此时只采集临时文件，不预建历史。"""
        if (
            not failed
            or self.mode != "AutoProxy"
            or self.replay_cancelled
            or not user.log_record
        ):
            return
        if not Config.setting.Replay.Enabled:
            return
        run = self._replay_runs.setdefault(script.script_id, uuid.uuid4().hex)
        key = (run, user.user_id)
        if key in self._replay_seen or key in self._history_capture_tasks:
            return
        from app.services import obs_replay as _service_obs_replay

        capture = RuntimeTasks.spawn(
            _service_obs_replay.ObsReplay.capture(Config.obs_replay_options()),
            name="obs-user-capture",
        )
        if capture is not None:
            self._history_capture_tasks[key] = capture

    async def save_user_history(
        self,
        records: Sequence[HistoryWrite],
        *,
        script: ScriptItem,
        user: UserItem,
        log_warning: Callable[[str], None] | None = None,
    ) -> None:
        """为本次用户历史装配能力，专项只交出已判定的条目与诊断入口。"""

        await save_user_history(
            records,
            dependencies=UserHistoryDependencies(
                record=History.record,
                collect_attachments=partial(
                    self.collect_user_history_attachments, script=script, user=user
                ),
                discard_capture=partial(
                    self.discard_user_history_capture, script=script, user=user
                ),
                report_failure=self._report_history_save_failure,
                log_warning=log_warning
                if log_warning is not None
                else logger.opt(exception=True).warning,
            ),
        )

    async def _report_history_save_failure(self, message: str) -> None:
        await Publisher.send(
            id=self.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="warning", message=message),
        )

    async def collect_user_history_attachments(
        self, script: ScriptItem, user: UserItem
    ) -> list[HistoryAttachmentInput]:
        """保存前等待该用户已有采集，捕获故障不影响执行结论和其余记录。"""
        run = self._replay_runs.setdefault(script.script_id, uuid.uuid4().hex)
        key = (run, user.user_id)
        if key in self._replay_seen:
            return []
        self.begin_user_history_capture(script, user, failed=user.status == "异常")
        capture = self._history_capture_tasks.pop(key, None)
        if capture is None:
            return []
        self._replay_seen.add(key)
        try:
            path = await capture
            if self.replay_cancelled or user.status != "异常":
                await asyncio.to_thread(path.unlink, missing_ok=True)
                return []
            self._history_capture_files[key] = path
            return [
                HistoryAttachmentInput(
                    path=path, kind="video", role="obs_replay", display_name=path.name
                )
            ]
        except Exception as error:
            logger.opt(exception=True).warning(f"用户失败回放未采集：{error}")
            with suppress(Exception):
                await Publisher.send(
                    id=self.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="warning", message=f"失败回放未采集：{error}"
                    ),
                )
            return []

    async def _discard_history_capture_file(self, path: Path) -> bool:
        from app.services import obs_replay as _service_obs_replay

        try:
            if (
                _service_obs_replay.ObsReplay.directory.is_symlink()
                or _service_obs_replay.ObsReplay.directory.is_junction()
                or path.is_symlink()
                or path.parent.resolve()
                != _service_obs_replay.ObsReplay.directory.resolve()
            ):
                logger.warning(f"拒绝清理回放临时目录外的文件：{path}")
                return False
            await asyncio.to_thread(path.unlink, missing_ok=True)
            return True
        except OSError as error:
            logger.warning(f"未归档回放临时副本清理失败：{error}")
            return False

    async def discard_user_history_capture(
        self, script: ScriptItem, user: UserItem
    ) -> None:
        """归档返回后释放本用户的采集副本，包括配额拒收与复制回退留下的源。"""
        run = self._replay_runs.get(script.script_id)
        if run is None:
            return
        key = (run, user.user_id)
        path = self._history_capture_files.get(key)
        if path is not None and await self._discard_history_capture_file(path):
            self._history_capture_files.pop(key, None)

    async def discard_history_captures(self) -> None:
        """异常中断未交给用户历史的采集只能丢弃，不能在队列末尾补挂。"""
        captures = list(self._history_capture_tasks.values())
        self._history_capture_tasks.clear()
        for capture in captures:
            if not capture.done():
                capture.cancel()
        results = await asyncio.gather(*captures, return_exceptions=True)
        for result in results:
            if isinstance(result, Path):
                await self._discard_history_capture_file(result)
        for key, path in list(self._history_capture_files.items()):
            if await self._discard_history_capture_file(path):
                self._history_capture_files.pop(key, None)

    def _request_unassigned_replay(
        self, script: ScriptItem | None, *, reason: str
    ) -> None:
        """无用户归属的诊断只请求 OBS 原件，不创建 MAS 回放档案。"""
        if (
            self.mode != "AutoProxy"
            or self.replay_cancelled
            or not Config.setting.Replay.Enabled
        ):
            return
        script_id = script.script_id if script is not None else "scheduler"
        run = self._replay_runs.setdefault(script_id, uuid.uuid4().hex)
        key = (run, "diagnostic")
        if key in self._replay_seen:
            return
        self._replay_seen.add(key)
        options = Config.obs_replay_options()

        async def capture() -> None:
            from app.services import obs_replay as _service_obs_replay

            try:
                path = await _service_obs_replay.ObsReplay.capture(
                    options, temporary_copy=False
                )
                message = f"{reason}；回放仅保留在 OBS 输出：{path}"
            except Exception as error:
                message = f"{reason}；诊断回放未采集：{error}"
            logger.warning(message)
            with suppress(Exception):
                await Publisher.send(
                    id=self.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(level="warning", message=message),
                )

        RuntimeTasks.spawn(capture(), name="obs-diagnostic-capture")

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
            script = self.script_list[self.current_index]
            log = script.log
            if (
                log == self._last_pushed_log
                and script.log_first_line == self._last_pushed_log_first_line
            ):
                return
            # 日志只在尾部追加时只推增量；首次推送或日志被重置/变短时整体替换。
            # 部分任务模式（MAA/SRC/General/M9A）无上限累积脚本日志，全量 JSON
            # 序列化超大字符串会在 iterencode 阶段 MemoryError；整体替换时做
            # 防御性限长（保留最新日志），一处覆盖所有任务模式。
            if (
                self._last_pushed_log
                and log.startswith(self._last_pushed_log)
                and script.log_first_line == self._last_pushed_log_first_line
            ):
                payload = log[len(self._last_pushed_log) :]
                append = True
                # 追加段接着界面已有的内容往下排，行号由前端自己累加，这个值不会被读；
                # 字段本身有默认值，这里只是把它显式带上，保持两种分支的载荷形状一致。
                first_line = WSTaskLogUpdatedData.model_fields["firstLine"].default
            else:
                payload = log[-200_000:]
                append = False
                # 界面行号 = 这段内容在完整日志里的真实行号：生产者自己截掉的那部分
                # （script.log_first_line）加上这里又被截掉的行数。
                dropped_hint = log[: len(log) - len(payload)]
                first_line = script.log_first_line + dropped_hint.count("\n")
            self._log_seq += 1
            await Publisher.send(
                id=self.task_id,
                type=protocol.TASK_LOG_UPDATED,
                data=WSTaskLogUpdatedData(
                    log=payload,
                    seq=self._log_seq,
                    append=append,
                    firstLine=first_line,
                ),
            )
            self._last_pushed_log = log
            if not append:
                self._last_pushed_log_first_line = script.log_first_line


class Task(TaskExecuteBase):
    wait_for_finalizer_on_cancel = True

    def __init__(
        self,
        task_info: TaskInfo,
        script_identities: list[WSTaskScriptIdentityData],
        script_reservations: _ScriptTaskReservations | None = None,
        script_run_days: list[list[str]] | None = None,
        on_finished: Callable[[TaskStatusOut], None] | None = None,
        *,
        manager_factories: Mapping[type[ConfigEntry], ManagerFactory | None],
    ):
        super().__init__()
        self._manager_factories = manager_factories
        self.task_info = task_info
        self.script_identities = script_identities
        # 结束时的终态回调（调度器用来留存结果，供 taskId 单点查询）
        self._on_finished = on_finished
        # 队列项限定的运行周几，与 script_identities 一一对应；非队列任务为 None。
        # 以任务创建那一刻的星期为准，队列跨过午夜后后面的项不会按第二天算。
        self.script_run_days = script_run_days
        self.run_weekday = datetime.now().strftime("%A")
        self.script_reservations = script_reservations or _ScriptTaskReservations()
        self.is_closing = False
        self._exit_result = "success"
        self._exit_error: str | None = None
        self._queue_run_started = False
        self._queue_before_script_ran = False
        self._queue_after_script_ran = False
        self._queue_script_task: asyncio.Task | None = None

    def _record_error(self, error: str) -> None:
        """保留任务遇到的首个错误，供完成事件提供机器可读结果。"""
        if self._exit_result == "success":
            self._exit_result = "error"
            self._exit_error = error

    def cancel(self) -> bool:
        """记录显式取消结果，覆盖尚未进入脚本执行阶段的任务。"""
        self.task_info.replay_cancelled = True
        self.stopped_manually = True
        # 运行前脚本随主任务取消；运行后脚本在独立的收尾协程里，需要主动取消。
        if (
            self._queue_after_script_ran
            and self._queue_script_task is not None
            and not self._queue_script_task.done()
        ):
            self._queue_script_task.cancel()
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
                name=Config.ScriptConfig[uuid.UUID(script_id)].Info.Name,
                user_list=[]
                if self.task_info.mode == "AutoProxy"
                else [
                    UserItem(user_id=str(uuid.uuid4()), name="暂未加载", status="等待")
                ],
            )
            for script_id in script_ids
        ]
        self.task_info.schedule_on_change()

        logger.success(
            f"任务 {self.task_info.task_id} 检索完成，包含 {len(self.task_info.script_list)} 个脚本项"
        )

    async def main_task(self):
        from app.services import telemetry as _service_telemetry

        attributes = {
            "mode": self.task_info.mode,
            "trigger": self.task_info.trigger_source,
        }
        started_at = time.perf_counter()
        outcome = "success"

        try:
            with _service_telemetry.observe_span(
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
            _service_telemetry.record_count(
                "auto_mas.task.runs", attributes=metric_attributes
            )
            _service_telemetry.record_distribution(
                "auto_mas.task.duration",
                (time.perf_counter() - started_at) * 1000,
                unit="millisecond",
                attributes=metric_attributes,
            )

    @contextmanager
    def _observe_script_run(
        self, script_item: ScriptItem, script_config
    ) -> Iterator[None]:
        """按专项记一次脚本运行；顺序执行与循环运行共用。

        结果只看用户状态：MAA、通用脚本等专项无论成败都把脚本状态收成「完成」，
        拿脚本状态判会把全员失败也记成成功，各专项之间没法比。
        """

        from app.services import telemetry as _service_telemetry

        outcome = "error"
        partial_failure = "unknown"
        run = (
            WSTaskScriptStartedData(
                taskId=self.task_info.task_id,
                runId=str(uuid.uuid4()),
                scriptType=_SCRIPT_TYPE_BY_CLASS.get(
                    type(script_config).__name__, "unknown"
                ),
                mode="CycleRun" if self.task_info.is_cycle else "AutoProxy",
            )
            if self.task_info.mode == "AutoProxy"
            else None
        )
        started = (
            _publish_script_observation(
                message_type=protocol.TASK_SCRIPT_STARTED, data=run
            )
            if run is not None
            else None
        )
        try:
            yield
            user_statuses = [
                user.status
                for user in script_item.user_list
                if not user.maintenance_skipped
            ]
            if script_item.status == "异常":
                outcome = "failed"
            elif script_item.user_list and not user_statuses:
                outcome = "skipped"
            elif not user_statuses:
                # 运行前检查没过时还没加载用户，脚本状态是「异常」
                outcome = "failed" if script_item.status == "异常" else "no_user"
            elif all(status in SUCCESS_USER_STATUSES for status in user_statuses):
                outcome = "success"
                partial_failure = "yes" if "部分失败" in user_statuses else "no"
            elif "异常" in user_statuses:
                outcome = "failed"
            else:
                outcome = "incomplete"
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        finally:
            _service_telemetry.record_count(
                "auto_mas.script.runs",
                attributes={
                    "script_type": _SCRIPT_TYPE_BY_CLASS.get(
                        type(script_config).__name__, "unknown"
                    ),
                    "mode": self.task_info.mode,
                    "outcome": outcome,
                },
            )
            if run is not None and started is not None:
                _publish_script_observation(
                    message_type=protocol.TASK_SCRIPT_FINISHED,
                    data=WSTaskScriptFinishedData(
                        **run.model_dump(),
                        outcome=outcome,
                        partialFailure=partial_failure,
                    ),
                    after=started,
                )

    def _build_task_item(
        self,
        script_item: ScriptItem,
        script_config,
        *,
        script_uid: uuid.UUID,
        reservation_owner: str,
        root_paths: tuple[Path, ...],
        emulator_key: str | None,
    ):
        """按脚本类型构造对应的脚本调度器，类型不支持时返回 None。

        顺序执行与循环运行共用宿主注入的工厂，按 type 精确查表。
        """

        build = self._manager_factories.get(type(script_config))
        if build is None:
            return None
        return build(
            script_item,
            ManagerBuildContext(
                root_paths=root_paths,
                # 追加目录与初始预约使用同一归属及模拟器键。
                reserve_root=lambda root_path: self.script_reservations.try_acquire(
                    script_uid,
                    reservation_owner,
                    root_paths=(root_path,),
                    emulator_key=emulator_key,
                ),
            ),
        )

    async def _run_cycle_task(self) -> None:
        """循环运行：按各队列项自己的周期，持续调度整个队列。

        与顺序执行的区别只在「什么时候跑哪一项」，真正跑脚本的那一步共用
        ``_build_task_item``；每一轮对脚本适配器而言就是一次普通的自动代理。
        """

        if self.task_info.queue_id is None:
            raise RuntimeError("循环运行必须指定队列")

        queue_uid = uuid.UUID(self.task_info.queue_id)
        logger.info(f"循环队列开始运行: {queue_uid}")
        # 占用标记在 add_task 里与重复启动检查一起打上，这里只负责撤掉；
        # prepare 也放进 try，它一失败标记就得跟着清。
        try:
            await self.prepare()
            await self._notice_scope_skipped_scripts()
            self._queue_run_started = True
            await self._run_queue_extra_script(
                queue_uid,
                "IfScriptBeforeTask",
                "ScriptBeforeTask",
                "队列运行前脚本",
            )
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
        entries = self._collect_entries(queue_uid)

        # 首次推算的结果要落盘，重启后才不会当成「立刻可跑」重来一遍。
        # 只在还是空值哨兵时写：已经排过期的每轮重写一遍纯属白费写盘。
        for entry in entries:
            queue_item = queue.QueueItem[uuid.UUID(entry.queue_item_id)]
            stored = parse_cycle_time(queue_item.Schedule.NextRunAt)
            if is_empty_cycle_time(stored) and entry.next_run_at > now:
                await queue_item.update(
                    type(queue_item).model_validate(
                        {
                            "Schedule": {
                                "NextRunAt": format_cycle_time(entry.next_run_at)
                            }
                        }
                    ),
                    check_visibility=False,
                )

        await self._publish_cycle_preview(entries)

        if not entries:
            await asyncio.sleep(CYCLE_IDLE_SLEEP_SECONDS)
            return

        pending = due_entries(entries)
        if not pending:
            await self._sleep_until(min(entry.next_run_at for entry in entries))
            return

        await self._run_due_entries(queue_uid, pending)

    async def _sleep_until(self, target: datetime) -> None:
        """睡到目标时刻，单次不超过上限。

        上限是防时钟跳变的：睡醒后调用方会用当前时间重新推算，跳变最多让这一轮
        迟到一个上限的时间。
        """

        delay = (target - datetime.now()).total_seconds()
        await asyncio.sleep(max(1.0, min(delay, CYCLE_MAX_SLEEP_SECONDS)))

    async def _run_due_entries(
        self, queue_uid: uuid.UUID, pending: list[CycleEntry]
    ) -> None:
        """按队列顺序跑完这一轮所有到点的条目。

        每跑一个都重新推算：前一个条目刚改写了自己的下次运行时间，后面的预览和
        判断都得基于新状态，不能沿用本轮开头那份快照。被占用或没跑成的条目留到
        下一轮；一轮里一个都没跑成就先退避，不让循环空转。
        """

        results: list[str] = []
        for stale in pending:
            entries = self._collect_entries(queue_uid)
            entry = next(
                (e for e in entries if e.queue_item_id == stale.queue_item_id), None
            )
            if entry is None or not entry.is_due:
                continue
            results.append(await self._run_cycle_entry(queue_uid, entry, entries))

        if results and not any(result in ("success", "skipped") for result in results):
            await asyncio.sleep(CYCLE_RETRY_SLEEP_SECONDS)

    def _scope_skipped_script_ids(self) -> set[str]:
        """本次运行范围内被整项排除的托管（勾选后一个用户都没选）。"""

        scope = self.task_info.user_ids_by_script
        if not scope:
            return set()
        return {script_id for script_id, user_ids in scope.items() if not user_ids}

    async def _notice_scope_skipped_scripts(self) -> None:
        """循环运行前把本次未选择任何用户的托管标记为跳过，并只提示一次。"""

        skipped = self._scope_skipped_script_ids()
        if not skipped:
            return
        for script_item in self.task_info.script_list:
            if script_item.script_id not in skipped:
                continue
            script_item.status = "跳过"
            logger.info(f"跳过任务: {script_item.script_id}, 本次未选择任何用户")
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="warning",
                    message=f"任务 {script_item.name} 本次未选择任何用户, 已跳过",
                ),
            )

    def _collect_entries(self, queue_uid: uuid.UUID) -> list[CycleEntry]:
        """收集队列的待运行条目，并剔除本次一个用户都没选的托管。"""

        entries = collect_cycle_entries(
            Config.QueueConfig[queue_uid], Config.ScriptConfig, datetime.now()
        )
        skipped = self._scope_skipped_script_ids()
        if not skipped:
            return entries
        return [entry for entry in entries if entry.script_id not in skipped]

    async def _run_cycle_entry(
        self,
        queue_uid: uuid.UUID,
        entry: CycleEntry,
        entries: list[CycleEntry],
    ) -> Literal["success", "failed", "blocked", "skipped"]:
        """跑一个队列项。

        Returns:
            ``blocked`` 表示脚本被别的任务占用、本轮没跑；``failed`` 表示跑了但没成功。
            ``skipped`` 表示维护跳过，按原周期排下一轮，不立即重试。
        """

        # 脚本列表是建任务时冻结的，靠下标回写状态。队列结构在运行中被改过
        # （队列项没了、下标对不上脚本）就不能再信任，宁可停下也不能跑错脚本。
        try:
            queue_item = Config.QueueConfig[queue_uid].QueueItem[
                uuid.UUID(entry.queue_item_id)
            ]
        except KeyError:
            raise RuntimeError(
                "循环队列的结构在运行中被改动，已停止循环，请重新启动"
            ) from None
        script_list = self.task_info.script_list
        if (
            entry.index >= len(script_list)
            or script_list[entry.index].script_id != entry.script_id
        ):
            raise RuntimeError("循环队列的结构在运行中被改动，已停止循环，请重新启动")
        script_uid = uuid.UUID(entry.script_id)
        script_item = script_list[entry.index]

        # collect 时已过滤掉被删的脚本，这里只防它在本轮中途被删。
        if script_uid not in Config.ScriptConfig:
            self.task_info.begin_script_run(script_item)
            script_item.status = "异常"
            logger.warning(f"循环跳过: {script_uid} 对应脚本已被删除")
            return "failed"

        script_config = Config.ScriptConfig[script_uid]
        self.task_info.current_index = entry.index
        root_paths, emulator_key = _exclusive_resources(script_config)
        reservation_owner = self.task_info.task_id

        # 与顺序执行同一套原子占用，不再自己判 is_locked 轮询。
        if script_config.is_locked or not self.script_reservations.try_acquire(
            script_uid,
            reservation_owner,
            root_paths=root_paths,
            emulator_key=emulator_key,
        ):
            script_item.status = "等待"
            logger.info(f"循环等待: {entry.script_name} 已被其他任务占用")
            return "blocked"

        self.task_info.begin_script_run(script_item)
        started_at = datetime.now()
        previous_started_at = queue_item.Data.LastCycleStartedAt
        success = False
        # 循环要跑上几天，单个条目出错只算这一轮失败，不能把整个循环带崩；
        # 用户主动停止走的是 CancelledError，不在这里拦。
        try:
            await queue_item.update(
                type(queue_item).model_validate(
                    {"Data": {"LastCycleStartedAt": format_cycle_time(started_at)}}
                ),
                check_visibility=False,
            )
            # 先按开始时间排下一轮：万一这轮崩了，下次运行时间也不会停在过去。
            if queue_item.Schedule.IntervalAnchor == "start":
                await queue_item.update(
                    type(queue_item).model_validate(
                        {
                            "Schedule": {
                                "NextRunAt": format_next_run(
                                    next_after_start(queue_item, started_at)
                                )
                            }
                        }
                    ),
                    check_visibility=False,
                )

            task_item = self._build_task_item(
                script_item,
                script_config,
                script_uid=script_uid,
                reservation_owner=reservation_owner,
                root_paths=root_paths,
                emulator_key=emulator_key,
            )
            if task_item is None:
                script_item.status = "异常"
                logger.error(f"不支持的脚本类型: {type(script_config).__name__}")
            else:
                self.task_info.current_index = entry.index
                script_item.status = "运行"
                logger.info(f"循环任务开始: {script_uid}")
                # 开跑那一刻就把预览翻成「运行中」，别等旁路任务 5 秒后才刷新
                await self._publish_cycle_preview(entries, running=entry)

                with self._observe_script_run(script_item, script_config):
                    await self._spawn_with_preview(task_item, entry, queue_uid)

                success = is_script_success(
                    script_item.status,
                    (user.status for user in script_item.user_list),
                )
        except Exception as e:
            script_item.status = "异常"
            logger.exception(f"循环任务出现异常: {entry.script_name}: {e}")
        finally:
            self.script_reservations.release(script_uid, reservation_owner)

        # 维护可能在 manager 准备期间开始；全员尚未开跑时不留实际运行记录。
        if (
            script_item.status == "跳过"
            and script_item.user_list
            and all(user.maintenance_skipped for user in script_item.user_list)
        ):
            await queue_item.update(
                type(queue_item).model_validate(
                    {"Data": {"LastCycleStartedAt": previous_started_at}}
                ),
                check_visibility=False,
            )
            await self._advance_cycle_after_maintenance(queue_item)
            return "skipped"

        # 成败都要把下次运行时间推到未来，否则失败的条目会立刻再被挑中。
        finished_at = datetime.now()
        await queue_item.update(
            type(queue_item).model_validate(
                {"Data": {"LastCycleFinishedAt": format_cycle_time(finished_at)}}
            ),
            check_visibility=False,
        )
        if queue_item.Schedule.IntervalAnchor == "start":
            # 跑得比间隔还久时往后顺延，别一结束就立刻再来一轮。
            next_run_at = next_after_start(queue_item, started_at, after=finished_at)
        else:
            next_run_at = next_after_finish(queue_item, finished_at)
        await queue_item.update(
            type(queue_item).model_validate(
                {"Schedule": {"NextRunAt": format_next_run(next_run_at)}}
            ),
            check_visibility=False,
        )

        if not success:
            logger.warning(f"循环任务未成功: {entry.script_name}")
        return "success" if success else "failed"

    async def _advance_cycle_after_maintenance(self, queue_item) -> None:
        """仅消费本次排期，不记录代理执行，也不安排维护结束补跑。"""
        skipped_at = datetime.now()
        if queue_item.Schedule.IntervalAnchor == "start":
            next_run_at = next_after_start(queue_item, skipped_at)
        else:
            next_run_at = next_after_finish(queue_item, skipped_at)
        await queue_item.update(
            type(queue_item).model_validate(
                {"Schedule": {"NextRunAt": format_next_run(next_run_at)}}
            ),
            check_visibility=False,
        )

    async def _spawn_with_preview(
        self,
        task_item: TaskExecuteBase,
        entry: CycleEntry,
        queue_uid: uuid.UUID,
    ) -> None:
        """跑子任务，期间定期刷新预览，让「还有多久轮到下一个」保持准确。

        子任务必须直接 ``await``：用户停止时取消要顺着这个 await 传到子任务，
        换成 ``asyncio.wait`` 之类的间接等待，取消就只会停到循环这一层，正在跑的
        脚本还会继续。所以定时刷新放在旁路任务里，跑完就撤。
        """

        child = self.spawn(task_item)
        refresher = RuntimeTasks.spawn(
            self._refresh_preview_while_running(queue_uid, entry),
            name=f"cycle-preview:{self.task_info.task_id}",
        )
        try:
            await child
        finally:
            if refresher is not None:
                refresher.cancel()

    async def _refresh_preview_while_running(
        self, queue_uid: uuid.UUID, running: CycleEntry
    ) -> None:
        # 每次都重新推算：跑得久的时候其他条目会陆续到点，预览得跟着变
        while True:
            await asyncio.sleep(CYCLE_PREVIEW_REFRESH_SECONDS)
            await self._publish_cycle_preview(
                self._collect_entries(queue_uid), running=running
            )

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

    async def _run_main_task(self):

        # 循环运行不参与签到与顺序执行那套流程，单独走自己的调度。
        if self.task_info.is_cycle:
            await self._run_cycle_task()
            return

        # 签到在后台并行执行；完成事件由报告协调器接收，不阻塞脚本初始化与运行。
        if self.task_info.mode == "AutoProxy":
            from app.core import MainTimer
            from app.core.notify.task_report import (
                receive_task_community_results as receive_task_community_results,
            )

            sign_source = {
                "scheduled_task": "task_scheduled",
                "manual_task": "task_manual",
                "startup_task": "task_startup",
            }.get(self.task_info.trigger_source, "task_manual")
            community_sign = Notify.create_task_report_coordinator(self.task_info)
            self.task_info.community_sign_notification = community_sign
            MainTimer.schedule_community_for_task(
                source=sign_source,
                on_completed=lambda results: receive_task_community_results(
                    community_sign, results
                ),
            )

        await self.prepare()

        if self.task_info.queue_id is not None:
            self._queue_run_started = True
            await self._run_queue_extra_script(
                self.task_info.queue_id,
                "IfScriptBeforeTask",
                "ScriptBeforeTask",
                "队列运行前脚本",
            )

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

        # 依次运行任务。桌面保障是常驻守卫，这里只强制它立刻巡检一次：轮询有几秒窗口，
        # 而任务一旦在幻影屏上起来，游戏就会把坏掉的窗口尺寸记进自己的配置。
        await ensure_desktop_available()
        await self._run_script_list(start_index)

    async def _run_queue_extra_script(
        self, queue_id: str | uuid.UUID, if_key: str, path_key: str, label: str
    ) -> bool:
        """执行队列级额外脚本；每个阶段只允许由队列生命周期调用一次。"""

        if self.stopped_manually or self.is_closing:
            return False

        queue_uid = uuid.UUID(str(queue_id))
        if queue_uid not in Config.QueueConfig:
            return False
        queue_config = Config.QueueConfig[queue_uid]
        if not getattr(queue_config.Info, if_key):
            return False

        script_path = str(getattr(queue_config.Info, path_key) or "").strip()
        if not script_path:
            return False

        if if_key == "IfScriptBeforeTask":
            if self._queue_before_script_ran:
                return False
            self._queue_before_script_ran = True
        elif if_key == "IfScriptAfterTask":
            if self._queue_after_script_ran:
                return False
            self._queue_after_script_ran = True

        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="info", message=f"开始执行{label}"),
        )
        # 发布通知会让出执行权，停止请求可能恰好落在创建脚本进程之前。
        if self.stopped_manually or self.is_closing:
            return False
        script_task = asyncio.create_task(execute_script_task(Path(script_path), label))
        self._queue_script_task = script_task
        try:
            succeeded = await script_task
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="info" if succeeded else "warning",
                    message=f"{label}执行{'成功' if succeeded else '失败'}",
                ),
            )
            return succeeded
        except asyncio.CancelledError:
            # 停止收尾脚本后仍发布任务终态，且不再安排完成后操作。
            if self.stopped_manually and if_key == "IfScriptAfterTask":
                return False
            raise
        finally:
            if self._queue_script_task is script_task:
                self._queue_script_task = None

    def _is_script_scheduled_today(self, index: int) -> bool:
        """队列项的运行周几不含创建任务当天时跳过；非队列任务与缺省项一律运行。"""

        if self.script_run_days is None or index >= len(self.script_run_days):
            return True
        return self.run_weekday in self.script_run_days[index]

    async def _run_script_list(self, start_index: int) -> None:
        for self.task_info.current_index in range(
            start_index, len(self.task_info.script_list)
        ):
            script_item = self.task_info.script_list[self.task_info.current_index]
            self.task_info.begin_script_run(script_item)
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

            # 队列任务按托管勾选了本次运行范围时，一个用户都没选的托管整项跳过
            script_scope = self.task_info.script_user_scope(script_item.script_id)
            if script_scope is not None and not script_scope:
                script_item.status = "跳过"
                logger.info(f"跳过任务: {current_script_uid}, 本次未选择任何用户")
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="warning",
                        message=f"任务 {script_item.name} 本次未选择任何用户, 已跳过",
                    ),
                )
                continue

            if not self._is_script_scheduled_today(self.task_info.current_index):
                script_item.status = "跳过"
                logger.info(
                    f"跳过任务: {current_script_uid}, 队列项未安排在 {self.run_weekday} 运行"
                )
                continue

            # 原子占用脚本，避免两个调度器同时通过布尔锁前置检查。
            reservation_owner = self.task_info.task_id
            script_config = Config.ScriptConfig[current_script_uid]
            root_paths, emulator_key = _exclusive_resources(script_config)
            if not self.script_reservations.try_acquire(
                current_script_uid,
                reservation_owner,
                root_paths=root_paths,
                emulator_key=emulator_key,
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
                    root_paths=root_paths,
                    emulator_key=emulator_key,
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
                with self._observe_script_run(script_item, script_config):
                    await self.spawn(task_item)
            finally:
                self.script_reservations.release(current_script_uid, reservation_owner)

    async def final_task(self) -> None:
        await self.task_info.discard_history_captures()

        # 收尾脚本完成后才发布终态，期间队列仍可被停止。
        if self._queue_run_started and self.task_info.queue_id is not None:
            await self._run_queue_extra_script(
                self.task_info.queue_id,
                "IfScriptAfterTask",
                "ScriptAfterTask",
                "队列运行后脚本",
            )

        logger.info(f"任务结束: {self.task_info.task_id}")

        if self.task_info.community_sign_notification is not None:
            self.task_info.community_sign_notification.finish()

        # 完成面板文本带采集节点详情（与推送报告同源渲染），
        # 未配置推送的用户在调度台也能看到
        result_text = build_task_result_text(self.task_info.script_list)
        await Publisher.send(
            id=str(self.task_info.task_id),
            type=protocol.TASK_COMPLETED,
            data=WSTaskCompletedData(
                result=result_text,
                outcome=self._exit_result,
                error=self._exit_error,
                task_info=self.task_info.asdict,
            ),
        )
        # 同一步里先留存终态：任务从运行快照摘掉后仍要能凭 taskId 查到
        if self._on_finished is not None:
            self._on_finished(
                TaskStatusOut(
                    taskId=str(self.task_info.task_id),
                    status=self._exit_result,
                    detail=result_text,
                    error=self._exit_error,
                    mode=self.task_info.mode,
                    isCycle=self.task_info.is_cycle,
                    queueId=self.task_info.queue_id,
                    scriptId=self.task_info.script_id,
                    userId=self.task_info.user_id,
                    finishedAt=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
            )

        # 循环任务只会被用户主动停止，此时不该再执行队列的「完成后操作」——
        # 那会把关机之类的动作接在一次手动停止后面。
        if (
            not self.is_closing
            and not self.stopped_manually
            and not self.task_info.is_cycle
            and self.task_info.mode == "AutoProxy"
            and self.task_info.queue_id is not None
        ):
            if Config.power_sign == "NoAction":
                queue_uid = uuid.UUID(self.task_info.queue_id)
                if queue_uid not in Config.QueueConfig:
                    logger.info(f"队列 {queue_uid} 已删除，跳过完成后操作")
                    return
                queue_config = Config.QueueConfig[queue_uid]
                Config.power_sign = queue_config.Info.AfterAccomplish
                # 队列可为完成后操作单独设定延时, 延时期间不弹出倒计时窗口
                Config.power_delay = queue_config.Info.AfterAccomplishDelay * 60
                await Publisher.send(
                    id=protocol.ID_MAIN,
                    type=protocol.POWER_SIGN_UPDATED,
                    data=WSPowerSignData(signal=Config.power_sign),
                )

    async def on_crash(self, e: Exception) -> None:
        """处理任务异常并记录退出状态。"""
        current = self.task_info.current_index
        script = (
            self.task_info.script_list[current]
            if 0 <= current < len(self.task_info.script_list)
            else None
        )
        self.task_info._request_unassigned_replay(
            script, reason=f"任务执行异常：{type(e).__name__}: {e}"
        )
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

        self._manager_factories: (
            Mapping[type[ConfigEntry], ManagerFactory | None] | None
        ) = None
        self.task_info: Dict[uuid.UUID, TaskInfo] = {}
        self.task_handler: Dict[uuid.UUID, Task] = {}
        # taskId → (结束时刻的单调读数, 终态)，供单点查询在任务摘掉后回读
        self._recent_results: OrderedDict[str, tuple[float, TaskStatusOut]] = (
            OrderedDict()
        )
        self._script_reservations = _ScriptTaskReservations()
        self._cleanup_tasks: set[asyncio.Task[None]] = set()
        self._stop_all_lock = asyncio.Lock()
        self._stopping_all = False
        # 已通过 add_task 入口检查、尚未 execute 的任务数；停止全部任务要等它们落定再取快照
        self._creating_tasks = 0
        self._creating_tasks_idle = asyncio.Event()
        self._creating_tasks_idle.set()
        self._startup_queue_started = False
        # 正在等待/执行启动队列的连接回调任务，同一时间只有一个
        self._startup_queue_task: asyncio.Task | None = None

    def bind_manager_factories(
        self, factories: Mapping[type[ConfigEntry], ManagerFactory | None]
    ) -> None:
        """启动时由宿主绑定；拒绝在已有任务时替换工厂。"""
        if self._manager_factories is not None:
            raise RuntimeError("任务工厂已经装配")
        self._manager_factories = factories

    @staticmethod
    def _queue_script_entries(
        queue_id: uuid.UUID,
    ) -> list[tuple[uuid.UUID, list[str]]]:
        """返回队列中实际引用的脚本 ID 及该队列项限定的运行周几。"""

        return [
            (uuid.UUID(script_id), list(queue_item.Schedule.Days))
            for queue_item in Config.QueueConfig[queue_id].QueueItem.values()
            if (script_id := str(queue_item.Info.ScriptId or "").strip())
            and script_id != "-"
        ]

    @classmethod
    def _queue_script_ids(cls, queue_id: uuid.UUID) -> list[uuid.UUID]:
        """返回队列中实际引用的脚本 ID。"""

        return [script_id for script_id, _ in cls._queue_script_entries(queue_id)]

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
            if queue.Info.CycleEnabled:
                continue
            if not queue.Info.TimeEnabled:
                continue
            if not any(
                (
                    time_set.Info.Enabled and time_set.Info.Days
                    for time_set in queue.TimeSet.values()
                )
            ):
                continue

            for script_id in self._queue_script_ids(queue_id):
                if script_id not in Config.ScriptConfig:
                    continue
                identities.setdefault(script_id, self._script_identity(script_id))

        return list(identities.values())

    def _remember_result(self, status: TaskStatusOut) -> None:
        """留存刚结束任务的终态，供已摘掉的任务按 taskId 回查。"""

        self._recent_results.pop(status.taskId, None)
        self._recent_results[status.taskId] = (time.monotonic(), status)
        while len(self._recent_results) > _RECENT_RESULTS_MAX:
            self._recent_results.popitem(last=False)

    def _prune_recent_results(self) -> None:
        """丢弃超出留存时长的终态，避免陈旧结果被当成刚结束的任务。"""

        deadline = time.monotonic() - _RECENT_RESULTS_TTL_SECONDS
        while self._recent_results:
            finished_at, _ = next(iter(self._recent_results.values()))
            if finished_at > deadline:
                break
            self._recent_results.popitem(last=False)

    def get_task_status(self, task_id: str) -> TaskStatusOut | None:
        """按 taskId 单点返回运行中或最近完成任务的终态；找不到返回 None。"""

        try:
            task_uid = uuid.UUID(task_id)
        except ValueError:
            return None

        task_info = self.task_info.get(task_uid)
        if task_info is not None:
            handler = self.task_handler.get(task_uid)
            return TaskStatusOut(
                taskId=task_id,
                status="running",
                mode=task_info.mode,
                isCycle=task_info.is_cycle,
                queueId=task_info.queue_id,
                scriptId=task_info.script_id,
                userId=task_info.user_id,
                stopping=bool(handler and handler.is_closing),
            )

        self._prune_recent_results()
        remembered = self._recent_results.get(task_id)
        return remembered[1] if remembered is not None else None

    def get_runtime_snapshot(self) -> TaskRuntimeSnapshot:
        """返回任务运行状态与定时队列的 HTTP 初始快照。"""

        tasks: list[TaskRuntimeSnapshotItem] = []
        for task_uid, task_info in list(self.task_info.items()):
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
                    # 返回上次推送的日志而非当前日志, 保证与下一条增量推送衔接
                    log=task_info._last_pushed_log[-200_000:],
                    logSeq=task_info._log_seq,
                    logFirstLine=task_info._last_pushed_log_first_line
                    + task_info._last_pushed_log.count(
                        "\n", 0, max(0, len(task_info._last_pushed_log) - 200_000)
                    ),
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

    @staticmethod
    def _resolve_target_user(
        script_uid: uuid.UUID, user_id: str | None
    ) -> uuid.UUID | None:
        """校验单独运行所指定的用户

        Args:
            script_uid (uuid.UUID): 目标脚本 UID。
            user_id (str | None): 指定的用户 ID; 为 None 时表示运行全部用户。

        Returns:
            uuid.UUID | None: 指定用户的 UID; 未指定时为 None。

        Raises:
            ValueError: 用户不属于该脚本, 或该用户当前不可运行。
        """

        if user_id is None:
            return None

        script_config = Config.ScriptConfig[script_uid]
        script_name = script_config.Info.Name
        try:
            user_uid = uuid.UUID(user_id)
        except ValueError as e:
            raise ValueError(f"用户 {user_id} 不属于脚本 {script_name}") from e
        if user_uid not in script_config.UserData:
            raise ValueError(f"用户 {user_id} 不属于脚本 {script_name}")

        # 与各脚本适配器构建用户列表时的筛选口径保持一致，否则会静默跑出一个空用户列表
        user_config = script_config.UserData[user_uid]
        if not user_config.Info.Status or user_config.Info.RemainedDay == 0:
            raise ValueError(f"用户 {user_config.Info.Name} 未启用或代理天数已耗尽")
        return user_uid

    def _resolve_target_users(
        self, script_uid: uuid.UUID, user_ids: list[str] | None
    ) -> frozenset[str] | None:
        # 校验多选运行所指定的用户集合。
        if user_ids is None:
            return None
        if not user_ids:
            raise ValueError("至少选择一个用户")

        selected: set[str] = set()
        for user_id in user_ids:
            user_uid = self._resolve_target_user(script_uid, user_id)
            if user_uid is not None:
                selected.add(str(user_uid))

        return frozenset(selected)

    def _resolve_queue_user_scope(
        self, queue_id: uuid.UUID, queue_user_ids: dict[str, list[str]]
    ) -> dict[str, frozenset[str]]:
        # 校验队列任务按脚本指定的本次运行用户，口径与脚本任务的多选一致。
        queue_script_ids = {
            str(script_id) for script_id in self._queue_script_ids(queue_id)
        }
        scope: dict[str, frozenset[str]] = {}
        for script_id, user_ids in queue_user_ids.items():
            if script_id not in queue_script_ids:
                queue_name = Config.QueueConfig[queue_id].Info.Name
                raise ValueError(f"脚本 {script_id} 不属于队列 {queue_name}")
            if not user_ids:
                # 空集合是有意义的取值：该托管本次一个用户都不跑。
                scope[script_id] = frozenset()
                continue
            scope[script_id] = (
                self._resolve_target_users(uuid.UUID(script_id), list(user_ids))
                or frozenset()
            )
        return scope

    async def add_task(
        self,
        mode: Literal["AutoProxy", "ScriptConfig", "Update", "CycleRun"],
        id: str,
        new_task_info: dict | None = None,
        resume_from_script_id: str | None = None,
        user_id: str | None = None,
        user_ids: list[str] | None = None,
        queue_user_ids: dict[str, list[str]] | None = None,
        trigger_source: TaskTriggerSource = "manual_task",
        view_only: bool = False,
        instance_idx: int | None = None,
    ) -> uuid.UUID:
        """
        添加任务, 根据 id 值搜索实际指向的任务配置

        Args:
            mode (str): 任务模式; CycleRun 只接受循环队列
            id (str): 任务项对应的配置 ID
            new_task_info (dict): 新任务项信息. Defaults to {}.
            user_id (str): 单独运行的用户 ID; 仅脚本的自动代理任务可用。
            user_ids (list[str]): 多选运行的用户 ID; 仅脚本的自动代理任务可用。
            queue_user_ids (dict[str, list[str]]): 按脚本ID指定本次运行的用户 ID;
                仅队列任务可用, 未列出的脚本不限, 空列表表示该脚本本次整项跳过。
            trigger_source: MAS 任务触发来源，API 手动启动默认 manual_task。
            view_only: 配置查看会话（ScriptConfig 专用）：只读打开原生界面，
                不注入基线也不回读字段，用于「查看历史备份」等预览场景。
            instance_idx: 配置会话（ScriptConfig 专用）：直控指定会话窗口
                打开的原生实例（临时切换活跃，会话结束还原）。

        Returns:
            uuid.UUID: 任务 UID
        """

        if self._manager_factories is None:
            raise RuntimeError("任务工厂未初始化：请先由宿主装配")
        uid = uuid.UUID(id)

        # 停止全部任务期间拒绝新任务，否则它不在停止快照里，却会让停止流程
        # 一直等到它自然跑完。从这里到下方计入 _creating_tasks 之间不能有 await。
        if self._stopping_all:
            raise RuntimeError("正在停止全部任务，暂不接受新任务")

        # 用户范围只对「脚本 + 自动代理」成立；队列到不了用户粒度，设置类任务
        # 的用户由 uid 自身表达。放在循环队列占用标记之前，避免拒绝时留下脏标记。
        if user_id is not None and user_ids is not None:
            raise ValueError("多选用户不能与单独运行用户同时使用")

        if (user_id is not None or user_ids is not None) and (
            mode != "AutoProxy" or uid not in Config.ScriptConfig
        ):
            raise ValueError("指定运行用户仅支持脚本的自动代理任务")

        # 队列的用户范围是按托管分别收窄，与脚本任务的整任务用户范围是两套入参。
        if queue_user_ids is not None and (
            mode not in ("AutoProxy", "CycleRun") or uid not in Config.QueueConfig
        ):
            raise ValueError("按脚本指定运行用户仅支持队列任务")

        # CycleRun 只是「怎么排」的差别，脚本仍按自动代理执行；各脚本适配器
        # 只认 AutoProxy，所以模式在这里就翻译掉，循环与否记在 is_cycle 上。
        is_cycle = mode == "CycleRun"
        exec_mode: Literal["AutoProxy", "ScriptConfig", "Update"] = (
            "AutoProxy" if is_cycle else mode
        )

        if is_cycle:
            if uid not in Config.QueueConfig:
                raise ValueError(f"循环运行的任务 {uid} 必须是调度队列")
            if not Config.QueueConfig[uid].Info.CycleEnabled:
                raise ValueError(
                    f"队列 {Config.QueueConfig[uid].Info.Name} 不是循环队列"
                )
            if uid in Config.running_cycle_queue_ids:
                raise RuntimeError(
                    f"循环队列 {Config.QueueConfig[uid].Info.Name} 已在运行"
                )
            # 立刻打上占用标记：检查到这里之间没有 await，并发的两次启动才不会都通过
            Config.running_cycle_queue_ids.add(uid)

        selected_user_ids: frozenset[str] | None = None
        selected_user_scope: dict[str, frozenset[str]] | None = None

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
            user_uid = self._resolve_target_user(uid, user_id)
            selected_user_ids = self._resolve_target_users(uid, user_ids)
        else:
            raise ValueError(f"任务 {uid} 无法找到对应脚本配置")

        # 创建时冻结任务脚本身份，供 task.created 通知与运行时快照复用；
        # 队列项限定的运行周几随身份一起冻结，顺序执行时据此跳过
        script_run_days: list[list[str]] | None = None
        if queue_id is not None:
            queue_entries = [
                entry
                for entry in self._queue_script_entries(queue_id)
                if entry[0] in Config.ScriptConfig
            ]
            target_script_ids = [script_id for script_id, _ in queue_entries]
            script_run_days = [days for _, days in queue_entries]
            if queue_user_ids is not None:
                selected_user_scope = self._resolve_queue_user_scope(
                    queue_id, queue_user_ids
                )
        elif script_uid is not None and script_uid in Config.ScriptConfig:
            target_script_ids = [script_uid]
        else:
            target_script_ids = []
        script_identities = [
            self._script_identity(script_id) for script_id in target_script_ids
        ]

        reservation_owner = str(task_uid)
        reservation_acquired = False
        if script_uid is not None:
            script_config = Config.ScriptConfig[script_uid]
            root_paths, emulator_key = _exclusive_resources(script_config)
            if script_config.is_locked or not self._script_reservations.try_acquire(
                script_uid,
                reservation_owner,
                root_paths=root_paths,
                emulator_key=emulator_key,
            ):
                raise RuntimeError(f"任务 {script_config.Info.Name} 已在运行")
            reservation_acquired = True

        self._creating_tasks += 1
        self._creating_tasks_idle.clear()
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
                user_ids=selected_user_ids,
                user_ids_by_script=selected_user_scope,
                resume_from_script_id=resume_from_script_id,
                trigger_source=trigger_source,
                is_cycle=is_cycle,
                view_only=view_only and exec_mode == "ScriptConfig",
                instance_idx=instance_idx if exec_mode == "ScriptConfig" else None,
            )
            self.task_handler[task_uid] = Task(
                self.task_info[task_uid],
                script_identities,
                self._script_reservations,
                script_run_days=script_run_days,
                on_finished=self._remember_result,
                manager_factories=self._manager_factories,
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
            if is_cycle:
                Config.running_cycle_queue_ids.discard(uid)
            self.task_handler.pop(task_uid, None)
            self.task_info.pop(task_uid, None)
            raise
        finally:
            self._creating_tasks -= 1
            if self._creating_tasks == 0:
                self._creating_tasks_idle.set()

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
            from app.core import MainTimer

            await System.start_power_task(before_power=MainTimer.drain_community_tasks)

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
                Config.power_delay = 0
                try:
                    if System.power_task is not None and not System.power_task.done():
                        await System.cancel_power_task()

                    # 新任务已被拒绝；已过入口检查、正在发送创建通知的任务等它们
                    # execute 之后再取快照，保证快照覆盖全部任务。
                    await self._creating_tasks_idle.wait()

                    # 先全部发出取消再统一等待，不让一个任务的收尾拖住其余任务的取消。
                    task_item_list = list(self.task_handler.values())
                    if task_item_list:
                        logger.info("等待全部任务中的子任务结束...")
                    for task_item in task_item_list:
                        if not task_item.is_closing:
                            task_item.cancel()
                            task_item.is_closing = True
                    await asyncio.gather(
                        *(task_item.accomplish.wait() for task_item in task_item_list)
                    )
                    for task_item in task_item_list:
                        logger.info(f"子任务已结束: {task_item.task_info.task_id}")
                    cleanup_tasks = [
                        cleanup for cleanup in self._cleanup_tasks if not cleanup.done()
                    ]
                    if cleanup_tasks:
                        await asyncio.gather(*cleanup_tasks)
                finally:
                    # final_task 可能重新写入 AfterAccomplish，主动停止全部任务时必须丢弃。
                    Config.power_sign = "NoAction"
                    Config.power_delay = 0
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

        # 旧连接的回调还在等待时，新连接的回调不能直接跳过：旧回调随后会随旧连接
        # 一起被取消，启动队列就要拖到下一次连接才跑。这里等它结束后再重新判断。
        while (running_task := self._startup_queue_task) is not None:
            logger.info("启动时任务正在等待运行，等待其结束后再判断")
            await asyncio.wait({running_task})

        if self._startup_queue_started:
            logger.info("启动时任务已触发，跳过重复运行")
            return

        self._startup_queue_task = asyncio.current_task()

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
                is_cycle = bool(queue.Info.CycleEnabled)
                start_mode = "CycleRun" if is_cycle else "AutoProxy"
                task_type = "启动时循环" if is_cycle else "启动时代理"

                StartUpMode = queue.Info.StartUpMode
                if StartUpMode == "Always":
                    logger.info(f"启动时需要运行的队列：{uid}")
                    # 单个队列创建失败（脚本被锁/已在运行）不中断其余启动队列；
                    # 失败时不写 LastStartupTime，下次启动仍可重试。
                    try:
                        await self.add_task(
                            start_mode,
                            str(uid),
                            new_task_info={
                                "queueId": str(uid),
                                "taskName": f"队列 - {queue.Info.Name}",
                                "taskType": task_type,
                            },
                            trigger_source="startup_task",
                        )
                    except (RuntimeError, ValueError) as error:
                        logger.error(f"启动时队列 {uid} 无法创建任务：{error}")
                        continue
                    await queue.update(
                        type(queue).model_validate(
                            {"Data": {"LastStartupTime": datetime.now().astimezone()}}
                        ),
                        check_visibility=False,
                    )

                elif StartUpMode == "DailyFirst":
                    # 检查 DailyFirst 模式是否已在今日运行过
                    if queue.Data.LastStartupTime.strftime("%Y-%m-%d") == curday:
                        logger.info(f"队列 {uid} 已在今日运行过，跳过该次运行")
                        continue

                    logger.info(f"启动时需要运行的队列：{uid}")
                    try:
                        await self.add_task(
                            start_mode,
                            str(uid),
                            new_task_info={
                                "queueId": str(uid),
                                "taskName": f"队列 - {queue.Info.Name}",
                                "taskType": task_type,
                            },
                            trigger_source="startup_task",
                        )
                    except (RuntimeError, ValueError) as error:
                        logger.error(f"启动时队列 {uid} 无法创建任务：{error}")
                        continue
                    await queue.update(
                        type(queue).model_validate(
                            {"Data": {"LastStartupTime": datetime.now().astimezone()}}
                        ),
                        check_visibility=False,
                    )

        finally:
            self._startup_queue_task = None

        logger.success("启动时任务开始运行")


def build_task_result_text(scripts: Iterable) -> str:
    """任务完成页自行统计和筛选，再复用公共文本排版。"""
    script_list = list(scripts)
    if not script_list:
        return "任务未加载"
    blocks: list[str] = []
    for script in script_list:
        if not script.user_list:
            status_text = {
                "等待": "等待运行",
                "跳过": "已跳过",
                "异常": "检查失败",
            }.get(script.status, "未运行")
            blocks.append(f"{script.name}：\n\n    {status_text}")
            continue
        if any(user.push_log for user in script.user_list):
            has_uncompleted = any(
                user.status in ("异常", "等待") for user in script.user_list
            )
            rows: list[UserReportText] = []
            for user in script.user_list:
                entries = []
                for item in user.push_log:
                    entry = (
                        item
                        if isinstance(item, LogEntry)
                        else LogEntry.from_legacy(item)
                    )
                    if entry.log_type != LOG_TYPE_ERROR or has_uncompleted:
                        entries.append(entry)
                mode = getattr(user, "push_log_mode", "逐条")
                if mode == "关闭":
                    details = []
                elif mode == "汇总":
                    details = _notification_report.render_aggregate_push_log(entries)
                else:
                    details = _notification_report.render_scatter_push_log(entries)
                rows.append(
                    UserReportText(
                        name=user.name, result=user.result, detail_lines=tuple(details)
                    )
                )
            user_text = _notification_report.render_user_result_text(rows)
        else:
            user_text = script.result
        indented = "\n".join(
            f"    {line}" if line else line for line in user_text.split("\n")
        )
        if all(
            getattr(user, "maintenance_skipped", False) for user in script.user_list
        ):
            blocks.append(f"{script.name}：\n\n{indented}")
            continue
        completed = sum(user.status == "完成" for user in script.user_list)
        uncompleted = sum(
            user.status != "完成" and not getattr(user, "maintenance_skipped", False)
            for user in script.user_list
        )
        blocks.append(
            f"{script.name}：\n\n"
            f"    已完成用户数：{completed}；未完成用户数：{uncompleted}\n\n{indented}"
        )
    return "\n\n\n".join(blocks)
