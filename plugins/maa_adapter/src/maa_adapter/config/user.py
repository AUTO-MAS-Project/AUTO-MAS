from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from typing import Annotated, ClassVar, Literal, Self, cast
from uuid import UUID

from auto_mas_core import UserEntry
from auto_mas_core.host.config import (
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    FieldChangeEvent,
    UiVisibility,
    Virtual,
    collection,
    config_manager,
    encrypted,
    legacy,
    ref,
    tz,
    ui,
    virtual_field,
)
from auto_mas_core.host.config_types import (
    FilePath,
    JsonDictString,
    JsonListString,
    WindowsNameString,
)
from auto_mas_core.host.models_config_queue import Webhook
from auto_mas_core.host.models_config_shared import (
    _tag_notes,
    _tag_proxy,
    _tag_remained_days,
    none_as,
)
from auto_mas_core.host.task_proxy_helpers import (
    CONFIG_BASE_NATIVE,
    CONFIG_BASE_SHARED,
    read_config_base,
)
from auto_mas_core.host.utils import constants as _utils_constants
from pydantic import Field

from maa_adapter.config.fields import DepotQuotaNumb, StageCode
from maa_adapter.config.migration import migrate_maa_stamina_pipeline
from maa_adapter.config.plan import MaaPlanConfig
from maa_adapter.constants import (
    MAA_STAGE_KEY,
    RESOURCE_STAGE_INFO,
    get_game_day_tz,
)


class MaaUserConfig(UserEntry):
    "MAA账号配置"

    related_config: ClassVar = {}

    class DataFields(ConfigGroup):
        def _game_day_timezone(self):
            """按当前账号服务器读取游戏日时间，不改变保存的 UTC 时刻。"""
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
            datetime | None,
            tz(_utils_constants.UTC4),
            ui(widget="datetime", format="hms"),
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
            description="无时段排班表下一班的索引：每账号一份、由 MAS 在基建换班完成后推进； 带时段表交 MAA 按时段选班，不读它",
        )

        LastProxyDate: Annotated[
            datetime,
            tz(_game_day_timezone),
            ui(format="date"),
            ui(visibility=UiVisibility.HIDE),
        ] = Field(
            default_factory=lambda: datetime(2000, 1, 1, tzinfo=_utils_constants.UTC4),
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
            description="理智流程升级前完整账号配置 JSON", default_factory=lambda: "{}"
        )

        StaminaPipelineVersion: Annotated[int, Field(ge=0, le=1)] = Field(
            default_factory=lambda: 1,
            description="理智流程配置迁移版本与升级前完整账号配置（关闭的旧计划仍可找回）",
        )

    Data: DataFields = Field(default_factory=DataFields)

    class InfoFields(ConfigGroup):
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

        Id: str = Field(default_factory=lambda: "", description="账号 ID")

        IfQuickConfig: bool = Field(
            default_factory=lambda: True,
            description="是否启用覆写常规配置（与配置来源独立，按账号保存）",
        )

        IfScriptAfterTask: bool = Field(
            default_factory=lambda: False, description="任务后执行脚本"
        )

        IfScriptBeforeTask: bool = Field(
            default_factory=lambda: False, description="任务前执行脚本"
        )

        Name: WindowsNameString = Field(
            default_factory=lambda: "新账号", description="账号名称"
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
            description="账号标签信息（虚拟字段，供前端显示）",
        )

    Info: InfoFields = Field(default_factory=InfoFields)  # pyright: ignore[reportIncompatibleVariableOverride]

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

    Notify: NotifyFields = Field(default_factory=NotifyFields)  # pyright: ignore[reportIncompatibleVariableOverride]

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

        Stage: Annotated[StageCode, legacy(group="Info", name="Stage")] = Field(
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

        Stage_1: Annotated[StageCode, legacy(group="Info", name="Stage_1")] = Field(
            default_factory=lambda: "-", description="备选关卡 1"
        )

        Stage_2: Annotated[StageCode, legacy(group="Info", name="Stage_2")] = Field(
            default_factory=lambda: "-", description="备选关卡 2"
        )

        Stage_3: Annotated[StageCode, legacy(group="Info", name="Stage_3")] = Field(
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

        CultivateAllOwned: bool = Field(
            default_factory=lambda: False,
            description="是否托管全部已有干员，按森空岛练度补充精二与技能七级目标",
        )

        CultivateSkipDuringActivity: bool = Field(
            default_factory=lambda: False, description="活动期间是否跳过养成计划"
        )

        CultivateSkipDuringResourceCollection: bool = Field(
            default_factory=lambda: False, description="资源收集期是否跳过养成计划"
        )

        CultivateMonthlyCard: bool = Field(
            default_factory=lambda: False,
            description="预计材料时间是否计入月卡每日额外 80 理智，仅用于估算",
        )

        CultivateSklandAccount: str = Field(
            default_factory=lambda: "",
            description="森空岛绑定：签到账号组 UUID（凭据引用，凭据本体只存签到域）",
        )

        CultivateSklandUid: str = Field(
            default_factory=lambda: "",
            description="森空岛绑定：绑定角色的游戏 uid（非森空岛 userId）",
        )

        DepotMaintainMedicineNumb: DepotQuotaNumb = Field(
            default_factory=lambda: None,
            description="普通库存保持每条计划使用理智药数量；留空沿用 MAA 配置",
        )

        DepotMaintainStoneNumb: DepotQuotaNumb = Field(
            default_factory=lambda: None,
            description="普通库存保持每条计划使用源石数量；留空沿用 MAA 配置",
        )

        CultivateMedicineNumb: DepotQuotaNumb = Field(
            default_factory=lambda: None,
            description="干员养成每条计划使用理智药数量；留空沿用 MAA 配置",
        )

        CultivateStoneNumb: DepotQuotaNumb = Field(
            default_factory=lambda: None,
            description="干员养成每条计划使用源石数量；留空沿用 MAA 配置",
        )

        CultivateTargets: JsonListString = Field(
            default_factory=lambda: "[]", description="干员养成目标"
        )

        DepotMaintainPlans: JsonListString = Field(
            default_factory=lambda: (
                '[{"Stage":"PR-A-1","DropId":"3261","DropCount":20},{"Stage":"PR-A-1","DropId":"3231","DropCount":20},{"Stage":"PR-B-1","DropId":"3251","DropCount":20},{"Stage":"PR-B-1","DropId":"3241","DropCount":20},{"Stage":"PR-C-1","DropId":"3211","DropCount":20},{"Stage":"PR-C-1","DropId":"3271","DropCount":20},{"Stage":"PR-D-1","DropId":"3221","DropCount":20},{"Stage":"PR-D-1","DropId":"3281","DropCount":20},{"Stage":"PR-A-2","DropId":"3262","DropCount":20},{"Stage":"PR-A-2","DropId":"3232","DropCount":20},{"Stage":"PR-B-2","DropId":"3252","DropCount":20},{"Stage":"PR-B-2","DropId":"3242","DropCount":20},{"Stage":"PR-C-2","DropId":"3212","DropCount":20},{"Stage":"PR-C-2","DropId":"3272","DropCount":20},{"Stage":"PR-D-2","DropId":"3222","DropCount":20},{"Stage":"PR-D-2","DropId":"3282","DropCount":20},{"Stage":"CE-6","DropId":"4001","DropCount":2000000},{"Stage":"AP-5","DropId":"4006","DropCount":5000},{"Stage":"CA-5","DropId":"3303","DropCount":200}]'
            ),
            description="库存保持计划（覆写常规配置面板维护；MAA 侧同名 PlanList 为透传载体）",
        )

        EventDepotMaintainPlans: JsonListString = Field(
            default_factory=lambda: (
                '[{"StageType":"all","DropCount":999,"OrundumDropCount":9999}]'
            ),
            description="活动库存保持计划，保存材料关序号及目标库存，运行时解析当前活动",
        )

        EventDepotMaintainMedicineNumb: DepotQuotaNumb = Field(
            default_factory=lambda: None,
            description="活动库存保持每条计划使用理智药数量；留空沿用 MAA 配置",
        )

        EventDepotMaintainStoneNumb: DepotQuotaNumb = Field(
            default_factory=lambda: None,
            description="活动库存保持每条计划使用源石数量；留空沿用 MAA 配置",
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
        """从当前基建模式和已保存的原生基建资料提取可展示名称，无配置时返回对应提示。"""
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
        """生成账号标签列表，返回JSON字符串格式的TagItem列表"""
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
        """将资源关卡标识转换为简短中文名称，未找到对应条目时保留原标识。"""
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
        """复制用户配置输入并执行已有体力管线迁移，避免激活过程修改调用方原始数据。"""
        data = deepcopy(data)
        migrated_data, migrated = migrate_maa_stamina_pipeline(data)
        return migrated_data

    @virtual_field("Info.Tag")
    def compute_Info_Tag(self):
        """计算账号展示标签，生成失败时以错误文本保留诊断信息。"""
        try:
            return self.getTags()
        except Exception as exc:
            return str(exc)

    @virtual_field("Task.InfrastName")
    def compute_Task_InfrastName(self):
        """计算基建配置展示名称，读取失败时返回错误文本供界面诊断。"""
        try:
            return self.getInfrastName()
        except Exception as exc:
            return str(exc)

    class Metadata(UserEntry.Info):
        # 来源兼容字段改为虚拟读取；Virtual 的冷态 None 与父类可写字段类型不同。
        name: Virtual[str] = None  # pyright: ignore[reportIncompatibleVariableOverride]
        enabled: Virtual[bool] = None  # pyright: ignore[reportIncompatibleVariableOverride]
        config_path: Virtual[str] = None  # pyright: ignore[reportIncompatibleVariableOverride]

    info: Metadata = Field(default_factory=Metadata)  # pyright: ignore[reportIncompatibleVariableOverride]

    @virtual_field("info.name")
    def plugin_name(self):
        """将来源账号名称字段提供给插件用户基类使用。"""
        return self.Info.Name

    @virtual_field("info.enabled")
    def plugin_enabled(self):
        """将来源账号启用状态提供给插件用户基类使用。"""
        return self.Info.Status

    @virtual_field("info.config_path")
    def plugin_config_path(self) -> str:
        """通过已有目录字段提供生效配置位置，不向宿主登记专项目录解析回调。"""
        from auto_mas_core import Config

        from maa_adapter.config.script import MaaConfig
        from maa_adapter.config.user_update import resolve_user_config_dir

        collection = self.parent
        script = collection.parent if collection is not None else None
        if not isinstance(script, MaaConfig):
            return ""
        if (
            read_config_base(self, CONFIG_BASE_SHARED) == CONFIG_BASE_NATIVE
            and script.Info.Path is None
        ):
            return ""
        return str(resolve_user_config_dir(script, self, data_path=Config.data_path))

    async def update(
        self, other: ConfigEntry, *, check_visibility: bool = True
    ) -> None:
        """在插件内准备用户保存所需数据，再通过既有配置更新入口提交并执行信号联动。"""
        if not check_visibility or "Task" not in other.model_fields_set:
            await super().update(cast(Self, other), check_visibility=check_visibility)
            return
        from maa_adapter.config.script import MaaConfig
        from maa_adapter.config.user_update import prepare_user_update

        collection = self.parent
        script = collection.parent if collection is not None else None
        # Entry 导出是完整配置视图；保存补丁只读取明确传入的组与字段，避免默认值覆盖绑定。
        data = {
            group: {field: values.__dict__[field] for field in values.model_fields_set}
            for group in other.model_fields_set
            if group in other._cfg_group_fields
            and isinstance(values := other.__dict__[group], ConfigGroup)
        }
        guard = await prepare_user_update(cast(MaaConfig, script), self, data=data)
        async with config_manager.execution_gate():
            if guard is not None:
                guard()
            await super().update(
                type(self).model_validate(data), check_visibility=check_visibility
            )

    @staticmethod
    async def check_native_source(sender: object, event: FieldChangeEvent) -> None:
        """原生来源变更时检查同托管其他账号，冲突由配置事务回退本次字段写入。"""
        user = cast(MaaUserConfig, sender)
        users = user.parent
        if event.value != _utils_constants.BASE_NATIVE or users is None:
            return
        if any(
            sibling.uid != user.uid
            and sibling.Info.Base == _utils_constants.BASE_NATIVE
            for sibling in cast(ConfigCollection[MaaUserConfig], users).values()
        ):
            raise ValueError(
                "每个托管仅允许一个原生来源账号, 多账号请在该账号的实例管理中配置"
            )

    async def _activate_from_payload(self, payload, *, regenerate_uuids=False):
        """先迁移来源账号配置，再交给配置框架激活节点及处理标识重建。"""
        await super()._activate_from_payload(
            type(self).normalize_payload(payload), regenerate_uuids=regenerate_uuids
        )


MaaUserConfig.connect(
    MaaUserConfig.check_native_source, phase="runtime", group="Info", field="Base"
)
