"""模拟器管理中间基类：在 GameControl 上补模拟器通行操作。"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, TypeVar
from uuid import UUID

from app.config.core.node import LockTicket
from app.models.config.plugin_emulator import EmulatorDeviceEntry, EmulatorEntry
from app.models.emulator import (
    DeviceInfo,
    DeviceRef,
    EmulatorAdbInfo,
    HostAdb,
    InstanceSettings,
)
from app.plugin.base.game import GameControl

TEmulator = TypeVar("TEmulator", bound=EmulatorEntry, covariant=True)
TEmulatorDevice = TypeVar("TEmulatorDevice", bound=EmulatorDeviceEntry, covariant=True)


@dataclass(frozen=True)
class EmulatorExpect:
    """任务对实例的期望。订阅时备份原状并写入，退订时整份还原。

    作为 ``subscribe_device`` 的 ``expect`` 传入，品牌钩子里解释。
    两类关键项，口径取自非插件版 ``app/utils/emulator2``：

    - **分辨率**（``settings.py``）：逐任务不同，故必填。宽高成对 —— 厂商侧
      按另一半的旧值算比例，单改一边得到的是任务没见过的布局。``dpi`` 为
      ``None`` 时不动，不替用户猜像素密度。
    - **稳定模式**（``stability.py``）：脚本靠「截图 + 固定坐标」，下面几项会
      破坏这两个前提。开关项一律三态：``None`` 不做要求，该键一个字都不碰；
      给了值就按值覆写，不看厂商当前是什么 —— 任务要什么写什么，品牌不做判断。
      枚举项（``*_strategy``）给**容许值列表**：当前值在表内就不动（那是用户
      的性能偏好），越界才写表首。判据同样来自任务，品牌只做键映射。

    ``expect`` 为 ``None`` 表示任务不提期望：只备份与还原，一个键都不写。
    """

    width: int
    height: int
    dpi: int | None = None
    # 后台保活：MAA 的 issue 模板要求填报，视为故障相关因素
    keep_alive: bool | None = None
    # 动态调帧 / 高帧率：同样被 MAA issue 模板收集
    high_frame_rate: bool | None = None
    # 垂直同步会让画面按显示器节奏出帧，截到的可能是上一帧
    vertical_sync: bool | None = None
    # 帧率浮层是画在画面上的，直接进截图，可能盖住要识别的元素
    display_fps: bool | None = None
    # 自动旋转一转，固定坐标全废
    auto_rotate: bool | None = None
    # 显存使用策略：枚举项，取值是厂商自己的档位名（MuMu 为 auto / perf / dis）。
    # 给容许值列表，越界写表首 —— MAA 文档只点名「资源占用更小」(dis) 不可用，
    # 故任务给 ``("auto", "perf")``：两档都放过，只把 dis 拨回 auto。
    vram_strategy: tuple[str, ...] | None = None


class EmulatorControl(GameControl[TEmulator, TEmulatorDevice]):
    """模拟器通行控制。open 可带包名；触发器路径不传包名。

    实例订阅走基类的 ``subscribe_device`` / ``unsubscribe_device``：``expect``
    传 ``EmulatorExpect``，品牌在 ``_on_device_subscribed`` /
    ``_on_device_unsubscribed`` 里备份、写入与还原。

    用户设置使用各插件支持的有限设置契约；任务只声明 ``EmulatorExpect``，
    临时修改在退订时恢复，恢复失败保留原值供下次重试。
    """

    kind: ClassVar[str] = "general"

    @abstractmethod
    async def open(
        self, device_uid: UUID, package: str | None = None, *, ticket: LockTicket
    ) -> None:
        """启动模拟器；``package`` 非空时就绪后拉起该应用。"""

    @abstractmethod
    async def launch_app(
        self, device_uid: UUID, package: str, *, ticket: LockTicket
    ) -> None:
        """设备已在线时只拉起应用，不重开模拟器。"""

    @abstractmethod
    async def open_store(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        """打开该品牌应用商店 / 游戏中心。"""

    @abstractmethod
    async def create_instance(self, name: str | None = None) -> UUID:
        """厂商侧新建多开，refresh 后返回新设备 uid。新建无既有身份，不校验凭据。"""

    @abstractmethod
    async def delete_instance(self, device_uid: UUID, *, ticket: LockTicket) -> None:
        """厂商侧删除多开并对齐 devices。"""

    @abstractmethod
    async def install_app(
        self, device_uid: UUID, path: Path, *, ticket: LockTicket
    ) -> None:
        """将宿主机 ``path`` 指向的安装包（APK 等）装到该实例。"""

    async def device_info(self, uid: UUID) -> DeviceInfo:
        """读取真实设备状态、ADB 地址及进程身份。"""
        raise NotImplementedError

    def resolve_device(self, uid: UUID) -> DeviceRef:
        """返回真实安装与原生实例号，不把稳定 UID 当作原生序号。"""
        raise NotImplementedError

    def get_adb_path(self) -> Path | None:
        return None

    def installation_root(self, uid: UUID) -> Path:
        return Path(self.resolve_device(uid).manager_path).parent

    async def adb_info(self, uid: UUID) -> EmulatorAdbInfo | None:
        return None

    async def host_adb(self, uid: UUID) -> HostAdb | None:
        return None

    async def process_env(self, uid: UUID) -> dict[str, str] | None:
        return None

    async def read_settings(self, uid: UUID) -> InstanceSettings:
        raise NotImplementedError("此设备不提供实例设置")

    async def write_settings(
        self,
        uid: UUID,
        changes: dict[str, int],
        expected: dict[str, int | None] | None,
        *,
        ticket: LockTicket,
    ) -> dict[str, int]:
        raise NotImplementedError("此设备不提供实例设置")

    async def save_settings(
        self,
        uid: UUID,
        changes: dict[str, int],
        expected: dict[str, int | None] | None,
        *,
        ticket: LockTicket,
    ) -> InstanceSettings:
        """保存用户设置，由插件维护本身的配置守卫基准。"""
        raise NotImplementedError("此设备不提供实例设置")

    async def capture_baseline(
        self, uid: UUID, *, ticket: LockTicket
    ) -> dict[str, int]:
        """由插件读取并保存其支持的配置守卫基准。"""
        raise NotImplementedError("此设备不提供配置守卫")

    async def maafw_adb_extra(self, uid: UUID) -> dict[str, object]:
        raise NotImplementedError("此设备不提供 MaaFW ADB 扩展设置")

    def supports_maafw_adb_extra_version(self, version: str | None) -> bool | None:
        return None

    async def apply_stable_mode(self, uid: UUID, *, ticket: LockTicket) -> list[str]:
        raise NotImplementedError("此设备不提供稳定模式")

    async def instance_options(self, uid: UUID) -> dict:
        raise NotImplementedError("此设备不提供实例选项")

    async def close_all(self) -> None:
        """宿主电源动作前关闭当前安装，具体插件可使用原生批量入口。"""
        from app.models.config.game import TRIGGER_TICKET
        from app.utils import get_logger

        try:
            await self.refresh()
        except Exception as error:
            get_logger("游戏管理").warning(f"读取设备失败，继续关闭已登记实例：{error}")
        for device in list(self.config.devices.values()):
            if getattr(device.info, "tombstone", False):
                continue
            try:
                await self.close(device.uid, ticket=TRIGGER_TICKET)
            except Exception as error:
                get_logger("游戏管理").warning(f"关闭设备失败，继续其他实例：{error}")
