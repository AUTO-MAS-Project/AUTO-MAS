#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import os
import subprocess
import time
import psutil
import asyncio

from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from app.utils.platform import window
from app.utils.platform.common.errors import UnsupportedPlatformError
from app.utils.platform.process import platform_process

from .process_runner import ProcessResult, ProcessRunner


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
        if target.name is not None and proc.name() != target.name:
            return False
        if target.exe is not None and Path(proc.exe()) != Path(target.exe):
            return False
        if target.cmdline is not None and proc.cmdline() != target.cmdline:
            return False
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False

    return True


def is_process_running(process_name: str) -> bool:
    """检查指定进程名是否正在运行且存在可见窗口"""

    for proc in psutil.process_iter(["name"]):
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            if proc.info.get("name") == process_name:
                # 平台不支持窗口能力时 get_window_handles 返回空列表, 循环不进入
                for hwnd in get_window_handles(proc.pid):
                    if window.is_visible(hwnd):
                        return True
    return False


def is_process_alive(process_name: str) -> bool:
    """检查指定进程名是否有存活实例（不依赖窗口）。

    is_process_running 要求存在可见窗口，窗口销毁后进程仍可能存活；
    需要「等待进程完全退出」的调用方（如多用户切换等待旧游戏退出）应
    用本函数按进程名判断存活。
    """

    for proc in psutil.process_iter(["name"]):
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            if proc.info.get("name") == process_name:
                return True
    return False


def has_visible_window(pid: int) -> bool:
    """指定进程是否已经拥有可见窗口。

    用作「程序起来了没有」的就绪判据：进程创建远早于窗口出现，只看进程在不在
    会把还在加载的游戏当成已就绪。
    """

    for hwnd in window.get_window_handles(pid):
        with suppress(Exception):
            if window.is_visible(hwnd):
                return True
    return False


def activate_window_by_pid(
    pid: int, window_title: str | None = None, window_class_name: str | None = None
) -> bool:
    """按 pid 把窗口置前。

    给「只有 pid、不该为此造一个 ProcessManager」的调用方用：ProcessManager 代表
    「本次由我方启动并持有的进程」，为了点一下窗口就 new 一个，会让持有关系失真
    （也会污染按实例计数的测试）。
    """

    hwnd = window.get_main_window_handle(pid, window_title, window_class_name)
    if hwnd is None:
        return False
    try:
        return window.activate_window(hwnd)
    except Exception:
        return False


def get_window_handles(pid: int) -> list[int]:
    """获取指定进程的所有窗口句柄"""

    try:
        return window.get_window_handles(pid)
    except UnsupportedPlatformError:
        return []


def get_main_window_handle(
    pid: int,
    window_title: str | None = None,
    window_class_name: str | None = None,
) -> int | None:
    """获取指定进程的主窗口句柄

    优先按标题或类名定位, 若未命中则回退到 PID 下最合适的顶层窗口。
    平台不支持窗口能力时返回 None。
    """

    try:
        return window.get_main_window_handle(pid, window_title, window_class_name)
    except UnsupportedPlatformError:
        return None


class ProcessManager:
    """进程监视器类, 用于跟踪主进程及其所有子进程的状态"""

    def __init__(
        self, window_title: str | None = None, window_class_name: str | None = None
    ):
        super().__init__()

        self.process: asyncio.subprocess.Process | None = None
        self.target_process: psutil.Process | None = None
        self.window_title = window_title
        self.window_class_name = window_class_name
        self._drain_tasks: list[asyncio.Task[None]] = []

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

    @property
    def main_hwnd(self) -> int | None:
        """主进程的主窗口句柄"""

        if self.main_pid is None:
            return None
        return get_main_window_handle(
            self.main_pid, self.window_title, self.window_class_name
        )

    async def open_process(
        self,
        program: Path | str,
        *args: str,
        cwd: Path | None = None,
        target_process: ProcessInfo | None = None,
        stdin: int = asyncio.subprocess.DEVNULL,
        stdout: int = asyncio.subprocess.DEVNULL,
        stderr: int = asyncio.subprocess.DEVNULL,
        null_stream_to_pipe: bool = False,
        elevated: bool = False,
    ) -> None:
        """
        启动子进程并跟踪目标进程

        Args:
            program (Path | str): 可执行文件路径
            *args (str): 传递给可执行文件的参数
            cwd (Path | None): 可选的工作目录, 默认为可执行文件所在目录
            target_process (ProcessInfo | None): 期望目标进程信息, 用于跟踪主进程及其子进程, 默认为 None 表示跟踪直接启动的子进程
            stdin (int): 标准输入重定向选项, 默认为 asyncio.subprocess.DEVNULL
            stdout (int): 标准输出重定向选项, 默认为 asyncio.subprocess.DEVNULL
            stderr (int): 标准错误重定向选项, 默认为 asyncio.subprocess.DEVNULL
            null_stream_to_pipe (bool): 若为 True, 将设为 DEVNULL 的 stdout/stderr 替换为一条自动销毁输出的标准流管道。
            elevated (bool): 若为 True 且在 Windows 上, 以管理员权限启动进程（触发 UAC），此时不直接持有子进程句柄，依赖 target_process 追踪。
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

        if elevated and os.name == "nt":
            # 以管理员权限启动进程（触发 UAC），ShellExecute 不返回子进程句柄，
            # 因此无法直接持有 process，仅支持通过 target_process 追踪。
            await asyncio.get_running_loop().run_in_executor(
                None, self._open_process_elevated, program, args, cwd
            )
            if target_process is not None:
                await self.search_process(
                    target_process,
                    60.0,
                    min_create_time=time.time(),
                )
            return

        # 若指定了 null_stream_to_pipe, 将 stdout/stderr 为 DEVNULL 的流替换为管道, 并在后台消费以防止阻塞
        drain_streams = []
        if null_stream_to_pipe:
            if stdout == asyncio.subprocess.DEVNULL:
                stdout = asyncio.subprocess.PIPE
                drain_streams.append("stdout")
            if stderr == asyncio.subprocess.DEVNULL:
                stderr = asyncio.subprocess.PIPE
                drain_streams.append("stderr")

        self.process = await asyncio.create_subprocess_exec(
            program,
            *args,
            cwd=cwd or (Path(program).parent if Path(program).is_file() else None),
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            creationflags=platform_process.creation_flags,
        )

        # 启动协程消费管道流以防止阻塞
        if drain_streams:
            for name in drain_streams:
                stream = getattr(self.process, name)
                if stream is not None:
                    self._drain_tasks.append(asyncio.create_task(self._drain(stream)))

        if target_process is not None:
            await self.search_process(
                target_process,
                60.0,
                min_create_time=time.time(),
            )

    @staticmethod
    def _open_process_elevated(
        program: Path | str, args: tuple[str, ...], cwd: Path | None
    ) -> None:
        """以管理员权限启动进程（触发 UAC），ShellExecute 成功时返回码大于 32。

        win32 仅在 Windows 路径才使用，故延迟导入，保证本平台通用模块在
        非 Windows 上也能安全导入。
        """
        import win32api
        import win32con

        parameters = subprocess.list2cmdline(list(args)) if args else None
        working_directory = str(cwd) if cwd is not None else None

        ret = win32api.ShellExecute(
            None,
            "runas",
            str(program),
            parameters,
            working_directory,
            win32con.SW_SHOWNORMAL,
        )
        if ret <= 32:
            raise RuntimeError(
                f"以管理员权限启动进程失败: {program} (ShellExecute 返回 {ret})"
            )

    async def _drain(self, stream: asyncio.StreamReader) -> None:
        """
        消费子进程标准流, 丢弃写入, 防止管道背压阻塞子进程。

        Args:
            stream (asyncio.StreamReader): 子进程的标准流对象
        """

        try:
            while _ := await stream.readline():
                pass
        except (ValueError, OSError):
            # 管道读端在子进程退出后被关闭, 属正常终止; 忽略无效句柄冲突
            pass

    async def open_protocol(
        self, protocol_url: str, target_process: ProcessInfo
    ) -> None:
        """
        使用自定义协议启动子进程, 需要目标进程信息进行跟踪

        Args:
            protocol_url (str): 自定义协议 URL
            target_process (ProcessInfo): 期望目标进程信息
        """

        try:
            await platform_process.open_protocol(protocol_url)
        except UnsupportedPlatformError:
            raise
        except Exception as e:
            raise RuntimeError(f"无法启动协议 {protocol_url}: {e}") from e

        await self.search_process(
            target_process,
            60.0,
            min_create_time=time.time(),
        )

    async def search_process(
        self,
        target_process: ProcessInfo,
        timeout_seconds: float = 60.0,
        min_create_time: float | None = None,
    ) -> None:
        """查找目标进程

        Args:
            target_process: 期望目标进程信息
            timeout_seconds: 搜索超时秒数，按单调时钟计量，不受系统时钟跳变影响
            min_create_time: 进程创建时间下限（epoch 秒），早于该时刻创建的同名进程视为
                启动前的残留实例并跳过，避免错误跟踪旧进程（留 2 秒容差吸收时间戳偏差）
        """

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            for proc in psutil.process_iter(
                ["pid", "name", "exe", "cmdline", "create_time"]
            ):
                try:
                    if match_process(proc, target_process):
                        if (
                            min_create_time is not None
                            and proc.create_time() < min_create_time - 2
                        ):
                            continue
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

        # 清理残留的排水任务, 避免泄漏
        if self._drain_tasks:
            for task in self._drain_tasks:
                if not task.done():
                    task.cancel()
            with suppress(asyncio.CancelledError):
                await asyncio.gather(*self._drain_tasks, return_exceptions=True)
            self._drain_tasks = []

        self.process = None
        self.target_process = None

    async def is_visible(self) -> bool:
        """检查主进程窗口是否可见

        Returns:
            bool: 窗口是否可见
        """

        hwnd = self.main_hwnd
        if hwnd is None:
            return False

        try:
            return window.is_visible(hwnd)
        except Exception:
            return False

    async def show_window(self) -> bool:
        """显示主进程窗口

        Returns:
            bool: 操作是否成功
        """

        hwnd = self.main_hwnd
        if hwnd is None:
            return False

        try:
            return window.show_window(hwnd)
        except Exception:
            return False

    async def hide_window(self) -> bool:
        """隐藏主进程窗口

        Returns:
            bool: 操作是否成功
        """
        hwnd = self.main_hwnd
        if hwnd is None:
            return False

        try:
            return window.hide_window(hwnd)
        except Exception:
            return False

    async def minimize_window(self) -> bool:
        """最小化主进程窗口

        Returns:
            bool: 操作是否成功
        """

        hwnd = self.main_hwnd
        if hwnd is None:
            return False

        try:
            return window.minimize_window(hwnd)
        except Exception:
            return False

    async def activate_window(self) -> bool:
        """激活主进程窗口并将其置于前台

        Returns:
            bool: 操作是否成功
        """

        hwnd = self.main_hwnd
        if hwnd is None:
            return False

        try:
            return window.activate_window(hwnd)
        except Exception:
            return False
