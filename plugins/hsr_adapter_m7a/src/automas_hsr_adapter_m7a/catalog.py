from __future__ import annotations

from typing import Any

from automas_script_hsr import (
    HSRAdapterDescriptor,
    HSRStageCategory,
    HSRTaskDescriptor,
)


M7A_TASKS = (
    HSRTaskDescriptor(
        key="Daily",
        name="日常模块",
        phase="daily",
        description="清体力、历战余响",
        default_enabled=True,
        strategy_lines=("白名单补丁 M7A config.yaml", "调用 routine 并按日志确认完成"),
        native_tasks=("routine",),
    ),
    HSRTaskDescriptor(
        key="ReceiveRewards",
        name="领取奖励",
        phase="daily",
        description="每日实训、活动检测、奖励领取、兑换码",
        default_enabled=True,
        strategy_lines=("仅打开奖励相关白名单字段", "调用 M7A routine"),
        native_tasks=("routine",),
    ),
    HSRTaskDescriptor(
        key="DivergentUniverse",
        name="差分宇宙",
        phase="weekly",
        description="差分宇宙周期/常规演算",
        strategy_lines=("应用差分宇宙白名单补丁", "调用 M7A divergent"),
        native_tasks=("divergent",),
    ),
    HSRTaskDescriptor(
        key="CurrencyWars",
        name="货币战争",
        phase="weekly",
        description="货币战争标准博弈",
        strategy_lines=("应用货币战争白名单补丁", "调用 M7A currencywars"),
        native_tasks=("currencywars",),
    ),
)

M7A_DESCRIPTOR = HSRAdapterDescriptor(
    engine="M7A",
    display_name="March7thAssistant",
    version="2026.4.27",
    tasks=M7A_TASKS,
    supported_modes=("AutoProxy",),
    capabilities=frozenset({"stage_catalog"}),
)


class M7ATaskCatalog:
    descriptor = M7A_DESCRIPTOR

    def list_tasks(self) -> tuple[HSRTaskDescriptor, ...]:
        return self.descriptor.tasks

    def list_stage_options(
        self,
        *,
        script_config: Any,
        user_config: Any | None,
        slot: str,
    ) -> tuple[HSRStageCategory, ...]:
        _ = user_config, slot
        from .stages import load_m7a_stage_options

        return load_m7a_stage_options(script_config)
