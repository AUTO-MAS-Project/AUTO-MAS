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

"""专项接入声明及宿主索引构造；不导入具体专项或配置单例。"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from app.config import ConfigEntry
from app.models.script_contracts import ScriptConfigHandler
from app.task.restore_registry import RestorePoolResolver

if TYPE_CHECKING:
    from app.models.task import ScriptItem, TaskExecuteBase
    from app.utils.common.config.restore import ConfigRestorePool


@dataclass(frozen=True)
class ManagerBuildContext:
    """任务构造时提供资源值与追加预约能力。"""

    root_paths: tuple[Path, ...]
    reserve_root: Callable[[Path], bool]


ManagerFactory = Callable[["ScriptItem", ManagerBuildContext], "TaskExecuteBase"]
RestorePoolLoader = Callable[[], list["ConfigRestorePool"]]


@dataclass(frozen=True, kw_only=True)
class ScriptRegistration:
    """三项能力必须显式声明；None 表示不支持，不等同于漏登。"""

    config_type: type[ConfigEntry]
    run_types: tuple[type[ConfigEntry], ...]
    manager_factory: ManagerFactory | None
    create_config_handler: Callable[[], ScriptConfigHandler] | None
    load_restore_pools: RestorePoolLoader | None
    # 配置与恢复沿用各自的有序 isinstance 规则，不是最近父类匹配。
    config_priority: int
    restore_priority: int


@dataclass(frozen=True, kw_only=True)
class ScriptCapabilities:
    """装配结果只交给宿主；消费者分别获得自己的小接口。"""

    manager_factories: Mapping[type[ConfigEntry], ManagerFactory | None]
    config_handlers: tuple[tuple[type[ConfigEntry], ScriptConfigHandler | None], ...]
    resolve_restore_pools: RestorePoolResolver


def build_script_capabilities(
    registrations: Iterable[ScriptRegistration],
    *,
    expected_types: Iterable[type[ConfigEntry]],
) -> ScriptCapabilities:
    """先校验登记，再构造当前宿主的 handler；不缓存服务或运行器。"""
    declarations = tuple(registrations)
    config_types: set[type[ConfigEntry]] = set()
    factories: dict[type[ConfigEntry], ManagerFactory | None] = {}
    for declaration in declarations:
        if declaration.config_type in config_types:
            raise ValueError(f"重复的配置/恢复登记: {declaration.config_type.__name__}")
        config_types.add(declaration.config_type)
        for run_type in declaration.run_types:
            if run_type in factories:
                raise ValueError(f"重复的运行登记: {run_type.__name__}")
            factories[run_type] = declaration.manager_factory
    for entry_type in expected_types:
        if entry_type not in factories or not any(
            issubclass(entry_type, registered) for registered in config_types
        ):
            raise ValueError(f"专项能力漏登: {entry_type.__name__}")

    return ScriptCapabilities(
        manager_factories=MappingProxyType(factories),
        config_handlers=tuple(
            (
                item.config_type,
                item.create_config_handler()
                if item.create_config_handler is not None
                else None,
            )
            for item in sorted(declarations, key=lambda item: item.config_priority)
        ),
        resolve_restore_pools=RestorePoolResolver(
            tuple(
                (item.config_type, item.load_restore_pools)
                for item in sorted(declarations, key=lambda item: item.restore_priority)
            )
        ),
    )
