from __future__ import annotations

from typing import Any

from automas_script_hsr import (
    HSRAdapterDescriptor,
    HSRStageCategory,
    HSRTaskDescriptor,
)


SRA_TASKS = (
    HSRTaskDescriptor(
        key="Daily",
        name="日常模块",
        phase="daily",
        description="清体力、历战余响",
        default_enabled=True,
        strategy_lines=("使用脚本所选 SRA 原生关卡", "按配置决定是否执行历战余响"),
        native_tasks=("TrailblazePowerTask",),
    ),
    HSRTaskDescriptor(
        key="ReceiveRewards",
        name="领取奖励",
        phase="daily",
        description="每日实训、活动检测、奖励领取、兑换码",
        default_enabled=True,
        strategy_lines=("调用 SRA ReceiveRewardsTask", "仅启用现有奖励领取能力"),
        native_tasks=("ReceiveRewardsTask",),
    ),
    HSRTaskDescriptor(
        key="DivergentUniverse",
        name="差分宇宙",
        phase="weekly",
        description="差分宇宙周期/常规演算",
        strategy_lines=("调用 SRA CosmicStrifeTask", "启用差分宇宙并关闭货币战争"),
        native_tasks=("CosmicStrifeTask",),
    ),
    HSRTaskDescriptor(
        key="CurrencyWars",
        name="货币战争",
        phase="weekly",
        description="货币战争标准博弈",
        strategy_lines=("调用 SRA CosmicStrifeTask", "启用货币战争并关闭差分宇宙"),
        native_tasks=("CosmicStrifeTask",),
    ),
)

SRA_DESCRIPTOR = HSRAdapterDescriptor(
    engine="SRA",
    display_name="StarRailAssistant",
    version="2.16.1",
    tasks=SRA_TASKS,
    supported_modes=("AutoProxy", "ManualReview"),
    capabilities=frozenset({"account_login", "manual_review", "stage_catalog"}),
)


class SRATaskCatalog:
    descriptor = SRA_DESCRIPTOR

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
        from .stages import load_sra_stage_options

        return load_sra_stage_options(script_config)
