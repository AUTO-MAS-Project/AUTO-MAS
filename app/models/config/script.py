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

import asyncio
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from pathlib import Path as NativePath
from typing import Annotated, Any, ClassVar, Literal
from uuid import UUID

from pydantic import Field, PrivateAttr

from app.config import (
    ConfigCollection,
    ConfigGroup,
    UiVisibility,
    Virtual,
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
    WindowsNameString,
    path_policy,
)
from app.utils.constants import (
    MAA_STAGE_KEY,
    MAAEND_INVENTORY_TARGET_DEFAULTS,
    MAAEND_SANITY_TASK_DETAIL_LABELS,
    MAAEND_SANITY_TASK_FIELDS,
    MAAEND_SANITY_TASK_LABELS,
    MAAEND_STAGE_WITH_AB,
    RESOURCE_STAGE_INFO,
    STARRAIL_STAGE_BOOK,
    UTC4,
    get_game_day_tz,
    normalize_base_source,
)

from .base import DomainEntry
from .plan import BAAHPlanConfig, MaaEndPlanConfig, MaaPlanConfig, MSSPlanConfig
from .queue import Webhook
from .shared import (
    _BGI_LEGACY_SERVERS_TO_RESOURCE,
    SRAProfileName,
    _migrate_baah_event_first,
    _migrate_bgi_account_switch_default,
    _migrate_oknte_launch_mode_default,
    _normalize_maaend_sanity_task_type,
    _tag_last_status,
    _tag_notes,
    _tag_proxy,
    _tag_remained_days,
    local_timezone,
    migrate_maa_stamina_pipeline,
    none_as,
    normalize_maaend_plan_key,
)


class MaaUserConfig(DomainEntry):
    "MAA用户配置"

    related_config: ClassVar = {}

    class DataFields(ConfigGroup):
        def _game_day_timezone(self):
            """按当前用户服务器读取游戏日时间，不改变保存的 UTC 时刻。"""
            return get_game_day_tz(self.__dict__["_entry"].Info.Server)

        AnnihilationCompletedWeek: Annotated[str, none_as("")] = Field(
            default_factory=lambda: "2000-W01",
            description='剿灭达到周上限时的 ISO 周（形如 "2026-W34"）',
        )

        CultivateNotice: str = Field(
            default_factory=lambda: "",
            description="养成接管提示（注入时写入，供前端展示接管态；空 = 未接管）",
        )

        CustomInfrast: Annotated[JsonDictString, ui(visibility=UiVisibility.HIDE)] = (
            Field(default_factory=lambda: "{ }", description="自定义基建配置")
        )

        GreenTicketStoreMonth: Annotated[
            datetime | None, tz(UTC4), ui(widget="datetime", format="hms")
        ] = Field(
            default=None,
            description="上次完成绿票商店购买的完整时间，按 UTC+4 判断月份；空值表示尚未完成",
        )

        InfrastPlanIndex: Annotated[
            int,
            Field(ge=0, le=9999),
            ui(visibility=UiVisibility.HIDE),
        ] = Field(
            default_factory=lambda: 0,
            description="无时段排班表下一班的索引：每用户一份、由 MAS 在基建换班完成后推进； 带时段表交 MAA 按时段选班，不读它",
        )

        LastProxyDate: Annotated[
            datetime,
            tz(_game_day_timezone),
            ui(format="date"),
            ui(visibility=UiVisibility.HIDE),
        ] = Field(
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=UTC4),
            description="上次代理日期",
        )

        LastResVersion: str = Field(
            default_factory=lambda: "",
            description="上次成功代理时服务端的游戏资源版本，用于识别待下载的资源热更新",
        )

        ProxyTimes: Annotated[
            int,
            Field(ge=0, le=9999),
            ui(visibility=UiVisibility.HIDE),
        ] = Field(default_factory=lambda: 0, description="代理次数")

        StaminaPipelineBackup: JsonDictString = Field(
            description="理智流程升级前完整用户配置 JSON", default_factory=lambda: "{}"
        )

        StaminaPipelineVersion: Annotated[int, Field(ge=0, le=1)] = Field(
            default_factory=lambda: 1,
            description="理智流程配置迁移版本与升级前完整用户配置（关闭的旧计划仍可找回）",
        )

    Data: DataFields = Field(default_factory=DataFields)

    class InfoFields(ConfigGroup):
        Base: Annotated[
            Literal["shared", "independent", "native"],
            legacy(group="Info", name="Mode", convert=normalize_base_source),
        ] = Field(
            default_factory=lambda: "shared",
            description="base 来源（shared=共享/independent=独立/native=原生）",
        )

        Id: str = Field(default_factory=lambda: "", description="用户 ID")

        IfQuickConfig: bool = Field(
            default_factory=lambda: True,
            description="是否启用快速配置（与配置来源独立，按用户保存）",
        )

        IfScriptAfterTask: bool = Field(
            default_factory=lambda: False, description="任务后执行脚本"
        )

        IfScriptBeforeTask: bool = Field(
            default_factory=lambda: False, description="任务前执行脚本"
        )

        Name: WindowsNameString = Field(
            default_factory=lambda: "新用户", description="用户名称"
        )

        Notes: str = Field(default_factory=lambda: "无", description="备注")

        Password: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "", description="密码"
        )
        RemainedDay: Annotated[int, Field(ge=-1, le=9999), none_as(-1)] = Field(
            default_factory=lambda: -1, description="剩余天数"
        )

        ScriptAfterTask: FilePath = Field(
            description="任务后脚本路径", default_factory=lambda: None
        )

        ScriptBeforeTask: FilePath = Field(
            description="任务前脚本路径", default_factory=lambda: None
        )

        Server: Literal[
            "Official", "Bilibili", "YoStarEN", "YoStarJP", "YoStarKR", "txwy"
        ] = Field(default_factory=lambda: "Official", description="游戏服务器")

        Status: bool = Field(default_factory=lambda: True, description="是否启用")

        Tag: Virtual[str] = Field(
            default_factory=lambda: None,
            description="用户标签信息（虚拟字段，供前端显示）",
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class NotifyFields(ConfigGroup):
        Enabled: bool = Field(default_factory=lambda: False, description="是否启用通知")

        IfSendMail: bool = Field(
            default_factory=lambda: False, description="是否发送邮件"
        )

        IfSendSixStar: bool = Field(
            default_factory=lambda: False, description="是否发送六星通知"
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
        MedicineNumb: Annotated[
            int,
            Field(ge=0, le=9999),
            legacy(group="Info", name="MedicineNumb"),
            none_as(0),
        ] = Field(default_factory=lambda: 0, description="理智药数量")

        SeriesNumb: Annotated[
            Literal["0", "6", "5", "4", "3", "2", "1", "-1"],
            legacy(group="Info", name="SeriesNumb"),
        ] = Field(default_factory=lambda: "0", description="连战次数")

        Stage: Annotated[str, legacy(group="Info", name="Stage")] = Field(
            default_factory=lambda: "-", description="主关卡"
        )

        StageMode: Annotated[
            UUID | str,
            ref(
                "PlanConfig",
                default="Fixed",
                allow_values=("Fixed",),
                entry_types=(MaaPlanConfig,),
                display_field="Info.Name",
            ),
            legacy(group="Info", name="StageMode"),
        ] = Field(
            default_factory=lambda: "Fixed",
            description="关卡模式（Fixed 或关卡计划表 UUID）",
        )

        Stage_1: Annotated[str, legacy(group="Info", name="Stage_1")] = Field(
            default_factory=lambda: "-", description="备选关卡 1"
        )

        Stage_2: Annotated[str, legacy(group="Info", name="Stage_2")] = Field(
            default_factory=lambda: "-", description="备选关卡 2"
        )

        Stage_3: Annotated[str, legacy(group="Info", name="Stage_3")] = Field(
            default_factory=lambda: "-", description="备选关卡 3"
        )

    Stage: StageFields = Field(default_factory=StageFields)

    class TaskFields(ConfigGroup):
        ActivityMedicineNumb: Annotated[
            int,
            Field(ge=0, le=9999),
            legacy(group="Info", name="MedicineNumb"),
            none_as(0),
        ] = Field(
            default_factory=lambda: 0,
            description="活动关优先任务吃理智药数量",
        )

        ActivityStageIndex: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 1,
            description="优先刷取的活动关卡序号",
        )

        Annihilation: Annotated[
            Literal[
                "Close",
                "Annihilation",
                "Chernobog@Annihilation",
                "LungmenOutskirts@Annihilation",
                "LungmenDowntown@Annihilation",
            ],
            legacy(group="Info", name="Annihilation"),
        ] = Field(default_factory=lambda: "Annihilation", description="剿灭模式")

        AnnihilationStartWeekday: Annotated[
            Literal[
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ],
            legacy(group="Info", name="AnnihilationStartWeekday"),
        ] = Field(default_factory=lambda: "Monday", description="剿灭开始星期")

        CultivateAutoRaise: bool = Field(
            default_factory=lambda: False, description="是否注入 MAA 原生干员培养任务"
        )

        CultivateSkipDuringActivity: bool = Field(
            default_factory=lambda: False, description="活动期间是否跳过养成计划"
        )

        CultivateSkipDuringResourceCollection: bool = Field(
            default_factory=lambda: False, description="资源收集期是否跳过养成计划"
        )

        CultivateSklandAccount: str = Field(
            default_factory=lambda: "",
            description="森空岛绑定：签到账号组 UUID（凭据引用，凭据本体只存签到域）",
        )

        CultivateSklandUid: str = Field(
            default_factory=lambda: "",
            description="森空岛绑定：绑定角色的游戏 uid（非森空岛 userId）",
        )

        CultivateTargets: JsonListString = Field(
            default_factory=lambda: "[]", description="干员养成目标"
        )

        DepotMaintainPlans: JsonListString = Field(
            default_factory=lambda: (
                '[{"Stage":"PR-A-1","DropId":"3261","DropCount":20},{"Stage":"PR-A-1","DropId":"3231","DropCount":20},{"Stage":"PR-B-1","DropId":"3251","DropCount":20},{"Stage":"PR-B-1","DropId":"3241","DropCount":20},{"Stage":"PR-C-1","DropId":"3211","DropCount":20},{"Stage":"PR-C-1","DropId":"3271","DropCount":20},{"Stage":"PR-D-1","DropId":"3221","DropCount":20},{"Stage":"PR-D-1","DropId":"3281","DropCount":20},{"Stage":"PR-A-2","DropId":"3262","DropCount":20},{"Stage":"PR-A-2","DropId":"3232","DropCount":20},{"Stage":"PR-B-2","DropId":"3252","DropCount":20},{"Stage":"PR-B-2","DropId":"3242","DropCount":20},{"Stage":"PR-C-2","DropId":"3212","DropCount":20},{"Stage":"PR-C-2","DropId":"3272","DropCount":20},{"Stage":"PR-D-2","DropId":"3222","DropCount":20},{"Stage":"PR-D-2","DropId":"3282","DropCount":20},{"Stage":"CE-6","DropId":"4001","DropCount":2000000},{"Stage":"AP-5","DropId":"4006","DropCount":5000},{"Stage":"CA-5","DropId":"3303","DropCount":200}]'
            ),
            description="库存保持计划（快速配置面板维护；MAA 侧同名 PlanList 为透传载体）",
        )

        EventDepotMaintainPlans: JsonListString = Field(
            default_factory=lambda: (
                '[{"StageType":"all","DropCount":999,"OrundumDropCount":9999}]'
            ),
            description="活动库存保持计划，保存材料关序号及目标库存，运行时解析当前活动",
        )

        IfActivityFirst: bool = Field(
            default_factory=lambda: False, description="活动期间是否优先刷活动关"
        )

        IfAward: bool = Field(default_factory=lambda: True, description="是否领取奖励")

        IfCultivate: bool = Field(
            default_factory=lambda: False, description="是否干员养成"
        )

        IfDepotMaintain: bool = Field(
            default_factory=lambda: True, description="是否库存保持"
        )

        IfEventDepotMaintain: bool = Field(
            default_factory=lambda: True, description="是否启用活动关均衡理智"
        )

        IfFight: bool = Field(default_factory=lambda: True, description="是否理智作战")

        IfGreenTicketStore: bool = Field(
            default_factory=lambda: False, description="是否每月自动购买一次绿票商店"
        )

        IfInfrast: bool = Field(
            default_factory=lambda: True, description="是否基建换班"
        )

        IfMall: bool = Field(default_factory=lambda: True, description="是否信用收支")

        IfRecruit: bool = Field(
            default_factory=lambda: True, description="是否公开招募"
        )

        IfStartUp: bool = Field(
            default_factory=lambda: True, description="是否自动唤醒"
        )

        IfSwitchTheme: bool = Field(
            default_factory=lambda: False,
            description="是否更换主题（主题名称在 MAA 侧配置，MAS 仅透传）",
        )

        InfrastMode: Annotated[
            Literal["Normal", "Rotation", "Custom"],
            legacy(group="Info", name="InfrastMode"),
        ] = Field(default_factory=lambda: "Normal", description="基建模式")

        InfrastName: Annotated[
            Virtual[str], legacy(group="Info", name="InfrastName")
        ] = Field(default_factory=lambda: None, description="基建配置名称")

    Task: TaskFields = Field(default_factory=TaskFields)
    Notify_CustomWebhooks: ConfigCollection[Webhook] = collection(Webhook)

    def getInfrastName(self) -> str:
        if self.Task.InfrastMode != "Custom":
            return "未使用自定义基建模式"
        infrast_data = json.loads(self.Data.CustomInfrast)
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
        tags.append(_tag_proxy(self, tz=get_game_day_tz(self.Info.Server)))
        tags.append(_tag_remained_days(self))
        if not self.Info.IfQuickConfig:
            tags.append(_tag_notes(self))
            return json.dumps(tags, ensure_ascii=False)

        infrast_mode = self.Task.InfrastMode
        if self.Task.IfInfrast:
            if infrast_mode == "Normal":
                infrast_text = "基建：常规"
            elif infrast_mode == "Rotation":
                infrast_text = "基建：轮换"
            elif infrast_mode == "Custom":
                infrast_text = f"基建：{(self.getInfrastName() if len(self.getInfrastName()) < 10 else self.getInfrastName()[:10] + '...')}"
            else:
                infrast_text = "基建：开启"
            tags.append({"text": infrast_text, "color": "purple"})
        else:
            tags.append({"text": "基建：关闭", "color": "red"})
        plan_data = {
            stage_key: self.get_stage_zh(getattr(self.Stage, stage_key))
            for stage_key in MAA_STAGE_KEY[2:]
        }
        tag_color = "blue"
        if self.Stage.StageMode != "Fixed":
            plan = self.related_config["PlanConfig"][self.Stage.StageMode]
            if isinstance(plan, MaaPlanConfig):
                plan_data = {
                    stage_key: self.get_stage_zh(
                        plan.get_current_info(stage_key, server=self.Info.Server)
                    )
                    for stage_key in MAA_STAGE_KEY[2:]
                }
                tag_color = "green"
        tags.append({"text": f"主关卡：{plan_data['Stage']}", "color": tag_color})
        backup_stages = [
            plan_data[f"Stage_{i}"]
            for i in range(1, 4)
            if plan_data[f"Stage_{i}"] != "禁用"
        ]
        if backup_stages:
            tags.append(
                {"text": f"备选：{', '.join(backup_stages)}", "color": tag_color}
            )
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

    @classmethod
    def normalize_payload(cls, data):
        data = deepcopy(data)
        migrated_data, migrated = migrate_maa_stamina_pipeline(data)
        return migrated_data

    @virtual_field("Info.Tag")
    def compute_Info_Tag(self):
        try:
            return self.getTags()
        except Exception as exc:
            return str(exc)

    @virtual_field("Task.InfrastName")
    def compute_Task_InfrastName(self):
        try:
            return self.getInfrastName()
        except Exception as exc:
            return str(exc)


class MaaConfig(DomainEntry):
    "MAA配置"

    related_config: ClassVar = {}

    class EmulatorFields(ConfigGroup):
        Id: Annotated[
            UUID | str,
            ref(
                "EmulatorConfig",
                default="-",
                allow_values=("-",),
                display_field="Info.Name",
            ),
        ] = Field(default_factory=lambda: "-", description="模拟器 ID")
        Index: str = Field(default_factory=lambda: "-", description="模拟器索引")

    Emulator: EmulatorFields = Field(default_factory=EmulatorFields)

    class InfoFields(ConfigGroup):
        Name: str = Field(
            default_factory=lambda: "新 MAA 脚本", description="MAA 脚本名称"
        )

        Path: FolderPath = Field(default_factory=lambda: None, description="MAA 路径")

    Info: InfoFields = Field(default_factory=InfoFields)

    class RunFields(ConfigGroup):
        AnnihilationTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 40,
            description="剿灭时间限制（分钟）",
        )

        GameUpdateTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 60,
            description="游戏更新时间限制（分钟）",
        )

        HardTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 120,
            description="单账号运行总时限（分钟），包含等待和全部重试",
        )

        IfAutoInstallGameApk: bool = Field(
            default_factory=lambda: False,
            description="是否允许自动下载并安装游戏安装包（仅官服）",
        )

        IfCheckGameUpdate: bool = Field(
            default_factory=lambda: False, description="是否在启动 MAA 前检查游戏更新"
        )

        ProxyTimesLimit: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            default_factory=lambda: 0, description="代理次数限制"
        )

        RoutineTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 10,
            description="日常时间限制（分钟）",
        )

        RunTimesLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 3, description="运行次数限制"
        )

        TaskTransitionMethod: Literal["NoAction", "ExitGame", "ExitEmulator"] = Field(
            default_factory=lambda: "ExitEmulator", description="任务切换方式"
        )

    Run: RunFields = Field(default_factory=RunFields)

    class UpdateFields(ConfigGroup):
        TakeoverMigrationVersion: Annotated[int, Field(ge=0, le=1)] = Field(
            default=1, description="更新接管一次性迁移版本"
        )

        MirrorChyanCDK: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="本脚本的 Mirror 酱 CDK（加密存储，留空回退 MAS 全局配置）",
        )
        TakeoverEnabled: bool = Field(
            default_factory=lambda: False,
            description="是否接管 MAA 本体与资源更新（关=完全由 MAA 自行处理）",
        )

    Update: UpdateFields = Field(default_factory=UpdateFields)
    UserData: ConfigCollection[MaaUserConfig] = collection(MaaUserConfig)

    @classmethod
    def normalize_payload(cls, data):
        data = super().normalize_payload(data)
        if data and "TakeoverMigrationVersion" not in data.get("Update", {}):
            data.setdefault("Update", {})["TakeoverMigrationVersion"] = 0
        return data

    async def migrate_update_takeover(self, *, global_cdk: str) -> bool:
        """为有 CDK 的旧脚本一次性开启接管，之后保留用户的选择。"""
        if self.Update.TakeoverMigrationVersion:
            return False
        enabled = bool(self.Update.MirrorChyanCDK.strip() or global_cdk.strip())
        values = {"TakeoverMigrationVersion": 1}
        if enabled:
            values["TakeoverEnabled"] = True
        await self.update(type(self).model_validate({"Update": values}))
        return enabled


class MaaEndUserConfig(DomainEntry):
    "MaaEnd用户配置"

    related_config: ClassVar = {}

    class DataFields(ConfigGroup):
        LastProxyDate: Annotated[datetime, tz(UTC4), ui(format="date")] = Field(
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=UTC4),
            description="上次代理日期",
        )

        LastProxyStatus: Literal["未知", "成功", "失败"] = Field(
            default_factory=lambda: "未知", description="上次代理状态"
        )

        PeriodTaskRecords: JsonDictString = Field(
            default_factory=lambda: "{ }",
            description="MaaEnd 每日任务完成记录，结构为 daily -> task name -> 日期",
        )

        ProxyTimes: Annotated[int, Field(ge=0, le=9999)] = Field(
            default_factory=lambda: 0, description="代理次数"
        )

    Data: DataFields = Field(default_factory=DataFields)

    class InfoFields(ConfigGroup):
        Base: Annotated[
            Literal["shared", "independent", "native"],
            legacy(group="Info", name="Mode", convert=normalize_base_source),
        ] = Field(
            default_factory=lambda: "shared",
            description="base 来源（shared=共享/independent=独立/native=原生）",
        )

        Id: str = Field(default_factory=lambda: "", description="用户ID")

        IfQuickConfig: bool = Field(
            default_factory=lambda: True, description="是否启用快速配置"
        )

        IfScriptAfterTask: bool = Field(
            default_factory=lambda: False, description="任务后执行脚本"
        )

        IfScriptBeforeTask: bool = Field(
            default_factory=lambda: False, description="任务前执行脚本"
        )

        Name: WindowsNameString = Field(
            default_factory=lambda: "新用户", description="用户名称"
        )

        Notes: str = Field(default_factory=lambda: "无", description="备注")

        Password: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "", description="密码"
        )
        RemainedDay: Annotated[int, Field(ge=-1, le=9999), none_as(-1)] = Field(
            default_factory=lambda: -1, description="剩余天数"
        )

        Resource: Literal["官服"] = Field(
            default_factory=lambda: "官服", description="资源名称"
        )

        SanityStrategy: Literal["MAS", "Native", "Inventory"] = Field(
            default="MAS", description="理智任务策略：指定任务、原生策略或库存目标"
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

        ScriptAfterTask: FilePath = Field(
            description="任务后脚本路径", default_factory=lambda: None
        )

        ScriptBeforeTask: FilePath = Field(
            description="任务前脚本路径", default_factory=lambda: None
        )

        Status: bool = Field(default_factory=lambda: True, description="是否启用")

        Tag: Virtual[str] = Field(
            default_factory=lambda: None, description="用户标签信息"
        )

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
            default_factory=lambda: json.dumps(MAAEND_INVENTORY_TARGET_DEFAULTS),
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

        CrisisDrills: Literal[
            "AdvancedProgression1",
            "AdvancedProgression2",
            "AdvancedProgression3",
            "AdvancedProgression4",
            "AdvancedProgression5",
        ] = Field(
            description="危境预演任务", default_factory=lambda: "AdvancedProgression1"
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

        IfSanity: bool = Field(description="理智任务", default_factory=lambda: True)

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
        mode = self.Info.SanityMode
        if mode == "Fixed":
            return (
                normalize_maaend_plan_key(
                    {
                        field: getattr(self.Task, field)
                        for field in MAAEND_SANITY_TASK_FIELDS
                    }
                ),
                "Fixed",
            )
        try:
            plan = self.related_config["PlanConfig"][mode]
        except (KeyError, ValueError) as e:
            raise ValueError("引用的理智任务计划表不存在") from e
        return (plan.get_current_key(), str(mode))

    def getTags(self) -> str:
        """生成用户标签列表，返回JSON字符串格式的TagItem列表"""
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

        if self.Task.IfSanity and self.Info.SanityStrategy in ("Native", "Inventory"):
            label = (
                "库存目标"
                if self.Info.SanityStrategy == "Inventory"
                else "MaaEnd 原生策略"
            )
            tags.append({"text": f"理智任务：{label}", "color": "blue"})
        elif self.Task.IfSanity:
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
            tags.append({"text": f"详细任务：{detail_label}", "color": "blue"})
            if detail_key in MAAEND_STAGE_WITH_AB:
                tags.append(
                    {
                        "text": "奖励组：奖励组 A"
                        if task_key["RewardsSetOption"] == "RewardsSetA"
                        else "奖励组：奖励组 B",
                        "color": "blue",
                    }
                )
        tags.append(_tag_notes(self))
        return json.dumps(tags, ensure_ascii=False)

    @classmethod
    def normalize_payload(cls, data):
        data = deepcopy(data)
        info_data = data.get("Info")
        if isinstance(info_data, dict):
            legacy_base = str(info_data.get("Mode") or "")
            # 旧 Mode 同时决定来源和快速配置开关；已给出的新来源始终优先。
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

        EmulatorId: Annotated[
            UUID | str,
            ref(
                "EmulatorConfig",
                default="-",
                allow_values=("-",),
                display_field="Info.Name",
            ),
        ] = Field(default_factory=lambda: "-", description="模拟器 ID")
        EmulatorIndex: str = Field(
            default_factory=lambda: "-", description="模拟器索引"
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
            default_factory=lambda: "新 MaaEnd 脚本", description="MaaEnd 脚本名称"
        )

        Path: FolderPath = Field(
            default_factory=lambda: None, description="MaaEnd 路径"
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class RunFields(ConfigGroup):
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
            description="任务失败时保存日志包的目录，留空表示不保存",
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
    _loaded_resource: dict = PrivateAttr(default_factory=dict)
    _preload_task: Any = PrivateAttr(default=None)

    async def _activate_from_payload(
        self, payload: dict[str, Any], *, regenerate_uuids: bool = False
    ) -> None:
        """按当前资源入口迁移历史 Client 启动方式，再激活配置。"""
        from app.task.MaaEnd.resource_loader import try_load_maaend_options

        payload = type(self).normalize_payload(payload)
        game = payload.get("Game", {})
        if isinstance(game, dict) and game.get("LaunchMode") == "Client":
            root_path = payload.get("Info", {}).get("Path")
            root = Path(root_path) if root_path else None
            if root is not None and (root / "interface.json").is_file():
                options = await asyncio.to_thread(try_load_maaend_options, root)
                if options is not None:
                    game["LaunchMode"] = (
                        "MaaEnd"
                        if game.get("ControllerType")
                        in options["launchGameControllers"]
                        else "MAS"
                    )
        await super()._activate_from_payload(payload, regenerate_uuids=regenerate_uuids)

    async def preload_resource(self) -> None:
        """尝试预加载 MaaEnd 动态资源，失败时保留现有配置。"""
        root_path = str(self.Info.Path or "").strip()
        if not root_path:
            return

        def _try_load_in_thread():
            from app.task.MaaEnd.resource_loader import try_load_maaend_options

            return try_load_maaend_options(Path(root_path))

        resource = await asyncio.to_thread(_try_load_in_thread)
        if resource is None:
            return
        for user_config in self.UserData.values():
            user_config.cache_maaend_resource(resource)

    def get_loaded_resource(self) -> dict[str, Any]:
        """读取已经载入内存的 MaaEnd 动态资源。"""
        root_path = str(self.Info.Path or "").strip()
        if not root_path:
            raise ValueError("MaaEnd 路径未配置")
        from app.task.MaaEnd.resource_loader import get_loaded_maaend_options

        return get_loaded_maaend_options(Path(root_path))

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


class SrcUserConfig(DomainEntry):
    "SRC用户配置"

    related_config: ClassVar = {}

    class DataFields(ConfigGroup):
        LastProxyDate: Annotated[datetime, tz(UTC4), ui(format="date")] = Field(
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=UTC4),
            description="上次代理日期",
        )

        ProxyTimes: Annotated[int, Field(ge=0, le=9999)] = Field(
            default_factory=lambda: 0, description="代理次数"
        )

    Data: DataFields = Field(default_factory=DataFields)

    class InfoFields(ConfigGroup):
        Base: Annotated[
            Literal["shared", "independent", "native"],
            legacy(group="Info", name="Mode", convert=normalize_base_source),
        ] = Field(
            default_factory=lambda: "shared",
            description="base 来源（shared=共享/independent=独立/native=原生）",
        )

        Id: str = Field(default_factory=lambda: "", description="用户 ID")

        IfQuickConfig: bool = Field(
            default_factory=lambda: True,
            description="是否启用快速配置（与配置来源独立，按用户保存）",
        )

        IfScriptAfterTask: bool = Field(
            default_factory=lambda: False, description="任务后执行脚本"
        )

        IfScriptBeforeTask: bool = Field(
            default_factory=lambda: False, description="任务前执行脚本"
        )

        Name: WindowsNameString = Field(
            default_factory=lambda: "新用户", description="用户名称"
        )

        Notes: str = Field(default_factory=lambda: "无", description="备注")

        Password: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "", description="密码"
        )
        RemainedDay: Annotated[int, Field(ge=-1, le=9999), none_as(-1)] = Field(
            default_factory=lambda: -1, description="剩余天数"
        )

        ScriptAfterTask: FilePath = Field(
            description="任务后脚本路径", default_factory=lambda: None
        )

        ScriptBeforeTask: FilePath = Field(
            description="任务前脚本路径", default_factory=lambda: None
        )

        Server: Literal[
            "CN-Official",
            "CN-Bilibili",
            "VN-Official",
            "OVERSEA-America",
            "OVERSEA-Asia",
            "OVERSEA-Europe",
            "OVERSEA-TWHKMO",
        ] = Field(default_factory=lambda: "CN-Official", description="游戏服务器")

        Status: bool = Field(default_factory=lambda: True, description="是否启用")

        Tag: Virtual[str] = Field(
            default_factory=lambda: None, description="用户标签信息"
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

    class StageFields(ConfigGroup):
        Channel: Literal["Relic", "Materials", "Ornament"] = Field(
            default_factory=lambda: "Relic", description="关卡通道"
        )

        EchoOfWar: Literal[
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
        ] = Field(default_factory=lambda: "-", description="历战余响关卡")

        ExtractReservedTrailblazePower: bool = Field(
            default_factory=lambda: False, description="使用储备开拓力"
        )

        FuelReserve: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            default_factory=lambda: 5, description="保留的燃料数量"
        )

        Materials: Literal[
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
        ] = Field(default_factory=lambda: "-", description="材料关卡")

        Ornament: Literal[
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
        ] = Field(default_factory=lambda: "-", description="饰品关卡")

        Relic: Literal[
            "-",
            "Cavern_of_Corrosion_Path_of_Insight",
            "Cavern_of_Corrosion_Path_of_Possession",
            "Cavern_of_Corrosion_Path_of_Hidden_Salvation",
            "Cavern_of_Corrosion_Path_of_Thundersurge",
            "Cavern_of_Corrosion_Path_of_Aria",
            "Cavern_of_Corrosion_Path_of_Uncertainty",
            "Cavern_of_Corrosion_Path_of_Cavalier",
            "Cavern_of_Corrosion_Path_of_Dreamdive",
            "Cavern_of_Corrosion_Path_of_Darkness",
            "Cavern_of_Corrosion_Path_of_Elixir_Seekers",
            "Cavern_of_Corrosion_Path_of_Conflagration",
            "Cavern_of_Corrosion_Path_of_Holy_Hymn",
            "Cavern_of_Corrosion_Path_of_Providence",
            "Cavern_of_Corrosion_Path_of_Drifting",
            "Cavern_of_Corrosion_Path_of_Jabbing_Punch",
            "Cavern_of_Corrosion_Path_of_Gelid_Wind",
        ] = Field(default_factory=lambda: "-", description="遗器关卡")

        SimulatedUniverseWorld: Literal[
            "-",
            "Simulated_Universe_World_3",
            "Simulated_Universe_World_4",
            "Simulated_Universe_World_5",
            "Simulated_Universe_World_6",
            "Simulated_Universe_World_8",
        ] = Field(default_factory=lambda: "-", description="模拟宇宙关卡")

        UseFuel: bool = Field(default_factory=lambda: False, description="使用燃料")

    Stage: StageFields = Field(default_factory=StageFields)
    Notify_CustomWebhooks: ConfigCollection[Webhook] = collection(Webhook)

    def getTags(self) -> str:
        """生成用户标签列表，返回JSON字符串格式的TagItem列表"""
        tags = []
        tags.append(_tag_proxy(self))
        tags.append(_tag_remained_days(self))
        if not self.Info.IfQuickConfig:
            tags.append(_tag_notes(self))
            return json.dumps(tags, ensure_ascii=False)

        tags.append(
            {
                "text": f"关卡：{STARRAIL_STAGE_BOOK.get(getattr(self.Stage, self.Stage.Channel), '未知关卡')}",
                "color": "blue",
            }
        )
        tags.append(
            {
                "text": f"周本：{STARRAIL_STAGE_BOOK.get(self.Stage.EchoOfWar, '未知关卡')}",
                "color": "blue",
            }
        )
        tags.append(
            {
                "text": f"模拟宇宙：{STARRAIL_STAGE_BOOK.get(self.Stage.SimulatedUniverseWorld, '未知关卡')}",
                "color": "blue",
            }
        )
        tags.append(_tag_notes(self))
        return json.dumps(tags, ensure_ascii=False)

    @virtual_field("Info.Tag")
    def compute_Info_Tag(self):
        try:
            return self.getTags()
        except Exception as exc:
            return str(exc)


class SrcConfig(DomainEntry):
    "SRC配置"

    related_config: ClassVar = {}

    class EmulatorFields(ConfigGroup):
        Id: Annotated[
            UUID | str,
            ref(
                "EmulatorConfig",
                default="-",
                allow_values=("-",),
                display_field="Info.Name",
            ),
        ] = Field(default_factory=lambda: "-", description="模拟器 ID")
        Index: str = Field(default_factory=lambda: "-", description="模拟器索引")

    Emulator: EmulatorFields = Field(default_factory=EmulatorFields)

    class InfoFields(ConfigGroup):
        Name: str = Field(
            default_factory=lambda: "新 SRC 脚本", description="SRC 脚本名称"
        )

        Path: FolderPath = Field(default_factory=lambda: None, description="SRC 路径")

    Info: InfoFields = Field(default_factory=InfoFields)

    class RunFields(ConfigGroup):
        GameUpdateTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 60,
            description="游戏更新时间限制（分钟）",
        )

        HardTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 120,
            description="单账号运行总时限（分钟），包含等待和全部重试",
        )

        IfAutoInstallGameApk: bool = Field(
            default_factory=lambda: False,
            description="版本落后时是否由 MAS 自动下载并安装安装包",
        )

        IfCheckGameUpdate: bool = Field(
            default_factory=lambda: False, description="是否在登录游戏前检查游戏更新"
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

        TaskTransitionMethod: Literal["ExitGame", "ExitEmulator"] = Field(
            default_factory=lambda: "ExitGame", description="任务切换方式"
        )

    Run: RunFields = Field(default_factory=RunFields)
    UserData: ConfigCollection[SrcUserConfig] = collection(SrcUserConfig)


class HSRUserConfig(DomainEntry):
    "HSR用户配置"

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

    class DataFields(ConfigGroup):
        EchoOfWarCompletedThisWeek: bool = Field(
            default_factory=lambda: False, description="本周是否已完成历战余响"
        )

        EchoOfWarLastCompletionDate: Annotated[
            datetime, tz(UTC4), ui(format="date")
        ] = Field(
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=UTC4),
            description="历战余响最近一次完成日期",
        )

        EchoOfWarLastResetWeek: str = Field(
            default_factory=lambda: "2000-W01",
            description='历战余响上次重置 ISO 周（形如 "2025-W23"）',
        )

        LastProxyDate: Annotated[datetime, tz(UTC4), ui(format="date")] = Field(
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=UTC4),
            description="上次代理日期",
        )

        M7ARedeemCodeFingerprint: str = Field(
            description="M7A 兑换码指纹", default_factory=lambda: ""
        )

        ProxyTimes: Annotated[int, Field(ge=0, le=9999)] = Field(
            default_factory=lambda: 0, description="代理次数"
        )

        SRARedeemCodeFingerprint: str = Field(
            default_factory=lambda: "",
            description="兑换码状态指纹（仅状态信息，不保存兑换码明文）",
        )

        WeeklyCompletedThisWeek: bool = Field(
            default_factory=lambda: False,
            description="本周是否已完成周常（仅依据 Data 字段判断）",
        )

        WeeklyLastCompletionDate: Annotated[datetime, tz(UTC4), ui(format="date")] = (
            Field(
                default_factory=lambda: datetime(2000, 1, 1, tzinfo=UTC4),
                description="周常（差分宇宙/货币战争）最近一次完成日期",
            )
        )

        WeeklyLastResetWeek: str = Field(
            default_factory=lambda: "2000-W01",
            description='周常上次重置 ISO 周（形如 "2025-W23"）',
        )

    Data: DataFields = Field(default_factory=DataFields)

    class InfoFields(ConfigGroup):
        Base: Annotated[
            Literal["shared", "independent", "native"],
            legacy(group="Info", name="Mode", convert=normalize_base_source),
        ] = Field(
            default_factory=lambda: "shared",
            description="base 来源（shared/independent/native）：shared = 共用脚本级计划； independent = 本用户自己的计划；native = 原样运行 SRA / 三月七 当前的原生配置",
        )

        Id: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "", description="用户 ID（账号）"
        )
        IfQuickConfig: bool = Field(
            default_factory=lambda: True,
            description="是否启用快速配置（与配置来源独立，按用户保存）",
        )

        IfScriptAfterTask: bool = Field(
            default_factory=lambda: False, description="任务后执行脚本"
        )

        IfScriptBeforeTask: bool = Field(
            default_factory=lambda: False, description="任务前执行脚本"
        )

        Name: WindowsNameString = Field(
            default_factory=lambda: "新用户", description="用户名称"
        )

        Notes: str = Field(default_factory=lambda: "无", description="备注")

        Password: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "", description="密码"
        )
        RemainedDay: Annotated[int, Field(ge=-1, le=9999), none_as(-1)] = Field(
            default_factory=lambda: -1, description="剩余天数"
        )

        ScriptAfterTask: FilePath = Field(
            description="任务后脚本路径", default_factory=lambda: None
        )

        ScriptBeforeTask: FilePath = Field(
            description="任务前脚本路径", default_factory=lambda: None
        )

        Server: Literal["CN-Official"] = Field(
            default_factory=lambda: "CN-Official", description="游戏服务器"
        )

        Status: bool = Field(default_factory=lambda: True, description="是否启用")

        Tag: Virtual[str] = Field(
            default_factory=lambda: None,
            description="用户标签信息（虚拟字段，供前端显示）",
        )

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
        ``related_config["ScriptConfig"]`` 找到持有自己的那份脚本配置；
        ``independent`` / ``native`` 来源，或找不到所属脚本（如未挂到全局配置的
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
        """生成 HSR 用户标签列表，返回JSON字符串格式的TagItem列表。"""
        tags: list[dict] = []
        server = self.Info.Server
        server_label_map = {"CN-Official": "官服"}
        server_label = server_label_map.get(server, server or "未知")
        tags.append({"text": f"服务器：{server_label}", "color": "blue"})
        tags.append(_tag_proxy(self))
        tags.append(_tag_remained_days(self))
        now = datetime.now(tz=UTC4)
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
            description="各用户最近一次确认已登录的时间（user_id → ISO 时间），只读展示用， 由运行结束后的写回与「登录云游戏」接口维护",
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
            default_factory=lambda: "新 HSR 脚本", description="HSR 脚本名称"
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

    class RunFields(ConfigGroup):
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
        AutoUpdateMode: Literal["Off", "AfterRun"] = Field(
            default_factory=lambda: "Off",
            description="外部脚本（M7A / SRA）的自动更新。默认关闭：这两个是用户自己安装、 自带更新器的第三方工具，未经开启就改写它们的目录属于越界；停留在 某个旧版也是真实需求。 只有 AfterRun 一档，没有 BeforeRun：更新的收益本来就落在下一次运行 上，没有理由让当前这轮先等一个 170–750MB 的下载。想立刻更新走配置 页的手动按钮。留成枚举而非布尔，是为了日后要加档时不必做 bool→enum 迁移（MaaFW 正为此背着一个废弃字段）。 选项顺序有意义：OptionsValidator.correct() 回退的是 **options[0]**， 不是这里的默认值，Off 必须排在最前。",
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


class MaaFWUserConfig(DomainEntry):
    "MaaFW 用户配置"

    class DataFields(ConfigGroup):
        IfPassCheck: bool = Field(
            default_factory=lambda: True, description="是否通过检查"
        )

        LastProxyDate: Annotated[datetime, tz(UTC4), ui(format="date")] = Field(
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=UTC4),
            description="上次代理日期",
        )

        LastProxyStatus: str = Field(
            default_factory=lambda: "未知", description="上次运行状态"
        )

        PeriodTaskRecords: JsonDictString = Field(
            default_factory=lambda: "{ }",
            description="MaaFW 周期任务完成记录，结构为 weekly/monthly -> task name -> period key",
        )

        ProxyTimes: Annotated[int, Field(ge=0, le=9999)] = Field(
            default_factory=lambda: 0, description="代理次数"
        )

    Data: DataFields = Field(default_factory=DataFields)

    class DeviceFields(ConfigGroup):
        AdbAddress: str = Field(
            default_factory=lambda: "",
            description="当前用户覆盖 ADB 地址，留空时使用脚本级模拟器配置",
        )

        HWnd: Annotated[int, Field(ge=0, le=999999999999)] = Field(
            default_factory=lambda: 0,
            description="Win32 / Gamepad 窗口句柄，0 表示未指定",
        )

        PlayCoverAddress: str = Field(
            default_factory=lambda: "", description="PlayCover 地址"
        )

        PlayCoverUuid: str = Field(
            default_factory=lambda: "", description="PlayCover UUID"
        )

    Device: DeviceFields = Field(default_factory=DeviceFields)

    class InfoFields(ConfigGroup):
        Account: str = Field(
            default_factory=lambda: "",
            description="账号信息，仅用于 AUTO-MAS 记录，不自动传入 MaaFW 任务",
        )

        Base: Annotated[
            Literal["shared", "independent", "native"],
            legacy(group="Info", name="Mode", convert=normalize_base_source),
        ] = Field(
            default_factory=lambda: "independent",
            description="base 来源（shared=共享/independent=独立/native=原生）",
        )

        Controller: str = Field(
            default_factory=lambda: "",
            description="MaaFW controller 名称，留空时按 interface 和设备配置自动选择",
        )

        IfQuickConfig: bool = Field(
            default_factory=lambda: True,
            description="是否启用快速配置（与配置来源独立，按用户保存）",
        )

        IfScriptAfterTask: bool = Field(
            default_factory=lambda: False, description="是否在任务后执行脚本"
        )

        IfScriptBeforeTask: bool = Field(
            default_factory=lambda: False, description="是否在任务前执行脚本"
        )

        Name: WindowsNameString = Field(
            default_factory=lambda: "新用户", description="用户名称"
        )

        Notes: str = Field(default_factory=lambda: "无", description="备注")

        Password: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="密码信息，仅用于 AUTO-MAS 记录，不自动传入 MaaFW 任务",
        )
        RemainedDay: Annotated[int, Field(ge=-1, le=9999), none_as(-1)] = Field(
            default_factory=lambda: -1, description="剩余天数"
        )

        Resource: str = Field(
            default_factory=lambda: "",
            description="MaaFW resource 名称，留空时选择匹配 controller 的第一个 resource",
        )

        ScriptAfterTask: FilePath = Field(
            default_factory=lambda: None, description="任务后脚本路径"
        )

        ScriptBeforeTask: FilePath = Field(
            default_factory=lambda: None, description="任务前脚本路径"
        )

        Status: bool = Field(default_factory=lambda: True, description="是否启用")

        Tag: Virtual[str] = Field(
            default_factory=lambda: None, description="用户标签信息"
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

    class TaskFields(ConfigGroup):
        SelectedPreset: str = Field(
            default_factory=lambda: "",
            description="当前选中的 interface preset 名称，留空时使用 interface 默认逻辑",
        )

        # 新队列的 keepUnchecked 标记随 JSON 原样保存；无标记的旧 false 实例仍隐藏。
        TaskSnapshot: JsonDictString = Field(
            default_factory=lambda: "{ }",
            description="当前用户的任务快照，结构为 taskOrder/taskChecked/taskOptions/globalOptions， 可选 taskLabels（用户给某一份实例起的显示名，只影响界面显示）； 除 globalOptions 外各键都是任务实例 id，同一个任务可以重复入队（见 MaaFWTaskSnapshot）； globalOptions 是全局选项的值，每个用户一份、所有任务共用。 默认的空快照在建用户、读用户与运行前按项目默认（预设或默认勾选）补成实打实的队列， 见 app/task/MaaFW/tools/embedded/default_snapshot.py",
        )

    Task: TaskFields = Field(default_factory=TaskFields)
    Notify_CustomWebhooks: ConfigCollection[Webhook] = collection(Webhook)

    def getTags(self) -> str:
        """生成 MaaFW 用户标签列表"""
        tags = []
        last_status = self.Data.LastProxyStatus
        tags.append(
            {
                "text": f"上次：{_tag_last_status(last_status)}",
                "color": "red" if last_status == "失败" else "green",
            }
        )
        if not self.Data.IfPassCheck:
            tags.append({"text": "人工排查未通过", "color": "red"})
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


class MaaFWConfig(DomainEntry):
    """MaaFW 项目配置。

    特调通过继承配置分组扩展默认值，并显式声明自身的用户集合类型。
    """

    related_config: ClassVar = {}
    DEFAULT_SCRIPT_NAME: ClassVar = "新 MFW 脚本"
    USER_CONFIG_CLASS: ClassVar = MaaFWUserConfig
    FLAVOR: ClassVar = None
    DEFAULT_TASK_TIME_LIMIT_OVERRIDES: ClassVar = "{ }"

    class DeviceFields(ConfigGroup):
        AdbAddress: str = Field(
            default_factory=lambda: "",
            description="ADB 地址，留空时启动脚本级模拟器获取",
        )

        AdbInputMethods: Annotated[int, Field(ge=-999, le=999999999999)] = Field(
            default_factory=lambda: -1,
            description="ADB 输入方法，默认优先模拟器增强，失败后回退到 MaaTouch / MiniTouch / ADB 同上，仅第二层适用；第一层运行期写死 InputMethods=18446744073709551607",
        )

        AdbPath: FilePath = Field(
            default_factory=lambda: None,
            description="ADB 路径，留空时从 MAS 模拟器配置或 MaaFW Toolkit 推导",
        )

        AdbScreencapMethods: Annotated[int, Field(ge=-999, le=999999999999)] = Field(
            default_factory=lambda: -57,
            description="ADB 截图方法，默认优先模拟器增强，失败后回退到 ADB 截图 仅第二层（MAS 进程内 runner）适用：第一层由外壳自己创建控制器，运行期按 M9A 专项的既验证取值写死（ScreencapMethods=64），本项不参与外部运行， 接线前不要暴露到前端，否则用户改了不会生效也没有提示",
        )

        GamepadType: Annotated[int, Field(ge=0, le=999999999999)] = Field(
            default_factory=lambda: 0,
            description="Gamepad 类型，默认 Xbox360",
        )

        HWnd: Annotated[int, Field(ge=0, le=999999999999)] = Field(
            default_factory=lambda: 0,
            description="Win32 / Gamepad 窗口句柄，0 表示未指定",
        )

        PlayCoverAddress: str = Field(
            default_factory=lambda: "", description="PlayCover 地址"
        )

        PlayCoverUuid: str = Field(
            default_factory=lambda: "", description="PlayCover UUID"
        )

        Win32KeyboardMethod: Annotated[int, Field(ge=0, le=999999999999)] = Field(
            default_factory=lambda: 0,
            description="Win32 键盘方法，0 表示使用 interface 声明或 MaaFW 默认值",
        )

        Win32MouseMethod: Annotated[int, Field(ge=0, le=999999999999)] = Field(
            default_factory=lambda: 0,
            description="Win32 鼠标方法，0 表示使用 interface 声明或 MaaFW 默认值",
        )

        Win32ScreencapMethod: Annotated[int, Field(ge=0, le=999999999999)] = Field(
            default_factory=lambda: 0,
            description="Win32 截图方法，0 表示使用 interface 声明或 MaaFW 默认值",
        )

    Device: DeviceFields = Field(default_factory=DeviceFields)

    class EmbeddedFields(ConfigGroup):
        FollowSource: bool = Field(
            default_factory=lambda: False,
            description="跟随来源目录（开发者模式），默认关。开着时每次运行前比一下来源目录（投影会带走的 文件的路径 + 大小 + 修改时间），变了就重新导入到这个脚本自己的私有渠道（不比版本、 不与同项目其它脚本共用版本），不做项目更新；关掉后回到 Update.Channel 的组。 见 tools/embedded/embedded_project.py「跟随来源目录」一节。",
        )

        ImportedAt: Annotated[
            datetime | None, tz(local_timezone), ui(widget="datetime", format="hms")
        ] = Field(default=None, description="导入时间，仅展示；空值表示尚未导入")

        Report: JsonDictString = Field(
            default_factory=lambda: "{ }",
            description="投影报告（省下多少、外壳家族、排除条数与原因），JSON 字符串",
        )

        SourceVersion: str = Field(
            default_factory=lambda: "",
            description="由 AUTO-MAS 内嵌一份按 interface 白名单投影的副本来运行。副本在 data/mfw/<脚本 uuid 前 12 位>/，由脚本 ID 推出、不进配置、用户不可手改； Info.Path 继续存用户选的来源目录。更新落地时同样只写白名单内的条目。 导入时来源的 interface 版本，仅展示",
        )

    Embedded: EmbeddedFields = Field(default_factory=EmbeddedFields)

    class EmulatorFields(ConfigGroup):
        Id: Annotated[
            UUID | str,
            ref(
                "EmulatorConfig",
                default="-",
                allow_values=("-",),
                display_field="Info.Name",
            ),
        ] = Field(
            default_factory=lambda: "-",
            description="模拟器 ID，ADB controller 留空地址时使用",
        )
        Index: str = Field(default_factory=lambda: "-", description="模拟器索引")

    Emulator: EmulatorFields = Field(default_factory=EmulatorFields)

    class GameFields(ConfigGroup):
        Arguments: CliArgumentString = Field(
            default_factory=lambda: "", description="游戏启动参数"
        )

        Hotkeys: JsonDictString = Field(
            default_factory=lambda: "{}",
            description='脚本级键位（PI v2.8 hotkey 选项）：``{option 名: {字段名: 组合键字符串}}``， 组合键写成「修饰键+…+主键」（如 ``"Ctrl+E"``）。只存与 interface 默认不同的 字段；运行时叠加到每个任务实际生效的 hotkey 选项上，盖过用户快照 / 预设里的值。 仅 Win32 控制器生效（Adb 等其他控制器不叠加）。interface 里已没有的 option / 字段静默忽略，映射不了的值告警后回落到快照 / 默认值（runner/run_plan.py）。',
        )

        LaunchMode: Literal["DirectExe", "AttachOnly"] = Field(
            default_factory=lambda: "DirectExe", description="游戏生命周期模式"
        )

        LaunchPath: FilePath = Field(
            default_factory=lambda: None,
            description="DirectExe 模式下 MAS 启动的游戏 exe",
        )

        PackageName: str = Field(
            default_factory=lambda: "",
            description="安卓游戏包名，Adb controller 用：启动模拟器时顺带把游戏拉起来。 留空表示从项目的 pipeline 里自动识别（见 embedded/game_package.py）； 自动识别是启发式的，填了这里就以这里为准。识别不出且没填则不启动游戏。",
        )

        UnityResolution: Literal["Off", "1920x1080", "1280x720"] = Field(
            default_factory=lambda: "Off",
            description="DirectExe 模式下，启动游戏前按 exe 路径反查 Unity 注册表，临时把分辨率改成所选 尺寸的窗口模式，游戏关闭后恢复原值（tools/embedded/game_resolution.py）。 只对 Unity 引擎的游戏有效；游戏已在运行时不改。Off 表示不碰。",
        )

        WaitTime: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            default_factory=lambda: 120,
            description="游戏启动等待时间（秒）：既是等窗口出现的上限，也是窗口出现后等画面稳定的上限。 Unity 游戏窗口出现时还在黑屏加载，登录界面往往要二三十秒后才渲染出来； MaaEnd 的 SceneManager 见连续画面不变十几秒就判「环境识别异常」直接失败。 等画面时 worker 每秒截一帧，有内容且连续几秒不变就提前下发，等不到才等满； MaaFW 初始化（加载资源、连 controller、起 agent）与之重叠而不是干等。 只对本轮由 MAS 拉起的游戏生效，AttachOnly 与「游戏已在运行」不等画面。",
        )

    Game: GameFields = Field(default_factory=GameFields)

    class InfoFields(ConfigGroup):
        Controller: str = Field(
            default_factory=lambda: "",
            description="MaaFW controller 名称，留空时按 interface 和设备配置自动选择",
        )

        Name: str = Field(
            default_factory=lambda: "新 MFW 脚本", description="MaaFW 脚本名称"
        )

        # 导入完成后来源可删除；完整保留版本号目录名，不能去后缀或清空。
        Path: Annotated[
            NativePath | None,
            path_policy(kind="folder", blocked_dirs=STANDARD_BLOCKED_DIRS),
        ] = Field(
            default_factory=lambda: None,
            description="MaaFW 项目的导入来源目录，应包含 interface.json；导入后可删，删了也原样保留",
        )

        ProjectLabel: str = Field(
            default_factory=lambda: "",
            description="项目标签，可用于区分同一 ProjectInterface 的不同实例",
        )

        Resource: str = Field(
            default_factory=lambda: "",
            description="MaaFW resource 名称，留空时选择匹配 controller 的第一个 resource",
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class RunFields(ConfigGroup):
        DailyOnceTasks: JsonListString = Field(
            default_factory=lambda: "[ ]",
            description="每天正常完成一次后，当天剩余时间跳过的 MaaFW 任务名列表",
        )

        GameUpdateMode: Literal["Off", "Check", "AutoInstall"] = Field(
            default_factory=lambda: "Off",
            description="游戏客户端更新：Off 不检查 / Check 只检查，落后时本次判失败并提示手动更新 / AutoInstall 落后时自动下载安装包并 adb 安装（保留游戏数据）。只在特调实现了 游戏更新钩子（当前只有 M9A）且 controller 是 ADB 时生效，通用 MaaFW 不读。 Off 必须排第一：OptionsValidator 纠错回退的是 options[0]。",
        )

        LoopGuard: bool = Field(
            default_factory=lambda: False,
            description="原地打转检测（实验性，默认关）。任务在短周期里反复执行同一串节点（周期 ≤ 8 步、每轮都有点击 / 滑动等物理动作）、识别结果又几乎不变时判定卡死：≥ 200 轮且持续 ≥ 10 分钟就停掉这个任务，收尾与单任务超时同一口径（截图、第一个任务或关键任务 结束本轮，其余记失败后继续）。判据见 tools/core/runner/loop_guard.py。",
        )

        MonthlyOnceTasks: JsonListString = Field(
            default_factory=lambda: "[ ]",
            description="每月正常完成一次后，本月剩余时间跳过的 MaaFW 任务名列表",
        )

        ProxyTimesLimit: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            default_factory=lambda: 0,
            description="运行引擎，决定「谁来跑」： 代理次数限制",
        )

        RunTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 120,
            description="单次运行时间限制（分钟），套在单个用户的整次运行上。截止时刻随 job 文件交给 worker：到点它自己停掉当前任务、截一张超时图、带回已完成的任务；宿主只在 worker 没能及时停下时才强杀（那时既没有截图也没有进度）。MaaFW 项目一轮日常 动辄几十分钟，30 分钟默认值实测常被误伤，放宽到 120。",
        )

        RunTimesLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 3,
            description="运行次数限制。重试不关游戏、不再等启动，从当前画面接着跑； 脚本自己的加载超时（MaaEnd 回大世界 20s）一次抖动就把整轮判失败， 只给一次机会时用户看到的就是「从来没成功过」，默认与其他专项一样 3 次。",
        )

        TaskTimeLimit: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            default_factory=lambda: 45,
            description="单个任务的时限（分钟），0 表示不限。某个任务卡住时到点只停它、截一张超时图， 记一条任务失败后接着跑后面的任务（计划里第一个任务超时则结束本轮）；不再让 一个卡住的任务吃掉整轮 RunTimeLimit 的时间。 默认 45 而不是 30：M9A 智能均衡刷材料正常 1–22 分钟，自动深眠在新内容日 实测 33.7 分钟，30 会误伤正常运行。",
        )

        TaskTimeLimitOverrides: JsonDictString = Field(
            default_factory=lambda: "{ }",
            description="按任务名覆盖的单任务时限（分钟），键是 MaaFW 任务名；值 0 表示该任务不限。 默认值由类属性 DEFAULT_TASK_TIME_LIMIT_OVERRIDES 决定（特调可内置几条）； 只在配置里没有这个键时生效，用户存过的值（含清空成 {}）原样保留。",
        )

        WeeklyOnceTasks: JsonListString = Field(
            default_factory=lambda: "[ ]",
            description="每周正常完成一次后，本周剩余时间跳过的 MaaFW 任务名列表",
        )

    Run: RunFields = Field(default_factory=RunFields)

    class SelectionFields(ConfigGroup):
        Controller: JsonListString = Field(
            default_factory=lambda: "[ ]",
            description="当前阶段保留：manager.py 仍从 Selection.* 读取运行范围， 字段迁移到 Info.* / 用户任务配置属于后续 P3 前端回收。 选中的 controller 列表",
        )

        Resource: JsonListString = Field(
            default_factory=lambda: "[ ]", description="选中的 resource 列表"
        )

        Tasks: JsonListString = Field(
            default_factory=lambda: "[ ]", description="选中的 task 列表"
        )

    Selection: SelectionFields = Field(default_factory=SelectionFields)

    class TaskFields(ConfigGroup):
        Templates: JsonListString = Field(
            default_factory=lambda: "[ ]",
            description='用户页任务队列的自定义模板，同一脚本的用户共用。JSON 列表，每项 ``{"name": 模板名, "snapshot": {taskOrder, taskChecked, taskOptions, taskLabels?}}``， 快照形状同用户的 Task.TaskSnapshot（键是任务实例 id），但不含受管任务、密码字段 与全局选项（globalOptions 归各用户自己）； 名称在脚本内唯一。运行流程不读它，只由用户页套用到某个用户的队列。',
        )

    Task: TaskFields = Field(default_factory=TaskFields)

    class UpdateFields(ConfigGroup):
        AutoUpdateMode: Annotated[
            Literal["Off", "BeforeRun", "AfterRun"],
            legacy(
                group="Update",
                name="IfAutoUpdate",
                convert=lambda value: "Off" if value is False else "BeforeRun",
            ),
        ] = Field(
            default_factory=lambda: "BeforeRun",
            description="项目自动更新时机：Off 不更新 / BeforeRun 运行前 / AfterRun 全部用户跑完后。 由 embedded_manager 在用户任务之外执行，耗时不计入 Run.RunTimeLimit。",
        )

        Channel: Literal["stable", "beta"] = Field(
            default_factory=lambda: "stable",
            description="更新渠道只有稳定版与测试版，默认稳定版，要测试版由用户手动切。 不给「跟随全局」：全局那个 Update.Channel 是 MAS 自身的发布通道， 和脚本本体的版本档位是两回事，串在一起只会让人猜。 Mirror 酱还支持 channel=alpha，**故意不开放**——那是项目方的内部 验证档，稳定性无保证，而这里更新的是用户日常在跑的脚本本体。 这两个值必须与前端 updateChannelOptions 和 schema 的 Literal 一致： 三处任一多给一档，用户选了就会 422 或被静默纠回默认值。 旧配置里的空串现在是非法值，会被 correct() 回退成 options[0]， 即 stable——这里的顺序同样不能随意调换。",
        )

        GitHubAssetPattern: str = Field(
            description="[已废弃] GitHub release asset 文件名匹配模式",
            default_factory=lambda: "",
        )

        GitHubRepo: str = Field(
            default_factory=lambda: "",
            description="[已废弃] GitHub 仓库/tag/asset 覆盖：仓库与资产名改为从 interface.json 和目录名自动推导，运行流程不再读取；保留一个版本兼容旧配置文件后删除。",
        )

        GitHubTag: str = Field(
            description="[已废弃] GitHub release tag 覆盖", default_factory=lambda: ""
        )

        IfAutoUpdate: bool = Field(
            default_factory=lambda: True,
            description="[已废弃] 旧布尔开关，只在 load() 里迁移为 AutoUpdateMode（False → Off）， 运行流程不再读取；保留一个版本兼容旧配置文件后删除。",
        )

        MirrorChyanCDK: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="Mirror 酱 CDK，由用户自己填。**不做全局兜底**：全局那个服务的是 AUTO-MAS 自身的更新，和脚本本体不是一回事，串在一起只会让人猜 自己在用哪个。选 Mirror 酱作为下载源时这一项必填。 （合并逻辑见 tools/embedded/update_credentials.py）",
        )
        ProxyAddress: str = Field(
            default_factory=lambda: "",
            description="脚本级网络代理，给这个项目的更新包下载与运行环境安装（uv / pip、 binding 源码兜底）用。与 CDK / 渠道不同，这一项**留空就跟随全局** `Update.ProxyAddress`（设置 → 其他 → 网络代理），填了就只走自己的： 代理解决的是「这台机器连不连得上」，多数人全局一份就够，个别项目 的源在别的网络才需要单独指。格式同全局项，`host:port` 不带协议时 补 `http://`（合并逻辑见 tools/embedded/update_credentials.py）。",
        )

        Source: Literal["GitHub", "MirrorChyan"] = Field(
            default_factory=lambda: "GitHub",
            description="更新包的下载源，由用户显式选择——**不做自动分流**。 版本检查始终走 Mirror 酱（无 CDK 也能查），但下载去哪由这一项决定： 选 Mirror 酱就必须自己填 CDK，CDK 不可用时明确报错，不悄悄换成 GitHub——用户得知道自己在从哪下载，出问题才查得动。 默认 GitHub：零配置即可用，与全局 Update.Source 的默认值一致。 选项顺序有意义：OptionsValidator.correct() 回退的是 **options[0]**， 不是这里的默认值。旧配置里 Source 是空串（旧默认），加载时会被 correct 成第一项并写回磁盘——GitHub 必须排在前面，否则所有既有 脚本会被静默改成 Mirror 酱，而它们并没有 CDK，每次运行都更新失败。",
        )

    Update: UpdateFields = Field(default_factory=UpdateFields)
    UserData: ConfigCollection[MaaFWUserConfig] = collection(MaaFWUserConfig)


class M9AUserConfig(MaaFWUserConfig):
    """M9A 用户配置：与 MaaFW 用户配置同形。

    ``Info.Account`` 在这里不只是备注：脚本资源为官服且账号非空时，运行前会自动插入
    「切换账号」任务（见 ``app/task/M9A/flavor.py``）。
    """


class M9AConfig(MaaFWConfig):
    """M9A 脚本配置：MaaFW 的特调类型。

    字段集与 MaaFW 完全一致，运行、更新、内嵌副本全部走 MaaFW 引擎；差别只有类型身份
    （键 / 图标 / 创建卡）、默认脚本名、内置的按任务单任务时限，以及运行前的队列装饰
    （启动 / 关闭游戏首尾、``Info.Account`` 绑定切号）。旧版 M9A 专项的配置形状在启动时由
    ``app/task/M9A/migration.py`` 一次性迁到这个形状。
    """

    DEFAULT_SCRIPT_NAME: ClassVar = "新 M9A 脚本"
    USER_CONFIG_CLASS: ClassVar = M9AUserConfig
    FLAVOR: ClassVar = "app.task.M9A.flavor:FLAVOR"
    DEFAULT_TASK_TIME_LIMIT_OVERRIDES: ClassVar = (
        '{"智能均衡刷材料": 45, "自动深眠": 60, "自动醒梦": 60}'
    )

    class InfoFields(MaaFWConfig.InfoFields):
        Name: str = Field(
            default_factory=lambda: "新 M9A 脚本", description="MaaFW 脚本名称"
        )

    # 独立配置类型有意覆盖分组及集合，保留专项默认值与准确字段类型。
    Info: InfoFields = Field(  # pyright: ignore[reportIncompatibleVariableOverride]
        default_factory=InfoFields
    )

    class RunFields(MaaFWConfig.RunFields):
        TaskTimeLimitOverrides: JsonDictString = Field(
            default_factory=lambda: (
                '{"智能均衡刷材料": 45, "自动深眠": 60, "自动醒梦": 60}'
            ),
            description="按任务名覆盖的单任务时限（分钟），键是 MaaFW 任务名；值 0 表示该任务不限。 默认值由类属性 DEFAULT_TASK_TIME_LIMIT_OVERRIDES 决定（特调可内置几条）； 只在配置里没有这个键时生效，用户存过的值（含清空成 {}）原样保留。",
        )

    Run: RunFields = Field(  # pyright: ignore[reportIncompatibleVariableOverride]
        default_factory=RunFields
    )
    UserData: ConfigCollection[M9AUserConfig] = collection(  # pyright: ignore[reportIncompatibleVariableOverride]
        M9AUserConfig
    )

    class GameFields(MaaFWConfig.GameFields):
        WaitTime: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            default=15, description="启动等待时间(秒)"
        )

    # 独立特调类型有意覆盖分组默认值，保留准确字段提示。
    Game: GameFields = Field(default_factory=GameFields)  # pyright: ignore[reportIncompatibleVariableOverride]


class MSSUserConfig(MaaFWUserConfig):
    """MSS（MaaStellaSora / 星塔旅人）用户配置：MaaFW 用户配置再加一项计划表引用。

    ``Info.PlanMode`` 是比 MaaFW 多出的唯一字段：``Fixed`` 表示悬赏试炼按任务队列里
    用户自己配的选项跑；填了 MSS 计划表的 UID，运行前由特调钩子按当天槽位改写悬赏试炼的
    关卡、难度与次数（见 ``app/task/MSS/flavor.py``）。
    """

    related_config: ClassVar = {}

    class DataFields(MaaFWUserConfig.DataFields):
        PersonalMssDefense: Annotated[
            JsonDictString, ui(visibility=UiVisibility.HIDE)
        ] = Field(
            default_factory=lambda: "{ }",
            description='个人版「灾变防线」的编排记录，形如 {"armed": 期, "done": 期}。 armed 是上次把它编进队列的那一期，done 是已经确认打完的那一期： 用「上次运行是否成功」把 armed 升成 done，所以跑失败的那期下次还会重试。 期取活动公告的开始时刻（见 app/tools/stella_official.py），跨月也认得出是同一期。',
        )

    # 独立配置类型有意扩展分组，保留专项字段及其校验声明。
    Data: DataFields = Field(  # pyright: ignore[reportIncompatibleVariableOverride]
        default_factory=DataFields
    )

    class InfoFields(MaaFWUserConfig.InfoFields):
        IfActivityFirst: bool = Field(
            default_factory=lambda: True,
            description="活动优先：队列里没加「活动快速战斗」时，确认在活动期也自动加入，排在悬赏试炼之前",
        )

        PlanMode: Annotated[
            UUID | str,
            ref(
                "PlanConfig",
                default="Fixed",
                allow_values=("Fixed",),
                entry_types=(MSSPlanConfig,),
                display_field="Info.Name",
            ),
        ] = Field(
            default_factory=lambda: "Fixed",
            description="悬赏试炼关卡来源：Fixed 用任务队列里配的，选了计划表就按当天槽位改",
        )

    Info: InfoFields = Field(  # pyright: ignore[reportIncompatibleVariableOverride]
        default_factory=InfoFields
    )


class MSSConfig(MaaFWConfig):
    """MSS 脚本配置：MaaFW 的特调类型。

    字段集与 MaaFW 完全一致，运行、更新、内嵌副本全部走 MaaFW 引擎；差别只有类型身份
    （键 / 图标 / 创建卡）、默认脚本名、用户上的计划表引用，以及运行前的队列装饰
    （活动期先打活动、按计划表改悬赏试炼、新版爬塔放最后）。
    """

    DEFAULT_SCRIPT_NAME: ClassVar = "新 MSS 脚本"
    USER_CONFIG_CLASS: ClassVar = MSSUserConfig
    FLAVOR: ClassVar = "app.task.MSS.flavor:FLAVOR"

    class InfoFields(MaaFWConfig.InfoFields):
        Name: str = Field(
            default_factory=lambda: "新 MSS 脚本", description="MaaFW 脚本名称"
        )

    # 独立配置类型有意覆盖分组及集合，保留专项默认值与准确字段类型。
    Info: InfoFields = Field(  # pyright: ignore[reportIncompatibleVariableOverride]
        default_factory=InfoFields
    )
    UserData: ConfigCollection[MSSUserConfig] = collection(  # pyright: ignore[reportIncompatibleVariableOverride]
        MSSUserConfig
    )


class GeneralUserConfig(DomainEntry):
    "通用脚本用户配置"

    class DataFields(ConfigGroup):
        LastProxyDate: Annotated[datetime, tz(UTC4), ui(format="date")] = Field(
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=UTC4),
            description="上次代理日期",
        )

        ProxyTimes: Annotated[int, Field(ge=0, le=9999)] = Field(
            default_factory=lambda: 0, description="代理次数"
        )

    Data: DataFields = Field(default_factory=DataFields)

    class InfoFields(ConfigGroup):
        Base: Annotated[
            Literal["shared", "independent", "native"],
            legacy(group="Info", name="Mode", convert=normalize_base_source),
        ] = Field(
            default_factory=lambda: "independent",
            description="base 来源（shared=共享/independent=独立/native=原生）",
        )

        IfScriptAfterTask: bool = Field(
            default_factory=lambda: False, description="是否在任务后执行脚本"
        )

        IfScriptBeforeTask: bool = Field(
            default_factory=lambda: False, description="是否在任务前执行脚本"
        )

        IfUseMasConfig: bool = Field(
            default_factory=lambda: True, description="兼容旧版用户独立脚本配置"
        )

        Name: WindowsNameString = Field(
            default_factory=lambda: "新用户", description="用户名称"
        )

        Notes: str = Field(default_factory=lambda: "无", description="备注")

        RemainedDay: Annotated[int, Field(ge=-1, le=9999), none_as(-1)] = Field(
            default_factory=lambda: -1, description="剩余天数"
        )

        ScriptAfterTask: FilePath = Field(
            default_factory=lambda: None, description="任务后脚本路径"
        )

        ScriptBeforeTask: FilePath = Field(
            default_factory=lambda: None, description="任务前脚本路径"
        )

        Status: bool = Field(default_factory=lambda: True, description="是否启用")

        Tag: Virtual[str] = Field(
            default_factory=lambda: None, description="用户标签信息"
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
        """生成通用用户标签列表"""
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
    "OK-WW 用户配置（ok-script 线）"

    OKWW_TASK_BOOK: ClassVar = {1: "日常"}

    class DataFields(ConfigGroup):
        LastProxyDate: Annotated[datetime, tz(UTC4), ui(format="date")] = Field(
            description="上次代理日期",
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=UTC4),
        )

        LastProxyStatus: Literal["未知", "成功", "失败", "维护中"] = Field(
            description="上次代理状态（未知/成功/失败）", default_factory=lambda: "未知"
        )

        LastTaskIndex: Annotated[int, Field(ge=0, le=9999)] = Field(
            description="上次运行的 ok-ww 任务序号（-t N）",
            default_factory=lambda: 0,
        )

        ProxyTimes: Annotated[int, Field(ge=0, le=9999)] = Field(
            description="代理次数", default_factory=lambda: 0
        )

    Data: DataFields = Field(default_factory=DataFields)

    class InfoFields(ConfigGroup):
        Base: Annotated[
            Literal["shared", "independent", "native"],
            legacy(group="Info", name="Mode", convert=normalize_base_source),
        ] = Field(
            description="base 来源（shared=共享、independent=独立、native=脚本原生配置）",
            default_factory=lambda: "shared",
        )

        Id: str = Field(description="账号", default_factory=lambda: "")

        IfQuickConfig: bool = Field(
            default_factory=lambda: True,
            description="是否启用 MAS 快速配置覆盖高频任务字段",
        )

        IfScriptAfterTask: bool = Field(
            description="是否在任务后执行脚本", default_factory=lambda: False
        )

        IfScriptBeforeTask: bool = Field(
            description="是否在任务前执行脚本", default_factory=lambda: False
        )

        Name: WindowsNameString = Field(
            description="用户名", default_factory=lambda: "新用户"
        )

        Notes: str = Field(description="备注", default_factory=lambda: "无")

        RemainedDay: Annotated[int, Field(ge=-1, le=9999), none_as(-1)] = Field(
            description="剩余天数", default_factory=lambda: -1
        )

        Resource: Literal["官服", "国际服"] = Field(
            description="游戏资源", default_factory=lambda: "官服"
        )

        ScriptAfterTask: FilePath = Field(
            description="任务后脚本路径", default_factory=lambda: None
        )

        ScriptBeforeTask: FilePath = Field(
            description="任务前脚本路径", default_factory=lambda: None
        )

        Status: bool = Field(description="用户状态", default_factory=lambda: True)

        Tag: Virtual[str] = Field(
            description="用户标签列表（JSON字符串，TagItem的dict列表）",
            default_factory=lambda: None,
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class NotifyFields(ConfigGroup):
        Enabled: bool = Field(
            default_factory=lambda: False, description="是否启用用户通知"
        )

        IfSendMail: bool = Field(
            default_factory=lambda: False, description="是否发送邮件"
        )

        IfSendStatistic: bool = Field(
            default_factory=lambda: False, description="是否发送用户统计信息"
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

        ToAddress: str = Field(default_factory=lambda: "", description="用户收件地址")

    Notify: NotifyFields = Field(default_factory=NotifyFields)

    class TaskFields(ConfigGroup):
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

        MaterialSelection: Literal["Resonator EXP", "Weapon EXP", "Shell Credit"] = (
            Field(default_factory=lambda: "Shell Credit", description="模拟领域材料")
        )

        WhichForgeryChallengeToFarm: Annotated[int, Field(ge=1, le=99), none_as(1)] = (
            Field(default_factory=lambda: 1, description="凝素领域序号")
        )

        WhichTacetSuppressionToFarm: Annotated[int, Field(ge=1, le=99), none_as(1)] = (
            Field(default_factory=lambda: 1, description="无音区序号")
        )

        WhichToFarm: Literal[
            "Tacet Suppression", "Forgery Challenge", "Simulation Challenge"
        ] = Field(
            default_factory=lambda: "Tacet Suppression",
            description="MAS 仅接管 DailyTask 及 DailyTask 高频设置；账号切换由 MAS 侧 account_switch 实现，不再暴露上游 MultiAccountDailyTask。 每日任务体力用途",
        )

    Task: TaskFields = Field(default_factory=TaskFields)
    Notify_CustomWebhooks: ConfigCollection[Webhook] = collection(Webhook)

    def getTags(self) -> str:
        tags = []
        last_status = self.Data.LastProxyStatus
        tags.append(
            {"text": f"上次：{_tag_last_status(last_status)}", "color": "green"}
        )
        last_task_index = int(self.Data.LastTaskIndex or 0)
        task_label = self.OKWW_TASK_BOOK.get(last_task_index, "未知")
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
    "OK-NTE 用户配置（ok-script 线）"

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

    class DataFields(ConfigGroup):
        LastProxyDate: Annotated[datetime, tz(UTC4), ui(format="date")] = Field(
            description="上次代理日期",
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=UTC4),
        )

        LastProxyStatus: Literal["未知", "成功", "失败", "维护中"] = Field(
            description="上次代理状态（未知/成功/失败）", default_factory=lambda: "未知"
        )

        LastTaskIndex: Annotated[int, Field(ge=0, le=9999)] = Field(
            description="上次运行的 ok-nte 任务序号（-t N）",
            default_factory=lambda: 0,
        )

        ProxyTimes: Annotated[int, Field(ge=0, le=9999)] = Field(
            description="代理次数", default_factory=lambda: 0
        )

    Data: DataFields = Field(default_factory=DataFields)

    class InfoFields(ConfigGroup):
        Base: Annotated[
            Literal["shared", "independent", "native"],
            legacy(group="Info", name="Mode", convert=normalize_base_source),
        ] = Field(
            description="base 来源（shared=共享、independent=独立、native=脚本原生配置）",
            default_factory=lambda: "shared",
        )

        Id: str = Field(description="账号", default_factory=lambda: "")

        IfQuickConfig: bool = Field(
            description="是否启用快速配置（与配置来源独立）",
            default_factory=lambda: True,
        )

        IfScriptAfterTask: bool = Field(
            description="是否在任务后执行脚本", default_factory=lambda: False
        )

        IfScriptBeforeTask: bool = Field(
            description="是否在任务前执行脚本", default_factory=lambda: False
        )

        Name: WindowsNameString = Field(
            description="用户名", default_factory=lambda: "新用户"
        )

        Notes: str = Field(description="备注", default_factory=lambda: "无")

        Password: Annotated[str, encrypted()] = Field(
            description="密码", default_factory=lambda: ""
        )
        RemainedDay: Annotated[int, Field(ge=-1, le=9999), none_as(-1)] = Field(
            description="剩余天数", default_factory=lambda: -1
        )

        Resource: Literal["官服"] = Field(
            description="游戏资源", default_factory=lambda: "官服"
        )

        ScriptAfterTask: FilePath = Field(
            description="任务后脚本路径", default_factory=lambda: None
        )

        ScriptBeforeTask: FilePath = Field(
            description="任务前脚本路径", default_factory=lambda: None
        )

        Status: bool = Field(description="用户状态", default_factory=lambda: True)

        Tag: Virtual[str] = Field(
            description="用户标签列表（JSON字符串，TagItem的dict列表）",
            default_factory=lambda: None,
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
            {"text": f"上次：{_tag_last_status(last_status)}", "color": "green"}
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


class BetterGIUserConfig(DomainEntry):
    "BetterGI 用户配置（更好的原神）"

    class DataFields(ConfigGroup):
        LastProxyDate: Annotated[datetime, tz(UTC4), ui(format="date")] = Field(
            description="上次代理日期",
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=UTC4),
        )

        LastProxyStatus: Literal["未知", "成功", "失败", "维护中"] = Field(
            description="上次代理状态（未知/成功/失败）", default_factory=lambda: "未知"
        )

        ProxyTimes: Annotated[int, Field(ge=0, le=9999)] = Field(
            description="代理次数", default_factory=lambda: 0
        )

    Data: DataFields = Field(default_factory=DataFields)

    class InfoFields(ConfigGroup):
        Base: Annotated[
            Literal["shared", "independent", "native"],
            legacy(group="Info", name="Mode", convert=normalize_base_source),
        ] = Field(
            default_factory=lambda: "independent",
            description="base 来源（shared=共享/independent=独立/native=原生）",
        )

        Id: str = Field(description="账号", default_factory=lambda: "")

        IfQuickConfig: bool = Field(
            default_factory=lambda: True,
            description="是否启用快速配置（与配置来源独立，按用户保存）",
        )

        IfScriptAfterTask: bool = Field(
            description="是否在任务后执行脚本", default_factory=lambda: False
        )

        IfScriptBeforeTask: bool = Field(
            description="是否在任务前执行脚本", default_factory=lambda: False
        )

        IfUseMasConfig: bool = Field(
            default_factory=lambda: True, description="兼容旧版用户独立一条龙配置"
        )

        Name: WindowsNameString = Field(
            description="用户名", default_factory=lambda: "新用户"
        )

        Notes: str = Field(description="备注", default_factory=lambda: "无")

        Password: Annotated[str, encrypted()] = Field(
            description="密码", default_factory=lambda: ""
        )
        RemainedDay: Annotated[int, Field(ge=-1, le=9999), none_as(-1)] = Field(
            description="剩余天数", default_factory=lambda: -1
        )

        ScriptAfterTask: FilePath = Field(
            description="任务后脚本路径", default_factory=lambda: None
        )

        ScriptBeforeTask: FilePath = Field(
            description="任务前脚本路径", default_factory=lambda: None
        )

        Status: bool = Field(description="用户状态", default_factory=lambda: True)

        Tag: Virtual[str] = Field(
            description="用户标签列表（JSON字符串，TagItem的dict列表）",
            default_factory=lambda: None,
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class NotifyFields(ConfigGroup):
        Enabled: bool = Field(
            default_factory=lambda: False, description="是否启用用户通知"
        )

        IfSendDropStatistics: bool = Field(
            default_factory=lambda: True,
            description="是否统计掉落（BGI「奖励识别」）：默认开启；开启后运行前强制打开奖励识别， 并把日志里的逐轮识别结果汇总进统计通知",
        )

        IfSendMail: bool = Field(
            default_factory=lambda: False, description="是否发送邮件"
        )

        IfSendStatistic: bool = Field(
            default_factory=lambda: False, description="是否发送用户统计信息"
        )

        IfServerChan: bool = Field(
            default_factory=lambda: False, description="是否启用 Server 酱"
        )

        PushLogMode: Literal["关闭", "逐条", "汇总"] = Field(
            default_factory=lambda: "汇总",
            description="任务报告节点详情的推送模式（一条龙/执行层分步表）： 关闭 = 不注入；逐条 = 逐条带回时间戳；汇总 = 按状态聚合",
        )

        ServerChanKey: str = Field(
            default_factory=lambda: "", description="Server 酱密钥"
        )

        ToAddress: str = Field(default_factory=lambda: "", description="用户收件地址")

    Notify: NotifyFields = Field(default_factory=NotifyFields)

    class OneDragonFields(ConfigGroup):
        AutoBossStrategyName: str = Field(
            default_factory=lambda: "",
            description="战斗策略（对应 BetterGI 一条龙的 AutoBossStrategyName，留空不覆盖） 默认「根据队伍自动选择」为 BetterGI 内置策略名",
        )

        CustomGroups: JsonListString = Field(
            default_factory=lambda: "[]",
            description='自定义配置组列表：JSON 数组字符串，元素为 {"name": str, "enabled": bool}',
        )

        DailyRewardPartyName: str = Field(
            default_factory=lambda: "",
            description="领取奖励队伍（对应 BetterGI 一条龙的 DailyRewardPartyName，留空不覆盖）",
        )

        Groups: list[str] = Field(
            default_factory=lambda: [
                "领取邮件",
                "合成树脂",
                "自动幽境危战",
                "自动地脉花",
                "自动首领讨伐",
                "自动秘境",
                "领取尘歌壶奖励",
                "领取每日奖励",
            ],
            description="一条龙要执行的内置配置组（按组名，默认全部 8 组开启）",
        )

        IfUseCustomGroups: bool = Field(
            default_factory=lambda: False,
            description="是否管理自定义配置组（总开关；OFF 时沿 BetterGI 原生设置，自定义组原样保留）",
        )

        IfUseTeams: bool = Field(
            default_factory=lambda: False,
            description="「队伍配置」总开关（胶囊开关）：ON 时表格内队伍参与运行时「战斗场景」选队； OFF 时数据保留但不参与匹配（通用队伍 PartyName/AutoBossStrategyName 照旧生效）。",
        )

        PartyName: str = Field(
            default_factory=lambda: "",
            description="战斗队伍（对应 BetterGI 一条龙的通用 PartyName，留空不覆盖）",
        )

        Plan: str = Field(
            default_factory=lambda: "",
            description="一条龙执行计划（Plan）JSON 字符串：{version, steps:[{uid,kind,name,enabled,settings}]}。 战斗 4 项（自动秘境/自动地脉花/自动幽境危战/自动首领讨伐）直连执行层时由本字段 承载其 per-任务参数；右栏对应设置仅写入本字段（不落原生一条龙配置）。",
        )

        Queue: JsonListString = Field(
            default_factory=lambda: "[]",
            description='一条龙队列（可视化编排）：JSON 数组字符串，按执行顺序存储，元素为 {"kind": str, "name": str}（kind ∈ builtin/js/pathing/scriptgroup/custom， 内置组名命中时后端强制 builtin）。仅表达顺序与成员（含同名重复实例）， 行启停仍由 Groups / CustomGroups 承载；为空或非法时回退旧行为 （按副本 TaskOrder 相对顺序，不重排）。',
        )

        Teams: JsonListString = Field(
            default_factory=lambda: "[]",
            description='队伍配置表：JSON 数组字符串，数组顺序即界面展示顺序（可拖拽重排），元素为 {"name": str,            # 队伍名称（游戏内队伍名） "strategy": str,        # 战斗策略名（留空 = 跟随通用策略 AutoBossStrategyName） "scenes": {             # 战斗场景（可跨标签页任意叠加，空则本行不参与匹配） "domain": [{"region": str, "domain": str, "reward": str}],   # 秘境：地区/秘境名/奖励档 "leyline": [{"country": str, "type": str}],                  # 地脉花：地区/地脉类型 "boss": [{"region": str, "boss": str}]},                     # 首领讨伐：地区/首领名 "note": str,            # 备注 "enabled": bool}        # 启用状态 序号 0 的「通用队伍」不落本字段（直绑 PartyName / AutoBossStrategyName）。 运行期由 team_resolver 按 L1 精确匹配 + 随机选取，写入 Plan 步骤的 masTeamOverride / masStrategyOverride（最高优先级，压过每周行与步骤级字段）。',
        )

        UseExecutionLayer: bool = Field(
            default_factory=lambda: True,
            description="是否启用「直连执行层」：战斗 4 项由 MAS 自编排 Plan 驱动（按需求恒开，预留开关）。",
        )

    OneDragon: OneDragonFields = Field(default_factory=OneDragonFields)

    class SwitchFields(ConfigGroup):
        GamePath: FilePath = Field(
            default_factory=lambda: None,
            description="游戏客户端路径（用户级覆盖，可空）：官服/B服/国际服是三个互相隔离的客户端， B站账号只能登录B服客户端。留空 = 跟随 BetterGI 全局配置的游戏路径；填写后该 用户运行时由 MAS 按此路径临时拉起游戏（不修改 BetterGI 配置），实现同脚本 混服用户各用各的客户端",
        )

        Resource: Literal["官服", "B服", "亚服", "欧服", "美服", "港澳台服"] = Field(
            default_factory=lambda: "官服",
            description="切换账号配置（BetterGI「切换账号多模式」脚本专项适配） 账号/密码复用 Info.Id / Info.Password（密码经 EncryptValidator 加密） 切换模式不再由用户配置，运行时按密码是否填写推断： 填密码 → 「账号+密码+OCR」，未填 → 「下拉列表」；B服 强制「B服切换另一个账号匹配+键鼠」。 游戏服务器（账号所在服务器：官服/B服/国际服各服务器）",
        )

        Uid: str = Field(
            default_factory=lambda: "",
            description="账号 UID（可不填，切换前识别一致将不执行切换动作；仅 BetterGI 脚本方式生效）",
        )

    Switch: SwitchFields = Field(default_factory=SwitchFields)

    class TaskFields(ConfigGroup):
        OneDragonConfigName: str = Field(
            default_factory=lambda: "",
            description="BetterGI「一条龙」配置名，对应脚本一条龙页面中已保存的配置名称",
        )

    Task: TaskFields = Field(default_factory=TaskFields)
    Notify_CustomWebhooks: ConfigCollection[Webhook] = collection(Webhook)

    def getTags(self) -> str:
        tags = []
        last_status = self.Data.LastProxyStatus
        tags.append(
            {"text": f"上次：{_tag_last_status(last_status)}", "color": "green"}
        )
        if self.Info.IfQuickConfig:
            config_name = "MAS独立配置"
        else:
            config_name = self.Task.OneDragonConfigName or "未设置"
        tags.append({"text": f"一条龙：{config_name}", "color": "orange"})
        tags.append(_tag_remained_days(self))
        tags.append(_tag_notes(self))
        return json.dumps(tags, ensure_ascii=False)

    @classmethod
    def normalize_payload(cls, data):
        data = deepcopy(data)
        normalized_data = deepcopy(data) if isinstance(data, dict) else {}
        switch = normalized_data.get("Switch")
        if isinstance(switch, dict) and "Resource" not in switch:
            if switch.get("Modes") == "B服切换另一个账号匹配+键鼠":
                switch["Resource"] = "B服"
            elif switch.get("GlobalAccount"):
                server = switch.get("Servers")
                switch["Resource"] = (
                    _BGI_LEGACY_SERVERS_TO_RESOURCE.get(server, "亚服")
                    if isinstance(server, str)
                    else "亚服"
                )
            else:
                switch["Resource"] = "官服"
        normalized_data = migrate_legacy_fields(cls, normalized_data)
        info = normalized_data.get("Info")
        if isinstance(info, dict):
            base = info.get("Base")
            if base in ("shared", "independent", "native"):
                info["IfQuickConfig"] = base != "native"
        return normalized_data

    @virtual_field("Info.Tag")
    def compute_Info_Tag(self):
        try:
            return self.getTags()
        except Exception as exc:
            return str(exc)


class GeneralConfig(DomainEntry):
    "通用配置"

    related_config: ClassVar = {}

    class GameFields(ConfigGroup):
        Arguments: CliArgumentString = Field(
            default_factory=lambda: "", description="游戏启动参数"
        )

        EmulatorId: Annotated[
            UUID | str,
            ref(
                "EmulatorConfig",
                default="-",
                allow_values=("-",),
                display_field="Info.Name",
            ),
        ] = Field(default_factory=lambda: "-", description="模拟器 ID")
        EmulatorIndex: str = Field(
            default_factory=lambda: "-", description="模拟器索引"
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
        Name: str = Field(default_factory=lambda: "新通用脚本", description="脚本名称")

        RootPath: FolderPath = Field(
            default_factory=lambda: None, description="根目录路径"
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class RunFields(ConfigGroup):
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


class OkwwConfig(DomainEntry):
    "OK-WW 配置（ok-script 线）"

    class GameFields(ConfigGroup):
        AccountSwitch: bool = Field(
            default_factory=lambda: False,
            description="运行前强制切换账号（依赖游戏配置启用；用户未填手机号时不切换）",
        )

        Arguments: CliArgumentString = Field(
            default_factory=lambda: "",
            description="鸣潮启动参数（直启时 MAS 会额外内置 -krqlv=hd，与本参数并存）",
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
            description="游戏启动方式：Client=直启客户端（内置 -krqlv=hd），Launcher=经官方启动器 默认值必须排首位：值非法时 correct() 回落到 options[0]",
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
            default_factory=lambda: "新 OK-WW 脚本", description="脚本名称"
        )

        RootPath: FolderPath = Field(
            default_factory=lambda: None, description="OK-WW 脚本根目录"
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class RunFields(ConfigGroup):
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
            description="静默启动（Autoplay）= 启动器带 /autoplay 拉起，不点按钮；启动器界面启动 （LauncherUi）= 打开启动器界面，由 OCR 点「开始游戏」及其弹窗/更新分支。 默认值双轨：新建脚本取类默认 Autoplay；存量脚本（配置无该键）由 load 迁移 固化升级前的 LauncherUi（见 _migrate_oknte_launch_mode_default），保持升级前行为。",
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
            description="脚本名称", default_factory=lambda: "新 OK-NTE 脚本"
        )

        RootPath: FolderPath = Field(
            description="脚本根目录", default_factory=lambda: None
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class RunFields(ConfigGroup):
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
            description="OkNte 运行参数建议由用户配置（-t / -e 由用户配置 Task 决定），但仍保留高级参数入口",
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
        data = deepcopy(data)
        migrated_data, migrated = _migrate_oknte_launch_mode_default(data)
        return migrated_data


class BetterGIConfig(DomainEntry):
    "BetterGI 配置（更好的原神，原生 GUI 原生来源 + 仅一条龙任务）"

    class GameFields(ConfigGroup):
        CloseOnFinish: bool = Field(
            default_factory=lambda: True, description="任务结束后关闭游戏"
        )

        Controller: Literal["电脑端-前台", "电脑端-云原神", "电脑端-桌面分身"] = Field(
            default_factory=lambda: "电脑端-前台",
            description="控制器（游戏控制方式：电脑端-前台 / 电脑端-云原神 / 电脑端-桌面分身） ⚠️ 预留字段：当前运行时不读取（BetterGI 自行管理游戏控制），云原神 / 桌面分身 尚未开发。为将来支持而保留占位并持久化，恒为默认「电脑端-前台」，勿被判定死代码误删。",
        )

        IfAutoUpdate: bool = Field(
            default_factory=lambda: False,
            description="是否在启动 BetterGI 前由 MAS 检查并接管原神客户端更新",
        )

    Game: GameFields = Field(default_factory=GameFields)

    class InfoFields(ConfigGroup):
        Name: str = Field(
            description="脚本名称", default_factory=lambda: "新 BetterGI 脚本"
        )

        RootPath: FolderPath = Field(
            description="脚本根目录", default_factory=lambda: None
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class RunFields(ConfigGroup):
        AccountSwitchMethod: Literal["BGI", "MAS"] = Field(
            default_factory=lambda: "MAS",
            description="账号切换方式（脚本级，参考 MaaEnd Run.AccountSwitchMethod）： BGI = BetterGI「切换账号多模式」脚本执行（国际服请改用此方式）；MAS = MAS 侧 前台 OCR 直接操控游戏切号（官服/B服，游戏由 MAS 托管启动），官服/B服推荐。 默认值双轨：新建脚本取类默认 MAS；存量脚本（配置无该键）由 load 迁移固化 旧默认 BGI（见 _migrate_bgi_account_switch_default），保持升级前行为。",
        )

        HardTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 120,
            description="单账号运行总时限（分钟），包含等待和全部重试",
        )

        ProxyTimesLimit: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            description="每日代理次数限制", default_factory=lambda: 0
        )

        RunTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            description="日志超时限制", default_factory=lambda: 10
        )

        RunTimesLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            description="重试次数限制", default_factory=lambda: 3
        )

        UseAdmin: bool = Field(
            default_factory=lambda: True,
            description="是否以管理员权限启动 BetterGI。默认提权（贴近旧行为）；若 MAS 平时以非管理员 运行、又不希望每次启动 BGI 都弹 UAC（无人值守任务尤其容易挂在授权上），可关闭。 MAS 自身已提权时，即使此处开启，也不会重复触发 UAC（子进程自动继承管理员令牌）。",
        )

    Run: RunFields = Field(default_factory=RunFields)
    UserData: ConfigCollection[BetterGIUserConfig] = collection(BetterGIUserConfig)

    @classmethod
    def normalize_payload(cls, data):
        data = deepcopy(data)
        migrated_data, migrated = _migrate_bgi_account_switch_default(data)
        return migrated_data


class ZzzOdUserConfig(DomainEntry):
    """绝区零一条龙用户配置（zzz-od 线，MaaEnd 式字段化用户配置）

    用户配置的事实源是本类的 配置字段（web 界面直接编辑，走通用
    updateUser 链路）：Game 区为账号/区服/游戏路径，OneDragon 区为一条龙
    任务编排（JSON，顺序即执行顺序）。运行时由这些字段生成 game_account.yml
    与 one_dragon/_group.yml 注入当前活跃实例槽、结束恢复原状（MAS 不留
    痕迹）。原生（native）来源不使用字段配置，直接以 zzz-od 原生配置运行。
    """

    class DataFields(ConfigGroup):
        LastProxyDate: Annotated[datetime, tz(UTC4), ui(format="date")] = Field(
            description="上次代理日期",
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=UTC4),
        )

        LastProxyStatus: Literal["未知", "成功", "失败"] = Field(
            description="上次代理状态（未知/成功/失败）", default_factory=lambda: "未知"
        )

        LauncherLastGood: Annotated[
            Literal["", "原始", "集成"],
            ui(visibility=UiVisibility.HIDE),
        ] = Field(
            default_factory=lambda: "",
            description='智能启动器模式最近一次成功运行的启动器（""=尚未记录；下次智能优先用它）',
        )

        ProxyTimes: Annotated[int, Field(ge=0, le=9999)] = Field(
            description="代理次数", default_factory=lambda: 0
        )

    Data: DataFields = Field(default_factory=DataFields)

    class GameFields(ConfigGroup):
        Account: str = Field(
            default_factory=lambda: "",
            description="登录账号（手机号/邮箱；留空沿用 zzz-od 已保存的登录态）",
        )

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

        Password: Annotated[str, encrypted()] = Field(
            default_factory=lambda: "",
            description="登录密码（DPAPI 加密落盘，注入/回读写 game_account.yml 时经 get/set 自动加解密）",
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

    class InfoFields(ConfigGroup):
        Base: Annotated[
            Literal["shared", "independent", "native"],
            legacy(group="Info", name="Mode", convert=normalize_base_source),
        ] = Field(
            default_factory=lambda: "independent",
            description="base 来源（shared=共享/independent=独立/native=原生）",
        )

        IfQuickConfig: bool = Field(
            default_factory=lambda: True,
            description="是否启用快速配置（已封锁，仅保留字段兼容存量数据：原生来源在 load/update 归一为关，共享/独立来源不消费本开关）",
        )

        IfScriptAfterTask: bool = Field(
            description="是否在任务后执行脚本", default_factory=lambda: False
        )

        IfScriptBeforeTask: bool = Field(
            description="是否在任务前执行脚本", default_factory=lambda: False
        )

        LauncherMode: Literal["自动", "原始", "集成"] = Field(
            default_factory=lambda: "自动",
            description="一条龙启动器选择（原生/独立两态通用）： 自动 = 优先用「上次成功」的启动器，启动失败自动换另一个重试并记住下一次 成功的那个；原始/集成 = 固定用对应启动器（对应 exe 未安装时回退可用项）",
        )

        Name: WindowsNameString = Field(
            description="用户名", default_factory=lambda: "新用户"
        )

        Notes: str = Field(description="备注", default_factory=lambda: "无")

        RemainedDay: Annotated[int, Field(ge=-1, le=9999), none_as(-1)] = Field(
            description="剩余天数", default_factory=lambda: -1
        )

        ScriptAfterTask: FilePath = Field(
            description="任务后脚本路径", default_factory=lambda: None
        )

        ScriptBeforeTask: FilePath = Field(
            description="任务前脚本路径", default_factory=lambda: None
        )

        SlotIdx: Annotated[int, Field(ge=-1, le=9999)] = Field(
            default_factory=lambda: -1,
            description="绑定的 zzz-od 实例槽下标（运行/配置会话内临时合成视图写回原生配置，非持久注册）：-1=未分配，首次运行或 「在一条龙内配置」时自动分配空闲 idx 并锁定该槽至会话结束， 此后配置会话与运行时注入都固定使用该槽。新槽从 MAS_SLOT_BASE（1001）起， 退到一条龙「升序找最小空号」够不到的高位段（上限 9999 与之一致放宽）",
        )

        Status: bool = Field(description="用户状态", default_factory=lambda: True)

        Tag: Virtual[str] = Field(
            description="用户标签列表（JSON字符串，TagItem的dict列表）",
            default_factory=lambda: None,
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class NotifyFields(ConfigGroup):
        Enabled: bool = Field(
            default_factory=lambda: False, description="是否启用用户通知"
        )

        IfSendMail: bool = Field(
            default_factory=lambda: False, description="是否发送邮件"
        )

        IfSendStatistic: bool = Field(
            default_factory=lambda: False, description="是否发送用户统计信息"
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

        ToAddress: str = Field(default_factory=lambda: "", description="用户收件地址")

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
            description="多用户账号切换方式（脚本级下拉，value 对应 manager 的分派分支）： 单实例切换（默认，推荐）= 逐用户独立会话：注入该用户配置 → 单实例 运行（仅运行当前，无槽间切换）→ 跑完关闭 → 下一个用户。失败域 隔离最好，重试只重启失败用户； 多实例切换（不推荐）= 全部启用用户合并为一轮多账号运行，一条龙内部 依次切换账号。总时长最短，但单槽失败会拖整轮重试、切换次数随 用户数线性增长； MAS切换 = MAS 侧 OCR 操控游戏完成账号切换后交一条龙运行（暂未开放）。",
        )

        Arguments: CliArgumentString = Field(
            default_factory=lambda: "", description="游戏启动参数"
        )

        CloseOnFinish: bool = Field(
            default_factory=lambda: True,
            description="任务结束后由 MAS 关闭游戏（收尾/手动停止时按进程名结束游戏本体， 覆盖失败重试与手动停止场景，是「结束后操作」的兜底）。与用户级 OneDragon.AfterDone 下发的 --close-game 相互独立，同时配置会各 执行一次（无害）",
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
            default_factory=lambda: "新绝区零一条龙脚本", description="脚本名称"
        )

        RootPath: FolderPath = Field(
            default_factory=lambda: None,
            description="zzz-od 安装根目录（含 OneDragon 启动器、src 与 config）",
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class RunFields(ConfigGroup):
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
    "BAAH 用户配置"

    related_config: ClassVar = {}

    class DataFields(ConfigGroup):
        LastProxyDate: Annotated[datetime, tz(UTC4), ui(format="date")] = Field(
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=UTC4),
            description="上次代理日期",
        )

        ProxyTimes: Annotated[int, Field(ge=0, le=9999)] = Field(
            default_factory=lambda: 0, description="代理次数"
        )

    Data: DataFields = Field(default_factory=DataFields)

    class InfoFields(ConfigGroup):
        ActivityLineType: Literal["JP", "Globle", "CN"] = Field(
            default_factory=lambda: "CN",
            description="活动排期按哪个服判断，供「活动关优先」使用（Kivo 时间轴的原文拼写：JP / Globle / CN）",
        )

        Base: Annotated[
            Literal["shared", "independent", "native"],
            legacy(group="Info", name="Mode", convert=normalize_base_source),
        ] = Field(
            default_factory=lambda: "independent",
            description="base 来源（shared=共享/independent=独立/native=原生）",
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
            description="是否启用快速配置（与配置来源独立，按用户保存）",
        )

        Name: WindowsNameString = Field(
            default_factory=lambda: "新用户", description="用户名称"
        )

        Notes: str = Field(default_factory=lambda: "无", description="备注")

        RemainedDay: Annotated[int, Field(ge=-1, le=9999), none_as(-1)] = Field(
            default_factory=lambda: -1, description="剩余天数"
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
            description="关卡计划表；Fixed 表示按脚本配置",
        )

        Status: bool = Field(default_factory=lambda: True, description="是否启用")

        Tag: Virtual[str] = Field(
            default_factory=lambda: None, description="用户标签信息"
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
        """生成 BAAH 用户标签列表"""
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

    related_config: ClassVar = {}

    class EmulatorFields(ConfigGroup):
        Id: Annotated[
            UUID | str,
            ref(
                "EmulatorConfig",
                default="-",
                allow_values=("-",),
                display_field="Info.Name",
            ),
        ] = Field(default_factory=lambda: "-", description="模拟器 ID")
        Index: str = Field(default_factory=lambda: "-", description="模拟器索引")

    Emulator: EmulatorFields = Field(default_factory=EmulatorFields)

    class InfoFields(ConfigGroup):
        Name: str = Field(
            default_factory=lambda: "新 BAAH 脚本", description="脚本名称"
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
        BAAHPath: FilePath = Field(
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


class WhimboxUserConfig(DomainEntry):
    """奇想盒用户配置（无限暖暖，一条龙配置档）

    一条龙字段定义与值域完全来自上游安装目录三件套（任务目录，运行时读取），
    本类只存「用户勾了哪些步骤、选了哪些值」的覆盖集（Tasks/Options 两个
    JSON map），不复制上游字段模型；写入时按当前模板键集过滤后物化到上游
    configs/config.json。
    """

    class DataFields(ConfigGroup):
        LastProxyDate: Annotated[datetime, tz(UTC4), ui(format="date")] = Field(
            description="上次代理日期",
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=UTC4),
        )

        LastProxyStatus: Literal["未知", "成功", "失败"] = Field(
            description="上次代理状态（未知/成功/失败）", default_factory=lambda: "未知"
        )

        ProxyTimes: Annotated[int, Field(ge=0, le=9999)] = Field(
            description="代理次数", default_factory=lambda: 0
        )

    Data: DataFields = Field(default_factory=DataFields)

    class InfoFields(ConfigGroup):
        Base: Annotated[
            Literal["shared", "independent", "native"],
            legacy(group="Info", name="Mode", convert=normalize_base_source),
        ] = Field(
            default_factory=lambda: "shared",
            description="base 来源三态（shared=共享/independent=独立/native=原生）：共享/独立= 用 MAS 面板配置（当前运行行为一致，为后续特殊功能预留），原生=直接用奇想盒 自带配置（MAS 零写入）",
        )

        IfQuickConfig: bool = Field(
            default_factory=lambda: False,
            description="是否启用覆写层（快速配置，与来源独立，按账号保存，默认关）：开启时原生态 也会在任务前把面板覆盖集写入奇想盒（overlay，任务结束还原）；共享/独立态 面板本就是 base 来源，开关暂无额外消费点，为后续特殊功能预留。默认关保证 「原生=零写入」与 _write_config_or_hint 报错里「切原生绕开写入」的出路成立",
        )

        IfScriptAfterTask: bool = Field(
            description="是否在任务后执行脚本", default_factory=lambda: False
        )

        IfScriptBeforeTask: bool = Field(
            description="是否在任务前执行脚本", default_factory=lambda: False
        )

        Name: WindowsNameString = Field(
            description="用户名", default_factory=lambda: "新用户"
        )

        Notes: str = Field(description="备注", default_factory=lambda: "无")

        RemainedDay: Annotated[int, Field(ge=-1, le=9999), none_as(-1)] = Field(
            description="剩余天数", default_factory=lambda: -1
        )

        ScriptAfterTask: FilePath = Field(
            description="任务后脚本路径", default_factory=lambda: None
        )

        ScriptBeforeTask: FilePath = Field(
            description="任务前脚本路径", default_factory=lambda: None
        )

        Status: bool = Field(description="用户状态", default_factory=lambda: True)

        Tag: Virtual[str] = Field(
            description="用户标签列表（JSON字符串，TagItem的dict列表）",
            default_factory=lambda: None,
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class NotifyFields(ConfigGroup):
        Enabled: bool = Field(
            default_factory=lambda: False, description="是否启用用户通知"
        )

        IfSendMail: bool = Field(
            default_factory=lambda: False, description="是否发送邮件"
        )

        IfSendStatistic: bool = Field(
            default_factory=lambda: False, description="是否发送用户统计信息"
        )

        IfServerChan: bool = Field(
            default_factory=lambda: False, description="是否启用 Server 酱"
        )

        ServerChanKey: str = Field(
            default_factory=lambda: "", description="Server 酱密钥"
        )

        ToAddress: str = Field(default_factory=lambda: "", description="用户收件地址")

    Notify: NotifyFields = Field(default_factory=NotifyFields)

    class OneDragonFields(ConfigGroup):
        IfRunAllAccounts: bool = Field(
            default_factory=lambda: False,
            description="一条龙是否循环全部游戏账号（物化为上游 OneDragon.change_account； 账号列表由奇想盒运行期 OCR 动态发现，MAS 不做账号定向）",
        )

    OneDragon: OneDragonFields = Field(default_factory=OneDragonFields)

    class TaskFields(ConfigGroup):
        Options: JsonDictString = Field(
            default_factory=lambda: "{ }",
            description="目标/参数覆盖集：JSON map {键: 值}，键集来自任务目录 （上游 OneDragon 节托管字段），只存用户显式选择的值",
        )

        Tasks: JsonDictString = Field(
            default_factory=lambda: "{ }",
            description="步骤开关覆盖集：JSON map {步骤键: bool}，键集来自任务目录 （上游 OneDragonDefaultSteps 节），只存用户勾选结果",
        )

    Task: TaskFields = Field(default_factory=TaskFields)
    Notify_CustomWebhooks: ConfigCollection[Webhook] = collection(Webhook)

    def getTags(self) -> str:
        """生成奇想盒用户标签列表"""
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


class WhimboxConfig(DomainEntry):
    "奇想盒配置（无限暖暖，BetterGI 线：无头 CLI + 日志面判定）"

    class InfoFields(ConfigGroup):
        Name: str = Field(
            description="脚本名称", default_factory=lambda: "新奇想盒脚本"
        )

        RootPath: FolderPath = Field(
            default_factory=lambda: None,
            description="奇想盒安装根目录（whimbox_app.exe 所在目录；configs/logs 与其同级）",
        )

    Info: InfoFields = Field(default_factory=InfoFields)

    class RunFields(ConfigGroup):
        HardTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 120,
            description="单账号运行总时限（分钟），包含等待和全部重试",
        )

        ProxyTimesLimit: Annotated[int, Field(ge=0, le=9999), none_as(0)] = Field(
            description="每日代理次数上限（0=不限）",
            default_factory=lambda: 0,
        )

        RunTimeLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 30,
            description="运行超时（分钟）：日志静默超过该时长判定卡死",
        )

        RunTimesLimit: Annotated[int, Field(ge=1, le=9999), none_as(1)] = Field(
            default_factory=lambda: 3,
            description="失败重试次数：只用于「没有上游结论」的异常（进程提前退出/卡死）； 上游自己判负时，仅当失败原因与上一轮不同才继续重试（同一结论连着出现即收口）",
        )

        UseAdmin: bool = Field(
            default_factory=lambda: True,
            description="以管理员权限启动奇想盒后端（上游强制管理员，缺权限会在起跑即退出； MAS 自身已提权时不重复触发 UAC，子进程自动继承管理员令牌）",
        )

    Run: RunFields = Field(default_factory=RunFields)
    UserData: ConfigCollection[WhimboxUserConfig] = collection(WhimboxUserConfig)


__all__ = [
    "ScriptConfigType",
    "UserConfigType",
    "MaaUserConfig",
    "MaaConfig",
    "MaaEndUserConfig",
    "MaaEndConfig",
    "SrcUserConfig",
    "SrcConfig",
    "HSRUserConfig",
    "HSRConfig",
    "MaaFWUserConfig",
    "MaaFWConfig",
    "M9AUserConfig",
    "M9AConfig",
    "MSSUserConfig",
    "MSSConfig",
    "GeneralUserConfig",
    "OkwwUserConfig",
    "OkNteUserConfig",
    "BetterGIUserConfig",
    "GeneralConfig",
    "OkwwConfig",
    "OkNteConfig",
    "BetterGIConfig",
    "ZzzOdUserConfig",
    "ZzzOdConfig",
    "BAAHUserConfig",
    "BAAHConfig",
    "WhimboxUserConfig",
    "WhimboxConfig",
]


type ScriptConfigType = (
    MaaConfig
    | MaaEndConfig
    | SrcConfig
    | HSRConfig
    | MaaFWConfig
    | M9AConfig
    | MSSConfig
    | GeneralConfig
    | OkwwConfig
    | OkNteConfig
    | BetterGIConfig
    | ZzzOdConfig
    | BAAHConfig
    | WhimboxConfig
)
type UserConfigType = (
    MaaUserConfig
    | MaaEndUserConfig
    | SrcUserConfig
    | HSRUserConfig
    | MaaFWUserConfig
    | M9AUserConfig
    | MSSUserConfig
    | GeneralUserConfig
    | OkwwUserConfig
    | OkNteUserConfig
    | BetterGIUserConfig
    | ZzzOdUserConfig
    | BAAHUserConfig
    | WhimboxUserConfig
)
