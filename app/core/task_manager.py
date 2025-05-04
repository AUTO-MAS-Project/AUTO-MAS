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
AUTO_MAA业务调度器
v4.3
作者：DLmaster_361
"""

from loguru import logger
from PySide6.QtCore import QThread, QObject, Signal
from qfluentwidgets import MessageBox
from datetime import datetime
from packaging import version
from typing import Dict, Union

from .config import Config
from .main_info_bar import MainInfoBar
from .network import Network
from app.models import MaaManager
from app.services import System


class Task(QThread):
    """业务线程"""

    check_maa_version = Signal(str)
    push_info_bar = Signal(str, str, str, int)
    question = Signal(str, str)
    question_response = Signal(bool)
    update_user_info = Signal(str, dict)
    create_task_list = Signal(list)
    create_user_list = Signal(list)
    update_task_list = Signal(list)
    update_user_list = Signal(list)
    update_log_text = Signal(str)
    accomplish = Signal(list)

    def __init__(
        self, mode: str, name: str, info: Dict[str, Dict[str, Union[str, int, bool]]]
    ):
        super(Task, self).__init__()

        self.mode = mode
        self.name = name
        self.info = info

        self.logs = []

        self.question_response.connect(lambda: print("response"))

    @logger.catch
    def run(self):

        if "设置MAA" in self.mode:

            logger.info(f"任务开始：设置{self.name}")
            self.push_info_bar.emit("info", "设置MAA", self.name, 3000)

            self.task = MaaManager(
                self.mode,
                Config.member_dict[self.name],
                (None if "全局" in self.mode else self.info["SetMaaInfo"]["Path"]),
            )
            self.task.check_maa_version.connect(self.check_maa_version.emit)
            self.task.push_info_bar.connect(self.push_info_bar.emit)
            self.task.accomplish.connect(lambda: self.accomplish.emit([]))

            self.task.run()

        else:

            self.task_list = [
                [
                    (
                        value
                        if Config.member_dict[value]["Config"].get(
                            Config.member_dict[value]["Config"].MaaSet_Name
                        )
                        == ""
                        else f"{value} - {Config.member_dict[value]["Config"].get(Config.member_dict[value]["Config"].MaaSet_Name)}"
                    ),
                    "等待",
                    value,
                ]
                for _, value in sorted(
                    self.info["Queue"].items(), key=lambda x: int(x[0][7:])
                )
                if value != "禁用"
            ]

            self.create_task_list.emit(self.task_list)

            for task in self.task_list:

                if self.isInterruptionRequested():
                    break

                task[1] = "运行"
                self.update_task_list.emit(self.task_list)

                if task[2] in Config.running_list:

                    task[1] = "跳过"
                    self.update_task_list.emit(self.task_list)
                    logger.info(f"跳过任务：{task[0]}")
                    self.push_info_bar.emit("info", "跳过任务", task[0], 3000)
                    continue

                Config.running_list.append(task[2])
                logger.info(f"任务开始：{task[0]}")
                self.push_info_bar.emit("info", "任务开始", task[0], 3000)

                if Config.member_dict[task[2]]["Type"] == "Maa":

                    self.task = MaaManager(
                        self.mode[0:4],
                        Config.member_dict[task[2]],
                    )

                    self.task.check_maa_version.connect(self.check_maa_version.emit)
                    self.task.question.connect(self.question.emit)
                    self.question_response.disconnect()
                    self.question_response.connect(self.task.question_response.emit)
                    self.task.push_info_bar.connect(self.push_info_bar.emit)
                    self.task.create_user_list.connect(self.create_user_list.emit)
                    self.task.update_user_list.connect(self.update_user_list.emit)
                    self.task.update_log_text.connect(self.update_log_text.emit)
                    self.task.update_user_info.connect(self.update_user_info.emit)
                    self.task.accomplish.connect(
                        lambda log: self.task_accomplish(task[2], log)
                    )

                    self.task.run()

                Config.running_list.remove(task[2])

                task[1] = "完成"
                self.update_task_list.emit(self.task_list)
                logger.info(f"任务完成：{task[0]}")
                self.push_info_bar.emit("info", "任务完成", task[0], 3000)

            self.accomplish.emit(self.logs)

    def task_accomplish(self, name: str, log: dict):
        """保存保存任务结果"""

        self.logs.append([name, log])
        self.task.deleteLater()


class _TaskManager(QObject):
    """业务调度器"""

    create_gui = Signal(Task)
    connect_gui = Signal(Task)

    def __init__(self):
        super(_TaskManager, self).__init__()

        self.task_dict: Dict[str, Task] = {}

    def add_task(
        self, mode: str, name: str, info: Dict[str, Dict[str, Union[str, int, bool]]]
    ):
        """添加任务"""

        if name in Config.running_list or name in self.task_dict:

            logger.warning(f"任务已存在：{name}")
            MainInfoBar.push_info_bar("warning", "任务已存在", name, 5000)
            return None

        logger.info(f"任务开始：{name}")
        MainInfoBar.push_info_bar("info", "任务开始", name, 3000)

        Config.running_list.append(name)
        self.task_dict[name] = Task(mode, name, info)
        self.task_dict[name].check_maa_version.connect(self.check_maa_version)
        self.task_dict[name].question.connect(
            lambda title, content: self.push_dialog(name, title, content)
        )
        self.task_dict[name].push_info_bar.connect(MainInfoBar.push_info_bar)
        self.task_dict[name].update_user_info.connect(Config.change_user_info)
        self.task_dict[name].accomplish.connect(
            lambda logs: self.remove_task(mode, name, logs)
        )

        if "新调度台" in mode:
            self.create_gui.emit(self.task_dict[name])

        elif "主调度台" in mode:
            self.connect_gui.emit(self.task_dict[name])

        self.task_dict[name].start()

    def stop_task(self, name: str):
        """中止任务"""

        logger.info(f"中止任务：{name}")
        MainInfoBar.push_info_bar("info", "中止任务", name, 3000)

        if name == "ALL":

            for name in self.task_dict:

                self.task_dict[name].task.requestInterruption()
                self.task_dict[name].requestInterruption()
                self.task_dict[name].quit()
                self.task_dict[name].wait()

        elif name in self.task_dict:

            self.task_dict[name].task.requestInterruption()
            self.task_dict[name].requestInterruption()
            self.task_dict[name].quit()
            self.task_dict[name].wait()

    def remove_task(self, mode: str, name: str, logs: list):
        """任务结束后的处理"""

        logger.info(f"任务结束：{name}")
        MainInfoBar.push_info_bar("info", "任务结束", name, 3000)

        self.task_dict[name].deleteLater()
        self.task_dict.pop(name)
        Config.running_list.remove(name)

        if "调度队列" in name and "人工排查" not in mode:

            if len(logs) > 0:
                time = logs[0][1]["Time"]
                history = ""
                for log in logs:
                    history += f"任务名称：{log[0]}，{log[1]["History"].replace("\n","\n    ")}\n"
                Config.save_history(name, {"Time": time, "History": history})
            else:
                Config.save_history(
                    name,
                    {
                        "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "History": "没有任务被执行",
                    },
                )

            if (
                Config.queue_dict[name]["Config"].get(
                    Config.queue_dict[name]["Config"].queueSet_AfterAccomplish
                )
                != "None"
            ):

                from app.ui import ProgressRingMessageBox

                mode_book = {
                    "Shutdown": "关机",
                    "Hibernate": "休眠",
                    "Sleep": "睡眠",
                    "KillSelf": "关闭AUTO_MAA",
                }

                choice = ProgressRingMessageBox(
                    Config.main_window,
                    f"{mode_book[Config.queue_dict[name]["Config"].get(Config.queue_dict[name]["Config"].queueSet_AfterAccomplish)]}倒计时",
                )
                if choice.exec():
                    System.set_power(
                        Config.queue_dict[name]["Config"].get(
                            Config.queue_dict[name]["Config"].queueSet_AfterAccomplish
                        )
                    )

    def check_maa_version(self, v: str):
        """检查MAA版本"""

        Network.set_info(
            mode="get",
            url="https://mirrorchyan.com/api/resources/MAA/latest?user_agent=AutoMaaGui&os=win&arch=x64&channel=stable",
        )
        Network.start()
        Network.loop.exec()
        if Network.stutus_code == 200:
            maa_info = Network.response_json
        else:
            logger.warning(f"获取MAA版本信息时出错：{Network.error_message}")
            MainInfoBar.push_info_bar(
                "warning",
                "获取MAA版本信息时出错",
                f"网络错误：{Network.stutus_code}",
                5000,
            )
            return None

        if version.parse(maa_info["data"]["version_name"]) > version.parse(v):

            logger.info(
                f"检测到MAA版本过低：{v}，最新版本：{maa_info['data']['version_name']}"
            )
            MainInfoBar.push_info_bar(
                "info",
                "MAA版本过低",
                f"当前版本：{v}，最新稳定版：{maa_info['data']['version_name']}",
                -1,
            )

    def push_dialog(self, name: str, title: str, content: str):
        """推送对话框"""

        choice = MessageBox(title, content, Config.main_window)
        choice.yesButton.setText("是")
        choice.cancelButton.setText("否")

        self.task_dict[name].question_response.emit(bool(choice.exec()))


TaskManager = _TaskManager()
