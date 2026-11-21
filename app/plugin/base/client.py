"""本地客户端进程适配中间契约。"""

from abc import abstractmethod
from pathlib import Path
from typing import TypedDict, TypeVar, Unpack
from uuid import UUID

from app.config import LockTicket
from app.models.config.game import GameDeviceEntry, GameEntry
from app.plugin.base.game import GameControl
from app.utils import ProcessInfo, ProcessManager

TClient = TypeVar("TClient", bound=GameEntry, covariant=True)
TClientDevice = TypeVar("TClientDevice", bound=GameDeviceEntry, covariant=True)


class ProcessStartOptions(TypedDict, total=False):
    cwd: Path | None
    target_process: ProcessInfo | None
    stdin: int
    stdout: int
    stderr: int
    null_stream_to_pipe: bool
    elevated: bool
    breakaway: bool
    env: dict[str, str] | None


class ClientControl(GameControl[TClient, TClientDevice]):
    @property
    @abstractmethod
    def executable_path(self) -> Path | None:
        """所选实际游戏程序；路径尚未配置时为空。"""

    @property
    @abstractmethod
    def launcher_path(self) -> Path | None:
        """独立启动器路径，未设置时为空。"""

    @abstractmethod
    def checked_process(self, uid: UUID, *, ticket: LockTicket) -> ProcessManager:
        """每次借用前验证当前设备票据，进程所有权仍归插件。"""

    @abstractmethod
    async def start_process(
        self,
        uid: UUID,
        program: Path | str,
        *args: str,
        ticket: LockTicket,
        **options: Unpack[ProcessStartOptions],
    ) -> None:
        """执行已锁定专项声明的启动方式，跟踪所选目标程序。"""

    @abstractmethod
    async def track_process(
        self,
        uid: UUID,
        target: ProcessInfo,
        timeout_seconds: float = 60.0,
        min_create_time: float | None = None,
        *,
        ticket: LockTicket,
        owned: bool = True,
    ) -> None:
        """将现有进程观察限定于所选游戏目标。"""

    @abstractmethod
    async def stop_process(self, uid: UUID, *, ticket: LockTicket) -> None:
        """结束所选游戏的真实进程，失败须向调用任务报告。"""

    @abstractmethod
    async def start_protocol(
        self, uid: UUID, url: str, target: ProcessInfo, *, ticket: LockTicket
    ) -> None:
        """使用已有协议入口启动，并将观察限定于所选游戏。"""
