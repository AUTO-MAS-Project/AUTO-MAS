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
AUTO_MAA主业务定时器
v4.2
作者：DLmaster_361
"""

from loguru import logger
from PySide6.QtWidgets import QWidget
from PySide6 import QtCore
import json
import datetime

from .config import AppConfig
from .task_manager import TaskManager
from app.services import SystemHandler


class MainTimer(QWidget):

    def __init__(
        self,
        config: AppConfig,
        system: SystemHandler,
        task_manager: TaskManager,
        parent=None,
    ):
        super().__init__(parent)

        self.config = config
        self.system = system
        self.task_manager = task_manager

        self.Timer = QtCore.QTimer()
        self.Timer.timeout.connect(self.timed_start)
        self.Timer.timeout.connect(self.set_silence)
        self.Timer.start(1000)

    def timed_start(self):
        """定时启动代理任务"""

        # 获取定时列表
        queue_list = self.search_queue()

        for i in queue_list:

            name, info = i

            if not info["QueueSet"]["Enabled"]:
                continue

            history = self.config.get_history(name)

            time_set = [
                info["Time"][f"TimeSet_{_}"]
                for _ in range(10)
                if info["Time"][f"TimeEnabled_{_}"]
            ]
            # 按时间调起代理任务
            curtime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            if (
                curtime[11:16] in time_set
                and curtime != history["Time"][:16]
                and name not in self.config.running_list
            ):

                logger.info(f"按时间调起任务：{name}")
                self.task_manager.add_task("运行队列", name, info)

    def set_silence(self):
        """设置静默模式"""
        # # 临时
        # windows = self.system.get_window_info()
        # if any(emulator_path in _ for _ in windows):
        #     try:
        #         pyautogui.hotkey(*boss_key)
        #     except pyautogui.FailSafeException as e:
        # 执行日志记录，暂时缺省
        logger.debug(self.config.running_list)

    def set_last_time(self):
        """设置上次运行时间"""

        pass

    def search_queue(self) -> list:
        """搜索所有调度队列实例"""

        queue_list = []

        if (self.config.app_path / "config/QueueConfig").exists():
            for json_file in (self.config.app_path / "config/QueueConfig").glob(
                "*.json"
            ):
                with json_file.open("r", encoding="utf-8") as f:
                    info = json.load(f)
                queue_list.append([json_file.stem, info])

        return queue_list
