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


import asyncio
import calendar
import json
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from app.utils import get_logger
from app.utils.constants import (
    CYCLE_EMPTY_TIME,
    MAA_STAGE_KEY,
    MAAEND_AUTO_COLLECT_MODES,
    MAAEND_AUTO_COLLECT_ROUTE_OPTIONS,
    MAAEND_AUTO_COLLECT_TASK,
    MAAEND_AUTO_ESSENCE_MENUS,
    MAAEND_DELIVERY_COMMISSION_SOURCES,
    MAAEND_DELIVERY_TASK,
    MAAEND_PROTOCOL_SPACE_TASK_OPTIONS,
    MAAEND_SANITY_TASK_DEFAULTS,
    MAAEND_SANITY_TASK_DETAIL_LABELS,
    MAAEND_SANITY_TASK_FIELDS,
    MAAEND_SANITY_TASK_LABELS,
    MAAEND_SANITY_TASK_TYPES,
    MAAEND_STAGE_WITH_AB,
    MAAEND_TASKS,
    MATERIALS_MAP,
    PLAN_CONSUMER_VALUES,
    RESOURCE_STAGE_INFO,
    STARRAIL_STAGE_BOOK,
    UTC4,
)

from . import schema as schema_model
from .ConfigBase import (
    AdvancedArgumentValidator,
    ArgumentValidator,
    BoolValidator,
    ConfigBase,
    ConfigItem,
    DateTimeValidator,
    EmulatorPathValidator,
    EncryptValidator,
    FileValidator,
    FolderValidator,
    JSONValidator,
    KeyValidator,
    MultipleConfig,
    MultipleOptionsValidator,
    MultipleUIDValidator,
    OptionsValidator,
    RangeValidator,
    StringListValidator,
    StringValidator,
    TypedMultipleUIDValidator,
    URLValidator,
    UserNameValidator,
    UUIDValidator,
    ValidatorBase,
    VirtualConfigValidator,
)
from .schema import TagItem

logger = get_logger("配置模型")


def init_maaend_task_config(config) -> None:
    """初始化 MaaEnd 托管任务配置"""

    ## 理智任务类型
    config.Task_SanityTaskType = ConfigItem(
        "Task",
        "SanityTaskType",
        MAAEND_SANITY_TASK_DEFAULTS["SanityTaskType"],
        OptionsValidator(list(MAAEND_SANITY_TASK_TYPES)),
    )
    ## 干员养成任务
    config.Task_OperatorProgression = ConfigItem(
        "Task",
        "OperatorProgression",
        MAAEND_SANITY_TASK_DEFAULTS["OperatorProgression"],
        OptionsValidator(
            list(MAAEND_PROTOCOL_SPACE_TASK_OPTIONS["OperatorProgression"])
        ),
    )
    ## 武器养成任务
    config.Task_WeaponProgression = ConfigItem(
        "Task",
        "WeaponProgression",
        MAAEND_SANITY_TASK_DEFAULTS["WeaponProgression"],
        OptionsValidator(list(MAAEND_PROTOCOL_SPACE_TASK_OPTIONS["WeaponProgression"])),
    )
    ## 危境预演任务
    config.Task_CrisisDrills = ConfigItem(
        "Task",
        "CrisisDrills",
        MAAEND_SANITY_TASK_DEFAULTS["CrisisDrills"],
        OptionsValidator(list(MAAEND_PROTOCOL_SPACE_TASK_OPTIONS["CrisisDrills"])),
    )
    ## 奖励套组选项
    config.Task_RewardsSetOption = ConfigItem(
        "Task",
        "RewardsSetOption",
        MAAEND_SANITY_TASK_DEFAULTS["RewardsSetOption"],
        OptionsValidator(["RewardsSetA", "RewardsSetB"]),
    )
    ## 基质刷取地点
    config.Task_AutoEssenceSpecifiedLocation = ConfigItem(
        "Task",
        "AutoEssenceSpecifiedLocation",
        MAAEND_SANITY_TASK_DEFAULTS["AutoEssenceSpecifiedLocation"],
        StringValidator(),
    )
    ## 基质刷取模式（兼容 MaaEnd 2.28+ 的 Random/Location/Target）
    config.Task_AutoEssenceMenu = ConfigItem(
        "Task",
        "AutoEssenceMenu",
        MAAEND_SANITY_TASK_DEFAULTS["AutoEssenceMenu"],
        OptionsValidator(list(MAAEND_AUTO_ESSENCE_MENUS)),
    )
    ## 基质目标武器 ID（选项由 MaaEnd 安装目录动态提供）
    config.Task_AutoEssenceTargetWeapons = ConfigItem(
        "Task",
        "AutoEssenceTargetWeapons",
        list(MAAEND_SANITY_TASK_DEFAULTS["AutoEssenceTargetWeapons"]),
        StringListValidator(),
    )

    ## 抢委托送货最低接取价格（万）
    config.Task_SeizeDeliveryJobsReward = ConfigItem(
        "Task", "SeizeDeliveryJobsReward", 15.9, RangeValidator(0, 9999)
    )
    ## 抢委托送货委托接收点
    config.Task_SeizeDeliveryJobsCommissionSource = ConfigItem(
        "Task",
        "SeizeDeliveryJobsCommissionSource",
        "Unlimited",
        OptionsValidator(list(MAAEND_DELIVERY_COMMISSION_SOURCES)),
    )
    ## 独立送货任务
    setattr(
        config,
        f"Task_If{MAAEND_DELIVERY_TASK}",
        ConfigItem("Task", f"If{MAAEND_DELIVERY_TASK}", True, BoolValidator()),
    )

    ## 独立自动采集任务
    config.Task_IfAutoCollect = ConfigItem(
        "Task", f"If{MAAEND_AUTO_COLLECT_TASK}", True, BoolValidator()
    )
    ## 自动采集路线安排：分散为三日轮换，集中为每三日执行一次
    config.Task_AutoCollectMode = ConfigItem(
        "Task",
        "AutoCollectMode",
        "Distributed",
        OptionsValidator(list(MAAEND_AUTO_COLLECT_MODES)),
    )
    ## 自动采集区域资源路线
    config.Task_AutoCollectRoutes = ConfigItem(
        "Task",
        "AutoCollectRoutes",
        list(MAAEND_AUTO_COLLECT_ROUTE_OPTIONS["AutoCollectRoutes"]),
        MultipleOptionsValidator(
            list(MAAEND_AUTO_COLLECT_ROUTE_OPTIONS["AutoCollectRoutes"])
        ),
    )
    ## 自动采集通用资源路线
    config.Task_AutoCollectCommonRoutes = ConfigItem(
        "Task",
        "AutoCollectCommonRoutes",
        list(MAAEND_AUTO_COLLECT_ROUTE_OPTIONS["AutoCollectCommonRoutes"]),
        MultipleOptionsValidator(
            list(MAAEND_AUTO_COLLECT_ROUTE_OPTIONS["AutoCollectCommonRoutes"])
        ),
    )

    ## 每日正常完成一次后，当天剩余时间跳过的任务名列表
    config.Task_DailyOnceTasks = ConfigItem(
        "Task", "DailyOnceTasks", "[ ]", JSONValidator(list)
    )

    for task_name in MAAEND_TASKS:
        setattr(
            config,
            f"Task_If{task_name}",
            ConfigItem(
                "Task",
                f"If{task_name}",
                task_name != "PullCountCalculator",
                BoolValidator(),
            ),
        )


"""
脚本级和用户级的 MaaEnd 任务配置项结构相同。配置文件来源为脚本且启用快速配置时,
任务开关读取脚本配置；理智任务选项始终读取用户配置。
"""


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
        candidate = {
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
        key = schema_model.MaaEndPlanConfig_Item(Key=candidate).Key
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

    key = schema_model.MaaEndPlanConfig_Item(Key=raw_key).Key
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


class MaaEndPlanKeyValidator(ValidatorBase):
    """MaaEnd 计划表 key 验证器。"""

    def validate(self, value: Any) -> bool:
        try:
            return validate_maaend_plan_key(value) == value
        except ValueError:
            return False

    def correct(self, value: Any) -> dict[str, Any]:
        return normalize_maaend_plan_key(value)


class SRAProfileValidator(ValidatorBase):
    """SRA 配置档案名验证器：只接受能直接拼成文件名的档案 id，空串表示自动。"""

    _FORBIDDEN = frozenset('\\/:*?"<>|')

    def validate(self, value):
        if not isinstance(value, str):
            return False
        if value == "":
            return True
        stripped = value.strip()
        if stripped != value or stripped in {".", ".."}:
            return False
        return not any(ch in self._FORBIDDEN or ord(ch) < 32 for ch in value)

    def correct(self, value):
        return value if self.validate(value) else ""


class EmulatorConfig(ConfigBase):
    """模拟器配置"""

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 模拟器名称
        self.Info_Name = ConfigItem("Info", "Name", "新模拟器")
        ## 模拟器类型
        self.Info_Type = ConfigItem(
            "Info",
            "Type",
            "general",
            OptionsValidator(
                [
                    "general",
                    "mumu",
                    "ldplayer",
                    # Emulator 2.0: 一条配置管多条模拟器路径, 路径写在 Info_Paths,
                    # Info_Path 保持空串(EmulatorPathValidator 允许空串)
                    "emulator2",
                    # "nox",  # 以下都是骗你的, 根本没有写~~
                    # "memu",
                    # "blueStacks",
                ]
            ),
            legacy_group="Data",
        )
        ## 模拟器路径
        self.Info_Path = ConfigItem(
            "Info", "Path", "", EmulatorPathValidator(self.Info_Type)
        )
        ## Emulator 2.0 纳管的模拟器路径列表
        ## [{"pathId", "installPath", "alias", "type", "version"}]
        self.Info_Paths = ConfigItem("Info", "Paths", "[]", JSONValidator(list))
        ## Emulator 2.0 的设备号槽位表
        ## [{"slot", "pathId", "nativeIndex", "state": "active"|"tombstone"}]
        ## 槽位号在本配置内单调递增分配, 移除路径写墓碑, 号码永不复用
        self.Info_Slots = ConfigItem("Info", "Slots", "[]", JSONValidator(list))
        ## Emulator 2.0 的稳定模式：开着就把会干扰截图识别的模拟器功能压住,
        ## 启动实例前顺带确保一次, 这样新建的实例也会跟着进入安全状态。
        ## 关掉只是不再确保, **不会把那些项改回去**——不知道用户原本想要什么值。
        ## Emulator 2.0 的配置守卫：以 MAS 存的这份设置为准, 启动前与关闭后各核验一次,
        ## 对不上就写回去。与旧雷电那套「开机拍快照关机还原」不是一回事, 见 utils/emulator2/guard.py
        self.Info_ConfigGuard = ConfigItem(
            "Info", "ConfigGuard", False, BoolValidator()
        )
        ## 守卫的基准: {设备号: {字段: 值}}, 只记用户显式设过的字段
        self.Info_Baselines = ConfigItem("Info", "Baselines", "{}", JSONValidator(dict))
        self.Info_StableMode = ConfigItem("Info", "StableMode", False, BoolValidator())
        ## 老板键快捷键配置
        self.Info_BossKey = ConfigItem(
            "Info", "BossKey", "[ ]", JSONValidator(list), legacy_group="Data"
        )
        ## 最大等待时间（秒）
        self.Info_MaxWaitTime = ConfigItem(
            "Info", "MaxWaitTime", 300, RangeValidator(1, 9999), legacy_group="Data"
        )
        ## 关闭 MuMu 时强力清理残留进程
        self.Info_ForceKillOnClose = ConfigItem(
            "Info", "ForceKillOnClose", False, BoolValidator()
        )

        super().__init__()


class Webhook(ConfigBase):
    """Webhook 配置"""

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## Webhook 名称
        self.Info_Name = ConfigItem("Info", "Name", "新自定义 Webhook 通知")
        ## 是否启用
        self.Info_Enabled = ConfigItem("Info", "Enabled", True, BoolValidator())

        ## Data ------------------------------------------------------------
        ## Webhook URL 地址
        self.Data_Url = ConfigItem("Data", "Url", "", URLValidator())
        ## 消息模板
        self.Data_Template = ConfigItem("Data", "Template", "")
        ## 请求头
        self.Data_Headers = ConfigItem("Data", "Headers", "{ }", JSONValidator())
        ## 请求方法
        self.Data_Method = ConfigItem(
            "Data", "Method", "POST", OptionsValidator(["POST", "GET"])
        )

        super().__init__()


class QueueItem(ConfigBase):
    """队列项配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 脚本 ID
        self.Info_ScriptId = ConfigItem(
            "Info",
            "ScriptId",
            "-",
            MultipleUIDValidator("-", self.related_config, "ScriptConfig"),
        )

        ## Schedule --------------------------------------------------------
        ## 是否参与循环调度
        self.Schedule_Enabled = ConfigItem("Schedule", "Enabled", True, BoolValidator())
        ## 循环调度模式: fixed_time 为固定时间, interval 为间隔
        self.Schedule_Mode = ConfigItem(
            "Schedule",
            "Mode",
            "fixed_time",
            OptionsValidator(["fixed_time", "interval"]),
        )
        ## 固定时间模式的执行周期
        self.Schedule_Days = ConfigItem(
            "Schedule",
            "Days",
            list(calendar.day_name),
            MultipleOptionsValidator(list(calendar.day_name)),
        )
        ## 固定时间模式的执行时间
        self.Schedule_Time = ConfigItem(
            "Schedule", "Time", "00:00", DateTimeValidator("%H:%M")
        )
        ## 间隔模式的间隔分钟数
        self.Schedule_IntervalMinutes = ConfigItem(
            "Schedule", "IntervalMinutes", 480, RangeValidator(1, 10080)
        )
        ## 间隔模式的计时基准: start 为上次开始, finish 为上次结束
        self.Schedule_IntervalAnchor = ConfigItem(
            "Schedule",
            "IntervalAnchor",
            "start",
            OptionsValidator(["start", "finish"]),
        )
        ## 下次运行时间, 空值哨兵表示由调度器按模式推算
        self.Schedule_NextRunAt = ConfigItem(
            "Schedule",
            "NextRunAt",
            CYCLE_EMPTY_TIME,
            DateTimeValidator("%Y-%m-%d %H:%M:%S"),
        )

        ## Data ------------------------------------------------------------
        ## 上次循环开始时间
        self.Data_LastCycleStartedAt = ConfigItem(
            "Data",
            "LastCycleStartedAt",
            CYCLE_EMPTY_TIME,
            DateTimeValidator("%Y-%m-%d %H:%M:%S"),
        )
        ## 上次循环结束时间
        self.Data_LastCycleFinishedAt = ConfigItem(
            "Data",
            "LastCycleFinishedAt",
            CYCLE_EMPTY_TIME,
            DateTimeValidator("%Y-%m-%d %H:%M:%S"),
        )

        super().__init__()


class TimeSet(ConfigBase):
    """时间设置配置"""

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 是否启用
        self.Info_Enabled = ConfigItem("Info", "Enabled", True, BoolValidator())
        ## 执行周期
        self.Info_Days = ConfigItem(
            "Info",
            "Days",
            list(calendar.day_name),
            MultipleOptionsValidator(list(calendar.day_name)),
        )
        ## 执行时间
        self.Info_Time = ConfigItem("Info", "Time", "00:00", DateTimeValidator("%H:%M"))

        super().__init__()


class QueueConfig(ConfigBase):
    """队列配置"""

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 队列名称
        self.Info_Name = ConfigItem("Info", "Name", "新队列")
        ## 是否启用定时启动
        self.Info_TimeEnabled = ConfigItem(
            "Info", "TimeEnabled", False, BoolValidator()
        )
        ## 是否在启动时自动运行
        self.Info_StartUpMode = ConfigItem(
            "Info",
            "StartUpMode",
            "Never",
            OptionsValidator(["Never", "Always", "DailyFirst"]),
        )
        ## 是否为循环队列: 定时与循环互斥, 循环队列按队列项各自的周期持续运行
        self.Info_CycleEnabled = ConfigItem(
            "Info", "CycleEnabled", False, BoolValidator()
        )
        ## 完成后操作
        self.Info_AfterAccomplish = ConfigItem(
            "Info",
            "AfterAccomplish",
            "NoAction",
            OptionsValidator(
                [
                    "NoAction",
                    "Shutdown",
                    "ShutdownForce",
                    "Reboot",
                    "Hibernate",
                    "Sleep",
                    "KillSelf",
                    "Logoff",
                ]
            ),
        )
        ## 完成后操作的延时时长, 单位分钟, 0 表示队列结束后直接进入倒计时
        self.Info_AfterAccomplishDelay = ConfigItem(
            "Info", "AfterAccomplishDelay", 0, RangeValidator(0, 1440)
        )

        ## Data ------------------------------------------------------------
        ## 上次定时启动时间
        self.Data_LastTimedStart = ConfigItem(
            "Data",
            "LastTimedStart",
            "2000-01-01 00:00",
            DateTimeValidator("%Y-%m-%d %H:%M"),
        )
        # 上次启动时运行时间
        self.Data_LastStartupTime = ConfigItem(
            "Data",
            "LastStartupTime",
            "2000-01-01",
            DateTimeValidator("%Y-%m-%d"),
        )

        self.TimeSet = MultipleConfig([TimeSet])
        self.QueueItem = MultipleConfig([QueueItem])

        super().__init__()

    async def load(self, data: dict) -> bool:
        """加载并迁移旧版调度队列配置文件"""

        info_data = data.get("Info")
        if isinstance(info_data, dict) and "StartUpMode" not in info_data:
            StartUpEnabled = info_data.get("StartUpEnabled")
            if isinstance(StartUpEnabled, bool):
                info_data["StartUpMode"] = "Always" if StartUpEnabled else "Never"

        return await super().load(data)


def _tag_proxy(config: ConfigBase, label: str = "日常") -> dict:
    """上次代理标签（使用东4区时间），label 区分日常/任务文案。"""
    if (
        datetime.strptime(config.get("Data", "LastProxyDate"), "%Y-%m-%d").date()
        == datetime.now(tz=UTC4).date()
    ):
        return {
            "text": f"{label}：已代理{config.get('Data', 'ProxyTimes')}次",
            "color": "green",
        }
    return {"text": f"{label}：未代理", "color": "orange"}


def _tag_remained_days(config: ConfigBase) -> dict:
    """剩余天数标签。"""
    remained_day = config.get("Info", "RemainedDay")
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


def _tag_notes(config: ConfigBase) -> dict:
    """备注标签。"""
    notes = config.get("Info", "Notes")
    return {
        "text": (f"备注：{notes}" if len(notes) <= 20 else f"备注：{notes[:20]}..."),
        "color": "pink",
    }


class MaaUserConfig(ConfigBase):
    """MAA用户配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 用户名称
        self.Info_Name = ConfigItem("Info", "Name", "新用户", UserNameValidator())
        ## 用户 ID
        self.Info_Id = ConfigItem("Info", "Id", "")
        ## 密码
        self.Info_Password = ConfigItem("Info", "Password", "", EncryptValidator())
        ## 脚本模式
        self.Info_Mode = ConfigItem("Info", "Mode", "脚本", ScriptUserModeValidator())
        ## 关卡模式
        self.Info_StageMode = ConfigItem(
            "Info",
            "StageMode",
            "Fixed",
            TypedMultipleUIDValidator(
                "Fixed", self.related_config, "PlanConfig", MaaPlanConfig
            ),
        )
        ## 游戏服务器
        self.Info_Server = ConfigItem(
            "Info",
            "Server",
            "Official",
            OptionsValidator(
                ["Official", "Bilibili", "YoStarEN", "YoStarJP", "YoStarKR", "txwy"]
            ),
        )
        ## 是否启用
        self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
        ## 剩余天数
        self.Info_RemainedDay = ConfigItem(
            "Info", "RemainedDay", -1, RangeValidator(-1, 9999)
        )
        ## 剿灭模式
        self.Info_Annihilation = ConfigItem(
            "Info",
            "Annihilation",
            "Annihilation",
            OptionsValidator(
                [
                    "Close",
                    "Annihilation",
                    "Chernobog@Annihilation",
                    "LungmenOutskirts@Annihilation",
                    "LungmenDowntown@Annihilation",
                ]
            ),
        )
        ## 剿灭开始星期
        self.Info_AnnihilationStartWeekday = ConfigItem(
            "Info",
            "AnnihilationStartWeekday",
            "Monday",
            OptionsValidator(
                [
                    "Monday",
                    "Tuesday",
                    "Wednesday",
                    "Thursday",
                    "Friday",
                    "Saturday",
                    "Sunday",
                ]
            ),
        )
        ## 基建模式
        self.Info_InfrastMode = ConfigItem(
            "Info",
            "InfrastMode",
            "Normal",
            OptionsValidator(["Normal", "Rotation", "Custom"]),
        )
        ## 基建配置名称
        self.Info_InfrastName = ConfigItem(
            "Info", "InfrastName", "-", VirtualConfigValidator(self.getInfrastName)
        )
        ## 基建配置索引
        self.Info_InfrastIndex = ConfigItem(
            "Info", "InfrastIndex", "-", VirtualConfigValidator(self.getInfrastIndex)
        )
        ## 任务前执行脚本
        self.Info_IfScriptBeforeTask = ConfigItem(
            "Info", "IfScriptBeforeTask", False, BoolValidator()
        )
        self.Info_ScriptBeforeTask = ConfigItem(
            "Info", "ScriptBeforeTask", "", FileValidator()
        )
        ## 任务后执行脚本
        self.Info_IfScriptAfterTask = ConfigItem(
            "Info", "IfScriptAfterTask", False, BoolValidator()
        )
        self.Info_ScriptAfterTask = ConfigItem(
            "Info", "ScriptAfterTask", "", FileValidator()
        )
        ## 备注
        self.Info_Notes = ConfigItem("Info", "Notes", "无")
        ## 理智药数量
        self.Info_MedicineNumb = ConfigItem(
            "Info", "MedicineNumb", 0, RangeValidator(0, 9999)
        )
        ## 连战次数
        self.Info_SeriesNumb = ConfigItem(
            "Info",
            "SeriesNumb",
            "0",
            OptionsValidator(["0", "6", "5", "4", "3", "2", "1", "-1"]),
        )
        ## 关卡
        self.Info_Stage = ConfigItem("Info", "Stage", "-")
        ## 关卡 1
        self.Info_Stage_1 = ConfigItem("Info", "Stage_1", "-")
        ## 关卡 2
        self.Info_Stage_2 = ConfigItem("Info", "Stage_2", "-")
        ## 关卡 3
        self.Info_Stage_3 = ConfigItem("Info", "Stage_3", "-")
        ## 备用关卡
        self.Info_Stage_Remain = ConfigItem("Info", "Stage_Remain", "-")
        ## 用户标签信息（虚拟字段，供前端显示）
        self.Info_Tag = ConfigItem(
            "Info", "Tag", "[ ]", VirtualConfigValidator(self.getTags)
        )

        ## Data ------------------------------------------------------------
        ## 上次代理日期
        self.Data_LastProxyDate = ConfigItem(
            "Data", "LastProxyDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        ## 代理次数
        self.Data_ProxyTimes = ConfigItem(
            "Data", "ProxyTimes", 0, RangeValidator(0, 9999)
        )
        ## 剿灭达到周上限时的 ISO 周（形如 "2026-W34"）
        self.Data_AnnihilationCompletedWeek = ConfigItem(
            "Data", "AnnihilationCompletedWeek", "2000-W01"
        )
        ## 上次完成绿票商店购买的月份
        self.Data_GreenTicketStoreMonth = ConfigItem(
            "Data", "GreenTicketStoreMonth", "2000-01", DateTimeValidator("%Y-%m")
        )
        ## 上次成功代理时服务端的游戏资源版本，用于识别待下载的资源热更新
        self.Data_LastResVersion = ConfigItem("Data", "LastResVersion", "")
        ## 自定义基建配置
        self.Data_CustomInfrast = ConfigItem(
            "Data", "CustomInfrast", "{ }", JSONValidator()
        )
        ## 基建配置索引数据
        self.Data_InfrastIndex = ConfigItem(
            "Data", "InfrastIndex", "0", legacy_group="Info"
        )

        ## Task ------------------------------------------------------------
        ## 是否自动唤醒
        self.Task_IfStartUp = ConfigItem("Task", "IfStartUp", True, BoolValidator())
        ## 是否理智作战
        self.Task_IfFight = ConfigItem("Task", "IfFight", True, BoolValidator())
        ## 是否基建换班
        self.Task_IfInfrast = ConfigItem("Task", "IfInfrast", True, BoolValidator())
        ## 是否公开招募
        self.Task_IfRecruit = ConfigItem("Task", "IfRecruit", True, BoolValidator())
        ## 是否信用收支
        self.Task_IfMall = ConfigItem("Task", "IfMall", True, BoolValidator())
        ## 是否领取奖励
        self.Task_IfAward = ConfigItem("Task", "IfAward", True, BoolValidator())
        ## 是否更换主题（主题名称在 MAA 侧配置，MAS 仅透传）
        self.Task_IfSwitchTheme = ConfigItem(
            "Task", "IfSwitchTheme", False, BoolValidator()
        )
        ## 是否自动肉鸽
        self.Task_IfRoguelike = ConfigItem(
            "Task", "IfRoguelike", False, BoolValidator()
        )
        ## 是否生息演算
        self.Task_IfReclamation = ConfigItem(
            "Task", "IfReclamation", False, BoolValidator()
        )
        ## 是否库存保持
        self.Task_IfDepotMaintain = ConfigItem(
            "Task", "IfDepotMaintain", False, BoolValidator()
        )
        ## 是否每月自动购买一次绿票商店
        self.Task_IfGreenTicketStore = ConfigItem(
            "Task", "IfGreenTicketStore", False, BoolValidator()
        )
        ## 活动期间是否优先刷活动关
        self.Task_IfActivityFirst = ConfigItem(
            "Task", "IfActivityFirst", False, BoolValidator()
        )
        ## 优先刷取的活动关卡序号
        self.Task_ActivityStageIndex = ConfigItem(
            "Task", "ActivityStageIndex", 1, RangeValidator(1, 9999)
        )
        ## 活动关优先任务吃理智药数量
        self.Task_ActivityMedicineNumb = ConfigItem(
            "Task",
            "ActivityMedicineNumb",
            0,
            RangeValidator(0, 9999),
            legacy_group="Info",
            legacy_name="MedicineNumb",
        )
        ## 库存保持计划
        self.Task_DepotMaintainPlans = ConfigItem(
            "Task", "DepotMaintainPlans", "[]", JSONValidator(list)
        )

        ## Notify ----------------------------------------------------------
        ## 是否启用通知
        self.Notify_Enabled = ConfigItem("Notify", "Enabled", False, BoolValidator())
        ## 是否发送统计信息
        self.Notify_IfSendStatistic = ConfigItem(
            "Notify", "IfSendStatistic", False, BoolValidator()
        )
        ## 是否发送六星通知
        self.Notify_IfSendSixStar = ConfigItem(
            "Notify", "IfSendSixStar", False, BoolValidator()
        )
        ## 是否发送邮件
        self.Notify_IfSendMail = ConfigItem(
            "Notify", "IfSendMail", False, BoolValidator()
        )
        ## 收件地址
        self.Notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
        ## 是否启用 Server 酱
        self.Notify_IfServerChan = ConfigItem(
            "Notify", "IfServerChan", False, BoolValidator()
        )
        ## Server 酱密钥
        self.Notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
        ## 自定义 Webhook 列表
        self.Notify_CustomWebhooks = MultipleConfig([Webhook])

        super().__init__()

    def getInfrastName(self) -> str:

        if self.get("Info", "InfrastMode") != "Custom":
            return "未使用自定义基建模式"

        infrast_data = json.loads(self.get("Data", "CustomInfrast"))
        if (
            infrast_data.get("title", "文件标题") != "文件标题"
            and infrast_data.get("description", "文件描述") != "文件描述"
        ):
            return f"{infrast_data['title']} - {infrast_data['description']}"
        elif infrast_data.get("title", "文件标题") != "文件标题":
            return str(infrast_data["title"])
        elif infrast_data.get("id", None):
            return str(infrast_data["id"])
        else:
            return "未命名自定义基建"

    def getInfrastIndex(self) -> str:

        if self.get("Info", "InfrastMode") != "Custom":
            return "-1"

        infrast_data = json.loads(self.get("Data", "CustomInfrast"))

        if len(infrast_data.get("plans", [])) == 0:
            return "-1"

        for i, plan in enumerate(infrast_data.get("plans", [])):
            for t in plan.get("period", []):
                if (
                    datetime.strptime(t[0], "%H:%M").time()
                    <= datetime.now().time()
                    <= datetime.strptime(t[1], "%H:%M").time()
                ):
                    return str(i)

        else:
            return self.get("Data", "InfrastIndex") or "0"

    def getTags(self) -> str:
        """生成用户标签列表，返回JSON字符串格式的TagItem列表"""
        tags = []

        # 日常代理标签（使用东4区时间）
        tags.append(_tag_proxy(self))

        # 剩余天数标签
        tags.append(_tag_remained_days(self))

        # 基建模式标签
        infrast_mode = self.get("Info", "InfrastMode")
        if self.get("Task", "IfInfrast"):
            if infrast_mode == "Normal":
                infrast_text = "基建：常规"
            elif infrast_mode == "Rotation":
                infrast_text = "基建：轮换"
            elif infrast_mode == "Custom":
                infrast_text = f"基建：{self.getInfrastName() if len(self.getInfrastName()) < 10 else self.getInfrastName()[:10] + '...'}"
            else:
                infrast_text = "基建：开启"
            tags.append({"text": infrast_text, "color": "purple"})
        else:
            tags.append({"text": "基建：关闭", "color": "red"})

        # 关卡信息标签
        if self.get("Info", "StageMode") == "Fixed":
            plan_data = {
                stage_key: self.get_stage_zh(self.get("Info", stage_key))
                for stage_key in MAA_STAGE_KEY[2:]
            }
            tag_color = "blue"
        else:
            plan = self.related_config["PlanConfig"][
                uuid.UUID(self.get("Info", "StageMode"))
            ]
            if isinstance(plan, MaaPlanConfig):
                plan_data = {
                    stage_key: self.get_stage_zh(
                        plan.get_current_info(stage_key).getValue()
                    )
                    for stage_key in MAA_STAGE_KEY[2:]
                }
                tag_color = "green"
        # 主关卡
        tags.append({"text": f"主关卡：{plan_data['Stage']}", "color": tag_color})
        # 备选关卡（合并显示）
        backup_stages = [
            plan_data[f"Stage_{i}"]
            for i in range(1, 4)
            if plan_data[f"Stage_{i}"] != "禁用"
        ]
        if backup_stages:
            tags.append(
                {"text": f"备选：{', '.join(backup_stages)}", "color": tag_color}
            )
        # 剩余关卡
        if plan_data["Stage_Remain"] != "禁用":
            tags.append(
                {"text": f"剩余：{plan_data['Stage_Remain']}", "color": tag_color}
            )

        # 备注标签
        tags.append(_tag_notes(self))

        return json.dumps(tags, ensure_ascii=False)

    @staticmethod
    def get_stage_zh(stage: str) -> str:

        for stage_info in RESOURCE_STAGE_INFO:
            if stage_info.get("value") == stage:
                return (
                    stage_info.get("text", stage)
                    .replace("经验-6/5", "经验")
                    .replace("龙门币-6/5", "龙门币")
                    .replace("红票-5", "红票")
                    .replace("技能-5", "技能")
                    .replace("碳-5", "碳")
                )
        else:
            return stage


class MaaConfig(ConfigBase):
    """MAA配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## MAA 脚本名称
        self.Info_Name = ConfigItem("Info", "Name", "新 MAA 脚本")
        ## MAA 路径
        self.Info_Path = ConfigItem("Info", "Path", "", FolderValidator())

        ## Emulator --------------------------------------------------------
        ## 模拟器 ID
        self.Emulator_Id = ConfigItem(
            "Emulator",
            "Id",
            "-",
            MultipleUIDValidator("-", self.related_config, "EmulatorConfig"),
        )
        ## 模拟器索引
        self.Emulator_Index = ConfigItem("Emulator", "Index", "-")

        ## Run -------------------------------------------------------------
        ## 任务切换方式
        self.Run_TaskTransitionMethod = ConfigItem(
            "Run",
            "TaskTransitionMethod",
            "ExitEmulator",
            OptionsValidator(["NoAction", "ExitGame", "ExitEmulator"]),
        )
        ## 代理次数限制
        self.Run_ProxyTimesLimit = ConfigItem(
            "Run", "ProxyTimesLimit", 0, RangeValidator(0, 9999)
        )
        ## 运行次数限制
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 3, RangeValidator(1, 9999)
        )
        ## 剿灭时间限制（分钟）
        self.Run_AnnihilationTimeLimit = ConfigItem(
            "Run", "AnnihilationTimeLimit", 40, RangeValidator(1, 9999)
        )
        ## 日常时间限制（分钟）
        self.Run_RoutineTimeLimit = ConfigItem(
            "Run", "RoutineTimeLimit", 10, RangeValidator(1, 9999)
        )
        ## 是否在启动 MAA 前检查游戏更新
        self.Run_IfCheckGameUpdate = ConfigItem(
            "Run", "IfCheckGameUpdate", False, BoolValidator()
        )
        ## 是否允许自动下载并安装游戏安装包（仅官服）
        self.Run_IfAutoInstallGameApk = ConfigItem(
            "Run", "IfAutoInstallGameApk", False, BoolValidator()
        )
        ## 游戏更新时间限制（分钟）
        self.Run_GameUpdateTimeLimit = ConfigItem(
            "Run", "GameUpdateTimeLimit", 60, RangeValidator(1, 9999)
        )

        self.UserData = MultipleConfig([MaaUserConfig])

        super().__init__()


class MaaEndConfigModeValidator(OptionsValidator):
    """兼容旧版来源名称，统一为脚本/用户/直控。"""

    LEGACY_MODE_MAP = {"简洁": "脚本", "详细": "用户", "自定义": "用户"}

    def __init__(self) -> None:
        super().__init__(["脚本", "用户", "直控"])

    def correct(self, value: Any) -> Any:
        if value in self.LEGACY_MODE_MAP:
            return self.LEGACY_MODE_MAP[value]
        return super().correct(value)


class MaaEndUserConfig(ConfigBase):
    """MaaEnd用户配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:
        self._maaend_essence_location_labels: dict[str, str] = {}

        ## Info ------------------------------------------------------------
        ## 用户名称
        self.Info_Name = ConfigItem("Info", "Name", "新用户", UserNameValidator())
        ## 是否启用
        self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
        ## 用户ID
        self.Info_Id = ConfigItem("Info", "Id", "")
        ## 密码
        self.Info_Password = ConfigItem("Info", "Password", "", EncryptValidator())
        ## 配置文件来源
        self.Info_Mode = ConfigItem("Info", "Mode", "脚本", MaaEndConfigModeValidator())
        ## 是否启用快速配置
        self.Info_IfQuickConfig = ConfigItem(
            "Info", "IfQuickConfig", True, BoolValidator()
        )
        ## 理智任务配置模式
        self.Info_SanityMode = ConfigItem(
            "Info",
            "SanityMode",
            "Fixed",
            TypedMultipleUIDValidator(
                "Fixed", self.related_config, "PlanConfig", MaaEndPlanConfig
            ),
        )
        ## 资源名称
        self.Info_Resource = ConfigItem(
            "Info", "Resource", "官服", OptionsValidator(["官服"])
        )
        ## 剩余天数
        self.Info_RemainedDay = ConfigItem(
            "Info", "RemainedDay", -1, RangeValidator(-1, 9999)
        )
        ## 任务前执行脚本
        self.Info_IfScriptBeforeTask = ConfigItem(
            "Info", "IfScriptBeforeTask", False, BoolValidator()
        )
        self.Info_ScriptBeforeTask = ConfigItem(
            "Info", "ScriptBeforeTask", "", FileValidator()
        )
        ## 任务后执行脚本
        self.Info_IfScriptAfterTask = ConfigItem(
            "Info", "IfScriptAfterTask", False, BoolValidator()
        )
        self.Info_ScriptAfterTask = ConfigItem(
            "Info", "ScriptAfterTask", "", FileValidator()
        )
        ## 备注
        self.Info_Notes = ConfigItem("Info", "Notes", "无")
        ## 用户标签信息
        self.Info_Tag = ConfigItem(
            "Info", "Tag", "[ ]", VirtualConfigValidator(self.getTags)
        )

        ## Task ------------------------------------------------------------
        init_maaend_task_config(self)

        ## Data ------------------------------------------------------------
        ## 上次代理日期
        self.Data_LastProxyDate = ConfigItem(
            "Data", "LastProxyDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        ## 代理次数
        self.Data_ProxyTimes = ConfigItem(
            "Data", "ProxyTimes", 0, RangeValidator(0, 9999)
        )
        ## 上次代理状态
        self.Data_LastProxyStatus = ConfigItem(
            "Data",
            "LastProxyStatus",
            "未知",
            OptionsValidator(["未知", "成功", "失败"]),
        )
        ## MaaEnd 每日任务完成记录，结构为 daily -> task name -> 日期
        self.Data_PeriodTaskRecords = ConfigItem(
            "Data", "PeriodTaskRecords", "{ }", JSONValidator(dict)
        )
        ## Notify ----------------------------------------------------------
        ## 是否启用通知
        self.Notify_Enabled = ConfigItem("Notify", "Enabled", False, BoolValidator())
        ## 是否发送统计信息
        self.Notify_IfSendStatistic = ConfigItem(
            "Notify", "IfSendStatistic", False, BoolValidator()
        )
        ## 是否发送邮件
        self.Notify_IfSendMail = ConfigItem(
            "Notify", "IfSendMail", False, BoolValidator()
        )
        ## 收件地址
        self.Notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
        ## 是否启用 Server 酱
        self.Notify_IfServerChan = ConfigItem(
            "Notify", "IfServerChan", False, BoolValidator()
        )
        ## Server 酱密钥
        self.Notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
        ## 自定义 Webhook 列表
        self.Notify_CustomWebhooks = MultipleConfig([Webhook])

        super().__init__()

    async def load(self, data: dict):
        info_data = data.get("Info")
        # 兼容旧版 MaaEnd 用户配置:
        # 旧“自定义”仍等价于用户级配置且关闭快速配置。
        # 没有 SanityMode 的旧“简洁/详细”回落为脚本级配置来源，快速配置使用默认值。
        if isinstance(info_data, dict):
            if info_data.get("Mode") == "自定义":
                info_data["Mode"] = "用户"
                info_data["IfQuickConfig"] = False
            elif (
                info_data.get("Mode") in ("简洁", "详细")
                and "SanityMode" not in info_data
            ):
                info_data["Mode"] = "脚本"
                info_data.pop("IfQuickConfig", None)
        task_data = data.get("Task")
        if isinstance(task_data, dict):
            _normalize_maaend_sanity_task_type(task_data)
        await super().load(data)

    def cache_maaend_resource(self, resource: dict[str, Any]) -> None:
        """缓存 MaaEnd 动态资源的展示文本。"""

        self._maaend_essence_location_labels = {
            str(item["value"]): str(item["label"])
            for item in resource.get("essenceLocations", [])
            if isinstance(item, dict) and item.get("value") is not None
        }

    def _get_maaend_location_label(self, value: str) -> str:
        if not value:
            return ""
        return self._maaend_essence_location_labels.get(value, value)

    def get_effective_sanity_task_key(self) -> tuple[dict[str, Any], str]:
        """获取当前生效的完整 MaaEnd key。"""

        mode = self.get("Info", "SanityMode")
        if mode == "Fixed":
            return normalize_maaend_plan_key(
                {field: self.get("Task", field) for field in MAAEND_SANITY_TASK_FIELDS}
            ), mode

        try:
            plan = self.related_config["PlanConfig"][uuid.UUID(mode)]
        except (KeyError, ValueError) as e:
            raise ValueError("引用的理智任务计划表不存在") from e

        return plan.get_current_key(), mode

    def getTags(self) -> str:
        """生成用户标签列表，返回JSON字符串格式的TagItem列表"""
        tags = []

        # 上次代理标签
        tags.append(
            {
                "text": f"上次：{self.get('Data', 'LastProxyStatus')}",
                "color": (
                    "red" if self.get("Data", "LastProxyStatus") == "失败" else "green"
                ),
            }
        )

        # 日常代理标签（使用东4区时间）
        tags.append(_tag_proxy(self))

        # 剩余天数标签
        tags.append(_tag_remained_days(self))

        # 理智任务标签
        if self.get("Task", "IfSanity"):
            task_key, _ = self.get_effective_sanity_task_key()
            sanity_task_type = task_key["SanityTaskType"]
            tags.append(
                {
                    "text": f"理智任务：{MAAEND_SANITY_TASK_LABELS[sanity_task_type]}",
                    "color": "blue",
                }
            )

            if sanity_task_type == "Essence" and task_key.get("AutoEssenceMenu") == "Target":
                target_weapons = task_key.get("AutoEssenceTargetWeapons", [])
                detail_key = "Target"
                detail_label = (
                    "目标武器（未限制）"
                    if not target_weapons
                    else f"目标武器（{len(target_weapons)} 件）"
                )
            else:
                detail_key = (
                    task_key["AutoEssenceSpecifiedLocation"]
                    if sanity_task_type == "Essence"
                    else task_key[sanity_task_type]
                )
                detail_label = (
                    self._get_maaend_location_label(detail_key)
                    if sanity_task_type == "Essence"
                    else MAAEND_SANITY_TASK_DETAIL_LABELS[detail_key]
                )
            tags.append(
                {
                    "text": f"详细任务：{detail_label}",
                    "color": "blue",
                }
            )

            if detail_key in MAAEND_STAGE_WITH_AB:
                tags.append(
                    {
                        "text": (
                            "奖励组：奖励组 A"
                            if task_key["RewardsSetOption"] == "RewardsSetA"
                            else "奖励组：奖励组 B"
                        ),
                        "color": "blue",
                    }
                )

        # 备注标签
        tags.append(_tag_notes(self))

        return json.dumps(tags, ensure_ascii=False)


class MaaEndConfig(ConfigBase):
    """MaaEnd配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## MaaEnd 脚本名称
        self.Info_Name = ConfigItem("Info", "Name", "新 MaaEnd 脚本")
        ## MaaEnd 路径
        self.Info_Path = ConfigItem("Info", "Path", "", FolderValidator())

        ## Run -------------------------------------------------------------
        ## 运行超时阈值
        self.Run_RunTimeLimit = ConfigItem(
            "Run", "RunTimeLimit", 10, RangeValidator(1, 9999)
        )
        ## 每日代理次数限制
        self.Run_ProxyTimesLimit = ConfigItem(
            "Run", "ProxyTimesLimit", 0, RangeValidator(0, 9999)
        )
        ## 运行次数限制
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 3, RangeValidator(1, 9999)
        )
        ## 账号切换方式
        self.Run_AccountSwitchMethod = ConfigItem(
            "Run",
            "AccountSwitchMethod",
            "MAS",
            OptionsValidator(["MAS", "MAAEND"]),
        )
        ## 任务切换方式
        self.Run_TaskTransitionMethod = ConfigItem(
            "Run",
            "TaskTransitionMethod",
            "NoAction",
            OptionsValidator(["NoAction", "ExitGame"]),
        )

        ## Game ------------------------------------------------------------
        ## 控制器类型
        self.Game_ControllerType = ConfigItem(
            "Game",
            "ControllerType",
            "",
            StringValidator(),
        )
        ## 终末地游戏路径
        self.Game_Path = ConfigItem("Game", "Path", "", FileValidator())
        ## 终末地游戏启动参数
        self.Game_Arguments = ConfigItem("Game", "Arguments", "", ArgumentValidator())
        ## 等待时间（秒）
        self.Game_WaitTime = ConfigItem(
            "Game", "WaitTime", 60, RangeValidator(60, 9999)
        )
        ## 模拟器 ID
        self.Game_EmulatorId = ConfigItem(
            "Game",
            "EmulatorId",
            "-",
            MultipleUIDValidator("-", self.related_config, "EmulatorConfig"),
        )
        ## 模拟器索引
        self.Game_EmulatorIndex = ConfigItem("Game", "EmulatorIndex", "-")
        ## 结束后是否关闭游戏
        self.Game_CloseOnFinish = ConfigItem(
            "Game", "CloseOnFinish", True, BoolValidator()
        )

        self.UserData = MultipleConfig([MaaEndUserConfig])

        super().__init__()

    async def load(self, data: dict) -> bool:
        is_dirty = await super().load(data)
        root_path_value = str(self.get("Info", "Path")).strip()
        resource_interface_path = Path(root_path_value) / "interface.json"
        if root_path_value and resource_interface_path.is_file():
            # 预加载搬入后台：MaaEnd 资源链的 import（约 270ms）与磁盘读取
            # 不再阻塞启动路径，资源就绪后仍会缓存到用户配置
            self._preload_task = asyncio.create_task(self.preload_resource())
        return is_dirty

    async def preload_resource(self) -> None:
        """尝试预加载 MaaEnd 动态资源，失败时保留现有配置。"""

        def _try_load_in_thread():
            from app.task.MaaEnd.resource_loader import try_load_maaend_options

            return try_load_maaend_options(Path(self.get("Info", "Path")))

        resource = await asyncio.to_thread(_try_load_in_thread)
        if resource is None:
            return
        for user_config in self.UserData.values():
            user_config.cache_maaend_resource(resource)

    def get_loaded_resource(self) -> dict[str, Any]:
        """读取已经载入内存的 MaaEnd 动态资源。"""

        from app.task.MaaEnd.resource_loader import get_loaded_maaend_options

        return get_loaded_maaend_options(Path(self.get("Info", "Path")))


class SrcUserConfig(ConfigBase):
    """SRC用户配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 用户名称
        self.Info_Name = ConfigItem("Info", "Name", "新用户", UserNameValidator())
        ## 是否启用
        self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
        ## 用户 ID
        self.Info_Id = ConfigItem("Info", "Id", "")
        ## 密码
        self.Info_Password = ConfigItem("Info", "Password", "", EncryptValidator())
        ## 脚本模式
        self.Info_Mode = ConfigItem("Info", "Mode", "脚本", ScriptUserModeValidator())
        ## 游戏服务器
        self.Info_Server = ConfigItem(
            "Info",
            "Server",
            "CN-Official",
            OptionsValidator(
                [
                    "CN-Official",
                    "CN-Bilibili",
                    "VN-Official",
                    "OVERSEA-America",
                    "OVERSEA-Asia",
                    "OVERSEA-Europe",
                    "OVERSEA-TWHKMO",
                ]
            ),
        )
        ## 剩余天数
        self.Info_RemainedDay = ConfigItem(
            "Info", "RemainedDay", -1, RangeValidator(-1, 9999)
        )
        ## 任务前执行脚本
        self.Info_IfScriptBeforeTask = ConfigItem(
            "Info", "IfScriptBeforeTask", False, BoolValidator()
        )
        self.Info_ScriptBeforeTask = ConfigItem(
            "Info", "ScriptBeforeTask", "", FileValidator()
        )
        ## 任务后执行脚本
        self.Info_IfScriptAfterTask = ConfigItem(
            "Info", "IfScriptAfterTask", False, BoolValidator()
        )
        self.Info_ScriptAfterTask = ConfigItem(
            "Info", "ScriptAfterTask", "", FileValidator()
        )
        ## 备注
        self.Info_Notes = ConfigItem("Info", "Notes", "无")
        ## 用户标签信息
        self.Info_Tag = ConfigItem(
            "Info", "Tag", "[ ]", VirtualConfigValidator(self.getTags)
        )

        ## 关卡配置----------------------------------------------------------
        ## 关卡通道
        self.Stage_Channel = ConfigItem(
            "Stage",
            "Channel",
            "Relic",
            OptionsValidator(["Relic", "Materials", "Ornament"]),
        )
        ## 遗器关卡
        self.Stage_Relic = ConfigItem(
            "Stage",
            "Relic",
            "-",
            OptionsValidator(
                [
                    "-",
                    "Cavern_of_Corrosion_Path_of_Insight",
                    "Cavern_of_Corrosion_Path_of_Possession",
                    "Cavern_of_Corrosion_Path_of_Hidden_Salvation",
                    "Cavern_of_Corrosion_Path_of_Thundersurge",
                    "Cavern_of_Corrosion_Path_of_Aria",
                    "Cavern_of_Corrosion_Path_of_Uncertainty",
                    "Cavern_of_Corrosion_Path_of_Cavalier",
                    "Cavern_of_Corrosion_Path_of_Dreamdive"
                    "Cavern_of_Corrosion_Path_of_Darkness",
                    "Cavern_of_Corrosion_Path_of_Elixir_Seekers",
                    "Cavern_of_Corrosion_Path_of_Conflagration",
                    "Cavern_of_Corrosion_Path_of_Holy_Hymn",
                    "Cavern_of_Corrosion_Path_of_Providence",
                    "Cavern_of_Corrosion_Path_of_Drifting",
                    "Cavern_of_Corrosion_Path_of_Jabbing_Punch",
                    "Cavern_of_Corrosion_Path_of_Gelid_Wind",
                ]
            ),
        )
        ## 材料关卡
        self.Stage_Materials = ConfigItem(
            "Stage",
            "Materials",
            "-",
            OptionsValidator(
                [
                    "-",
                    "Calyx_Golden_Memories_Planarcadia",
                    "Calyx_Golden_Memories_Amphoreus",
                    "Calyx_Golden_Memories_Penacony",
                    "Calyx_Golden_Memories_The_Xianzhou_Luofu",
                    "Calyx_Golden_Memories_Jarilo_VI",
                    "Calyx_Golden_Aether_Planarcadia",
                    "Calyx_Golden_Aether_Amphoreus",
                    "Calyx_Golden_Aether_Penacony",
                    "Calyx_Golden_Aether_The_Xianzhou_Luofu",
                    "Calyx_Golden_Aether_Jarilo_VI",
                    "Calyx_Golden_Treasures_Planarcadia",
                    "Calyx_Golden_Treasures_Amphoreus",
                    "Calyx_Golden_Treasures_Penacony",
                    "Calyx_Golden_Treasures_The_Xianzhou_Luofu",
                    "Calyx_Golden_Treasures_Jarilo_VI",
                    "Calyx_Crimson_Destruction_Herta_StorageZone",
                    "Calyx_Crimson_Destruction_Luofu_ScalegorgeWaterscape",
                    "Calyx_Crimson_Destruction_Planarcadia_InkfordHermitage",
                    "Calyx_Crimson_Preservation_Herta_SupplyZone",
                    "Calyx_Crimson_Preservation_Penacony_ClockStudiosThemePark",
                    "Calyx_Crimson_The_Hunt_Jarilo_OutlyingSnowPlains",
                    "Calyx_Crimson_The_Hunt_Penacony_SoulGladScorchsandAuditionVenue",
                    "Calyx_Crimson_The_Hunt_Amphoreus_MemortisShoreRuinsofTime",
                    "Calyx_Crimson_Abundance_Jarilo_BackwaterPass",
                    "Calyx_Crimson_Abundance_Luofu_FyxestrollGarden",
                    "Calyx_Crimson_Erudition_Jarilo_RivetTown",
                    "Calyx_Crimson_Erudition_Penacony_PenaconyGrandTheater",
                    "Calyx_Crimson_Erudition_Planarcadia_SeafeldTVTower",
                    "Calyx_Crimson_Harmony_Jarilo_RobotSettlement",
                    "Calyx_Crimson_Harmony_Penacony_TheReverieDreamscape",
                    "Calyx_Crimson_Nihility_Jarilo_GreatMine",
                    "Calyx_Crimson_Nihility_Luofu_AlchemyCommission",
                    "Calyx_Crimson_Nihility_Amphoreus_RadiantScarwoodGroveofEpiphany",
                    "Calyx_Crimson_Remembrance_Amphoreus_StrifeRuinsCastrumKremnos",
                    "Calyx_Crimson_Elation_Planarcadia_WorldEndTavern",
                    "Stagnant_Shadow_Spike",
                    "Stagnant_Shadow_Perdition",
                    "Stagnant_Shadow_Duty",
                    "Stagnant_Shadow_Deepsheaf",
                    "Stagnant_Shadow_Blaze",
                    "Stagnant_Shadow_Scorch",
                    "Stagnant_Shadow_Roast",
                    "Stagnant_Shadow_Ire",
                    "Stagnant_Shadow_Ashes",
                    "Stagnant_Shadow_Rime",
                    "Stagnant_Shadow_Icicle",
                    "Stagnant_Shadow_Nectar",
                    "Stagnant_Shadow_Sirens",
                    "Stagnant_Shadow_Fulmination",
                    "Stagnant_Shadow_Doom",
                    "Stagnant_Shadow_Mechwolf",
                    "Stagnant_Shadow_Soundburst",
                    "Stagnant_Shadow_Gust",
                    "Stagnant_Shadow_Celestial",
                    "Stagnant_Shadow_Gloam",
                    "Stagnant_Shadow_Cinders",
                    "Stagnant_Shadow_Quanta",
                    "Stagnant_Shadow_Abomination",
                    "Stagnant_Shadow_Gelidmoon",
                    "Stagnant_Shadow_Devour",
                    "Stagnant_Shadow_Mirage",
                    "Stagnant_Shadow_Puppetry",
                    "Stagnant_Shadow_Timbre",
                    "Stagnant_Shadow_Sloggyre",
                ]
            ),
        )
        ## 饰品关卡
        self.Stage_Ornament = ConfigItem(
            "Stage",
            "Ornament",
            "-",
            OptionsValidator(
                [
                    "-",
                    "Divergent_Universe_Bugs_Incoming",
                    "Divergent_Universe_Gilded_Recollection",
                    "Divergent_Universe_Within_the_West_Wind",
                    "Divergent_Universe_Moonlit_Blood",
                    "Divergent_Universe_Unceasing_Strife",
                    "Divergent_Universe_Famished_Worker",
                    "Divergent_Universe_Eternal_Comedy",
                    "Divergent_Universe_To_Sweet_Dreams",
                    "Divergent_Universe_Pouring_Blades",
                    "Divergent_Universe_Fruit_of_Evil",
                    "Divergent_Universe_Permafrost",
                    "Divergent_Universe_Gentle_Words",
                    "Divergent_Universe_Smelted_Heart",
                    "Divergent_Universe_Untoppled_Walls",
                ]
            ),
        )
        ## 使用储备开拓力
        self.Stage_ExtractReservedTrailblazePower = ConfigItem(
            "Stage", "ExtractReservedTrailblazePower", False, BoolValidator()
        )
        ## 使用燃料
        self.Stage_UseFuel = ConfigItem("Stage", "UseFuel", False, BoolValidator())
        ## 保留的燃料数量
        self.Stage_FuelReserve = ConfigItem(
            "Stage", "FuelReserve", 5, RangeValidator(0, 9999)
        )
        ## 历战余响关卡
        self.Stage_EchoOfWar = ConfigItem(
            "Stage",
            "EchoOfWar",
            "-",
            OptionsValidator(
                [
                    "-",
                    "Echo_of_War_The_Comedy_of_Doom",
                    "Echo_of_War_Rusted_Crypt_of_the_Iron_Carcass",
                    "Echo_of_War_Glance_of_Twilight",
                    "Echo_of_War_Inner_Beast_Battlefield",
                    "Echo_of_War_Salutations_of_Ashen_Dreams",
                    "Echo_of_War_Borehole_Planet_Past_Nightmares",
                    "Echo_of_War_Divine_Seed",
                    "Echo_of_War_End_of_the_Eternal_Freeze",
                    "Echo_of_War_Destruction_Beginning",
                ]
            ),
        )
        ## 模拟宇宙关卡
        self.Stage_SimulatedUniverseWorld = ConfigItem(
            "Stage",
            "SimulatedUniverseWorld",
            "-",
            OptionsValidator(
                [
                    "-",
                    "Simulated_Universe_World_3",
                    "Simulated_Universe_World_4",
                    "Simulated_Universe_World_5",
                    "Simulated_Universe_World_6",
                    "Simulated_Universe_World_8",
                ]
            ),
        )

        ## Data ------------------------------------------------------------
        ## 上次代理日期
        self.Data_LastProxyDate = ConfigItem(
            "Data", "LastProxyDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        ## 代理次数
        self.Data_ProxyTimes = ConfigItem(
            "Data", "ProxyTimes", 0, RangeValidator(0, 9999)
        )

        ## Notify ----------------------------------------------------------
        ## 是否启用通知
        self.Notify_Enabled = ConfigItem("Notify", "Enabled", False, BoolValidator())
        ## 是否发送统计信息
        self.Notify_IfSendStatistic = ConfigItem(
            "Notify", "IfSendStatistic", False, BoolValidator()
        )
        ## 是否发送邮件
        self.Notify_IfSendMail = ConfigItem(
            "Notify", "IfSendMail", False, BoolValidator()
        )
        ## 收件地址
        self.Notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
        ## 是否启用 Server 酱
        self.Notify_IfServerChan = ConfigItem(
            "Notify", "IfServerChan", False, BoolValidator()
        )
        ## Server 酱密钥
        self.Notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
        ## 自定义 Webhook 列表
        self.Notify_CustomWebhooks = MultipleConfig([Webhook])

        super().__init__()

    def getTags(self) -> str:
        """生成用户标签列表，返回JSON字符串格式的TagItem列表"""
        tags = []

        # 日常代理标签（使用东4区时间）
        tags.append(_tag_proxy(self))

        # 剩余天数标签
        tags.append(_tag_remained_days(self))

        # 关卡信息标签
        tags.append(
            {
                "text": f"关卡：{STARRAIL_STAGE_BOOK.get(self.get('Stage', self.get('Stage', 'Channel')), '未知关卡')}",
                "color": "blue",
            }
        )
        tags.append(
            {
                "text": f"周本：{STARRAIL_STAGE_BOOK.get(self.get('Stage', 'EchoOfWar'), '未知关卡')}",
                "color": "blue",
            }
        )
        tags.append(
            {
                "text": f"模拟宇宙：{STARRAIL_STAGE_BOOK.get(self.get('Stage', 'SimulatedUniverseWorld'), '未知关卡')}",
                "color": "blue",
            }
        )

        # 备注标签
        tags.append(_tag_notes(self))

        return json.dumps(tags, ensure_ascii=False)


class SrcConfig(ConfigBase):
    """SRC配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## SRC 脚本名称
        self.Info_Name = ConfigItem("Info", "Name", "新 SRC 脚本")
        ## SRC 路径
        self.Info_Path = ConfigItem("Info", "Path", "", FolderValidator())

        ## Emulator --------------------------------------------------------
        ## 模拟器 ID
        self.Emulator_Id = ConfigItem(
            "Emulator",
            "Id",
            "-",
            MultipleUIDValidator("-", self.related_config, "EmulatorConfig"),
        )
        ## 模拟器索引
        self.Emulator_Index = ConfigItem("Emulator", "Index", "-")

        ## Run -------------------------------------------------------------
        ## 任务切换方式
        self.Run_TaskTransitionMethod = ConfigItem(
            "Run",
            "TaskTransitionMethod",
            "ExitGame",
            OptionsValidator(["ExitGame", "ExitEmulator"]),
        )
        ## 代理次数限制
        self.Run_ProxyTimesLimit = ConfigItem(
            "Run", "ProxyTimesLimit", 0, RangeValidator(0, 9999)
        )
        ## 运行次数限制
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 3, RangeValidator(1, 9999)
        )
        ## 运行时间限制（分钟）
        self.Run_RunTimeLimit = ConfigItem(
            "Run", "RunTimeLimit", 10, RangeValidator(1, 9999)
        )

        self.UserData = MultipleConfig([SrcUserConfig])

        super().__init__()


class HSRUserConfig(ConfigBase):
    """HSR用户配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 用户名称
        self.Info_Name = ConfigItem("Info", "Name", "新用户", UserNameValidator())
        ## 是否启用
        self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
        ## 用户 ID（账号）
        self.Info_Id = ConfigItem("Info", "Id", "", EncryptValidator())
        ## 密码
        self.Info_Password = ConfigItem("Info", "Password", "", EncryptValidator())
        ## 游戏服务器
        self.Info_Server = ConfigItem(
            "Info",
            "Server",
            "CN-Official",
            OptionsValidator(["CN-Official"]),
        )
        ## 剩余天数
        self.Info_RemainedDay = ConfigItem(
            "Info", "RemainedDay", -1, RangeValidator(-1, 9999)
        )
        ## 任务前执行脚本
        self.Info_IfScriptBeforeTask = ConfigItem(
            "Info", "IfScriptBeforeTask", False, BoolValidator()
        )
        self.Info_ScriptBeforeTask = ConfigItem(
            "Info", "ScriptBeforeTask", "", FileValidator()
        )
        ## 任务后执行脚本
        self.Info_IfScriptAfterTask = ConfigItem(
            "Info", "IfScriptAfterTask", False, BoolValidator()
        )
        self.Info_ScriptAfterTask = ConfigItem(
            "Info", "ScriptAfterTask", "", FileValidator()
        )
        ## 备注
        self.Info_Notes = ConfigItem("Info", "Notes", "无")
        ## 用户标签信息（虚拟字段，供前端显示）
        self.Info_Tag = ConfigItem(
            "Info", "Tag", "[ ]", VirtualConfigValidator(self.getTags)
        )

        ## Data ------------------------------------------------------------
        ## 上次代理日期
        self.Data_LastProxyDate = ConfigItem(
            "Data", "LastProxyDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        ## 代理次数
        self.Data_ProxyTimes = ConfigItem(
            "Data", "ProxyTimes", 0, RangeValidator(0, 9999)
        )
        ## 本周是否已完成历战余响
        self.Data_EchoOfWarCompletedThisWeek = ConfigItem(
            "Data", "EchoOfWarCompletedThisWeek", False, BoolValidator()
        )
        ## 历战余响上次重置 ISO 周（形如 "2025-W23"）
        self.Data_EchoOfWarLastResetWeek = ConfigItem(
            "Data", "EchoOfWarLastResetWeek", "2000-W01"
        )
        ## 历战余响最近一次完成日期
        self.Data_EchoOfWarLastCompletionDate = ConfigItem(
            "Data",
            "EchoOfWarLastCompletionDate",
            "2000-01-01",
            DateTimeValidator("%Y-%m-%d"),
        )
        ## 周常（差分宇宙/货币战争）最近一次完成日期
        self.Data_WeeklyLastCompletionDate = ConfigItem(
            "Data",
            "WeeklyLastCompletionDate",
            "2000-01-01",
            DateTimeValidator("%Y-%m-%d"),
        )
        ## 本周是否已完成周常（仅依据 Data 字段判断）
        self.Data_WeeklyCompletedThisWeek = ConfigItem(
            "Data", "WeeklyCompletedThisWeek", False, BoolValidator()
        )
        ## 周常上次重置 ISO 周（形如 "2025-W23"）
        self.Data_WeeklyLastResetWeek = ConfigItem(
            "Data", "WeeklyLastResetWeek", "2000-W01"
        )
        ## TaskSwitch ------------------------------------------------------
        ## 模块执行开关
        self.TaskSwitch_Daily = ConfigItem("TaskSwitch", "Daily", True, BoolValidator())
        self.TaskSwitch_ReceiveRewards = ConfigItem(
            "TaskSwitch", "ReceiveRewards", True, BoolValidator()
        )
        self.TaskSwitch_DivergentUniverse = ConfigItem(
            "TaskSwitch", "DivergentUniverse", False, BoolValidator()
        )
        self.TaskSwitch_CurrencyWars = ConfigItem(
            "TaskSwitch", "CurrencyWars", False, BoolValidator()
        )
        ## Stage -----------------------------------------------------------
        ## 关卡通道
        self.Stage_Channel = ConfigItem(
            "Stage",
            "Channel",
            "CalyxGolden",
            OptionsValidator(["CalyxGolden", "CalyxCrimson", "Relic", "Ornament"]),
        )
        ## 主刷关卡的脚本原生字段 JSON（SRA: id+level；M7A: instance_type+name）
        self.Stage_ScriptStage = ConfigItem(
            "Stage", "ScriptStage", "{ }", JSONValidator()
        )
        ## 历战余响的脚本原生字段 JSON
        self.Stage_ScriptEchoOfWar = ConfigItem(
            "Stage", "ScriptEchoOfWar", "{ }", JSONValidator()
        )

        ## TaskOpt ---------------------------------------------------------
        ## 历战余响开始刷的星期（周一 ~ 周日）
        self.TaskOpt_EchoOfWarWeekday = ConfigItem(
            "TaskOpt",
            "EchoOfWarWeekday",
            "Monday",
            OptionsValidator(
                [
                    "Monday",
                    "Tuesday",
                    "Wednesday",
                    "Thursday",
                    "Friday",
                    "Saturday",
                    "Sunday",
                ]
            ),
        )

        ## Notify ----------------------------------------------------------
        ## 是否启用通知
        self.Notify_Enabled = ConfigItem("Notify", "Enabled", False, BoolValidator())
        ## 是否发送统计信息
        self.Notify_IfSendStatistic = ConfigItem(
            "Notify", "IfSendStatistic", False, BoolValidator()
        )
        ## 是否发送邮件
        self.Notify_IfSendMail = ConfigItem(
            "Notify", "IfSendMail", False, BoolValidator()
        )
        ## 收件地址
        self.Notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
        ## 是否启用 Server 酱
        self.Notify_IfServerChan = ConfigItem(
            "Notify", "IfServerChan", False, BoolValidator()
        )
        ## Server 酱密钥
        self.Notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
        ## 自定义 Webhook 列表
        self.Notify_CustomWebhooks = MultipleConfig([Webhook])

        ## Control / Managed / Direct ------------------------------------
        ## 兼容插件版的托管/直连配置形状。内置 HSRManager 按模式读取
        ## 这些字段；普通用户 API 只返回非敏感元数据。
        self.Control_Mode = ConfigItem(
            "Control", "Mode", "managed", OptionsValidator(["managed", "direct"])
        )
        self.Control_SRA = ConfigItem("Control", "SRA", False, BoolValidator())
        self.Control_M7A = ConfigItem("Control", "M7A", False, BoolValidator())
        self.Managed_TaskMapping = ConfigItem(
            "Managed", "TaskMapping", "{ }", JSONValidator()
        )
        self.Managed_Options = ConfigItem("Managed", "Options", "{ }", JSONValidator())
        self.Direct_SRAConfig = ConfigItem(
            "Direct", "SRAConfig", "", EncryptValidator()
        )
        self.Direct_M7AConfig = ConfigItem(
            "Direct", "M7AConfig", "", EncryptValidator()
        )
        self.Direct_SRAImportedAt = ConfigItem("Direct", "SRAImportedAt", "")
        self.Direct_M7AImportedAt = ConfigItem("Direct", "M7AImportedAt", "")
        self.Direct_SRASource = ConfigItem("Direct", "SRASource", "")
        self.Direct_M7ASource = ConfigItem("Direct", "M7ASource", "")

        ## 兑换码状态指纹（仅状态信息，不保存兑换码明文）
        self.Data_SRARedeemCodeFingerprint = ConfigItem(
            "Data", "SRARedeemCodeFingerprint", ""
        )
        self.Data_M7ARedeemCodeFingerprint = ConfigItem(
            "Data", "M7ARedeemCodeFingerprint", ""
        )

        super().__init__()

    def getTags(self) -> str:
        """生成 HSR 用户标签列表，返回JSON字符串格式的TagItem列表。"""
        tags: list[dict] = []

        server = self.get("Info", "Server")
        server_label_map = {"CN-Official": "官服"}
        server_label = server_label_map.get(server, server or "未知")
        tags.append({"text": f"服务器：{server_label}", "color": "blue"})

        # 日常代理标签（使用东4区时间）
        tags.append(_tag_proxy(self))

        # 剩余天数标签
        tags.append(_tag_remained_days(self))

        # 与 HSRAutoProxyTask._period_markers 同口径：星铁在服务器时间周一 04:00
        # 重置，UTC+4 的零点正是这一刻。两边必须一致，否则用户列表上的「本周已完成」
        # 标签会和实际跑不跑这个任务对不上。
        now = datetime.now(tz=UTC4)
        iso_year, iso_week, _ = now.isocalendar()
        current_week = f"{iso_year:04d}-W{iso_week:02d}"

        eow_done = (
            bool(self.get("Data", "EchoOfWarCompletedThisWeek"))
            and self.get("Data", "EchoOfWarLastResetWeek") == current_week
        )
        tags.append(
            {
                "text": "历战余响：已完成" if eow_done else "历战余响：未完成",
                "color": "green" if eow_done else "orange",
            }
        )

        weekly_done = (
            bool(self.get("Data", "WeeklyCompletedThisWeek"))
            and self.get("Data", "WeeklyLastResetWeek") == current_week
        )
        du_on = bool(self.get("TaskSwitch", "DivergentUniverse"))
        cw_on = bool(self.get("TaskSwitch", "CurrencyWars"))
        if weekly_done:
            if du_on:
                weekly_text, weekly_color = "差分宇宙 已完成", "green"
            elif cw_on:
                weekly_text, weekly_color = "货币战争 已完成", "green"
            else:
                weekly_text, weekly_color = "周常 已完成", "green"
        else:
            weekly_text, weekly_color = "周常：未完成", "orange"
        tags.append({"text": weekly_text, "color": weekly_color})

        # 备注标签
        tags.append(_tag_notes(self))

        return json.dumps(tags, ensure_ascii=False)


class HSRConfig(ConfigBase):
    """HSR配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## HSR 脚本名称
        self.Info_Name = ConfigItem("Info", "Name", "新 HSR 脚本")
        ## M7A 路径
        self.Info_M7APath = ConfigItem("Info", "M7APath", "", FolderValidator())
        ## SRA 路径
        self.Info_SRAPath = ConfigItem("Info", "SRAPath", "", FolderValidator())
        ## SRA 配置档案（%APPDATA%\SRA\configs 下的文件名，不含扩展名；空串表示自动）
        self.Info_SRAProfile = ConfigItem(
            "Info", "SRAProfile", "", SRAProfileValidator()
        )

        ## Game ------------------------------------------------------------
        ## 是否由 MAS 管理游戏启停、进程监测和窗口操作
        self.Game_Enabled = ConfigItem("Game", "Enabled", True, BoolValidator())
        ## 游戏路径
        self.Game_Path = ConfigItem("Game", "Path", "", FileValidator())
        ## 等待时间（秒）
        self.Game_WaitTime = ConfigItem("Game", "WaitTime", 60, RangeValidator(0, 9999))
        ## 启动游戏时临时覆盖 1920×1080 注册表分辨率
        self.Game_ForceResolution1920x1080 = ConfigItem(
            "Game", "ForceResolution1920x1080", False, BoolValidator()
        )
        ## 仅在原生兑换码内容变化时执行兑换
        self.Game_RedeemCodesOnlyWhenChanged = ConfigItem(
            "Game", "RedeemCodesOnlyWhenChanged", True, BoolValidator()
        )

        ## Run -------------------------------------------------------------
        ## 失败任务最大尝试次数
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 3, RangeValidator(1, 9999)
        )
        ## 日常任务超时限制（分钟）
        self.Run_DailyTimeLimit = ConfigItem(
            "Run", "DailyTimeLimit", 20, RangeValidator(1, 9999)
        )
        ## 周常任务超时限制（分钟）
        self.Run_WeeklyTimeLimit = ConfigItem(
            "Run", "WeeklyTimeLimit", 60, RangeValidator(1, 9999)
        )
        ## 低性能兼容模式（仅三月七差分宇宙使用，映射到 weekly_divergent_stable_mode）
        self.Run_LowPerformanceMode = ConfigItem(
            "Run", "LowPerformanceMode", False, BoolValidator()
        )
        ## Update ----------------------------------------------------------
        ## 外部脚本（M7A / SRA）的自动更新。默认关闭：这两个是用户自己安装、
        ## 自带更新器的第三方工具，未经开启就改写它们的目录属于越界；停留在
        ## 某个旧版也是真实需求。
        ## 只有 AfterRun 一档，没有 BeforeRun：更新的收益本来就落在下一次运行
        ## 上，没有理由让当前这轮先等一个 170–750MB 的下载。想立刻更新走配置
        ## 页的手动按钮。留成枚举而非布尔，是为了日后要加档时不必做
        ## bool→enum 迁移（MaaFW 正为此背着一个废弃字段）。
        ## 选项顺序有意义：OptionsValidator.correct() 回退的是 **options[0]**，
        ## 不是这里的默认值，Off 必须排在最前。
        self.Update_AutoUpdateMode = ConfigItem(
            "Update", "AutoUpdateMode", "Off", OptionsValidator(["Off", "AfterRun"])
        )
        ## 更新渠道，两个引擎共用。Mirror 酱还支持 alpha，**故意不开放**——
        ## 那是项目方的内部验证档。这两个值必须与前端选项和 schema 的 Literal
        ## 一致，三处任一多给一档，用户选了就会 422 或被静默纠回默认值。
        self.Update_Channel = ConfigItem(
            "Update", "Channel", "stable", OptionsValidator(["stable", "beta"])
        )
        ## 下载源按引擎拆开：两者可用的源本就不同，共用一项给不出不同默认值。
        ## 版本检查恒走 Mirror 酱的免 CDK 接口（自建站没有 latest 接口，只能用
        ## tag 拼 URL，靠这条口径补上）；这里只决定字节从哪来，且**不做自动
        ## 分流**——选了 Mirror 酱而 CDK 不可用时报明原因并跳过，不悄悄换成
        ## GitHub，用户得知道自己在从哪下载。
        ## M7A 没有上 AUTO-MAS 自建站，所以只有两个源，默认 GitHub。
        self.Update_M7ASource = ConfigItem(
            "Update", "M7ASource", "GitHub", OptionsValidator(["GitHub", "MirrorChyan"])
        )
        ## SRA 默认自建站：免 CDK、不限流、sha256 与 GitHub 逐字节一致，且
        ## SRA 上游 CI 会主动往这里推送，其自带更新器也有 AUTO-MAS 这一档。
        self.Update_SRASource = ConfigItem(
            "Update",
            "SRASource",
            "AutoSite",
            OptionsValidator(["AutoSite", "GitHub", "MirrorChyan"]),
        )
        ## Mirror 酱 CDK，由用户自己填，**不做全局兜底**：全局那个服务的是
        ## AUTO-MAS 自身的更新，和外部脚本不是一回事，串在一起只会让人猜自己
        ## 在用哪个。选 Mirror 酱作为下载源时这一项必填。
        self.Update_MirrorChyanCDK = ConfigItem(
            "Update", "MirrorChyanCDK", "", EncryptValidator()
        )

        ## TaskMapping -----------------------------------------------------
        ## 模块脚本分配（延迟导入以避免循环依赖）
        from app.task.HSR.task_mapping import HSR_TASK_MODULES as _HSR_TASK_MODULES

        for module in _HSR_TASK_MODULES:
            self.__setattr__(
                f"TaskMapping_{module.key}",
                ConfigItem(
                    "TaskMapping",
                    module.key,
                    module.default_script,
                    OptionsValidator(list(module.supported_scripts)),
                ),
            )

        self.UserData = MultipleConfig([HSRUserConfig])

        super().__init__()


class M9AUserConfig(ConfigBase):
    """M9A用户配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 用户名称
        self.Info_Name = ConfigItem("Info", "Name", "新用户", UserNameValidator())
        ## 是否启用
        self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
        ## 剩余天数
        self.Info_RemainedDay = ConfigItem(
            "Info", "RemainedDay", -1, RangeValidator(-1, 9999)
        )
        ## 任务前执行脚本
        self.Info_IfScriptBeforeTask = ConfigItem(
            "Info", "IfScriptBeforeTask", False, BoolValidator()
        )
        self.Info_ScriptBeforeTask = ConfigItem(
            "Info", "ScriptBeforeTask", "", FileValidator()
        )
        ## 任务后执行脚本
        self.Info_IfScriptAfterTask = ConfigItem(
            "Info", "IfScriptAfterTask", False, BoolValidator()
        )
        self.Info_ScriptAfterTask = ConfigItem(
            "Info", "ScriptAfterTask", "", FileValidator()
        )
        ## 备注
        self.Info_Notes = ConfigItem("Info", "Notes", "无")
        ## 用户标签信息
        self.Info_Tag = ConfigItem(
            "Info", "Tag", "[ ]", VirtualConfigValidator(self.getTags)
        )
        ## 服务器资源
        self.Info_Resource = ConfigItem("Info", "Resource", "官服")
        ## 账号信息（用于切换账号）
        self.Info_Account = ConfigItem("Info", "Account", "")

        ## Task -------------------------------------------------------------
        ## 可用任务列表（从 M9A 配置文件读取）
        self.Task_AvailableTasks = ConfigItem(
            "Task", "AvailableTasks", "[]", JSONValidator(list)
        )
        ## 运行任务队列 (用户在可用任务列表中选择)
        self.Task_Queue = ConfigItem("Task", "Queue", "[]", JSONValidator(list))

        ## Data ------------------------------------------------------------
        ## 上次代理日期
        self.Data_LastProxyDate = ConfigItem(
            "Data", "LastProxyDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        ## 上次完成每日心相日期
        self.Data_LastPsychubeDate = ConfigItem(
            "Data", "LastPsychubeDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        ## 上次完成自动深眠月份
        self.Data_LastLimboMonth = ConfigItem(
            "Data", "LastLimboMonth", "2000-01", DateTimeValidator("%Y-%m")
        )
        ## 上次完成自动醒梦月份
        self.Data_LastLucidscapeMonth = ConfigItem(
            "Data", "LastLucidscapeMonth", "2000-01", DateTimeValidator("%Y-%m")
        )
        ## 代理次数
        self.Data_ProxyTimes = ConfigItem(
            "Data", "ProxyTimes", 0, RangeValidator(0, 9999)
        )

        ## Notify ----------------------------------------------------------
        ## 是否启用通知
        self.Notify_Enabled = ConfigItem("Notify", "Enabled", False, BoolValidator())
        ## 是否发送统计信息
        self.Notify_IfSendStatistic = ConfigItem(
            "Notify", "IfSendStatistic", False, BoolValidator()
        )
        ## 是否发送邮件
        self.Notify_IfSendMail = ConfigItem(
            "Notify", "IfSendMail", False, BoolValidator()
        )
        ## 收件地址
        self.Notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
        ## 是否启用 Server 酱
        self.Notify_IfServerChan = ConfigItem(
            "Notify", "IfServerChan", False, BoolValidator()
        )
        ## Server 酱密钥
        self.Notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
        ## 自定义 Webhook 列表
        self.Notify_CustomWebhooks = MultipleConfig([Webhook])

        super().__init__()

    def getTags(self) -> str:
        """生成用户标签列表，返回JSON字符串格式的TagItem列表"""
        tags = []

        # 日常代理标签（使用东4区时间）
        tags.append(_tag_proxy(self))

        # 剩余天数标签
        tags.append(_tag_remained_days(self))
        # 备注标签
        tags.append(_tag_notes(self))

        return json.dumps(tags, ensure_ascii=False)


class M9AConfig(ConfigBase):
    """M9A配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## M9A 脚本名称
        self.Info_Name = ConfigItem("Info", "Name", "新 M9A 脚本")
        ## M9A 路径
        self.Info_Path = ConfigItem("Info", "Path", "", FolderValidator())

        ## Emulator --------------------------------------------------------
        ## 模拟器 ID
        self.Emulator_Id = ConfigItem(
            "Emulator",
            "Id",
            "-",
            MultipleUIDValidator("-", self.related_config, "EmulatorConfig"),
        )
        ## 模拟器索引
        self.Emulator_Index = ConfigItem("Emulator", "Index", "-")

        ## Run -------------------------------------------------------------
        ## 代理次数限制
        self.Run_ProxyTimesLimit = ConfigItem(
            "Run", "ProxyTimesLimit", 0, RangeValidator(0, 9999)
        )
        ## 运行次数限制
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 3, RangeValidator(1, 9999)
        )
        ## 运行时间限制（分钟）
        self.Run_RunTimeLimit = ConfigItem(
            "Run", "RunTimeLimit", 10, RangeValidator(1, 9999)
        )
        ## 是否在队列结束后自动更新
        self.Run_IfAutoUpdateAfterQueue = ConfigItem(
            "Run", "IfAutoUpdateAfterQueue", False, BoolValidator()
        )
        ## 每日心相每日只执行一次
        self.Run_IfPsychubeDailyOnce = ConfigItem(
            "Run", "IfPsychubeDailyOnce", False, BoolValidator()
        )
        ## 深眠浅梦每月只执行一次
        self.Run_IfSleepDreamMonthlyOnce = ConfigItem(
            "Run", "IfSleepDreamMonthlyOnce", False, BoolValidator()
        )

        self.UserData = MultipleConfig([M9AUserConfig])

        super().__init__()


class MaaFWUserConfig(ConfigBase):
    """MaaFW 用户配置"""

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 用户名称
        self.Info_Name = ConfigItem("Info", "Name", "新用户", UserNameValidator())
        ## 是否启用
        self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
        ## 剩余天数
        self.Info_RemainedDay = ConfigItem(
            "Info", "RemainedDay", -1, RangeValidator(-1, 9999)
        )
        ## 是否在任务前执行脚本
        self.Info_IfScriptBeforeTask = ConfigItem(
            "Info", "IfScriptBeforeTask", False, BoolValidator()
        )
        ## 任务前脚本路径
        self.Info_ScriptBeforeTask = ConfigItem(
            "Info", "ScriptBeforeTask", "", FileValidator()
        )
        ## 是否在任务后执行脚本
        self.Info_IfScriptAfterTask = ConfigItem(
            "Info", "IfScriptAfterTask", False, BoolValidator()
        )
        ## 任务后脚本路径
        self.Info_ScriptAfterTask = ConfigItem(
            "Info", "ScriptAfterTask", "", FileValidator()
        )
        ## 备注
        self.Info_Notes = ConfigItem("Info", "Notes", "无")
        ## 用户标签信息
        self.Info_Tag = ConfigItem(
            "Info", "Tag", "[ ]", VirtualConfigValidator(self.getTags)
        )
        ## 账号信息，仅用于 AUTO-MAS 记录，不自动传入 MaaFW 任务
        self.Info_Account = ConfigItem("Info", "Account", "")
        ## 密码信息，仅用于 AUTO-MAS 记录，不自动传入 MaaFW 任务
        self.Info_Password = ConfigItem("Info", "Password", "", EncryptValidator())
        ## MaaFW controller 名称，留空时按 interface 和设备配置自动选择
        self.Info_Controller = ConfigItem("Info", "Controller", "")
        ## MaaFW resource 名称，留空时选择匹配 controller 的第一个 resource
        self.Info_Resource = ConfigItem("Info", "Resource", "")

        ## Task ------------------------------------------------------------
        ## 当前选中的 interface preset 名称，留空时使用 interface 默认逻辑
        self.Task_SelectedPreset = ConfigItem("Task", "SelectedPreset", "")
        ## 当前用户的任务快照，结构为 taskOrder/taskChecked/taskOptions；
        ## 三者的键都是任务实例 id，同一个任务可以重复入队（见 MaaFWTaskSnapshot）
        self.Task_TaskSnapshot = ConfigItem(
            "Task", "TaskSnapshot", "{ }", JSONValidator(dict)
        )

        ## Device ----------------------------------------------------------
        ## 当前用户覆盖 ADB 地址，留空时使用脚本级模拟器配置
        self.Device_AdbAddress = ConfigItem("Device", "AdbAddress", "")
        ## Win32 / Gamepad 窗口句柄，0 表示未指定
        self.Device_HWnd = ConfigItem(
            "Device", "HWnd", 0, RangeValidator(0, 999999999999)
        )
        ## PlayCover 地址
        self.Device_PlayCoverAddress = ConfigItem("Device", "PlayCoverAddress", "")
        ## PlayCover UUID
        self.Device_PlayCoverUuid = ConfigItem("Device", "PlayCoverUuid", "")

        ## Data ------------------------------------------------------------
        ## 上次代理日期
        self.Data_LastProxyDate = ConfigItem(
            "Data", "LastProxyDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        ## 代理次数
        self.Data_ProxyTimes = ConfigItem(
            "Data", "ProxyTimes", 0, RangeValidator(0, 9999)
        )
        ## 是否通过检查
        self.Data_IfPassCheck = ConfigItem("Data", "IfPassCheck", True, BoolValidator())
        ## 上次运行状态
        self.Data_LastProxyStatus = ConfigItem("Data", "LastProxyStatus", "未知")
        ## MaaFW 周期任务完成记录，结构为 weekly/monthly -> task name -> period key
        self.Data_PeriodTaskRecords = ConfigItem(
            "Data", "PeriodTaskRecords", "{ }", JSONValidator(dict)
        )

        ## Notify ----------------------------------------------------------
        ## 是否启用通知
        self.Notify_Enabled = ConfigItem("Notify", "Enabled", False, BoolValidator())
        ## 是否发送统计信息
        self.Notify_IfSendStatistic = ConfigItem(
            "Notify", "IfSendStatistic", False, BoolValidator()
        )
        ## 是否发送邮件
        self.Notify_IfSendMail = ConfigItem(
            "Notify", "IfSendMail", False, BoolValidator()
        )
        ## 收件地址
        self.Notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
        ## 是否启用 Server 酱
        self.Notify_IfServerChan = ConfigItem(
            "Notify", "IfServerChan", False, BoolValidator()
        )
        ## Server 酱密钥
        self.Notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
        ## 自定义 Webhook 列表
        self.Notify_CustomWebhooks = MultipleConfig([Webhook])

        super().__init__()

    def getTags(self) -> str:
        """生成 MaaFW 用户标签列表"""
        tags = []

        last_status = self.get("Data", "LastProxyStatus")
        tags.append({"text": f"上次：{last_status}", "color": "green"})

        if not self.get("Data", "IfPassCheck"):
            tags.append({"text": "人工排查未通过", "color": "red"})

        # 任务代理标签（使用东4区时间）
        tags.append(_tag_proxy(self, "任务"))

        # 剩余天数标签
        tags.append(_tag_remained_days(self))

        # 备注标签
        tags.append(_tag_notes(self))

        return json.dumps(tags, ensure_ascii=False)


def _migrate_maafw_auto_update_mode(data: dict) -> dict:
    """兼容旧版 Update.IfAutoUpdate 布尔开关 → 三态 Update.AutoUpdateMode

    旧值 False（关闭）迁移为 ``Off``，保留用户之前的关闭选择；旧值 True 交由
    新默认 ``BeforeRun`` 生效。只在新项尚未显式写入时迁移，且不动旧键：
    ``IfAutoUpdate`` 的 ConfigItem 还保留一个版本兼容旧配置文件。
    """
    normalized_data = deepcopy(data) if isinstance(data, dict) else {}
    update = normalized_data.get("Update")
    if (
        isinstance(update, dict)
        and update.get("IfAutoUpdate") is False
        and "AutoUpdateMode" not in update
    ):
        update["AutoUpdateMode"] = "Off"
    return normalized_data


class MaaFWConfig(ConfigBase):
    """MaaFW 项目配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## MaaFW 脚本名称
        self.Info_Name = ConfigItem("Info", "Name", "新 MFW 脚本")
        ## 项目标签，可用于区分同一 ProjectInterface 的不同实例
        self.Info_ProjectLabel = ConfigItem("Info", "ProjectLabel", "")
        ## MaaFW 项目根目录，应包含 interface.json
        self.Info_Path = ConfigItem("Info", "Path", "", FolderValidator())
        ## MaaFW controller 名称，留空时按 interface 和设备配置自动选择
        self.Info_Controller = ConfigItem("Info", "Controller", "")
        ## MaaFW resource 名称，留空时选择匹配 controller 的第一个 resource
        self.Info_Resource = ConfigItem("Info", "Resource", "")

        ## Emulator --------------------------------------------------------
        ## 模拟器 ID，ADB controller 留空地址时使用
        self.Emulator_Id = ConfigItem(
            "Emulator",
            "Id",
            "-",
            MultipleUIDValidator("-", self.related_config, "EmulatorConfig"),
        )
        ## 模拟器索引
        self.Emulator_Index = ConfigItem("Emulator", "Index", "-")

        ## Device ----------------------------------------------------------
        ## ADB 路径，留空时从 MAS 模拟器配置或 MaaFW Toolkit 推导
        self.Device_AdbPath = ConfigItem("Device", "AdbPath", "", FileValidator())
        ## ADB 地址，留空时启动脚本级模拟器获取
        self.Device_AdbAddress = ConfigItem("Device", "AdbAddress", "")
        ## ADB 截图方法，默认优先模拟器增强，失败后回退到 ADB 截图
        ## 仅第二层（MAS 进程内 runner）适用：第一层由外壳自己创建控制器，运行期按
        ## M9A 专项的既验证取值写死（ScreencapMethods=64），本项不参与外部运行，
        ## 接线前不要暴露到前端，否则用户改了不会生效也没有提示
        self.Device_AdbScreencapMethods = ConfigItem(
            "Device", "AdbScreencapMethods", -57, RangeValidator(-999, 999999999999)
        )
        ## ADB 输入方法，默认优先模拟器增强，失败后回退到 MaaTouch / MiniTouch / ADB
        ## 同上，仅第二层适用；第一层运行期写死 InputMethods=18446744073709551607
        self.Device_AdbInputMethods = ConfigItem(
            "Device", "AdbInputMethods", -1, RangeValidator(-999, 999999999999)
        )
        ## Win32 / Gamepad 窗口句柄，0 表示未指定
        self.Device_HWnd = ConfigItem(
            "Device", "HWnd", 0, RangeValidator(0, 999999999999)
        )
        ## Win32 截图方法，0 表示使用 interface 声明或 MaaFW 默认值
        self.Device_Win32ScreencapMethod = ConfigItem(
            "Device", "Win32ScreencapMethod", 0, RangeValidator(0, 999999999999)
        )
        ## Win32 鼠标方法，0 表示使用 interface 声明或 MaaFW 默认值
        self.Device_Win32MouseMethod = ConfigItem(
            "Device", "Win32MouseMethod", 0, RangeValidator(0, 999999999999)
        )
        ## Win32 键盘方法，0 表示使用 interface 声明或 MaaFW 默认值
        self.Device_Win32KeyboardMethod = ConfigItem(
            "Device", "Win32KeyboardMethod", 0, RangeValidator(0, 999999999999)
        )
        ## Gamepad 类型，默认 Xbox360
        self.Device_GamepadType = ConfigItem(
            "Device", "GamepadType", 0, RangeValidator(0, 999999999999)
        )
        ## PlayCover 地址
        self.Device_PlayCoverAddress = ConfigItem("Device", "PlayCoverAddress", "")
        ## PlayCover UUID
        self.Device_PlayCoverUuid = ConfigItem("Device", "PlayCoverUuid", "")

        ## Game ------------------------------------------------------------
        ## 游戏生命周期模式
        self.Game_LaunchMode = ConfigItem(
            "Game",
            "LaunchMode",
            "AttachOnly",
            # 只保留两种：我自己启动游戏（AttachOnly）/ 让 MAS 启动并按设置关闭
            # （DirectExe）。LauncherExe 与 URL 已下线，旧配置由校验器纠正回默认值。
            OptionsValidator(["AttachOnly", "DirectExe"]),
        )
        ## DirectExe 模式下 MAS 启动的游戏 exe
        self.Game_LaunchPath = ConfigItem("Game", "LaunchPath", "", FileValidator())
        ## 安卓游戏包名，Adb controller 用：启动模拟器时顺带把游戏拉起来。
        ## 留空表示从项目的 pipeline 里自动识别（见 embedded/game_package.py）；
        ## 自动识别是启发式的，填了这里就以这里为准。识别不出且没填则不启动游戏。
        self.Game_PackageName = ConfigItem("Game", "PackageName", "")
        ## 游戏启动参数
        self.Game_Arguments = ConfigItem("Game", "Arguments", "", ArgumentValidator())
        ## 游戏启动后等待窗口就绪的时间（秒）
        self.Game_WaitTime = ConfigItem("Game", "WaitTime", 60, RangeValidator(0, 9999))
        ## 任务结束后是否关闭由 MAS 启动的游戏
        self.Game_CloseOnFinish = ConfigItem(
            "Game", "CloseOnFinish", True, BoolValidator()
        )

        ## Update ----------------------------------------------------------
        ## 项目自动更新时机：Off 不更新 / BeforeRun 运行前 / AfterRun 全部用户跑完后。
        ## 由 embedded_manager 在用户任务之外执行，耗时不计入 Run.RunTimeLimit。
        self.Update_AutoUpdateMode = ConfigItem(
            "Update",
            "AutoUpdateMode",
            "BeforeRun",
            OptionsValidator(["Off", "BeforeRun", "AfterRun"]),
        )
        ## [已废弃] 旧布尔开关，只在 load() 里迁移为 AutoUpdateMode（False → Off），
        ## 运行流程不再读取；保留一个版本兼容旧配置文件后删除。
        self.Update_IfAutoUpdate = ConfigItem(
            "Update", "IfAutoUpdate", True, BoolValidator()
        )
        ## 更新包的下载源，由用户显式选择——**不做自动分流**。
        ## 版本检查始终走 Mirror 酱（无 CDK 也能查），但下载去哪由这一项决定：
        ## 选 Mirror 酱就必须自己填 CDK，CDK 不可用时明确报错，不悄悄换成
        ## GitHub——用户得知道自己在从哪下载，出问题才查得动。
        ## 默认 GitHub：零配置即可用，与全局 Update.Source 的默认值一致。
        # 选项顺序有意义：OptionsValidator.correct() 回退的是 **options[0]**，
        # 不是这里的默认值。旧配置里 Source 是空串（旧默认），加载时会被
        # correct 成第一项并写回磁盘——GitHub 必须排在前面，否则所有既有
        # 脚本会被静默改成 Mirror 酱，而它们并没有 CDK，每次运行都更新失败。
        self.Update_Source = ConfigItem(
            "Update", "Source", "GitHub", OptionsValidator(["GitHub", "MirrorChyan"])
        )
        ## 更新渠道只有稳定版与测试版，默认稳定版，要测试版由用户手动切。
        ## 不给「跟随全局」：全局那个 Update.Channel 是 MAS 自身的发布通道，
        ## 和脚本本体的版本档位是两回事，串在一起只会让人猜。
        ## Mirror 酱还支持 channel=alpha，**故意不开放**——那是项目方的内部
        ## 验证档，稳定性无保证，而这里更新的是用户日常在跑的脚本本体。
        ## 这两个值必须与前端 updateChannelOptions 和 schema 的 Literal 一致：
        ## 三处任一多给一档，用户选了就会 422 或被静默纠回默认值。
        ## 旧配置里的空串现在是非法值，会被 correct() 回退成 options[0]，
        ## 即 stable——这里的顺序同样不能随意调换。
        self.Update_Channel = ConfigItem(
            "Update", "Channel", "stable", OptionsValidator(["stable", "beta"])
        )
        ## Mirror 酱 CDK，由用户自己填。**不做全局兜底**：全局那个服务的是
        ## AUTO-MAS 自身的更新，和脚本本体不是一回事，串在一起只会让人猜
        ## 自己在用哪个。选 Mirror 酱作为下载源时这一项必填。
        ## （合并逻辑见 tools/embedded/update_credentials.py）
        self.Update_MirrorChyanCDK = ConfigItem(
            "Update", "MirrorChyanCDK", "", EncryptValidator()
        )
        ## [已废弃] GitHub 仓库/tag/asset 覆盖：仓库与资产名改为从 interface.json
        ## 和目录名自动推导，运行流程不再读取；保留一个版本兼容旧配置文件后删除。
        self.Update_GitHubRepo = ConfigItem("Update", "GitHubRepo", "")
        self.Update_GitHubTag = ConfigItem("Update", "GitHubTag", "")
        self.Update_GitHubAssetPattern = ConfigItem("Update", "GitHubAssetPattern", "")

        ## Managed --------------------------------------------------------
        ## 是否由 Project Store 和 Runtime Pool 托管项目资源
        self.Managed_Enabled = ConfigItem("Managed", "Enabled", False, BoolValidator())
        self.Managed_ProjectId = ConfigItem("Managed", "ProjectId", "")
        self.Managed_StoreId = ConfigItem("Managed", "StoreId", "")
        self.Managed_Version = ConfigItem("Managed", "Version", "")
        self.Managed_RuntimeConstraint = ConfigItem("Managed", "RuntimeConstraint", "")
        self.Managed_ProjectManifest = ConfigItem(
            "Managed", "ProjectManifest", "{ }", JSONValidator(dict)
        )
        self.Managed_CheckoutPath = ConfigItem("Managed", "CheckoutPath", "")
        self.Managed_PendingUpgrade = ConfigItem(
            "Managed", "PendingUpgrade", "{ }", JSONValidator(dict)
        )
        self.Managed_LastOperation = ConfigItem(
            "Managed", "LastOperation", "{ }", JSONValidator(dict)
        )

        ## ManagedRuntime -------------------------------------------------
        self.ManagedRuntime_RuntimeId = ConfigItem("ManagedRuntime", "RuntimeId", "")
        self.ManagedRuntime_PoolId = ConfigItem("ManagedRuntime", "PoolId", "")
        self.ManagedRuntime_PythonExecutable = ConfigItem(
            "ManagedRuntime", "PythonExecutable", ""
        )
        self.ManagedRuntime_VenvPath = ConfigItem("ManagedRuntime", "VenvPath", "")
        self.ManagedRuntime_RuntimeBinding = ConfigItem(
            "ManagedRuntime", "RuntimeBinding", "{ }", JSONValidator(dict)
        )

        ## ManagedRemote --------------------------------------------------
        self.ManagedRemote_Source = ConfigItem(
            "ManagedRemote",
            "Source",
            "MirrorChyan",
            OptionsValidator(["MirrorChyan", "GitHub"]),
        )
        self.ManagedRemote_Channel = ConfigItem(
            "ManagedRemote", "Channel", "stable", OptionsValidator(["stable", "beta"])
        )
        self.ManagedRemote_MirrorChyanRID = ConfigItem(
            "ManagedRemote", "MirrorChyanRID", ""
        )
        self.ManagedRemote_MirrorChyanCDK = ConfigItem(
            "ManagedRemote", "MirrorChyanCDK", "", EncryptValidator()
        )
        self.ManagedRemote_GitHubRepo = ConfigItem("ManagedRemote", "GitHubRepo", "")
        self.ManagedRemote_GitHubTag = ConfigItem("ManagedRemote", "GitHubTag", "")
        self.ManagedRemote_GitHubAssetPattern = ConfigItem(
            "ManagedRemote", "GitHubAssetPattern", r"\.zip$"
        )

        ## Run -------------------------------------------------------------
        ## 运行引擎，决定「谁来跑」：
        ## 代理次数限制
        self.Run_ProxyTimesLimit = ConfigItem(
            "Run", "ProxyTimesLimit", 0, RangeValidator(0, 9999)
        )
        ## 运行次数限制
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 1, RangeValidator(1, 9999)
        )
        ## 单次运行时间限制（分钟）
        self.Run_RunTimeLimit = ConfigItem(
            "Run", "RunTimeLimit", 30, RangeValidator(1, 9999)
        )
        ## 每天正常完成一次后，当天剩余时间跳过的 MaaFW 任务名列表
        self.Run_DailyOnceTasks = ConfigItem(
            "Run", "DailyOnceTasks", "[ ]", JSONValidator(list)
        )
        ## 每周正常完成一次后，本周剩余时间跳过的 MaaFW 任务名列表
        self.Run_WeeklyOnceTasks = ConfigItem(
            "Run", "WeeklyOnceTasks", "[ ]", JSONValidator(list)
        )
        ## 每月正常完成一次后，本月剩余时间跳过的 MaaFW 任务名列表
        self.Run_MonthlyOnceTasks = ConfigItem(
            "Run", "MonthlyOnceTasks", "[ ]", JSONValidator(list)
        )

        ## Selection -------------------------------------------------------
        ## 当前阶段保留：manager.py 仍从 Selection.* 读取运行范围，
        ## 字段迁移到 Info.* / 用户任务配置属于后续 P3 前端回收。
        ## 选中的 controller 列表
        self.Selection_Controller = ConfigItem(
            "Selection", "Controller", "[ ]", JSONValidator(list)
        )
        ## 选中的 resource 列表
        self.Selection_Resource = ConfigItem(
            "Selection", "Resource", "[ ]", JSONValidator(list)
        )
        ## 选中的 task 列表
        self.Selection_Tasks = ConfigItem(
            "Selection", "Tasks", "[ ]", JSONValidator(list)
        )

        self.UserData = MultipleConfig([MaaFWUserConfig])

        super().__init__()

    async def load(self, data: dict) -> bool:
        """加载脚本配置前迁移旧版 Update.IfAutoUpdate 布尔开关。"""
        return await super().load(_migrate_maafw_auto_update_mode(data))


class MaaPlanConfig(ConfigBase):
    """MAA计划表配置"""

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 计划表名称
        self.Info_Name = ConfigItem("Info", "Name", "新 MAA 计划表")
        ## 计划表模式
        self.Info_Mode = ConfigItem(
            "Info", "Mode", "ALL", OptionsValidator(["ALL", "Weekly"])
        )
        self.config_item_dict: dict[str, dict[str, ConfigItem]] = {}

        for group in ["ALL", *calendar.day_name]:
            self.config_item_dict[group] = {}

            ## 理智药数量
            self.config_item_dict[group]["MedicineNumb"] = ConfigItem(
                group, "MedicineNumb", 0, RangeValidator(0, 9999)
            )
            ## 连战次数
            self.config_item_dict[group]["SeriesNumb"] = ConfigItem(
                group,
                "SeriesNumb",
                "0",
                OptionsValidator(["0", "6", "5", "4", "3", "2", "1", "-1"]),
            )

            ## 理智关卡
            for name in MAA_STAGE_KEY[2:]:
                # Stage、Stage_1、Stage_2、Stage_3、Stage_Remain
                self.config_item_dict[group][name] = ConfigItem(group, name, "-")

            for name in MAA_STAGE_KEY:
                setattr(self, f"{group}_{name}", self.config_item_dict[group][name])

        super().__init__()

    def get_current_info(self, name: str) -> ConfigItem:
        """获取当前的计划表配置项"""

        if self.get("Info", "Mode") == "ALL":
            return self.config_item_dict["ALL"][name]

        elif self.get("Info", "Mode") == "Weekly":
            today = datetime.now(tz=UTC4).strftime("%A")

            if today in self.config_item_dict:
                return self.config_item_dict[today][name]
            else:
                return self.config_item_dict["ALL"][name]

        else:
            raise ValueError("非法的计划表模式")


class WeeklyKeyPlanConfig(ConfigBase):
    """只保存日期槽位并返回完整 key 的通用周计划表。"""

    def __init__(
        self,
        default_name: str,
        default_key: Any,
        key_validator: ValidatorBase,
    ) -> None:
        self.Info_Name = ConfigItem("Info", "Name", default_name)
        self.Info_Mode = ConfigItem(
            "Info", "Mode", "ALL", OptionsValidator(["ALL", "Weekly"])
        )

        self.config_item_dict: dict[str, ConfigItem] = {}
        for group in ["ALL", *calendar.day_name]:
            item = ConfigItem(group, "Key", deepcopy(default_key), key_validator)
            self.config_item_dict[group] = item
            setattr(self, f"{group}_Key", item)

        super().__init__()

    def get_current_key(self) -> Any:
        """按当前模式返回完整 key，不解释 key 内容。"""

        if self.get("Info", "Mode") == "ALL":
            return self.config_item_dict["ALL"].getValue()

        today = datetime.now(tz=UTC4).strftime("%A")
        return self.config_item_dict[today].getValue()


class MaaEndPlanConfig(WeeklyKeyPlanConfig):
    """MaaEnd 计划表配置。"""

    def __init__(self) -> None:
        super().__init__(
            default_name="新 MaaEnd 计划表",
            default_key=normalize_maaend_plan_key({}),
            key_validator=MaaEndPlanKeyValidator(),
        )

    async def load(self, data: dict) -> bool:
        """加载计划表并迁移没有 Key 包装的旧日期槽位。"""

        normalized_data = deepcopy(data) if isinstance(data, dict) else {}
        for group in ["ALL", *calendar.day_name]:
            group_data = normalized_data.get(group)
            if isinstance(group_data, dict):
                normalized_data[group] = {"Key": normalize_maaend_plan_key(group_data)}
        return await super().load(normalized_data)


class GeneralUserConfig(ConfigBase):
    """通用脚本用户配置"""

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 用户名称
        self.Info_Name = ConfigItem("Info", "Name", "新用户", UserNameValidator())
        ## 是否启用
        self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
        ## 剩余天数
        self.Info_RemainedDay = ConfigItem(
            "Info", "RemainedDay", -1, RangeValidator(-1, 9999)
        )
        ## 是否使用用户独立脚本配置
        self.Info_IfUseMasConfig = ConfigItem(
            "Info", "IfUseMasConfig", True, BoolValidator()
        )
        ## 是否在任务前执行脚本
        self.Info_IfScriptBeforeTask = ConfigItem(
            "Info", "IfScriptBeforeTask", False, BoolValidator()
        )
        ## 任务前脚本路径
        self.Info_ScriptBeforeTask = ConfigItem(
            "Info", "ScriptBeforeTask", "", FileValidator()
        )
        ## 是否在任务后执行脚本
        self.Info_IfScriptAfterTask = ConfigItem(
            "Info", "IfScriptAfterTask", False, BoolValidator()
        )
        ## 任务后脚本路径
        self.Info_ScriptAfterTask = ConfigItem(
            "Info", "ScriptAfterTask", "", FileValidator()
        )
        ## 备注
        self.Info_Notes = ConfigItem("Info", "Notes", "无")
        ## 用户标签信息
        self.Info_Tag = ConfigItem(
            "Info", "Tag", "[ ]", VirtualConfigValidator(self.getTags)
        )

        ## Data ------------------------------------------------------------
        ## 上次代理日期
        self.Data_LastProxyDate = ConfigItem(
            "Data", "LastProxyDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        ## 代理次数
        self.Data_ProxyTimes = ConfigItem(
            "Data", "ProxyTimes", 0, RangeValidator(0, 9999)
        )

        ## Notify ----------------------------------------------------------
        ## 是否启用通知
        self.Notify_Enabled = ConfigItem("Notify", "Enabled", False, BoolValidator())
        ## 是否发送统计信息
        self.Notify_IfSendStatistic = ConfigItem(
            "Notify", "IfSendStatistic", False, BoolValidator()
        )
        ## 是否发送邮件
        self.Notify_IfSendMail = ConfigItem(
            "Notify", "IfSendMail", False, BoolValidator()
        )
        ## 收件地址
        self.Notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
        ## 是否启用 Server 酱
        self.Notify_IfServerChan = ConfigItem(
            "Notify", "IfServerChan", False, BoolValidator()
        )
        ## Server 酱密钥
        self.Notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
        ## 自定义 Webhook 列表
        self.Notify_CustomWebhooks = MultipleConfig([Webhook])

        super().__init__()

    def getTags(self) -> str:
        """生成通用用户标签列表"""
        tags = []

        # 任务代理标签（使用东4区时间）
        tags.append(_tag_proxy(self, "任务"))

        # 剩余天数标签
        tags.append(_tag_remained_days(self))

        # 备注标签
        tags.append(_tag_notes(self))

        return json.dumps(tags, ensure_ascii=False)


class OkwwTaskIndexValidator(OptionsValidator):
    """兼容旧版中以序号 2 保存的多账号日常任务。"""

    def __init__(self) -> None:
        super().__init__([1, 7])

    def correct(self, value: Any) -> Any:
        return 7 if value == 2 else super().correct(value)


class ScriptUserModeValidator(OptionsValidator):
    """脚本/用户配置来源，兼容旧版“简洁/详细”。

    旧配置里“简洁”即脚本级配置，“详细”即用户级配置，加载时自动归一为“脚本/用户”。
    """

    LEGACY_MODE_MAP = {"简洁": "脚本", "详细": "用户"}

    def __init__(self) -> None:
        super().__init__(["脚本", "用户"])

    def correct(self, value: Any) -> Any:
        return self.LEGACY_MODE_MAP.get(value, super().correct(value))


class OkwwConfigModeValidator(OptionsValidator):
    """兼容旧版“简洁/详细”，统一为脚本/用户/直控配置来源。"""

    LEGACY_MODE_MAP = {"简洁": "脚本", "详细": "用户"}

    def __init__(self) -> None:
        super().__init__(["脚本", "用户", "直控"])

    def correct(self, value: Any) -> Any:
        return self.LEGACY_MODE_MAP.get(value, super().correct(value))


def _migrate_push_log_mode(data: dict) -> None:
    """兼容旧版 Notify.PushLogEnabled 布尔开关 → 三态 PushLogMode

    旧值 False（关闭）迁移为「关闭」，保留用户之前的关闭选择；旧值 True 交由
    新默认「汇总」生效；随后清理旧键，避免其作为未知字段残留。
    """
    notify = data.get("Notify")
    if (
        isinstance(notify, dict)
        and "PushLogEnabled" in notify
        and "PushLogMode" not in notify
    ):
        if notify.get("PushLogEnabled") is False:
            notify["PushLogMode"] = "关闭"
        notify.pop("PushLogEnabled", None)


class OkwwUserConfig(ConfigBase):
    """OK-WW 用户配置（ok-script 线）"""

    async def load(self, data: dict):
        """加载用户配置前迁移旧版推送模式字段。"""
        _migrate_push_log_mode(data)
        await super().load(data)

    # 用户卡 Tag 仅展示中文简称（与编辑页下拉的 English（中文） 区分）
    OKWW_TASK_BOOK: dict[int, str] = {
        1: "日常",
        7: "多账号日常",
    }

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        self.Info_Name = ConfigItem("Info", "Name", "新用户", UserNameValidator())
        self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
        self.Info_Id = ConfigItem("Info", "Id", "")
        self.Info_Resource = ConfigItem(
            "Info", "Resource", "官服", OptionsValidator(["官服", "国际服"])
        )
        self.Info_RemainedDay = ConfigItem(
            "Info", "RemainedDay", -1, RangeValidator(-1, 9999)
        )
        self.Info_Mode = ConfigItem("Info", "Mode", "脚本", OkwwConfigModeValidator())
        # 是否启用 MAS 快速配置覆盖高频任务字段
        self.Info_IfQuickConfig = ConfigItem(
            "Info", "IfQuickConfig", True, BoolValidator()
        )
        self.Info_IfScriptBeforeTask = ConfigItem(
            "Info", "IfScriptBeforeTask", False, BoolValidator()
        )
        self.Info_ScriptBeforeTask = ConfigItem(
            "Info", "ScriptBeforeTask", "", FileValidator()
        )
        self.Info_IfScriptAfterTask = ConfigItem(
            "Info", "IfScriptAfterTask", False, BoolValidator()
        )
        self.Info_ScriptAfterTask = ConfigItem(
            "Info", "ScriptAfterTask", "", FileValidator()
        )
        self.Info_Notes = ConfigItem("Info", "Notes", "无")
        self.Info_Tag = ConfigItem(
            "Info", "Tag", "[ ]", VirtualConfigValidator(self.getTags)
        )

        ## Task ------------------------------------------------------------
        # MAS 仅接管 DailyTask / MultiAccountDailyTask 及 DailyTask 高频设置。
        ## 启动任务序号
        self.Task_TaskIndex = ConfigItem(
            "Task", "TaskIndex", 1, OkwwTaskIndexValidator()
        )
        ## 每日任务体力用途
        self.Task_WhichToFarm = ConfigItem(
            "Task",
            "WhichToFarm",
            "Tacet Suppression",
            OptionsValidator(
                ["Tacet Suppression", "Forgery Challenge", "Simulation Challenge"]
            ),
        )
        ## 无音区序号
        self.Task_WhichTacetSuppressionToFarm = ConfigItem(
            "Task", "WhichTacetSuppressionToFarm", 1, RangeValidator(1, 99)
        )
        ## 凝素领域序号
        self.Task_WhichForgeryChallengeToFarm = ConfigItem(
            "Task", "WhichForgeryChallengeToFarm", 1, RangeValidator(1, 99)
        )
        ## 模拟领域材料
        self.Task_MaterialSelection = ConfigItem(
            "Task",
            "MaterialSelection",
            "Shell Credit",
            OptionsValidator(["Resonator EXP", "Weapon EXP", "Shell Credit"]),
        )
        ## 使用梦魇巢穴完成日常声骸
        self.Task_FarmNightmareNestForDailyEcho = ConfigItem(
            "Task", "FarmNightmareNestForDailyEcho", True, BoolValidator()
        )
        ## 每日任务后运行的附加任务
        self.Task_AdditionalTasks = ConfigItem(
            "Task",
            "AdditionalTasks",
            ["Check Weekly Garden"],
            MultipleOptionsValidator(
                [
                    "Check Weekly Garden",
                    "Auto Farm all Nightmare Nest",
                    "Merge Echo If discarded > 1000",
                    "Teleport and Farm 4C Echo",
                ]
            ),
        )

        ## Data ------------------------------------------------------------
        self.Data_LastProxyDate = ConfigItem(
            "Data", "LastProxyDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        self.Data_ProxyTimes = ConfigItem(
            "Data", "ProxyTimes", 0, RangeValidator(0, 9999)
        )
        self.Data_LastProxyStatus = ConfigItem(
            "Data",
            "LastProxyStatus",
            "未知",
            OptionsValidator(["未知", "成功", "失败"]),
        )
        self.Data_LastTaskIndex = ConfigItem(
            "Data", "LastTaskIndex", 0, RangeValidator(0, 9999)
        )

        ## Notify ----------------------------------------------------------
        ## 是否启用用户通知
        self.Notify_Enabled = ConfigItem("Notify", "Enabled", False, BoolValidator())
        ## 任务报告节点详情的推送模式（log_box 采集的关键节点）：
        ## 关闭 = 不采集；逐条 = 采集并逐条带回时间戳；汇总 = 采集并按状态聚合
        self.Notify_PushLogMode = ConfigItem(
            "Notify",
            "PushLogMode",
            "汇总",
            OptionsValidator(["关闭", "逐条", "汇总"]),
        )
        ## 是否发送用户统计信息
        self.Notify_IfSendStatistic = ConfigItem(
            "Notify", "IfSendStatistic", False, BoolValidator()
        )
        ## 是否发送邮件
        self.Notify_IfSendMail = ConfigItem(
            "Notify", "IfSendMail", False, BoolValidator()
        )
        ## 用户收件地址
        self.Notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
        ## 是否启用 Server 酱
        self.Notify_IfServerChan = ConfigItem(
            "Notify", "IfServerChan", False, BoolValidator()
        )
        ## Server 酱密钥
        self.Notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
        ## 用户自定义 Webhook 列表
        self.Notify_CustomWebhooks = MultipleConfig([Webhook])

        super().__init__()

    def getTags(self) -> str:
        tags = []

        last_status = self.get("Data", "LastProxyStatus")
        tags.append({"text": f"上次：{last_status}", "color": "green"})

        last_task_index = int(self.get("Data", "LastTaskIndex") or 0)
        task_label = self.OKWW_TASK_BOOK.get(last_task_index, "未知")
        tags.append({"text": f"任务：{task_label}", "color": "orange"})

        # 剩余天数标签
        tags.append(_tag_remained_days(self))

        # 备注标签
        tags.append(_tag_notes(self))

        return json.dumps(tags, ensure_ascii=False)


class OkNteUserConfig(ConfigBase):
    """OK-NTE 用户配置（ok-script 线）"""

    async def load(self, data: dict):
        """加载用户配置前迁移旧版推送模式字段。"""
        _migrate_push_log_mode(data)
        await super().load(data)

    OKNTE_TASK_BOOK: dict[int, str] = {
        1: "启动游戏",
        2: "日常任务",
        3: "自动钓鱼",
        4: "异象界域",
        5: "异象追猎",
        6: "音游",
        7: "店长特供",
        8: "粉爪大劫案",
        9: "呗果智能体",
        10: "自动小旋风",
        11: "九百九十九夜",
        12: "自动战斗检测诊断",
        13: "诊断",
        14: "日常领取",
        15: "羁遇赠礼",
        16: "一咖舍",
        17: "喷泉签到",
        18: "异象家具",
        19: "影院约会",
    }

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        self.Info_Name = ConfigItem("Info", "Name", "新用户", UserNameValidator())
        self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
        self.Info_Id = ConfigItem("Info", "Id", "")
        self.Info_Password = ConfigItem("Info", "Password", "", EncryptValidator())
        self.Info_Resource = ConfigItem(
            "Info", "Resource", "官服", OptionsValidator(["官服"])
        )
        self.Info_RemainedDay = ConfigItem(
            "Info", "RemainedDay", -1, RangeValidator(-1, 9999)
        )
        self.Info_Mode = ConfigItem("Info", "Mode", "脚本", ScriptUserModeValidator())
        self.Info_IfScriptBeforeTask = ConfigItem(
            "Info", "IfScriptBeforeTask", False, BoolValidator()
        )
        self.Info_ScriptBeforeTask = ConfigItem(
            "Info", "ScriptBeforeTask", "", FileValidator()
        )
        self.Info_IfScriptAfterTask = ConfigItem(
            "Info", "IfScriptAfterTask", False, BoolValidator()
        )
        self.Info_ScriptAfterTask = ConfigItem(
            "Info", "ScriptAfterTask", "", FileValidator()
        )
        self.Info_Notes = ConfigItem("Info", "Notes", "无")
        self.Info_Tag = ConfigItem(
            "Info", "Tag", "[ ]", VirtualConfigValidator(self.getTags)
        )

        ## Task ------------------------------------------------------------
        # ok-nte.exe -t N -e；新版上游 DailyRoutineTask 是 -t 2
        self.Task_TaskIndex = ConfigItem("Task", "TaskIndex", 2, RangeValidator(1, 19))
        self.Task_ExitOnFinish = ConfigItem(
            "Task", "ExitOnFinish", True, BoolValidator()
        )

        ## Data ------------------------------------------------------------
        self.Data_LastProxyDate = ConfigItem(
            "Data", "LastProxyDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        self.Data_ProxyTimes = ConfigItem(
            "Data", "ProxyTimes", 0, RangeValidator(0, 9999)
        )
        self.Data_LastProxyStatus = ConfigItem(
            "Data",
            "LastProxyStatus",
            "未知",
            OptionsValidator(["未知", "成功", "失败"]),
        )
        self.Data_LastTaskIndex = ConfigItem(
            "Data", "LastTaskIndex", 0, RangeValidator(0, 9999)
        )

        ## Notify ----------------------------------------------------------
        self.Notify_Enabled = ConfigItem("Notify", "Enabled", False, BoolValidator())
        ## 任务报告节点详情的推送模式（log_box 采集的关键节点）：
        ## 关闭 = 不采集；逐条 = 采集并逐条带回时间戳；汇总 = 采集并按状态聚合
        self.Notify_PushLogMode = ConfigItem(
            "Notify",
            "PushLogMode",
            "汇总",
            OptionsValidator(["关闭", "逐条", "汇总"]),
        )
        self.Notify_IfSendStatistic = ConfigItem(
            "Notify", "IfSendStatistic", False, BoolValidator()
        )
        self.Notify_IfSendMail = ConfigItem(
            "Notify", "IfSendMail", False, BoolValidator()
        )
        self.Notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
        self.Notify_IfServerChan = ConfigItem(
            "Notify", "IfServerChan", False, BoolValidator()
        )
        self.Notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
        self.Notify_CustomWebhooks = MultipleConfig([Webhook])

        super().__init__()

    def getTags(self) -> str:
        tags = []

        last_status = self.get("Data", "LastProxyStatus")
        tags.append({"text": f"上次：{last_status}", "color": "green"})

        last_task_index = int(self.get("Data", "LastTaskIndex") or 0)
        task_label = self.OKNTE_TASK_BOOK.get(last_task_index, "未知")
        tags.append({"text": f"任务：{task_label}", "color": "orange"})

        # 剩余天数标签
        tags.append(_tag_remained_days(self))

        # 备注标签
        tags.append(_tag_notes(self))

        return json.dumps(tags, ensure_ascii=False)


# BetterGI 一条龙内置配置组（MAS 默认顺序，与 tools/one_dragon.py 保持同步）。
# 「体力作战」为 MAS 前端预留的虚拟项（尚未开展制作，前端默认隐藏，不在此表），
# 恢复展示后在 initDragonList 插入「合成树脂」之后；此处仅列 BetterGI 官方内置 8 组。
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

# 旧版「国际服服务器(Servers)」→ 新版「游戏资源(Resource)」的映射。
# 用于加载旧配置时迁移（GlobalAccount=True 且 Servers 未知/「不切换服务器」时兜底为亚服）。
_BGI_LEGACY_SERVERS_TO_RESOURCE = {
    "Asia": "亚服",
    "Europe": "欧服",
    "America": "美服",
    "TW,HK,MO": "港澳台服",
}


class BetterGIUserConfig(ConfigBase):
    """BetterGI 用户配置（更好的原神）"""

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        self.Info_Name = ConfigItem("Info", "Name", "新用户", UserNameValidator())
        self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
        self.Info_Id = ConfigItem("Info", "Id", "")
        self.Info_Password = ConfigItem("Info", "Password", "", EncryptValidator())
        self.Info_RemainedDay = ConfigItem(
            "Info", "RemainedDay", -1, RangeValidator(-1, 9999)
        )
        self.Info_IfScriptBeforeTask = ConfigItem(
            "Info", "IfScriptBeforeTask", False, BoolValidator()
        )
        self.Info_ScriptBeforeTask = ConfigItem(
            "Info", "ScriptBeforeTask", "", FileValidator()
        )
        self.Info_IfScriptAfterTask = ConfigItem(
            "Info", "IfScriptAfterTask", False, BoolValidator()
        )
        self.Info_ScriptAfterTask = ConfigItem(
            "Info", "ScriptAfterTask", "", FileValidator()
        )
        self.Info_Notes = ConfigItem("Info", "Notes", "无")
        self.Info_Tag = ConfigItem(
            "Info", "Tag", "[ ]", VirtualConfigValidator(self.getTags)
        )
        ## 是否使用用户独立一条龙配置（借鉴通用脚本 IfUseMasConfig）
        self.Info_IfUseMasConfig = ConfigItem(
            "Info", "IfUseMasConfig", True, BoolValidator()
        )

        ## Task ------------------------------------------------------------
        ## BetterGI「一条龙」配置名，对应脚本一条龙页面中已保存的配置名称
        self.Task_OneDragonConfigName = ConfigItem("Task", "OneDragonConfigName", "")

        ## OneDragon -------------------------------------------------------
        ## 一条龙要执行的内置配置组（按组名，默认全部 8 组开启）
        self.OneDragon_Groups = ConfigItem(
            "OneDragon",
            "Groups",
            list(_BGI_BUILTIN_ONE_DRAGON_GROUPS),
            MultipleOptionsValidator(_BGI_BUILTIN_ONE_DRAGON_GROUPS),
        )
        ## 领取奖励队伍（对应 BetterGI 一条龙的 DailyRewardPartyName，留空不覆盖）
        self.OneDragon_DailyRewardPartyName = ConfigItem(
            "OneDragon", "DailyRewardPartyName", ""
        )
        ## 战斗队伍（对应 BetterGI 一条龙的通用 PartyName，留空不覆盖）
        self.OneDragon_PartyName = ConfigItem("OneDragon", "PartyName", "")
        ## 战斗策略（对应 BetterGI 一条龙的 AutoBossStrategyName，留空不覆盖）
        ## 默认「根据队伍自动选择」为 BetterGI 内置策略名
        self.OneDragon_AutoBossStrategyName = ConfigItem(
            "OneDragon", "AutoBossStrategyName", ""
        )
        ## 是否管理自定义配置组（总开关；OFF 时沿 BetterGI 原生设置，自定义组原样保留）
        self.OneDragon_IfUseCustomGroups = ConfigItem(
            "OneDragon", "IfUseCustomGroups", False, BoolValidator()
        )
        ## 自定义配置组列表：JSON 数组字符串，元素为 {"name": str, "enabled": bool}
        self.OneDragon_CustomGroups = ConfigItem(
            "OneDragon", "CustomGroups", "[]", JSONValidator(list)
        )
        ## 一条龙队列（可视化编排）：JSON 数组字符串，按执行顺序存储，元素为
        ## {"kind": str, "name": str}（kind ∈ builtin/js/pathing/scriptgroup/custom，
        ## 内置组名命中时后端强制 builtin）。仅表达顺序与成员（含同名重复实例），
        ## 行启停仍由 Groups / CustomGroups 承载；为空或非法时回退旧行为
        ## （按副本 TaskOrder 相对顺序，不重排）。
        self.OneDragon_Queue = ConfigItem("OneDragon", "Queue", "[]", JSONValidator(list))
        ## 一条龙执行计划（Plan）JSON 字符串：{version, steps:[{uid,kind,name,enabled,settings}]}。
        ## 战斗 4 项（自动秘境/自动地脉花/自动幽境危战/自动首领讨伐）直连执行层时由本字段
        ## 承载其 per-任务参数；右栏对应设置仅写入本字段（不落原生一条龙配置）。
        self.OneDragon_Plan = ConfigItem("OneDragon", "Plan", "", StringValidator())
        ## 是否启用「直连执行层」：战斗 4 项由 MAS 自编排 Plan 驱动（按需求恒开，预留开关）。
        self.OneDragon_UseExecutionLayer = ConfigItem(
            "OneDragon", "UseExecutionLayer", True, BoolValidator()
        )

        ## Switch ----------------------------------------------------------
        ## 切换账号配置（BetterGI「切换账号多模式」脚本专项适配）
        ## 账号/密码复用 Info.Id / Info.Password（密码经 EncryptValidator 加密）
        ## 切换模式不再由用户配置，运行时按密码是否填写推断：
        ##   填密码 → 「账号+密码+OCR」，未填 → 「下拉列表」；B服 强制「B服切换另一个账号匹配+键鼠」。
        ## 游戏服务器（账号所在服务器：官服/B服/国际服各服务器）
        self.Switch_Resource = ConfigItem(
            "Switch",
            "Resource",
            "官服",
            OptionsValidator(["官服", "B服", "亚服", "欧服", "美服", "港澳台服"]),
        )
        ## 账号 UID（可不填，切换前识别一致将不执行切换动作）
        self.Switch_Uid = ConfigItem("Switch", "Uid", "")

        ## Data ------------------------------------------------------------
        self.Data_LastProxyDate = ConfigItem(
            "Data", "LastProxyDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        self.Data_ProxyTimes = ConfigItem(
            "Data", "ProxyTimes", 0, RangeValidator(0, 9999)
        )
        self.Data_LastProxyStatus = ConfigItem(
            "Data",
            "LastProxyStatus",
            "未知",
            OptionsValidator(["未知", "成功", "失败"]),
        )

        ## Notify ----------------------------------------------------------
        ## 是否启用用户通知
        self.Notify_Enabled = ConfigItem("Notify", "Enabled", False, BoolValidator())
        ## 是否发送用户统计信息
        self.Notify_IfSendStatistic = ConfigItem(
            "Notify", "IfSendStatistic", False, BoolValidator()
        )
        ## 是否发送邮件
        self.Notify_IfSendMail = ConfigItem(
            "Notify", "IfSendMail", False, BoolValidator()
        )
        ## 用户收件地址
        self.Notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
        ## 是否启用 Server 酱
        self.Notify_IfServerChan = ConfigItem(
            "Notify", "IfServerChan", False, BoolValidator()
        )
        ## Server 酱密钥
        self.Notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
        ## 用户自定义 Webhook 列表
        self.Notify_CustomWebhooks = MultipleConfig([Webhook])

        super().__init__()

    async def load(self, data: dict) -> bool:
        """加载配置前，把旧版「国际服账号 + 国际服服务器 / B服切换模式」迁移为「游戏服务器」。"""
        normalized_data = deepcopy(data) if isinstance(data, dict) else {}
        switch = normalized_data.get("Switch")
        if isinstance(switch, dict) and "Resource" not in switch:
            if switch.get("Modes") == "B服切换另一个账号匹配+键鼠":
                # 旧版 B服 是切换模式，现作为游戏服务器
                switch["Resource"] = "B服"
            elif switch.get("GlobalAccount"):
                switch["Resource"] = _BGI_LEGACY_SERVERS_TO_RESOURCE.get(
                    switch.get("Servers"), "亚服"
                )
            else:
                switch["Resource"] = "官服"
        return await super().load(normalized_data)

    def getTags(self) -> str:
        tags = []

        last_status = self.get("Data", "LastProxyStatus")
        tags.append({"text": f"上次：{last_status}", "color": "green"})

        # 用户独立配置：一条龙固定走「MAS独立配置」槽位（名称冻结），仅直控模式显示所选实配名
        if self.get("Info", "IfUseMasConfig"):
            config_name = "MAS独立配置"
        else:
            config_name = self.get("Task", "OneDragonConfigName") or "未设置"
        tags.append({"text": f"一条龙：{config_name}", "color": "orange"})

        # 剩余天数标签
        tags.append(_tag_remained_days(self))

        # 备注标签
        tags.append(_tag_notes(self))

        return json.dumps(tags, ensure_ascii=False)


class GeneralConfig(ConfigBase):
    """通用配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 脚本名称
        self.Info_Name = ConfigItem("Info", "Name", "新通用脚本")
        ## 根目录路径
        self.Info_RootPath = ConfigItem("Info", "RootPath", "", FileValidator())

        ## Script ----------------------------------------------------------
        ## 脚本路径
        self.Script_ScriptPath = ConfigItem("Script", "ScriptPath", "", FileValidator())
        ## 脚本参数
        self.Script_Arguments = ConfigItem(
            "Script", "Arguments", "", AdvancedArgumentValidator()
        )
        ## 是否追踪进程
        self.Script_IfTrackProcess = ConfigItem(
            "Script", "IfTrackProcess", False, BoolValidator()
        )
        ## 追踪进程的名称
        self.Script_TrackProcessName = ConfigItem("Script", "TrackProcessName", "")
        ## 追踪进程的文件路径
        self.Script_TrackProcessExe = ConfigItem("Script", "TrackProcessExe", "")
        ## 追踪进程的启动命令行参数
        self.Script_TrackProcessCmdline = ConfigItem(
            "Script", "TrackProcessCmdline", "", ArgumentValidator()
        )
        self.Script_ConfigPath = ConfigItem("Script", "ConfigPath", "", FileValidator())
        ## 配置路径模式
        self.Script_ConfigPathMode = ConfigItem(
            "Script", "ConfigPathMode", "File", OptionsValidator(["File", "Folder"])
        )
        ## 更新配置模式
        self.Script_UpdateConfigMode = ConfigItem(
            "Script",
            "UpdateConfigMode",
            "Never",
            OptionsValidator(["Never", "Success", "Failure", "Always"]),
        )
        ## 日志路径
        self.Script_LogPath = ConfigItem("Script", "LogPath", "", FileValidator())
        ## 日志路径格式
        self.Script_LogPathFormat = ConfigItem("Script", "LogPathFormat", "%Y-%m-%d")
        ## 日志时间戳开始位置
        self.Script_LogTimeStart = ConfigItem(
            "Script", "LogTimeStart", 1, RangeValidator(1, 9999)
        )
        ## 日志时间戳结束位置
        self.Script_LogTimeEnd = ConfigItem(
            "Script", "LogTimeEnd", 1, RangeValidator(1, 9999)
        )
        ## 日志时间格式
        self.Script_LogTimeFormat = ConfigItem(
            "Script", "LogTimeFormat", "%Y-%m-%d %H:%M:%S"
        )
        ## 日志处理钩子启用开关：关闭时保留规则配置，行为与未配置钩子完全一致
        self.Script_LogHookEnabled = ConfigItem(
            "Script", "LogHookEnabled", False, BoolValidator()
        )
        ## 日志处理钩子规则（JSON 数组，每项形如 {"type":"drop|replace",...}）；
        ## 钩子先于任务日志、推送日志采集与成功/失败判定执行，丢弃的行不进入下游
        self.Script_LogHookRules = ConfigItem("Script", "LogHookRules", "")
        ## 成功日志匹配
        self.Script_SuccessLog = ConfigItem("Script", "SuccessLog", "")
        ## 成功日志匹配模式：Split = 「|」分隔关键字子串包含；Regex = 正则表达式
        self.Script_SuccessLogMode = ConfigItem(
            "Script", "SuccessLogMode", "Split", OptionsValidator(["Split", "Regex"])
        )
        ## 错误日志匹配
        self.Script_ErrorLog = ConfigItem("Script", "ErrorLog", "")
        ## 错误日志匹配模式：Split = 「|」分隔关键字子串包含；Regex = 正则表达式
        self.Script_ErrorLogMode = ConfigItem(
            "Script", "ErrorLogMode", "Split", OptionsValidator(["Split", "Regex"])
        )
        ## 推送日志启用开关：关闭后保留高级正则配置，但不会实际采集推送日志
        self.Script_PushLogEnabled = ConfigItem(
            "Script", "PushLogEnabled", False, BoolValidator()
        )
        ## 推送日志高级模式（JSON 数组，每项形如 {"type":"regex|multiline",...}）
        self.Script_PushLogPatterns = ConfigItem("Script", "PushLogPatterns", "")

        ## Game ------------------------------------------------------------
        ## 是否启用游戏
        self.Game_Enabled = ConfigItem("Game", "Enabled", False, BoolValidator())
        ## 游戏类型
        self.Game_Type = ConfigItem(
            "Game", "Type", "Emulator", OptionsValidator(["Emulator", "Client", "URL"])
        )
        ## 游戏路径
        self.Game_Path = ConfigItem("Game", "Path", "", FileValidator())
        ## 自定义协议URL
        self.Game_URL = ConfigItem("Game", "URL", "")
        ## 游戏进程名称
        self.Game_ProcessName = ConfigItem("Game", "ProcessName", "")
        ## 游戏启动参数
        self.Game_Arguments = ConfigItem("Game", "Arguments", "", ArgumentValidator())
        ## 等待时间（秒）
        self.Game_WaitTime = ConfigItem("Game", "WaitTime", 0, RangeValidator(0, 9999))
        ## 是否强制关闭
        self.Game_IfForceClose = ConfigItem(
            "Game", "IfForceClose", False, BoolValidator()
        )
        ## 模拟器 ID
        self.Game_EmulatorId = ConfigItem(
            "Game",
            "EmulatorId",
            "-",
            MultipleUIDValidator("-", self.related_config, "EmulatorConfig"),
        )
        ## 模拟器索引
        self.Game_EmulatorIndex = ConfigItem("Game", "EmulatorIndex", "-")

        ## Run -------------------------------------------------------------
        ## 代理次数限制
        self.Run_ProxyTimesLimit = ConfigItem(
            "Run", "ProxyTimesLimit", 0, RangeValidator(0, 9999)
        )
        ## 运行次数限制
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 3, RangeValidator(1, 9999)
        )
        ## 运行时间限制（分钟）
        self.Run_RunTimeLimit = ConfigItem(
            "Run", "RunTimeLimit", 10, RangeValidator(1, 9999)
        )

        self.UserData = MultipleConfig([GeneralUserConfig])

        super().__init__()


class OkwwConfig(ConfigBase):
    """OK-WW 配置（ok-script 线）"""

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 脚本名称
        self.Info_Name = ConfigItem("Info", "Name", "新 OK-WW 脚本")
        ## OK-WW 脚本根目录
        self.Info_RootPath = ConfigItem("Info", "RootPath", "", FileValidator())

        ## Game ------------------------------------------------------------
        ## 是否由 MAS 管理游戏进程
        self.Game_Enabled = ConfigItem("Game", "Enabled", False, BoolValidator())
        ## 鸣潮启动器路径
        self.Game_Path = ConfigItem("Game", "Path", "", FileValidator())
        ## 鸣潮启动参数
        self.Game_Arguments = ConfigItem("Game", "Arguments", "", ArgumentValidator())
        ## 等待游戏启动时间
        self.Game_WaitTime = ConfigItem("Game", "WaitTime", 60, RangeValidator(0, 9999))
        ## 任务前是否由 MAS 检查并接管更新游戏
        self.Game_IfAutoUpdate = ConfigItem(
            "Game", "IfAutoUpdate", True, BoolValidator()
        )
        ## 整文件同步体积上限（GB），超过则中止并提示手动处理
        self.Game_UpdateFullSyncLimit = ConfigItem(
            "Game", "UpdateFullSyncLimit", 30, RangeValidator(1, 9999)
        )
        ## 运行前强制切换账号（依赖游戏配置启用；用户未填手机号时不切换）
        self.Game_AccountSwitch = ConfigItem(
            "Game", "AccountSwitch", False, BoolValidator()
        )
        ## Run -------------------------------------------------------------
        ## 每日代理次数上限
        self.Run_ProxyTimesLimit = ConfigItem(
            "Run", "ProxyTimesLimit", 0, RangeValidator(0, 9999)
        )
        ## 单次任务重试次数
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 3, RangeValidator(1, 9999)
        )
        ## 单次运行超时时间
        self.Run_RunTimeLimit = ConfigItem(
            "Run", "RunTimeLimit", 60, RangeValidator(1, 9999)
        )

        self.UserData = MultipleConfig([OkwwUserConfig])

        super().__init__()


class OkNteConfig(ConfigBase):
    """OK-NTE 配置（ok-script 线）"""

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        self.Info_Name = ConfigItem("Info", "Name", "新 OK-NTE 脚本")
        self.Info_RootPath = ConfigItem("Info", "RootPath", "", FileValidator())

        ## Script ----------------------------------------------------------
        self.Script_ScriptPath = ConfigItem("Script", "ScriptPath", "", FileValidator())
        # OkNte 运行参数建议由用户配置（-t / -e 由用户配置 Task 决定），但仍保留高级参数入口
        self.Script_Arguments = ConfigItem(
            "Script", "Arguments", "", AdvancedArgumentValidator()
        )
        self.Script_IfTrackProcess = ConfigItem(
            "Script", "IfTrackProcess", True, BoolValidator()
        )
        self.Script_TrackProcessName = ConfigItem("Script", "TrackProcessName", "")
        self.Script_TrackProcessExe = ConfigItem("Script", "TrackProcessExe", "")
        self.Script_TrackProcessCmdline = ConfigItem(
            "Script", "TrackProcessCmdline", "", ArgumentValidator()
        )
        self.Script_ConfigPath = ConfigItem("Script", "ConfigPath", "", FileValidator())
        self.Script_ConfigPathMode = ConfigItem(
            "Script", "ConfigPathMode", "Folder", OptionsValidator(["File", "Folder"])
        )
        self.Script_UpdateConfigMode = ConfigItem(
            "Script",
            "UpdateConfigMode",
            "Always",
            OptionsValidator(["Never", "Success", "Failure", "Always"]),
        )
        self.Script_LogPath = ConfigItem("Script", "LogPath", "", FileValidator())
        self.Script_LogPathFormat = ConfigItem("Script", "LogPathFormat", "")
        self.Script_LogTimeStart = ConfigItem(
            "Script", "LogTimeStart", 1, RangeValidator(1, 9999)
        )
        self.Script_LogTimeEnd = ConfigItem(
            "Script", "LogTimeEnd", 23, RangeValidator(1, 9999)
        )
        self.Script_LogTimeFormat = ConfigItem(
            "Script", "LogTimeFormat", "%Y-%m-%d %H:%M:%S,%f"
        )
        self.Script_SuccessLog = ConfigItem(
            "Script", "SuccessLog", "Successfully Executed Task|任务执行完成"
        )
        self.Script_SuccessLogMode = ConfigItem(
            "Script", "SuccessLogMode", "Split", OptionsValidator(["Split", "Regex"])
        )
        self.Script_ErrorLog = ConfigItem(
            "Script",
            "ErrorLog",
            "connected:False|Resolution Error|Timed out waiting for game process|"
            "Timed out waiting for launcher process",
        )
        self.Script_ErrorLogMode = ConfigItem(
            "Script", "ErrorLogMode", "Split", OptionsValidator(["Split", "Regex"])
        )

        ## Game ------------------------------------------------------------
        self.Game_Enabled = ConfigItem("Game", "Enabled", False, BoolValidator())
        self.Game_LaunchBeforeTask = ConfigItem(
            "Game", "LaunchBeforeTask", False, BoolValidator()
        )
        self.Game_Type = ConfigItem(
            "Game", "Type", "Client", OptionsValidator(["Client", "URL"])
        )
        # 异环直启 HTGame.exe 会卡界面，此路径为启动器 exe（NTELauncher/NTEGame.exe），
        # 旧值为 HTGame.exe 时运行时自动反推同安装根下的启动器
        self.Game_Path = ConfigItem("Game", "Path", "", FileValidator())
        self.Game_URL = ConfigItem("Game", "URL", "")
        self.Game_ProcessName = ConfigItem("Game", "ProcessName", "")
        self.Game_Arguments = ConfigItem("Game", "Arguments", "", ArgumentValidator())
        self.Game_WaitTime = ConfigItem("Game", "WaitTime", 60, RangeValidator(0, 9999))
        self.Game_IfForceClose = ConfigItem(
            "Game", "IfForceClose", True, BoolValidator()
        )
        self.Game_CloseOnFinish = ConfigItem(
            "Game", "CloseOnFinish", True, BoolValidator()
        )
        ## 运行前强制切换账号（依赖游戏配置启用；用户未填手机号时不切换）
        self.Game_AccountSwitch = ConfigItem(
            "Game", "AccountSwitch", False, BoolValidator()
        )

        ## Run -------------------------------------------------------------
        self.Run_ProxyTimesLimit = ConfigItem(
            "Run", "ProxyTimesLimit", 0, RangeValidator(0, 9999)
        )
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 1, RangeValidator(1, 9999)
        )
        self.Run_RunTimeLimit = ConfigItem(
            "Run", "RunTimeLimit", 120, RangeValidator(1, 9999)
        )

        self.UserData = MultipleConfig([OkNteUserConfig])

        super().__init__()


class BetterGIConfig(ConfigBase):
    """BetterGI 配置（更好的原神，原生 GUI 直控 + 仅一条龙任务）"""

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        self.Info_Name = ConfigItem("Info", "Name", "新 BetterGI 脚本")
        self.Info_RootPath = ConfigItem("Info", "RootPath", "", FileValidator())

        ## Run -------------------------------------------------------------
        self.Run_ProxyTimesLimit = ConfigItem(
            "Run", "ProxyTimesLimit", 0, RangeValidator(0, 9999)
        )
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 3, RangeValidator(1, 9999)
        )
        self.Run_RunTimeLimit = ConfigItem(
            "Run", "RunTimeLimit", 10, RangeValidator(1, 9999)
        )
        ## 是否以管理员权限启动 BetterGI。默认提权（贴近旧行为）；若 MAS 平时以非管理员
        ## 运行、又不希望每次启动 BGI 都弹 UAC（无人值守任务尤其容易挂在授权上），可关闭。
        ## MAS 自身已提权时，即使此处开启，也不会重复触发 UAC（子进程自动继承管理员令牌）。
        self.Run_UseAdmin = ConfigItem("Run", "UseAdmin", True, BoolValidator())

        ## Game ------------------------------------------------------------
        ## 控制器（游戏控制方式：电脑端-前台 / 电脑端-云原神 / 电脑端-桌面分身）
        ## ⚠️ 预留字段：当前运行时不读取（BetterGI 自行管理游戏控制），云原神 / 桌面分身
        ##    尚未开发。为将来支持而保留占位并持久化，恒为默认「电脑端-前台」，勿被判定死代码误删。
        self.Game_Controller = ConfigItem(
            "Game",
            "Controller",
            "电脑端-前台",
            OptionsValidator(["电脑端-前台", "电脑端-云原神", "电脑端-桌面分身"]),
        )
        ## 任务结束后关闭游戏
        self.Game_CloseOnFinish = ConfigItem(
            "Game", "CloseOnFinish", True, BoolValidator()
        )

        self.UserData = MultipleConfig([BetterGIUserConfig])

        super().__init__()


class ZzzOdUserConfig(ConfigBase):
    """绝区零一条龙用户配置（zzz-od 线，MaaEnd 式字段化用户配置）

    用户配置的事实源是本类的 ConfigItem 字段（web 界面直接编辑，走通用
    updateUser 链路）：Game 区为账号/区服/游戏路径，OneDragon 区为一条龙
    任务编排（JSON，顺序即执行顺序）。运行时由这些字段生成 game_account.yml
    与 one_dragon/_group.yml 注入当前活跃实例槽、结束恢复原状（MAS 不留
    痕迹）。「直控」模式不使用字段配置，直接以 zzz-od 原生配置运行。
    """

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        self.Info_Name = ConfigItem("Info", "Name", "新用户", UserNameValidator())
        self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
        ## 配置来源两态（对齐 MaaEnd 简洁/详细）：用户=本配置字段；直控=zzz-od 原生配置
        self.Info_Mode = ConfigItem(
            "Info", "Mode", "用户", OptionsValidator(["用户", "直控"])
        )
        ## 绑定的 zzz-od 实例槽下标（运行/配置会话内临时合成视图写回原生配置，非持久注册）：-1=未分配，首次运行或
        ## 「在一条龙内配置」时自动分配空闲 idx 并锁定该槽至会话结束，
        ## 此后配置会话与运行时注入都固定使用该槽
        self.Info_SlotIdx = ConfigItem(
            "Info", "SlotIdx", -1, RangeValidator(-1, 999)
        )
        ## 一条龙启动器选择（直控/用户两态通用）：
        ## 自动 = 优先用「上次成功」的启动器，启动失败自动换另一个重试并记住下一次
        ## 成功的那个；原始/集成 = 固定用对应启动器（对应 exe 未安装时回退可用项）
        self.Info_LauncherMode = ConfigItem(
            "Info",
            "LauncherMode",
            "自动",
            OptionsValidator(["自动", "原始", "集成"]),
        )
        self.Info_RemainedDay = ConfigItem(
            "Info", "RemainedDay", -1, RangeValidator(-1, 9999)
        )
        self.Info_IfScriptBeforeTask = ConfigItem(
            "Info", "IfScriptBeforeTask", False, BoolValidator()
        )
        self.Info_ScriptBeforeTask = ConfigItem(
            "Info", "ScriptBeforeTask", "", FileValidator()
        )
        self.Info_IfScriptAfterTask = ConfigItem(
            "Info", "IfScriptAfterTask", False, BoolValidator()
        )
        self.Info_ScriptAfterTask = ConfigItem(
            "Info", "ScriptAfterTask", "", FileValidator()
        )
        self.Info_Notes = ConfigItem("Info", "Notes", "无")
        self.Info_Tag = ConfigItem(
            "Info", "Tag", "[ ]", VirtualConfigValidator(self.getTags)
        )

        ## Game ------------------------------------------------------------
        ## 游戏区服（zzz-od game_account.yml 的 game_region 取值）
        self.Game_GameRegion = ConfigItem(
            "Game",
            "GameRegion",
            "cn",
            OptionsValidator(["cn", "cn_b", "us", "eu", "asia", "twhkmo"]),
        )
        ## 游戏 exe 完整路径（ZenlessZoneZero.exe）
        self.Game_GamePath = ConfigItem("Game", "GamePath", "", FileValidator())
        ## 游戏界面语言
        self.Game_GameLanguage = ConfigItem(
            "Game", "GameLanguage", "cn", OptionsValidator(["cn", "en"])
        )
        ## 登录账号（手机号/邮箱；留空沿用 zzz-od 已保存的登录态）
        self.Game_Account = ConfigItem("Game", "Account", "")
        ## 登录密码（DPAPI 加密落盘，注入/回读写 game_account.yml 时经 get/set 自动加解密）
        self.Game_Password = ConfigItem("Game", "Password", "", EncryptValidator())
        ## B服登录账号名
        self.Game_BilibiliAccountName = ConfigItem("Game", "BilibiliAccountName", "")
        ## 游戏平台（上游枚举 GamePlatformEnum.PC 的真实值为大写 'PC'）
        self.Game_Platform = ConfigItem(
            "Game", "Platform", "PC", OptionsValidator(["PC"])
        )
        ## 是否使用自定义窗口标题
        self.Game_UseCustomWinTitle = ConfigItem(
            "Game", "UseCustomWinTitle", False, BoolValidator()
        )
        ## 自定义窗口标题
        self.Game_CustomWinTitle = ConfigItem("Game", "CustomWinTitle", "")

        ## OneDragon -------------------------------------------------------
        ## 一条龙任务编排（JSON 数组字符串 [{"app_id": "...", "enabled": true}, ...]，
        ## 数组顺序即执行顺序；enabled=false 的任务由 zzz-od 跳过）
        self.OneDragon_AppList = ConfigItem("OneDragon", "AppList", "[]")

        ## Data ------------------------------------------------------------
        self.Data_LastProxyDate = ConfigItem(
            "Data", "LastProxyDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        self.Data_ProxyTimes = ConfigItem(
            "Data", "ProxyTimes", 0, RangeValidator(0, 9999)
        )
        self.Data_LastProxyStatus = ConfigItem(
            "Data",
            "LastProxyStatus",
            "未知",
            OptionsValidator(["未知", "成功", "失败"]),
        )
        ## 智能启动器模式最近一次成功运行的启动器（""=尚未记录；下次智能优先用它）
        self.Data_LauncherLastGood = ConfigItem(
            "Data",
            "LauncherLastGood",
            "",
            OptionsValidator(["", "原始", "集成"]),
        )

        ## Notify ----------------------------------------------------------
        ## 是否启用用户通知
        self.Notify_Enabled = ConfigItem("Notify", "Enabled", False, BoolValidator())
        ## 任务报告节点详情的推送模式（运行记录 diff 出的各任务结果）：
        ## 关闭 = 不采集；逐条 = 逐条带回时间戳；汇总 = 按状态聚合
        self.Notify_PushLogMode = ConfigItem(
            "Notify",
            "PushLogMode",
            "汇总",
            OptionsValidator(["关闭", "逐条", "汇总"]),
        )
        ## 是否发送用户统计信息
        self.Notify_IfSendStatistic = ConfigItem(
            "Notify", "IfSendStatistic", False, BoolValidator()
        )
        ## 是否发送邮件
        self.Notify_IfSendMail = ConfigItem(
            "Notify", "IfSendMail", False, BoolValidator()
        )
        ## 用户收件地址
        self.Notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
        ## 是否启用 Server 酱
        self.Notify_IfServerChan = ConfigItem(
            "Notify", "IfServerChan", False, BoolValidator()
        )
        ## Server 酱密钥
        self.Notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
        ## 用户自定义 Webhook 列表
        self.Notify_CustomWebhooks = MultipleConfig([Webhook])

        super().__init__()

    def getTags(self) -> str:
        tags = []

        last_status = self.get("Data", "LastProxyStatus")
        tags.append(
            {
                "text": f"上次：{last_status}",
                "color": "red" if last_status == "失败" else "green",
            }
        )

        mode = str(self.get("Info", "Mode") or "用户")
        if mode == "用户":
            ## 一条龙任务编排仅用户模式消费（直控事实源是原生配置，MAS 字段会失真）
            try:
                app_list = json.loads(self.get("OneDragon", "AppList") or "[]")
            except (TypeError, ValueError):
                app_list = []
            if not isinstance(app_list, list):
                app_list = []
            enabled_count = sum(
                1 for item in app_list if isinstance(item, dict) and item.get("enabled")
            )
            if enabled_count > 0:
                tags.append({"text": f"一条龙：{enabled_count} 项", "color": "orange"})
            else:
                tags.append({"text": "一条龙：未编排", "color": "orange"})

        remained_day = self.get("Info", "RemainedDay")
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
        tags.append(
            {
                "text": (
                    f"剩余天数：{remained_day}天"
                    if remained_day >= 0
                    else "剩余天数：无期限"
                ),
                "color": tag_color,
            }
        )

        notes = self.get("Info", "Notes")
        tags.append(
            {
                "text": (
                    f"备注：{notes}" if len(notes) <= 20 else f"备注：{notes[:20]}..."
                ),
                "color": "pink",
            }
        )

        return json.dumps(tags, ensure_ascii=False)


class ZzzOdConfig(ConfigBase):
    """绝区零一条龙配置（zzz-od 线）"""

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 脚本名称
        self.Info_Name = ConfigItem("Info", "Name", "新绝区零一条龙脚本")
        ## zzz-od 安装根目录（含 OneDragon 启动器、src 与 config）
        self.Info_RootPath = ConfigItem("Info", "RootPath", "", FolderValidator())

        ## Game ------------------------------------------------------------
        ## 是否由 MAS 管理游戏进程（任务前启动游戏由此开关总控）
        self.Game_Enabled = ConfigItem("Game", "Enabled", False, BoolValidator())
        ## 任务前由 MAS 启动游戏（检测到游戏进程正在运行时跳过重复启动）
        self.Game_LaunchBeforeTask = ConfigItem(
            "Game", "LaunchBeforeTask", False, BoolValidator()
        )
        ## 游戏路径（游戏本体 ZenlessZoneZero.exe）
        self.Game_Path = ConfigItem("Game", "Path", "", FileValidator())
        ## 游戏启动参数
        self.Game_Arguments = ConfigItem("Game", "Arguments", "", ArgumentValidator())
        ## 启动游戏后的等待时间（秒）
        self.Game_WaitTime = ConfigItem("Game", "WaitTime", 60, RangeValidator(0, 9999))
        ## 任务结束后由 MAS 关闭游戏（收尾/手动停止时按进程名结束游戏本体，
        ## 不再委托一条龙 --close-game）
        self.Game_CloseOnFinish = ConfigItem(
            "Game", "CloseOnFinish", True, BoolValidator()
        )
        ## 多用户账号切换方式（脚本级下拉，value 对应 manager 的分派分支）：
        ## 单实例切换（默认，推荐）= 逐用户独立会话：注入该用户配置 → 单实例
        ##   运行（仅运行当前，无槽间切换）→ 跑完关闭 → 下一个用户。失败域
        ##   隔离最好，重试只重启失败用户；
        ## 多实例切换（不推荐）= 全部启用用户合并为一轮多账号运行，一条龙内部
        ##   依次切换账号。总时长最短，但单槽失败会拖整轮重试、切换次数随
        ##   用户数线性增长；
        ## MAS切换 = MAS 侧 OCR 操控游戏完成账号切换后交一条龙运行（暂未开放）。
        self.Game_AccountSwitch = ConfigItem(
            "Game",
            "AccountSwitch",
            "单实例切换",
            OptionsValidator(["单实例切换", "多实例切换", "MAS切换"]),
        )

        ## Run -------------------------------------------------------------
        ## 每日代理次数上限
        self.Run_ProxyTimesLimit = ConfigItem(
            "Run", "ProxyTimesLimit", 0, RangeValidator(0, 9999)
        )
        ## 单次任务重试次数
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 3, RangeValidator(1, 9999)
        )
        ## 单次运行超时时间（分钟）；这是日志停滞超时（latest_time 距今），不是
        ## 总时长上限——一条龙持续写日志就不会触发；启动器层故障（不写应用层
        ## 日志）也靠它兜底超时后切换启动器
        self.Run_RunTimeLimit = ConfigItem(
            "Run", "RunTimeLimit", 40, RangeValidator(1, 9999)
        )

        self.UserData = MultipleConfig([ZzzOdUserConfig])

        super().__init__()


class GameSignAccountGroup(ConfigBase):
    """游戏社区账号组配置"""

    def __init__(self) -> None:

        ## GameSignAccount - 账号组名称
        self.Name = ConfigItem("GameSignAccount", "Name", "用户 1", StringValidator())
        ## GameSignAccount - 是否启用（该用户是否参与签到）
        self.Enabled = ConfigItem("GameSignAccount", "Enabled", True, BoolValidator())
        ## GameSignAccount - 米游社登录凭证 (DPAPI 加密)
        self.MiyousheToken = ConfigItem(
            "GameSignAccount", "MiyousheToken", "", EncryptValidator()
        )
        ## GameSignAccount - 米游社安卓设备 ID (DPAPI 加密，仅用于绝区零便笺)
        self.MiyousheDeviceId = ConfigItem(
            "GameSignAccount", "MiyousheDeviceId", "", EncryptValidator()
        )
        ## GameSignAccount - 米游社安卓设备指纹 (DPAPI 加密，仅用于绝区零便笺)
        self.MiyousheDeviceFp = ConfigItem(
            "GameSignAccount", "MiyousheDeviceFp", "", EncryptValidator()
        )
        ## GameSignAccount - 云原神 combo token (DPAPI 加密)
        self.CloudGenshinToken = ConfigItem(
            "GameSignAccount", "CloudGenshinToken", "", EncryptValidator()
        )
        ## GameSignAccount - 库街区登录凭证 (DPAPI 加密)
        self.KuroToken = ConfigItem(
            "GameSignAccount", "KuroToken", "", EncryptValidator()
        )
        ## GameSignAccount - 森空岛登录凭证 (DPAPI 加密)
        self.SklandToken = ConfigItem(
            "GameSignAccount", "SklandToken", "", EncryptValidator()
        )
        ## GameSignAccount - 塔吉多及云异环登录凭证 (DPAPI 加密)
        ## 支持 refreshToken 纯文本或包含 cloudToken/cloudUserId 的 JSON。
        self.TaygedoToken = ConfigItem(
            "GameSignAccount", "TaygedoToken", "", EncryptValidator()
        )
        ## GameSignAccount - 上次签到日期 (按用户隔离，防止重复触发)
        self.LastSignDate = ConfigItem(
            "GameSignAccount",
            "LastSignDate",
            "2000-01-01",
            DateTimeValidator("%Y-%m-%d"),
        )

        super().__init__()


class ToolsConfig(ConfigBase):
    """工具配置"""

    def __init__(self) -> None:

        self.ArknightsPC_Enabled = ConfigItem(
            "ArknightsPC", "Enabled", False, BoolValidator()
        )
        self.ArknightsPC_PauseKey = ConfigItem(
            "ArknightsPC", "PauseKey", "f10", KeyValidator("f10")
        )
        self.ArknightsPC_SelectDeployedKey = ConfigItem(
            "ArknightsPC", "SelectDeployedKey", "w", KeyValidator("w")
        )
        self.ArknightsPC_UseSkillKey = ConfigItem(
            "ArknightsPC", "UseSkillKey", "r", KeyValidator("r")
        )
        self.ArknightsPC_RetreatKey = ConfigItem(
            "ArknightsPC", "RetreatKey", "t", KeyValidator("t")
        )
        self.ArknightsPC_NextFrameKey = ConfigItem(
            "ArknightsPC", "NextFrameKey", "f", KeyValidator("f")
        )
        self.ArknightsPC_AnotherQuitKey = ConfigItem(
            "ArknightsPC", "AnotherQuitKey", "space", KeyValidator("space")
        )
        self.ArknightsPC_Status = ConfigItem(
            "ArknightsPC",
            "Status",
            "-",
            VirtualConfigValidator(self.arknights_pc_status),
        )

        ## GameSign - 启用签到
        self.GameSign_Enabled = ConfigItem(
            "GameSign", "Enabled", False, BoolValidator()
        )
        ## GameSign - 签到后发送通知
        self.GameSign_NotifyEnabled = ConfigItem(
            "GameSign", "NotifyEnabled", False, BoolValidator()
        )
        ## GameSign - 启用日常便笺
        self.GameSign_ActivityEnabled = ConfigItem(
            "GameSign", "ActivityEnabled", True, BoolValidator()
        )
        ## GameSign - 启动时运行
        self.GameSign_RunOnStartup = ConfigItem(
            "GameSign", "RunOnStartup", False, BoolValidator()
        )
        ## GameSign - 是否立即开始
        self.GameSign_AutoStart = ConfigItem(
            "GameSign", "AutoStart", False, BoolValidator()
        )
        ## GameSign - 账号组 (MultipleConfig)
        self.GameSign_Accounts = MultipleConfig([GameSignAccountGroup])
        ## GameSign - 上次签到日期 (防止重复触发)
        self.GameSign_LastSignDate = ConfigItem(
            "GameSign", "LastSignDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        ## GameSign - 签到状态标签 (虚拟字段)
        self.GameSign_Status = ConfigItem(
            "GameSign",
            "Status",
            "-",
            VirtualConfigValidator(self.game_sign_status),
        )
        ## GameSign - 签到结果详情 (虚拟字段)
        self.GameSign_Result = ConfigItem(
            "GameSign",
            "Result",
            "{}",
            VirtualConfigValidator(self.game_sign_result),
        )

        self.arknights_pc_running = False
        self.arknights_pc_get_connected: Callable[[], bool] = lambda: False
        self._game_sign_result_data: dict = {}

        super().__init__()

    @property
    def arknights_pc_connected(self) -> bool:

        return self.arknights_pc_get_connected()

    def arknights_pc_status(self) -> str:

        if not self.get("ArknightsPC", "Enabled"):
            return TagItem(text="未启用", color="gray").model_dump_json()
        else:
            if self.arknights_pc_running:
                if self.arknights_pc_connected:
                    return TagItem(text="运行中", color="green").model_dump_json()
                else:
                    return TagItem(text="未连接", color="red").model_dump_json()
            else:
                return TagItem(text="已暂停", color="yellow").model_dump_json()

    @property
    def arknights_pc_keys(self) -> list[str]:
        """获取明日方舟 PC 按键配置"""

        return [
            self.get("ArknightsPC", _)
            for _ in (
                "SelectDeployedKey",
                "UseSkillKey",
                "RetreatKey",
                "NextFrameKey",
                "AnotherQuitKey",
            )
        ]

    def game_sign_status(self) -> str:
        """游戏社区状态标签"""

        if not self.get("GameSign", "Enabled"):
            return TagItem(text="未启用", color="gray").model_dump_json()
        return TagItem(text="已启用", color="green").model_dump_json()

    def game_sign_result(self) -> str:
        """游戏社区结果 JSON"""

        return json.dumps(self._game_sign_result_data, ensure_ascii=False)


class GlobalConfig(ConfigBase):
    """全局配置"""

    def __init__(self):

        ## Function ---------------------------------------------------------
        ## 历史记录保留时间（天）
        self.Function_HistoryRetentionTime = ConfigItem(
            "Function",
            "HistoryRetentionTime",
            0,
            OptionsValidator([7, 15, 30, 60, 90, 180, 365, 0]),
        )
        ## 是否允许睡眠
        self.Function_IfAllowSleep = ConfigItem(
            "Function", "IfAllowSleep", False, BoolValidator()
        )
        ## 是否启用静默模式
        self.Function_IfSilence = ConfigItem(
            "Function", "IfSilence", False, BoolValidator()
        )
        ## 是否同意 Bilibili 协议
        self.Function_IfAgreeBilibili = ConfigItem(
            "Function", "IfAgreeBilibili", False, BoolValidator()
        )
        ## 是否屏蔽模拟器广告
        self.Function_IfBlockAd = ConfigItem(
            "Function", "IfBlockAd", False, BoolValidator()
        )
        ## 是否启用匿名遥测
        self.Function_IfEnableTelemetry = ConfigItem(
            "Function", "IfEnableTelemetry", True, BoolValidator()
        )

        ## Display ----------------------------------------------------------
        ## 无人值守时是否允许 MAS 挂载虚拟显示器。
        ## 所有真实显示输出都断开后 Windows 只保留一块占位的幻影屏，它照旧上报正常的
        ## 分辨率但背后没有输出；冷启动时更会起在很小的分辨率上，把被托管的 PC 端游戏
        ## 窗口压小并被游戏写进自己的配置，之后每轮都在同一处失败。挂一块真实的虚拟屏
        ## 可从源头断掉。
        ## 需要用户自行安装 Parsec 虚拟显示驱动，MAS 不分发驱动。
        self.Display_IfEnableVirtualDisplay = ConfigItem(
            "Display", "IfEnableVirtualDisplay", False, BoolValidator()
        )
        ## 虚拟显示器的刷新率（分辨率固定 1920x1080）。
        ## 分辨率固定是因为只有它 Windows 给 100% 缩放，再高会被自动上缩放，游戏窗口
        ## 又要面对 DPI 虚拟化。取值必须在驱动 advertise 的模式表里，否则会被 BADMODE 拒绝。
        self.Display_VirtualDisplayMode = ConfigItem(
            "Display",
            "VirtualDisplayMode",
            "1920x1080@60",
            OptionsValidator(["1920x1080@60", "1920x1080@30"]),
        )

        ## Voice ------------------------------------------------------------
        ## 是否启用语音
        self.Voice_Enabled = ConfigItem("Voice", "Enabled", False, BoolValidator())
        ## 语音类型
        self.Voice_Type = ConfigItem(
            "Voice", "Type", "simple", OptionsValidator(["simple", "noisy"])
        )

        ## Start ------------------------------------------------------------
        ## 是否自动启动
        self.Start_IfSelfStart = ConfigItem(
            "Start", "IfSelfStart", False, BoolValidator()
        )
        ## 是否启动时直接最小化
        self.Start_IfMinimizeDirectly = ConfigItem(
            "Start", "IfMinimizeDirectly", False, BoolValidator()
        )

        ## UI ---------------------------------------------------------------
        ## 是否显示托盘图标
        self.UI_IfShowTray = ConfigItem("UI", "IfShowTray", False, BoolValidator())
        ## 是否关闭到托盘
        self.UI_IfToTray = ConfigItem("UI", "IfToTray", False, BoolValidator())
        ## 是否隐藏主窗口关闭按钮
        self.UI_IfHideCloseButton = ConfigItem(
            "UI", "IfHideCloseButton", False, BoolValidator()
        )

        ## Notify -----------------------------------------------------------
        ## 任务结果推送时间
        self.Notify_SendTaskResultTime = ConfigItem(
            "Notify",
            "SendTaskResultTime",
            "不推送",
            OptionsValidator(["不推送", "任何时刻", "仅失败时"]),
        )
        ## 是否发送统计信息
        self.Notify_IfSendStatistic = ConfigItem(
            "Notify", "IfSendStatistic", False, BoolValidator()
        )
        ## 是否发送六星通知
        self.Notify_IfSendSixStar = ConfigItem(
            "Notify", "IfSendSixStar", False, BoolValidator()
        )
        ## 是否推送系统通知
        self.Notify_IfPushPlyer = ConfigItem(
            "Notify", "IfPushPlyer", False, BoolValidator()
        )
        ## 是否发送邮件
        self.Notify_IfSendMail = ConfigItem(
            "Notify", "IfSendMail", False, BoolValidator()
        )
        ## 是否发送Koishi通知
        self.Notify_IfKoishiSupport = ConfigItem(
            "Notify", "IfKoishiSupport", False, BoolValidator()
        )
        ## Koishi WebSocket 服务器地址
        self.Notify_KoishiServerAddress = ConfigItem(
            "Notify",
            "KoishiServerAddress",
            "ws://localhost:5140/AUTO_MAS",
            URLValidator(),
        )
        ## Koishi Token
        self.Notify_KoishiToken = ConfigItem("Notify", "KoishiToken", "")
        ## 是否启用微信 Claw 通知（凭据由扫码登录流程管理）
        self.Notify_IfOpenClawWeixin = ConfigItem(
            "Notify", "IfOpenClawWeixin", False, BoolValidator()
        )
        ## 是否启用 QQ 官方机器人通知（凭据由扫码登录流程管理）
        self.Notify_IfOpenClawQQ = ConfigItem(
            "Notify", "IfOpenClawQQ", False, BoolValidator()
        )
        ## QQ 官方机器人应用 ID（由扫码登录响应返回）
        self.Notify_OpenClawQQAppId = ConfigItem("Notify", "OpenClawQQAppId", "")
        ## QQ 官方机器人客户端密钥（由扫码登录响应返回）
        self.Notify_OpenClawQQClientSecret = ConfigItem(
            "Notify", "OpenClawQQClientSecret", "", EncryptValidator()
        )
        ## QQ 官方机器人目标用户 OpenID（由扫码登录响应返回）
        self.Notify_OpenClawQQTargetOpenId = ConfigItem(
            "Notify", "OpenClawQQTargetOpenId", ""
        )
        self.Notify_OpenClawWeixinServerAddress = ConfigItem(
            "Notify",
            "OpenClawWeixinServerAddress",
            "https://ilinkai.weixin.qq.com",
            URLValidator(schemes=["https"]),
        )
        self.Notify_OpenClawWeixinBotToken = ConfigItem(
            "Notify", "OpenClawWeixinBotToken", "", EncryptValidator()
        )
        ## 微信 Claw 账号 ID（由二维码登录响应返回）
        self.Notify_OpenClawWeixinAccountId = ConfigItem(
            "Notify", "OpenClawWeixinAccountId", ""
        )
        ## 微信 Claw 用户 ID（由二维码登录响应返回）
        self.Notify_OpenClawWeixinTargetUserId = ConfigItem(
            "Notify", "OpenClawWeixinTargetUserId", ""
        )
        ## SMTP 服务器地址
        self.Notify_SMTPServerAddress = ConfigItem("Notify", "SMTPServerAddress", "")
        ## 邮箱授权码
        self.Notify_AuthorizationCode = ConfigItem(
            "Notify", "AuthorizationCode", "", EncryptValidator()
        )
        ## 发件地址
        self.Notify_FromAddress = ConfigItem("Notify", "FromAddress", "")
        ## 收件地址
        self.Notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
        ## 是否启用 Server 酱
        self.Notify_IfServerChan = ConfigItem(
            "Notify", "IfServerChan", False, BoolValidator()
        )
        ## Server 酱密钥
        self.Notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
        ## 自定义 Webhook 列表
        self.Notify_CustomWebhooks = MultipleConfig([Webhook])

        ## Update -----------------------------------------------------------
        ## 是否自动更新
        self.Update_IfAutoUpdate = ConfigItem(
            "Update", "IfAutoUpdate", False, BoolValidator()
        )
        ## 更新源
        self.Update_Source = ConfigItem(
            "Update",
            "Source",
            "GitHub",
            OptionsValidator(["GitHub", "MirrorChyan", "AutoSite", "CNB"]),
        )
        ## 更新频道
        self.Update_Channel = ConfigItem(
            "Update", "Channel", "stable", OptionsValidator(["stable", "beta"])
        )
        ## 代理地址
        self.Update_ProxyAddress = ConfigItem("Update", "ProxyAddress", "")
        ## 镜像站 CDK
        self.Update_MirrorChyanCDK = ConfigItem(
            "Update", "MirrorChyanCDK", "", EncryptValidator()
        )

        ## Data -------------------------------------------------------------
        ## 唯一标识符
        self.Data_UID = ConfigItem("Data", "UID", str(uuid.uuid4()), UUIDValidator())
        ## 上次统计上传时间
        self.Data_LastStatisticsUpload = ConfigItem(
            "Data",
            "LastStatisticsUpload",
            "2000-01-01 00:00:00",
            DateTimeValidator("%Y-%m-%d %H:%M:%S"),
        )
        ## 上次关卡更新时间
        self.Data_LastStageUpdated = ConfigItem(
            "Data",
            "LastStageUpdated",
            "2000-01-01 00:00:00",
            DateTimeValidator("%Y-%m-%d %H:%M:%S"),
        )
        ## 关卡数据的版本标识符
        self.Data_StageETag = ConfigItem("Data", "StageETag", "")
        ## 关卡信息数据
        self.Data_StageData = ConfigItem(
            "Data", "StageData", "{ }", JSONValidator(), legacy_name="Stage"
        )
        ## 关卡信息
        self.Data_Stage = ConfigItem(
            "Data", "Stage", "-", VirtualConfigValidator(self.getStage)
        )
        ## 上次公告更新时间
        self.Data_LastNoticeUpdated = ConfigItem(
            "Data",
            "LastNoticeUpdated",
            "2000-01-01 00:00:00",
            DateTimeValidator("%Y-%m-%d %H:%M:%S"),
        )
        ## 公告的版本标识符
        self.Data_NoticeETag = ConfigItem("Data", "NoticeETag", "")
        ## 是否显示公告
        self.Data_IfShowNotice = ConfigItem(
            "Data", "IfShowNotice", True, BoolValidator()
        )
        ## 公告内容
        self.Data_Notice = ConfigItem("Data", "Notice", "{ }", JSONValidator())
        ## 上次 Web 配置更新时间
        self.Data_LastWebConfigUpdated = ConfigItem(
            "Data",
            "LastWebConfigUpdated",
            "2000-01-01 00:00:00",
            DateTimeValidator("%Y-%m-%d %H:%M:%S"),
        )
        ## Web 配置
        self.Data_WebConfig = ConfigItem(
            "Data", "WebConfig", "[ ]", JSONValidator(list)
        )
        super().__init__()

        ## 模拟器配置列表
        self.EmulatorConfig = MultipleConfig([EmulatorConfig])
        ## 计划表配置列表
        self.PlanConfig = MultipleConfig(
            [item["config_class"] for item in PLAN_BOOK.values()]
        )
        ## 脚本配置列表
        self.ScriptConfig = MultipleConfig(
            [
                MaaConfig,
                MaaEndConfig,
                SrcConfig,
                M9AConfig,
                MaaFWConfig,
                GeneralConfig,
                OkwwConfig,
                OkNteConfig,
                HSRConfig,
                BetterGIConfig,
                ZzzOdConfig,
                BAAHConfig,
            ]
        )
        ## 队列配置列表
        self.QueueConfig = MultipleConfig([QueueConfig])
        ## 工具箱配置
        self.ToolsConfig = ToolsConfig()

        MaaConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        MaaEndConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        SrcConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        M9AConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        MaaFWConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        GeneralConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        BAAHConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        MaaUserConfig.related_config["PlanConfig"] = self.PlanConfig
        MaaEndUserConfig.related_config["PlanConfig"] = self.PlanConfig
        QueueItem.related_config["ScriptConfig"] = self.ScriptConfig

    def getStage(self) -> str:
        """获取关卡信息"""

        try:
            raw_stage_data = json.loads(self.get("Data", "StageData"))
            if "Official" in raw_stage_data:
                stage_data_by_server = {
                    server: data.get("sideStoryStage", {})
                    for server, data in raw_stage_data.items()
                    if isinstance(data, dict)
                }
            else:
                stage_data_by_server = {"Official": raw_stage_data}

            all_stage_data = {}
            for server, server_stage_data in stage_data_by_server.items():
                activity_stage_drop_info = []
                activity_stage_combox = []

                for side_story in server_stage_data.values():
                    activity = side_story["Activity"]
                    activity_timezone = timezone(
                        timedelta(hours=activity.get("TimeZone", 8))
                    )
                    if (
                        datetime.strptime(
                            activity["UtcStartTime"], "%Y/%m/%d %H:%M:%S"
                        ).replace(tzinfo=activity_timezone)
                        < datetime.now(tz=activity_timezone)
                        < datetime.strptime(
                            activity["UtcExpireTime"], "%Y/%m/%d %H:%M:%S"
                        ).replace(tzinfo=activity_timezone)
                    ):
                        for stage in side_story["Stages"]:
                            activity_stage_combox.append(
                                {"label": stage["Display"], "value": stage["Value"]}
                            )

                            if "SSReopen" not in stage["Display"]:
                                if stage["Drop"] in MATERIALS_MAP:
                                    drop_id = stage["Drop"]
                                elif "玉" in stage["Drop"]:
                                    drop_id = "30012"
                                else:
                                    drop_id = "NotFound"

                                activity_stage_drop_info.append(
                                    {
                                        "Display": stage["Display"],
                                        "Value": stage["Value"],
                                        "Drop": drop_id,
                                        "DropName": MATERIALS_MAP.get(
                                            stage["Drop"], stage["Drop"]
                                        ),
                                        "Activity": activity,
                                    }
                                )

                stage_data = {"Info": activity_stage_drop_info}

                for day in range(0, 8):
                    res_stage = []

                    for stage in RESOURCE_STAGE_INFO:
                        if day in stage["days"] or day == 0:
                            res_stage.append(
                                {"label": stage["text"], "value": stage["value"]}
                            )

                    stage_data[calendar.day_name[day - 1] if day > 0 else "ALL"] = (
                        res_stage[0:1] + activity_stage_combox + res_stage[1:]
                    )

                all_stage_data[server] = stage_data
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning(
                f"解析活动关卡信息失败, 按空关卡处理: {type(e).__name__}: {e}"
            )
            return "{ }"

        return json.dumps(all_stage_data, ensure_ascii=False)


class BAAHUserConfig(ConfigBase):
    """BAAH 用户配置"""

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 用户名称
        self.Info_Name = ConfigItem("Info", "Name", "新用户", UserNameValidator())
        ## 是否启用
        self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
        ## 剩余天数
        self.Info_RemainedDay = ConfigItem(
            "Info", "RemainedDay", -1, RangeValidator(-1, 9999)
        )
        ## BAAH 配置文件名（BAAH_CONFIGS 目录下的文件名，不含 .json 后缀）
        self.Info_ConfigName = ConfigItem("Info", "ConfigName", "")
        ## 备注
        self.Info_Notes = ConfigItem("Info", "Notes", "无")
        ## 用户标签信息
        self.Info_Tag = ConfigItem(
            "Info", "Tag", "[ ]", VirtualConfigValidator(self.getTags)
        )

        ## Data ------------------------------------------------------------
        ## 上次代理日期
        self.Data_LastProxyDate = ConfigItem(
            "Data", "LastProxyDate", "2000-01-01", DateTimeValidator("%Y-%m-%d")
        )
        ## 代理次数
        self.Data_ProxyTimes = ConfigItem(
            "Data", "ProxyTimes", 0, RangeValidator(0, 9999)
        )

        ## Notify ----------------------------------------------------------
        ## 是否启用通知
        self.Notify_Enabled = ConfigItem("Notify", "Enabled", False, BoolValidator())
        ## 是否发送统计信息
        self.Notify_IfSendStatistic = ConfigItem(
            "Notify", "IfSendStatistic", False, BoolValidator()
        )
        ## 是否发送邮件
        self.Notify_IfSendMail = ConfigItem(
            "Notify", "IfSendMail", False, BoolValidator()
        )
        ## 收件地址
        self.Notify_ToAddress = ConfigItem("Notify", "ToAddress", "")
        ## 是否启用 Server 酱
        self.Notify_IfServerChan = ConfigItem(
            "Notify", "IfServerChan", False, BoolValidator()
        )
        ## Server 酱密钥
        self.Notify_ServerChanKey = ConfigItem("Notify", "ServerChanKey", "")
        ## 自定义 Webhook 列表
        self.Notify_CustomWebhooks = MultipleConfig([Webhook])

        super().__init__()

    def getTags(self) -> str:
        """生成 BAAH 用户标签列表"""
        tags = []

        # 任务代理标签（使用东4区时间）
        tags.append(_tag_proxy(self, "任务"))

        # 剩余天数标签
        tags.append(_tag_remained_days(self))

        # 备注标签
        tags.append(_tag_notes(self))

        return json.dumps(tags, ensure_ascii=False)


class BAAHConfig(ConfigBase):
    """BAAH 配置"""

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## 脚本名称
        self.Info_Name = ConfigItem("Info", "Name", "新 BAAH 脚本")

        ## Script ----------------------------------------------------------
        ## BAAH 主程序路径；程序目录、配置目录与日志目录都从它派生
        self.Script_BAAHPath = ConfigItem("Script", "BAAHPath", "", FileValidator())
        ## 是否由本软件托管运行所需的关键配置项
        self.Script_IfManageConfig = ConfigItem(
            "Script", "IfManageConfig", True, BoolValidator()
        )
        ## 是否在任务报告中展示 BAAH 的任务节点详情
        self.Script_PushLogEnabled = ConfigItem(
            "Script", "PushLogEnabled", True, BoolValidator()
        )

        ## Run -------------------------------------------------------------
        ## 运行次数限制
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 2, RangeValidator(1, 9999)
        )
        ## 运行时间限制（分钟）
        self.Run_RunTimeLimit = ConfigItem(
            "Run", "RunTimeLimit", 60, RangeValidator(1, 9999)
        )

        ## Emulator --------------------------------------------------------
        ## 模拟器 ID
        self.Emulator_Id = ConfigItem(
            "Emulator",
            "Id",
            "-",
            MultipleUIDValidator("-", self.related_config, "EmulatorConfig"),
        )
        ## 模拟器索引
        self.Emulator_Index = ConfigItem("Emulator", "Index", "-")

        self.UserData = MultipleConfig([BAAHUserConfig])

        super().__init__()


CLASS_BOOK = {
    "MAA": MaaConfig,
    "SRC": SrcConfig,
    "MaaEnd": MaaEndConfig,
    "M9A": M9AConfig,
    "MaaFW": MaaFWConfig,
    "General": GeneralConfig,
    "Okww": OkwwConfig,
    "OkNte": OkNteConfig,
    "HSR": HSRConfig,
    "BetterGI": BetterGIConfig,
    "ZzzOd": ZzzOdConfig,
    "BAAH": BAAHConfig,
}
"""配置类映射表"""

PLAN_BOOK = {
    "MaaPlanConfig": {
        "create_type": "MaaPlan",
        "config_class": MaaPlanConfig,
        "schema_class": schema_model.MaaPlanConfig,
        "consumer": PLAN_CONSUMER_VALUES[0],
        "script_class": MaaConfig,
        "field_name": "StageMode",
    },
    "MaaEndPlanConfig": {
        "create_type": "MaaEndPlan",
        "config_class": MaaEndPlanConfig,
        "schema_class": schema_model.MaaEndPlanConfig,
        "consumer": PLAN_CONSUMER_VALUES[1],
        "script_class": MaaEndConfig,
        "field_name": "SanityMode",
    },
}
"""计划表注册表"""
