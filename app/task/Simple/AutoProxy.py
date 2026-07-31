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
import shlex
import uuid
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
    ProcessInfo,
    ProcessManager,
    get_logger,
    is_process_running,
)
from app.utils.ProcessManager import match_process
from app.utils.constants import UTC4


logger = get_logger("简易脚本自动代理")


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
        self.user_start_time = datetime.now()
        self.run_start_time = datetime.now()
        self.script_path = Path(self.script_config.get("Script", "ScriptPath"))
        self.script_arguments = shlex.split(
            self.script_config.get("Script", "Arguments")
        )
        self.target_process_info = self._build_target_process_info()
        self.ignored_target_pids: set[int] = set()
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
            self.cur_user_item.log_record[self.run_start_time] = self.cur_user_log = (
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
                await self._record_run_error("启动或监控进程失败", e)
            finally:
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
        self.script_info.log = "正在启动简易脚本"
        logger.info(f"运行脚本任务: {self.script_path}, 参数: {self.script_arguments}")
        await self.process_manager.open_process(
            self.script_path,
            *self.script_arguments,
            target_process=self.target_process_info,
            ignored_target_pids=self.ignored_target_pids,
        )

    async def _wait_for_run_result(self) -> None:
        """等待进程退出，并应用单次总时长限制"""

        run_time_limit = self.script_config.get("Run", "RunTimeLimit")
        timeout = run_time_limit * 60 if run_time_limit > 0 else None
        elapsed = (datetime.now() - self.run_start_time).total_seconds()
        remaining_timeout = max(0, timeout - elapsed) if timeout is not None else None

        try:
            if remaining_timeout is None:
                return_code = await self.process_manager.wait()
            else:
                return_code = await asyncio.wait_for(
                    self.process_manager.wait(),
                    timeout=remaining_timeout,
                )
        except asyncio.TimeoutError:
            self.cur_user_log.status = "脚本进程超时"
            self.cur_user_log.content = ["脚本进程运行超时"]
            self.script_info.log = self.cur_user_log.content[0]
            return

        if return_code == 0:
            result = "脚本进程正常退出，退出码: 0"
            self.cur_user_log.status = "Success!"
        elif return_code is None:
            result = "目标进程已退出，未获取到退出码"
            self.cur_user_log.status = "Success!"
        else:
            result = f"脚本进程异常退出，退出码: {return_code}"
            self.cur_user_log.status = f"脚本进程异常退出: {return_code}"

        self.cur_user_log.content = [result]
        self.script_info.log = result
        logger.info(f"简易脚本任务结果: {result}")

    async def _record_run_error(
        self, error_message: str, error: Exception | None = None
    ) -> None:
        """记录启动或进程监控阶段错误"""

        if error is None:
            logger.error(f"用户 {self.cur_user_uid} - {error_message}")
            message = error_message
        else:
            logger.exception(f"用户 {self.cur_user_uid} - {error_message}: {error}")
            message = f"{error_message}: {error}"

        self.cur_user_log.content = [message]
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
        """保存运行结果、统计与用户执行状态"""

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

            if not log_item.content:
                log_item.content = ["未记录到进程结果"]

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
            await self._cleanup_managed_processes()
        except Exception as cleanup_error:
            logger.exception(f"清理简易脚本进程失败: {cleanup_error}")

        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"简易脚本自动代理任务出现异常: {e}"},
        )
