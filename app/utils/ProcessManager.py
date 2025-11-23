#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import asyncio
import os
import psutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


class ProcessManager:
    """进程监视器类, 用于跟踪主进程及其所有子进程的状态"""

    def __init__(self):
        super().__init__()

        self.main_pid = None
        self.tracked_pids = set()
        self.check_task = None
        self.track_end_time = datetime.now()

    async def open_process(
        self, path: Path, args: list = [], tracking_time: int = 60
    ) -> None:
        """
        启动一个新进程并返回其pid, 并开始监视该进程

        Parameters
        ----------
        path: 可执行文件的路径
        args: 启动参数列表
        tracking_time: 子进程追踪持续时间（秒）
        """

        process = subprocess.Popen(
            [path, *args],
            cwd=path.parent,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        await self.start_monitoring(process.pid, tracking_time)

    async def open_protocol(
        self, protocol_uri: str, tracking_time: int = 60, process_name: Optional[str] = None
    ) -> None:
        """
        使用自定义协议启动程序并监视该进程

        Parameters
        ----------
        protocol_uri: 自定义协议URL (例如: "Starward://xxxxx")
        tracking_time: 子进程追踪持续时间（秒）
        process_name: 可选，要监视的进程名称（例如: "Starward.exe"）。
                     如果未提供，将尝试从协议中提取或监视所有新启动的进程
        """

        # 记录启动前的进程列表
        before_pids = set(p.pid for p in psutil.process_iter())

        # 使用 os.startfile 或 subprocess 启动协议
        try:
            # 在 Windows 上使用 os.startfile 打开协议
            if os.name == 'nt':
                os.startfile(protocol_uri)
            else:
                raise NotImplementedError("仅支持 Windows 平台的自定义协议启动")
        except Exception as e:
            raise RuntimeError(f"无法启动协议 {protocol_uri}: {e}")

        # 等待一小段时间让进程启动
        await asyncio.sleep(3)

        # 查找新启动的进程
        after_pids = set(p.pid for p in psutil.process_iter())
        new_pids = after_pids - before_pids

        target_pid = None

        # 如果提供了进程名称，查找匹配的进程
        if process_name:
            for pid in new_pids:
                try:
                    proc = psutil.Process(pid)
                    if proc.name().lower() == process_name.lower():
                        target_pid = pid
                        break
                except psutil.NoSuchProcess:
                    continue

            # 如果在新进程中没找到，在所有进程中查找
            if target_pid is None:
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        if proc.info['name'].lower() == process_name.lower():
                            target_pid = proc.info['pid']
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
        else:
            # 如果没有提供进程名称，尝试使用第一个新进程
            if new_pids:
                target_pid = list(new_pids)[0]

        if target_pid:
            await self.start_monitoring(target_pid, tracking_time)
        else:
            raise RuntimeError(f"无法找到由协议 {protocol_uri} 启动的进程")

    async def start_monitoring(self, pid: int, tracking_time: int = 60) -> None:
        """
        启动进程监视器, 跟踪指定的主进程及其子进程

        :param pid: 被监视进程的PID
        :param tracking_time: 子进程追踪持续时间（秒）
        """

        await self.clear()

        self.main_pid = pid
        self.tracking_time = tracking_time

        # 扫描并记录所有相关进程
        try:
            # 获取主进程
            main_proc = psutil.Process(self.main_pid)
            self.tracked_pids.add(self.main_pid)

            # 递归获取所有子进程
            if tracking_time:
                for child in main_proc.children(recursive=True):
                    self.tracked_pids.add(child.pid)

        except psutil.NoSuchProcess:
            pass

        # 启动持续追踪任务
        if tracking_time > 0:
            self.track_end_time = datetime.now() + timedelta(seconds=tracking_time)
            self.check_task = asyncio.create_task(self.track_processes())

    async def track_processes(self) -> None:
        """更新子进程列表"""

        while datetime.now() < self.track_end_time:
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
            await asyncio.sleep(0.1)

    async def is_running(self) -> bool:
        """检查所有跟踪的进程是否还在运行"""

        for pid in self.tracked_pids:
            try:
                proc = psutil.Process(pid)
                if proc.is_running():
                    return True
            except psutil.NoSuchProcess:
                continue

        return False

    async def kill(self, if_force: bool = False) -> None:
        """停止监视器并中止所有跟踪的进程"""

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

        await self.clear()

    async def clear(self) -> None:
        """清空跟踪的进程列表"""

        if self.check_task is not None and not self.check_task.done():
            self.check_task.cancel()

            try:
                await self.check_task
            except asyncio.CancelledError:
                pass

        self.main_pid = None
        self.tracked_pids.clear()
