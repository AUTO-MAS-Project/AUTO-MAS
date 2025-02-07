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
AUTO_MAA系统服务
v4.2
作者：DLmaster_361
"""

from loguru import logger
from PySide6.QtWidgets import QWidget
import sys
import ctypes
import win32gui
import win32process
import winreg
import psutil
import subprocess

from app.core import Config


class _SystemHandler:

    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001

    def __init__(self, main_window: QWidget = None):

        self.main_window = main_window

        self.set_Sleep()
        self.set_SelfStart()

    def set_Sleep(self):
        """同步系统休眠状态"""

        if Config.global_config.get(Config.global_config.function_IfAllowSleep):
            # 设置系统电源状态
            ctypes.windll.kernel32.SetThreadExecutionState(
                self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED
            )
        else:
            # 恢复系统电源状态
            ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS)

    def set_SelfStart(self):
        """同步开机自启"""

        if (
            Config.global_config.get(Config.global_config.start_IfSelfStart)
            and not self.is_startup()
        ):
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                winreg.KEY_SET_VALUE,
                winreg.KEY_ALL_ACCESS | winreg.KEY_WRITE | winreg.KEY_CREATE_SUB_KEY,
            )
            winreg.SetValueEx(key, "AUTO_MAA", 0, winreg.REG_SZ, Config.app_path_sys)
            winreg.CloseKey(key)
        elif (
            not Config.global_config.get(Config.global_config.start_IfSelfStart)
            and self.is_startup()
        ):
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                winreg.KEY_SET_VALUE,
                winreg.KEY_ALL_ACCESS | winreg.KEY_WRITE | winreg.KEY_CREATE_SUB_KEY,
            )
            winreg.DeleteValue(key, "AUTO_MAA")
            winreg.CloseKey(key)

    def set_power(self, mode):

        if sys.platform.startswith("win"):

            if mode == "None":

                logger.info("不执行系统电源操作")

            elif mode == "Shutdown":

                logger.info("执行关机操作")
                subprocess.run(["shutdown", "/s", "/t", "0"])

            elif mode == "Hibernate":

                logger.info("执行休眠操作")
                subprocess.run(["shutdown", "/h"])

            elif mode == "Sleep":

                logger.info("执行睡眠操作")
                subprocess.run(
                    ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]
                )

            elif mode == "KillSelf":

                self.main_window.close()

        elif sys.platform.startswith("linux"):

            if mode == "None":

                logger.info("不执行系统电源操作")

            elif mode == "Shutdown":

                logger.info("执行关机操作")
                subprocess.run(["shutdown", "-h", "now"])

            elif mode == "Hibernate":

                logger.info("执行休眠操作")
                subprocess.run(["systemctl", "hibernate"])

            elif mode == "Sleep":

                logger.info("执行睡眠操作")
                subprocess.run(["systemctl", "suspend"])

            elif mode == "KillSelf":

                self.main_window.close()

    def is_startup(self):
        """判断程序是否已经开机自启"""

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        )

        try:
            value, _ = winreg.QueryValueEx(key, "AUTO_MAA")
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            winreg.CloseKey(key)
            return False

    def get_window_info(self):
        """获取当前窗口信息"""

        def callback(hwnd, window_info):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                process = psutil.Process(pid)
                window_info.append((win32gui.GetWindowText(hwnd), process.exe()))
            return True

        window_info = []
        win32gui.EnumWindows(callback, window_info)
        return window_info


System = _SystemHandler()
