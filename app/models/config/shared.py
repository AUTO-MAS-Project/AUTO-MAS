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
from typing import TYPE_CHECKING, Annotated, Any, Literal, cast

from pydantic import BeforeValidator, Field, TypeAdapter

from app.config import ConfigGroup, Virtual, encrypted, tz, ui
from app.config.types import FilePath, WindowsNameString

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

parse_legacy_bool = TypeAdapter(bool).validate_python


def none_as(value: str | int | float) -> BeforeValidator:
    """将显式空值还原为配置项原有的清空值，不改变省略或非空值的校验。"""

    def normalize(input_value: object) -> object:
        return value if input_value is None else input_value

    return BeforeValidator(normalize)


ProxyStatus = Literal["未知", "成功", "失败", "维护中", "运行中"]
"""账号上次运行结果：全部专项共用一套取值，写入方与展示方按此对齐。"""


class AccountNameFields(ConfigGroup):
    """账号名称与启用状态、剩余天数、备注、标签。全部专项都有。"""

    Name: WindowsNameString = Field(
        default_factory=lambda: "新账号", description="账号名称"
    )

    Notes: str = Field(default_factory=lambda: "无", description="备注")

    RemainedDay: Annotated[int, Field(ge=-1, le=9999), none_as(-1)] = Field(
        default_factory=lambda: -1, description="剩余天数"
    )

    Status: bool = Field(default_factory=lambda: True, description="是否启用")

    Tag: Virtual[str] = Field(default_factory=lambda: None, description="账号标签信息")


class AccountCredentialFields(ConfigGroup):
    """账号 / 密码。没有账号概念的专项（General、BAAH、Whimbox）不继承。"""

    Id: Annotated[str, encrypted()] = Field(
        default_factory=lambda: "", description="账号"
    )

    Password: Annotated[str, encrypted()] = Field(
        default_factory=lambda: "", description="密码"
    )


class AccountScriptHookFields(ConfigGroup):
    """任务前后执行脚本。BAAH 无此项。"""

    IfScriptAfterTask: bool = Field(
        default_factory=lambda: False, description="是否在任务后执行脚本"
    )

    IfScriptBeforeTask: bool = Field(
        default_factory=lambda: False, description="是否在任务前执行脚本"
    )

    ScriptAfterTask: FilePath = Field(
        default_factory=lambda: None, description="任务后脚本路径"
    )

    ScriptBeforeTask: FilePath = Field(
        default_factory=lambda: None, description="任务前脚本路径"
    )


class AccountRunFields(ConfigGroup):
    """上次代理日期与代理次数。全部专项都有。"""

    LastProxyDate: Annotated[datetime, tz(UTC4), ui(format="date")] = Field(
        default_factory=lambda: datetime(2000, 1, 1, tzinfo=UTC4),
        description="上次代理日期",
    )

    ProxyTimes: Annotated[int, Field(ge=0, le=9999)] = Field(
        default_factory=lambda: 0, description="代理次数"
    )


class AccountRunStatusFields(ConfigGroup):
    """上次运行结果。没有「上次状态」概念的专项（General、BAAH、HSR、Src）不继承。"""

    LastProxyStatus: ProxyStatus = Field(
        default_factory=lambda: "未知", description="上次代理状态"
    )


AccountFields = (AccountNameFields, AccountCredentialFields, AccountScriptHookFields)
"""账号 Info 的常用切片组合，供各类按需多继承。"""

AccountDataFields = (AccountRunFields, AccountRunStatusFields)
"""账号 Data 的切片组合。"""


class AccountNotifyFields(ConfigGroup):
    """账号通知：全部专项都有，服务端推送与邮件收件人。"""

    Enabled: bool = Field(default_factory=lambda: False, description="是否启用通知")

    IfSendMail: bool = Field(default_factory=lambda: False, description="是否发送邮件")

    IfSendStatistic: bool = Field(
        default_factory=lambda: False, description="是否发送统计信息"
    )

    IfServerChan: bool = Field(
        default_factory=lambda: False, description="是否启用 Server 酱"
    )

    ServerChanKey: str = Field(default_factory=lambda: "", description="Server 酱密钥")

    ToAddress: str = Field(default_factory=lambda: "", description="收件地址")


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
    if (
        config.Data.LastProxyDate.astimezone(tz).date() == datetime.now(tz=tz).date()
        and config.Data.ProxyTimes > 0
    ):
        return {"text": f"{label}：已代理{config.Data.ProxyTimes}次", "color": "green"}
    return {"text": f"{label}：未代理", "color": "orange"}


def _tag_remained_days(config: UserConfigType) -> dict:
    """剩余天数标签。"""
    remained_day = config.Info.RemainedDay
    if remained_day == -1:
        tag_color = "default"
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
        "color": "default",
    }


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


def _migrate_oknte_launch_mode_default(data: dict) -> tuple[dict, bool]:
    """为存量 OK-NTE 脚本固化升级前的启动方式「启动器界面」。

    ``Game.LaunchMode`` 是新增字段且类默认值定为 ``Autoplay``（静默启动）；
    升级前的存量脚本配置里没有该键，若不补值会随新默认落到 ``Autoplay``，
    而升级前「任务前启动游戏」走的只有「打开启动器界面 + 点开始游戏」这一条
    路——静默启动不驱动启动器弹窗、也不驱动游戏更新，直接改默认会让这部分
    用户从「能跑」变「启动失败」。故 load 前缺键注入升级前的 ``LauncherUi``；
    Game 段缺失（手工编辑/截断文件）同样按存量处理；Game 段损坏（非 dict）
    时跳过注入交给 load 的纠错路径重建，不在此崩掉启动。显式保存过该键的
    配置原样保留；新建托管由类默认落盘 ``Autoplay``，不走此路径。

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


__all__ = [
    "SRAProfileName",
    "_clamp_plan_number",
    "_migrate_oknte_launch_mode_default",
    "_normalize_maaend_sanity_task_type",
    "_tag_last_status",
    "_tag_notes",
    "_tag_proxy",
    "_tag_remained_days",
    "logger",
    "normalize_maaend_plan_key",
    "normalize_mss_plan_key",
    "schema_model",
    "validate_maaend_plan_key",
]


class OkwwTaskFields(ConfigGroup):
    AdditionalTasks: list[
        Literal[
            "Check Weekly Garden",
            "Auto Farm all Nightmare Nest",
            "Merge Echo If discarded > 1000",
            "Teleport and Farm 4C Echo",
        ]
    ] = Field(
        default_factory=lambda: ["Check Weekly Garden"],
        description="每日任务后运行的附加任务",
    )

    FarmNightmareNestForDailyEcho: bool = Field(
        default_factory=lambda: True, description="使用梦魇巢穴完成日常声骸"
    )

    MaterialSelection: Literal["Resonator EXP", "Weapon EXP", "Shell Credit"] = Field(
        default_factory=lambda: "Shell Credit", description="模拟领域材料"
    )

    WhichForgeryChallengeToFarm: Annotated[int, Field(ge=1, le=99), none_as(1)] = Field(
        default_factory=lambda: 1, description="凝素领域序号"
    )

    WhichTacetSuppressionToFarm: Annotated[int, Field(ge=1, le=99), none_as(1)] = Field(
        default_factory=lambda: 1, description="无音区序号"
    )

    WhichToFarm: Literal[
        "Tacet Suppression", "Forgery Challenge", "Simulation Challenge"
    ] = Field(
        default_factory=lambda: "Tacet Suppression",
        description="每日任务体力用途（日常任务按账号覆写或绑定计划生效）",
    )


def migrate_maaend_sanity_tasks(data: dict[str, Any]) -> dict[str, Any]:
    """拆分旧理智开关，保留固定任务、原生配置与轮换计划的运行范围。"""
    task = data.get("Task")
    if not isinstance(task, dict) or "IfSanity" not in task:
        return data
    info = data.setdefault("Info", {})
    enabled = parse_legacy_bool(task.pop("IfSanity"))
    strategy = info.setdefault("SanityStrategy", "MAS")
    mode = info.get("SanityMode", "Fixed")
    essence = strategy == "MAS" and task.get("SanityTaskType") in (
        "Essence",
        "Matrix",
        "AutoEssence",
    )
    scheduled = strategy == "MAS" and mode != "Fixed"
    task.setdefault("IfProtocolSpace", enabled and (not essence or scheduled))
    task.setdefault(
        "IfAutoEssence", enabled and (essence or scheduled or strategy == "Native")
    )
    info.setdefault(
        "AutoEssenceMode",
        "Native" if strategy == "Native" else mode if scheduled else "Fixed",
    )
    if essence and not scheduled:
        task["SanityTaskType"] = "OperatorProgression"
    # 新的每日一次分别消费原生任务名，旧总开关的记录同时迁入两项。
    selected = task.get("DailyOnceTasks", "[]")
    try:
        names = json.loads(selected) if isinstance(selected, str) else selected
    except (TypeError, ValueError):
        names = []
    if isinstance(names, list) and "Sanity" in names:
        names = [name for name in names if name != "Sanity"]
        task["DailyOnceTasks"] = json.dumps(
            list(dict.fromkeys([*names, "ProtocolSpace", "AutoEssence"]))
        )
    history = data.get("Data", {})
    try:
        records = json.loads(history.get("PeriodTaskRecords", "{}"))
    except (TypeError, ValueError):
        records = {}
    if isinstance(records, dict) and isinstance(records.get("daily"), dict):
        daily = records["daily"]
        if "Sanity" in daily:
            completed = daily.pop("Sanity")
            daily.setdefault("ProtocolSpace", completed)
            daily.setdefault("AutoEssence", completed)
            history["PeriodTaskRecords"] = json.dumps(records, ensure_ascii=False)
    return data
