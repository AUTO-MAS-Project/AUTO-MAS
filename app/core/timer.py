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
from PySide6.QtCore import QTimer
import json
from datetime import datetime
import pyautogui

from .config import Config
from .task_manager import Task_manager
from app.services import System


class MainTimer(QWidget):

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent)

        self.if_FailSafeException = False

        self.Timer = QTimer()
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

            history = Config.get_history(name)

            time_set = [
                info["Time"][f"TimeSet_{_}"]
                for _ in range(10)
                if info["Time"][f"TimeEnabled_{_}"]
            ]
            # 按时间调起代理任务
            curtime = datetime.now().strftime("%Y-%m-%d %H:%M")
            if (
                curtime[11:16] in time_set
                and curtime != history["Time"][:16]
                and name not in Config.running_list
            ):

                logger.info(f"定时任务：{name}")
                Task_manager.add_task("自动代理_新窗口", name, info)

    def set_silence(self):
        """设置静默模式"""

        windows = System.get_window_info()
        if any(
            str(emulator_path) in window
            for window in windows
            for emulator_path in Config.silence_list
        ):
            try:
                pyautogui.hotkey(
                    *[
                        _.strip().lower()
                        for _ in Config.global_config.get(
                            Config.global_config.function_BossKey
                        ).split("+")
                    ]
                )
            except pyautogui.FailSafeException as e:
                if not self.if_FailSafeException:
                    logger.warning(f"FailSafeException: {e}")
                    self.if_FailSafeException = True

    def search_queue(self) -> list:
        """搜索所有调度队列实例"""

        queue_list = []

        if (Config.app_path / "config/QueueConfig").exists():
            for json_file in (Config.app_path / "config/QueueConfig").glob("*.json"):
                with json_file.open("r", encoding="utf-8") as f:
                    info = json.load(f)
                queue_list.append([json_file.stem, info])

        return queue_list


Main_timer = MainTimer()
