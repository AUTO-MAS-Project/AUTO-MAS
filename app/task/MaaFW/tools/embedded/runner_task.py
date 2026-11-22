from __future__ import annotations

import asyncio
import tempfile
import time
import uuid
from contextlib import suppress
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, Callable, Mapping

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
    HistoryWrite,
    WSTaskNoticeData,
)
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase
from app.services import execute_script_task
from app.task.client import client_executable_path, client_launcher_path
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
    describe_project_runtime_architecture_mismatch,
)
from app.task.MaaFW.tools.core.runner.models import (
    MaaFWDeviceConfig,
    MaaFWRunPlan,
    MaaFWRunResult,
)
from app.task.MaaFW.tools.core.runner.plan_transforms import (
    MaaFWPeriodLimits,
    PeriodRecords,
    filter_period_once_tasks,
    parse_period_records,
    period_records_after,
    skip_tasks_completed_this_run,
)
from app.task.MaaFW.tools.core.runner.run_events import (
    CATEGORY_SIGNAL,
    STAGE_CLIENT,
    STAGE_PRETASK,
)
from app.task.MaaFW.tools.core.runner.run_plan import (
    MaaFWRunPlanError,
    resolve_run_selection,
)
from app.task.MaaFW.tools.core.runner.service import MaaFWRunnerService
from app.task.MaaFW.tools.core.runner.task_selection import (
    MaaFWSnapshotExpansion,
    MaaFWSnapshotInspection,
    apply_plan_rules,
    attach_snapshot_findings,
    build_arranged_plan,
    describe_plan_failure,
    expand_task_snapshot,
    inspect_task_snapshot,
)
from app.task.run_flow import (
    begin_attempt,
    game_update_result,
    point,
)
from app.utils import UTC4, get_logger, power
from app.utils import game_apk as _utils_game_apk
from app.utils.common.game_resolution import (
    parse_resolution_option,
)
from app.utils.common.process.scope import (
    current_process_scope,
)
from app.utils.common.process.session import desktop_process_target

from .attempt_ledger import MaaFWAttemptLedger
from .desktop_game import (
    MaaFWDesktopGame,
    MaaFWDesktopGameSpec,
    describe_desktop_launch_error,
    desktop_launch_managed,
)
from .device_config import (
    WIN32_NO_WINDOW_RULES_MESSAGE,
    MaaFWAdbDeviceState,
    adb_ready_timeout,
    build_adb_control_profile,
    build_adb_device_config,
    build_win32_device_config,
    choose_game_package,
    find_controller,
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
from .host_client import (
    WORKSTATION_LOCKED_MESSAGE,
    open_emulator_for_run,
    script_adb_env,
    workstation_lock_reason,
)
from .option_secrets import (
    DPAPI_SECRET_OPENER,
    open_task_snapshot,
    script_task_snapshots,
    user_task_snapshot,
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
from .pretask_run import (
    MaaFWPretaskRunner,
    MaaFWPretaskRunRequest,
    pretasks_need_rerun,
)
from .project_path import (
    is_project_updating,
    release_run_reservation,
    try_reserve_project_path,
)
from .proxy_quota import (
    proxy_day_rolled,
    proxy_times_used_up,
    proxy_today,
    success_settlement,
)
from .resource_failure import (
    describe_resource_failure,
)
from .resource_repair import MaaFWRepairRequest, MaaFWResourceRepair
from .run_messages import (
    MISSING_TASK_NOTICE_PREFIX,
    describe_failed_result,
    format_completed_task_labels,
    format_run_overview_log,
    format_user_log_line,
    period_all_done_message,
    record_event_point,
    remaining_done_message,
    retry_skip_log_lines,
    signal_attempt_facts,
)
from .run_notices import (
    game_update_notice_text,
    statistics_mark,
    statistics_title,
    success_notice_text,
)
from .run_record import RUN_RECORD_HISTORY_KEY
from .run_redaction import (
    log_redaction_notice,
    project_log_secret_variants,
    run_secret_values,
    secret_log_variants,
)
from .run_settings import (
    load_json_dict,
    load_script_hotkeys,
    loop_guard,
    period_limits,
    task_time_limits,
)
from .run_verdict import (
    VERDICT_GAME_UPDATE_REQUIRED,
    VERDICT_SIGNAL,
    VERDICT_SUCCEEDED,
    judge_attempt,
)
from .run_verdict import MaaFWGameUpdateRequired as _MaaFWGameUpdateRequired
from .run_verdict import MaaFWWorkstationLocked as _MaaFWWorkstationLocked
from .signal_notice import (
    MAINTENANCE_LAST_STATUS,
    MAINTENANCE_SKIP_MESSAGE,
    SERVER_MAINTENANCE,
    SIGNAL_USER_MESSAGES,
    MaaFWSignalTracker,
)
from .update_credentials import resolve_update_proxy_url

logger = get_logger("MaaFW 插件自动代理")

# 桌面游戏启停的时限常量（等窗口、URL 拉起、兜底关闭）只在 desktop_game 里定义一份。
# 一次尝试算成功、信号、要更新游戏还是失败，失败了重不重试、先不先修资源、重不重启客户端，
# 都由 run_verdict.judge_attempt 判定（环境级失败的标记也在那里）；主循环只读判定。
# 给人看的文案（失败摘要、资源包失败停止、重跑的称呼、重试与周期提示）在 run_messages，
# 运行设置的原值解析（时限、原地打转、周期名单、键位）在 run_settings。
# 哪些 worker 日志 / 原生诊断进界面的几组文案规则在 worker_protocol（forwards_to_ui）：
# worker 发事件时按它定 audience，宿主只对旧格式事件与 stdout 上的原生诊断再用它判。


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
        # on_crash 记下的异常原文：还没进第一次尝试就崩了时，推送靠它说原因
        self._crash_message: str | None = None
        # 当前这次尝试给用户看的称呼（「第 2 次尝试」「清理残留后的重新运行」），与日志开头
        # 那行同口径：通知的任务详情和失败截图标签用它，不用 _record_attempt 的内部序号——
        # 清理后的重跑不计入尝试次数，内部序号会比日志多 1。
        self._attempt_title: str | None = None
        self._history_temp = tempfile.TemporaryDirectory(prefix="mas-maafw-run-")
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
        # Win32 桌面游戏（desktop_game）：开没开过、游戏刚启动的时刻、链接拉起的时刻、临时改过的
        # Unity 分辨率、AttachOnly 兜底关闭的分界都在它身上，跨尝试保留
        self._desktop = MaaFWDesktopGame(self._on_plan_run_event)
        # 模拟器路径上本轮游戏刚启动的单调时钟时刻（MAS 随模拟器把游戏拉到前台那一刻），据此算
        # 首个任务的最早下发时刻；None 表示游戏早就在跑。桌面路径用 _desktop.started_at。
        self.game_started_at: float | None = None
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
        # 资源包加载失败后的发行包核对（resource_repair）：每个账号每次运行只做一次，正在跑的核对
        # 任务留给释放项目预约前等；清理过就额外再跑一次（不占重试次数），``_extra_attempts`` 记
        # 多出来的几次。
        self._repair = MaaFWResourceRepair(self._append_log)
        self._extra_attempts = 0
        # 各次尝试的记账（attempt_ledger）：结构化运行记录、尝试结果、history 状态与附件，
        # 键是这次尝试的日志记录 id(cur_user_log)。_run_record 就是它里面的那份运行记录。
        self._ledger = MaaFWAttemptLedger()
        self._run_record = self._ledger.recorder

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
                return period_all_done_message(self.run_plan)

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
            # 提示音。与打开项目（project_session.reserve）那条「整个脚本一句话跳过，别让每个账号在
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
        self._desktop.mark_run_started(time.time())
        logger.info(f"开始代理 MaaFW 账号: {self.cur_user_uid}")
        if self.run_plan is not None:
            selected_preset = str(
                self.cur_user_config.Task.SelectedPreset or ""
            ).strip()
            self._append_log(
                format_run_overview_log(
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
                    with self._ledger.stage(
                        STAGE_PRETASK,
                        enabled=bool(getattr(self.run_plan, "pretasks", None)),
                    ):
                        await self._run_pretasks()
                    pretasks_done = True
                with self._ledger.stage(STAGE_CLIENT):
                    await self._ensure_desktop_game_started()
                    device_config = await self._build_device_config(
                        self.run_plan,
                        self.interface_model,
                    )
                result = await self._run_maafw(device_config)
            except Exception as exc:
                # 怎么走只读判定（run_verdict.judge_attempt），文案与通知照旧在这里发。
                verdict = judge_attempt(exc)
                message = str(verdict.message)
                if verdict.outcome == VERDICT_GAME_UPDATE_REQUIRED:
                    # 游戏客户端要手动更新：重试多少次都一样，本账号本次直接判失败。
                    # 说明已由 _ensure_game_updated 写进运行日志，这里不再重复。
                    self._record_attempt(
                        index + 1, [], message, category=verdict.category
                    )
                    if self.cur_user_log is not None:
                        await self.cur_user_log.set_state(status=message)
                    await Publisher.send(
                        id=self.task_info.task_id,
                        type=protocol.TASK_NOTICE,
                        data=WSTaskNoticeData(level="error", message=message),
                    )
                    with suppress(Exception):
                        title, text, ticker = game_update_notice_text(
                            self.cur_user_item.name, message
                        )
                        await Notify.send_notice(
                            LocalNotice(
                                title=title,
                                message=text,
                                ticker=ticker,
                                duration_seconds=3,
                            )
                        )
                    break
                self._append_log(message, warning=True)
                self._record_attempt(
                    index + 1,
                    [],
                    message,
                    user_message=verdict.user_message,
                    category=verdict.category,
                )
                if verdict.environment_unusable:
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
                if not verdict.retry:
                    break
                previous_failure = message
                if verdict.restart_client:
                    (
                        previous_restarted,
                        client_reset,
                    ) = await self._reset_client_for_retry(index + 1)
                continue

            await self._mark_period_tasks_completed(result.completedTasks)
            verdict = judge_attempt(result)
            if verdict.outcome == VERDICT_SIGNAL:
                # 项目声明的信号节点命中：停服维护 = 本次跳过，需要更新客户端 = 失败；
                # 两种都是重试多少次都一样，不重启游戏 / 模拟器，直接收尾。
                point(
                    self,
                    "run",
                    state="skipped" if verdict.maintenance else "failed",
                )
                await self._finish_on_signal(index + 1, result)
                break
            succeeded = verdict.outcome == VERDICT_SUCCEEDED
            point(self, "run", state="succeeded" if succeeded else "failed")
            if succeeded:
                self.run_complete = True
                if self.cur_user_log is not None:
                    await self.cur_user_log.set_state(status="Success!")
                completed_task_labels = format_completed_task_labels(
                    self.run_plan,
                    result.completedTasks,
                )
                self._append_log("MaaFW 任务完成: " + ", ".join(completed_task_labels))
                self._record_attempt(index + 1, completed_task_labels, None)
            else:
                if verdict.repair_resource and result.resourceFailure is not None:
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
                else:
                    message = describe_failed_result(
                        result,
                        self.run_plan,
                        run_time_limit=self.script_config.Run.RunTimeLimit,
                    )
                if self.cur_user_log is not None:
                    await self.cur_user_log.set_state(status=message)
                self._append_log(message, warning=True)
                self._record_attempt(
                    index + 1,
                    format_completed_task_labels(self.run_plan, result.completedTasks),
                    message,
                    user_message=result.userMessage,
                    failed_task=result.failedTask,
                    screenshots=[
                        (
                            format_completed_task_labels(self.run_plan, [shot.task])[0],
                            Path(shot.path),
                        )
                        for shot in result.failureScreenshots
                    ],
                    category=verdict.category,
                )
                if verdict.repair_resource and result.resourceFailure is not None:
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
                if not verdict.retry:
                    # worker 在任务里报的环境级失败（如原生库架构不符）：每轮都一样，
                    # 不再为它起停模拟器 / 游戏重试。
                    if verdict.environment_unusable:
                        self._append_log(
                            "运行环境不可用，重试也不会有别的结果，已停止本轮",
                            warning=True,
                        )
                    break
                await self._refresh_run_plan_after_period_update(result.completedTasks)
                if self.run_plan is not None and not self.run_plan.tasks:
                    self.run_complete = True
                    # 计划被重试跳过剔空的，不能说成「周期任务」
                    self._append_log(remaining_done_message(self.run_plan))
                else:
                    previous_failure = message
                    if verdict.restart_client:
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
            # 当天第一次成功才扣剩余天数（-1 不限不扣），代理次数加 1；逐条写、逐条提交
            remained_day, proxy_times = success_settlement(
                self.cur_user_config.Data.ProxyTimes,
                self.cur_user_config.Info.RemainedDay,
            )
            if remained_day is not None:
                self.cur_user_config.Info.RemainedDay = remained_day
                await self.cur_user_config.commit()
            self.cur_user_config.Data.ProxyTimes = proxy_times
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
                self._ledger.mark_error(id(self.cur_user_log))
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

    def _desktop_spec(self, *, for_close: bool = False) -> MaaFWDesktopGameSpec:
        """桌面游戏启停用到的配置原值（``desktop_game``），每个调用点现取。

        游戏 exe 与启动器来自客户端绑定（``client_executable_path`` / ``client_launcher_path``）：
        DirectExe 下 MAS 启动它，URL / AttachOnly 下只用来认出游戏。``Game.LaunchMode`` 配置
        激活后一定有默认值，这里的兜底只是防御性的。

        ``for_close``：收尾关游戏用。读客户端绑定出错不在这里抛，记进 spec 交给 ``desktop_game``
        在原来读路径的那一步再抛——没开过游戏时根本不读路径，开过的先关进程再抛。
        """

        game_path: Path | None = None
        launcher_path: Path | None = None
        game_path_error: Exception | None = None
        launcher_path_error: Exception | None = None
        try:
            raw = str(client_executable_path(self.script_config) or "").strip()
            game_path = Path(raw) if raw else None
        except Exception as exc:
            if not for_close:
                raise
            game_path_error = exc
        try:
            launcher_path = client_launcher_path(self.script_config)
        except Exception as exc:
            if not for_close:
                raise
            launcher_path_error = exc
        game = self.script_config.Game
        return MaaFWDesktopGameSpec(
            launch_mode=str(game.LaunchMode or "DirectExe").strip(),
            game_path=game_path,
            launcher_path=launcher_path,
            url=str(game.URL or "").strip(),
            arguments=game.Arguments,
            wait_seconds=game.WaitTime,
            unity_resolution=parse_resolution_option(game.UnityResolution),
            close_mode=str(game.CloseMode or "OnFailure").strip(),
            configured_hwnd=self.script_config.Device.HWnd,
            game_path_error=game_path_error,
            launcher_path_error=launcher_path_error,
        )

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
        elif run_plan.tasks and run_plan.controllerType == "Win32":
            spec = self._desktop_spec()
            if desktop_launch_managed(spec):
                game_path_error = describe_desktop_launch_error(spec)
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
        task_snapshot = load_json_dict(self.cur_user_config.Task.TaskSnapshot)
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
        script_hotkeys = load_script_hotkeys(self.script_config.Game.Hotkeys)
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
                return attach_snapshot_findings(
                    apply_plan_rules(plan, rules), inspection
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
                return build_arranged_plan(
                    self.project_path,
                    interface_model,
                    expansion=expansion,
                    inspection=inspection,
                    task_ids=arranged_ids,
                    task_options=arranged_options,
                    task_snapshot=task_snapshot,
                    controller_name=controller_name,
                    resource_name=resource_name,
                    script_hotkeys=script_hotkeys,
                    rules=rules,
                )
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
        self.opened_emulator = True
        # 开模拟器、冷启动游戏时打 launched 点与记时刻、静默时藏窗口（host_client）
        launch = await open_emulator_for_run(
            self.emulator_manager,
            emulator_index,
            package_name,
            silent=bool(Config.setting.Function.IfSilence),
            emit=self._on_plan_run_event,
        )
        device_info = launch.device_info
        # 冷启动游戏时首任务闸门改按读盘判据放行（task_start_gate）
        self.game_started_at = launch.started_at
        self.game_start_disk_quiet = launch.started_at is not None
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

    async def _script_adb_env(self) -> dict[str, str]:
        """脚本专用 adb server 的进程环境（``host_client.script_adb_env``）。"""

        return await script_adb_env(
            self.emulator_manager, game_device_id(self.script_config)
        )

    async def _run_maafw(self, device_config: MaaFWDeviceConfig) -> MaaFWRunResult:
        """取配置、组装入参，交给 ``plan_run`` 跑这份计划；事件转成账号日志、运行记录与进度点。"""

        plan = self.run_plan
        if plan is None:
            raise RuntimeError("MaaFW 运行计划尚未初始化")
        task_limit_seconds, task_limit_overrides = task_time_limits(
            self.script_config.Run.TaskTimeLimit,
            self.script_config.Run.TaskTimeLimitOverrides,
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
            loop_guard=loop_guard(self._loop_guard_raw()),
            run_secrets=secrets,
            project_log_secrets=project_log_secret_variants(
                secrets,
                script_task_snapshots(self.script_config),
                self.interface_model,
                DPAPI_SECRET_OPENER,
            ),
            redaction_notice=self._log_redaction_notice(),
            # 同一账号运行里只走一条路：Win32 是桌面游戏刚启动的时刻，ADB 是随模拟器冷启动的时刻
            game_started_at=(
                self._desktop.started_at
                if plan.controllerType == "Win32"
                else self.game_started_at
            ),
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
                self._ledger.add_attachments(attempt_key, run.attachments)
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

    def _loop_guard_raw(self) -> Any:
        """``Run.LoopGuard`` 的原值（原地打转检测，配置默认开）；读不到按关。"""

        try:
            return self.script_config.Run.LoopGuard
        except Exception:
            return None

    def _on_plan_run_event(self, event: MaaFWPlanRunEvent) -> None:
        """``plan_run`` 与 ``pretask_run`` 的事件出口：账号日志、进度点（以本任务为 owner）、运行记录。"""

        if isinstance(event, MaaFWPlanRunLog):
            self._append_log(event.message, warning=event.warning)
        elif isinstance(event, MaaFWPlanRunPoint):
            point(self, event.stage, state=event.state, key=event.key)
        elif isinstance(event, MaaFWPlanRunRecord):
            self._on_run_record_event(event.data)
        elif isinstance(event, MaaFWPlanRunStage):
            self._ledger.mark_stage(event.stage, event.ok)

    def _run_password_values(self) -> list[str]:
        """本次运行要打码的密码值（``run_redaction.run_secret_values``）：从配置里取出快照原值，
        密文经 DPAPI 认读。每个调用点现算，不缓存。"""

        return run_secret_values(
            self.run_plan,
            self.interface_model,
            user_task_snapshot(getattr(self, "cur_user_config", None)),
            DPAPI_SECRET_OPENER,
        )

    def _secret_log_variants(self) -> list[str]:
        """本次运行要打码的密码值在日志里可能出现的写法（见 run_redaction）。"""

        return secret_log_variants(self._run_password_values())

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
        return period_limits(
            run.DailyOnceTasks, run.WeeklyOnceTasks, run.MonthlyOnceTasks
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

        for line in retry_skip_log_lines(self.run_plan, self._retry_rerun_duplicates):
            self._append_log(line)

    def _load_period_task_records(self) -> PeriodRecords:
        return parse_period_records(
            load_json_dict(self.cur_user_config.Data.PeriodTaskRecords)
        )

    async def _mark_period_tasks_completed(self, completed_tasks: list[str]) -> None:
        if not completed_tasks:
            return
        limits = self._period_limits()
        if limits.empty:
            return

        new_records = period_records_after(
            load_json_dict(self.cur_user_config.Data.PeriodTaskRecords),
            limits,
            completed_tasks,
            datetime.now(tz=UTC4),
        )
        if new_records is not None:
            self.cur_user_config.Data.PeriodTaskRecords = new_records
            await self.cur_user_config.commit()

    async def _mark_run_started(self) -> None:
        if proxy_day_rolled(self.cur_user_config.Data.LastProxyDate, self.curdate):
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
        """Win32 场景下由 MAS 负责启动/激活桌面游戏客户端（``desktop_game``），供后续窗口解析使用。"""
        if self.run_plan is None or self.run_plan.controllerType != "Win32":
            return
        await self._desktop.ensure_started(
            self._desktop_spec(),
            interface=self.interface_model,
            controller_name=self.run_plan.controllerName,
            desktop=desktop_process_target.get(),
        )

    def _attempt_limit(self) -> int:
        """本账号这次运行最多跑几次：``Run.RunTimesLimit``，加上清理残留后额外的重跑。"""

        return int(self.script_config.Run.RunTimesLimit or 0) + self._extra_attempts

    async def _recover_resource_failure(self, kind: str) -> tuple[str, str] | None:
        """资源包加载失败之后与发行包核对（``resource_repair``）：视图换了载荷就返回下一次的
        （开头那行, 称呼）、该立刻再跑一次；其余情况它写一行停止原因、返回 None。"""

        from .embedded_project import follow_source_enabled, shell_hint_from_report
        from .update_credentials import resolve_update_credentials

        return await self._repair.run(
            kind,
            MaaFWRepairRequest(
                script_id=str(self.script_info.script_id),
                script_name=str(self.script_info.name or ""),
                follow_source=follow_source_enabled(self.script_config),
                channel=resolve_update_credentials(self.script_config).channel,
                proxy_url=resolve_update_proxy_url(self.script_config),
                shell_hint=shell_hint_from_report(self.script_config),
            ),
        )

    async def _reset_client_for_retry(self, attempt: int) -> tuple[bool, bool]:
        """重试前关掉 MAS 自己起的客户端，返回（是否全部关成, 是否已不在）。

        前者只决定下一轮日志开头写不写「已重启」；后者给运行前设置判断要不要重跑——
        关的时候报错，opened_* 也已清掉、下一轮会重新拉起，运行前设置同样要重来。
        """

        had_client = self._desktop.opened or self.opened_emulator
        restarted = await self._restart_client_before_retry(attempt)
        still_open = self._desktop.opened or self.opened_emulator
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
        if not self._desktop.opened and not self.opened_emulator:
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

    def _begin_run_record_attempt(self, attempt: int) -> None:
        """这次尝试的结构化记录：与本次尝试的日志（history 记录）同一个键。"""

        self._ledger.begin(
            id(self.cur_user_log),
            attempt=attempt,
            title=self._attempt_title,
            plan=self.run_plan,
        )

    def _run_record_statistic(self, key: int) -> HistorySnapshotStatistic | None:
        """某次尝试的运行记录，包成 history 的 snapshot 统计；没有记录返回 None。"""

        value = self._ledger.history_value(key)
        return HistorySnapshotStatistic(value=value) if value is not None else None

    def _on_run_record_event(self, data: Any) -> None:
        """将 worker 推来的阶段、任务起止事件归入本次尝试的专项记录。"""

        event = self._ledger.apply_record_event(data)
        task_point = record_event_point(event)
        if task_point is not None:
            name, state = task_point
            point(self, "special", key=name, state=state)
        if self._ledger.current_has_success():
            from app.core.script_update_queue import report_script_task_completed

            report_script_task_completed()

    def run_incident_notice(self) -> str:
        """本次运行里被原地打转检测或单任务时限停下的任务（见 ``attempt_ledger.incident_notice``）。"""

        return self._ledger.incident_notice(
            run_complete=self.run_complete,
            signal_message=self._signal_user_message(),
            check_passed=self.check_result == "Pass",
        )

    async def _finish_on_signal(self, attempt: int, result: MaaFWRunResult) -> None:
        """worker 回报了信号节点命中：记账、写日志状态。

        不发任务页提示（TASK_NOTICE 会在前端弹通知框并响提示音）：界面上只有 runner
        那行日志，正式通知由管理器收尾时按「信号 + 资源」各发一条（同一资源可能有
        多位用户）。证据图只进那条通知，不当失败截图进统计信息与汇总。
        """

        facts = signal_attempt_facts(
            result, self.run_plan, user_messages=SIGNAL_USER_MESSAGES
        )
        signal = facts.signal
        self.run_signal = signal
        point(self, "special", state="matched", key=signal)
        message = facts.message
        # runner 那行「游戏停服维护中，本轮剩余任务已跳过: <任务>」已进任务日志，
        # 这里只记后端日志，不在界面上再复述一遍。
        logger.warning(
            f"MaaFW 账号 {self.cur_user_item.name} 命中项目信号 {signal}"
            f"（节点 {facts.node}）：{message}"
        )
        # 证据图只随信号通知发一次，不进统计信息与代理结果汇总（facts.report_shots 已去掉它）；
        # 前面任务的普通失败截图照常进。
        self._record_attempt(
            attempt,
            facts.labels,
            message,
            screenshots=facts.report_shots,
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
        self.signal_tracker.record(
            signal,
            resource_name=facts.resource_name,
            resource_label=facts.resource_label,
            project_name=project_name,
            node=facts.node,
            user_id=str(self.cur_user_uid),
            user_name=self.cur_user_item.name,
            screenshot=facts.evidence_path,
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

    async def _close_game(self) -> bool:
        """关闭由 MAS 启动的游戏，返回是否关成（本来就没开过算关成）；见 ``desktop_game.close``。"""

        return await self._desktop.close(self._desktop_spec(for_close=True))

    async def _close_game_after_run(self, *, failed: bool) -> None:
        """最终收尾关游戏：MAS 启动的照常关，AttachOnly 再按 ``Game.CloseMode`` 兜底。

        ``failed`` 为真表示本次运行没正常完成（失败、超时、停止、``on_crash``）。重试之间
        走的是 ``_restart_client_before_retry``，不经这里，AttachOnly 下不关。
        """

        plan = self.run_plan
        await self._desktop.close_after_run(
            self._desktop_spec(for_close=True),
            interface=self.interface_model,
            controller_name=plan.controllerName if plan is not None else None,
            controller_type=plan.controllerType if plan is not None else None,
            failed=failed,
            desktop=desktop_process_target.get(),
        )

    async def _try_enter_project_path(self) -> bool:
        project_lock_key = await try_reserve_project_path(self.project_path)
        if project_lock_key is None:
            return False
        self.project_lock_key = project_lock_key
        return True

    async def _release_project_path(self) -> None:
        """交回本账号的项目预约（``project_path.release_run_reservation``）：停止时等作用域收尾、
        运行前设置的进程确认退出、资源包核对做完再放。"""

        if self.project_lock_key is None:
            return
        key, self.project_lock_key = self.project_lock_key, None
        await release_run_reservation(
            key,
            scope=current_process_scope.get(),
            pretask_exit_confirmation=self._pretasks.exit_confirmation,
            pending=self._repair.task,
        )

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
        """要用交互式桌面的控制器，锁屏时直接判失败，不进会重启游戏的重试。

        探测与告警在 ``host_client.workstation_lock_reason``（查不出来不拦）。
        """

        reason = await workstation_lock_reason(
            self.run_plan.controllerType if self.run_plan is not None else None,
            desktop_process_target.get(),
        )
        if reason is not None:
            raise _MaaFWWorkstationLocked(WORKSTATION_LOCKED_MESSAGE)

    def _release_display_hold(self) -> None:
        hold, self._display_hold = self._display_hold, None
        if hold is not None:
            hold.release()

    async def _freeze_notification_images(self) -> None:
        """归档会移动临时文件，通知及跨账号报告先持有自己的图片内容。"""
        self._notification_screenshots = []
        for label, path in self._ledger.failure_screenshots(
            run_complete=self.run_complete
        )[-NOTIFY_SCREENSHOT_LIMIT:]:
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
        self._ledger.finish_open(stopped=self.stopped_manually)
        records = []
        items = list(self.cur_user_item.iter_history_logs())
        for timestamp, log_item in items:
            status = self._ledger.history_status(
                id(log_item),
                stopped=self.stopped_manually,
                maintenance=self._is_maintenance_skip(),
            )
            record = HistoryWrite(
                time=timestamp.astimezone(UTC4),
                username=self.cur_user_item.name,
                script_name=self.script_info.name,
                status=status,
                message=log_item.status,
                logs="".join(log_item.content),
            )
            run_record = self._ledger.call(
                lambda: self._run_record_statistic(id(log_item))
            )
            if run_record is not None:
                record.data[RUN_RECORD_HISTORY_KEY] = run_record
            record.attachments.extend(
                HistoryAttachmentInput(
                    path=item.path,
                    kind=item.kind,
                    role=item.role,
                    display_name=item.display_name,
                )
                for item in self._ledger.attachments(id(log_item))
            )
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
        """记下本次尝试的结果（``attempt_ledger.record``），键是这次尝试的日志记录。

        这次尝试的日志还没有开始时刻时不记 history 状态（与原来同一判据）。
        """

        key = id(self.cur_user_log)
        self._ledger.record(
            key,
            status_key=key if self.cur_user_log_started_at is not None else None,
            attempt=attempt,
            title=self._attempt_title,
            completed=completed_labels,
            failure=failure,
            maintenance=self.run_signal == SERVER_MAINTENANCE,
            screenshots=screenshots,
            category=category,
            signal=signal,
            user_message=user_message,
            failed_task=failed_task,
        )

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

        return self._ledger.task_details(
            run_complete=self.run_complete,
            signal_message=self._signal_user_message(),
            check_passed=self.check_result == "Pass",
            missing=self.missing_task_notice(),
        )

    def _report_result(self, *, short: bool = False) -> str:
        """本账号这次的结果，账号级统计报告与托管级「代理结果」同一口径（见
        ``attempt_ledger.report_result``）。``short``：托管级每个账号一行用的简短说法。
        """

        return self._ledger.report_result(
            short=short,
            run_complete=self.run_complete,
            missing_task_names=self.missing_task_names,
            signal_message=self._signal_user_message(),
            check_passed=self.check_result == "Pass",
            check_status=(
                self.cur_user_log.status
                if self.cur_user_log is not None
                else self.check_result
            ),
            crash_message=getattr(self, "_crash_message", None),
        )

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
            mark = statistics_mark(
                run_complete=self.run_complete,
                has_missing=bool(self.missing_task_names),
                maintenance=self._is_maintenance_skip(),
            )
            await Notify.push_statistics_report(
                payload=_format_maafw.build_statistics_payload(
                    title=statistics_title(
                        datetime.now(), mark, self.cur_user_item.name
                    ),
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
            title, message, ticker = success_notice_text(
                self.cur_user_item.name, self.missing_task_names
            )
            await Notify.send_notice(
                LocalNotice(
                    title=title,
                    message=message,
                    ticker=ticker,
                    duration_seconds=3,
                )
            )
        except Exception as exc:
            logger.warning(f"MaaFW 插件用户通知发送失败: {exc}")

    def _append_log(self, message: str, *, warning: bool = False) -> None:
        # 失败类的账号日志按 WARNING 进 app.log，事后按级别筛得出来
        (logger.warning if warning else logger.info)(message)
        if self.cur_user_log is None:
            self._pending_user_log.append(format_user_log_line(message))
            return
        record = self.cur_user_log

        async def publish():
            await record.append_content(format_user_log_line(message))
            content = record.content
            await self.script_info.set_log("".join(content))

        self.callbacks.submit(publish())
