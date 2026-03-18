#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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
import json
import re
import shutil
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path

from app.core import Config
from app.models.ConfigBase import MultipleConfig
from app.models.config import MaaEndConfig, MaaEndUserConfig
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase
from app.services import Notify, System
from app.utils import LogMonitor, ProcessManager, get_logger
from app.utils.constants import UTC4

from .runtime_bridge import build_runtime_config
from .paths import (
    LOCAL_CONFIG_NAME,
    managed_default_config_path,
    managed_user_config_path,
)
from .tools.login import login as maaend_login
from .tools import push_notification


logger = get_logger("MaaEnd 自动代理")
TASK_ID_RE = re.compile(
    r'"?task_id"?\s*[:=]\s*"?([^\s,\]\}\""]+)"?', re.IGNORECASE
)
TASK_IDS_RE = re.compile(r"task_ids?\s*[:=]\s*\[([^\]]*)\]", re.IGNORECASE)
INSTANCE_ID_RE = re.compile(r"instance_id\s*[:=]\s*([^\s,\]]+)", re.IGNORECASE)
STOP_GRACE_SECONDS = 2.0
GAME_START_WAIT_SECONDS = 90
GAME_START_WAIT_INTERVAL = 1.0
WINDOW_READY_WAIT_SECONDS = 45
WINDOW_READY_WAIT_INTERVAL = 0.5


class AutoProxyTask(TaskExecuteBase):
    """MaaEnd 自动代理模式"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: MaaEndConfig,
        user_config: MultipleConfig[MaaEndUserConfig],
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config

        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config = self.user_config[self.cur_user_uid]

        self.check_result = "-"
        self.run_success = False
        self.last_status = "-"
        self.instance_id: str | None = None
        self.session_task_ids: set[str] = set()
        self.task_results: dict[str, str] = {}
        self.tauri_tasks_seeded = False
        self.instance_stopped = False
        self.session_started_at: datetime | None = None
        self.session_first_task_id: str | None = None
        self.session_id: str | None = None
        self.session_closed = False
        self.session_settle_task: asyncio.Task | None = None
        self.display_log_lines: deque[str] = deque(maxlen=400)
        self.tauri_log_cursor = 0
        self.maa_log_cursor = 0
        self.web_log_cursor = 0
        self.visit_friends_protection_enabled = False
        self.visit_friends_timeout_sec = 180
        self.runtime_has_visit_friends = False

    async def check(self) -> str:
        if self.script_config.get(
            "Run", "ProxyTimesLimit"
        ) != 0 and self.cur_user_config.get(
            "Data", "RunTimes"
        ) >= self.script_config.get(
            "Run", "ProxyTimesLimit"
        ):
            self.cur_user_item.status = "跳过"
            return "今日代理次数已达上限, 跳过该用户"

        if self.script_config.get("Run", "RunTimesLimit") <= 0:
            self.cur_user_item.status = "异常"
            return "RunTimesLimit 必须大于 0"

        if not bool(self.script_config.get("MaaEnd", "ConfigLocked")):
            self.cur_user_item.status = "异常"
            return "MaaEnd 配置未锁定，请先执行 ScriptConfig 完成配置并保存"

        user_config_cache_path = managed_user_config_path(
            self.script_info.script_id, self.cur_user_item.user_id
        )
        if (
            self.cur_user_config.get("Info", "Mode") == "详细"
            and not user_config_cache_path.exists()
        ):
            self.cur_user_item.status = "异常"
            return "未找到用户专属 MaaEnd 配置，请先在用户配置页完成「MaaEnd 配置」步骤"

        return "Pass"

    async def prepare(self):
        self.maaend_root_path = Path(self.script_config.get("Info", "Path"))
        self.maaend_exe_path = self.maaend_root_path / "MaaEnd.exe"
        self.game_exe_path = Path(str(self.script_config.get("Run", "GamePath")).strip())
        self.maaend_config_path = self.maaend_root_path / "config" / LOCAL_CONFIG_NAME
        self.tauri_log_path = self.maaend_root_path / "debug" / "mxu-tauri.log"
        self.maa_log_path = self.maaend_root_path / "debug" / "maa.log"
        self.web_log_path = (
            self.maaend_root_path
            / "debug"
            / f"mxu-web-{datetime.now().strftime('%Y-%m-%d')}.log"
        )
        self.runtime_source_config_path = (
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_item.user_id}/Runtime/AUTO-MAS.source.json"
        )
        self.user_config_cache_path = managed_user_config_path(
            self.script_info.script_id, self.cur_user_item.user_id
        )
        self.default_config_cache_path = managed_default_config_path(
            self.script_info.script_id
        )
        self.runtime_source_config_path.parent.mkdir(parents=True, exist_ok=True)
        mode = str(self.cur_user_config.get("Info", "Mode") or "简洁").strip()
        if mode == "详细":
            if self.user_config_cache_path.exists():
                source_path = self.user_config_cache_path
            elif self.default_config_cache_path.exists():
                source_path = self.default_config_cache_path
            else:
                raise FileNotFoundError(
                    f"MaaEnd managed config not found: {self.user_config_cache_path} "
                    f"(fallback {self.default_config_cache_path})"
                )
        else:
            if self.default_config_cache_path.exists():
                source_path = self.default_config_cache_path
            elif self.user_config_cache_path.exists():
                source_path = self.user_config_cache_path
            else:
                raise FileNotFoundError(
                    f"MaaEnd managed config not found: {self.default_config_cache_path} "
                    f"(fallback {self.user_config_cache_path})"
                )
        shutil.copy(source_path, self.runtime_source_config_path)

        self.timeout_minutes = self.script_config.get("Run", "Timeout")
        self.wait_event = asyncio.Event()
        self.maaend_process_manager = ProcessManager()
        self.game_process_manager = ProcessManager()
        self.tauri_log_monitor = LogMonitor(
            (1, 21),
            "%Y-%m-%d][%H:%M:%S",
            self.check_tauri_log,
        )
        self.maa_log_monitor = LogMonitor(
            (1, 20),
            "%Y-%m-%d %H:%M:%S",
            self.check_maa_log,
        )
        self.web_log_monitor = LogMonitor(
            (0, 19),
            "%Y-%m-%d %H:%M:%S",
            self.check_web_log,
        )
        self.visit_friends_protection_enabled = (
            str(self.cur_user_config.get("Task", "VisitFriendsStallProtection")).strip()
            == "Enabled"
        )
        timeout_sec = self.cur_user_config.get("Task", "VisitFriendsTimeoutSec")
        try:
            timeout_sec = int(timeout_sec)
        except Exception:
            timeout_sec = 180
        self.visit_friends_timeout_sec = max(30, timeout_sec)

    def _detect_visit_friends_enabled_in_runtime(self) -> bool:
        try:
            config_data = json.loads(self.maaend_config_path.read_text(encoding="utf-8"))
        except Exception:
            return False

        instances = config_data.get("instances")
        if not isinstance(instances, list) or not instances:
            return False

        active_id = config_data.get("lastActiveInstanceId")
        selected_instance = next(
            (
                item
                for item in instances
                if isinstance(item, dict) and item.get("id") == active_id
            ),
            None,
        )
        if selected_instance is None:
            selected_instance = next(
                (item for item in instances if isinstance(item, dict)),
                None,
            )
        if not isinstance(selected_instance, dict):
            return False

        tasks = selected_instance.get("tasks")
        if not isinstance(tasks, list):
            return False

        for task in tasks:
            if not isinstance(task, dict):
                continue
            if str(task.get("taskName", "")).strip() != "VisitFriends":
                continue
            return bool(task.get("enabled", True))
        return False

    async def _prepare_runtime_config(self) -> None:
        runtime_path = build_runtime_config(
            self.script_info.script_id,
            self.cur_user_item.user_id,
            self.script_config,
            self.cur_user_config,
            source_path=self.runtime_source_config_path,
        )
        self.maaend_config_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(runtime_path, self.maaend_config_path)

    def _push_debug_line(self, message: str) -> None:
        line = f"[AUTO-MAS] {message}"
        self.display_log_lines.append(line)
        joined = "\n".join(self.display_log_lines)
        self.script_info.log = joined
        self.cur_user_log.content = list(self.display_log_lines)
        logger.info(line)

    def _set_stage_message(self, title: str, detail: str | None = None) -> None:
        if detail:
            self._push_debug_line(f"{title}: {detail}")
            return
        self._push_debug_line(title)

    async def _ensure_game_running(self) -> bool:
        game_running = len(await System.search_pids(self.game_exe_path)) > 0
        if game_running:
            self._set_stage_message("检测到 Endfield 已在运行", str(self.game_exe_path))
            return True

        self._set_stage_message("正在启动 Endfield", str(self.game_exe_path))
        await self.game_process_manager.open_process(self.game_exe_path)
        for elapsed in range(1, GAME_START_WAIT_SECONDS + 1, int(GAME_START_WAIT_INTERVAL)):
            game_running = len(await System.search_pids(self.game_exe_path)) > 0
            if game_running:
                self._set_stage_message(
                    "Endfield 进程已启动",
                    f"{self.game_exe_path}，耗时约 {elapsed} 秒",
                )
                return True
            await asyncio.sleep(GAME_START_WAIT_INTERVAL)

        self._set_stage_message(
            "启动 Endfield 失败",
            f"{GAME_START_WAIT_SECONDS} 秒内未检测到进程: {self.game_exe_path}",
        )
        return False

    @staticmethod
    def _find_window_handle(window_keyword: str) -> int | None:
        try:
            import win32gui  # type: ignore
        except Exception:
            return None

        hwnd = win32gui.FindWindow(None, window_keyword)
        if hwnd:
            return hwnd

        matched: list[int] = []

        def _enum_cb(handle: int, _param):
            if not win32gui.IsWindowVisible(handle):
                return
            title = (win32gui.GetWindowText(handle) or "").strip()
            if window_keyword.lower() in title.lower():
                matched.append(handle)

        win32gui.EnumWindows(_enum_cb, None)
        return matched[0] if matched else None

    async def _wait_and_focus_window(self, window_keyword: str) -> bool:
        try:
            import win32gui  # type: ignore
        except Exception:
            return False

        for _ in range(
            1, int(WINDOW_READY_WAIT_SECONDS / WINDOW_READY_WAIT_INTERVAL) + 1
        ):
            hwnd = self._find_window_handle(window_keyword)
            if hwnd:
                try:
                    # 9 = SW_RESTORE
                    win32gui.ShowWindow(hwnd, 9)
                    win32gui.SetForegroundWindow(hwnd)
                except Exception:
                    pass
                return True
            await asyncio.sleep(WINDOW_READY_WAIT_INTERVAL)
        return False

    def _mark_account_switch_placeholder(self, run_idx: int) -> None:
        message = "切号功能暂为占位实现，当前运行将跳过实际切换账号"
        logger.warning(f"用户 {self.cur_user_item.name} {message}")
        self._push_debug_line(message)
        self.script_info.log = (
            f"用户 {self.cur_user_item.name} 执行中：轮次 {run_idx + 1}"
            f"{self.script_info.log}"
        )

    async def _prepare_before_maaend(
        self, run_idx: int, skip_account_switch_and_login: bool = False
    ) -> bool:
        controller_type = str(self.script_config.get("Run", "ControllerType")).strip()
        if not controller_type.startswith("Win32"):
            return True

        if_account_switch_enabled = bool(self.script_config.get("Run", "IfAccountSwitch"))

        if skip_account_switch_and_login and if_account_switch_enabled:
            self._set_stage_message("同账号重试：跳过切号与自动登录，仅重启 MaaEnd")
            return await self._ensure_game_running()

        if if_account_switch_enabled:
            account_switch_method = str(
                self.script_config.get("Run", "AccountSwitchMethod")
            ).strip()
            if account_switch_method == "ExitGame":
                self._set_stage_message("切号模式为 ExitGame，正在重启 Endfield")
                await System.kill_process(self.game_exe_path)
            elif account_switch_method != "NoAction":
                self._mark_account_switch_placeholder(run_idx)

        if not await self._ensure_game_running():
            return False

        self._set_stage_message("等待 Endfield 窗口就绪并置前")
        if not await self._wait_and_focus_window("Endfield"):
            self._set_stage_message("Endfield 窗口未就绪，取消启动 MaaEnd")
            return False

        account = ""
        password = ""
        try:
            account = str(self.cur_user_config.get("Info", "Account") or "").strip()
            password = str(self.cur_user_config.get("Info", "Password") or "").strip()
        except Exception:
            account = ""
            password = ""

        if if_account_switch_enabled and account and password:
            self._set_stage_message("检测到账号密码，尝试自动登录 Endfield")
            if not await maaend_login(account, password):
                self._set_stage_message("自动登录 Endfield 失败")
                return False

        return True

    async def _run_once(
        self,
        run_idx: int,
        skip_account_switch_and_login: bool = False,
        kill_game_on_visitfriends_timeout: bool = False,
    ) -> bool:
        self.script_info.log = f"用户 {self.cur_user_item.name} 执行中：轮次 {run_idx + 1}"

        self.log_start_time = datetime.now()
        self.instance_id = None
        self.session_task_ids.clear()
        self.task_results.clear()
        self.tauri_tasks_seeded = False
        self.instance_stopped = False
        self.session_started_at = self.log_start_time
        self.session_first_task_id = None
        self.session_id = None
        self.session_closed = False
        if self.session_settle_task is not None and not self.session_settle_task.done():
            self.session_settle_task.cancel()
        self.session_settle_task = None
        self.display_log_lines.clear()
        self.tauri_log_cursor = 0
        self.maa_log_cursor = 0
        self.web_log_cursor = 0
        self.cur_user_item.log_record[self.log_start_time] = self.cur_user_log = LogRecord()

        await self._prepare_runtime_config()
        self.runtime_has_visit_friends = self._detect_visit_friends_enabled_in_runtime()

        await self.maaend_process_manager.kill()
        await System.kill_process(self.maaend_exe_path)
        self._set_stage_message(
            "已生成运行时配置", str(self.runtime_source_config_path.parent)
        )
        if not await self._prepare_before_maaend(
            run_idx, skip_account_switch_and_login=skip_account_switch_and_login
        ):
            return False

        self.wait_event.clear()
        self._set_stage_message("正在启动 MaaEnd", str(self.maaend_exe_path))
        await self.maaend_process_manager.open_process(self.maaend_exe_path)
        await asyncio.sleep(1)

        await self.tauri_log_monitor.start_monitor_file(
            self.tauri_log_path, self.log_start_time
        )
        await self.maa_log_monitor.start_monitor_file(self.maa_log_path, self.log_start_time)
        await self.web_log_monitor.start_monitor_file(self.web_log_path, self.log_start_time)
        total_timeout_sec = int(self.timeout_minutes * 60) if self.timeout_minutes > 0 else 0
        started_at = datetime.now()
        while not self.wait_event.is_set():
            elapsed_sec = (datetime.now() - started_at).total_seconds()

            if total_timeout_sec > 0 and elapsed_sec >= total_timeout_sec:
                self.cur_user_log.status = "Timeout"
                self.session_closed = True
                self.wait_event.set()
                break

            if (
                self.visit_friends_protection_enabled
                and self.runtime_has_visit_friends
                and elapsed_sec >= self.visit_friends_timeout_sec
            ):
                self.cur_user_log.status = "VisitFriendsTimeout"
                self.session_closed = True
                await self.cur_user_config.set(
                    "Data",
                    "VisitFriendsStealDisabledDate",
                    datetime.now(tz=UTC4).strftime("%Y-%m-%d"),
                )
                self.wait_event.set()
                self._set_stage_message(
                    "检测到拜访好友疑似卡死",
                    f"超时 {self.visit_friends_timeout_sec} 秒，今日禁用偷菜并重试",
                )
                break

            if not await self.maaend_process_manager.is_running():
                self.cur_user_log.status = "InstanceStoppedOrFailed"
                self.session_closed = True
                self.wait_event.set()
                self._set_stage_message("检测到 MaaEnd 主进程退出", "任务在完成前终止")
                break

            await asyncio.sleep(1.0)
        await self._stop_monitors()
        if self.session_settle_task is not None and not self.session_settle_task.done():
            self.session_settle_task.cancel()
        self.session_settle_task = None

        if self.cur_user_log.status == "Success!":
            return True

        await self._terminate_runtime()
        if (
            self.cur_user_log.status == "VisitFriendsTimeout"
            and kill_game_on_visitfriends_timeout
        ):
            self._set_stage_message("拜访好友超时后重置 Endfield 进程")
            await System.kill_process(self.game_exe_path)
        return False

    @staticmethod
    def _extract_task_id(log_line: str) -> str | None:
        match = TASK_ID_RE.search(log_line)
        if match is None:
            return None
        task_id = match.group(1).strip()
        return task_id or None

    def _append_incremental_log(
        self, log_content: list[str], cursor_attr: str, source: str | None = None
    ) -> list[str]:
        cursor = getattr(self, cursor_attr, 0)
        if len(log_content) < cursor:
            cursor = 0
        if len(log_content) == cursor:
            return []

        new_lines = log_content[cursor:]

        if source is not None:
            for line in new_lines:
                text = line.rstrip("\r\n")
                if not text:
                    continue
                self.display_log_lines.append(f"[{source}] {text}")

            joined = "\n".join(self.display_log_lines)
            self.script_info.log = joined
            self.cur_user_log.content = list(self.display_log_lines)

        setattr(self, cursor_attr, len(log_content))
        return new_lines

    def _refresh_session_id(self) -> None:
        if self.session_started_at is None:
            self.session_started_at = datetime.now()
        if self.session_id is not None:
            return
        start_text = self.session_started_at.strftime("%Y%m%d%H%M%S")
        instance_text = self.instance_id or "unknown"
        first_task = self.session_first_task_id or "none"
        self.session_id = f"{start_text}-{instance_text}-{first_task}"

    def _track_task(self, task_id: str | None, from_tauri: bool = False) -> None:
        if not task_id:
            return
        if from_tauri:
            self.tauri_tasks_seeded = True
        self.session_task_ids.add(task_id)
        if self.session_first_task_id is None:
            self.session_first_task_id = task_id
        self._refresh_session_id()

    def _all_tasks_terminal(self) -> bool:
        if not self.tauri_tasks_seeded:
            return False
        if not self.session_task_ids:
            return False
        return all(
            self.task_results.get(task_id) in {"Succeeded", "Failed"}
            for task_id in self.session_task_ids
        )

    def _all_tasks_succeeded(self) -> bool:
        if not self.session_task_ids:
            return False
        return all(
            self.task_results.get(task_id) == "Succeeded"
            for task_id in self.session_task_ids
        )

    def _schedule_settlement(self, reason: str, delay_seconds: float) -> None:
        if self.session_closed:
            return
        if self.session_settle_task is not None and not self.session_settle_task.done():
            self.session_settle_task.cancel()
        self.session_settle_task = asyncio.create_task(
            self._settle_after_delay(reason, delay_seconds)
        )

    async def _settle_after_delay(self, reason: str, delay_seconds: float) -> None:
        try:
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)
            await self._finalize_session(reason)
        except asyncio.CancelledError:
            return

    async def _finalize_session(self, reason: str) -> None:
        if self.session_closed:
            return
        self.session_closed = True
        self._refresh_session_id()

        if self._all_tasks_succeeded():
            self.cur_user_log.status = "Success!"
        else:
            self.cur_user_log.status = "InstanceStoppedOrFailed"

        logger.info(
            f"MaaEnd 会话结算: session_id={self.session_id}, reason={reason}, status={self.cur_user_log.status}"
        )
        self.wait_event.set()

    async def main_task(self):
        # 初始化每日代理状态
        curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        last_run = str(self.cur_user_config.get("Data", "LastRun") or "").strip()
        if not last_run.startswith(curdate):
            await self.cur_user_config.set("Data", "RunTimes", 0)

        self.check_result = await self.check()
        if self.check_result != "Pass":
            if self.cur_user_item.status == "异常":
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={
                        "Error": f"用户 {self.cur_user_item.name} 检查未通过: {self.check_result}"
                    },
                )
            return

        await self.prepare()
        self.user_start_time = datetime.now()
        self.cur_user_item.status = "运行"

        attempts = self.script_config.get("Run", "RunTimesLimit")
        if_account_switch_enabled = bool(self.script_config.get("Run", "IfAccountSwitch"))
        self.run_success = False
        self.last_status = "Crash"
        skip_account_switch_and_login = False

        for run_idx in range(attempts):
            is_last_attempt = run_idx + 1 >= attempts
            self.run_success = await self._run_once(
                run_idx,
                skip_account_switch_and_login=skip_account_switch_and_login,
                kill_game_on_visitfriends_timeout=is_last_attempt,
            )
            skip_account_switch_and_login = False

            if self.run_success:
                self.last_status = "Success"
                break

            if self.cur_user_log.status == "Timeout":
                self.last_status = "Timeout"
            elif self.cur_user_log.status == "VisitFriendsTimeout":
                self.last_status = "VisitFriendsTimeout"
                if not is_last_attempt and if_account_switch_enabled:
                    skip_account_switch_and_login = True
            elif self.cur_user_log.status.startswith("InstanceStoppedOrFailed"):
                self.last_status = "TaskFailed"
            else:
                self.last_status = "Crash"

        await self.cur_user_config.set(
            "Data", "LastRun", datetime.now(tz=UTC4).strftime("%Y-%m-%d %H:%M:%S")
        )
        if self.run_success:
            await self.cur_user_config.set(
                "Data", "RunTimes", self.cur_user_config.get("Data", "RunTimes") + 1
            )
        await self.cur_user_config.set("Data", "LastStatus", self.last_status)

        if self.run_success:
            self.cur_user_item.status = "完成"
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Info": f"用户 {self.cur_user_item.name} MaaEnd 自动代理完成"},
            )
        else:
            self.cur_user_item.status = "异常"
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={
                    "Error": (
                        f"用户 {self.cur_user_item.name} MaaEnd 自动代理失败: "
                        f"{self.cur_user_log.status}"
                    )
                },
            )

    async def check_tauri_log(self, log_content: list[str], _latest_time: datetime) -> None:
        if self.session_closed:
            return
        new_lines = self._append_incremental_log(
            log_content, "tauri_log_cursor", "mxu-tauri"
        )

        for line in new_lines:
            if "maa_start_tasks" in line:
                instance_match = INSTANCE_ID_RE.search(line)
                if instance_match:
                    start_instance_id = instance_match.group(1).strip().strip("'\"")
                    if (
                        self.instance_id is not None
                        and start_instance_id == self.instance_id
                        and self.session_task_ids
                    ):
                        # 同实例新一轮启动，先结算上一轮
                        self._schedule_settlement("next_round", 0.0)
                    self.instance_id = start_instance_id
                    self._refresh_session_id()

            if "post_task returned task_id" in line:
                task_id = self._extract_task_id(line)
                self._track_task(task_id, from_tauri=True)

            task_ids_match = TASK_IDS_RE.search(line)
            if task_ids_match:
                task_ids = [
                    task_id.strip().strip("'\"")
                    for task_id in task_ids_match.group(1).split(",")
                    if task_id.strip()
                ]
                for task_id in task_ids:
                    self._track_task(task_id, from_tauri=True)

            if "maa_stop_agent called for instance" in line:
                if self.instance_id is None:
                    self.instance_stopped = True
                elif self.instance_id in line:
                    self.instance_stopped = True
                if self.instance_stopped:
                    self._schedule_settlement("stop_agent", STOP_GRACE_SECONDS)

    def _parse_maa_lines(self, lines: list[str]) -> None:
        if self.session_closed:
            return
        for line in lines:
            if "msg=Tasker.Task.Succeeded" in line:
                task_id = self._extract_task_id(line)
                if task_id is not None:
                    self._track_task(task_id)
                    self.task_results[task_id] = "Succeeded"
                continue

            if "msg=Tasker.Task.Failed" in line:
                task_id = self._extract_task_id(line)
                if task_id is not None:
                    self._track_task(task_id)
                    self.task_results[task_id] = "Failed"
                continue
            if "task end:" in line:
                task_id = self._extract_task_id(line)
                if task_id is None:
                    continue
                self._track_task(task_id)
                if "ret=true" in line:
                    self.task_results[task_id] = "Succeeded"
                elif "ret=false" in line:
                    self.task_results[task_id] = "Failed"

        if self._all_tasks_terminal():
            self._schedule_settlement("all_terminal", 0.0)

    async def check_maa_log(self, log_content: list[str], _latest_time: datetime) -> None:
        if self.session_closed:
            return
        new_lines = self._append_incremental_log(log_content, "maa_log_cursor", "maa")
        self._parse_maa_lines(new_lines)

        if not self.wait_event.is_set():
            self.cur_user_log.status = "MaaEnd 运行中"

    async def check_web_log(self, log_content: list[str], _latest_time: datetime) -> None:
        self._append_incremental_log(log_content, "web_log_cursor", "mxu-web")

    async def _close_game_if_needed(self) -> None:
        close_game = bool(self.script_config.get("Run", "CloseGameOnFinish"))
        if not close_game:
            return

        game_path = str(self.script_config.get("Run", "GamePath")).strip()
        if not game_path:
            return

        await System.kill_process(Path(game_path))

    async def _stop_monitors(self) -> None:
        await self.tauri_log_monitor.stop()
        await self.maa_log_monitor.stop()
        await self.web_log_monitor.stop()

    async def _terminate_runtime(self) -> None:
        await self.maaend_process_manager.kill()
        await System.kill_process(self.maaend_exe_path)

    async def final_task(self):
        if self.check_result != "Pass":
            return

        await self._stop_monitors()
        await self._terminate_runtime()
        await self._close_game_if_needed()

        user_logs_list = []
        for t, log_item in self.cur_user_item.log_record.items():
            dt = t.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone(UTC4)
            log_path = (
                Path.cwd()
                / f"history/{dt.strftime('%Y-%m-%d')}/{self.cur_user_item.name}/{dt.strftime('%H-%M-%S')}.log"
            )
            user_logs_list.append(log_path.with_suffix(".json"))

            if log_item.status == "MaaEnd 运行中":
                log_item.status = "任务被用户手动中止"

            if len(log_item.content) == 0:
                log_item.content = ["未捕获到任何日志内容"]
                log_item.status = "未捕获到日志"

            await Config.save_general_log(log_path, log_item.content, log_item.status)

        statistics = await Config.merge_statistic_info(user_logs_list)
        statistics["user_info"] = self.cur_user_item.name
        statistics["start_time"] = self.user_start_time.strftime("%Y-%m-%d %H:%M:%S")
        statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        statistics["user_result"] = (
            "代理任务全部完成" if self.run_success else self.cur_user_log.status
        )
        success_symbol = "√" if self.run_success else "X"
        try:
            await push_notification(
                "统计信息",
                f"{datetime.now().strftime('%m-%d')} |{success_symbol}|  {self.cur_user_item.name} 的自动代理统计报告",
                statistics,
                self.cur_user_config,
            )
        except Exception as e:
            logger.exception(f"推送通知时出现异常: {e}")
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": f"推送通知时出现异常: {e}"},
            )

        if self.run_success:
            await Notify.push_plyer(
                "成功完成一个自动代理任务！",
                f"已完成用户 {self.cur_user_item.name} 的自动代理任务",
                f"已完成 {self.cur_user_item.name} 的自动代理任务",
                3,
            )
        else:
            self.cur_user_item.status = "异常"

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        await self.cur_user_config.set(
            "Data", "LastRun", datetime.now(tz=UTC4).strftime("%Y-%m-%d %H:%M:%S")
        )
        await self.cur_user_config.set("Data", "LastStatus", "Crash")
        logger.exception(f"MaaEnd 自动代理任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"MaaEnd 自动代理任务出现异常: {e}"},
        )


