import json
import secrets
import string
import asyncio
import aiofiles
from pathlib import Path
from typing import Any, TypeVar, Generic, cast
from pydantic import BaseModel

from app.utils.logger import get_logger

T = TypeVar('T', bound=BaseModel)

class ConfigManager(Generic[T]):
    """
    异步配置管理基类，支持自动保存和Pydantic数据验证
    子类需定义具体的配置模型类型
    """
    
    def __init__(self, file_path: str, log_name: str, model_type: type[T]):
        """
        初始化配置管理器
        
        Args:
            file_path: 配置文件路径
            log_name: 日志名称
            model_type: 配置项的Pydantic模型类型
        """
        self.file_path = Path(file_path)
        self.logger = get_logger(log_name)
        self.model_type = model_type
        self.data: dict[str, Any] = {
            "instance_order": [],
            "instances": {}
        }
        self._lock = asyncio.Lock()
        self._save_task: asyncio.Task|None = None
        self._pending_save = False
        self._load_task = asyncio.create_task(self._load_async())
    
    async def _load_async(self) -> None:
        """异步加载配置文件 - 带健壮的错误处理"""
        async with self._lock:
            try:
                # 检查文件是否存在
                if not self.file_path.exists():
                    self.logger.info(f"配置文件 {self.file_path} 不存在，创建新配置")
                    self.file_path.parent.mkdir(parents=True, exist_ok=True)
                    # 初始化空配置
                    self.data = {
                        "instance_order": [],
                        "instances": {}
                    }
                    return
                
                # 检查文件是否为空
                if self.file_path.stat().st_size == 0:
                    self.logger.warning(f"配置文件 {self.file_path} 为空，初始化新配置")
                    self.data = {
                        "instance_order": [],
                        "instances": {}
                    }
                    return
                
                # 读取并解析配置
                async with aiofiles.open(self.file_path, 'r', encoding='utf-8') as f:
                    content = await f.read()
                
                # 尝试解析JSON
                try:
                    raw_data = json.loads(content)
                except json.JSONDecodeError as e:
                    self.logger.error(f"配置文件 {self.file_path} JSON解析失败: {e}")
                    # 尝试备份损坏的配置文件
                    await self._backup_corrupted_config()
                    # 初始化空配置
                    self.data = {
                        "instance_order": [],
                        "instances": {}
                    }
                    return
                
                # 验证并加载实例
                instance_order = raw_data.get("instance_order", [])
                instances_raw = raw_data.get("instances", {})
                
                instances = {}
                for uid, config_data in instances_raw.items():
                    try:
                        # 使用Pydantic验证配置数据
                        instances[uid] = self.model_type(**config_data)
                    except Exception as e:
                        self.logger.error(f"配置项 {uid} 验证失败: {e}")
                        # 不中断整个加载过程，跳过无效配置
                        continue
                
                # 确保instance_order与现有实例匹配
                valid_order = [uid for uid in instance_order if uid in instances]
                self.data = {
                    "instance_order": valid_order,
                    "instances": instances
                }
                self.logger.info(f"成功加载 {len(instances)} 个配置实例")
                
            except Exception as e:
                self.logger.error(f"配置加载失败: {e}", exc_info=True)
                # 初始化空配置作为安全措施
                self.data = {
                    "instance_order": [],
                    "instances": {}
                }
                # 尝试备份损坏的配置文件
                await self._backup_corrupted_config()
    
    async def _backup_corrupted_config(self) -> None:
        """备份损坏的配置文件"""
        try:
            backup_path = self.file_path.with_suffix(f"{self.file_path.suffix}.bak")
            counter = 1
            while backup_path.exists():
                backup_path = self.file_path.with_suffix(f"{self.file_path.suffix}.bak{counter}")
                counter += 1
            
            if self.file_path.exists():
                async with aiofiles.open(self.file_path, 'rb') as src, \
                          aiofiles.open(backup_path, 'wb') as dst:
                    content = await src.read()
                    await dst.write(content)
                
                self.logger.warning(f"已备份损坏的配置文件到: {backup_path}")
        except Exception as e:
            self.logger.error(f"备份损坏配置失败: {e}")
    
    async def _save_async(self) -> None:
        """异步保存配置到文件"""
        async with self._lock:
            try:
                serializable = {
                    "instance_order": self.data["instance_order"],
                    "instances": {
                        uid: instance.model_dump(mode='json')
                        for uid, instance in self.data["instances"].items()
                    }
                }
                
                # 确保目录存在
                self.file_path.parent.mkdir(parents=True, exist_ok=True)
                
                async with aiofiles.open(self.file_path, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(serializable, indent=2, ensure_ascii=False))
                
                self.logger.debug(f"配置已异步保存到: {self.file_path}")
            except Exception as e:
                self.logger.error(f"配置保存失败: {e}", exc_info=True)
                raise
            finally:
                self._save_task = None
                self._pending_save = False
    
    def _schedule_save(self) -> None:
        """
        调度配置保存（避免频繁保存）
        使用防抖技术，确保短时间内多次修改只保存一次
        """
        if self._save_task and not self._save_task.done():
            # 已有保存任务在运行，标记需要再次保存
            self._pending_save = True
            return
        
        async def save_with_debounce():
            # 等待短暂时间，合并多次修改
            await asyncio.sleep(0.1)
            
            # 如果有新的保存请求，递归处理
            if self._pending_save:
                self._pending_save = False
                await save_with_debounce()
                return
            
            await self._save_async()
        
        self._save_task = asyncio.create_task(save_with_debounce())
    
    @staticmethod
    def generate_uid(length: int = 8) -> str:
        """生成8位随机UID"""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    async def create(self, **kwargs) -> str:
        """创建新的配置实例"""
        async with self._lock:
            # 确保配置已加载完成
            if not self._load_task.done():
                await self._load_task
            
            # 生成唯一UID
            uid = self.generate_uid()
            while uid in self.data["instances"]:
                uid = self.generate_uid()
            
            try:
                # 使用Pydantic模型验证数据
                new_config = self.model_type(**kwargs)
            except Exception as e:
                self.logger.error(f"无效的配置数据: {e}")
                raise
            
            self.data["instances"][uid] = new_config
            self.data["instance_order"].append(uid)
            self._schedule_save()
            self.logger.info(f"创建新的配置实例: {uid}")
            return uid
    
    # 实现所需魔法方法（同步方法）
    def __getitem__(self, uid: str) -> T:
        """获取配置项（同步）"""
        # 确保配置已加载完成
        if not self._load_task.done():
            raise RuntimeError("配置尚未加载完成，请等待初始化完成")
        
        return cast(T, self.data["instances"][uid])
    
    def __setitem__(self, uid: str, value: T | dict[str, Any]) -> None:
        """
        设置配置项（同步）
        注意：此方法是同步的，但会触发异步保存
        
        支持两种用法：
        1. config[uid] = config_model_instance
        2. config[uid] = {"name": "value", ...}  # 字典形式
        """
        # 确保配置已加载完成
        if not self._load_task.done():
            raise RuntimeError("配置尚未加载完成，请等待初始化完成")
        
        # 如果传入的是字典，转换为模型实例
        if isinstance(value, dict):
            try:
                value = self.model_type(**value)
            except Exception as e:
                self.logger.error(f"配置数据转换失败: {e}")
                raise ValueError("无效的配置数据") from e
        
        if not isinstance(value, self.model_type):
            raise TypeError(f"值必须是 {self.model_type.__name__} 类型或字典")
        
        # 更新内存数据
        if uid not in self.data["instances"]:
            self.data["instance_order"].append(uid)
        
        self.data["instances"][uid] = value
        self._schedule_save()
    
    def __delitem__(self, uid: str) -> None:
        """删除配置项（同步）"""
        # 确保配置已加载完成
        if not self._load_task.done():
            raise RuntimeError("配置尚未加载完成，请等待初始化完成")
        
        if uid in self.data["instances"]:
            del self.data["instances"][uid]
            if uid in self.data["instance_order"]:
                self.data["instance_order"].remove(uid)
            self._schedule_save()
        else:
            raise KeyError(uid)
    
    def __contains__(self, uid: str) -> bool:
        """检查UID是否存在（同步）"""
        # 确保配置已加载完成
        if not self._load_task.done():
            return False  # 配置未加载完成时，认为不存在
        
        return uid in self.data["instances"]
    
    def __len__(self) -> int:
        """返回配置实例数量（同步）"""
        # 确保配置已加载完成
        if not self._load_task.done():
            return 0
        
        return len(self.data["instance_order"])
    
    def get_instance_order(self) -> list[str]:
        """获取实例顺序列表（同步）"""
        # 确保配置已加载完成
        if not self._load_task.done():
            return []
        
        return self.data["instance_order"].copy()
    
    def get_all_instances(self) -> dict[str, T]:
        """获取所有配置实例（同步）"""
        # 确保配置已加载完成
        if not self._load_task.done():
            return {}
        
        return cast(dict[str, T], self.data["instances"].copy())
    
    async def wait_until_ready(self) -> None:
        """等待配置加载完成"""
        await self._load_task
    
    async def save_now(self) -> None:
        """立即保存配置（等待保存完成）"""
        if self._save_task:
            await self._save_task
        else:
            await self._save_async()
    
    def is_ready(self) -> bool:
        """检查配置是否已加载完成"""
        return self._load_task.done() and not self._load_task.cancelled()
    
    
    
'''
初始化
ConfigManager(file_path: str, log_name: str, model_type: type[T])
    file_path: 配置文件路径
    log_name: 日志记录器名称
    model_type: 配置模型类型（继承自 Pydantic BaseModel）
主要方法
    create(**kwargs) -> str
    异步创建新的配置实例，返回唯一标识符(UID)

    wait_until_ready() -> None
    异步等待配置加载完成

    save_now() -> None
    立即保存配置到文件

    is_ready() -> bool
    检查配置是否已加载完成

    get_instance_order() -> list[str]
    获取配置实例的顺序列表

    get_all_instances() -> dict[str, T]
    获取所有配置实例

魔法方法
    getitem(uid: str) -> T
    通过 UID 获取配置实例

    setitem(uid: str, value: T | dict[str, Any]) -> None
    通过 UID 设置配置实例

    delitem(uid: str) -> None
    通过 UID 删除配置实例

    contains(uid: str) -> bool
    检查是否存在指定 UID 的配置实例

    len() -> int
    获取配置实例数量
'''