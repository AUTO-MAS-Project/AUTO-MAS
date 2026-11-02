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


import asyncio
import locale
import os
import time
from collections import deque
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from inspect import isawaitable
from pathlib import Path
from typing import Awaitable, Callable, Mapping

import psutil

from app.utils import ProcessManager, decode_bytes, get_logger

from .log_detect import (
    HSR_CONSOLE_PAUSE_SUCCESS_MARKER,
    M7A_COMPLETION_MARKERS,
    emit_process_output,
    has_failure_output,
    unescape_backslash_u,
)

logger = get_logger("HSR M7A 运行器")

# 仅 M7A 输出中文编码优先；通用配置读取保留系统代码页。
_M7A_OUTPUT_ENCODINGS = tuple(
    dict.fromkeys(
        ("utf-8", "utf-8-sig", "gbk", "gb18030", locale.getpreferredencoding())
    )
)

# M7A 的四处「按任意键继续」统一由 utils/console.py 的 should_skip_pause() 放行，
# 它认 MARCH7TH_GUI_STARTED，M7A 自己的图形界面拉起 CLI 时用的就是这个标记。
# 托管运行没人按键：不带它时任务正文跑完仍会停在 input()，而系统 ANSI 代码页
# 不是中文时更会直接崩在写不出中文的 stdout 上，把已经做完的模块判成失败。
#
# M7A 读配置时环境变量优先于 config.yaml（module/config/config.py 的映射表）。
# MARCH7TH_AFTER_FINISH 钉成 None：托管与原生来源都不让 M7A 在任务后退出游戏、
# 关机或睡眠——这些由 MAS 的队列完成后操作负责。后端环境里其余 MARCH7TH_*
# 会静默盖过 MAS 写进 config.yaml 的值，起进程前剔掉（见 build_m7a_env）。
M7A_HEADLESS_ENV: dict[str, str] = {
    "MARCH7TH_GUI_STARTED": "true",
    "MARCH7TH_AFTER_FINISH": "None",
}
M7A_ENV_PREFIX = "MARCH7TH_"
# 保留的近期输出行数：M7A 失败前会连打十几条同样的 WARNING，太短会把
# 真正的 ERROR 挤掉。
RECENT_OUTPUT_LINES = 40


class _M7ACommandTimeout(TimeoutError):
    """命令预算耗尽，与输出回调自身抛出的 TimeoutError 区分。"""


def _env_bool(value: bool) -> str:
    # 三月七的转换函数是 v.lower() in ("true", "1")，只能写这两个字面量之一。
    return "true" if value else "false"


def build_m7a_platform_env(
    *, cloud: bool, use_paid_time: bool = False
) -> dict[str, str]:
    """按游戏平台钉住三月七的云开关（环境变量优先于 config.yaml）。

    客户端平台钉 ``false``，托管运行时用户在三月七里开过云游戏也不会跑到云上
    （客户端 + 原生来源不调用这里，见 ``build_platform_m7a_env``）；云平台再钉浏览器
    类型与有窗口模式，与 MAS 托管浏览器的
    连接条件一致（内置 Chrome + 同版本 chromedriver，没有 ``--headless``）。
    ``browser_debug_port`` 等键没有环境变量，只能写 config.yaml。
    """

    env = {"MARCH7TH_CLOUD_GAME_ENABLE": _env_bool(cloud)}
    if cloud:
        env.update(
            {
                "MARCH7TH_BROWSER_TYPE": "integrated",
                "MARCH7TH_BROWSER_HEADLESS_ENABLE": _env_bool(False),
                "MARCH7TH_CLOUD_GAME_USE_PAID_TIME": _env_bool(use_paid_time),
            }
        )
    return env


def build_m7a_env(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    """M7A 子进程环境：继承后端环境，剔除继承的 ``MARCH7TH_*``，再叠上 MAS 自己的。

    ``overrides`` 是本轮的平台钉扎（见 :func:`build_m7a_platform_env`）。
    """

    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(M7A_ENV_PREFIX)
    }
    env.update(M7A_HEADLESS_ENV)
    if overrides:
        env.update(overrides)
    return env


@dataclass
class M7ACommandResult:
    task_name: str
    exe_path: str
    success: bool = False
    output: str = ""
    error: str = ""
    returncode: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None


class M7ARunner:
    """March7th Assistant 命令执行器。"""

    def __init__(
        self,
        m7a_dir: Path,
        log_callback: Callable[[str], None] | None = None,
        output_line_callback: Callable[[str], Awaitable[None] | None] | None = None,
        completion_grace_timeout: float = 5.0,
        env_overrides: Mapping[str, str] | None = None,
        kill_tree: bool = False,
    ):
        self._m7a_dir = Path(m7a_dir)
        self._m7a_exe = self._m7a_dir / "March7th Assistant.exe"
        self._process_manager = ProcessManager()
        # 同一运行器跨模块/用户复用；命令连同收尾串行，排队取消不触碰当前进程。
        self._command_lock = asyncio.Lock()
        self._termination_lock = asyncio.Lock()
        self._tree_root: psutil.Process | None = None
        self._tree_children: set[psutil.Process] = set()
        self._log_callback = log_callback
        self._output_line_callback = output_line_callback
        self._completion_grace_timeout = completion_grace_timeout
        # 本轮的平台钉扎（MARCH7TH_CLOUD_GAME_ENABLE 等），每条命令起进程时叠加。
        self.env_overrides: dict[str, str] = dict(env_overrides or {})
        # 停止、超时、收尾时是否按进程树终止（见 terminate）；由平台决定，调用侧
        # 统一经 account_switch.configure_m7a_runner 设置。
        self.kill_tree = kill_tree
        # 当前这条命令最近的输出，供游戏守卫判断进程消失前 M7A 在做什么。
        self._recent_output: deque[str] = deque(maxlen=RECENT_OUTPUT_LINES)

    @property
    def root_path(self) -> Path:
        return self._m7a_dir

    def set_output_line_callback(
        self, callback: Callable[[str], Awaitable[None] | None] | None
    ) -> None:
        """换成当前用户的逐行输出回调（运行器在同一轮的用户之间复用）。"""

        self._output_line_callback = callback

    @property
    def recent_output_lines(self) -> list[str]:
        """当前（或最近一条）M7A 命令末尾的输出行，按时间先后排列。"""

        return list(self._recent_output)

    async def terminate_current_process(self) -> bool:
        """终止当前 M7A 子进程。"""

        process = self._process_manager.main_process
        async with self._termination_lock:
            if process is not self._process_manager.main_process:
                return False
            if not await self._process_manager.is_running():
                return False

            logger.warning("正在终止三月七当前子进程")
            await self._wait_for_cleanup(
                asyncio.create_task(self._process_manager.kill())
            )
            return True

    async def terminate(self) -> bool:
        """停止、超时、收尾统一走这里：按 ``kill_tree`` 选按树终止或只杀主进程。

        云平台下三月七的子进程只有 chromedriver 与它自建的浏览器，按树杀干净；
        客户端平台下三月七可能自己拉起了游戏客户端，按树杀会把游戏带走，只杀主进程。
        """

        if self.kill_tree:
            return await self.terminate_process_tree()
        return await self.terminate_current_process()

    async def terminate_process_tree(self) -> bool:
        """按进程树终止当前 M7A：先冻结主进程，杀光子孙，再终止主进程。

        三月七经 selenium 拉起的 chromedriver 以 ``close_fds=False`` 继承了它的
        stdout/stderr 管道：只杀主进程时管道仍无 EOF，``run_task`` 会一直挂到命令
        超时，chromedriver 也成了 MAS 清理不到的孤儿。冻结主进程是为了杀子进程
        期间它不再派生新的。
        """

        process = self._process_manager.main_process
        async with self._termination_lock:
            # 后台停止可能在上一命令清理后才获得执行机会，不能清理下一命令。
            if process is not self._process_manager.main_process:
                return False
            if isinstance(process, asyncio.subprocess.Process):
                await self._remember_process_tree(process)
            root = self._tree_root
            children = set(self._tree_children)
            if process is None and not children:
                return False

            def _kill_descendants() -> int:
                if root is not None and root.is_running():
                    with suppress(psutil.Error):
                        root.suspend()
                    with suppress(psutil.Error):
                        for child in root.children(recursive=True):
                            # 只有可读取创建时间的对象才可用于稍后的身份校验。
                            with suppress(psutil.Error):
                                child.create_time()
                                children.add(child)
                killed = []
                failed = 0
                for child in children:
                    try:
                        # psutil 按 PID + 创建时间校验，禁止用旧 PID 重建对象来杀。
                        if (
                            child.is_running()
                            and child.status() != psutil.STATUS_ZOMBIE
                        ):
                            child.kill()
                            killed.append(child)
                    except psutil.NoSuchProcess:
                        pass
                    except psutil.AccessDenied:
                        failed += 1
                count = len(killed)
                # 已退出的孤儿在部分宿主上暂为 zombie；不能等宿主回收 PID 才继续。
                deadline = time.monotonic() + 3
                while killed and time.monotonic() < deadline:
                    _, alive = psutil.wait_procs(killed, timeout=0.05)
                    killed = []
                    for child in alive:
                        try:
                            if child.status() != psutil.STATUS_ZOMBIE:
                                killed.append(child)
                        except psutil.NoSuchProcess:
                            pass
                        except psutil.AccessDenied:
                            failed += 1
                if killed or failed:
                    raise RuntimeError(
                        f"有 {len(killed) + failed} 个三月七云端后代未能终止"
                    )
                return count

            try:
                kill_task = asyncio.create_task(asyncio.to_thread(_kill_descendants))
                await self._wait_for_cleanup(kill_task)
                count = kill_task.result()
            finally:
                # 后代处理异常也必须结束可能已被冻结的主进程，不能直接丢掉跟踪。
                await self._wait_for_cleanup(
                    asyncio.create_task(self._process_manager.kill())
                )
            if root is None and process is not None:
                logger.warning(
                    "未能在三月七退出前确认后代归属，仅清理已知进程，不扫描孤儿进程"
                )
            logger.warning(f"正在按进程树终止三月七（子进程 {count} 个）")
            return True

    async def _remember_process_tree(self, proc: asyncio.subprocess.Process) -> None:
        """在父进程仍可确认时记录云端后代身份，供父进程退出后清理。

        首次采样前或快照间隙产生且已脱离的后代无法补认，不按名称或裸 PID 扫描。
        """

        known_root = self._tree_root

        def _snapshot():
            root = known_root
            children = []
            try:
                if root is None:
                    if proc.returncode is not None:
                        return None, children
                    candidate = psutil.Process(proc.pid)
                    candidate.create_time()
                    root = candidate
                if root.is_running():
                    for child in root.children(recursive=True):
                        with suppress(psutil.Error):
                            child.create_time()
                            children.append(child)
            except psutil.Error:
                pass
            return root, children

        # 退出观察器也可能在快照期间被取消，先接收已确认的身份，再传播取消。
        snapshot = asyncio.create_task(asyncio.to_thread(_snapshot))
        cancelled = False
        try:
            await self._wait_for_cleanup(snapshot)
        except asyncio.CancelledError:
            cancelled = True
        root, children = snapshot.result()
        if self._process_manager.main_process is proc:
            self._tree_root = root
            self._tree_children.update(children)
        if cancelled:
            raise asyncio.CancelledError

    def _emit_process_output(self, title: str, text: str) -> None:
        emit_process_output(self._log_callback, title, text)

    @staticmethod
    def _decode_stream_output(output: bytes | bytearray) -> str:
        # 按完整字节行解码，避免分块读取切开 UTF-8/GBK 字符或反斜杠转义。
        return "\n".join(
            line.strip()
            for raw_line in bytes(output).split(b"\n")
            for line in unescape_backslash_u(
                decode_bytes(raw_line, encodings=_M7A_OUTPUT_ENCODINGS)
            ).splitlines()
            if line.strip()
        )

    async def _read_stream_live(
        self,
        stream,
        title: str,
        output: bytearray,
        completion_event: asyncio.Event | None = None,
    ) -> None:
        """先保存已读字节，再逐行转发；无换行尾部不依赖 EOF 才能保留。"""

        pending = b""
        while True:
            raw = await stream.read(4096)
            if raw:
                output.extend(raw)
                pending += raw
                complete, _, pending = pending.rpartition(b"\n")
            else:
                complete = pending
            for line in self._decode_stream_output(complete).splitlines():
                self._recent_output.append(line)
                self._emit_process_output(title, line)
                if self._output_line_callback is not None:
                    result = self._output_line_callback(line)
                    if isawaitable(result):
                        await result
                if completion_event is not None and self._is_completion_line(line):
                    completion_event.set()
            if not raw:
                break

    @staticmethod
    def _is_completion_line(line: str) -> bool:
        return any(marker in line for marker in M7A_COMPLETION_MARKERS)

    @classmethod
    def _has_completion_marker(cls, text: str) -> bool:
        return any(cls._is_completion_line(line) for line in text.splitlines())

    async def _send_enter_to_process(self, proc: asyncio.subprocess.Process) -> bool:
        """向已完成但等待交互关闭的 M7A 进程发送回车。"""

        stdin = getattr(proc, "stdin", None)
        if stdin is None:
            return False

        try:
            stdin.write(b"\n")
            await stdin.drain()
        except (BrokenPipeError, ConnectionResetError, RuntimeError, OSError) as e:
            logger.debug(f"M7A 子进程 stdin 已不可写，跳过发送回车：{e}")
            return False
        return True

    async def _wait_for_process_exit(self, proc: asyncio.subprocess.Process) -> None:
        # asyncio 的 wait() 在部分平台会连同管道 EOF 一起等待；returncode
        # 由子进程退出通知更新，不受后代继承 stdout/stderr 的影响。
        next_snapshot = 0.0
        while proc.returncode is None:
            now = asyncio.get_running_loop().time()
            if self.kill_tree and now >= next_snapshot:
                async with self._termination_lock:
                    await self._remember_process_tree(proc)
                next_snapshot = now + 0.25
            await asyncio.sleep(0.05)

    @staticmethod
    def _close_process_pipes(proc: asyncio.subprocess.Process) -> None:
        if proc.stdin is not None:
            proc.stdin.close()
        # StreamReader 没有公开的 close；只关闭本次子进程的读端，不终止可能是
        # 游戏客户端的后代。项目固定 Python 3.12，升级时需核对该 transport 接口。
        for fd in (1, 2):
            pipe = proc._transport.get_pipe_transport(fd)
            if pipe is not None:
                pipe.close()

    async def _cleanup_process(self, proc: asyncio.subprocess.Process | None) -> None:
        # open_process 已创建进程但尚未返回时也可能收到取消，此时本地 proc
        # 还没赋值，仍须取回管理器持有的句柄并关闭管道。
        process = proc or self._process_manager.main_process
        try:
            if isinstance(process, asyncio.subprocess.Process):
                self._close_process_pipes(process)
        finally:
            try:
                await self.terminate()
            finally:
                await self._process_manager.clear()
                self._tree_root = None
                self._tree_children.clear()

    @staticmethod
    async def _wait_for_cleanup(cleanup: asyncio.Future) -> None:
        """推迟重复取消，直到本次资源清理真正结束。"""

        cancelled = False
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                cancelled = True
        cleanup.result()
        if cancelled:
            raise asyncio.CancelledError

    async def _communicate_with_live_output(
        self,
        proc: asyncio.subprocess.Process,
        timeout: int,
    ) -> tuple[str, str, bool, bool]:
        """返回输出、是否在停止标记后主动终止进程及输出是否完整。"""

        stdout_stream = getattr(proc, "stdout", None)
        stderr_stream = getattr(proc, "stderr", None)
        stdout_readable = callable(getattr(stdout_stream, "read", None))
        stderr_readable = callable(getattr(stderr_stream, "read", None))
        if not (stdout_readable or stderr_readable):
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError as exc:
                raise _M7ACommandTimeout from exc
            stdout = unescape_backslash_u(
                decode_bytes(stdout_bytes, encodings=_M7A_OUTPUT_ENCODINGS)
            ).strip()
            stderr = unescape_backslash_u(
                decode_bytes(stderr_bytes, encodings=_M7A_OUTPUT_ENCODINGS)
            ).strip()
            self._emit_process_output("三月七", stdout)
            self._emit_process_output("三月七 stderr", stderr)
            for text in (stdout, stderr):
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    self._recent_output.append(line)
                    if self._output_line_callback is None:
                        continue
                    result = self._output_line_callback(line)
                    if isawaitable(result):
                        await result
            return stdout, stderr, False, True

        stdout_output = bytearray()
        stderr_output = bytearray()
        read_tasks: list[asyncio.Task] = []
        completion_event = asyncio.Event()
        if stdout_readable:
            read_tasks.append(
                asyncio.create_task(
                    self._read_stream_live(
                        stdout_stream,
                        "三月七",
                        stdout_output,
                        completion_event,
                    )
                )
            )
        if stderr_readable:
            read_tasks.append(
                asyncio.create_task(
                    self._read_stream_live(
                        stderr_stream,
                        "三月七 stderr",
                        stderr_output,
                        completion_event,
                    )
                )
            )

        read_group = asyncio.gather(*read_tasks)
        exit_wait = asyncio.create_task(self._wait_for_process_exit(proc))
        completion_wait = asyncio.create_task(completion_event.wait())
        deadline = asyncio.get_running_loop().time() + timeout
        terminated_after_completion = False
        output_complete = False
        try:
            pending = {exit_wait, completion_wait, read_group}
            while not exit_wait.done():
                done, _ = await asyncio.wait(
                    pending,
                    timeout=max(0, deadline - asyncio.get_running_loop().time()),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    if proc.returncode is not None or completion_event.is_set():
                        break
                    raise _M7ACommandTimeout
                if read_group in done:
                    # EOF 不等于进程退出；读取/回调异常则立即传播，不等命令超时。
                    await read_group
                    pending.remove(read_group)
                if completion_wait in done:
                    pending.remove(completion_wait)
                    deadline = min(
                        deadline,
                        asyncio.get_running_loop().time()
                        + self._completion_grace_timeout,
                    )
                    await self._send_enter_to_process(proc)
                    logger.info("三月七已输出停止运行标记，等待进程自然退出")

            if proc.returncode is None:
                logger.warning("三月七已停止运行但进程未退出，终止子进程")
                terminated_after_completion = True
                self._close_process_pipes(proc)
                await self._wait_for_cleanup(asyncio.create_task(self.terminate()))

            try:
                await asyncio.wait_for(
                    asyncio.shield(read_group),
                    # 进程已结束，排空预算独立于命令截止时间，避免丢掉已写出的尾部错误。
                    timeout=self._completion_grace_timeout,
                )
                output_complete = True
            except asyncio.TimeoutError:
                if read_group.done():
                    # 不把回调本身的 TimeoutError 当成输出排空到期。
                    await read_group
                    output_complete = True
                else:
                    logger.warning("三月七进程已退出，输出未在宽限期内结束，关闭管道")
        finally:
            # 成功、异常与取消均回收全部读流/退出等待任务。关闭的是本次运行的
            # 管道，客户端后代是否终止仍由既有平台策略决定。
            for task in (*read_tasks, exit_wait, completion_wait):
                task.cancel()
            self._close_process_pipes(proc)
            try:
                # 超时/取消时先停主进程，再等回调的 finally，避免清理拖延实际执行。
                if proc.returncode is None:
                    await self._wait_for_cleanup(asyncio.create_task(self.terminate()))
            finally:
                await self._wait_for_cleanup(
                    asyncio.gather(
                        *read_tasks,
                        read_group,
                        exit_wait,
                        completion_wait,
                        return_exceptions=True,
                    )
                )

        return (
            self._decode_stream_output(stdout_output),
            self._decode_stream_output(stderr_output),
            terminated_after_completion,
            output_complete,
        )

    async def run_task(self, task_name: str, timeout: int = 600) -> M7ACommandResult:
        """执行一条 M7A 命令。"""

        async with self._command_lock:
            started_at = datetime.now(timezone.utc)
            try:
                return await self._run_task(task_name, timeout)
            except Exception as error:
                # 最终清理也可能失败；仍返回失败结果，取消继续原样传播。
                logger.opt(exception=True).warning(f"三月七清理失败：{error}")
                return M7ACommandResult(
                    task_name=task_name,
                    exe_path=str(self._m7a_exe),
                    success=False,
                    error=str(error),
                    started_at=started_at,
                    finished_at=datetime.now(timezone.utc),
                )

    async def _run_task(self, task_name: str, timeout: int) -> M7ACommandResult:
        started_at = datetime.now(timezone.utc)
        self._recent_output.clear()
        self._tree_root = None
        self._tree_children.clear()
        proc: asyncio.subprocess.Process | None = None

        if not self._m7a_exe.exists():
            msg = f"March7th Assistant.exe does not exist: {self._m7a_exe}"
            logger.warning(msg)
            return M7ACommandResult(
                task_name=task_name,
                exe_path=str(self._m7a_exe),
                success=False,
                error=msg,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )

        try:
            await self._process_manager.open_process(
                str(self._m7a_exe),
                task_name,
                cwd=self._m7a_dir,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=build_m7a_env(self.env_overrides),
            )
            process = self._process_manager.main_process
            if not isinstance(process, asyncio.subprocess.Process):
                raise RuntimeError("三月七子进程启动后未能被 ProcessManager 跟踪")
            proc = process
            if self.kill_tree:
                async with self._termination_lock:
                    await self._remember_process_tree(proc)
            (
                stdout,
                stderr,
                terminated_after_completion,
                output_complete,
            ) = await self._communicate_with_live_output(proc, timeout)
            # rc=0 且没有任何输出不算成功：M7A 未提权时会另起提权进程后原进程
            # 直接 exit(0)，真正干活的进程脱离了 MAS 的视野。
            combined_output = f"{stdout}\n{stderr}"
            # 沿用旧版三月七成功后暂停崩溃的兼容；普通非零退出即便打过
            # 「停止运行」也不能据此判成功，正文失败仍由 has_failure_output 否决。
            completed_before_pause_crash = (
                self._has_completion_marker(combined_output)
                and HSR_CONSOLE_PAUSE_SUCCESS_MARKER in combined_output
            )
            success = (
                (
                    (terminated_after_completion and proc.returncode is not None)
                    or completed_before_pause_crash
                    or (proc.returncode == 0 and bool(stdout or stderr))
                )
                and not has_failure_output(stdout, stderr)
                and output_complete
            )

            error = stderr if success else combined_output.strip()
            if not output_complete:
                error = f"{error}\n三月七输出未完整收集，无法确认任务成功".strip()

            logger.info(
                f"三月七 {task_name} → {'success' if success else 'failed'}"
                f" (rc={proc.returncode})"
            )
            return M7ACommandResult(
                task_name=task_name,
                exe_path=str(self._m7a_exe),
                success=success,
                output=stdout,
                error=error,
                returncode=proc.returncode or 0,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )

        except _M7ACommandTimeout:
            logger.warning(f"三月七 {task_name} timed out after {timeout}s")
            return M7ACommandResult(
                task_name=task_name,
                exe_path=str(self._m7a_exe),
                success=False,
                error=f"command timed out after {timeout}s",
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )

        except asyncio.CancelledError:
            logger.warning(f"三月七 {task_name} 收到取消请求，准备终止子进程")
            raise

        except Exception as e:
            logger.opt(exception=True).warning(f"三月七 {task_name} error: {e}")
            return M7ACommandResult(
                task_name=task_name,
                exe_path=str(self._m7a_exe),
                success=False,
                error=str(e),
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )
        finally:
            # 清理期间重复点击停止，也要先终止进程再清除跟踪信息。
            await self._wait_for_cleanup(
                asyncio.create_task(self._cleanup_process(proc))
            )
