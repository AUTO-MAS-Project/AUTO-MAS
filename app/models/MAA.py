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

"""
AUTO_MAA
MAA功能组件
v4.3
作者：DLmaster_361
"""

from loguru import logger
from PySide6.QtCore import QObject, Signal, QEventLoop, QFileSystemWatcher, QTimer
import json
import subprocess
import shutil
import time
import re
import win32com.client
from datetime import datetime, timedelta
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from typing import Union, List, Dict

from app.core import Config, MaaConfig, MaaUserConfig
from app.services import Notify, System


class MaaManager(QObject):
    """MAA控制器"""

    check_maa_version = Signal(str)
    question = Signal(str, str)
    question_response = Signal(bool)
    update_user_info = Signal(str, dict)
    push_info_bar = Signal(str, str, str, int)
    create_user_list = Signal(list)
    update_user_list = Signal(list)
    update_log_text = Signal(str)
    interrupt = Signal()
    accomplish = Signal(dict)

    isInterruptionRequested = False

    def __init__(
        self,
        mode: str,
        config: Dict[
            str,
            Union[
                str,
                Path,
                MaaConfig,
                Dict[str, Dict[str, Union[Path, MaaUserConfig]]],
            ],
        ],
        user_config_path: Path = None,
    ):
        super(MaaManager, self).__init__()

        self.user_list = ""
        self.mode = mode
        self.config_path = config["Path"]
        self.user_config_path = user_config_path

        self.log_monitor = QFileSystemWatcher()
        self.log_monitor_timer = QTimer()
        self.log_monitor_timer.timeout.connect(self.refresh_maa_log)
        self.monitor_loop = QEventLoop()

        self.question_loop = QEventLoop()
        self.question_response.connect(self.__capture_response)
        self.question_response.connect(self.question_loop.quit)

        self.interrupt.connect(self.quit_monitor)

        self.maa_version = None
        self.maa_update_package = ""
        self.task_dict = {}
        self.set = config["Config"].toDict()

        self.data = {}
        if "设置MAA" not in self.mode:
            for name, info in config["UserData"].items():
                self.data[name] = {
                    "Path": info["Path"],
                    "Config": info["Config"].toDict(),
                }
                planed_info = info["Config"].get_plan_info()
                for key, value in planed_info.items():
                    self.data[name]["Config"]["Info"][key] = value

            self.data = dict(sorted(self.data.items(), key=lambda x: int(x[0][3:])))

    def configure(self):
        """提取配置信息"""

        self.name = self.set["MaaSet"]["Name"]
        self.maa_root_path = Path(self.set["MaaSet"]["Path"])
        self.maa_set_path = self.maa_root_path / "config/gui.json"
        self.maa_log_path = self.maa_root_path / "debug/gui.log"
        self.maa_exe_path = self.maa_root_path / "MAA.exe"
        self.maa_tasks_path = self.maa_root_path / "resource/tasks/tasks.json"
        self.port_range = [0] + [
            (i // 2 + 1) * (-1 if i % 2 else 1)
            for i in range(0, 2 * self.set["RunSet"]["ADBSearchRange"])
        ]

    def run(self):
        """主进程，运行MAA代理进程"""

        current_date = datetime.now().strftime("%m-%d")
        curdate = Config.server_date().strftime("%Y-%m-%d")
        begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.configure()
        # 检查MAA路径是否可用
        if not self.maa_exe_path.exists() or not self.maa_set_path.exists():

            logger.error("未正确配置MAA路径，MAA代理进程中止")
            self.push_info_bar.emit(
                "error", "启动MAA代理进程失败", "您还未正确配置MAA路径！", -1
            )
            self.accomplish.emit(
                {
                    "Time": begin_time,
                    "History": "由于未正确配置MAA路径，MAA代理进程中止",
                }
            )
            return None

        # 整理用户数据，筛选需代理的用户
        if "设置MAA" not in self.mode:

            self.data = dict(
                sorted(
                    self.data.items(),
                    key=lambda x: (x[1]["Config"]["Info"]["Mode"], int(x[0][3:])),
                )
            )
            self.user_list: List[List[str, str, str]] = [
                [_["Config"]["Info"]["Name"], "等待", index]
                for index, _ in self.data.items()
                if (
                    _["Config"]["Info"]["RemainedDay"] != 0
                    and _["Config"]["Info"]["Status"]
                )
            ]
            self.create_user_list.emit(self.user_list)

        # 自动代理模式
        if self.mode == "自动代理":

            # 标记是否需要重启模拟器
            self.if_open_emulator = True
            # 执行情况预处理
            for _ in self.user_list:
                if self.data[_[2]]["Config"]["Data"]["LastProxyDate"] != curdate:
                    self.data[_[2]]["Config"]["Data"]["LastProxyDate"] = curdate
                    self.data[_[2]]["Config"]["Data"]["ProxyTimes"] = 0
                _[
                    0
                ] += f" - 第{self.data[_[2]]["Config"]["Data"]["ProxyTimes"] + 1}次代理"

            # 开始代理
            for user in self.user_list:

                user_data = self.data[user[2]]["Config"]

                if self.isInterruptionRequested:
                    break

                if (
                    self.set["RunSet"]["ProxyTimesLimit"] == 0
                    or user_data["Data"]["ProxyTimes"]
                    < self.set["RunSet"]["ProxyTimesLimit"]
                ):
                    user[1] = "运行"
                    self.update_user_list.emit(self.user_list)
                else:
                    user[1] = "跳过"
                    self.update_user_list.emit(self.user_list)
                    continue

                logger.info(f"{self.name} | 开始代理用户: {user[0]}")

                # 初始化代理情况记录和模式替换表
                run_book = {"Annihilation": False, "Routine": False}
                mode_book = {
                    "Annihilation": "自动代理_剿灭",
                    "Routine": "自动代理_日常",
                }

                # 简洁模式用户默认开启日常选项
                if user_data["Info"]["Mode"] == "简洁":
                    user_data["Info"]["Routine"] = True
                # 详细模式用户首次代理需打开模拟器
                elif user_data["Info"]["Mode"] == "详细":
                    self.if_open_emulator = True

                user_logs_list = []
                user_start_time = datetime.now()

                # 剿灭-日常模式循环
                for mode in ["Annihilation", "Routine"]:

                    if self.isInterruptionRequested:
                        break

                    # 剿灭模式；满足条件跳过剿灭
                    if (
                        mode == "Annihilation"
                        and self.set["RunSet"]["AnnihilationWeeklyLimit"]
                        and datetime.strptime(
                            user_data["Data"]["LastAnnihilationDate"], "%Y-%m-%d"
                        ).isocalendar()[:2]
                        == datetime.strptime(curdate, "%Y-%m-%d").isocalendar()[:2]
                    ):
                        logger.info(
                            f"{self.name} | 用户: {user_data["Info"]["Name"]} - 本周剿灭模式已达上限，跳过执行剿灭任务"
                        )
                        run_book[mode] = True
                        continue
                    else:
                        self.weekly_annihilation_limit_reached = False

                    if not user_data["Info"][mode]:
                        run_book[mode] = True
                        continue

                    if user_data["Info"]["Mode"] == "详细":

                        if not (
                            self.data[user[2]]["Path"] / f"{mode}/gui.json"
                        ).exists():
                            logger.error(
                                f"{self.name} | 用户: {user[0]} - 未找到{mode_book[mode][5:7]}配置文件"
                            )
                            self.push_info_bar.emit(
                                "error",
                                "启动MAA代理进程失败",
                                f"未找到{user[0]}的{mode_book[mode][5:7]}配置文件！",
                                -1,
                            )
                            run_book[mode] = False
                            continue

                    # 更新当前模式到界面
                    self.update_user_list.emit(
                        [
                            (
                                [f"{_[0]} - {mode_book[mode][5:7]}", _[1], _[2]]
                                if _[2] == user[2]
                                else _
                            )
                            for _ in self.user_list
                        ]
                    )

                    # 解析任务构成
                    if mode == "Routine":

                        self.task_dict = {
                            "WakeUp": str(user_data["Task"]["IfWakeUp"]),
                            "Recruiting": str(user_data["Task"]["IfRecruiting"]),
                            "Base": str(user_data["Task"]["IfBase"]),
                            "Combat": str(user_data["Task"]["IfCombat"]),
                            "Mission": str(user_data["Task"]["IfMission"]),
                            "Mall": str(user_data["Task"]["IfMall"]),
                            "AutoRoguelike": str(user_data["Task"]["IfAutoRoguelike"]),
                            "Reclamation": str(user_data["Task"]["IfReclamation"]),
                        }

                    elif mode == "Annihilation":

                        if user_data["Info"]["Mode"] == "简洁":

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

                        elif user_data["Info"]["Mode"] == "详细":

                            with (self.data[user[2]]["Path"] / f"{mode}/gui.json").open(
                                mode="r", encoding="utf-8"
                            ) as f:
                                data = json.load(f)

                            self.task_dict = {
                                "WakeUp": data["Configurations"]["Default"][
                                    "TaskQueue.WakeUp.IsChecked"
                                ],
                                "Recruiting": data["Configurations"]["Default"][
                                    "TaskQueue.Recruiting.IsChecked"
                                ],
                                "Base": data["Configurations"]["Default"][
                                    "TaskQueue.Base.IsChecked"
                                ],
                                "Combat": data["Configurations"]["Default"][
                                    "TaskQueue.Combat.IsChecked"
                                ],
                                "Mission": data["Configurations"]["Default"][
                                    "TaskQueue.Mission.IsChecked"
                                ],
                                "Mall": data["Configurations"]["Default"][
                                    "TaskQueue.Mall.IsChecked"
                                ],
                                "AutoRoguelike": data["Configurations"]["Default"][
                                    "TaskQueue.AutoRoguelike.IsChecked"
                                ],
                                "Reclamation": data["Configurations"]["Default"][
                                    "TaskQueue.Reclamation.IsChecked"
                                ],
                            }

                    # 尝试次数循环
                    for i in range(self.set["RunSet"]["RunTimesLimit"]):

                        if self.isInterruptionRequested:
                            break

                        if run_book[mode]:
                            break

                        logger.info(
                            f"{self.name} | 用户: {user[0]} - 模式: {mode_book[mode]} - 尝试次数: {i + 1}/{self.set["RunSet"]["RunTimesLimit"]}"
                        )

                        # 配置MAA
                        set = self.set_maa(mode_book[mode], user[2])
                        # 记录当前时间
                        start_time = datetime.now()

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
                                logger.error(
                                    f"{self.name} | 解析快捷方式时出现异常：{e}"
                                )
                                self.push_info_bar.emit(
                                    "error",
                                    "解析快捷方式时出现异常",
                                    "请检查快捷方式",
                                    -1,
                                )
                                self.if_open_emulator = True
                                break
                        elif not self.emulator_path.exists():
                            logger.error(
                                f"{self.name} | 模拟器快捷方式不存在：{self.emulator_path}"
                            )
                            self.push_info_bar.emit(
                                "error",
                                "启动模拟器时出现异常",
                                "模拟器快捷方式不存在",
                                -1,
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
                            logger.info(f"{self.name} | 释放ADB：{self.ADB_address}")
                            subprocess.run(
                                [self.ADB_path, "disconnect", self.ADB_address],
                                creationflags=subprocess.CREATE_NO_WINDOW,
                            )
                        except subprocess.CalledProcessError as e:
                            # 忽略错误,因为可能本来就没有连接
                            logger.warning(f"{self.name} | 释放ADB时出现异常：{e}")
                        except Exception as e:
                            logger.error(f"{self.name} | 释放ADB时出现异常：{e}")
                            self.push_info_bar.emit(
                                "error",
                                "释放ADB时出现异常",
                                "请检查MAA中ADB路径设置",
                                -1,
                            )

                        if self.if_open_emulator_process:
                            try:
                                logger.info(
                                    f"{self.name} | 启动模拟器：{self.emulator_path}，参数：{self.emulator_arguments}"
                                )
                                self.emulator_process = subprocess.Popen(
                                    [self.emulator_path, *self.emulator_arguments],
                                    creationflags=subprocess.CREATE_NO_WINDOW,
                                )
                            except Exception as e:
                                logger.error(f"{self.name} | 启动模拟器时出现异常：{e}")
                                self.push_info_bar.emit(
                                    "error",
                                    "启动模拟器时出现异常",
                                    "请检查MAA中模拟器路径设置",
                                    -1,
                                )
                                self.if_open_emulator = True
                                break

                        # 添加静默进程标记
                        Config.silence_list.append(self.emulator_path)

                        self.search_ADB_address()

                        # 创建MAA任务
                        maa = subprocess.Popen(
                            [self.maa_exe_path],
                            creationflags=subprocess.CREATE_NO_WINDOW,
                        )
                        # 监测MAA运行状态
                        self.start_monitor(start_time, mode_book[mode])

                        if self.maa_result == "Success!":

                            # 标记任务完成
                            run_book[mode] = True

                            # 从配置文件中解析所需信息
                            with self.maa_set_path.open(
                                mode="r", encoding="utf-8"
                            ) as f:
                                data = json.load(f)

                            # 记录自定义基建索引
                            user_data["Data"]["CustomInfrastPlanIndex"] = data[
                                "Configurations"
                            ]["Default"]["Infrast.CustomInfrastPlanIndex"]

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

                            logger.info(
                                f"{self.name} | 用户: {user[0]} - MAA进程完成代理任务"
                            )
                            self.update_log_text.emit(
                                "检测到MAA进程完成代理任务\n正在等待相关程序结束\n请等待10s"
                            )

                            for _ in range(10):
                                if self.isInterruptionRequested:
                                    break
                                time.sleep(1)
                        else:
                            logger.error(
                                f"{self.name} | 用户: {user[0]} - 代理任务异常: {self.maa_result}"
                            )
                            # 打印中止信息
                            # 此时，log变量内存储的就是出现异常的日志信息，可以保存或发送用于问题排查
                            self.update_log_text.emit(
                                f"{self.maa_result}\n正在中止相关程序\n请等待10s"
                            )
                            # 无命令行中止MAA与其子程序
                            System.kill_process(self.maa_exe_path)

                            # 中止模拟器进程
                            self.emulator_process.terminate()
                            self.emulator_process.wait()

                            self.if_open_emulator = True

                            # 从配置文件中解析所需信息
                            with self.maa_set_path.open(
                                mode="r", encoding="utf-8"
                            ) as f:
                                data = json.load(f)

                            # 记录自定义基建索引
                            if self.task_dict["Base"] == "False":
                                user_data["Data"]["CustomInfrastPlanIndex"] = data[
                                    "Configurations"
                                ]["Default"]["Infrast.CustomInfrastPlanIndex"]

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

                            # 推送异常通知
                            Notify.push_plyer(
                                "用户自动代理出现异常！",
                                f"用户 {user[0].replace("_", " 今天的")}的{mode_book[mode][5:7]}部分出现一次异常",
                                f"{user[0].replace("_", " ")}的{mode_book[mode][5:7]}出现异常",
                                1,
                            )
                            for _ in range(10):
                                if self.isInterruptionRequested:
                                    break
                                time.sleep(1)

                        # 任务结束后释放ADB
                        try:
                            logger.info(f"{self.name} | 释放ADB：{self.ADB_address}")
                            subprocess.run(
                                [self.ADB_path, "disconnect", self.ADB_address],
                                creationflags=subprocess.CREATE_NO_WINDOW,
                            )
                        except subprocess.CalledProcessError as e:
                            # 忽略错误,因为可能本来就没有连接
                            logger.warning(f"{self.name} | 释放ADB时出现异常：{e}")
                        except Exception as e:
                            logger.error(f"{self.name} | 释放ADB时出现异常：{e}")
                            self.push_info_bar.emit(
                                "error",
                                "释放ADB时出现异常",
                                "请检查MAA中ADB路径设置",
                                -1,
                            )
                        # 任务结束后再次手动中止模拟器进程，防止退出不彻底
                        if self.if_kill_emulator:
                            self.emulator_process.terminate()
                            self.emulator_process.wait()
                            self.if_open_emulator = True

                        # 记录剿灭情况
                        if (
                            mode == "Annihilation"
                            and self.weekly_annihilation_limit_reached
                        ):
                            user_data["Data"]["LastAnnihilationDate"] = curdate
                        # 保存运行日志以及统计信息
                        if_six_star = Config.save_maa_log(
                            Config.app_path
                            / f"history/{curdate}/{user_data["Info"]["Name"]}/{start_time.strftime("%H-%M-%S")}.log",
                            self.check_maa_log(start_time, mode_book[mode]),
                            self.maa_result,
                        )
                        user_logs_list.append(
                            Config.app_path
                            / f"history/{curdate}/{user_data["Info"]["Name"]}/{start_time.strftime("%H-%M-%S")}.json",
                        )
                        if if_six_star:
                            self.push_notification(
                                "公招六星",
                                f"喜报：用户 {user[0]} 公招出六星啦！",
                                {
                                    "user_name": user_data["Info"]["Name"],
                                },
                                user_data,
                            )

                        # 执行MAA解压更新动作
                        if self.maa_update_package:

                            logger.info(
                                f"{self.name} | 检测到MAA更新，正在执行更新动作"
                            )

                            self.update_log_text.emit(
                                f"检测到MAA存在更新\nMAA正在执行更新动作\n请等待10s"
                            )
                            self.set_maa("更新MAA", None)
                            subprocess.Popen(
                                [self.maa_exe_path],
                                creationflags=subprocess.CREATE_NO_WINDOW,
                            )
                            for _ in range(10):
                                if self.isInterruptionRequested:
                                    break
                                time.sleep(1)
                            System.kill_process(self.maa_exe_path)

                            logger.info(f"{self.name} | 更新动作结束")

                # 发送统计信息
                statistics = Config.merge_maa_logs("指定项", user_logs_list)
                statistics["user_index"] = user[2]
                statistics["user_info"] = user[0]
                statistics["start_time"] = user_start_time.strftime("%Y-%m-%d %H:%M:%S")
                statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                statistics["maa_result"] = (
                    "代理任务全部完成"
                    if (run_book["Annihilation"] and run_book["Routine"])
                    else "代理任务未全部完成"
                )
                self.push_notification(
                    "统计信息",
                    f"{current_date} | 用户 {user[0]} 的自动代理统计报告",
                    statistics,
                    user_data,
                )

                if run_book["Annihilation"] and run_book["Routine"]:
                    # 成功完成代理的用户修改相关参数
                    if (
                        user_data["Data"]["ProxyTimes"] == 0
                        and user_data["Info"]["RemainedDay"] != -1
                    ):
                        user_data["Info"]["RemainedDay"] -= 1
                    user_data["Data"]["ProxyTimes"] += 1
                    user[1] = "完成"
                    Notify.push_plyer(
                        "成功完成一个自动代理任务！",
                        f"已完成用户 {user[0].replace("_", " 今天的")}任务",
                        f"已完成 {user[0].replace("_", " 的")}",
                        3,
                    )
                else:
                    # 录入代理失败的用户
                    user[1] = "异常"

                self.update_user_list.emit(self.user_list)

        # 人工排查模式
        elif self.mode == "人工排查":

            # 人工排查时，屏蔽静默操作
            Config.if_ignore_silence = True

            # 标记是否需要启动模拟器
            self.if_open_emulator = True
            # 标识排查模式
            for _ in self.user_list:
                _[0] += "_排查模式"

            # 开始排查
            for user in self.user_list:

                user_data = self.data[user[2]]["Config"]

                if self.isInterruptionRequested:
                    break

                logger.info(f"{self.name} | 开始排查用户: {user[0]}")

                user[1] = "运行"
                self.update_user_list.emit(self.user_list)

                if user_data["Info"]["Mode"] == "详细":
                    self.if_open_emulator = True

                run_book = [False for _ in range(2)]

                # 启动重试循环
                while not self.isInterruptionRequested:

                    # 配置MAA
                    self.set_maa("人工排查", user[2])

                    # 记录当前时间
                    start_time = datetime.now()
                    # 创建MAA任务
                    maa = subprocess.Popen(
                        [self.maa_exe_path],
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )

                    # 监测MAA运行状态
                    self.start_monitor(start_time, "人工排查")

                    if self.maa_result == "Success!":
                        logger.info(
                            f"{self.name} | 用户: {user[0]} - MAA进程成功登录PRTS"
                        )
                        run_book[0] = True
                        self.update_log_text.emit("检测到MAA进程成功登录PRTS")
                    else:
                        logger.error(
                            f"{self.name} | 用户: {user[0]} - MAA未能正确登录到PRTS: {self.maa_result}"
                        )
                        self.update_log_text.emit(
                            f"{self.maa_result}\n正在中止相关程序\n请等待10s"
                        )
                        # 无命令行中止MAA与其子程序
                        System.kill_process(self.maa_exe_path)
                        self.if_open_emulator = True
                        for _ in range(10):
                            if self.isInterruptionRequested:
                                break
                            time.sleep(1)

                    # 登录成功，结束循环
                    if run_book[0]:
                        break
                    # 登录失败，询问是否结束循环
                    elif not self.isInterruptionRequested:

                        if not self.push_question(
                            "操作提示", "MAA未能正确登录到PRTS，是否重试？"
                        ):
                            break

                # 登录成功，录入人工排查情况
                if run_book[0] and not self.isInterruptionRequested:

                    if self.push_question(
                        "操作提示", "请检查用户代理情况，该用户是否正确完成代理任务？"
                    ):
                        run_book[1] = True

                # 结果录入
                if run_book[0] and run_book[1]:
                    logger.info(f"{self.name} | 用户 {user[0]} 通过人工排查")
                    user_data["Data"]["IfPassCheck"] = True
                    user[1] = "完成"
                else:
                    logger.info(f"{self.name} | 用户 {user[0]} 未通过人工排查")
                    user_data["Data"]["IfPassCheck"] = False
                    user[1] = "异常"

                self.update_user_list.emit(self.user_list)

            # 解除静默操作屏蔽
            Config.if_ignore_silence = False

        # 设置MAA模式
        elif "设置MAA" in self.mode:

            # 配置MAA
            self.set_maa(self.mode, "")
            # 创建MAA任务
            maa = subprocess.Popen(
                [self.maa_exe_path],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            # 记录当前时间
            start_time = datetime.now()

            # 监测MAA运行状态
            self.start_monitor(start_time, "设置MAA")

            if "全局" in self.mode:
                (self.config_path / "Default").mkdir(parents=True, exist_ok=True)
                shutil.copy(self.maa_set_path, self.config_path / "Default")

            elif "用户" in self.mode:
                self.user_config_path.mkdir(parents=True, exist_ok=True)
                shutil.copy(self.maa_set_path, self.user_config_path)

            result_text = ""

        # 导出结果
        if self.mode in ["自动代理", "人工排查"]:

            # 关闭可能未正常退出的MAA进程
            if self.isInterruptionRequested:
                System.kill_process(self.maa_exe_path)

            # 复原MAA配置文件
            shutil.copy(self.config_path / "Default/gui.json", self.maa_set_path)

            # 更新用户数据
            updated_info = {_[2]: self.data[_[2]] for _ in self.user_list}
            self.update_user_info.emit(self.config_path.name, updated_info)

            error_index = [_[2] for _ in self.user_list if _[1] == "异常"]
            over_index = [_[2] for _ in self.user_list if _[1] == "完成"]
            wait_index = [_[2] for _ in self.user_list if _[1] == "等待"]

            # 保存运行日志
            title = (
                f"{current_date} | {self.set["MaaSet"]["Name"]}的{self.mode[:4]}任务报告"
                if self.set["MaaSet"]["Name"] != ""
                else f"{current_date} | {self.mode[:4]}任务报告"
            )
            result = {
                "title": f"{self.mode[:4]}任务报告",
                "script_name": (
                    self.set["MaaSet"]["Name"]
                    if self.set["MaaSet"]["Name"] != ""
                    else "空白"
                ),
                "start_time": begin_time,
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "completed_count": len(over_index),
                "uncompleted_count": len(error_index) + len(wait_index),
                "failed_user": [
                    self.data[_]["Config"]["Info"]["Name"] for _ in error_index
                ],
                "waiting_user": [
                    self.data[_]["Config"]["Info"]["Name"] for _ in wait_index
                ],
            }

            # 生成结果文本
            result_text = (
                f"任务开始时间：{result["start_time"]}，结束时间：{result["end_time"]}\n"
                f"已完成数：{result["completed_count"]}，未完成数：{result["uncompleted_count"]}\n\n"
            )
            if len(result["failed_user"]) > 0:
                result_text += f"{self.mode[2:4]}未成功的用户：\n{"\n".join(result["failed_user"])}\n"
            if len(result["waiting_user"]) > 0:
                result_text += f"\n未开始{self.mode[2:4]}的用户：\n{"\n".join(result["waiting_user"])}\n"

            # 推送代理结果通知
            Notify.push_plyer(
                title.replace("报告", "已完成！"),
                f"已完成用户数：{len(over_index)}，未完成用户数：{len(error_index) + len(wait_index)}",
                f"已完成用户数：{len(over_index)}，未完成用户数：{len(error_index) + len(wait_index)}",
                10,
            )
            self.push_notification("代理结果", title, result)

        self.agree_bilibili(False)
        self.log_monitor.deleteLater()
        self.log_monitor_timer.deleteLater()
        self.accomplish.emit({"Time": begin_time, "History": result_text})

    def requestInterruption(self) -> None:
        logger.info(f"{self.name} | 收到任务中止申请")

        if len(self.log_monitor.files()) != 0:
            self.interrupt.emit()

        self.maa_result = "任务被手动中止"
        self.isInterruptionRequested = True

    def push_question(self, title: str, message: str) -> bool:

        self.question.emit(title, message)
        self.question_loop.exec()
        return self.response

    def __capture_response(self, response: bool) -> None:
        self.response = response

    def search_ADB_address(self) -> None:
        """搜索ADB实际地址"""

        self.update_log_text.emit(
            f"即将搜索ADB实际地址\n正在等待模拟器完成启动\n请等待{self.wait_time}s"
        )

        for _ in range(self.wait_time):
            if self.isInterruptionRequested:
                break
            time.sleep(1)

        # 移除静默进程标记
        Config.silence_list.remove(self.emulator_path)

        if "-" in self.ADB_address:
            ADB_ip = f"{self.ADB_address.split("-")[0]}-"
            ADB_port = int(self.ADB_address.split("-")[1])

        elif ":" in self.ADB_address:
            ADB_ip = f"{self.ADB_address.split(':')[0]}:"
            ADB_port = int(self.ADB_address.split(":")[1])

        logger.info(
            f"{self.name} | 正在搜索ADB实际地址，ADB前缀：{ADB_ip}，初始端口：{ADB_port}，搜索范围：{self.port_range}"
        )

        for port in self.port_range:

            ADB_address = f"{ADB_ip}{ADB_port + port}"

            # 尝试通过ADB连接到指定地址
            connect_result = subprocess.run(
                [self.ADB_path, "connect", ADB_address],
                creationflags=subprocess.CREATE_NO_WINDOW,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            if "connected" in connect_result.stdout:

                # 检查连接状态
                devices_result = subprocess.run(
                    [self.ADB_path, "devices"],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                if ADB_address in devices_result.stdout:

                    logger.info(f"{self.name} | ADB实际地址：{ADB_address}")

                    # 断开连接
                    subprocess.run(
                        [self.ADB_path, "disconnect", ADB_address],
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )

                    self.ADB_address = ADB_address

                    # 覆写当前ADB地址
                    System.kill_process(self.maa_exe_path)
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
                    logger.info(f"{self.name} | 无法连接到ADB地址：{ADB_address}")
            else:
                logger.info(f"{self.name} | 无法连接到ADB地址：{ADB_address}")

    def refresh_maa_log(self) -> None:
        """刷新MAA日志"""

        with self.maa_log_path.open(mode="r", encoding="utf-8") as f:
            pass

        # 一分钟内未执行日志变化检查，强制检查一次
        if datetime.now() - self.last_check_time > timedelta(minutes=1):
            self.log_monitor.fileChanged.emit(self.log_monitor.files()[0])

    def check_maa_log(self, start_time: datetime, mode: str) -> list:
        """获取MAA日志并检查以判断MAA程序运行状态"""

        self.last_check_time = datetime.now()

        # 获取日志
        logs = []
        if_log_start = False
        with self.maa_log_path.open(mode="r", encoding="utf-8") as f:
            for entry in f:
                if not if_log_start:
                    try:
                        entry_time = datetime.strptime(entry[1:20], "%Y-%m-%d %H:%M:%S")
                        if entry_time > start_time:
                            if_log_start = True
                            logs.append(entry)
                    except ValueError:
                        pass
                else:
                    logs.append(entry)
        log = "".join(logs)

        # 更新MAA日志
        if len(logs) > 100:
            self.update_log_text.emit("".join(logs[-100:]))
        else:
            self.update_log_text.emit("".join(logs))

        # 获取MAA版本号
        if not self.set["RunSet"]["AutoUpdateMaa"] and not self.maa_version:

            section_match = re.search(r"={35}(.*?)={35}", log, re.DOTALL)
            if section_match:

                version_match = re.search(
                    r"Version\s+v(\d+\.\d+\.\d+(?:-\w+\.\d+)?)", section_match.group(1)
                )
                if version_match:
                    self.maa_version = f"v{version_match.group(1)}"
                    self.check_maa_version.emit(self.maa_version)

        if "自动代理" in mode:

            # 获取最近一条日志的时间
            latest_time = start_time
            for _ in logs[::-1]:
                try:
                    if "如果长时间无进一步日志更新，可能需要手动干预。" in _:
                        continue
                    latest_time = datetime.strptime(_[1:20], "%Y-%m-%d %H:%M:%S")
                    break
                except ValueError:
                    pass

            time_book = {
                "自动代理_剿灭": "AnnihilationTimeLimit",
                "自动代理_日常": "RoutineTimeLimit",
            }

            if mode == "自动代理_剿灭" and "剿灭任务失败" in log:
                self.weekly_annihilation_limit_reached = True
            else:
                self.weekly_annihilation_limit_reached = False

            if "任务出错: StartUp" in log:
                self.maa_result = "MAA未能正确登录PRTS"

            elif "任务已全部完成！" in log:

                if "完成任务: StartUp" in log:
                    self.task_dict["WakeUp"] = "False"
                if "完成任务: Recruit" in log:
                    self.task_dict["Recruiting"] = "False"
                if "完成任务: Infrast" in log:
                    self.task_dict["Base"] = "False"
                if "完成任务: Fight" in log or "剿灭任务失败" in log:
                    self.task_dict["Combat"] = "False"
                if "完成任务: Mall" in log:
                    self.task_dict["Mall"] = "False"
                if "完成任务: Award" in log:
                    self.task_dict["Mission"] = "False"
                if "完成任务: Roguelike" in log:
                    self.task_dict["AutoRoguelike"] = "False"
                if "完成任务: Reclamation" in log:
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

            elif "MaaAssistantArknights GUI exited" in log:
                self.maa_result = "MAA在完成任务前退出"

            elif datetime.now() - latest_time > timedelta(
                minutes=self.set["RunSet"][time_book[mode]]
            ):
                self.maa_result = "MAA进程超时"

            elif self.isInterruptionRequested:
                self.maa_result = "任务被手动中止"

            else:
                self.maa_result = "Wait"

        elif mode == "人工排查":
            if "完成任务: StartUp" in log:
                self.maa_result = "Success!"
            elif "请 ｢检查连接设置｣ → ｢尝试重启模拟器与 ADB｣ → ｢重启电脑｣" in log:
                self.maa_result = "MAA的ADB连接异常"
            elif "未检测到任何模拟器" in log:
                self.maa_result = "MAA未检测到任何模拟器"
            elif "已停止" in log:
                self.maa_result = "MAA在完成任务前中止"
            elif "MaaAssistantArknights GUI exited" in log:
                self.maa_result = "MAA在完成任务前退出"
            elif self.isInterruptionRequested:
                self.maa_result = "任务被手动中止"
            else:
                self.maa_result = "Wait"

        elif mode == "设置MAA":
            if "MaaAssistantArknights GUI exited" in log:
                self.maa_result = "Success!"
            else:
                self.maa_result = "Wait"

        if self.maa_result != "Wait":

            self.quit_monitor()

        return logs

    def start_monitor(self, start_time: datetime, mode: str) -> None:
        """开始监视MAA日志"""

        logger.info(f"{self.name} | 开始监视MAA日志")
        self.log_monitor.addPath(str(self.maa_log_path))
        self.log_monitor.fileChanged.connect(
            lambda: self.check_maa_log(start_time, mode)
        )
        self.log_monitor_timer.start(1000)
        self.last_check_time = datetime.now()
        self.monitor_loop.exec()

    def quit_monitor(self) -> None:
        """退出MAA日志监视进程"""

        if len(self.log_monitor.files()) != 0:

            logger.info(f"{self.name} | 退出MAA日志监视")
            self.log_monitor.removePath(str(self.maa_log_path))
            self.log_monitor.fileChanged.disconnect()
            self.log_monitor_timer.stop()
            self.last_check_time = None
            self.monitor_loop.quit()

    def set_maa(self, mode, index) -> dict:
        """配置MAA运行参数"""
        logger.info(f"{self.name} | 配置MAA运行参数: {mode}/{index}")

        if "设置MAA" not in self.mode and "更新MAA" not in mode:
            user_data = self.data[index]["Config"]

        # 配置MAA前关闭可能未正常退出的MAA进程
        System.kill_process(self.maa_exe_path)

        # 预导入MAA配置文件
        if mode == "设置MAA_用户":
            if self.user_config_path.exists():
                shutil.copy(self.user_config_path / "gui.json", self.maa_set_path)
            else:
                shutil.copy(
                    self.config_path / "Default/gui.json",
                    self.maa_set_path,
                )
        elif (mode in ["设置MAA_全局", "更新MAA"]) or (
            ("自动代理" in mode or "人工排查" in mode)
            and user_data["Info"]["Mode"] == "简洁"
        ):
            shutil.copy(
                self.config_path / "Default/gui.json",
                self.maa_set_path,
            )
        elif "自动代理" in mode and user_data["Info"]["Mode"] == "详细":
            if mode == "自动代理_剿灭":
                shutil.copy(
                    self.data[index]["Path"] / "Annihilation/gui.json",
                    self.maa_set_path,
                )
            elif mode == "自动代理_日常":
                shutil.copy(
                    self.data[index]["Path"] / "Routine/gui.json",
                    self.maa_set_path,
                )
        elif "人工排查" in mode and user_data["Info"]["Mode"] == "详细":
            shutil.copy(
                self.data[index]["Path"] / "Routine/gui.json",
                self.maa_set_path,
            )
        with self.maa_set_path.open(mode="r", encoding="utf-8") as f:
            data = json.load(f)

        if ("设置MAA" not in self.mode and "更新MAA" not in mode) and (
            (
                user_data["Info"]["Mode"] == "简洁"
                and user_data["Info"]["Server"] == "Bilibili"
            )
            or (
                user_data["Info"]["Mode"] == "详细"
                and data["Configurations"]["Default"]["Start.ClientType"] == "Bilibili"
            )
        ):
            self.agree_bilibili(True)
        else:
            self.agree_bilibili(False)

        # 自动代理配置
        if "自动代理" in mode:

            data["Current"] = "Default"  # 切换配置
            for i in range(1, 9):
                data["Global"][f"Timer.Timer{i}"] = "False"  # 时间设置

            if (
                next((i for i, _ in enumerate(self.user_list) if _[2] == index), None)
                == len(self.user_list) - 1
            ) or (
                self.data[
                    self.user_list[
                        next(
                            (i for i, _ in enumerate(self.user_list) if _[2] == index),
                            None,
                        )
                        + 1
                    ][2]
                ]["Config"]["Info"]["Mode"]
                == "详细"
            ):
                data["Configurations"]["Default"][
                    "MainFunction.PostActions"
                ] = "12"  # 完成后退出MAA和模拟器
            else:
                method_dict = {"NoAction": "8", "ExitGame": "9", "ExitEmulator": "12"}
                data["Configurations"]["Default"]["MainFunction.PostActions"] = (
                    method_dict[self.set["RunSet"]["TaskTransitionMethod"]]
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
            data["Global"]["VersionUpdate.AutoDownloadUpdatePackage"] = str(
                self.set["RunSet"]["AutoUpdateMaa"]
            )  # 自动下载更新包
            data["Global"][
                "VersionUpdate.AutoInstallUpdatePackage"
            ] = "False"  # 自动安装更新包

            if Config.get(Config.function_IfSilence):
                data["Global"]["Start.MinimizeDirectly"] = "True"  # 启动MAA后直接最小化
                data["Global"]["GUI.UseTray"] = "True"  # 显示托盘图标
                data["Global"]["GUI.MinimizeToTray"] = "True"  # 最小化时隐藏至托盘

            # 账号切换
            if user_data["Info"]["Server"] == "Official":
                data["Configurations"]["Default"]["Start.AccountName"] = (
                    f"{user_data["Info"]["Id"][:3]}****{user_data["Info"]["Id"][7:]}"
                    if len(user_data["Info"]["Id"]) == 11
                    else user_data["Info"]["Id"]
                )
            elif user_data["Info"]["Server"] == "Bilibili":
                data["Configurations"]["Default"]["Start.AccountName"] = user_data[
                    "Info"
                ]["Id"]

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

            if user_data["Info"]["Mode"] == "简洁":

                data["Configurations"]["Default"]["Start.ClientType"] = user_data[
                    "Info"
                ][
                    "Server"
                ]  # 客户端类型

                # 整理任务顺序
                data["Configurations"]["Default"]["TaskQueue.Order.WakeUp"] = "0"
                data["Configurations"]["Default"]["TaskQueue.Order.Recruiting"] = "1"
                data["Configurations"]["Default"]["TaskQueue.Order.Base"] = "2"
                data["Configurations"]["Default"]["TaskQueue.Order.Combat"] = "3"
                data["Configurations"]["Default"]["TaskQueue.Order.Mall"] = "4"
                data["Configurations"]["Default"]["TaskQueue.Order.Mission"] = "5"
                data["Configurations"]["Default"]["TaskQueue.Order.AutoRoguelike"] = "6"
                data["Configurations"]["Default"]["TaskQueue.Order.Reclamation"] = "7"

                if "剿灭" in mode:

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

                elif "日常" in mode:

                    data["Configurations"]["Default"]["MainFunction.UseMedicine"] = (
                        "False" if user_data["Info"]["MedicineNumb"] == 0 else "True"
                    )  # 吃理智药
                    data["Configurations"]["Default"][
                        "MainFunction.UseMedicine.Quantity"
                    ] = str(
                        user_data["Info"]["MedicineNumb"]
                    )  # 吃理智药数量
                    data["Configurations"]["Default"]["MainFunction.Stage1"] = (
                        user_data["Info"]["GameId"]
                        if user_data["Info"]["GameId"] != "-"
                        else ""
                    )  # 主关卡
                    data["Configurations"]["Default"]["MainFunction.Stage2"] = (
                        user_data["Info"]["GameId_1"]
                        if user_data["Info"]["GameId_1"] != "-"
                        else ""
                    )  # 备选关卡1
                    data["Configurations"]["Default"]["MainFunction.Stage3"] = (
                        user_data["Info"]["GameId_2"]
                        if user_data["Info"]["GameId_2"] != "-"
                        else ""
                    )  # 备选关卡2
                    data["Configurations"]["Default"]["Fight.RemainingSanityStage"] = (
                        user_data["Info"]["GameId_Remain"]
                        if user_data["Info"]["GameId_Remain"] != "-"
                        else ""
                    )  # 剩余理智关卡
                    data["Configurations"]["Default"][
                        "MainFunction.Series.Quantity"
                    ] = user_data["Info"][
                        "SeriesNumb"
                    ]  # 连战次数
                    data["Configurations"]["Default"][
                        "Penguin.IsDrGrandet"
                    ] = "False"  # 博朗台模式
                    data["Configurations"]["Default"][
                        "GUI.CustomStageCode"
                    ] = "True"  # 手动输入关卡名
                    data["Configurations"]["Default"][
                        "GUI.UseAlternateStage"
                    ] = "True"  # 备选关卡
                    data["Configurations"]["Default"][
                        "Fight.UseRemainingSanityStage"
                    ] = (
                        "True" if user_data["Info"]["GameId_Remain"] != "-" else "False"
                    )  # 使用剩余理智
                    data["Configurations"]["Default"][
                        "Fight.UseExpiringMedicine"
                    ] = "True"  # 无限吃48小时内过期的理智药
                    # 自定义基建配置
                    if user_data["Info"]["InfrastMode"] == "Custom":

                        if (
                            self.data[index]["Path"]
                            / "Infrastructure/infrastructure.json"
                        ).exists():

                            data["Configurations"]["Default"][
                                "Infrast.InfrastMode"
                            ] = "Custom"  # 基建模式
                            data["Configurations"]["Default"][
                                "Infrast.CustomInfrastPlanIndex"
                            ] = user_data["Data"][
                                "CustomInfrastPlanIndex"
                            ]  # 自定义基建配置索引
                            data["Configurations"]["Default"][
                                "Infrast.DefaultInfrast"
                            ] = "user_defined"  # 内置配置
                            data["Configurations"]["Default"][
                                "Infrast.IsCustomInfrastFileReadOnly"
                            ] = "False"  # 自定义基建配置文件只读
                            data["Configurations"]["Default"][
                                "Infrast.CustomInfrastFile"
                            ] = str(
                                self.data[index]["Path"]
                                / "Infrastructure/infrastructure.json"
                            )  # 自定义基建配置文件地址
                        else:
                            logger.warning(
                                f"未选择用户 {user_data["Info"]["Name"]} 的自定义基建配置文件"
                            )
                            self.push_info_bar.emit(
                                "warning",
                                "启用自定义基建失败",
                                f"未选择用户 {user_data["Info"]["Name"]} 的自定义基建配置文件",
                                -1,
                            )
                            data["Configurations"]["Default"][
                                "Infrast.CustomInfrastEnabled"
                            ] = "Normal"  # 基建模式
                    else:
                        data["Configurations"]["Default"][
                            "Infrast.InfrastMode"
                        ] = user_data["Info"][
                            "InfrastMode"
                        ]  # 基建模式

            elif user_data["Info"]["Mode"] == "详细":

                if "剿灭" in mode:

                    pass

                elif "日常" in mode:

                    data["Configurations"]["Default"]["MainFunction.UseMedicine"] = (
                        "False" if user_data["Info"]["MedicineNumb"] == 0 else "True"
                    )  # 吃理智药
                    data["Configurations"]["Default"][
                        "MainFunction.UseMedicine.Quantity"
                    ] = str(
                        user_data["Info"]["MedicineNumb"]
                    )  # 吃理智药数量
                    data["Configurations"]["Default"]["MainFunction.Stage1"] = (
                        user_data["Info"]["GameId"]
                        if user_data["Info"]["GameId"] != "-"
                        else ""
                    )  # 主关卡
                    data["Configurations"]["Default"]["MainFunction.Stage2"] = (
                        user_data["Info"]["GameId_1"]
                        if user_data["Info"]["GameId_1"] != "-"
                        else ""
                    )  # 备选关卡1
                    data["Configurations"]["Default"]["MainFunction.Stage3"] = (
                        user_data["Info"]["GameId_2"]
                        if user_data["Info"]["GameId_2"] != "-"
                        else ""
                    )  # 备选关卡2
                    data["Configurations"]["Default"]["Fight.RemainingSanityStage"] = (
                        user_data["Info"]["GameId_Remain"]
                        if user_data["Info"]["GameId_Remain"] != "-"
                        else ""
                    )  # 剩余理智关卡
                    data["Configurations"]["Default"][
                        "MainFunction.Series.Quantity"
                    ] = user_data["Info"][
                        "SeriesNumb"
                    ]  # 连战次数
                    data["Configurations"]["Default"][
                        "GUI.UseAlternateStage"
                    ] = "True"  # 备选关卡
                    data["Configurations"]["Default"][
                        "Fight.UseRemainingSanityStage"
                    ] = (
                        "True" if user_data["Info"]["GameId_Remain"] != "-" else "False"
                    )  # 使用剩余理智

                    # 基建模式
                    if (
                        data["Configurations"]["Default"]["Infrast.InfrastMode"]
                        == "Custom"
                    ):
                        data["Configurations"]["Default"][
                            "Infrast.CustomInfrastPlanIndex"
                        ] = user_data["Data"][
                            "CustomInfrastPlanIndex"
                        ]  # 自定义基建配置索引

        # 人工排查配置
        elif "人工排查" in mode:

            data["Current"] = "Default"  # 切换配置
            for i in range(1, 9):
                data["Global"][f"Timer.Timer{i}"] = "False"  # 时间设置
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

            # 账号切换
            if user_data["Info"]["Server"] == "Official":
                data["Configurations"]["Default"]["Start.AccountName"] = (
                    f"{user_data["Info"]["Id"][:3]}****{user_data["Info"]["Id"][7:]}"
                    if len(user_data["Info"]["Id"]) == 11
                    else user_data["Info"]["Id"]
                )
            elif user_data["Info"]["Server"] == "Bilibili":
                data["Configurations"]["Default"]["Start.AccountName"] = user_data[
                    "Info"
                ]["Id"]

            if user_data["Info"]["Mode"] == "简洁":

                data["Configurations"]["Default"]["Start.ClientType"] = user_data[
                    "Info"
                ][
                    "Server"
                ]  # 客户端类型

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

        # 设置MAA配置
        elif "设置MAA" in mode:

            data["Current"] = "Default"  # 切换配置
            for i in range(1, 9):
                data["Global"][f"Timer.Timer{i}"] = "False"  # 时间设置
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

            if Config.get(Config.function_IfSilence):
                data["Global"][
                    "Start.MinimizeDirectly"
                ] = "False"  # 启动MAA后直接最小化

            if "全局" in mode:

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

        elif mode == "更新MAA":

            data["Current"] = "Default"  # 切换配置
            for i in range(1, 9):
                data["Global"][f"Timer.Timer{i}"] = "False"  # 时间设置
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
        if "设置MAA" not in mode and "更新MAA" not in mode and self.if_open_emulator:
            self.if_open_emulator = False

        # 覆写配置文件
        with self.maa_set_path.open(mode="w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        return data

    def agree_bilibili(self, if_agree):
        """向MAA写入Bilibili协议相关任务"""
        logger.info(
            f"{self.name} | Bilibili协议相关任务状态: {"启用" if if_agree else "禁用"}"
        )

        with self.maa_tasks_path.open(mode="r", encoding="utf-8") as f:
            data = json.load(f)

        if if_agree and Config.get(Config.function_IfAgreeBilibili):
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

    def push_notification(
        self,
        mode: str,
        title: str,
        message: Union[str, dict],
        user_data: Dict[str, Dict[str, Union[str, int, bool]]] = None,
    ) -> None:
        """通过所有渠道推送通知"""

        env = Environment(
            loader=FileSystemLoader(str(Config.app_path / "resources/html"))
        )

        if mode == "代理结果" and (
            Config.get(Config.notify_SendTaskResultTime) == "任何时刻"
            or (
                Config.get(Config.notify_SendTaskResultTime) == "仅失败时"
                and message["uncompleted_count"] != 0
            )
        ):
            # 生成文本通知内容
            message_text = (
                f"任务开始时间：{message["start_time"]}，结束时间：{message["end_time"]}\n"
                f"已完成数：{message["completed_count"]}，未完成数：{message["uncompleted_count"]}\n\n"
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

            if Config.get(Config.notify_IfSendMail):
                Notify.send_mail(
                    "网页", title, message_html, Config.get(Config.notify_ToAddress)
                )

            if Config.get(Config.notify_IfServerChan):
                Notify.ServerChanPush(
                    title,
                    f"{serverchan_message}\n\nAUTO_MAA 敬上",
                    Config.get(Config.notify_ServerChanKey),
                    Config.get(Config.notify_ServerChanTag),
                    Config.get(Config.notify_ServerChanChannel),
                )

            if Config.get(Config.notify_IfCompanyWebHookBot):
                Notify.CompanyWebHookBotPush(
                    title,
                    f"{message_text}\n\nAUTO_MAA 敬上",
                    Config.get(Config.notify_CompanyWebHookBotUrl),
                )

        elif mode == "统计信息":

            # 生成文本通知内容
            formatted = []
            for stage, items in message["drop_statistics"].items():
                formatted.append(f"掉落统计（{stage}）:")
                for item, quantity in items.items():
                    formatted.append(f"  {item}: {quantity}")
            drop_text = "\n".join(formatted)

            formatted = ["招募统计:"]
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
            if Config.get(Config.notify_IfSendStatistic):

                if Config.get(Config.notify_IfSendMail):
                    Notify.send_mail(
                        "网页", title, message_html, Config.get(Config.notify_ToAddress)
                    )

                if Config.get(Config.notify_IfServerChan):
                    Notify.ServerChanPush(
                        title,
                        f"{serverchan_message}\n\nAUTO_MAA 敬上",
                        Config.get(Config.notify_ServerChanKey),
                        Config.get(Config.notify_ServerChanTag),
                        Config.get(Config.notify_ServerChanChannel),
                    )

                if Config.get(Config.notify_IfCompanyWebHookBot):
                    Notify.CompanyWebHookBotPush(
                        title,
                        f"{message_text}\n\nAUTO_MAA 敬上",
                        Config.get(Config.notify_CompanyWebHookBotUrl),
                    )

            # 发送用户单独通知
            if (
                user_data["Notify"]["Enabled"]
                and user_data["Notify"]["IfSendStatistic"]
            ):

                # 发送邮件通知
                if user_data["Notify"]["IfSendMail"]:
                    if user_data["Notify"]["ToAddress"]:
                        Notify.send_mail(
                            "网页",
                            title,
                            message_html,
                            user_data["Notify"]["ToAddress"],
                        )
                    else:
                        logger.error(
                            f"{self.name} | 用户邮箱地址为空，无法发送用户单独的邮件通知"
                        )

                # 发送ServerChan通知
                if user_data["Notify"]["IfServerChan"]:
                    if user_data["Notify"]["ServerChanKey"]:
                        Notify.ServerChanPush(
                            title,
                            f"{serverchan_message}\n\nAUTO_MAA 敬上",
                            user_data["Notify"]["ServerChanKey"],
                            user_data["Notify"]["ServerChanTag"],
                            user_data["Notify"]["ServerChanChannel"],
                        )
                    else:
                        logger.error(
                            f"{self.name} |用户ServerChan密钥为空，无法发送用户单独的ServerChan通知"
                        )

                # 推送CompanyWebHookBot通知
                if user_data["Notify"]["IfCompanyWebHookBot"]:
                    if user_data["Notify"]["CompanyWebHookBotUrl"]:
                        Notify.CompanyWebHookBotPush(
                            title,
                            f"{message_text}\n\nAUTO_MAA 敬上",
                            user_data["Notify"]["CompanyWebHookBotUrl"],
                        )
                    else:
                        logger.error(
                            f"{self.name} |用户CompanyWebHookBot密钥为空，无法发送用户单独的CompanyWebHookBot通知"
                        )

        elif mode == "公招六星":

            # 生成HTML通知内容
            template = env.get_template("MAA_six_star.html")

            message_html = template.render(message)

            # 发送全局通知
            if Config.get(Config.notify_IfSendSixStar):

                if Config.get(Config.notify_IfSendMail):
                    Notify.send_mail(
                        "网页", title, message_html, Config.get(Config.notify_ToAddress)
                    )

                if Config.get(Config.notify_IfServerChan):
                    Notify.ServerChanPush(
                        title,
                        "好羡慕~\n\nAUTO_MAA 敬上",
                        Config.get(Config.notify_ServerChanKey),
                        Config.get(Config.notify_ServerChanTag),
                        Config.get(Config.notify_ServerChanChannel),
                    )

                if Config.get(Config.notify_IfCompanyWebHookBot):
                    Notify.CompanyWebHookBotPush(
                        title,
                        "好羡慕~\n\nAUTO_MAA 敬上",
                        Config.get(Config.notify_CompanyWebHookBotUrl),
                    )

            # 发送用户单独通知
            if user_data["Notify"]["Enabled"] and user_data["Notify"]["IfSendSixStar"]:

                # 发送邮件通知
                if user_data["Notify"]["IfSendMail"]:
                    if user_data["Notify"]["ToAddress"]:
                        Notify.send_mail(
                            "网页",
                            title,
                            message_html,
                            user_data["Notify"]["ToAddress"],
                        )
                    else:
                        logger.error(
                            f"{self.name} | 用户邮箱地址为空，无法发送用户单独的邮件通知"
                        )

                # 发送ServerChan通知
                if user_data["Notify"]["IfServerChan"]:

                    if user_data["Notify"]["ServerChanKey"]:
                        Notify.ServerChanPush(
                            title,
                            "好羡慕~\n\nAUTO_MAA 敬上",
                            user_data["Notify"]["ServerChanKey"],
                            user_data["Notify"]["ServerChanTag"],
                            user_data["Notify"]["ServerChanChannel"],
                        )
                    else:
                        logger.error(
                            f"{self.name} |用户ServerChan密钥为空，无法发送用户单独的ServerChan通知"
                        )

                # 推送CompanyWebHookBot通知
                if user_data["Notify"]["IfCompanyWebHookBot"]:
                    if user_data["Notify"]["CompanyWebHookBotUrl"]:
                        Notify.CompanyWebHookBotPush(
                            title,
                            "好羡慕~\n\nAUTO_MAA 敬上",
                            user_data["Notify"]["CompanyWebHookBotUrl"],
                        )
                    else:
                        logger.error(
                            f"{self.name} |用户CompanyWebHookBot密钥为空，无法发送用户单独的CompanyWebHookBot通知"
                        )
        return None
