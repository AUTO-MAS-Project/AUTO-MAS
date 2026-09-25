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


"""HSR 托管表单的显式字段表：按引擎、按模块列出 MAS 允许覆盖的原生键。

这张表同时决定两件事，二者必须同源：

- **表单露出什么**：托管表单只按这里的顺序列出原生配置里确实存在的键；
- **运行时改什么**：三月七各模块的 patch 白名单、SRA 临时配置套用的原生值，
  都只认这里的键。

所以「表单露出集 = 运行生效集」：表里没有的原生键（包括外部脚本新版本新增的键）
不再自动露出，也不会被 MAS 覆盖；在 MAS 下没有意义的键（由 MAS 推导的总开关、
运行状态、MAS 已关掉的通知等）一律不进表。

本模块只放数据，不导入同包其它模块，供 ``m7a_config`` / ``sra_runtime`` /
``managed_config`` 共同引用而不成环。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

HSRFieldGroup = Literal[
    "common", "team", "support", "activity", "replenish", "reroll", "misc"
]
"""字段分组：``common`` 在弹窗里平铺，其余各成一个默认收起的折叠面板。
分组显示名由前端 i18n（``hsrFieldGroup.<group>``）提供。"""


@dataclass(frozen=True, slots=True)
class ManagedFieldVisibleWhen:
    """同模块同引擎里字段 ``key`` 的当前值在 ``values`` 中时才显示。"""

    key: str
    values: tuple[Any, ...]

    def asdict(self) -> dict[str, Any]:
        return {"key": self.key, "values": list(self.values)}


@dataclass(frozen=True, slots=True)
class ManagedFieldSpec:
    """字段表里的一项。

    ``label`` / ``description`` 不为 ``None`` 时覆盖从原生配置说明推出来的文案；
    ``type`` 用于原生值可能为空（YAML 里只写了键名）的列表字段。
    """

    key: str
    group: HSRFieldGroup = "common"
    visible_when: ManagedFieldVisibleWhen | None = None
    label: str | None = None
    description: str | None = None
    type: str | None = None


def _specs(
    group: HSRFieldGroup, *keys: str | ManagedFieldSpec
) -> tuple[ManagedFieldSpec, ...]:
    return tuple(
        key if isinstance(key, ManagedFieldSpec) else ManagedFieldSpec(key, group)
        for key in keys
    )


def _on(key: str) -> ManagedFieldVisibleWhen:
    """从属字段只在总开关 ``key`` 打开时显示（只影响表单，运行时照常套用）。"""

    return ManagedFieldVisibleWhen(key, (True,))


# ---------------------------------------------------------------- 三月七

_M7A_BUILD_TARGET_ON = _on("build_target_enable")
_M7A_TEAM_ON = _on("instance_team_enable")
_M7A_BORROW_ON = _on("borrow_enable")

M7A_MANAGED_FIELDS: dict[str, tuple[ManagedFieldSpec, ...]] = {
    # 不露出：power_plan_keep（体力计划不由 MAS 管）、calyx_golden_preference（三月七
    # 读点已注释掉）、power_limit（只有循环模式读）、activity_enable（MAS 按本模块
    # 三个活动子开关推导）。
    "Daily": (
        ManagedFieldSpec("build_target_enable"),
        *(
            ManagedFieldSpec(key, visible_when=_M7A_BUILD_TARGET_ON)
            for key in (
                "build_target_scheme",
                "build_target_ornament_weekly_count",
                "build_target_use_user_instance_when_only_erosion_and_ornament",
            )
        ),
        *_specs("common", "use_reserved_trailblaze_power", "use_fuel"),
        *_specs(
            "team",
            "instance_team_enable",
            ManagedFieldSpec(
                "instance_team_number",
                "team",
                visible_when=_M7A_TEAM_ON,
                description="没有匹配「指定副本队伍」规则的副本使用这个队伍编号。",
            ),
            ManagedFieldSpec(
                "instance_teams",
                "team",
                visible_when=_M7A_TEAM_ON,
                label="指定副本队伍",
                description=(
                    "为特定副本指定出战队伍，按副本名称匹配；"
                    "没有匹配的副本使用上面的队伍编号。"
                ),
                type="json",
            ),
        ),
        *_specs(
            "support",
            "borrow_enable",
            ManagedFieldSpec(
                "borrow_character_enable", "support", visible_when=_M7A_BORROW_ON
            ),
            ManagedFieldSpec(
                "borrow_friends",
                "support",
                visible_when=_M7A_BORROW_ON,
                label="支援好友列表",
                description=(
                    "按顺序查找的支援角色与对应好友名称；角色为 None 的行会被跳过。"
                ),
                type="json",
            ),
            ManagedFieldSpec(
                "borrow_scroll_times", "support", visible_when=_M7A_BORROW_ON
            ),
        ),
        *_specs(
            "activity",
            "activity_gardenofplenty_enable",
            ManagedFieldSpec(
                "activity_gardenofplenty_instance_type",
                "activity",
                visible_when=_on("activity_gardenofplenty_enable"),
            ),
            "activity_realmofthestrange_enable",
            "activity_planarfissure_enable",
        ),
        *_specs(
            "misc",
            "tp_before_instance",
            "break_down_level_four_relicset",
            "merge_immersifier",
            ManagedFieldSpec(
                "merge_immersifier_limit",
                "misc",
                visible_when=_on("merge_immersifier"),
            ),
        ),
    ),
    # 不露出：daily_tasks（运行状态）、activity_journey_highlights_notification_enable
    # （MAS 关掉了三月七全部通知）、activity_enable（按签到开关推导）、
    # daily_memory_one_team（三月七内部角色代号 + 秘技序号的队伍配置，只能在三月七
    # GUI 的角色选择器里配；MAS 只露出是否走「回忆一」）。
    "ReceiveRewards": _specs(
        "common",
        "reward_dispatch_enable",
        "reward_mail_enable",
        "reward_assist_enable",
        "reward_quest_enable",
        "reward_srpass_enable",
        "reward_redemption_code_enable",
        "reward_achievement_enable",
        "reward_message_enable",
        "activity_dailycheckin_enable",
        "daily_material_enable",
        "daily_himeko_try_enable",
        "daily_memory_one_enable",
    ),
    # 不露出 weekly_divergent_stable_mode：以脚本级「低性能兼容模式」为准。
    "DivergentUniverse": _specs(
        "common",
        "weekly_divergent_type",
        "weekly_divergent_level",
        "weekly_divergent_bonus_enable",
    ),
    "CurrencyWars": _specs(
        "common",
        "currencywars_type",
        "currencywars_rank_difficulty",
        "currencywars_bonus_enable",
        "currencywars_fast_mode",
        "currencywars_strategy",
        "currencywars_strategy_restart_on_special_tags",
    ),
}


# ---------------------------------------------------------------- SRA

SRA_REWARD_LABELS = (
    "签证（支援）奖励",
    "委托奖励",
    "邮件奖励",
    "每日实训奖励",
    "无名勋礼奖励",
    "巡星之礼",
    "兑换码奖励",
)
"""SRA receiveRewards 奖励开关的顺序词表（索引式 ``rewards.<i>`` 与命名键
``rewards.<name>`` 共用同一顺序，顺序以 SRA TasksConfig 为准）"""
SRA_REWARD_NAMED_KEYS = (
    "rewards.trailblazeProfile",
    "rewards.assignments",
    "rewards.mail",
    "rewards.dailyTraining",
    "rewards.namelessHonor",
    "rewards.giftOfOdyssey",
    "rewards.redeemCode",
)
"""SRA 2.22.0 起的具名奖励键，顺序同 ``ReceiveRewardsConfig.to_dict``"""
SRA_REWARD_LEGACY_KEYS = tuple(
    f"rewards.{index}" for index in range(len(SRA_REWARD_NAMED_KEYS))
)
"""旧 profile 的数组式奖励开关（``receiveRewards.rewards[i]`` 展开成 ``rewards.<i>``）。
与具名键同时存在时 SRA 以具名为准，只露出具名键。"""

_SRA_ACTIVITY_ON = _on("activity.enabled")
_SRA_REPLENISH_ON = _on("replenish.enabled")
_SRA_REROLL_MODE = ManagedFieldVisibleWhen("currencyWars.mode", (2,))

SRA_MANAGED_FIELDS: dict[str, tuple[ManagedFieldSpec, ...]] = {
    "Daily": (
        *_specs("common", "useBuildTarget", "useAssistant"),
        ManagedFieldSpec("replenish.enabled", "replenish"),
        *(
            ManagedFieldSpec(key, "replenish", visible_when=_SRA_REPLENISH_ON)
            for key in ("replenish.way", "replenish.times")
        ),
        ManagedFieldSpec("activity.enabled", "activity"),
        *(
            ManagedFieldSpec(key, "activity", visible_when=_SRA_ACTIVITY_ON)
            for key in (
                "activity.gardenOfPlenty.level1",
                "activity.gardenOfPlenty.level2",
                "activity.planarFissure.level",
                "activity.realmOfTheStrange.level",
            )
        ),
    ),
    # redeemCodes 不露出：兑换码在 SRA 里维护，开关生效时运行期原样拷进临时配置。
    "ReceiveRewards": _specs("common", *SRA_REWARD_NAMED_KEYS, *SRA_REWARD_LEGACY_KEYS),
    # 不露出 divergentUniverse.mode：SRA 2.21 起固定周期演算，不再读它。
    "DivergentUniverse": _specs(
        "common",
        "divergentUniverse.runtimes",
        "divergentUniverse.useTechnique",
        "pointRewards.enabled",
    ),
    # 不露出 currencyWars.strategyIndex / currencyWars.policy：SRA 不读。
    "CurrencyWars": (
        *_specs(
            "common",
            "currencyWars.mode",
            "currencyWars.difficulty",
            "currencyWars.runtimes",
            "currencyWars.strategy",
            "currencyWars.username",
        ),
        *(
            ManagedFieldSpec(key, "reroll", visible_when=_SRA_REROLL_MODE)
            for key in (
                "currencyWars.reroll.bossNames",
                "currencyWars.reroll.bossAffixes",
                "currencyWars.reroll.investEnvironments",
                "currencyWars.reroll.investStrategies",
            )
        ),
    ),
}


MANAGED_FIELDS: dict[str, dict[str, tuple[ManagedFieldSpec, ...]]] = {
    "M7A": M7A_MANAGED_FIELDS,
    "SRA": SRA_MANAGED_FIELDS,
}


def managed_field_specs(engine: str, module_key: str) -> tuple[ManagedFieldSpec, ...]:
    """某引擎某模块的字段表（有序）；没有该模块时为空。"""

    return MANAGED_FIELDS.get(str(engine).upper(), {}).get(module_key, ())


def managed_field_keys(engine: str, module_key: str) -> tuple[str, ...]:
    """某引擎某模块 MAS 允许覆盖的原生键（有序）。"""

    return tuple(spec.key for spec in managed_field_specs(engine, module_key))


def select_sra_reward_keys(keys: set[str] | frozenset[str]) -> frozenset[str]:
    """具名奖励键与数组下标键同时存在时丢掉下标键（SRA 以具名为准）。"""

    if any(key in keys for key in SRA_REWARD_NAMED_KEYS):
        return frozenset(key for key in keys if key not in SRA_REWARD_LEGACY_KEYS)
    return frozenset(keys)


__all__ = [
    "HSRFieldGroup",
    "M7A_MANAGED_FIELDS",
    "MANAGED_FIELDS",
    "ManagedFieldSpec",
    "ManagedFieldVisibleWhen",
    "SRA_MANAGED_FIELDS",
    "SRA_REWARD_LABELS",
    "SRA_REWARD_LEGACY_KEYS",
    "SRA_REWARD_NAMED_KEYS",
    "managed_field_keys",
    "managed_field_specs",
    "select_sra_reward_keys",
]
