import asyncio
import locale
import time
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

import psutil

from app.utils import get_logger

logger = get_logger("进程管理")
_PROCESS_CLEANUP_SECONDS = 8


class ProcessCleanupUnconfirmed(RuntimeError):
    """进程树未确认停止，调用方必须保留可能仍被写入的文件。"""


def is_process_cleanup_unconfirmed(error: BaseException) -> bool:
    """识别取消和 asyncio 超时包装中保留的未确认退出原因。"""
    while isinstance(error, (asyncio.CancelledError, TimeoutError)):
        if error.__cause__ is None:
            return False
        error = error.__cause__
    return isinstance(error, ProcessCleanupUnconfirmed)


def close_process_pipes(process: asyncio.subprocess.Process) -> None:
    """释放本地读端，不终止继承了写端的后台服务。"""
    # StreamReader 没有公开的 close；项目固定 Python 3.12，升级时需核对接口。
    for fd in (1, 2):
        pipe = process._transport.get_pipe_transport(fd)
        if pipe is not None:
            pipe.close()


async def wait_for_process_cleanup[T](task: asyncio.Task[T], *, timeout: float) -> T:
    """在固定收尾预算内推迟重复取消，超时不取消仍持有资源的工作。"""
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
        except asyncio.CancelledError as exc:
            cancellation = exc
    result = task.result()
    if cancellation is not None:
        raise cancellation
    return result


def _terminate_process_tree(pid: int, *, grace_period: float = 3) -> None:
    """同步终止进程及其当前子进程，用于取消异步命令时的兜底清理。"""

    try:
        root = psutil.Process(pid)
        processes = [*root.children(recursive=True), root]
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return

    for process in reversed(processes):
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            process.terminate()

    _, alive = psutil.wait_procs(processes, timeout=grace_period)
    for process in alive:
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            process.kill()
    if alive and grace_period > 0:
        psutil.wait_procs(alive, timeout=grace_period)


async def stop_process(
    process: asyncio.subprocess.Process,
    *,
    kill_tree: bool = False,
    deadline: float | None = None,
) -> None:
    """回收命令后有界排空管道；不能确认停写时明确报错。"""

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
        # 进程树回收完成后也不能无限等待失去父子关系的后台进程关闭管道。
        try:
            async with asyncio.timeout(1):
                # communicate 的读协程已被取消；仅 wait 会留下暂停读取的满管道。
                await process.communicate()
        except TimeoutError:
            close_process_pipes(process)
            if kill_tree:
                raise ProcessCleanupUnconfirmed(
                    "命令已停止，但子进程尚未确认退出，已保留可能仍被写入的文件"
                ) from None
            logger.warning("子进程已发送终止信号，等待输出管道关闭超时，已关闭本地读端")

    # 停进程树在线程里执行；重复停止不能只取消等待，让 pip 等写入者继续运行。
    cleanup = asyncio.create_task(stop_and_wait())
    try:
        await wait_for_process_cleanup(cleanup, timeout=_PROCESS_CLEANUP_SECONDS)
    except (TimeoutError, ProcessCleanupUnconfirmed) as error:
        failure = error
        if isinstance(error, TimeoutError):
            close_process_pipes(process)
            cleanup.add_done_callback(
                lambda task: None if task.cancelled() else task.exception()
            )
            failure = ProcessCleanupUnconfirmed(
                "进程回收超过等待上限，已保留可能仍被写入的文件"
            )
        # 保留标准取消类型，避免普通失败处理吞掉停止，也兼容 asyncio.timeout。
        if (current := asyncio.current_task()) is not None and current.cancelling():
            raise asyncio.CancelledError from failure
        if failure is error:
            raise
        raise failure from error


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

    base_flags = platform_process.creation_flags
    breakaway_flags = platform_process.breakaway_flags if breakaway else 0
    try:
        return await asyncio.create_subprocess_exec(
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
        return await asyncio.create_subprocess_exec(
            program,
            *args,
            creationflags=base_flags,
            **kwargs,
        )


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
    ) -> ProcessResult:
        """运行子进程并等待其结束，返回解码后的输出。

        breakaway 只给模拟器控制台这类会拉起不该随后端退出的进程的调用点，
        其余（taskkill/schtasks/adb 等工具）保持默认 False，留在监督器的 Job 里。
        deadline 可选，使用 time.monotonic() 的绝对时间，覆盖创建和执行；超时或
        取消后立即清理，最多再等 1 秒释放管道。要求回收进程树时，先等创建落定
        取得句柄，最多等待 8 秒；句柄晚到时仍继续回收。输出管道收尾最多等待 1 秒，进程树
        未确认停止时保留 ProcessCleanupUnconfirmed 原因，取消仍向上抛出
        CancelledError。写入方须检查该原因，不得删除仍可能被使用的文件。
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
                    try:
                        process = await asyncio.shield(pending)
                    except asyncio.CancelledError as cancelled:
                        try:
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
                                except Exception as creation_error:
                                    logger.warning(
                                        f"取消后的进程创建失败: {creation_error}"
                                    )
                                    return
                                cleanup = asyncio.create_task(
                                    stop_process(
                                        created, kill_tree=True, deadline=deadline
                                    )
                                )
                                cleanup.add_done_callback(
                                    lambda done: (
                                        None if done.cancelled() else done.exception()
                                    )
                                )

                            pending.add_done_callback(reap_created)
                            failure = ProcessCleanupUnconfirmed(
                                "进程创建尚未结束，已停止等待；句柄返回后将继续回收，请保留相关文件"
                            )
                            raise cancelled from failure
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
    "stop_process",
    "wait_for_process_cleanup",
]
