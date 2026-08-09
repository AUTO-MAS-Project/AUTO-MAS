#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.
#
#   Contact: DLmaster_361@163.com


"""M7A config.yaml patch 构造。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

import yaml


M7A_MANAGED_STAGE_KEYS: frozenset[str] = frozenset(
    {
        "power_enable",
        "power_plan",
        "instance_type",
        "instance_names",
        "instance_names_challenge_count",
        "echo_of_war_enable",
        "echo_of_war_timestamp",
        "echo_of_war_start_day_of_week",
        "currencywars_remembrance_trailblazer_name",
    }
)


def managed_modules_for_key(key: str) -> tuple[str, ...]:
    """Map a native M7A key to the MAS module that may override it."""

    if key in M7A_MANAGED_STAGE_KEYS or key.endswith("_timestamp") or key == "last_run_timestamp":
        return ()
    if key.startswith("weekly_divergent_"):
        return () if key == "weekly_divergent_enable" else ("DivergentUniverse",)
    if key.startswith("currencywars_"):
        return () if key == "currencywars_enable" else ("CurrencyWars",)
    if key == "activity_enable":
        return ("Daily", "ReceiveRewards")
    if key.startswith(("activity_dailycheckin_", "activity_journey_highlights_")):
        return ("ReceiveRewards",)
    if key.startswith("activity_"):
        return ("Daily",)
    if key.startswith("reward_") or key.startswith("daily_"):
        return () if key in {"reward_enable", "daily_enable"} else ("ReceiveRewards",)
    if key.startswith(
        (
            "power_",
            "instance_",
            "build_target_",
            "tp_",
            "borrow_",
            "merge_immersifier",
            "use_reserved_trailblaze_power",
            "use_fuel",
            "break_down_level_four_relicset",
            "calyx_golden_preference",
        )
    ):
        return ("Daily",)
    return ()


def _user_managed_options(user_config: Any, module_key: str) -> dict[str, Any]:
    if user_config is None:
        return {}
    try:
        raw = user_config.get("Managed", "Options")
    except (AttributeError, KeyError, TypeError):
        raw = {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    if not isinstance(raw, dict):
        return {}
    engine = raw.get("M7A")
    if not isinstance(engine, dict):
        return {}
    module = engine.get(module_key)
    return dict(module) if isinstance(module, dict) else {}


def _same_value_kind(value: Any, reference: Any) -> bool:
    if isinstance(reference, bool):
        return isinstance(value, bool)
    if isinstance(reference, int):
        return isinstance(value, int) and not isinstance(value, bool)
    if isinstance(reference, float):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(reference, list):
        return isinstance(value, list)
    if isinstance(reference, dict):
        return isinstance(value, dict)
    return isinstance(value, str) if isinstance(reference, str) else True


def resolve_managed_options(
    native_config: Mapping[str, Any],
    user_config: Any,
    module_key: str,
) -> dict[str, Any]:
    """Overlay one user's dynamic values onto fields discovered in config.yaml."""

    native = {
        str(key): value
        for key, value in native_config.items()
        if module_key in managed_modules_for_key(str(key))
    }
    overrides = _user_managed_options(user_config, module_key)
    unknown = sorted(set(overrides).difference(native))
    if unknown:
        raise ValueError(f"M7A {module_key} 包含当前原生配置不支持的字段：{'、'.join(unknown)}")
    effective = dict(native)
    for key, value in overrides.items():
        if not _same_value_kind(value, native[key]):
            raise ValueError(f"M7A {module_key}.{key} 的值类型与原生配置不一致")
        effective[key] = value
    return effective

_EOW_WEEKDAY_MAP: dict[str, int] = {
    "Monday": 1,
    "Tuesday": 2,
    "Wednesday": 3,
    "Thursday": 4,
    "Friday": 5,
    "Saturday": 6,
    "Sunday": 7,
}


def _echo_of_war_weekday_to_iso(weekday: object) -> int:
    """把 MAS 的星期配置转成 M7A 接受的 ISO weekday。"""
    if isinstance(weekday, str):
        normalized = weekday.strip().capitalize()
        if normalized in _EOW_WEEKDAY_MAP:
            return _EOW_WEEKDAY_MAP[normalized]
    return 1


M7A_INSTANCE_TYPE_RELIC = "侵蚀隧洞"
M7A_INSTANCE_TYPE_CALYX_GOLDEN = "拟造花萼（金）"
M7A_INSTANCE_TYPE_CALYX_CRIMSON = "拟造花萼（赤）"
M7A_INSTANCE_TYPE_STAGNANT_SHADOW = "凝滞虚影"
M7A_INSTANCE_TYPE_ORNAMENT = "饰品提取"

M7A_EOW_INSTANCE_NAME_KEY = "历战余响"
M7A_NO_OP_INSTANCE_TYPE = M7A_INSTANCE_TYPE_RELIC
M7A_NO_OP_INSTANCE_NAME = "无"
M7A_INSTANCE_TYPES_DAILY: tuple[str, ...] = (
    M7A_INSTANCE_TYPE_RELIC,
    M7A_INSTANCE_TYPE_CALYX_GOLDEN,
    M7A_INSTANCE_TYPE_CALYX_CRIMSON,
    M7A_INSTANCE_TYPE_STAGNANT_SHADOW,
    M7A_INSTANCE_TYPE_ORNAMENT,
)

M7A_ATTEMPTS_PER_RUN_MAX: dict[str, int] = {
    M7A_INSTANCE_TYPE_CALYX_GOLDEN: 24,
    M7A_INSTANCE_TYPE_CALYX_CRIMSON: 24,
    M7A_INSTANCE_TYPE_STAGNANT_SHADOW: 8,
    M7A_INSTANCE_TYPE_RELIC: 6,
    M7A_INSTANCE_TYPE_ORNAMENT: 6,
}

M7A_NOTIFICATION_DISABLE_PATCH: dict[str, Any] = {
    "notification_enable": False,
    "notify_merge": False,
    "notify_send_images": False,
    "notify_winotify_enable": False,
    "notify_telegram_enable": False,
    "notify_matrix_enable": False,
    "notify_serverchanturbo_enable": False,
    "notify_serverchan3_enable": False,
    "notify_bark_enable": False,
    "notify_smtp_enable": False,
    "notify_onebot_enable": False,
    "notify_gocqhttp_enable": False,
    "notify_dingtalk_enable": False,
    "notify_pushplus_enable": False,
    "notify_wechatworkapp_enable": False,
    "notify_wechatworkbot_enable": False,
    "notify_gotify_enable": False,
    "notify_discord_enable": False,
    "notify_pushdeer_enable": False,
    "notify_lark_enable": False,
    "notify_lark_imageenable": False,
    "notify_kook_enable": False,
    "notify_meow_enable": False,
    "notify_webhook_enable": False,
    "notify_custom_enable": False,
}
M7A_NOTIFICATION_PATCH_WHITELIST: frozenset[str] = frozenset(
    M7A_NOTIFICATION_DISABLE_PATCH
)


M7A_DAILY_PATCH_WHITELIST: frozenset[str] = frozenset({
    "daily_enable",
    "daily_material_enable",
    "daily_himeko_try_enable",
    "daily_memory_one_enable",
    "activity_enable",
    "activity_dailycheckin_enable",
    "activity_gardenofplenty_enable",
    "activity_realmofthestrange_enable",
    "activity_planarfissure_enable",
    "activity_journey_highlights_notification_enable",
    "reward_enable",
    "reward_dispatch_enable",
    "reward_mail_enable",
    "reward_assist_enable",
    "reward_quest_enable",
    "reward_srpass_enable",
    "reward_redemption_code_enable",
    "reward_achievement_enable",
    "reward_message_enable",
    "redemption_code",
    "power_enable",
    "echo_of_war_enable",
    "echo_of_war_timestamp",
    "build_target_enable",
    "build_target_scheme",
    "build_target_ornament_weekly_count",
    "build_target_use_user_instance_when_only_erosion_and_ornament",
    "instance_type",
    "instance_names",
    "instance_names_challenge_count",
    "use_reserved_trailblaze_power",
    "use_fuel",
    "echo_of_war_start_day_of_week",
    "cloud_game_enable",
})

M7A_DAILY_DEEP_MERGE_KEYS: frozenset[str] = frozenset({
    "instance_names",
    "instance_names_challenge_count",
})


def build_m7a_daily_patch(
    user_config: Any,
    daily_eow_enabled: bool,
    main_stage: tuple[str, str] | None = None,
    eow_name: str | None = None,
    *,
    script_config: Any | None = None,
    cultivation_target: Mapping[str, Any] | None = None,
) -> dict:
    """构造 M7A routine 的运行配置 patch。"""
    eow_enabled = bool(daily_eow_enabled)
    cultivation_enabled = bool(
        cultivation_target is not None and cultivation_target.get("Enabled")
    )

    # 配置不完整时直接报错，避免刷错副本。
    if eow_enabled and eow_name is None:
        raise RuntimeError(
            "本周需要尝试历战余响，但 Stage.ScriptEchoOfWar 缺少当前执行脚本可识别的"
            "原生历战余响字段；请在体力配置中重新选择历战余响"
        )

    eow_start_weekday = _echo_of_war_weekday_to_iso(
        user_config.get("TaskOpt", "EchoOfWarWeekday")
    )

    patch: dict = {
        "daily_enable": False,
        "daily_material_enable": False,
        "daily_himeko_try_enable": False,
        "daily_memory_one_enable": False,
        "activity_enable": False,
        "activity_dailycheckin_enable": False,
        "activity_gardenofplenty_enable": False,
        "activity_realmofthestrange_enable": False,
        "activity_planarfissure_enable": False,
        "activity_journey_highlights_notification_enable": False,
        "reward_enable": False,
        "reward_dispatch_enable": False,
        "reward_mail_enable": False,
        "reward_assist_enable": False,
        "reward_quest_enable": False,
        "reward_srpass_enable": False,
        "reward_redemption_code_enable": False,
        "reward_achievement_enable": False,
        "reward_message_enable": False,
        "redemption_code": [],
        "build_target_enable": False,
        "use_fuel": False,
        "use_reserved_trailblaze_power": False,
        "echo_of_war_start_day_of_week": eow_start_weekday,
        "cloud_game_enable": False,
    }

    new_instance_names: dict[str, str] = {}
    new_instance_counts: dict[str, int] = {}

    if main_stage is not None:
        main_type, main_name = main_stage
        count_max = M7A_ATTEMPTS_PER_RUN_MAX[main_type]
        patch["instance_type"] = main_type
        new_instance_names[main_type] = main_name
        new_instance_counts[main_type] = count_max
        patch["power_enable"] = True
    elif cultivation_enabled or eow_enabled:
        patch["power_enable"] = True
        patch["instance_type"] = M7A_NO_OP_INSTANCE_TYPE
        new_instance_names[M7A_NO_OP_INSTANCE_TYPE] = M7A_NO_OP_INSTANCE_NAME
    elif not eow_enabled:
        patch["power_enable"] = False
    else:
        patch["power_enable"] = True
        patch["instance_type"] = M7A_NO_OP_INSTANCE_TYPE
        new_instance_names[M7A_NO_OP_INSTANCE_TYPE] = M7A_NO_OP_INSTANCE_NAME

    if eow_enabled:
        assert eow_name is not None, "前置校验保证启用历战余响时 eow_name 不为 None"
        new_instance_names[M7A_EOW_INSTANCE_NAME_KEY] = eow_name
        patch["echo_of_war_enable"] = True
        patch["echo_of_war_timestamp"] = 0
    else:
        patch["echo_of_war_enable"] = False

    if new_instance_names:
        patch["instance_names"] = new_instance_names
    if new_instance_counts:
        patch["instance_names_challenge_count"] = new_instance_counts

    if cultivation_enabled:
        assert cultivation_target is not None
        scheme = cultivation_target.get("M7ARecognitionScheme") or "instance"
        if scheme not in ("instance", "drop"):
            raise ValueError(f"build_target_scheme 非法: {scheme!r}")
        ornament_count = cultivation_target.get("M7AOrnamentWeeklyCount")
        if (
            not isinstance(ornament_count, int)
            or isinstance(ornament_count, bool)
            or not 0 <= ornament_count <= 7
        ):
            raise ValueError(
                f"build_target_ornament_weekly_count 越界: {ornament_count!r}"
            )
        patch["build_target_enable"] = True
        patch["build_target_scheme"] = scheme
        patch["build_target_ornament_weekly_count"] = ornament_count
        patch[
            "build_target_use_user_instance_when_only_erosion_and_ornament"
        ] = bool(cultivation_target.get("M7AUseUserStageWhenOnlyRelics"))

    return _apply_managed_patch(
        patch,
        script_config=script_config,
        user_config=user_config,
        module_key="Daily",
        whitelist=M7A_DAILY_PATCH_WHITELIST,
    )


def with_disabled_notifications(patch: Mapping[str, Any]) -> dict[str, Any]:
    """叠加 M7A 本体通知关闭字段。"""

    merged = dict(patch)
    merged.update(M7A_NOTIFICATION_DISABLE_PATCH)
    return merged


def merge_whitelist(
    current_config: Mapping[str, Any] | None,
    patch: Mapping[str, Any],
    whitelist: frozenset[str] | None = None,
    deep_merge_keys: frozenset[str] | None = None,
) -> dict:
    """按白名单把 patch 合并到当前 M7A 配置。"""
    src = dict(current_config) if current_config else {}
    effective_whitelist = (
        whitelist if whitelist is not None else M7A_DAILY_PATCH_WHITELIST
    )
    effective_deep_merge = (
        deep_merge_keys if deep_merge_keys is not None else M7A_DAILY_DEEP_MERGE_KEYS
    )
    for k, v in patch.items():
        if k not in effective_whitelist:
            continue
        if (
            k in effective_deep_merge
            and isinstance(v, dict)
            and isinstance(src.get(k), dict)
        ):
            merged = dict(src[k])
            for sub_k, sub_v in v.items():
                merged[sub_k] = sub_v
            src[k] = merged
        else:
            src[k] = v
    return src


M7A_WEEKLY_DIVERGENT_TYPE: str = "cycle"  # 周期演算
M7A_WEEKLY_DIVERGENT_LEVEL: int = 5  # 难度 V
M7A_WEEKLY_DIVERGENT_BONUS_ENABLE: bool = True  # 积分奖励启用

M7A_WEEKLY_DIVERGENT_STABLE_MODE_DEFAULT: bool = False

M7A_CURRENCY_WARS_TYPE: str = "normal"  # 标准博弈
M7A_CURRENCY_WARS_RANK_DIFFICULTY: str = "lowest"  # 最低职级
M7A_CURRENCY_WARS_STRATEGY: str = "aglaea"  # 阿格莱雅策略
M7A_CURRENCY_WARS_STRATEGY_RESTART_ON_SPECIAL_TAGS: bool = True  # 特定词条接受重开
M7A_CURRENCY_WARS_FAST_MODE: bool = False
M7A_CURRENCY_WARS_BONUS_ENABLE: bool = True  # 积分奖励启用


def _script_option(script_config: Any, group: str, key: str, default: Any) -> Any:
    if script_config is None:
        return default
    try:
        value = script_config.get(group, key)
    except (AttributeError, KeyError, TypeError):
        value = None
    return default if value is None else value


def _load_native_config_for_managed(script_config: Any) -> dict[str, Any]:
    raw_root = _script_option(script_config, "M7A", "Path", "")
    if not raw_root:
        raw_root = _script_option(script_config, "Info", "M7APath", "")
    path = Path(str(raw_root or "").strip()) / "config.yaml"
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _apply_managed_patch(
    patch: dict[str, Any],
    *,
    script_config: Any,
    user_config: Any,
    module_key: str,
    whitelist: frozenset[str],
) -> dict[str, Any]:
    """Apply only dynamic fields accepted by the module's existing whitelist."""

    native = _load_native_config_for_managed(script_config)
    if not native:
        return patch
    effective = resolve_managed_options(native, user_config, module_key)
    protected = M7A_MANAGED_STAGE_KEYS
    for key, value in effective.items():
        if key in whitelist and key not in protected:
            patch[key] = value
    return patch


def build_receive_rewards_patch(
    user_config=None,
    *,
    script_config=None,
    redeem_codes_enabled: bool = True,
) -> dict[str, Any]:
    """构建 M7A 领取奖励 patch。"""
    run_daily_training = bool(
        _script_option(script_config, "M7AReceiveRewards", "RunDailyTraining", True)
    )
    daily_check_in = bool(
        _script_option(script_config, "M7AReceiveRewards", "DailyCheckIn", True)
    )
    rewards = {
        "reward_dispatch_enable": bool(
            _script_option(script_config, "M7AReceiveRewards", "Dispatch", True)
        ),
        "reward_mail_enable": bool(
            _script_option(script_config, "M7AReceiveRewards", "Mail", True)
        ),
        "reward_assist_enable": bool(
            _script_option(script_config, "M7AReceiveRewards", "Support", True)
        ),
        "reward_quest_enable": bool(
            _script_option(script_config, "M7AReceiveRewards", "DailyTrainingReward", True)
        ),
        "reward_srpass_enable": bool(
            _script_option(script_config, "M7AReceiveRewards", "NamelessHonor", True)
        ),
        "reward_redemption_code_enable": bool(
            _script_option(script_config, "M7AReceiveRewards", "RedeemCode", True)
        )
        and bool(redeem_codes_enabled),
        "reward_achievement_enable": bool(
            _script_option(script_config, "M7AReceiveRewards", "Achievement", False)
        ),
        "reward_message_enable": bool(
            _script_option(script_config, "M7AReceiveRewards", "Messages", False)
        ),
    }
    patch = {
        "power_enable": False,
        "echo_of_war_enable": False,
        "build_target_enable": False,
        "cloud_game_enable": False,
        "daily_enable": run_daily_training,
        "daily_material_enable": run_daily_training
        and bool(_script_option(script_config, "M7AReceiveRewards", "UseSynthesis", True)),
        "daily_himeko_try_enable": run_daily_training
        and bool(_script_option(script_config, "M7AReceiveRewards", "UseHimekoTrial", False)),
        "daily_memory_one_enable": run_daily_training
        and bool(_script_option(script_config, "M7AReceiveRewards", "UseMemoryOne", False)),
        "activity_enable": daily_check_in,
        "activity_dailycheckin_enable": daily_check_in,
        "activity_gardenofplenty_enable": False,
        "activity_realmofthestrange_enable": False,
        "activity_planarfissure_enable": False,
        "activity_journey_highlights_notification_enable": False,
        "reward_enable": any(rewards.values()),
        **rewards,
    }
    patch = _apply_managed_patch(
        patch,
        script_config=script_config,
        user_config=user_config,
        module_key="ReceiveRewards",
        whitelist=M7A_RECEIVE_REWARDS_PATCH_WHITELIST,
    )
    # 动态原生选项应用后重新收紧 ReceiveRewards 的运行边界；尤其不能让
    # “兑换码仅配置变化时执行”的本轮禁用判定被原生配置重新打开。
    patch.update({
        "power_enable": False,
        "echo_of_war_enable": False,
        "build_target_enable": False,
        "cloud_game_enable": False,
    })
    patch["reward_redemption_code_enable"] = bool(
        patch.get("reward_redemption_code_enable")
    ) and bool(redeem_codes_enabled)
    patch["daily_enable"] = any(
        bool(patch.get(key))
        for key in (
            "daily_material_enable",
            "daily_himeko_try_enable",
            "daily_memory_one_enable",
        )
    )
    patch["reward_enable"] = any(
        bool(value)
        for key, value in patch.items()
        if key.startswith("reward_") and key != "reward_enable"
    )
    return patch


def build_divergent_universe_patch(
    script_config,
    user_config,
    ornament_stage_name: str | None = None,
) -> dict[str, Any]:
    """构建 M7A 差分宇宙 patch。"""

    low_perf_value = _script_option(script_config, "Run", "LowPerformanceMode", None)
    low_perf_mode = (
        M7A_WEEKLY_DIVERGENT_STABLE_MODE_DEFAULT
        if low_perf_value is None
        else bool(low_perf_value)
    )

    patch = {
        "cloud_game_enable": False,
        "weekly_divergent_enable": True,
        "weekly_divergent_type": str(
            _script_option(script_config, "M7ADivergentUniverse", "Mode", M7A_WEEKLY_DIVERGENT_TYPE)
        ),
        "weekly_divergent_level": int(
            _script_option(script_config, "M7ADivergentUniverse", "Level", M7A_WEEKLY_DIVERGENT_LEVEL)
        ),
        "weekly_divergent_bonus_enable": bool(
            _script_option(script_config, "M7ADivergentUniverse", "BonusEnabled", M7A_WEEKLY_DIVERGENT_BONUS_ENABLE)
        ),
        "weekly_divergent_stable_mode": low_perf_mode,
    }
    if patch["weekly_divergent_bonus_enable"] and ornament_stage_name:
        patch["instance_names"] = {
            M7A_INSTANCE_TYPE_ORNAMENT: ornament_stage_name,
        }
    return _apply_managed_patch(
        patch,
        script_config=script_config,
        user_config=user_config,
        module_key="DivergentUniverse",
        whitelist=M7A_COSMIC_STRIFE_PATCH_WHITELIST,
    )


def build_currency_wars_patch(
    user_config,
    ornament_stage_name: str | None = None,
    *,
    script_config=None,
) -> dict[str, Any]:
    """构建 M7A 货币战争 patch。"""
    username = str(user_config.get("Info", "Name") or "").strip()

    patch = {
        "cloud_game_enable": False,
        "currencywars_enable": True,
        "currencywars_type": str(_script_option(script_config, "M7ACurrencyWars", "Mode", M7A_CURRENCY_WARS_TYPE)),
        "currencywars_rank_difficulty": str(_script_option(script_config, "M7ACurrencyWars", "RankDifficulty", M7A_CURRENCY_WARS_RANK_DIFFICULTY)),
        "currencywars_strategy": str(_script_option(script_config, "M7ACurrencyWars", "Strategy", M7A_CURRENCY_WARS_STRATEGY)),
        "currencywars_strategy_restart_on_special_tags": bool(_script_option(script_config, "M7ACurrencyWars", "RestartOnSpecialTags", M7A_CURRENCY_WARS_STRATEGY_RESTART_ON_SPECIAL_TAGS)),
        "currencywars_fast_mode": bool(_script_option(script_config, "M7ACurrencyWars", "FastMode", M7A_CURRENCY_WARS_FAST_MODE)),
        "currencywars_remembrance_trailblazer_name": username,
        "currencywars_bonus_enable": bool(_script_option(script_config, "M7ACurrencyWars", "BonusEnabled", M7A_CURRENCY_WARS_BONUS_ENABLE)),
    }
    if patch["currencywars_bonus_enable"] and ornament_stage_name:
        patch["instance_names"] = {
            M7A_INSTANCE_TYPE_ORNAMENT: ornament_stage_name,
        }
    return _apply_managed_patch(
        patch,
        script_config=script_config,
        user_config=user_config,
        module_key="CurrencyWars",
        whitelist=M7A_COSMIC_STRIFE_PATCH_WHITELIST,
    )


M7A_COSMIC_STRIFE_PATCH_WHITELIST: frozenset[str] = frozenset({
    "weekly_divergent_enable",
    "weekly_divergent_type",
    "weekly_divergent_level",
    "weekly_divergent_bonus_enable",
    "weekly_divergent_stable_mode",
    "currencywars_enable",
    "currencywars_type",
    "currencywars_rank_difficulty",
    "currencywars_strategy",
    "currencywars_strategy_restart_on_special_tags",
    "currencywars_fast_mode",
    "currencywars_remembrance_trailblazer_name",
    "currencywars_bonus_enable",
    "instance_names",
    "cloud_game_enable",
})


M7A_RECEIVE_REWARDS_PATCH_WHITELIST: frozenset[str] = frozenset({
    "power_enable",
    "echo_of_war_enable",
    "build_target_enable",
    "daily_enable",
    "daily_material_enable",
    "daily_himeko_try_enable",
    "daily_memory_one_enable",
    "activity_enable",
    "activity_dailycheckin_enable",
    "activity_gardenofplenty_enable",
    "activity_realmofthestrange_enable",
    "activity_planarfissure_enable",
    "activity_journey_highlights_notification_enable",
    "reward_enable",
    "reward_dispatch_enable",
    "reward_mail_enable",
    "reward_assist_enable",
    "reward_quest_enable",
    "reward_srpass_enable",
    "reward_redemption_code_enable",
    "reward_achievement_enable",
    "reward_message_enable",
    "cloud_game_enable",
})


# 保留旧 API 的一次性导入契约。三深渊已不再注册为任务，也不会进入运行队列；
# 这里只读取旧配置字段，供历史用户页导入接口继续返回兼容数据。
_LEGACY_ABYSS_PREFIX_MAP: dict[str, str] = {
    "ForgottenHall": "forgottenhall",
    "PureFiction": "purefiction",
    "Apocalyptic": "apocalyptic",
}
_LEGACY_ABYSS_CONFIG_KEYS: frozenset[str] = frozenset(
    f"{prefix}_{suffix}"
    for prefix in _LEGACY_ABYSS_PREFIX_MAP.values()
    for suffix in ("enable", "level", "team1", "team2", "team3")
)


def read_m7a_abyss_snapshots(
    config_path: Path,
) -> tuple[dict[str, dict], list[dict[str, Any]]]:
    """读取历史三深渊配置快照（仅供旧导入 API，非执行路径）。"""

    full_config = yaml.safe_load(config_path.read_text(encoding="utf-8-sig")) or {}
    if not isinstance(full_config, dict):
        raise ValueError("M7A config.yaml 顶层必须是对象")

    snapshots: dict[str, dict] = {}
    items: list[dict[str, Any]] = []
    for group, prefix in _LEGACY_ABYSS_PREFIX_MAP.items():
        key_prefix = f"{prefix}_"
        snapshot = {
            key: full_config[key]
            for key in _LEGACY_ABYSS_CONFIG_KEYS
            if key.startswith(key_prefix) and key in full_config
        }
        if not snapshot:
            continue

        snapshots[group] = snapshot
        level_value = snapshot.get(f"{prefix}_level")
        team_keys = sorted(
            {
                key.removeprefix(f"{prefix}_")
                for key in snapshot
                if re.fullmatch(rf"{re.escape(prefix)}_team\d+", str(key))
            },
            key=lambda key: int(key.removeprefix("team")),
        )
        items.append(
            {
                "snapshotKey": group,
                "success": True,
                "level": level_value if isinstance(level_value, list) else None,
                "teamKeys": team_keys,
            }
        )

    if not snapshots:
        raise ValueError("未从 M7A config.yaml 读取到任何历史三深渊快照")
    return snapshots, items
