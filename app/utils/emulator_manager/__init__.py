from app.models.config import EmulatorManagerConfig
from app.models.ConfigBase import MultipleConfig

from app.utils.emulator_manager.mumu import MumuManager
from app.utils.emulator_manager.ldplayer import LDManager
from app.utils.emulator_manager.general import GeneralDeviceManager
from app.utils.emulator_manager.utils import BaseDevice, DeviceStatus
from typing import Literal


class EmulatorManager:
    def __init__(self) -> None:
        self.config = MultipleConfig([EmulatorManagerConfig])

    async def init(self) -> None:
        self.emulator_dict = await self.build_emulator_dict()

    async def create_emulator_instance(
        self, config_instance: EmulatorManagerConfig
    ) -> tuple[Literal[True], BaseDevice] | tuple[Literal[False], None]:
        """
        根据emulator_type创建对应的模拟器管理器实例

        Args:
            emulator_type (str): 模拟器类型

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

    async def build_emulator_dict(self) -> dict[str, BaseDevice]:
        """
        构建模拟器实例字典，用于存储所有模拟器实例
        !若实例类失败，则不会添加进字典
        """
        emulator_dict = {}
        for config_id, config_instance in self.config.items():
            OK, emulator_instance = await self.create_emulator_instance(config_instance)
            if OK:
                emulator_dict[config_id] = emulator_instance

        return emulator_dict

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
        result = {}
        try:
            for uuid, emulator_instance in self.emulator_dict.items():
                info = await emulator_instance.get_all_info()
                result[uuid] = info
            return True, result
        except Exception as e:
            return False, f"获取模拟器状态时发生异常: {str(e)}"
