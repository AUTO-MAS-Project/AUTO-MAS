import asyncio
import os
import subprocess
import time
from collections.abc import Sequence
from pathlib import Path
from threading import Lock
from typing import Any, Unpack

import psutil
import pywintypes
import win32api
import win32con
import win32job
import win32process

from app.utils.common.process.runner import ProcessRunner

from ..contracts.process import ElevatedProcess, EmulatorPopenOptions


class WindowsTaskProcessJob:
    # 先挂起创建，加入任务 Job 后再恢复，避免短命包装器抢先派生并退出。
    creation_flags = 0x00000004  # CREATE_SUSPENDED

    def __init__(self) -> None:
        self._lock = Lock()
        self._closed = False
        self._stopping = False
        inherited = win32job.CreateJobObject(None, "")
        try:
            detached = win32job.CreateJobObject(None, "")
        except Exception:
            inherited.Close()
            raise
        # 脱离 Runtime 的进程不能与继承 Runtime 的进程共用同一个嵌套 Job。
        self._handles = {False: inherited, True: detached}
        self._adopted: list[Any] = []

    def assign(self, pid: int, *, suspended: bool, breakaway: bool) -> None:
        # 安装线程与任务停止共用这把锁，强杀开始后不得再分配或恢复新进程。
        with self._lock:
            if self._closed or self._stopping:
                raise asyncio.CancelledError
            process = win32api.OpenProcess(
                win32con.PROCESS_SET_QUOTA
                | win32con.PROCESS_TERMINATE
                | win32con.PROCESS_QUERY_INFORMATION,
                False,
                pid,
            )
            try:
                job = self._handles[breakaway]
                if not win32job.IsProcessInJob(process, job):
                    win32job.AssignProcessToJobObject(job, process)
            finally:
                process.Close()
            if suspended:
                for thread in psutil.Process(pid).threads():
                    handle = win32api.OpenThread(
                        win32con.THREAD_SUSPEND_RESUME, False, thread.id
                    )
                    try:
                        win32process.ResumeThread(handle)
                    finally:
                        handle.Close()

    def adopt(self, pid: int, create_time: float) -> None:
        """给明确接管的进程及已有后代加 Job 标记，后续后代由系统继承。"""
        with self._lock:
            if self._closed or self._stopping:
                raise asyncio.CancelledError
            root = psutil.Process(pid)
            if root.create_time() != create_time:
                raise psutil.NoSuchProcess(pid, msg="接管进程的 PID 已复用")
            pending, seen = [root], set()
            while pending:
                target = pending.pop()
                if target.pid in seen:
                    continue
                seen.add(target.pid)

                try:
                    # 先保留已发现的孩子，父进程在接管期间退出也不能丢掉它们。
                    pending.extend(target.children())
                    process = win32api.OpenProcess(
                        win32con.PROCESS_SET_QUOTA
                        | win32con.PROCESS_TERMINATE
                        | win32con.PROCESS_QUERY_INFORMATION,
                        False,
                        target.pid,
                    )
                    try:
                        # OpenProcess 的句柄固定目标；再用缓存的创建时间核对身份。
                        if not target.is_running():
                            continue
                        jobs = (*self._handles.values(), *self._adopted)
                        if any(win32job.IsProcessInJob(process, job) for job in jobs):
                            continue
                        # 外部进程可能来自不同的系统 Job，不能共用一个嵌套 Job。
                        job = win32job.CreateJobObject(None, "")
                        try:
                            win32job.AssignProcessToJobObject(job, process)
                        except BaseException:
                            job.Close()
                            raise
                        self._adopted.append(job)
                        # 标记后新生的孩子自动继承，再补登记期间已有的孩子。
                        pending.extend(target.children())
                    finally:
                        process.Close()
                except (psutil.NoSuchProcess, pywintypes.error):
                    # 只容忍已退出或 PID 已复用的旧目标；存活目标的权限等错误仍需上报。
                    if target.is_running():
                        raise

    def kill(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._stopping = True
            errors = []
            jobs = (*self._handles.values(), *self._adopted)
            for job in jobs:
                try:
                    win32job.TerminateJobObject(job, 1)
                except Exception as error:
                    errors.append(error)
            # TerminateJobObject 只发起终止；确认组内进程已退出，不等待输出 EOF。
            deadline = time.monotonic() + 1
            try:
                while any(
                    win32job.QueryInformationJobObject(
                        job, win32job.JobObjectBasicAccountingInformation
                    )["ActiveProcesses"]
                    for job in jobs
                ):
                    if time.monotonic() >= deadline:
                        raise TimeoutError("任务进程组强制终止后仍有进程存活")
                    time.sleep(0.01)
            except Exception as error:
                errors.append(error)
            if errors:
                raise ExceptionGroup("部分任务进程组未能强制终止", errors)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            errors = []
            for job in (*self._handles.values(), *self._adopted):
                try:
                    job.Close()
                except Exception as error:
                    errors.append(error)
            if errors:
                raise ExceptionGroup("部分任务进程组句柄未能关闭", errors)


class WindowsProcessPlatform:
    @staticmethod
    def create_task_job() -> WindowsTaskProcessJob:
        return WindowsTaskProcessJob()

    supports_elevation = True
    # 后端被 AUTO-MAS-Runtime 用 Job Object 监督（KILL_ON_JOB_CLOSE，且允许
    # breakaway）时，子进程默认都留在 Job 里：MAA.exe、各专项脚本进程、MaaFW
    # agent、taskkill/schtasks 之类的工具调用，在后端被硬杀或宿主崩溃时都要
    # 能被 Job 一并回收，不能变成孤儿。所以 creation_flags 只有基础标志，
    # 不带 CREATE_BREAKAWAY_FROM_JOB。
    #
    # 按 Runtime 契约 C8（游戏与模拟器不随后端退出）和 D-3 决策（AUTO-MAS 只在
    # 拉起游戏/模拟器时带 CREATE_BREAKAWAY_FROM_JOB），脱离标志单独放在
    # breakaway_flags 里，由 ProcessManager.open_process / ProcessRunner.run_process
    # 的 breakaway=True 调用点按需叠加——目前只有模拟器控制台、general 脚本
    # 的游戏客户端和 MaaFW DirectExe 桌面游戏三处，其余调用点一律默认 False，
    # 不要把它加回全局标志。
    #
    # 父进程若恰好处在一个不允许 breakaway 的 Job 里，带这个标志的
    # CreateProcess 会以 ERROR_ACCESS_DENIED（WinError 5）失败；
    # process_runner.create_subprocess 对此有去掉该位重试一次的兜底。
    creation_flags = subprocess.CREATE_NO_WINDOW
    breakaway_flags = subprocess.CREATE_BREAKAWAY_FROM_JOB
    # 自更新时接替当前进程的安装程序必须活过后端退出，因此这组标志固定带
    # 脱离位。注意 DETACHED_PROCESS 本身不会让子进程脱离 Job，必须靠
    # CREATE_BREAKAWAY_FROM_JOB 才行，不要以为 DETACHED_PROCESS 已经处理了
    # 这件事。
    detached_flags = (
        subprocess.CREATE_NEW_PROCESS_GROUP
        | subprocess.DETACHED_PROCESS
        | subprocess.CREATE_NO_WINDOW
        | subprocess.CREATE_BREAKAWAY_FROM_JOB
    )

    async def open_protocol(self, protocol_url: str) -> None:
        os.startfile(protocol_url)

    async def kill_process(self, pid: int, kill_tree: bool = False) -> tuple[bool, str]:
        """用 taskkill 终止进程，返回 (是否成功, 失败原因)。"""

        args = ["taskkill", "/F"]
        if kill_tree:
            args.append("/T")
        args.extend(["/PID", str(pid)])

        result = await ProcessRunner.run_process(*args, timeout=10, cleanup=True)
        if result.returncode != 0:
            output = result.stderr.strip() or result.stdout.strip() or "无错误信息"
            return False, f"返回码: {result.returncode}, 原因: {output}"
        return True, ""

    agent_flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    emulator_flags = (
        subprocess.CREATE_NO_WINDOW
        | subprocess.CREATE_NEW_PROCESS_GROUP
        | subprocess.CREATE_BREAKAWAY_FROM_JOB
    )

    @staticmethod
    def popen_emulator(
        args: Sequence[str], **kwargs: Unpack[EmulatorPopenOptions]
    ) -> subprocess.Popen[bytes]:
        try:
            return subprocess.Popen(
                args, creationflags=WindowsProcessPlatform.emulator_flags, **kwargs
            )
        except OSError as exc:
            if getattr(exc, "winerror", None) != 5:
                raise
            return subprocess.Popen(
                args,
                creationflags=WindowsProcessPlatform.emulator_flags
                & ~WindowsProcessPlatform.breakaway_flags,
                **kwargs,
            )

    @staticmethod
    def prepare_elevated() -> ElevatedProcess:
        """在事件循环线程解析 UAC 依赖，再返回同步启动函数。"""
        import win32api
        import win32con

        def open_elevated(
            program: str | Path, args: Sequence[str], cwd: str | Path | None
        ) -> None:
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

        return open_elevated


platform_process = WindowsProcessPlatform()
