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


from dataclasses import dataclass, field
from typing import Literal

from ..registry import resolve_configured_engines

ScriptType = Literal["M7A", "SRA"]
ModuleCategory = Literal["daily", "weekly"]


@dataclass(frozen=True)
class HSRTaskModule:
    key: str
    name: str
    category: ModuleCategory
    description: str
    supported_scripts: tuple[ScriptType, ...]
    default_script: ScriptType
    m7a_tasks: tuple[str, ...] = field(default_factory=tuple)
    sra_task: str | None = None
    sra_overrides: dict | None = None


HSR_TASK_MODULES: tuple[HSRTaskModule, ...] = (
    HSRTaskModule(
        key="Daily",
        name="日常模块",
        category="daily",
        description="清体力、历战余响",
        supported_scripts=("M7A", "SRA"),
        default_script="SRA",
        m7a_tasks=("routine",),
        sra_task="TrailblazePowerTask",
        sra_overrides={"trailblazePower": {"enabled": True}},
    ),
    HSRTaskModule(
        key="ReceiveRewards",
        name="领取奖励",
        category="daily",
        description="每日实训、活动检测、奖励领取、兑换码",
        supported_scripts=("M7A", "SRA"),
        default_script="SRA",
        m7a_tasks=("routine",),
        sra_task="ReceiveRewardsTask",
        sra_overrides={"receiveRewards": {"enabled": True}},
    ),
    HSRTaskModule(
        key="DivergentUniverse",
        name="差分宇宙",
        category="weekly",
        description="差分宇宙周期/常规演算",
        supported_scripts=("M7A", "SRA"),
        default_script="SRA",
        m7a_tasks=("divergent",),
        sra_task="CosmicStrifeTask",
        sra_overrides={
            "cosmicStrife": {
                "enabled": True,
                "divergentUniverse.enabled": True,
                "currencyWars.enabled": False,
            }
        },
    ),
    HSRTaskModule(
        key="CurrencyWars",
        name="货币战争",
        category="weekly",
        description="货币战争标准博弈",
        supported_scripts=("M7A", "SRA"),
        default_script="SRA",
        m7a_tasks=("currencywars",),
        sra_task="CosmicStrifeTask",
        sra_overrides={
            "cosmicStrife": {
                "enabled": True,
                "divergentUniverse.enabled": False,
                "currencyWars.enabled": True,
            }
        },
    ),
)

HSR_TASK_MODULE_MAP: dict[str, HSRTaskModule] = {m.key: m for m in HSR_TASK_MODULES}


def get_module(key: str) -> HSRTaskModule | None:
    """根据模块键获取模块定义，找不到时返回 None"""
    return HSR_TASK_MODULE_MAP.get(key)


def script_supports(module_key: str, script: ScriptType) -> bool:
    """判断指定脚本是否支持该模块"""
    module = get_module(module_key)
    if module is None:
        return False
    return script in module.supported_scripts


def _resolve_effective_engines(
    script_config,
    effective_engines: tuple[ScriptType, ...] | None,
) -> tuple[ScriptType, ...]:
    engines = (
        resolve_configured_engines(script_config)
        if effective_engines is None
        else effective_engines
    )
    return tuple(
        engine
        for item in engines
        if (engine := str(item).upper()) in ("SRA", "M7A")
    )  # type: ignore[return-value]


def get_assigned_script(
    module: HSRTaskModule,
    script_config,
    *,
    effective_engines: tuple[ScriptType, ...] | None = None,
) -> ScriptType:
    """Resolve a module to an effective engine for the current script."""

    effective = _resolve_effective_engines(script_config, effective_engines)
    supported = tuple(
        engine for engine in effective if engine in module.supported_scripts
    )
    if len(supported) == 1:
        return supported[0]  # type: ignore[return-value]
    assigned = script_config.get("TaskMapping", module.key)
    normalized = "SRA" if assigned == "SRA" else "M7A"
    if normalized in supported:
        return normalized
    if supported:
        return supported[0]  # type: ignore[return-value]
    return normalized


def module_is_available(
    module: HSRTaskModule,
    script_config,
    *,
    effective_engines: tuple[ScriptType, ...] | None = None,
) -> bool:
    """Return whether at least one effective engine provides the module."""

    effective = set(_resolve_effective_engines(script_config, effective_engines))
    return bool(effective.intersection(module.supported_scripts))
