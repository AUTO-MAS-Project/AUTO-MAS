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
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


from .tools import decode_bytes
from .constants import CREATION_FLAGS


@dataclass
class ProcessInfo:
    pid: int | None = None
    name: str | None = None
    exe: str | None = None
    cmdline: list[str] | None = None


@dataclass
class ProcessResult:
    stdout: str
    stderr: str
    returncode: int


def match_process(proc: psutil.Process, target: ProcessInfo) -> bool:
    """检查进程是否与目标进程信息匹配"""

    try:
        if target.pid is not None and proc.pid != target.pid:
            return False
        if target.name is not None and proc.name() != target.name:
            return False
        if target.exe is not None and Path(proc.exe()) != Path(target.exe):
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
        """主进程的 PID"""

        if self.target_process is not None:
            return self.target_process.pid
        if self.process is not None:
            return self.process.pid
        return None

    @property
    def main_process(self) -> psutil.Process | asyncio.subprocess.Process | None:
        """主进程对象"""

        if self.target_process is not None:
            return self.target_process
        if self.process is not None:
            return self.process
        return None

    async def open_process(
        self,
        program: Path | str,
        *args: str,
        cwd: Path | None = None,
        target_process: ProcessInfo | None = None,
        capture_output: bool = False,
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
            program,
            *args,
            cwd=cwd or (Path(program).parent if Path(program).is_file() else None),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=(
                asyncio.subprocess.PIPE
                if capture_output and target_process is None
                else asyncio.subprocess.DEVNULL
            ),
            stderr=(
                asyncio.subprocess.STDOUT
                if capture_output and target_process is None
                else asyncio.subprocess.DEVNULL
            ),
            creationflags=CREATION_FLAGS,
        )

        if target_process is not None:

            await self.search_process(
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

        await self.search_process(
            target_process, datetime.now() + timedelta(seconds=60)
        )

    async def search_process(
        self, target_process: ProcessInfo, search_end_time: datetime
    ) -> None:
        """查找目标进程"""

        while datetime.now() < search_end_time:
            for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
                try:
                    if match_process(proc, target_process):
                        self.target_process = proc
                        return
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("未能在限定时间内找到目标进程")

    async def is_running(self) -> bool:
        """检查当前管理的进程是否仍在运行"""

        if self.target_process is not None:
            return self.target_process.is_running()
        if self.process is not None:
            return self.process.returncode is None
        return False

    async def kill(self) -> None:
        """停止监视器并中止所有跟踪的进程"""

        if self.target_process is not None and self.target_process.is_running():
            with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                try:
                    self.target_process.terminate()
                    await asyncio.get_running_loop().run_in_executor(
                        None, self.target_process.wait, 3
                    )
                except psutil.TimeoutExpired:
                    self.target_process.kill()
                    with suppress(psutil.TimeoutExpired):
                        await asyncio.get_running_loop().run_in_executor(
                            None, self.target_process.wait, 3
                        )

        if self.process is not None and self.process.returncode is None:
            with suppress(ProcessLookupError):
                try:
                    self.process.terminate()
                    await asyncio.wait_for(self.process.wait(), timeout=3)
                except asyncio.TimeoutError:
                    self.process.kill()
                    with suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(self.process.wait(), timeout=3)

        await self.clear()

    async def clear(self) -> None:
        """清空跟踪的进程信息"""

        self.process = None
        self.target_process = None


class ProcessRunner:
    """用于运行子进程并获取结果的实用程序类"""

    @staticmethod
    async def run_process(
        program: Path | str,
        *args: str,
        cwd: Path | None = None,
        timeout: float = 60,
        if_merge_std: bool = False,
    ) -> ProcessResult:
        """运行子进程并获取结果"""

        process = await asyncio.create_subprocess_exec(
            program,
            *args,
            cwd=cwd or (Path(program).parent if Path(program).is_file() else None),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=(
                asyncio.subprocess.STDOUT if if_merge_std else asyncio.subprocess.PIPE
            ),
            creationflags=CREATION_FLAGS,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()
            raise

        return ProcessResult(
            stdout=decode_bytes(stdout),
            stderr=decode_bytes(stderr),
            returncode=(
                process.returncode
                if process.returncode is not None
                else await process.wait()
            ),
        )
