"""进程平台差异契约；共享的进程匹配和任务等待仍在 common。"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from subprocess import Popen
from typing import IO, Protocol, TypedDict, Unpack


class EmulatorPopenOptions(TypedDict, total=False):
    stdin: int | IO[bytes] | None
    stdout: int | IO[bytes] | None
    stderr: int | IO[bytes] | None
    cwd: str | Path | None
    env: Mapping[str, str] | None
    close_fds: bool


class ElevatedProcess(Protocol):
    def __call__(
        self, program: str | Path, args: Sequence[str], cwd: str | Path | None
    ) -> None: ...


class ProcessPlatform(Protocol):
    @property
    def supports_elevation(self) -> bool: ...

    @property
    def creation_flags(self) -> int: ...
    @property
    def breakaway_flags(self) -> int: ...
    @property
    def detached_flags(self) -> int: ...
    @property
    def agent_flags(self) -> int: ...
    @property
    def emulator_flags(self) -> int: ...

    async def open_protocol(self, protocol_url: str) -> None: ...
    async def kill_process(
        self, pid: int, kill_tree: bool = False
    ) -> tuple[bool, str]: ...
    def popen_emulator(
        self, args: Sequence[str], **kwargs: Unpack[EmulatorPopenOptions]
    ) -> Popen[bytes]: ...
    def prepare_elevated(self) -> ElevatedProcess: ...


class ProcessAPI(Protocol):
    @property
    def platform_process(self) -> ProcessPlatform: ...
