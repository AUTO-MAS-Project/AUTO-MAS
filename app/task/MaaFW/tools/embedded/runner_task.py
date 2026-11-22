from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import tempfile
import threading
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any, Callable, Mapping

import psutil

import app.core.notify.formats.maafw as _format_maafw
from app.core import Config, Notify, Publisher
from app.core.notify.task_content import (
    NOTIFY_SCREENSHOT_LIMIT as NOTIFY_SCREENSHOT_LIMIT,
)
from app.core.notify.task_content import (
    prepare_screenshot_images as prepare_screenshot_images,
)
from app.core.notify.task_content import screenshot_entries as screenshot_entries
from app.core.ws import protocol
from app.models.emulator import DeviceBase, DeviceInfo
from app.models.notification import LocalNotice
from app.models.schema import (
    HistoryAttachmentInput,
    HistorySnapshotStatistic,
    HistoryStatus,
    HistoryWrite,
    WSTaskNoticeData,
)
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase
from app.services import execute_script_task
from app.task.client import ClientProcess, client_executable_path, client_launcher_path
from app.task.emulator_core import close_emulator, resolve_host_adb
from app.task.game import game_device_id, game_is_emulator, game_target_id
from app.task.MaaFW.tools.core.controller_win32.service import (
    controller_has_window_rules,
)
from app.task.MaaFW.tools.core.interface.agent_command import MaaFWAgentCommandPlan
from app.task.MaaFW.tools.core.interface.models import (
    MaaFWInterface,
)
from app.task.MaaFW.tools.core.interface.preview import (
    interface_display_name,
)
from app.task.MaaFW.tools.core.interface.service import (
    MaaFWInterfaceService,
)
from app.task.MaaFW.tools.core.native.project_runtime import (
    ARCHITECTURE_MISMATCH_MARKERS,
    describe_project_runtime_architecture_mismatch,
)
from app.task.MaaFW.tools.core.runner.models import (
    MaaFWDeviceConfig,
    MaaFWRunPlan,
    MaaFWRunResult,
    MaaFWSkippedTaskPlan,
)
from app.task.MaaFW.tools.core.runner.plan_transforms import (
    PERIOD_DONE_REASONS,
    RETRY_SKIP_REASON,
    MaaFWPeriodLimits,
    PeriodRecords,
    filter_period_once_tasks,
    parse_period_records,
    record_period_completions,
    skip_tasks_completed_this_run,
)
from app.task.MaaFW.tools.core.runner.run_events import (
    CATEGORY_ENVIRONMENT,
    CATEGORY_GAME_UPDATE_REQUIRED,
    CATEGORY_HOST_ERROR,
    CATEGORY_PRETASK_FAILED,
    CATEGORY_RESOURCE_FAILURE,
    CATEGORY_RUN_TIMEOUT,
    CATEGORY_SCRIPT_STOPPED,
    CATEGORY_SIGNAL,
    CATEGORY_USER_STOPPED,
    STAGE_CLIENT,
    STAGE_PRETASK,
    MaaFWTaskEndEvent,
    MaaFWTaskStartEvent,
)
from app.task.MaaFW.tools.core.runner.run_plan import (
    QUEUE_SKIPPED_TASK_REASON,
    MaaFWRunPlanError,
    resolve_run_selection,
)
from app.task.MaaFW.tools.core.runner.service import MaaFWRunnerService
from app.task.MaaFW.tools.core.runner.task_selection import (
    OFF_DAY_REASON_SUFFIX,
    MaaFWSnapshotExpansion,
    MaaFWSnapshotInspection,
    apply_plan_rules,
    attach_snapshot_findings,
    describe_plan_failure,
    expand_task_snapshot,
    inspect_task_snapshot,
    merge_arranged_queue,
)
from app.task.MaaFW.tools.core.worker_protocol import (
    SIGNAL_SCREENSHOT_KINDS,
)
from app.task.run_flow import (
    PointState,
    begin_attempt,
    game_update_result,
    operation,
    point,
)
from app.utils import IS_WINDOWS, UTC4, ProcessInfo, get_logger, power
from app.utils import display as _utils_display
from app.utils import game_apk as _utils_game_apk
from app.utils.common.game_resolution import (
    UnityGameResolutionOverride,
    parse_resolution_option,
)
from app.utils.common.process.operations import (
    iter_processes,
    managed_process,
    terminate_process,
)
from app.utils.common.process.scope import (
    current_process_scope,
    detached_process_context,
)
from app.utils.common.process.session import desktop_process_target

from .device_config import (
    WIN32_NO_WINDOW_RULES_MESSAGE,
    MaaFWAdbDeviceState,
    adb_ready_timeout,
    build_adb_control_profile,
    build_adb_device_config,
    build_win32_device_config,
    choose_game_package,
    find_controller,
    game_launched_with_emulator,
    list_desktop_window_matches,
    match_controller_windows,
    match_windows_in_session,
    optional_int,
    resolve_adb_path,
    resolve_login_adb_path,
    resolve_window_handle,
)
from .embedded_project import resolve_maafw_project_root
from .flavor import (
    MaaFWLoginRequired,
    MaaFWSelectionContext,
    StartupTask,
    plan_rules,
    resolve_flavor,
    resolve_game_update_hook,
    resolve_login_hook,
    skip_on_retry_entries,
)
from .option_secrets import (
    collect_run_password_values,
    collect_script_password_values,
    log_redaction_notice,
    open_task_snapshot,
    secret_log_variants,
)
from .plan_run import (
    MaaFWPlanRun,
    MaaFWPlanRunEvent,
    MaaFWPlanRunLog,
    MaaFWPlanRunPoint,
    MaaFWPlanRunRecord,
    MaaFWPlanRunRequest,
    MaaFWPlanRunStage,
    MaaFWTaskDeadlineExpired,
)
from .plan_run import MaaFWRunTimeoutError as _MaaFWRunTimeoutError
from .pretask_run import (
    MaaFWPretaskError,
    MaaFWPretaskRunner,
    MaaFWPretaskRunRequest,
    pretasks_need_rerun,
)
from .project_path import (
    is_project_updating,
    release_project_path,
    release_project_path_sync,
    try_reserve_project_path,
)
from .proxy_quota import proxy_times_used_up, proxy_today
from .resource_failure import (
    describe_resource_failure,
)
from .run_record import (
    RUN_RECORD_HISTORY_KEY,
    MaaFWRunRecorder,
    MaaFWTaskRecord,
    format_incident_lines,
)
from .run_report import (
    CATEGORY_REASONS,
    MaaFWAttemptReport,
    failure_summary,
    failure_summary_tasks,
    format_timeline,
    human_reason,
)
from .signal_notice import (
    MAINTENANCE_LAST_STATUS,
    MAINTENANCE_SKIP_MESSAGE,
    SERVER_MAINTENANCE,
    SIGNAL_USER_MESSAGES,
    MaaFWSignalTracker,
)
from .update_credentials import resolve_update_proxy_url

logger = get_logger("MaaFW 插件自动代理")


_RUN_OVERVIEW_LOG_VALUE_LIMIT = 1200
# 启动/附着游戏后定位其窗口的等待秒数
WINDOW_SEARCH_TIMEOUT_SECONDS = 5.0
# Game.WaitTime 填 0 时等游戏窗口出现的上限（秒）
_WINDOW_READY_FALLBACK_SECONDS = 60
# URL 模式打开链接后找游戏进程的最短时限（秒）：Steam 冷启动要先起客户端再拉游戏
_URL_LAUNCH_MIN_TIMEOUT_SECONDS = 60
# 按创建时间认「本次运行期间打开的进程」时的容差（秒），与 ProcessManager.search_process 一致
_PROCESS_CREATE_TIME_TOLERANCE_SECONDS = 2.0
# 兜底关闭进程时 terminate 之后等它自己退出的秒数，到点仍在就 kill
_PROCESS_TERMINATE_GRACE_SECONDS = 3.0

# 环境级失败：解释器自身坏了、依赖没装上。重试只会原样再失败一遍，而每次重试
# 还要重启一遍模拟器/游戏——默认 RunTimesLimit=3，白等好几分钟才告诉用户同一件事。
# 判据取消息标记而不是异常类型：这些错误跨了 runtime_pool 与 runner 两个包，
# 而 runner_task 有意不在模块层导入 runtime_pool（那会让所有请求都付出导入成本）。
_UNRETRYABLE_ENVIRONMENT_MARKERS = (
    "MaaFW runtime Python 自检失败",
    "MaaFW runtime ABI 探测失败",
    "runtime Python identity could not be verified",
    "MaaFW Runner 环境准备失败",
    "MaaFW Runner 环境准备超时",
    # 项目自带的 MaaFramework 与本机架构不符：换哪次尝试都是同一份库。运行前自检一般已
    # 拦下，这里兜住 worker 侧才发现的情况（异常与任务失败两条路都认）。
    *ARCHITECTURE_MISMATCH_MARKERS,
)
# 资源包加载失败（节点重名、JSON 写错、资源目录不在）：资源文件一次尝试到下一次不会自己变，
# 重试只会原样再失败、还要白白重启游戏 / 模拟器。与上面的环境级失败分开说：不是运行环境的事。
_RESOURCE_FAILURE_STOP_MESSAGE = (
    "资源包加载失败，重试也不会有别的结果，已停止本轮（不再重启游戏/模拟器）"
)
# 资源包加载失败后换了载荷、立刻再跑的那一次：（开头那行，之后「上一次（…）」里的称呼）。
# 不计入尝试次数，所以不编号。
_RERUN_AFTER_CLEANUP = (
    "已清理残留，立即重新运行（不计入尝试次数）",
    "清理残留后的重新运行",
)
_RERUN_AFTER_SWITCH = (
    "已换上同项目其他托管在用的版本，立即重新运行（不计入尝试次数）",
    "换版本后的重新运行",
)
# 用户点停止后，等核对 / 清理线程收尾的上限：到点就不等了，预约交给它完成后再放。
_RELEASE_CHECK_CANCEL_GRACE_SECONDS = 30.0
# 哪些 worker 日志 / 原生诊断进界面的几组文案规则在 worker_protocol（forwards_to_ui）：
# worker 发事件时按它定 audience，宿主只对旧格式事件与 stdout 上的原生诊断再用它判。


class _MaaFWGameUpdateRequired(RuntimeError):
    """特调的游戏更新钩子判定客户端要手动更新：本账号本次判失败，不重试。"""


class _MaaFWWorkstationLocked(RuntimeError):
    """电脑锁着屏，要用交互式桌面的控制器跑不了：本账号本次判失败，不重试。"""


# 截图和输入都要落在用户的交互式桌面上的控制器。ADB 不受锁屏影响。
_DESKTOP_CONTROLLER_TYPES = frozenset({"Win32", "Gamepad"})


class MaaFWPluginAutoProxyTask(TaskExecuteBase):
    """MaaFW 插件版 AutoProxy 执行器。"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: Any,
        user_config: Mapping[uuid.UUID, Any],
        emulator_manager: DeviceBase | None,
        project_update_logs: list[str] | None = None,
        signal_tracker: MaaFWSignalTracker | None = None,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.emulator_manager = emulator_manager
        self.project_update_logs = list(project_update_logs or [])
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config = self.user_config[self.cur_user_uid]
        self.project_path = resolve_maafw_project_root(
            str(self.script_info.script_id), self.script_config
        ).resolve()
        self.interface_model: MaaFWInterface | None = None
        self.base_run_plan: MaaFWRunPlan | None = None
        self.run_plan: MaaFWRunPlan | None = None
        # 本账号这一轮第一次借运行环境时 agent 环境算出的 agent 命令计划，重试沿用
        self._worker_agent_plans: tuple[MaaFWAgentCommandPlan, ...] | None = None
        self.cur_user_log: LogRecord | None = None
        # 运行前检查时本账号的日志还没建（特调钩子建计划时的提示就在这时候到），
        # 先攒在这里，prepare() 建好日志时并进去
        self._pending_user_log: list[str] = []
        # 与 MAA 等专项同口径：user_start_time 是本账号这一轮的开始（统计通知用），
        # cur_user_log_started_at 是当前这次尝试的开始（日志记录与 history 文件名用）
        self.user_start_time: datetime | None = None
        self.cur_user_log_started_at: datetime | None = None
        # 每次尝试的结构化结果：worker 回报的人话摘要、失败任务名（推送的时间线与结果行用，
        # 见 run_report）、完成清单（运行记录不可用时的退路）与失败截图。
        self._attempt_reports: list[dict[str, Any]] = []
        # on_crash 记下的异常原文：还没进第一次尝试就崩了时，推送靠它说原因
        self._crash_message: str | None = None
        # 当前这次尝试给用户看的称呼（「第 2 次尝试」「清理残留后的重新运行」），与日志开头
        # 那行同口径：通知的任务详情和失败截图标签用它，不用 _record_attempt 的内部序号——
        # 清理后的重跑不计入尝试次数，内部序号会比日志多 1。
        self._attempt_title: str | None = None
        self._history_temp = tempfile.TemporaryDirectory(prefix="mas-maafw-run-")
        self._history_attachments: dict[int, list[HistoryAttachmentInput]] = {}
        self._history_statuses: dict[int, HistoryStatus] = {}
        self._history_saved = False
        self._user_finalized = False
        self._user_teardown_pending = False
        self._notification_screenshots: list[tuple[str, bytes]] = []
        self.check_result = "-"
        self.curdate = proxy_today()
        self.run_complete = False
        # 本账号运行期间的「保持显示开启」请求，见 main_task。
        self._display_hold: Any = None
        self.opened_emulator = False
        self.opened_game = False
        self.game_process_manager = ClientProcess()
        # 启动游戏前临时改写的 Unity 注册表分辨率，游戏关闭后恢复；None 表示没改
        self.game_resolution_override: UnityGameResolutionOverride | None = None
        # 本轮游戏刚启动的单调时钟时刻，据此算首个任务的最早下发时刻。只在游戏是刚
        # 启动的才记：桌面游戏是窗口出现那一刻（MAS 拉起、或接管时等到窗口冒出来），
        # 模拟器是 MAS 随模拟器把游戏拉到前台那一刻。None 表示游戏早就在跑。
        self.game_started_at: float | None = None
        # URL 模式本轮打开链接的时刻（epoch 秒）：Steam 拉起的游戏不是 MAS 的子进程、还可能
        # 自我重启换 PID，关游戏时据此兜底结束这之后出现的同 exe 进程。None 表示没经链接拉起
        self.game_launched_at: float | None = None
        # URL 模式本次运行**第一次**打开链接的时刻：重试之间不清，只在最终收尾用完清空。
        # Steam 冷启动 / 更新超过等待时限时，游戏会在 MAS 放弃之后才出现，下一轮又按「已在
        # 运行」接管、不算 MAS 开的；收尾按它再扫一遍，MAS 拉起的游戏不会留在外面
        self.url_first_launched_at: float | None = None
        # 本账号这次运行开始的时刻（epoch 秒，第一次尝试的运行前设置之前）：AttachOnly 下由
        # MAS 兜底关闭时只关这之后才出现的进程，收尾做过一次就清空（见 _close_attached_game）
        self.run_started_at: float | None = None
        # 模拟器冷启动游戏时为真：闸门改按「画面有内容 + 客体读盘停下来」放行，上限仍是
        # Game.WaitTime（加载页和动态标题都一直在动，像素判断分不出两者）。桌面路径始终为假。
        self.game_start_disk_quiet = False
        self.project_lock_key: str | None = None
        # 正在跑的那一份计划（plan_run）：停止时经它结束 worker
        self._plan_run: MaaFWPlanRun | None = None
        # 项目的运行前设置（pretask_run）：跨尝试共用一份，停止与清理的状态要跨尝试保留；
        # 释放项目预约前要等它那边的进程确认退出
        self._pretasks = MaaFWPretaskRunner(self._on_plan_run_event)
        # ADB 地址、路径与控制档案：同一次模拟器启动内只解析一次，关模拟器时清（见
        # _close_emulator）
        self._adb_state = MaaFWAdbDeviceState()
        # 随模拟器拉起的游戏包名（空串表示没拉起），交给特调的游戏更新钩子
        self._launched_package_name = ""
        # 游戏更新钩子每个账号每次运行只调一次，重试重新开模拟器时不再查
        self._game_update_checked = False
        # 运行前登录在同一客户端会话内只完成一次；客户端重启后重新验证
        self._login_checked = False
        self._startup_task: StartupTask | None = None
        self.maafw_runtime_pool_root: Path | None = None
        self.maafw_runtime_pool_id: str | None = None
        # 本轮（整个脚本）的信号账：同一资源已确认维护时后续账号直接跳过，收尾时由
        # 管理器按「信号 + 资源」各发一条通知。管理器传入共享的一份。
        self.signal_tracker = signal_tracker or MaaFWSignalTracker()
        # 本账号这次运行命中的信号（worker 回报），决定收尾怎么结算。
        self.run_signal: str | None = None
        # 运行前检查发现同一资源本轮已确认在维护、本账号没启动就跳过。
        self.maintenance_skipped = False
        # 运行前检查时项目预约被占（手动更新、编辑页准备环境 / 导入），本账号没跑成。
        self.project_busy_skipped = False
        # 队列里 interface 已没有的任务名（项目更新改了 name），建计划时填，进任务报告
        self.missing_task_names: list[str] = []
        # 本次运行里各次尝试已完成的任务名（累计，按份数）：重试时剔掉特调声明的
        # skip_on_retry_entries；剔了什么每次重试开头按当前计划的 skippedTasks 写一行
        self._completed_this_run: list[str] = []
        # 已完成过、但在队列里有多份同名的任务名：重试时不剔、全部重跑，开头写一行说明
        self._retry_rerun_duplicates: list[str] = []
        # 本次尝试的原生 ERR 行（plan_run 返回：原生日志副本里的优先，没有就用 worker stdout /
        # stderr 上的）：资源包加载失败时据此说出具体原因（见 resource_failure）。
        self._attempt_native_errors: list[str] = []
        # 资源包加载失败后的发行包核对每个账号每次运行只做一次；清理过就额外再跑一次（不占重试
        # 次数），``_extra_attempts`` 记多出来的几次。
        self._release_check_done = False
        self._extra_attempts = 0
        self._release_check_task: asyncio.Task[Any] | None = None
        # 结构化运行记录（每次尝试一份）：worker 推的阶段 / 任务起止 + 宿主自己的阶段，
        # 进 history 的 data 与推送里单列的原地打转 / 单任务超时。
        self._run_record = MaaFWRunRecorder()

    async def check(self) -> str:
        # 与管理器筛账号同一判据（proxy_quota）：全员到上限时管理器不做运行前更新
        if proxy_times_used_up(self.cur_user_config, self.script_config, self.curdate):
            await self.cur_user_item.set_state(status="跳过")
            return "今日代理次数已达上限，跳过该账号"

        if not await self._try_enter_project_path():
            # 项目被占着没跑成：记「异常」而不是「跳过」。「跳过」不进异常用户，
            # 脚本会记「完成」、汇总是 0 完成 / 0 未完成，「仅失败时」也不推送。
            # 与 manager 层「正在切换版本，已跳过」同一口径。
            await self.cur_user_item.set_state(status="异常")
            self.project_busy_skipped = True
            if is_project_updating(self.project_path):
                return "项目正在更新，本次未运行该账号"
            return (
                "项目正被编辑页的准备运行环境、导入或另一次运行占用，本次未运行该账号"
            )

        keep_reservation = False
        try:
            loop = asyncio.get_running_loop()

            def send_plan_log(message: str) -> None:
                # 运行计划在工作线程里构建，特调钩子的账号日志要回到事件循环线程
                # 再写 script_info.log（与 send_runner_log 同一做法），否则撞上
                # 「no running event loop」，整份计划都算构建失败。
                loop.call_soon_threadsafe(self._append_log, message)

            try:
                # 特调建计划可能提交配置；取消后先等线程结束，不能让它越过 X 锁释放。
                build_task = asyncio.create_task(
                    asyncio.to_thread(self._load_run_state_for_check, send_plan_log)
                )
                try:
                    state = await asyncio.shield(build_task)
                except asyncio.CancelledError:
                    while not build_task.done():
                        try:
                            await asyncio.shield(build_task)
                        except asyncio.CancelledError:
                            continue
                        except Exception:
                            break
                    with suppress(Exception):
                        build_task.result()
                    raise
                (
                    self.interface_model,
                    self.base_run_plan,
                    self.run_plan,
                    game_path_error,
                ) = state
                # 计划重建了，agent 命令计划下次借环境时按新的声明重算
                self._worker_agent_plans = None
            except Exception as exc:
                await self.cur_user_item.set_state(status="异常")
                return f"无法构建 MaaFW 运行计划，请检查项目和任务配置: {exc}"

            if not self.run_plan.tasks:
                await self.cur_user_item.set_state(status="跳过")
                return _period_all_done_message(self.run_plan)

            # 本轮前面的用户已经撞上同一资源的停服维护：不再拉起游戏 / 模拟器，
            # 并进那条维护通知的账号列表。代理次数、上次状态都不动。
            maintenance = self.signal_tracker.maintenance(self.run_plan.resourceName)
            if maintenance is not None:
                maintenance.add_user(str(self.cur_user_uid), self.cur_user_item.name)
                await self.cur_user_item.set_state(status="跳过")
                self.maintenance_skipped = True
                return MAINTENANCE_SKIP_MESSAGE

            if self.run_plan.controllerType == "Adb":
                emulator_id = game_target_id(self.script_config)
                emulator_index = game_device_id(self.script_config)
                if emulator_id == "-" or emulator_index in ("", "-"):
                    await self.cur_user_item.set_state(status="异常")
                    return (
                        "当前 MaaFW controller 需要 ADB，请在托管管理页选择模拟器和实例"
                    )
            elif game_path_error is not None:
                await self.cur_user_item.set_state(status="异常")
                return game_path_error

            # 项目自带的 MaaFramework 与本机架构不符时 worker 里必然加载失败；在这里先说清楚
            # （还没拉起游戏 / 模拟器），并按导入来源 Info.Path 判断重新导入能不能解决。
            architecture_error = await asyncio.to_thread(
                self._describe_runtime_architecture_mismatch
            )
            if architecture_error:
                await self.cur_user_item.set_state(status="异常")
                return architecture_error

            keep_reservation = True
            return "Pass"
        finally:
            if not keep_reservation:
                await self._release_project_path()

    def _describe_runtime_architecture_mismatch(self) -> str | None:
        source = str(self.script_config.Info.Path or "").strip()
        return describe_project_runtime_architecture_mismatch(
            self.project_path, source_path=Path(source) if source else None
        )

    async def prepare(self) -> None:
        start_time = datetime.now().astimezone()
        self.user_start_time = start_time
        self.cur_user_log_started_at = start_time
        self.cur_user_log = LogRecord()
        self.cur_user_log = await self.cur_user_item.add_log_record(
            start_time, self.cur_user_log
        )
        await self.cur_user_log.append_content(
            *self.project_update_logs, *self._pending_user_log
        )
        content = self.cur_user_log.content
        self._pending_user_log.clear()
        if content:
            await self.script_info.set_log("".join(content))

    async def main_task(self) -> None:
        self.curdate = proxy_today()
        self.check_result = await self.check()
        if self.check_result != "Pass":
            # 也记一行后端日志：否则只有 WS 通知，事后日志里只见「任务开始」紧接「任务结束」。
            # 「异常」是失败，按 WARNING 记；「跳过」（次数用完、周期已完成）是正常分支。
            (logger.warning if self.cur_user_item.status == "异常" else logger.info)(
                f"MFW 用户运行前检查未通过（{self.cur_user_item.name}，{self.cur_user_item.status}）：{self.check_result}"
            )
            # 项目被占用不逐个弹窗：所有账号撞的是同一件事，10 个账号就弹 10 次、响 10 次
            # 提示音。与 embedded_manager._check 那条「整个脚本一句话跳过，别让每个账号在
            # runner_task 里各报一遍」同一用意；「异常」状态、本账号日志与统计
            # 照常记（见下面与 final_task），汇总与「仅失败时」推送照常带上它。
            if self.cur_user_item.status == "异常" and not self.project_busy_skipped:
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error",
                        message=(
                            f"账号 {self.cur_user_item.name} 检查未通过: "
                            f"{self.check_result}"
                        ),
                    ),
                )
            if self.maintenance_skipped or self.project_busy_skipped:
                # 同一资源已确认在维护、或项目被占用没跑成：记一份本账号的日志，让代理
                # 结果汇总与统计信息写明原因（其他跳过原因照旧不记），未派发用户不建历史。
                # 前面拿到的运行前更新日志也随这份内存日志保留。
                # 窗口与行号由 _append_log 按本账号日志算好（前面可能还有更新日志与
                # 检查阶段的特调提示），不再改写成只剩这一行
                await self.prepare()
                self._append_log(self.check_result)
                if self.cur_user_log is not None:
                    await self.cur_user_log.set_state(status=self.check_result)
            else:
                # 没有本账号的日志：窗口只剩检查结果这一行，行号回到 1，
                # 不接着上一个账号的行号往下数
                await self.script_info.set_log(self.check_result)
            return

        await self._mark_run_started()
        await self.prepare()
        await self.cur_user_item.set_state(status="运行")
        # AttachOnly 兜底关闭的分界：之后才出现的游戏 / 启动器才算本次运行打开的
        self.run_started_at = time.time()
        logger.info(f"开始代理 MaaFW 账号: {self.cur_user_uid}")
        if self.run_plan is not None:
            selected_preset = str(
                self.cur_user_config.Task.SelectedPreset or ""
            ).strip()
            self._append_log(
                _format_run_overview_log(
                    self.run_plan,
                    selected_preset=selected_preset,
                )
            )
            for warning in self.run_plan.warnings:
                self._append_log(f"MaaFW 运行计划提示: {warning}")

        # Windows 到点熄屏后，鹰角启动器这类网页界面不出画面，项目的运行前设置在里面什么都
        # 认不出（2026-10-17/18 生产 MaaEnd「🚀启动游戏（PC）」两晚失败，亮屏 5 秒即过）。
        # 整个账号运行期间保持显示开启，屏已熄就先叫醒；收尾时撤销，final_task 再兜一次。
        self._ensure_display_hold()
        self._user_teardown_pending = True
        # 执行任务前脚本（每账号仅一次，重试不重复跑）。
        # 用户后脚本和清理在受保护的 final_task 中配对执行。
        if self.cur_user_config.Info.IfScriptBeforeTask:
            await execute_script_task(
                self.cur_user_config.Info.ScriptBeforeTask, "脚本前任务"
            )

        # 上一次尝试的失败摘要与是否重启过客户端：新一次另起日志后界面从头显示，
        # 不在开头写一句，用户只看到「尝试次数: 2/3」，不知道为什么重来。
        previous_failure: str | None = None
        previous_restarted = False
        # 项目的运行前设置（interface pretask，如 MaaEnd 的「启动游戏（PC）」）放进每次
        # 尝试里：它自己失败要能重试；游戏被本轮的「关闭游戏」任务或重启关掉后，重试也要
        # 靠它重新拉起，否则第 2、3 次在找窗口那一步当场失败。
        pretasks_done = False
        # 上一次失败后 MAS 自己起的游戏 / 模拟器是否已关掉（关的时候报错也算：两个关闭
        # 函数不论成败都清掉 opened_*，下一轮会重新拉起），这时运行前设置要重跑
        client_reset = False
        # 资源包加载失败后换了载荷、立刻再跑的那一次不计入尝试次数：日志里不给它编号，之后的
        # 序号扣掉它，分母一律是用户配的 RunTimesLimit（用户配 3 次就是「x/3」）。
        # ``index + 1`` 仍是内部序号（_record_attempt、_reset_client_for_retry 用）。
        rerun_note: tuple[str, str] | None = None
        previous_label = ""
        index = -1
        while True:
            # 不用 range：资源包加载失败后清理过载荷时额外再跑一次（_extra_attempts），上限会变。
            index += 1
            if index >= self._attempt_limit() or self.run_complete:
                break
            begin_attempt(self, index + 1)

            # 每次尝试单独一份日志（界面与 history 都分开）：第一次沿用 prepare()
            # 建的那份，开头有更新检查与运行总览；之后每次另起。
            if index > 0:
                await self._start_attempt_log()

            if rerun_note is not None:
                header, current_label = rerun_note
                self._append_log(f"账号 {self.cur_user_item.name} - {header}")
                rerun_note = None
                self._attempt_title = current_label
            else:
                ordinal = index + 1 - self._extra_attempts
                self._append_log(
                    f"账号 {self.cur_user_item.name} - 尝试次数: "
                    f"{ordinal}/{self.script_config.Run.RunTimesLimit}"
                )
                current_label = f"第 {ordinal} 次"
                self._attempt_title = f"{current_label}尝试"
            if index > 0 and previous_failure:
                self._append_log(
                    f"上一次（{previous_label}）：{previous_failure}"
                    + ("，已重启游戏/模拟器" if previous_restarted else "")
                )
            previous_label = current_label
            self._begin_run_record_attempt(index + 1)

            try:
                if index > 0:
                    self._log_retry_skipped_tasks()
                if self.run_plan is None or self.interface_model is None:
                    raise RuntimeError("MaaFW 运行计划尚未初始化")
                self._ensure_display_hold()
                # 放在运行前设置之前：锁屏时启动器、游戏照样能被拉起来，但截图和输入用不了，
                # 进了重试还会白白重启游戏。
                await self._ensure_workstation_unlocked()
                if not pretasks_done or await self._pretasks_need_rerun(client_reset):
                    # 先清标记：重跑到一半失败时，下一轮不能因为窗口已被拉起就跳过
                    pretasks_done = False
                    # 计划里没有运行前设置时不记这一段（getattr：记录是旁路，不多读计划）
                    with self._run_record.stage(
                        STAGE_PRETASK,
                        enabled=bool(getattr(self.run_plan, "pretasks", None)),
                    ):
                        await self._run_pretasks()
                    pretasks_done = True
                with self._run_record.stage(STAGE_CLIENT):
                    await self._ensure_desktop_game_started()
                    device_config = await self._build_device_config(
                        self.run_plan,
                        self.interface_model,
                    )
                result = await self._run_maafw(device_config)
            except _MaaFWGameUpdateRequired as exc:
                # 游戏客户端要手动更新：重试多少次都一样，本账号本次直接判失败。
                # 说明已由 _ensure_game_updated 写进运行日志，这里不再重复。
                message = str(exc)
                self._record_attempt(
                    index + 1, [], message, category=CATEGORY_GAME_UPDATE_REQUIRED
                )
                if self.cur_user_log is not None:
                    await self.cur_user_log.set_state(status=message)
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(level="error", message=message),
                )
                with suppress(Exception):
                    await Notify.send_notice(
                        LocalNotice(
                            title="游戏需要手动更新！",
                            message=message,
                            ticker=f"{self.cur_user_item.name}的游戏需要手动更新",
                            duration_seconds=3,
                        )
                    )
                break
            except Exception as exc:
                locked = isinstance(exc, _MaaFWWorkstationLocked)
                message = (
                    str(exc)
                    if isinstance(
                        exc,
                        (
                            MaaFWPretaskError,
                            MaaFWLoginRequired,
                            _MaaFWWorkstationLocked,
                        ),
                    )
                    else f"MaaFW 运行异常: {exc}"
                )
                self._append_log(message, warning=True)
                unretryable = locked or _is_unretryable_failure(message)
                self._record_attempt(
                    index + 1,
                    [],
                    message,
                    # 宿主自己抛的多是 MAS 写的人话（「当前 controller 需要 ADB，请在托管管理页
                    # 选择模拟器」「Path未配置」），推送照它说；带的排障片段由 run_report 滤掉。
                    # 整次运行超时有固定说法，不用异常原文
                    user_message=(
                        None if isinstance(exc, _MaaFWRunTimeoutError) else str(exc)
                    ),
                    category=(
                        CATEGORY_PRETASK_FAILED
                        if isinstance(exc, MaaFWPretaskError)
                        else CATEGORY_RUN_TIMEOUT
                        if isinstance(exc, _MaaFWRunTimeoutError)
                        else CATEGORY_ENVIRONMENT
                        if unretryable
                        else CATEGORY_HOST_ERROR
                    ),
                )
                if unretryable and not locked:
                    # 锁屏的说明自带「不重试」，不再重复一句
                    self._append_log(
                        "运行环境不可用，重试也不会有别的结果，已停止本轮",
                        warning=True,
                    )
                if self.cur_user_log is not None:
                    await self.cur_user_log.set_state(status=message)
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(level="error", message=message),
                )
                if unretryable:
                    break
                previous_failure = message
                (
                    previous_restarted,
                    client_reset,
                ) = await self._reset_client_for_retry(index + 1)
                continue

            await self._mark_period_tasks_completed(result.completedTasks)
            if result.signal is not None:
                # 项目声明的信号节点命中：停服维护 = 本次跳过，需要更新客户端 = 失败；
                # 两种都是重试多少次都一样，不重启游戏 / 模拟器，直接收尾。
                point(
                    self,
                    "run",
                    state="skipped"
                    if result.signal == SERVER_MAINTENANCE
                    else "failed",
                )
                await self._finish_on_signal(index + 1, result)
                break
            point(self, "run", state="succeeded" if result.success else "failed")
            if result.success:
                self.run_complete = True
                if self.cur_user_log is not None:
                    await self.cur_user_log.set_state(status="Success!")
                completed_task_labels = _format_completed_task_labels(
                    self.run_plan,
                    result.completedTasks,
                )
                self._append_log("MaaFW 任务完成: " + ", ".join(completed_task_labels))
                self._record_attempt(index + 1, completed_task_labels, None)
            else:
                if result.resourceFailure is not None:
                    # 资源包没能加载：原因只在原生 ERR 行里，换成一句人话（取不到才保留
                    # 「详见 .maafw.log」）。
                    message = await asyncio.to_thread(
                        describe_resource_failure,
                        result.resourceFailure.kind,
                        result.resourceFailure.path,
                        self._attempt_native_errors,
                        project_root=self.project_path,
                        secrets=self._secret_log_variants(),
                    )
                elif result.timedOut:
                    message = self._timed_out_user_summary(result)
                else:
                    message = _failed_task_user_summary(result, self.run_plan)
                    retry_skipped = (
                        sum(
                            1
                            for skipped in self.run_plan.skippedTasks
                            if skipped.reason == _RETRY_SKIP_REASON
                        )
                        if self.run_plan is not None
                        else 0
                    )
                    total = (
                        len(self.run_plan.tasks) + retry_skipped
                        if self.run_plan is not None
                        else 0
                    )
                    done = len(result.completedTasks) + retry_skipped
                    if total > 1 and done > 0:
                        message += f"（共 {total} 个任务，完成 {done} 个）"
                if self.cur_user_log is not None:
                    await self.cur_user_log.set_state(status=message)
                self._append_log(message, warning=True)
                self._record_attempt(
                    index + 1,
                    _format_completed_task_labels(self.run_plan, result.completedTasks),
                    message,
                    user_message=result.userMessage,
                    failed_task=result.failedTask,
                    screenshots=[
                        (
                            _format_completed_task_labels(self.run_plan, [shot.task])[
                                0
                            ],
                            Path(shot.path),
                        )
                        for shot in result.failureScreenshots
                    ],
                    category=_result_failure_category(result),
                )
                if result.resourceFailure is not None:
                    # 不重启游戏 / 模拟器：资源加载失败不改变游戏状态，换载荷也不碰它们。
                    # 只有刚把载荷里的旧版本残留清掉、视图换过时立刻再跑一次（不占重试次数）。
                    rerun_note = await self._recover_resource_failure(
                        result.resourceFailure.kind
                    )
                    if rerun_note is not None:
                        self._extra_attempts += 1
                        previous_failure = message
                        previous_restarted = False
                        client_reset = False
                        continue
                    break
                if _is_unretryable_failure(result.errorMessage or ""):
                    # worker 在任务里报的环境级失败（如原生库架构不符）：每轮都一样，
                    # 不再为它起停模拟器 / 游戏重试。
                    self._append_log(
                        "运行环境不可用，重试也不会有别的结果，已停止本轮",
                        warning=True,
                    )
                    break
                await self._refresh_run_plan_after_period_update(result.completedTasks)
                if self.run_plan is not None and not self.run_plan.tasks:
                    self.run_complete = True
                    # 计划被重试跳过剔空的，不能说成「周期任务」
                    self._append_log(
                        "MaaFW 剩余任务都已完成，停止本轮重试"
                        if _retry_skipped_tasks(self.run_plan)
                        else "MaaFW 剩余周期任务已完成，停止本轮重试"
                    )
                else:
                    previous_failure = message
                    (
                        previous_restarted,
                        client_reset,
                    ) = await self._reset_client_for_retry(index + 1)

    async def final_task(self) -> None:
        if self._user_finalized:
            return
        self._user_finalized = True
        self.history.begin_user_history_capture(
            self.script_info,
            self.cur_user_item,
            failed=self.check_result == "Pass"
            and not self.run_complete
            and self.run_signal != SERVER_MAINTENANCE
            and not self.stopped_manually,
        )
        try:
            await self._finalize_user()
        except Exception as error:
            if not self._history_saved:
                with suppress(Exception):
                    await self.on_crash(error)
            raise
        finally:
            try:
                if not self._history_saved:
                    await self._save_user_history()
            finally:
                try:
                    if self.stopped_manually:
                        # 即使设备关闭或统计中断，也必须把预约交给安全释放检查。
                        await self._release_project_path()
                finally:
                    await asyncio.to_thread(self._history_temp.cleanup)

    async def _finalize_user(self) -> None:
        if self._user_teardown_pending:
            self._user_teardown_pending = False
            # 后脚本可能仍需使用模拟器，必须先完成，再关闭资源与保存历史。
            if self.cur_user_config.Info.IfScriptAfterTask:
                await execute_script_task(
                    self.cur_user_config.Info.ScriptAfterTask, "脚本后任务"
                )
        self._release_display_hold()
        await self._shutdown_runner()
        if self.check_result != "Pass":
            if self.maintenance_skipped:
                # 维护连带跳过：同样是跳过不是失败，代理次数不动；上次状态
                # 与统计信息都写明原因。
                self.cur_user_config.Data.LastProxyStatus = MAINTENANCE_LAST_STATUS
                await self.cur_user_config.commit()
                await self._save_user_history()
                await self._push_user_statistics()
            elif self.project_busy_skipped:
                # 没跑成：统计信息写明原因；代理次数与上次状态不动。
                await self._save_user_history()
                await self._push_user_statistics()
            await self._release_project_path()
            return

        await self._close_emulator()
        await self._close_game_after_run(failed=not self.run_complete)
        if self.run_complete:
            if (
                self.cur_user_config.Data.ProxyTimes == 0
                and self.cur_user_config.Info.RemainedDay != -1
            ):
                self.cur_user_config.Info.RemainedDay = (
                    self.cur_user_config.Info.RemainedDay - 1
                )
                await self.cur_user_config.commit()
            self.cur_user_config.Data.ProxyTimes = (
                self.cur_user_config.Data.ProxyTimes + 1
            )
            await self.cur_user_config.commit()
            self.cur_user_config.Data.LastProxyStatus = "成功"
            await self.cur_user_config.commit()
            await self.cur_user_item.set_state(status="完成")
        elif self.run_signal == SERVER_MAINTENANCE:
            # 维护是跳过不是失败：代理次数、剩余天数不动，下次定时照常再跑
            self.cur_user_config.Data.LastProxyStatus = MAINTENANCE_LAST_STATUS
            await self.cur_user_config.commit()
            await self.cur_user_item.set_state(status="跳过")
        else:
            self.cur_user_config.Data.LastProxyStatus = "失败"
            await self.cur_user_config.commit()
            if self.cur_user_item.status == "运行":
                await self.cur_user_item.set_state(status="异常")

        await self._save_user_history()
        if self.run_complete:
            await self._send_success_notify()
        await self._push_user_statistics()
        await self._release_project_path()

    async def on_crash(self, e: Exception) -> None:
        await self.cur_user_item.set_state(status="异常")
        logger.exception(f"MaaFW 内置运行任务出现异常: {e}")
        # 还没进第一次尝试就崩了（prepare、脚本前任务出错）时推送靠它说原因
        self._crash_message = str(e)
        if self.cur_user_log is not None:
            await self.cur_user_log.set_state(status=f"MaaFW 内置运行任务出现异常: {e}")
            if self.cur_user_log_started_at is not None:
                self._history_statuses[id(self.cur_user_log)] = "error"
        try:
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="error",
                    message=f"MaaFW 内置运行任务出现异常: {e}",
                ),
            )
        except Exception:
            pass
        await self._shutdown_runner()
        await self._close_emulator()
        await self._close_game_after_run(failed=True)
        await self._release_project_path()

    def _game_launch_mode(self) -> str:
        """``Game.LaunchMode``：DirectExe / URL / AttachOnly。

        配置激活后一定有默认值，这里的兜底只是防御性的。
        """

        return str(self.script_config.Game.LaunchMode or "DirectExe").strip()

    def _mas_manages_game_launch(self) -> bool:
        """MAS 是否负责启动/关闭游戏。

        三种模式：DirectExe（默认；MAS 按 exe 启动，结束后由 MAS 关闭）、URL（MAS 打开
        链接拉起游戏，游戏 exe 只用来认出它，结束后同样由 MAS 关闭）与 AttachOnly（脚本或
        用户自己启动，MAS 只接管窗口；结束后关不关看 ``Game.CloseMode``，见
        ``_close_attached_game``）。
        """

        return self._game_launch_mode() != "AttachOnly"

    def _resolve_game_launch_path(self) -> Path | None:
        """游戏 exe：DirectExe 下 MAS 启动它，URL / AttachOnly 下只用来认出游戏。"""

        raw = str(client_executable_path(self.script_config) or "").strip()
        return Path(raw) if raw else None

    def _resolve_launcher_path(self) -> Path | None:
        """AttachOnly 下可选的启动器 exe，MAS 兜底关闭时一并关它。"""

        return client_launcher_path(self.script_config)

    def _describe_game_launch_config_error(self) -> str | None:
        """MAS 负责启动游戏时缺了什么配置；不缺返回 None。会读盘，调用方放在工作线程里。"""

        mode = self._game_launch_mode()
        game_path = self._resolve_game_launch_path()
        if mode == "URL":
            if not str(self.script_config.Game.URL or "").strip():
                return "启动方式为通过链接启动，请在托管管理页填写启动链接"
            if game_path is None or not game_path.is_file():
                return "启动方式为通过链接启动，请在托管管理页选择游戏 exe（用来识别和关闭游戏）"
            return None
        if game_path is None or not game_path.is_file():
            return "当前 MaaFW controller 需要由 MAS 启动游戏，请在托管管理页选择实际游戏 exe"
        return None

    def _load_run_state_for_check(
        self,
        send_log: Callable[[str], None] | None = None,
    ) -> tuple[MaaFWInterface, MaaFWRunPlan, MaaFWRunPlan, str | None]:
        interface_model = MaaFWInterfaceService().load(self.project_path)
        base_run_plan = self._build_run_plan(interface_model, send_log=send_log)
        run_plan = self._filter_period_once_tasks(base_run_plan)

        game_path_error: str | None = None
        if (
            desktop_process_target.get() is not None
            and run_plan.controllerType != "Win32"
        ):
            raise ValueError("MaaFW 桌面分身仅支持 Win32 控制器")
        if (
            run_plan.tasks
            and run_plan.controllerType == "Win32"
            and (not optional_int(self.script_config.Device.HWnd))
            and (
                not controller_has_window_rules(
                    find_controller(interface_model, run_plan.controllerName)
                )
            )
        ):
            # 控制器一条窗口匹配规则都没写，又没指定句柄：以前会随便抓桌面上第一个窗口。
            # 在拉起游戏之前就报。
            game_path_error = WIN32_NO_WINDOW_RULES_MESSAGE
        elif (
            run_plan.tasks
            and run_plan.controllerType == "Win32"
            and self._mas_manages_game_launch()
        ):
            game_path_error = self._describe_game_launch_config_error()
        return interface_model, base_run_plan, run_plan, game_path_error

    def _build_run_plan(
        self,
        interface_model: MaaFWInterface,
        *,
        send_log: Callable[[str], None] | None = None,
    ) -> MaaFWRunPlan:
        # 不看 Info.IfQuickConfig：MaaFW 没有可退回的原生配置，账号页上配的任务队列就是
        # 唯一的任务来源。开关在界面上已经不提供，这里若还读它，被隐藏的旧值会让页面上
        # 能改、运行时却不生效。
        task_snapshot = _load_json_dict(self.cur_user_config.Task.TaskSnapshot)
        selected_preset = str(self.cur_user_config.Task.SelectedPreset or "").strip()
        controller_name, resource_name = self._select_run_selection(interface_model)
        effective_preset = (
            selected_preset if selected_preset and not task_snapshot else None
        )
        # 有规则的脚本类型（脚本配置类声明了 FLAVOR）：先展开任务快照（剔掉不可选任务与今天
        # 不在运行日的实例），交给钩子排队列（补首尾任务、切号绑定之类），再按排好的队列建计划。
        # 通用 MaaFW 没有钩子、规则表为空，仍按快照直接建计划，行为不变。
        flavor = resolve_flavor(self.script_config)
        rules = plan_rules(flavor)
        # 托管级键位（Game.Hotkeys）：坏 JSON / 不是对象当空，字段级的校验在建计划时做。
        script_hotkeys = _load_script_hotkeys(self.script_config.Game.Hotkeys)
        # 本方法在工作线程里跑：没给线程安全的回调就只进后端日志。
        log = send_log if send_log is not None else logger.info
        inspection: MaaFWSnapshotInspection | None = None
        expansion: MaaFWSnapshotExpansion | None = None
        try:
            # 密码字段（PI v2.10.0）在配置里是密文，只在这份内存副本里解开交给计划；
            # 账号配置本身不动，运行后的整表写回也就写不出明文。
            task_snapshot = open_task_snapshot(task_snapshot, interface_model)
            # 先只看快照：项目更新改了任务 name 后，队列里的旧 id 在归一化时就被滤掉了，改了
            # case 名的选项值会被静默换回默认值，建完计划分别记成跳过与提示。运行日按本机今天
            # 的星期判（与队列「执行日期」同口径），只在开跑建计划时判这一次：结果固化在
            # base_run_plan 里，重试从它重建、不再重判，跨零点重试也不翻。
            iso_weekday = datetime.now().isoweekday()
            inspection = inspect_task_snapshot(
                self.project_path,
                interface_model,
                task_snapshot,
                iso_weekday=iso_weekday,
            )
            self.missing_task_names = list(dict.fromkeys(inspection.missing_task_names))
            if flavor is None:
                # 今天不跑的实例与红灯一样在建计划之前排除，不校验它们的选项（坏配置不挡整轮）
                plan = MaaFWRunnerService().build_plan(
                    self.project_path,
                    interface_model,
                    controller_name=controller_name,
                    resource_name=resource_name,
                    selected_preset=effective_preset,
                    task_snapshot=task_snapshot or None,
                    script_hotkeys=script_hotkeys,
                    excluded_task_reasons=inspection.off_day_reasons(),
                )
            else:
                expansion = expand_task_snapshot(
                    self.project_path,
                    interface_model,
                    task_snapshot=task_snapshot,
                    selected_preset=effective_preset,
                    iso_weekday=iso_weekday,
                    rules=rules,
                    inspection=inspection,
                )
                for line in expansion.notices:
                    log(line)
                # 钩子看到的是今天真要跑的队列（剔空了就不补首尾）。红灯与今天不跑的实例经上下文
                # 交给钩子，钩子另读账号配置自动补任务时跳过它们，不必自己再解析快照、再判星期。
                arranged_ids, arranged_options = flavor.decorate_selection(
                    interface_model,
                    list(expansion.task_ids),
                    dict(expansion.task_options),
                    context=MaaFWSelectionContext(
                        script_config=self.script_config,
                        user_config=self.cur_user_config,
                        resource_name=resource_name,
                        excluded_task_ids=expansion.excluded_task_ids,
                        log=log,
                    ),
                )
                # 钩子按固定规则补回的同一实例照常跑、不受运行日影响；其余停跑日实例由核心在
                # 建计划前排除、记成跳过（不校验选项），全被排除时计划为空。
                queue = merge_arranged_queue(expansion, arranged_ids, arranged_options)
                plan = MaaFWRunnerService().build_plan(
                    self.project_path,
                    interface_model,
                    controller_name=controller_name,
                    resource_name=resource_name,
                    # 已选任务拆成 task_ids 交给核心；仍带上原始快照，让核心把用户显式设为
                    # 跳过的实例写进 skippedTasks，并从它取从密文解出来的字段（下发失败的提示
                    # 按密码处理）。
                    task_snapshot=task_snapshot,
                    task_ids=queue.task_ids,
                    task_options=queue.task_options,
                    global_options=dict(expansion.global_options),
                    script_hotkeys=script_hotkeys,
                    no_default_fallback_inputs=rules.no_default_fallback_inputs,
                    excluded_task_reasons=queue.excluded_task_reasons,
                )
            return attach_snapshot_findings(apply_plan_rules(plan, rules), inspection)
        except Exception as exc:
            raise MaaFWRunPlanError(
                describe_plan_failure(str(exc), inspection, expansion)
            ) from exc

    def _select_run_selection(
        self, interface_model: MaaFWInterface
    ) -> tuple[str | None, str | None]:
        """``(交给建计划的 controller 名, 实际生效的 resource 名)``，口径见 ``resolve_run_selection``。

        用户在托管页显式选的 controller 优先。这里曾把「配了模拟器」排在前面，于是先在 ADB
        模式下选过模拟器、之后把控制方式改成 Win32 的用户会被静默改回 ADB：Emulator.Id 还留着
        旧值（Win32 分支下模拟器下拉被隐藏，用户没有入口清它），运行时回落到第一个 Adb
        controller，按 Win32 编排的任务被 run_plan 过滤掉，或者直接报「当前 controller/resource
        下没有可执行任务」。特调在保存与启动期整理用户配置时用同一个函数判资源。
        """

        return resolve_run_selection(
            interface_model,
            configured_controller=str(self.script_config.Info.Controller or ""),
            emulator_selected=game_is_emulator(self.script_config),
            configured_resource=str(self.script_config.Info.Resource or ""),
        )

    async def _build_device_config(
        self,
        plan: MaaFWRunPlan,
        interface_model: MaaFWInterface,
    ) -> MaaFWDeviceConfig:
        """取脚本配置与模拟器入口，交给 ``device_config`` 换算成设备配置。

        这里只做三件事：取配置原值、管 ADB 缓存（``_adb_state``）、在中间调游戏更新与
        运行前登录钩子。
        """
        if plan.controllerType == "Adb":
            state = self._adb_state
            address, device_info = await self._resolve_adb_address()
            if state.adb_path is None:
                state.adb_path = await resolve_adb_path(
                    self.emulator_manager,
                    game_device_id(self.script_config),
                    configured_path=self.script_config.Device.AdbPath,
                    device_info=device_info,
                    log=self._append_log,
                )
            adb_path = await resolve_login_adb_path(
                address,
                state.adb_path,
                ask_toolkit=(
                    state.adb_path is None
                    and bool(address)
                    and bool(resolve_login_hook(self.script_config))
                ),
                log=self._append_log,
            )
            await self._ensure_game_updated(address, adb_path)
            await self._ensure_logged_in(address, adb_path)
            if state.profile is None:
                state.profile = await build_adb_control_profile(
                    self.emulator_manager,
                    target_id=game_target_id(self.script_config),
                    device_uid=game_device_id(self.script_config),
                    log=self._append_log,
                )
            return build_adb_device_config(
                address=address,
                adb_path=adb_path,
                profile=state.profile,
                device_info=device_info,
                configured_screencap_methods=self.script_config.Device.AdbScreencapMethods,
                configured_input_methods=self.script_config.Device.AdbInputMethods,
                ready_timeout=adb_ready_timeout(self.emulator_manager),
            )

        if plan.controllerType == "Win32":
            await self._ensure_logged_in("", None)
            controller = find_controller(interface_model, plan.controllerName)
            device = self.script_config.Device
            hwnd = await resolve_window_handle(
                controller, device.HWnd, log=self._append_log
            )
            return build_win32_device_config(
                controller,
                hwnd,
                configured_screencap_method=device.Win32ScreencapMethod,
                configured_mouse_method=device.Win32MouseMethod,
                configured_keyboard_method=device.Win32KeyboardMethod,
                log=self._append_log,
            )

        raise RuntimeError(f"当前仅支持 Adb/Win32 controller: {plan.controllerType}")

    async def _resolve_adb_address(self) -> tuple[str, DeviceInfo | None]:
        state = self._adb_state
        if state.address is not None:
            return state.address, state.device_info
        if self.emulator_manager is None:
            raise RuntimeError("当前 controller 需要 ADB，请在托管管理页选择模拟器")

        emulator_index = game_device_id(self.script_config)
        if emulator_index in ("", "-"):
            raise RuntimeError("当前 controller 需要 ADB，请在托管管理页选择模拟器实例")

        package_name = await choose_game_package(
            self.script_config.Game.PackageName, self.run_plan, log=self._append_log
        )
        self._launched_package_name = package_name
        self._append_log(f"正在启动模拟器: {emulator_index}")
        self.opened_emulator = True
        device_info = await self.emulator_manager.open(
            emulator_index, package_name, **self._mod_avd_open_kwargs()
        )
        # 只有冷启动才等（判据见 game_launched_with_emulator），首任务闸门按这里记的
        # 时刻与读盘判据算（task_start_gate）
        if game_launched_with_emulator(device_info):
            point(self, "start_game", state="succeeded", key="launched")
            self.game_started_at = time.monotonic()
            self.game_start_disk_quiet = True
            self._append_log(f"已随模拟器启动游戏: {package_name}")
        else:
            self.game_started_at = None
            self.game_start_disk_quiet = False
        if Config.setting.Function.IfSilence:
            with suppress(Exception):
                await self.emulator_manager.setVisible(emulator_index, False)
        if not device_info.adb_address or device_info.adb_address == "Unknown":
            raise RuntimeError("模拟器未返回可用 ADB 地址")

        state.address = device_info.adb_address
        state.device_info = device_info
        self._append_log(f"模拟器启动完成，ADB 地址: {device_info.adb_address}")
        return device_info.adb_address, device_info

    async def _ensure_game_updated(self, address: str, adb_path: str | None) -> None:
        """模拟器启动后、第一个任务下发前，调特调的游戏更新钩子（契约见 flavor.py）。

        每个账号每次运行只调一次。钩子判定要手动更新时抛 ``_MaaFWGameUpdateRequired``，
        由 main_task 判失败且不重试；钩子自己出错只记警告，照常运行。
        """

        if self._game_update_checked:
            return
        self._game_update_checked = True
        mode = str(self.script_config.Run.GameUpdateMode or "Off")
        hook = resolve_game_update_hook(self.script_config)
        if mode == "Off" or hook is None or self.run_plan is None:
            return

        async def report(text: str) -> None:
            self._append_log(text)

        self._append_log("正在检查游戏客户端更新")
        point(self, "game_update")
        try:
            # ModAVD 实例：钩子在宿主进程里调 adb（game_apk），改走 ``modavd adb``（ModAVD 的私有 server），
            # 不落到 5037；其余模拟器不接管
            with _utils_game_apk.adb_runner_scope(await resolve_host_adb(self)):
                result = await hook(
                    script_config=self.script_config,
                    resource_name=self.run_plan.resourceName,
                    package_name=self._launched_package_name,
                    adb_path=adb_path,
                    adb_address=address,
                    if_auto_install=mode == "AutoInstall",
                    progress=report,
                )
        except asyncio.CancelledError:
            point(self, "game_update", state="cancelled")
            raise
        except Exception as exc:
            point(self, "game_update", state="failed")
            logger.opt(exception=True).warning(f"游戏更新检查异常: {exc}")
            self._append_log(f"游戏更新检查出错，本次照常运行: {exc}")
            return

        game_update_result(self, result)
        self._append_log(result.message)
        if result.status == "NeedManualUpdate":
            raise _MaaFWGameUpdateRequired(result.message)

    async def _ensure_logged_in(self, address: str, adb_path: str | None) -> None:
        """模拟器启动后、第一个任务下发前，调特调的运行前登录钩子（契约见 flavor.py）。

        紧跟游戏更新检查之后。登录成功后同一客户端会话里不再调；失败时下一次尝试重新调，
        重试关闭游戏 / 模拟器（客户端重启）后也重新调。钩子判定本次无法继续时抛
        ``MaaFWLoginRequired``，按普通失败结算、照常重试；钩子实现里的其它异常同样按失败
        处理，原因附在异常原文后面。没实现钩子（通用 MaaFW）时什么都不做。
        """

        if self._login_checked:
            return
        self._startup_task = None
        hook = resolve_login_hook(self.script_config)
        if hook is None or self.run_plan is None:
            return

        async def report(text: str) -> None:
            self._append_log(text)

        try:
            message = await hook(
                script_config=self.script_config,
                user_config=self.cur_user_config,
                resource_name=self.run_plan.resourceName,
                package_name=self._launched_package_name,
                adb_path=adb_path,
                adb_address=address,
                progress=report,
                host_adb=await resolve_host_adb(self),
            )
        except MaaFWLoginRequired:
            raise
        except Exception as exc:
            logger.opt(exception=True).warning(f"运行前登录钩子异常: {exc}")
            raise MaaFWLoginRequired(f"运行前登录出错：{exc}") from exc

        if isinstance(message, StartupTask):
            self._startup_task = message
            return
        if message:
            self._append_log(str(message))
        # 登录成功才记「已登录」：失败时保持未完成，外层重试会重新走这个钩子，
        # 不允许带着没登录（或登录到别的账号）的状态下发任务。
        self._login_checked = True

    def _mod_avd_open_kwargs(self) -> dict[str, Any]:
        return {"allow_mod_avd": True}

    async def _script_adb_env(self) -> dict[str, str]:
        if self.emulator_manager is None:
            return {}
        env = await self.emulator_manager.process_env(
            game_device_id(self.script_config)
        )
        return (
            {"ANDROID_ADB_SERVER_PORT": env["ANDROID_ADB_SERVER_PORT"]}
            if env is not None
            else {}
        )

    async def _run_maafw(self, device_config: MaaFWDeviceConfig) -> MaaFWRunResult:
        """取配置、组装入参，交给 ``plan_run`` 跑这份计划；事件转成账号日志、运行记录与进度点。"""

        plan = self.run_plan
        if plan is None:
            raise RuntimeError("MaaFW 运行计划尚未初始化")
        task_limit_seconds, task_limit_overrides = task_time_limits_from_config(
            self.script_config
        )
        # 特调把登录交给首任务完成（StartupTask）：首任务失败即结束本轮，时限截到剩余的登录
        # 时限——截止时刻交给 plan_run，在下发 job 前一刻换算成秒（借环境的耗时照样扣掉）。
        startup = self._startup_task
        task_deadlines: dict[str, float] = {}
        if startup is not None:
            if not plan.tasks or plan.tasks[0].entry != startup.entry:
                raise MaaFWLoginRequired("启动失败：运行计划缺少公开启动任务")
            first = plan.tasks[0]
            plan = plan.model_copy(
                update={
                    "tasks": [
                        first.model_copy(update={"abortRoundMessage": "启动游戏失败"}),
                        *plan.tasks[1:],
                    ]
                }
            )
            task_deadlines[first.name] = startup.deadline
        secrets = self._secret_log_variants()
        profile = self._adb_state.profile
        request = MaaFWPlanRunRequest(
            project_path=self.project_path,
            plan=plan,
            device_config=device_config,
            runtime_pool_root=self.maafw_runtime_pool_root,
            runtime_pool_id=str(self.maafw_runtime_pool_id or ""),
            lease_owner=f"automas-script-maafw:{self.script_info.script_id}",
            run_time_limit_minutes=self.script_config.Run.RunTimeLimit,
            attachment_root=Path(self._history_temp.name),
            task_time_limit_seconds=task_limit_seconds,
            task_time_limit_overrides=task_limit_overrides,
            task_deadlines=task_deadlines,
            loop_guard=loop_guard_from_config(self.script_config),
            run_secrets=secrets,
            project_log_secrets=self._project_log_secret_variants(secrets),
            redaction_notice=self._log_redaction_notice(),
            game_started_at=self.game_started_at,
            game_start_disk_quiet=self.game_start_disk_quiet,
            game_wait_seconds=self.script_config.Game.WaitTime,
            import_paths=[Config.source_path],
            # 与运行前更新 / 预检同一份解析：托管级 Update.ProxyAddress 优先，留空跟随全局
            proxy_url=resolve_update_proxy_url(self.script_config),
            agent_plans=self._worker_agent_plans,
            extra_env=await self._script_adb_env(),
            desktop=desktop_process_target.get(),
            avd_emulator=(
                self.emulator_manager
                if profile is not None and profile.emulator_type == "avd"
                else None
            ),
        )
        run = MaaFWPlanRun(request, self._on_plan_run_event)
        self._plan_run = run
        attempt_key = id(self.cur_user_log)
        try:
            outcome = await run.run()
        except MaaFWTaskDeadlineExpired:
            raise MaaFWLoginRequired("启动失败：登录时限已耗尽") from None
        finally:
            if self._plan_run is run:
                self._plan_run = None
            # 附件、原生报错行与 agent 命令计划在运行抛异常时同样要留下
            if run.attachments:
                self._history_attachments.setdefault(attempt_key, []).extend(
                    HistoryAttachmentInput(
                        path=item.path,
                        kind=item.kind,
                        role=item.role,
                        display_name=item.display_name,
                    )
                    for item in run.attachments
                )
            self._attempt_native_errors = list(run.native_errors)
            # 同一账号这一轮只认第一次借环境时算出的 agent 命令计划，重试沿用
            if self._worker_agent_plans is None and run.agent_plans is not None:
                self._worker_agent_plans = run.agent_plans
        result = outcome.result
        if startup is not None and plan.tasks[0].name in result.completedTasks:
            # 首任务（登录）完成才记「已登录」
            self._login_checked = True
            self._startup_task = None
        return result

    def _on_plan_run_event(self, event: MaaFWPlanRunEvent) -> None:
        """``plan_run`` 与 ``pretask_run`` 的事件出口：账号日志、进度点（以本任务为 owner）、运行记录。"""

        if isinstance(event, MaaFWPlanRunLog):
            self._append_log(event.message, warning=event.warning)
        elif isinstance(event, MaaFWPlanRunPoint):
            point(self, event.stage, state=event.state, key=event.key)
        elif isinstance(event, MaaFWPlanRunRecord):
            self._on_run_record_event(event.data)
        elif isinstance(event, MaaFWPlanRunStage):
            self._run_record.mark_stage(event.stage, event.ok)

    def _run_password_values(self) -> list[str]:
        """本次运行要打码的密码值：计划里 password 字段的值 + 该账号快照里全部密文解开的值
        （项目撤掉了 password 标记的字段建计划时照样解开，见 option_secrets）。"""

        if self.run_plan is None or self.interface_model is None:
            return []
        return collect_run_password_values(
            self.run_plan,
            self.interface_model,
            getattr(self, "cur_user_config", None),
        )

    def _secret_log_variants(self) -> list[str]:
        """本次运行要打码的密码值在日志里可能出现的写法（见 option_secrets）。"""

        return secret_log_variants(self._run_password_values())

    def _project_log_secret_variants(self, plan_variants: list[str]) -> list[str]:
        """项目日志不一定是本次运行的用户写的（上一个账号留下的片段也可能落在本次新增里），
        所以按脚本全部用户的密码打码，再并上本次运行计划里的。"""

        try:
            values = collect_script_password_values(
                self.script_config, self.interface_model
            )
        except Exception as exc:  # noqa: BLE001 - 取不到时退回本次运行计划里的
            logger.debug(f"收集脚本全部用户的密码失败，只按本次运行的打码: {exc}")
            return plan_variants
        return sorted(
            set(plan_variants) | set(secret_log_variants(values)),
            key=len,
            reverse=True,
        )

    def _log_redaction_notice(self) -> str | None:
        """项目有 password 输入框或本次有要打码的值时写进 ``.worker.log`` 开头的打码说明。"""

        if self.run_plan is None or self.interface_model is None:
            return None
        return log_redaction_notice(self.interface_model, self._run_password_values())

    async def _shutdown_runner(self) -> None:
        await self._pretasks.stop()
        await self._terminate_runner_process()

    async def _pretasks_need_rerun(self, client_reset: bool) -> bool:
        """重试前要不要再跑一遍已经成功过的运行前设置（判据见 ``pretask_run.pretasks_need_rerun``）。"""

        return await pretasks_need_rerun(
            self.run_plan,
            self.interface_model,
            client_reset=client_reset,
            configured_hwnd=self.script_config.Device.HWnd,
            emit=self._on_plan_run_event,
        )

    async def _run_pretasks(self) -> None:
        """取配置、组装入参，交给 ``pretask_run`` 跑这次尝试的运行前设置。"""

        if self.run_plan is None:
            raise RuntimeError("MaaFW 运行计划尚未初始化")
        # ModAVD 实例：pretask 若用 adb，也走脚本专用 server（同 worker）
        adb_env = await self._script_adb_env()
        await self._pretasks.run(
            MaaFWPretaskRunRequest(
                project_path=self.run_plan.path,
                pretasks=self.run_plan.pretasks,
                run_time_limit_minutes=self.script_config.Run.RunTimeLimit,
                plan_env=self.run_plan.piEnv,
                extra_env=adb_env,
                secrets=self._secret_log_variants(),
                desktop=desktop_process_target.get(),
            )
        )

    async def _terminate_runner_process(self) -> None:
        """停止时结束正在跑的 worker（经 ``plan_run`` 的停止入口；没有在跑的就什么都不做）。"""

        run = self._plan_run
        if run is not None:
            await run.stop()

    def _period_limits(self) -> MaaFWPeriodLimits:
        run = self.script_config.Run
        return MaaFWPeriodLimits.of(
            _load_json_list(run.DailyOnceTasks),
            _load_json_list(run.WeeklyOnceTasks),
            _load_json_list(run.MonthlyOnceTasks),
        )

    def _filter_period_once_tasks(self, plan: MaaFWRunPlan) -> MaaFWRunPlan:
        limits = self._period_limits()
        if limits.empty:
            return plan
        return filter_period_once_tasks(
            plan,
            limits,
            self._load_period_task_records(),
            datetime.now(tz=UTC4),
        )

    async def _refresh_run_plan_after_period_update(
        self, completed_tasks: list[str]
    ) -> None:
        """重试前重建计划：从 ``base_run_plan`` 重新按周期过滤，再剔掉本次运行已完成的。

        ``completed_tasks`` 是刚结束这次尝试的 ``completedTasks``（任务名，不是 entry）。
        剔除必须跟在重建之后：重建会把上一次剔掉的任务放回来，所以按累计结果每次都重剔。
        """

        self._completed_this_run.extend(completed_tasks)
        if self.base_run_plan is not None:
            plan = await asyncio.to_thread(
                self._filter_period_once_tasks,
                self.base_run_plan,
            )
            self.run_plan = self._skip_tasks_completed_this_run(plan)

    def _skip_tasks_completed_this_run(self, plan: MaaFWRunPlan) -> MaaFWRunPlan:
        """剔掉特调声明的 ``skip_on_retry_entries`` 里、本次运行已完成过的任务。

        按 entry 认任务、按任务名计份数；同名任务在队列里有多份时全部重跑（见下面注释）。
        没有声明的特调与通用 MaaFW 原样返回。剔掉的记进 ``skippedTasks``，每次重试开头
        据此写一行（``_log_retry_skipped_tasks``）。
        """

        flavor = resolve_flavor(self.script_config)
        entries = skip_on_retry_entries(flavor)
        if not entries:
            return plan
        # 同名多份时一份都不剔、全部重跑，见 skip_tasks_completed_this_run
        outcome = skip_tasks_completed_this_run(plan, self._completed_this_run, entries)
        self._retry_rerun_duplicates = outcome.rerun_duplicates
        return outcome.plan

    def _log_retry_skipped_tasks(self) -> None:
        """重试开头写一行被重试跳过的任务。

        不一次性消费：上一次尝试 worker 崩溃时计划原样沿用，这一行要照样写。
        """

        if self.run_plan is None:
            return
        skipped = _retry_skipped_tasks(self.run_plan)
        if skipped:
            self._append_log(
                f"{_RETRY_SKIP_REASON}，不再补跑: "
                + "、".join(_task_display_name(task) for task in skipped)
            )
        duplicates = list(dict.fromkeys(self._retry_rerun_duplicates))
        if duplicates:
            labels = _format_completed_task_labels(self.run_plan, duplicates)
            self._append_log(
                f"{'、'.join(labels)} 在队列里有多份，分不清完成的是哪一份，重试时全部重跑"
            )

    def _load_period_task_records(self) -> PeriodRecords:
        return parse_period_records(
            _load_json_dict(self.cur_user_config.Data.PeriodTaskRecords)
        )

    async def _mark_period_tasks_completed(self, completed_tasks: list[str]) -> None:
        if not completed_tasks:
            return
        limits = self._period_limits()
        if limits.empty:
            return

        records = self._load_period_task_records()
        new_records = record_period_completions(
            records, limits, completed_tasks, datetime.now(tz=UTC4)
        )
        if new_records != records:
            self.cur_user_config.Data.PeriodTaskRecords = json.dumps(
                new_records, ensure_ascii=False
            )
            await self.cur_user_config.commit()

    async def _mark_run_started(self) -> None:
        if self.cur_user_config.Data.LastProxyDate.strftime("%Y-%m-%d") != self.curdate:
            self.cur_user_config.Data.LastProxyDate = datetime.now(tz=UTC4)
            await self.cur_user_config.commit()
            self.cur_user_config.Data.ProxyTimes = 0
            await self.cur_user_config.commit()
        self.cur_user_config.Data.LastProxyStatus = "运行中"
        await self.cur_user_config.commit()

    async def _close_emulator(self) -> bool:
        """关闭由 MAS 启动的模拟器，返回是否关成（本来就没开过算关成）。"""

        if not self.opened_emulator:
            return True
        try:
            # 失败原因（含超时）记 warning 进 app.log：#708 设成静默的理由「插件清理属
            # 预期路径」已经不成立（没有插件这一层了）。账号日志不写：重试路径下一轮
            # MAS 会自己重开模拟器，「请手动关闭」会误导。
            return await close_emulator(self)
        finally:
            self.opened_emulator = False
            # 地址与雷电 extras 里的 pid 都是随这次启动的，下一轮重开要重新拿
            self._adb_state.forget_emulator_launch()
            # 游戏随模拟器一起关了；下一轮重开时按那次拉起重新起算
            self.game_started_at = None
            self.game_start_disk_quiet = False

    async def _ensure_desktop_game_started(self) -> None:
        """Win32 场景下由 MAS 负责启动/激活桌面游戏客户端，供后续窗口解析使用。"""
        if self.run_plan is None or self.run_plan.controllerType != "Win32":
            return
        if self.opened_game:
            return
        if not self._mas_manages_game_launch():
            # AttachOnly：游戏由脚本或用户自己起，MAS 只负责找窗口。窗口找不到时
            # device_config.resolve_window_handle 会给出「未找到匹配 MaaFW Win32 controller
            # 的窗口」，比在这里索要一个本模式用不上的 exe 更贴题。
            return

        config_error = await asyncio.to_thread(self._describe_game_launch_config_error)
        game_path = self._resolve_game_launch_path()
        if config_error is not None or game_path is None:
            raise RuntimeError(
                config_error
                or "当前 MaaFW controller 需要由 MAS 启动游戏，请在托管管理页选择实际游戏 exe"
            )

        if self.interface_model is not None and self.run_plan is not None:
            controller = find_controller(
                self.interface_model,
                self.run_plan.controllerName,
            )
            matches = await match_windows_in_session(controller)
            if matches:
                selected = matches[0]
                self._append_log(
                    "检测到游戏客户端窗口: "
                    f"hWnd={selected.hWnd}, class={selected.className}, "
                    f"title={selected.windowName}"
                )
                self._note_resolution_override_skipped()
                self._note_launch_arguments_skipped()
                await self._activate_desktop_game_window(game_path)
                return

        if await asyncio.to_thread(_is_process_path_running, game_path):
            # 走 _append_log（它同样写 app.log）：直接改 script_info.log 会整块替换日志
            # 窗口，这一行也不进账号日志与 history，下一条日志一来就没了。
            self._append_log(
                f"检测到游戏进程已在运行，跳过由 MAS 重复启动游戏: {game_path.name}"
            )
            self._note_resolution_override_skipped()
            self._note_launch_arguments_skipped()
            if await self._wait_for_desktop_game_ready(game_path):
                # 进程在、窗口是等出来的：游戏正在启动，和 MAS 自己拉起的一样要等画面
                self.game_started_at = time.monotonic()
            await self._activate_desktop_game_window(game_path)
            return

        if self._game_launch_mode() == "URL":
            with operation(self, "start_game"):
                await self._launch_game_by_url(game_path)
            await self._activate_desktop_game_window(game_path)
            return

        game_arguments = shlex.split(
            str(self.script_config.Game.Arguments or "").strip()
        )
        logger.info(f"启动游戏: {game_path} - {self.script_config.Game.Arguments}")
        # 注册表必须在进程起来之前改好：Unity 播放器只在启动时读一次这些值
        await self._apply_game_resolution_override(game_path)
        try:
            with operation(self, "start_game"):
                await self.game_process_manager.open_process(
                    game_path,
                    *game_arguments,
                    cwd=game_path.parent,
                    breakaway=True,
                )
                # 进程一起来就算 MAS 开的：等窗口时被停止（CancelledError 不是 Exception，
                # 下面接不住），收尾的 _close_game 要看到它才会关游戏。
                self.opened_game = True
                await self._wait_for_desktop_game_ready(game_path)
            self.game_started_at = time.monotonic()
        except Exception:
            self.opened_game = False
            with suppress(Exception):
                await self.game_process_manager.kill()
            await self._restore_game_resolution_override()
            raise

        await self._activate_desktop_game_window(game_path)

    async def _launch_game_by_url(self, game_path: Path) -> None:
        """URL 模式：打开链接拉起游戏，再按游戏 exe 找到本次启动后出现的进程、等窗口。

        游戏不是 MAS 的子进程（Steam 等转一手），只能按 exe + 创建时间认；``Game.Arguments``
        不用，参数要写进链接。Steam 冷启动慢，找进程的时限不少于
        ``_URL_LAUNCH_MIN_TIMEOUT_SECONDS``。
        """

        url = str(self.script_config.Game.URL or "").strip()
        timeout = max(
            int(self.script_config.Game.WaitTime or 0), _URL_LAUNCH_MIN_TIMEOUT_SECONDS
        )
        logger.info(f"通过链接启动游戏: {url} - {game_path}")
        # 注册表必须在进程起来之前改好：Unity 播放器只在启动时读一次这些值
        await self._apply_game_resolution_override(game_path)
        launched_at = time.time()
        try:
            await _open_launch_url(url)
        except Exception as exc:
            # 被停止（取消）时不在这里恢复：收尾的 _close_game 见 opened_game 为假也会恢复
            await self._restore_game_resolution_override()
            raise RuntimeError(f"无法打开启动链接 {url}: {exc}") from exc
        # 链接一打开就算 MAS 开的（同 DirectExe）：之后等不到、被停止，收尾都要关
        self.opened_game = True
        self.game_launched_at = launched_at
        if self.url_first_launched_at is None:
            self.url_first_launched_at = launched_at
        self._append_log(
            f"已打开启动链接，等待游戏进程启动（最多 {timeout}s）: {game_path.name}"
        )
        try:
            try:
                await self.game_process_manager.search_process(
                    ProcessInfo(exe=str(game_path.resolve())),
                    timeout,
                    min_create_time=launched_at,
                )
            except RuntimeError as exc:
                raise RuntimeError(
                    f"打开启动链接后 {timeout}s 内没有等到游戏进程: {game_path.name}"
                ) from exc
            await self._wait_for_desktop_game_ready(game_path)
            self.game_started_at = time.monotonic()
        except Exception:
            await self._close_game()
            raise

    def _unity_resolution_target(self) -> tuple[int, int] | None:
        """``Game.UnityResolution`` 选了尺寸就返回 (宽, 高)，Off 返回 None。"""

        return parse_resolution_option(self.script_config.Game.UnityResolution)

    def _note_resolution_override_skipped(self) -> None:
        """游戏已在运行时不能中途改分辨率，选了尺寸的用户要知道这轮没改。"""

        if self._unity_resolution_target() is not None:
            self._append_log("检测到游戏已在运行，本轮不会中途修改分辨率")

    def _note_launch_arguments_skipped(self) -> None:
        """游戏已在运行时不会重复启动，配了启动参数的用户要知道这轮没生效。"""

        if self._game_launch_mode() == "URL":
            # URL 模式本来就不用启动参数（参数写在链接里）
            return
        arguments = str(self.script_config.Game.Arguments or "").strip()
        if arguments:
            self._append_log(f"检测到游戏已在运行，本轮不会应用启动参数（{arguments}）")

    async def _apply_game_resolution_override(self, game_path: Path) -> None:
        """按 exe 反查 Unity 注册表并临时写入所选尺寸的窗口模式。

        失败不阻断启动：这只是帮用户过脚本侧的分辨率闸门，改不成就按当前分辨率
        启动，闸门该报什么由脚本自己报，比在这里把整轮打掉更贴题。
        """

        target = self._unity_resolution_target()
        if target is None:
            return
        override = UnityGameResolutionOverride.for_executable(game_path, *target)
        if override is None:
            self._append_log(
                f"未找到 {game_path.name} 的 Unity app.info，无法反查注册表，"
                "跳过临时固定分辨率（只有 Unity 引擎的游戏支持）"
            )
            return
        # 先记下再写：写注册表在工作线程里，等它时被停止（取消）的话，收尾的
        # _close_game 仍要能把它恢复回去
        self.game_resolution_override = override
        try:
            await asyncio.to_thread(override.apply)
        except Exception as exc:
            self.game_resolution_override = None
            logger.warning(f"MaaFW 临时固定游戏分辨率失败: {exc}")
            self._append_log(f"临时固定游戏分辨率失败，按当前分辨率启动: {exc}")
            return
        self._append_log(
            f"已尝试把 HKCU\\{override.registry_path} 的分辨率临时设为 "
            f"{override.label} 窗口模式，游戏关闭后恢复原值"
        )

    async def _restore_game_resolution_override(self) -> None:
        override = self.game_resolution_override
        if override is None:
            return
        self.game_resolution_override = None
        try:
            restored = await asyncio.to_thread(override.restore)
        except Exception as exc:
            logger.warning(f"MaaFW 恢复游戏分辨率注册表失败: {exc}")
            self._append_log(f"恢复游戏分辨率注册表失败: {exc}")
            return
        if restored:
            self._append_log("已恢复启动前的游戏分辨率注册表")

    async def _wait_for_desktop_game_ready(
        self,
        game_path: Path,
        poll_interval: float = 1.0,
    ) -> bool:
        """等到游戏窗口（或配置了句柄时等到进程）就绪。

        返回窗口是不是**等出来的**：第一轮就在的算 False（游戏早就在跑），至少睡过
        一轮才出现的算 True（游戏正在启动）。调用方据此决定要不要再等画面稳定。
        """

        wait_time = max(0, int(self.script_config.Game.WaitTime or 0))
        if wait_time <= 0:
            # 「等待时间」填 0 只表示不等画面稳定；窗口还是要等出来，否则刚拉起的游戏
            # 当场判「窗口未就绪」、被关掉重试，次次如此
            wait_time = _WINDOW_READY_FALLBACK_SECONDS
        if self.run_plan is None or self.interface_model is None:
            raise RuntimeError("MaaFW 运行计划未完成初始化")

        configured_hwnd = self.script_config.Device.HWnd
        explicit_hwnd = optional_int(configured_hwnd)
        controller = find_controller(self.interface_model, self.run_plan.controllerName)

        self._append_log(
            f"正在等待游戏客户端窗口就绪，最大等待时间 {wait_time}s: {game_path.name}"
        )

        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_time

        async def match_before_deadline():
            if desktop_process_target.get() is None:
                return await match_windows_in_session(controller)
            try:
                async with asyncio.timeout_at(deadline):
                    return await match_windows_in_session(controller)
            except TimeoutError as exc:
                raise RuntimeError(
                    f"游戏窗口在 {wait_time}s 内未就绪: {game_path.name}"
                ) from exc

        waited = False
        process_detected = False
        while loop.time() < deadline:
            if not explicit_hwnd:
                matches = await match_before_deadline()
                if matches:
                    selected = matches[0]
                    self._append_log(
                        "检测到游戏客户端窗口: "
                        f"hWnd={selected.hWnd}, class={selected.className}, "
                        f"title={selected.windowName}"
                    )
                    return waited

            if await asyncio.to_thread(_is_process_path_running, game_path):
                if not process_detected:
                    self._append_log(f"检测到游戏进程已启动: {game_path.name}")
                    process_detected = True

                if explicit_hwnd:
                    self._append_log(
                        f"已配置窗口句柄，跳过窗口正则等待: {explicit_hwnd}"
                    )
                    return waited

                matches = await match_before_deadline()
                if matches:
                    selected = matches[0]
                    self._append_log(
                        "检测到游戏客户端窗口: "
                        f"hWnd={selected.hWnd}, class={selected.className}, "
                        f"title={selected.windowName}"
                    )
                    return waited

            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            await asyncio.sleep(min(poll_interval, remaining))
            waited = True

        if desktop_process_target.get() is not None:
            raise RuntimeError(f"游戏窗口在 {wait_time}s 内未就绪: {game_path.name}")

        if not explicit_hwnd:
            matches = await match_windows_in_session(controller)
            if matches:
                selected = matches[0]
                self._append_log(
                    "检测到游戏客户端窗口: "
                    f"hWnd={selected.hWnd}, class={selected.className}, "
                    f"title={selected.windowName}"
                )
                return True

        if await asyncio.to_thread(_is_process_path_running, game_path):
            if explicit_hwnd:
                self._append_log(f"已配置窗口句柄，跳过窗口正则等待: {explicit_hwnd}")
                return True

            matches = await match_windows_in_session(controller)
            if matches:
                selected = matches[0]
                self._append_log(
                    "检测到游戏客户端窗口: "
                    f"hWnd={selected.hWnd}, class={selected.className}, "
                    f"title={selected.windowName}"
                )
                return True

            raise RuntimeError(f"游戏窗口在 {wait_time}s 内未就绪: {game_path.name}")

        raise RuntimeError(f"游戏进程在 {wait_time}s 内未启动: {game_path.name}")

    async def _activate_desktop_game_window(self, game_path: Path) -> None:
        try:
            # 第二个参数是**秒数**，不是截止时刻。dev 的 #473 把计时改成单调时钟后
            # 内部是 `time.monotonic() + timeout_seconds`，传 datetime 会直接
            # TypeError（真机上表现为「游戏进程已启动，但定位窗口失败」，窗口没被
            # 前置，随后第一个任务识别不到而失败）。
            await self.game_process_manager.search_process(
                ProcessInfo(exe=str(game_path.resolve())),
                WINDOW_SEARCH_TIMEOUT_SECONDS,
                owned=self.opened_game,
            )
        except Exception as exc:
            logger.warning(f"MaaFW 定位游戏进程窗口失败: {exc}")
            self._append_log(f"游戏进程已启动，但定位窗口失败: {exc}")
            return

        activate_end_time = datetime.now() + timedelta(seconds=5)
        while datetime.now() < activate_end_time:
            if await self.game_process_manager.activate_window():
                self._append_log("游戏窗口已置于前台")
                return
            await asyncio.sleep(0.5)

        self._append_log("游戏窗口前置失败，将继续启动 MaaFW 任务")

    def _attempt_limit(self) -> int:
        """本账号这次运行最多跑几次：``Run.RunTimesLimit``，加上清理残留后额外的重跑。"""

        return int(self.script_config.Run.RunTimesLimit or 0) + self._extra_attempts

    async def _recover_resource_failure(self, kind: str) -> tuple[str, str] | None:
        """资源包加载失败之后：视图刚换了载荷（清掉了旧版本残留，或经组同步换上了同组兄弟已
        清理过的那份）就返回下一次的（开头那行, 称呼），该立刻再跑一次；其余情况写一行停止
        原因、返回 None（不重试）。

        只有 MaaFramework 拒收资源包（``load_failed``）才核对：资源目录不在（``missing``）不是
        多了文件。每次运行只核对一次；开发者模式（跟随来源目录）以来源为准、不更新，不核对。
        """

        if kind != "load_failed" or self._release_check_done:
            self._append_log(_RESOURCE_FAILURE_STOP_MESSAGE, warning=True)
            return None
        self._release_check_done = True
        from .embedded_project import follow_source_enabled, shell_hint_from_report

        if follow_source_enabled(self.script_config):
            self._append_log(
                "开发者模式（跟随来源目录）以来源目录为准，不与官方发行包核对；"
                + _RESOURCE_FAILURE_STOP_MESSAGE,
                warning=True,
            )
            return None

        import httpx

        from .update_credentials import resolve_update_credentials
        from .view_release_check import (
            check_view_release,
            describe_outcome,
            release_group_members,
        )

        script_id = str(self.script_info.script_id)
        proxy_url = resolve_update_proxy_url(self.script_config)
        try:
            proxy = httpx.Proxy(proxy_url) if proxy_url else None
        except Exception:  # noqa: BLE001 - 代理填错按直连，地址不进日志
            proxy = None
        stop = threading.Event()
        task = asyncio.create_task(
            check_view_release(
                script_id,
                channel=resolve_update_credentials(self.script_config).channel,
                members=lambda: release_group_members(script_id),
                send_log=self._append_log,
                proxy=proxy,
                shell_hint=shell_hint_from_report(self.script_config),
                script_name=str(self.script_info.name or ""),
                cancel_event=stop,
            )
        )
        # 核对 / 清理 / 切视图都在工作线程里改载荷与视图：用户这时点停止，得等它收尾再放预约
        # （_release_project_path 会等这个任务），否则编辑页的导入、手动更新能同时动同一棵视图。
        self._release_check_task = task
        try:
            outcome = await asyncio.shield(task)
        except asyncio.CancelledError:
            stop.set()
            raise
        self._append_log(describe_outcome(outcome), warning=not outcome.switched)
        cleaned = outcome.status in {"cleaned", "repointed"}
        if outcome.switched and outcome.version_changed:
            # 等锁那几秒里组被推到了新版本、视图跟着换了：本次的 interface 与运行计划是按旧
            # 版本建的，不能拿来跑新版本。停下，下次运行前按新版本重做检查。
            self._append_log(
                f"本托管已换到 {outcome.version or '新版本'}，这一轮不再重新运行，"
                "下次运行会按新版本重新准备",
                warning=True,
            )
            return None
        if outcome.switched:
            # 视图换了载荷就重跑，不看 status：同组兄弟已清理过、本托管经组同步换过来时，
            # 核对的是换来的那份（status 是 verified / clean），旧视图里的残留照样没了。
            self._append_log(
                "已换上清理后的版本，立即重新运行（不重启游戏/模拟器）"
                if cleaned
                else "立即用换上的版本重新运行（不重启游戏/模拟器）"
            )
            return _RERUN_AFTER_CLEANUP if cleaned else _RERUN_AFTER_SWITCH
        if cleaned:
            self._append_log(
                "清理后的版本已准备好，但本托管这次没能切换过去，下次运行前自动切换",
                warning=True,
            )
        self._append_log(_RESOURCE_FAILURE_STOP_MESSAGE, warning=True)
        return None

    async def _reset_client_for_retry(self, attempt: int) -> tuple[bool, bool]:
        """重试前关掉 MAS 自己起的客户端，返回（是否全部关成, 是否已不在）。

        前者只决定下一轮日志开头写不写「已重启」；后者给运行前设置判断要不要重跑——
        关的时候报错，opened_* 也已清掉、下一轮会重新拉起，运行前设置同样要重来。
        """

        had_client = self.opened_game or self.opened_emulator
        restarted = await self._restart_client_before_retry(attempt)
        still_open = self.opened_game or self.opened_emulator
        return restarted, bool(had_client and not still_open)

    async def _restart_client_before_retry(self, attempt: int) -> bool:
        """一轮失败后把 MAS 自己拉起的游戏/模拟器关掉，让下一轮从启动重新来。

        和 MAA 专项的重试一个口径：出了问题就整个重来。以前重试只是重启 MaaFW 框架
        再接回同一个窗口——超时那种卡在某一屏的情况（弹窗关不掉、按钮点不动），
        第二、三轮 3 秒内就撞回同一屏，白等两倍时限。
        游戏/模拟器不是 MAS 起的（AttachOnly、发现已在运行）时照旧不碰；
        这是最后一轮时也不在这里关，收尾统一关。返回这次是否全部关成：
        该关的有一个没关成就是 False，下一轮日志开头不写「已重启」。
        """

        if attempt >= self._attempt_limit():
            return False
        if not self.opened_game and not self.opened_emulator:
            return False
        # 只在真正要重启 MAS 自己启动的客户端时撤销预下载资格。
        # 等待 FluxDown/HTTPX 确认停止后才关闭游戏或模拟器；AttachOnly、
        # 最后一次尝试和不重登的资源换载荷路径不需要重置成功计时。
        from app.core.script_update_queue import report_script_task_retrying

        await report_script_task_retrying()
        self._append_log("本轮失败，关闭由 MAS 启动的游戏/模拟器，下一轮重新启动")
        emulator_closed = await self._close_emulator()
        game_closed = await self._close_game()
        # 客户端被重启了：登录会话可能变化（也可能回到别的账号），下一轮必须重新验证登录。
        self._login_checked = False
        return emulator_closed and game_closed

    async def _start_attempt_log(self) -> None:
        """重试前另起一份日志记录，与 MAA 等专项一样每次尝试单独成段。

        界面日志从这一次重新显示；history 里的 ``.log`` / ``.json``、``.worker.log``、
        ``.maafw.log`` 与失败截图都使用本次尝试自己的临时目录。保留真实开始时刻，
        不再为了文件名冲突顺延时间。
        """

        start_time = datetime.now().astimezone()
        self.cur_user_log_started_at = start_time
        self.cur_user_log = LogRecord()
        self.cur_user_log = await self.cur_user_item.add_log_record(
            start_time, self.cur_user_log
        )
        # 这份日志从零开始，行号也要回到 1，否则会接着上一个账号的行号往下数

    def _run_record_call(self, action: Callable[[], Any]) -> Any:
        """运行记录是旁路：记录这一侧出了错只记后端日志、返回 None，不影响运行与收尾。"""

        try:
            return action()
        except Exception as exc:  # noqa: BLE001 - 旁路不能拖垮运行
            logger.opt(exception=True).warning(
                f"MaaFW 运行记录出错（不影响运行）: {exc}"
            )
            return None

    def _begin_run_record_attempt(self, attempt: int) -> None:
        """这次尝试的结构化记录：与本次尝试的日志（history 记录）同一个键。"""

        def begin() -> None:
            plan = self.run_plan
            self._run_record.begin_attempt(
                id(self.cur_user_log),
                attempt=attempt,
                title=self._attempt_title or f"第 {attempt} 次尝试",
                planned=(
                    [(task.name, _task_display_name(task)) for task in plan.tasks]
                    if plan is not None
                    else []
                ),
                retry_skipped=(
                    len(_retry_skipped_tasks(plan)) if plan is not None else 0
                ),
            )

        self._run_record_call(begin)

    def _run_record_statistic(self, key: int) -> HistorySnapshotStatistic | None:
        """某次尝试的运行记录，包成 history 的 snapshot 统计；没有记录返回 None。"""

        value = self._run_record.history_value(key)
        return HistorySnapshotStatistic(value=value) if value is not None else None

    def _on_run_record_event(self, data: Any) -> None:
        """将 worker 推来的阶段、任务起止事件归入本次尝试的专项记录。"""

        event = self._run_record_call(lambda: self._run_record.apply(data))
        if isinstance(event, MaaFWTaskStartEvent):
            point(self, "special", key=event.name)
        elif isinstance(event, MaaFWTaskEndEvent):
            state: PointState = "failed"
            if event.outcome in ("succeeded", "skipped"):
                state = event.outcome
            elif event.outcome == "stopped":
                if event.category == CATEGORY_USER_STOPPED:
                    state = "cancelled"
                elif event.category != CATEGORY_SCRIPT_STOPPED or not event.counted:
                    state = "stopped"
            point(self, "special", key=event.name, state=state)
        record = self._run_record.current
        if record is not None and any(
            task.outcome == "succeeded" for task in record.tasks
        ):
            from app.core.script_update_queue import report_script_task_completed

            report_script_task_completed()

    def run_incident_notice(self) -> str:
        """本次运行里被原地打转检测或单任务时限停下的任务：进用户与脚本两份报告。

        只在最后没成功时列出；后面的重试成功了就不写，免得一份「全部完成」的报告里
        还挂着前面尝试的问题。结果行（``_report_result``，代理结果里账号那一行也是它）
        已经点名的最后一次尝试的任务不列，再单列一遍就是同一件事说两次；结果行没点名的
        （比如不计入失败的任务原地打转，失败的是另一个任务）照常列出。"""

        if self.run_complete:
            return ""

        def notice() -> str:
            named: list[MaaFWTaskRecord] = []
            attempts = self._run_record.attempts()
            # 与 _report_result 同一分支：信号或运行前检查没过时结果行不是 failure_summary
            if (
                attempts
                and self._signal_user_message() is None
                and self.check_result == "Pass"
            ):
                named = failure_summary_tasks(attempts[-1])
            return format_incident_lines(self._run_record.incidents(exclude=named))

        return self._run_record_call(notice) or ""

    async def _finish_on_signal(self, attempt: int, result: MaaFWRunResult) -> None:
        """worker 回报了信号节点命中：记账、写日志状态。

        不发任务页提示（TASK_NOTICE 会在前端弹通知框并响提示音）：界面上只有 runner
        那行日志，正式通知由管理器收尾时按「信号 + 资源」各发一条（同一资源可能有
        多位用户）。证据图只进那条通知，不当失败截图进统计信息与汇总。
        """

        signal = str(result.signal)
        self.run_signal = signal
        point(self, "special", state="matched", key=signal)
        message = SIGNAL_USER_MESSAGES.get(signal, str(result.errorMessage or signal))
        # runner 那行「游戏停服维护中，本轮剩余任务已跳过: <任务>」已进任务日志，
        # 这里只记后端日志，不在界面上再复述一遍。
        logger.warning(
            f"MaaFW 账号 {self.cur_user_item.name} 命中项目信号 {signal}"
            f"（节点 {result.signalNode}）：{message}"
        )
        # 证据图只认命中那个任务、kind 是信号那种的：前面任务普通失败的 failed 图不算。
        evidence = _signal_evidence_shot(result)
        labels = (
            _format_completed_task_labels(self.run_plan, result.completedTasks)
            if self.run_plan is not None
            else list(result.completedTasks)
        )
        # 证据图只随信号通知发一次，不再进统计信息与代理结果汇总；前面任务的普通
        # 失败截图照常进。
        report_shots = [
            (
                _format_completed_task_labels(self.run_plan, [shot.task])[0]
                if self.run_plan is not None
                else shot.task,
                Path(shot.path),
            )
            for shot in result.failureScreenshots
            if shot is not evidence
        ]
        self._record_attempt(
            attempt,
            labels,
            message,
            screenshots=report_shots,
            category=CATEGORY_SIGNAL,
            signal=signal,
        )
        if self.cur_user_log is not None:
            await self.cur_user_log.set_state(status=message)

        project_name = ""
        if self.interface_model is not None:
            with suppress(Exception):
                project_name = await asyncio.to_thread(
                    interface_display_name, self.project_path, self.interface_model
                )
        plan = self.run_plan
        if not project_name and plan is not None:
            project_name = str(plan.projectLabel or plan.projectName or "")
        resource_label = ""
        if plan is not None:
            label = str(plan.resource.label or "").strip()
            resource_label = (
                label if label and not label.startswith("$") else plan.resourceName
            )
        self.signal_tracker.record(
            signal,
            resource_name=plan.resourceName
            if plan is not None
            else result.resourceName,
            resource_label=resource_label,
            project_name=project_name,
            node=result.signalNode,
            user_id=str(self.cur_user_uid),
            user_name=self.cur_user_item.name,
            screenshot=Path(evidence.path) if evidence is not None else None,
        )

    def _is_maintenance_skip(self) -> bool:
        return self.maintenance_skipped or self.run_signal == SERVER_MAINTENANCE

    def _signal_user_message(self) -> str | None:
        """本账号因信号没跑成时给人看的原因；没有信号返回 None。"""

        if self.maintenance_skipped:
            return MAINTENANCE_SKIP_MESSAGE
        if self.run_signal is not None:
            return SIGNAL_USER_MESSAGES.get(self.run_signal, self.run_signal)
        return None

    def _timed_out_user_summary(self, result: MaaFWRunResult) -> str:
        limit = self.script_config.Run.RunTimeLimit
        total = len(self.run_plan.tasks) if self.run_plan is not None else 0
        stopped_at = ""
        if result.failedTask and self.run_plan is not None:
            labels = _format_completed_task_labels(self.run_plan, [result.failedTask])
            stopped_at = f"，最后停在 {labels[0]}"
        return (
            f"MaaFW 任务运行超时（限制 {limit} 分钟，已完成 "
            f"{len(result.completedTasks)}/{total}{stopped_at}）"
        )

    async def _close_game(self) -> bool:
        """关闭由 MAS 启动的游戏，返回是否关成（本来就没开过算关成）。

        只看 opened_game：由 MAS 启动的（DirectExe、URL）一律关，其他方式启动（AttachOnly、
        或发现游戏已在运行而没重复启动）的这里不碰——AttachOnly 的兜底关闭只在最终收尾做，
        见 ``_close_attached_game``。URL 模式另按游戏 exe 兜底扫一遍：游戏不是 MAS 的子进程，
        有的还会自我重启换 PID，跟踪的那一个关掉了不等于游戏关掉了。
        """

        if not self.opened_game:
            await self._restore_game_resolution_override()
            return True

        launched_at = self.game_launched_at
        closed = True
        point(self, "stop_game")
        try:
            try:
                await self.game_process_manager.kill()
            except Exception as exc:
                logger.warning(f"MaaFW 清理时关闭游戏失败: {exc}")
                closed = False
            else:
                if launched_at is not None:
                    # 链接拉起的游戏不是 MAS 的子进程，写一行让用户知道是 MAS 关的
                    self._append_log("已关闭本次通过链接打开的游戏")
            game_path = self._resolve_game_launch_path()
            if launched_at is not None and game_path is not None:
                try:
                    if not await self._end_processes_started_since(
                        launched_at, exes=[game_path]
                    ):
                        closed = False
                except Exception as exc:
                    logger.warning(f"MaaFW 清理时关闭链接拉起的游戏失败: {exc}")
                    closed = False
            point(self, "stop_game", state="succeeded" if closed else "failed")
            return closed
        finally:
            self.opened_game = False
            self.game_started_at = None
            self.game_launched_at = None
            await self._restore_game_resolution_override()

    async def _close_game_after_run(self, *, failed: bool) -> None:
        """最终收尾关游戏：MAS 启动的照常关，AttachOnly 再按 ``Game.CloseMode`` 兜底。

        ``failed`` 为真表示本次运行没正常完成（失败、超时、停止、``on_crash``）。重试之间
        走的是 ``_restart_client_before_retry``，不经这里，AttachOnly 下不关。
        """

        await self._close_game()
        await self._close_url_game_left_behind()
        await self._close_attached_game(failed=failed)

    async def _close_url_game_left_behind(self) -> None:
        """URL 模式最终收尾：按本次运行第一次打开链接的时刻，再扫一遍同 exe 的进程。

        覆盖「等进程超时之后游戏才出现」：那一轮 _close_game 时还没有进程可关，之后的
        尝试按「已在运行」接管（opened_game 为假），没有这一步就会留在外面。运行前就开着
        的游戏不会进 URL 分支（直接接管），所以这个时刻之后出现的同 exe 进程都是 MAS 拉起的。
        """

        since = self.url_first_launched_at
        self.url_first_launched_at = None
        game_path = self._resolve_game_launch_path()
        if since is None or game_path is None:
            return
        try:
            await self._end_processes_started_since(since, exes=[game_path])
        except Exception as exc:
            logger.warning(f"MaaFW 收尾关闭链接拉起的游戏失败: {exc}")
            self._append_log(f"关闭游戏失败: {exc}", warning=True)

    def _attached_game_close_wanted(self, *, failed: bool) -> bool:
        if self._game_launch_mode() != "AttachOnly":
            return False
        if self.run_plan is None or self.run_plan.controllerType != "Win32":
            return False
        mode = str(self.script_config.Game.CloseMode or "OnFailure").strip()
        return mode == "Always" or (mode == "OnFailure" and failed)

    async def _close_attached_game(self, *, failed: bool) -> None:
        """AttachOnly 下由 MAS 兜底关闭本次运行期间打开的游戏与启动器。

        只关创建时间不早于本次运行开始（``run_started_at``，容差 2s）的进程，运行前就开着的
        一律不碰。候选三路：控制器窗口匹配到的窗口所属进程、``Game.LaunchPath``、
        ``Game.LauncherPath``。每次运行只做一次（做过即清空分界时刻），``on_crash`` 与正常
        收尾先后来时不会重复关、重复写日志。
        """

        since = self.run_started_at
        self.run_started_at = None
        if since is None or not self._attached_game_close_wanted(failed=failed):
            return
        try:
            if (
                desktop_process_target.get() is not None
                and self.interface_model is not None
            ):
                controller = find_controller(
                    self.interface_model, self.run_plan.controllerName
                )
                pids = {
                    int(row[3]) for row in await list_desktop_window_matches(controller)
                }
            else:
                pids = await asyncio.to_thread(self._attached_game_window_pids)
            exes = [
                path
                for path in (
                    self._resolve_game_launch_path(),
                    self._resolve_launcher_path(),
                )
                if path is not None
            ]
            await self._end_processes_started_since(
                since, exes=exes, pids=pids, log_kept=True
            )
        except Exception as exc:
            logger.warning(f"MaaFW 收尾关闭游戏失败: {exc}")
            self._append_log(f"关闭游戏失败: {exc}", warning=True)

    def _attached_game_window_pids(self) -> set[int]:
        """控制器窗口匹配到的窗口所属进程；没有窗口规则、扫不了窗口时返回空集。"""

        if self.interface_model is None or self.run_plan is None:
            return set()
        try:
            controller = find_controller(
                self.interface_model, self.run_plan.controllerName
            )
            if not controller_has_window_rules(controller):
                return set()
            windows = match_controller_windows(controller)
        except Exception as exc:
            logger.warning(f"MaaFW 收尾查找游戏窗口失败: {exc}")
            return set()
        pids: set[int] = set()
        for window in windows:
            pid = _window_process_id(int(window.hWnd))
            if pid:
                pids.add(pid)
        return pids

    async def _end_processes_started_since(
        self,
        since: float,
        *,
        exes: list[Path],
        pids: set[int] | None = None,
        log_kept: bool = False,
    ) -> bool:
        """结束候选里创建时间不早于 ``since``（容差 2s）的进程，每个写一行运行日志。

        候选是 pid 在 ``pids`` 里、或 exe 等于 ``exes`` 之一的进程。``log_kept`` 为真时，
        运行前就在的候选也各写一行说明为什么不关。返回该关的是否都关掉了；没关掉的
        （多半是游戏以管理员身份运行、MAS 没有）写一行警告进运行日志。
        """

        closing, kept = await asyncio.to_thread(
            _find_processes_started_since, since, exes=exes, pids=pids or set()
        )
        if log_kept:
            for process in kept:
                self._append_log(f"{process.label} 在运行开始前就已打开，不关闭")
        if not closing:
            return True
        ended, failed = await asyncio.to_thread(_end_processes, closing)
        for process in ended:
            self._append_log(f"已关闭本次运行期间打开的 {process.label}")
        for process in failed:
            self._append_log(
                f"没能关闭 {process.label}，可能需要以管理员身份运行 AUTO-MAS",
                warning=True,
            )
        return not failed

    async def _try_enter_project_path(self) -> bool:
        project_lock_key = await try_reserve_project_path(self.project_path)
        if project_lock_key is None:
            return False
        self.project_lock_key = project_lock_key
        return True

    async def _release_project_path(self) -> None:
        if self.project_lock_key is None:
            return
        scope = current_process_scope.get()
        if scope is not None and scope.requested:
            # #1871 的新收尾确认可能早于统一进程清理结束，不能此时
            # 放开预约；后面的强杀若失败，还可能有旧 pretask 在写目录。
            key, self.project_lock_key = self.project_lock_key, None
            pending = self._release_check_task
            # 此刻要等的运行前设置清理与正在结束的 pretask 进程
            pretasks_exited = self._pretasks.exit_confirmation()

            async def release_after_confirmed_stop() -> None:
                await scope.finished.wait()
                if scope.cleanup_failed:
                    logger.error("MaaFW 任务进程未确认停止，保留项目占用，拒绝并发修改")
                    return
                # 清理没确认时 pretask_run 记一句，这里保留占用
                if not await pretasks_exited():
                    return
                if pending is not None:
                    try:
                        await asyncio.shield(pending)
                    except asyncio.CancelledError:
                        # 核对通过停止令牌退出也算完成；它由 scope 保留，
                        # 不会在文件操作尚未结束时被统一取消。
                        # 若只是当前释放任务被取消，核对仍在运行，则继续保留预约。
                        if not pending.cancelled():
                            raise
                    except Exception as error:
                        logger.warning(f"MaaFW 项目核对未确认，保留占用: {error}")
                        return
                release_project_path_sync(key)

            worker = asyncio.create_task(
                release_after_confirmed_stop(),
                name="maafw-confirmed-project-release",
                context=detached_process_context(),
            )
            scope.retain_worker(worker)
            return

        pending = self._release_check_task
        if pending is not None and not pending.done():
            # 资源加载失败后的核对 / 清理还在工作线程里改视图（用户停止时）：等它收尾，等不到就
            # 把释放交给它的完成回调，预约不能先放。
            with suppress(BaseException):
                await asyncio.wait_for(
                    asyncio.shield(pending),
                    timeout=_RELEASE_CHECK_CANCEL_GRACE_SECONDS,
                )
            if not pending.done():
                key = self.project_lock_key
                self.project_lock_key = None

                def _release_later(task: asyncio.Task[Any]) -> None:
                    # 顺手取走异常，免得报「never retrieved」（同 manager 的 _release_after_work）
                    if not task.cancelled():
                        task.exception()
                    release_project_path_sync(key)

                pending.add_done_callback(_release_later)
                return
        await release_project_path(self.project_lock_key)
        self.project_lock_key = None

    def _ensure_display_hold(self) -> None:
        """没有生效中的「保持显示开启」请求就再请求一份。

        每次尝试开头都调：电源延时 / 倒计时期间又起了任务时，MAS 执行睡眠 / 休眠前会撤掉
        所有请求、醒来后不会自己补；请求本身失败也会变成已撤销。怕熄屏的启动器那一步就在
        尝试开头的运行前设置里。
        """

        hold = self._display_hold
        if hold is None or not hold.active:
            self._display_hold = power.hold_display(
                f"MFW 运行（{self.cur_user_item.name}）"
            )

    async def _ensure_workstation_unlocked(self) -> None:
        """要用交互式桌面的控制器，锁屏时直接判失败，不进会重启游戏的重试。"""

        if (
            not IS_WINDOWS
            or self.run_plan is None
            or self.run_plan.controllerType not in _DESKTOP_CONTROLLER_TYPES
        ):
            return
        try:
            if (desktop := desktop_process_target.get()) is None:
                reason = await asyncio.to_thread(
                    _utils_display.input_desktop_unavailable
                )
            else:
                from app.utils.windows.desktop_session.process_runner import (
                    run_desktop_action,
                )

                _, output, _ = await run_desktop_action(
                    desktop, "input_desktop_unavailable", {}
                )
                reason = output.decode("utf-8") if output else None
        except Exception as error:
            # 查不出来不拦：这一步是给出明确原因的改善项，不该把本来能跑的任务打掉
            logger.opt(exception=True).warning(f"检查锁屏状态失败，照常运行：{error}")
            return
        if reason is None:
            return
        logger.warning(f"MaaFW 运行前检查到锁屏：{reason}")
        raise _MaaFWWorkstationLocked(
            "电脑处于锁屏状态，Win32 控制器的项目要在解锁的桌面上才能截图和操作，"
            "本次不运行、不重试，请解锁后再运行"
        )

    def _release_display_hold(self) -> None:
        hold, self._display_hold = self._display_hold, None
        if hold is not None:
            hold.release()

    async def _freeze_notification_images(self) -> None:
        """归档会移动临时文件，通知及跨账号报告先持有自己的图片内容。"""
        self._notification_screenshots = []
        for label, path in self._collect_failure_screenshots()[
            -NOTIFY_SCREENSHOT_LIMIT:
        ]:
            try:
                self._notification_screenshots.append(
                    (label, await asyncio.to_thread(path.read_bytes))
                )
            except OSError as error:
                self._append_log(f"冻结通知截图失败：{error}", warning=True)
        await self.signal_tracker.freeze_user_screenshots(str(self.cur_user_uid))

    async def _save_user_history(self) -> None:
        if self._history_saved:
            return
        self._history_saved = True
        # 预检未派发的用户只保留当前报告；实际执行后遇到维护仍归档 skipped。
        if self.check_result != "Pass":
            return
        try:
            await self._freeze_notification_images()
        except Exception as error:
            self._append_log(f"冻结通知截图失败：{error}", warning=True)
            logger.opt(exception=True).warning(f"冻结通知截图失败：{error}")
        # 用户停止 / 崩溃时最后一次尝试没走到 _record_attempt：按停止或宿主异常收尾
        self._run_record_call(
            lambda: self._run_record.finish_attempt(
                outcome="stopped" if self.stopped_manually else "failed",
                category=CATEGORY_USER_STOPPED
                if self.stopped_manually
                else CATEGORY_HOST_ERROR,
            )
        )
        records = []
        items = list(self.cur_user_item.iter_history_logs())
        for timestamp, log_item in items:
            status = self._history_statuses.get(id(log_item))
            if status is None:
                status = (
                    "cancelled"
                    if self.stopped_manually
                    else "skipped"
                    if self._is_maintenance_skip()
                    else "error"
                )
            record = HistoryWrite(
                time=timestamp.astimezone(UTC4),
                username=self.cur_user_item.name,
                script_name=self.script_info.name,
                status=status,
                message=log_item.status,
                logs="".join(log_item.content),
            )
            run_record = self._run_record_call(
                lambda: self._run_record_statistic(id(log_item))
            )
            if run_record is not None:
                record.data[RUN_RECORD_HISTORY_KEY] = run_record
            record.attachments.extend(self._history_attachments.get(id(log_item), []))
            records.append(record)
        if records:
            await self.history.save_user_history(
                records,
                script=self.script_info,
                user=self.cur_user_item,
                log_warning=partial(self._append_log, warning=True),
            )

    def _record_attempt(
        self,
        attempt: int,
        completed_labels: list[str],
        failure: str | None,
        *,
        screenshots: list[tuple[str, Path]] | None = None,
        category: str | None = None,
        signal: str | None = None,
        user_message: str | None = None,
        failed_task: str | None = None,
    ) -> None:
        """记下本次尝试的结果，供统计通知的「任务详情」与失败截图用。

        ``category`` / ``signal`` 进结构化运行记录；没给类别的失败由记录按任务结局补
        （任务都没开始是初始化失败，否则取第一个计入失败的任务的类别）。
        ``user_message`` / ``failed_task`` 是 worker 回报的人话摘要与失败任务名，推送里的
        失败原因只从它们和失败类别来（``failure`` 是日志里那句，可能带节点链等排障细节）。
        """

        if self.cur_user_log_started_at is not None:
            self._history_statuses[id(self.cur_user_log)] = (
                "success"
                if failure is None
                else "skipped"
                if self.run_signal == SERVER_MAINTENANCE
                else "error"
            )
        self._run_record_call(
            lambda: self._run_record.finish_attempt(
                outcome=(
                    "success"
                    if failure is None
                    else "skipped"
                    if self.run_signal == SERVER_MAINTENANCE
                    else "failed"
                ),
                category=category,
                signal=signal,
            )
        )
        self._attempt_reports.append(
            {
                "attempt": attempt,
                "title": self._attempt_title or f"第 {attempt} 次尝试",
                "time": datetime.now().strftime("%H:%M:%S"),
                "completed": list(completed_labels),
                "failure": failure,
                "screenshots": list(screenshots or []),
                # 对上这次尝试的运行记录（键同 _begin_run_record_attempt）
                "record_key": id(self.cur_user_log),
                "user_message": user_message,
                "failed_task": failed_task,
            }
        )

    def _collect_failure_screenshots(self) -> list[tuple[str, Path]]:
        """本账号要随通知发出去的失败截图（标签, 路径），按时间顺序。

        最终成功的运行不带图：任务详情那边成功时也不提前面尝试的失败，
        早先尝试的失败画面对已经跑通的一轮没有意义。张数上限由消费方裁。
        """

        if self.run_complete:
            return []
        shots: list[tuple[str, Path]] = []
        for report in self._attempt_reports:
            for label, path in report.get("screenshots", ()):
                shots.append((f"{report['title']} · {label}", path))
        return shots

    def report_screenshots(self) -> list[tuple[str, bytes]]:
        """给托管级「代理结果」报告用的失败截图，标签带上账号名称以区分多账号。"""

        return [
            (f"{self.cur_user_item.name} · {label}", path)
            for label, path in self._notification_screenshots
        ]

    def _build_task_details(self) -> str:
        """账号级统计报告的任务详情：最后一次尝试的逐任务时间线（见 ``run_report``）。

        最后没成功时另起一段列结果行没点名的原地打转 / 单任务超时（每类一行），队列里有
        失效任务时末尾再附一行。整次运行一个任务都没开始时没有时间线，原因在运行结果那行。
        """

        details = self._run_record_call(self._task_timeline)
        if details is None:
            details = self._completed_tasks_fallback()
        incidents = self.run_incident_notice()
        missing = self.missing_task_notice()
        return "\n\n".join(part for part in (details, incidents, missing) if part)

    def _attempt_outcomes(self) -> list[MaaFWAttemptReport]:
        """各次尝试的运行记录，配上 worker 回报的人话摘要与失败任务名。"""

        reports = {report.get("record_key"): report for report in self._attempt_reports}
        outcomes = []
        for key, record in self._run_record.attempt_items():
            report = reports.get(key) or {}
            outcomes.append(
                MaaFWAttemptReport(
                    record=record,
                    user_message=report.get("user_message"),
                    failed_task=report.get("failed_task"),
                )
            )
        return outcomes

    def _task_timeline(self) -> str | None:
        """逐任务时间线；没有运行记录返回 None（由调用方退回完成清单）。"""

        outcomes = self._attempt_outcomes()
        if not outcomes:
            return None
        return format_timeline(outcomes)

    def _completed_tasks_fallback(self) -> str:
        """运行记录出错、没有可用记录时的退路：只列完成了哪些任务，不带失败原文。"""

        reports = getattr(self, "_attempt_reports", None) or []
        if not reports:
            return ""
        if getattr(self, "run_complete", False):
            merged: list[str] = []
            for report in reports:
                for label in report["completed"]:
                    if label not in merged:
                        merged.append(label)
        else:
            merged = list(reports[-1]["completed"])
        return "已完成: " + ("、".join(merged) if merged else "无")

    def _report_result(self, *, short: bool = False) -> str:
        """本账号这次的结果，账号级统计报告与托管级「代理结果」同一口径。

        成功只说完成；失败说失败在哪些任务、为什么（只用人话，见 ``run_report``）；
        信号与运行前检查跳过沿用原来那句话。``short``：托管级每个账号一行用的简短说法。
        """

        if self.run_complete:
            if self.missing_task_names:
                return MISSING_TASK_USER_RESULT
            return "全部完成" if short else "代理任务全部完成"
        signal_message = self._signal_user_message()
        if signal_message is not None:
            return signal_message
        if self.check_result != "Pass":
            return (
                self.cur_user_log.status
                if self.cur_user_log is not None
                else self.check_result
            )
        summary = self._run_record_call(
            lambda: failure_summary(self._attempt_outcomes())
        )
        if summary:
            return summary
        crash = getattr(self, "_crash_message", None)
        if crash is not None:
            # 还没进第一次尝试就崩了：没有运行记录，按崩溃原因说一句
            reason = human_reason(crash) or CATEGORY_REASONS[CATEGORY_HOST_ERROR]
            return f"MaaFW 运行失败：{reason}"
        return "代理任务未完成"

    def proxy_report_line(self) -> str | None:
        """托管级「代理结果」里本账号的那一行；运行前检查没过、也没记日志的返回 None，
        由管理器沿用通用的账号结果。"""

        if self.check_result != "Pass" and self.cur_user_log is None:
            return None
        return self._report_result(short=True)

    def missing_task_notice(self) -> str:
        """队列里 interface 已没有的任务（多半是项目更新改了 name）：进用户与脚本两份报告。"""

        if not self.missing_task_names:
            return ""
        return f"{MISSING_TASK_NOTICE_PREFIX}: " + "、".join(self.missing_task_names)

    async def _push_user_statistics(self) -> None:
        """按通知设置推送账号级统计信息。

        与 M9A 专项同形（``M9A/AutoProxy.py`` 的「统计信息」分支）：合并本轮各次
        尝试的统计文件，补上账号名称 / 起止时间 / 结果，再发往全局与该账号自己的
        渠道。``MaaFWUserConfig`` 的 Notify 组一直都在、编辑页也能配，但在此之前
        没有任何代码往它发——托管级「代理结果」是唯一会发出去的报告。

        放在状态落定之后：``user_result`` 要读最终的 ``run_complete``。
        """

        try:
            statistics = {}
            statistics["user_info"] = self.cur_user_item.name
            statistics["start_time"] = (
                self.user_start_time.strftime("%Y-%m-%d %H:%M:%S")
                if self.user_start_time is not None
                else ""
            )
            statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            statistics["task_details"] = self._build_task_details()
            images = await prepare_screenshot_images(
                self._notification_screenshots,
                image_id_prefix="maafw",
            )
            statistics["screenshots"] = screenshot_entries(images)
            # 有失效任务时照常算完成（次数、状态不动），但不能说成「全部完成」；
            # 失败时不再用日志状态那句（里面可能有节点链、框架事件）
            statistics["user_result"] = self._report_result()
            if self.run_complete and self.missing_task_names:
                mark = "!"
            elif self.run_complete:
                mark = "√"
            elif self._is_maintenance_skip():
                mark = MAINTENANCE_LAST_STATUS
            else:
                mark = "X"
            await Notify.push_statistics_report(
                payload=_format_maafw.build_statistics_payload(
                    title=f"{datetime.now().strftime('%m-%d')} |{mark}|  {self.cur_user_item.name} 的自动代理统计报告",
                    message=statistics,
                    images=[image for _, image in images],
                ),
                user_config=self.cur_user_config,
                task_info=self.task_info,
            )
        except Exception as exc:
            logger.opt(exception=True).warning(f"推送 MaaFW 统计信息时出现异常: {exc}")
            with suppress(Exception):
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error",
                        message=f"推送 MaaFW 统计信息时出现异常: {exc}",
                    ),
                )

    async def _send_success_notify(self) -> None:
        try:
            if self.missing_task_names:
                names = "、".join(self.missing_task_names)
                await Notify.send_notice(
                    LocalNotice(
                        title="MaaFW 自动代理任务完成，但有失效任务",
                        message=f"账号 {self.cur_user_item.name} 的队列里有 interface 内已没有的任务，"
                        f"已跳过：{names}",
                        ticker=f"{self.cur_user_item.name} 有失效任务：{names}",
                        duration_seconds=3,
                    )
                )
                return
            await Notify.send_notice(
                LocalNotice(
                    title="MaaFW 自动代理任务完成",
                    message=f"已完成账号 {self.cur_user_item.name} 的 MaaFW 自动代理任务",
                    ticker=f"已完成 {self.cur_user_item.name} 的 MaaFW 自动代理任务",
                    duration_seconds=3,
                )
            )
        except Exception as exc:
            logger.warning(f"MaaFW 插件用户通知发送失败: {exc}")

    def _append_log(self, message: str, *, warning: bool = False) -> None:
        # 失败类的账号日志按 WARNING 进 app.log，事后按级别筛得出来
        (logger.warning if warning else logger.info)(message)
        if self.cur_user_log is None:
            self._pending_user_log.append(_format_user_log_line(message))
            return
        record = self.cur_user_log

        async def publish():
            await record.append_content(_format_user_log_line(message))
            content = record.content
            await self.script_info.set_log("".join(content))

        self.callbacks.submit(publish())


def _is_process_path_running(executable_path: Path) -> bool:
    target_path = executable_path.resolve()
    for proc in iter_processes(["exe"]):
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            raw_exe = proc.info.get("exe") or proc.exe()
            if raw_exe and Path(raw_exe).resolve() == target_path:
                return True
    return False


async def _open_launch_url(url: str) -> None:
    """用系统默认处理程序打开启动链接（Windows 上是 ShellExecute）。"""
    if (desktop := desktop_process_target.get()) is not None:
        from app.utils.windows.desktop_session.process_runner import open_in_desktop

        await open_in_desktop(desktop, url)
        return

    from app.utils import process_platform

    await process_platform.platform_process.open_protocol(url)


@dataclass(frozen=True)
class _ProcessSnapshot:
    """兜底关闭用的进程快照：exe 读不到时为空串，创建时间读不到时为 None。"""

    pid: int
    exe: str
    create_time: float | None

    @property
    def label(self) -> str:
        name = Path(self.exe).name if self.exe else "进程"
        return f"{name}（pid={self.pid}）"


def _normalized_exe(path: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _snapshot_processes() -> list[_ProcessSnapshot]:
    snapshots: list[_ProcessSnapshot] = []
    for proc in iter_processes(["pid", "exe", "create_time"]):
        info = proc.info
        snapshots.append(
            _ProcessSnapshot(
                pid=int(info.get("pid") or proc.pid),
                exe=str(info.get("exe") or ""),
                create_time=info.get("create_time"),
            )
        )
    return snapshots


def _window_process_id(hwnd: int) -> int | None:
    """窗口所属进程的 pid；拿不到（窗口已销毁、非 Windows）返回 None。"""

    try:
        import win32process

        _, pid = win32process.GetWindowThreadProcessId(hwnd)
    except Exception:
        return None
    return int(pid) or None


def _find_processes_started_since(
    since: float, *, exes: list[Path], pids: set[int]
) -> tuple[list[_ProcessSnapshot], list[_ProcessSnapshot]]:
    """按 pid 或 exe 找候选，按创建时间分成（本次之后才出现的, 之前就在的）。

    创建时间读不到的算「之前就在」：宁可漏关，不误关用户自己开着的进程。本进程不算候选。
    """

    targets: set[str] = set()
    for path in exes:
        with suppress(OSError):
            path = path.resolve()
        targets.add(_normalized_exe(path))
    own_pid = os.getpid()
    closing: list[_ProcessSnapshot] = []
    kept: list[_ProcessSnapshot] = []
    for snapshot in _snapshot_processes():
        if snapshot.pid == own_pid:
            continue
        matched = snapshot.pid in pids or (
            bool(snapshot.exe) and _normalized_exe(snapshot.exe) in targets
        )
        if not matched:
            continue
        if (
            snapshot.create_time is not None
            and snapshot.create_time >= since - _PROCESS_CREATE_TIME_TOLERANCE_SECONDS
        ):
            closing.append(snapshot)
        else:
            kept.append(snapshot)
    return closing, kept


def _end_processes(
    targets: list[_ProcessSnapshot],
    grace_seconds: float = _PROCESS_TERMINATE_GRACE_SECONDS,
) -> tuple[list[_ProcessSnapshot], list[_ProcessSnapshot]]:
    """先 terminate，``grace_seconds`` 后仍在的 kill；返回（已结束的, 没能结束的）。

    结束前按创建时间再核一次：快照之后 pid 被别的进程复用了就不碰它（两边都不算）。
    已经自己退出的也不算失败。
    """

    started: dict[psutil.Process, _ProcessSnapshot] = {}
    failed: list[_ProcessSnapshot] = []
    for target in targets:
        try:
            proc = managed_process(target.pid, expected_create_time=target.create_time)
            if proc is None:
                continue
            if not terminate_process(proc):
                if proc.is_running():
                    logger.warning(f"MaaFW 未能结束进程: {target.label}")
                    failed.append(target)
                continue
        except psutil.NoSuchProcess:
            continue
        except ProcessLookupError:
            logger.warning(f"MaaFW 结束进程时无法确认目标归属: {target.label}")
            failed.append(target)
            continue
        except (psutil.AccessDenied, OSError) as exc:
            logger.warning(f"MaaFW 结束进程失败 {target.label}: {exc}")
            failed.append(target)
            continue
        started[proc] = target
    if not started:
        return [], failed
    _, alive = psutil.wait_procs(list(started), timeout=grace_seconds)
    for proc in alive:
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            terminate_process(proc, force=True)
    if alive:
        _, alive = psutil.wait_procs(alive, timeout=grace_seconds)
    for proc in alive:
        logger.warning(f"MaaFW 结束进程后仍在运行: {started[proc].label}")
        failed.append(started[proc])
    return [snapshot for proc, snapshot in started.items() if proc not in alive], failed


def _load_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        with suppress(json.JSONDecodeError):
            data = json.loads(value)
            if isinstance(data, dict):
                return data
    return {}


def _load_script_hotkeys(value: Any) -> dict[str, dict[str, str]]:
    """``Game.Hotkeys`` → ``{option 名: {字段名: 组合键}}``；不成形的部分丢掉。"""

    result: dict[str, dict[str, str]] = {}
    for option_name, fields in _load_json_dict(value).items():
        if not isinstance(option_name, str) or not isinstance(fields, dict):
            continue
        cleaned = {
            field_name: field_value
            for field_name, field_value in fields.items()
            if isinstance(field_name, str) and isinstance(field_value, str)
        }
        if cleaned:
            result[option_name] = cleaned
    return result


def _minutes_to_seconds(minutes: Any) -> int:
    """配置里的分钟数换算成秒。0 / 负数 / 写坏的值都当「不限」（返回 0）。"""

    try:
        value = int(minutes)
    except (TypeError, ValueError):
        return 0
    return value * 60 if value > 0 else 0


def task_time_limits_from_config(config: Any) -> tuple[int, dict[str, int]]:
    """读 Run.TaskTimeLimit / Run.TaskTimeLimitOverrides 并换算成秒。

    宿主在拉起 worker 之前算一次，随 job 下发：worker 是独立进程，读不到 Config，
    核心包也只收秒数，不认宿主的配置键。

    Returns:
        (默认单任务时限秒数, {任务名: 时限秒数})，0 表示不限。
    """

    default_seconds = _minutes_to_seconds(config.Run.TaskTimeLimit)
    # 配置系统里 JSON 项存的是字符串（JSONValidator），读出来再解析一次。
    overrides = {
        str(name): _minutes_to_seconds(minutes)
        for name, minutes in _load_json_dict(config.Run.TaskTimeLimitOverrides).items()
    }
    return default_seconds, overrides


def loop_guard_from_config(config: Any) -> bool:
    """读 Run.LoopGuard（原地打转检测，配置默认开）；读不到或写坏按关。"""

    try:
        return config.Run.LoopGuard is True
    except Exception:
        return False


def _load_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        with suppress(json.JSONDecodeError):
            data = json.loads(value)
            if isinstance(data, list):
                return [str(item) for item in data if str(item).strip()]
    return []


# worker 截图文件名是 ``[<前缀>.]<kind>-<HHMMSS>-<任务>.png``，信号证据图的 kind 与 worker
# 共用 worker_protocol.SIGNAL_SCREENSHOT_KINDS。
_SIGNAL_EVIDENCE_NAME_RE = re.compile(
    r"(?:^|\.)(?:"
    + "|".join(re.escape(kind) for kind in SIGNAL_SCREENSHOT_KINDS.values())
    + r")-\d{6}-"
)


def _signal_evidence_shot(result: Any) -> Any | None:
    """信号命中那个任务的证据图；找不到就不带图（宁缺勿错）。"""

    for shot in getattr(result, "failureScreenshots", None) or ():
        if shot.task == result.failedTask and _SIGNAL_EVIDENCE_NAME_RE.search(
            Path(shot.path).name
        ):
            return shot
    return None


def _is_unretryable_failure(message: str) -> bool:
    return any(marker in message for marker in _UNRETRYABLE_ENVIRONMENT_MARKERS)


def _result_failure_category(result: MaaFWRunResult) -> str | None:
    """worker 回报失败时尝试级的类别：只看结果里已有的字段与现有的环境级判定。

    返回 None 时由运行记录按任务结局补（任务都没开始是初始化失败）。
    """

    if result.resourceFailure is not None:
        return CATEGORY_RESOURCE_FAILURE
    if result.timedOut:
        return CATEGORY_RUN_TIMEOUT
    if _is_unretryable_failure(result.errorMessage or ""):
        return CATEGORY_ENVIRONMENT
    return None


_FAILURE_REASON_MAX_CHARS = 300


def _failure_reason_for_user(result: Any) -> str:
    """从运行结果里取一句可读的失败原因。

    runner 会把异常原文放进 ``errorMessage``，但它同时也用
    ``MaaFW 任务执行失败: {exc}`` 发一条日志——那条命中
    ``worker_protocol._RAW_FAILURE_UI_LOG_MARKERS`` 会被当框架噪声过滤掉。若这里再不取，
    Python 侧异常（如缺模块）在任务页上就只剩「任务执行失败」四个字。

    框架自身的失败原文可能是整段原生 backtrace，因此只取首个非空行并截断；
    完整内容仍在本次运行的 ``*.worker.log`` 里。
    """

    raw = str(
        getattr(result, "userMessage", None)
        or getattr(result, "errorMessage", "")
        or ""
    ).strip()
    if not raw:
        return ""
    first_line = next((line.strip() for line in raw.splitlines() if line.strip()), "")
    if not first_line:
        return ""
    while len(first_line) > _FAILURE_REASON_MAX_CHARS and "；" in first_line:
        first_line = first_line.rsplit("；", 1)[0]
    if len(first_line) > _FAILURE_REASON_MAX_CHARS:
        first_line = first_line[: _FAILURE_REASON_MAX_CHARS - 1] + "…"
    return first_line


def _failed_task_user_summary(result: Any, plan: Any | None) -> str:
    if getattr(result, "userMessage", None):
        return _failure_reason_for_user(result)
    failed_task = str(getattr(result, "failedTask", "") or "").strip()
    reason = _failure_reason_for_user(result)
    if not failed_task:
        # 还没投递任何任务就失败了（ADB 未就绪、Agent 连接超时、资源加载失败……）：
        # 不把原因挂到第一个任务头上，用户会去查错任务
        return f"MaaFW 运行失败{'：' + reason if reason else ''}"
    suffix = f"：任务执行失败{'：' + reason if reason else ''}"
    tasks = tuple(getattr(plan, "tasks", ()) or ()) if plan is not None else ()
    if tasks:
        for task in tasks:
            task_name = str(getattr(task, "name", "") or "").strip()
            task_entry = str(getattr(task, "entry", "") or "").strip()
            if failed_task and failed_task not in {task_name, task_entry}:
                continue
            return f"{_task_display_name(task)}{suffix}"
    return f"{failed_task or 'MaaFW 任务'}{suffix}"


def _task_display_name(task: Any) -> str:
    label = getattr(task, "label", None)
    # 红灯记录的 label 已在建计划时解析；用户自己起的名字可以以 $ 开头。
    queue_skipped = (
        isinstance(task, MaaFWSkippedTaskPlan)
        and task.reason == QUEUE_SKIPPED_TASK_REASON
    )
    if (
        isinstance(label, str)
        and label.strip()
        and (queue_skipped or not label.lstrip().startswith("$"))
    ):
        return label.strip()
    return str(getattr(task, "name", ""))


def _format_completed_task_labels(
    plan: MaaFWRunPlan | None,
    task_names: list[str],
) -> list[str]:
    labels_by_name = (
        {task.name: _task_display_name(task) for task in plan.tasks}
        if plan is not None
        else {}
    )
    return [labels_by_name.get(task_name, task_name) for task_name in task_names]


def _format_run_overview_log(
    plan: MaaFWRunPlan,
    *,
    selected_preset: str,
) -> str:
    task_names = " -> ".join(_task_display_name(task) for task in plan.tasks) or "-"
    if len(task_names) > _RUN_OVERVIEW_LOG_VALUE_LIMIT:
        task_names = task_names[:_RUN_OVERVIEW_LOG_VALUE_LIMIT] + "..."
    project_name = (
        plan.projectLabel.strip()
        if isinstance(plan.projectLabel, str)
        and plan.projectLabel.strip()
        and not plan.projectLabel.lstrip().startswith("$")
        else plan.projectName
    )
    project_version = str(plan.piEnv.get("PI_VERSION") or "").strip() or "未知"
    overview = (
        "MaaFW 运行总览: "
        f"project={project_name}; version={project_version}; "
        f"controller={plan.controllerName}; resource={plan.resourceName}; "
        f"preset={selected_preset or '自定义'}; "
        f"enabled_tasks({len(plan.tasks)})={task_names}"
    )
    if not plan.skippedTasks:
        return overview

    # 被跳过的任务此前没有任何出口，用户把任务加进队列却看不出它为什么没跑。
    skipped_names = " -> ".join(
        f"{_task_display_name(task)}({task.reason})" for task in plan.skippedTasks
    )
    if len(skipped_names) > _RUN_OVERVIEW_LOG_VALUE_LIMIT:
        skipped_names = skipped_names[:_RUN_OVERVIEW_LOG_VALUE_LIMIT] + "..."
    return f"{overview}; skipped_tasks({len(plan.skippedTasks)})={skipped_names}"


#: 任务报告里「失效任务」一行的前缀：队列里的任务 interface 已没有，本次跳过。
MISSING_TASK_NOTICE_PREFIX = (
    "失效任务（interface 内已无，已跳过，请到账号配置里重新添加）"
)
#: 其余任务都跑完、但队列里有失效任务时统计报告的结果：照常算完成，不说「全部完成」。
MISSING_TASK_USER_RESULT = "代理任务完成，但有失效任务"
#: 特调声明的 skip_on_retry_entries 在重试时被剔掉的原因（进 skippedTasks 与尝试日志）。
_RETRY_SKIP_REASON = RETRY_SKIP_REASON


def _retry_skipped_tasks(plan: MaaFWRunPlan) -> list[MaaFWSkippedTaskPlan]:
    return [task for task in plan.skippedTasks if task.reason == _RETRY_SKIP_REASON]


_PERIOD_DONE_LABELS = {
    PERIOD_DONE_REASONS["daily"]: "今日",
    PERIOD_DONE_REASONS["weekly"]: "本周",
    PERIOD_DONE_REASONS["monthly"]: "本月",
}


def _period_all_done_message(plan: MaaFWRunPlan) -> str:
    """队列里的任务都因周期限制被跳过时的提示，按实际跳过原因说今日 / 本周 / 本月。"""

    periods: list[str] = []
    for task in plan.skippedTasks:
        label = _PERIOD_DONE_LABELS.get(task.reason or "")
        if label and label not in periods:
            periods.append(label)
    ordered = [label for label in ("今日", "本周", "本月") if label in periods]
    # 运行日的说法只在跳过原因全是「不在运行日」（或再加周期已完成）时用；混了红灯、失效任务
    # 等别的原因时，照改动前这种情况原本的提示说
    reasons = [task.reason or "" for task in plan.skippedTasks]
    off_day = any(reason.endswith(OFF_DAY_REASON_SUFFIX) for reason in reasons)
    only_off_day_or_period = all(
        reason.endswith(OFF_DAY_REASON_SUFFIX) or reason in _PERIOD_DONE_LABELS
        for reason in reasons
    )
    if off_day and only_off_day_or_period and not ordered:
        return "MaaFW 队列里的任务今天都不在运行日，跳过本次运行"
    if off_day and only_off_day_or_period:
        return (
            f"MaaFW 队列里的任务今天不在运行日或已在{' / '.join(ordered)}完成，"
            "跳过本次运行"
        )
    if not periods:
        return "MaaFW 队列里的周期任务都已在本周期内完成，跳过本次运行"
    return f"MaaFW 队列里的周期任务都已在{' / '.join(ordered)}完成，跳过本次运行"


def _format_user_log_line(message: str) -> str:
    timestamp = datetime.now().astimezone().strftime("%H:%M:%S")
    lines = str(message).splitlines() or [""]
    return "".join(f"[{timestamp}] {line}\n" for line in lines)
