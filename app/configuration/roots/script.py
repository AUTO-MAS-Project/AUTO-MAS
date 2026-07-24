"""ScriptConfig 的原生 Config v2 多态根与 r6 兼容转换。

八类正式脚本及其 UserData 均使用可审计的 ``ConfigGroup`` 字段模型；
内置用户配置不保留 opaque JSON 逃生舱。转换器严格拒绝未知字段、孤儿、
重复 UUID 与别名冲突，并在回滚边界强制敏感值保持 DPAPI 密文。

本模块只做内存对象转换，不读写真实配置文件。
"""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, Field

from app.configuration import (
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    Virtual,
    WireDict,
    collection,
    encrypted,
    ref,
    virtual_field,
)
from app.configuration.roots.config import CustomWebhooks, Webhook
from app.configuration.v2.support.security import (
    is_probable_dpapi_ciphertext,
)
from app.utils.constants import (
    FORBIDDEN_PATH_EXACT,
    FORBIDDEN_PATH_PREFIXES,
    ILLEGAL_CHARS,
    MAA_STAGE_KEY,
    MAAEND_AUTO_ESSENCE_LOCATION_OPTIONS,
    MAAEND_PROTOCOL_SPACE_TASK_OPTIONS,
    MAAEND_SANITY_TASK_DEFAULTS,
    MAAEND_SANITY_TASK_TYPES,
    MAAEND_TASKS,
    RESERVED_NAMES,
    RESOURCE_STAGE_INFO,
    STARRAIL_STAGE_BOOK,
    UTC4,
    UTC8,
)

SCRIPT_COLLECTION_NAME = "ScriptConfig"
EMULATOR_COLLECTION_NAME = "EmulatorConfig"
PLAN_COLLECTION_NAME = "PlanConfig"

NATIVE_SCRIPT_TYPES = (
    "MaaConfig",
    "MaaEndConfig",
    "SrcConfig",
    "M9AConfig",
    "MaaFWConfig",
    "GeneralConfig",
    "OkwwConfig",
    "PluginScriptConfig",
)
NATIVE_USER_TYPES = (
    "MaaUserConfig",
    "MaaEndUserConfig",
    "SrcUserConfig",
    "M9AUserConfig",
    "MaaFWUserConfig",
    "GeneralUserConfig",
    "OkwwUserConfig",
)


def _validate_uuid_or_dash(value: str) -> str:
    if value == "-":
        return value
    try:
        return str(UUID(value))
    except (ValueError, AttributeError):
        raise ValueError("引用值必须为 '-' 或 UUID 字符串") from None


def _validate_plan_ref(value: str) -> str:
    if value == "Fixed":
        return value
    try:
        return str(UUID(value))
    except (ValueError, AttributeError):
        raise ValueError("关卡计划必须为 'Fixed' 或 UUID 字符串") from None


def _load_json_text(
    value: str,
    *,
    expected: type[dict] | type[list],
    path: str,
) -> dict[str, Any] | list[Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        raise ValueError(f"{path} 必须是有效 JSON") from None
    if not isinstance(parsed, expected):
        label = "对象" if expected is dict else "列表"
        raise ValueError(f"{path} 必须是 JSON {label}")
    return parsed


def _validate_json_list_text(value: str) -> str:
    _load_json_text(value, expected=list, path="配置值")
    return value


def _validate_json_dict_text(value: str) -> str:
    _load_json_text(value, expected=dict, path="配置值")
    return value


def _validate_datetime_text(value: str, *, fmt: str) -> str:
    try:
        datetime.strptime(value, fmt)
    except (TypeError, ValueError):
        raise ValueError(f"配置值必须匹配日期格式 {fmt}") from None
    return value


def _validate_date(value: str) -> str:
    return _validate_datetime_text(value, fmt="%Y-%m-%d")


def _validate_month(value: str) -> str:
    return _validate_datetime_text(value, fmt="%Y-%m")


def _validate_username(value: str) -> str:
    if not value or value != value.strip():
        raise ValueError("用户名不能为空或包含首尾空白")
    if value.endswith("."):
        raise ValueError("用户名不能以点结尾")
    if any(char in ILLEGAL_CHARS for char in value):
        raise ValueError("用户名包含 Windows 非法字符")
    if value.upper() in RESERVED_NAMES:
        raise ValueError("用户名是 Windows 保留名称")
    if len(value) > 255:
        raise ValueError("用户名不能超过 255 个字符")
    return value


def _validate_file_path(value: str) -> str:
    if not value:
        return value
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("文件路径必须是绝对路径")
    if path.suffix.lower() == ".lnk":
        raise ValueError("不允许 Windows 快捷方式")
    resolved = path.resolve()
    if resolved.parent == resolved:
        raise ValueError("不允许磁盘根目录")
    for forbidden in (*FORBIDDEN_PATH_PREFIXES, Path.cwd().resolve()):
        if (
            resolved == forbidden
            or forbidden in resolved.parents
            or resolved in forbidden.parents
        ):
            raise ValueError("路径位于受保护目录")
    if resolved in FORBIDDEN_PATH_EXACT:
        raise ValueError("路径是受保护路径")
    return value


def _validate_folder_path(value: str) -> str:
    _validate_file_path(value)
    if value and not Path(value).is_dir():
        raise ValueError("文件夹路径必须指向现有目录")
    return value


def _validate_script_root_path(value: str) -> str:
    if not value:
        return value
    path = Path(value)
    if not path.is_absolute() or not path.is_dir():
        raise ValueError("脚本根目录必须是现有绝对目录")
    resolved = path.resolve()
    if resolved.parent == resolved:
        raise ValueError("不允许磁盘根目录")
    for forbidden in FORBIDDEN_PATH_PREFIXES:
        if (
            resolved == forbidden
            or forbidden in resolved.parents
            or resolved in forbidden.parents
        ):
            raise ValueError("脚本根目录位于受保护目录")
    if resolved in FORBIDDEN_PATH_EXACT:
        raise ValueError("脚本根目录是受保护路径")
    return value


def _validate_argument_text(value: str) -> str:
    if value:
        try:
            shlex.split(value.strip())
        except ValueError:
            raise ValueError("启动参数引号不匹配") from None
    return value


def _validate_advanced_argument_text(value: str) -> str:
    try:
        for segment in value.split("|"):
            segment = segment.strip()
            if segment:
                shlex.split(segment.split("%", 1)[-1].strip())
    except ValueError:
        raise ValueError("高级启动参数引号不匹配") from None
    return value


def _one_of(options: tuple[str, ...], label: str):
    def validate(value: str) -> str:
        if value not in options:
            raise ValueError(f"{label} 不在允许选项中")
        return value

    return validate


def _base_tags(
    if_pass_check: bool,
    last_proxy_date: str,
    proxy_times: int,
    remained_day: int,
    notes: str,
) -> list[dict[str, str]]:
    tags: list[dict[str, str]] = []
    if not if_pass_check:
        tags.append({"text": "人工排查未通过", "color": "red"})
    if (
        datetime.strptime(last_proxy_date, "%Y-%m-%d").date()
        == datetime.now(tz=UTC4).date()
    ):
        tags.append(
            {
                "text": f"日常：已代理{proxy_times}次",
                "color": "green",
            }
        )
    else:
        tags.append({"text": "日常：未代理", "color": "orange"})
    if remained_day == -1:
        color = "gold"
    elif remained_day == 0:
        color = "red"
    elif remained_day <= 3:
        color = "orange"
    elif remained_day <= 7:
        color = "yellow"
    elif remained_day <= 30:
        color = "blue"
    else:
        color = "green"
    tags.append(
        {
            "text": (
                f"剩余天数：{remained_day}天"
                if remained_day >= 0
                else "剩余天数：无期限"
            ),
            "color": color,
        }
    )
    tags.append(
        {
            "text": f"备注：{notes}" if len(notes) <= 20 else f"备注：{notes[:20]}...",
            "color": "pink",
        }
    )
    return tags


StrictText = Annotated[str, Field(strict=True)]
Count0 = Annotated[int, Field(strict=True, ge=0, le=9999)]
Count1 = Annotated[int, Field(strict=True, ge=1, le=9999)]
RemainingDays = Annotated[int, Field(strict=True, ge=-1, le=9999)]
UserNameText = Annotated[
    str, Field(strict=True), AfterValidator(_validate_username)
]
DateText = Annotated[str, Field(strict=True), AfterValidator(_validate_date)]
MonthText = Annotated[str, Field(strict=True), AfterValidator(_validate_month)]
FilePathText = Annotated[
    str, Field(strict=True), AfterValidator(_validate_file_path)
]
FolderPathText = Annotated[
    str, Field(strict=True), AfterValidator(_validate_folder_path)
]
ArgumentText = Annotated[
    str, Field(strict=True), AfterValidator(_validate_argument_text)
]
ScriptRootPathText = Annotated[
    str, Field(strict=True), AfterValidator(_validate_script_root_path)
]
AdvancedArgumentText = Annotated[
    str,
    Field(strict=True),
    AfterValidator(_validate_advanced_argument_text),
]
JsonListText = Annotated[
    str,
    Field(strict=True),
    AfterValidator(_validate_json_list_text),
]
PlanRef = Annotated[
    str,
    Field(strict=True),
    AfterValidator(_validate_plan_ref),
    ref(
        PLAN_COLLECTION_NAME,
        default="Fixed",
        allow_values=("Fixed",),
    ),
]
MaaEndOperatorProgression = Annotated[
    str,
    Field(strict=True),
    AfterValidator(
        _one_of(
            tuple(MAAEND_PROTOCOL_SPACE_TASK_OPTIONS["OperatorProgression"]),
            "干员养成任务",
        )
    ),
]
MaaEndWeaponProgression = Annotated[
    str,
    Field(strict=True),
    AfterValidator(
        _one_of(
            tuple(MAAEND_PROTOCOL_SPACE_TASK_OPTIONS["WeaponProgression"]),
            "武器养成任务",
        )
    ),
]
MaaEndCrisisDrills = Annotated[
    str,
    Field(strict=True),
    AfterValidator(
        _one_of(
            tuple(MAAEND_PROTOCOL_SPACE_TASK_OPTIONS["CrisisDrills"]),
            "危境预演任务",
        )
    ),
]
MaaEndEssenceLocation = Annotated[
    str,
    Field(strict=True),
    AfterValidator(
        _one_of(
            tuple(MAAEND_AUTO_ESSENCE_LOCATION_OPTIONS),
            "基质刷取地点",
        )
    ),
]

_SRC_RELIC_OPTIONS = tuple(
    ["-"]
    + [
        key
        for key in STARRAIL_STAGE_BOOK
        if key.startswith("Cavern_of_Corrosion_")
        and key
        not in {
            "Cavern_of_Corrosion_Path_of_Dreamdive",
            "Cavern_of_Corrosion_Path_of_Darkness",
            "Cavern_of_Corrosion_Path_of_Divine_Insight",
        }
    ]
)
_SRC_MATERIAL_OPTIONS = tuple(
    ["-"]
    + [
        key
        for key in STARRAIL_STAGE_BOOK
        if (
            key.startswith("Calyx_")
            or key.startswith("Stagnant_Shadow_")
        )
        and key
        not in {
            "Calyx_Crimson_Destruction_Amphoreus_InkfordHermitage",
            "Calyx_Crimson_Erudition_Amphoreus_SeafeldTVTower",
            (
                "Calyx_Crimson_Nihility_Amphoreus_"
                "SacredTracewoodGroveofDivineInsight"
            ),
            "Stagnant_Shadow_Devour",
        }
    ]
)
_SRC_ORNAMENT_OPTIONS = tuple(
    ["-"]
    + [
        key
        for key in STARRAIL_STAGE_BOOK
        if key.startswith("Divergent_Universe_")
        and key != "Divergent_Universe_Gilded_Reminiscence"
    ]
)
_SRC_ECHO_OPTIONS = tuple(
    ["-"]
    + [key for key in STARRAIL_STAGE_BOOK if key.startswith("Echo_of_War_")]
)
_SRC_SIMULATED_OPTIONS = (
    "-",
    "Simulated_Universe_World_3",
    "Simulated_Universe_World_4",
    "Simulated_Universe_World_5",
    "Simulated_Universe_World_6",
    "Simulated_Universe_World_8",
)
SrcRelic = Annotated[
    str,
    Field(strict=True),
    AfterValidator(_one_of(_SRC_RELIC_OPTIONS, "遗器关卡")),
]
SrcMaterials = Annotated[
    str,
    Field(strict=True),
    AfterValidator(_one_of(_SRC_MATERIAL_OPTIONS, "材料关卡")),
]
SrcOrnament = Annotated[
    str,
    Field(strict=True),
    AfterValidator(_one_of(_SRC_ORNAMENT_OPTIONS, "饰品关卡")),
]
SrcEcho = Annotated[
    str,
    Field(strict=True),
    AfterValidator(_one_of(_SRC_ECHO_OPTIONS, "历战余响关卡")),
]
SrcSimulated = Annotated[
    str,
    Field(strict=True),
    AfterValidator(_one_of(_SRC_SIMULATED_OPTIONS, "模拟宇宙关卡")),
]
JsonDictText = Annotated[
    str,
    Field(strict=True),
    AfterValidator(_validate_json_dict_text),
]
EmulatorRef = Annotated[
    str,
    Field(strict=True),
    AfterValidator(_validate_uuid_or_dash),
    ref(
        EMULATOR_COLLECTION_NAME,
        default="-",
        allow_values=("-",),
    ),
]


class _BaseInfoGroup(ConfigGroup):
    Name: UserNameText = "新用户"
    Status: Annotated[bool, Field(strict=True)] = True
    RemainedDay: RemainingDays = -1
    IfScriptBeforeTask: Annotated[bool, Field(strict=True)] = False
    ScriptBeforeTask: FilePathText = ""
    IfScriptAfterTask: Annotated[bool, Field(strict=True)] = False
    ScriptAfterTask: FilePathText = ""
    Notes: StrictText = "无"
    Tag: Virtual[str] = None


class _CommonNotifyGroup(ConfigGroup):
    Enabled: Annotated[bool, Field(strict=True)] = False
    IfSendStatistic: Annotated[bool, Field(strict=True)] = False
    IfSendMail: Annotated[bool, Field(strict=True)] = False
    ToAddress: StrictText = ""
    IfServerChan: Annotated[bool, Field(strict=True)] = False
    ServerChanKey: Annotated[str, Field(strict=True), encrypted()] = ""


class MaaUser(ConfigEntry):
    class InfoGroup(_BaseInfoGroup):
        Id: StrictText = ""
        Password: Annotated[str, Field(strict=True), encrypted()] = ""
        Mode: Literal["简洁", "详细"] = "简洁"
        StageMode: PlanRef = "Fixed"
        Server: Literal[
            "Official",
            "Bilibili",
            "YoStarEN",
            "YoStarJP",
            "YoStarKR",
            "txwy",
        ] = "Official"
        Annihilation: Literal[
            "Close",
            "Annihilation",
            "Chernobog@Annihilation",
            "LungmenOutskirts@Annihilation",
            "LungmenDowntown@Annihilation",
        ] = "Annihilation"
        InfrastMode: Literal["Normal", "Rotation", "Custom"] = "Normal"
        InfrastName: Virtual[str] = None
        InfrastIndex: Virtual[str] = None
        MedicineNumb: Count0 = 0
        SeriesNumb: Literal["0", "6", "5", "4", "3", "2", "1", "-1"] = "0"
        Stage: StrictText = "-"
        Stage_1: StrictText = "-"
        Stage_2: StrictText = "-"
        Stage_3: StrictText = "-"
        Stage_Remain: StrictText = "-"
        IfSkland: Annotated[bool, Field(strict=True)] = False
        SklandToken: Annotated[str, Field(strict=True), encrypted()] = ""

    class DataGroup(ConfigGroup):
        LastProxyDate: DateText = "2000-01-01"
        LastSklandDate: DateText = "2000-01-01"
        ProxyTimes: Count0 = 0
        IfPassCheck: Annotated[bool, Field(strict=True)] = True
        CustomInfrast: JsonDictText = "{ }"
        InfrastIndex: StrictText = "0"

    class TaskGroup(ConfigGroup):
        IfStartUp: Annotated[bool, Field(strict=True)] = True
        IfFight: Annotated[bool, Field(strict=True)] = True
        IfInfrast: Annotated[bool, Field(strict=True)] = True
        IfRecruit: Annotated[bool, Field(strict=True)] = True
        IfMall: Annotated[bool, Field(strict=True)] = True
        IfAward: Annotated[bool, Field(strict=True)] = True
        IfRoguelike: Annotated[bool, Field(strict=True)] = False
        IfReclamation: Annotated[bool, Field(strict=True)] = False

    class NotifyGroup(_CommonNotifyGroup):
        IfSendSixStar: Annotated[bool, Field(strict=True)] = False

    Info: InfoGroup = Field(default_factory=InfoGroup)
    Data: DataGroup = Field(default_factory=DataGroup)
    Task: TaskGroup = Field(default_factory=TaskGroup)
    Notify: NotifyGroup = Field(default_factory=NotifyGroup)
    Notify_CustomWebhooks: CustomWebhooks = collection(Webhook)

    @virtual_field("Info.InfrastName")
    def infrast_name(self) -> str:
        if self.Info.InfrastMode != "Custom":
            return "未使用自定义基建模式"
        payload = json.loads(self.Data.CustomInfrast)
        title = payload.get("title", "文件标题")
        description = payload.get("description", "文件描述")
        if title != "文件标题" and description != "文件描述":
            return f"{title} - {description}"
        if title != "文件标题":
            return str(title)
        if payload.get("id"):
            return str(payload["id"])
        return "未命名自定义基建"

    @virtual_field("Info.InfrastIndex")
    def infrast_index(self) -> str:
        if self.Info.InfrastMode != "Custom":
            return "-1"
        payload = json.loads(self.Data.CustomInfrast)
        if not payload.get("plans"):
            return "-1"
        for index, plan in enumerate(payload.get("plans", [])):
            for period in plan.get("period", []):
                start = datetime.strptime(period[0], "%H:%M").time()
                end = datetime.strptime(period[1], "%H:%M").time()
                if start <= datetime.now().time() <= end:
                    return str(index)
        return self.Data.InfrastIndex or "0"

    @virtual_field("Info.Tag")
    def tags(self) -> str:
        tags = _base_tags(
            self.Data.IfPassCheck,
            self.Data.LastProxyDate,
            self.Data.ProxyTimes,
            self.Info.RemainedDay,
            self.Info.Notes,
        )
        if self.Info.IfSkland:
            signed = (
                datetime.strptime(
                    self.Data.LastSklandDate, "%Y-%m-%d"
                ).date()
                == datetime.now(tz=UTC8).date()
            )
            tags.insert(
                2,
                {
                    "text": "森空岛：已签到" if signed else "森空岛：未签到",
                    "color": "green" if signed else "orange",
                },
            )
        else:
            tags.insert(2, {"text": "森空岛：禁用", "color": "red"})
        return json.dumps(tags, ensure_ascii=False)


class MaaUsers(ConfigCollection[MaaUser]):
    _default_entry_types = (MaaUser,)


class MaaEndUser(ConfigEntry):
    class InfoGroup(_BaseInfoGroup):
        Id: StrictText = ""
        Password: Annotated[str, Field(strict=True), encrypted()] = ""
        Mode: Literal["简洁", "详细"] = "简洁"
        IfQuickConfig: Annotated[bool, Field(strict=True)] = True
        SanityMode: StrictText = "Fixed"
        Resource: Literal["官服"] = "官服"
        IfSkland: Annotated[bool, Field(strict=True)] = False
        SklandToken: Annotated[str, Field(strict=True), encrypted()] = ""

    class TaskGroup(ConfigGroup):
        SanityTaskType: Literal[
            "OperatorProgression",
            "WeaponProgression",
            "CrisisDrills",
            "Essence",
        ] = MAAEND_SANITY_TASK_DEFAULTS["SanityTaskType"]
        OperatorProgression: MaaEndOperatorProgression = (
            MAAEND_SANITY_TASK_DEFAULTS["OperatorProgression"]
        )
        WeaponProgression: MaaEndWeaponProgression = (
            MAAEND_SANITY_TASK_DEFAULTS["WeaponProgression"]
        )
        CrisisDrills: MaaEndCrisisDrills = (
            MAAEND_SANITY_TASK_DEFAULTS["CrisisDrills"]
        )
        RewardsSetOption: Literal["RewardsSetA", "RewardsSetB"] = (
            MAAEND_SANITY_TASK_DEFAULTS["RewardsSetOption"]
        )
        AutoEssenceSpecifiedLocation: MaaEndEssenceLocation = (
            MAAEND_SANITY_TASK_DEFAULTS["AutoEssenceSpecifiedLocation"]
        )
        IfSanity: Annotated[bool, Field(strict=True)] = True
        IfAutoUseSpMedication: Annotated[bool, Field(strict=True)] = True
        IfDijiangRewards: Annotated[bool, Field(strict=True)] = True
        IfDeliveryJobs: Annotated[bool, Field(strict=True)] = True
        IfSellProduct: Annotated[bool, Field(strict=True)] = True
        IfAutoStockpile: Annotated[bool, Field(strict=True)] = True
        IfAutoStockStaple: Annotated[bool, Field(strict=True)] = True
        IfVisitFriends: Annotated[bool, Field(strict=True)] = True
        IfCreditShoppingN2: Annotated[bool, Field(strict=True)] = True
        IfSeizeEntrustTask: Annotated[bool, Field(strict=True)] = True
        IfAutoEcoFarm: Annotated[bool, Field(strict=True)] = True
        IfAutoSell: Annotated[bool, Field(strict=True)] = True
        IfEnvironmentMonitoring: Annotated[bool, Field(strict=True)] = True
        IfAutoCollect: Annotated[bool, Field(strict=True)] = True
        IfDailyRewards: Annotated[bool, Field(strict=True)] = True
        IfResourceRecycleStation: Annotated[bool, Field(strict=True)] = True

    class DataGroup(ConfigGroup):
        LastProxyDate: DateText = "2000-01-01"
        ProxyTimes: Count0 = 0
        LastProxyStatus: Literal["未知", "成功", "失败"] = "未知"
        LastSklandDate: DateText = "2000-01-01"
        IfPassCheck: Annotated[bool, Field(strict=True)] = True

    Info: InfoGroup = Field(default_factory=InfoGroup)
    Task: TaskGroup = Field(default_factory=TaskGroup)
    Data: DataGroup = Field(default_factory=DataGroup)
    Notify: _CommonNotifyGroup = Field(default_factory=_CommonNotifyGroup)
    Notify_CustomWebhooks: CustomWebhooks = collection(Webhook)

    @virtual_field("Info.Tag")
    def tags(self) -> str:
        tags = _base_tags(
            self.Data.IfPassCheck,
            self.Data.LastProxyDate,
            self.Data.ProxyTimes,
            self.Info.RemainedDay,
            self.Info.Notes,
        )
        tags.insert(
            1,
            {
                "text": f"上次：{self.Data.LastProxyStatus}",
                "color": (
                    "red" if self.Data.LastProxyStatus == "失败" else "green"
                ),
            },
        )
        return json.dumps(tags, ensure_ascii=False)


class MaaEndUsers(ConfigCollection[MaaEndUser]):
    _default_entry_types = (MaaEndUser,)


class SrcUser(ConfigEntry):
    class InfoGroup(_BaseInfoGroup):
        Id: StrictText = ""
        Password: Annotated[str, Field(strict=True), encrypted()] = ""
        Mode: Literal["简洁", "详细"] = "简洁"
        Server: Literal[
            "CN-Official",
            "CN-Bilibili",
            "VN-Official",
            "OVERSEA-America",
            "OVERSEA-Asia",
            "OVERSEA-Europe",
            "OVERSEA-TWHKMO",
        ] = "CN-Official"

    class StageGroup(ConfigGroup):
        Channel: Literal["Relic", "Materials", "Ornament"] = "Relic"
        Relic: SrcRelic = "-"
        Materials: SrcMaterials = "-"
        Ornament: SrcOrnament = "-"
        ExtractReservedTrailblazePower: Annotated[
            bool, Field(strict=True)
        ] = False
        UseFuel: Annotated[bool, Field(strict=True)] = False
        FuelReserve: Annotated[int, Field(strict=True, ge=0, le=9999)] = 5
        EchoOfWar: SrcEcho = "-"
        SimulatedUniverseWorld: SrcSimulated = "-"

    class DataGroup(ConfigGroup):
        LastProxyDate: DateText = "2000-01-01"
        ProxyTimes: Count0 = 0
        IfPassCheck: Annotated[bool, Field(strict=True)] = True

    Info: InfoGroup = Field(default_factory=InfoGroup)
    Stage: StageGroup = Field(default_factory=StageGroup)
    Data: DataGroup = Field(default_factory=DataGroup)
    Notify: _CommonNotifyGroup = Field(default_factory=_CommonNotifyGroup)
    Notify_CustomWebhooks: CustomWebhooks = collection(Webhook)

    @virtual_field("Info.Tag")
    def tags(self) -> str:
        return json.dumps(
            _base_tags(
                self.Data.IfPassCheck,
                self.Data.LastProxyDate,
                self.Data.ProxyTimes,
                self.Info.RemainedDay,
                self.Info.Notes,
            ),
            ensure_ascii=False,
        )


class SrcUsers(ConfigCollection[SrcUser]):
    _default_entry_types = (SrcUser,)


class M9AUser(ConfigEntry):
    class InfoGroup(_BaseInfoGroup):
        Resource: StrictText = "官服"
        Account: StrictText = ""

    class TaskGroup(ConfigGroup):
        AvailableTasks: JsonListText = "[]"
        Queue: JsonListText = "[]"

    class DataGroup(ConfigGroup):
        LastProxyDate: DateText = "2000-01-01"
        LastPsychubeDate: DateText = "2000-01-01"
        LastLimboMonth: MonthText = "2000-01"
        LastLucidscapeMonth: MonthText = "2000-01"
        ProxyTimes: Count0 = 0
        IfPassCheck: Annotated[bool, Field(strict=True)] = True

    Info: InfoGroup = Field(default_factory=InfoGroup)
    Task: TaskGroup = Field(default_factory=TaskGroup)
    Data: DataGroup = Field(default_factory=DataGroup)
    Notify: _CommonNotifyGroup = Field(default_factory=_CommonNotifyGroup)
    Notify_CustomWebhooks: CustomWebhooks = collection(Webhook)

    @virtual_field("Info.Tag")
    def tags(self) -> str:
        return json.dumps(
            _base_tags(
                self.Data.IfPassCheck,
                self.Data.LastProxyDate,
                self.Data.ProxyTimes,
                self.Info.RemainedDay,
                self.Info.Notes,
            ),
            ensure_ascii=False,
        )


class M9AUsers(ConfigCollection[M9AUser]):
    _default_entry_types = (M9AUser,)


class MaaFWUser(ConfigEntry):
    class InfoGroup(_BaseInfoGroup):
        Account: StrictText = ""
        Password: Annotated[str, Field(strict=True), encrypted()] = ""
        Controller: StrictText = ""
        Resource: StrictText = ""

    class TaskGroup(ConfigGroup):
        SelectedPreset: StrictText = ""
        TaskSnapshot: JsonDictText = "{ }"

    class DeviceGroup(ConfigGroup):
        AdbAddress: StrictText = ""
        HWnd: Annotated[int, Field(strict=True, ge=0, le=999999999999)] = 0
        PlayCoverAddress: StrictText = ""
        PlayCoverUuid: StrictText = ""

    class DataGroup(ConfigGroup):
        LastProxyDate: DateText = "2000-01-01"
        ProxyTimes: Count0 = 0
        IfPassCheck: Annotated[bool, Field(strict=True)] = True
        LastProxyStatus: StrictText = "未知"
        PeriodTaskRecords: JsonDictText = "{ }"

    Info: InfoGroup = Field(default_factory=InfoGroup)
    Task: TaskGroup = Field(default_factory=TaskGroup)
    Device: DeviceGroup = Field(default_factory=DeviceGroup)
    Data: DataGroup = Field(default_factory=DataGroup)
    Notify: _CommonNotifyGroup = Field(default_factory=_CommonNotifyGroup)
    Notify_CustomWebhooks: CustomWebhooks = collection(Webhook)

    @virtual_field("Info.Tag")
    def tags(self) -> str:
        status_map = {
            "未知": "未知",
            "成功": "成功",
            "失败": "失败",
            "运行中": "运行中",
            "鏈煡": "未知",
            "鎴愬姛": "成功",
            "澶辫触": "失败",
            "杩愯涓?": "运行中",
        }
        status = status_map.get(
            self.Data.LastProxyStatus,
            self.Data.LastProxyStatus or "未知",
        )
        tags = _base_tags(
            self.Data.IfPassCheck,
            self.Data.LastProxyDate,
            self.Data.ProxyTimes,
            self.Info.RemainedDay,
            self.Info.Notes,
        )
        tags.insert(
            0,
            {
                "text": f"上次：{status}",
                "color": {
                    "成功": "green",
                    "失败": "red",
                    "运行中": "blue",
                }.get(status, "orange"),
            },
        )
        return json.dumps(tags, ensure_ascii=False)


class MaaFWUsers(ConfigCollection[MaaFWUser]):
    _default_entry_types = (MaaFWUser,)


class GeneralUser(ConfigEntry):
    class DataGroup(ConfigGroup):
        LastProxyDate: DateText = "2000-01-01"
        ProxyTimes: Count0 = 0

    Info: _BaseInfoGroup = Field(default_factory=_BaseInfoGroup)
    Data: DataGroup = Field(default_factory=DataGroup)
    Notify: _CommonNotifyGroup = Field(default_factory=_CommonNotifyGroup)
    Notify_CustomWebhooks: CustomWebhooks = collection(Webhook)

    @virtual_field("Info.Tag")
    def tags(self) -> str:
        return json.dumps(
            _base_tags(
                True,
                self.Data.LastProxyDate,
                self.Data.ProxyTimes,
                self.Info.RemainedDay,
                self.Info.Notes,
            ),
            ensure_ascii=False,
        )


class GeneralUsers(ConfigCollection[GeneralUser]):
    _default_entry_types = (GeneralUser,)


class OkwwUser(ConfigEntry):
    class InfoGroup(_BaseInfoGroup):
        Id: StrictText = ""
        Password: Annotated[str, Field(strict=True), encrypted()] = ""
        Mode: Literal["简洁", "详细"] = "详细"
        Resource: Literal["官服"] = "官服"

    class TaskGroup(ConfigGroup):
        TaskIndex: Annotated[int, Field(strict=True, ge=1, le=8)] = 1

    class DataGroup(ConfigGroup):
        LastProxyDate: DateText = "2000-01-01"
        ProxyTimes: Count0 = 0
        LastProxyStatus: Literal["未知", "成功", "失败"] = "未知"
        LastTaskIndex: Count0 = 0

    Info: InfoGroup = Field(default_factory=InfoGroup)
    Task: TaskGroup = Field(default_factory=TaskGroup)
    Data: DataGroup = Field(default_factory=DataGroup)
    Notify: _CommonNotifyGroup = Field(default_factory=_CommonNotifyGroup)
    Notify_CustomWebhooks: CustomWebhooks = collection(Webhook)

    @virtual_field("Info.Tag")
    def tags(self) -> str:
        tags = _base_tags(
            True,
            self.Data.LastProxyDate,
            self.Data.ProxyTimes,
            self.Info.RemainedDay,
            self.Info.Notes,
        )
        labels = {
            1: "日常",
            2: "多账号日常",
            3: "刷声骸",
            4: "半自动肉鸽",
            5: "凝素领域",
            6: "梦魇巢穴",
            7: "模拟领域",
            8: "无音区",
        }
        tags.insert(
            0,
            {
                "text": f"任务：{labels[self.Task.TaskIndex]}",
                "color": "blue",
            },
        )
        return json.dumps(tags, ensure_ascii=False)


class OkwwUsers(ConfigCollection[OkwwUser]):
    _default_entry_types = (OkwwUser,)


class PluginUser(ConfigEntry):
    """插件用户配置的原生宿主容器。"""

    class MetaGroup(ConfigGroup):
        PluginTypeKey: StrictText = ""

    class InfoGroup(ConfigGroup):
        Name: StrictText = "新用户"

    class PluginDataGroup(ConfigGroup):
        Config: Annotated[
            str,
            Field(strict=True),
            AfterValidator(_validate_json_dict_text),
            encrypted(),
        ] = "{}"

    Meta: MetaGroup = Field(default_factory=MetaGroup)
    Info: InfoGroup = Field(default_factory=InfoGroup)
    PluginData: PluginDataGroup = Field(default_factory=PluginDataGroup)


class PluginUsers(ConfigCollection[PluginUser]):
    _default_entry_types = (PluginUser,)


class MaaScript(ConfigEntry):
    class InfoGroup(ConfigGroup):
        Name: StrictText = "新 MAA 脚本"
        Path: FolderPathText = ""

    class EmulatorGroup(ConfigGroup):
        Id: EmulatorRef = "-"
        Index: StrictText = "-"

    class RunGroup(ConfigGroup):
        TaskTransitionMethod: Literal[
            "NoAction",
            "ExitGame",
            "ExitEmulator",
        ] = "ExitEmulator"
        ProxyTimesLimit: Count0 = 0
        RunTimesLimit: Count1 = 3
        AnnihilationTimeLimit: Count1 = 40
        RoutineTimeLimit: Count1 = 10
        AnnihilationAvoidWaste: Annotated[bool, Field(strict=True)] = False

    Info: InfoGroup = Field(default_factory=InfoGroup)
    Emulator: EmulatorGroup = Field(default_factory=EmulatorGroup)
    Run: RunGroup = Field(default_factory=RunGroup)
    UserData: MaaUsers = collection(MaaUser)


class MaaEndScript(ConfigEntry):
    class InfoGroup(ConfigGroup):
        Name: StrictText = "新 MaaEnd 脚本"
        Path: FolderPathText = ""

    class RunGroup(ConfigGroup):
        RunTimeLimit: Count1 = 10
        ProxyTimesLimit: Count0 = 0
        RunTimesLimit: Count1 = 3

    class GameGroup(ConfigGroup):
        ControllerType: Literal["Win32-Front", "ADB"] = "Win32-Front"
        Path: FilePathText = ""
        Arguments: ArgumentText = ""
        WaitTime: Annotated[int, Field(strict=True, ge=60, le=9999)] = 60
        EmulatorId: EmulatorRef = "-"
        EmulatorIndex: StrictText = "-"
        CloseOnFinish: Annotated[bool, Field(strict=True)] = True

    Info: InfoGroup = Field(default_factory=InfoGroup)
    Run: RunGroup = Field(default_factory=RunGroup)
    Game: GameGroup = Field(default_factory=GameGroup)
    UserData: MaaEndUsers = collection(MaaEndUser)


class SrcScript(ConfigEntry):
    class InfoGroup(ConfigGroup):
        Name: StrictText = "新 SRC 脚本"
        Path: FolderPathText = ""

    class EmulatorGroup(ConfigGroup):
        Id: EmulatorRef = "-"
        Index: StrictText = "-"

    class RunGroup(ConfigGroup):
        TaskTransitionMethod: Literal[
            "ExitGame",
            "ExitEmulator",
        ] = "ExitGame"
        ProxyTimesLimit: Count0 = 0
        RunTimesLimit: Count1 = 3
        RunTimeLimit: Count1 = 10

    Info: InfoGroup = Field(default_factory=InfoGroup)
    Emulator: EmulatorGroup = Field(default_factory=EmulatorGroup)
    Run: RunGroup = Field(default_factory=RunGroup)
    UserData: SrcUsers = collection(SrcUser)


class M9AScript(ConfigEntry):
    class InfoGroup(ConfigGroup):
        Name: StrictText = "新 M9A 脚本"
        Path: FolderPathText = ""

    class EmulatorGroup(ConfigGroup):
        Id: EmulatorRef = "-"
        Index: StrictText = "-"

    class RunGroup(ConfigGroup):
        ProxyTimesLimit: Count0 = 0
        RunTimesLimit: Count1 = 3
        RunTimeLimit: Count1 = 10
        IfAutoUpdateAfterQueue: Annotated[bool, Field(strict=True)] = False
        IfPsychubeDailyOnce: Annotated[bool, Field(strict=True)] = False
        IfSleepDreamMonthlyOnce: Annotated[bool, Field(strict=True)] = False

    Info: InfoGroup = Field(default_factory=InfoGroup)
    Emulator: EmulatorGroup = Field(default_factory=EmulatorGroup)
    Run: RunGroup = Field(default_factory=RunGroup)
    UserData: M9AUsers = collection(M9AUser)


class MaaFWScript(ConfigEntry):
    class InfoGroup(ConfigGroup):
        Name: StrictText = "新 MaaFW 脚本"
        ProjectLabel: StrictText = ""
        Path: FolderPathText = ""
        Controller: StrictText = ""
        Resource: StrictText = ""

    class EmulatorGroup(ConfigGroup):
        Id: EmulatorRef = "-"
        Index: StrictText = "-"

    class DeviceGroup(ConfigGroup):
        AdbPath: FilePathText = ""
        AdbAddress: StrictText = ""
        AdbScreencapMethods: Annotated[
            int,
            Field(strict=True, ge=-999, le=999999999999),
        ] = -57
        AdbInputMethods: Annotated[
            int,
            Field(strict=True, ge=-999, le=999999999999),
        ] = -1
        HWnd: Annotated[
            int,
            Field(strict=True, ge=0, le=999999999999),
        ] = 0
        Win32ScreencapMethod: Annotated[
            int,
            Field(strict=True, ge=0, le=999999999999),
        ] = 0
        Win32MouseMethod: Annotated[
            int,
            Field(strict=True, ge=0, le=999999999999),
        ] = 0
        Win32KeyboardMethod: Annotated[
            int,
            Field(strict=True, ge=0, le=999999999999),
        ] = 0
        GamepadType: Annotated[
            int,
            Field(strict=True, ge=0, le=999999999999),
        ] = 0
        PlayCoverAddress: StrictText = ""
        PlayCoverUuid: StrictText = ""

    class GameGroup(ConfigGroup):
        Path: FilePathText = ""
        Arguments: ArgumentText = ""
        WaitTime: Count0 = 60
        CloseOnFinish: Annotated[bool, Field(strict=True)] = True

    class UpdateGroup(ConfigGroup):
        IfAutoUpdate: Annotated[bool, Field(strict=True)] = True
        Source: Literal["MirrorChyan"] = "MirrorChyan"
        Channel: Literal["", "stable", "beta"] = ""
        MirrorChyanCDK: Annotated[
            str,
            Field(strict=True),
            encrypted(),
        ] = ""

    class RunGroup(ConfigGroup):
        ProxyTimesLimit: Count0 = 0
        RunTimesLimit: Count1 = 1
        RunTimeLimit: Count1 = 30
        DailyOnceTasks: JsonListText = "[ ]"
        WeeklyOnceTasks: JsonListText = "[ ]"
        MonthlyOnceTasks: JsonListText = "[ ]"

    Info: InfoGroup = Field(default_factory=InfoGroup)
    Emulator: EmulatorGroup = Field(default_factory=EmulatorGroup)
    Device: DeviceGroup = Field(default_factory=DeviceGroup)
    Game: GameGroup = Field(default_factory=GameGroup)
    Update: UpdateGroup = Field(default_factory=UpdateGroup)
    Run: RunGroup = Field(default_factory=RunGroup)
    UserData: MaaFWUsers = collection(MaaFWUser)


class GeneralScript(ConfigEntry):
    class InfoGroup(ConfigGroup):
        Name: StrictText = "新通用脚本"
        RootPath: ScriptRootPathText = ""

    class ScriptGroup(ConfigGroup):
        ScriptPath: FilePathText = ""
        Arguments: AdvancedArgumentText = ""
        IfTrackProcess: Annotated[bool, Field(strict=True)] = False
        TrackProcessName: StrictText = ""
        TrackProcessExe: StrictText = ""
        TrackProcessCmdline: ArgumentText = ""
        ConfigPath: FilePathText = ""
        ConfigPathMode: Literal["File", "Folder"] = "File"
        UpdateConfigMode: Literal[
            "Never",
            "Success",
            "Failure",
            "Always",
        ] = "Never"
        LogPath: FilePathText = ""
        LogPathFormat: StrictText = "%Y-%m-%d"
        LogTimeStart: Count1 = 1
        LogTimeEnd: Count1 = 1
        LogTimeFormat: StrictText = "%Y-%m-%d %H:%M:%S"
        SuccessLog: StrictText = ""
        ErrorLog: StrictText = ""

    class GameGroup(ConfigGroup):
        Enabled: Annotated[bool, Field(strict=True)] = False
        Type: Literal["Emulator", "Client", "URL"] = "Emulator"
        Path: FilePathText = ""
        URL: StrictText = ""
        ProcessName: StrictText = ""
        Arguments: ArgumentText = ""
        WaitTime: Count0 = 0
        IfForceClose: Annotated[bool, Field(strict=True)] = False
        EmulatorId: EmulatorRef = "-"
        EmulatorIndex: StrictText = "-"

    class RunGroup(ConfigGroup):
        ProxyTimesLimit: Count0 = 0
        RunTimesLimit: Count1 = 3
        RunTimeLimit: Count1 = 10

    Info: InfoGroup = Field(default_factory=InfoGroup)
    Script: ScriptGroup = Field(default_factory=ScriptGroup)
    Game: GameGroup = Field(default_factory=GameGroup)
    Run: RunGroup = Field(default_factory=RunGroup)
    UserData: GeneralUsers = collection(GeneralUser)


class OkwwScript(ConfigEntry):
    class InfoGroup(ConfigGroup):
        Name: StrictText = "鸣潮"
        RootPath: ScriptRootPathText = ""

    class GameGroup(ConfigGroup):
        Enabled: Annotated[bool, Field(strict=True)] = False
        LaunchBeforeTask: Annotated[bool, Field(strict=True)] = False
        Path: FilePathText = ""
        Arguments: ArgumentText = ""
        WaitTime: Count0 = 60

    class RunGroup(ConfigGroup):
        ProxyTimesLimit: Count0 = 0
        RunTimesLimit: Count1 = 1
        RunTimeLimit: Count1 = 60

    Info: InfoGroup = Field(default_factory=InfoGroup)
    Game: GameGroup = Field(default_factory=GameGroup)
    Run: RunGroup = Field(default_factory=RunGroup)
    UserData: OkwwUsers = collection(OkwwUser)


class PluginScript(ConfigEntry):
    """插件脚本配置的原生宿主容器。"""

    class MetaGroup(ConfigGroup):
        PluginTypeKey: StrictText = ""

    class InfoGroup(ConfigGroup):
        Name: StrictText = "新插件脚本"

    class PluginDataGroup(ConfigGroup):
        Config: Annotated[
            str,
            Field(strict=True),
            AfterValidator(_validate_json_dict_text),
            encrypted(),
        ] = "{}"

    Meta: MetaGroup = Field(default_factory=MetaGroup)
    Info: InfoGroup = Field(default_factory=InfoGroup)
    PluginData: PluginDataGroup = Field(default_factory=PluginDataGroup)
    UserData: PluginUsers = collection(PluginUser)


class Scripts(ConfigCollection[ConfigEntry]):
    """独立 ``ScriptConfig.json`` 生产根。"""

    _default_entry_types = (
        MaaScript,
        MaaEndScript,
        SrcScript,
        M9AScript,
        MaaFWScript,
        GeneralScript,
        OkwwScript,
        PluginScript,
    )


@dataclass(frozen=True)
class _FieldSpec:
    default: object
    kind: Literal[
        "str",
        "bool",
        "int",
        "option",
        "json-list",
        "json-dict",
        "ref",
        "date",
        "month",
        "username",
        "file",
        "folder",
        "argument",
        "script-root",
        "advanced-argument",
    ]
    minimum: int | None = None
    maximum: int | None = None
    options: tuple[str, ...] = ()
    encrypted_value: bool = False
    encrypted_json: bool = False


def _str(
    default: str = "",
    *,
    encrypted_value: bool = False,
    encrypted_json: bool = False,
) -> _FieldSpec:
    return _FieldSpec(
        default,
        "str",
        encrypted_value=encrypted_value,
        encrypted_json=encrypted_json,
    )


def _bool(default: bool) -> _FieldSpec:
    return _FieldSpec(default, "bool")


def _int(default: int, minimum: int, maximum: int) -> _FieldSpec:
    return _FieldSpec(
        default,
        "int",
        minimum=minimum,
        maximum=maximum,
    )


def _option(default: str, *options: str) -> _FieldSpec:
    return _FieldSpec(default, "option", options=options)


def _json_list(default: str = "[ ]") -> _FieldSpec:
    return _FieldSpec(default, "json-list")


def _json_dict(default: str = "{ }") -> _FieldSpec:
    return _FieldSpec(default, "json-dict")


def _ref(default: str = "-") -> _FieldSpec:
    return _FieldSpec(default, "ref")


def _date(default: str = "2000-01-01") -> _FieldSpec:
    return _FieldSpec(default, "date")


def _month(default: str = "2000-01") -> _FieldSpec:
    return _FieldSpec(default, "month")


def _username(default: str = "新用户") -> _FieldSpec:
    return _FieldSpec(default, "username")


def _file(default: str = "") -> _FieldSpec:
    return _FieldSpec(default, "file")


def _folder(default: str = "") -> _FieldSpec:
    return _FieldSpec(default, "folder")


def _argument(default: str = "") -> _FieldSpec:
    return _FieldSpec(default, "argument")


def _script_root(default: str = "") -> _FieldSpec:
    return _FieldSpec(default, "script-root")


def _advanced_argument(default: str = "") -> _FieldSpec:
    return _FieldSpec(default, "advanced-argument")


_MAA_GROUPS = {
    "Info": {"Name": _str("新 MAA 脚本"), "Path": _folder()},
    "Emulator": {"Id": _ref(), "Index": _str("-")},
    "Run": {
        "TaskTransitionMethod": _option(
            "ExitEmulator",
            "NoAction",
            "ExitGame",
            "ExitEmulator",
        ),
        "ProxyTimesLimit": _int(0, 0, 9999),
        "RunTimesLimit": _int(3, 1, 9999),
        "AnnihilationTimeLimit": _int(40, 1, 9999),
        "RoutineTimeLimit": _int(10, 1, 9999),
        "AnnihilationAvoidWaste": _bool(False),
    },
}
_MAAEND_GROUPS = {
    "Info": {"Name": _str("新 MaaEnd 脚本"), "Path": _folder()},
    "Run": {
        "RunTimeLimit": _int(10, 1, 9999),
        "ProxyTimesLimit": _int(0, 0, 9999),
        "RunTimesLimit": _int(3, 1, 9999),
    },
    "Game": {
        "ControllerType": _option("Win32-Front", "Win32-Front", "ADB"),
        "Path": _file(),
        "Arguments": _argument(),
        "WaitTime": _int(60, 60, 9999),
        "EmulatorId": _ref(),
        "EmulatorIndex": _str("-"),
        "CloseOnFinish": _bool(True),
    },
}
_SRC_GROUPS = {
    "Info": {"Name": _str("新 SRC 脚本"), "Path": _folder()},
    "Emulator": {"Id": _ref(), "Index": _str("-")},
    "Run": {
        "TaskTransitionMethod": _option(
            "ExitGame",
            "ExitGame",
            "ExitEmulator",
        ),
        "ProxyTimesLimit": _int(0, 0, 9999),
        "RunTimesLimit": _int(3, 1, 9999),
        "RunTimeLimit": _int(10, 1, 9999),
    },
}
_M9A_GROUPS = {
    "Info": {"Name": _str("新 M9A 脚本"), "Path": _folder()},
    "Emulator": {"Id": _ref(), "Index": _str("-")},
    "Run": {
        "ProxyTimesLimit": _int(0, 0, 9999),
        "RunTimesLimit": _int(3, 1, 9999),
        "RunTimeLimit": _int(10, 1, 9999),
        "IfAutoUpdateAfterQueue": _bool(False),
        "IfPsychubeDailyOnce": _bool(False),
        "IfSleepDreamMonthlyOnce": _bool(False),
    },
}
_MAAFW_GROUPS = {
    "Info": {
        "Name": _str("新 MaaFW 脚本"),
        "ProjectLabel": _str(),
        "Path": _folder(),
        "Controller": _str(),
        "Resource": _str(),
    },
    "Emulator": {"Id": _ref(), "Index": _str("-")},
    "Device": {
        "AdbPath": _file(),
        "AdbAddress": _str(),
        "AdbScreencapMethods": _int(-57, -999, 999999999999),
        "AdbInputMethods": _int(-1, -999, 999999999999),
        "HWnd": _int(0, 0, 999999999999),
        "Win32ScreencapMethod": _int(0, 0, 999999999999),
        "Win32MouseMethod": _int(0, 0, 999999999999),
        "Win32KeyboardMethod": _int(0, 0, 999999999999),
        "GamepadType": _int(0, 0, 999999999999),
        "PlayCoverAddress": _str(),
        "PlayCoverUuid": _str(),
    },
    "Game": {
        "Path": _file(),
        "Arguments": _argument(),
        "WaitTime": _int(60, 0, 9999),
        "CloseOnFinish": _bool(True),
    },
    "Update": {
        "IfAutoUpdate": _bool(True),
        "Source": _option("MirrorChyan", "MirrorChyan"),
        "Channel": _option("", "", "stable", "beta"),
        "MirrorChyanCDK": _str("", encrypted_value=True),
    },
    "Run": {
        "ProxyTimesLimit": _int(0, 0, 9999),
        "RunTimesLimit": _int(1, 1, 9999),
        "RunTimeLimit": _int(30, 1, 9999),
        "DailyOnceTasks": _json_list(),
        "WeeklyOnceTasks": _json_list(),
        "MonthlyOnceTasks": _json_list(),
    },
}
_GENERAL_GROUPS = {
    "Info": {"Name": _str("新通用脚本"), "RootPath": _script_root()},
    "Script": {
        "ScriptPath": _file(),
        "Arguments": _advanced_argument(),
        "IfTrackProcess": _bool(False),
        "TrackProcessName": _str(),
        "TrackProcessExe": _str(),
        "TrackProcessCmdline": _argument(),
        "ConfigPath": _file(),
        "ConfigPathMode": _option("File", "File", "Folder"),
        "UpdateConfigMode": _option(
            "Never",
            "Never",
            "Success",
            "Failure",
            "Always",
        ),
        "LogPath": _file(),
        "LogPathFormat": _str("%Y-%m-%d"),
        "LogTimeStart": _int(1, 1, 9999),
        "LogTimeEnd": _int(1, 1, 9999),
        "LogTimeFormat": _str("%Y-%m-%d %H:%M:%S"),
        "SuccessLog": _str(),
        "ErrorLog": _str(),
    },
    "Game": {
        "Enabled": _bool(False),
        "Type": _option("Emulator", "Emulator", "Client", "URL"),
        "Path": _file(),
        "URL": _str(),
        "ProcessName": _str(),
        "Arguments": _argument(),
        "WaitTime": _int(0, 0, 9999),
        "IfForceClose": _bool(False),
        "EmulatorId": _ref(),
        "EmulatorIndex": _str("-"),
    },
    "Run": {
        "ProxyTimesLimit": _int(0, 0, 9999),
        "RunTimesLimit": _int(3, 1, 9999),
        "RunTimeLimit": _int(10, 1, 9999),
    },
}
_OKWW_GROUPS = {
    "Info": {"Name": _str("鸣潮"), "RootPath": _script_root()},
    "Game": {
        "Enabled": _bool(False),
        "LaunchBeforeTask": _bool(False),
        "Path": _file(),
        "Arguments": _argument(),
        "WaitTime": _int(60, 0, 9999),
    },
    "Run": {
        "ProxyTimesLimit": _int(0, 0, 9999),
        "RunTimesLimit": _int(1, 1, 9999),
        "RunTimeLimit": _int(60, 1, 9999),
    },
}
_PLUGIN_GROUPS = {
    "Meta": {"PluginTypeKey": _str()},
    "Info": {"Name": _str("新插件脚本")},
    "PluginData": {
        "Config": _str("{}", encrypted_value=True, encrypted_json=True)
    },
}
_PLUGIN_USER_GROUPS = {
    "Meta": {"PluginTypeKey": _str()},
    "Info": {"Name": _str("新用户")},
    "PluginData": {
        "Config": _str("{}", encrypted_value=True, encrypted_json=True)
    },
}
_WEBHOOK_GROUPS = {
    "Info": {
        "Name": _str("新自定义 Webhook 通知"),
        "Enabled": _bool(True),
    },
    "Data": {
        "Url": _str("", encrypted_value=True),
        "Template": _str(),
        "Headers": _str(
            "{ }",
            encrypted_value=True,
            encrypted_json=True,
        ),
        "Method": _option("POST", "POST", "GET"),
    },
}
_COMMON_NOTIFY_GROUP = {
    "Enabled": _bool(False),
    "IfSendStatistic": _bool(False),
    "IfSendMail": _bool(False),
    "ToAddress": _str(),
    "IfServerChan": _bool(False),
    "ServerChanKey": _str("", encrypted_value=True),
}


def _base_user_info() -> dict[str, _FieldSpec]:
    return {
        "Name": _username(),
        "Status": _bool(True),
        "RemainedDay": _int(-1, -1, 9999),
        "IfScriptBeforeTask": _bool(False),
        "ScriptBeforeTask": _file(),
        "IfScriptAfterTask": _bool(False),
        "ScriptAfterTask": _file(),
        "Notes": _str("无"),
    }


_MAA_USER_GROUPS = {
    "Info": {
        **_base_user_info(),
        "Id": _str(),
        "Password": _str("", encrypted_value=True),
        "Mode": _option("简洁", "简洁", "详细"),
        "StageMode": _FieldSpec("Fixed", "ref"),
        "Server": _option(
            "Official",
            "Official",
            "Bilibili",
            "YoStarEN",
            "YoStarJP",
            "YoStarKR",
            "txwy",
        ),
        "Annihilation": _option(
            "Annihilation",
            "Close",
            "Annihilation",
            "Chernobog@Annihilation",
            "LungmenOutskirts@Annihilation",
            "LungmenDowntown@Annihilation",
        ),
        "InfrastMode": _option(
            "Normal",
            "Normal",
            "Rotation",
            "Custom",
        ),
        "MedicineNumb": _int(0, 0, 9999),
        "SeriesNumb": _option(
            "0",
            "0",
            "6",
            "5",
            "4",
            "3",
            "2",
            "1",
            "-1",
        ),
        "Stage": _str("-"),
        "Stage_1": _str("-"),
        "Stage_2": _str("-"),
        "Stage_3": _str("-"),
        "Stage_Remain": _str("-"),
        "IfSkland": _bool(False),
        "SklandToken": _str("", encrypted_value=True),
    },
    "Data": {
        "LastProxyDate": _date(),
        "LastSklandDate": _date(),
        "ProxyTimes": _int(0, 0, 9999),
        "IfPassCheck": _bool(True),
        "CustomInfrast": _json_dict(),
        "InfrastIndex": _str("0"),
    },
    "Task": {
        "IfStartUp": _bool(True),
        "IfFight": _bool(True),
        "IfInfrast": _bool(True),
        "IfRecruit": _bool(True),
        "IfMall": _bool(True),
        "IfAward": _bool(True),
        "IfRoguelike": _bool(False),
        "IfReclamation": _bool(False),
    },
    "Notify": {
        **_COMMON_NOTIFY_GROUP,
        "IfSendSixStar": _bool(False),
    },
}
_MAAEND_USER_GROUPS = {
    "Info": {
        **_base_user_info(),
        "Id": _str(),
        "Password": _str("", encrypted_value=True),
        "Mode": _option("简洁", "简洁", "详细"),
        "IfQuickConfig": _bool(True),
        "SanityMode": _str("Fixed"),
        "Resource": _option("官服", "官服"),
        "IfSkland": _bool(False),
        "SklandToken": _str("", encrypted_value=True),
    },
    "Task": {
        "SanityTaskType": _option(
            MAAEND_SANITY_TASK_DEFAULTS["SanityTaskType"],
            *MAAEND_SANITY_TASK_TYPES,
        ),
        "OperatorProgression": _option(
            MAAEND_SANITY_TASK_DEFAULTS["OperatorProgression"],
            *MAAEND_PROTOCOL_SPACE_TASK_OPTIONS["OperatorProgression"],
        ),
        "WeaponProgression": _option(
            MAAEND_SANITY_TASK_DEFAULTS["WeaponProgression"],
            *MAAEND_PROTOCOL_SPACE_TASK_OPTIONS["WeaponProgression"],
        ),
        "CrisisDrills": _option(
            MAAEND_SANITY_TASK_DEFAULTS["CrisisDrills"],
            *MAAEND_PROTOCOL_SPACE_TASK_OPTIONS["CrisisDrills"],
        ),
        "RewardsSetOption": _option(
            MAAEND_SANITY_TASK_DEFAULTS["RewardsSetOption"],
            "RewardsSetA",
            "RewardsSetB",
        ),
        "AutoEssenceSpecifiedLocation": _option(
            MAAEND_SANITY_TASK_DEFAULTS[
                "AutoEssenceSpecifiedLocation"
            ],
            *MAAEND_AUTO_ESSENCE_LOCATION_OPTIONS,
        ),
        **{f"If{name}": _bool(True) for name in MAAEND_TASKS},
    },
    "Data": {
        "LastProxyDate": _date(),
        "ProxyTimes": _int(0, 0, 9999),
        "LastProxyStatus": _option("未知", "未知", "成功", "失败"),
        "LastSklandDate": _date(),
        "IfPassCheck": _bool(True),
    },
    "Notify": dict(_COMMON_NOTIFY_GROUP),
}
_SRC_USER_GROUPS = {
    "Info": {
        **_base_user_info(),
        "Id": _str(),
        "Password": _str("", encrypted_value=True),
        "Mode": _option("简洁", "简洁", "详细"),
        "Server": _option(
            "CN-Official",
            "CN-Official",
            "CN-Bilibili",
            "VN-Official",
            "OVERSEA-America",
            "OVERSEA-Asia",
            "OVERSEA-Europe",
            "OVERSEA-TWHKMO",
        ),
    },
    "Stage": {
        "Channel": _option(
            "Relic",
            "Relic",
            "Materials",
            "Ornament",
        ),
        "Relic": _option("-", *_SRC_RELIC_OPTIONS),
        "Materials": _option("-", *_SRC_MATERIAL_OPTIONS),
        "Ornament": _option("-", *_SRC_ORNAMENT_OPTIONS),
        "ExtractReservedTrailblazePower": _bool(False),
        "UseFuel": _bool(False),
        "FuelReserve": _int(5, 0, 9999),
        "EchoOfWar": _option("-", *_SRC_ECHO_OPTIONS),
        "SimulatedUniverseWorld": _option(
            "-",
            *_SRC_SIMULATED_OPTIONS,
        ),
    },
    "Data": {
        "LastProxyDate": _date(),
        "ProxyTimes": _int(0, 0, 9999),
        "IfPassCheck": _bool(True),
    },
    "Notify": dict(_COMMON_NOTIFY_GROUP),
}
_M9A_USER_GROUPS = {
    "Info": {
        **_base_user_info(),
        "Resource": _str("官服"),
        "Account": _str(),
    },
    "Task": {
        "AvailableTasks": _json_list("[]"),
        "Queue": _json_list("[]"),
    },
    "Data": {
        "LastProxyDate": _date(),
        "LastPsychubeDate": _date(),
        "LastLimboMonth": _month(),
        "LastLucidscapeMonth": _month(),
        "ProxyTimes": _int(0, 0, 9999),
        "IfPassCheck": _bool(True),
    },
    "Notify": dict(_COMMON_NOTIFY_GROUP),
}
_MAAFW_USER_GROUPS = {
    "Info": {
        **_base_user_info(),
        "Account": _str(),
        "Password": _str("", encrypted_value=True),
        "Controller": _str(),
        "Resource": _str(),
    },
    "Task": {
        "SelectedPreset": _str(),
        "TaskSnapshot": _json_dict(),
    },
    "Device": {
        "AdbAddress": _str(),
        "HWnd": _int(0, 0, 999999999999),
        "PlayCoverAddress": _str(),
        "PlayCoverUuid": _str(),
    },
    "Data": {
        "LastProxyDate": _date(),
        "ProxyTimes": _int(0, 0, 9999),
        "IfPassCheck": _bool(True),
        "LastProxyStatus": _str("未知"),
        "PeriodTaskRecords": _json_dict(),
    },
    "Notify": dict(_COMMON_NOTIFY_GROUP),
}
_GENERAL_USER_GROUPS = {
    "Info": _base_user_info(),
    "Data": {
        "LastProxyDate": _date(),
        "ProxyTimes": _int(0, 0, 9999),
    },
    "Notify": dict(_COMMON_NOTIFY_GROUP),
}
_OKWW_USER_GROUPS = {
    "Info": {
        **_base_user_info(),
        "Id": _str(),
        "Password": _str("", encrypted_value=True),
        "Mode": _option("详细", "简洁", "详细"),
        "Resource": _option("官服", "官服"),
    },
    "Task": {"TaskIndex": _int(1, 1, 8)},
    "Data": {
        "LastProxyDate": _date(),
        "ProxyTimes": _int(0, 0, 9999),
        "LastProxyStatus": _option("未知", "未知", "成功", "失败"),
        "LastTaskIndex": _int(0, 0, 9999),
    },
    "Notify": dict(_COMMON_NOTIFY_GROUP),
}
_USER_VIRTUAL_FIELDS = {
    "MaaUser": {
        "Info": {"Tag", "InfrastName", "InfrastIndex"},
    },
    "MaaEndUser": {"Info": {"Tag"}},
    "SrcUser": {"Info": {"Tag"}},
    "M9AUser": {"Info": {"Tag"}},
    "MaaFWUser": {"Info": {"Tag"}},
    "GeneralUser": {"Info": {"Tag"}},
    "OkwwUser": {"Info": {"Tag"}},
    "PluginUser": {},
}


@dataclass(frozen=True)
class _ScriptDescriptor:
    legacy_type: str
    v2_type: str
    groups: dict[str, dict[str, _FieldSpec]]
    user_legacy_type: str
    user_v2_type: str
    user_groups: dict[str, dict[str, _FieldSpec]]


_DESCRIPTORS = (
    _ScriptDescriptor(
        "MaaConfig",
        "MaaScript",
        _MAA_GROUPS,
        "MaaUserConfig",
        "MaaUser",
        _MAA_USER_GROUPS,
    ),
    _ScriptDescriptor(
        "MaaEndConfig",
        "MaaEndScript",
        _MAAEND_GROUPS,
        "MaaEndUserConfig",
        "MaaEndUser",
        _MAAEND_USER_GROUPS,
    ),
    _ScriptDescriptor(
        "SrcConfig",
        "SrcScript",
        _SRC_GROUPS,
        "SrcUserConfig",
        "SrcUser",
        _SRC_USER_GROUPS,
    ),
    _ScriptDescriptor(
        "M9AConfig",
        "M9AScript",
        _M9A_GROUPS,
        "M9AUserConfig",
        "M9AUser",
        _M9A_USER_GROUPS,
    ),
    _ScriptDescriptor(
        "MaaFWConfig",
        "MaaFWScript",
        _MAAFW_GROUPS,
        "MaaFWUserConfig",
        "MaaFWUser",
        _MAAFW_USER_GROUPS,
    ),
    _ScriptDescriptor(
        "GeneralConfig",
        "GeneralScript",
        _GENERAL_GROUPS,
        "GeneralUserConfig",
        "GeneralUser",
        _GENERAL_USER_GROUPS,
    ),
    _ScriptDescriptor(
        "OkwwConfig",
        "OkwwScript",
        _OKWW_GROUPS,
        "OkwwUserConfig",
        "OkwwUser",
        _OKWW_USER_GROUPS,
    ),
    _ScriptDescriptor(
        "PluginScriptConfig",
        "PluginScript",
        _PLUGIN_GROUPS,
        "PluginUserConfig",
        "PluginUser",
        _PLUGIN_USER_GROUPS,
    ),
)
_BY_LEGACY_TYPE = {item.legacy_type: item for item in _DESCRIPTORS}
_BY_V2_TYPE = {item.v2_type: item for item in _DESCRIPTORS}


def _require_dict(value: object, *, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{path} 必须是对象")
    if not all(isinstance(key, str) for key in value):
        raise TypeError(f"{path} 的键必须是字符串")
    return value


def _parse_uid(value: object, *, path: str) -> tuple[UUID, str]:
    if not isinstance(value, str):
        raise ValueError(f"{path} 必须是 UUID 字符串")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise ValueError(f"{path} 不是有效 UUID") from None
    return parsed, str(parsed)


def _validate_field(
    value: object,
    spec: _FieldSpec,
    *,
    path: str,
    rollback: bool,
) -> object:
    if spec.encrypted_value:
        if not isinstance(value, str):
            raise TypeError(f"{path} 必须是字符串")
        if is_probable_dpapi_ciphertext(value):
            return value
        if value:
            raise ValueError(f"{path} 持久化值必须保持 DPAPI 密文")
        return value

    if spec.kind == "str":
        if not isinstance(value, str):
            raise TypeError(f"{path} 必须是字符串")
        return value
    if spec.kind == "bool":
        if not isinstance(value, bool):
            raise TypeError(f"{path} 必须是布尔值")
        return value
    if spec.kind == "int":
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{path} 必须是整数")
        assert spec.minimum is not None and spec.maximum is not None
        if not spec.minimum <= value <= spec.maximum:
            raise ValueError(
                f"{path} 必须在 {spec.minimum}..{spec.maximum} 范围内"
            )
        return value
    if spec.kind == "option":
        if not isinstance(value, str) or value not in spec.options:
            raise ValueError(f"{path} 不在允许选项中")
        return value
    if spec.kind == "json-list":
        if not isinstance(value, str):
            raise TypeError(f"{path} 必须是 JSON 字符串")
        _load_json_text(value, expected=list, path=path)
        return value
    if spec.kind == "json-dict":
        if not isinstance(value, str):
            raise TypeError(f"{path} 必须是 JSON 字符串")
        _load_json_text(value, expected=dict, path=path)
        return value
    if spec.kind == "ref":
        if not isinstance(value, str):
            raise TypeError(f"{path} 必须是引用字符串")
        return (
            _validate_plan_ref(value)
            if spec.default == "Fixed"
            else _validate_uuid_or_dash(value)
        )
    if spec.kind == "date":
        if not isinstance(value, str):
            raise TypeError(f"{path} 必须是日期字符串")
        return _validate_date(value)
    if spec.kind == "month":
        if not isinstance(value, str):
            raise TypeError(f"{path} 必须是月份字符串")
        return _validate_month(value)
    if spec.kind == "username":
        if not isinstance(value, str):
            raise TypeError(f"{path} 必须是用户名字符串")
        return _validate_username(value)
    if spec.kind == "file":
        if not isinstance(value, str):
            raise TypeError(f"{path} 必须是文件路径字符串")
        return _validate_file_path(value)
    if spec.kind == "folder":
        if not isinstance(value, str):
            raise TypeError(f"{path} 必须是文件夹路径字符串")
        return _validate_folder_path(value)
    if spec.kind == "argument":
        if not isinstance(value, str):
            raise TypeError(f"{path} 必须是启动参数字符串")
        return _validate_argument_text(value)
    if spec.kind == "script-root":
        if not isinstance(value, str):
            raise TypeError(f"{path} 必须是脚本根目录字符串")
        return _validate_script_root_path(value)
    if spec.kind == "advanced-argument":
        if not isinstance(value, str):
            raise TypeError(f"{path} 必须是高级启动参数字符串")
        return _validate_advanced_argument_text(value)
    raise AssertionError(f"未实现的字段规格: {spec.kind}")


def _normalize_script_entry(
    value: object,
    *,
    descriptor: _ScriptDescriptor,
    path: str,
    rollback: bool,
) -> WireDict:
    entry = _require_dict(value, path=path)
    allowed = set(descriptor.groups) | {"SubConfigsInfo", "UserData"}
    unknown = sorted(set(entry) - allowed)
    if unknown:
        raise ValueError(
            "未知 ScriptConfig 路径: "
            + ", ".join(f"{path}.{name}" for name in unknown)
        )
    if "SubConfigsInfo" in entry and "UserData" in entry:
        raise ValueError(
            f"{path}.SubConfigsInfo.UserData 与 {path}.UserData 别名冲突"
        )

    normalized: WireDict = {}
    for group_name, fields in descriptor.groups.items():
        raw_group = _require_dict(
            entry.get(group_name, {}),
            path=f"{path}.{group_name}",
        )
        unknown_fields = sorted(set(raw_group) - set(fields))
        if unknown_fields:
            raise ValueError(
                "未知 ScriptConfig 路径: "
                + ", ".join(
                    f"{path}.{group_name}.{name}"
                    for name in unknown_fields
                )
            )
        normalized[group_name] = {
            name: _validate_field(
                raw_group.get(name, spec.default),
                spec,
                path=f"{path}.{group_name}.{name}",
                rollback=rollback,
            )
            for name, spec in fields.items()
        }
    return normalized


def _parse_legacy_collection(
    value: object,
    *,
    expected_type: str,
    v2_type: str,
    groups: dict[str, dict[str, _FieldSpec]],
    virtual_fields: dict[str, set[str]],
    path: str,
) -> WireDict:
    root = _require_dict(value, path=path)
    raw_order = root.get("instances", [])
    if not isinstance(raw_order, list):
        raise TypeError(f"{path}.instances 必须是列表")

    order: list[tuple[UUID, str, str]] = []
    seen: set[UUID] = set()
    raw_uid_keys: set[str] = set()
    for index, item_value in enumerate(raw_order):
        item_path = f"{path}.instances[{index}]"
        item = _require_dict(item_value, path=item_path)
        if set(item) != {"uid", "type"}:
            raise ValueError(f"{item_path} 必须且只能包含 uid 和 type")
        parsed_uid, canonical_uid = _parse_uid(
            item["uid"],
            path=f"{item_path}.uid",
        )
        if parsed_uid in seen:
            raise ValueError(f"{path}.instances 包含重复 uid")
        if item["type"] != expected_type:
            raise ValueError(f"{item_path}.type 仅允许 {expected_type}")
        seen.add(parsed_uid)
        raw_uid = str(item["uid"])
        raw_uid_keys.add(raw_uid)
        order.append((parsed_uid, canonical_uid, raw_uid))

    unknown = sorted(set(root) - {"instances"} - raw_uid_keys)
    if unknown:
        raise ValueError(
            f"{path} 包含孤儿或未知字段: " + ", ".join(unknown)
        )
    if any(raw_uid not in root for _, _, raw_uid in order):
        raise ValueError(f"{path}.instances 引用了缺失的数据项")

    data: dict[str, Any] = {}
    for _, canonical_uid, raw_uid in order:
        data[canonical_uid] = _legacy_user_to_wire(
            root[raw_uid],
            groups=groups,
            virtual_fields=virtual_fields,
            user_type=v2_type,
            path=f"{path}.{raw_uid}",
        )

    return {
        "order": [
            {"uid": canonical_uid, "type": v2_type}
            for _, canonical_uid, _ in order
        ],
        "data": data,
    }


def _legacy_webhooks_to_wire(value: object, *, path: str) -> WireDict:
    root = _require_dict(value, path=path)
    raw_order = root.get("instances", [])
    if not isinstance(raw_order, list):
        raise TypeError(f"{path}.instances 必须是列表")
    order: list[tuple[UUID, str, str]] = []
    seen: set[UUID] = set()
    raw_uid_keys: set[str] = set()
    for index, item_value in enumerate(raw_order):
        item_path = f"{path}.instances[{index}]"
        item = _require_dict(item_value, path=item_path)
        if set(item) != {"uid", "type"}:
            raise ValueError(f"{item_path} 必须且只能包含 uid 和 type")
        parsed_uid, canonical_uid = _parse_uid(
            item["uid"],
            path=f"{item_path}.uid",
        )
        if parsed_uid in seen:
            raise ValueError(f"{path}.instances 包含重复 uid")
        if item["type"] != "Webhook":
            raise ValueError(f"{item_path}.type 仅允许 Webhook")
        seen.add(parsed_uid)
        raw_uid = str(item["uid"])
        raw_uid_keys.add(raw_uid)
        order.append((parsed_uid, canonical_uid, raw_uid))
    unknown = sorted(set(root) - {"instances"} - raw_uid_keys)
    if unknown:
        raise ValueError(
            f"{path} 包含孤儿或未知字段: " + ", ".join(unknown)
        )
    if any(raw_uid not in root for _, _, raw_uid in order):
        raise ValueError(f"{path}.instances 引用了缺失的数据项")
    return {
        "order": [
            {"uid": canonical_uid, "type": "Webhook"}
            for _, canonical_uid, _ in order
        ],
        "data": {
            canonical_uid: _normalize_groups_only(
                root[raw_uid],
                groups=_WEBHOOK_GROUPS,
                path=f"{path}.{raw_uid}",
                rollback=False,
            )
            for _, canonical_uid, raw_uid in order
        },
    }


def _normalize_user_groups(
    value: object,
    *,
    groups: dict[str, dict[str, _FieldSpec]],
    virtual_fields: dict[str, set[str]],
    user_type: str,
    path: str,
    rollback: bool,
) -> WireDict:
    entry = _require_dict(value, path=path)
    raw_groups: dict[str, dict[str, Any]] = {}
    for group_name in groups:
        raw_groups[group_name] = dict(
            _require_dict(
                entry.get(group_name, {}),
                path=f"{path}.{group_name}",
            )
        )

    if user_type == "MaaUser":
        info = raw_groups["Info"]
        data = raw_groups["Data"]
        if not rollback and "InfrastIndex" not in data:
            legacy_index = info.get("InfrastIndex")
            if legacy_index is not None:
                data["InfrastIndex"] = legacy_index
    elif user_type == "MaaEndUser" and not rollback:
        info = raw_groups["Info"]
        if info.get("Mode") == "自定义":
            info["Mode"] = "详细"
            info["IfQuickConfig"] = False
        elif (
            info.get("Mode") in ("简洁", "详细")
            and "SanityMode" not in info
        ):
            info["Mode"] = "简洁"
            info.pop("IfQuickConfig", None)
        task = raw_groups["Task"]
        if task.get("SanityTaskType") == "ProtocolSpace":
            legacy_tab = task.pop("ProtocolSpaceTab", None)
            if legacy_tab not in MAAEND_SANITY_TASK_TYPES[:-1]:
                raise ValueError(
                    f"{path}.Task.ProtocolSpaceTab 不在允许选项中"
                )
            task["SanityTaskType"] = legacy_tab

    normalized: WireDict = {}
    for group_name, fields in groups.items():
        raw_group = raw_groups[group_name]
        virtual = virtual_fields.get(group_name, set())
        supplied_virtual = sorted(set(raw_group) & virtual)
        if rollback and supplied_virtual:
            raise ValueError(
                "Config v2 Wire 不得持久化虚拟字段: "
                + ", ".join(
                    f"{path}.{group_name}.{name}"
                    for name in supplied_virtual
                )
            )
        for name in supplied_virtual:
            raw_group.pop(name)
        unknown_fields = sorted(set(raw_group) - set(fields))
        if unknown_fields:
            raise ValueError(
                "未知 ScriptConfig 路径: "
                + ", ".join(
                    f"{path}.{group_name}.{name}"
                    for name in unknown_fields
                )
            )
        normalized[group_name] = {
            name: _validate_field(
                raw_group.get(name, spec.default),
                spec,
                path=f"{path}.{group_name}.{name}",
                rollback=rollback,
            )
            for name, spec in fields.items()
        }
    return normalized


def _legacy_user_to_wire(
    value: object,
    *,
    groups: dict[str, dict[str, _FieldSpec]],
    virtual_fields: dict[str, set[str]],
    user_type: str,
    path: str,
) -> WireDict:
    entry = _require_dict(value, path=path)
    supports_webhooks = user_type != "PluginUser"
    allowed = set(groups)
    if supports_webhooks:
        allowed |= {"SubConfigsInfo", "Notify_CustomWebhooks"}
    unknown = sorted(set(entry) - allowed)
    if unknown:
        raise ValueError(
            "未知 ScriptConfig 路径: "
            + ", ".join(f"{path}.{name}" for name in unknown)
        )
    if supports_webhooks and (
        "Notify_CustomWebhooks" in entry
        and "SubConfigsInfo" in entry
    ):
        raise ValueError(
            f"{path}.Notify_CustomWebhooks 与 "
            f"{path}.SubConfigsInfo.Notify_CustomWebhooks 别名冲突"
        )
    normalized = _normalize_user_groups(
        entry,
        groups=groups,
        virtual_fields=virtual_fields,
        user_type=user_type,
        path=path,
        rollback=False,
    )
    if not supports_webhooks:
        return normalized
    if "Notify_CustomWebhooks" in entry:
        raw_webhooks = entry["Notify_CustomWebhooks"]
    else:
        subconfigs = _require_dict(
            entry.get("SubConfigsInfo", {}),
            path=f"{path}.SubConfigsInfo",
        )
        unknown_subconfigs = sorted(
            set(subconfigs) - {"Notify_CustomWebhooks"}
        )
        if unknown_subconfigs:
            raise ValueError(
                "未知 ScriptConfig 路径: "
                + ", ".join(
                    f"{path}.SubConfigsInfo.{name}"
                    for name in unknown_subconfigs
                )
            )
        raw_webhooks = subconfigs.get("Notify_CustomWebhooks", {})
    normalized["Notify_CustomWebhooks"] = _legacy_webhooks_to_wire(
        raw_webhooks,
        path=f"{path}.SubConfigsInfo.Notify_CustomWebhooks",
    )
    return normalized


def _normalize_groups_only(
    value: object,
    *,
    groups: dict[str, dict[str, _FieldSpec]],
    path: str,
    rollback: bool,
) -> WireDict:
    entry = _require_dict(value, path=path)
    unknown_groups = sorted(set(entry) - set(groups))
    if unknown_groups:
        raise ValueError(
            "未知 ScriptConfig 路径: "
            + ", ".join(f"{path}.{name}" for name in unknown_groups)
        )
    normalized: WireDict = {}
    for group_name, fields in groups.items():
        raw_group = _require_dict(
            entry.get(group_name, {}),
            path=f"{path}.{group_name}",
        )
        unknown_fields = sorted(set(raw_group) - set(fields))
        if unknown_fields:
            raise ValueError(
                "未知 ScriptConfig 路径: "
                + ", ".join(
                    f"{path}.{group_name}.{name}"
                    for name in unknown_fields
                )
            )
        normalized[group_name] = {
            name: _validate_field(
                raw_group.get(name, spec.default),
                spec,
                path=f"{path}.{group_name}.{name}",
                rollback=rollback,
            )
            for name, spec in fields.items()
        }
    return normalized


def _legacy_user_data(
    entry: dict[str, Any],
    *,
    descriptor: _ScriptDescriptor,
    path: str,
) -> WireDict:
    if "UserData" in entry:
        return _parse_legacy_collection(
            entry["UserData"],
            expected_type=descriptor.user_legacy_type,
            v2_type=descriptor.user_v2_type,
            groups=descriptor.user_groups,
            virtual_fields=_USER_VIRTUAL_FIELDS[
                descriptor.user_v2_type
            ],
            path=f"{path}.UserData",
        )
    subconfigs = _require_dict(
        entry.get("SubConfigsInfo", {}),
        path=f"{path}.SubConfigsInfo",
    )
    unknown = sorted(set(subconfigs) - {"UserData"})
    if unknown:
        raise ValueError(
            "未知 ScriptConfig 路径: "
            + ", ".join(
                f"{path}.SubConfigsInfo.{name}" for name in unknown
            )
        )
    return _parse_legacy_collection(
        subconfigs.get("UserData", {}),
        expected_type=descriptor.user_legacy_type,
        v2_type=descriptor.user_v2_type,
        groups=descriptor.user_groups,
        virtual_fields=_USER_VIRTUAL_FIELDS[
            descriptor.user_v2_type
        ],
        path=f"{path}.SubConfigsInfo.UserData",
    )


def legacy_scripts_to_wire(legacy_data: object) -> WireDict:
    """将 r6 ``ScriptConfig.json`` 纯转换为 Config v2 Wire。"""

    root = _require_dict(legacy_data, path="$")
    raw_order = root.get("instances", [])
    if not isinstance(raw_order, list):
        raise TypeError("$.instances 必须是列表")

    order: list[tuple[UUID, str, str, _ScriptDescriptor]] = []
    seen: set[UUID] = set()
    raw_uid_keys: set[str] = set()
    for index, item_value in enumerate(raw_order):
        item_path = f"$.instances[{index}]"
        item = _require_dict(item_value, path=item_path)
        if set(item) != {"uid", "type"}:
            raise ValueError(f"{item_path} 必须且只能包含 uid 和 type")
        parsed_uid, canonical_uid = _parse_uid(
            item["uid"],
            path=f"{item_path}.uid",
        )
        if parsed_uid in seen:
            raise ValueError("$.instances 包含重复 uid")
        legacy_type = item["type"]
        if not isinstance(legacy_type, str):
            raise TypeError(f"{item_path}.type 必须是字符串")
        descriptor = _BY_LEGACY_TYPE.get(legacy_type)
        if descriptor is None:
            raise ValueError(
                f"{item_path}.type 尚无原生类型: "
                f"{legacy_type}"
            )
        seen.add(parsed_uid)
        raw_uid = str(item["uid"])
        raw_uid_keys.add(raw_uid)
        order.append((parsed_uid, canonical_uid, raw_uid, descriptor))

    unknown = sorted(set(root) - {"instances"} - raw_uid_keys)
    if unknown:
        raise ValueError("$ 包含孤儿或未知字段: " + ", ".join(unknown))
    if any(raw_uid not in root for _, _, raw_uid, _ in order):
        raise ValueError("$.instances 引用了缺失的数据项")

    data: dict[str, Any] = {}
    for _, canonical_uid, raw_uid, descriptor in order:
        entry_path = f"$.{raw_uid}"
        raw_entry = _require_dict(root[raw_uid], path=entry_path)
        normalized = _normalize_script_entry(
            raw_entry,
            descriptor=descriptor,
            path=entry_path,
            rollback=False,
        )
        normalized["UserData"] = _legacy_user_data(
            raw_entry,
            descriptor=descriptor,
            path=entry_path,
        )
        data[canonical_uid] = normalized

    return {
        "order": [
            {"uid": canonical_uid, "type": descriptor.v2_type}
            for _, canonical_uid, _, descriptor in order
        ],
        "data": data,
    }


def _wire_webhooks_to_legacy(value: object, *, path: str) -> dict[str, Any]:
    root = _require_dict(value, path=path)
    unknown_root = sorted(set(root) - {"order", "data"})
    if unknown_root:
        raise ValueError(
            "未知 ScriptConfig 路径: "
            + ", ".join(f"{path}.{name}" for name in unknown_root)
        )
    raw_order = root.get("order", [])
    raw_data = _require_dict(root.get("data", {}), path=f"{path}.data")
    if not isinstance(raw_order, list):
        raise TypeError(f"{path}.order 必须是列表")
    order: list[tuple[UUID, str]] = []
    seen: set[UUID] = set()
    for index, item_value in enumerate(raw_order):
        item_path = f"{path}.order[{index}]"
        item = _require_dict(item_value, path=item_path)
        if set(item) != {"uid", "type"}:
            raise ValueError(f"{item_path} 必须且只能包含 uid 和 type")
        parsed_uid, canonical_uid = _parse_uid(
            item["uid"],
            path=f"{item_path}.uid",
        )
        if parsed_uid in seen:
            raise ValueError(f"{path}.order 包含重复 uid")
        if item["type"] != "Webhook":
            raise ValueError(f"{item_path}.type 仅允许 Webhook")
        seen.add(parsed_uid)
        order.append((parsed_uid, canonical_uid))
    data_by_uid: dict[UUID, tuple[str, object]] = {}
    for raw_uid, payload in raw_data.items():
        parsed_uid, canonical_uid = _parse_uid(
            raw_uid,
            path=f"{path}.data key",
        )
        if parsed_uid in data_by_uid:
            raise ValueError(f"{path}.data 包含重复 uid")
        data_by_uid[parsed_uid] = (canonical_uid, payload)
    if seen != set(data_by_uid):
        raise ValueError(f"{path}.order 与 data 包含缺失或孤儿 uid")
    legacy: dict[str, Any] = {"instances": []}
    for parsed_uid, canonical_uid in order:
        _, payload = data_by_uid[parsed_uid]
        legacy["instances"].append(
            {"uid": canonical_uid, "type": "Webhook"}
        )
        legacy[canonical_uid] = _normalize_groups_only(
            payload,
            groups=_WEBHOOK_GROUPS,
            path=f"{path}.data.{canonical_uid}",
            rollback=True,
        )
    return legacy


def _wire_user_to_legacy(
    value: object,
    *,
    groups: dict[str, dict[str, _FieldSpec]],
    virtual_fields: dict[str, set[str]],
    user_type: str,
    path: str,
) -> WireDict:
    entry = _require_dict(value, path=path)
    supports_webhooks = user_type != "PluginUser"
    allowed = set(groups)
    if supports_webhooks:
        allowed.add("Notify_CustomWebhooks")
    unknown = sorted(set(entry) - allowed)
    if unknown:
        raise ValueError(
            "未知 ScriptConfig 路径: "
            + ", ".join(f"{path}.{name}" for name in unknown)
        )
    normalized = _normalize_user_groups(
        entry,
        groups=groups,
        virtual_fields=virtual_fields,
        user_type=user_type,
        path=path,
        rollback=True,
    )
    if not supports_webhooks:
        return normalized
    normalized["SubConfigsInfo"] = {
        "Notify_CustomWebhooks": _wire_webhooks_to_legacy(
            entry.get("Notify_CustomWebhooks", {}),
            path=f"{path}.Notify_CustomWebhooks",
        )
    }
    return normalized


def _parse_v2_collection(
    value: object,
    *,
    expected_type: str,
    legacy_type: str,
    groups: dict[str, dict[str, _FieldSpec]],
    virtual_fields: dict[str, set[str]],
    path: str,
) -> dict[str, Any]:
    root = _require_dict(value, path=path)
    unknown_root = sorted(set(root) - {"order", "data"})
    if unknown_root:
        raise ValueError(
            "未知 ScriptConfig 路径: "
            + ", ".join(f"{path}.{name}" for name in unknown_root)
        )
    raw_order = root.get("order", [])
    raw_data = _require_dict(root.get("data", {}), path=f"{path}.data")
    if not isinstance(raw_order, list):
        raise TypeError(f"{path}.order 必须是列表")

    order: list[tuple[UUID, str]] = []
    seen: set[UUID] = set()
    for index, item_value in enumerate(raw_order):
        item_path = f"{path}.order[{index}]"
        item = _require_dict(item_value, path=item_path)
        if set(item) != {"uid", "type"}:
            raise ValueError(f"{item_path} 必须且只能包含 uid 和 type")
        parsed_uid, canonical_uid = _parse_uid(
            item["uid"],
            path=f"{item_path}.uid",
        )
        if parsed_uid in seen:
            raise ValueError(f"{path}.order 包含重复 uid")
        if item["type"] != expected_type:
            raise ValueError(f"{item_path}.type 仅允许 {expected_type}")
        seen.add(parsed_uid)
        order.append((parsed_uid, canonical_uid))

    data_by_uid: dict[UUID, tuple[str, object]] = {}
    for raw_uid, payload in raw_data.items():
        parsed_uid, canonical_uid = _parse_uid(
            raw_uid,
            path=f"{path}.data key",
        )
        if parsed_uid in data_by_uid:
            raise ValueError(f"{path}.data 包含重复 uid")
        data_by_uid[parsed_uid] = (canonical_uid, payload)
    if seen != set(data_by_uid):
        raise ValueError(f"{path}.order 与 data 包含缺失或孤儿 uid")

    legacy: dict[str, Any] = {"instances": []}
    for parsed_uid, canonical_uid in order:
        _, payload_value = data_by_uid[parsed_uid]
        legacy_payload = _wire_user_to_legacy(
            payload_value,
            groups=groups,
            virtual_fields=virtual_fields,
            user_type=expected_type,
            path=f"{path}.data.{canonical_uid}",
        )

        legacy["instances"].append(
            {"uid": canonical_uid, "type": legacy_type}
        )
        legacy[canonical_uid] = legacy_payload
    return legacy


def scripts_wire_to_legacy(wire_data: object) -> dict[str, Any]:
    """将 Config v2 Wire 纯转换为可回滚的 r6 JSON 形状。"""

    root = _require_dict(wire_data, path="$")
    unknown_root = sorted(set(root) - {"order", "data"})
    if unknown_root:
        raise ValueError(
            "未知 ScriptConfig 路径: "
            + ", ".join(f"$.{name}" for name in unknown_root)
        )
    raw_order = root.get("order", [])
    raw_data = _require_dict(root.get("data", {}), path="$.data")
    if not isinstance(raw_order, list):
        raise TypeError("$.order 必须是列表")

    order: list[tuple[UUID, str, _ScriptDescriptor]] = []
    seen: set[UUID] = set()
    for index, item_value in enumerate(raw_order):
        item_path = f"$.order[{index}]"
        item = _require_dict(item_value, path=item_path)
        if set(item) != {"uid", "type"}:
            raise ValueError(f"{item_path} 必须且只能包含 uid 和 type")
        parsed_uid, canonical_uid = _parse_uid(
            item["uid"],
            path=f"{item_path}.uid",
        )
        if parsed_uid in seen:
            raise ValueError("$.order 包含重复 uid")
        v2_type = item["type"]
        if not isinstance(v2_type, str):
            raise TypeError(f"{item_path}.type 必须是字符串")
        descriptor = _BY_V2_TYPE.get(v2_type)
        if descriptor is None:
            raise ValueError(f"{item_path}.type 不是受支持的原生类型")
        seen.add(parsed_uid)
        order.append((parsed_uid, canonical_uid, descriptor))

    data_by_uid: dict[UUID, tuple[str, object]] = {}
    for raw_uid, payload in raw_data.items():
        parsed_uid, canonical_uid = _parse_uid(
            raw_uid,
            path="$.data key",
        )
        if parsed_uid in data_by_uid:
            raise ValueError("$.data 包含重复 uid")
        data_by_uid[parsed_uid] = (canonical_uid, payload)
    if seen != set(data_by_uid):
        raise ValueError("$.order 与 data 包含缺失或孤儿 uid")

    legacy: dict[str, Any] = {"instances": []}
    for parsed_uid, canonical_uid, descriptor in order:
        _, payload_value = data_by_uid[parsed_uid]
        entry_path = f"$.data.{canonical_uid}"
        payload = _require_dict(payload_value, path=entry_path)
        normalized = _normalize_script_entry(
            payload,
            descriptor=descriptor,
            path=entry_path,
            rollback=True,
        )
        user_data = _parse_v2_collection(
            payload.get("UserData", {}),
            expected_type=descriptor.user_v2_type,
            legacy_type=descriptor.user_legacy_type,
            groups=descriptor.user_groups,
            virtual_fields=_USER_VIRTUAL_FIELDS[
                descriptor.user_v2_type
            ],
            path=f"{entry_path}.UserData",
        )

        legacy["instances"].append(
            {"uid": canonical_uid, "type": descriptor.legacy_type}
        )
        normalized["SubConfigsInfo"] = {"UserData": user_data}
        legacy[canonical_uid] = normalized
    return legacy


__all__ = [
    "EMULATOR_COLLECTION_NAME",
    "GeneralUser",
    "GeneralScript",
    "M9AUser",
    "M9AScript",
    "MaaEndUser",
    "MaaEndScript",
    "MaaFWUser",
    "MaaFWScript",
    "MaaUser",
    "MaaScript",
    "NATIVE_SCRIPT_TYPES",
    "NATIVE_USER_TYPES",
    "OkwwUser",
    "OkwwScript",
    "PLAN_COLLECTION_NAME",
    "PluginScript",
    "PluginUser",
    "SCRIPT_COLLECTION_NAME",
    "Scripts",
    "SrcUser",
    "SrcScript",
    "legacy_scripts_to_wire",
    "scripts_wire_to_legacy",
]
