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
import re
from _strptime import TimeRE
from copy import deepcopy
from datetime import datetime
from pathlib import Path as NativePath
from typing import Annotated, Any, ClassVar, Literal
from uuid import UUID

from pydantic import Field, PrivateAttr

from app.config import (
    ConfigCollection,
    ConfigGroup,
    UiVisibility,
    collection,
    encrypted,
    legacy,
    ref,
    tz,
    ui,
    virtual_field,
)
from app.config.fields.hints import migrate_legacy_fields
from app.config.types import (
    STANDARD_BLOCKED_DIRS,
    CliArgumentListString,
    CliArgumentString,
    FilePath,
    FolderPath,
    JsonDictString,
    JsonListString,
    path_policy,
)
from app.utils import constants as _utils_constants

from .base import DomainEntry as _DomainEntry
from .game_binding import GameBindingOwner
from .plan import (
    BAAHPlanConfig,
    MaaEndPlanConfig,
    OkNtePlanConfig,
    OkwwPlanConfig,
    UniversalPlanConfig,
)
from .plugin_script import ScriptEntry, UserEntry
from .queue import Webhook
from .shared import (
    AccountCredentialFields,
    AccountNameFields,
    AccountRunFields,
    AccountRunStatusFields,
    AccountScriptHookFields,
    OkwwTaskFields,
    SRAProfileName,
    _migrate_baah_event_first,
    _migrate_oknte_launch_mode_default,
    _normalize_maaend_sanity_task_type,
    _tag_last_status,
    _tag_notes,
    _tag_proxy,
    _tag_remained_days,
    migrate_maaend_sanity_tasks,
    none_as,
    normalize_maaend_plan_key,
)


class DomainEntry(_DomainEntry, GameBindingOwner):
    """旧专项配置复用新游戏绑定，保留原有配置输入转换。"""


MaaEndInstallPath = Annotated[
    NativePath | None, path_policy(kind="folder", blocked_dirs=STANDARD_BLOCKED_DIRS)
]
"""保留更新中断时暂缺的安装路径，供恢复入口定位相邻的原安装备份。"""


BAAHInstallPath = Annotated[
    NativePath | None,
    path_policy(kind="file", extensions=(".exe",), blocked_dirs=STANDARD_BLOCKED_DIRS),
]
"""保留目录切换中断时暂缺的主程序路径，供安装恢复定位原目录。"""


class MaaEndUserConfig(DomainEntry):
    "MaaEnd账号配置"

    related_config: ClassVar = {}

    class DataFields(AccountRunFields, AccountRunStatusFields):
        PeriodTaskRecords: JsonDictString = Field(
            default_factory=lambda: "{ }",
            description="MaaEnd 每日任务完成记录，结构为 daily -> task name -> 日期",
        )

    Data: DataFields = Field(default_factory=DataFields)

    class InfoFields(
        AccountNameFields, AccountCredentialFields, AccountScriptHookFields
    ):
        Base: Annotated[
            Literal["shared", "independent", "native"],
            legacy(
                group="Info",
                name="Mode",
                convert=_utils_constants.normalize_base_source,
            ),
        ] = Field(
            default_factory=lambda: "shared",
            description="base 来源（shared=共享/independent=独立/native=原生）",
        )

        Id: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "", description="账号ID"
        )

        IfQuickConfig: bool = Field(
            default_factory=lambda: True, description="是否启用覆写常规配置"
        )

        Password: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "", description="密码"
        )

        Resource: str = Field(
            default_factory=lambda: "官服",
            description="MaaEnd 启动服务器选项原值，官服为旧配置兼容值",
        )

        SanityStrategy: Literal["MAS", "Native", "Inventory"] = Field(
            default="Inventory",
            description="协议空间策略：库存保持、指定任务或原生配置",
        )

        SanityMode: Annotated[
            UUID | str,
            ref(
                "PlanConfig",
                default="Fixed",
                allow_values=("Fixed",),
                entry_types=(MaaEndPlanConfig,),
                display_field="Info.Name",
            ),
        ] = Field(default_factory=lambda: "Fixed", description="理智任务配置模式")

        AutoEssenceMode: Annotated[
            UUID | str,
            ref(
                "PlanConfig",
                default="Fixed",
                allow_values=("Fixed", "Native"),
                entry_types=(MaaEndPlanConfig,),
                display_field="Info.Name",
            ),
        ] = Field(default_factory=lambda: "Fixed", description="基质刷取配置模式")

    Info: InfoFields = Field(default_factory=InfoFields)

    class NotifyFields(ConfigGroup):
        Enabled: bool = Field(default_factory=lambda: False, description="是否启用通知")

        IfSendMail: bool = Field(
            default_factory=lambda: False, description="是否发送邮件"
        )

        IfSendInventory: bool = Field(
            default=False, description="是否推送本轮养成材料状态"
        )

        IfSendStatistic: bool = Field(
            default_factory=lambda: False, description="是否发送统计信息"
        )

        IfServerChan: bool = Field(
            default_factory=lambda: False, description="是否启用 Server 酱"
        )

        PushLogMode: Literal["关闭", "逐条", "汇总"] = Field(
            default_factory=lambda: "汇总",
            description="任务报告节点详情的推送模式（log_box 采集的关键节点）： 关闭 = 不采集；逐条 = 采集并逐条带回时间戳；汇总 = 采集并按状态聚合",
        )

        ServerChanKey: str = Field(
            default_factory=lambda: "", description="Server 酱密钥"
        )

        ToAddress: str = Field(default_factory=lambda: "", description="收件地址")

    Notify: NotifyFields = Field(default_factory=NotifyFields)

    class TaskFields(ConfigGroup):
        SupplyPlanLimits: JsonDictString = Field(
            default_factory=lambda: json.dumps(
                _utils_constants.MAAEND_INVENTORY_TARGET_DEFAULTS
            ),
            description="上游库存目标输入值，原字段名与字符串值透传",
        )
        ProtocolSpaceObtainModeClaim: str = Field(
            default="ObtainScaling2", description="库存任务领取方式，由 MaaEnd 声明"
        )

        AutoCollectCommonRoutes: Any = Field(
            description="自动采集通用资源路线", default_factory=lambda: None
        )

        AutoCollectMode: Literal["Distributed", "Concentrated"] = Field(
            description="自动采集路线安排：分散或集中",
            default_factory=lambda: "Distributed",
        )

        AutoCollectRoutes: Any = Field(
            description="自动采集区域资源路线", default_factory=lambda: None
        )

        AutoEssenceMenu: Literal["Random", "Location", "Target"] = Field(
            description="基质刷取模式", default_factory=lambda: "Location"
        )

        AutoEssenceSpecifiedLocation: str = Field(
            description="基质刷取指定地点", default_factory=lambda: ""
        )

        AutoEssenceTargetWeapons: list[str] = Field(
            description="基质目标武器 ID 列表", default_factory=lambda: []
        )

        CrisisDrills: str = Field(
            description="危境预演任务，由 MaaEnd 声明",
            default="AdvancedProgression1",
            min_length=1,
        )

        DailyOnceTasks: JsonListString = Field(
            description="每日正常完成一次后当天跳过的 MaaEnd 任务名列表（JSON 字符串）",
            default_factory=lambda: "[ ]",
        )

        IfAutoCollect: bool = Field(
            description="自动采集", default_factory=lambda: True
        )

        IfAutoEcoFarm: bool = Field(
            description="生态农场", default_factory=lambda: True
        )

        IfAutoSell: bool = Field(
            description="售卖弹性物资", default_factory=lambda: True
        )

        IfAutoStockStaple: bool = Field(
            description="购买稳定物资", default_factory=lambda: True
        )

        IfAutoStockpile: bool = Field(
            description="自动囤货", default_factory=lambda: True
        )

        IfAutoUseSpMedication: bool = Field(
            description="应急理智加强剂", default_factory=lambda: True
        )

        IfCreditShoppingN2: bool = Field(
            description="信用点购物", default_factory=lambda: True
        )

        IfDailyRewards: bool = Field(
            description="日常奖励领取", default_factory=lambda: True
        )

        IfDeliveryJobs: bool = Field(
            description="转交委托", default_factory=lambda: True
        )

        IfDijiangRewards: bool = Field(
            description="基建任务", default_factory=lambda: True
        )

        IfEnvironmentMonitoring: bool = Field(
            description="环境监测", default_factory=lambda: True
        )

        IfPullCountCalculator: bool = Field(
            description="抽数计算", default_factory=lambda: False
        )

        IfResourceRecycleStation: bool = Field(
            description="资源回收站", default_factory=lambda: True
        )

        IfProtocolSpace: Annotated[bool, legacy(group="Task", name="IfSanity")] = Field(
            default=True, description="协议空间（库存保持）"
        )

        IfAutoEssence: bool = Field(default=False, description="基质刷取")

        IfSeizeDeliveryJobs: bool = Field(
            description="抢委托送货", default_factory=lambda: True
        )

        IfSellProduct: bool = Field(
            description="售卖产品", default_factory=lambda: True
        )

        IfTrialOfSwordmancy: bool = Field(
            description="选剑演武", default_factory=lambda: True
        )

        IfVisitFriends: bool = Field(
            description="拜访好友", default_factory=lambda: True
        )

        OperatorProgression: Literal[
            "OperatorEXP", "Promotions", "T-Creds", "SkillUp"
        ] = Field(description="干员养成任务", default_factory=lambda: "OperatorEXP")

        RewardsSetOption: Literal["RewardsSetA", "RewardsSetB"] = Field(
            description="奖励组选项", default_factory=lambda: "RewardsSetA"
        )

        SanityTaskType: Literal[
            "OperatorProgression", "WeaponProgression", "CrisisDrills", "Essence"
        ] = Field(
            description="理智任务类型", default_factory=lambda: "OperatorProgression"
        )

        SeizeDeliveryJobsCommissionSource: Literal[
            "Unlimited", "WulingCity", "TestArea"
        ] = Field(
            description="抢委托送货委托接收点", default_factory=lambda: "Unlimited"
        )

        SeizeDeliveryJobsReward: Annotated[float, Field(ge=0, le=9999)] = Field(
            description="抢委托送货最低接取价格（万）",
            default_factory=lambda: 15.9,
        )

        WeaponProgression: Literal["WeaponEXP", "WeaponTune"] = Field(
            description="武器养成任务", default_factory=lambda: "WeaponEXP"
        )

    Task: TaskFields = Field(default_factory=TaskFields)
    Notify_CustomWebhooks: ConfigCollection[Webhook] = collection(Webhook)
    _maaend_essence_location_labels: dict = PrivateAttr(default_factory=dict)
    _maaend_crisis_drills_labels: dict[str, str] = PrivateAttr(default_factory=dict)

    def cache_maaend_resource(self, resource: dict[str, Any]) -> None:
        """缓存 MaaEnd 动态资源的展示文本。"""
        self._maaend_essence_location_labels = {
            str(item["value"]): str(item["label"])
            for item in resource.get("essenceLocations", [])
            if isinstance(item, dict) and item.get("value") is not None
        }
        self._maaend_crisis_drills_labels = {
            str(item["value"]): str(item["label"])
            for item in resource.get("crisisDrills", [])
        }

    def _get_maaend_location_label(self, value: str) -> str:
        if not value:
            return ""
        return self._maaend_essence_location_labels.get(value, value)

    def get_effective_sanity_task_key(self) -> tuple[dict[str, Any], str]:
        """获取当前生效的完整 MaaEnd key。"""
        mode = self.Info.SanityMode
        if mode == "Fixed":
            return (
                normalize_maaend_plan_key(
                    {
                        field: getattr(self.Task, field)
                        for field in _utils_constants.MAAEND_SANITY_TASK_FIELDS
                    }
                ),
                "Fixed",
            )
        try:
            plan = self.related_config["PlanConfig"][mode]
        except (KeyError, ValueError) as e:
            raise ValueError("引用的理智任务计划表不存在") from e
        return (plan.get_current_key(), str(mode))

    def get_effective_essence_task_key(self) -> dict[str, Any] | None:
        """读取独立基质配置，计划表当天为协议空间时不执行基质。"""
        mode = self.Info.AutoEssenceMode
        if mode == "Native":
            return None
        if mode == "Fixed":
            return normalize_maaend_plan_key(
                {
                    "SanityTaskType": "Essence",
                    "AutoEssenceMenu": self.Task.AutoEssenceMenu,
                    "AutoEssenceSpecifiedLocation": self.Task.AutoEssenceSpecifiedLocation,
                    "AutoEssenceTargetWeapons": self.Task.AutoEssenceTargetWeapons,
                }
            )
        try:
            plan = self.related_config["PlanConfig"][mode]
        except (KeyError, ValueError) as error:
            raise ValueError("引用的基质刷取计划表不存在") from error
        key = plan.get_current_key()
        return key if key["SanityTaskType"] == "Essence" else None

    def getTags(self) -> str:
        """生成账号标签列表，返回JSON字符串格式的TagItem列表"""
        tags = []
        tags.append(
            {
                "text": f"上次：{_tag_last_status(self.Data.LastProxyStatus)}",
                "color": "red" if self.Data.LastProxyStatus == "失败" else "green",
            }
        )
        tags.append(_tag_proxy(self))
        tags.append(_tag_remained_days(self))
        if not self.Info.IfQuickConfig:
            tags.append(_tag_notes(self))
            return json.dumps(tags, ensure_ascii=False)

        if self.Task.IfProtocolSpace and self.Info.SanityStrategy in (
            "Native",
            "Inventory",
        ):
            label = (
                "库存目标"
                if self.Info.SanityStrategy == "Inventory"
                else "MaaEnd 原生策略"
            )
            tags.append({"text": f"协议空间：{label}", "color": "blue"})
        elif self.Task.IfProtocolSpace:
            task_key, _ = self.get_effective_sanity_task_key()
            sanity_task_type = task_key["SanityTaskType"]
            if sanity_task_type != "Essence":
                tags.append(
                    {
                        "text": f"协议空间：{_utils_constants.MAAEND_SANITY_TASK_LABELS[sanity_task_type]}",
                        "color": "blue",
                    }
                )
                detail_key = task_key[sanity_task_type]
                detail_label = self._maaend_crisis_drills_labels.get(
                    detail_key,
                    _utils_constants.MAAEND_SANITY_TASK_DETAIL_LABELS.get(
                        detail_key, detail_key
                    ),
                )
                tags.append({"text": f"详细任务：{detail_label}", "color": "blue"})
                if detail_key in _utils_constants.MAAEND_STAGE_WITH_AB:
                    label = (
                        "奖励组 A"
                        if task_key["RewardsSetOption"] == "RewardsSetA"
                        else "奖励组 B"
                    )
                    tags.append({"text": f"奖励组：{label}", "color": "blue"})
        if self.Task.IfAutoEssence:
            tags.append({"text": "基质刷取", "color": "blue"})
        tags.append(_tag_notes(self))
        return json.dumps(tags, ensure_ascii=False)

    @classmethod
    def normalize_payload(cls, data):
        data = migrate_maaend_sanity_tasks(deepcopy(data))
        info_data = data.get("Info")
        if isinstance(info_data, dict):
            legacy_base = str(info_data.get("Mode") or "")
            # 旧 Mode 同时决定来源和覆写常规配置开关；已给出的新来源始终优先。
            if "Base" not in info_data and legacy_base == "自定义":
                info_data["Base"] = "independent"
                info_data["IfQuickConfig"] = False
            elif (
                "Base" not in info_data
                and legacy_base in ("简洁", "详细")
                and "SanityMode" not in info_data
            ):
                info_data["Base"] = "shared"
                info_data.pop("IfQuickConfig", None)
        task_data = data.get("Task")
        if isinstance(task_data, dict):
            _normalize_maaend_sanity_task_type(task_data)
        return data

    @virtual_field("Info.Tag")
    def compute_Info_Tag(self):
        try:
            return self.getTags()
        except Exception as exc:
            return str(exc)


class DesktopSessionRunFields(ConfigGroup):
    """支持桌面分身的托管运行设置。"""

    ExecutionSession: Literal["main", "desktop"] = Field(
        default="main", description="单独启动托管时使用的 Windows 会话"
    )


class MaaEndConfig(DomainEntry):
    "MaaEnd配置"

    related_config: ClassVar = {}

    class GameFields(ConfigGroup):
        LaunchMode: Literal["Client", "Launcher", "MAS", "MaaEnd"] = Field(
            default="Launcher", description="游戏启动方式，Client 为历史迁移值"
        )

        Arguments: CliArgumentString = Field(
            default_factory=lambda: "", description="终末地游戏启动参数"
        )

        CloseOnFinish: bool = Field(
            default_factory=lambda: True, description="结束后是否关闭游戏"
        )

        ControllerType: str = Field(
            default_factory=lambda: "", description="控制器类型"
        )

        IfAutoUpdate: bool = Field(
            default_factory=lambda: False,
            description="是否在任务启动前检查并自动更新终末地 PC 客户端",
        )

        LauncherPath: FilePath = Field(
            default_factory=lambda: None,
            description="鹰角官方启动器路径（Launcher.exe 或 Games.exe）",
        )

        Path: FilePath = Field(
            default_factory=lambda: None, description="终末地游戏路径"
        )

        RestoreDisplayType: Literal["Window", "Fullscreen"] = Field(
            default_factory=lambda: "Window",
            description="关闭游戏时恢复的显示模式，与具体分辨率独立配置",
        )

        RestoreResolution: Literal[
            "Off", "Original", "1920x1080", "2560x1440", "3840x2160", "Custom"
        ] = Field(
            default_factory=lambda: "Off",
            description="关闭游戏时恢复分辨率；Original 复用启动前读取的注册表值",
        )

        RestoreResolutionHeight: Annotated[int, Field(ge=1, le=16384)] = Field(
            default_factory=lambda: 1080,
            description="自定义恢复分辨率高度",
        )

        RestoreResolutionWidth: Annotated[int, Field(ge=1, le=16384)] = Field(
            default_factory=lambda: 1920,
            description="自定义恢复分辨率宽度",
        )

        RestoreAutoHDR: Literal["Unchanged", "Disable", "Enable"] = Field(
            default_factory=lambda: "Unchanged",
            description="关闭游戏时的自动 HDR 设置",
        )

        AutoHDR: Literal["Unchanged", "Disable", "Enable"] = Field(
            default_factory=lambda: "Unchanged",
            description="MaaEnd 启动时的自动 HDR 设置",
        )

        SetResolution: bool = Field(
            default_factory=lambda: False,
            description="是否在启动游戏时执行 MaaEnd 分辨率设置预任务",
        )

        UpdateTimeLimit: Annotated[int, Field(ge=1, le=9999)] = Field(
            default_factory=lambda: 240,
            description="游戏客户端更新时长限制（分钟）",
        )

        WaitTime: Annotated[int, Field(ge=60, le=9999), none_as(60)] = Field(
            default_factory=lambda: 60, description="等待时间（秒）"
        )

    Game: GameFields = Field(default_factory=GameFields)

    class InfoFields(ConfigGroup):
        Name: str = Field(
            default_factory=lambda: "新 MaaEnd 托管", description="MaaEnd 托管名称"
        )

        # 目录切换中断时路径可能暂时不存在，必须保留以便运行前恢复原安装。
        Path: MaaEndInstallPath = Field(
            default_factory=lambda: None, description="MaaEnd 路径"
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class RunFields(DesktopSessionRunFields):
        AccountSwitchMethod: Literal["MAS", "MAAEND"] = Field(
            default_factory=lambda: "MAAEND",
            description="账号切换方式（默认使用 MAAEND，MAS 为兼容入口）",
        )

        HardTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 120,
            description="单账号运行总时限（分钟），包含等待和全部重试",
        )

        IfSaveLogBundle: bool = Field(
            default_factory=lambda: False,
            description="任务失败时是否按 MaaEnd 的导出规则打包运行日志",
        )

        LogBundlePath: FolderPath = Field(
            default_factory=lambda: None,
            description="任务失败时保存日志包的目录，留空使用 MAS 目录下的 debug/maaend",
        )

        ProxyTimesLimit: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            default_factory=lambda: 0, description="每日代理次数限制"
        )

        RunTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 10, description="运行超时阈值"
        )

        RunTimesLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 3, description="运行次数限制"
        )

        TaskTransitionMethod: Literal["NoAction", "ExitGame"] = Field(
            default_factory=lambda: "NoAction", description="任务切换方式"
        )

    Run: RunFields = Field(default_factory=RunFields)
    UserData: ConfigCollection[MaaEndUserConfig] = collection(MaaEndUserConfig)

    class UpdateFields(ConfigGroup):
        TakeoverEnabled: bool = Field(
            default_factory=lambda: False,
            description="运行前由 MAS 下载、校验并安装 MaaEnd 官方完整包；不暂停 MXU 自身的更新检查",
        )
        PackageMode: Literal["full", "incremental"] = Field(
            default="full",
            description="全量或优先增量；增量有风险，无可信缓存、匹配增量包或校验失败时回退全量",
        )
        Channel: Literal["stable", "beta"] = Field(
            default_factory=lambda: "stable", description="MaaEnd 更新通道"
        )
        MirrorChyanCDK: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="MaaEnd Mirror 酱 CDK，留空使用全局 CDK，无 CDK 使用 GitHub",
        )

    Update: UpdateFields = Field(default_factory=UpdateFields)

    @classmethod
    def normalize_payload(cls, data):
        data = deepcopy(data)
        data = deepcopy(data)
        game_data = data.get("Game") if isinstance(data, dict) else None
        migrated = (
            isinstance(game_data, dict)
            and game_data.get("RestoreResolution") == "Fullscreen"
        )
        if migrated and isinstance(game_data, dict):
            game_data["RestoreDisplayType"] = "Fullscreen"
            game_data["RestoreResolution"] = "1920x1080"
        return data


class HSRUserConfig(DomainEntry):
    "HSR账号配置"

    related_config: ClassVar = {}

    class ControlFields(ConfigGroup):
        M7A: bool = Field(
            description="原生来源时是否运行三月七", default_factory=lambda: False
        )

        SRA: bool = Field(
            default_factory=lambda: False,
            description="原生来源（native）时运行哪几个引擎；都没勾时回落到已配置路径的引擎",
        )

    Control: ControlFields = Field(default_factory=ControlFields)

    class DataFields(AccountRunFields, AccountRunStatusFields):
        EchoOfWarCompletedThisWeek: bool = Field(
            default_factory=lambda: False, description="本周是否已完成历战余响"
        )

        EchoOfWarLastCompletionDate: Annotated[
            datetime, tz(_utils_constants.UTC4), ui(format="date")
        ] = Field(
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=_utils_constants.UTC4),
            description="历战余响最近一次完成日期",
        )

        EchoOfWarLastResetWeek: str = Field(
            default_factory=lambda: "2000-W01",
            description='历战余响上次重置 ISO 周（形如 "2025-W23"）',
        )

        M7ARedeemCodeFingerprint: str = Field(
            description="M7A 兑换码指纹", default_factory=lambda: ""
        )

        SRARedeemCodeFingerprint: str = Field(
            default_factory=lambda: "",
            description="兑换码状态指纹（仅状态信息，不保存兑换码明文）",
        )

        WeeklyCompletedThisWeek: bool = Field(
            default_factory=lambda: False,
            description="本周是否已完成周常（仅依据 Data 字段判断）",
        )

        WeeklyLastCompletionDate: Annotated[
            datetime, tz(_utils_constants.UTC4), ui(format="date")
        ] = Field(
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=_utils_constants.UTC4),
            description="周常（差分宇宙/货币战争）最近一次完成日期",
        )

        WeeklyLastResetWeek: str = Field(
            default_factory=lambda: "2000-W01",
            description='周常上次重置 ISO 周（形如 "2025-W23"）',
        )

    Data: DataFields = Field(default_factory=DataFields)

    class InfoFields(
        AccountNameFields, AccountCredentialFields, AccountScriptHookFields
    ):
        Base: Annotated[
            Literal["shared", "independent", "native"],
            legacy(
                group="Info",
                name="Mode",
                convert=_utils_constants.normalize_base_source,
            ),
        ] = Field(
            default_factory=lambda: "shared",
            description="base 来源（shared/independent/native）：shared = 共用托管级计划； independent = 本账号自己的计划；native = 原样运行 SRA / 三月七 当前的原生配置",
        )

        Id: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "", description="账号"
        )

        IfQuickConfig: bool = Field(
            default_factory=lambda: True,
            description="兼容字段；HSR 运行不消费此开关，不提供覆写常规配置",
        )

        Password: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "", description="密码"
        )

        Resource: Annotated[
            Literal["CN-Official"], legacy(group="Info", name="Server")
        ] = Field(default_factory=lambda: "CN-Official", description="游戏服务器")

    Info: InfoFields = Field(default_factory=InfoFields)

    class ManagedFields(ConfigGroup):
        Options: JsonDictString = Field(
            description="托管任务选项 JSON", default_factory=lambda: "{ }"
        )

        TaskMapping: JsonDictString = Field(
            description="托管任务映射 JSON", default_factory=lambda: "{ }"
        )

    Managed: ManagedFields = Field(default_factory=ManagedFields)

    class NotifyFields(ConfigGroup):
        Enabled: bool = Field(default_factory=lambda: False, description="是否启用通知")

        IfSendMail: bool = Field(
            default_factory=lambda: False, description="是否发送邮件"
        )

        IfSendStatistic: bool = Field(
            default_factory=lambda: False, description="是否发送统计信息"
        )

        IfServerChan: bool = Field(
            default_factory=lambda: False, description="是否启用 Server 酱"
        )

        ServerChanKey: str = Field(
            default_factory=lambda: "", description="Server 酱密钥"
        )

        ToAddress: str = Field(default_factory=lambda: "", description="收件地址")

    Notify: NotifyFields = Field(default_factory=NotifyFields)

    class StageFields(ConfigGroup):
        Channel: Literal["CalyxGolden", "CalyxCrimson", "Relic", "Ornament"] = Field(
            description="体力关卡通道", default_factory=lambda: "CalyxGolden"
        )

        ScriptEchoOfWar: JsonDictString = Field(
            description="历战余响脚本原生字段 JSON", default_factory=lambda: "{ }"
        )

        ScriptStage: JsonDictString = Field(
            description="主刷关卡脚本原生字段 JSON", default_factory=lambda: "{ }"
        )

    Stage: StageFields = Field(default_factory=StageFields)

    class TaskOptFields(ConfigGroup):
        EchoOfWarWeekday: Literal[
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ] = Field(
            description="历战余响开始刷的星期（周一 ~ 周日）",
            default_factory=lambda: "Monday",
        )

    TaskOpt: TaskOptFields = Field(default_factory=TaskOptFields)

    class TaskSwitchFields(ConfigGroup):
        CurrencyWars: bool = Field(
            description="货币战争模块开关", default_factory=lambda: False
        )

        Daily: bool = Field(description="日常模块开关", default_factory=lambda: True)

        DivergentUniverse: bool = Field(
            description="差分宇宙模块开关", default_factory=lambda: False
        )

        ReceiveRewards: bool = Field(
            description="领取奖励模块开关", default_factory=lambda: True
        )

    TaskSwitch: TaskSwitchFields = Field(default_factory=TaskSwitchFields)
    Notify_CustomWebhooks: ConfigCollection[Webhook] = collection(Webhook)

    def _tag_plan(self) -> HSRUserConfig | HSRConfig:
        """标签读计划字段时用的对象。

        ``shared`` 来源的计划在所属 ``HSRConfig`` 的同名组上，经
        ``related_config["ScriptConfig"]`` 找到持有自己的那份托管配置；
        ``independent`` / ``native`` 来源，或找不到所属托管（如未挂到全局配置的
        独立实例）时读自己。
        """
        if self.Info.Base in ("independent", "native"):
            return self
        scripts = self.related_config.get("ScriptConfig")
        if scripts is None:
            return self
        for script in scripts.values():
            if isinstance(script, HSRConfig) and any(
                (user is self for user in script.UserData.values())
            ):
                return script
        return self

    def getTags(self) -> str:
        """生成 HSR 账号标签列表，返回JSON字符串格式的TagItem列表。"""
        tags: list[dict] = []
        server = self.Info.Resource
        server_label_map = {"CN-Official": "官服"}
        server_label = server_label_map.get(server, server or "未知")
        tags.append({"text": f"服务器：{server_label}", "color": "blue"})
        tags.append(_tag_proxy(self))
        tags.append(_tag_remained_days(self))
        now = datetime.now(tz=_utils_constants.UTC4)
        iso_year, iso_week, _ = now.isocalendar()
        current_week = f"{iso_year:04d}-W{iso_week:02d}"
        eow_done = (
            bool(self.Data.EchoOfWarCompletedThisWeek)
            and self.Data.EchoOfWarLastResetWeek == current_week
        )
        tags.append(
            {
                "text": "历战余响：已完成" if eow_done else "历战余响：未完成",
                "color": "green" if eow_done else "orange",
            }
        )
        weekly_done = (
            bool(self.Data.WeeklyCompletedThisWeek)
            and self.Data.WeeklyLastResetWeek == current_week
        )
        plan = self._tag_plan()
        du_on = bool(plan.TaskSwitch.DivergentUniverse)
        cw_on = bool(plan.TaskSwitch.CurrencyWars)
        if weekly_done:
            if du_on:
                weekly_text, weekly_color = ("差分宇宙 已完成", "green")
            elif cw_on:
                weekly_text, weekly_color = ("货币战争 已完成", "green")
            else:
                weekly_text, weekly_color = ("周常 已完成", "green")
        else:
            weekly_text, weekly_color = ("周常：未完成", "orange")
        tags.append({"text": weekly_text, "color": weekly_color})
        tags.append(_tag_notes(self))
        return json.dumps(tags, ensure_ascii=False)

    @classmethod
    def normalize_payload(cls, data):
        data = deepcopy(data)
        info = data.setdefault("Info", {})
        control = data.get("Control", {})
        if (
            "Base" not in info
            and isinstance(control, dict)
            and str(control.get("Mode") or "").strip().lower() == "direct"
        ):
            info["Base"] = "native"
        elif "Base" not in info and "Mode" not in info:
            info["Base"] = "independent"
        return data

    @virtual_field("Info.Tag")
    def compute_Info_Tag(self):
        try:
            return self.getTags()
        except Exception as exc:
            return str(exc)


class HSRConfig(DomainEntry):
    "HSR配置"

    related_config: ClassVar = {}

    class CloudFields(ConfigGroup):
        LastLogin: JsonDictString = Field(
            default_factory=lambda: "{ }",
            description="各账号最近一次确认已登录的时间（user_id → ISO 时间），只读展示用， 由运行结束后的写回与「登录云游戏」接口维护",
        )

        LoginTimeoutMinutes: Annotated[int, Field(ge=1, le=9999)] = Field(
            default_factory=lambda: 20,
            description="等待用户在浏览器窗口里手动登录的时间（分钟）",
        )

        MaxQueueMinutes: Annotated[int, Field(ge=1, le=9999)] = Field(
            default_factory=lambda: 60,
            description="最长排队时间（分钟），同时计入每个模块的超时预算",
        )

        UsePaidTime: bool = Field(
            default_factory=lambda: False,
            description="云·星穹铁道（Game.Platform = Cloud）专用，映射到三月七的 cloud_game_* 键 是否允许消耗付费时长走快速排队通道（花钱的开关，默认关）",
        )

    Cloud: CloudFields = Field(default_factory=CloudFields)

    class GameFields(ConfigGroup):
        Enabled: bool = Field(
            default_factory=lambda: True,
            description="是否由 MAS 管理游戏启停、进程监测和窗口操作（仅客户端平台）",
        )

        ForceResolution1920x1080: bool = Field(
            default_factory=lambda: False,
            description="启动游戏时临时覆盖 1920×1080 注册表分辨率",
        )

        # 页面选择游戏目录，同时兼容已保存的 StarRail.exe 路径。
        Path: Annotated[
            NativePath | None,
            path_policy(
                kind="any", must_exist=True, blocked_dirs=STANDARD_BLOCKED_DIRS
            ),
        ] = Field(default_factory=lambda: None, description="游戏路径")

        Platform: Literal["Client", "Cloud"] = Field(
            default_factory=lambda: "Client",
            description="游戏平台：本地客户端 / 云·星穹铁道（MAS 托管浏览器，只用三月七）。 OptionsValidator.correct() 回退的是 options[0]，Client 必须排第一。",
        )

        RedeemCodesOnlyWhenChanged: bool = Field(
            default_factory=lambda: True, description="仅在原生兑换码内容变化时执行兑换"
        )

        WaitTime: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            default_factory=lambda: 60, description="等待时间（秒）"
        )

    Game: GameFields = Field(default_factory=GameFields)

    class InfoFields(ConfigGroup):
        M7APath: FolderPath = Field(
            default_factory=lambda: None, description="M7A 路径"
        )

        Name: str = Field(
            default_factory=lambda: "新 HSR 托管", description="HSR 托管名称"
        )

        SRAPath: FolderPath = Field(
            default_factory=lambda: None, description="SRA 路径"
        )

        SRAProfile: SRAProfileName = Field(
            default_factory=lambda: "",
            description="SRA 配置档案（%APPDATA%\\SRA\\configs 下的文件名，不含扩展名；空串表示自动）",
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class ManagedFields(ConfigGroup):
        Options: JsonDictString = Field(
            description="托管任务选项 JSON", default_factory=lambda: "{ }"
        )

        TaskMapping: Annotated[JsonDictString, ui(visibility=UiVisibility.HIDE)] = (
            Field(default_factory=lambda: "{ }")
        )

    Managed: ManagedFields = Field(default_factory=ManagedFields)

    class RunFields(DesktopSessionRunFields):
        DailyTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 20,
            description="日常任务超时限制（分钟）",
        )

        LowPerformanceMode: bool = Field(
            default_factory=lambda: False,
            description="低性能兼容模式（仅三月七差分宇宙使用，映射到 weekly_divergent_stable_mode）",
        )

        ProxyTimesLimit: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            default_factory=lambda: 0, description="代理次数限制"
        )

        RunTimesLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 3, description="失败任务最大尝试次数"
        )

        WeeklyTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 60,
            description="周常任务超时限制（分钟）",
        )

    Run: RunFields = Field(default_factory=RunFields)

    class StageFields(ConfigGroup):
        Channel: Literal["CalyxGolden", "CalyxCrimson", "Relic", "Ornament"] = Field(
            description="体力关卡通道", default_factory=lambda: "CalyxGolden"
        )

        ScriptEchoOfWar: JsonDictString = Field(
            description="历战余响脚本原生字段 JSON", default_factory=lambda: "{ }"
        )

        ScriptStage: JsonDictString = Field(
            description="主刷关卡脚本原生字段 JSON", default_factory=lambda: "{ }"
        )

    Stage: StageFields = Field(default_factory=StageFields)

    class TaskMappingFields(ConfigGroup):
        CurrencyWars: Literal["M7A", "SRA"] = Field(
            description="货币战争模块执行脚本", default_factory=lambda: "SRA"
        )

        Daily: Literal["M7A", "SRA"] = Field(
            description="日常模块执行脚本", default_factory=lambda: "SRA"
        )

        DivergentUniverse: Literal["M7A", "SRA"] = Field(
            description="差分宇宙模块执行脚本", default_factory=lambda: "SRA"
        )

        ReceiveRewards: Literal["M7A", "SRA"] = Field(
            description="领取奖励模块执行脚本", default_factory=lambda: "SRA"
        )

    TaskMapping: TaskMappingFields = Field(default_factory=TaskMappingFields)

    class TaskOptFields(ConfigGroup):
        EchoOfWarWeekday: Literal[
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ] = Field(
            description="历战余响开始刷的星期（周一 ~ 周日）",
            default_factory=lambda: "Monday",
        )

    TaskOpt: TaskOptFields = Field(default_factory=TaskOptFields)

    class TaskSwitchFields(ConfigGroup):
        CurrencyWars: bool = Field(
            description="货币战争模块开关", default_factory=lambda: False
        )

        Daily: bool = Field(description="日常模块开关", default_factory=lambda: True)

        DivergentUniverse: bool = Field(
            description="差分宇宙模块开关", default_factory=lambda: False
        )

        ReceiveRewards: bool = Field(
            description="领取奖励模块开关", default_factory=lambda: True
        )

    TaskSwitch: TaskSwitchFields = Field(default_factory=TaskSwitchFields)

    class UpdateFields(ConfigGroup):
        AutoUpdateMode: Literal["Off", "BeforeRun", "AfterRun"] = Field(
            default_factory=lambda: "BeforeRun",
            description="SRA、三月七的自动更新：Off 关闭，BeforeRun 在任务开始前由 MAS 检查、下载、校验并安装。默认运行前更新；旧配置 AfterRun 兼容为运行前执行，显式关闭保持关闭。",
        )

        Channel: Literal["stable", "beta"] = Field(
            default_factory=lambda: "stable",
            description="更新渠道，两个引擎共用。Mirror 酱还支持 alpha，**故意不开放**—— 那是项目方的内部验证档。这两个值必须与前端选项和 schema 的 Literal 一致，三处任一多给一档，用户选了就会 422 或被静默纠回默认值。",
        )

        M7ASource: Literal["GitHub", "MirrorChyan"] = Field(
            default_factory=lambda: "GitHub",
            description="下载源按引擎拆开：两者可用的源本就不同，共用一项给不出不同默认值。 版本检查恒走 Mirror 酱的免 CDK 接口（自建站没有 latest 接口，只能用 tag 拼 URL，靠这条口径补上）；这里只决定字节从哪来，且**不做自动 分流**——选了 Mirror 酱而 CDK 不可用时报明原因并跳过，不悄悄换成 GitHub，用户得知道自己在从哪下载。 M7A 没有上 AUTO-MAS 自建站，所以只有两个源，默认 GitHub。",
        )

        MirrorChyanCDK: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="Mirror 酱 CDK，由用户自己填，**不做全局兜底**：全局那个服务的是 AUTO-MAS 自身的更新，和外部脚本不是一回事，串在一起只会让人猜自己 在用哪个。选 Mirror 酱作为下载源时这一项必填。",
        )
        SRASource: Literal["AutoSite", "GitHub", "MirrorChyan"] = Field(
            default_factory=lambda: "AutoSite",
            description="SRA 默认自建站：免 CDK、不限流、sha256 与 GitHub 逐字节一致，且 SRA 上游 CI 会主动往这里推送，其自带更新器也有 AUTO-MAS 这一档。",
        )

    Update: UpdateFields = Field(default_factory=UpdateFields)
    UserData: ConfigCollection[HSRUserConfig] = collection(HSRUserConfig)


class GeneralUserConfig(DomainEntry):
    "通用脚本账号配置"

    class DataFields(AccountRunFields): ...

    Data: DataFields = Field(default_factory=DataFields)

    class InfoFields(AccountNameFields, AccountScriptHookFields):
        PlanMode: Annotated[
            UUID | Literal["Fixed"],
            ref(
                "PlanConfig",
                default="Fixed",
                allow_values=("Fixed",),
                entry_types=(UniversalPlanConfig,),
            ),
        ] = Field(default="Fixed", description="固定配置或通用脚本计划表")

        Base: Annotated[
            Literal["shared", "independent", "native"],
            legacy(
                group="Info",
                name="Mode",
                convert=_utils_constants.normalize_base_source,
            ),
        ] = Field(
            default_factory=lambda: "independent",
            description="配置来源：independent 使用当前账号配置；兼容值 shared 当前仍使用该账号配置；native 使用外部脚本现有配置",
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class NotifyFields(ConfigGroup):
        Enabled: bool = Field(default_factory=lambda: False, description="是否启用通知")

        IfSendMail: bool = Field(
            default_factory=lambda: False, description="是否发送邮件"
        )

        IfSendStatistic: bool = Field(
            default_factory=lambda: False, description="是否发送统计信息"
        )

        IfServerChan: bool = Field(
            default_factory=lambda: False, description="是否启用 Server 酱"
        )

        ServerChanKey: str = Field(
            default_factory=lambda: "", description="Server 酱密钥"
        )

        ToAddress: str = Field(default_factory=lambda: "", description="收件地址")

    Notify: NotifyFields = Field(default_factory=NotifyFields)
    Notify_CustomWebhooks: ConfigCollection[Webhook] = collection(Webhook)

    def getTags(self) -> str:
        """生成通用账号标签列表"""
        tags = []
        tags.append(_tag_proxy(self, "任务"))
        tags.append(_tag_remained_days(self))
        tags.append(_tag_notes(self))
        return json.dumps(tags, ensure_ascii=False)

    @virtual_field("Info.Tag")
    def compute_Info_Tag(self):
        try:
            return self.getTags()
        except Exception as exc:
            return str(exc)


class OkwwUserConfig(DomainEntry):
    "OK-WW 账号配置（ok-script 线）"

    OKWW_TASK_BOOK: ClassVar = {1: "日常"}

    class DataFields(AccountRunFields, AccountRunStatusFields):
        LastTaskName: Literal["", "DailyTask", "MultiAccountConfigTask"] = Field(
            default="", description="上次运行的 ok-ww 任务名称；空值沿用历史任务序号"
        )

        LastTaskIndex: Annotated[int, Field(ge=0, le=9999)] = Field(
            description="上次运行的 ok-ww 任务序号（-t N）",
            default_factory=lambda: 0,
        )

    Data: DataFields = Field(default_factory=DataFields)

    class InfoFields(AccountNameFields, AccountScriptHookFields):
        PlanMode: Annotated[
            UUID | Literal["Fixed"],
            ref(
                "PlanConfig",
                default="Fixed",
                allow_values=("Fixed",),
                entry_types=(OkwwPlanConfig,),
            ),
        ] = Field(default="Fixed", description="固定配置或 Okww 计划表")

        Base: Annotated[
            Literal["shared", "independent", "native"],
            legacy(
                group="Info",
                name="Mode",
                convert=_utils_constants.normalize_base_source,
            ),
        ] = Field(
            description="base 来源（shared=共享、independent=独立、native=脚本原生配置）",
            default_factory=lambda: "shared",
        )

        Id: Annotated[str, encrypted()] = Field(
            description="账号", default_factory=lambda: ""
        )

        IfQuickConfig: bool = Field(
            default_factory=lambda: True,
            description="是否启用 MAS 覆写常规配置覆盖高频任务字段",
        )

        Resource: Literal["官服", "国际服"] = Field(
            default_factory=lambda: "官服", description="游戏服务器"
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class NotifyFields(ConfigGroup):
        Enabled: bool = Field(
            default_factory=lambda: False, description="是否启用账号通知"
        )

        IfSendMail: bool = Field(
            default_factory=lambda: False, description="是否发送邮件"
        )

        IfSendStatistic: bool = Field(
            default_factory=lambda: False, description="是否发送账号统计信息"
        )

        IfServerChan: bool = Field(
            default_factory=lambda: False, description="是否启用 Server 酱"
        )

        PushLogMode: Annotated[
            Literal["关闭", "逐条", "汇总"],
            legacy(
                group="Notify",
                name="PushLogEnabled",
                convert=lambda value: "关闭" if value is False else "汇总",
            ),
        ] = Field(
            default_factory=lambda: "汇总",
            description="任务报告节点详情的推送模式（log_box 采集的关键节点）： 关闭 = 不采集；逐条 = 采集并逐条带回时间戳；汇总 = 采集并按状态聚合",
        )

        ServerChanKey: str = Field(
            default_factory=lambda: "", description="Server 酱密钥"
        )

        ToAddress: str = Field(
            default_factory=lambda: "", description="账号通知收件地址"
        )

    Notify: NotifyFields = Field(default_factory=NotifyFields)

    class TaskFields(OkwwTaskFields):
        NativeConfigs: dict[str, dict[str, Any]] = Field(
            default_factory=dict, description="专项高级面板的原生配置"
        )

        DailyConfig: dict[str, Any] = Field(
            default_factory=dict, description="日常任务原生配置面板"
        )

        FarmEchoConfig: dict[str, Any] = Field(
            default_factory=dict, description="4C 声骸原生配置覆写，空值继承来源配置"
        )

        IfCustomArguments: bool = Field(
            default_factory=lambda: False, description="启用自定义启动参数"
        )
        CustomArguments: str = Field(
            default_factory=lambda: "-t DailyTask",
            description="自定义启动参数，开启后原样传递给 ok-ww",
        )

    Task: TaskFields = Field(default_factory=TaskFields)
    Notify_CustomWebhooks: ConfigCollection[Webhook] = collection(Webhook)

    def getTags(self) -> str:
        tags = []
        last_status = self.Data.LastProxyStatus
        tags.append(
            {
                "text": f"上次：{_tag_last_status(last_status)}",
                "color": "red" if last_status == "失败" else "green",
            }
        )
        last_task_index = int(self.Data.LastTaskIndex or 0)
        task_label = self.OKWW_TASK_BOOK.get(last_task_index, "未知")
        if self.Data.LastTaskName == "MultiAccountConfigTask":
            task_label = "原生多账号配置"
        elif self.Data.LastTaskName == "CustomTask":
            task_label = "自定义任务"
        tags.append({"text": f"任务：{task_label}", "color": "orange"})
        tags.append(_tag_remained_days(self))
        tags.append(_tag_notes(self))
        return json.dumps(tags, ensure_ascii=False)

    @virtual_field("Info.Tag")
    def compute_Info_Tag(self):
        try:
            return self.getTags()
        except Exception as exc:
            return str(exc)


class OkNteUserConfig(DomainEntry):
    "OK-NTE 账号配置（ok-script 线）"

    OKNTE_TASK_BOOK: ClassVar = {
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

    class DataFields(AccountRunFields, AccountRunStatusFields):
        LastTaskIndex: Annotated[int, Field(ge=0, le=9999)] = Field(
            description="上次运行的 ok-nte 任务序号（-t N）",
            default_factory=lambda: 0,
        )

    Data: DataFields = Field(default_factory=DataFields)

    class InfoFields(
        AccountNameFields, AccountCredentialFields, AccountScriptHookFields
    ):
        PlanMode: Annotated[
            UUID | Literal["Fixed"],
            ref(
                "PlanConfig",
                default="Fixed",
                allow_values=("Fixed",),
                entry_types=(OkNtePlanConfig,),
            ),
        ] = Field(default="Fixed", description="固定配置或 OkNte 计划表")

        Base: Annotated[
            Literal["shared", "independent", "native"],
            legacy(
                group="Info",
                name="Mode",
                convert=_utils_constants.normalize_base_source,
            ),
        ] = Field(
            description="base 来源（shared=共享、independent=独立、native=脚本原生配置）",
            default_factory=lambda: "shared",
        )

        Id: Annotated[str, encrypted()] = Field(
            description="账号", default_factory=lambda: ""
        )

        IfQuickConfig: bool = Field(
            description="是否启用覆写常规配置（与配置来源独立）",
            default_factory=lambda: True,
        )

        Password: Annotated[str, encrypted()] = Field(
            description="密码", default_factory=lambda: ""
        )

        Resource: Literal["官服"] = Field(
            default_factory=lambda: "官服", description="游戏服务器"
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class NotifyFields(ConfigGroup):
        Enabled: bool = Field(description="是否启用通知", default_factory=lambda: False)

        IfSendMail: bool = Field(
            description="是否发送邮件通知", default_factory=lambda: False
        )

        IfSendStatistic: bool = Field(
            description="是否发送统计信息", default_factory=lambda: False
        )

        IfServerChan: bool = Field(
            description="是否使用Server酱推送", default_factory=lambda: False
        )

        PushLogMode: Annotated[
            Literal["关闭", "逐条", "汇总"],
            legacy(
                group="Notify",
                name="PushLogEnabled",
                convert=lambda value: "关闭" if value is False else "汇总",
            ),
        ] = Field(
            default_factory=lambda: "汇总",
            description="任务报告节点详情的推送模式（log_box 采集的关键节点）： 关闭 = 不采集；逐条 = 采集并逐条带回时间戳；汇总 = 采集并按状态聚合",
        )

        ServerChanKey: str = Field(
            description="ServerChanKey", default_factory=lambda: ""
        )

        ToAddress: str = Field(description="邮件接收地址", default_factory=lambda: "")

    Notify: NotifyFields = Field(default_factory=NotifyFields)

    class TaskFields(ConfigGroup):
        ExitOnFinish: bool = Field(
            description="任务结束后退出（-e）", default_factory=lambda: True
        )

        TaskIndex: Annotated[int, Field(ge=1, le=19), none_as(1)] = Field(
            default_factory=lambda: 2,
            description="ok-nte.exe -t N -e；新版上游 DailyRoutineTask 是 -t 2",
        )

    Task: TaskFields = Field(default_factory=TaskFields)
    Notify_CustomWebhooks: ConfigCollection[Webhook] = collection(Webhook)

    def getTags(self) -> str:
        tags = []
        last_status = self.Data.LastProxyStatus
        tags.append(
            {
                "text": f"上次：{_tag_last_status(last_status)}",
                "color": "red" if last_status == "失败" else "green",
            }
        )
        last_task_index = int(self.Data.LastTaskIndex or 0)
        task_label = self.OKNTE_TASK_BOOK.get(last_task_index, "未知")
        tags.append({"text": f"任务：{task_label}", "color": "orange"})
        tags.append(_tag_remained_days(self))
        tags.append(_tag_notes(self))
        return json.dumps(tags, ensure_ascii=False)

    @virtual_field("Info.Tag")
    def compute_Info_Tag(self):
        try:
            return self.getTags()
        except Exception as exc:
            return str(exc)


def _compile_strptime_format(value: str) -> str:
    """用上游脚本同一个 strptime 编译器试一遍格式。

    格式写错（不认识的指令、重复命名的捕获组）要等到运行期准备阶段才炸，
    那一炸还会把收尾一起带断，所以在写进配置时就挡住。
    """

    try:
        TimeRE().compile(value)
    except KeyError as exc:
        raise ValueError(f"日志格式含不认识的指令 {exc}: {value}") from exc
    except re.error as exc:
        raise ValueError(f"日志格式无法编译（{exc}）: {value}") from exc
    return value


def reject_invalid_log_formats(data: dict[str, Any]) -> str | None:
    """保存前检查一次日志格式；返回给用户看的原因，没问题就是 None。

    接口侧的配置更新是宽松投影（``ConfigInput``），不跑字段校验，所以要在入口
    单独调一次；模型本身也挂了同一个校验，加载旧配置时同样会被挡住。
    """

    script = data.get("Script")
    if not isinstance(script, dict):
        return None
    for field, label in (
        ("LogPathFormat", "日志路径格式"),
        ("LogTimeFormat", "日志时间格式"),
    ):
        value = script.get(field)
        if isinstance(value, str) and value:
            try:
                _compile_strptime_format(value)
            except ValueError as exc:
                return f"{label}不可用：{exc}"
    return None


class GeneralConfig(DomainEntry):
    "通用配置"

    related_config: ClassVar = {}

    class GameFields(ConfigGroup):
        Arguments: CliArgumentString = Field(
            default_factory=lambda: "", description="游戏启动参数"
        )

        Enabled: bool = Field(default_factory=lambda: False, description="是否启用游戏")

        IfForceClose: bool = Field(
            default_factory=lambda: False, description="是否强制关闭"
        )

        Path: FilePath = Field(default_factory=lambda: None, description="游戏路径")

        ProcessName: str = Field(default_factory=lambda: "", description="游戏进程名称")

        Type: Literal["Emulator", "Client", "URL"] = Field(
            default_factory=lambda: "Emulator", description="游戏类型"
        )

        URL: str = Field(default_factory=lambda: "", description="自定义协议URL")

        WaitTime: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            default_factory=lambda: 0, description="等待时间（秒）"
        )

    Game: GameFields = Field(default_factory=GameFields)

    class InfoFields(ConfigGroup):
        Name: str = Field(default_factory=lambda: "新通用托管", description="托管名称")

        RootPath: FolderPath = Field(
            default_factory=lambda: None, description="根目录路径"
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class RunFields(DesktopSessionRunFields):
        HardTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 120,
            description="单账号运行总时限（分钟），包含等待和全部重试",
        )

        ProxyTimesLimit: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            default_factory=lambda: 0, description="代理次数限制"
        )

        RunTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 10,
            description="运行时间限制（分钟）",
        )

        RunTimesLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 3, description="运行次数限制"
        )

    Run: RunFields = Field(default_factory=RunFields)

    class ScriptFields(ConfigGroup):
        Arguments: CliArgumentListString = Field(
            default_factory=lambda: "", description="脚本参数"
        )

        ConfigPath: Annotated[
            NativePath | None,
            path_policy(kind="any", blocked_dirs=STANDARD_BLOCKED_DIRS),
        ] = Field(description="配置文件路径", default_factory=lambda: None)

        ConfigPathMode: Literal["File", "Folder"] = Field(
            default_factory=lambda: "File", description="配置路径模式"
        )

        ErrorLog: str = Field(default_factory=lambda: "", description="错误日志匹配")

        ErrorLogMode: Literal["Split", "Regex"] = Field(
            default_factory=lambda: "Split",
            description="错误日志匹配模式：Split = 「|」分隔关键字子串包含；Regex = 正则表达式",
        )

        IfTrackProcess: bool = Field(
            default_factory=lambda: False, description="是否追踪进程"
        )

        LogHookEnabled: bool = Field(
            default_factory=lambda: False,
            description="日志预处理启用开关：关闭时保留规则配置，行为与未配置预处理完全一致",
        )

        LogHookRules: str = Field(
            default_factory=lambda: "",
            description='日志预处理规则（JSON 数组，每项形如 {"type":"drop|replace",...}）； 预处理先于任务日志、推送日志采集与成功/失败判定执行，丢弃的行不进入下游',
        )

        LogPath: Annotated[
            NativePath | None,
            path_policy(kind="file", blocked_dirs=STANDARD_BLOCKED_DIRS),
        ] = Field(default_factory=lambda: None, description="日志路径")

        LogPathFormat: str = Field(
            default_factory=lambda: "%Y-%m-%d", description="日志路径格式"
        )

        LogTimeEnd: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 1, description="日志时间戳结束位置"
        )

        LogTimeFormat: str = Field(
            default_factory=lambda: "%Y-%m-%d %H:%M:%S", description="日志时间格式"
        )

        LogTimeStart: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 1, description="日志时间戳开始位置"
        )

        PushLogEnabled: bool = Field(
            default_factory=lambda: False,
            description="推送日志启用开关：关闭后保留高级正则配置，但不会实际采集推送日志",
        )

        PushLogPatterns: str = Field(
            default_factory=lambda: "",
            description='推送日志高级模式（JSON 数组，每项形如 {"type":"regex|multiline",...}）',
        )

        ScriptPath: Annotated[
            NativePath | None,
            path_policy(
                kind="any", must_exist=True, blocked_dirs=STANDARD_BLOCKED_DIRS
            ),
        ] = Field(default_factory=lambda: None, description="脚本路径")

        SuccessLog: str = Field(default_factory=lambda: "", description="成功日志匹配")

        SuccessLogMode: Literal["Split", "Regex"] = Field(
            default_factory=lambda: "Split",
            description="成功日志匹配模式：Split = 「|」分隔关键字子串包含；Regex = 正则表达式",
        )

        TrackProcessCmdline: CliArgumentString = Field(
            default_factory=lambda: "", description="追踪进程的启动命令行参数"
        )

        TrackProcessExe: str = Field(
            default_factory=lambda: "", description="追踪进程的文件路径"
        )

        TrackProcessName: str = Field(
            default_factory=lambda: "", description="追踪进程的名称"
        )

        UpdateConfigMode: Literal["Never", "Success", "Failure", "Always"] = Field(
            default_factory=lambda: "Never", description="更新配置模式"
        )

    Script: ScriptFields = Field(default_factory=ScriptFields)
    UserData: ConfigCollection[GeneralUserConfig] = collection(GeneralUserConfig)

    @classmethod
    def normalize_payload(cls, data: dict[str, Any]) -> dict[str, Any]:
        data = super().normalize_payload(data)
        script = data.get("Script")
        if isinstance(script, dict):
            # 保留旧文件选择器文案的变体兼容，无关未知值仍交给字段校验拒绝。
            mode = script.get("ConfigPathMode")
            if isinstance(mode, str) and "所有文件" in mode:
                script["ConfigPathMode"] = "File"
            elif mode == "文件夹":
                script["ConfigPathMode"] = "Folder"
        return data


class OkwwConfig(DomainEntry):
    "OK-WW 配置（ok-script 线）"

    class GameFields(ConfigGroup):
        AccountSwitchMethod: Annotated[
            Literal["NONE", "MAS", "OKWW_SINGLE", "OKWW"],
            legacy(
                group="Game",
                name="AccountSwitch",
                convert=lambda value: "MAS" if value else "NONE",
            ),
        ] = Field(
            default="MAS",
            description="账号切换方式：NONE 不切换；MAS 切换（推荐）；OKWW_SINGLE 由脚本逐账号切换、分别运行和重试；OKWW 批量切换并补跑未完成账号",
        )

        Arguments: CliArgumentString = Field(
            default_factory=lambda: "",
            description="鸣潮启动参数（直启默认补充 -krqlv=hd，可用 -krqlv=sd 或 -krqlv=uhd 覆盖，需已安装对应资源）",
        )

        ClientPath: FilePath = Field(
            default_factory=lambda: None,
            description="直启模式下手动指定的客户端程序路径（留空则由启动器路径自动定位）",
        )

        Enabled: bool = Field(
            default_factory=lambda: False, description="是否由 MAS 管理游戏进程"
        )

        IfAutoUpdate: bool = Field(
            default_factory=lambda: True,
            description="任务前是否由 MAS 检查并接管更新游戏",
        )

        Path: FilePath = Field(
            default_factory=lambda: None,
            description="鸣潮官方启动器路径（两种启动方式均由它定位游戏安装目录）",
        )

        Type: Literal["Client", "Launcher"] = Field(
            default_factory=lambda: "Client",
            description="游戏启动方式：Client=直启客户端（资源档位默认 HD，可通过启动参数覆盖），Launcher=经官方启动器 默认值必须排首位：值非法时 correct() 回落到 options[0]",
        )

        UpdateFullSyncLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 30,
            description="整文件同步体积上限（GB），超过则中止并提示手动处理",
        )

        WaitTime: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            default_factory=lambda: 60, description="等待游戏启动时间"
        )

    Game: GameFields = Field(default_factory=GameFields)

    class InfoFields(ConfigGroup):
        Name: str = Field(
            default_factory=lambda: "新 OK-WW 托管", description="托管名称"
        )

        RootPath: FolderPath = Field(
            default_factory=lambda: None, description="OK-WW 脚本根目录"
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class RunFields(DesktopSessionRunFields):
        HardTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 120,
            description="单账号运行总时限（分钟），包含等待和全部重试",
        )

        ProxyTimesLimit: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            default_factory=lambda: 0, description="每日代理次数上限"
        )

        RunTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 60, description="单次运行超时时间"
        )

        RunTimesLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 3, description="单次任务重试次数"
        )

    Run: RunFields = Field(default_factory=RunFields)
    UserData: ConfigCollection[OkwwUserConfig] = collection(OkwwUserConfig)


class OkNteConfig(DomainEntry):
    "OK-NTE 配置（ok-script 线）"

    class GameFields(ConfigGroup):
        AccountSwitch: bool = Field(
            default_factory=lambda: False,
            description="运行前强制切换账号（依赖游戏配置启用；用户未填手机号时不切换）",
        )

        Arguments: CliArgumentString = Field(
            description="游戏启动参数", default_factory=lambda: ""
        )

        CloseOnFinish: bool = Field(
            description="任务结束后是否关闭游戏", default_factory=lambda: True
        )

        ClosePolicyMigrationVersion: Annotated[
            int, Field(ge=0, le=1), ui(visibility=UiVisibility.HIDE)
        ] = Field(default=1, description="独立关闭游戏策略迁移版本")

        Enabled: bool = Field(
            description="游戏相关功能是否启用", default_factory=lambda: False
        )

        IfForceClose: bool = Field(
            description="是否强制关闭游戏进程", default_factory=lambda: True
        )

        LaunchBeforeTask: bool = Field(
            description="任务开始前是否由 MAS 启动游戏", default_factory=lambda: False
        )

        LaunchMode: Literal["Autoplay", "LauncherUi"] = Field(
            default_factory=lambda: "Autoplay",
            description="静默启动（Autoplay）= 启动器带 /autoplay 拉起，不点按钮；启动器界面启动 （LauncherUi）= 打开启动器界面，由 OCR 点「开始游戏」及其弹窗/更新分支。 默认值双轨：新建托管取类默认 Autoplay；既有托管（配置无该键）由 load 迁移 固化升级前的 LauncherUi（见 _migrate_oknte_launch_mode_default），保持升级前行为。",
        )

        Path: FilePath = Field(
            default_factory=lambda: None,
            description="异环直启 HTGame.exe 会卡界面，此路径为启动器 exe（NTELauncher/NTEGame.exe）， 旧值为 HTGame.exe 时运行时自动反推同安装根下的启动器",
        )

        ProcessName: str = Field(description="游戏进程名称", default_factory=lambda: "")

        Type: Literal["Client", "URL"] = Field(
            description="类型: PC端, URL协议", default_factory=lambda: "Client"
        )

        URL: str = Field(description="自定义协议URL", default_factory=lambda: "")

        WaitTime: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            description="游戏等待启动时间", default_factory=lambda: 60
        )

    Game: GameFields = Field(default_factory=GameFields)

    class InfoFields(ConfigGroup):
        Name: str = Field(
            description="托管名称", default_factory=lambda: "新 OK-NTE 托管"
        )

        RootPath: FolderPath = Field(
            description="脚本根目录", default_factory=lambda: None
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class RunFields(DesktopSessionRunFields):
        HardTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 120,
            description="单账号运行总时限（分钟），包含等待和全部重试",
        )

        ProxyTimesLimit: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            description="每日代理次数限制", default_factory=lambda: 0
        )

        RunTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            description="日志超时限制", default_factory=lambda: 120
        )

        RunTimesLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            description="重试次数限制", default_factory=lambda: 1
        )

    Run: RunFields = Field(default_factory=RunFields)

    class ScriptFields(ConfigGroup):
        Arguments: CliArgumentListString = Field(
            default_factory=lambda: "",
            description="OkNte 运行参数建议由账号配置（-t / -e 由账号配置 Task 决定），但仍保留高级参数入口",
        )

        ConfigPath: Annotated[
            NativePath | None,
            path_policy(kind="any", blocked_dirs=STANDARD_BLOCKED_DIRS),
        ] = Field(description="配置文件路径", default_factory=lambda: None)

        ConfigPathMode: Literal["File", "Folder"] = Field(
            description="配置文件类型: 单个文件, 文件夹",
            default_factory=lambda: "Folder",
        )

        ErrorLog: str = Field(
            description="错误时日志",
            default_factory=lambda: (
                "connected:False|Resolution Error|Timed out waiting for game process|Timed out waiting for launcher process"
            ),
        )

        ErrorLogMode: Literal["Split", "Regex"] = Field(
            description="错误时日志匹配模式: 关键字子串包含, 正则表达式",
            default_factory=lambda: "Split",
        )

        IfTrackProcess: bool = Field(
            description="是否追踪脚本子进程", default_factory=lambda: True
        )

        LogPath: Annotated[
            NativePath | None,
            path_policy(kind="file", blocked_dirs=STANDARD_BLOCKED_DIRS),
        ] = Field(description="日志文件路径", default_factory=lambda: None)

        LogPathFormat: str = Field(
            description="日志文件名格式", default_factory=lambda: ""
        )

        LogTimeEnd: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            description="日志时间戳结束位置", default_factory=lambda: 23
        )

        LogTimeFormat: str = Field(
            description="日志时间戳格式", default_factory=lambda: "%Y-%m-%d %H:%M:%S,%f"
        )

        LogTimeStart: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            description="日志时间戳开始位置", default_factory=lambda: 1
        )

        ScriptPath: FilePath = Field(
            description="脚本可执行文件路径", default_factory=lambda: None
        )

        SuccessLog: str = Field(
            description="成功时日志",
            default_factory=lambda: "Successfully Executed Task|任务执行完成",
        )

        SuccessLogMode: Literal["Split", "Regex"] = Field(
            description="成功时日志匹配模式: 关键字子串包含, 正则表达式",
            default_factory=lambda: "Split",
        )

        TrackProcessCmdline: CliArgumentString = Field(
            description="追踪进程启动命令行参数", default_factory=lambda: ""
        )

        TrackProcessExe: str = Field(
            description="追踪进程文件路径", default_factory=lambda: ""
        )

        TrackProcessName: str = Field(
            description="追踪进程名称", default_factory=lambda: ""
        )

        UpdateConfigMode: Literal["Never", "Success", "Failure", "Always"] = Field(
            description="更新配置时机, 从不, 仅成功时, 仅失败时, 任务结束时",
            default_factory=lambda: "Always",
        )

    Script: ScriptFields = Field(default_factory=ScriptFields)
    UserData: ConfigCollection[OkNteUserConfig] = collection(OkNteUserConfig)

    @classmethod
    def normalize_payload(cls, data):
        data, _ = _migrate_oknte_launch_mode_default(data)
        game = data.get("Game")
        if isinstance(game, dict) and not game.get("ClosePolicyMigrationVersion"):
            # 旧版关闭受托管总开关限制；只转换一次，后续保留用户独立开启的选择。
            if not game.get("Enabled", False):
                game["CloseOnFinish"] = False
            game["ClosePolicyMigrationVersion"] = 1
        return data


class ZzzOdUserConfig(DomainEntry):
    """绝区零一条龙账号配置（zzz-od 线，MaaEnd 式字段化账号配置）

    账号配置的事实源是本类的 配置字段（web 界面直接编辑，走通用
    updateUser 链路）：Game 区为账号/区服/游戏路径，OneDragon 区为一条龙
    任务编排（JSON，顺序即执行顺序）。运行时由这些字段生成 game_account.yml
    与 one_dragon/_group.yml 注入当前活跃实例槽、结束恢复原状（MAS 不留
    痕迹）。原生（native）来源不使用字段配置，直接以 zzz-od 原生配置运行。
    """

    class DataFields(AccountRunFields, AccountRunStatusFields):
        LauncherLastGood: Annotated[
            Literal["", "原始", "集成"],
            ui(visibility=UiVisibility.HIDE),
        ] = Field(
            default_factory=lambda: "",
            description='智能启动器模式最近一次成功运行的启动器（""=尚未记录；下次智能优先用它）',
        )

    Data: DataFields = Field(default_factory=DataFields)

    class GameFields(ConfigGroup):
        BilibiliAccountName: str = Field(
            default_factory=lambda: "", description="B服登录账号名"
        )

        CustomWinTitle: str = Field(
            default_factory=lambda: "", description="自定义窗口标题"
        )

        Dx12: bool = Field(
            default_factory=lambda: False,
            description="DX12 启动（MAS 便捷开关：注入时把 -use-d3d12 合并进一条龙的 launch_argument_advance；上游无独立字段，勾选框是唯一权威）",
        )

        FullScreen: Literal["0", "1"] = Field(
            default_factory=lambda: "0",
            description="全屏模式（上游枚举原值为字符串：'0'=窗口化 '1'=全屏）",
        )

        GameLanguage: Literal["cn", "en"] = Field(
            default_factory=lambda: "cn", description="游戏界面语言"
        )

        GamePath: FilePath = Field(
            default_factory=lambda: None,
            description="游戏 exe 完整路径（ZenlessZoneZero.exe）",
        )

        GameRegion: Literal["cn", "cn_b", "us", "eu", "asia", "twhkmo"] = Field(
            default_factory=lambda: "cn",
            description="游戏区服（zzz-od game_account.yml 的 game_region 取值）",
        )

        LaunchArgument: bool = Field(
            default_factory=lambda: False,
            description="一条龙游戏启动参数（game.yml 六字段，照抄上游 BasicGameConfig 默认值与取值；一条龙启动游戏时消费，总开关关闭则全部不生效）： 启动参数总开关",
        )

        LaunchArgumentAdvance: str = Field(
            default_factory=lambda: "",
            description="高级参数（原样透传给一条龙拼接，上游不解析，不做 shlex 校验）",
        )

        Monitor: Literal["1", "2", "3", "4"] = Field(
            default_factory=lambda: "1",
            description="显示器序号（上游枚举原值为字符串）",
        )

        Platform: Literal["PC"] = Field(
            default_factory=lambda: "PC",
            description="游戏平台（上游枚举 GamePlatformEnum.PC 的真实值为大写 'PC'）",
        )

        PopupWindow: bool = Field(
            default_factory=lambda: False,
            description="无边框窗口（一条龙拼参时转 -popupwindow）",
        )

        ScreenSize: Literal["1920x1080", "2560x1440", "3840x2160"] = Field(
            default_factory=lambda: "1920x1080", description="窗口尺寸（上游枚举原值）"
        )

        UseCustomWinTitle: bool = Field(
            default_factory=lambda: False, description="是否使用自定义窗口标题"
        )

    Game: GameFields = Field(default_factory=GameFields)

    class InfoFields(AccountNameFields, AccountScriptHookFields):
        Id: Annotated[str, legacy(group="Game", name="Account"), encrypted()] = Field(
            default_factory=lambda: "",
            description="登录账号（手机号/邮箱；留空沿用 zzz-od 已保存的登录态）",
        )

        Password: Annotated[str, legacy(group="Game", name="Password"), encrypted()] = (
            Field(
                default_factory=lambda: "",
                description="登录密码（DPAPI 加密落盘，注入/回读写 game_account.yml 时经 get/set 自动加解密）",
            )
        )

        Base: Annotated[
            Literal["shared", "independent", "native"],
            legacy(
                group="Info",
                name="Mode",
                convert=_utils_constants.normalize_base_source,
            ),
        ] = Field(
            default_factory=lambda: "independent",
            description="base 来源（shared=共享/independent=独立/native=原生）",
        )

        IfQuickConfig: bool = Field(
            default_factory=lambda: True,
            description="是否启用覆写常规配置（已封锁，仅保留字段兼容存量数据：原生来源在 load/update 归一为关，共享/独立来源不消费本开关）",
        )

        LauncherMode: Literal["自动", "原始", "集成"] = Field(
            default_factory=lambda: "自动",
            description="一条龙启动器选择（原生/独立两态通用）： 自动 = 优先用「上次成功」的启动器，启动失败自动换另一个重试并记住下一次 成功的那个；原始/集成 = 固定用对应启动器（对应 exe 未安装时回退可用项）",
        )

        SlotIdx: Annotated[int, Field(ge=-1, le=9999)] = Field(
            default_factory=lambda: -1,
            description="绑定的 zzz-od 实例槽下标（运行/配置会话内临时合成视图写回原生配置，非持久注册）：-1=未分配，首次运行或 「在一条龙内配置」时自动分配空闲 idx 并锁定该槽至会话结束， 此后配置会话与运行时注入都固定使用该槽。新槽从 MAS_SLOT_BASE（1001）起， 退到一条龙「升序找最小空号」够不到的高位段（上限 9999 与之一致放宽）",
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class NotifyFields(ConfigGroup):
        Enabled: bool = Field(
            default_factory=lambda: False, description="是否启用账号通知"
        )

        IfSendMail: bool = Field(
            default_factory=lambda: False, description="是否发送邮件"
        )

        IfSendStatistic: bool = Field(
            default_factory=lambda: False, description="是否发送账号统计信息"
        )

        IfServerChan: bool = Field(
            default_factory=lambda: False, description="是否启用 Server 酱"
        )

        PushLogMode: Literal["关闭", "逐条", "汇总"] = Field(
            default_factory=lambda: "汇总",
            description="任务报告节点详情的推送模式（运行记录 diff 出的各任务结果）： 关闭 = 不采集；逐条 = 逐条带回时间戳；汇总 = 按状态聚合",
        )

        ServerChanKey: str = Field(
            default_factory=lambda: "", description="Server 酱密钥"
        )

        ToAddress: str = Field(
            default_factory=lambda: "", description="账号通知收件地址"
        )

    Notify: NotifyFields = Field(default_factory=NotifyFields)

    class OneDragonFields(ConfigGroup):
        AfterDone: Literal["无", "关闭游戏", "关机"] = Field(
            default_factory=lambda: "关闭游戏",
            description="游戏结束后操作（仅 MAS 拉起的一条龙运行消费：CLI 传参 --close-game / --shutdown 60；无=不传参，游戏保持运行。 与一条龙原生 GUI 的「结束后」下拉无关——原生 after_done 只在 从 GUI 内启动运行时被消费，CLI 路径不读它）",
        )

        AppList: str = Field(
            default_factory=lambda: "[]",
            description='一条龙任务编排（JSON 数组字符串 [{"app_id": "...", "enabled": true}, ...]， 数组顺序即执行顺序；enabled=false 的任务由 zzz-od 跳过）',
        )

    OneDragon: OneDragonFields = Field(default_factory=OneDragonFields)
    Notify_CustomWebhooks: ConfigCollection[Webhook] = collection(Webhook)

    def getTags(self) -> str:
        tags = []
        last_status = self.Data.LastProxyStatus
        tags.append(
            {
                "text": f"上次：{_tag_last_status(last_status)}",
                "color": "red" if last_status == "失败" else "green",
            }
        )
        base = str(self.Info.Base or "independent")
        if base == "independent":
            try:
                app_list = json.loads(self.OneDragon.AppList or "[]")
            except (TypeError, ValueError):
                app_list = []
            if not isinstance(app_list, list):
                app_list = []
            enabled_count = sum(
                (
                    1
                    for item in app_list
                    if isinstance(item, dict) and item.get("enabled")
                )
            )
            if enabled_count > 0:
                tags.append({"text": f"一条龙：{enabled_count} 项", "color": "orange"})
            else:
                tags.append({"text": "一条龙：未编排", "color": "orange"})
        remained_day = self.Info.RemainedDay
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
                "text": f"剩余天数：{remained_day}天"
                if remained_day >= 0
                else "剩余天数：无期限",
                "color": tag_color,
            }
        )
        notes = self.Info.Notes
        tags.append(
            {
                "text": f"备注：{notes}"
                if len(notes) <= 20
                else f"备注：{notes[:20]}...",
                "color": "pink",
            }
        )
        return json.dumps(tags, ensure_ascii=False)

    @classmethod
    def normalize_payload(cls, data):
        data = deepcopy(data)
        normalized_data = deepcopy(data) if isinstance(data, dict) else {}
        normalized_data = migrate_legacy_fields(cls, normalized_data)
        info = normalized_data.get("Info")
        if isinstance(info, dict) and info.get("Base") == "native":
            info["IfQuickConfig"] = False
        return normalized_data

    @virtual_field("Info.Tag")
    def compute_Info_Tag(self):
        try:
            return self.getTags()
        except Exception as exc:
            return str(exc)


class ZzzOdConfig(DomainEntry):
    "绝区零一条龙配置（zzz-od 线）"

    class GameFields(ConfigGroup):
        AccountSwitch: Literal["单实例切换", "多实例切换", "MAS切换"] = Field(
            default_factory=lambda: "单实例切换",
            description="多账号账号切换方式（托管级下拉，value 对应 manager 的分派分支）： 单实例切换（默认，推荐）= 逐账号独立会话：注入该账号配置 → 单实例 运行（仅运行当前，无槽间切换）→ 跑完关闭 → 下一个账号。失败域 隔离最好，重试只重启失败账号； 多实例切换（不推荐）= 全部启用账号合并为一轮多账号运行，一条龙内部 依次切换账号。总时长最短，但单槽失败会拖整轮重试、切换次数随 账号数线性增长； MAS切换 = MAS 侧 OCR 操控游戏完成账号切换后交一条龙运行（暂未开放）。",
        )

        Arguments: CliArgumentString = Field(
            default_factory=lambda: "", description="游戏启动参数"
        )

        CloseOnFinish: bool = Field(
            default_factory=lambda: True,
            description="任务结束后由 MAS 关闭游戏（收尾/手动停止时按进程名结束游戏本体， 覆盖失败重试与手动停止场景，是「结束后操作」的兜底）。与账号级 OneDragon.AfterDone 下发的 --close-game 相互独立，同时配置会各 执行一次（无害）",
        )

        Enabled: bool = Field(
            default_factory=lambda: False,
            description="是否由 MAS 管理游戏进程（任务前启动游戏由此开关总控）",
        )

        LaunchBeforeTask: bool = Field(
            default_factory=lambda: False,
            description="任务前由 MAS 启动游戏（检测到游戏进程正在运行时跳过重复启动）",
        )

        Path: FilePath = Field(
            default_factory=lambda: None,
            description="游戏路径（游戏本体 ZenlessZoneZero.exe）",
        )

        WaitTime: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            default_factory=lambda: 60,
            description="启动游戏后的等待时间（秒）",
        )

    Game: GameFields = Field(default_factory=GameFields)

    class InfoFields(ConfigGroup):
        Name: str = Field(
            default_factory=lambda: "新绝区零一条龙托管", description="托管名称"
        )

        RootPath: FolderPath = Field(
            default_factory=lambda: None,
            description="zzz-od 安装根目录（含 OneDragon 启动器、src 与 config）",
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class RunFields(DesktopSessionRunFields):
        HardTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 120,
            description="单账号运行总时限（分钟），包含等待和全部重试",
        )

        ProxyTimesLimit: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            default_factory=lambda: 0, description="每日代理次数上限"
        )

        RunTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 40,
            description="单次运行超时时间（分钟）；这是日志停滞超时（latest_time 距今），不是 总时长上限——一条龙持续写日志就不会触发；启动器层故障（不写应用层 日志）也靠它兜底超时后切换启动器",
        )

        RunTimesLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 3, description="单次任务重试次数"
        )

    Run: RunFields = Field(default_factory=RunFields)
    UserData: ConfigCollection[ZzzOdUserConfig] = collection(ZzzOdUserConfig)


class BAAHUserConfig(DomainEntry):
    "BAAH 账号配置"

    related_config: ClassVar = {}

    class DataFields(AccountRunFields): ...

    Data: DataFields = Field(default_factory=DataFields)

    class InfoFields(AccountNameFields):
        ActivityLineType: Literal["JP", "Globle", "CN"] = Field(
            default_factory=lambda: "CN",
            description="活动排期按哪个服判断，供「活动关优先」使用（Kivo 时间轴的原文拼写：JP / Globle / CN）",
        )

        ConfigName: str = Field(
            default_factory=lambda: "",
            description="默认使用的 BAAH 配置文件名（BAAH_CONFIGS 目录下的文件名，不含 .json 后缀）",
        )

        IfEventFirst: bool = Field(
            default_factory=lambda: False,
            description="活动期间自动把「活动关卡」任务排到最前并打开",
        )

        IfQuickConfig: bool = Field(
            default_factory=lambda: True,
            description="兼容字段；BAAH 运行不消费此开关，运行期写入由配置托管、计划表及活动优先等实际选项决定",
        )

        StageMode: Annotated[
            UUID | str,
            ref(
                "PlanConfig",
                default="Fixed",
                allow_values=("Fixed",),
                entry_types=(BAAHPlanConfig,),
                display_field="Info.Name",
            ),
        ] = Field(
            default_factory=lambda: "Fixed",
            description="关卡计划表；Fixed 表示沿用 BAAH 中的关卡配置",
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class NotifyFields(ConfigGroup):
        Enabled: bool = Field(default_factory=lambda: False, description="是否启用通知")

        IfSendMail: bool = Field(
            default_factory=lambda: False, description="是否发送邮件"
        )

        IfSendStatistic: bool = Field(
            default_factory=lambda: False, description="是否发送统计信息"
        )

        IfServerChan: bool = Field(
            default_factory=lambda: False, description="是否启用 Server 酱"
        )

        ServerChanKey: str = Field(
            default_factory=lambda: "", description="Server 酱密钥"
        )

        ToAddress: str = Field(default_factory=lambda: "", description="收件地址")

    Notify: NotifyFields = Field(default_factory=NotifyFields)
    Notify_CustomWebhooks: ConfigCollection[Webhook] = collection(Webhook)

    def getTags(self) -> str:
        """生成 BAAH 账号标签列表"""
        tags = []
        tags.append(_tag_proxy(self, "任务"))
        tags.append(_tag_remained_days(self))
        tags.append(_tag_notes(self))
        return json.dumps(tags, ensure_ascii=False)

    @classmethod
    def normalize_payload(cls, data):
        data = deepcopy(data)
        migrated_data, migrated = _migrate_baah_event_first(data)
        return migrated_data

    @virtual_field("Info.Tag")
    def compute_Info_Tag(self):
        try:
            return self.getTags()
        except Exception as exc:
            return str(exc)


class BAAHConfig(DomainEntry):
    "BAAH 配置"

    class UpdateFields(ConfigGroup):
        TakeoverEnabled: bool = Field(
            default=False,
            description="运行前由 MAS 下载校验并安装 BAAH 官方更新包，普通下载失败后沿用当前安装",
        )
        Channel: Literal["stable", "beta"] = Field(
            default="stable", description="BAAH 更新通道"
        )
        MirrorChyanCDK: Annotated[str, encrypted()] = Field(
            default="",
            description="BAAH Mirror 酱 CDK，留空使用全局 CDK，无 CDK 使用 GitHub",
        )

    Update: UpdateFields = Field(default_factory=UpdateFields)

    related_config: ClassVar = {}

    class InfoFields(ConfigGroup):
        Name: str = Field(
            default_factory=lambda: "新 BAAH 托管", description="托管名称"
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class RunFields(ConfigGroup):
        HardTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 120,
            description="单账号运行总时限（分钟），包含等待和全部重试",
        )

        RunTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 60,
            description="运行时间限制（分钟）",
        )

        RunTimesLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 2, description="运行次数限制"
        )

    Run: RunFields = Field(default_factory=RunFields)

    class ScriptFields(ConfigGroup):
        BAAHPath: BAAHInstallPath = Field(
            default_factory=lambda: None,
            description="BAAH 主程序路径；程序目录、配置目录与日志目录都从它派生",
        )

        IfManageConfig: bool = Field(
            default_factory=lambda: True,
            description="是否由本软件托管运行所需的关键配置项",
        )

        PushLogEnabled: bool = Field(
            default_factory=lambda: True,
            description="是否在任务报告中展示 BAAH 的任务节点详情",
        )

    Script: ScriptFields = Field(default_factory=ScriptFields)
    UserData: ConfigCollection[BAAHUserConfig] = collection(BAAHUserConfig)


__all__ = [
    "ScriptConfigType",
    "UserConfigType",
    "MaaEndUserConfig",
    "MaaEndConfig",
    "HSRUserConfig",
    "HSRConfig",
    "GeneralUserConfig",
    "OkwwUserConfig",
    "OkNteUserConfig",
    "GeneralConfig",
    "OkwwConfig",
    "OkNteConfig",
    "ZzzOdUserConfig",
    "ZzzOdConfig",
    "BAAHUserConfig",
    "BAAHConfig",
]


type ScriptConfigType = (
    ScriptEntry
    | MaaEndConfig
    | HSRConfig
    | GeneralConfig
    | OkwwConfig
    | OkNteConfig
    | ZzzOdConfig
    | BAAHConfig
)
type UserConfigType = (
    UserEntry
    | MaaEndUserConfig
    | HSRUserConfig
    | GeneralUserConfig
    | OkwwUserConfig
    | OkNteUserConfig
    | ZzzOdUserConfig
    | BAAHUserConfig
)
