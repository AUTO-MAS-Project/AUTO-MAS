from pathlib import Path
from typing import Optional, List, Dict, Tuple
from app.core import Config
from app.models.config import EmulatorManagerConfig
from app.utils import get_logger

from .mumu import MumuManager
from .ldplayer import LDManager
from .general import GeneralDeviceManager
from .utils import BaseDevice, DeviceStatus
from .emulator_search import search_emulators
from typing import Literal

logger = get_logger("模拟器管理")


class EmulatorManager:
    """模拟器实例管理器（保持原有功能）"""

    def __init__(self) -> None:
        self.config = Config.EmulatorData
        self.emulator_dict = {}

    async def create_emulator_instance(
        self, config_instance: EmulatorManagerConfig
    ) -> tuple[Literal[True], BaseDevice] | tuple[Literal[False], None]:
        """
        根据emulator_type创建对应的模拟器管理器实例

        Args:
            config_instance: 模拟器配置实例

        Returns:
            对应的模拟器管理器实例
        """
        emulator_type = config_instance.get("Info", "Type")
        try:
            if emulator_type == "mumu":
                return True, MumuManager(config_instance)
            elif emulator_type == "ldplayer":
                return True, LDManager(config_instance)
            elif emulator_type == "general":
                return True, GeneralDeviceManager(config_instance)
            else:
                return False, None
        except:  # noqa: E722
            return False, None

    async def start_emulator(
        self, uuid: str, index: str, package_name: str = ""
    ) -> tuple[bool, str, dict]:
        """
        根据UUID和模拟器索引打开指定模拟器

        Args:
            uuid (str): 配置项的UUID
            index (str): 模拟器索引
            package_name (str, optional): 启动包名

        Returns:
            tuple[bool, str, dict]: (是否成功, 结果, adb信息)
        """
        # 检查UUID是否存在
        if uuid not in self.emulator_dict:
            return False, f"未找到UUID为 {uuid} 的模拟器配置", {}

        # 获取对应的模拟器实例
        emulator_instance = self.emulator_dict[uuid]

        try:
            # 调用模拟器实例的start方法启动指定索引的模拟器
            success, status, info = await emulator_instance.start(index, package_name)

            if success:
                return (
                    True,
                    f"成功启动模拟器，索引: {index}，状态: {DeviceStatus(status).name}",
                    info,
                )
            else:
                return (
                    False,
                    f"启动模拟器失败，索引: {index}，状态: {DeviceStatus(status).name}",
                    info,
                )

        except Exception as e:
            return False, f"启动模拟器时发生异常: {str(e)}", {}

    async def close_emulator(self, uuid: str, index: str) -> tuple[bool, str]:
        """
        根据UUID和模拟器索引关闭指定模拟器

        Args:
            uuid (str): 配置项的UUID
            index (str): 模拟器索引

        Returns:
            tuple[bool, str]: (是否成功, 结果信息)
        """
        # 检查UUID是否存在
        if uuid not in self.emulator_dict:
            return False, f"未找到UUID为 {uuid} 的模拟器配置"

        # 获取对应的模拟器实例
        emulator_instance = self.emulator_dict[uuid]

        try:
            # 调用模拟器实例的close方法关闭指定索引的模拟器
            success, status = await emulator_instance.close(index)

            if success:
                return (
                    True,
                    f"成功关闭模拟器，索引: {index}，状态: {DeviceStatus(status).name}",
                )
            else:
                return (
                    False,
                    f"关闭模拟器失败，索引: {index}，状态: {DeviceStatus(status).name}",
                )

        except Exception as e:
            return False, f"关闭模拟器时发生异常: {str(e)}"

    async def get_all_emulator_status(
        self,
    ) -> tuple[Literal[True], dict] | tuple[Literal[False], str]:
        """
        获取所有模拟器的状态

        Returns:
            tuple[bool, str]: (是否成功, 状态信息)
        """
        data = {}
        try:
            for uuid, emulator_instance in self.emulator_dict.items():
                info = {}
                info = await emulator_instance.get_all_info()
                data[uuid] = info
            return True, data
        except Exception as e:
            return False, f"获取模拟器状态时发生异常: {str(e)}"

    async def get_emulator_status(
        self, uuid
    ) -> tuple[Literal[True], dict] | tuple[Literal[False], str]:
        """
        获取模拟器的状态

        Returns:
            tuple[bool, str]: (是否成功, 状态信息)
        """
        info = {}
        try:
            emulator_instance = self.emulator_dict.get(uuid)
            if emulator_instance:
                info = await emulator_instance.get_all_info()
            return True, info
        except Exception as e:
            return False, f"获取模拟器状态时发生异常: {str(e)}"


# 全局配置管理器实例
emulator_manager = EmulatorManager()
