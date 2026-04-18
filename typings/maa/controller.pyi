from typing import Any


class Job:
    failed: bool

    def wait(self) -> Any: ...


class JobWithResult(Job):
    def get(self) -> Any: ...


class AdbController:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

    def post_connection(self) -> Job: ...


class Win32Controller:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

    def post_connection(self) -> Job: ...


class MaaAdbScreencapMethodEnum:
    Default: int


class MaaAdbInputMethodEnum:
    Default: int


class MaaWin32ScreencapMethodEnum:
    FramePool: int
    PrintWindow: int


class MaaWin32InputMethodEnum:
    Seize: int
    PostMessageWithCursorPos: int
