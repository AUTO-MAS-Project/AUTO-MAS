#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import uuid
import shlex
import shutil
import asyncio
from pathlib import Path
from datetime import datetime, timedelta

from app.core import Config
from app.models.task import TaskExecuteBase, ScriptItem, LogRecord
from app.models.ConfigBase import MultipleConfig
from app.models.config import GeneralConfig, GeneralUserConfig
from app.models.emulator import DeviceBase
from app.services import Notify, System
from app.utils import get_logger, LogMonitor, ProcessManager, ProcessInfo, strptime
from app.utils.constants import UTC4
from .tools import execute_script_task

logger = get_logger("通用脚本自动代理")


class AutoProxyTask(TaskExecuteBase):
    """自动代理模式"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: GeneralConfig,
        user_config: MultipleConfig[GeneralUserConfig],
        game_manager: ProcessManager | DeviceBase | None,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.game_manager = game_manager
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config = self.user_config[self.cur_user_uid]
        self.check_result = "-"

    async def check(self) -> str:

        if self.script_config.get(
            "Run", "ProxyTimesLimit"
        ) != 0 and self.cur_user_config.get(
            "Data", "ProxyTimes"
        ) >= self.script_config.get(
            "Run", "ProxyTimesLimit"
        ):
            self.cur_user_item.status = "跳过"
            return "今日代理次数已达上限, 跳过该用户"

        if not (
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile"
        ).exists():
            self.cur_user_item.status = "异常"
            return "未找到用户的通用脚本配置文件"
        return "Pass"

    async def prepare(self):

        self.general_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()
        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now()

        self.script_root_path = Path(self.script_config.get("Info", "RootPath"))
        self.script_path = Path(self.script_config.get("Script", "ScriptPath"))

        arguments_list = []
        path_list = []

        for argument in [
            part.strip()
            for part in str(self.script_config.get("Script", "Arguments")).split("|")
            if part.strip()
        ]:
            arg_parts = [
                part.strip() for part in argument.split("%", 1) if part.strip()
            ]

            path_list.append(
                (
                    self.script_path / arg_parts[0]
                    if len(arg_parts) > 1
                    else self.script_path
                ).resolve()
            )
            arguments_list.append(shlex.split(arg_parts[-1]))

        self.script_exe_path = path_list[0] if len(path_list) > 0 else self.script_path
        self.script_arguments = arguments_list[0] if len(arguments_list) > 0 else []
        self.script_set_arguments = arguments_list[1] if len(arguments_list) > 1 else []

        self.script_config_path = Path(self.script_config.get("Script", "ConfigPath"))
        self.script_log_path = (
            Path(self.script_config.get("Script", "LogPath")).with_stem(
                datetime.now().strftime(
                    self.script_config.get("Script", "LogPathFormat")
                )
            )
            if self.script_config.get("Script", "LogPathFormat")
            else Path(self.script_config.get("Script", "LogPath"))
        )
        if not self.script_log_path.exists():
            self.script_log_path.parent.mkdir(parents=True, exist_ok=True)
            self.script_log_path.touch(exist_ok=True)
        self.game_path = Path(self.script_config.get("Game", "Path"))
        self.game_url = self.script_config.get("Game", "URL")
        self.game_process_name = self.script_config.get("Game", "ProcessName")
        self.log_time_range = (
            self.script_config.get("Script", "LogTimeStart") - 1,
            self.script_config.get("Script", "LogTimeEnd"),
        )
        self.success_log = (
            [
                _.strip()
                for _ in self.script_config.get("Script", "SuccessLog").split("|")
            ]
            if self.script_config.get("Script", "SuccessLog")
            else []
        )
        self.error_log = [
            _.strip() for _ in self.script_config.get("Script", "ErrorLog").split("|")
        ]
        self.general_log_monitor = LogMonitor(
            self.log_time_range,
            self.script_config.get("Script", "LogTimeFormat"),
            self.check_log,
        )

        self.run_book = False

    async def main_task(self):
        """自动代理模式主逻辑"""

        # 初始化每日代理状态
        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        if self.cur_user_config.get("Data", "LastProxyDate") != self.curdate:
            await self.cur_user_config.set("Data", "LastProxyDate", self.curdate)
            await self.cur_user_config.set("Data", "ProxyTimes", 0)

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

        logger.info(f"开始代理用户: {self.cur_user_uid}")
        self.cur_user_item.status = "运行"

        for i in range(self.script_config.get("Run", "RunTimesLimit")):
            if self.run_book:
                break
            logger.info(
                f"用户 {self.cur_user_item.name} - 尝试次数: {i + 1}/{self.script_config.get('Run', 'RunTimesLimit')}"
            )
            self.log_start_time = datetime.now()
            self.cur_user_item.log_record[self.log_start_time] = self.cur_user_log = (
                LogRecord()
            )

            # 执行任务前脚本
            if self.cur_user_config.get("Info", "IfScriptBeforeTask"):
                await execute_script_task(
                    Path(self.cur_user_config.get("Info", "ScriptBeforeTask")),
                    "脚本前任务",
                )

            # 启动游戏/模拟器
            if self.game_manager is not None:
                try:
                    if isinstance(self.game_manager, ProcessManager):

                        if self.script_config.get("Game", "Type") == "URL":
                            logger.info(
                                f"启动游戏: {self.game_process_name}, 参数{self.game_url}"
                            )
                            await self.game_manager.open_protocol(
                                self.game_url, ProcessInfo(name=self.game_process_name)
                            )
                        else:
                            logger.info(
                                f"启动游戏: {self.game_path}, 参数: {self.script_config.get('Game','Arguments')}"
                            )
                            await self.game_manager.open_process(
                                self.game_path,
                                *str(self.script_config.get("Game", "Arguments")).split(
                                    " "
                                ),
                            )
                    elif isinstance(self.game_manager, DeviceBase):
                        logger.info(
                            f"启动模拟器: {self.script_config.get('Game', 'EmulatorIndex')}"
                        )
                        await self.game_manager.open(
                            self.script_config.get("Game", "EmulatorIndex"),
                        )
                except Exception as e:
                    logger.exception(
                        f"用户: {self.cur_user_uid} - 游戏/模拟器启动失败: {e}"
                    )
                    await Config.send_websocket_message(
                        id=self.task_info.task_id,
                        type="Info",
                        data={"Error": f"启动游戏/模拟器时出现异常: {e}"},
                    )
                    self.cur_user_log.content = [
                        "游戏/模拟器启动失败, 通用脚本未实际运行, 无日志记录"
                    ]
                    self.cur_user_log.status = "模拟器启动失败"

                    if isinstance(self.game_manager, ProcessManager):
                        await self.game_manager.kill()
                    elif isinstance(self.game_manager, DeviceBase):
                        await self.game_manager.close(
                            self.script_config.get("Game", "EmulatorIndex"),
                        )

                    await Notify.push_plyer(
                        "用户自动代理出现异常！",
                        f"用户 {self.cur_user_item.name} 的自动代理出现一次异常",
                        f"{self.cur_user_item.name}的自动代理出现异常",
                        3,
                    )
                    continue

                self.script_info.log = f"正在等待游戏/模拟器完成启动\n请等待{self.script_config.get('Game', 'WaitTime')}s"
                await asyncio.sleep(self.script_config.get("Game", "WaitTime"))

            await self.set_general()
            logger.info(
                f"运行脚本任务: {self.script_exe_path}, 参数: {self.script_arguments}"
            )

            self.wait_event.clear()
            await self.general_process_manager.open_process(
                self.script_exe_path, *self.script_arguments
            )
            await self.general_log_monitor.start(
                self.script_log_path, self.log_start_time
            )
            await self.wait_event.wait()
            await self.general_log_monitor.stop()

            if self.cur_user_log.status == "Success!":
                self.run_book = True
                logger.info(f"用户: {self.cur_user_uid} - 通用脚本进程完成代理任务")
                self.script_info.log = (
                    "检测到通用脚本进程完成代理任务\n正在等待相关程序结束\n请等待"
                )

                # 中止相关程序
                await self.close_script_process()

                await asyncio.sleep(10)

                # 更新脚本配置文件
                if self.script_config.get("Script", "UpdateConfigMode") in (
                    "Success",
                    "Always",
                ):
                    await self.update_config()

            else:
                logger.error(
                    f"用户: {self.cur_user_uid} - 代理任务异常: {self.cur_user_log.status}"
                )
                self.script_info.log = (
                    f"{self.cur_user_log.status}\n正在中止相关程序\n请等待"
                )

                # 中止相关程序
                await self.close_script_process()

                await Notify.push_plyer(
                    "用户自动代理出现异常！",
                    f"用户 {self.cur_user_item.name} 的自动代理出现一次异常",
                    f"{self.cur_user_item.name}的自动代理出现异常",
                    3,
                )

                await asyncio.sleep(10)
                # 更新脚本配置文件
                if self.script_config.get("Script", "UpdateConfigMode") in (
                    "Failure",
                    "Always",
                ):
                    await self.update_config()

            # 执行任务后脚本
            if self.cur_user_config.get("Info", "IfScriptAfterTask"):
                await execute_script_task(
                    Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
                    "脚本后任务",
                )

    async def update_config(self):

        if self.script_config.get("Script", "ConfigPathMode") == "Folder":
            shutil.copytree(
                self.script_config_path,
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile",
                dirs_exist_ok=True,
            )
        elif self.script_config.get("Script", "ConfigPathMode") == "File":
            shutil.copy(
                self.script_config_path,
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile"
                / self.script_config_path.name,
            )
        logger.success("通用脚本配置文件已更新")

    async def close_script_process(self):
        logger.info(f"中止相关程序: {self.script_exe_path}")
        await self.general_process_manager.kill()
        await System.kill_process(self.script_exe_path)
        if self.game_manager is not None:
            logger.info("中止游戏/模拟器进程")
            if isinstance(self.game_manager, ProcessManager):
                await self.game_manager.kill()
                if self.script_config.get("Game", "IfForceClose"):
                    await System.kill_process(self.game_path)
            elif isinstance(self.game_manager, DeviceBase):
                await self.game_manager.close(
                    self.script_config.get("Game", "EmulatorIndex"),
                )

    async def set_general(self) -> None:
        """配置通用脚本运行参数"""
        logger.info(f"开始配置脚本运行参数: 自动代理")

        # 配置前关闭可能未正常退出的脚本进程
        await System.kill_process(self.script_exe_path)

        # 导入配置文件
        if self.script_config.get("Script", "ConfigPathMode") == "Folder":
            shutil.copytree(
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile",
                self.script_config_path,
                dirs_exist_ok=True,
            )
        elif self.script_config.get("Script", "ConfigPathMode") == "File":
            shutil.copy(
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile"
                / self.script_config_path.name,
                self.script_config_path,
            )

        logger.info(f"脚本运行参数配置完成: 自动代理")

    async def check_log(self, log_content: list[str]) -> None:
        """日志回调"""

        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log

        latest_time = self.log_start_time
        for _ in log_content[::-1]:
            try:
                latest_time = strptime(
                    _[self.log_time_range[0] : self.log_time_range[1]],
                    self.script_config.get("Script", "LogTimeFormat"),
                    self.log_start_time,
                )
                break
            except ValueError:
                pass

        for success_sign in self.success_log:
            if success_sign in log:
                self.cur_user_log.status = "Success!"
                break
        else:
            if datetime.now() - latest_time > timedelta(
                minutes=self.script_config.get("Run", "RunTimeLimit")
            ):
                self.cur_user_log.status = "脚本进程超时"
            else:
                for error_sign in self.error_log:
                    if error_sign in log:
                        self.cur_user_log.status = f"异常日志: {error_sign}"
                        break
                else:
                    if await self.general_process_manager.is_running():
                        self.cur_user_log.status = "通用脚本正常运行中"
                    elif self.success_log:
                        self.cur_user_log.status = "脚本在完成任务前退出"
                    else:
                        self.cur_user_log.status = "Success!"

        logger.debug(f"通用脚本日志分析结果: {self.cur_user_log.status}")
        if self.cur_user_log.status != "通用脚本正常运行中":
            logger.info(f"通用脚本任务结果: {self.cur_user_log.status}, 日志锁已释放")
            self.wait_event.set()

    async def final_task(self):

        if self.check_result != "Pass":
            return

        logger.debug("开始进入结束通用脚本任务进程")

        # 结束各子任务
        await self.general_log_monitor.stop()
        await self.general_process_manager.kill()
        await System.kill_process(self.script_exe_path)
        del self.general_process_manager
        del self.general_log_monitor
        if self.game_manager is not None:
            if isinstance(self.game_manager, ProcessManager):
                await self.game_manager.kill()
            elif isinstance(self.game_manager, DeviceBase):
                await self.game_manager.close(
                    self.script_config.get("Game", "EmulatorIndex"),
                )
            del self.game_manager

        user_logs_list = []
        for t, log_item in self.cur_user_item.log_record.items():

            dt = t.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone(UTC4)
            log_path = (
                Path.cwd()
                / f"history/{dt.strftime('%Y-%m-%d')}/{self.cur_user_item.name}/{dt.strftime('%H-%M-%S')}.log"
            )
            user_logs_list.append(log_path.with_suffix(".json"))

            if len(log_item.content) == 0:
                log_item.content = ["未捕获到任何日志内容"]
                log_item.status = "未捕获到日志"

            await Config.save_general_log(
                log_path,
                log_item.content,
                (
                    log_item.status
                    if log_item.status != "通用脚本正常运行中"
                    else "任务被用户手动中止"
                ),
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
            logger.success(f"用户 {self.cur_user_uid} 的自动代理任务已完成")
            await Notify.push_plyer(
                "成功完成一个自动代理任务！",
                f"已完成用户 {self.cur_user_item.name} 的自动代理任务",
                f"已完成 {self.cur_user_item.name} 的自动代理任务",
                3,
            )
        else:
            logger.error(f"用户 {self.cur_user_uid} 的自动代理任务未完成")
            self.cur_user_item.status = "异常"

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.exception(f"自动代理任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"自动代理任务出现异常: {e}"},
        )
