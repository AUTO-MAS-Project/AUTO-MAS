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
) -> dict:
    """构造 M7A routine 的运行配置 patch。"""
    eow_enabled = bool(daily_eow_enabled)

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

    return patch


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


def build_receive_rewards_patch(user_config=None) -> dict[str, Any]:
    """构建 M7A 领取奖励 patch。"""
    return {
        "power_enable": False,
        "echo_of_war_enable": False,
        "build_target_enable": False,
        "cloud_game_enable": False,
        "daily_enable": True,
        "daily_material_enable": True,
        "daily_himeko_try_enable": False,
        "daily_memory_one_enable": False,
        "activity_enable": True,
        "activity_dailycheckin_enable": True,
        "activity_gardenofplenty_enable": False,
        "activity_realmofthestrange_enable": False,
        "activity_planarfissure_enable": False,
        "activity_journey_highlights_notification_enable": False,
        "reward_enable": True,
        "reward_dispatch_enable": True,
        "reward_mail_enable": True,
        "reward_assist_enable": True,
        "reward_quest_enable": True,
        "reward_srpass_enable": True,
        "reward_redemption_code_enable": True,
        "reward_achievement_enable": False,
        "reward_message_enable": False,
    }


def build_divergent_universe_patch(
    script_config,
    user_config,
    ornament_stage_name: str | None = None,
) -> dict[str, Any]:
    """构建 M7A 差分宇宙 patch。"""

    low_perf_value = script_config.get("Run", "LowPerformanceMode")
    low_perf_mode = (
        M7A_WEEKLY_DIVERGENT_STABLE_MODE_DEFAULT
        if low_perf_value is None
        else bool(low_perf_value)
    )

    patch = {
        "cloud_game_enable": False,
        "weekly_divergent_enable": True,
        "weekly_divergent_type": M7A_WEEKLY_DIVERGENT_TYPE,
        "weekly_divergent_level": M7A_WEEKLY_DIVERGENT_LEVEL,
        "weekly_divergent_bonus_enable": M7A_WEEKLY_DIVERGENT_BONUS_ENABLE,
        "weekly_divergent_stable_mode": low_perf_mode,
    }
    if M7A_WEEKLY_DIVERGENT_BONUS_ENABLE and ornament_stage_name:
        patch["instance_names"] = {
            M7A_INSTANCE_TYPE_ORNAMENT: ornament_stage_name,
        }
    return patch


def build_currency_wars_patch(
    user_config,
    ornament_stage_name: str | None = None,
) -> dict[str, Any]:
    """构建 M7A 货币战争 patch。"""
    username = str(user_config.get("Info", "Name") or "").strip()

    patch = {
        "cloud_game_enable": False,
        "currencywars_enable": True,
        "currencywars_type": M7A_CURRENCY_WARS_TYPE,
        "currencywars_rank_difficulty": M7A_CURRENCY_WARS_RANK_DIFFICULTY,
        "currencywars_strategy": M7A_CURRENCY_WARS_STRATEGY,
        "currencywars_strategy_restart_on_special_tags": (
            M7A_CURRENCY_WARS_STRATEGY_RESTART_ON_SPECIAL_TAGS
        ),
        "currencywars_fast_mode": M7A_CURRENCY_WARS_FAST_MODE,
        "currencywars_remembrance_trailblazer_name": username,
        "currencywars_bonus_enable": M7A_CURRENCY_WARS_BONUS_ENABLE,
    }
    if M7A_CURRENCY_WARS_BONUS_ENABLE and ornament_stage_name:
        patch["instance_names"] = {
            M7A_INSTANCE_TYPE_ORNAMENT: ornament_stage_name,
        }
    return patch


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


M7A_FORGOTTEN_HALL_PATCH_WHITELIST: frozenset[str] = frozenset({
    "forgottenhall_enable",
    "forgottenhall_level",
    "forgottenhall_team1",
    "forgottenhall_team2",
    "forgottenhall_team3",
    "purefiction_enable",
    "purefiction_level",
    "purefiction_team1",
    "purefiction_team2",
    "purefiction_team3",
    "apocalyptic_enable",
    "apocalyptic_level",
    "apocalyptic_team1",
    "apocalyptic_team2",
    "apocalyptic_team3",
    "cloud_game_enable",
})

_ABYSS_PREFIX_MAP: dict[str, str] = {
    "ForgottenHall": "forgottenhall",
    "PureFiction": "purefiction",
    "Apocalyptic": "apocalyptic",
}

_ABYSS_LABEL_MAP: dict[str, str] = {
    "ForgottenHall": "混沌回忆",
    "PureFiction": "虚构叙事",
    "Apocalyptic": "末日幻影",
}

ABYSS_RUN_SEQUENCE: tuple[tuple[str, str, str], ...] = (
    ("ForgottenHall", "forgottenhall", "混沌回忆"),
    ("PureFiction", "purefiction", "虚构叙事"),
    ("Apocalyptic", "apocalyptic", "末日幻影"),
)


def read_m7a_abyss_snapshots(
    config_path: Path,
) -> tuple[dict[str, dict], list[dict[str, Any]]]:
    """从 M7A config.yaml 读取三深渊快照。"""

    full_config = yaml.safe_load(config_path.read_text(encoding="utf-8-sig")) or {}
    if not isinstance(full_config, dict):
        raise ValueError("M7A config.yaml 顶层必须是对象")

    snapshots: dict[str, dict] = {}
    items: list[dict[str, Any]] = []
    for group, prefix in _ABYSS_PREFIX_MAP.items():
        key_prefix = f"{prefix}_"
        snapshot = {
            key: full_config[key]
            for key in M7A_FORGOTTEN_HALL_PATCH_WHITELIST
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
        raise ValueError("未从 M7A config.yaml 读取到任何三深渊快照")

    return snapshots, items


def _read_abyss_snapshots(user_config) -> dict:
    """读取并解析三深渊快照集合 JSON。"""
    raw_snapshot = user_config.get("Abyss", "Snapshots")

    if (
        raw_snapshot is None
        or not isinstance(raw_snapshot, str)
        or not raw_snapshot.strip()
    ):
        raise RuntimeError(
            "三深渊快照字段 Abyss.Snapshots 为空，"
            f"请先在 M7A 配置三深渊并从用户页「从 M7A 导入三深渊配置」导入"
        )

    try:
        snapshots = json.loads(raw_snapshot)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"三深渊快照 Abyss.Snapshots JSON 解析失败: {e}"
        ) from e

    if not isinstance(snapshots, dict):
        raise RuntimeError(
            f"三深渊快照 Abyss.Snapshots 不是 JSON 对象 "
            f"(类型: {type(snapshots).__name__})"
        )

    return snapshots


def _read_abyss_snapshot(user_config, abyss_type: str, label: str) -> dict:
    """从三深渊快照集合中读取单个深渊快照。"""
    snapshots = _read_abyss_snapshots(user_config)
    snapshot = snapshots.get(abyss_type)
    if not isinstance(snapshot, dict):
        raise RuntimeError(
            f"三深渊「{label}」快照缺失或不是 JSON 对象，"
            f"请重新从 M7A 导入三深渊配置"
        )
    return snapshot


def build_single_abyss_patch(user_config, abyss_type: str) -> dict[str, Any]:
    """按单个深渊快照构建 M7A config.yaml 白名单 patch。"""
    if abyss_type not in _ABYSS_PREFIX_MAP:
        raise RuntimeError(
            f"三深渊类型非法: {abyss_type!r}，"
            f"期望 ForgottenHall / PureFiction / Apocalyptic"
        )

    prefix = _ABYSS_PREFIX_MAP[abyss_type]
    label = _ABYSS_LABEL_MAP[abyss_type]

    snapshot = _read_abyss_snapshot(user_config, abyss_type, label)

    if not snapshot:
        raise RuntimeError(
            f"三深渊「{label}」尚未从 M7A 导入快照（Abyss.Snapshots 中为空对象），"
            f"请先在用户页点击「从 M7A 导入三深渊配置」"
        )

    required_fields = [
        f"{prefix}_{suffix}" for suffix in ("enable", "level", "team1", "team2")
    ]
    missing = [f for f in required_fields if f not in snapshot]
    if missing:
        raise RuntimeError(
            f"三深渊「{label}」快照缺少必需字段: {missing}，"
            f"快照中现有字段: {sorted(snapshot.keys())}；请重新从 M7A 导入"
        )

    patch: dict[str, Any] = {"cloud_game_enable": False}
    for other_prefix in _ABYSS_PREFIX_MAP.values():
        if other_prefix != prefix:
            patch[f"{other_prefix}_enable"] = False

    patch[f"{prefix}_enable"] = True
    team_fields = sorted(
        [
            key for key in snapshot
            if re.fullmatch(rf"{re.escape(prefix)}_team\d+", str(key))
        ],
        key=lambda key: int(str(key).rsplit("team", 1)[1]),
    )
    for field in [f"{prefix}_level", *team_fields]:
        patch[field] = snapshot[field]

    for k in list(patch.keys()):
        if k not in M7A_FORGOTTEN_HALL_PATCH_WHITELIST:
            raise RuntimeError(
                f"内部错误：build_single_abyss_patch 产出了白名单外字段 {k!r}"
            )
    for k in ("forgottenhall_timestamp", "purefiction_timestamp", "apocalyptic_timestamp"):
        if k in patch:
            raise RuntimeError(
                f"内部错误：build_single_abyss_patch 产出了 timestamp 字段 {k!r}"
            )

    return patch
