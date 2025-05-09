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
AUTO_MAA主业务定时器
v4.3
作者：DLmaster_361
"""

from loguru import logger
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QTimer
from datetime import datetime
import pyautogui

from .config import Config
from .task_manager import TaskManager
from app.services import System


class _MainTimer(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.if_FailSafeException = False

        self.Timer = QTimer()
        self.Timer.timeout.connect(self.timed_start)
        self.Timer.timeout.connect(self.set_silence)
        self.Timer.timeout.connect(self.check_power)
        self.Timer.start(1000)
        self.LongTimer = QTimer()
        self.LongTimer.timeout.connect(self.long_timed_task)
        self.LongTimer.start(3600000)

    def long_timed_task(self):
        """长时间定期检定任务"""

        Config.get_gameid()
        Config.main_window.setting.show_notice()
        if Config.get(Config.update_IfAutoUpdate):
            Config.main_window.setting.check_update()

    def timed_start(self):
        """定时启动代理任务"""

        for name, info in Config.queue_dict.items():

            if not info["Config"].get(info["Config"].queueSet_Enabled):
                continue

            data = info["Config"].toDict()

            time_set = [
                data["Time"][f"TimeSet_{_}"]
                for _ in range(10)
                if data["Time"][f"TimeEnabled_{_}"]
            ]
            # 按时间调起代理任务
            curtime = datetime.now().strftime("%Y-%m-%d %H:%M")
            if (
                curtime[11:16] in time_set
                and curtime
                != info["Config"].get(info["Config"].Data_LastProxyTime)[:16]
                and name not in Config.running_list
            ):

                logger.info(f"定时任务：{name}")
                TaskManager.add_task("自动代理_新调度台", name, data)

    def set_silence(self):
        """设置静默模式"""

        if (
            not Config.if_ignore_silence
            and Config.get(Config.function_IfSilence)
            and Config.get(Config.function_BossKey) != ""
        ):

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
                            for _ in Config.get(Config.function_BossKey).split("+")
                        ]
                    )
                except pyautogui.FailSafeException as e:
                    if not self.if_FailSafeException:
                        logger.warning(f"FailSafeException: {e}")
                        self.if_FailSafeException = True

    def check_power(self):

        if Config.power_signal and not Config.running_list:

            from app.ui import ProgressRingMessageBox

            mode_book = {
                "Shutdown": "关机",
                "Hibernate": "休眠",
                "Sleep": "睡眠",
                "KillSelf": "关闭AUTO_MAA",
            }

            choice = ProgressRingMessageBox(
                Config.main_window, f"{mode_book[Config.power_signal]}倒计时"
            )
            if choice.exec():
                System.set_power(Config.power_signal)
                Config.power_signal = None
            else:
                Config.power_signal = None


MainTimer = _MainTimer()
