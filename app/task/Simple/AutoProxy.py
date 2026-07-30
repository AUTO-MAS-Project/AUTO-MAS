#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


import asyncio
import re
import shlex
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path

import psutil

from app.core import Config
from app.models.ConfigBase import MultipleConfig
from app.models.config import SimpleConfig, SimpleUserConfig
from app.models.emulator import DeviceBase
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase
from app.services import Notify, System
from app.task.general.tools import execute_script_task, push_notification
from app.utils import (
    LogMonitor,
    ProcessInfo,
    ProcessManager,
    get_logger,
    is_process_running,
    strptime,
)
from app.utils.ProcessManager import match_process
from app.utils.constants import UTC4


logger = get_logger("简易脚本自动代理")

_PREFIX_SENTINEL = "******"
_STRPTIME_DIRECTIVES: dict[str, str] = {
    "%Y": r"\d{4}",
    "%y": r"\d{2}",
    "%m": r"\d{1,2}",
    "%d": r"\d{1,2}",
    "%H": r"\d{1,2}",
    "%I": r"\d{1,2}",
    "%M": r"\d{1,2}",
    "%S": r"\d{1,2}",
    "%f": r"\d+",
    "%j": r"\d{1,3}",
    "%U": r"\d{1,2}",
    "%W": r"\d{1,2}",
    "%w": r"\d",
    "%A": r"\w+",
    "%a": r"\w+",
    "%B": r"\w+",
    "%b": r"\w+",
    "%p": r"[APap][Mm]",
    "%%": r"%",
}


def _format_to_prefix_regex(fmt: str) -> re.Pattern[str]:
    """将 strptime 格式转换为文件名前缀正则"""

    parts: list[str] = []
    index = 0
    while index < len(fmt):
        if fmt[index] == "%" and index + 1 < len(fmt):
            directive = fmt[index : index + 2]
            if directive in _STRPTIME_DIRECTIVES:
                parts.append(_STRPTIME_DIRECTIVES[directive])
                index += 2
                continue
        parts.append(re.escape(fmt[index]))
        index += 1
    return re.compile("^" + "".join(parts))


def _matching_process_ids(target: ProcessInfo) -> set[int]:
    """返回当前已匹配目标条件的进程 ID"""

    process_ids: set[int] = set()
    for process in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
        if match_process(process, target):
            process_ids.add(process.pid)
    return process_ids


class SimpleAutoProxyTask(TaskExecuteBase):
    """简易脚本自动代理模式"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: SimpleConfig,
        user_config: MultipleConfig[SimpleUserConfig],
        game_manager: ProcessManager | DeviceBase | None,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info: ScriptItem = script_info
        self.script_config: SimpleConfig = script_config
        self.user_config: MultipleConfig[SimpleUserConfig] = user_config
        self.game_manager: ProcessManager | DeviceBase | None = game_manager
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.cur_user_uid: uuid.UUID = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config: SimpleUserConfig = self.user_config[self.cur_user_uid]

        self.process_manager = ProcessManager()
        self.wait_event = asyncio.Event()
        self.user_start_time = datetime.now()
        self.run_start_time = datetime.now()
        self.log_start_time = datetime.now()
        self.script_path = Path(self.script_config.get("Script", "ScriptPath"))
        self.script_arguments = shlex.split(
            self.script_config.get("Script", "Arguments")
        )
        self.target_process_info = self._build_target_process_info()
        self.ignored_target_pids: set[int] = set()
        self.log_path = Path(self.script_config.get("Script", "LogPath"))
        self.log_enabled = bool(self.script_config.get("Script", "LogPath"))
        self.log_format = self.script_config.get("Script", "LogPathFormat")
        self.log_use_prefix = bool(self.log_format) and self.log_format.endswith(
            _PREFIX_SENTINEL
        )
        self.success_logs = [
            item.strip()
            for item in self.script_config.get("Script", "SuccessLog").split("|")
            if item.strip()
        ]
        self.error_logs = [
            item.strip()
            for item in self.script_config.get("Script", "ErrorLog").split("|")
            if item.strip()
        ]
        self.log_monitor = LogMonitor(
            (
                self.script_config.get("Script", "LogTimeStart") - 1,
                self.script_config.get("Script", "LogTimeEnd"),
            ),
            self.script_config.get("Script", "LogTimeFormat"),
            self.check_log,
        )
        self.cur_user_log = LogRecord()
        self.run_book = False
        self.check_result = "-"

    def _build_target_process_info(self) -> ProcessInfo | None:
        """构建可选的目标进程匹配条件"""

        if not self.script_config.get("Script", "IfTrackProcess"):
            return None
        return ProcessInfo(
            name=self.script_config.get("Script", "TrackProcessName") or None,
            exe=self.script_config.get("Script", "TrackProcessExe") or None,
            cmdline=shlex.split(
                self.script_config.get("Script", "TrackProcessCmdline"),
                posix=False,
            )
            or None,
        )

    async def check(self) -> str:
        """检查用户限制及脚本进程占用"""

        if self.script_config.get(
            "Run", "ProxyTimesLimit"
        ) != 0 and self.cur_user_config.get(
            "Data", "ProxyTimes"
        ) >= self.script_config.get("Run", "ProxyTimesLimit"):
            self.cur_user_item.status = "跳过"
            return "今日代理次数已达上限, 跳过该用户"

        script_target = ProcessInfo(exe=str(self.script_path.resolve()))
        if _matching_process_ids(script_target):
            self.cur_user_item.status = "异常"
            return "脚本程序已在运行，请先退出后重试"

        return "Pass"

    async def main_task(self) -> None:
        """运行当前用户的简易脚本任务"""

        current_date = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        if self.cur_user_config.get("Data", "LastProxyDate") != current_date:
            await self.cur_user_config.set("Data", "LastProxyDate", current_date)
            await self.cur_user_config.set("Data", "ProxyTimes", 0)

        self.check_result = await self.check()
        if self.check_result != "Pass":
            if self.cur_user_item.status == "异常":
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={
                        "Error": (
                            f"用户 {self.cur_user_item.name} 检查未通过: "
                            f"{self.check_result}"
                        )
                    },
                )
            return

        self.cur_user_item.status = "运行"
        for attempt in range(self.script_config.get("Run", "RunTimesLimit")):
            if self.run_book:
                break

            logger.info(
                f"用户 {self.cur_user_item.name} - 尝试次数: "
                f"{attempt + 1}/{self.script_config.get('Run', 'RunTimesLimit')}"
            )
            self.run_start_time = datetime.now()
            self.log_start_time = self.run_start_time
            self.cur_user_item.log_record[self.log_start_time] = self.cur_user_log = (
                LogRecord()
            )

            if self.cur_user_config.get("Info", "IfScriptBeforeTask"):
                await execute_script_task(
                    Path(self.cur_user_config.get("Info", "ScriptBeforeTask")),
                    "脚本前任务",
                )

            try:
                await self._start_game()
                await self._start_script()
                await self._wait_for_run_result()
            except Exception as e:
                await self._record_run_error("启动或监控脚本失败", e)
            finally:
                await self.log_monitor.stop()
                await self._cleanup_managed_processes()

            if self.cur_user_log.status == "Success!":
                self.run_book = True
                logger.success(f"用户 {self.cur_user_uid} - 简易脚本任务完成")
            else:
                logger.error(
                    f"用户 {self.cur_user_uid} - 任务异常: {self.cur_user_log.status}"
                )
                await Notify.push_plyer(
                    "用户自动代理出现异常！",
                    f"用户 {self.cur_user_item.name} 的自动代理出现一次异常",
                    f"{self.cur_user_item.name}的自动代理出现异常",
                    3,
                )

            if self.cur_user_config.get("Info", "IfScriptAfterTask"):
                await execute_script_task(
                    Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
                    "脚本后任务",
                )

            if not self.run_book:
                await asyncio.sleep(3)

    async def _start_game(self) -> None:
        """按 General 规则启动游戏、客户端或模拟器"""

        if self.game_manager is None:
            return

        self.script_info.log = "正在启动游戏 / 模拟器"
        if isinstance(self.game_manager, ProcessManager):
            game_type = self.script_config.get("Game", "Type")
            if game_type == "URL":
                process_name = self.script_config.get("Game", "ProcessName")
                if process_name and is_process_running(process_name):
                    logger.info(f"检测到游戏进程已在运行，跳过重复启动: {process_name}")
                    await asyncio.sleep(2)
                    return
                await self.game_manager.open_protocol(
                    self.script_config.get("Game", "URL"),
                    ProcessInfo(name=process_name),
                )
                await asyncio.sleep(2)
                return

            game_path = Path(self.script_config.get("Game", "Path"))
            if game_path.name and is_process_running(game_path.name):
                logger.info(f"检测到游戏进程已在运行，跳过重复启动: {game_path.name}")
                await asyncio.sleep(self.script_config.get("Game", "WaitTime"))
                return

            await self.game_manager.open_process(
                game_path,
                *shlex.split(self.script_config.get("Game", "Arguments")),
            )
            await asyncio.sleep(self.script_config.get("Game", "WaitTime"))
            return

        await self.game_manager.open(self.script_config.get("Game", "EmulatorIndex"))

    async def _start_script(self) -> None:
        """启动脚本并只追踪本次新出现的目标进程"""

        self.ignored_target_pids = (
            _matching_process_ids(self.target_process_info)
            if self.target_process_info is not None
            else set()
        )
        self.wait_event.clear()
        self.script_info.log = "正在启动简易脚本"
        logger.info(f"运行脚本任务: {self.script_path}, 参数: {self.script_arguments}")
        await self.process_manager.open_process(
            self.script_path,
            *self.script_arguments,
            target_process=self.target_process_info,
            ignored_target_pids=self.ignored_target_pids,
        )

        if self.log_enabled:
            target_log_path = await self._wait_for_log_file()
            await self.log_monitor.start_monitor_file(
                target_log_path,
                self.log_start_time,
            )

    async def _wait_for_log_file(self) -> Path:
        """按 General 文件名规则等待本次运行的日志文件"""

        self.script_info.log = "正在等待脚本日志文件生成"
        deadline = asyncio.get_running_loop().time() + 60

        if self.log_use_prefix:
            prefix_format = self.log_format[: -len(_PREFIX_SENTINEL)]
            pattern = _format_to_prefix_regex(prefix_format)
            target_suffix: int | None = None

            while asyncio.get_running_loop().time() < deadline:
                current_suffix = 0
                current_file: Path | None = None
                if self.log_path.parent.exists():
                    for log_file in self.log_path.parent.iterdir():
                        if not log_file.is_file():
                            continue
                        match = pattern.match(log_file.name)
                        if not match:
                            continue
                        try:
                            file_time = strptime(
                                match.group(0), prefix_format, self.log_start_time
                            )
                        except ValueError:
                            continue
                        if file_time.date() != self.log_start_time.date():
                            continue
                        tail = log_file.name[match.end() :]
                        number_match = re.search(r"(\d+)\s*$", tail.rsplit(".", 1)[0])
                        suffix = int(number_match.group(1)) if number_match else 0
                        if suffix > current_suffix:
                            current_suffix = suffix
                            current_file = log_file

                if target_suffix is None:
                    target_suffix = current_suffix + 1
                if current_suffix >= target_suffix and current_file is not None:
                    logger.success(f"成功定位到日志文件: {current_file}")
                    return current_file
                await asyncio.sleep(1)

            raise RuntimeError("未找到日志文件")

        if not self.log_format:
            while asyncio.get_running_loop().time() < deadline:
                if self.log_path.is_file():
                    return self.log_path
                await asyncio.sleep(1)
            raise RuntimeError("未找到日志文件")

        log_format = self.log_format
        with suppress(ValueError):
            datetime.strptime(self.log_path.stem, log_format)
            log_format = f"{log_format}{self.log_path.suffix}"

        while asyncio.get_running_loop().time() < deadline:
            if self.log_path.parent.exists():
                for log_file in self.log_path.parent.iterdir():
                    if not log_file.is_file():
                        continue
                    with suppress(ValueError):
                        if (
                            strptime(log_file.name, log_format, self.log_start_time)
                            >= self.log_start_time
                        ):
                            logger.success(f"成功定位到日志文件: {log_file}")
                            return log_file
            await asyncio.sleep(1)

        raise RuntimeError("未找到日志文件")

    async def _wait_for_run_result(self) -> None:
        """等待日志判定或进程退出，并统一应用总时长限制"""

        process_wait_task = asyncio.create_task(self.process_manager.wait())
        wait_tasks: set[asyncio.Task] = {process_wait_task}
        log_wait_task: asyncio.Task | None = None
        if self.log_enabled:
            log_wait_task = asyncio.create_task(self.wait_event.wait())
            wait_tasks.add(log_wait_task)

        run_time_limit = self.script_config.get("Run", "RunTimeLimit")
        timeout = run_time_limit * 60 if run_time_limit > 0 else None
        elapsed = (datetime.now() - self.run_start_time).total_seconds()
        remaining_timeout = max(0, timeout - elapsed) if timeout is not None else None

        done, pending = await asyncio.wait(
            wait_tasks,
            timeout=remaining_timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

        if not done:
            self.cur_user_log.status = "脚本进程超时"
            return

        if log_wait_task is not None and log_wait_task in done:
            return

        return_code = process_wait_task.result()
        if self.log_enabled:
            await self.check_log(self.log_monitor.log_contents, datetime.now())
            return

        self.cur_user_log.content = []
        self.cur_user_log.status = (
            "Success!"
            if return_code in (0, None)
            else f"脚本进程异常退出: {return_code}"
        )

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """根据日志关键字和进程状态判断任务结果"""

        del latest_time
        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log

        for success_sign in self.success_logs:
            if success_sign in log:
                self.cur_user_log.status = "Success!"
                break
        else:
            for error_sign in self.error_logs:
                if error_sign in log:
                    self.cur_user_log.status = f"异常日志: {error_sign}"
                    break
            else:
                if await self.process_manager.is_running():
                    self.cur_user_log.status = "简易脚本正常运行中"
                elif self.success_logs:
                    self.cur_user_log.status = "脚本在完成任务前退出"
                else:
                    self.cur_user_log.status = "Success!"

        if self.cur_user_log.status != "简易脚本正常运行中":
            logger.info(f"简易脚本任务结果: {self.cur_user_log.status}")
            self.wait_event.set()

    async def _record_run_error(
        self, error_message: str, error: Exception | None = None
    ) -> None:
        """记录启动或监控阶段错误"""

        if error is None:
            logger.error(f"用户 {self.cur_user_uid} - {error_message}")
            message = error_message
        else:
            logger.exception(f"用户 {self.cur_user_uid} - {error_message}: {error}")
            message = f"{error_message}: {error}"

        self.cur_user_log.content = [f"{message}, 无日志记录"]
        self.cur_user_log.status = error_message
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": message},
        )

    async def _cleanup_managed_processes(self) -> None:
        """独立清理脚本与游戏进程"""

        try:
            await self.process_manager.kill()
        except Exception as e:
            logger.exception(f"中止简易脚本进程失败: {e}")

        if self.game_manager is None:
            return

        try:
            if isinstance(self.game_manager, ProcessManager):
                await self.game_manager.kill()
                if self.script_config.get(
                    "Game", "Type"
                ) == "Client" and self.script_config.get("Game", "IfForceClose"):
                    await System.kill_process(
                        Path(self.script_config.get("Game", "Path"))
                    )
            else:
                await self.game_manager.close(
                    self.script_config.get("Game", "EmulatorIndex")
                )
        except Exception as e:
            logger.exception(f"关闭游戏/模拟器失败: {e}")

    async def final_task(self) -> None:
        """保存日志、统计与用户执行状态"""

        await self.log_monitor.stop()
        await self._cleanup_managed_processes()

        if self.check_result != "Pass":
            return

        user_logs_list = []
        for start_time, log_item in self.cur_user_item.log_record.items():
            local_time = start_time.replace(
                tzinfo=datetime.now().astimezone().tzinfo
            ).astimezone(UTC4)
            log_path = (
                Path.cwd()
                / "history"
                / local_time.strftime("%Y-%m-%d")
                / self.cur_user_item.name
                / f"{local_time.strftime('%H-%M-%S')}.log"
            )
            user_logs_list.append(log_path.with_suffix(".json"))

            if log_item.status == "简易脚本正常运行中":
                log_item.status = "任务被用户手动中止"
            if not log_item.content:
                log_item.content = ["未捕获到日志内容"]

            await Config.save_general_log(log_path, log_item.content, log_item.status)

        statistics = await Config.merge_statistic_info(user_logs_list)
        statistics["user_info"] = self.cur_user_item.name
        statistics["start_time"] = self.user_start_time.strftime("%Y-%m-%d %H:%M:%S")
        statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        statistics["user_result"] = (
            "代理任务全部完成" if self.run_book else self.cur_user_item.result
        )

        success_symbol = "√" if self.run_book else "X"
        try:
            await push_notification(
                "统计信息",
                (
                    f"{datetime.now().strftime('%m-%d')} |{success_symbol}| "
                    f"{self.cur_user_item.name} 的自动代理统计报告"
                ),
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

        if self.run_book:
            if (
                self.cur_user_config.get("Data", "ProxyTimes") == 0
                and self.cur_user_config.get("Info", "RemainedDay") != -1
            ):
                await self.cur_user_config.set(
                    "Info",
                    "RemainedDay",
                    self.cur_user_config.get("Info", "RemainedDay") - 1,
                )
            await self.cur_user_config.set(
                "Data",
                "ProxyTimes",
                self.cur_user_config.get("Data", "ProxyTimes") + 1,
            )
            self.cur_user_item.status = "完成"
            await Notify.push_plyer(
                "成功完成一个自动代理任务！",
                f"已完成用户 {self.cur_user_item.name} 的自动代理任务",
                f"已完成 {self.cur_user_item.name} 的自动代理任务",
                3,
            )
        else:
            self.cur_user_item.status = "异常"

    async def on_crash(self, e: Exception) -> None:
        """记录用户任务异常"""

        self.cur_user_item.status = "异常"
        logger.exception(f"简易脚本自动代理任务出现异常: {e}")

        try:
            await self.log_monitor.stop()
        except Exception as stop_error:
            logger.exception(f"停止日志监控失败: {stop_error}")
        try:
            await self._cleanup_managed_processes()
        except Exception as cleanup_error:
            logger.exception(f"清理简易脚本进程失败: {cleanup_error}")

        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"简易脚本自动代理任务出现异常: {e}"},
        )
