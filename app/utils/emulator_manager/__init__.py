import uuid
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from app.models.config import EmulatorManagerConfig
from app.models.ConfigBase import MultipleConfig
from app.utils import get_logger

from app.utils.emulator_manager.mumu import MumuManager
from app.utils.emulator_manager.ldplayer import LDManager
from app.utils.emulator_manager.general import GeneralDeviceManager
from app.utils.emulator_manager.utils import BaseDevice, DeviceStatus
from app.utils.emulator_manager.emulator_search import search_emulators
from typing import Literal

logger = get_logger("模拟器管理")


class EmulatorConfigManager:
    """模拟器配置管理器"""

    def __init__(self) -> None:
        self.config = MultipleConfig([EmulatorManagerConfig])
        self.config_path = Path.cwd() / "config" / "EmulatorManagerConfig.json"
        self._initialized = False

    async def init(self) -> None:
        """初始化模拟器配置管理器"""
        if not self._initialized:
            await self.config.connect(self.config_path)
            self._initialized = True
            logger.info("模拟器配置管理器初始化完成")

    async def get_emulator(
        self, emulator_id: Optional[str] = None
    ) -> Tuple[List[Dict], Dict[str, Dict]]:
        """获取模拟器配置"""

        await self.init()

        if emulator_id is None:
            logger.info("获取所有模拟器配置")

            index = []
            data = {}

            for uid, config in self.config.items():
                index.append({"uuid": str(uid), "name": config.get("Info", "Name")})
                data[str(uid)] = await config.toDict()

            return index, data
        else:
            logger.info(f"获取模拟器配置: {emulator_id}")

            emulator_uid = uuid.UUID(emulator_id)
            if emulator_uid not in self.config:
                raise ValueError(f"未找到ID为 {emulator_id} 的模拟器配置")

            config_instance = self.config[emulator_uid]
            index = [
                {"uuid": str(emulator_uid), "name": config_instance.get("Info", "Name")}
            ]
            data = {str(emulator_uid): await config_instance.toDict()}

            return index, data

    async def add_emulator(self) -> Tuple[uuid.UUID, EmulatorManagerConfig]:
        """添加新的模拟器配置"""

        await self.init()

        logger.info("添加新的模拟器配置")

        uid, config_instance = await self.config.add(EmulatorManagerConfig)
        await self.config.save()

        return uid, config_instance

    async def update_emulator(self, emulator_id: str, data: Dict) -> None:
        """更新模拟器配置"""

        await self.init()

        logger.info(f"更新模拟器配置: {emulator_id}")

        emulator_uid = uuid.UUID(emulator_id)
        if emulator_uid not in self.config:
            raise ValueError(f"未找到ID为 {emulator_id} 的模拟器配置")

        await self.config[emulator_uid].load(data)
        await self.config.save()

    async def del_emulator(self, emulator_id: str) -> None:
        """删除模拟器配置"""

        await self.init()

        logger.info(f"删除模拟器配置: {emulator_id}")

        emulator_uid = uuid.UUID(emulator_id)
        if emulator_uid not in self.config:
            raise ValueError(f"未找到ID为 {emulator_id} 的模拟器配置")

        await self.config.remove(emulator_uid)
        await self.config.save()

    async def reorder_emulator(self, index_list: List[str]) -> None:
        """重新排序模拟器配置"""

        await self.init()

        logger.info(f"重新排序模拟器配置: {index_list}")

        await self.config.setOrder(list(map(uuid.UUID, index_list)))
        await self.config.save()

    async def search_emulators(self) -> List[Dict[str, str]]:
        """自动搜索模拟器"""

        logger.info("开始自动搜索模拟器")

        try:
            return await search_emulators()
        except Exception as e:
            logger.error(f"模拟器搜索失败: {e}")
            return []


class EmulatorManager:
    """模拟器实例管理器（保持原有功能）"""

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


# 全局配置管理器实例
emulator_config_manager = EmulatorConfigManager()


# 导出函数供API使用
async def get_emulator(
    emulator_id: Optional[str] = None,
) -> Tuple[List[Dict], Dict[str, Dict]]:
    """获取模拟器配置"""
    return await emulator_config_manager.get_emulator(emulator_id)


async def add_emulator() -> Tuple[uuid.UUID, EmulatorManagerConfig]:
    """添加新的模拟器配置"""
    return await emulator_config_manager.add_emulator()


async def update_emulator(emulator_id: str, data: Dict) -> None:
    """更新模拟器配置"""
    await emulator_config_manager.update_emulator(emulator_id, data)


async def del_emulator(emulator_id: str) -> None:
    """删除模拟器配置"""
    await emulator_config_manager.del_emulator(emulator_id)


async def reorder_emulator(index_list: List[str]) -> None:
    """重新排序模拟器配置"""
    await emulator_config_manager.reorder_emulator(index_list)


async def search_emulators_api() -> List[Dict[str, str]]:
    """自动搜索模拟器（API接口）"""
    return await emulator_config_manager.search_emulators()
