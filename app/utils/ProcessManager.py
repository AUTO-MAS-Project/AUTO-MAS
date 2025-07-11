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
AUTO_MAA进程管理组件
v4.4
作者：DLmaster_361
"""


import psutil
import subprocess
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import QTimer, QObject, Signal


class ProcessManager(QObject):
    """进程监视器类，用于跟踪主进程及其所有子进程的状态"""

    processClosed = Signal()

    def __init__(self):
        super().__init__()

        self.main_pid = None
        self.tracked_pids = set()

        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self.check_processes)

    def open_process(
        self,
        path: Path,
        args: list = [],
        tracking_time: int = 60,
    ) -> int:
        """
        启动一个新进程并返回其pid，并开始监视该进程

        :param path: 可执行文件的路径
        :param args: 启动参数列表
        :param tracking_time: 子进程追踪持续时间（秒）
        :return: 新进程的PID
        """

        process = subprocess.Popen(
            [path, *args],
            cwd=path.parent,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        self.start_monitoring(process.pid, tracking_time)

    def start_monitoring(self, pid: int, tracking_time: int = 60) -> None:
        """
        启动进程监视器，跟踪指定的主进程及其子进程

        :param pid: 被监视进程的PID
        :param tracking_time: 子进程追踪持续时间（秒）
        """

        self.clear()

        self.main_pid = pid
        self.tracking_time = tracking_time

        # 扫描并记录所有相关进程
        try:
            # 获取主进程及其子进程
            main_proc = psutil.Process(self.main_pid)
            self.tracked_pids.add(self.main_pid)

            # 递归获取所有子进程
            if tracking_time:
                for child in main_proc.children(recursive=True):
                    self.tracked_pids.add(child.pid)

        except psutil.NoSuchProcess:
            pass

        # 启动持续追踪机制
        self.start_time = datetime.now()
        self.check_timer.start(100)

    def check_processes(self) -> None:
        """检查跟踪的进程是否仍在运行，并更新子进程列表"""

        # 仅在时限内持续更新跟踪的进程列表，发现新的子进程
        if (datetime.now() - self.start_time).total_seconds() < self.tracking_time:

            current_pids = set(self.tracked_pids)
            for pid in current_pids:
                try:
                    proc = psutil.Process(pid)
                    for child in proc.children():
                        if child.pid not in self.tracked_pids:
                            # 新发现的子进程
                            self.tracked_pids.add(child.pid)
                except psutil.NoSuchProcess:
                    continue

        if not self.is_running():
            self.clear()
            self.processClosed.emit()

    def is_running(self) -> bool:
        """检查所有跟踪的进程是否还在运行"""

        for pid in self.tracked_pids:
            try:
                proc = psutil.Process(pid)
                if proc.is_running():
                    return True
            except psutil.NoSuchProcess:
                continue

        return False

    def kill(self, if_force: bool = False) -> None:
        """停止监视器并中止所有跟踪的进程"""

        self.check_timer.stop()

        for pid in self.tracked_pids:
            try:
                proc = psutil.Process(pid)
                if if_force:
                    kill_process = subprocess.Popen(
                        ["taskkill", "/F", "/T", "/PID", str(pid)],
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    kill_process.wait()
                proc.terminate()
            except psutil.NoSuchProcess:
                continue

        if self.main_pid:
            self.processClosed.emit()
        self.clear()

    def clear(self) -> None:
        """清空跟踪的进程列表"""

        self.main_pid = None
        self.check_timer.stop()
        self.tracked_pids.clear()
