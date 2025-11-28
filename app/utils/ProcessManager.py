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


import os
import psutil
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


@dataclass
class ProcessInfo:
    pid: int | None = None
    name: str | None = None
    exe: str | None = None
    cmdline: list[str] | None = None


def match_process(proc: psutil.Process, target: ProcessInfo) -> bool:
    """检查进程是否与目标进程信息匹配"""

    try:
        if target.pid is not None and proc.pid != target.pid:
            return False
        if target.name is not None and proc.name().lower() != target.name.lower():
            return False
        if target.exe is not None and proc.exe().lower() != target.exe.lower():
            return False
        if target.cmdline is not None and proc.cmdline() != target.cmdline:
            return False
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False

    return True


class ProcessManager:
    """进程监视器类, 用于跟踪主进程及其所有子进程的状态"""

    def __init__(self):
        super().__init__()

        self.process: asyncio.subprocess.Process | None = None
        self.target_process: psutil.Process | None = None

    @property
    def main_pid(self) -> int | None:
        """获取主进程的 PID"""

        if self.target_process is not None:
            return self.target_process.pid
        if self.process is not None:
            return self.process.pid
        return None

    async def open_process(
        self, cmd: list[str], target_process: ProcessInfo | None = None
    ) -> None:
        """
        使用命令行启动子进程, 多级派生类型进程需要目标进程信息进行跟踪

        Args:
            path (Path): 可执行文件路径
            args (list, optional): 启动参数列表
            target_process (TargetProcess | None, optional): 期望目标进程信息
        """

        if await self.is_running():
            raise RuntimeError("无法同时管理多个进程")

        if (
            target_process is not None
            and target_process.pid is None
            and target_process.name is None
            and target_process.cmdline is None
            and target_process.exe is None
        ):
            raise ValueError("目标进程信息不完整")

        await self.clear()

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=Path(cmd[0]).parent if Path(cmd[0]).is_file() else None,
        )

        if target_process is not None:

            await self.track_process(
                target_process, datetime.now() + timedelta(seconds=60)
            )

    async def open_protocol(
        self, protocol_url: str, target_process: ProcessInfo
    ) -> None:
        """
        使用自定义协议启动子进程, 需要目标进程信息进行跟踪

        Args:
            protocol_url (str): 自定义协议 URL
            target_process (ProcessInfo): 期望目标进程信息
        """

        # 使用 os.startfile 或 subprocess 启动协议
        try:
            # 在 Windows 上使用 os.startfile 打开协议
            if os.name == "nt":
                os.startfile(protocol_url)
            else:
                raise NotImplementedError("仅支持 Windows 平台的自定义协议启动")
        except Exception as e:
            raise RuntimeError(f"无法启动协议 {protocol_url}: {e}")

        await self.track_process(target_process, datetime.now() + timedelta(seconds=60))

    async def track_process(
        self, target_process: ProcessInfo, track_end_time: datetime
    ) -> None:
        """更新子进程列表"""

        while datetime.now() < track_end_time:
            for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
                try:
                    if match_process(proc, target_process):
                        self.target_process = proc
                        return
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("未能在指定时间内找到目标进程")

    async def is_running(self) -> bool:
        """检查当前管理的进程是否仍在运行"""

        if self.target_process is not None:
            return self.target_process.is_running()
        if self.process is not None:
            return self.process.returncode is None
        return False

    async def kill(self, if_force: bool = False) -> None:
        """停止监视器并中止所有跟踪的进程"""

        if self.target_process is not None and self.target_process.is_running():
            try:
                if if_force:
                    self.target_process.kill()
                else:
                    self.target_process.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if self.process is not None and self.process.returncode is None:
            if if_force:
                self.process.kill()
            else:
                self.process.terminate()
            await self.process.wait()

        await self.clear()

    async def clear(self) -> None:
        """清空跟踪的进程信息"""

        self.process = None
        self.target_process = None
