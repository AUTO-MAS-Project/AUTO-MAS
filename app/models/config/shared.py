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


from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone, tzinfo
from typing import TYPE_CHECKING, Annotated, Any, cast

from pydantic import BeforeValidator, TypeAdapter

if TYPE_CHECKING:
    from .script import UserConfigType
from app.utils import (
    MAAEND_AUTO_ESSENCE_MENUS,
    MAAEND_SANITY_TASK_DEFAULTS,
    MAAEND_SANITY_TASK_TYPES,
    MSS_DEFAULT_TRIBULATION_STAGE,
    MSS_TRIBULATION_STAGES,
    UTC4,
    get_logger,
)

from .. import schema as schema_model

logger = get_logger("配置模型")


def none_as(value: str | int | float) -> BeforeValidator:
    """将显式空值还原为配置项原有的清空值，不改变省略或非空值的校验。"""

    def normalize(input_value: object) -> object:
        return value if input_value is None else input_value

    return BeforeValidator(normalize)


def local_timezone(_model: object = None) -> timezone:
    """读取系统当前固定偏移，保留本地调度与缓存记录的原有时间口径。"""
    return cast(timezone, datetime.now().astimezone().tzinfo)


def normalize_sra_profile(value: object) -> str:
    """档案名可直接作为文件名，空串表示自动选择。"""
    if not isinstance(value, str):
        return ""
    if value != value.strip() or value in {".", ".."}:
        return ""
    if any(ch in '\\/:*?"<>|' or ord(ch) < 32 for ch in value):
        return ""
    return value


SRAProfileName = Annotated[str, BeforeValidator(normalize_sra_profile)]


def _normalize_maaend_sanity_task_type(task_data: object) -> None:
    """将旧版 MaaEnd 理智任务配置迁移到当前结构"""

    if not isinstance(task_data, dict):
        return

    sanity_task_type = task_data.get("SanityTaskType")
    if sanity_task_type == "ProtocolSpace":
        protocol_space_tab = task_data.get("ProtocolSpaceTab")
        if protocol_space_tab in MAAEND_SANITY_TASK_TYPES[:-1]:
            task_data["SanityTaskType"] = protocol_space_tab

    if task_data.get("SanityTaskType") not in MAAEND_SANITY_TASK_TYPES:
        return

    # 2.28+ 将基质模式拆为 AutoEssenceMenu；旧用户配置只有地点字段。
    menu = task_data.get("AutoEssenceMenu")
    if menu not in MAAEND_AUTO_ESSENCE_MENUS:
        target_weapons = task_data.get("AutoEssenceTargetWeapons")
        if isinstance(target_weapons, list) and target_weapons:
            task_data["AutoEssenceMenu"] = "Target"
        elif isinstance(task_data.get("AutoEssenceSpecifiedLocation"), str):
            task_data["AutoEssenceMenu"] = "Location"


def normalize_maaend_plan_key(raw_key: object) -> dict[str, Any]:
    """将固定配置或旧计划表日期槽位转换为 MaaEnd key。"""

    if isinstance(raw_key, dict) and "Key" in raw_key:
        raw_key = raw_key["Key"]
    data = raw_key if isinstance(raw_key, dict) else {}

    sanity_task_type = data.get("SanityTaskType")
    if sanity_task_type == "ProtocolSpace":
        sanity_task_type = data.get("ProtocolSpaceTab")
    elif sanity_task_type in ("Matrix", "AutoEssence"):
        sanity_task_type = "Essence"

    if sanity_task_type == "Essence":
        location = data.get("AutoEssenceSpecifiedLocation", "")
        candidate: dict[str, Any] = {
            "SanityTaskType": "Essence",
            "AutoEssenceSpecifiedLocation": location
            if isinstance(location, str)
            else "",
        }
        if "AutoEssenceMenu" in data:
            menu = data["AutoEssenceMenu"]
            target_weapons = data.get("AutoEssenceTargetWeapons")
            candidate["AutoEssenceMenu"] = (
                menu
                if menu in MAAEND_AUTO_ESSENCE_MENUS
                else (
                    "Target"
                    if isinstance(target_weapons, list) and target_weapons
                    else "Location"
                )
            )
        if "AutoEssenceTargetWeapons" in data:
            target_weapons = data["AutoEssenceTargetWeapons"]
            candidate["AutoEssenceTargetWeapons"] = (
                [item for item in target_weapons if isinstance(item, str)]
                if isinstance(target_weapons, list)
                else []
            )
    else:
        if sanity_task_type not in MAAEND_SANITY_TASK_TYPES[:-1]:
            sanity_task_type = MAAEND_SANITY_TASK_DEFAULTS["SanityTaskType"]
        candidate = {
            "SanityTaskType": sanity_task_type,
            "OperatorProgression": data.get(
                "OperatorProgression",
                MAAEND_SANITY_TASK_DEFAULTS["OperatorProgression"],
            ),
            "WeaponProgression": data.get(
                "WeaponProgression",
                MAAEND_SANITY_TASK_DEFAULTS["WeaponProgression"],
            ),
            "CrisisDrills": data.get(
                "CrisisDrills", MAAEND_SANITY_TASK_DEFAULTS["CrisisDrills"]
            ),
            "RewardsSetOption": data.get(
                "RewardsSetOption",
                MAAEND_SANITY_TASK_DEFAULTS["RewardsSetOption"],
            ),
        }

    try:
        key = TypeAdapter(schema_model.MaaEndPlanKey).validate_python(candidate)
    except ValueError:
        # Essence 的新字段来自动态资源；字段漂移或旧值损坏时仍保留基质任务，
        # 不应因为模式值无法识别而退回协议空间。
        key = (
            schema_model.MaaEndAutoEssencePlanKey()
            if sanity_task_type == "Essence"
            else schema_model.MaaEndProtocolSpacePlanKey()
        )
    if isinstance(key, schema_model.MaaEndAutoEssencePlanKey):
        # 保留历史 key 的稳定形状：新字段只在调用方明确提供时写入。
        result: dict[str, Any] = {
            "SanityTaskType": "Essence",
            "AutoEssenceSpecifiedLocation": key.AutoEssenceSpecifiedLocation,
        }
        if key.AutoEssenceMenu is not None and "AutoEssenceMenu" in candidate:
            result["AutoEssenceMenu"] = key.AutoEssenceMenu
        if key.AutoEssenceTargetWeapons and "AutoEssenceTargetWeapons" in candidate:
            result["AutoEssenceTargetWeapons"] = list(key.AutoEssenceTargetWeapons)
        return result
    return key.model_dump()


def validate_maaend_plan_key(raw_key: object) -> dict[str, Any]:
    """严格校验并返回规范化的 MaaEnd key。"""

    key = TypeAdapter(schema_model.MaaEndPlanKey).validate_python(raw_key)
    if isinstance(key, schema_model.MaaEndAutoEssencePlanKey):
        data = raw_key.get("Key", raw_key) if isinstance(raw_key, dict) else {}
        result: dict[str, Any] = {
            "SanityTaskType": "Essence",
            "AutoEssenceSpecifiedLocation": key.AutoEssenceSpecifiedLocation,
        }
        if isinstance(data, dict) and "AutoEssenceMenu" in data:
            result["AutoEssenceMenu"] = key.AutoEssenceMenu
        if (
            isinstance(data, dict)
            and "AutoEssenceTargetWeapons" in data
            and key.AutoEssenceTargetWeapons
        ):
            result["AutoEssenceTargetWeapons"] = list(key.AutoEssenceTargetWeapons)
        return result
    return key.model_dump()


def _tag_last_status(status: object) -> str:
    """「上次」标签文案。存储值的默认是「未知」，但从没跑过的用户显示「未知」很怪，
    页面上写成「未运行」；其余状态（成功 / 失败 / 运行中）原样。"""

    text = str(status or "").strip()
    return "未运行" if text in ("", "未知") else text


def _tag_proxy(config: UserConfigType, label: str = "日常", tz: tzinfo = UTC4) -> dict:
    """上次代理标签（默认使用东4区时间，tz 为游戏日时区），label 区分日常/任务文案。"""
    if config.Data.LastProxyDate.astimezone(tz).date() == datetime.now(tz=tz).date():
        return {"text": f"{label}：已代理{config.Data.ProxyTimes}次", "color": "green"}
    return {"text": f"{label}：未代理", "color": "orange"}


def _tag_remained_days(config: UserConfigType) -> dict:
    """剩余天数标签。"""
    remained_day = config.Info.RemainedDay
    if remained_day == -1:
        tag_color = "gold"
    elif remained_day == 0:
        tag_color = "red"
    elif remained_day <= 3:
        tag_color = "orange"
    elif remained_day <= 7:
        tag_color = "yellow"
    elif remained_day <= 30:
        tag_color = "blue"
    else:
        tag_color = "green"
    return {
        "text": (
            f"剩余天数：{remained_day}天" if remained_day >= 0 else "剩余天数：无期限"
        ),
        "color": tag_color,
    }


def _tag_notes(config: UserConfigType) -> dict:
    """备注标签。"""
    notes = config.Info.Notes
    return {
        "text": (f"备注：{notes}" if len(notes) <= 20 else f"备注：{notes[:20]}..."),
        "color": "pink",
    }


def migrate_maa_stamina_pipeline(data: dict) -> tuple[dict, bool]:
    """保留完整旧配置，将原来启用的两类活动内容合并为动态库存目标。"""

    migrated = deepcopy(data) if isinstance(data, dict) else {}
    if not migrated or migrated.get("Data", {}).get("StaminaPipelineVersion") == 1:
        return migrated, False
    task = migrated.setdefault("Task", {})
    old_task = data.get("Task", {})
    plans = []
    if old_task.get("IfEventDepotMaintain", False):
        saved = old_task.get("EventDepotMaintainPlans", "[]")
        try:
            saved = json.loads(saved) if isinstance(saved, str) else saved
        except (TypeError, ValueError):
            saved = []
            logger.warning("旧活动库存计划无法解析，原内容已保留在迁移前备份")
        if not isinstance(saved, list):
            saved = []
        for index, plan in enumerate(saved, start=1):
            if isinstance(plan, dict):
                plan = deepcopy(plan)
                plan.setdefault("StageType", "material")
                plan.setdefault("StageIndex", index)
                plan["LegacyIndex"] = True
                plans.append(plan)
    if old_task.get("IfActivityFirst", True):
        plans.append(
            {
                "StageType": "activity",
                "StageIndex": old_task.get("ActivityStageIndex", 1),
                "DropCount": 999,
                "OrundumDropCount": 9999,
                "LegacyActivityFirst": True,
            }
        )
    task["IfEventDepotMaintain"] = bool(
        old_task.get("IfEventDepotMaintain", False)
        or old_task.get("IfActivityFirst", True)
    )
    task["EventDepotMaintainPlans"] = json.dumps(plans, ensure_ascii=False)
    state = migrated.setdefault("Data", {})
    state["StaminaPipelineBackup"] = json.dumps(data, ensure_ascii=False)
    state["StaminaPipelineVersion"] = 1
    return migrated, True


BAAH_PLAN_KEY_SHAPE = {
    # 字段: (默认值, 最短长度, 最长长度)，与 schema 的 BAAHPlanKey 逐位对应；
    # 每一位的取值范围见 schema.BAAH_PLAN_KEY_SLOT_RULES，不在这里重复一份。
    "Wanted": ([1, -1, -1], 2, 4),
    "Special": ([1, -1, -1], 2, 4),
    "Exchange": ([1, -1, -1], 2, 4),
    "Hard": ([1, 1, -1], 2, 4),
    "Normal": ([1, 1, -1], 2, 4),
}


def default_baah_plan_key() -> dict[str, Any]:
    """默认拉满悬赏通缉和交流会、关闭特别委托，其余沿用 BAAH。"""
    return {"Wanted": [1, -1, -1], "Special": [], "Exchange": [1, -1, -1]}


def normalize_baah_plan_key(raw_key: object) -> dict[str, Any]:
    """将固定配置或旧计划表日期槽位转换为 BAAH key，任何输入都不抛异常。

    输入里没有的字段，结果里**也不会出现**：缺席表示「今天这一类不干预」，由 BAAH
    沿用自己配置里的关卡与开关；在这里补齐默认值会把它静默改成「按默认关卡打」。

    越界的位按 schema 的逐位规则修正到最近的合法值（困难图关卡 0/-1 修成 1、
    次数小于 -1 修成 -1、开关位非 0/1 修成 1），存量的脏配置因此也能过校验。
    """

    if isinstance(raw_key, dict) and "Key" in raw_key:
        raw_key = raw_key["Key"]
    data = raw_key if isinstance(raw_key, dict) else {}

    result: dict[str, Any] = {}
    for field, (default, minimum, maximum) in BAAH_PLAN_KEY_SHAPE.items():
        if field not in data:
            continue

        value = data[field]
        if value is None:
            # 显式 null 与字段缺失同义：都不干预这一类
            continue

        if not isinstance(value, list):
            result[field] = list(default)
            continue

        if not value:
            # 空数组表示「今天不打这一类」，补成默认值就变成照默认关卡打了
            result[field] = []
            continue

        try:
            items = [int(item) for item in value]
        except (TypeError, ValueError):
            # 每一位都有固定含义（如「地区、关卡、次数」），丢掉一位会让后面的
            # 位整体错位，所以只要有一位转不成 int，整项就回落到默认值。
            result[field] = list(default)
            continue

        if len(items) > maximum:
            items = items[:maximum]
        elif len(items) < minimum:
            # 缺位用默认值补齐，已经写明的位保持不动。
            items = items + default[len(items) :]

        # 存量配置里可能存着越界的位（如困难图关卡写成 0），按 schema 的规则表
        # 修正到最近的合法值：这一步只修不问，任何输入都不抛异常。
        result[field] = [
            schema_model.fix_baah_plan_slot(field, index, item)
            for index, item in enumerate(items)
        ]

    return result


def validate_baah_plan_key(raw_key: object) -> dict[str, Any]:
    """严格校验并返回规范化的 BAAH key，不合法时抛 ValueError。

    ``exclude_none=True`` 是必需的：缺席字段不能被 dump 成 ``None``，否则
    「今天不干预这一类」会跟着 key 一起落盘，语义与「不打这一类」混在一起。
    """

    return schema_model.BAAHPlanKey.model_validate(raw_key).model_dump(
        exclude_none=True, exclude={"Event"}
    )


def normalize_mss_plan_key(raw_key: object) -> dict[str, Any]:
    """将固定配置或旧计划表日期槽位转换为 MSS key。"""

    if isinstance(raw_key, dict) and "Key" in raw_key:
        raw_key = raw_key["Key"]
    data = raw_key if isinstance(raw_key, dict) else {}

    stage = data.get("TribulationStage")
    if stage not in MSS_TRIBULATION_STAGES:
        stage = MSS_DEFAULT_TRIBULATION_STAGE
    return {
        "TribulationStage": stage,
        "SkipDifficulty": bool(data.get("SkipDifficulty", False)),
        "Difficulty": _clamp_plan_number(data.get("Difficulty"), 1),
        "ConsumeAllEnergy": bool(data.get("ConsumeAllEnergy", False)),
        "FightTimes": _clamp_plan_number(data.get("FightTimes"), 1),
    }


def _clamp_plan_number(value: object, default: int) -> int:
    """把计划表里的难度 / 次数收成 1..99 的整数；非法值退回默认。"""

    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return number if 1 <= number <= 99 else default


_BGI_BUILTIN_ONE_DRAGON_GROUPS = [
    "领取邮件",
    "合成树脂",
    "自动幽境危战",
    "自动地脉花",
    "自动首领讨伐",
    "自动秘境",
    "领取尘歌壶奖励",
    "领取每日奖励",
]

_BGI_LEGACY_SERVERS_TO_RESOURCE = {
    "Asia": "亚服",
    "Europe": "欧服",
    "America": "美服",
    "TW,HK,MO": "港澳台服",
}


def _migrate_oknte_launch_mode_default(data: dict) -> tuple[dict, bool]:
    """为存量 OK-NTE 脚本固化升级前的启动方式「启动器界面」。

    ``Game.LaunchMode`` 是新增字段且类默认值定为 ``Autoplay``（静默启动）；
    升级前的存量脚本配置里没有该键，若不补值会随新默认落到 ``Autoplay``，
    而升级前「任务前启动游戏」走的只有「打开启动器界面 + 点开始游戏」这一条
    路——静默启动不驱动启动器弹窗、也不驱动游戏更新，直接改默认会让这部分
    用户从「能跑」变「启动失败」。故 load 前缺键注入升级前的 ``LauncherUi``；
    Game 段缺失（手工编辑/截断文件）同样按存量处理；Game 段损坏（非 dict）
    时跳过注入交给 load 的纠错路径重建，不在此崩掉启动。显式保存过该键的
    配置原样保留；新建脚本由类默认落盘 ``Autoplay``，不走此路径。

    Returns:
        (迁移后的配置字典, 是否发生了注入)
    """
    normalized_data = deepcopy(data) if isinstance(data, dict) else {}
    if "Game" not in normalized_data:
        normalized_data["Game"] = {}
    game = normalized_data["Game"]
    if isinstance(game, dict) and "LaunchMode" not in game:
        game["LaunchMode"] = "LauncherUi"
        return normalized_data, True
    return normalized_data, False


def _migrate_bgi_account_switch_default(data: dict) -> tuple[dict, bool]:
    """为存量 BetterGI 脚本固化旧默认切号方式 BGI。

    ``Run.AccountSwitchMethod`` 是 v5.6.0 新增字段且类默认值定为 MAS；
    5.5.0 升级上来的存量脚本配置里没有该键，若不补值会随新默认落到 MAS，
    使国际服/第三方登录等不被 MAS 切号支持的用户从「能跑」变「报错」。
    故 load 前缺键注入 ``BGI``（升级前的唯一切号路径）：Run 段缺失（手工
    编辑/截断文件）同样按存量处理；Run 段损坏（非 dict）时跳过注入交给
    load 的纠错路径重建，不在此崩掉启动。显式保存过该键的配置原样保留。

    Returns:
        (迁移后的配置字典, 是否发生了注入)
    """
    normalized_data = deepcopy(data) if isinstance(data, dict) else {}
    if "Run" not in normalized_data:
        normalized_data["Run"] = {}
    run = normalized_data["Run"]
    if isinstance(run, dict) and "AccountSwitchMethod" not in run:
        run["AccountSwitchMethod"] = "BGI"
        return normalized_data, True
    return normalized_data, False


def _migrate_baah_event_first(data: dict) -> tuple[dict, bool]:
    """把存量配置里的「活动适配」开关接到新的「活动关优先」。

    ``Info.IfActivityAdapt`` 与 ``Info.ActivityConfigName`` 随 5.5.0 / 5.6.0
    发出去过，本版改成计划表 + 活动关优先后两个字段都被删除。若直接删字段，
    当年开着活动适配的用户升级后 ``IfEventFirst`` 仍取默认的关，活动期间不再
    有任何动作，等于静默失效；这里把那时开着的适配开关迁移到 ``IfEventFirst``，
    保持升级前后的行为一致。

    ``ActivityConfigName`` 指向的是 BAAH 的配置文件名，新方案里没有对应概念
    （换成按周排的计划表），无法自动迁移，只能留在旧文件里不再读取。

    Returns:
        (迁移后的配置字典, 是否发生了迁移)
    """

    normalized_data = deepcopy(data) if isinstance(data, dict) else {}
    info = normalized_data.get("Info")
    if not isinstance(info, dict):
        return normalized_data, False

    ## 已经写过新键的配置不动，避免把用户后来的选择覆盖回 True
    if "IfEventFirst" in info or not info.get("IfActivityAdapt"):
        return normalized_data, False

    info["IfEventFirst"] = True
    return normalized_data, True


__all__ = [
    "SRAProfileName",
    "BAAH_PLAN_KEY_SHAPE",
    "_BGI_BUILTIN_ONE_DRAGON_GROUPS",
    "_BGI_LEGACY_SERVERS_TO_RESOURCE",
    "_clamp_plan_number",
    "_migrate_baah_event_first",
    "_migrate_bgi_account_switch_default",
    "_migrate_oknte_launch_mode_default",
    "_normalize_maaend_sanity_task_type",
    "_tag_last_status",
    "_tag_notes",
    "_tag_proxy",
    "_tag_remained_days",
    "default_baah_plan_key",
    "logger",
    "migrate_maa_stamina_pipeline",
    "normalize_baah_plan_key",
    "normalize_maaend_plan_key",
    "normalize_mss_plan_key",
    "schema_model",
    "validate_baah_plan_key",
    "validate_maaend_plan_key",
]
