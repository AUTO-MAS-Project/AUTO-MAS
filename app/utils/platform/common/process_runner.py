import asyncio
import locale
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProcessResult:
    stdout: str
    stderr: str
    returncode: int


# 在导入时求值一次: locale.getpreferredencoding() 每次调用都会做一轮
# 进程级 setlocale 往返, 而本函数位于日志逐行解码与 ADB 轮询热路径
ENCODINGS = tuple(
    e
    for e in dict.fromkeys(
        ["utf-8", "utf-8-sig", locale.getpreferredencoding(), "gbk", "gb18030"]
    )
    if e
)


def decode_bytes(data: bytes | None) -> str:
    if not data:
        return ""
    for encoding in ENCODINGS:
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

    from app.utils.platform.process import platform_process

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
        from app.utils import get_logger

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
    ) -> ProcessResult:
        """运行子进程并等待其结束，返回解码后的输出。

        breakaway 只给模拟器控制台这类会拉起不该随后端退出的进程的调用点，
        其余（taskkill/schtasks/adb 等工具）保持默认 False，留在监督器的 Job 里。
        """

        process = await create_subprocess(
            program,
            *args,
            breakaway=breakaway,
            cwd=cwd or (Path(program).parent if Path(program).is_file() else None),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=(
                asyncio.subprocess.STDOUT if if_merge_std else asyncio.subprocess.PIPE
            ),
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


__all__ = ["ProcessResult", "ProcessRunner", "create_subprocess", "decode_bytes"]
