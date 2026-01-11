#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025 AUTO-MAS Team

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

"""
LLM 配置管理模块

本模块负责管理 LLM 服务提供商配置，包括：
- 配置加载和保存功能
- 提供商的增删改查功能
- 配置导出和导入功能
"""

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, asdict

from app.models.config import LLMProviderConfig
from app.models.ConfigBase import MultipleConfig
from app.utils import get_logger

logger = get_logger("LLM配置管理")


# 预设提供商配置
PRESET_PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    "claude": {
        "name": "Claude",
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-3-haiku-20240307",
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "qwen": {
        "name": "Qwen",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-turbo",
    },
    "mimo": {
        "name": "小米 MiMo",
        "base_url": "https://api.xiaomimimo.com/v1",
        "model": "mimo-v2-flash",
    },
}


@dataclass
class LLMGlobalSettings:
    """LLM 全局设置"""

    enabled: bool = False
    active_provider_id: str = ""
    timeout: int = 30
    max_retries: int = 1
    rate_limit: int = 10


@dataclass
class LLMProviderData:
    """LLM 提供商数据"""

    uid: str
    name: str
    type: str
    active: bool
    api_key: str
    base_url: str
    model: str
    max_tokens: int
    temperature: float


class LLMConfigManager:
    """
    LLM 配置管理器

    负责管理 LLM 服务提供商配置，包括配置的加载、保存、
    提供商的增删改查以及配置的导出和导入功能。
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        初始化 LLM 配置管理器

        Parameters
        ----------
        config_path : Optional[Path]
            配置文件路径，默认为 config/LLMConfig.json
        """
        self.config_path = config_path or Path.cwd() / "config" / "LLMConfig.json"
        self.providers: MultipleConfig[LLMProviderConfig] = MultipleConfig(
            [LLMProviderConfig]
        )
        self.global_settings = LLMGlobalSettings()
        self._initialized = False

    async def init(self) -> None:
        """
        初始化配置管理器，加载配置文件

        如果配置文件不存在，将创建默认配置。
        如果配置文件损坏，将使用默认值并记录警告。
        """
        if self._initialized:
            return

        logger.info(f"初始化 LLM 配置管理器，配置路径: {self.config_path}")

        try:
            await self._load_config()
            self._initialized = True
            logger.info("LLM 配置加载成功")
        except Exception as e:
            logger.warning(f"LLM 配置加载失败，使用默认配置: {e}")
            self._initialized = True
            await self.save()

    async def _load_config(self) -> None:
        """从文件加载配置"""
        if not self.config_path.exists():
            logger.info("配置文件不存在，将创建默认配置")
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            await self.save()
            return

        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            logger.warning(f"配置文件 JSON 解析失败: {e}")
            raise ValueError(f"配置文件损坏: {e}")

        # 加载全局设置
        await self._load_global_settings(data.get("LLM", {}))

        # 加载提供商配置
        await self._load_providers(data.get("Providers", {}))

    async def _load_global_settings(self, data: Dict[str, Any]) -> None:
        """加载全局设置"""
        try:
            self.global_settings.enabled = bool(data.get("Enabled", False))
            self.global_settings.active_provider_id = str(
                data.get("ActiveProviderId", "")
            )
            self.global_settings.timeout = int(data.get("Timeout", 30))
            self.global_settings.max_retries = int(data.get("MaxRetries", 1))
            self.global_settings.rate_limit = int(data.get("RateLimit", 10))

            # 验证范围
            self.global_settings.timeout = max(5, min(120, self.global_settings.timeout))
            self.global_settings.max_retries = max(
                0, min(3, self.global_settings.max_retries)
            )
            self.global_settings.rate_limit = max(
                1, min(60, self.global_settings.rate_limit)
            )
        except (TypeError, ValueError) as e:
            logger.warning(f"全局设置加载失败，使用默认值: {e}")
            self.global_settings = LLMGlobalSettings()

    async def _load_providers(self, data: Dict[str, Any]) -> None:
        """加载提供商配置"""
        if not data:
            return

        try:
            await self.providers.load(data)
        except Exception as e:
            logger.warning(f"提供商配置加载失败: {e}")
            # 清空并使用空配置
            self.providers = MultipleConfig([LLMProviderConfig])

    async def save(self) -> None:
        """保存配置到文件"""
        logger.info("保存 LLM 配置")

        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "LLM": {
                "Enabled": self.global_settings.enabled,
                "ActiveProviderId": self.global_settings.active_provider_id,
                "Timeout": self.global_settings.timeout,
                "MaxRetries": self.global_settings.max_retries,
                "RateLimit": self.global_settings.rate_limit,
            },
            "Providers": await self.providers.toDict(if_decrypt=False),
        }

        self.config_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
        )

        logger.info("LLM 配置保存成功")

    # ==================== 提供商 CRUD 操作 ====================

    async def add_provider(
        self, provider_type: str = "custom", api_key: str = ""
    ) -> Tuple[str, LLMProviderConfig]:
        """添加新的 LLM 提供商"""
        logger.info(f"添加 LLM 提供商: {provider_type}")

        uid, config = await self.providers.add(LLMProviderConfig)

        # 设置提供商类型
        await config.set("Info", "Type", provider_type)

        # 如果是预设提供商，自动填充配置
        if provider_type in PRESET_PROVIDERS:
            preset = PRESET_PROVIDERS[provider_type]
            await config.set("Info", "Name", preset["name"])
            await config.set("Data", "BaseUrl", preset["base_url"])
            await config.set("Data", "Model", preset["model"])

        # 设置 API 密钥
        if api_key:
            await config.set("Data", "ApiKey", api_key)

        await self.save()

        logger.info(f"LLM 提供商添加成功: {uid}")
        return str(uid), config

    async def get_provider(self, provider_id: str) -> Optional[LLMProviderConfig]:
        """获取指定的 LLM 提供商配置"""
        try:
            uid = uuid.UUID(provider_id)
            if uid in self.providers:
                return self.providers[uid]
        except (ValueError, KeyError):
            pass
        return None

    async def get_all_providers(self) -> List[Dict[str, Any]]:
        """获取所有 LLM 提供商配置"""
        providers = []
        for uid in self.providers.keys():
            config = self.providers[uid]
            provider_data = await config.toDict()
            provider_data["uid"] = str(uid)
            provider_data["is_active"] = (
                str(uid) == self.global_settings.active_provider_id
            )
            providers.append(provider_data)
        return providers

    async def update_provider(
        self, provider_id: str, data: Dict[str, Dict[str, Any]]
    ) -> bool:
        """更新 LLM 提供商配置"""
        logger.info(f"更新 LLM 提供商: {provider_id}")

        config = await self.get_provider(provider_id)
        if config is None:
            logger.warning(f"提供商不存在: {provider_id}")
            return False

        try:
            for group, items in data.items():
                for name, value in items.items():
                    await config.set(group, name, value)

            await self.save()
            logger.info(f"LLM 提供商更新成功: {provider_id}")
            return True
        except Exception as e:
            logger.error(f"更新提供商失败: {e}")
            return False

    async def delete_provider(self, provider_id: str) -> bool:
        """删除 LLM 提供商"""
        logger.info(f"删除 LLM 提供商: {provider_id}")

        try:
            uid = uuid.UUID(provider_id)
            if uid not in self.providers:
                logger.warning(f"提供商不存在: {provider_id}")
                return False

            await self.providers.remove(uid)

            # 如果删除的是当前激活的提供商，清空激活 ID
            if self.global_settings.active_provider_id == provider_id:
                self.global_settings.active_provider_id = ""

            await self.save()
            logger.info(f"LLM 提供商删除成功: {provider_id}")
            return True
        except Exception as e:
            logger.error(f"删除提供商失败: {e}")
            return False

    async def set_active_provider(self, provider_id: str) -> bool:
        """设置当前激活的提供商"""
        logger.info(f"设置激活提供商: {provider_id}")

        if provider_id and provider_id != "":
            config = await self.get_provider(provider_id)
            if config is None:
                logger.warning(f"提供商不存在: {provider_id}")
                return False

        self.global_settings.active_provider_id = provider_id
        await self.save()

        logger.info(f"激活提供商设置成功: {provider_id}")
        return True

    async def get_active_provider(self) -> Optional[LLMProviderConfig]:
        """获取当前激活的提供商配置"""
        if not self.global_settings.active_provider_id:
            return None
        return await self.get_provider(self.global_settings.active_provider_id)

    # ==================== 全局设置操作 ====================

    async def get_global_settings(self) -> Dict[str, Any]:
        """获取全局设置"""
        return asdict(self.global_settings)

    async def update_global_settings(self, data: Dict[str, Any]) -> bool:
        """更新全局设置"""
        logger.info("更新 LLM 全局设置")

        try:
            if "enabled" in data:
                self.global_settings.enabled = bool(data["enabled"])
            if "active_provider_id" in data:
                self.global_settings.active_provider_id = str(
                    data["active_provider_id"]
                )
            if "timeout" in data:
                self.global_settings.timeout = max(5, min(120, int(data["timeout"])))
            if "max_retries" in data:
                self.global_settings.max_retries = max(
                    0, min(3, int(data["max_retries"]))
                )
            if "rate_limit" in data:
                self.global_settings.rate_limit = max(
                    1, min(60, int(data["rate_limit"]))
                )

            await self.save()
            logger.info("LLM 全局设置更新成功")
            return True
        except Exception as e:
            logger.error(f"更新全局设置失败: {e}")
            return False

    # ==================== 导出和导入功能 ====================

    async def export_config(self, file_path: Union[str, Path]) -> bool:
        """导出配置到文件"""
        logger.info(f"导出 LLM 配置到: {file_path}")

        try:
            file_path = Path(file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "LLM": {
                    "Enabled": self.global_settings.enabled,
                    "ActiveProviderId": self.global_settings.active_provider_id,
                    "Timeout": self.global_settings.timeout,
                    "MaxRetries": self.global_settings.max_retries,
                    "RateLimit": self.global_settings.rate_limit,
                },
                "Providers": await self.providers.toDict(if_decrypt=False),
            }

            file_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
            )

            logger.info("LLM 配置导出成功")
            return True
        except Exception as e:
            logger.error(f"导出配置失败: {e}")
            return False

    async def import_config(self, file_path: Union[str, Path]) -> bool:
        """从文件导入配置"""
        logger.info(f"从文件导入 LLM 配置: {file_path}")

        try:
            file_path = Path(file_path)
            if not file_path.exists():
                logger.error(f"导入文件不存在: {file_path}")
                return False

            data = json.loads(file_path.read_text(encoding="utf-8"))

            # 验证数据结构
            if not isinstance(data, dict):
                logger.error("导入文件格式无效")
                return False

            # 加载全局设置
            await self._load_global_settings(data.get("LLM", {}))

            # 加载提供商配置
            await self._load_providers(data.get("Providers", {}))

            await self.save()

            logger.info("LLM 配置导入成功")
            return True
        except json.JSONDecodeError as e:
            logger.error(f"导入文件 JSON 解析失败: {e}")
            return False
        except Exception as e:
            logger.error(f"导入配置失败: {e}")
            return False

    # ==================== 辅助方法 ====================

    def is_enabled(self) -> bool:
        """检查 LLM 功能是否启用"""
        return self.global_settings.enabled

    def get_preset_providers(self) -> Dict[str, Dict[str, str]]:
        """获取预设提供商配置"""
        return PRESET_PROVIDERS.copy()


# 全局 LLM 配置管理器实例
llm_config_manager: Optional[LLMConfigManager] = None


async def get_llm_config_manager() -> LLMConfigManager:
    """获取全局 LLM 配置管理器实例"""
    global llm_config_manager
    if llm_config_manager is None:
        llm_config_manager = LLMConfigManager()
        await llm_config_manager.init()
    return llm_config_manager
