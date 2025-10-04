import subprocess
import os
from abc import ABC, abstractmethod
from enum import IntEnum
from app.models.config import EmulatorManagerConfig


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


class ExeRunner:
    def __init__(self, exe_path, encoding) -> None:
        """
        指定 exe 路径
        !请传入绝对路径，使用/分隔路径
        """
        if not os.path.isfile(exe_path):
            raise FileNotFoundError(f"找不到文件: {exe_path}")
        self.exe_path = os.path.abspath(exe_path)  # 转为绝对路径
        self.encoding = encoding

    def run(self, *args) -> subprocess.CompletedProcess[str]:
        """
        执行命令，返回结果
        """
        cmd = [self.exe_path] + list(args)
        print(f"执行: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding=self.encoding,
            errors="replace",
        )
        return result


class BaseDevice(ABC):
    def __init__(self, config: EmulatorManagerConfig) -> None:
        self.max_wait_time = config.get("Data", "max_wait_time")

    @abstractmethod
    async def start(self, idx: str, package_name: str) -> tuple[bool, int, dict]:
        """
        启动设备
        返回值: (是否成功, 状态码, 启动信息)
        """
        ...

    @abstractmethod
    async def close(self, idx: str) -> tuple[bool, int]:
        """
        关闭设备或服务
        返回值: (是否成功, 状态码)
        """
        ...

    @abstractmethod
    async def get_status(self, idx: str) -> int:
        """
        获取指定模拟器当前状态
        返回值: 状态码
        """
        ...

    @abstractmethod
    async def hide_device(self, idx: str) -> tuple[bool, int]:
        """
        隐藏设备窗口
        返回值: (是否成功, 状态码)
        """
        ...

    @abstractmethod
    async def show_device(self, idx: str) -> tuple[bool, int]:
        """
        显示设备窗口
        返回值: (是否成功, 状态码)
        """
        ...

    async def get_all_info(self) -> dict[str, dict[str, str]]:
        """
        获取设备信息
        返回值: 设备字典
        结构示例:
        {
            "0":{
                "title": 模拟器名字,
                "status": "1"
            }
        }
        """
        ...
