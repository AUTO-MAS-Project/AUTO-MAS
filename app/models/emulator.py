#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum


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


class DeviceBase(ABC):

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
