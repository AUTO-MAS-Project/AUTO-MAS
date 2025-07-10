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
AUTO_MAA系统服务
v4.4
作者：DLmaster_361
"""

from loguru import logger
from PySide6.QtWidgets import QApplication
import sys
import ctypes
import win32gui
import win32process
import winreg
import psutil
import subprocess
from pathlib import Path

from app.core import Config


class _SystemHandler:

    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001

    def __init__(self):

        self.set_Sleep()
        self.set_SelfStart()

    def set_Sleep(self) -> None:
        """同步系统休眠状态"""

        if Config.get(Config.function_IfAllowSleep):
            # 设置系统电源状态
            ctypes.windll.kernel32.SetThreadExecutionState(
                self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED
            )
        else:
            # 恢复系统电源状态
            ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS)

    def set_SelfStart(self) -> bool:
        """同步开机自启"""

        if Config.get(Config.start_IfSelfStart) and not self.is_startup():

            try:

                # 创建任务计划
                result = subprocess.run(
                    [
                        "schtasks",
                        "/create",
                        "/tn",
                        "AUTO_MAA_AutoStart",
                        "/tr",
                        Config.app_path_sys,
                        "/sc",
                        "onlogon",
                        "/rl",
                        "highest",  # 以最高权限运行
                        "/f",  # 强制创建（覆盖现有任务）
                    ],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:
                    logger.info(f"任务计划程序自启动已创建: {Config.app_path_sys}")
                    return True
                else:
                    logger.error(f"创建任务计划失败: {result.stderr}")
                    return False

            except Exception as e:
                logger.error(f"设置任务计划程序自启动失败: {e}")
                return False

        elif not Config.get(Config.start_IfSelfStart) and self.is_startup():

            try:

                result = subprocess.run(
                    ["schtasks", "/delete", "/tn", "AUTO_MAA_AutoStart", "/f"],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:
                    logger.info("任务计划程序自启动已删除")
                    return True
                else:
                    logger.error(f"删除任务计划失败: {result.stderr}")
                    return False

            except Exception as e:
                logger.error(f"删除任务计划程序自启动失败: {e}")
                return False

    def set_power(self, mode) -> None:

        if sys.platform.startswith("win"):

            if mode == "NoAction":

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

                Config.main_window.close()
                QApplication.quit()
                sys.exit(0)

        elif sys.platform.startswith("linux"):

            if mode == "NoAction":

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

                Config.main_window.close()
                QApplication.quit()
                sys.exit(0)

    def is_startup(self) -> bool:
        """判断程序是否已经开机自启"""

        try:
            result = subprocess.run(
                ["schtasks", "/query", "/tn", "AUTO_MAA_AutoStart"],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"检查任务计划程序失败: {e}")
            return False

    def get_window_info(self) -> list:
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

    def kill_process(self, path: Path) -> None:
        """根据路径中止进程"""

        for pid in self.search_pids(path):
            killprocess = subprocess.Popen(
                f"taskkill /F /T /PID {pid}",
                shell=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            killprocess.wait()

    def search_pids(self, path: Path) -> list:
        """根据路径查找进程PID"""

        pids = []
        for proc in psutil.process_iter(["pid", "exe"]):
            try:
                if proc.info["exe"] and proc.info["exe"].lower() == str(path).lower():
                    pids.append(proc.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                # 进程可能在此期间已结束或无法访问，忽略这些异常
                pass
        return pids


System = _SystemHandler()
