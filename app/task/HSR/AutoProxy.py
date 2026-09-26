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
from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Literal

from app.core.ws import Publisher, protocol
from app.models.config import HSRConfig, HSRUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.schema import WSTaskNoticeData
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase, UserItem
from app.services.system import System
from app.utils import ProcessManager, get_logger, is_process_running
from app.utils.constants import UTC4

from .task_mapping import (
    HSR_TASK_MODULES,
    engine_label,
    resolve_script_assignment,
)
from .tools import push_notification
from .tools.account_switch import (
    HSR_GAME_PROCESS_NAME,
    HSR_GAME_READY_DELAY_SECONDS,
    HSRAccountSwitcher,
    cloud_login_timeout_minutes,
    cloud_max_queue_minutes,
    configure_m7a_runner,
    is_cloud_platform,
    is_game_management_enabled,
    resolve_game_executable_path,
    stop_external_processes,
    user_needs_account_switch,
)
from .tools.backup_archive import archive_mas_runtime_backup, read_mas_overlay
from .tools.extra_script import run_script_after_task, run_script_before_task
from .tools.log_detect import (
    HSR_CLOUD_REMAINING_WARN_MINUTES,
    detect_cloud_login_required,
    detect_echo_of_war_completion,
    find_m7a_self_game_stop,
    is_cloud_login_success,
    is_m7a_self_browser_start,
    parse_cloud_remaining,
    select_failure_summary_lines,
)
from .tools.m7a_config import M7A_DAILY_ACTIVITY_SWITCH_KEYS
from .tools.m7a_control import HSRM7AControl
from .tools.m7a_runtime import M7ARunner
from .tools.managed_config import list_managed_modules, redeem_code_fingerprint
from .tools.native_control import (
    resolve_configured_engines,
    resolve_phase_timeout_minutes,
    resolve_plan,
    resolve_script_path,
)
from .tools.run_model import (
    CompletionWriteback,
    HSRGameExitedError,
    HSRLoginPlan,
    HSRModuleResult,
    HSRModuleResultStatus,
    HSRNonRetryableTaskError,
    HSRPhase,
    HSRRetryableTaskError,
    HSRRunItem,
    HSRRuntimeState,
    external_result_failure_summary,
)
from .tools.sra_control import HSRSRAControl
from .tools.sra_runtime import (
    SRA_REWARD_REDEEM_CODE_KEY,
    SRA_REWARD_REDEEM_CODE_LEGACY_KEY,
    cleanup_sra_temp_config,
)
from .tools.stage_runtime import resolve_configured_daily_stages

logger = get_logger("HSR 自动代理")

# 队列中止时写给剩余未执行项的原因，用户会在任务报告里直接看到。
HSR_ABORT_REASON_LOGIN_FAILED = "SRA 登录/切号失败，当前阶段未执行"
HSR_ABORT_REASON_GAME_EXITED = "游戏进程已退出，当前阶段剩余模块未执行"
HSR_ABORT_REASON_CLOUD = "云·星穹铁道无法继续，本轮剩余模块未执行"
# 游戏进程消失后再等这么久才下结论：读输出的协程要把 M7A 关游戏前那行
# ERROR 收进来；脚本自己关游戏后紧接着退出的，等它自然结束就不用杀。
GAME_EXIT_SETTLE_SECONDS = 2

MODULE_KEYS_BY_PHASE: dict[HSRPhase, tuple[str, ...]] = {
    phase: tuple(module.key for module in HSR_TASK_MODULES if module.category == phase)
    for phase in ("daily", "weekly")
}


def resolve_daily_native_modes(
    assigned_script: str, values: Mapping[str, object]
) -> tuple[bool, bool]:
    """从体力模块的托管值里读出 (培养目标已开, 活动双倍已开)。

    这两种模式下脚本自己决定副本，MAS 里没选体力主关卡是正常的；自动代理的
    跳过判定与任务预检都以此为准。
    """

    if assigned_script == "SRA":
        return bool(values.get("useBuildTarget", False)), bool(
            values.get("activity.enabled", False)
        )
    # 活动总开关 activity_enable 不在表单里，运行时按这三个子开关推导（见
    # build_m7a_daily_patch），判定口径与之相同。
    activity_enabled = any(
        bool(values.get(key, False)) for key in M7A_DAILY_ACTIVITY_SWITCH_KEYS
    )
    return bool(values.get("build_target_enable", False)), activity_enabled


def _server_day_clock(now_dt: datetime | None = None) -> datetime:
    """把一个时刻换算成游戏换日口径（UTC+4）的挂钟时间。

    星铁在服务器时间（UTC+8）周一 04:00 重置，等价于 UTC+4 的零点，按 UTC+4 取
    `isocalendar()` / `%A` / `%Y-%m-%d` 就会在正确时刻翻页。日 / 周标记是「那个瞬间」
    的属性，与调用方或用户本机在哪个时区无关，所以带时区的输入一律换算过去；naive
    输入按已经是 UTC+4 处理。
    """

    if now_dt is None:
        return datetime.now(tz=UTC4)
    if now_dt.tzinfo is None:
        return now_dt.replace(tzinfo=UTC4)
    return now_dt.astimezone(UTC4)


def _has_enabled_phase_module(plan, phase: HSRPhase) -> bool:
    """判断计划是否启用了指定周期的任一 HSR 模块。"""

    return any(bool(plan.get("TaskSwitch", key)) for key in MODULE_KEYS_BY_PHASE[phase])


class HSRAutoProxyTask(TaskExecuteBase):
    """HSR 单用户自动代理任务。"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: HSRConfig,
        user_config: MultipleConfig[HSRUserConfig],
        user_item: UserItem,
        runtime: HSRRuntimeState,
    ) -> None:
        super().__init__()
        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.cur_user_item = user_item
        self.cur_user_uid: uuid.UUID = uuid.UUID(user_item.user_id)
        self.cur_user_config: HSRUserConfig = self.user_config[self.cur_user_uid]
        self.runtime = runtime
        self._log_lines: list[str] = runtime.log_lines
        self._completion_writebacks: list[CompletionWriteback] = (
            runtime.completion_writebacks
        )
        self._game_process_manager: ProcessManager = runtime.game_process_manager
        self._account_switcher = HSRAccountSwitcher(
            script_config=self.script_config,
            runtime=self.runtime,
            append_log=self._append_log,
            script_id=self.script_info.script_id,
            user_id=user_item.user_id,
        )
        self._sra_control = HSRSRAControl(
            script_config=self.script_config,
            account_switcher=self._account_switcher,
            append_log=self._append_log,
            phase_timeout_seconds=self._phase_timeout_seconds,
            module_timeout_seconds=self._module_timeout_seconds,
            queue_eow_completion=self._queue_eow_completion_if_confirmed,
            queue_weekly_completion=self._queue_weekly_completion,
            record_module_result=self._record_module_result,
        )
        self._m7a_control = HSRM7AControl(
            script_config=self.script_config,
            account_switcher=self._account_switcher,
            append_log=self._append_log,
            module_timeout_seconds=self._module_timeout_seconds,
            queue_eow_completion=self._queue_eow_completion_if_confirmed,
            queue_weekly_completion=self._queue_weekly_completion,
            record_module_result=self._record_module_result,
        )
        self._current_user_item: UserItem | None = None
        self._current_user_log: LogRecord | None = None
        self._current_log_start_time: datetime | None = None
        self.user_start_time: datetime | None = None
        self.temp_files: list[Path] = []
        self.steps_count: int = 0
        self.crashed: bool = False
        self.error_message: str = ""
        self._managed_options_cache: dict[tuple[int, str, str], dict[str, object]] = {}
        # 输出回调里派生的后台任务（如终止三月七），持有引用防止被回收。
        self._background_tasks: set[asyncio.Task] = set()
        # 本用户的 SRA 登录项工厂（按阶段）；登录计划不走 SRA StartGame 时为 None。
        # 队列中途因模块失败重启游戏后，下一个 SRA 模块前要先用它登录一次。
        self._restart_login_item_factory: Callable[[HSRPhase], HSRRunItem] | None = None

    def _append_log(self, message: str, *, max_lines: int = 500) -> None:
        text = str(message).strip()
        if not text:
            return
        # 日志行时间戳跟随用户本机时区；HSR 之外的专项都用本地时间，
        # 这里曾硬编码 UTC+8，非中国时区的用户看到的每一行都是偏的。
        # 注意别把周常重置日、历战余响开始日那几处一起改掉，那些是游戏服务器
        # 日期语义，用 UTC+4 表达：星铁的日 / 周边界是服务器时间周一 04:00，
        # 正好等于 UTC+4 的零点，`isocalendar()` 与 `%A` 因此会在正确时刻翻页。
        now_text = datetime.now().astimezone().strftime("%H:%M:%S")
        appended_lines: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                formatted = f"[{now_text}] {line}"
                self._log_lines.append(formatted)
                appended_lines.append(formatted)
        if len(self._log_lines) > max_lines:
            del self._log_lines[:-max_lines]
        self.script_info.log = "\n".join(self._log_lines)
        if self._current_user_log is not None:
            if self._current_user_log.status in ("未开始监看日志", ""):
                self._current_user_log.status = "HSR 正常运行中"
            self._current_user_log.content.extend(
                f"{line}\n" for line in appended_lines
            )

    def _start_user_log(
        self,
        user_item: UserItem,
        user_name: str,
        attempt: int = 1,
        retry_limit: int = 1,
    ) -> None:
        """为当前 HSR 用户创建运行日志记录。"""

        self._current_user_item = user_item
        self._current_log_start_time = datetime.now()
        self._current_user_log = LogRecord(status="HSR 正常运行中")
        user_item.log_record[self._current_log_start_time] = self._current_user_log
        user_item.status = "运行"
        if attempt <= 1:
            self._append_log(f"开始处理用户「{user_name}」")
        else:
            self._append_log(
                f"开始处理用户「{user_name}」第 {attempt}/{retry_limit} 次尝试"
            )

    def _finish_current_user_log(
        self,
        log_status: str,
        user_status: str = "完成",
    ) -> None:
        """结束当前用户日志记录，并清空当前用户上下文。"""

        if self._current_user_log is not None:
            self._current_user_log.status = log_status
        if self._current_user_item is not None:
            self._current_user_item.status = user_status
        self._current_user_item = None
        self._current_user_log = None
        self._current_log_start_time = None

    def _mark_current_user_abnormal(
        self,
        log_status: str,
        user_status: str = "异常",
    ) -> None:
        """异常或中止时给当前用户补充明确结果。"""

        if self._current_user_log is not None:
            self._current_user_log.status = log_status
        if self._current_user_item is not None:
            self._current_user_item.status = user_status

    async def _stop_external_processes(self) -> None:
        """停止当前仍在运行的 SRA/M7A 子进程。"""

        await stop_external_processes(
            self.runtime,
            self._append_log,
            self.script_config,
        )

    def _module_timeout_seconds(self, module_key: str) -> int:
        """按模块所属周期读取超时配置，返回秒。"""

        phase = next(
            (
                module.category
                for module in HSR_TASK_MODULES
                if module.key == module_key
            ),
            "weekly",
        )
        return self._timeout_seconds_for_phase(phase)

    async def _restart_game(self, user_name: str, reason: str) -> None:
        """按开关决定是否由 MAS 关闭并重新启动游戏。

        云平台不重启浏览器：同一用户的模块之间浏览器保持在游戏画面里，三月七
        下一次连回去不用重新登录、排队；这里只确认它还活着。
        """

        await self._stop_external_processes()
        if is_cloud_platform(self.script_config):
            self.runtime.last_external_script = None
            self.runtime.game_session_clean = False
            self._append_log(
                f"用户「{user_name}」{reason}，云·星穹铁道保持浏览器不重启"
            )
            await self._account_switcher.ensure_cloud_browser()
            return
        if not is_game_management_enabled(self.script_config):
            self.runtime.game_launch_checked = True
            self.runtime.game_started_by_mas = False
            self.runtime.game_session_clean = False
            self.runtime.last_external_script = None
            self._append_log(
                f"用户「{user_name}」{reason}，MAS 未管理游戏，跳过游戏重启并继续执行"
            )
            return

        game_exe_path = resolve_game_executable_path(self.script_config)
        process_name = HSR_GAME_PROCESS_NAME

        self._append_log(f"用户「{user_name}」{reason}，正在由 MAS 重启游戏")

        self.runtime.game_exe_path = game_exe_path
        self.runtime.game_launch_checked = False
        self.runtime.game_started_by_mas = False
        self.runtime.game_session_clean = False
        self.runtime.last_external_script = None
        self.runtime.game_transitioning = True

        try:
            await System.kill_process(game_exe_path)
            await self._game_process_manager.clear()
            self._append_log(
                f"已请求关闭游戏，等待 {HSR_GAME_READY_DELAY_SECONDS}s 后重新启动"
            )
            await asyncio.sleep(HSR_GAME_READY_DELAY_SECONDS)
            if process_name and is_process_running(process_name):
                self._append_log(
                    f"等待后仍检测到游戏进程运行（{process_name}），"
                    "将继续按启动流程等待游戏就绪"
                )
            else:
                self._append_log("游戏进程已关闭，准备重新启动")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"{reason}关闭 HSR 游戏失败：{e}")
            self._append_log(f"{reason}关闭游戏失败，将继续尝试启动流程：{e}")

        try:
            await self._account_switcher.ensure_game_started_by_mas()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"{reason}重启 HSR 游戏失败：{e}")
            raise RuntimeError(f"{reason}重启游戏失败：{e}") from e
        finally:
            self.runtime.game_transitioning = False

    def _get_run_times_limit(self) -> int:
        """读取脚本页最大尝试次数，最小为 1。"""

        value = self.script_config.get("Run", "RunTimesLimit")
        return max(1, int(value or 3))

    @staticmethod
    def _period_markers(
        now_dt: datetime | None = None,
    ) -> tuple[str, str]:
        """返回当前日期和 ISO 周标记（游戏服务器口径）。

        用 UTC+4 而不是 UTC+8：星铁在服务器时间周一 04:00 重置，UTC+4 的零点正是
        这一刻。按 UTC+8 算会提前四小时翻页——周一 00:00~04:00（北京时间，对 UTC+2
        用户就是周日晚上）跑的那一轮，会把「上一周已完成」的结果写成新一周的完成态，
        真正重置后整周都不再尝试。
        """

        now_dt = _server_day_clock(now_dt)
        iso_year, iso_week, _ = now_dt.isocalendar()
        return (
            now_dt.strftime("%Y-%m-%d"),
            f"{iso_year:04d}-W{iso_week:02d}",
        )

    def _queue_data_writeback(
        self,
        user_id: str,
        user_name: str,
        reason: str,
        fields: list[tuple[str, str, object]],
    ) -> None:
        """登记完成态写回。"""

        self._completion_writebacks.append(
            CompletionWriteback(
                user_id=user_id,
                user_name=user_name,
                reason=reason,
                fields=fields,
            )
        )
        logger.info(f"用户「{user_name}」已登记 HSR 完成态写回：{reason}")

    @staticmethod
    def _build_daily_proxy_writeback_fields(
        user_config,
        now_dt: datetime | None = None,
    ) -> list[tuple[str, str, object]]:
        """构造日常代理状态写回字段，口径与用户列表标签保持一致。"""

        now_dt = _server_day_clock(now_dt)

        today = now_dt.strftime("%Y-%m-%d")
        last_proxy_date = str(user_config.get("Data", "LastProxyDate") or "")
        proxy_times = int(user_config.get("Data", "ProxyTimes") or 0)
        next_proxy_times = proxy_times + 1 if last_proxy_date == today else 1

        fields: list[tuple[str, str, object]] = [
            ("Data", "LastProxyDate", today),
            ("Data", "ProxyTimes", next_proxy_times),
        ]

        if last_proxy_date != today:
            remained_day = int(user_config.get("Info", "RemainedDay") or 0)
            if remained_day != -1:
                fields.append(("Info", "RemainedDay", remained_day - 1))

        return fields

    def _queue_daily_proxy_completion(
        self,
        user_id: str,
        user_name: str,
    ) -> None:
        """整轮 HSR 用户任务成功后，登记列表日常代理状态写回。"""

        self._queue_data_writeback(
            user_id=user_id,
            user_name=user_name,
            reason="HSR 用户任务成功完成",
            fields=self._build_daily_proxy_writeback_fields(self.cur_user_config),
        )

    def _record_module_result(
        self,
        *,
        user_id: str,
        user_name: str,
        module_key: str,
        module_name: str,
        script: str,
        status: HSRModuleResultStatus,
        reason: str = "",
    ) -> None:
        """记录模块最终态，供运行日志和通知汇总使用。"""

        self.runtime.record_module_result(
            HSRModuleResult(
                user_id=user_id,
                user_name=user_name,
                module_key=module_key,
                module_name=module_name,
                script=script,
                status=status,
                reason=reason,
            )
        )

    def _format_current_user_module_results(self) -> str:
        """格式化当前用户的模块完成情况。"""

        items = [
            item
            for item in self.runtime.module_results
            if item.user_id == self.cur_user_item.user_id
        ]
        if not items:
            return ""

        status_label = {
            "completed": "完成",
            "failed": "失败",
            "incomplete": "未完成",
            "skipped": "跳过",
        }
        lines = ["模块执行情况："]
        for item in items:
            label = status_label.get(item.status, item.status)
            text = (
                f"{item.module_name}（{engine_label(item.script, left=False, right=False)}）"
                f"：{label}"
            )
            if item.reason and item.status != "completed":
                text = f"{text}，{item.reason}"
            lines.append(text)
        return "\n".join(lines)

    async def _push_user_statistics_notification(self) -> None:
        """推送当前用户的 HSR 统计通知。"""

        started_at = self.user_start_time or datetime.now()
        user_result = self.cur_user_item.result
        module_result = self._format_current_user_module_results()
        if module_result:
            user_result = f"{user_result}\n\n{module_result}"
        cloud_remaining = self._format_cloud_remaining(self.cur_user_item.user_id)
        if cloud_remaining:
            user_result = f"{user_result}\n\n{cloud_remaining}"

        statistics = {
            "user_info": self.cur_user_item.name,
            "start_time": started_at.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user_result": user_result,
        }
        success_symbol = "√" if self.cur_user_item.status == "完成" else "X"

        try:
            await push_notification(
                "统计信息",
                (
                    f"{datetime.now().strftime('%m-%d')} |{success_symbol}|  "
                    f"{self.cur_user_item.name} 的 HSR 自动代理统计报告"
                ),
                statistics,
                self.cur_user_config,
            )
        except Exception as e:
            logger.opt(exception=True).warning(f"推送 HSR 用户统计通知时出现异常: {e}")
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="error",
                    message=f"推送 HSR 用户统计通知时出现异常: {e}",
                ),
            )

    async def _send_task_notice(self, level: str, message: str) -> None:
        """调度台提示；发送失败不影响任务。"""

        try:
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level=level, message=message),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"发送 HSR 调度台提示失败：{e}")

    def _format_cloud_remaining(self, user_id: str) -> str:
        """结束通知里的云·星穹铁道剩余时长；没读到时返回空串。"""

        remaining = self.runtime.cloud_remaining.get(user_id)
        if remaining is None:
            return ""
        total, paid, free = remaining
        text = (
            f"云·星穹铁道剩余时长：{total} 分钟（付费 {paid} 分钟，免费 {free} 分钟）"
        )
        if total < HSR_CLOUD_REMAINING_WARN_MINUTES:
            text += f"\n剩余时长不足 {HSR_CLOUD_REMAINING_WARN_MINUTES} 分钟，下次可能跑不完"
        return text

    async def _on_m7a_output_line(self, line: str) -> None:
        """三月七逐行输出：客户端照旧做截图窗口恢复；云平台识别登录与剩余时长。"""

        await self._account_switcher.recover_game_window_if_screenshot_blocked(line)
        if is_cloud_platform(self.script_config):
            await self._handle_cloud_line(line)

    async def _handle_cloud_line(self, line: str) -> None:
        uid = self.cur_user_item.user_id
        user_name = self.cur_user_item.name
        runtime = self.runtime

        if is_m7a_self_browser_start(line):
            if runtime.cloud_self_browser_detected:
                return
            runtime.cloud_self_browser_detected = True
            runtime.cloud_login_suppressed.add(uid)
            runtime.cloud_login_times.pop(uid, None)
            self._append_log(
                f"用户「{user_name}」三月七没找到 MAS 托管的云浏览器，正准备自己新建"
                "（通常是云游戏窗口被关掉后三月七重试启动）；已终止本次三月七，"
                "下次尝试前由 MAS 重新启动该用户的浏览器，本轮不记录登录时间"
            )
            runner = runtime.m7a_runner
            if runner is not None:
                # 不在读输出的协程里等进程退出：管道要继续被读，交给独立任务终止。
                task = asyncio.create_task(runner.terminate_process_tree())
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
            return

        login_required, timeout_minutes = detect_cloud_login_required(line)
        if login_required:
            if uid in runtime.cloud_login_notified:
                return
            runtime.cloud_login_notified.add(uid)
            minutes = timeout_minutes or cloud_login_timeout_minutes(self.script_config)
            message = (
                f"用户「{user_name}」需要在 {self.script_info.name or 'HSR'} "
                "弹出的云·星穹铁道浏览器窗口里登录米哈游通行证（扫码或密码均可），"
                f"请在 {minutes} 分钟内完成"
            )
            self._append_log(message)
            await self._send_task_notice("warning", message)
            try:
                await push_notification(
                    "云登录提醒",
                    f"{user_name} 需要登录云·星穹铁道",
                    {"message": message},
                    self.cur_user_config,
                )
            except Exception as e:  # noqa: BLE001
                logger.opt(exception=True).warning(f"推送云登录提醒失败：{e}")
            return

        if is_cloud_login_success(line):
            if uid in runtime.cloud_login_suppressed:
                return
            runtime.cloud_login_times[uid] = (
                datetime.now().astimezone().isoformat(timespec="seconds")
            )
            if uid in runtime.cloud_login_notified:
                runtime.cloud_login_notified.discard(uid)
                message = f"用户「{user_name}」已登录云·星穹铁道"
                self._append_log(message)
                await self._send_task_notice("info", message)
            return

        remaining = parse_cloud_remaining(line)
        if remaining is not None:
            runtime.cloud_remaining[uid] = remaining
            total, paid, free = remaining
            self._append_log(
                f"用户「{user_name}」云·星穹铁道剩余时长 {total} 分钟"
                f"（付费 {paid} 分钟，免费 {free} 分钟）"
            )
            if total < HSR_CLOUD_REMAINING_WARN_MINUTES:
                self._append_log(
                    f"用户「{user_name}」云·星穹铁道剩余时长不足 "
                    f"{HSR_CLOUD_REMAINING_WARN_MINUTES} 分钟，可能跑不完本轮任务"
                )

    def _queue_eow_completion_if_confirmed(
        self,
        user_id: str,
        user_name: str,
        eow_enabled: bool,
        result: object,
        script: Literal["M7A", "SRA"],
    ) -> None:
        """外部脚本确认历战余响完成后，登记完成态。"""

        if not eow_enabled:
            return

        completed, reason = detect_echo_of_war_completion(
            result,
            script,
        )
        if not completed:
            self._record_module_result(
                user_id=user_id,
                user_name=user_name,
                module_key="EchoOfWar",
                module_name="历战余响",
                script=script,
                status="incomplete",
                reason=reason,
            )
            self._append_log(
                f"用户「{user_name}」历战余响保持未完成：{reason}；"
                "下次 HSR 运行会继续尝试"
            )
            return

        self._record_module_result(
            user_id=user_id,
            user_name=user_name,
            module_key="EchoOfWar",
            module_name="历战余响",
            script=script,
            status="completed",
            reason=reason,
        )
        today, current_week = self._period_markers()
        self._queue_data_writeback(
            user_id=user_id,
            user_name=user_name,
            reason=f"历战余响本周任务已完成：{reason}",
            fields=[
                ("Data", "EchoOfWarCompletedThisWeek", True),
                ("Data", "EchoOfWarLastResetWeek", current_week),
                ("Data", "EchoOfWarLastCompletionDate", today),
            ],
        )

    def _queue_weekly_completion(
        self,
        user_id: str,
        user_name: str,
        module_name: str,
    ) -> None:
        """差分宇宙 / 货币战争成功后，登记本周周常完成态。"""

        today, current_week = self._period_markers()
        self._queue_data_writeback(
            user_id=user_id,
            user_name=user_name,
            reason=f"{module_name} 成功执行",
            fields=[
                ("Data", "WeeklyCompletedThisWeek", True),
                ("Data", "WeeklyLastResetWeek", current_week),
                ("Data", "WeeklyLastCompletionDate", today),
            ],
        )

    @staticmethod
    def _resolve_daily_params(
        user_config,
        now_dt: datetime | None = None,
        *,
        plan=None,
    ) -> tuple[bool, bool]:
        """解析本周历战余响任务，不写用户 Data。

        开始日读 ``plan``（缺省即 ``user_config``），完成态读 ``user_config``。
        """

        if plan is None:
            plan = user_config
        weekday_options = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        eow_target = plan.get("TaskOpt", "EchoOfWarWeekday") or "Monday"
        if eow_target not in weekday_options:
            eow_target = "Monday"

        # 游戏周边界是服务器时间周一 04:00 = UTC+4 零点，见 _period_markers
        now_dt = _server_day_clock(now_dt)
        iso_year, iso_week, _ = now_dt.isocalendar()
        now_week = f"{iso_year:04d}-W{iso_week:02d}"

        last_reset_week = (
            user_config.get("Data", "EchoOfWarLastResetWeek") or "2000-W01"
        )
        eow_is_new_week = last_reset_week != now_week
        eow_completed_this_week = not eow_is_new_week and bool(
            user_config.get("Data", "EchoOfWarCompletedThisWeek")
        )

        today = now_dt.strftime("%A")
        if today not in weekday_options:
            today = "Monday"

        weekday_index = {wd: i for i, wd in enumerate(weekday_options)}
        if (
            weekday_index[today] >= weekday_index[eow_target]
            and not eow_completed_this_week
        ):
            eow_enabled = True
        else:
            eow_enabled = False

        return eow_enabled, eow_is_new_week

    @staticmethod
    def _resolve_weekly_skip(
        user_config,
        now_dt: datetime | None = None,
        *,
        plan=None,
    ) -> tuple[bool, str, bool]:
        """解析周常是否本周已完成，不写用户 Data。

        模块开关读 ``plan``（缺省即 ``user_config``），完成态读 ``user_config``。
        """
        weekly_enabled = _has_enabled_phase_module(
            user_config if plan is None else plan, "weekly"
        )

        # 游戏周边界是服务器时间周一 04:00 = UTC+4 零点，见 _period_markers
        now_dt = _server_day_clock(now_dt)
        iso_year, iso_week, _ = now_dt.isocalendar()
        now_week = f"{iso_year:04d}-W{iso_week:02d}"

        last_reset_week = user_config.get("Data", "WeeklyLastResetWeek") or "2000-W01"
        weekly_done_stored = bool(user_config.get("Data", "WeeklyCompletedThisWeek"))

        if last_reset_week != now_week:
            is_new_week_in_mem = True
            weekly_done_in_mem = False
        else:
            is_new_week_in_mem = False
            weekly_done_in_mem = weekly_done_stored

        if not weekly_enabled:
            return True, "已关闭周常", is_new_week_in_mem
        if weekly_done_in_mem:
            return True, "本周已完成（周常）", is_new_week_in_mem

        return False, "", is_new_week_in_mem

    def _timeout_seconds_for_phase(self, phase: HSRPhase) -> int:
        """按周期读取超时配置，返回秒。

        云平台每个模块都可能先排队，超时再加上一份排队预算。
        """

        minutes = resolve_phase_timeout_minutes(self.script_config, phase)
        if is_cloud_platform(self.script_config):
            minutes += cloud_max_queue_minutes(self.script_config)
        return minutes * 60

    def _phase_timeout_seconds(self, phase: HSRPhase) -> int:
        """按阶段读取超时配置，返回秒。"""

        return self._timeout_seconds_for_phase(phase)

    def _managed_module_values(
        self,
        *,
        assigned_script: str,
        module_key: str,
        plan,
    ) -> dict[str, object]:
        """读取动态托管页展示的原生值，并叠加计划里的托管覆盖。"""

        cache_key = (id(plan), assigned_script, module_key)
        if cache_key in self._managed_options_cache:
            return dict(self._managed_options_cache[cache_key])
        try:
            modules = list_managed_modules(
                assigned_script,
                self.script_config,
                plan,
            )
            for module in modules:
                if module.key == module_key:
                    values = {field.key: field.value for field in module.fields}
                    self._managed_options_cache[cache_key] = values
                    return dict(values)
        except (OSError, ValueError, TypeError):
            # 发现失败不应阻断旧的 MAS 队列；控制器会在真正写配置时给出
            # 更具体的错误。
            pass
        self._managed_options_cache[cache_key] = {}
        return {}

    def _daily_native_modes(self, *, assigned_script: str, plan) -> tuple[bool, bool]:
        values = self._managed_module_values(
            assigned_script=assigned_script,
            module_key="Daily",
            plan=plan,
        )
        return resolve_daily_native_modes(assigned_script, values)

    def _resolve_redeem_code_policy(
        self,
        *,
        engine: str,
        user_cfg,
        plan,
        user_name: str,
    ) -> tuple[bool, str | None]:
        values = self._managed_module_values(
            assigned_script=engine,
            module_key="ReceiveRewards",
            plan=plan,
        )
        if engine == "SRA":
            # SRA 2.22.0 起兑换码开关是具名键，旧 profile 仍是数组下标 6
            selected = bool(
                values.get(
                    SRA_REWARD_REDEEM_CODE_KEY,
                    values.get(SRA_REWARD_REDEEM_CODE_LEGACY_KEY, True),
                )
            )
        else:
            selected = bool(values.get("reward_redemption_code_enable", True))
        if not selected:
            self._append_log(
                f"用户「{user_name}」已关闭{engine_label(engine)}兑换码奖励，本轮跳过"
            )
            return False, None
        if engine == "M7A":
            # 三月七每日任务从在线码表取兑换码、按 already_used_codes 自行去重，
            # 不读用户手填的 redemption_code；按手填列表算指纹会让在线新码永远不兑。
            return True, None
        only_when_changed = self.script_config.get("Game", "RedeemCodesOnlyWhenChanged")
        if only_when_changed is False:
            return True, None
        try:
            fingerprint = redeem_code_fingerprint(engine, self.script_config)
        except (OSError, ValueError, TypeError) as exc:
            logger.warning(
                f"用户「{user_name}」读取{engine_label(engine)}兑换码版本失败，"
                f"保守执行：{exc}"
            )
            return True, None
        previous = str(user_cfg.get("Data", f"{engine}RedeemCodeFingerprint") or "")
        if previous == fingerprint:
            self._append_log(
                f"用户「{user_name}」{engine_label(engine, left=False)}兑换码未变化，"
                "本轮跳过兑换码领取"
            )
            return False, fingerprint
        return True, fingerprint

    def _resolve_daily_runnable_parts(
        self,
        *,
        assigned_script: str,
        plan,
        user_name: str,
        uid: str,
        daily_eow_enabled: bool,
    ) -> tuple[bool, bool]:
        """判断体力模块实际可执行内容；缺少关卡配置时跳过而不是失败。"""

        cultivation_enabled, native_activity_enabled = self._daily_native_modes(
            assigned_script=assigned_script,
            plan=plan,
        )

        main_configured, eow_configured = resolve_configured_daily_stages(
            plan, assigned_script
        )

        if cultivation_enabled or native_activity_enabled:
            main_configured = True

        effective_eow_enabled = daily_eow_enabled and eow_configured
        if daily_eow_enabled and not eow_configured:
            reason = "本周需要历战余响，但未配置历战余响关卡，已跳过"
            self._append_log(f"用户「{user_name}」历战余响跳过：{reason}")
            self._record_module_result(
                user_id=uid,
                user_name=user_name,
                module_key="EchoOfWar",
                module_name="历战余响",
                script=assigned_script,
                status="skipped",
                reason=reason,
            )

        return main_configured, effective_eow_enabled

    def _build_phase_items(
        self,
        *,
        phase: HSRPhase,
        user_item: UserItem,
        user_cfg,
        plan,
        user_name: str,
        uid: str,
        m7a_path: str,
        m7a_runner: M7ARunner,
        sra_exe_path: Path,
        script_id: str,
        temp_files: list[Path],
        daily_eow_enabled: bool,
    ) -> list[HSRRunItem]:
        """按阶段构建队列，保持 HSR_TASK_MODULES 中的业务顺序。

        模块开关、引擎分配、副本与托管覆盖读 ``plan``；兑换码指纹等完成态读
        ``user_cfg``。
        """

        items: list[HSRRunItem] = []
        effective_engines = resolve_configured_engines(self.script_config)

        for module in HSR_TASK_MODULES:
            if module.category != phase:
                continue
            if not plan.get("TaskSwitch", module.key):
                continue

            # 脚本来源时 plan 是脚本配置，其 Managed.TaskMapping 恒为空，
            # 自然落到脚本级 TaskMapping。
            assigned = resolve_script_assignment(
                module,
                self.script_config,
                user_config=plan,
                effective_engines=effective_engines,
            )
            module_daily_eow_enabled = daily_eow_enabled
            redeem_codes_enabled = True
            redeem_code_fingerprint: str | None = None
            if module.key == "Daily":
                main_configured, module_daily_eow_enabled = (
                    self._resolve_daily_runnable_parts(
                        assigned_script=assigned,
                        plan=plan,
                        user_name=user_name,
                        uid=uid,
                        daily_eow_enabled=daily_eow_enabled,
                    )
                )
                if not main_configured and not module_daily_eow_enabled:
                    reason = "未配置体力主关卡或可执行的历战余响关卡"
                    self._append_log(f"用户「{user_name}」体力模块跳过：{reason}")
                    self._record_module_result(
                        user_id=uid,
                        user_name=user_name,
                        module_key=module.key,
                        module_name=module.name,
                        script=assigned,
                        status="skipped",
                        reason=reason,
                    )
                    continue
            elif module.key == "ReceiveRewards":
                redeem_codes_enabled, redeem_code_fingerprint = (
                    self._resolve_redeem_code_policy(
                        engine=assigned,
                        user_cfg=user_cfg,
                        plan=plan,
                        user_name=user_name,
                    )
                )

            if assigned == "SRA":
                # 培养目标模式由 SRA 原生识别决定副本，塞进 tasklist 的周本不一定
                # 被执行（2.20.0 之前更是完全不读 tasklist），单独跑一次保证周本。
                if module.key == "Daily" and module_daily_eow_enabled:
                    cultivation_enabled, _ = self._daily_native_modes(
                        assigned_script=assigned,
                        plan=plan,
                    )
                    if cultivation_enabled:
                        items.append(
                            self._sra_control.create_echo_of_war_item(
                                user_item=user_item,
                                plan=plan,
                                user_name=user_name,
                                uid=uid,
                                phase=phase,
                                sra_exe_path=sra_exe_path,
                                script_id=script_id,
                                temp_files=temp_files,
                            )
                        )
                        module_daily_eow_enabled = False
                item = self._sra_control.create_module_item(
                    user_item=user_item,
                    user_cfg=user_cfg,
                    plan=plan,
                    user_name=user_name,
                    uid=uid,
                    module=module,
                    phase=phase,
                    sra_exe_path=sra_exe_path,
                    script_id=script_id,
                    temp_files=temp_files,
                    daily_eow_enabled=module_daily_eow_enabled,
                    redeem_codes_enabled=redeem_codes_enabled,
                )
                if item is not None:
                    if (
                        module.key == "ReceiveRewards"
                        and redeem_codes_enabled
                        and redeem_code_fingerprint
                    ):
                        previous_on_success = item.on_success

                        def on_rewards_success(
                            result,
                            previous_on_success=previous_on_success,
                            fingerprint=redeem_code_fingerprint,
                            engine=assigned,
                        ):
                            if previous_on_success is not None:
                                previous_on_success(result)
                            self._queue_data_writeback(
                                user_id=uid,
                                user_name=user_name,
                                reason=f"{engine_label(engine, left=False)}兑换码任务成功完成",
                                fields=[
                                    (
                                        "Data",
                                        f"{engine}RedeemCodeFingerprint",
                                        fingerprint,
                                    )
                                ],
                            )

                        item.on_success = on_rewards_success
                    items.append(item)
            else:
                item = self._m7a_control.create_module_item(
                    user_item=user_item,
                    user_cfg=user_cfg,
                    plan=plan,
                    user_name=user_name,
                    uid=uid,
                    module=module,
                    phase=phase,
                    m7a_path=m7a_path,
                    m7a_runner=m7a_runner,
                    daily_eow_enabled=module_daily_eow_enabled,
                    redeem_codes_enabled=redeem_codes_enabled,
                )
                if item is not None:
                    if (
                        module.key == "ReceiveRewards"
                        and redeem_codes_enabled
                        and redeem_code_fingerprint
                    ):
                        previous_on_success = item.on_success

                        def on_rewards_success(
                            result,
                            previous_on_success=previous_on_success,
                            fingerprint=redeem_code_fingerprint,
                            engine=assigned,
                        ):
                            if previous_on_success is not None:
                                previous_on_success(result)
                            self._queue_data_writeback(
                                user_id=uid,
                                user_name=user_name,
                                reason=f"{engine_label(engine, left=False)}兑换码任务成功完成",
                                fields=[
                                    (
                                        "Data",
                                        f"{engine}RedeemCodeFingerprint",
                                        fingerprint,
                                    )
                                ],
                            )

                        item.on_success = on_rewards_success
                    items.append(item)

        return items

    def _build_login_plan(
        self,
        *,
        user_cfg,
        sra_path: str,
    ) -> HSRLoginPlan:
        """根据 SRA 可用性和账号密码生成本轮登录计划。

        云平台不走 SRA StartGame：按切号处理，由切换器换成本用户的云浏览器，
        登录态在该用户自己的浏览器 profile 里。
        """

        sra_exe_path = Path(sra_path) / "SRA-cli.exe"
        if is_cloud_platform(self.script_config):
            return HSRLoginPlan(mode="cloud", sra_exe_path=sra_exe_path)
        sra_available = bool(sra_path.strip()) and sra_exe_path.exists()
        if not sra_available:
            return HSRLoginPlan(
                mode="m7a_fallback",
                sra_exe_path=sra_exe_path,
            )

        mode = "sra_switch" if user_needs_account_switch(user_cfg) else "sra_remembered"
        return HSRLoginPlan(
            mode=mode,
            sra_exe_path=sra_exe_path,
        )

    def _create_start_game_item(
        self,
        *,
        user_item: UserItem,
        user_cfg,
        user_name: str,
        uid: str,
        phase: HSRPhase,
        login_plan: HSRLoginPlan,
        script_id: str,
        temp_files: list[Path],
    ) -> HSRRunItem:
        """创建统一的 SRA StartGame 登录/切号队列项。"""

        return self._sra_control.create_start_item(
            user_item=user_item,
            user_cfg=user_cfg,
            user_name=user_name,
            uid=uid,
            phase=phase,
            sra_exe_path=login_plan.sra_exe_path,
            script_id=script_id,
            temp_files=temp_files,
        )

    def _with_phase_login_items(
        self,
        phase_items: list[HSRRunItem],
        *,
        user_item: UserItem,
        user_cfg,
        user_name: str,
        uid: str,
        phase: HSRPhase,
        login_plan: HSRLoginPlan,
        script_id: str,
        temp_files: list[Path],
    ) -> list[HSRRunItem]:
        """为一个阶段补齐 SRA StartGame，覆盖阶段重启和 M7A->SRA 混排。"""

        if not phase_items or not login_plan.uses_sra_start_game:
            return phase_items

        items: list[HSRRunItem] = []
        previous_script: str | None = None
        if not any(item.module_key == "StartGame" for item in phase_items):
            items.append(
                self._create_start_game_item(
                    user_item=user_item,
                    user_cfg=user_cfg,
                    user_name=user_name,
                    uid=uid,
                    phase=phase,
                    login_plan=login_plan,
                    script_id=script_id,
                    temp_files=temp_files,
                )
            )

        for item in phase_items:
            if (
                item.module_key != "StartGame"
                and item.script == "SRA"
                and previous_script == "M7A"
            ):
                items.append(
                    self._create_start_game_item(
                        user_item=user_item,
                        user_cfg=user_cfg,
                        user_name=user_name,
                        uid=uid,
                        phase=phase,
                        login_plan=login_plan,
                        script_id=script_id,
                        temp_files=temp_files,
                    )
                )
            items.append(item)
            if item.module_key != "StartGame":
                previous_script = item.script

        return items

    def _with_login_items_for_queue(
        self,
        items: list[HSRRunItem],
        *,
        user_item: UserItem,
        user_cfg,
        user_name: str,
        uid: str,
        login_plan: HSRLoginPlan,
        script_id: str,
        temp_files: list[Path],
    ) -> list[HSRRunItem]:
        """按登录计划为队列补齐阶段级和脚本切换前的 SRA StartGame。"""

        if not items or not login_plan.uses_sra_start_game:
            return items

        result: list[HSRRunItem] = []
        for phase in ("daily", "weekly"):
            phase_items = [item for item in items if item.phase == phase]
            result.extend(
                self._with_phase_login_items(
                    phase_items,
                    user_item=user_item,
                    user_cfg=user_cfg,
                    user_name=user_name,
                    uid=uid,
                    phase=phase,
                    login_plan=login_plan,
                    script_id=script_id,
                    temp_files=temp_files,
                )
            )
        return result

    @staticmethod
    def _retry_phase_needs_login(
        items: list[HSRRunItem],
        *,
        login_plan: HSRLoginPlan,
    ) -> bool:
        """补跑阶段有可用 SRA 时先登录；开头已是登录项时不重复插入。"""

        if not login_plan.uses_sra_start_game:
            return False
        return not (items and items[0].module_key == "StartGame")

    def _build_retry_queue_items(
        self,
        failed_items: list[HSRRunItem],
        *,
        user_item: UserItem,
        user_cfg,
        user_name: str,
        uid: str,
        login_plan: HSRLoginPlan,
        script_id: str,
        temp_files: list[Path],
    ) -> list[HSRRunItem]:
        """按登录计划构造补跑队列；无 SRA 时保留原失败项。"""

        retry_items: list[HSRRunItem] = []

        for phase in ("daily", "weekly"):
            phase_items = [item for item in failed_items if item.phase == phase]
            if not phase_items:
                continue
            # 队列中途重启游戏后插入的登录项失败了也会进失败列表，落在中间：补跑前
            # 游戏刚重启、停在标题画面，只有开头的登录项能救回来，中间那条不再单独补跑。
            phase_items = [
                item
                for index, item in enumerate(phase_items)
                if index == 0 or item.module_key != "StartGame"
            ]

            if self._retry_phase_needs_login(
                phase_items,
                login_plan=login_plan,
            ):
                phase_items = [
                    self._create_start_game_item(
                        user_item=user_item,
                        user_cfg=user_cfg,
                        user_name=user_name,
                        uid=uid,
                        phase=phase,
                        login_plan=login_plan,
                        script_id=script_id,
                        temp_files=temp_files,
                    ),
                    *phase_items,
                ]

            retry_items.extend(
                self._with_phase_login_items(
                    phase_items,
                    user_item=user_item,
                    user_cfg=user_cfg,
                    user_name=user_name,
                    uid=uid,
                    phase=phase,
                    login_plan=login_plan,
                    script_id=script_id,
                    temp_files=temp_files,
                )
            )

        return retry_items

    def _build_user_queue(
        self,
        *,
        user_item: UserItem,
        user_cfg,
        plan,
        user_name: str,
        uid: str,
        m7a_path: str,
        m7a_runner: M7ARunner,
        sra_exe_path: Path,
        login_plan: HSRLoginPlan,
        script_id: str,
        temp_files: list[Path],
    ) -> list[HSRRunItem]:
        """按用户构建本轮 HSR 执行队列。

        ``plan`` 是该用户生效的任务计划（脚本来源为脚本配置，用户来源为
        ``user_cfg`` 本身）；``Data`` / ``Info`` 恒读 ``user_cfg``。
        """

        daily_eow_enabled, eow_is_new_week = self._resolve_daily_params(
            user_cfg, plan=plan
        )
        weekly_skip, weekly_skip_reason, weekly_is_new_week = self._resolve_weekly_skip(
            user_cfg, plan=plan
        )
        logger.debug(
            f"用户「{user_name}」resolver: "
            f"daily_eow_enabled={daily_eow_enabled}, "
            f"eow_is_new_week={eow_is_new_week}, "
            f"weekly_skip={weekly_skip} ({weekly_skip_reason!r}), "
            f"weekly_is_new_week={weekly_is_new_week}"
        )

        daily_items = self._build_phase_items(
            phase="daily",
            user_item=user_item,
            user_cfg=user_cfg,
            plan=plan,
            user_name=user_name,
            uid=uid,
            m7a_path=m7a_path,
            m7a_runner=m7a_runner,
            sra_exe_path=sra_exe_path,
            script_id=script_id,
            temp_files=temp_files,
            daily_eow_enabled=daily_eow_enabled,
        )
        items = list(daily_items)

        weekly_due = not weekly_skip

        if weekly_due:
            items.extend(
                self._build_phase_items(
                    phase="weekly",
                    user_item=user_item,
                    user_cfg=user_cfg,
                    plan=plan,
                    user_name=user_name,
                    uid=uid,
                    m7a_path=m7a_path,
                    m7a_runner=m7a_runner,
                    sra_exe_path=sra_exe_path,
                    script_id=script_id,
                    temp_files=temp_files,
                    daily_eow_enabled=daily_eow_enabled,
                )
            )
        else:
            self._append_log(f"用户「{user_name}」周常跳过：{weekly_skip_reason}")

        return self._with_login_items_for_queue(
            items,
            user_item=user_item,
            user_cfg=user_cfg,
            user_name=user_name,
            uid=uid,
            login_plan=login_plan,
            script_id=script_id,
            temp_files=temp_files,
        )

    @staticmethod
    def _remaining_items_after(
        items: list[HSRRunItem],
        *,
        phases: tuple[HSRPhase, ...],
        phase_index: int,
        phase_items: list[HSRRunItem],
        item_index: int,
        failures: list[HSRRunItem],
        reason: str,
    ) -> list[HSRRunItem]:
        """返回当前项之后尚未执行且尚未标记失败的队列项，并写入未执行原因。"""

        remaining = list(phase_items[item_index + 1 :])
        for later_phase in phases[phase_index + 1 :]:
            remaining.extend(item for item in items if item.phase == later_phase)
        skipped = [
            candidate
            for candidate in remaining
            if all(candidate is not failed for failed in failures)
        ]
        for candidate in skipped:
            candidate.last_error = reason
        return skipped

    def _login_item_after_restart(self, item: HSRRunItem) -> HSRRunItem | None:
        """队列中途重启游戏后，``item`` 之前是否要先补一次 SRA 登录。

        只有 MAS 真的重启了本地客户端（客户端平台且管理游戏）、登录计划走 SRA
        StartGame、且下一个是 SRA 的非登录模块时才需要：三月七自己会处理进入
        游戏；紧跟着的若本来就是登录项也不重复插。
        """

        factory = getattr(self, "_restart_login_item_factory", None)
        if factory is None or item.script != "SRA" or item.module_key == "StartGame":
            return None
        if is_cloud_platform(self.script_config) or not is_game_management_enabled(
            self.script_config
        ):
            return None
        self._append_log(
            f"用户「{item.user_name}」游戏已重启，执行 SRA 模块「{item.module_name}」前"
            "先登录进入游戏"
        )
        return factory(item.phase)

    async def _run_queue_items(
        self,
        items: list[HSRRunItem],
    ) -> list[HSRRunItem]:
        """执行一组队列项并返回失败项。"""

        failures: list[HSRRunItem] = []
        completed_phases: set[HSRPhase] = set()
        # 模块失败（超时被终止、报错、判定失败）后画面停在哪里不可知，下一个模块
        # 直接接着跑只会在脏画面上再失败一次：先由 MAS 重启游戏再继续。补跑同样
        # 走这里，每个失败模块之后都重启，而不是每轮尝试只在开头重启一次。
        restart_reason: str | None = None
        phases: tuple[HSRPhase, ...] = ("daily", "weekly")
        phase_labels = {
            "daily": "日常",
            "weekly": "周常",
        }

        for phase_index, phase in enumerate(phases):
            phase_items = [item for item in items if item.phase == phase]
            if not phase_items:
                continue

            user_name = phase_items[0].user_name
            if completed_phases:
                await self._restart_game(user_name, f"进入{phase_labels[phase]}阶段前")
                restart_reason = None
            completed_phases.add(phase)

            item_index = -1
            while item_index + 1 < len(phase_items):
                item_index += 1
                item = phase_items[item_index]
                if restart_reason is not None:
                    await self._restart_game(
                        item.user_name,
                        f"{restart_reason}，执行模块「{item.module_name}」前",
                    )
                    restart_reason = None
                    # 重启后游戏停在标题 / 登录画面：SRA 的非登录任务从大世界或
                    # ESC 菜单起步，先插一次登录；登录项失败时按登录失败中止后续。
                    login_item = self._login_item_after_restart(item)
                    if login_item is not None:
                        phase_items.insert(item_index, login_item)
                        item = login_item
                item.attempts += 1
                self._append_log(
                    f"用户「{item.user_name}」执行{engine_label(item.script)}"
                    f"{item.module_name}：{item.description}"
                )
                try:
                    result = await self._run_item_with_game_guard(item)
                except asyncio.CancelledError:
                    raise
                except HSRNonRetryableTaskError as e:
                    # 云·星穹铁道的登录超时、排队超时、时长耗尽、浏览器起不来：
                    # 后面的模块和补跑都只会再撞一遍，本用户本轮直接判失败。
                    item.last_error = str(e)
                    item.retryable = False
                    failures.append(item)
                    self._append_log(
                        f"用户「{item.user_name}」模块「{item.module_name}」执行失败"
                        f"（不重试）：{item.last_error}"
                    )
                    remaining = self._remaining_items_after(
                        items,
                        phases=phases,
                        phase_index=phase_index,
                        phase_items=phase_items,
                        item_index=item_index,
                        failures=failures,
                        reason=HSR_ABORT_REASON_CLOUD,
                    )
                    for skipped in remaining:
                        skipped.retryable = False
                    if remaining:
                        self._append_log(
                            f"用户「{item.user_name}」{HSR_ABORT_REASON_CLOUD}"
                            f"（共 {len(remaining)} 项）"
                        )
                    failures.extend(remaining)
                    await self._send_task_notice(
                        "error",
                        f"HSR 用户「{item.user_name}」{item.module_name}失败，"
                        f"本轮不再补跑：{item.last_error}",
                    )
                    return failures
                except HSRRetryableTaskError as e:
                    item.last_error = str(e)
                    failures.append(item)
                    self._append_log(
                        f"用户「{item.user_name}」模块「{item.module_name}」执行失败："
                        f"{item.last_error}"
                    )
                    abort_reason: str | None = None
                    if item.module_key == "StartGame":
                        abort_reason = HSR_ABORT_REASON_LOGIN_FAILED
                    elif isinstance(e, HSRGameExitedError):
                        # 游戏已经没了，再启动后续模块只会白跑一次并再记一条失败。
                        abort_reason = HSR_ABORT_REASON_GAME_EXITED
                    if abort_reason is not None:
                        remaining = self._remaining_items_after(
                            items,
                            phases=phases,
                            phase_index=phase_index,
                            phase_items=phase_items,
                            item_index=item_index,
                            failures=failures,
                            reason=abort_reason,
                        )
                        if remaining:
                            self._append_log(
                                f"用户「{item.user_name}」{abort_reason}"
                                f"（共 {len(remaining)} 项）"
                            )
                        failures.extend(remaining)
                        return failures
                    restart_reason = f"模块「{item.module_name}」失败后"
                    continue
                except Exception as e:  # noqa: BLE001
                    # 非 HSRRetryableTaskError 的异常是配置或代码错误, 补跑也不会
                    # 变好: 记录堆栈、记为失败但标记不可重试, 后续模块照常继续
                    item.last_error = str(e)
                    item.retryable = False
                    failures.append(item)
                    logger.opt(exception=True).warning(
                        f"用户「{item.user_name}」模块「{item.module_name}」执行异常："
                        f"{item.last_error}"
                    )
                    self._append_log(
                        f"用户「{item.user_name}」模块「{item.module_name}」执行异常："
                        f"{item.last_error}"
                    )
                    if item.module_key == "StartGame":
                        remaining = self._remaining_items_after(
                            items,
                            phases=phases,
                            phase_index=phase_index,
                            phase_items=phase_items,
                            item_index=item_index,
                            failures=failures,
                            reason=HSR_ABORT_REASON_LOGIN_FAILED,
                        )
                        for skipped in remaining:
                            skipped.retryable = False
                        if remaining:
                            self._append_log(
                                f"用户「{item.user_name}」{HSR_ABORT_REASON_LOGIN_FAILED}"
                                f"（共 {len(remaining)} 项）"
                            )
                        failures.extend(remaining)
                        return failures
                    restart_reason = f"模块「{item.module_name}」异常后"
                    continue

                if bool(getattr(result, "success", False)):
                    if item.on_success is not None:
                        item.on_success(result)
                    # 历战余响、差分宇宙、货币战争的最终结果由 on_success 按日志判定
                    # 并记满「完成 / 未完成」两条分支；这里再兜底记一次「完成」，
                    # 会因后写入为准把「未完成」覆盖成「完成」。
                    if item.module_key not in (
                        "StartGame",
                        "EchoOfWar",
                        "DivergentUniverse",
                        "CurrencyWars",
                    ):
                        self._record_module_result(
                            user_id=item.user_id,
                            user_name=item.user_name,
                            module_key=item.module_key,
                            module_name=item.module_name,
                            script=item.script,
                            status="completed",
                            reason="外部脚本返回成功",
                        )
                    self._append_log(
                        f"用户「{item.user_name}」模块「{item.module_name}」执行完成"
                    )
                    continue

                item.last_error = external_result_failure_summary(result)
                failures.append(item)
                self._append_log(
                    f"用户「{item.user_name}」模块「{item.module_name}」执行失败："
                    f"{item.last_error}"
                )

                if item.module_key == "StartGame":
                    remaining = self._remaining_items_after(
                        items,
                        phases=phases,
                        phase_index=phase_index,
                        phase_items=phase_items,
                        item_index=item_index,
                        failures=failures,
                        reason=HSR_ABORT_REASON_LOGIN_FAILED,
                    )
                    failures.extend(remaining)
                    return failures
                restart_reason = f"模块「{item.module_name}」失败后"

        return failures

    async def _run_item_with_game_guard(self, item: HSRRunItem) -> object:
        """执行外部模块；启用游戏管理时监测游戏进程并及时中止脚本。"""

        run_task = asyncio.create_task(item.run())
        try:
            # 云平台没有 StarRail.exe；浏览器存活由每个三月七模块开跑前检查，
            # 死了重起而不是判「游戏退出」。
            if is_cloud_platform(self.script_config) or not is_game_management_enabled(
                self.script_config
            ):
                return await run_task

            while not run_task.done():
                await asyncio.sleep(1)
                # 睡醒后先复查任务态：外部脚本可能在这 1 秒里先关掉游戏再自行
                # 退出，此时任务已经完成，不能再拿「游戏进程不在」去取消它。
                if run_task.done():
                    break
                if self.runtime.game_transitioning:
                    continue
                if is_process_running(HSR_GAME_PROCESS_NAME):
                    continue
                # 进程刚消失时先让出一拍：让读输出的协程把 M7A 关游戏前打的
                # 那行 ERROR 收进来，也给「脚本自己关掉游戏后紧接着退出」留出
                # 自然结束的机会。
                await asyncio.sleep(GAME_EXIT_SETTLE_SECONDS)
                if run_task.done():
                    break
                reason = self._describe_game_exit(item)
                await self._stop_external_processes()
                run_task.cancel()
                with suppress(BaseException):
                    await run_task
                raise HSRGameExitedError(reason)
            return await run_task
        except asyncio.CancelledError:
            run_task.cancel()
            with suppress(BaseException):
                await run_task
            raise

    def _describe_game_exit(self, item: HSRRunItem) -> str:
        """游戏进程消失时给出准确归因。

        M7A 等 6 分钟识不出任何界面会自己 stop_game() 再 continue 重启游戏，
        这时把失败写成「进程已退出，若是用户主动关闭…」既冤枉用户，也把真正
        的原因（画面卡在哪、错误截图在哪）藏进了几十行 WARNING 里。
        """

        runner = self.runtime.m7a_runner
        if item.script == "M7A" and runner is not None:
            recent = runner.recent_output_lines
            if find_m7a_self_game_stop(recent) is not None:
                cause = (
                    "长时间未识别出游戏界面"
                    if any("获取当前界面超时" in line for line in recent)
                    else "启动或检查游戏时出错"
                )
                detail = "\n".join(select_failure_summary_lines(recent))
                return (
                    f"三月七{cause}，已自行关闭游戏；"
                    "MAS 已终止本次三月七，补跑前会重新启动游戏。三月七最后的报错："
                    f"\n{detail}"
                )
        return (
            "检测到星穹铁道进程已退出，已终止当前外部脚本；"
            "若是用户主动关闭游戏，请同时在 MAS 中停止任务"
        )

    def _format_queue_failures(
        self,
        failures: list[HSRRunItem],
        retry_limit: int,
    ) -> str:
        """格式化用户级重试后仍失败的任务。"""

        parts = [f"HSR 用户任务重试后仍未完成（最大尝试次数 {retry_limit}）"]
        for item in failures:
            parts.append(
                f"用户「{item.user_name}」模块「{item.module_name}」"
                f"（{engine_label(item.script, left=False, right=False)}，"
                f"已尝试 {item.attempts} 次）："
                f"{item.last_error or '未知错误'}"
            )
        return "\n".join(parts)

    async def _prepare_before_first_attempt(
        self,
        *,
        user_name: str,
        login_plan: HSRLoginPlan,
    ) -> None:
        """首轮执行前按登录计划准备游戏状态。"""

        if login_plan.needs_account_switch:
            await self._account_switcher.prepare_game_for_account_switch(user_name)
            return

        self.runtime.game_launch_checked = False
        await self._account_switcher.ensure_game_started_by_mas()

    async def _prepare_before_retry_attempt(self, user_name: str) -> None:
        """补跑前按开关准备游戏状态，必要时重启游戏。"""

        await self._restart_game(user_name, "补跑失败任务前")

    async def main_task(self):
        """执行当前用户的 HSR 队列。"""

        user_item = self.cur_user_item
        uid = user_item.user_id
        user_cfg = self.cur_user_config
        user_name = user_cfg.get("Info", "Name")
        # 直控用户由 HSRManager._run_direct_user 执行，不会进这里。
        plan = resolve_plan(user_cfg, self.script_config)
        if plan is None:
            raise RuntimeError(f"用户「{user_name}」为直控来源，不能进入 MAS 托管队列")
        m7a_path = resolve_script_path(self.script_config, "M7A")
        sra_path = resolve_script_path(self.script_config, "SRA")
        script_id = self.script_info.script_id
        retry_limit = self._get_run_times_limit()
        self.user_start_time = datetime.now()

        m7a_runner = self.runtime.m7a_runner
        if m7a_runner is None or m7a_runner.root_path != Path(m7a_path):
            m7a_runner = M7ARunner(
                Path(m7a_path),
                log_callback=self._append_log,
                output_line_callback=(
                    self._account_switcher.recover_game_window_if_screenshot_blocked
                ),
            )
            self.runtime.m7a_runner = m7a_runner
        # 平台钉扎走环境变量（优先于 config.yaml），与 patch 里的平台字段一致。
        configure_m7a_runner(m7a_runner, self.script_config)
        # 运行器在用户之间复用，逐行回调要换成当前用户的（云登录提醒、剩余时长
        # 与 LastLogin 都按当前用户记）。
        m7a_runner.set_output_line_callback(self._on_m7a_output_line)
        login_plan = self._build_login_plan(user_cfg=user_cfg, sra_path=sra_path)
        if login_plan.uses_sra_start_game:

            def build_restart_login_item(phase: HSRPhase) -> HSRRunItem:
                return self._create_start_game_item(
                    user_item=user_item,
                    user_cfg=user_cfg,
                    user_name=user_name,
                    uid=uid,
                    phase=phase,
                    login_plan=login_plan,
                    script_id=script_id,
                    temp_files=self.temp_files,
                )

            self._restart_login_item_factory = build_restart_login_item
        else:
            self._restart_login_item_factory = None

        # 物化前归档本用户字段侧车（_build_user_queue 会把托管字段注入原生
        # 配置；指纹去重，失败只记日志不阻断运行——native 池由 manager
        # prepare 在任务级一次性归档）
        archive_mas_runtime_backup(
            script_id, uid, read_mas_overlay(user_cfg, self.script_config)
        )

        full_queue = self._build_user_queue(
            user_item=user_item,
            user_cfg=user_cfg,
            plan=plan,
            user_name=user_name,
            uid=uid,
            m7a_path=m7a_path,
            m7a_runner=m7a_runner,
            sra_exe_path=login_plan.sra_exe_path,
            login_plan=login_plan,
            script_id=script_id,
            temp_files=self.temp_files,
        )
        self.steps_count = len(full_queue)

        if not full_queue:
            self._start_user_log(user_item, user_name)
            self._append_log(f"用户「{user_name}」本轮没有需要执行的 HSR 任务")
            self._finish_current_user_log("HSR 本轮无需执行，已跳过")
            return

        # 执行任务前脚本（每用户仅一次，补跑不重复执行）
        await run_script_before_task(user_cfg)

        failed_items: list[HSRRunItem] = []
        permanent_failures: list[HSRRunItem] = []
        current_items = full_queue
        for attempt in range(1, retry_limit + 1):
            if not current_items:
                break

            self._start_user_log(
                user_item,
                user_name,
                attempt=attempt,
                retry_limit=retry_limit,
            )
            try:
                if attempt == 1:
                    await self._prepare_before_first_attempt(
                        user_name=user_name,
                        login_plan=login_plan,
                    )
                else:
                    await self._prepare_before_retry_attempt(user_name)

                failed_items = await self._run_queue_items(current_items)
            except asyncio.CancelledError:
                self._mark_current_user_abnormal("任务被用户手动中止")
                raise
            except Exception as e:  # noqa: BLE001
                self._mark_current_user_abnormal(f"HSR 运行异常: {e}")
                raise

            if not failed_items:
                status = "HSR 用户任务完成" if attempt == 1 else "HSR 失败任务补跑完成"
            else:
                status = (
                    "HSR 用户任务部分失败"
                    if attempt == 1
                    else "HSR 失败任务补跑部分失败"
                )
            # 只要日常阶段有模块执行成功，就登记代理日期；
            # 后续周常失败不影响日常已完成的事实。
            _daily_items = [
                i
                for i in current_items
                if i.phase == "daily" and i.module_key != "StartGame"
            ]
            _daily_failed = [
                i
                for i in failed_items
                if i.phase == "daily" and i.module_key != "StartGame"
            ]
            if _daily_items and len(_daily_failed) < len(_daily_items):
                self._queue_daily_proxy_completion(uid, user_name)
            # 结束当前用户日志会清空用户上下文，每轮只能调用一次；
            # 用户状态必须在这一次里定好，否则后续补写全部失效。
            if not failed_items:
                self._finish_current_user_log(status)
                # 执行任务后脚本（每用户仅一次）
                await run_script_after_task(user_cfg)
                return

            # 不可重试的失败（配置或代码错误）只记结果, 不进补跑队列
            permanent_failures.extend(i for i in failed_items if not i.retryable)
            retryable_failures = [i for i in failed_items if i.retryable]
            if attempt < retry_limit and retryable_failures:
                if is_cloud_platform(self.script_config):
                    retry_action = "云·星穹铁道保持浏览器，直接补跑"
                elif is_game_management_enabled(self.script_config):
                    retry_action = "将重新启动游戏后补跑"
                else:
                    retry_action = "MAS 未管理游戏，直接补跑"
                self._append_log(
                    f"用户「{user_name}」第 {attempt}/{retry_limit} 次尝试后，"
                    f"仍有 {len(retryable_failures)} 个失败任务，{retry_action}"
                )
                self._finish_current_user_log(status, user_status="运行")
                current_items = self._build_retry_queue_items(
                    retryable_failures,
                    user_item=user_item,
                    user_cfg=user_cfg,
                    user_name=user_name,
                    uid=uid,
                    login_plan=login_plan,
                    script_id=script_id,
                    temp_files=self.temp_files,
                )
            else:
                self._finish_current_user_log(status, user_status="异常")
                failed_items = permanent_failures + retryable_failures
                for failed_item in failed_items:
                    if failed_item.module_key == "StartGame":
                        continue
                    self._record_module_result(
                        user_id=failed_item.user_id,
                        user_name=failed_item.user_name,
                        module_key=failed_item.module_key,
                        module_name=failed_item.module_name,
                        script=failed_item.script,
                        status="failed",
                        reason=failed_item.last_error or "重试后仍未完成",
                    )
                # 执行任务后脚本（每用户仅一次）
                await run_script_after_task(user_cfg)
                raise RuntimeError(
                    self._format_queue_failures(failed_items, retry_limit)
                )

    async def final_task(self):
        """用户任务结束后清理临时配置；异常时停止外部脚本。"""

        if self.crashed:
            await self._stop_external_processes()
        await self._push_user_statistics_notification()
        for tp in self.temp_files:
            cleanup_sra_temp_config(tp)

    async def on_crash(self, e: Exception):
        self.crashed = True
        self.error_message = str(e)
        self._mark_current_user_abnormal(f"HSR 用户任务异常: {e}")
        logger.opt(exception=True).warning(
            f"HSR 用户「{self.cur_user_item.name}」任务出现异常：{e}"
        )
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(
                level="error",
                message=f"HSR 用户「{self.cur_user_item.name}」任务出现异常：{e}",
            ),
        )
