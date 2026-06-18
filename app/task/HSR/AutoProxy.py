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
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Literal

from app.core import Config
from app.models.ConfigBase import MultipleConfig
from app.models.config import HSRConfig, HSRUserConfig
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase, UserItem
from app.services.system import System
from app.utils import ProcessManager, get_logger, is_process_running
from app.utils.constants import UTC4, UTC8
from .task_mapping import HSR_TASK_MODULES, get_assigned_script
from .tools.m7a_control import HSRM7AControl
from .tools.run_model import (
    CompletionWriteback,
    HSRLoginPlan,
    HSRModuleResult,
    HSRModuleResultStatus,
    HSRPhase,
    HSRRetryableTaskError,
    HSRRunItem,
    HSRRuntimeState,
    external_result_failure_summary,
)
from .tools.sra_control import HSRSRAControl
from .tools.account_switch import (
    HSRAccountSwitcher,
    HSR_GAME_PROCESS_NAME,
    HSR_GAME_READY_DELAY_SECONDS,
    stop_external_processes,
    resolve_game_executable_path,
    user_needs_account_switch,
)
from .tools import push_notification
from .tools.log_detect import detect_echo_of_war_completion
from .tools.m7a_runtime import M7ARunner
from .tools.sra_runtime import cleanup_sra_temp_config
from .tools.stage_runtime import (
    get_sra_native_stage,
    read_native_main_stage,
    read_native_stage,
    resolve_m7a_eow_stage,
    resolve_m7a_main_stage,
)

logger = get_logger("HSR 自动代理")

PHASE_TIMEOUT_CONFIG: dict[HSRPhase, tuple[str, int]] = {
    "daily": ("DailyTimeLimit", 20),
    "weekly": ("WeeklyTimeLimit", 60),
    "monthly": ("MonthlyTimeLimit", 60),
}

MODULE_KEYS_BY_PHASE: dict[HSRPhase, tuple[str, ...]] = {
    phase: tuple(
        module.key for module in HSR_TASK_MODULES if module.category == phase
    )
    for phase in ("daily", "weekly", "monthly")
}


def _has_enabled_phase_module(user_config, phase: HSRPhase) -> bool:
    """判断用户是否启用了指定周期的任一 HSR 模块。"""

    return any(
        bool(user_config.get("TaskSwitch", key))
        for key in MODULE_KEYS_BY_PHASE[phase]
    )


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
            queue_abyss_completion=self._queue_abyss_completion,
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

    def _append_log(self, message: str, *, max_lines: int = 500) -> None:
        text = str(message).strip()
        if not text:
            return
        now_text = datetime.now(tz=UTC8).strftime("%H:%M:%S")
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
            self._current_user_log.content.extend(f"{line}\n" for line in appended_lines)

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
            "monthly",
        )
        return self._timeout_seconds_for_phase(phase)

    async def _restart_game(self, user_name: str, reason: str) -> None:
        """由 MAS 关闭并重新启动游戏。"""

        game_exe_path = resolve_game_executable_path(self.script_config)
        process_name = HSR_GAME_PROCESS_NAME

        self._append_log(
            f"用户「{user_name}」{reason}，正在由 MAS 重启游戏"
        )
        await self._stop_external_processes()

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
                f"已请求关闭游戏，等待 "
                f"{HSR_GAME_READY_DELAY_SECONDS}s 后重新启动"
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
    ) -> tuple[str, str, str]:
        """返回当前日期、ISO 周、自然月标记。"""

        if now_dt is None:
            now_dt = datetime.now(tz=UTC8)
        iso_year, iso_week, _ = now_dt.isocalendar()
        return (
            now_dt.strftime("%Y-%m-%d"),
            f"{iso_year:04d}-W{iso_week:02d}",
            now_dt.strftime("%Y-%m"),
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
        logger.info(
            f"用户「{user_name}」已登记 HSR 完成态写回：{reason}"
        )

    @staticmethod
    def _build_daily_proxy_writeback_fields(
        user_config,
        now_dt: datetime | None = None,
    ) -> list[tuple[str, str, object]]:
        """构造日常代理状态写回字段，口径与用户列表标签保持一致。"""

        if now_dt is None:
            now_dt = datetime.now(tz=UTC4)

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
            text = f"{item.module_name}（{item.script}）：{label}"
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
            logger.exception(f"推送 HSR 用户统计通知时出现异常: {e}")
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": f"推送 HSR 用户统计通知时出现异常: {e}"},
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

        completed, reason = detect_echo_of_war_completion(result, script)
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
        today, current_week, _ = self._period_markers()
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

        today, current_week, _ = self._period_markers()
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

    def _queue_abyss_completion(
        self,
        user_id: str,
        user_name: str,
    ) -> None:
        """三深渊三项全部成功后，登记本月完成态。"""

        today, _, current_month = self._period_markers()
        self._queue_data_writeback(
            user_id=user_id,
            user_name=user_name,
            reason="三深渊三项全部成功执行",
            fields=[
                ("Data", "AbyssCompletedThisMonth", True),
                ("Data", "AbyssLastResetMonth", current_month),
                ("Data", "AbyssLastCompletionDate", today),
            ],
        )

    @staticmethod
    def _resolve_daily_params(
        user_config,
        now_dt: datetime | None = None,
    ) -> tuple[bool, bool]:
        """解析本周历战余响任务，不写用户 Data。"""

        weekday_options = [
            "Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday",
        ]
        eow_target = user_config.get("TaskOpt", "EchoOfWarWeekday") or "Monday"
        if eow_target not in weekday_options:
            eow_target = "Monday"

        if now_dt is None:
            now_dt = datetime.now(tz=UTC8)
        iso_year, iso_week, _ = now_dt.isocalendar()
        now_week = f"{iso_year:04d}-W{iso_week:02d}"

        last_reset_week = user_config.get("Data", "EchoOfWarLastResetWeek") or "2000-W01"
        eow_is_new_week = last_reset_week != now_week
        eow_completed_this_week = (
            not eow_is_new_week
            and bool(user_config.get("Data", "EchoOfWarCompletedThisWeek"))
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
    ) -> tuple[bool, str, bool]:
        """解析周常是否本周已完成，不写用户 Data。"""
        weekly_enabled = _has_enabled_phase_module(user_config, "weekly")

        if now_dt is None:
            now_dt = datetime.now(tz=UTC8)
        iso_year, iso_week, _ = now_dt.isocalendar()
        now_week = f"{iso_year:04d}-W{iso_week:02d}"

        last_reset_week = (
            user_config.get("Data", "WeeklyLastResetWeek") or "2000-W01"
        )
        weekly_done_stored = bool(
            user_config.get("Data", "WeeklyCompletedThisWeek")
        )

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

    @staticmethod
    def _resolve_abyss_monthly_skip(
        user_config,
        now_dt: datetime | None = None,
    ) -> tuple[bool, str, bool]:
        """解析三深渊本自然月是否已完成（纯计算，不修改 user_config / Data 字段）。

        跨月时只在内存中按“新月已重置”计算，执行成功后的完成态由
        调度器在三个深渊全部成功后统一写回。
        """
        monthly_enabled = _has_enabled_phase_module(user_config, "monthly")

        if now_dt is None:
            now_dt = datetime.now(tz=UTC8)
        now_month = now_dt.strftime("%Y-%m")

        last_reset_month = (
            user_config.get("Data", "AbyssLastResetMonth") or "2000-01"
        )
        done_stored = bool(
            user_config.get("Data", "AbyssCompletedThisMonth")
        )

        if last_reset_month != now_month:
            # 跨月 —— 仅在内存中按"新月已重置"计算
            is_new_month_in_mem = True
            done_in_mem = False
        else:
            is_new_month_in_mem = False
            done_in_mem = done_stored

        if not monthly_enabled:
            return True, "已关闭月常", is_new_month_in_mem
        if done_in_mem:
            return True, "本月已完成（三深渊）", is_new_month_in_mem

        return False, "", is_new_month_in_mem

    def _timeout_seconds_for_phase(self, phase: HSRPhase) -> int:
        """按周期读取超时配置，返回秒。"""

        key, default = PHASE_TIMEOUT_CONFIG[phase]
        minutes = int(self.script_config.get("Run", key) or default)
        return max(1, minutes) * 60

    def _phase_timeout_seconds(self, phase: HSRPhase) -> int:
        """按阶段读取超时配置，返回秒。"""

        return self._timeout_seconds_for_phase(phase)

    def _resolve_daily_runnable_parts(
        self,
        *,
        assigned_script: str,
        user_cfg,
        user_name: str,
        uid: str,
        daily_eow_enabled: bool,
    ) -> tuple[bool, bool]:
        """判断体力模块实际可执行内容；缺少关卡配置时跳过而不是失败。"""

        if assigned_script == "SRA":
            main_configured = (
                get_sra_native_stage(read_native_main_stage(user_cfg)) is not None
            )
            eow_configured = (
                get_sra_native_stage(
                    read_native_stage(user_cfg, "ScriptEchoOfWar")
                )
                is not None
            )
        else:
            main_configured = resolve_m7a_main_stage(user_cfg) is not None
            eow_configured = resolve_m7a_eow_stage(user_cfg) is not None

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
        user_name: str,
        uid: str,
        m7a_path: str,
        m7a_runner: M7ARunner,
        sra_exe_path: Path,
        script_id: str,
        temp_files: list[Path],
        daily_eow_enabled: bool,
    ) -> list[HSRRunItem]:
        """按阶段构建队列，保持 HSR_TASK_MODULES 中的业务顺序。"""

        items: list[HSRRunItem] = []

        for module in HSR_TASK_MODULES:
            if module.category != phase:
                continue
            if not user_cfg.get("TaskSwitch", module.key):
                continue

            assigned = get_assigned_script(module, self.script_config)
            module_daily_eow_enabled = daily_eow_enabled
            if module.key == "Daily":
                main_configured, module_daily_eow_enabled = (
                    self._resolve_daily_runnable_parts(
                        assigned_script=assigned,
                        user_cfg=user_cfg,
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

            if assigned == "SRA":
                item = self._sra_control.create_module_item(
                    user_item=user_item,
                    user_cfg=user_cfg,
                    user_name=user_name,
                    uid=uid,
                    module=module,
                    phase=phase,
                    sra_exe_path=sra_exe_path,
                    script_id=script_id,
                    temp_files=temp_files,
                    daily_eow_enabled=module_daily_eow_enabled,
                )
                if item is not None:
                    items.append(item)
            else:
                item = self._m7a_control.create_module_item(
                    user_item=user_item,
                    user_cfg=user_cfg,
                    user_name=user_name,
                    uid=uid,
                    module=module,
                    phase=phase,
                    m7a_path=m7a_path,
                    m7a_runner=m7a_runner,
                    daily_eow_enabled=module_daily_eow_enabled,
                )
                if item is not None:
                    items.append(item)

        return items

    def _build_login_plan(
        self,
        *,
        user_cfg,
        sra_path: str,
    ) -> HSRLoginPlan:
        """根据 SRA 可用性和账号密码生成本轮登录计划。"""

        sra_exe_path = Path(sra_path) / "SRA-cli.exe"
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
        for phase in ("daily", "weekly", "monthly"):
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
        """补跑阶段有可用 SRA 时先登录；已有登录项时不重复插入。"""

        if not login_plan.uses_sra_start_game:
            return False
        return not any(item.module_key == "StartGame" for item in items)

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

        for phase in ("daily", "weekly", "monthly"):
            phase_items = [item for item in failed_items if item.phase == phase]
            if not phase_items:
                continue

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
        user_name: str,
        uid: str,
        m7a_path: str,
        m7a_runner: M7ARunner,
        sra_exe_path: Path,
        login_plan: HSRLoginPlan,
        script_id: str,
        temp_files: list[Path],
    ) -> list[HSRRunItem]:
        """按用户构建本轮 HSR 执行队列。"""

        daily_eow_enabled, eow_is_new_week = self._resolve_daily_params(user_cfg)
        weekly_skip, weekly_skip_reason, weekly_is_new_week = (
            self._resolve_weekly_skip(user_cfg)
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

        abyss_skip, abyss_skip_reason, abyss_is_new_month = (
            self._resolve_abyss_monthly_skip(user_cfg)
        )
        logger.debug(
            f"用户「{user_name}」monthly resolver: "
            f"abyss_skip={abyss_skip} ({abyss_skip_reason!r}), "
            f"abyss_is_new_month={abyss_is_new_month}"
        )
        if abyss_skip:
            self._append_log(f"用户「{user_name}」月常跳过：{abyss_skip_reason}")
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

        items.extend(
            self._build_phase_items(
                phase="monthly",
                user_item=user_item,
                user_cfg=user_cfg,
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
    ) -> list[HSRRunItem]:
        """返回当前项之后尚未执行且尚未标记失败的队列项。"""

        remaining = list(phase_items[item_index + 1:])
        for later_phase in phases[phase_index + 1:]:
            remaining.extend(item for item in items if item.phase == later_phase)
        return [
            candidate for candidate in remaining
            if all(candidate is not failed for failed in failures)
        ]

    async def _run_queue_items(
        self,
        items: list[HSRRunItem],
    ) -> list[HSRRunItem]:
        """执行一组队列项并返回失败项。"""

        failures: list[HSRRunItem] = []
        completed_phases: set[HSRPhase] = set()
        phases: tuple[HSRPhase, ...] = ("daily", "weekly", "monthly")
        phase_labels = {
            "daily": "日常",
            "weekly": "周常",
            "monthly": "月常",
        }

        for phase_index, phase in enumerate(phases):
            phase_items = [item for item in items if item.phase == phase]
            if not phase_items:
                continue

            user_name = phase_items[0].user_name
            if completed_phases:
                await self._restart_game(user_name, f"进入{phase_labels[phase]}阶段前")
            completed_phases.add(phase)

            for item_index, item in enumerate(phase_items):
                item.attempts += 1
                self._append_log(
                    f"用户「{item.user_name}」执行 {item.script} "
                    f"{item.module_name}：{item.description}"
                )
                try:
                    result = await self._run_item_with_game_guard(item)
                except asyncio.CancelledError:
                    raise
                except HSRRetryableTaskError as e:
                    item.last_error = str(e)
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
                        )
                        for candidate in remaining:
                            candidate.last_error = "SRA 登录/切号失败，当前阶段未执行"
                        failures.extend(remaining)
                        return failures
                    continue
                except Exception as e:  # noqa: BLE001
                    item.last_error = str(e)
                    failures.append(item)
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
                        )
                        for candidate in remaining:
                            candidate.last_error = "SRA 登录/切号失败，当前阶段未执行"
                        failures.extend(remaining)
                        return failures
                    continue

                if bool(getattr(result, "success", True)):
                    if item.on_success is not None:
                        item.on_success(result)
                    if item.module_key != "StartGame":
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
                    )
                    for candidate in remaining:
                        candidate.last_error = "SRA 登录/切号失败，当前阶段未执行"
                    failures.extend(remaining)
                    return failures

        return failures

    async def _run_item_with_game_guard(self, item: HSRRunItem) -> object:
        """执行单个外部模块；若游戏进程被关闭，尽快中止外部脚本。"""

        run_task = asyncio.create_task(item.run())
        try:
            while not run_task.done():
                await asyncio.sleep(1)
                if self.runtime.game_transitioning:
                    continue
                if not is_process_running(HSR_GAME_PROCESS_NAME):
                    await self._stop_external_processes()
                    run_task.cancel()
                    with suppress(BaseException):
                        await run_task
                    raise HSRRetryableTaskError(
                        "检测到星穹铁道进程已退出，已终止当前外部脚本；"
                        "若是用户主动关闭游戏，请同时在 MAS 中停止任务"
                    )
            return await run_task
        except asyncio.CancelledError:
            run_task.cancel()
            with suppress(BaseException):
                await run_task
            raise

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
                f"（{item.script}，已尝试 {item.attempts} 次）："
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
        """补跑前统一重启游戏，避免外部脚本继承异常场景。"""

        await self._restart_game(user_name, "补跑失败任务前")

    async def main_task(self):
        """执行当前用户的 HSR 队列。"""

        user_item = self.cur_user_item
        uid = user_item.user_id
        user_cfg = self.cur_user_config
        user_name = user_cfg.get("Info", "Name")
        m7a_path = self.script_config.get("Info", "M7APath") or ""
        sra_path = self.script_config.get("Info", "SRAPath") or ""
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
        login_plan = self._build_login_plan(user_cfg=user_cfg, sra_path=sra_path)

        full_queue = self._build_user_queue(
            user_item=user_item,
            user_cfg=user_cfg,
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

        failed_items: list[HSRRunItem] = []
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
            # 后续周常/月常失败不影响日常已完成的事实。
            _daily_items = [
                i for i in current_items
                if i.phase == "daily" and i.module_key != "StartGame"
            ]
            _daily_failed = [
                i for i in failed_items
                if i.phase == "daily" and i.module_key != "StartGame"
            ]
            if _daily_items and len(_daily_failed) < len(_daily_items):
                self._queue_daily_proxy_completion(uid, user_name)
            self._finish_current_user_log(status)
            if not failed_items:
                return

            if attempt < retry_limit:
                self._append_log(
                    f"用户「{user_name}」第 {attempt}/{retry_limit} 次尝试后，"
                    f"仍有 {len(failed_items)} 个失败任务，将重新启动游戏后补跑"
                )
                self._finish_current_user_log(
                    "HSR 用户任务本轮失败，等待补跑",
                    user_status="运行",
                )
                current_items = self._build_retry_queue_items(
                    failed_items,
                    user_item=user_item,
                    user_cfg=user_cfg,
                    user_name=user_name,
                    uid=uid,
                    login_plan=login_plan,
                    script_id=script_id,
                    temp_files=self.temp_files,
                )
            else:
                self._finish_current_user_log(
                    "HSR 用户任务重试失败",
                    user_status="异常",
                )
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
        logger.exception(f"HSR 用户「{self.cur_user_item.name}」任务出现异常：{e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"HSR 用户「{self.cur_user_item.name}」任务出现异常：{e}"},
        )
