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


def decode_bytes(data: bytes | None) -> str:
    if not data:
        return ""
    for encoding in (
        "utf-8",
        "utf-8-sig",
        locale.getpreferredencoding(),
        "gbk",
        "gb18030",
    ):
        try:
            return data.decode(encoding, errors="strict")
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("latin1", errors="replace")


class ProcessRunner:
    @staticmethod
    async def run_process(
        program: Path | str,
        *args: str,
        cwd: Path | None = None,
        timeout: float = 60,
        if_merge_std: bool = False,
    ) -> ProcessResult:
        from app.utils.platform.process import platform_process

        process = await asyncio.create_subprocess_exec(
            program,
            *args,
            cwd=cwd or (Path(program).parent if Path(program).is_file() else None),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=(
                asyncio.subprocess.STDOUT if if_merge_std else asyncio.subprocess.PIPE
            ),
            creationflags=platform_process.creation_flags,
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


__all__ = ["ProcessResult", "ProcessRunner", "decode_bytes"]
