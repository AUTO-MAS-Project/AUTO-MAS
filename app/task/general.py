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


import os
import sys
import uuid
import shutil
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from jinja2 import Environment, FileSystemLoader
from typing import List, Dict, Optional


from app.core import Config, GeneralConfig, GeneralUserConfig
from app.models.schema import WebSocketMessage
from app.models.ConfigBase import MultipleConfig
from app.services import Notify, System
from app.utils import get_logger, LogMonitor, ProcessManager, strptime


logger = get_logger("通用调度器")


class GeneralManager:
    """通用脚本调度器"""

    def __init__(
        self, mode: str, script_id: uuid.UUID, user_id: Optional[uuid.UUID], ws_id: str
    ):
        super(GeneralManager, self).__init__()

        self.mode = mode
        self.script_id = script_id
        self.user_id = user_id
        self.ws_id = ws_id

        self.game_process_manager = ProcessManager()
        self.general_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()

        self.general_logs = []
        self.log_start_time = datetime.now()
        self.general_result = "Wait"

    async def configure(self):
        """提取配置信息"""

        await Config.ScriptConfig[self.script_id].lock()

        self.script_config = Config.ScriptConfig[self.script_id]
        self.user_config = MultipleConfig([GeneralUserConfig])
        await self.user_config.load(await self.script_config.UserData.toDict())

        self.script_root_path = Path(self.script_config.get("Info", "RootPath"))
        self.script_path = Path(self.script_config.get("Script", "ScriptPath"))

        arguments_list = []
        path_list = []

        for argument in [
            _.strip()
            for _ in str(self.script_config.get("Script", "Arguments")).split("|")
            if _.strip()
        ]:
            arg = [_.strip() for _ in argument.split("%") if _.strip()]
            if len(arg) > 1:
                path_list.append((self.script_path / arg[0]).resolve())
                arguments_list.append(
                    [_.strip() for _ in arg[1].split(" ") if _.strip()]
                )
            elif len(arg) > 0:
                path_list.append(self.script_path)
                arguments_list.append(
                    [_.strip() for _ in arg[0].split(" ") if _.strip()]
                )

        self.script_exe_path = path_list[0] if len(path_list) > 0 else self.script_path
        self.script_arguments = arguments_list[0] if len(arguments_list) > 0 else []
        self.script_set_exe_path = (
            path_list[1] if len(path_list) > 1 else self.script_path
        )
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
            self.check_general_log,
        )

        logger.success(f"{self.script_id}已锁定, 通用配置提取完成")

    def check_config(self) -> str:
        """检查配置是否可用"""

        if not isinstance(Config.ScriptConfig[self.script_id], GeneralConfig):
            return "脚本配置类型错误, 不是通用脚本类型"

        if self.mode == "人工排查":
            return "通用脚本不支持人工排查模式"
        if self.mode == "设置脚本" and self.user_id is None:
            return "设置脚本模式下用户ID不能为空"

        return "Success!"

    async def run(self):
        """主进程, 运行通用脚本代理进程"""

        self.current_date = datetime.now().strftime("%m-%d")
        self.curdate = Config.server_date().strftime("%Y-%m-%d")
        self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        await self.configure()
        self.check_result = self.check_config()
        if self.check_result != "Success!":
            logger.error(f"未通过配置检查: {self.check_result}")
            await Config.send_json(
                WebSocketMessage(
                    id=self.ws_id, type="Info", data={"Error": self.check_result}
                ).model_dump()
            )
            return

        # 记录配置文件
        logger.info(f"记录通用脚本配置文件: {self.script_config_path}")
        (Path.cwd() / f"data/{self.script_id}/Temp").mkdir(parents=True, exist_ok=True)
        if self.script_config_path.exists():
            if self.script_config.get("Script", "ConfigPathMode") == "Folder":
                shutil.copytree(
                    self.script_config_path,
                    Path.cwd() / f"data/{self.script_id}/Temp",
                    dirs_exist_ok=True,
                )
            elif self.script_config.get("Script", "ConfigPathMode") == "File":
                shutil.copy(
                    self.script_config_path,
                    Path.cwd() / f"data/{self.script_id}/Temp/config.temp",
                )

        # 整理用户数据, 筛选需代理的用户
        if self.mode != "设置脚本":

            self.user_list: List[Dict[str, str]] = [
                {
                    "user_id": str(uid),
                    "status": "等待",
                    "name": config.get("Info", "Name"),
                }
                for uid, config in self.user_config.items()
                if config.get("Info", "Status")
                and config.get("Info", "RemainedDay") != 0
            ]

            logger.info(f"用户列表创建完成, 已筛选子配置数: {len(self.user_list)}")

        # 自动代理模式
        if self.mode == "自动代理":

            # 执行情况预处理
            for _ in self.user_list:
                if (
                    self.user_config[uuid.UUID(_["user_id"])].get(
                        "Data", "LastProxyDate"
                    )
                    != self.curdate
                ):
                    await self.user_config[uuid.UUID(_["user_id"])].set(
                        "Data", "LastProxyDate", self.curdate
                    )
                    await self.user_config[uuid.UUID(_["user_id"])].set(
                        "Data", "ProxyTimes", 0
                    )

            # 开始代理
            for self.index, user in enumerate(self.user_list):

                try:

                    self.cur_user_data = self.user_config[uuid.UUID(user["user_id"])]

                    if (self.script_config.get("Run", "ProxyTimesLimit") == 0) or (
                        self.cur_user_data.get("Data", "ProxyTimes")
                        < self.script_config.get("Run", "ProxyTimesLimit")
                    ):
                        user["status"] = "运行"
                        await Config.send_json(
                            WebSocketMessage(
                                id=self.ws_id,
                                type="Update",
                                data={"user_list": self.user_list},
                            ).model_dump()
                        )
                    else:
                        user["status"] = "跳过"
                        await Config.send_json(
                            WebSocketMessage(
                                id=self.ws_id,
                                type="Update",
                                data={"user_list": self.user_list},
                            ).model_dump()
                        )
                        continue

                    logger.info(f"开始代理用户: {user['user_id']}")

                    self.user_start_time = datetime.now()

                    self.run_book = False

                    if not (
                        Path.cwd()
                        / f"data/{self.script_id}/{user['user_id']}/ConfigFile"
                    ).exists():

                        logger.error(f"用户: {user['user_id']} - 未找到配置文件")
                        await Config.send_json(
                            WebSocketMessage(
                                id=self.ws_id,
                                type="Info",
                                data={"Error": f"未找到 {user['user_id']} 的配置文件"},
                            ).model_dump()
                        )
                        self.run_book = False
                        continue

                    # 尝试次数循环
                    for i in range(self.script_config.get("Run", "RunTimesLimit")):

                        if self.run_book:
                            break

                        logger.info(
                            f"用户 {user['user_id']} - 尝试次数: {i + 1}/{self.script_config.get('Run','RunTimesLimit')}"
                        )

                        # 配置脚本
                        await self.set_general()
                        # 记录当前时间
                        self.log_start_time = datetime.now()

                        # 执行任务前脚本
                        if (
                            self.cur_user_data.get("Info", "IfScriptBeforeTask")
                            and Path(
                                self.cur_user_data.get("Info", "ScriptBeforeTask")
                            ).exists()
                        ):
                            await self.execute_script_task(
                                Path(
                                    self.cur_user_data.get("Info", "ScriptBeforeTask")
                                ),
                                "脚本前任务",
                            )

                        # 启动游戏/模拟器
                        if self.script_config.get("Game", "Enabled"):

                            try:
                                logger.info(
                                    f"启动游戏/模拟器: {self.game_path}, 参数: {self.script_config.get('Game','Arguments')}"
                                )
                                await self.game_process_manager.open_process(
                                    self.game_path,
                                    str(
                                        self.script_config.get("Game", "Arguments")
                                    ).split(" "),
                                    0,
                                )
                            except Exception as e:
                                logger.exception(f"启动游戏/模拟器时出现异常: {e}")
                                await Config.send_json(
                                    WebSocketMessage(
                                        id=self.ws_id,
                                        type="Info",
                                        data={
                                            "Error": f"启动游戏/模拟器时出现异常: {e}"
                                        },
                                    ).model_dump()
                                )
                                self.general_result = "游戏/模拟器启动失败"
                                break

                            # 更新静默进程标记有效时间
                            if self.script_config.get("Game", "Type") == "Emulator":
                                logger.info(
                                    f"更新静默进程标记: {self.game_path}, 标记有效时间: {datetime.now() + timedelta(seconds=self.script_config.get('Game', 'WaitTime') + 10)}"
                                )
                                Config.silence_dict[
                                    self.game_path
                                ] = datetime.now() + timedelta(
                                    seconds=self.script_config.get("Game", "WaitTime")
                                    + 10
                                )

                            await Config.send_json(
                                WebSocketMessage(
                                    id=self.ws_id,
                                    type="Update",
                                    data={
                                        "log": f"正在等待游戏/模拟器完成启动\n请等待{self.script_config.get('Game', 'WaitTime')}s"
                                    },
                                ).model_dump()
                            )
                            await asyncio.sleep(
                                self.script_config.get("Game", "WaitTime")
                            )

                        # 运行脚本任务
                        logger.info(
                            f"运行脚本任务: {self.script_exe_path}, 参数: {self.script_arguments}"
                        )
                        await self.general_process_manager.open_process(
                            self.script_exe_path,
                            self.script_arguments,
                            tracking_time=(
                                60
                                if self.script_config.get("Script", "IfTrackProcess")
                                else 0
                            ),
                        )

                        # 监测运行状态
                        await self.general_log_monitor.start(
                            self.script_log_path, self.log_start_time
                        )
                        self.wait_event.clear()
                        await self.wait_event.wait()

                        await self.general_log_monitor.stop()

                        # 处理通用脚本结果
                        if self.general_result == "Success!":

                            # 标记任务完成
                            self.run_book = True

                            logger.info(
                                f"用户: {user['user_id']} - 通用脚本进程完成代理任务"
                            )
                            await Config.send_json(
                                WebSocketMessage(
                                    id=self.ws_id,
                                    type="Update",
                                    data={
                                        "log": "检测到通用脚本进程完成代理任务\n正在等待相关程序结束\n请等待10s"
                                    },
                                ).model_dump()
                            )

                            # 中止相关程序
                            logger.info(f"中止相关程序: {self.script_exe_path}")
                            await self.general_process_manager.kill()
                            await System.kill_process(self.script_exe_path)
                            if self.script_config.get("Game", "Enabled"):
                                logger.info(
                                    f"中止游戏/模拟器进程: {list(self.game_process_manager.tracked_pids)}"
                                )
                                await self.game_process_manager.kill()
                                if self.script_config.get("Game", "IfForceClose"):
                                    await System.kill_process(self.game_path)

                            await asyncio.sleep(10)

                            # 更新脚本配置文件
                            if self.script_config.get("Script", "UpdateConfigMode") in [
                                "Success",
                                "Always",
                            ]:

                                if (
                                    self.script_config.get("Script", "ConfigPathMode")
                                    == "Folder"
                                ):
                                    shutil.copytree(
                                        self.script_config_path,
                                        Path.cwd()
                                        / f"data/{self.script_id}/{user['user_id']}/ConfigFile",
                                        dirs_exist_ok=True,
                                    )
                                elif (
                                    self.script_config.get("Script", "ConfigPathMode")
                                    == "File"
                                ):
                                    shutil.copy(
                                        self.script_config_path,
                                        Path.cwd()
                                        / f"data/{self.script_id}/{user['user_id']}/ConfigFile"
                                        / self.script_config_path.name,
                                    )
                                logger.success("通用脚本配置文件已更新")

                        else:
                            logger.error(
                                f"配置: {user['user_id']} - 代理任务异常: {self.general_result}"
                            )
                            # 打印中止信息
                            # 此时, log变量内存储的就是出现异常的日志信息, 可以保存或发送用于问题排查
                            await Config.send_json(
                                WebSocketMessage(
                                    id=self.ws_id,
                                    type="Update",
                                    data={
                                        "log": f"{self.general_result}\n正在中止相关程序\n请等待10s"
                                    },
                                ).model_dump()
                            )

                            # 中止相关程序
                            logger.info(f"中止相关程序: {self.script_exe_path}")
                            await self.general_process_manager.kill()
                            await System.kill_process(self.script_exe_path)
                            if self.script_config.get("Game", "Enabled"):
                                logger.info(
                                    f"中止游戏/模拟器进程: {list(self.game_process_manager.tracked_pids)}"
                                )
                                await self.game_process_manager.kill()
                                if self.script_config.get("Game", "IfForceClose"):
                                    await System.kill_process(self.game_path)

                            # 推送异常通知
                            await Notify.push_plyer(
                                "用户自动代理出现异常！",
                                f"用户 {user['name']} 的自动代理出现一次异常",
                                f"{user['name']} 的自动代理出现异常",
                                3,
                            )

                            await asyncio.sleep(10)

                            # 更新脚本配置文件
                            if self.script_config.get("Script", "UpdateConfigMode") in [
                                "Failure",
                                "Always",
                            ]:

                                if (
                                    self.script_config.get("Script", "ConfigPathMode")
                                    == "Folder"
                                ):
                                    shutil.copytree(
                                        self.script_config_path,
                                        Path.cwd()
                                        / f"data/{self.script_id}/{user['user_id']}/ConfigFile",
                                        dirs_exist_ok=True,
                                    )
                                elif (
                                    self.script_config.get("Script", "ConfigPathMode")
                                    == "File"
                                ):
                                    shutil.copy(
                                        self.script_config_path,
                                        Path.cwd()
                                        / f"data/{self.script_id}/{user['user_id']}/ConfigFile"
                                        / self.script_config_path.name,
                                    )
                                logger.success("通用脚本配置文件已更新")

                        # 执行任务后脚本
                        if (
                            self.cur_user_data.get("Info", "IfScriptAfterTask")
                            and Path(
                                self.cur_user_data.get("Info", "ScriptAfterTask")
                            ).exists()
                        ):
                            await self.execute_script_task(
                                Path(self.cur_user_data.get("Info", "ScriptAfterTask")),
                                "脚本后任务",
                            )

                        # 保存运行日志以及统计信息
                        await Config.save_general_log(
                            Path.cwd()
                            / f"history/{self.curdate}/{user['name']}/{self.log_start_time.strftime('%H-%M-%S')}.log",
                            self.general_logs,
                            self.general_result,
                        )

                    await self.result_record()

                except Exception as e:
                    logger.exception(f"用户 {user['user_id']} 代理时出现异常: {e}")
                    user["status"] = "异常"
                    await Config.send_json(
                        WebSocketMessage(
                            id=self.ws_id,
                            type="Info",
                            data={"Error": f"代理用户 {user['name']} 时出现异常: {e}"},
                        ).model_dump()
                    )

        # 设置通用脚本模式
        elif self.mode == "设置脚本":

            # 配置通用脚本
            await self.set_general()
            # 创建通用脚本任务
            logger.info(
                f"运行脚本任务: {self.script_set_exe_path}, 参数: {self.script_set_arguments}"
            )
            await self.general_process_manager.open_process(
                self.script_set_exe_path,
                self.script_set_arguments,
                tracking_time=(
                    60 if self.script_config.get("Script", "IfTrackProcess") else 0
                ),
            )

            # 等待用户完成配置
            self.wait_event.clear()
            await self.wait_event.wait()

    async def result_record(self) -> None:
        """记录用户结果信息"""

        # 发送统计信息
        statistics = {
            "user_info": self.user_list[self.index]["name"],
            "start_time": self.user_start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user_result": "代理成功" if self.run_book else self.general_result,
        }
        try:
            await self.push_notification(
                "统计信息",
                f"{self.current_date} | 用户 {self.user_list[self.index]['name']} 的自动代理统计报告",
                statistics,
            )
        except Exception as e:
            logger.exception(f"推送统计信息失败: {e}")
            await Config.send_json(
                WebSocketMessage(
                    id=self.ws_id,
                    type="Info",
                    data={"Error": f"推送统计信息失败: {e}"},
                ).model_dump()
            )

        if self.run_book:
            # 成功完成代理的用户修改相关参数
            if (
                self.cur_user_data.get("Data", "ProxyTimes") == 0
                and self.cur_user_data.get("Info", "RemainedDay") != -1
            ):
                await self.cur_user_data.set(
                    "Info",
                    "RemainedDay",
                    self.cur_user_data.get("Info", "RemainedDay") - 1,
                )
            await self.cur_user_data.set(
                "Data",
                "ProxyTimes",
                self.cur_user_data.get("Data", "ProxyTimes") + 1,
            )
            self.user_list[self.index]["status"] = "完成"
            logger.success(
                f"用户 {self.user_list[self.index]['user_id']} 的自动代理任务已完成"
            )
            await Notify.push_plyer(
                "成功完成一个自动代理任务！",
                f"已完成用户 {self.user_list[self.index]['name']} 的自动代理任务",
                f"已完成 {self.user_list[self.index]['name']} 的自动代理任务",
                3,
            )
        else:
            # 录入代理失败的用户
            logger.error(
                f"用户 {self.user_list[self.index]['user_id']} 的自动代理任务未完成"
            )
            self.user_list[self.index]["status"] = "异常"

    async def final_task(self, task: asyncio.Task):
        """结束时的收尾工作"""

        logger.info("MAA 主任务已结束, 开始执行后续操作")

        await Config.ScriptConfig[self.script_id].unlock()
        logger.success(f"已解锁脚本配置 {self.script_id}")

        # 结束各子任务
        await self.general_process_manager.kill(if_force=True)
        await System.kill_process(self.script_exe_path)
        await System.kill_process(self.script_set_exe_path)
        await self.game_process_manager.kill()
        await self.general_log_monitor.stop()
        del self.general_process_manager
        del self.game_process_manager
        del self.general_log_monitor

        if self.check_result != "Success!":
            return self.check_result

        if (
            self.mode == "自动代理"
            and hasattr(self, "index")
            and self.user_list[self.index]["status"] == "运行"
        ):

            self.general_result = "用户手动中止任务"

            # 更新脚本配置文件
            if self.script_config.get("Script", "UpdateConfigMode") in [
                "Failure",
                "Always",
            ]:

                if self.script_config.get("Script", "ConfigPathMode") == "Folder":
                    shutil.copytree(
                        self.script_config_path,
                        Path.cwd()
                        / f"data/{self.script_id}/{self.user_list[self.index]['user_id']}/ConfigFile",
                        dirs_exist_ok=True,
                    )
                elif self.script_config.get("Script", "ConfigPathMode") == "File":
                    shutil.copy(
                        self.script_config_path,
                        Path.cwd()
                        / f"data/{self.script_id}/{self.user_list[self.index]['user_id']}/ConfigFile"
                        / self.script_config_path.name,
                    )
                logger.success("通用脚本配置文件已更新")

            # 执行任务后脚本
            if (
                self.cur_user_data.get("Info", "IfScriptAfterTask")
                and Path(self.cur_user_data.get("Info", "ScriptAfterTask")).exists()
            ):
                await self.execute_script_task(
                    Path(self.cur_user_data.get("Info", "ScriptAfterTask")),
                    "脚本后任务",
                )

            # 保存运行日志以及统计信息
            await Config.save_general_log(
                Path.cwd()
                / f"history/{self.curdate}/{self.user_list[self.index]['name']}/{self.log_start_time.strftime('%H-%M-%S')}.log",
                self.general_logs,
                self.general_result,
            )

            await self.result_record()

        # 导出结果
        if self.mode == "自动代理":

            # 更新用户数据
            await Config.ScriptConfig[self.script_id].UserData.load(
                await self.user_config.toDict()
            )
            await Config.ScriptConfig.save()

            error_user = [_["name"] for _ in self.user_list if _["status"] == "异常"]
            over_user = [_["name"] for _ in self.user_list if _["status"] == "完成"]
            wait_user = [_["name"] for _ in self.user_list if _["status"] == "等待"]

            # 保存运行日志
            title = (
                f"{self.current_date} | {self.script_config.get("Info", "Name")}的{self.mode}任务报告"
                if self.script_config.get("Info", "Name") != ""
                else f"{self.current_date} | {self.mode}任务报告"
            )
            result = {
                "title": f"{self.mode}任务报告",
                "script_name": (
                    self.script_config.get("Info", "Name")
                    if self.script_config.get("Info", "Name") != ""
                    else "空白"
                ),
                "start_time": self.begin_time,
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "completed_count": len(over_user),
                "uncompleted_count": len(error_user) + len(wait_user),
                "failed_user": error_user,
                "waiting_user": wait_user,
            }

            # 生成结果文本
            result_text = (
                f"任务开始时间: {result['start_time']}, 结束时间: {result['end_time']}\n"
                f"已完成数: {result['completed_count']}, 未完成数: {result['uncompleted_count']}\n\n"
            )
            if len(result["failed_user"]) > 0:
                result_text += (
                    f"{self.mode} 未成功的用户: \n{"\n".join(result['failed_user'])}\n"
                )
            if len(result["waiting_user"]) > 0:
                result_text += f"\n未开始{self.mode}的用户: \n{"\n".join(result['waiting_user'])}\n"

            # 推送代理结果通知
            await Notify.push_plyer(
                title.replace("报告", "已完成！"),
                f"已完成配置数: {len(over_user)}, 未完成配置数: {len(error_user) + len(wait_user)}",
                f"已完成配置数: {len(over_user)}, 未完成配置数: {len(error_user) + len(wait_user)}",
                10,
            )
            try:
                await self.push_notification("代理结果", title, result)
            except Exception as e:
                logger.exception(f"推送代理结果失败: {e}")
                await Config.send_json(
                    WebSocketMessage(
                        id=self.ws_id,
                        type="Info",
                        data={"Error": f"推送代理结果失败: {e}"},
                    ).model_dump()
                )

        elif self.mode == "设置脚本":

            (Path.cwd() / f"data/{self.script_id}/{self.user_id}/ConfigFile").mkdir(
                parents=True, exist_ok=True
            )
            if self.script_config.get("Script", "ConfigPathMode") == "Folder":
                shutil.copytree(
                    self.script_config_path,
                    Path.cwd() / f"data/{self.script_id}/{self.user_id}/ConfigFile",
                    dirs_exist_ok=True,
                )
                logger.success(
                    f"通用脚本配置已保存到: {Path.cwd() / f'data/{self.script_id}/{self.user_id}/ConfigFile'}"
                )
            elif self.script_config.get("Script", "ConfigPathMode") == "File":
                shutil.copy(
                    self.script_config_path,
                    Path.cwd()
                    / f"data/{self.script_id}/{self.user_id}/ConfigFile"
                    / self.script_config_path.name,
                )
                logger.success(
                    f"通用脚本配置已保存到: {Path.cwd() / f'data/{self.script_id}/{self.user_id}/ConfigFile' / self.script_config_path.name}"
                )
            result_text = ""

        # 复原通用脚本配置文件
        if (
            self.script_config.get("Script", "ConfigPathMode") == "Folder"
            and (Path.cwd() / f"data/{self.script_id}/Temp").exists()
        ):
            logger.info(
                f"复原通用脚本配置文件: {Path.cwd() / f"data/{self.script_id}/Temp"}"
            )
            shutil.copytree(
                Path.cwd() / f"data/{self.script_id}/Temp",
                self.script_config_path,
                dirs_exist_ok=True,
            )
            shutil.rmtree(Path.cwd() / f"data/{self.script_id}/Temp")
        elif (
            self.script_config.get("Script", "ConfigPathMode") == "File"
            and (Path.cwd() / f"data/{self.script_id}/Temp/config.temp").exists()
        ):
            logger.info(
                f"复原通用脚本配置文件: {Path.cwd() / f"data/{self.script_id}/Temp/config.temp"}"
            )
            shutil.copy(
                Path.cwd() / f"data/{self.script_id}/Temp/config.temp",
                self.script_config_path,
            )
            shutil.rmtree(Path.cwd() / f"data/{self.script_id}/Temp")

        return result_text

    async def check_general_log(self, log_content: List[str]) -> None:
        """获取脚本日志并检查以判断脚本程序运行状态"""

        self.general_logs = log_content
        log = "".join(log_content)

        # 更新日志
        if await self.general_process_manager.is_running():

            await Config.send_json(
                WebSocketMessage(
                    id=self.ws_id, type="Update", data={"log": log}
                ).model_dump()
            )

        if "自动代理" in self.mode:

            # 获取最近一条日志的时间
            latest_time = self.log_start_time
            for _ in self.general_logs[::-1]:
                try:
                    latest_time = strptime(
                        _[self.log_time_range[0] : self.log_time_range[1]],
                        self.script_config.get("Script", "LogTimeFormat"),
                        self.log_start_time,
                    )
                    break
                except ValueError:
                    pass

            logger.info(f"通用脚本最近一条日志时间: {latest_time}")

            for success_sign in self.success_log:
                if success_sign in log:
                    self.general_result = "Success!"
                    break
            else:

                if datetime.now() - latest_time > timedelta(
                    minutes=self.script_config.get("Run", "RunTimeLimit")
                ):
                    self.general_result = "脚本进程超时"
                else:
                    for error_sign in self.error_log:
                        if error_sign in log:
                            self.general_result = f"异常日志: {error_sign}"
                            break
                    else:
                        if await self.general_process_manager.is_running():
                            self.general_result = "Wait"
                        elif self.success_log:
                            self.general_result = "脚本在完成任务前退出"
                        else:
                            self.general_result = "Success!"

        logger.info(f"通用脚本日志分析结果: {self.general_result}")

        if self.general_result != "Wait":

            logger.info(f"MAA 任务结果: {self.general_result}, 日志锁已释放")
            self.wait_event.set()

    async def set_general(self) -> None:
        """配置通用脚本运行参数"""
        logger.info(f"开始配置脚本运行参数: {self.mode}")

        # 配置前关闭可能未正常退出的脚本进程
        if self.mode == "自动代理":
            await System.kill_process(self.script_exe_path)
        elif self.mode == "设置脚本":
            await System.kill_process(self.script_set_exe_path)

        # 预导入配置文件
        if self.mode == "设置脚本":
            if (
                self.script_config.get("Script", "ConfigPathMode") == "Folder"
                and (
                    Path.cwd() / f"data/{self.script_id}/{self.user_id}/ConfigFile"
                ).exists()
            ):
                shutil.copytree(
                    Path.cwd() / f"data/{self.script_id}/{self.user_id}/ConfigFile",
                    self.script_config_path,
                    dirs_exist_ok=True,
                )
            elif (
                self.script_config.get("Script", "ConfigPathMode") == "File"
                and (
                    Path.cwd()
                    / f"data/{self.script_id}/{self.user_id}/ConfigFile"
                    / self.script_config_path.name
                ).exists()
            ):
                shutil.copy(
                    Path.cwd()
                    / f"data/{self.script_id}/{self.user_id}/ConfigFile"
                    / self.script_config_path.name,
                    self.script_config_path,
                )
        else:
            if self.script_config.get("Script", "ConfigPathMode") == "Folder":
                shutil.copytree(
                    Path.cwd()
                    / f"data/{self.script_id}/{self.user_list[self.index]['user_id']}/ConfigFile",
                    self.script_config_path,
                    dirs_exist_ok=True,
                )
            elif self.script_config.get("Script", "ConfigPathMode") == "File":
                shutil.copy(
                    Path.cwd()
                    / f"data/{self.script_id}/{self.user_list[self.index]['user_id']}/ConfigFile"
                    / self.script_config_path.name,
                    self.script_config_path,
                )

        logger.info(f"脚本运行参数配置完成: {self.mode}")

    async def execute_script_task(self, script_path: Path, task_name: str) -> bool:
        """执行脚本任务并等待结束"""

        try:
            logger.info(f"开始执行{task_name}: {script_path}")

            # 根据文件类型选择执行方式
            if script_path.suffix.lower() == ".py":
                cmd = [sys.executable, str(script_path)]
                use_shell = False
            elif script_path.suffix.lower() in [".bat", ".cmd"]:
                # bat/cmd 脚本使用 cmd.exe 执行，并传递 admin 参数跳过权限检查
                cmd = ["cmd.exe", "/c", str(script_path), "admin"]
                use_shell = False
            elif script_path.suffix.lower() == ".exe":
                cmd = [str(script_path)]
                use_shell = False
            elif script_path.suffix.lower() == "":
                logger.warning(f"{task_name}脚本没有指定后缀名, 无法执行")
                return False
            else:
                # 使用系统默认程序打开
                os.startfile(str(script_path))
                return True

            # 执行脚本并等待结束
            result = subprocess.run(
                cmd,
                cwd=script_path.parent,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                    if Config.get("Function", "IfSilence")
                    else 0
                ),
                timeout=600,
                shell=use_shell,
                text=True,
                encoding='utf-8',
                errors='replace',  # 使用 replace 而不是 ignore，避免输出丢失
                input='\n',  # 发送换行符，使 pause/input() 自动继续（会自动设置 stdin=PIPE，因此不必在使用stdin参数）
            )

            if result.returncode == 0:
                logger.info(f"{task_name}执行成功")
                if result.stdout and result.stdout.strip():
                    logger.info(f"{task_name}输出:\n{result.stdout}")
                return True
            else:
                logger.error(f"{task_name}执行失败, 返回码: {result.returncode}")
                if result.stdout and result.stdout.strip():
                    logger.warning(f"{task_name}标准输出:\n{result.stdout}")
                if result.stderr and result.stderr.strip():
                    logger.error(f"{task_name}错误输出:\n{result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"{task_name}执行超时")
            return False
        except Exception as e:
            logger.exception(f"执行{task_name}时出现异常: {e}")
            return False

    async def push_notification(self, mode: str, title: str, message) -> None:
        """通过所有渠道推送通知"""

        logger.info(f"开始推送通知, 模式: {mode}, 标题: {title}")

        env = Environment(loader=FileSystemLoader(str(Path.cwd() / "res/html")))

        if mode == "代理结果" and (
            Config.get("Notify", "SendTaskResultTime") == "任何时刻"
            or (
                Config.get("Notify", "SendTaskResultTime") == "仅失败时"
                and message["uncompleted_count"] != 0
            )
        ):
            # 生成文本通知内容
            message_text = (
                f"任务开始时间: {message['start_time']}, 结束时间: {message['end_time']}\n"
                f"已完成数: {message['completed_count']}, 未完成数: {message['uncompleted_count']}\n\n"
            )

            if len(message["failed_user"]) > 0:
                message_text += f"{self.mode[2:4]}未成功的配置: \n{"\n".join(message['failed_user'])}\n"
            if len(message["waiting_user"]) > 0:
                message_text += f"\n未开始{self.mode[2:4]}的配置: \n{"\n".join(message['waiting_user'])}\n"

            # 生成HTML通知内容
            message["failed_user"] = "、".join(message["failed_user"])
            message["waiting_user"] = "、".join(message["waiting_user"])

            template = env.get_template("general_result.html")
            message_html = template.render(message)

            # ServerChan的换行是两个换行符。故而将\n替换为\n\n
            serverchan_message = message_text.replace("\n", "\n\n")

            # 发送全局通知
            if Config.get("Notify", "IfSendMail"):
                await Notify.send_mail(
                    "网页", title, message_html, Config.get("Notify", "ToAddress")
                )

            if Config.get("Notify", "IfServerChan"):
                await Notify.ServerChanPush(
                    title,
                    f"{serverchan_message}\n\nAUTO-MAS 敬上",
                    Config.get("Notify", "ServerChanKey"),
                )

            # 发送自定义Webhook通知
            for webhook in Config.Notify_CustomWebhooks.values():
                await Notify.WebhookPush(
                    title, f"{message_text}\n\nAUTO-MAS 敬上", webhook
                )

        elif mode == "统计信息":

            message_text = (
                f"开始时间: {message['start_time']}\n"
                f"结束时间: {message['end_time']}\n"
                f"通用脚本执行结果: {message['user_result']}\n\n"
            )

            # 生成HTML通知内容
            template = env.get_template("general_statistics.html")
            message_html = template.render(message)

            # ServerChan的换行是两个换行符。故而将\n替换为\n\n
            serverchan_message = message_text.replace("\n", "\n\n")

            # 发送全局通知
            if Config.get("Notify", "IfSendStatistic"):

                if Config.get("Notify", "IfSendMail"):
                    await Notify.send_mail(
                        "网页", title, message_html, Config.get("Notify", "ToAddress")
                    )

                if Config.get("Notify", "IfServerChan"):
                    await Notify.ServerChanPush(
                        title,
                        f"{serverchan_message}\n\nAUTO-MAS 敬上",
                        Config.get("Notify", "ServerChanKey"),
                    )

                # 发送自定义Webhook通知
                for webhook in Config.Notify_CustomWebhooks.values():
                    await Notify.WebhookPush(
                        title, f"{message_text}\n\nAUTO-MAS 敬上", webhook
                    )

            # 发送用户单独通知
            if self.cur_user_data.get("Notify", "Enabled") and self.cur_user_data.get(
                "Notify", "IfSendStatistic"
            ):

                # 发送邮件通知
                if self.cur_user_data.get("Notify", "IfSendMail"):
                    if self.cur_user_data.get("Notify", "ToAddress"):
                        await Notify.send_mail(
                            "网页",
                            title,
                            message_html,
                            self.cur_user_data.get("Notify", "ToAddress"),
                        )
                    else:
                        logger.error(f"用户邮箱地址为空, 无法发送用户单独的邮件通知")

                # 发送ServerChan通知
                if self.cur_user_data.get("Notify", "IfServerChan"):
                    if self.cur_user_data.get("Notify", "ServerChanKey"):
                        await Notify.ServerChanPush(
                            title,
                            f"{serverchan_message}\n\nAUTO-MAS 敬上",
                            self.cur_user_data.get("Notify", "ServerChanKey"),
                        )
                    else:
                        logger.error(
                            "用户ServerChan密钥为空, 无法发送用户单独的ServerChan通知"
                        )

                # 推送CompanyWebHookBot通知
                for webhook in self.cur_user_data.Notify_CustomWebhooks.values():
                    await Notify.WebhookPush(
                        title, f"{message_text}\n\nAUTO-MAS 敬上", webhook
                    )
