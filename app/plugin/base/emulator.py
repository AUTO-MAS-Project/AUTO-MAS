"""模拟器管理中间基类：在 GameControl 上补模拟器通行操作。"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from uuid import UUID
from pathlib import Path

from app.config.core.node import LockTicket
from app.models.config.emulator import EmulatorDeviceEntry, EmulatorEntry
from app.plugin.base.game import GameControl


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


class EmulatorControl(GameControl[EmulatorEntry, EmulatorDeviceEntry]):
    """模拟器通行控制。open 可带包名；触发器路径不传包名。

    实例订阅走基类的 ``subscribe_device`` / ``unsubscribe_device``：``expect``
    传 ``EmulatorExpect``，品牌在 ``_on_device_subscribed`` /
    ``_on_device_unsubscribed`` 里备份、写入与还原。

    不含「自定义任意实例设置」的通行方法：实例设置由用户在厂商界面里定，
    任务只声明 ``EmulatorExpect`` 里那几项，别的键一律原样保留。
    """

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
