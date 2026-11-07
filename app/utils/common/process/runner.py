import asyncio
import locale
import time
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

import psutil

from app.utils import get_logger

from .scope import current_process_scope, current_update_scope, detached_process_context

logger = get_logger("进程管理")
_PROCESS_CLEANUP_SECONDS = 8


class ProcessCleanupUnconfirmed(RuntimeError):
    """进程未确认停止，调用方须保留可能仍被写入的文件。"""


def is_process_cleanup_unconfirmed(error: BaseException) -> bool:
    while isinstance(error, (asyncio.CancelledError, TimeoutError)):
        if error.__cause__ is None:
            return False
        error = error.__cause__
    return isinstance(error, ProcessCleanupUnconfirmed)


def close_process_pipes(process: asyncio.subprocess.Process) -> None:
    """直接关闭本命令全部本地管道，不再等待输出 EOF。"""
    for fd in (0, 1, 2):
        pipe = process._transport.get_pipe_transport(fd)
        if pipe is not None:
            pipe.close()


async def wait_for_process_cleanup[T](task: asyncio.Task[T], *, timeout: float) -> T:
    """固定收尾预算；重复取消不延长期限，也不丢掉资源持有者。"""
    expires = asyncio.get_running_loop().time() + timeout
    cancellation: asyncio.CancelledError | None = None
    while not task.done():
        remaining = expires - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError
        try:
            done, _ = await asyncio.wait({task}, timeout=remaining)
            if not done:
                raise TimeoutError
        except asyncio.CancelledError as error:
            cancellation = error
            scope = current_process_scope.get()
            if scope is not None and scope.closed:
                raise TimeoutError from error
    result = task.result()
    if cancellation is not None:
        raise cancellation
    return result


def observe_process_exit(
    process: asyncio.subprocess.Process, *, after_task_cleanup: bool = False
) -> asyncio.Task[int]:
    """锁的退出观察者只记账；任务强制停止时须先等统一清理结束。"""
    scope = current_process_scope.get()

    async def observe() -> int:
        while process.returncode is None:
            await asyncio.sleep(0.01)
        if after_task_cleanup and scope is not None and scope.requested:
            await scope.finished.wait()
            if scope.cleanup_failed:
                raise ProcessCleanupUnconfirmed("任务强制清理失败，安装目录仍保持占用")
        return process.returncode

    return asyncio.create_task(observe(), context=detached_process_context())


def _terminate_process_tree(pid: int, *, grace_period: float = 3) -> None:
    """同步终止进程及其当前子进程，用于取消异步命令时的兜底清理。"""

    try:
        root = psutil.Process(pid)
        processes = [*root.children(recursive=True), root]
    except psutil.NoSuchProcess:
        return

    for process in reversed(processes):
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            process.terminate()

    _, alive = psutil.wait_procs(processes, timeout=grace_period)
    for process in alive:
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            process.kill()
    if alive:
        _, alive = psutil.wait_procs(alive, timeout=max(1, grace_period))
        if alive:
            raise ProcessCleanupUnconfirmed("无法确认子进程树已停止，不能释放更新目录")


async def stop_process(
    process: asyncio.subprocess.Process,
    *,
    kill_tree: bool = False,
    deadline: float | None = None,
) -> None:
    async def stop_and_wait() -> None:
        if kill_tree and process.pid is not None:
            await asyncio.to_thread(
                _terminate_process_tree,
                process.pid,
                grace_period=0 if deadline is not None else 3,
            )
        else:
            with suppress(ProcessLookupError):
                process.kill()

        # 退出确认边界：安装进程树已回收，主进程也必须已经退出。
        # 这里不使用 process.wait()，它可能被尚未关闭的输出管道拖住。
        try:
            async with asyncio.timeout(1):
                while process.returncode is None:
                    await asyncio.sleep(0.01)
        except TimeoutError as error:
            raise ProcessCleanupUnconfirmed(
                "无法确认进程已停止，不能释放更新目录"
            ) from error

        # 确认之后统一强制清理；后续新增的例外判断放在此边界之后。
        # 项目固定 Python 3.12，不排空输出、不等待 EOF，直接关闭本命令全部管道。
        close_process_pipes(process)

    # 停进程树在线程里执行；重复停止不能只取消等待，让 pip 等写入者继续运行。
    cleanup = asyncio.create_task(stop_and_wait(), context=detached_process_context())
    try:
        await wait_for_process_cleanup(cleanup, timeout=_PROCESS_CLEANUP_SECONDS)
    except (TimeoutError, ProcessCleanupUnconfirmed, psutil.Error, OSError) as error:
        cleanup.add_done_callback(_consume_result)
        close_process_pipes(process)
        if isinstance(error, TimeoutError):
            failure = ProcessCleanupUnconfirmed(
                "进程回收超时，已保留安装现场并转入任务统一清理"
            )
        elif isinstance(error, ProcessCleanupUnconfirmed):
            failure = error
        else:
            failure = ProcessCleanupUnconfirmed("进程未确认退出，安装现场仍保持占用")
        if (current := asyncio.current_task()) is not None and current.cancelling():
            raise asyncio.CancelledError from failure
        if failure is error:
            raise
        raise failure from error


def _consume_result(task: asyncio.Future) -> None:
    if not task.cancelled():
        task.exception()


@dataclass
class ProcessResult:
    stdout: str
    stderr: str
    returncode: int

    def failure_detail(self) -> str:
        """命令失败时的可读文案：returncode / stdout / stderr 一个都不能少。

        模拟器命令崩溃时这三者常常一起为空（雷电的 dnconsole.exe 返回 3221225480
        就是这种形态），只回 stdout 的话界面上只剩「命令执行失败: 」加一个空串，
        用户分不清是路径配置错、实例不存在，还是模拟器自身挂了。
        """

        return (
            f"returncode={self.returncode}, "
            f"stdout={self.stdout!r}, stderr={self.stderr!r}"
        )


# 在导入时求值一次: locale.getpreferredencoding() 每次调用都会做一轮
# 进程级 setlocale 往返, 而本函数位于日志逐行解码与 ADB 轮询热路径。
# 系统编码仍用于通用配置文件；已知脚本的中文输出应由调用方指定编码顺序。
ENCODINGS = tuple(
    e
    for e in dict.fromkeys(
        ["utf-8", "utf-8-sig", locale.getpreferredencoding(), "gbk", "gb18030"]
    )
    if e
)


def decode_bytes(
    data: bytes | None, *, encodings: tuple[str, ...] | None = None
) -> str:
    if not data:
        return ""
    for encoding in ENCODINGS if encodings is None else encodings:
        try:
            return data.decode(encoding, errors="strict")
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("latin1", errors="replace")


async def create_subprocess(
    program: Path | str,
    *args: str,
    breakaway: bool = False,
    cleanup: bool = False,
    **kwargs,
) -> asyncio.subprocess.Process:
    """按平台标志启动子进程；``breakaway=True`` 时额外脱离监督器的 Job Object。

    后端被 AUTO-MAS-Runtime 用 Job Object 监督时，子进程默认留在 Job 里，随
    后端一起被回收；只有游戏/模拟器这类不该随后端退出的进程才由调用点显式
    传 ``breakaway=True``（详见 WindowsProcessPlatform 的说明）。

    父进程若恰好处在一个不允许 breakaway 的 Job 里，带
    CREATE_BREAKAWAY_FROM_JOB 的 CreateProcess 会以 ERROR_ACCESS_DENIED
    （WinError 5，映射为 PermissionError）失败——去掉该位重试一次，此时子进程
    会留在当前 Job 里。其他 OSError 原样抛出。
    """

    from app.utils import process_platform

    platform_process = process_platform.platform_process

    # 仅由明确的收尾命令使用；不加入已关闭的业务任务 Job。
    scope = None if cleanup else current_process_scope.get()
    if scope is not None:
        scope.ensure_can_start()

    base_flags = platform_process.creation_flags | kwargs.pop("creationflags", 0)
    if scope is not None:
        base_flags |= scope.creation_flags
    breakaway_flags = platform_process.breakaway_flags if breakaway else 0
    try:
        process = await asyncio.create_subprocess_exec(
            program,
            *args,
            creationflags=base_flags | breakaway_flags,
            **kwargs,
        )
    except OSError as exc:
        if not breakaway_flags or getattr(exc, "winerror", None) != 5:
            raise

        get_logger("进程管理").warning(
            f"带 CREATE_BREAKAWAY_FROM_JOB 启动子进程被拒绝(WinError 5)，"
            f"父进程所在 Job 不允许脱离，去掉该标志重试: {program}"
        )
        process = await asyncio.create_subprocess_exec(
            program,
            *args,
            creationflags=base_flags,
            **kwargs,
        )
    if scope is not None:
        if scope.closed:
            try:
                await stop_process(process, kill_tree=True, deadline=time.monotonic())
            except Exception as error:
                raise asyncio.CancelledError from error
            raise asyncio.CancelledError
        try:
            scope.track(
                process,
                suspended=bool(scope.creation_flags),
                writer=current_update_scope.get() is scope,
            )
        except Exception:
            with suppress(ProcessLookupError):
                process.kill()
            raise
    return process


class ProcessRunner:
    @staticmethod
    async def run_process(
        program: Path | str,
        *args: str,
        cwd: Path | None = None,
        timeout: float = 60,
        if_merge_std: bool = False,
        breakaway: bool = False,
        kill_tree_on_cancel: bool = False,
        env: Mapping[str, str] | None = None,
        deadline: float | None = None,
        cleanup: bool = False,
    ) -> ProcessResult:
        """运行子进程并等待其结束，返回解码后的输出。

        breakaway 只给模拟器控制台这类会拉起不该随后端退出的进程的调用点，
        其余（taskkill/schtasks/adb 等工具）保持默认 False，留在监督器的 Job 里。
        deadline 可选，使用 time.monotonic() 的绝对时间，覆盖创建和执行；超时或
        取消后立即清理，最多再等 1 秒释放管道。要求回收进程树时，先等创建落定
        取得句柄；创建及回收各自最多等 8 秒，句柄晚到仍继续回收。
        未确认退出时保留原因，取消仍以 CancelledError 传播。
        各命令取消后的输出统一直接关闭，不再等待 EOF。
        cleanup 只用于明确的进程清理命令（如 taskkill），允许任务作用域关闭后执行。
        """

        command = [str(program), *args]
        started_at = time.monotonic()
        logger.debug(f"启动子进程: {command}")
        if deadline is not None and deadline <= started_at:
            raise TimeoutError
        loop = asyncio.get_running_loop()
        expires_at = (
            None
            if deadline is None
            else loop.time() + max(0, deadline - time.monotonic())
        )
        process = None
        try:
            async with asyncio.timeout_at(expires_at):
                creation = create_subprocess(
                    program,
                    *args,
                    breakaway=breakaway,
                    cleanup=cleanup,
                    cwd=cwd
                    or (Path(program).parent if Path(program).is_file() else None),
                    env=env,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=(
                        asyncio.subprocess.STDOUT
                        if if_merge_std
                        else asyncio.subprocess.PIPE
                    ),
                )
                if kill_tree_on_cancel:
                    # OS 已启动进程时，异步管道仍可能没有连好。直接取消
                    # create_subprocess 只会由 asyncio 杀根进程，失去构建子进程
                    # 的父子关系。等待句柄交还，再交由统一进程树清理回收。
                    pending = asyncio.create_task(creation)
                    scope = current_process_scope.get()
                    if scope is not None:
                        # OS 创建不可被强行打断；晚到句柄仍须交回已关闭的 scope 杀掉。
                        scope.pending_creations.add(pending)
                        pending.add_done_callback(scope.pending_creations.discard)
                    try:
                        process = await asyncio.shield(pending)
                    except asyncio.CancelledError as cancelled:
                        try:
                            if scope is not None and scope.closed:
                                raise TimeoutError
                            with suppress(asyncio.CancelledError):
                                await wait_for_process_cleanup(
                                    pending, timeout=_PROCESS_CLEANUP_SECONDS
                                )
                            process = pending.result()
                        except TimeoutError:

                            def reap_created(task: asyncio.Task) -> None:
                                if task.cancelled():
                                    return
                                try:
                                    created = task.result()
                                except (asyncio.CancelledError, Exception):
                                    return
                                closing = asyncio.create_task(
                                    stop_process(
                                        created, kill_tree=True, deadline=deadline
                                    ),
                                    context=detached_process_context(),
                                )
                                closing.add_done_callback(_consume_result)

                            pending.add_done_callback(reap_created)
                            raise cancelled from ProcessCleanupUnconfirmed(
                                "进程创建超时，停止等待；句柄返回后继续强制回收"
                            )
                        except Exception as error:
                            raise cancelled from error
                        raise
                else:
                    process = await creation
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
        except asyncio.CancelledError:
            # 取消运行脚本的任务时，communicate() 不会替调用方回收子进程；
            # 先结束进程并等待句柄释放，避免停止队列后留下孤儿脚本进程。
            if process is not None:
                await stop_process(
                    process, kill_tree=kill_tree_on_cancel, deadline=deadline
                )
            raise
        except asyncio.TimeoutError:
            if process is not None:
                await stop_process(
                    process, kill_tree=kill_tree_on_cancel, deadline=deadline
                )
            logger.warning(
                f"子进程命令超时: {command} - 用时: "
                f"{time.monotonic() - started_at:.3f}秒 - 超时时间: {timeout}秒"
            )
            raise

        logger.info(
            f"子进程已退出: {command} - 用时: {time.monotonic() - started_at:.3f}秒"
        )
        scope = current_process_scope.get()
        if scope is not None and not cleanup:
            scope.forget(process)

        return ProcessResult(
            stdout=decode_bytes(stdout),
            stderr=decode_bytes(stderr),
            returncode=(
                process.returncode
                if process.returncode is not None
                else await process.wait()
            ),
        )


__all__ = [
    "ProcessCleanupUnconfirmed",
    "ProcessResult",
    "ProcessRunner",
    "close_process_pipes",
    "create_subprocess",
    "decode_bytes",
    "is_process_cleanup_unconfirmed",
    "observe_process_exit",
    "stop_process",
    "wait_for_process_cleanup",
]
