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
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Literal, Mapping, Self, cast


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


@dataclass(frozen=True, slots=True)
class EmulatorRuntimeConfig:
    """Validated immutable snapshot consumed by emulator device drivers."""

    name: str
    emulator_type: Literal["general", "mumu", "ldplayer"]
    path: str
    boss_key: str
    max_wait_time: int
    force_kill_on_close: bool

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> Self:
        info = payload.get("Info")
        if not isinstance(info, Mapping):
            raise TypeError("模拟器配置缺少 Info 对象")

        name = info.get("Name")
        emulator_type = info.get("Type")
        path = info.get("Path")
        boss_key = info.get("BossKey")
        max_wait_time = info.get("MaxWaitTime")
        force_kill_on_close = info.get("ForceKillOnClose")

        for field_name, value in (
            ("Name", name),
            ("Path", path),
            ("BossKey", boss_key),
        ):
            if not isinstance(value, str):
                raise TypeError(f"模拟器配置 Info.{field_name} 必须是字符串")
        if emulator_type not in {"general", "mumu", "ldplayer"}:
            raise ValueError(f"不支持的模拟器类型: {emulator_type}")
        if (
            not isinstance(max_wait_time, int)
            or isinstance(max_wait_time, bool)
            or max_wait_time < 1
        ):
            raise ValueError("模拟器配置 Info.MaxWaitTime 必须是正整数")
        if not isinstance(force_kill_on_close, bool):
            raise TypeError("模拟器配置 Info.ForceKillOnClose 必须是布尔值")

        return cls(
            name=name,
            emulator_type=cast(
                Literal["general", "mumu", "ldplayer"],
                emulator_type,
            ),
            path=path,
            boss_key=boss_key,
            max_wait_time=max_wait_time,
            force_kill_on_close=force_kill_on_close,
        )

    def get(self, group: str, name: str) -> Any:
        if group != "Info":
            raise AttributeError(f"配置项 '{group}.{name}' 不存在")
        fields: dict[str, object] = {
            "Name": self.name,
            "Type": self.emulator_type,
            "Path": self.path,
            "BossKey": self.boss_key,
            "MaxWaitTime": self.max_wait_time,
            "ForceKillOnClose": self.force_kill_on_close,
        }
        if name not in fields:
            raise AttributeError(f"配置项 '{group}.{name}' 不存在")
        return fields[name]


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
