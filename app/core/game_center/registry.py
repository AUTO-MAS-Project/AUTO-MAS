#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""游戏中心 Provider 注册表

内置 provider 自动注册; 外部插件可通过 register_provider() 注册新 provider。
"""

from __future__ import annotations

from typing import Any, Optional, Type

from app.utils import get_logger

from .base import GameProvider

logger = get_logger("游戏中心")

# provider 名 -> 类
_PROVIDERS: dict[str, Type[GameProvider]] = {}


def register_provider(name: str, cls: Type[GameProvider]) -> None:
    """注册一个 provider

    Args:
        name: provider 名称 (如 "mihoyo_pc")
        cls: GameProvider 子类
    """
    if not issubclass(cls, GameProvider):
        raise TypeError(f"{cls} 不是 GameProvider 子类")
    _PROVIDERS[name] = cls
    logger.debug(f"已注册游戏 provider: {name}")


def get_provider_cls(name: str) -> Optional[Type[GameProvider]]:
    return _PROVIDERS.get(name)


def create_provider(
    provider_name: str,
    config: Any,
    preset: Optional[Any] = None,
) -> Optional[GameProvider]:
    """创建 provider 实例并绑定 config

    Args:
        provider_name: provider 名称
        config: GameConfig 实例
        preset: GamePreset 实例 (可选)
    """
    cls = _PROVIDERS.get(provider_name)
    if cls is None:
        logger.error(f"未知的 provider 类型: {provider_name}")
        return None
    instance = cls()
    instance.set_config(config, preset)
    return instance


def _register_builtin_providers() -> None:
    """注册内置 provider"""
    from .providers.mihoyo import MihoyoPcProvider
    from .providers.hypergryph import HypergryphPcProvider
    from .providers.adb_apk import AdbApkProvider

    register_provider("mihoyo_pc", MihoyoPcProvider)
    register_provider("hypergryph_pc", HypergryphPcProvider)
    register_provider("adb_apk", AdbApkProvider)
