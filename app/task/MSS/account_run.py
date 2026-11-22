#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""MSS 一个账号这一轮的运行（账号级流程）。

由 ``manager.MSSManager`` 每个账号建一个、直接调 ``main_task``，收尾经 ``_run_final_task``。
写法照通用 MFW 的账号流程（``MaaFW/tools/embedded/runner_task``）逐段对应，差别只在 MSS 自己的几步：

- 建计划分三段，都包在 ``check`` 原来那个 shield 循环里（用户这时停止，照样等这一整段做完）：
  工作线程里读 interface、展开任务快照（规则表是空表）、取计划表今天那一格、``arrange.mss_arrange_head``；
  回到事件循环，前半段说要查时才 ``await stella.has_running_official_activity()``（每次运行最多查一次，
  出错同样算「无法构建运行计划」）；再进工作线程 ``arrange.mss_arrange_tail``、按排好的队列建计划、周期过滤、
  桌面检查。日志先后与一次排完时一字不差。活动探测在事件循环上查（旧的风味路径在工作线程里查），
  这是与通用流程跑 MSS 时唯一的差别；
- 没有运行前登录、游戏更新与登录交给首任务（ADB 也照样能跑：``ask_toolkit`` 恒为假，设备配置不插步骤）；
- 重试：剔除本次运行已完成的任务用 ``MSS_SKIP_ON_RETRY``。

跑计划、运行前设置、判定、记账、桌面游戏启停、开模拟器、文案与通知正文都调 ``MaaFW/tools/embedded``
里的叶子，只传普通数据；读写配置一律经 ``config_view``。日志、进度点、历史与通知的先后与通用流程完全相同
（logger 名、``lease_owner`` 也照旧）。
"""

from __future__ import annotations

import asyncio
import tempfile
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, Callable, Mapping

import app.core.notify.formats.maafw as _format_maafw
from app.core import Notify, Publisher
from app.core.notify.task_content import (
    NOTIFY_SCREENSHOT_LIMIT,
    prepare_screenshot_images,
    screenshot_entries,
)
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
from app.task.emulator_core import close_emulator
from app.task.MaaFW.tools.core.controller_win32.service import (
    controller_has_window_rules,
)
from app.task.MaaFW.tools.core.interface.agent_command import MaaFWAgentCommandPlan
from app.task.MaaFW.tools.core.interface.models import MaaFWInterface
from app.task.MaaFW.tools.core.interface.plan_rules import EMPTY_PLAN_RULES
from app.task.MaaFW.tools.core.interface.preview import interface_display_name
from app.task.MaaFW.tools.core.interface.service import MaaFWInterfaceService
from app.task.MaaFW.tools.core.native.project_runtime import (
    describe_project_runtime_architecture_mismatch,
)
from app.task.MaaFW.tools.core.runner.models import (
    MaaFWDeviceConfig,
    MaaFWRunPlan,
    MaaFWRunResult,
)
from app.task.MaaFW.tools.core.runner.plan_transforms import (
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
from app.task.MaaFW.tools.core.runner.run_plan import MaaFWRunPlanError
from app.task.MaaFW.tools.core.runner.task_selection import (
    MaaFWSnapshotExpansion,
    MaaFWSnapshotInspection,
    build_arranged_plan,
    describe_plan_failure,
    expand_task_snapshot,
    inspect_task_snapshot,
)
from app.task.MaaFW.tools.embedded.attempt_ledger import MaaFWAttemptLedger
from app.task.MaaFW.tools.embedded.desktop_game import (
    MaaFWDesktopGame,
    describe_desktop_launch_error,
    desktop_launch_managed,
)
from app.task.MaaFW.tools.embedded.device_config import (
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
from app.task.MaaFW.tools.embedded.host_client import (
    WORKSTATION_LOCKED_MESSAGE,
    open_emulator_for_run,
    script_adb_env,
    workstation_lock_reason,
)
from app.task.MaaFW.tools.embedded.option_secrets import (
    DPAPI_SECRET_OPENER,
    open_task_snapshot,
)
from app.task.MaaFW.tools.embedded.plan_run import (
    MaaFWPlanRun,
    MaaFWPlanRunEvent,
    MaaFWPlanRunLog,
    MaaFWPlanRunPoint,
    MaaFWPlanRunRecord,
    MaaFWPlanRunRequest,
    MaaFWPlanRunStage,
)
from app.task.MaaFW.tools.embedded.pretask_run import (
    MaaFWPretaskRunner,
    MaaFWPretaskRunRequest,
    pretasks_need_rerun,
)
from app.task.MaaFW.tools.embedded.project_path import (
    is_project_updating,
    release_run_reservation,
    try_reserve_project_path,
)
from app.task.MaaFW.tools.embedded.proxy_quota import (
    proxy_day_rolled,
    proxy_today,
    success_settlement,
)
from app.task.MaaFW.tools.embedded.resource_failure import describe_resource_failure
from app.task.MaaFW.tools.embedded.resource_repair import MaaFWResourceRepair
from app.task.MaaFW.tools.embedded.run_messages import (
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
from app.task.MaaFW.tools.embedded.run_notices import (
    statistics_mark,
    statistics_title,
    success_notice_text,
)
from app.task.MaaFW.tools.embedded.run_record import RUN_RECORD_HISTORY_KEY
from app.task.MaaFW.tools.embedded.run_redaction import (
    log_redaction_notice,
    project_log_secret_variants,
    run_secret_values,
    secret_log_variants,
)
from app.task.MaaFW.tools.embedded.run_settings import (
    load_json_dict,
    load_script_hotkeys,
    loop_guard,
    task_time_limits,
)
from app.task.MaaFW.tools.embedded.run_verdict import (
    VERDICT_SIGNAL,
    VERDICT_SUCCEEDED,
    MaaFWWorkstationLocked,
    judge_attempt,
)
from app.task.MaaFW.tools.embedded.signal_notice import (
    MAINTENANCE_LAST_STATUS,
    MAINTENANCE_SKIP_MESSAGE,
    SERVER_MAINTENANCE,
    SIGNAL_USER_MESSAGES,
    MaaFWSignalTracker,
)
from app.task.MSS import config_view
from app.task.MSS.arrange import (
    MSSArrangeState,
    mss_arrange_head,
    mss_arrange_tail,
)
from app.task.MSS.rules import MSS_SKIP_ON_RETRY
from app.task.run_flow import begin_attempt, point
from app.utils import UTC4, get_logger, power
from app.utils.common.process.scope import current_process_scope
from app.utils.common.process.session import desktop_process_target

# 与通用 MFW 的账号流程同名：app.log 的检索习惯不变
logger = get_logger("MaaFW 插件自动代理")


class MSSAccountRun(TaskExecuteBase):
    """MSS 一个账号这一轮的 AutoProxy 运行。"""

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
        # 配置对象只当句柄：读写经 config_view；close_emulator / resolve_host_adb 按任务对象读它
        self.script_config = script_config
        self.user_config = user_config
        self.emulator_manager = emulator_manager
        self.project_update_logs = list(project_update_logs or [])
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config = self.user_config[self.cur_user_uid]
        self.project_path = config_view.project_root(
            str(self.script_info.script_id), self.script_config
        ).resolve()
        self.interface_model: MaaFWInterface | None = None
        self.base_run_plan: MaaFWRunPlan | None = None
        self.run_plan: MaaFWRunPlan | None = None
        # 本账号这一轮第一次借运行环境时 agent 环境算出的 agent 命令计划，重试沿用
        self._worker_agent_plans: tuple[MaaFWAgentCommandPlan, ...] | None = None
        self.cur_user_log: LogRecord | None = None
        # 运行前检查时本账号的日志还没建（排队列的提示就在这时候到），先攒在这里，
        # prepare() 建好日志时并进去
        self._pending_user_log: list[str] = []
        # user_start_time 是本账号这一轮的开始（统计通知用），cur_user_log_started_at 是当前
        # 这次尝试的开始（日志记录与 history 文件名用）
        self.user_start_time: datetime | None = None
        self.cur_user_log_started_at: datetime | None = None
        # on_crash 记下的异常原文：还没进第一次尝试就崩了时，推送靠它说原因
        self._crash_message: str | None = None
        # 当前这次尝试给用户看的称呼（「第 2 次尝试」「清理残留后的重新运行」）
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
        # Win32 桌面游戏（desktop_game）：开没开过、游戏刚启动的时刻等都在它身上，跨尝试保留
        self._desktop = MaaFWDesktopGame(self._on_plan_run_event)
        # 模拟器路径上本轮游戏刚启动的单调时钟时刻；None 表示游戏早就在跑。桌面路径用
        # _desktop.started_at。
        self._emulator_started_at: float | None = None
        # 模拟器冷启动游戏时为真：首任务闸门改按读盘判据放行。桌面路径始终为假。
        self._disk_quiet = False
        self.project_lock_key: str | None = None
        # 正在跑的那一份计划（plan_run）：停止时经它结束 worker
        self._plan_run: MaaFWPlanRun | None = None
        # 项目的运行前设置（pretask_run）：跨尝试共用一份
        self._pretasks = MaaFWPretaskRunner(self._on_plan_run_event)
        # ADB 地址、路径与控制档案：同一次模拟器启动内只解析一次，关模拟器时清
        self._adb_state = MaaFWAdbDeviceState()
        self.maafw_runtime_pool_root: Path | None = None
        self.maafw_runtime_pool_id: str | None = None
        # 本轮（整个脚本）的信号账，管理器传入共享的一份。
        self.signal_tracker = signal_tracker or MaaFWSignalTracker()
        # 本账号这次运行命中的信号（worker 回报），决定收尾怎么结算。
        self.run_signal: str | None = None
        # 运行前检查发现同一资源本轮已确认在维护、本账号没启动就跳过。
        self.maintenance_skipped = False
        # 运行前检查时项目预约被占，本账号没跑成。
        self.project_busy_skipped = False
        # 队列里 interface 已没有的任务名（项目更新改了 name），建计划时填，进任务报告
        self.missing_task_names: list[str] = []
        # 本次运行里各次尝试已完成的任务名（累计，按份数）：重试时剔掉 MSS_SKIP_ON_RETRY 里的
        self._completed_this_run: list[str] = []
        # 已完成过、但在队列里有多份同名的任务名：重试时不剔、全部重跑，开头写一行说明
        self._retry_rerun_duplicates: list[str] = []
        # 本次尝试的原生 ERR 行：资源包加载失败时据此说出具体原因
        self._attempt_native_errors: list[str] = []
        # 资源包加载失败后的发行包核对（resource_repair）：每个账号每次运行只做一次
        self._repair = MaaFWResourceRepair(self._append_log)
        self._extra_attempts = 0
        # 各次尝试的记账（attempt_ledger），键是这次尝试的日志记录 id(cur_user_log)
        self._ledger = MaaFWAttemptLedger()

    # ------------------------------------------------------------------
    # 运行前检查
    # ------------------------------------------------------------------

    async def check(self) -> str:
        # 与管理器筛账号同一判据（proxy_quota）：全员到上限时管理器不做运行前更新
        if config_view.proxy_times_used_up(
            self.cur_user_config, self.script_config, self.curdate
        ):
            await self.cur_user_item.set_state(status="跳过")
            return "今日代理次数已达上限，跳过该账号"

        if not await self._try_enter_project_path():
            # 项目被占着没跑成：记「异常」而不是「跳过」
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
                # 运行计划在工作线程里构建，排队列的账号日志要回到事件循环线程再写
                loop.call_soon_threadsafe(self._append_log, message)

            try:
                # 建计划（两段工作线程，中间在事件循环上查一次活动排期）可能提交配置；取消后先等这一整段
                # 做完，不能让它越过 X 锁释放。
                build_task = asyncio.create_task(self._load_run_state(send_plan_log))
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

            # 本轮前面的用户已经撞上同一资源的停服维护：不再拉起游戏 / 模拟器
            maintenance = self.signal_tracker.maintenance(self.run_plan.resourceName)
            if maintenance is not None:
                maintenance.add_user(str(self.cur_user_uid), self.cur_user_item.name)
                await self.cur_user_item.set_state(status="跳过")
                self.maintenance_skipped = True
                return MAINTENANCE_SKIP_MESSAGE

            if self.run_plan.controllerType == "Adb":
                emulator_id = config_view.emulator_target(self.script_config)
                emulator_index = config_view.emulator_device(self.script_config)
                if emulator_id == "-" or emulator_index in ("", "-"):
                    await self.cur_user_item.set_state(status="异常")
                    return (
                        "当前 MaaFW controller 需要 ADB，请在托管管理页选择模拟器和实例"
                    )
            elif game_path_error is not None:
                await self.cur_user_item.set_state(status="异常")
                return game_path_error

            # 项目自带的 MaaFramework 与本机架构不符时 worker 里必然加载失败：先说清楚
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
        source = config_view.source_path(self.script_config)
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

    # ------------------------------------------------------------------
    # 主流程与重试
    # ------------------------------------------------------------------

    async def main_task(self) -> None:
        self.curdate = proxy_today()
        self.check_result = await self.check()
        if self.check_result != "Pass":
            # 也记一行后端日志；「异常」按 WARNING，「跳过」按 INFO
            (logger.warning if self.cur_user_item.status == "异常" else logger.info)(
                f"MFW 用户运行前检查未通过（{self.cur_user_item.name}，{self.cur_user_item.status}）：{self.check_result}"
            )
            # 项目被占用不逐个弹窗
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
                # 维护连带跳过、或项目被占用没跑成：记一份本账号的日志，让代理结果汇总与
                # 统计信息写明原因
                await self.prepare()
                self._append_log(self.check_result)
                if self.cur_user_log is not None:
                    await self.cur_user_log.set_state(status=self.check_result)
            else:
                # 没有本账号的日志：窗口只剩检查结果这一行
                await self.script_info.set_log(self.check_result)
            return

        await self._mark_run_started()
        await self.prepare()
        await self.cur_user_item.set_state(status="运行")
        # AttachOnly 兜底关闭的分界：之后才出现的游戏 / 启动器才算本次运行打开的
        self._desktop.mark_run_started(time.time())
        logger.info(f"开始代理 MaaFW 账号: {self.cur_user_uid}")
        if self.run_plan is not None:
            self._append_log(
                format_run_overview_log(
                    self.run_plan,
                    selected_preset=config_view.selected_preset(self.cur_user_config),
                )
            )
            for warning in self.run_plan.warnings:
                self._append_log(f"MaaFW 运行计划提示: {warning}")

        # 整个账号运行期间保持显示开启，屏已熄就先叫醒；收尾时撤销，final_task 再兜一次。
        self._ensure_display_hold()
        self._user_teardown_pending = True
        # 执行任务前脚本（每账号仅一次，重试不重复跑）。
        enabled, before_path = config_view.script_before_task(self.cur_user_config)
        if enabled:
            await execute_script_task(before_path, "脚本前任务")

        # 上一次尝试的失败摘要与是否重启过客户端：新一次另起日志后在开头写一句
        previous_failure: str | None = None
        previous_restarted = False
        # 运行前设置放进每次尝试里：它自己失败要能重试；客户端被关后重试也要靠它重新拉起
        pretasks_done = False
        # 上一次失败后 MAS 自己起的游戏 / 模拟器是否已关掉，这时运行前设置要重跑
        client_reset = False
        # 资源包加载失败后换了载荷、立刻再跑的那一次不计入尝试次数
        rerun_note: tuple[str, str] | None = None
        previous_label = ""
        index = -1
        while True:
            # 不用 range：资源包加载失败后清理过载荷时额外再跑一次（_extra_attempts），上限会变。
            index += 1
            if index >= self._attempt_limit() or self.run_complete:
                break
            begin_attempt(self, index + 1)

            # 每次尝试单独一份日志：第一次沿用 prepare() 建的那份，之后每次另起。
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
                    f"{ordinal}/{config_view.run_times_limit(self.script_config)}"
                )
                current_label = f"第 {ordinal} 次"
                self._attempt_title = f"{current_label}尝试"
            if index > 0 and previous_failure:
                self._append_log(
                    f"上一次（{previous_label}）：{previous_failure}"
                    + ("，已重启游戏/模拟器" if previous_restarted else "")
                )
            previous_label = current_label
            self._ledger.begin(
                id(self.cur_user_log),
                attempt=index + 1,
                title=self._attempt_title,
                plan=self.run_plan,
            )

            try:
                if index > 0:
                    self._log_retry_skipped_tasks()
                if self.run_plan is None or self.interface_model is None:
                    raise RuntimeError("MaaFW 运行计划尚未初始化")
                self._ensure_display_hold()
                # 放在运行前设置之前：锁屏时截图和输入用不了，进了重试还会白白重启游戏。
                await self._ensure_workstation_unlocked()
                if not pretasks_done or await self._pretasks_need_rerun(client_reset):
                    # 先清标记：重跑到一半失败时，下一轮不能因为窗口已被拉起就跳过
                    pretasks_done = False
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
                # 项目声明的信号节点命中：不重启游戏 / 模拟器，直接收尾。
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
                    # 资源包没能加载：原因只在原生 ERR 行里，换成一句人话
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
                        run_time_limit=config_view.run_time_limit(self.script_config),
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
                    # 不重启游戏 / 模拟器；只有视图换过载荷时立刻再跑一次（不占重试次数）。
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
                    # worker 在任务里报的环境级失败：每轮都一样，不再重试。
                    if verdict.environment_unusable:
                        self._append_log(
                            "运行环境不可用，重试也不会有别的结果，已停止本轮",
                            warning=True,
                        )
                    break
                await self._refresh_plan(result.completedTasks)
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

    # ------------------------------------------------------------------
    # 收尾
    # ------------------------------------------------------------------

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
            enabled, after_path = config_view.script_after_task(self.cur_user_config)
            if enabled:
                await execute_script_task(after_path, "脚本后任务")
        self._release_display_hold()
        await self._shutdown_runner()
        if self.check_result != "Pass":
            if self.maintenance_skipped:
                # 维护连带跳过：同样是跳过不是失败，代理次数不动
                await config_view.set_last_proxy_status(
                    self.cur_user_config, MAINTENANCE_LAST_STATUS
                )
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
                config_view.proxy_times(self.cur_user_config),
                config_view.remained_day(self.cur_user_config),
            )
            if remained_day is not None:
                await config_view.set_remained_day(self.cur_user_config, remained_day)
            await config_view.set_proxy_times(self.cur_user_config, proxy_times)
            await config_view.set_last_proxy_status(self.cur_user_config, "成功")
            await self.cur_user_item.set_state(status="完成")
        elif self.run_signal == SERVER_MAINTENANCE:
            # 维护是跳过不是失败：代理次数、剩余天数不动
            await config_view.set_last_proxy_status(
                self.cur_user_config, MAINTENANCE_LAST_STATUS
            )
            await self.cur_user_item.set_state(status="跳过")
        else:
            await config_view.set_last_proxy_status(self.cur_user_config, "失败")
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

    # ------------------------------------------------------------------
    # 建计划（工作线程）
    # ------------------------------------------------------------------

    async def _load_run_state(
        self,
        send_log: Callable[[str], None] | None = None,
    ) -> tuple[MaaFWInterface, MaaFWRunPlan, MaaFWRunPlan, str | None]:
        """建这一轮的计划：工作线程（前半段）→ 事件循环（按需查一次活动排期）→ 工作线程（后半段）。

        ``check`` 用原来那个 shield 循环等这整个协程：用户这时点停止，照样等它做完。
        """

        head = await asyncio.to_thread(self._plan_head, send_log)
        running: bool | None = None
        # 只在前半段说要查时查（活动不在队列里要补 / 在队列里要判，两者互斥），每次运行最多一次
        if head.state.probe_needed:
            # 按需导入、按模块属性调：本包在导入期不拉起网络模块
            from app.tools.common.game_calendar import stella

            try:
                running = await stella.has_running_official_activity()
            except Exception as exc:
                raise MaaFWRunPlanError(
                    describe_plan_failure(str(exc), head.inspection, head.expansion)
                ) from exc
        return await asyncio.to_thread(self._plan_tail, head, running, send_log)

    def _plan_head(self, send_log: Callable[[str], None] | None) -> "_PlanHead":
        """前半段（工作线程）：读 interface、展开任务快照、套计划表，算出要不要查活动排期。"""

        interface_model = MaaFWInterfaceService().load(self.project_path)
        # 账号页上配的任务队列就是唯一的任务来源（不看 Info.IfQuickConfig）。
        task_snapshot = load_json_dict(
            config_view.task_snapshot_raw(self.cur_user_config)
        )
        selected_preset = config_view.selected_preset(self.cur_user_config)
        controller_name, resource_name = config_view.run_selection(
            self.script_config, interface_model
        )
        effective_preset = (
            selected_preset if selected_preset and not task_snapshot else None
        )
        # 托管级键位（Game.Hotkeys）：坏 JSON / 不是对象当空，字段级的校验在建计划时做。
        script_hotkeys = load_script_hotkeys(
            config_view.hotkeys_raw(self.script_config)
        )
        # 本方法在工作线程里跑：没给线程安全的回调就只进后端日志。
        log = send_log if send_log is not None else logger.info
        inspection: MaaFWSnapshotInspection | None = None
        expansion: MaaFWSnapshotExpansion | None = None
        try:
            # 密码字段在配置里是密文，只在这份内存副本里解开交给计划。
            task_snapshot = open_task_snapshot(task_snapshot, interface_model)
            # 运行日按本机今天的星期判，只在开跑建计划时判这一次。
            iso_weekday = datetime.now().isoweekday()
            inspection = inspect_task_snapshot(
                self.project_path,
                interface_model,
                task_snapshot,
                iso_weekday=iso_weekday,
            )
            self.missing_task_names = list(dict.fromkeys(inspection.missing_task_names))
            # 先展开任务快照（剔掉今天不在运行日的实例；MSS 没有规则表），再按 MSS 的规矩排队列。
            expansion = expand_task_snapshot(
                self.project_path,
                interface_model,
                task_snapshot=task_snapshot,
                selected_preset=effective_preset,
                iso_weekday=iso_weekday,
                rules=EMPTY_PLAN_RULES,
                inspection=inspection,
            )
            for line in expansion.notices:
                log(line)
            # 日常：计划表今天那一格改写悬赏试炼。红灯与今天不跑的实例不自动补回（按任务名比）。
            plan_key = config_view.plan_slot(self.cur_user_config, log)
            state = mss_arrange_head(
                interface_model,
                list(expansion.task_ids),
                dict(expansion.task_options),
                excluded_ids=expansion.excluded_task_ids,
                plan_key=plan_key,
                if_activity_first=config_view.if_activity_first_raw(
                    self.cur_user_config
                ),
                log=log,
            )
        except Exception as exc:
            raise MaaFWRunPlanError(
                describe_plan_failure(str(exc), inspection, expansion)
            ) from exc
        return _PlanHead(
            interface_model=interface_model,
            task_snapshot=task_snapshot,
            controller_name=controller_name,
            resource_name=resource_name,
            script_hotkeys=script_hotkeys,
            inspection=inspection,
            expansion=expansion,
            state=state,
        )

    def _plan_tail(
        self,
        head: "_PlanHead",
        running: bool | None,
        send_log: Callable[[str], None] | None,
    ) -> tuple[MaaFWInterface, MaaFWRunPlan, MaaFWRunPlan, str | None]:
        """后半段（工作线程）：按活动排期处理活动任务、爬塔归位，按排好的队列建计划，再做周期过滤
        与桌面检查。"""

        interface_model = head.interface_model
        log = send_log if send_log is not None else logger.info
        try:
            arranged_ids, arranged_options = mss_arrange_tail(
                head.state, running, interface_model=interface_model, log=log
            )
            # 其余停跑日实例在建计划前排除、记成跳过（不校验选项），全被排除时计划为空。
            base_run_plan = build_arranged_plan(
                self.project_path,
                interface_model,
                expansion=head.expansion,
                inspection=head.inspection,
                task_ids=arranged_ids,
                task_options=arranged_options,
                task_snapshot=head.task_snapshot,
                controller_name=head.controller_name,
                resource_name=head.resource_name,
                script_hotkeys=head.script_hotkeys,
                rules=EMPTY_PLAN_RULES,
            )
        except Exception as exc:
            raise MaaFWRunPlanError(
                describe_plan_failure(str(exc), head.inspection, head.expansion)
            ) from exc
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
            and (not optional_int(config_view.configured_hwnd(self.script_config)))
            and (
                not controller_has_window_rules(
                    find_controller(interface_model, run_plan.controllerName)
                )
            )
        ):
            # 控制器一条窗口匹配规则都没写，又没指定句柄：在拉起游戏之前就报。
            game_path_error = WIN32_NO_WINDOW_RULES_MESSAGE
        elif run_plan.tasks and run_plan.controllerType == "Win32":
            spec = config_view.desktop_spec(self.script_config)
            if desktop_launch_managed(spec):
                game_path_error = describe_desktop_launch_error(spec)
        return interface_model, base_run_plan, run_plan, game_path_error

    # ------------------------------------------------------------------
    # 设备配置
    # ------------------------------------------------------------------

    async def _build_device_config(
        self,
        plan: MaaFWRunPlan,
        interface_model: MaaFWInterface,
    ) -> MaaFWDeviceConfig:
        """取配置原值与模拟器入口，交给 ``device_config`` 换算成设备配置。

        MSS 没有运行前登录与游戏更新：ADB（引擎不拦）不插任何步骤、不问 Toolkit，Win32 直接找窗口。
        """
        if plan.controllerType == "Adb":
            state = self._adb_state
            address, device_info = await self._resolve_adb_address()
            if state.adb_path is None:
                state.adb_path = await resolve_adb_path(
                    self.emulator_manager,
                    config_view.emulator_device(self.script_config),
                    configured_path=config_view.adb_path_raw(self.script_config),
                    device_info=device_info,
                    log=self._append_log,
                )
            # MSS 没有运行前登录：宿主没定下 adb 路径时也不去问 Toolkit
            adb_path = await resolve_login_adb_path(
                address,
                state.adb_path,
                ask_toolkit=False,
                log=self._append_log,
            )
            if state.profile is None:
                state.profile = await build_adb_control_profile(
                    self.emulator_manager,
                    target_id=config_view.emulator_target(self.script_config),
                    device_uid=config_view.emulator_device(self.script_config),
                    log=self._append_log,
                )
            screencap_methods, input_methods = config_view.adb_methods_raw(
                self.script_config
            )
            return build_adb_device_config(
                address=address,
                adb_path=adb_path,
                profile=state.profile,
                device_info=device_info,
                configured_screencap_methods=screencap_methods,
                configured_input_methods=input_methods,
                ready_timeout=adb_ready_timeout(self.emulator_manager),
            )

        if plan.controllerType == "Win32":
            controller = find_controller(interface_model, plan.controllerName)
            hwnd = await resolve_window_handle(
                controller,
                config_view.configured_hwnd(self.script_config),
                log=self._append_log,
            )
            screencap, mouse, keyboard = config_view.win32_methods_raw(
                self.script_config
            )
            return build_win32_device_config(
                controller,
                hwnd,
                configured_screencap_method=screencap,
                configured_mouse_method=mouse,
                configured_keyboard_method=keyboard,
                log=self._append_log,
            )

        raise RuntimeError(f"当前仅支持 Adb/Win32 controller: {plan.controllerType}")

    async def _resolve_adb_address(self) -> tuple[str, DeviceInfo | None]:
        state = self._adb_state
        if state.address is not None:
            return state.address, state.device_info
        if self.emulator_manager is None:
            raise RuntimeError("当前 controller 需要 ADB，请在托管管理页选择模拟器")

        emulator_index = config_view.emulator_device(self.script_config)
        if emulator_index in ("", "-"):
            raise RuntimeError("当前 controller 需要 ADB，请在托管管理页选择模拟器实例")

        package_name = await choose_game_package(
            config_view.game_package_name(self.script_config),
            self.run_plan,
            log=self._append_log,
        )
        self.opened_emulator = True
        # 开模拟器、冷启动游戏时打 launched 点与记时刻、静默时藏窗口（host_client）
        launch = await open_emulator_for_run(
            self.emulator_manager,
            emulator_index,
            package_name,
            silent=config_view.silent_mode(),
            emit=self._on_plan_run_event,
        )
        device_info = launch.device_info
        # 冷启动游戏时首任务闸门改按读盘判据放行（task_start_gate）
        self._emulator_started_at = launch.started_at
        self._disk_quiet = launch.started_at is not None
        if not device_info.adb_address or device_info.adb_address == "Unknown":
            raise RuntimeError("模拟器未返回可用 ADB 地址")

        state.address = device_info.adb_address
        state.device_info = device_info
        self._append_log(f"模拟器启动完成，ADB 地址: {device_info.adb_address}")
        return device_info.adb_address, device_info

    # ------------------------------------------------------------------
    # 跑计划
    # ------------------------------------------------------------------

    async def _run_maafw(self, device_config: MaaFWDeviceConfig) -> MaaFWRunResult:
        """取配置、组装入参，交给 ``plan_run`` 跑这份计划；事件转成账号日志、运行记录与进度点。"""

        plan = self.run_plan
        if plan is None:
            raise RuntimeError("MaaFW 运行计划尚未初始化")
        task_limit_raw, task_overrides_raw = config_view.task_time_limit_raw(
            self.script_config
        )
        task_limit_seconds, task_limit_overrides = task_time_limits(
            task_limit_raw, task_overrides_raw
        )
        # MSS 没有交给首任务的登录，不给任何任务截止时刻
        task_deadlines: dict[str, float] = {}
        secrets = self._secret_log_variants()
        profile = self._adb_state.profile
        request = MaaFWPlanRunRequest(
            project_path=self.project_path,
            plan=plan,
            device_config=device_config,
            runtime_pool_root=self.maafw_runtime_pool_root,
            runtime_pool_id=str(self.maafw_runtime_pool_id or ""),
            lease_owner=f"automas-script-maafw:{self.script_info.script_id}",
            run_time_limit_minutes=config_view.run_time_limit(self.script_config),
            attachment_root=Path(self._history_temp.name),
            task_time_limit_seconds=task_limit_seconds,
            task_time_limit_overrides=task_limit_overrides,
            task_deadlines=task_deadlines,
            loop_guard=loop_guard(config_view.loop_guard_raw(self.script_config)),
            run_secrets=secrets,
            project_log_secrets=project_log_secret_variants(
                secrets,
                config_view.all_task_snapshots(self.script_config),
                self.interface_model,
                DPAPI_SECRET_OPENER,
            ),
            redaction_notice=self._log_redaction_notice(),
            # 同一账号运行里只走一条路：Win32 是桌面游戏刚启动的时刻，ADB 是随模拟器冷启动的时刻
            game_started_at=(
                self._desktop.started_at
                if plan.controllerType == "Win32"
                else self._emulator_started_at
            ),
            game_start_disk_quiet=self._disk_quiet,
            game_wait_seconds=config_view.game_wait_time(self.script_config),
            import_paths=config_view.import_paths(),
            # 与运行前更新 / 预检同一份解析：托管级 Update.ProxyAddress 优先，留空跟随全局
            proxy_url=config_view.proxy_url(self.script_config),
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
        return outcome.result

    async def _script_adb_env(self) -> dict[str, str]:
        """脚本专用 adb server 的进程环境（``host_client.script_adb_env``）。"""

        return await script_adb_env(
            self.emulator_manager, config_view.emulator_device(self.script_config)
        )

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

    # ------------------------------------------------------------------
    # 打码值（每个调用点现算）
    # ------------------------------------------------------------------

    def _run_password_values(self) -> list[str]:
        return run_secret_values(
            self.run_plan,
            self.interface_model,
            config_view.task_snapshot_secret_raw(
                getattr(self, "cur_user_config", None)
            ),
            DPAPI_SECRET_OPENER,
        )

    def _secret_log_variants(self) -> list[str]:
        return secret_log_variants(self._run_password_values())

    def _log_redaction_notice(self) -> str | None:
        if self.run_plan is None or self.interface_model is None:
            return None
        return log_redaction_notice(self.interface_model, self._run_password_values())

    # ------------------------------------------------------------------
    # 运行前设置、worker 的停止
    # ------------------------------------------------------------------

    async def _shutdown_runner(self) -> None:
        await self._pretasks.stop()
        run = self._plan_run
        if run is not None:
            await run.stop()

    async def _pretasks_need_rerun(self, client_reset: bool) -> bool:
        return await pretasks_need_rerun(
            self.run_plan,
            self.interface_model,
            client_reset=client_reset,
            configured_hwnd=config_view.configured_hwnd(self.script_config),
            emit=self._on_plan_run_event,
        )

    async def _run_pretasks(self) -> None:
        if self.run_plan is None:
            raise RuntimeError("MaaFW 运行计划尚未初始化")
        # ModAVD 实例：pretask 若用 adb，也走脚本专用 server（同 worker）
        adb_env = await self._script_adb_env()
        await self._pretasks.run(
            MaaFWPretaskRunRequest(
                project_path=self.run_plan.path,
                pretasks=self.run_plan.pretasks,
                run_time_limit_minutes=config_view.run_time_limit(self.script_config),
                plan_env=self.run_plan.piEnv,
                extra_env=adb_env,
                secrets=self._secret_log_variants(),
                desktop=desktop_process_target.get(),
            )
        )

    # ------------------------------------------------------------------
    # 周期任务与重试时重建计划
    # ------------------------------------------------------------------

    def _filter_period_once_tasks(self, plan: MaaFWRunPlan) -> MaaFWRunPlan:
        limits = config_view.period_limits(self.script_config)
        if limits.empty:
            return plan
        return filter_period_once_tasks(
            plan,
            limits,
            self._load_period_task_records(),
            datetime.now(tz=UTC4),
        )

    async def _refresh_plan(self, completed_tasks: list[str]) -> None:
        """重试前重建计划：从 ``base_run_plan`` 重新按周期过滤，再剔掉本次运行已完成的。

        剔除必须跟在重建之后：重建会把上一次剔掉的任务放回来，所以按累计结果每次都重剔。
        同名任务在队列里有多份时全部重跑（见 ``skip_tasks_completed_this_run``）。
        """

        self._completed_this_run.extend(completed_tasks)
        if self.base_run_plan is not None:
            plan = await asyncio.to_thread(
                self._filter_period_once_tasks,
                self.base_run_plan,
            )
            outcome = skip_tasks_completed_this_run(
                plan, self._completed_this_run, MSS_SKIP_ON_RETRY
            )
            self._retry_rerun_duplicates = outcome.rerun_duplicates
            self.run_plan = outcome.plan

    def _log_retry_skipped_tasks(self) -> None:
        """重试开头写一行被重试跳过的任务；不一次性消费（worker 崩溃时计划原样沿用）。"""

        for line in retry_skip_log_lines(self.run_plan, self._retry_rerun_duplicates):
            self._append_log(line)

    def _load_period_task_records(self) -> PeriodRecords:
        return parse_period_records(
            load_json_dict(config_view.period_records_raw(self.cur_user_config))
        )

    async def _mark_period_tasks_completed(self, completed_tasks: list[str]) -> None:
        if not completed_tasks:
            return
        limits = config_view.period_limits(self.script_config)
        if limits.empty:
            return

        new_records = period_records_after(
            load_json_dict(config_view.period_records_raw(self.cur_user_config)),
            limits,
            completed_tasks,
            datetime.now(tz=UTC4),
        )
        if new_records is not None:
            await config_view.set_period_records(self.cur_user_config, new_records)

    async def _mark_run_started(self) -> None:
        if proxy_day_rolled(
            config_view.last_proxy_date(self.cur_user_config), self.curdate
        ):
            await config_view.set_last_proxy_date(
                self.cur_user_config, datetime.now(tz=UTC4)
            )
            await config_view.set_proxy_times(self.cur_user_config, 0)
        await config_view.set_last_proxy_status(self.cur_user_config, "运行中")

    # ------------------------------------------------------------------
    # 客户端（模拟器 / 桌面游戏）
    # ------------------------------------------------------------------

    async def _close_emulator(self) -> bool:
        """关闭由 MAS 启动的模拟器，返回是否关成（本来就没开过算关成）。"""

        if not self.opened_emulator:
            return True
        try:
            return await close_emulator(self)
        finally:
            self.opened_emulator = False
            # 地址与雷电 extras 里的 pid 都是随这次启动的，下一轮重开要重新拿
            self._adb_state.forget_emulator_launch()
            # 游戏随模拟器一起关了；下一轮重开时按那次拉起重新起算
            self._emulator_started_at = None
            self._disk_quiet = False

    async def _ensure_desktop_game_started(self) -> None:
        """Win32 场景下由 MAS 负责启动/激活桌面游戏客户端（``desktop_game``）。"""
        if self.run_plan is None or self.run_plan.controllerType != "Win32":
            return
        await self._desktop.ensure_started(
            config_view.desktop_spec(self.script_config),
            interface=self.interface_model,
            controller_name=self.run_plan.controllerName,
            desktop=desktop_process_target.get(),
        )

    def _attempt_limit(self) -> int:
        """本账号这次运行最多跑几次：``Run.RunTimesLimit``，加上清理残留后额外的重跑。"""

        return (
            int(config_view.run_times_limit(self.script_config) or 0)
            + self._extra_attempts
        )

    async def _recover_resource_failure(self, kind: str) -> tuple[str, str] | None:
        """资源包加载失败之后与发行包核对（``resource_repair``）。"""

        return await self._repair.run(
            kind,
            config_view.repair_request(
                str(self.script_info.script_id),
                str(self.script_info.name or ""),
                self.script_config,
            ),
        )

    async def _reset_client_for_retry(self, attempt: int) -> tuple[bool, bool]:
        """重试前关掉 MAS 自己起的客户端，返回（是否全部关成, 是否已不在）。"""

        had_client = self._desktop.opened or self.opened_emulator
        restarted = await self._restart_client_before_retry(attempt)
        still_open = self._desktop.opened or self.opened_emulator
        return restarted, bool(had_client and not still_open)

    async def _restart_client_before_retry(self, attempt: int) -> bool:
        """一轮失败后把 MAS 自己拉起的游戏/模拟器关掉，让下一轮从启动重新来。

        游戏/模拟器不是 MAS 起的时照旧不碰；这是最后一轮时也不在这里关，收尾统一关。返回这次是否
        全部关成。
        """

        if attempt >= self._attempt_limit():
            return False
        if not self._desktop.opened and not self.opened_emulator:
            return False
        # 只在真正要重启 MAS 自己启动的客户端时撤销预下载资格。
        from app.core.script_update_queue import report_script_task_retrying

        await report_script_task_retrying()
        self._append_log("本轮失败，关闭由 MAS 启动的游戏/模拟器，下一轮重新启动")
        emulator_closed = await self._close_emulator()
        game_closed = await self._close_game()
        return emulator_closed and game_closed

    async def _close_game(self) -> bool:
        """关闭由 MAS 启动的游戏（``desktop_game.close``）。"""

        return await self._desktop.close(
            config_view.desktop_spec(self.script_config, for_close=True)
        )

    async def _close_game_after_run(self, *, failed: bool) -> None:
        """最终收尾关游戏：MAS 启动的照常关，AttachOnly 再按 ``Game.CloseMode`` 兜底。"""

        plan = self.run_plan
        await self._desktop.close_after_run(
            config_view.desktop_spec(self.script_config, for_close=True),
            interface=self.interface_model,
            controller_name=plan.controllerName if plan is not None else None,
            controller_type=plan.controllerType if plan is not None else None,
            failed=failed,
            desktop=desktop_process_target.get(),
        )

    # ------------------------------------------------------------------
    # 项目预约、显示保持、锁屏
    # ------------------------------------------------------------------

    async def _try_enter_project_path(self) -> bool:
        project_lock_key = await try_reserve_project_path(self.project_path)
        if project_lock_key is None:
            return False
        self.project_lock_key = project_lock_key
        return True

    async def _release_project_path(self) -> None:
        """交回本账号的项目预约（``project_path.release_run_reservation``）。"""

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
        """没有生效中的「保持显示开启」请求就再请求一份（每次尝试开头都调）。"""

        hold = self._display_hold
        if hold is None or not hold.active:
            self._display_hold = power.hold_display(
                f"MFW 运行（{self.cur_user_item.name}）"
            )

    async def _ensure_workstation_unlocked(self) -> None:
        """要用交互式桌面的控制器，锁屏时直接判失败，不进会重启游戏的重试。"""

        reason = await workstation_lock_reason(
            self.run_plan.controllerType if self.run_plan is not None else None,
            desktop_process_target.get(),
        )
        if reason is not None:
            raise MaaFWWorkstationLocked(WORKSTATION_LOCKED_MESSAGE)

    def _release_display_hold(self) -> None:
        hold, self._display_hold = self._display_hold, None
        if hold is not None:
            hold.release()

    # ------------------------------------------------------------------
    # 信号、历史、记账
    # ------------------------------------------------------------------

    async def _finish_on_signal(self, attempt: int, result: MaaFWRunResult) -> None:
        """worker 回报了信号节点命中：记账、写日志状态（正式通知由管理器收尾时发）。"""

        facts = signal_attempt_facts(
            result, self.run_plan, user_messages=SIGNAL_USER_MESSAGES
        )
        signal = facts.signal
        self.run_signal = signal
        point(self, "special", state="matched", key=signal)
        message = facts.message
        logger.warning(
            f"MaaFW 账号 {self.cur_user_item.name} 命中项目信号 {signal}"
            f"（节点 {facts.node}）：{message}"
        )
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

    async def _start_attempt_log(self) -> None:
        """重试前另起一份日志记录，每次尝试单独成段。"""

        start_time = datetime.now().astimezone()
        self.cur_user_log_started_at = start_time
        self.cur_user_log = LogRecord()
        self.cur_user_log = await self.cur_user_item.add_log_record(
            start_time, self.cur_user_log
        )

    def _run_record_statistic(self, key: int) -> HistorySnapshotStatistic | None:
        value = self._ledger.history_value(key)
        return HistorySnapshotStatistic(value=value) if value is not None else None

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

        这次尝试的日志还没有开始时刻时不记 history 状态。
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

    # ------------------------------------------------------------------
    # 给管理器读的报告（与通用流程同名）
    # ------------------------------------------------------------------

    def run_incident_notice(self) -> str:
        """本次运行里被原地打转检测或单任务时限停下的任务。"""

        return self._ledger.incident_notice(
            run_complete=self.run_complete,
            signal_message=self._signal_user_message(),
            check_passed=self.check_result == "Pass",
        )

    def report_screenshots(self) -> list[tuple[str, bytes]]:
        """给托管级「代理结果」报告用的失败截图，标签带上账号名称以区分多账号。"""

        return [
            (f"{self.cur_user_item.name} · {label}", path)
            for label, path in self._notification_screenshots
        ]

    def _report_result(self, *, short: bool = False) -> str:
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
        """托管级「代理结果」里本账号的那一行；运行前检查没过、也没记日志的返回 None。"""

        if self.check_result != "Pass" and self.cur_user_log is None:
            return None
        return self._report_result(short=True)

    def missing_task_notice(self) -> str:
        """队列里 interface 已没有的任务：进用户与脚本两份报告。"""

        if not self.missing_task_names:
            return ""
        return f"{MISSING_TASK_NOTICE_PREFIX}: " + "、".join(self.missing_task_names)

    # ------------------------------------------------------------------
    # 通知
    # ------------------------------------------------------------------

    async def _push_user_statistics(self) -> None:
        """按通知设置推送账号级统计信息（放在状态落定之后：结果行要读最终的 run_complete）。"""

        try:
            statistics = {}
            statistics["user_info"] = self.cur_user_item.name
            statistics["start_time"] = (
                self.user_start_time.strftime("%Y-%m-%d %H:%M:%S")
                if self.user_start_time is not None
                else ""
            )
            statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            statistics["task_details"] = self._ledger.task_details(
                run_complete=self.run_complete,
                signal_message=self._signal_user_message(),
                check_passed=self.check_result == "Pass",
                missing=self.missing_task_notice(),
            )
            images = await prepare_screenshot_images(
                self._notification_screenshots,
                image_id_prefix="maafw",
            )
            statistics["screenshots"] = screenshot_entries(images)
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


@dataclass(frozen=True)
class _PlanHead:
    """建计划前半段交给后半段的东西（同一个 ``check`` 里，只在 ``_load_run_state`` 内部传）。"""

    interface_model: MaaFWInterface
    task_snapshot: dict[str, Any]
    controller_name: str | None
    resource_name: str | None
    script_hotkeys: Any
    inspection: MaaFWSnapshotInspection
    expansion: MaaFWSnapshotExpansion
    state: MSSArrangeState


__all__ = ["MSSAccountRun"]
