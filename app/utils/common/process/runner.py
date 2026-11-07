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


async def _stop_process(
    process: asyncio.subprocess.Process,
    *,
    kill_tree: bool,
    deadline: float | None,
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
        # 不回收进程树的命令可能拉起 ADB 服务，不能等后台服务关闭管道。
        # 依赖安装等写入者仍沿用原有等待策略，避免提前交还正在写入的目录。
        try:
            async with asyncio.timeout(
                1 if deadline is not None or not kill_tree else None
            ):
                # communicate 的读协程已被取消；仅 wait 会留下暂停读取的满管道。
                await process.communicate()
        except TimeoutError:
            # StreamReader 没有公开的 close；只释放本地读端，保留后台服务。
            # 项目固定 Python 3.12，升级时需核对 transport 接口。
            for fd in (1, 2):
                pipe = process._transport.get_pipe_transport(fd)
                if pipe is not None:
                    pipe.close()
            logger.warning("子进程已发送终止信号，等待输出管道关闭超时，已关闭本地读端")

    # 停进程树在线程里执行；重复停止不能只取消等待，让 pip 等写入者继续运行。
    cleanup = asyncio.create_task(stop_and_wait())
    cancellation: asyncio.CancelledError | None = None
    while not cleanup.done():
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError as exc:
            cancellation = exc
    cleanup.result()
    if cancellation is not None:
        raise cancellation


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
        取得句柄，再回收已启动的子进程。不回收进程树时，输出管道收尾也只等 1 秒；
        未传 deadline 的进程树回收保留原有等待策略。
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
                            while not pending.done():
                                try:
                                    await asyncio.shield(pending)
                                except asyncio.CancelledError:
                                    continue
                            process = pending.result()
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
                with suppress(asyncio.CancelledError):
                    await _stop_process(
                        process, kill_tree=kill_tree_on_cancel, deadline=deadline
                    )
            raise
        except asyncio.TimeoutError:
            if process is not None:
                await _stop_process(
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


__all__ = ["ProcessResult", "ProcessRunner", "create_subprocess", "decode_bytes"]
