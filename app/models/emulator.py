#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path


@dataclass(frozen=True)
class EmulatorRuntimePolicy:
    """宿主提供的实时运行策略；读取异常由各消费点按原有语义处理。"""

    silence_enabled: Callable[[], bool]
    block_ads_enabled: Callable[[], bool]
    resource_path: Path


class DeviceStatus(IntEnum):
    ONLINE = 0
    """设备在线"""
    OFFLINE = 1
    """设备离线"""
    STARTING = 2
    """设备开启中"""
    CLOSEING = 3
    """设备关闭中"""
    ERROR = 4
    """错误"""
    NOT_FOUND = 5
    """未找到设备"""
    UNKNOWN = 10
    """未知状态"""


@dataclass
class DeviceInfo:
    title: str
    status: DeviceStatus
    adb_address: str
    app_launch: str = ""
    """``open`` 带包名时拉应用那一步的结果（``AppLaunchResult.reason``，如冷启动 ``launched``、
    在前台 ``already-running``、从后台切回 ``resumed``）；没拉应用、或后端不支持带包启动时为空串。"""
    process_id: int | None = None
    """模拟器进程号；脚本等 adb 时据此判断模拟器是不是已经退出，退出了就不再空等。目前只有魔改 AVD
    的 ``open`` 给（qemu 进程），其它后端为 ``None``。"""
    process_started_at: float | None = None
    """该进程的启动时刻（Unix 秒，``psutil.Process.create_time()``）。和进程号一起比对，进程号被
    系统复用给别的进程时也能认出原来的模拟器已经没了。"""


@dataclass(frozen=True)
class DeviceRef:
    """一个设备索引解析出来的真实归属。

    ``manager_path`` 与 ``EmulatorConfig`` 的 ``Info.Path`` 同口径, 即主管理器程序
    （雷电是 ``ldconsole.exe``、MuMu 是 ``MuMuManager.exe``）的路径, 不是安装目录。
    ``native_index`` 是模拟器自己的实例索引, 用来算 ADB 端口等, 不能拿设备号顶替。
    """

    emulator_type: str
    manager_path: str
    native_index: str


class DeviceBase(ABC):
    """模拟器管理基类"""

    @abstractmethod
    async def open(self, idx: str, package_name: str = "") -> DeviceInfo:
        """
        启动设备

        Parameters
        ----------
        idx : str
            设备索引
        package_name : str
            启动的应用包名

        Returns
        -------
        DeviceInfo
            设备信息
        """
        ...

    @abstractmethod
    async def close(self, idx: str) -> DeviceStatus:
        """
        关闭设备或服务

        Parameters
        ----------
        idx : str
            设备索引

        Returns
        -------
        DeviceStatus
            设备状态
        """
        ...

    @abstractmethod
    async def getStatus(self, idx: str) -> DeviceStatus:
        """
        获取指定模拟器当前状态

        Parameters
        ----------
        idx : str
            设备索引

        Returns
        -------
        DeviceStatus
            设备状态
        """
        ...

    @abstractmethod
    async def list_devices(self) -> dict[str, str]:
        """获取可选设备实例。

        Returns:
            dict[str, str]: 设备索引与显示名称的映射。
        """
        ...

    @abstractmethod
    async def getInfo(self, idx: str | None) -> dict[str, DeviceInfo]:
        """
        获取设备信息

        Returns
        -------
        dict[str, DeviceInfo]
            设备信息字典，键为设备索引，值为设备信息
        """
        ...

    @abstractmethod
    async def setVisible(self, idx: str, is_visible: bool) -> DeviceStatus:
        """
        设置设备窗口可见性

        Parameters
        ----------
        idx : str
            设备索引
        is_visible : bool
            是否可见

        Returns
        -------
        DeviceStatus
            设备状态
        """
        ...

    def get_adb_path(self) -> Path | None:
        """
        获取该模拟器自带的 adb 可执行文件路径

        Returns
        -------
        Path | None
            自带 adb 的路径; 返回 ``None`` 表示该模拟器不自带 adb, 调用方应回退到系统 adb
        """
        return None

    def resolve_device(self, idx: str) -> "DeviceRef | None":
        """把设备索引解析成「真实模拟器类型 + 管理器路径 + 原生索引」

        脚本适配器里有几处不经管理器、直接读持久化配置的类型和路径来决定要不要启用
        模拟器专用能力（雷电专用连接、EmulatorExtras 截图）。一条配置纳管多个模拟器
        安装时，持久化的类型不再等于某个设备的真实类型，那些判断就会失效。
        调用方改成问这个方法，就不必关心配置形态。

        默认实现直接回报本管理器自己的类型与路径, 索引原样透传——对「一条配置一个安装」
        的旧配置永远成立。纳管多个安装的管理器需要覆盖它。

        Parameters
        ----------
        idx : str
            设备索引

        Returns
        -------
        DeviceRef | None
            解析结果; 返回 ``None`` 表示解析不出, 调用方应按「没有专用能力」处理
        """
        config = getattr(self, "config", None)
        if config is None:
            return None
        try:
            return DeviceRef(
                emulator_type=str(config.Info.Type or ""),
                manager_path=str(config.Info.Path or ""),
                native_index=str(idx),
            )
        except Exception:  # noqa: BLE001 - 解析不出就当没有专用能力, 不该让调用方炸
            return None


DeviceProvider = Callable[[str], Awaitable[DeviceBase]]
"""按模拟器 ID 取设备实例。缺省实现是 ``app.core`` 的 EmulatorManager 单例；
脚本域经构造参数注入可替换的实现, 测试与扩展用得上。"""
