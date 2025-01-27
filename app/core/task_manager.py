#   <AUTO_MAA:A MAA Multi Account Management and Automation Tool>
#   Copyright © <2024> <DLmaster361>

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

#   DLmaster_361@163.com

"""
AUTO_MAA
AUTO_MAA业务调度器
v4.2
作者：DLmaster_361
"""

from loguru import logger
from PySide6.QtCore import QThread, QObject, Signal
from qfluentwidgets import Dialog
from pathlib import Path
from typing import Dict, Union

from .config import Config
from .main_info_bar import MainInfoBar
from app.models import MaaManager


class Task(QThread):
    """业务线程"""

    push_info_bar = Signal(str, str, str, int)
    question = Signal(str, str)
    question_response = Signal(bool)
    update_user_info = Signal(Path, list, list, list, list, list, list)
    create_task_list = Signal(list)
    create_user_list = Signal(list)
    update_task_list = Signal(list)
    update_user_list = Signal(list)
    update_log_text = Signal(str)
    accomplish = Signal(list)

    def __init__(
        self,
        mode: str,
        name: str,
        info: Dict[str, Dict[str, Union[str, int, bool]]],
    ):
        super(Task, self).__init__()

        self.mode = mode
        self.name = name
        self.info = info

        self.logs = []

        self.question_response.connect(lambda: print("response"))

    def run(self):

        if "设置MAA" in self.mode:

            logger.info(f"任务开始：设置{self.name}")
            self.push_info_bar.emit("info", "设置MAA", self.name, 3000)

            self.task = MaaManager(
                self.mode,
                Config.app_path / f"config/MaaConfig/{self.name}",
                (
                    None
                    if "全局" in self.mode
                    else Config.app_path
                    / f"config/MaaConfig/{self.name}/beta/{self.info["SetMaaInfo"]["UserId"]}/{self.info["SetMaaInfo"]["SetType"]}"
                ),
            )
            self.task.push_info_bar.connect(self.push_info_bar.emit)
            self.task.accomplish.connect(lambda: self.accomplish.emit([]))

            self.task.run()

        else:

            self.member_dict = self.search_member()
            self.task_list = [
                [value, "等待"]
                for _, value in self.info["Queue"].items()
                if value != "禁用"
            ]

            self.create_task_list.emit(self.task_list)

            for i in range(len(self.task_list)):

                if self.isInterruptionRequested():
                    break

                self.task_list[i][1] = "运行"
                self.update_task_list.emit(self.task_list)

                if self.task_list[i][0] in Config.running_list:

                    self.task_list[i][1] = "跳过"
                    self.update_task_list.emit(self.task_list)
                    logger.info(f"跳过任务：{self.task_list[i][0]}")
                    self.push_info_bar.emit(
                        "info", "跳过任务", self.task_list[i][0], 3000
                    )
                    continue

                Config.running_list.append(self.task_list[i][0])
                logger.info(f"任务开始：{self.task_list[i][0]}")
                self.push_info_bar.emit("info", "任务开始", self.task_list[i][0], 3000)

                if self.member_dict[self.task_list[i][0]][0] == "Maa":

                    self.task = MaaManager(
                        self.mode[0:4],
                        self.member_dict[self.task_list[i][0]][1],
                    )

                    self.task.question.connect(self.question.emit)
                    self.question_response.disconnect()
                    self.question_response.connect(self.task.question_response.emit)
                    self.task.push_info_bar.connect(self.push_info_bar.emit)
                    self.task.create_user_list.connect(self.create_user_list.emit)
                    self.task.update_user_list.connect(self.update_user_list.emit)
                    self.task.update_log_text.connect(self.update_log_text.emit)
                    self.task.update_user_info.connect(
                        lambda modes, uids, days, lasts, notes, numbs: self.update_user_info.emit(
                            self.member_dict[self.task_list[i][0]][1],
                            modes,
                            uids,
                            days,
                            lasts,
                            notes,
                            numbs,
                        )
                    )
                    self.task.accomplish.connect(
                        lambda log: self.save_log(self.task_list[i][0], log)
                    )

                    self.task.run()

                Config.running_list.remove(self.task_list[i][0])

                self.task_list[i][1] = "完成"
                logger.info(f"任务完成：{self.task_list[i][0]}")
                self.push_info_bar.emit("info", "任务完成", self.task_list[i][0], 3000)

            self.accomplish.emit(self.logs)

    def search_member(self) -> dict:
        """搜索所有脚本实例并固定相关配置信息"""

        member_dict = {}

        if (Config.app_path / "config/MaaConfig").exists():
            for subdir in (Config.app_path / "config/MaaConfig").iterdir():
                if subdir.is_dir():

                    member_dict[subdir.name] = ["Maa", subdir]

        return member_dict

    def save_log(self, name: str, log: dict):
        """保存保存任务结果"""

        self.logs.append([name, log])


class TaskManager(QObject):
    """业务调度器"""

    create_gui = Signal(Task)
    connect_gui = Signal(Task)
    push_info_bar = Signal(str, str, str, int)

    def __init__(self):
        super(TaskManager, self).__init__()

        self.task_list: Dict[str, Task] = {}

    def add_task(
        self, mode: str, name: str, info: Dict[str, Dict[str, Union[str, int, bool]]]
    ):
        """添加任务"""

        if name in Config.running_list or name in self.task_list:

            logger.warning(f"任务已存在：{name}")
            MainInfoBar.push_info_bar("warning", "任务已存在", name, 5000)
            return None

        logger.info(f"任务开始：{name}")
        MainInfoBar.push_info_bar("info", "任务开始", name, 3000)

        Config.running_list.append(name)
        self.task_list[name] = Task(mode, name, info)
        self.task_list[name].question.connect(
            lambda title, content: self.push_dialog(name, title, content)
        )
        self.task_list[name].push_info_bar.connect(MainInfoBar.push_info_bar)
        self.task_list[name].update_user_info.connect(Config.change_user_info)
        self.task_list[name].accomplish.connect(
            lambda logs: self.remove_task(name, logs)
        )

        if "新窗口" in mode:
            self.create_gui.emit(self.task_list[name])

        elif "主窗口" in mode:
            self.connect_gui.emit(self.task_list[name])

        self.task_list[name].start()

    def stop_task(self, name: str):
        """中止任务"""

        logger.info(f"中止任务：{name}")
        MainInfoBar.push_info_bar("info", "中止任务", name, 3000)

        if name == "ALL":

            for name in self.task_list:

                self.task_list[name].task.requestInterruption()
                self.task_list[name].requestInterruption()
                self.task_list[name].quit()
                self.task_list[name].wait()

        elif name in self.task_list:

            self.task_list[name].task.requestInterruption()
            self.task_list[name].requestInterruption()
            self.task_list[name].quit()
            self.task_list[name].wait()

    def remove_task(self, name: str, logs: str):
        """移除任务标记"""

        logger.info(f"任务结束：{name}")
        MainInfoBar.push_info_bar("info", "任务结束", name, 3000)

        if len(logs) > 0:
            time = logs[0][1]["Time"]
            history = ""
            for log in logs:
                Config.save_history(log[0], log[1])
                history += (
                    f"任务名称：{log[0]}，{log[1]["History"].replace("\n","\n    ")}\n"
                )
            Config.save_history(name, {"Time": time, "History": history})

        self.task_list.pop(name)
        Config.running_list.remove(name)

    def push_dialog(self, name: str, title: str, content: str):
        """推送对话框"""

        choice = Dialog(title, content, None)
        choice.yesButton.setText("是")
        choice.cancelButton.setText("否")

        self.task_list[name].question_response.emit(bool(choice.exec_()))


Task_manager = TaskManager()
