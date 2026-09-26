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
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any, Callable

from app.utils import get_logger
from app.utils.constants import (
    CYCLE_EMPTY_TIME,
    MAA_STAGE_KEY,
    MAAEND_AUTO_COLLECT_MODES,
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
    MSS_DEFAULT_TRIBULATION_STAGE,
    MSS_TRIBULATION_STAGES,
    PLAN_CONSUMER_VALUES,
    RESOURCE_STAGE_INFO,
    STARRAIL_STAGE_BOOK,
    UTC4,
    game_now,
    get_game_day_tz,
)
from app.utils.io import read_file

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


def infrast_plan_mode(plans: list[dict]) -> str:
    """排班表的时段形态: period=全带时段, rotate=全不带, mixed=混合, empty=无班次。

    前提: ``plans`` 元素为 dict(``infrast_format_problem`` 已先行校验)。
    """

    if not plans:
        return "empty"
    has_period = [bool(plan.get("period")) for plan in plans]
    if all(has_period):
        return "period"
    if any(has_period):
        return "mixed"
    return "rotate"


def _is_infrast_time(value: Any) -> bool:
    """是否为 MAA 时间字段可解析的值(TimeOnly.Parse 接受 HH:MM[:SS[.fff]])。

    不用 ``time.fromisoformat``: 它拒绝上游接受的 ``8:00``, 却接受上游拒绝的
    ``2000`` / ``20-00``, 两边松紧正好相反。先 strip 对齐 .NET Parse 会跳过
    首尾空白的行为, 避免把上游能解析的值误判为坏值。
    """

    if not isinstance(value, str):
        return False
    value = value.strip()
    for time_format in ("%H:%M", "%H:%M:%S", "%H:%M:%S.%f"):
        try:
            datetime.strptime(value, time_format)
        except ValueError:
            continue
        return True
    return False


def _is_infrast_period(period: Any) -> bool:
    """period 是否为 MAA 可解析的时段表: 每段恰两个时间字符串(TimeOnly[])。

    MAA 的 TimeOnlyArrayListConverter 只接受 ``[["HH:MM", "HH:MM"], ...]``,
    段长不为 2 或时间无法解析都会抛异常, 连累整份排班在 MAA 侧反序列化失败
    (自愈为 0 且班次表为空), 因此这里按上游契约严格校验。
    """

    if period is None:
        return True
    if not isinstance(period, list):
        return False
    return all(
        isinstance(segment, list)
        and len(segment) == 2
        and all(_is_infrast_time(value) for value in segment)
        for segment in period
    )


def infrast_plan_state(custom_infrast: str | None) -> str:
    """排班表状态: period/rotate/mixed(时段不一致, 不可用)/empty(缺省或不可解析)。

    与 ``infrast_format_problem`` 用同一把尺子: 时段形态不合法的表同样按
    empty 处理, 否则运行期已判不可用, 下拉提示却还在宣称按时间段换班。
    """

    try:
        data = json.loads(custom_infrast)
    except (json.JSONDecodeError, TypeError):
        return "empty"
    plans = data.get("plans") if isinstance(data, dict) else None
    if not isinstance(plans, list) or not all(isinstance(plan, dict) for plan in plans):
        return "empty"
    if not all(_is_infrast_period(plan.get("period")) for plan in plans):
        return "empty"
    return infrast_plan_mode(plans)


def infrast_format_problem(infrast_data: Any) -> str | None:
    """校验自定义基建排班表的格式不变量, 返回问题描述; None 表示格式可用。

    不变量: plans 非空且元素为对象, 各班次要么全部带 period 要么全部不带,
    且 period 是 MAA 可解析的时段表(每段恰两个时间字符串)。
    混合格式在 MAA 侧会被静默按"有时段的班按时段命中, 其余永不命中"解释,
    MAS 不猜测这种意图, 统一按无效处理。
    """
    if not isinstance(infrast_data, dict):
        return "排班表不是有效的 JSON 对象"
    plans = infrast_data.get("plans")
    if not isinstance(plans, list) or not plans:
        return "排班表没有任何班次"
    if not all(isinstance(plan, dict) for plan in plans):
        return "排班表的班次格式不正确"
    if not all(_is_infrast_period(plan.get("period")) for plan in plans):
        return "排班表的时间段格式不正确（每段应为起止两个 HH:MM 时间）"
    if infrast_plan_mode(plans) == "mixed":
        return "排班表时段配置不一致（部分班次有时间段、部分没有）"
    return None


def load_infrast_plans(custom_infrast: str | None) -> tuple[list[dict], str | None]:
    """解析自定义基建排班 JSON, 返回 (plans, problem); problem 非 None 时 plans 为 []。"""
    try:
        data = json.loads(custom_infrast)
    except (json.JSONDecodeError, TypeError):
        return [], "排班表不是有效的 JSON"
    problem = infrast_format_problem(data)
    if problem is not None:
        return [], problem
    return data.get("plans", []), None


def read_maa_config(path: Path) -> dict | None:
    """读取 MAA gui.new.json 配置; 缺失或损坏返回 None(损坏另记警告)。"""

    try:
        data = read_file(path)
    except (OSError, json.JSONDecodeError):
        logger.opt(exception=True).warning(f"读取 MAA 配置失败: {path}")
        return None
    return data if isinstance(data, dict) and data else None


def maa_scheme_name(config_dir: Path, data: dict) -> str:
    """MAA 生效方案名, 与 AutoProxy.set_maa 的方案归一判定对称。

    多方案配置下 set_maa 把 gui.json 的 Current 方案复制进 gui.new.json 的
    Default 再注入, 故运行时读到的队列就是 Current 方案(该方案不在
    gui.new.json 里时才是 Default)。读取与回写都要落在同一方案, 否则写进去的
    班次会被方案归一覆盖。``data`` 为已读取的 gui.new.json 内容。
    """

    try:
        gui = read_file(config_dir / "gui.json")
    except (OSError, json.JSONDecodeError):
        return "Default"
    current = gui.get("Current") if isinstance(gui, dict) else None
    configurations = data.get("Configurations")
    if (
        isinstance(current, str)
        and current not in ("", "Default")
        and isinstance(configurations, dict)
        and isinstance(configurations.get(current), dict)
    ):
        return current
    return "Default"


def maa_task_queue(data: dict, scheme: str) -> Any:
    """取 MAA 配置中指定方案的任务队列; 结构不符返回 None。"""

    configurations = data.get("Configurations")
    if not isinstance(configurations, dict):
        return None
    configuration = configurations.get(scheme)
    if not isinstance(configuration, dict):
        return None
    return configuration.get("TaskQueue")


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
        None,  # 未配置时采用安装版本的默认路线，空列表表示不采集
        StringListValidator(allow_none=True),
    )
    ## 自动采集通用资源路线
    config.Task_AutoCollectCommonRoutes = ConfigItem(
        "Task",
        "AutoCollectCommonRoutes",
        None,  # 未配置时采用安装版本的默认路线，空列表表示不采集
        StringListValidator(allow_none=True),
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
        ## 启动 MuMu 实例前先关闭已在运行的实例并强力清理残留进程
        ## 用于已有非管理员实例导致新实例无法以管理员身份启动的场景; 会关掉全部实例, 多开慎用
        self.Info_ForceKillBeforeLaunch = ConfigItem(
            "Info", "ForceKillBeforeLaunch", False, BoolValidator()
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


def _tag_last_status(status: object) -> str:
    """「上次」标签文案。存储值的默认是「未知」，但从没跑过的用户显示「未知」很怪，
    页面上写成「未运行」；其余状态（成功 / 失败 / 运行中）原样。"""

    text = str(status or "").strip()
    return "未运行" if text in ("", "未知") else text


def _tag_proxy(config: ConfigBase, label: str = "日常", tz: tzinfo = UTC4) -> dict:
    """上次代理标签（默认使用东4区时间，tz 为游戏日时区），label 区分日常/任务文案。"""
    if (
        datetime.strptime(config.get("Data", "LastProxyDate"), "%Y-%m-%d").date()
        == datetime.now(tz=tz).date()
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
        ## 配置来源（脚本/用户/直控）
        self.Info_Mode = ConfigItem("Info", "Mode", "脚本", OkwwConfigModeValidator())
        ## 是否启用快速配置（与配置来源独立，按用户保存）
        self.Info_IfQuickConfig = ConfigItem(
            "Info", "IfQuickConfig", True, BoolValidator()
        )
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
        ## 养成接管提示（注入时写入，供前端展示接管态；空 = 未接管）
        self.Data_CultivateNotice = ConfigItem("Data", "CultivateNotice", "")
        ## 自定义基建配置
        self.Data_CustomInfrast = ConfigItem(
            "Data", "CustomInfrast", "{ }", JSONValidator()
        )
        ## 无时段排班表下一班的索引：每用户一份、由 MAS 在基建换班完成后推进；
        ## 带时段表交 MAA 按时段选班，不读它
        self.Data_InfrastPlanIndex = ConfigItem(
            "Data", "InfrastPlanIndex", 0, RangeValidator(0, 9999)
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
        ## 公开招募是否自动确认六星（MAA 界面无法勾选，暂只经接口设置）
        self.Task_IfRecruitSixStar = ConfigItem(
            "Task", "IfRecruitSixStar", False, BoolValidator()
        )
        ## 是否信用收支
        self.Task_IfMall = ConfigItem("Task", "IfMall", True, BoolValidator())
        ## 是否领取奖励
        self.Task_IfAward = ConfigItem("Task", "IfAward", True, BoolValidator())
        ## 是否更换主题（主题名称在 MAA 侧配置，MAS 仅透传）
        self.Task_IfSwitchTheme = ConfigItem(
            "Task", "IfSwitchTheme", False, BoolValidator()
        )
        ## 是否库存保持
        self.Task_IfDepotMaintain = ConfigItem(
            "Task", "IfDepotMaintain", False, BoolValidator()
        )
        ## 库存保持计划（快速配置面板维护；MAA 侧同名 PlanList 为透传载体）
        self.Task_DepotMaintainPlans = ConfigItem(
            "Task", "DepotMaintainPlans", "[]", JSONValidator(list)
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
        ## 是否干员养成
        self.Task_IfCultivate = ConfigItem(
            "Task", "IfCultivate", False, BoolValidator()
        )
        ## 干员养成目标
        self.Task_CultivateTargets = ConfigItem(
            "Task", "CultivateTargets", "[]", JSONValidator(list)
        )
        ## 活动期间是否跳过养成计划
        self.Task_CultivateSkipDuringActivity = ConfigItem(
            "Task", "CultivateSkipDuringActivity", False, BoolValidator()
        )
        ## 资源收集期是否跳过养成计划
        self.Task_CultivateSkipDuringResourceCollection = ConfigItem(
            "Task", "CultivateSkipDuringResourceCollection", False, BoolValidator()
        )
        ## 森空岛绑定：签到账号组 UUID（凭据引用，凭据本体只存签到域）
        self.Task_CultivateSklandAccount = ConfigItem(
            "Task", "CultivateSklandAccount", "", StringValidator()
        )
        ## 森空岛绑定：绑定角色的游戏 uid（非森空岛 userId）
        self.Task_CultivateSklandUid = ConfigItem(
            "Task", "CultivateSklandUid", "", StringValidator()
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

    def getTags(self) -> str:
        """生成用户标签列表，返回JSON字符串格式的TagItem列表"""
        tags = []

        # 日常代理标签（按区服的游戏日时区）
        tags.append(_tag_proxy(self, tz=get_game_day_tz(self.get("Info", "Server"))))

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
                        plan.get_current_info(
                            stage_key, server=self.get("Info", "Server")
                        ).getValue()
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


class ConfigSourceValidator(OptionsValidator):
    """配置来源校验器, 支持两态或三态, 并兼容旧版来源名。

    Args:
        modes: 允许的配置来源。三态=脚本/用户/直控, 两态=用户/直控。
        legacy_map: 旧版来源名到新名的映射, 加载时自动归一。
    """

    def __init__(
        self, modes: tuple[str, ...], legacy_map: dict[str, str] | None = None
    ) -> None:
        super().__init__(list(modes))
        self.legacy_map = legacy_map or {}

    def correct(self, value: Any) -> Any:
        if value in self.legacy_map:
            return self.legacy_map[value]
        return super().correct(value)


class MaaEndConfigModeValidator(ConfigSourceValidator):
    """脚本/用户/直控配置来源（兼容旧版“简洁/详细/自定义”）。"""

    def __init__(self) -> None:
        super().__init__(
            ("脚本", "用户", "直控"),
            {"简洁": "脚本", "详细": "用户", "自定义": "用户"},
        )


class UserDirectConfigModeValidator(ConfigSourceValidator):
    """脚本/用户/直控配置来源。"""

    def __init__(self) -> None:
        super().__init__(("脚本", "用户", "直控"))


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
        ## 任务报告节点详情的推送模式（log_box 采集的关键节点）：
        ## 关闭 = 不采集；逐条 = 采集并逐条带回时间戳；汇总 = 采集并按状态聚合
        self.Notify_PushLogMode = ConfigItem(
            "Notify",
            "PushLogMode",
            "汇总",
            OptionsValidator(["关闭", "逐条", "汇总"]),
        )
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
                "text": f"上次：{_tag_last_status(self.get('Data', 'LastProxyStatus'))}",
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

            if (
                sanity_task_type == "Essence"
                and task_key.get("AutoEssenceMenu") == "Target"
            ):
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
        ## 账号切换方式（默认使用 MAAEND，MAS 为兼容入口）
        self.Run_AccountSwitchMethod = ConfigItem(
            "Run",
            "AccountSwitchMethod",
            "MAAEND",
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
        ## 是否在启动游戏时执行 MaaEnd 分辨率设置预任务
        self.Game_SetResolution = ConfigItem(
            "Game", "SetResolution", False, BoolValidator()
        )
        ## 结束后是否关闭游戏
        self.Game_CloseOnFinish = ConfigItem(
            "Game", "CloseOnFinish", True, BoolValidator()
        )

        ## 关闭游戏时恢复的显示模式，与具体分辨率独立配置
        self.Game_RestoreDisplayType = ConfigItem(
            "Game",
            "RestoreDisplayType",
            "Window",
            OptionsValidator(["Window", "Fullscreen"]),
        )
        ## 关闭游戏时恢复分辨率；Original 复用启动前读取的注册表值
        self.Game_RestoreResolution = ConfigItem(
            "Game",
            "RestoreResolution",
            "Off",
            OptionsValidator(
                [
                    "Off",
                    "Original",
                    "1920x1080",
                    "2560x1440",
                    "3840x2160",
                    "Custom",
                ]
            ),
        )
        ## 自定义恢复分辨率宽度
        self.Game_RestoreResolutionWidth = ConfigItem(
            "Game", "RestoreResolutionWidth", 1920, RangeValidator(1, 16384)
        )
        ## 自定义恢复分辨率高度
        self.Game_RestoreResolutionHeight = ConfigItem(
            "Game", "RestoreResolutionHeight", 1080, RangeValidator(1, 16384)
        )

        self.UserData = MultipleConfig([MaaEndUserConfig])

        super().__init__()

    async def load(self, data: dict) -> bool:
        data = deepcopy(data)
        game_data = data.get("Game") if isinstance(data, dict) else None
        migrated = (
            isinstance(game_data, dict)
            and game_data.get("RestoreResolution") == "Fullscreen"
        )
        if migrated:
            game_data["RestoreDisplayType"] = "Fullscreen"
            game_data["RestoreResolution"] = "1920x1080"
        is_dirty = await super().load(data)
        if migrated and not is_dirty:
            await self._commit_changes()
        root_path_value = str(self.get("Info", "Path")).strip()
        resource_interface_path = Path(root_path_value) / "interface.json"
        if root_path_value and resource_interface_path.is_file():
            # 预加载搬入后台：MaaEnd 资源链的 import（约 270ms）与磁盘读取
            # 不再阻塞启动路径，资源就绪后仍会缓存到用户配置
            self._preload_task = asyncio.create_task(self.preload_resource())
        return is_dirty or migrated

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
        ## 配置来源（脚本/用户/直控）
        self.Info_Mode = ConfigItem("Info", "Mode", "脚本", OkwwConfigModeValidator())
        ## 是否启用快速配置（与配置来源独立，按用户保存）
        self.Info_IfQuickConfig = ConfigItem(
            "Info", "IfQuickConfig", True, BoolValidator()
        )
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
        ## 是否在登录游戏前检查游戏更新
        self.Run_IfCheckGameUpdate = ConfigItem(
            "Run", "IfCheckGameUpdate", False, BoolValidator()
        )
        ## 版本落后时是否由 MAS 自动下载并安装安装包
        self.Run_IfAutoInstallGameApk = ConfigItem(
            "Run", "IfAutoInstallGameApk", False, BoolValidator()
        )
        ## 游戏更新时间限制（分钟）
        self.Run_GameUpdateTimeLimit = ConfigItem(
            "Run", "GameUpdateTimeLimit", 60, RangeValidator(1, 9999)
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


def declare_hsr_plan_items(config: ConfigBase) -> None:
    """声明 HSR「任务计划」配置项，``HSRUserConfig`` 与 ``HSRConfig`` 共用。

    计划 = 任务开关 / 副本 / 历战余响开始日 / 托管覆盖 / 用户级引擎分配。
    配置来源为「用户」时计划读用户配置，为「脚本」时读脚本配置上的同名组
    （本脚本下所有脚本来源用户共用一份）。两边组名、键名、默认值必须完全
    一致，运行时、动态表单与备份才能只换一个对象就复用同一套读取代码，
    所以只在这里单点声明。

    ``Managed.TaskMapping`` 在脚本级是惰性字段：脚本态的引擎分配写脚本级
    ``TaskMapping`` 组，这一项恒为空对象，只为让两份计划形状一致——
    ``resolve_script_assignment`` 读到空对象后自然落到脚本级 ``TaskMapping``。
    """

    ## TaskSwitch ----------------------------------------------------------
    ## 模块执行开关
    config.TaskSwitch_Daily = ConfigItem("TaskSwitch", "Daily", True, BoolValidator())
    config.TaskSwitch_ReceiveRewards = ConfigItem(
        "TaskSwitch", "ReceiveRewards", True, BoolValidator()
    )
    config.TaskSwitch_DivergentUniverse = ConfigItem(
        "TaskSwitch", "DivergentUniverse", False, BoolValidator()
    )
    config.TaskSwitch_CurrencyWars = ConfigItem(
        "TaskSwitch", "CurrencyWars", False, BoolValidator()
    )
    ## Stage ---------------------------------------------------------------
    ## 关卡通道
    config.Stage_Channel = ConfigItem(
        "Stage",
        "Channel",
        "CalyxGolden",
        OptionsValidator(["CalyxGolden", "CalyxCrimson", "Relic", "Ornament"]),
    )
    ## 主刷关卡的脚本原生字段 JSON（SRA: id+level；M7A: instance_type+name）
    config.Stage_ScriptStage = ConfigItem(
        "Stage", "ScriptStage", "{ }", JSONValidator()
    )
    ## 历战余响的脚本原生字段 JSON
    config.Stage_ScriptEchoOfWar = ConfigItem(
        "Stage", "ScriptEchoOfWar", "{ }", JSONValidator()
    )
    ## TaskOpt -------------------------------------------------------------
    ## 历战余响开始刷的星期（周一 ~ 周日）
    config.TaskOpt_EchoOfWarWeekday = ConfigItem(
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
    ## Managed -------------------------------------------------------------
    ## 用户级模块引擎分配覆盖（脚本级恒为空，见上）
    config.Managed_TaskMapping = ConfigItem(
        "Managed", "TaskMapping", "{ }", JSONValidator()
    )
    ## 托管字段覆盖值（运行时叠加到原生配置的临时副本上）
    config.Managed_Options = ConfigItem("Managed", "Options", "{ }", JSONValidator())


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
        ## 配置来源（脚本/用户/直控）：脚本 = 共用脚本级计划；用户 = 本用户
        ## 自己的计划；直控 = 原样运行 SRA / 三月七当前的原生配置
        self.Info_Mode = ConfigItem(
            "Info", "Mode", "脚本", UserDirectConfigModeValidator()
        )
        ## 是否启用快速配置（与配置来源独立，按用户保存）
        self.Info_IfQuickConfig = ConfigItem(
            "Info", "IfQuickConfig", True, BoolValidator()
        )
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

        ## TaskSwitch / Stage / TaskOpt / Managed --------------------------
        ## 用户来源下的任务计划，与 HSRConfig 同名组共用一处声明
        declare_hsr_plan_items(self)

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

        ## Control ---------------------------------------------------------
        ## 直控时运行哪几个引擎；都没勾时回落到已配置路径的引擎
        self.Control_SRA = ConfigItem("Control", "SRA", False, BoolValidator())
        self.Control_M7A = ConfigItem("Control", "M7A", False, BoolValidator())

        ## 兑换码状态指纹（仅状态信息，不保存兑换码明文）
        self.Data_SRARedeemCodeFingerprint = ConfigItem(
            "Data", "SRARedeemCodeFingerprint", ""
        )
        self.Data_M7ARedeemCodeFingerprint = ConfigItem(
            "Data", "M7ARedeemCodeFingerprint", ""
        )

        super().__init__()

    async def load(self, data: dict) -> bool:
        """加载用户配置，并把已删除的旧字段迁移到 ``Info.Mode``。

        迁移直接读磁盘上的原始字典，不依赖旧 ``ConfigItem`` 仍然存在；旧字段
        本身不再声明，下次保存即从文件中消失，迁移天然只发生一次。

        - 旧 ``Control.Mode == "direct"`` → ``Info.Mode = "直控"``，不论
          ``Info.Mode`` 原来是什么：旧版运行时按「``Info.Mode == 直控`` 或
          ``Control.Mode == direct``」判直控，这类用户无论配置来源选了什么
          实际都在跑直控，迁成「直控」才是保持行为不变。
        - 存量记录里没有 ``Info.Mode``（早于三态来源的旧记录）→「用户」：
          这类用户一直按自己的计划运行；新建用户不经过 ``load``，仍取默认
          值「脚本」。
        """

        is_dirty = await super().load(data)

        raw = data if isinstance(data, dict) else {}
        raw_info = raw.get("Info")
        raw_control = raw.get("Control")
        raw_control_mode = (
            str(raw_control.get("Mode") or "").strip().lower()
            if isinstance(raw_control, dict)
            else ""
        )
        if raw_control_mode == "direct":
            if self.get("Info", "Mode") != "直控":
                await self.set("Info", "Mode", "直控")
                is_dirty = True
        elif isinstance(raw_info, dict) and "Mode" not in raw_info:
            if self.get("Info", "Mode") != "用户":
                await self.set("Info", "Mode", "用户")
                is_dirty = True

        # 旧版把 SRA 体力副本的数组位置存成了关卡编号，历战余响与饰品提取整体
        # 错位；repr 形态的旧载荷里带着真实编号，加载时改写（幂等）。
        from app.task.HSR.tools.stage_runtime import migrate_sra_legacy_stage_labels

        for field in ("ScriptStage", "ScriptEchoOfWar"):
            migrated, count, unresolved = migrate_sra_legacy_stage_labels(
                self.get("Stage", field)
            )
            if migrated is not None:
                await self.set("Stage", field, migrated)
                is_dirty = True
                logger.info(
                    f"HSR 用户「{self.get('Info', 'Name')}」的 Stage.{field} "
                    f"已迁移 {count} 条 SRA 副本到真实关卡编号"
                )
            if unresolved:
                logger.info(
                    f"HSR 用户「{self.get('Info', 'Name')}」的 Stage.{field} 有 "
                    f"{unresolved} 条 SRA 副本无法确认关卡编号，未改动；"
                    "如刷取的关卡不对，请在用户页重新选择一次"
                )

        return is_dirty

    def _tag_plan(self) -> ConfigBase:
        """标签读计划字段时用的对象。

        「脚本」来源的计划在所属 ``HSRConfig`` 的同名组上，经
        ``related_config["ScriptConfig"]`` 找到持有自己的那份脚本配置；「用户」
        「直控」来源，或找不到所属脚本（如未挂到全局配置的独立实例）时读自己。
        """

        if self.get("Info", "Mode") in ("用户", "直控"):
            return self
        scripts = self.related_config.get("ScriptConfig")
        if scripts is None:
            return self
        for script in scripts.values():
            if isinstance(script, HSRConfig) and any(
                user is self for user in script.UserData.values()
            ):
                return script
        return self

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
        # 完成态恒按用户记，开了哪个周常模块看计划 owner（脚本来源读共享计划）
        plan = self._tag_plan()
        du_on = bool(plan.get("TaskSwitch", "DivergentUniverse"))
        cw_on = bool(plan.get("TaskSwitch", "CurrencyWars"))
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
        ## 游戏平台：本地客户端 / 云·星穹铁道（MAS 托管浏览器，只用三月七）。
        ## OptionsValidator.correct() 回退的是 options[0]，Client 必须排第一。
        self.Game_Platform = ConfigItem(
            "Game", "Platform", "Client", OptionsValidator(["Client", "Cloud"])
        )
        ## 是否由 MAS 管理游戏启停、进程监测和窗口操作（仅客户端平台）
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

        ## Cloud -----------------------------------------------------------
        ## 云·星穹铁道（Game.Platform = Cloud）专用，映射到三月七的 cloud_game_* 键
        ## 是否允许消耗付费时长走快速排队通道（花钱的开关，默认关）
        self.Cloud_UsePaidTime = ConfigItem(
            "Cloud", "UsePaidTime", False, BoolValidator()
        )
        ## 最长排队时间（分钟），同时计入每个模块的超时预算
        self.Cloud_MaxQueueMinutes = ConfigItem(
            "Cloud", "MaxQueueMinutes", 60, RangeValidator(1, 9999)
        )
        ## 等待用户在浏览器窗口里手动登录的时间（分钟）
        self.Cloud_LoginTimeoutMinutes = ConfigItem(
            "Cloud", "LoginTimeoutMinutes", 20, RangeValidator(1, 9999)
        )
        ## 各用户最近一次确认已登录的时间（user_id → ISO 时间），只读展示用，
        ## 由运行结束后的写回与「登录云游戏」接口维护
        self.Cloud_LastLogin = ConfigItem("Cloud", "LastLogin", "{ }", JSONValidator())

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

        ## TaskSwitch / Stage / TaskOpt / Managed --------------------------
        ## 脚本来源下的共享任务计划：本脚本下所有「脚本」来源用户共用一份，
        ## 与 HSRUserConfig 同名组共用一处声明（Managed.TaskMapping 在这里是
        ## 恒为空的惰性字段，脚本态的引擎分配写下面的 TaskMapping 组）
        declare_hsr_plan_items(self)

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
        ## 配置来源（脚本/用户/直控）
        self.Info_Mode = ConfigItem(
            "Info", "Mode", "用户", UserDirectConfigModeValidator()
        )
        ## 是否启用快速配置（与配置来源独立，按用户保存）
        self.Info_IfQuickConfig = ConfigItem(
            "Info", "IfQuickConfig", True, BoolValidator()
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
        tags.append(
            {
                "text": f"上次：{_tag_last_status(last_status)}",
                "color": "red" if last_status == "失败" else "green",
            }
        )

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
    """MaaFW 项目配置。

    特调类型（M9A）是它的子类：字段集完全一致，只改下面三个类属性。``ConfigBase.__init__``
    在各子类 ``__init__`` 末尾才登记条目，子类不能在 ``super().__init__()`` 之后覆盖
    ``ConfigItem``，所以默认值与用户类都由类属性驱动。
    """

    related_config: dict[str, MultipleConfig] = {}

    ## 新建脚本时的默认名
    DEFAULT_SCRIPT_NAME = "新 MFW 脚本"
    ## 用户配置类（子类换成自己的同形子类，ScriptConfig.json 里 type 才对得上）
    USER_CONFIG_CLASS: type[ConfigBase] = MaaFWUserConfig
    ## 特调钩子：``"模块路径:属性名"``，运行期由 MaaFW 引擎按需导入（避免 models 反向依赖 task）；
    ## 通用 MaaFW 为 None。钩子装饰任务选择（可选再接管游戏客户端更新），引擎里不出现任何专项名字。
    FLAVOR: str | None = None

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        ## MaaFW 脚本名称
        self.Info_Name = ConfigItem("Info", "Name", self.DEFAULT_SCRIPT_NAME)
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
            "DirectExe",
            # 只保留两种：让 MAS 启动游戏（DirectExe，默认；由 MAS 启动的游戏结束后
            # 一律由 MAS 关闭）/ 使用其他方式启停游戏（AttachOnly，MAS 只接管已运行
            # 的窗口，不启动也不关闭）。LauncherExe 与 URL 已下线，旧配置由校验器
            # 纠正回 options[0]——它们本来就是「MAS 启动」的变体，落到 DirectExe 最贴近。
            OptionsValidator(["DirectExe", "AttachOnly"]),
        )
        ## DirectExe 模式下 MAS 启动的游戏 exe
        self.Game_LaunchPath = ConfigItem("Game", "LaunchPath", "", FileValidator())
        ## DirectExe 模式下，启动游戏前按 exe 路径反查 Unity 注册表，临时把分辨率改成所选
        ## 尺寸的窗口模式，游戏关闭后恢复原值（tools/embedded/game_resolution.py）。
        ## 只对 Unity 引擎的游戏有效；游戏已在运行时不改。Off 表示不碰。
        self.Game_UnityResolution = ConfigItem(
            "Game",
            "UnityResolution",
            "Off",
            OptionsValidator(["Off", "1920x1080", "1280x720"]),
        )
        ## 安卓游戏包名，Adb controller 用：启动模拟器时顺带把游戏拉起来。
        ## 留空表示从项目的 pipeline 里自动识别（见 embedded/game_package.py）；
        ## 自动识别是启发式的，填了这里就以这里为准。识别不出且没填则不启动游戏。
        self.Game_PackageName = ConfigItem("Game", "PackageName", "")
        ## 游戏启动参数
        self.Game_Arguments = ConfigItem("Game", "Arguments", "", ArgumentValidator())
        ## 游戏启动等待时间（秒）：既是等窗口出现的上限，也是窗口出现后等画面稳定的上限。
        ## Unity 游戏窗口出现时还在黑屏加载，登录界面往往要二三十秒后才渲染出来；
        ## MaaEnd 的 SceneManager 见连续画面不变十几秒就判「环境识别异常」直接失败。
        ## 等画面时 worker 每秒截一帧，有内容且连续几秒不变就提前下发，等不到才等满；
        ## MaaFW 初始化（加载资源、连 controller、起 agent）与之重叠而不是干等。
        ## 只对本轮由 MAS 拉起的游戏生效，AttachOnly 与「游戏已在运行」不等画面。
        self.Game_WaitTime = ConfigItem("Game", "WaitTime", 60, RangeValidator(0, 9999))
        # 原 Game.CloseOnFinish 开关已删：由 MAS 启动的游戏结束后一律关闭，
        # 其他方式启动的游戏 MAS 从不关闭，没有第三种组合需要用户选。

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
        ## 脚本级网络代理，给这个项目的更新包下载与运行环境安装（uv / pip、
        ## binding 源码兜底）用。与 CDK / 渠道不同，这一项**留空就跟随全局**
        ## `Update.ProxyAddress`（设置 → 其他 → 网络代理），填了就只走自己的：
        ## 代理解决的是「这台机器连不连得上」，多数人全局一份就够，个别项目
        ## 的源在别的网络才需要单独指。格式同全局项，`host:port` 不带协议时
        ## 补 `http://`（合并逻辑见 tools/embedded/update_credentials.py）。
        self.Update_ProxyAddress = ConfigItem("Update", "ProxyAddress", "")
        ## [已废弃] GitHub 仓库/tag/asset 覆盖：仓库与资产名改为从 interface.json
        ## 和目录名自动推导，运行流程不再读取；保留一个版本兼容旧配置文件后删除。
        self.Update_GitHubRepo = ConfigItem("Update", "GitHubRepo", "")
        self.Update_GitHubTag = ConfigItem("Update", "GitHubTag", "")
        self.Update_GitHubAssetPattern = ConfigItem("Update", "GitHubAssetPattern", "")

        ## Embedded -------------------------------------------------------
        ## 由 AUTO-MAS 内嵌一份按 interface 白名单投影的副本来运行。副本在
        ## data/mfw/<脚本 uuid 前 12 位>/，由脚本 ID 推出、不进配置、用户不可手改；
        ## Info.Path 继续存用户选的来源目录。更新落地时同样只写白名单内的条目。
        ## 导入时来源的 interface 版本，仅展示
        self.Embedded_SourceVersion = ConfigItem("Embedded", "SourceVersion", "")
        ## 导入时间，仅展示
        self.Embedded_ImportedAt = ConfigItem("Embedded", "ImportedAt", "")
        ## 投影报告（省下多少、外壳家族、排除条数与原因），JSON 字符串
        self.Embedded_Report = ConfigItem("Embedded", "Report", "{ }", JSONValidator())

        ## Run -------------------------------------------------------------
        ## 运行引擎，决定「谁来跑」：
        ## 代理次数限制
        self.Run_ProxyTimesLimit = ConfigItem(
            "Run", "ProxyTimesLimit", 0, RangeValidator(0, 9999)
        )
        ## 运行次数限制。重试不关游戏、不再等启动，从当前画面接着跑；
        ## 脚本自己的加载超时（MaaEnd 回大世界 20s）一次抖动就把整轮判失败，
        ## 只给一次机会时用户看到的就是「从来没成功过」，默认与其他专项一样 3 次。
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 3, RangeValidator(1, 9999)
        )
        ## 单次运行时间限制（分钟）。这是套在整次运行上的硬超时（asyncio.wait_for），
        ## 到点直接杀 worker、丢掉本轮进度与失败截图；MaaFW 项目一轮日常动辄
        ## 几十分钟，30 分钟默认值实测常被误伤，放宽到 120。
        self.Run_RunTimeLimit = ConfigItem(
            "Run", "RunTimeLimit", 120, RangeValidator(1, 9999)
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
        ## 游戏客户端更新：Off 不检查 / Check 只检查，落后时本次判失败并提示手动更新 /
        ## AutoInstall 落后时自动下载安装包并 adb 安装（保留游戏数据）。只在特调实现了
        ## 游戏更新钩子（当前只有 M9A）且 controller 是 ADB 时生效，通用 MaaFW 不读。
        ## Off 必须排第一：OptionsValidator 纠错回退的是 options[0]。
        self.Run_GameUpdateMode = ConfigItem(
            "Run",
            "GameUpdateMode",
            "Off",
            OptionsValidator(["Off", "Check", "AutoInstall"]),
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

        self.UserData = MultipleConfig([self.USER_CONFIG_CLASS])

        super().__init__()

    async def load(self, data: dict) -> bool:
        """加载脚本配置前迁移旧版 Update.IfAutoUpdate 布尔开关。"""
        return await super().load(_migrate_maafw_auto_update_mode(data))


class M9AUserConfig(MaaFWUserConfig):
    """M9A 用户配置：与 MaaFW 用户配置同形。

    ``Info.Account`` 在这里不只是备注：脚本资源为官服且账号非空时，运行前会自动插入
    「切换账号」任务（见 ``app/task/M9A/flavor.py``）。
    """


class M9AConfig(MaaFWConfig):
    """M9A 脚本配置：MaaFW 的特调类型。

    字段集与 MaaFW 完全一致，运行、更新、内嵌副本全部走 MaaFW 引擎；差别只有类型身份
    （键 / 图标 / 创建卡）、默认脚本名，以及运行前的队列装饰（启动 / 关闭游戏首尾、
    ``Info.Account`` 绑定切号）。旧版 M9A 专项的配置形状在启动时由
    ``app/task/M9A/migration.py`` 一次性迁到这个形状。
    """

    DEFAULT_SCRIPT_NAME = "新 M9A 脚本"
    USER_CONFIG_CLASS = M9AUserConfig
    FLAVOR = "app.task.M9A.flavor:FLAVOR"


class MSSUserConfig(MaaFWUserConfig):
    """MSS（MaaStellaSora / 星塔旅人）用户配置：MaaFW 用户配置再加一项计划表引用。

    ``Info.PlanMode`` 是比 MaaFW 多出的唯一字段：``Fixed`` 表示悬赏试炼按任务队列里
    用户自己配的选项跑；填了 MSS 计划表的 UID，运行前由特调钩子按当天槽位改写悬赏试炼的
    关卡、难度与次数（见 ``app/task/MSS/flavor.py``）。
    """

    related_config: dict[str, MultipleConfig] = {}

    def __init__(self) -> None:
        ## 活动优先：队列里没加「活动快速战斗」时，确认在活动期也自动加入并排到最前
        self.Info_IfActivityFirst = ConfigItem(
            "Info", "IfActivityFirst", True, BoolValidator()
        )
        ## 悬赏试炼关卡来源：Fixed 用任务队列里配的，选了计划表就按当天槽位改
        self.Info_PlanMode = ConfigItem(
            "Info",
            "PlanMode",
            "Fixed",
            TypedMultipleUIDValidator(
                "Fixed", self.related_config, "PlanConfig", MSSPlanConfig
            ),
        )

        super().__init__()


class MSSConfig(MaaFWConfig):
    """MSS 脚本配置：MaaFW 的特调类型。

    字段集与 MaaFW 完全一致，运行、更新、内嵌副本全部走 MaaFW 引擎；差别只有类型身份
    （键 / 图标 / 创建卡）、默认脚本名、用户上的计划表引用，以及运行前的队列装饰
    （活动期先打活动、按计划表改悬赏试炼、新版爬塔放最后）。
    """

    DEFAULT_SCRIPT_NAME = "新 MSS 脚本"
    USER_CONFIG_CLASS = MSSUserConfig
    FLAVOR = "app.task.MSS.flavor:FLAVOR"


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
                # Stage、Stage_1、Stage_2、Stage_3
                self.config_item_dict[group][name] = ConfigItem(group, name, "-")

            for name in MAA_STAGE_KEY:
                setattr(self, f"{group}_{name}", self.config_item_dict[group][name])

        super().__init__()

    def get_current_info(self, name: str, server: str | None = None) -> ConfigItem:
        """获取当前的计划表配置项，周模式按 server 区服的游戏日取当天配置"""

        if self.get("Info", "Mode") == "ALL":
            return self.config_item_dict["ALL"][name]

        elif self.get("Info", "Mode") == "Weekly":
            today = game_now(server).strftime("%A")

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


class MSSPlanKeyValidator(ValidatorBase):
    """MSS 计划表 key 验证器。"""

    def validate(self, value: Any) -> bool:
        try:
            return normalize_mss_plan_key(value) == value
        except ValueError:
            return False

    def correct(self, value: Any) -> dict[str, Any]:
        return normalize_mss_plan_key(value)


class MSSPlanConfig(WeeklyKeyPlanConfig):
    """MSS 计划表配置：每个日期槽位存一套悬赏试炼配置。"""

    def __init__(self) -> None:
        super().__init__(
            default_name="新 MSS 计划表",
            ## 用与校验器同一个函数生成默认值：手写字典的话，往 key 里加字段时
            ## 很容易漏改这里，配置项会因为「默认值不合法」直接起不来
            default_key=normalize_mss_plan_key({}),
            key_validator=MSSPlanKeyValidator(),
        )

    async def load(self, data: dict) -> bool:
        """加载计划表并迁移没有 Key 包装的旧日期槽位。"""

        normalized_data = deepcopy(data) if isinstance(data, dict) else {}
        for group in ["ALL", *calendar.day_name]:
            group_data = normalized_data.get(group)
            if isinstance(group_data, dict):
                normalized_data[group] = {"Key": normalize_mss_plan_key(group_data)}
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
        ## 配置来源（脚本/用户/直控）
        self.Info_Mode = ConfigItem(
            "Info", "Mode", "用户", UserDirectConfigModeValidator()
        )
        ## 兼容旧版用户独立脚本配置
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


class OkwwConfigModeValidator(ConfigSourceValidator):
    """脚本/用户/直控配置来源（兼容旧版“简洁/详细”）。"""

    def __init__(self) -> None:
        super().__init__(("脚本", "用户", "直控"), {"简洁": "脚本", "详细": "用户"})


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
        # MAS 仅接管 DailyTask 及 DailyTask 高频设置；账号切换由 MAS 侧
        # account_switch 实现，不再暴露上游 MultiAccountDailyTask。
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
        tags.append(
            {"text": f"上次：{_tag_last_status(last_status)}", "color": "green"}
        )

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
        self.Info_Mode = ConfigItem("Info", "Mode", "脚本", OkwwConfigModeValidator())
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
        tags.append(
            {"text": f"上次：{_tag_last_status(last_status)}", "color": "green"}
        )

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
        ## 配置来源（脚本/用户/直控）
        self.Info_Mode = ConfigItem(
            "Info", "Mode", "用户", UserDirectConfigModeValidator()
        )
        ## 是否启用快速配置（与配置来源独立，按用户保存）
        self.Info_IfQuickConfig = ConfigItem(
            "Info", "IfQuickConfig", True, BoolValidator()
        )
        ## 兼容旧版用户独立一条龙配置
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
        ## 「队伍配置」总开关（胶囊开关）：ON 时表格内队伍参与运行时「战斗场景」选队；
        ## OFF 时数据保留但不参与匹配（通用队伍 PartyName/AutoBossStrategyName 照旧生效）。
        self.OneDragon_IfUseTeams = ConfigItem(
            "OneDragon", "IfUseTeams", False, BoolValidator()
        )
        ## 队伍配置表：JSON 数组字符串，数组顺序即界面展示顺序（可拖拽重排），元素为
        ## {"name": str,            # 队伍名称（游戏内队伍名）
        ##  "strategy": str,        # 战斗策略名（留空 = 跟随通用策略 AutoBossStrategyName）
        ##  "scenes": {             # 战斗场景（可跨标签页任意叠加，空则本行不参与匹配）
        ##    "domain": [{"region": str, "domain": str, "reward": str}],   # 秘境：地区/秘境名/奖励档
        ##    "leyline": [{"country": str, "type": str}],                  # 地脉花：地区/地脉类型
        ##    "boss": [{"region": str, "boss": str}]},                     # 首领讨伐：地区/首领名
        ##  "note": str,            # 备注
        ##  "enabled": bool}        # 启用状态
        ## 序号 0 的「通用队伍」不落本字段（直绑 PartyName / AutoBossStrategyName）。
        ## 运行期由 team_resolver 按 L1 精确匹配 + 随机选取，写入 Plan 步骤的
        ## masTeamOverride / masStrategyOverride（最高优先级，压过每周行与步骤级字段）。
        self.OneDragon_Teams = ConfigItem(
            "OneDragon", "Teams", "[]", JSONValidator(list)
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
        self.OneDragon_Queue = ConfigItem(
            "OneDragon", "Queue", "[]", JSONValidator(list)
        )
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
        ## 账号 UID（可不填，切换前识别一致将不执行切换动作；仅 BetterGI 脚本方式生效）
        self.Switch_Uid = ConfigItem("Switch", "Uid", "")
        ## 游戏客户端路径（用户级覆盖，可空）：官服/B服/国际服是三个互相隔离的客户端，
        ## B站账号只能登录B服客户端。留空 = 跟随 BetterGI 全局配置的游戏路径；填写后该
        ## 用户运行时由 MAS 按此路径临时拉起游戏（不修改 BetterGI 配置），实现同脚本
        ## 混服用户各用各的客户端
        self.Switch_GamePath = ConfigItem("Switch", "GamePath", "", FileValidator())

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
        ## 是否统计掉落（BGI「奖励识别」）：默认开启；开启后运行前强制打开奖励识别，
        ## 并把日志里的逐轮识别结果汇总进统计通知
        self.Notify_IfSendDropStatistics = ConfigItem(
            "Notify", "IfSendDropStatistics", True, BoolValidator()
        )
        ## 用户自定义 Webhook 列表
        self.Notify_CustomWebhooks = MultipleConfig([Webhook])

        super().__init__()

    async def load(self, data: dict) -> bool:
        """加载配置前迁移旧版「游戏服务器」写法，并把快速配置开关按配置来源归一。

        快速配置开关已从 BetterGI 用户页隐藏，改为按 ``Info.Mode`` 派生（维护者决策）：
        直控 = 用 BGI 所选原生配置、MAS 不接管 ⇒ 恒为关；脚本 / 用户 = MAS 侧面板生效 ⇒ 开。
        存量数据里可能残留与来源相左的值（如「直控 + 开」），加载时统一以来源为准，
        免得 ``AutoProxy.writes_native_config`` 与界面语义又对不上。
        """
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
        # 来源字面量与 UserDirectConfigModeValidator 的取值一致（模型层不反向依赖 app.task）
        info = normalized_data.get("Info")
        if isinstance(info, dict) and info.get("Mode") in ("脚本", "用户", "直控"):
            info["IfQuickConfig"] = info["Mode"] != "直控"
        return await super().load(normalized_data)

    def getTags(self) -> str:
        tags = []

        last_status = self.get("Data", "LastProxyStatus")
        tags.append(
            {"text": f"上次：{_tag_last_status(last_status)}", "color": "green"}
        )

        # 快速配置开启时运行 MAS 槽位，关闭时运行所选原生配置。
        if self.get("Info", "IfQuickConfig"):
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
        ## 账号切换方式（脚本级，参考 MaaEnd Run.AccountSwitchMethod）：
        ## BGI = BetterGI「切换账号多模式」脚本执行（国际服请改用此方式）；MAS = MAS 侧
        ## 前台 OCR 直接操控游戏切号（官服/B服，游戏由 MAS 托管启动），官服/B服推荐。
        ## 默认值双轨：新建脚本取类默认 MAS；存量脚本（配置无该键）由 load 迁移固化
        ## 旧默认 BGI（见 _migrate_bgi_account_switch_default），保持升级前行为。
        self.Run_AccountSwitchMethod = ConfigItem(
            "Run", "AccountSwitchMethod", "MAS", OptionsValidator(["BGI", "MAS"])
        )

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

    async def load(self, data: dict) -> bool:
        """加载脚本配置前为存量脚本固化旧默认切号方式 BGI。

        注入后子级数据与完整存量文件（仅缺新键）比对不再 dirty，落盘靠两级：
        挂在 MultipleConfig 下时由父级整表比对发现缺键提交写盘；独立连接
        文件时由这里的显式提交完成（对齐 MaaEndConfig.load 的迁移范式）。
        返回值含迁移标记，不谎报「无写入」。
        """
        migrated_data, migrated = _migrate_bgi_account_switch_default(data)
        is_dirty = await super().load(migrated_data)
        if migrated and not is_dirty:
            await self._commit_changes()
        return is_dirty or migrated


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
        ## 配置来源（脚本/用户/直控）
        self.Info_Mode = ConfigItem(
            "Info", "Mode", "用户", UserDirectConfigModeValidator()
        )
        ## 是否启用快速配置（已封锁，仅保留字段兼容存量数据：直控在 load/update
        ## 归一为关，脚本/用户来源不消费本开关）
        self.Info_IfQuickConfig = ConfigItem(
            "Info", "IfQuickConfig", True, BoolValidator()
        )
        ## 绑定的 zzz-od 实例槽下标（运行/配置会话内临时合成视图写回原生配置，非持久注册）：-1=未分配，首次运行或
        ## 「在一条龙内配置」时自动分配空闲 idx 并锁定该槽至会话结束，
        ## 此后配置会话与运行时注入都固定使用该槽。新槽从 MAS_SLOT_BASE（1001）起，
        ## 退到一条龙「升序找最小空号」够不到的高位段（上限 9999 与之一致放宽）
        self.Info_SlotIdx = ConfigItem("Info", "SlotIdx", -1, RangeValidator(-1, 9999))
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

        ## 一条龙游戏启动参数（game.yml 六字段，照抄上游 BasicGameConfig
        ## 默认值与取值；一条龙启动游戏时消费，总开关关闭则全部不生效）：
        ## 启动参数总开关
        self.Game_LaunchArgument = ConfigItem(
            "Game", "LaunchArgument", False, BoolValidator()
        )
        ## 窗口尺寸（上游枚举原值）
        self.Game_ScreenSize = ConfigItem(
            "Game",
            "ScreenSize",
            "1920x1080",
            OptionsValidator(["1920x1080", "2560x1440", "3840x2160"]),
        )
        ## 全屏模式（上游枚举原值为字符串：'0'=窗口化 '1'=全屏）
        self.Game_FullScreen = ConfigItem(
            "Game", "FullScreen", "0", OptionsValidator(["0", "1"])
        )
        ## 无边框窗口（一条龙拼参时转 -popupwindow）
        self.Game_PopupWindow = ConfigItem(
            "Game", "PopupWindow", False, BoolValidator()
        )
        ## DX12 启动（MAS 便捷开关：注入时把 -use-d3d12 合并进一条龙的
        ## launch_argument_advance；上游无独立字段，勾选框是唯一权威）
        self.Game_Dx12 = ConfigItem("Game", "Dx12", False, BoolValidator())
        ## 显示器序号（上游枚举原值为字符串）
        self.Game_Monitor = ConfigItem(
            "Game", "Monitor", "1", OptionsValidator(["1", "2", "3", "4"])
        )
        ## 高级参数（原样透传给一条龙拼接，上游不解析，不做 shlex 校验）
        self.Game_LaunchArgumentAdvance = ConfigItem(
            "Game", "LaunchArgumentAdvance", "", StringValidator()
        )

        ## OneDragon -------------------------------------------------------
        ## 一条龙任务编排（JSON 数组字符串 [{"app_id": "...", "enabled": true}, ...]，
        ## 数组顺序即执行顺序；enabled=false 的任务由 zzz-od 跳过）
        self.OneDragon_AppList = ConfigItem("OneDragon", "AppList", "[]")
        ## 游戏结束后操作（仅 MAS 拉起的一条龙运行消费：CLI 传参
        ## --close-game / --shutdown 60；无=不传参，游戏保持运行。
        ## 与一条龙原生 GUI 的「结束后」下拉无关——原生 after_done 只在
        ## 从 GUI 内启动运行时被消费，CLI 路径不读它）
        self.OneDragon_AfterDone = ConfigItem(
            "OneDragon",
            "AfterDone",
            "关闭游戏",
            OptionsValidator(["无", "关闭游戏", "关机"]),
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
                "text": f"上次：{_tag_last_status(last_status)}",
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

    async def load(self, data: dict) -> bool:
        """加载前把直控用户的快速配置开关归一为关（快速配置已封锁，维护者决策）。

        直控 = MAS 零注入零干涉（与 ``update_user`` 切直控守卫同口径），快速配置
        的覆盖写槽与该语义相悖，消费点已移除。存量数据里「直控 + 开」的残留
        （旧版默认开、界面无开关可关）在此统一以来源为准归关；脚本 / 用户来源
        的开关值不消费、保持原样。

        归一作用在传入数据上（与 ``BetterGIConfig.load`` 同款写法），属**内存
        归一**：每次加载都会重新归位，该字段已无任何消费点，不需要为它额外
        回写磁盘；切换直控时的 ``update_user`` 守卫会把值真正落到盘上。
        """
        normalized_data = deepcopy(data) if isinstance(data, dict) else {}
        info = normalized_data.get("Info")
        if isinstance(info, dict) and info.get("Mode") == "直控":
            info["IfQuickConfig"] = False
        return await super().load(normalized_data)


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
        ## 覆盖失败重试与手动停止场景，是「结束后操作」的兜底）。与用户级
        ## OneDragon.AfterDone 下发的 --close-game 相互独立，同时配置会各
        ## 执行一次（无害）
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
        ## 是否启用中国移动新消息通知
        self.Notify_IfCMCCNewMsg = ConfigItem(
            "Notify", "IfCMCCNewMsg", False, BoolValidator()
        )
        ## 中国移动新消息 Channel API Key
        self.Notify_CMCCNewMsgApiKey = ConfigItem(
            "Notify", "CMCCNewMsgApiKey", "", EncryptValidator()
        )
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
        ## GitHub 加速镜像
        ## **只影响 MFW 项目包从 GitHub Release 下载这一条路**（脚本的
        ## `Update.Source` 选 GitHub 时）：国内直连 GitHub 常年 100 多 KB/s，
        ## 359MB 的全量包要四十分钟。`Auto` 依次试镜像、全部失败再回直连；
        ## `Off` 只直连。MAS 自身的更新与初始化 clone 走前端 mirrorService，
        ## 不读这一项；Mirror 酱是另一个源，也不受它影响。
        self.Update_GitHubMirror = ConfigItem(
            "Update", "GitHubMirror", "Auto", OptionsValidator(["Auto", "Off"])
        )
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
        ## 脚本配置列表（顺序与 CLASS_BOOK 一致）
        self.ScriptConfig = MultipleConfig(list(CLASS_BOOK.values()))
        ## 队列配置列表
        self.QueueConfig = MultipleConfig([QueueConfig])
        ## 启动期攒下、主连接建立后一次性发出的系统通知
        self.startup_notices: list[dict[str, Any]] = []
        ## 工具箱配置
        self.ToolsConfig = ToolsConfig()

        MaaConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        MaaEndConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        SrcConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        MaaFWConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        GeneralConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        BAAHConfig.related_config["EmulatorConfig"] = self.EmulatorConfig
        MaaUserConfig.related_config["PlanConfig"] = self.PlanConfig
        MaaEndUserConfig.related_config["PlanConfig"] = self.PlanConfig
        MSSUserConfig.related_config["PlanConfig"] = self.PlanConfig
        QueueItem.related_config["ScriptConfig"] = self.ScriptConfig
        HSRUserConfig.related_config["ScriptConfig"] = self.ScriptConfig

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
        ## 配置来源（脚本/用户/直控）
        self.Info_Mode = ConfigItem(
            "Info", "Mode", "用户", UserDirectConfigModeValidator()
        )
        ## 是否启用快速配置（与配置来源独立，按用户保存）
        self.Info_IfQuickConfig = ConfigItem(
            "Info", "IfQuickConfig", True, BoolValidator()
        )
        ## 默认使用的 BAAH 配置文件名（BAAH_CONFIGS 目录下的文件名，不含 .json 后缀）
        self.Info_ConfigName = ConfigItem("Info", "ConfigName", "")
        ## 活动期间使用的 BAAH 配置文件名；留空表示活动期间也用 ConfigName
        self.Info_ActivityConfigName = ConfigItem("Info", "ActivityConfigName", "")
        ## 是否按碧蓝档案有没有活动切换使用的配置文件
        self.Info_IfActivityAdapt = ConfigItem(
            "Info", "IfActivityAdapt", False, BoolValidator()
        )
        ## 活动排期按哪个服判断（Kivo 时间轴的原文拼写：JP / Globle / CN）
        self.Info_ActivityLineType = ConfigItem(
            "Info", "ActivityLineType", "CN", OptionsValidator(["JP", "Globle", "CN"])
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


class WhimboxUserConfig(ConfigBase):
    """奇想盒用户配置（无限暖暖，一条龙配置档）

    一条龙字段定义与值域完全来自上游安装目录三件套（任务目录，运行时读取），
    本类只存「用户勾了哪些步骤、选了哪些值」的覆盖集（Tasks/Options 两个
    JSON map），不复制上游字段模型；写入时按当前模板键集过滤后物化到上游
    configs/config.json。
    """

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        self.Info_Name = ConfigItem("Info", "Name", "新用户", UserNameValidator())
        self.Info_Status = ConfigItem("Info", "Status", True, BoolValidator())
        ## base 来源三态（共享/独立/原生，存储值沿用「脚本/用户/直控」）：共享/独立=
        ## 用 MAS 面板配置（当前运行行为一致，为后续特殊功能预留），原生=直接用奇想盒
        ## 自带配置（MAS 零写入）
        self.Info_Mode = ConfigItem(
            "Info", "Mode", "脚本", UserDirectConfigModeValidator()
        )
        ## 是否启用覆写层（快速配置，与来源独立，按账号保存，默认关）：开启时原生态
        ## 也会在任务前把面板覆盖集写入奇想盒（overlay，任务结束还原）；共享/独立态
        ## 面板本就是 base 来源，开关暂无额外消费点，为后续特殊功能预留。默认关保证
        ## 「原生=零写入」与 _write_config_or_hint 报错里「切原生绕开写入」的出路成立
        self.Info_IfQuickConfig = ConfigItem(
            "Info", "IfQuickConfig", False, BoolValidator()
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

        ## OneDragon -------------------------------------------------------
        ## 一条龙是否循环全部游戏账号（物化为上游 OneDragon.change_account；
        ## 账号列表由奇想盒运行期 OCR 动态发现，MAS 不做账号定向）
        self.OneDragon_IfRunAllAccounts = ConfigItem(
            "OneDragon", "IfRunAllAccounts", False, BoolValidator()
        )
        ## 一条龙结束后关闭游戏与奇想盒不设开关：恒物化上游
        ## OneDragon.auto_close_game=true（后续脚本流程依赖游戏已退出，
        ## 由适配层强制，用户不可关闭）

        ## Task ------------------------------------------------------------
        ## 步骤开关覆盖集：JSON map {步骤键: bool}，键集来自任务目录
        ## （上游 OneDragonDefaultSteps 节），只存用户勾选结果
        self.Task_Tasks = ConfigItem("Task", "Tasks", "{ }", JSONValidator(dict))
        ## 目标/参数覆盖集：JSON map {键: 值}，键集来自任务目录
        ## （上游 OneDragon 节托管字段），只存用户显式选择的值
        self.Task_Options = ConfigItem("Task", "Options", "{ }", JSONValidator(dict))

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
        ## 自定义 Webhook 列表
        self.Notify_CustomWebhooks = MultipleConfig([Webhook])

        super().__init__()

    def getTags(self) -> str:
        """生成奇想盒用户标签列表"""
        tags = []

        # 任务代理标签（使用东4区时间）
        tags.append(_tag_proxy(self, "任务"))

        # 剩余天数标签
        tags.append(_tag_remained_days(self))

        # 备注标签
        tags.append(_tag_notes(self))

        return json.dumps(tags, ensure_ascii=False)


class WhimboxConfig(ConfigBase):
    """奇想盒配置（无限暖暖，BetterGI 线：无头 CLI + 日志面判定）"""

    def __init__(self) -> None:

        ## Info ------------------------------------------------------------
        self.Info_Name = ConfigItem("Info", "Name", "新奇想盒脚本")
        ## 奇想盒安装根目录（whimbox_app.exe 所在目录；configs/logs 与其同级）
        self.Info_RootPath = ConfigItem("Info", "RootPath", "", FileValidator())

        ## Run -------------------------------------------------------------
        self.Run_ProxyTimesLimit = ConfigItem(
            "Run", "ProxyTimesLimit", 0, RangeValidator(0, 9999)
        )
        ## 失败重试次数：只用于「没有上游结论」的异常（进程提前退出/卡死）；
        #  上游自己判负时，仅当失败原因与上一轮不同才继续重试（同一结论连着出现即收口）
        self.Run_RunTimesLimit = ConfigItem(
            "Run", "RunTimesLimit", 3, RangeValidator(1, 9999)
        )
        ## 运行超时（分钟）：日志静默超过该时长判定卡死
        self.Run_RunTimeLimit = ConfigItem(
            "Run", "RunTimeLimit", 30, RangeValidator(1, 9999)
        )
        ## 以管理员权限启动奇想盒后端（上游强制管理员，缺权限会在起跑即退出；
        ## MAS 自身已提权时不重复触发 UAC，子进程自动继承管理员令牌）
        self.Run_UseAdmin = ConfigItem("Run", "UseAdmin", True, BoolValidator())

        self.UserData = MultipleConfig([WhimboxUserConfig])

        super().__init__()


CLASS_BOOK = {
    "MAA": MaaConfig,
    "MaaEnd": MaaEndConfig,
    "SRC": SrcConfig,
    "M9A": M9AConfig,
    "MaaFW": MaaFWConfig,
    "General": GeneralConfig,
    "Okww": OkwwConfig,
    "OkNte": OkNteConfig,
    "HSR": HSRConfig,
    "BetterGI": BetterGIConfig,
    "ZzzOd": ZzzOdConfig,
    "BAAH": BAAHConfig,
    "Whimbox": WhimboxConfig,
    "MSS": MSSConfig,
}
"""配置类映射表: 脚本类型键 → 配置类, GlobalConfig 的脚本配置列表由此派生"""

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
    "MSSPlanConfig": {
        "create_type": "MSSPlan",
        "config_class": MSSPlanConfig,
        "schema_class": schema_model.MSSPlanConfig,
        "consumer": PLAN_CONSUMER_VALUES[2],
        "script_class": MSSConfig,
        "field_name": "PlanMode",
    },
}
"""计划表注册表"""
