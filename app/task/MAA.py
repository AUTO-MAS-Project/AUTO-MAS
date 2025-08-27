#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361

#   This file is part of AUTO_MAA.

#   AUTO_MAA is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO_MAA is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO_MAA. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import json
import uuid
import asyncio
import subprocess
import shutil
import win32com.client
from pathlib import Path
from datetime import datetime, timedelta
from jinja2 import Environment, FileSystemLoader
from typing import List, Dict, Optional

from app.core import Broadcast, Config, MaaConfig, MaaUserConfig
from app.models.schema import WebSocketMessage
from app.models.ConfigBase import MultipleConfig
from app.services import Notify, System
from app.utils import get_logger, LogMonitor, ProcessManager
from .skland import skland_sign_in


logger = get_logger("MAA 调度器")


METHOD_BOOK = {"NoAction": "8", "ExitGame": "9", "ExitEmulator": "12"}
MOOD_BOOK = {"Annihilation": "剿灭", "Routine": "日常"}


class MaaManager:
    """MAA控制器"""

    def __init__(
        self, mode: str, script_id: uuid.UUID, user_id: Optional[uuid.UUID], ws_id: str
    ):
        super().__init__()

        self.mode = mode
        self.script_id = script_id
        self.user_id = user_id
        self.ws_id = ws_id

        self.emulator_process_manager = ProcessManager()
        self.maa_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()
        self.message_queue = asyncio.Queue()

        self.maa_logs = []
        self.maa_result = "Wait"
        self.maa_update_package = ""

    async def configure(self):
        """提取配置信息"""

        await Broadcast.subscribe(self.message_queue)

        await Config.ScriptConfig[self.script_id].lock()

        self.script_config = Config.ScriptConfig[self.script_id]
        if isinstance(self.script_config, MaaConfig):
            self.user_config = MultipleConfig([MaaUserConfig])
            await self.user_config.load(await self.script_config.UserData.toDict())

        self.maa_root_path = Path(self.script_config.get("Info", "Path"))
        self.maa_set_path = self.maa_root_path / "config/gui.json"
        self.maa_log_path = self.maa_root_path / "debug/gui.log"
        self.maa_exe_path = self.maa_root_path / "MAA.exe"
        self.maa_tasks_path = self.maa_root_path / "resource/tasks/tasks.json"
        self.port_range = [0] + [
            (i // 2 + 1) * (-1 if i % 2 else 1)
            for i in range(0, 2 * self.script_config.get("Run", "ADBSearchRange"))
        ]
        self.maa_log_monitor = LogMonitor(
            (1, 20), "%Y-%m-%d %H:%M:%S", self.check_maa_log
        )

        logger.success(f"{self.script_id}已锁定，MAA配置提取完成")

    def check_config(self) -> str:
        """检查配置是否可用"""

        if not self.maa_exe_path.exists():
            return "MAA.exe文件不存在，请检查MAA路径设置！"
        if not self.maa_set_path.exists():
            return "MAA配置文件不存在，请检查MAA路径设置！"
        if (self.mode != "设置脚本" or self.user_id is not None) and not (
            Path.cwd() / f"data/{self.script_id}/Default/ConfigFile/gui.json"
        ).exists():
            return "未完成 MAA 全局设置，请先设置 MAA！"
        return "Success!"

    async def run(self):
        """主进程，运行MAA代理进程"""

        self.current_date = datetime.now().strftime("%m-%d")
        self.curdate = Config.server_date().strftime("%Y-%m-%d")
        self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        await self.configure()
        self.check_result = self.check_config()
        if self.check_result != "Success!":
            logger.error(f"未通过配置检查：{self.check_result}")
            await Config.send_json(
                WebSocketMessage(
                    id=self.ws_id, type="Info", data={"Error": self.check_result}
                ).model_dump()
            )
            return

        # 记录 MAA 配置文件
        logger.info(f"记录 MAA 配置文件：{self.maa_set_path}")
        (Path.cwd() / f"data/{self.script_id}/Temp").mkdir(parents=True, exist_ok=True)
        if self.maa_set_path.exists():
            shutil.copy(
                self.maa_set_path, Path.cwd() / f"data/{self.script_id}/Temp/gui.json"
            )

        # 整理用户数据，筛选需代理的用户
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
            self.user_list = sorted(
                self.user_list,
                key=lambda x: (
                    self.user_config[uuid.UUID(x["user_id"])].get("Info", "Mode")
                ),
            )

            logger.info(f"用户列表创建完成，已筛选用户数：{len(self.user_list)}")

        # 自动代理模式
        if self.mode == "自动代理":

            # 标记是否需要重启模拟器
            self.if_open_emulator = True
            # # 执行情况预处理
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

                # 详细模式用户首次代理需打开模拟器
                if self.cur_user_data.get("Info", "Mode") == "详细":
                    self.if_open_emulator = True

                # 初始化代理情况记录和模式替换表
                self.run_book = {
                    "Annihilation": bool(
                        self.cur_user_data.get("Info", "Annihilation") == "Close"
                    ),
                    "Routine": self.cur_user_data.get("Info", "Mode") == "复杂"
                    and not self.cur_user_data.get("Info", "Routine"),
                }

                self.user_logs_list = []
                self.user_start_time = datetime.now()

                if self.cur_user_data.get(
                    "Info", "IfSkland"
                ) and self.cur_user_data.get("Info", "SklandToken"):

                    if self.cur_user_data.get(
                        "Data", "LastSklandDate"
                    ) != datetime.now().strftime("%Y-%m-%d"):

                        await Config.send_json(
                            WebSocketMessage(
                                id=self.ws_id,
                                type="Update",
                                data={"log": "正在执行森空岛签到中\n请稍候~"},
                            ).model_dump()
                        )

                        skland_result = await skland_sign_in(
                            self.cur_user_data.get("Info", "SklandToken")
                        )

                        for type, user_list in skland_result.items():

                            if type != "总计" and len(user_list) > 0:

                                logger.info(
                                    f"用户: {user['user_id']} - 森空岛签到{type}: {'、'.join(user_list)}",
                                )
                                await Config.send_json(
                                    WebSocketMessage(
                                        id=self.ws_id,
                                        type="Info",
                                        data={
                                            (
                                                "Info" if type != "失败" else "Error"
                                            ): f"用户 {user['name']} 森空岛签到{type}: {'、'.join(user_list)}"
                                        },
                                    ).model_dump()
                                )
                        if skland_result["总计"] == 0:
                            logger.info(f"用户: {user['user_id']} - 森空岛签到失败")
                            await Config.send_json(
                                WebSocketMessage(
                                    id=self.ws_id,
                                    type="Info",
                                    data={
                                        "Error": f"用户 {user['name']} 森空岛签到失败",
                                    },
                                ).model_dump()
                            )

                        if (
                            skland_result["总计"] > 0
                            and len(skland_result["失败"]) == 0
                        ):
                            await self.cur_user_data.set(
                                "Data",
                                "LastSklandDate",
                                datetime.now().strftime("%Y-%m-%d"),
                            )

                elif self.cur_user_data.get("Info", "IfSkland"):
                    logger.warning(
                        f"用户: {user['user_id']} - 未配置森空岛签到Token，跳过森空岛签到"
                    )
                    await Config.send_json(
                        WebSocketMessage(
                            id=self.ws_id,
                            type="Info",
                            data={
                                "Warning": f"用户 {user['name']} 未配置森空岛签到Token，跳过森空岛签到"
                            },
                        ).model_dump()
                    )

                # 剿灭-日常模式循环
                for mode in ["Annihilation", "Routine"]:

                    if self.run_book[mode]:
                        continue

                    # 剿灭模式；满足条件跳过剿灭
                    if (
                        mode == "Annihilation"
                        and self.script_config.get("Run", "AnnihilationWeeklyLimit")
                        and datetime.strptime(
                            self.cur_user_data.get("Data", "LastAnnihilationDate"),
                            "%Y-%m-%d",
                        ).isocalendar()[:2]
                        == datetime.strptime(self.curdate, "%Y-%m-%d").isocalendar()[:2]
                    ):
                        logger.info(
                            f"用户: {user['user_id']} - 本周剿灭模式已达上限，跳过执行剿灭任务"
                        )
                        self.run_book[mode] = True
                        continue
                    else:
                        self.weekly_annihilation_limit_reached = False

                    if (
                        self.cur_user_data.get("Info", "Mode") == "详细"
                        and not (
                            Path.cwd()
                            / f"data/{self.script_id}/{user['user_id']}/ConfigFile/gui.json"
                        ).exists()
                    ):
                        logger.error(
                            f"用户: {user['user_id']} - 未找到日常详细配置文件"
                        )
                        await Config.send_json(
                            WebSocketMessage(
                                id=self.ws_id,
                                type="Info",
                                data={"Error": f"未找到 {user['name']} 的详细配置文件"},
                            ).model_dump()
                        )
                        self.run_book[mode] = False
                        break

                    # 更新当前模式到界面
                    await Config.send_json(
                        WebSocketMessage(
                            id=self.ws_id,
                            type="Update",
                            data={
                                "user_status": {
                                    "user_id": user["user_id"],
                                    "type": mode,
                                }
                            },
                        ).model_dump()
                    )

                    # 解析任务构成
                    if mode == "Routine":

                        self.task_dict = {
                            "WakeUp": str(self.cur_user_data.get("Task", "IfWakeUp")),
                            "Recruiting": str(
                                self.cur_user_data.get("Task", "IfRecruiting")
                            ),
                            "Base": str(self.cur_user_data.get("Task", "IfBase")),
                            "Combat": str(self.cur_user_data.get("Task", "IfCombat")),
                            "Mission": str(self.cur_user_data.get("Task", "IfMission")),
                            "Mall": str(self.cur_user_data.get("Task", "IfMall")),
                            "AutoRoguelike": str(
                                self.cur_user_data.get("Task", "IfAutoRoguelike")
                            ),
                            "Reclamation": str(
                                self.cur_user_data.get("Task", "IfReclamation")
                            ),
                        }

                    elif mode == "Annihilation":

                        self.task_dict = {
                            "WakeUp": "True",
                            "Recruiting": "False",
                            "Base": "False",
                            "Combat": "True",
                            "Mission": "False",
                            "Mall": "False",
                            "AutoRoguelike": "False",
                            "Reclamation": "False",
                        }

                    logger.info(
                        f"用户 {user['name']} - 模式: {mode} - 任务列表: {self.task_dict.values()}"
                    )

                    # 尝试次数循环
                    for i in range(self.script_config.get("Run", "RunTimesLimit")):

                        if self.run_book[mode]:
                            break

                        logger.info(
                            f"用户 {user['name']} - 模式: {mode} - 尝试次数: {i + 1}/{self.script_config.get('Run','RunTimesLimit')}",
                        )

                        # 配置MAA
                        set = await self.set_maa(mode)
                        # 记录当前时间
                        self.log_start_time = datetime.now()

                        # 记录模拟器与ADB路径
                        self.emulator_path = Path(
                            set["Configurations"]["Default"]["Start.EmulatorPath"]
                        )
                        self.emulator_arguments = set["Configurations"]["Default"][
                            "Start.EmulatorAddCommand"
                        ].split()
                        # 如果是快捷方式，进行解析
                        if (
                            self.emulator_path.suffix == ".lnk"
                            and self.emulator_path.exists()
                        ):
                            try:
                                shell = win32com.client.Dispatch("WScript.Shell")
                                shortcut = shell.CreateShortcut(str(self.emulator_path))
                                self.emulator_path = Path(shortcut.TargetPath)
                                self.emulator_arguments = shortcut.Arguments.split()
                            except Exception as e:
                                logger.exception(f"解析快捷方式时出现异常：{e}")
                                await Config.send_json(
                                    WebSocketMessage(
                                        id=self.ws_id,
                                        type="Info",
                                        data={
                                            "Error": f"解析快捷方式时出现异常：{e}",
                                        },
                                    ).model_dump()
                                )
                                self.if_open_emulator = True
                                break
                        elif not self.emulator_path.exists():
                            logger.error(f"模拟器快捷方式不存在：{self.emulator_path}")
                            await Config.send_json(
                                WebSocketMessage(
                                    id=self.ws_id,
                                    type="Info",
                                    data={
                                        "Error": f"模拟器快捷方式 {self.emulator_path} 不存在",
                                    },
                                ).model_dump()
                            )
                            self.if_open_emulator = True
                            break

                        self.wait_time = int(
                            set["Configurations"]["Default"][
                                "Start.EmulatorWaitSeconds"
                            ]
                        )

                        self.ADB_path = Path(
                            set["Configurations"]["Default"]["Connect.AdbPath"]
                        )
                        self.ADB_path = (
                            self.ADB_path
                            if self.ADB_path.is_absolute()
                            else self.maa_root_path / self.ADB_path
                        )
                        self.ADB_address = set["Configurations"]["Default"][
                            "Connect.Address"
                        ]
                        self.if_kill_emulator = bool(
                            set["Configurations"]["Default"]["MainFunction.PostActions"]
                            == "12"
                        )
                        self.if_open_emulator_process = bool(
                            set["Configurations"]["Default"][
                                "Start.OpenEmulatorAfterLaunch"
                            ]
                            == "True"
                        )

                        # 任务开始前释放ADB
                        try:
                            logger.info(f"释放ADB：{self.ADB_address}")
                            subprocess.run(
                                [self.ADB_path, "disconnect", self.ADB_address],
                                creationflags=subprocess.CREATE_NO_WINDOW,
                            )
                        except subprocess.CalledProcessError as e:
                            # 忽略错误,因为可能本来就没有连接
                            logger.warning(f"释放ADB时出现异常：{e}")
                        except Exception as e:
                            logger.exception(f"释放ADB时出现异常：{e}")
                            await Config.send_json(
                                WebSocketMessage(
                                    id=self.ws_id,
                                    type="Info",
                                    data={"Warning": f"释放ADB时出现异常：{e}"},
                                ).model_dump()
                            )

                        if self.if_open_emulator_process:
                            try:
                                logger.info(
                                    f"启动模拟器：{self.emulator_path}，参数：{self.emulator_arguments}"
                                )
                                await self.emulator_process_manager.open_process(
                                    self.emulator_path, self.emulator_arguments, 0
                                )
                            except Exception as e:
                                logger.exception(f"启动模拟器时出现异常：{e}")
                                await Config.send_json(
                                    WebSocketMessage(
                                        id=self.ws_id,
                                        type="Info",
                                        data={
                                            "Error": "启动模拟器时出现异常，请检查MAA中模拟器路径设置"
                                        },
                                    ).model_dump()
                                )
                                self.if_open_emulator = True
                                break

                        # 更新静默进程标记有效时间
                        logger.info(
                            f"更新静默进程标记：{self.emulator_path}，标记有效时间：{datetime.now() + timedelta(seconds=self.wait_time + 10)}"
                        )
                        Config.silence_dict[self.emulator_path] = (
                            datetime.now() + timedelta(seconds=self.wait_time + 10)
                        )

                        await self.search_ADB_address()

                        # 创建MAA任务
                        logger.info(f"启动MAA进程：{self.maa_exe_path}")
                        await self.maa_process_manager.open_process(
                            self.maa_exe_path, [], 0
                        )

                        # 监测MAA运行状态
                        self.log_check_mode = mode
                        await self.maa_log_monitor.start(
                            self.maa_log_path, self.log_start_time
                        )

                        self.wait_event.clear()
                        await self.wait_event.wait()

                        await self.maa_log_monitor.stop()

                        # 处理MAA结果
                        if self.maa_result == "Success!":

                            # 标记任务完成
                            self.run_book[mode] = True

                            logger.info(
                                f"用户: {user['user_id']} - MAA进程完成代理任务"
                            )
                            await Config.send_json(
                                WebSocketMessage(
                                    id=self.ws_id,
                                    type="Update",
                                    data={
                                        "log": "检测到MAA进程完成代理任务\n正在等待相关程序结束\n请等待10s"
                                    },
                                ).model_dump()
                            )

                        else:
                            logger.error(
                                f"用户: {user['user_id']} - 代理任务异常: {self.maa_result}",
                            )
                            # 打印中止信息
                            # 此时，log变量内存储的就是出现异常的日志信息，可以保存或发送用于问题排查
                            await Config.send_json(
                                WebSocketMessage(
                                    id=self.ws_id,
                                    type="Update",
                                    data={
                                        "log": f"{self.maa_result}\n正在中止相关程序\n请等待10s"
                                    },
                                ).model_dump()
                            )
                            # 无命令行中止MAA与其子程序
                            logger.info(f"中止MAA进程：{self.maa_exe_path}")
                            await self.maa_process_manager.kill(if_force=True)
                            await System.kill_process(self.maa_exe_path)

                            # 中止模拟器进程
                            logger.info(
                                f"中止模拟器进程：{list(self.emulator_process_manager.tracked_pids)}"
                            )
                            await self.emulator_process_manager.kill()

                            self.if_open_emulator = True

                            # 推送异常通知
                            Notify.push_plyer(
                                "用户自动代理出现异常！",
                                f"用户 {user['name']} 的{MOOD_BOOK[mode]}部分出现一次异常",
                                f"{user['name']}的{MOOD_BOOK[mode]}出现异常",
                                3,
                            )

                        await asyncio.sleep(10)

                        # 任务结束后释放ADB
                        try:
                            logger.info(f"释放ADB：{self.ADB_address}")
                            subprocess.run(
                                [self.ADB_path, "disconnect", self.ADB_address],
                                creationflags=subprocess.CREATE_NO_WINDOW,
                            )
                        except subprocess.CalledProcessError as e:
                            # 忽略错误,因为可能本来就没有连接
                            logger.warning(f"释放ADB时出现异常：{e}")
                        except Exception as e:
                            logger.exception(f"释放ADB时出现异常：{e}")
                            await Config.send_json(
                                WebSocketMessage(
                                    id=self.ws_id,
                                    type="Info",
                                    data={"Error": f"释放ADB时出现异常：{e}"},
                                ).model_dump()
                            )
                        # 任务结束后再次手动中止模拟器进程，防止退出不彻底
                        if self.if_kill_emulator:
                            logger.info(
                                f"任务结束后再次中止模拟器进程：{list(self.emulator_process_manager.tracked_pids)}"
                            )
                            await self.emulator_process_manager.kill()
                            self.if_open_emulator = True

                        # 从配置文件中解析所需信息
                        with self.maa_set_path.open(mode="r", encoding="utf-8") as f:
                            data = json.load(f)

                        # 记录自定义基建索引
                        await self.cur_user_data.set(
                            "Data",
                            "CustomInfrastPlanIndex",
                            data["Configurations"]["Default"][
                                "Infrast.CustomInfrastPlanIndex"
                            ],
                        )

                        # 记录更新包路径
                        if (
                            data["Global"]["VersionUpdate.package"]
                            and (
                                self.maa_root_path
                                / data["Global"]["VersionUpdate.package"]
                            ).exists()
                        ):
                            self.maa_update_package = data["Global"][
                                "VersionUpdate.package"
                            ]

                        # 记录剿灭情况
                        if (
                            mode == "Annihilation"
                            and self.weekly_annihilation_limit_reached
                        ):
                            await self.cur_user_data.set(
                                "Data", "LastAnnihilationDate", self.curdate
                            )
                        # 保存运行日志以及统计信息
                        if_six_star = await Config.save_maa_log(
                            Path.cwd()
                            / f"history/{self.curdate}/{user['name']}/{self.log_start_time.strftime('%H-%M-%S')}.log",
                            self.maa_logs,
                            self.maa_result,
                        )
                        self.user_logs_list.append(
                            Path.cwd()
                            / f"history/{self.curdate}/{user['name']}/{self.log_start_time.strftime('%H-%M-%S')}.json"
                        )
                        if if_six_star:
                            await self.push_notification(
                                "公招六星",
                                f"喜报：用户 {user['name']} 公招出六星啦！",
                                {
                                    "user_name": user["name"],
                                },
                            )

                        # 执行MAA解压更新动作
                        if self.maa_update_package:

                            logger.info(f"检测到MAA更新，正在执行更新动作")

                            await Config.send_json(
                                WebSocketMessage(
                                    id=self.ws_id,
                                    type="Update",
                                    data={
                                        "log": "检测到MAA存在更新\nMAA正在执行更新动作\n请等待10s"
                                    },
                                ).model_dump()
                            )
                            await self.set_maa("Update")
                            subprocess.Popen(
                                [self.maa_exe_path],
                                creationflags=subprocess.CREATE_NO_WINDOW,
                            )
                            await asyncio.sleep(10)
                            await System.kill_process(self.maa_exe_path)

                            self.maa_update_package = ""

                            logger.info(f"更新动作结束")

                await self.result_record()

        # 人工排查模式
        elif self.mode == "人工排查":

            # 人工排查时，屏蔽静默操作
            logger.info("人工排查任务开始，屏蔽静默操作")
            Config.if_ignore_silence.append(self.script_id)

            # 标记是否需要启动模拟器
            self.if_open_emulator = True

            # 开始排查
            for self.index, user in enumerate(self.user_list):

                self.cur_user_data = self.user_config[uuid.UUID(user["user_id"])]

                logger.info(f"开始排查用户: {user['user_id']}")

                user["status"] = "运行"
                await Config.send_json(
                    WebSocketMessage(
                        id=self.ws_id,
                        type="Update",
                        data={"user_list": self.user_list},
                    ).model_dump()
                )

                if self.cur_user_data.get("Info", "Mode") == "详细":
                    self.if_open_emulator = True

                self.run_book = {"SignIn": False, "PassCheck": False}

                # 启动重试循环
                while True:

                    # 配置MAA
                    await self.set_maa("人工排查")

                    # 记录当前时间
                    self.log_start_time = datetime.now()
                    # 创建MAA任务
                    logger.info(f"启动MAA进程：{self.maa_exe_path}")
                    await self.maa_process_manager.open_process(
                        self.maa_exe_path, [], 0
                    )

                    # 监测MAA运行状态
                    self.log_check_mode = "人工排查"
                    await self.maa_log_monitor.start(
                        self.maa_log_path, self.log_start_time
                    )

                    self.wait_event.clear()
                    await self.wait_event.wait()

                    await self.maa_log_monitor.stop()

                    logger.info(
                        f"用户: {user['user_id']} - MAA进程登录PRTS结果: {self.maa_result}"
                    )

                    if self.maa_result == "Success!":
                        logger.info(
                            f"用户: {user['user_id']} - MAA进程成功登录PRTS",
                        )
                        self.run_book["SignIn"] = True
                        await Config.send_json(
                            WebSocketMessage(
                                id=self.ws_id,
                                type="Update",
                                data={"log": "检测到MAA进程成功登录PRTS"},
                            ).model_dump()
                        )
                    else:
                        logger.error(
                            f"用户: {user['user_id']} - MAA未能正确登录到PRTS: {self.maa_result}"
                        )
                        await Config.send_json(
                            WebSocketMessage(
                                id=self.ws_id,
                                type="Update",
                                data={
                                    "log": f"{self.maa_result}\n正在中止相关程序\n请等待10s"
                                },
                            ).model_dump()
                        )
                        # 无命令行中止MAA与其子程序
                        logger.info(f"中止MAA进程：{self.maa_exe_path}")
                        await self.maa_process_manager.kill(if_force=True)
                        await System.kill_process(self.maa_exe_path)
                        self.if_open_emulator = True
                        await asyncio.sleep(10)

                    # 登录成功，结束循环
                    if self.run_book["SignIn"]:
                        break
                    # 登录失败，询问是否结束循环
                    else:

                        uid = str(uuid.uuid4())
                        await Config.send_json(
                            WebSocketMessage(
                                id=self.ws_id,
                                type="Message",
                                data={
                                    "message_id": uid,
                                    "type": "Question",
                                    "title": "操作提示",
                                    "message": "MAA未能正确登录到PRTS，是否重试？",
                                },
                            ).model_dump()
                        )
                        result = await self.get_message(uid)
                        if result.get("choice", False):
                            break

                # 登录成功，录入人工排查情况
                if self.run_book["SignIn"]:

                    uid = str(uuid.uuid4())
                    await Config.send_json(
                        WebSocketMessage(
                            id=self.ws_id,
                            type="Message",
                            data={
                                "message_id": uid,
                                "type": "Question",
                                "title": "操作提示",
                                "message": "请检查用户代理情况，该用户是否正确完成代理任务？",
                            },
                        ).model_dump()
                    )
                    result = await self.get_message(uid)
                    if result.get("choice", False):
                        self.run_book["PassCheck"] = True

                await self.result_record()

                await Config.send_json(
                    WebSocketMessage(
                        id=self.ws_id,
                        type="Update",
                        data={"user_list": self.user_list},
                    ).model_dump()
                )

        # 设置MAA模式
        elif self.mode == "设置脚本":

            # 配置MAA
            await self.set_maa(self.mode)
            # 创建MAA任务
            logger.info(f"启动MAA进程：{self.maa_exe_path}")
            await self.maa_process_manager.open_process(self.maa_exe_path, [], 0)
            # 记录当前时间
            self.log_start_time = datetime.now()

            # 监测MAA运行状态
            self.log_check_mode = "设置脚本"
            await self.maa_log_monitor.start(self.maa_log_path, self.log_start_time)
            self.wait_event.clear()
            await self.wait_event.wait()
            await self.maa_log_monitor.stop()

    async def result_record(self):
        """记录用户结果信息"""

        if self.mode == "自动代理":
            # 发送统计信息
            statistics = await Config.merge_statistic_info(self.user_logs_list)
            statistics["user_info"] = self.user_list[self.index]["name"]
            statistics["start_time"] = self.user_start_time.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            statistics["maa_result"] = (
                "代理任务全部完成"
                if (self.run_book["Annihilation"] and self.run_book["Routine"])
                else "代理任务未全部完成"
            )
            await self.push_notification(
                "统计信息",
                f"{self.current_date} | 用户 {self.user_list[self.index]['name']} 的自动代理统计报告",
                statistics,
            )

            if self.run_book["Annihilation"] and self.run_book["Routine"]:
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
                Notify.push_plyer(
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

            await Config.send_json(
                WebSocketMessage(
                    id=self.ws_id, type="Update", data={"user_list": self.user_list}
                ).model_dump()
            )

        elif self.mode == "人工排查":

            if self.run_book["SignIn"] and self.run_book["PassCheck"]:
                logger.info(
                    f"用户 {self.user_list[self.index]['user_id']} 通过人工排查"
                )
                await self.cur_user_data.set("Data", "IfPassCheck", True)
                self.user_list[self.index]["status"] = "完成"
            else:
                logger.info(
                    f"用户 {self.user_list[self.index]['user_id']} 未通过人工排查",
                )
                await self.cur_user_data.set("Data", "IfPassCheck", False)
                self.user_list[self.index]["status"] = "异常"

    async def final_task(self, task: asyncio.Task):
        """结束时的收尾工作"""

        logger.info("MAA 主任务已结束，开始执行后续操作")

        await Config.ScriptConfig[self.script_id].unlock()
        logger.success(f"已解锁脚本配置 {self.script_id}")

        # 结束各子任务
        await Broadcast.unsubscribe(self.message_queue)
        await self.maa_process_manager.kill(if_force=True)
        await System.kill_process(self.maa_exe_path)
        await self.emulator_process_manager.kill()
        await self.maa_log_monitor.stop()
        del self.maa_process_manager
        del self.emulator_process_manager
        del self.maa_log_monitor

        if self.check_result != "Success!":
            return self.check_result

        if self.mode == "人工排查":

            # 解除静默操作屏蔽
            logger.info("人工排查任务结束，解除静默操作屏蔽")
            if self.script_id in Config.if_ignore_silence:
                Config.if_ignore_silence.remove(self.script_id)

        if self.mode == "自动代理" and self.user_list[self.index]["status"] == "运行":

            if not self.maa_update_package:

                self.maa_result = "用户手动中止任务"

                # 保存运行日志以及统计信息
                if_six_star = await Config.save_maa_log(
                    Path.cwd()
                    / f"history/{self.curdate}/{self.user_list[self.index]['name']}/{self.log_start_time.strftime('%H-%M-%S')}.log",
                    self.maa_logs,
                    self.maa_result,
                )
                self.user_logs_list.append(
                    Path.cwd()
                    / f"history/{self.curdate}/{self.user_list[self.index]['name']}/{self.log_start_time.strftime('%H-%M-%S')}.json"
                )
                if if_six_star:
                    await self.push_notification(
                        "公招六星",
                        f"喜报：用户 {self.user_list[self.index]['name']} 公招出六星啦！",
                        {
                            "user_name": self.user_list[self.index]["name"],
                        },
                    )

            await self.result_record()

        elif self.mode == "人工排查" and self.user_list[self.index]["status"] == "运行":

            await self.result_record()

        # 导出结果
        if self.mode in ["自动代理", "人工排查"]:

            # 更新用户数据
            sc = Config.ScriptConfig[self.script_id]
            if isinstance(sc, MaaConfig):
                await sc.UserData.load(await self.user_config.toDict())
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
                f"任务开始时间：{result["start_time"]}，结束时间：{result["end_time"]}\n"
                f"已完成数：{result["completed_count"]}，未完成数：{result["uncompleted_count"]}\n\n"
            )
            if len(result["failed_user"]) > 0:
                result_text += (
                    f"{self.mode}未成功的用户：\n{"\n".join(result["failed_user"])}\n"
                )
            if len(result["waiting_user"]) > 0:
                result_text += f"\n未开始{self.mode}的用户：\n{"\n".join(result["waiting_user"])}\n"

            # 推送代理结果通知
            Notify.push_plyer(
                title.replace("报告", "已完成！"),
                f"已完成用户数：{len(over_user)}，未完成用户数：{len(error_user) + len(wait_user)}",
                f"已完成用户数：{len(over_user)}，未完成用户数：{len(error_user) + len(wait_user)}",
                10,
            )
            await self.push_notification("代理结果", title, result)

        elif self.mode == "设置脚本":
            (
                Path.cwd()
                / f"data/{self.script_id}/{self.user_id if self.user_id else 'Default'}/ConfigFile"
            ).mkdir(parents=True, exist_ok=True)
            shutil.copy(
                self.maa_set_path,
                (
                    Path.cwd()
                    / f"data/{self.script_id}/{self.user_id if self.user_id else 'Default'}/ConfigFile/gui.json"
                ),
            )

            result_text = ""

        # 复原 MAA 配置文件
        logger.info(f"复原 MAA 配置文件：{Path.cwd() / f'data/{self.script_id}/Temp'}")
        if (Path.cwd() / f"data/{self.script_id}/Temp/gui.json").exists():
            shutil.copy(
                Path.cwd() / f"data/{self.script_id}/Temp/gui.json", self.maa_set_path
            )
        shutil.rmtree(Path.cwd() / f"data/{self.script_id}/Temp")

        self.agree_bilibili(False)
        return result_text

    async def get_message(self, message_id: str):
        """获取当前任务的属性值"""

        logger.info(f"等待客户端回应消息：{message_id}")

        while True:
            message = await self.message_queue.get()
            if message.get("message_id") == message_id:
                self.message_queue.task_done()
                logger.success(f"收到客户端回应消息：{message_id}")
                return message
            else:
                self.message_queue.task_done()

    async def search_ADB_address(self) -> None:
        """搜索ADB实际地址"""

        await Config.send_json(
            WebSocketMessage(
                id=self.ws_id,
                type="Update",
                data={
                    "log": f"即将搜索ADB实际地址\n正在等待模拟器完成启动\n请等待{self.wait_time}s"
                },
            ).model_dump()
        )

        await asyncio.sleep(self.wait_time)

        if "-" in self.ADB_address:
            ADB_ip = f"{self.ADB_address.split("-")[0]}-"
            ADB_port = int(self.ADB_address.split("-")[1])

        elif ":" in self.ADB_address:
            ADB_ip = f"{self.ADB_address.split(':')[0]}:"
            ADB_port = int(self.ADB_address.split(":")[1])

        logger.info(
            f"正在搜索ADB实际地址，ADB前缀：{ADB_ip}，初始端口：{ADB_port}，搜索范围：{self.port_range}"
        )

        for port in self.port_range:

            ADB_address = f"{ADB_ip}{ADB_port + port}"

            # 尝试通过ADB连接到指定地址
            connect_result = subprocess.run(
                [self.ADB_path, "connect", ADB_address],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            if "connected" in connect_result.stdout:

                # 检查连接状态
                devices_result = subprocess.run(
                    [self.ADB_path, "devices"],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                if ADB_address in devices_result.stdout:

                    logger.info(f"ADB实际地址：{ADB_address}")

                    # 断开连接
                    logger.info(f"断开ADB连接：{ADB_address}")
                    subprocess.run(
                        [self.ADB_path, "disconnect", ADB_address],
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )

                    self.ADB_address = ADB_address

                    # 覆写当前ADB地址
                    logger.info(f"开始使用实际 ADB 地址覆写：{self.ADB_address}")
                    await self.maa_process_manager.kill(if_force=True)
                    await System.kill_process(self.maa_exe_path)
                    with self.maa_set_path.open(mode="r", encoding="utf-8") as f:
                        data = json.load(f)
                    data["Configurations"]["Default"][
                        "Connect.Address"
                    ] = self.ADB_address
                    data["Configurations"]["Default"]["Start.EmulatorWaitSeconds"] = "0"
                    with self.maa_set_path.open(mode="w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=4)

                    return None

                else:
                    logger.info(f"无法连接到ADB地址：{ADB_address}")
            else:
                logger.info(f"无法连接到ADB地址：{ADB_address}")

    async def check_maa_log(self, log_content: List[str]) -> None:
        """获取MAA日志并检查以判断MAA程序运行状态"""

        self.maa_logs = log_content
        log = "".join(log_content)

        # 更新MAA日志
        if await self.maa_process_manager.is_running():

            await Config.send_json(
                WebSocketMessage(
                    id=self.ws_id, type="Update", data={"log": log}
                ).model_dump()
            )

        if self.mode == "自动代理":

            # 获取最近一条日志的时间
            latest_time = self.log_start_time
            for _ in self.maa_logs[::-1]:
                try:
                    if "如果长时间无进一步日志更新，可能需要手动干预。" in _:
                        continue
                    latest_time = datetime.strptime(_[1:20], "%Y-%m-%d %H:%M:%S")
                    break
                except ValueError:
                    pass

            logger.info(f"MAA最近一条日志时间：{latest_time}")

            if self.log_check_mode == "Annihilation" and "任务出错: 刷理智" in log:
                self.weekly_annihilation_limit_reached = True
            else:
                self.weekly_annihilation_limit_reached = False

            if "任务出错: StartUp" in log or "任务出错: 开始唤醒" in log:
                self.maa_result = "MAA未能正确登录PRTS"

            elif "任务已全部完成！" in log:

                if "完成任务: StartUp" in log or "完成任务: 开始唤醒" in log:
                    self.task_dict["WakeUp"] = "False"
                if "完成任务: Recruit" in log or "完成任务: 自动公招" in log:
                    self.task_dict["Recruiting"] = "False"
                if "完成任务: Infrast" in log or "完成任务: 基建换班" in log:
                    self.task_dict["Base"] = "False"
                if (
                    "完成任务: Fight" in log
                    or "完成任务: 刷理智" in log
                    or (
                        self.log_check_mode == "Annihilation"
                        and "任务出错: 刷理智" in log
                    )
                ):
                    self.task_dict["Combat"] = "False"
                if "完成任务: Mall" in log or "完成任务: 获取信用及购物" in log:
                    self.task_dict["Mall"] = "False"
                if "完成任务: Award" in log or "完成任务: 领取奖励" in log:
                    self.task_dict["Mission"] = "False"
                if "完成任务: Roguelike" in log or "完成任务: 自动肉鸽" in log:
                    self.task_dict["AutoRoguelike"] = "False"
                if "完成任务: Reclamation" in log or "完成任务: 生息演算" in log:
                    self.task_dict["Reclamation"] = "False"

                if all(v == "False" for v in self.task_dict.values()):
                    self.maa_result = "Success!"
                else:
                    self.maa_result = "MAA部分任务执行失败"

            elif "请 ｢检查连接设置｣ → ｢尝试重启模拟器与 ADB｣ → ｢重启电脑｣" in log:
                self.maa_result = "MAA的ADB连接异常"

            elif "未检测到任何模拟器" in log:
                self.maa_result = "MAA未检测到任何模拟器"

            elif "已停止" in log:
                self.maa_result = "MAA在完成任务前中止"

            elif (
                "MaaAssistantArknights GUI exited" in log
                or not await self.maa_process_manager.is_running()
            ):
                self.maa_result = "MAA在完成任务前退出"

            elif datetime.now() - latest_time > timedelta(
                minutes=self.script_config.get("Run", f"{self.log_check_mode}TimeLimit")
            ):
                self.maa_result = "MAA进程超时"

            else:
                self.maa_result = "Wait"

        elif self.mode == "人工排查":
            if "完成任务: StartUp" in log or "完成任务: 开始唤醒" in log:
                self.maa_result = "Success!"
            elif "请 ｢检查连接设置｣ → ｢尝试重启模拟器与 ADB｣ → ｢重启电脑｣" in log:
                self.maa_result = "MAA的ADB连接异常"
            elif "未检测到任何模拟器" in log:
                self.maa_result = "MAA未检测到任何模拟器"
            elif "已停止" in log:
                self.maa_result = "MAA在完成任务前中止"
            elif (
                "MaaAssistantArknights GUI exited" in log
                or not await self.maa_process_manager.is_running()
            ):
                self.maa_result = "MAA在完成任务前退出"
            else:
                self.maa_result = "Wait"

        elif self.mode == "设置脚本":
            if (
                "MaaAssistantArknights GUI exited" in log
                or not await self.maa_process_manager.is_running()
            ):
                self.maa_result = "Success!"
            else:
                self.maa_result = "Wait"

        logger.debug(f"MAA 日志分析结果：{self.maa_result}")

        if self.maa_result != "Wait":

            logger.info(f"MAA 任务结果：{self.maa_result}，日志锁已释放")
            self.wait_event.set()

    async def set_maa(self, mode: str) -> dict:
        """配置MAA运行参数"""
        logger.info(f"开始配置MAA运行参数: {mode}")

        if self.mode != "设置脚本" and mode != "Update":

            if self.cur_user_data.get("Info", "Server") == "Bilibili":
                self.agree_bilibili(True)
            else:
                self.agree_bilibili(False)

        # 配置MAA前关闭可能未正常退出的MAA进程
        await self.maa_process_manager.kill(if_force=True)
        await System.kill_process(self.maa_exe_path)

        # 预导入MAA配置文件
        if self.mode in ["自动代理", "人工排查"]:
            if self.cur_user_data.get("Info", "Mode") == "简洁":
                shutil.copy(
                    (Path.cwd() / f"data/{self.script_id}/Default/ConfigFile/gui.json"),
                    self.maa_set_path,
                )
            elif self.cur_user_data.get("Info", "Mode") == "详细":
                shutil.copy(
                    (
                        Path.cwd()
                        / f"data/{self.script_id}/{self.user_id}/ConfigFile/gui.json"
                    ),
                    self.maa_set_path,
                )
        elif self.mode == "设置脚本":
            if (
                self.user_id is None
                and (
                    Path.cwd() / f"data/{self.script_id}/Default/ConfigFile/gui.json"
                ).exists()
            ):
                shutil.copy(
                    (Path.cwd() / f"data/{self.script_id}/Default/ConfigFile/gui.json"),
                    self.maa_set_path,
                )
            elif self.user_id is not None:
                if (
                    Path.cwd()
                    / f"data/{self.script_id}/{self.user_id}/ConfigFile/gui.json"
                ).exists():
                    shutil.copy(
                        (
                            Path.cwd()
                            / f"data/{self.script_id}/{self.user_id}/ConfigFile/gui.json"
                        ),
                        self.maa_set_path,
                    )
                else:
                    shutil.copy(
                        (
                            Path.cwd()
                            / f"data/{self.script_id}/Default/ConfigFile/gui.json"
                        ),
                        self.maa_set_path,
                    )

        with self.maa_set_path.open(mode="r", encoding="utf-8") as f:
            data = json.load(f)

        # 切换配置
        if data["Current"] != "Default":

            data["Configurations"]["Default"] = data["Configurations"][data["Current"]]
            data["Current"] = "Default"

        # 时间设置
        for i in range(1, 9):
            data["Global"][f"Timer.Timer{i}"] = "False"

        # 自动代理配置
        if self.mode == "自动代理" and mode in ["Annihilation", "Routine"]:

            if (self.index == len(self.user_list) - 1) or (
                self.user_config[
                    uuid.UUID(self.user_list[self.index + 1]["user_id"])
                ].get("Info", "Mode")
                == "详细"
            ):
                data["Configurations"]["Default"][
                    "MainFunction.PostActions"
                ] = "12"  # 完成后退出MAA和模拟器
            else:

                data["Configurations"]["Default"]["MainFunction.PostActions"] = (
                    METHOD_BOOK[self.script_config.get("Run", "TaskTransitionMethod")]
                )  # 完成后行为

            data["Configurations"]["Default"][
                "Start.RunDirectly"
            ] = "True"  # 启动MAA后直接运行
            data["Configurations"]["Default"]["Start.OpenEmulatorAfterLaunch"] = str(
                self.if_open_emulator
            )  # 启动MAA后自动开启模拟器

            data["Global"][
                "VersionUpdate.ScheduledUpdateCheck"
            ] = "False"  # 定时检查更新
            data["Global"][
                "VersionUpdate.AutoDownloadUpdatePackage"
            ] = "True"  # 自动下载更新包
            data["Global"][
                "VersionUpdate.AutoInstallUpdatePackage"
            ] = "False"  # 自动安装更新包

            if Config.get("Function", "IfSilence"):
                data["Global"]["Start.MinimizeDirectly"] = "True"  # 启动MAA后直接最小化
                data["Global"]["GUI.UseTray"] = "True"  # 显示托盘图标
                data["Global"]["GUI.MinimizeToTray"] = "True"  # 最小化时隐藏至托盘

            # 客户端类型
            data["Configurations"]["Default"]["Start.ClientType"] = (
                self.cur_user_data.get("Info", "Server")
            )

            # 账号切换
            if self.cur_user_data.get("Info", "Server") == "Official":
                data["Configurations"]["Default"]["Start.AccountName"] = (
                    f"{self.cur_user_data.get("Info", "Id")[:3]}****{self.cur_user_data.get("Info", "Id")[7:]}"
                    if len(self.cur_user_data.get("Info", "Id")) == 11
                    else self.cur_user_data.get("Info", "Id")
                )
            elif self.cur_user_data.get("Info", "Server") == "Bilibili":
                data["Configurations"]["Default"]["Start.AccountName"] = (
                    self.cur_user_data.get("Info", "Id")
                )

            # 按预设设定任务
            data["Configurations"]["Default"][
                "TaskQueue.WakeUp.IsChecked"
            ] = "True"  # 开始唤醒
            data["Configurations"]["Default"]["TaskQueue.Recruiting.IsChecked"] = (
                self.task_dict["Recruiting"]
            )  # 自动公招
            data["Configurations"]["Default"]["TaskQueue.Base.IsChecked"] = (
                self.task_dict["Base"]
            )  # 基建换班
            data["Configurations"]["Default"]["TaskQueue.Combat.IsChecked"] = (
                self.task_dict["Combat"]
            )  # 刷理智
            data["Configurations"]["Default"]["TaskQueue.Mission.IsChecked"] = (
                self.task_dict["Mission"]
            )  # 领取奖励
            data["Configurations"]["Default"]["TaskQueue.Mall.IsChecked"] = (
                self.task_dict["Mall"]
            )  # 获取信用及购物
            data["Configurations"]["Default"]["TaskQueue.AutoRoguelike.IsChecked"] = (
                self.task_dict["AutoRoguelike"]
            )  # 自动肉鸽
            data["Configurations"]["Default"]["TaskQueue.Reclamation.IsChecked"] = (
                self.task_dict["Reclamation"]
            )  # 生息演算

            # 整理任务顺序
            if (
                mode == "Annihilation"
                or self.cur_user_data.get("Info", "Mode") == "简洁"
            ):

                data["Configurations"]["Default"]["TaskQueue.Order.WakeUp"] = "0"
                data["Configurations"]["Default"]["TaskQueue.Order.Recruiting"] = "1"
                data["Configurations"]["Default"]["TaskQueue.Order.Base"] = "2"
                data["Configurations"]["Default"]["TaskQueue.Order.Combat"] = "3"
                data["Configurations"]["Default"]["TaskQueue.Order.Mall"] = "4"
                data["Configurations"]["Default"]["TaskQueue.Order.Mission"] = "5"
                data["Configurations"]["Default"]["TaskQueue.Order.AutoRoguelike"] = "6"
                data["Configurations"]["Default"]["TaskQueue.Order.Reclamation"] = "7"

            if isinstance(self.cur_user_data, MaaUserConfig):
                try:
                    plan_data = self.cur_user_data.get_plan_info()
                except Exception as e:
                    logger.error(
                        f"获取用户 {self.user_list[self.index]['user_id']} 的代理计划信息失败: {e}"
                    )
                    plan_data = {}
            else:
                plan_data = {}

            data["Configurations"]["Default"]["MainFunction.UseMedicine"] = (
                "False" if plan_data.get("MedicineNumb", 0) == 0 else "True"
            )  # 吃理智药
            data["Configurations"]["Default"]["MainFunction.UseMedicine.Quantity"] = (
                str(plan_data.get("MedicineNumb", 0))
            )  # 吃理智药数量
            data["Configurations"]["Default"]["MainFunction.Series.Quantity"] = (
                plan_data.get("SeriesNumb", "0")
            )  # 连战次数

            if mode == "Annihilation":

                data["Configurations"]["Default"][
                    "MainFunction.Stage1"
                ] = "Annihilation"  # 主关卡
                data["Configurations"]["Default"][
                    "MainFunction.Stage2"
                ] = ""  # 备选关卡1
                data["Configurations"]["Default"][
                    "MainFunction.Stage3"
                ] = ""  # 备选关卡2
                data["Configurations"]["Default"][
                    "Fight.RemainingSanityStage"
                ] = ""  # 剩余理智关卡
                data["Configurations"]["Default"][
                    "MainFunction.Series.Quantity"
                ] = "1"  # 连战次数
                data["Configurations"]["Default"][
                    "MainFunction.Annihilation.UseCustom"
                ] = "True"  #   自定义剿灭关卡
                data["Configurations"]["Default"]["MainFunction.Annihilation.Stage"] = (
                    self.cur_user_data.get("Info", "Annihilation")
                )  #   自定义剿灭关卡号
                data["Configurations"]["Default"][
                    "Penguin.IsDrGrandet"
                ] = "False"  # 博朗台模式
                data["Configurations"]["Default"][
                    "GUI.CustomStageCode"
                ] = "True"  # 手动输入关卡名
                data["Configurations"]["Default"][
                    "GUI.UseAlternateStage"
                ] = "False"  # 使用备选关卡
                data["Configurations"]["Default"][
                    "Fight.UseRemainingSanityStage"
                ] = "False"  # 使用剩余理智
                data["Configurations"]["Default"][
                    "Fight.UseExpiringMedicine"
                ] = "True"  # 无限吃48小时内过期的理智药
                data["Configurations"]["Default"][
                    "GUI.HideSeries"
                ] = "False"  # 隐藏连战次数

            elif mode == "Routine":

                data["Configurations"]["Default"]["MainFunction.Stage1"] = (
                    plan_data.get("Stage") if plan_data.get("Stage", "-") != "-" else ""
                )  # 主关卡
                data["Configurations"]["Default"]["MainFunction.Stage2"] = (
                    plan_data.get("Stage_1")
                    if plan_data.get("Stage_1", "-") != "-"
                    else ""
                )  # 备选关卡1
                data["Configurations"]["Default"]["MainFunction.Stage3"] = (
                    plan_data.get("Stage_2")
                    if plan_data.get("Stage_2", "-") != "-"
                    else ""
                )  # 备选关卡2
                data["Configurations"]["Default"]["MainFunction.Stage4"] = (
                    plan_data.get("Stage_3")
                    if plan_data.get("Stage_3", "-") != "-"
                    else ""
                )  # 备选关卡3
                data["Configurations"]["Default"]["Fight.RemainingSanityStage"] = (
                    plan_data.get("Stage_Remain")
                    if plan_data.get("Stage_Remain", "-") != "-"
                    else ""
                )  # 剩余理智关卡
                data["Configurations"]["Default"][
                    "GUI.UseAlternateStage"
                ] = "True"  # 备选关卡
                data["Configurations"]["Default"]["Fight.UseRemainingSanityStage"] = (
                    "True" if plan_data.get("Stage_Remain", "-") != "-" else "False"
                )  # 使用剩余理智

                if self.cur_user_data.get("Info", "Mode") == "简洁":

                    data["Configurations"]["Default"][
                        "Penguin.IsDrGrandet"
                    ] = "False"  # 博朗台模式
                    data["Configurations"]["Default"][
                        "GUI.CustomStageCode"
                    ] = "True"  # 手动输入关卡名
                    data["Configurations"]["Default"][
                        "Fight.UseExpiringMedicine"
                    ] = "True"  # 无限吃48小时内过期的理智药
                    # 自定义基建配置
                    if self.cur_user_data.get("Info", "InfrastMode") == "Custom":

                        if (
                            Path.cwd()
                            / f"data/{self.script_id}/{self.user_id}/Infrastructure/infrastructure.json"
                        ).exists():

                            data["Configurations"]["Default"][
                                "Infrast.InfrastMode"
                            ] = "Custom"  # 基建模式
                            data["Configurations"]["Default"][
                                "Infrast.CustomInfrastPlanIndex"
                            ] = self.cur_user_data.get(
                                "Data", "CustomInfrastPlanIndex"
                            )  # 自定义基建配置索引
                            data["Configurations"]["Default"][
                                "Infrast.DefaultInfrast"
                            ] = "user_defined"  # 内置配置
                            data["Configurations"]["Default"][
                                "Infrast.IsCustomInfrastFileReadOnly"
                            ] = "False"  # 自定义基建配置文件只读
                            data["Configurations"]["Default"][
                                "Infrast.CustomInfrastFile"
                            ] = str(
                                Path.cwd()
                                / f"data/{self.script_id}/{self.user_id}/Infrastructure/infrastructure.json"
                            )  # 自定义基建配置文件地址
                        else:
                            logger.warning(
                                f"未选择用户 {self.cur_user_data.get('Info', 'Name')} 的自定义基建配置文件"
                            )
                            await Config.send_json(
                                WebSocketMessage(
                                    id=self.ws_id,
                                    type="Info",
                                    data={
                                        "warning": f"未选择用户 {self.cur_user_data.get('Info', 'Name')} 的自定义基建配置文件"
                                    },
                                ).model_dump()
                            )
                            data["Configurations"]["Default"][
                                "Infrast.CustomInfrastEnabled"
                            ] = "Normal"  # 基建模式
                    else:
                        data["Configurations"]["Default"]["Infrast.InfrastMode"] = (
                            self.cur_user_data.get("Info", "InfrastMode")
                        )  # 基建模式

                elif self.cur_user_data.get("Info", "Mode") == "详细":

                    # 基建模式
                    if (
                        data["Configurations"]["Default"]["Infrast.InfrastMode"]
                        == "Custom"
                    ):
                        data["Configurations"]["Default"][
                            "Infrast.CustomInfrastPlanIndex"
                        ] = self.cur_user_data.get(
                            "Data", "CustomInfrastPlanIndex"
                        )  # 自定义基建配置索引

        # 人工排查配置
        elif self.mode == "人工排查" and self.cur_user_data is not None:

            data["Configurations"]["Default"][
                "MainFunction.PostActions"
            ] = "8"  # 完成后退出MAA
            data["Configurations"]["Default"][
                "Start.RunDirectly"
            ] = "True"  # 启动MAA后直接运行
            data["Global"]["Start.MinimizeDirectly"] = "True"  # 启动MAA后直接最小化
            data["Global"]["GUI.UseTray"] = "True"  # 显示托盘图标
            data["Global"]["GUI.MinimizeToTray"] = "True"  # 最小化时隐藏至托盘
            data["Configurations"]["Default"]["Start.OpenEmulatorAfterLaunch"] = str(
                self.if_open_emulator
            )  # 启动MAA后自动开启模拟器
            data["Global"][
                "VersionUpdate.ScheduledUpdateCheck"
            ] = "False"  # 定时检查更新
            data["Global"][
                "VersionUpdate.AutoDownloadUpdatePackage"
            ] = "False"  # 自动下载更新包
            data["Global"][
                "VersionUpdate.AutoInstallUpdatePackage"
            ] = "False"  # 自动安装更新包

            # 客户端类型
            data["Configurations"]["Default"]["Start.ClientType"] = (
                self.cur_user_data.get("Info", "Server")
            )

            # 账号切换
            if self.cur_user_data.get("Info", "Server") == "Official":
                data["Configurations"]["Default"]["Start.AccountName"] = (
                    f"{self.cur_user_data.get('Info', 'Id')[:3]}****{self.cur_user_data.get('Info', 'Id')[7:]}"
                    if len(self.cur_user_data.get("Info", "Id")) == 11
                    else self.cur_user_data.get("Info", "Id")
                )
            elif self.cur_user_data.get("Info", "Server") == "Bilibili":
                data["Configurations"]["Default"]["Start.AccountName"] = (
                    self.cur_user_data.get("Info", "Id")
                )

            data["Configurations"]["Default"][
                "TaskQueue.WakeUp.IsChecked"
            ] = "True"  # 开始唤醒
            data["Configurations"]["Default"][
                "TaskQueue.Recruiting.IsChecked"
            ] = "False"  # 自动公招
            data["Configurations"]["Default"][
                "TaskQueue.Base.IsChecked"
            ] = "False"  # 基建换班
            data["Configurations"]["Default"][
                "TaskQueue.Combat.IsChecked"
            ] = "False"  # 刷理智
            data["Configurations"]["Default"][
                "TaskQueue.Mission.IsChecked"
            ] = "False"  # 领取奖励
            data["Configurations"]["Default"][
                "TaskQueue.Mall.IsChecked"
            ] = "False"  # 获取信用及购物
            data["Configurations"]["Default"][
                "TaskQueue.AutoRoguelike.IsChecked"
            ] = "False"  # 自动肉鸽
            data["Configurations"]["Default"][
                "TaskQueue.Reclamation.IsChecked"
            ] = "False"  # 生息演算

        # 设置脚本配置
        elif self.mode == "设置脚本":

            data["Configurations"]["Default"][
                "MainFunction.PostActions"
            ] = "0"  # 完成后无动作
            data["Configurations"]["Default"][
                "Start.RunDirectly"
            ] = "False"  # 启动MAA后直接运行
            data["Configurations"]["Default"][
                "Start.OpenEmulatorAfterLaunch"
            ] = "False"  # 启动MAA后自动开启模拟器
            data["Global"][
                "VersionUpdate.ScheduledUpdateCheck"
            ] = "False"  # 定时检查更新
            data["Global"][
                "VersionUpdate.AutoDownloadUpdatePackage"
            ] = "False"  # 自动下载更新包
            data["Global"][
                "VersionUpdate.AutoInstallUpdatePackage"
            ] = "False"  # 自动安装更新包

            if Config.get("Function", "IfSilence"):
                data["Global"][
                    "Start.MinimizeDirectly"
                ] = "False"  # 启动MAA后直接最小化

            data["Configurations"]["Default"][
                "TaskQueue.WakeUp.IsChecked"
            ] = "False"  # 开始唤醒
            data["Configurations"]["Default"][
                "TaskQueue.Recruiting.IsChecked"
            ] = "False"  # 自动公招
            data["Configurations"]["Default"][
                "TaskQueue.Base.IsChecked"
            ] = "False"  # 基建换班
            data["Configurations"]["Default"][
                "TaskQueue.Combat.IsChecked"
            ] = "False"  # 刷理智
            data["Configurations"]["Default"][
                "TaskQueue.Mission.IsChecked"
            ] = "False"  # 领取奖励
            data["Configurations"]["Default"][
                "TaskQueue.Mall.IsChecked"
            ] = "False"  # 获取信用及购物
            data["Configurations"]["Default"][
                "TaskQueue.AutoRoguelike.IsChecked"
            ] = "False"  # 自动肉鸽
            data["Configurations"]["Default"][
                "TaskQueue.Reclamation.IsChecked"
            ] = "False"  # 生息演算

        elif mode == "Update":

            data["Configurations"]["Default"][
                "MainFunction.PostActions"
            ] = "0"  # 完成后无动作
            data["Configurations"]["Default"][
                "Start.RunDirectly"
            ] = "False"  # 启动MAA后直接运行
            data["Configurations"]["Default"][
                "Start.OpenEmulatorAfterLaunch"
            ] = "False"  # 启动MAA后自动开启模拟器
            data["Global"]["Start.MinimizeDirectly"] = "True"  # 启动MAA后直接最小化
            data["Global"]["GUI.UseTray"] = "True"  # 显示托盘图标
            data["Global"]["GUI.MinimizeToTray"] = "True"  # 最小化时隐藏至托盘
            data["Global"][
                "VersionUpdate.package"
            ] = self.maa_update_package  # 更新包路径

            data["Global"][
                "VersionUpdate.ScheduledUpdateCheck"
            ] = "False"  # 定时检查更新
            data["Global"][
                "VersionUpdate.AutoDownloadUpdatePackage"
            ] = "False"  # 自动下载更新包
            data["Global"][
                "VersionUpdate.AutoInstallUpdatePackage"
            ] = "True"  # 自动安装更新包
            data["Configurations"]["Default"][
                "TaskQueue.WakeUp.IsChecked"
            ] = "False"  # 开始唤醒
            data["Configurations"]["Default"][
                "TaskQueue.Recruiting.IsChecked"
            ] = "False"  # 自动公招
            data["Configurations"]["Default"][
                "TaskQueue.Base.IsChecked"
            ] = "False"  # 基建换班
            data["Configurations"]["Default"][
                "TaskQueue.Combat.IsChecked"
            ] = "False"  # 刷理智
            data["Configurations"]["Default"][
                "TaskQueue.Mission.IsChecked"
            ] = "False"  # 领取奖励
            data["Configurations"]["Default"][
                "TaskQueue.Mall.IsChecked"
            ] = "False"  # 获取信用及购物
            data["Configurations"]["Default"][
                "TaskQueue.AutoRoguelike.IsChecked"
            ] = "False"  # 自动肉鸽
            data["Configurations"]["Default"][
                "TaskQueue.Reclamation.IsChecked"
            ] = "False"  # 生息演算

        # 启动模拟器仅生效一次
        if self.mode != "设置脚本" and mode != "Update" and self.if_open_emulator:
            self.if_open_emulator = False

        # 覆写配置文件
        with self.maa_set_path.open(mode="w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        logger.success(f"MAA运行参数配置完成: {mode}")

        return data

    def agree_bilibili(self, if_agree):
        """向MAA写入Bilibili协议相关任务"""
        logger.info(f"Bilibili协议相关任务状态: {'启用' if if_agree else '禁用'}")

        with self.maa_tasks_path.open(mode="r", encoding="utf-8") as f:
            data = json.load(f)

        if if_agree and Config.get("Function", "IfAgreeBilibili"):
            data["BilibiliAgreement_AUTO"] = {
                "algorithm": "OcrDetect",
                "action": "ClickSelf",
                "text": ["同意"],
                "maxTimes": 5,
                "Doc": "关闭B服用户协议",
                "next": ["StartUpThemes#next"],
            }
            if "BilibiliAgreement_AUTO" not in data["StartUpThemes"]["next"]:
                data["StartUpThemes"]["next"].insert(0, "BilibiliAgreement_AUTO")
        else:
            if "BilibiliAgreement_AUTO" in data:
                data.pop("BilibiliAgreement_AUTO")
            if "BilibiliAgreement_AUTO" in data["StartUpThemes"]["next"]:
                data["StartUpThemes"]["next"].remove("BilibiliAgreement_AUTO")

        with self.maa_tasks_path.open(mode="w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    async def push_notification(self, mode: str, title: str, message) -> None:
        """通过所有渠道推送通知"""
        logger.info(f"开始推送通知，模式：{mode}，标题：{title}")

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
                f"任务开始时间：{message['start_time']}，结束时间：{message['end_time']}\n"
                f"已完成数：{message['completed_count']}，未完成数：{message['uncompleted_count']}\n\n"
            )

            if len(message["failed_user"]) > 0:
                message_text += f"{self.mode[2:4]}未成功的用户：\n{"\n".join(message["failed_user"])}\n"
            if len(message["waiting_user"]) > 0:
                message_text += f"\n未开始{self.mode[2:4]}的用户：\n{"\n".join(message["waiting_user"])}\n"

            # 生成HTML通知内容
            message["failed_user"] = "、".join(message["failed_user"])
            message["waiting_user"] = "、".join(message["waiting_user"])

            template = env.get_template("MAA_result.html")
            message_html = template.render(message)

            # ServerChan的换行是两个换行符。故而将\n替换为\n\n
            serverchan_message = message_text.replace("\n", "\n\n")

            # 发送全局通知

            if Config.get("Notify", "IfSendMail"):
                Notify.send_mail(
                    "网页", title, message_html, Config.get("Notify", "ToAddress")
                )

            if Config.get("Notify", "IfServerChan"):
                Notify.ServerChanPush(
                    title,
                    f"{serverchan_message}\n\nAUTO_MAA 敬上",
                    Config.get("Notify", "ServerChanKey"),
                )

            if Config.get("Notify", "IfCompanyWebHookBot"):
                Notify.WebHookPush(
                    title,
                    f"{message_text}\n\nAUTO_MAA 敬上",
                    Config.get("Notify", "CompanyWebHookBotUrl"),
                )

        elif mode == "统计信息":

            # 生成文本通知内容
            formatted = []
            if "drop_statistics" in message:
                for stage, items in message["drop_statistics"].items():
                    formatted.append(f"掉落统计（{stage}）:")
                    for item, quantity in items.items():
                        formatted.append(f"  {item}: {quantity}")
            drop_text = "\n".join(formatted)

            formatted = ["招募统计:"]
            if "recruit_statistics" in message:
                for star, count in message["recruit_statistics"].items():
                    formatted.append(f"  {star}: {count}")
            recruit_text = "\n".join(formatted)

            message_text = (
                f"开始时间: {message['start_time']}\n"
                f"结束时间: {message['end_time']}\n"
                f"MAA执行结果: {message['maa_result']}\n\n"
                f"{recruit_text}\n"
                f"{drop_text}"
            )

            # 生成HTML通知内容
            template = env.get_template("MAA_statistics.html")
            message_html = template.render(message)

            # ServerChan的换行是两个换行符。故而将\n替换为\n\n
            serverchan_message = message_text.replace("\n", "\n\n")

            # 发送全局通知
            if Config.get("Notify", "IfSendStatistic"):

                if Config.get("Notify", "IfSendMail"):
                    Notify.send_mail(
                        "网页", title, message_html, Config.get("Notify", "ToAddress")
                    )

                if Config.get("Notify", "IfServerChan"):
                    Notify.ServerChanPush(
                        title,
                        f"{serverchan_message}\n\nAUTO_MAA 敬上",
                        Config.get("Notify", "ServerChanKey"),
                    )

                if Config.get("Notify", "IfCompanyWebHookBot"):
                    Notify.WebHookPush(
                        title,
                        f"{message_text}\n\nAUTO_MAA 敬上",
                        Config.get("Notify", "CompanyWebHookBotUrl"),
                    )

            # 发送用户单独通知
            if self.cur_user_data.get("Notify", "Enabled") and self.cur_user_data.get(
                "Notify", "IfSendStatistic"
            ):

                # 发送邮件通知
                if self.cur_user_data.get("Notify", "IfSendMail"):
                    if self.cur_user_data.get("Notify", "ToAddress"):
                        Notify.send_mail(
                            "网页",
                            title,
                            message_html,
                            self.cur_user_data.get("Notify", "ToAddress"),
                        )
                    else:
                        logger.error(f"用户邮箱地址为空，无法发送用户单独的邮件通知")

                # 发送ServerChan通知
                if self.cur_user_data.get("Notify", "IfServerChan"):
                    if self.cur_user_data.get("Notify", "ServerChanKey"):
                        Notify.ServerChanPush(
                            title,
                            f"{serverchan_message}\n\nAUTO_MAA 敬上",
                            self.cur_user_data.get("Notify", "ServerChanKey"),
                        )
                    else:
                        logger.error(
                            "用户ServerChan密钥为空，无法发送用户单独的ServerChan通知"
                        )

                # 推送CompanyWebHookBot通知
                if self.cur_user_data.get("Notify", "IfCompanyWebHookBot"):
                    if self.cur_user_data.get("Notify", "CompanyWebHookBotUrl"):
                        Notify.WebHookPush(
                            title,
                            f"{message_text}\n\nAUTO_MAA 敬上",
                            self.cur_user_data.get("Notify", "CompanyWebHookBotUrl"),
                        )
                    else:
                        logger.error(
                            f"用户CompanyWebHookBot密钥为空，无法发送用户单独的CompanyWebHookBot通知"
                        )

        elif mode == "公招六星":

            # 生成HTML通知内容
            template = env.get_template("MAA_six_star.html")

            message_html = template.render(message)

            # 发送全局通知
            if Config.get("Notify", "IfSendSixStar"):

                if Config.get("Notify", "IfSendMail"):
                    Notify.send_mail(
                        "网页", title, message_html, Config.get("Notify", "ToAddress")
                    )

                if Config.get("Notify", "IfServerChan"):
                    Notify.ServerChanPush(
                        title,
                        "好羡慕~\n\nAUTO_MAA 敬上",
                        Config.get("Notify", "ServerChanKey"),
                    )

                if Config.get("Notify", "IfCompanyWebHookBot"):
                    Notify.WebHookPush(
                        title,
                        "好羡慕~\n\nAUTO_MAA 敬上",
                        Config.get("Notify", "CompanyWebHookBotUrl"),
                    )
                    Notify.CompanyWebHookBotPushImage(
                        Path.cwd() / "res/images/notification/six_star.png",
                        Config.get("Notify", "CompanyWebHookBotUrl"),
                    )

            # 发送用户单独通知
            if self.cur_user_data.get("Notify", "Enabled") and self.cur_user_data.get(
                "Notify", "IfSendSixStar"
            ):

                # 发送邮件通知
                if self.cur_user_data.get("Notify", "IfSendMail"):
                    if self.cur_user_data.get("Notify", "ToAddress"):
                        Notify.send_mail(
                            "网页",
                            title,
                            message_html,
                            self.cur_user_data.get("Notify", "ToAddress"),
                        )
                    else:
                        logger.error("用户邮箱地址为空，无法发送用户单独的邮件通知")

                # 发送ServerChan通知
                if self.cur_user_data.get("Notify", "IfServerChan"):

                    if self.cur_user_data.get("Notify", "ServerChanKey"):
                        Notify.ServerChanPush(
                            title,
                            "好羡慕~\n\nAUTO_MAA 敬上",
                            self.cur_user_data.get("Notify", "ServerChanKey"),
                        )
                    else:
                        logger.error(
                            "用户ServerChan密钥为空，无法发送用户单独的ServerChan通知"
                        )

                # 推送CompanyWebHookBot通知
                if self.cur_user_data.get("Notify", "IfCompanyWebHookBot"):
                    if self.cur_user_data.get("Notify", "CompanyWebHookBotUrl"):
                        Notify.WebHookPush(
                            title,
                            "好羡慕~\n\nAUTO_MAA 敬上",
                            self.cur_user_data.get("Notify", "CompanyWebHookBotUrl"),
                        )
                        Notify.CompanyWebHookBotPushImage(
                            Path.cwd() / "res/images/notification/six_star.png",
                            self.cur_user_data.get("Notify", "CompanyWebHookBotUrl"),
                        )
                    else:
                        logger.error(
                            "用户CompanyWebHookBot密钥为空，无法发送用户单独的CompanyWebHookBot通知"
                        )

        return None
