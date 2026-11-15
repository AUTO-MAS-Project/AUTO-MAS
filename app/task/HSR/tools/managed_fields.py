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

所以「表单露出集 = 运行生效集」。外部脚本新版本新增的键按文件末尾「自动跟进」
的规则接在表后，同样两头生效；在 MAS 下没有意义的键（由 MAS 推导的总开关、
运行状态、MAS 已关掉的通知等）不进表，并写进自动跟进的排除名单。

本模块只放数据，不导入同包其它模块，供 ``m7a_config`` / ``sra_runtime`` /
``managed_config`` 共同引用而不成环。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

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
    # 不露出：power_plan_keep / power_plan_continue（体力计划不由 MAS 管）、
    # calyx_golden_preference（三月七读点已注释掉）、power_limit（只有循环模式读）、
    # activity_enable（MAS 按本模块三个活动子开关推导）、weekly_relic_cleanup_timestamp
    # （运行状态）。merge_immersifier 两项三月七 v2026.11 已删，留给旧版本。
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
            ManagedFieldSpec("instance_team_number", "team", visible_when=_M7A_TEAM_ON),
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
                description="从上到下依次查找。",
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
            "relic_bag_cleanup_enable",
            "break_down_level_four_relicset",
            ManagedFieldSpec(
                "weekly_relic_cleanup_day_of_week",
                "misc",
                visible_when=_on("break_down_level_four_relicset"),
                label="每周清理遗器的起始日",
                description="在游戏刷新时间后执行。",
            ),
            ManagedFieldSpec(
                "weekly_relic_smart_discard_enable",
                "misc",
                visible_when=_on("break_down_level_four_relicset"),
                label="每周清理时先智能弃置五星遗器",
                description="已弃置的遗器会一并分解。",
            ),
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
    # 不露出 weekly_divergent_stable_mode：以托管级「低性能兼容模式」为准。
    "DivergentUniverse": _specs(
        "common",
        "weekly_divergent_type",
        "weekly_divergent_level",
        "weekly_divergent_bonus_enable",
        "divergent_auto_save_enable",
    ),
    # currencywars_strategy_restart_on_special_tags 三月七 v2026.11 已删，留给旧版本。
    "CurrencyWars": _specs(
        "common",
        "currencywars_type",
        "currencywars_rank_difficulty",
        ManagedFieldSpec(
            "currencywars_unfinished_match",
            label="遇到未完成的对局",
            description="",
        ),
        "currencywars_bonus_enable",
        "currencywars_fast_mode",
        "currencywars_strategy",
        ManagedFieldSpec(
            "currencywars_investment_priority",
            label="投资环境与投资策略的选择",
            description="默认策略固定按图鉴优先，不受此项影响。",
        ),
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
        ManagedFieldSpec("useBuildTarget"),
        ManagedFieldSpec("materialPriority", visible_when=_on("useBuildTarget")),
        ManagedFieldSpec("useAssistant"),
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
    # divergentUniverse.mode：SRA 2.21 一度不读它，v2.25.5 的 CosmicStrifeTask
    # 又把它传给差分宇宙（0 刷单层 / 1 完整对局）。
    "DivergentUniverse": _specs(
        "common",
        "divergentUniverse.mode",
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
            "currencyWars.pointRewards",
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


# ---------------------------------------------------------------- 自动跟进
#
# 外部脚本新版本加的设置不必等 MAS 改字段表：原生配置里落在本模块范围内、
# 又不在排除名单里的标量键，自动接在字段表后面（「其它」分组），表单能改、
# 运行时照常套用。字段表只负责整理：排序、分组、从属显示、文案覆盖。

AUTO_FIELD_GROUP: HSRFieldGroup = "misc"

# 三月七 config.yaml 是平铺的，按键名前缀归模块。activity_ 不自动跟进：
# activity_enable 由 MAS 按已知的活动子开关推导，新活动开关单独打开也不会跑。
_M7A_AUTO_PREFIXES: dict[str, tuple[str, ...]] = {
    "Daily": ("instance_team", "borrow_", "build_target_", "relic_", "weekly_relic_"),
    "ReceiveRewards": ("reward_", "daily_"),
    "DivergentUniverse": ("weekly_divergent_", "divergent_"),
    "CurrencyWars": ("currencywars_",),
}
# 在 MAS 下没有意义的键：由 MAS 推导或钉死的开关、运行状态。
_M7A_AUTO_EXCLUDED: frozenset[str] = frozenset(
    {
        "daily_enable",
        "reward_enable",
        "weekly_divergent_enable",
        "weekly_divergent_stable_mode",
        "currencywars_enable",
        "currencywars_remembrance_trailblazer_name",
        # 手动跑差分宇宙用的模式；周常读 weekly_divergent_type
        "divergent_type",
    }
)
_M7A_AUTO_EXCLUDED_SUFFIXES: tuple[str, ...] = ("_timestamp", "_completed_count")

# SRA 的 profile 按任务分节：体力、领取奖励各占一节，整节都归本模块；
# 旷宇纷争一节里按点号前缀分给差分宇宙和货币战争。
_SRA_AUTO_PREFIXES: dict[str, tuple[str, ...]] = {
    "Daily": ("",),
    "ReceiveRewards": ("",),
    "DivergentUniverse": ("divergentUniverse.",),
    "CurrencyWars": ("currencyWars.",),
}
_SRA_AUTO_EXCLUDED: frozenset[str] = frozenset(
    {
        "enabled",
        "tasklist",
        "redeemCodes",
        "rewards",
        "divergentUniverse.enabled",
        "currencyWars.enabled",
        # SRA 不读
        "currencyWars.strategyIndex",
        "currencyWars.policy",
    }
)

_AUTO_RULES: dict[
    str, tuple[dict[str, tuple[str, ...]], frozenset[str], tuple[str, ...]]
] = {
    "M7A": (_M7A_AUTO_PREFIXES, _M7A_AUTO_EXCLUDED, _M7A_AUTO_EXCLUDED_SUFFIXES),
    "SRA": (_SRA_AUTO_PREFIXES, _SRA_AUTO_EXCLUDED, ()),
}


def auto_managed_keys(
    engine: str, module_key: str, native: Mapping[str, Any]
) -> tuple[str, ...]:
    """原生配置 ``native`` 里字段表没列、但按规则归本模块的标量键（按原生顺序）。

    ``native`` 对三月七是整份 config.yaml，对 SRA 是本模块所在的那一节。
    """

    engine = str(engine).upper()
    prefixes, excluded, excluded_suffixes = _AUTO_RULES.get(
        engine, ({}, frozenset(), ())
    )
    module_prefixes = prefixes.get(module_key, ())
    if not module_prefixes:
        return ()
    listed = {
        spec.key for specs in MANAGED_FIELDS.get(engine, {}).values() for spec in specs
    }
    return tuple(
        key
        for key, value in ((str(key), value) for key, value in native.items())
        if key.startswith(module_prefixes)
        and key not in listed
        and key not in excluded
        and not key.endswith(excluded_suffixes or ("\0",))
        and isinstance(value, (bool, int, float, str))
    )


def managed_field_specs(
    engine: str, module_key: str, native: Mapping[str, Any] | None = None
) -> tuple[ManagedFieldSpec, ...]:
    """某引擎某模块的字段（有序）：字段表在前；给了 ``native`` 时自动跟进的键接在后面。"""

    specs = MANAGED_FIELDS.get(str(engine).upper(), {}).get(module_key, ())
    if native is None:
        return specs
    return specs + tuple(
        ManagedFieldSpec(key, AUTO_FIELD_GROUP)
        for key in auto_managed_keys(engine, module_key, native)
    )


def managed_field_keys(
    engine: str, module_key: str, native: Mapping[str, Any] | None = None
) -> tuple[str, ...]:
    """某引擎某模块 MAS 允许覆盖的原生键（有序）。"""

    return tuple(spec.key for spec in managed_field_specs(engine, module_key, native))


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
    "auto_managed_keys",
    "managed_field_keys",
    "managed_field_specs",
    "select_sra_reward_keys",
]
