"""跨模块公共契约；端点专用请求与响应在所属 API 模块声明。"""

import math
import re
from datetime import date
from pathlib import Path
from typing import (
    Annotated,
    Any,
    Dict,
    Generic,
    List,
    Literal,
    NamedTuple,
    Optional,
    TypeVar,
    Union,
)
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationInfo,
    WithJsonSchema,
    field_validator,
)

from app.utils import MSS_DEFAULT_TRIBULATION_STAGE, MSS_TRIBULATION_STAGES

type HistoryCounterValue = int | float | dict[str, HistoryCounterValue]


class HistoryCounterStatistic(BaseModel):
    kind: Literal["counter"] = "counter"
    # 现有客户端生成器不能编译递归 Record 别名；仅展开传输首层，Python仍完整校验数值树。
    value: Annotated[
        int | float | dict[str, Any],
        WithJsonSchema(
            {
                "anyOf": [
                    {"type": "number"},
                    {"type": "object", "additionalProperties": {}},
                ],
                "description": "有限数值或任意深度的嵌套数值字典，所有叶子必须为数值",
            }
        ),
    ]

    @field_validator("value", mode="before")
    @classmethod
    def validate_counter(cls, value):
        def check(item):
            if type(item) in (int, float):
                if isinstance(item, float) and not math.isfinite(item):
                    raise ValueError("计数必须是有限数值")
            elif isinstance(item, dict):
                for key, child in item.items():
                    if not isinstance(key, str):
                        raise ValueError("计数键必须是字符串")
                    check(child)
            else:
                raise ValueError("计数只接受数值或嵌套数值字典")

        check(value)
        return value


HistoryJsonValue = Annotated[
    JsonValue,
    WithJsonSchema(
        {
            "anyOf": [
                {"type": "boolean"},
                {"type": "number"},
                {"type": "string"},
                {"type": "array", "items": {}},
                {"type": "object", "additionalProperties": {}},
            ],
            "nullable": True,
        }
    ),
]


class HistorySnapshotStatistic(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    kind: Literal["snapshot"] = "snapshot"
    value: HistoryJsonValue


class HistoryKeyedSnapshotStatistic(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    kind: Literal["keyed_snapshot"] = "keyed_snapshot"
    value: dict[str, HistoryJsonValue]


HistoryStatistic = Annotated[
    HistoryCounterStatistic | HistorySnapshotStatistic | HistoryKeyedSnapshotStatistic,
    Field(discriminator="kind"),
]
HistoryStatus = Literal["success", "error", "skipped", "cancelled"]
HistoryAttachmentKind = Literal["log", "image", "video", "diagnostic"]


class HistoryAttachmentInput(BaseModel):
    path: Path
    kind: HistoryAttachmentKind
    role: str
    display_name: str


class HistoryWrite(BaseModel):
    time: AwareDatetime
    username: str
    script_name: str
    status: HistoryStatus
    message: str
    logs: str
    data: dict[str, HistoryStatistic] = Field(default_factory=dict)
    attachments: list[HistoryAttachmentInput] = Field(default_factory=list)


class HistoryStorageIssue(BaseModel):
    stage: Literal["mkdir", "write_log", "move", "copy", "quota", "cleanup", "database"]
    attachment_index: int | None = None
    source_path: str | None = None
    target_path: str | None = None
    error_type: str
    message: str
    recovered: bool = False


class HistoryAttachment(BaseModel):
    id: UUID
    record_id: UUID
    kind: HistoryAttachmentKind
    role: str
    display_name: str
    relative_path: str | None = None
    byte_size: int = 0
    saved_via: Literal["move", "copy"] | None = None
    available: bool = False
    unavailable_reason: str | None = None


class HistoryIndexItem(BaseModel):
    id: UUID
    time: AwareDatetime
    username: str
    script_name: str
    status: HistoryStatus
    message: str
    storage_error_count: int = 0


class HistoryRecord(HistoryIndexItem):
    data: dict[str, HistoryStatistic] = Field(default_factory=dict)
    attachments: list[HistoryAttachment] = Field(default_factory=list)
    storage_errors: list[HistoryStorageIssue] = Field(default_factory=list)
    log_path: str | None = None
    has_log_fallback: bool = False


class HistoryDetail(HistoryRecord):
    log_content: str | None = None
    log_available: bool = False
    log_unavailable_reason: str | None = None


class HistoryAttachmentFile(HistoryAttachment):
    path: Path


class HistoryAggregationItem(BaseModel):
    time: AwareDatetime
    data: dict[str, HistoryStatistic] = Field(default_factory=dict)


class HistoryAggregateError(BaseModel):
    key: str
    message: str
    input_indices: list[int] = Field(default_factory=list)
    record_ids: list[UUID] = Field(default_factory=list)


class HistoryAggregate(BaseModel):
    data: dict[str, HistoryStatistic] = Field(default_factory=dict)
    errors: list[HistoryAggregateError] = Field(default_factory=list)


class HistoryBucket(BaseModel):
    index: list[HistoryIndexItem] = Field(default_factory=list)
    data: dict[str, HistoryStatistic] = Field(default_factory=dict)
    aggregate_errors: list[HistoryAggregateError] = Field(default_factory=list)


class HistoryRecordQuery(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    username: str | None = None
    script_name: str | None = None
    status: HistoryStatus | None = None
    limit: int = Field(default=100, ge=1, le=10000)


class HistoryUserOverview(BaseModel):
    execute_count: int = 0
    error_count: int = 0
    latest_time: AwareDatetime | None = None
    error_info: dict[UUID, str] = Field(default_factory=dict)


class HistoryCleanupReport(BaseModel):
    deleted_records: int = 0
    deleted_videos: int = 0
    reclaimed_bytes: int = 0
    errors: list[HistoryStorageIssue] = Field(default_factory=list)


class HistoryBackupSnapshot(BaseModel):
    destination: Path
    database: Path
    history: Path


class OutBase(BaseModel):
    code: int = Field(default=200, description="状态码")
    status: str = Field(default="success", description="操作状态")
    message: str = Field(default="操作成功", description="操作消息")


class TagItem(BaseModel):
    text: str = Field(..., description="标签文本")
    color: Literal[
        "red",
        "blue",
        "green",
        "yellow",
        "orange",
        "purple",
        "pink",
        "brown",
        "black",
        "white",
        "gray",
        "silver",
        "gold",
    ] = Field(..., description="标签颜色")


class ComboBoxItem(BaseModel):
    label: str = Field(..., description="展示值")
    value: Optional[str] = Field(..., description="实际值")


class ComboBoxOut(OutBase):
    data: List[ComboBoxItem] = Field(..., description="下拉框选项")


class VirtualDisplayCheckResultItem(BaseModel):
    """检测的三段之一。分开报是有意的：给用户的下一步动作完全不同。"""

    stage: Literal["installed", "openable", "effective"] = Field(description="检测阶段")
    passed: bool = Field(description="该阶段是否通过")
    message: str = Field(description="面向用户的说明")


class VirtualDisplayCheckOut(OutBase):
    driverVersion: Optional[int] = Field(default=None, description="驱动次版本号")
    monitors: str = Field(default="", description="检测时的显示器概况")
    holding: Optional[str] = Field(
        default=None,
        description="守卫此刻挂着的虚拟显示器（设备名与模式），没挂时为空；设置页据此显示当前挂着哪块",
    )
    results: list[VirtualDisplayCheckResultItem] = Field(default_factory=list)


class DeviceInfo(BaseModel):
    """设备信息"""

    title: str = Field(..., description="设备标题/名称")
    status: int = Field(..., description="设备状态, 参考DeviceStatus枚举值")
    adb_address: str = Field(..., description="ADB连接地址")


class UpdateDownloadSnapshot(BaseModel):
    """更新下载 HTTP 初始快照。"""

    status: Literal[
        "idle",
        "downloading",
        "switchingSource",
        "completed",
        "failed",
        "cancelled",
    ] = Field(default="idle")
    version: Optional[str] = Field(default=None, description="当前下载版本")
    source: Optional[str] = Field(default=None, description="当前下载源")
    downloaded_size: int = Field(default=0, ge=0)
    file_size: int = Field(default=0, ge=0)
    speed: float = Field(default=0, ge=0)
    file: Optional[str] = Field(default=None, description="完成后的更新包路径")
    message: Optional[str] = Field(default=None, description="失败或状态说明")


class EmulatorDeleteIn(BaseModel):
    emulatorId: str = Field(..., description="模拟器 ID")


PlanComboxConsumer = Literal["maa", "maaend", "baah", "mss"]


class MaaEndAutoEssencePlanKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    SanityTaskType: Literal["Essence"] = Field(
        default="Essence", description="基质刷取任务类型"
    )
    AutoEssenceSpecifiedLocation: str = Field(
        default="", description="基质刷取指定地点"
    )
    AutoEssenceMenu: Optional[Literal["Random", "Location", "Target"]] = Field(
        default=None, description="基质刷取模式"
    )
    AutoEssenceTargetWeapons: list[str] = Field(
        default_factory=list, description="基质目标武器 ID 列表"
    )


class MaaEndProtocolSpacePlanKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    SanityTaskType: Literal[
        "OperatorProgression", "WeaponProgression", "CrisisDrills"
    ] = Field(default="OperatorProgression", description="协议空间任务类型")
    OperatorProgression: Literal["OperatorEXP", "Promotions", "T-Creds", "SkillUp"] = (
        Field(default="OperatorEXP", description="干员养成任务")
    )
    WeaponProgression: Literal["WeaponEXP", "WeaponTune"] = Field(
        default="WeaponEXP", description="武器养成任务"
    )
    CrisisDrills: str = Field(
        default="AdvancedProgression1",
        description="危境预演任务，由 MaaEnd 声明",
        min_length=1,
    )
    RewardsSetOption: Literal["RewardsSetA", "RewardsSetB"] = Field(
        default="RewardsSetA", description="奖励组选项"
    )


# 未提供任务类型时使用协议空间模型的默认值；显式类型仍由各分支的 Literal 校验。
MaaEndPlanKey = MaaEndProtocolSpacePlanKey | MaaEndAutoEssencePlanKey


class BAAHSlotRule(NamedTuple):
    """BAAH 计划表某一位的取值规则。

    六个字段都是「三位一组」的整数列表，位置含义随字段而变（序号、地区、关卡、
    次数、开关），同一位在不同字段上的合法范围也不同，所以逐位列出规则表，
    校验与修正都从这张表读，避免两边各写一份后漂移。
    """

    title: str  # 这一位的中文名，报错信息里用
    minimum: int  # 允许的最小值
    maximum: Optional[int] = None  # 允许的最大值，None 表示不设上限
    allowed: tuple[int, ...] = ()  # 区间之外额外允许的取值（如关卡位的 -1）
    fallback: Optional[int] = None


BAAH_PLAN_KEY_SLOT_RULES: dict[str, tuple[BAAHSlotRule, ...]] = {
    "Event": (
        BAAHSlotRule("活动关卡序号", minimum=1),
        BAAHSlotRule("活动扫荡次数", minimum=-1),
        BAAHSlotRule("活动关卡开关", minimum=0, maximum=1, fallback=1),
    ),
    "Wanted": (
        BAAHSlotRule("地区", minimum=1, maximum=3),
        BAAHSlotRule("关卡", minimum=1, allowed=(-1,)),
        BAAHSlotRule("扫荡次数", minimum=-1),
        BAAHSlotRule("开关", minimum=0, maximum=1, fallback=1),
    ),
    "Special": (
        BAAHSlotRule("地区", minimum=1, maximum=2),
        BAAHSlotRule("关卡", minimum=1, allowed=(-1,)),
        BAAHSlotRule("扫荡次数", minimum=-1),
        BAAHSlotRule("开关", minimum=0, maximum=1, fallback=1),
    ),
    "Exchange": (
        BAAHSlotRule("学院", minimum=1, maximum=3),
        BAAHSlotRule("关卡", minimum=1, allowed=(-1,)),
        BAAHSlotRule("扫荡次数", minimum=-1),
        BAAHSlotRule("开关", minimum=0, maximum=1, fallback=1),
    ),
    "Hard": (
        BAAHSlotRule("章节", minimum=1),
        BAAHSlotRule("关卡", minimum=1),
        BAAHSlotRule("扫荡次数", minimum=-1),
        BAAHSlotRule("开关", minimum=0, maximum=1, fallback=1),
    ),
    "Normal": (
        BAAHSlotRule("章节", minimum=1),
        BAAHSlotRule("关卡", minimum=1),
        BAAHSlotRule("扫荡次数", minimum=-1),
        BAAHSlotRule("开关", minimum=0, maximum=1, fallback=1),
    ),
}


def _baah_slot_expected(rule: BAAHSlotRule) -> str:
    """把一位的合法取值说成一句人话，用于校验报错。"""

    if rule.allowed:
        extra = "、".join(str(item) for item in rule.allowed)
        return f"只能填 {extra} 或不小于 {rule.minimum}"
    if rule.maximum is None:
        return f"必须不小于 {rule.minimum}"
    if rule.minimum == rule.maximum:
        return f"只能是 {rule.minimum}"
    return f"只能填 {rule.minimum} 到 {rule.maximum}"


def baah_plan_slot_error(field: str, index: int, value: int) -> Optional[str]:
    """该位不合法时返回完整的中文原因（含字段、位次与期望取值），合法返回 None。"""

    rules = BAAH_PLAN_KEY_SLOT_RULES.get(field)
    # 列表比规则表短是合法的（可选位可以缺省），超出规则表的位不做判断。
    if rules is None or index >= len(rules):
        return None

    rule = rules[index]
    if value in rule.allowed:
        return None
    if value < rule.minimum or (rule.maximum is not None and value > rule.maximum):
        return (
            f"{field} 第 {index + 1} 位（{rule.title}）{_baah_slot_expected(rule)}，"
            f"当前为 {value}"
        )
    return None


def fix_baah_plan_slot(field: str, index: int, value: int) -> int:
    """把越界的一位修正到最近的合法值，规则表里没有的位原样返回。"""

    rules = BAAH_PLAN_KEY_SLOT_RULES.get(field)
    if rules is None or index >= len(rules):
        return value

    rule = rules[index]
    if value in rule.allowed:
        return value
    if value < rule.minimum:
        return rule.minimum if rule.fallback is None else rule.fallback
    if rule.maximum is not None and value > rule.maximum:
        return rule.maximum if rule.fallback is None else rule.fallback
    return value


BAAH_PLAN_KEY_MIN_LENGTH = 2


class BAAHPlanKey(BaseModel):
    """BAAH 计划表某一天要打的关卡。

    五类非活动关卡各自有三种状态，缺一不可地区分：
    缺席（字段不在 key 里）＝今天这一类不干预，BAAH 沿用自己配置文件里的关卡与开关；
    空数组＝今天不打这一类；有值（如 ``[3, -1, 1]``）＝今天按这个参数打这一类。
    因此默认值是 ``None`` 而不是某套具体关卡：补成默认值会把「不干预」静默变成
    「按默认关卡打」。
    """

    model_config = ConfigDict(extra="forbid")

    # 只兼容旧客户端的输入；配置加载和保存时移除，运行期不再从计划表下发活动关卡。
    Event: Optional[list[int]] = Field(
        default=None,
        max_length=3,
        description="活动关卡：关卡序号、扫荡次数；缺席表示今天不干预这一类",
    )
    Wanted: Optional[list[int]] = Field(
        default=None,
        max_length=4,
        description="悬赏通缉：地区、关卡、次数；缺席表示今天不干预这一类",
    )
    Special: Optional[list[int]] = Field(
        default=None,
        max_length=4,
        description="特殊任务：地区、关卡、次数；缺席表示今天不干预这一类",
    )
    Exchange: Optional[list[int]] = Field(
        default=None,
        max_length=4,
        description="学园交流会：学院、关卡、次数；缺席表示今天不干预这一类",
    )
    Hard: Optional[list[int]] = Field(
        default=None,
        max_length=4,
        description="困难图扫荡：章节、关卡、次数；缺席表示今天不干预这一类",
    )
    Normal: Optional[list[int]] = Field(
        default=None,
        max_length=4,
        description="普通图扫荡：章节、关卡、次数；缺席表示今天不干预这一类",
    )

    @field_validator("Event", "Wanted", "Special", "Exchange", "Hard", "Normal")
    @classmethod
    def validate_slot_values(
        cls, value: Optional[list[int]], info: ValidationInfo
    ) -> Optional[list[int]]:
        """逐位校验取值，并检查非空值的长度下限。

        只限制长度挡不住负数与 0，而它们会被原样传给 BAAH：悬赏通缉/特殊任务/
        学园交流会的关卡位 0 会让上游提示「关卡序号为0，无法扫荡」，困难图与普通
        图的关卡位走滚动选择，负数算不出坐标。规则表见 BAAH_PLAN_KEY_SLOT_RULES。

        ``None``（缺席）与空数组（今天不打这一类）都是合法取值，直接放行。
        """

        if value is None or len(value) == 0:
            return value

        if len(value) < BAAH_PLAN_KEY_MIN_LENGTH:
            raise ValueError(
                f"{info.field_name} 至少要写 {BAAH_PLAN_KEY_MIN_LENGTH} 位"
                f"（每一位含义固定），当前为 {value}"
            )

        for index, item in enumerate(value):
            error = baah_plan_slot_error(info.field_name, index, item)
            if error is not None:
                raise ValueError(error)
        return value


class WSEnvelope(BaseModel):
    """主 WebSocket 统一消息信封, 前后端均按 id + type 路由"""

    id: str = Field(
        ...,
        description="路由ID, 标识任务、请求或业务会话, 如 Main、TaskManager、任务UUID",
    )
    type: str = Field(
        ...,
        description="消息类别, 点分小写命名, 如 task.info.updated、backend.shutdown.ready",
    )
    data: Dict[str, JsonValue] = Field(
        default_factory=dict,
        description="消息数据, 关键消息使用对应的 WS*Data 模型构造",
    )

    @field_validator("id", "type")
    @classmethod
    def validate_route_field(cls, value: str) -> str:
        """路由字段必须为非空字符串，并统一去除首尾空白。"""

        normalized = value.strip()
        if not normalized:
            raise ValueError("WebSocket 路由 id/type 不能为空")
        return normalized


class WSTaskNoticeData(BaseModel):
    """任务提示消息数据 (type=task.notice)"""

    level: Literal["info", "warning", "error"] = Field(..., description="提示级别")
    message: str = Field(..., description="提示内容")
    messageKey: Optional[str] = Field(
        default=None, description="可选的前端翻译键；旧客户端仍使用 message"
    )


class WSTaskConfigDiscardedData(BaseModel):
    """配置会话改动被丢弃的消息数据 (type=task.config.discarded)

    reason 是机器可读原因，正文由前端按语言本地化：structure=队列结构或配置
    方案与基线不一致, unreadable=读取落盘配置失败, not_written=原生程序没写出
    完整配置。
    """

    reason: Literal["structure", "unreadable", "not_written"] = Field(
        ..., description="丢弃原因"
    )


class WSSystemNoticeData(BaseModel):
    """系统通知数据 (type=system.notice, id=Main)：启动期攒下、主连接建立后发出。"""

    level: Literal["info", "warning", "error"] = Field(..., description="提示级别")
    title: str = Field(..., description="标题")
    lines: List[str] = Field(default_factory=list, description="正文，每项一行")


class WSEmulatorOperationData(BaseModel):
    """模拟器操作结束通知 (type=emulator.operation.finished, id=EmulatorManager)

    启动 / 关闭是后台任务, 接口一调用就返回; 界面靠这条消息知道那一次操作什么时候真正结束。
    """

    emulatorId: str = Field(..., description="模拟器配置 ID")
    index: str = Field(..., description="设备索引 (Emulator 2.0 下是设备号)")
    operate: Literal["open", "close", "show", "hide"] = Field(
        ..., description="操作类型"
    )
    ok: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="失败原因; 成功时为空")


class WSAvdUpdateProgressData(BaseModel):
    """魔改 AVD 更新进度 (type=emulator2.avd-update.progress, id=EmulatorManager)

    下载、解包、核对、换上共用；``status`` 为 success / failed / idle 时这一次操作结束，
    界面据此重新取一次状态快照。
    """

    root: str = Field(..., description="魔改 AVD 根目录")
    stage: str = Field(
        ...,
        description=(
            "阶段: downloading / extracting / verifying / staged / installing / "
            "installed / failed"
        ),
    )
    status: str = Field(..., description="running / success / failed / idle")
    message: str = Field(default="", description="当前阶段的用户可读描述")
    percent: Optional[float] = Field(default=None, description="当前阶段进度百分比")
    downloadedBytes: Optional[int] = Field(
        default=None, description="已处理字节数（下载 / 解包 / 核对）"
    )
    totalBytes: Optional[int] = Field(default=None, description="本阶段总字节数")
    speedBytesPerSec: Optional[float] = Field(
        default=None, description="下载速度 (B/s)，首个采样点为 null"
    )


class WSTaskUserProgressData(BaseModel):
    """用户正在跑的任务进度（目前只有 MFW 给）。"""

    current: int = Field(..., description="当前是第几个任务, 从 1 起")
    total: int = Field(..., description="本次共几个任务")
    task: str = Field(..., description="当前任务名")


class WSTaskUserInfoData(BaseModel):
    """任务快照中的用户状态。"""

    user_id: str = Field(..., description="用户 ID")
    name: str = Field(..., description="用户名称")
    status: str = Field(..., description="用户执行状态")
    progress: Optional[WSTaskUserProgressData] = Field(
        default=None, description="正在跑的任务进度; 没有任务在跑或该专项不提供时为空"
    )


class WSTaskScriptInfoData(BaseModel):
    """任务快照中的脚本状态。"""

    script_id: str = Field(..., description="脚本 ID")
    name: str = Field(..., description="脚本名称")
    status: str = Field(..., description="脚本执行状态")
    userList: List[WSTaskUserInfoData] = Field(
        default_factory=list, description="脚本下的用户状态"
    )


class WSTaskCyclePreviewData(BaseModel):
    """循环运行的一个待运行条目。"""

    queueItemId: str = Field(..., description="队列项 ID")
    scriptId: str = Field(..., description="脚本 ID")
    scriptName: str = Field(..., description="脚本名称")
    nextRunAt: str = Field(..., description="下次运行时间, 格式为YYYY-MM-DD HH:MM:SS")
    isDue: bool = Field(default=False, description="是否已到运行时间")
    isRunning: bool = Field(default=False, description="是否正在运行")


class WSTaskInfoUpdatedData(BaseModel):
    """任务信息全量快照 (type=task.info.updated)。"""

    task_info: List[WSTaskScriptInfoData] = Field(
        default_factory=list, description="任务脚本与用户状态"
    )
    cycleNextList: List[WSTaskCyclePreviewData] = Field(
        default_factory=list, description="循环运行的待运行条目, 仅循环任务非空"
    )


class WSTaskLogUpdatedData(BaseModel):
    """任务日志更新 (type=task.log.updated), 按序号增量推送。"""

    log: str = Field(default="", description="append 为真时是新增片段, 否则是完整日志")
    seq: int = Field(default=0, description="推送序号, 每个任务独立, 从 1 起单调递增")
    append: bool = Field(default=False, description="是否追加到已有日志, 否则整体替换")
    firstLine: int = Field(
        default=1,
        description="log 第一行在完整日志里的行号, 供界面显示真实行号; append 时忽略",
    )


class WSTaskScriptIdentityData(BaseModel):
    """任务关联的脚本静态标识。"""

    scriptId: str = Field(..., description="脚本 ID")
    scriptType: str = Field(..., description="脚本类型键")


class TaskRuntimeSnapshotItem(BaseModel):
    """一个运行中任务的 HTTP 初始快照。"""

    taskId: str = Field(..., description="任务 ID")
    mode: Literal["AutoProxy", "ScriptConfig", "Update"] = Field(
        ..., description="脚本执行模式; 循环运行的脚本同样按 AutoProxy 执行"
    )
    isCycle: bool = Field(default=False, description="是否为循环运行任务")
    queueId: Optional[str] = Field(default=None, description="调度队列 ID")
    scriptId: Optional[str] = Field(default=None, description="脚本 ID")
    userId: Optional[str] = Field(default=None, description="用户 ID")
    stopping: bool = Field(default=False, description="任务是否正在停止")
    scripts: List[WSTaskScriptIdentityData] = Field(
        default_factory=list, description="任务关联的脚本静态标识"
    )
    task_info: List[WSTaskScriptInfoData] = Field(
        default_factory=list, description="任务脚本与用户状态"
    )
    cycleNextList: List[WSTaskCyclePreviewData] = Field(
        default_factory=list, description="循环运行的待运行条目, 仅循环任务非空"
    )
    log: str = Field(default="", description="已推送的脚本日志, 与下一条增量推送衔接")
    logSeq: int = Field(default=0, description="已推送日志对应的推送序号")
    logFirstLine: int = Field(default=1, description="快照日志首行在完整日志里的行号")


class TaskRuntimeSnapshot(BaseModel):
    """任务运行与定时队列 HTTP 初始快照。"""

    tasks: List[TaskRuntimeSnapshotItem] = Field(default_factory=list)
    scheduledScripts: List[WSTaskScriptIdentityData] = Field(
        default_factory=list, description="已启用定时队列关联的脚本静态标识"
    )


class TaskStatusOut(OutBase):
    """按 taskId 单点查询一个任务的状态, 不携带日志。"""

    taskId: str = Field(..., description="任务 ID")
    status: Literal["running", "success", "error", "cancelled"] = Field(
        ..., description="任务状态; running 为运行中, 其余为终态"
    )
    detail: Optional[str] = Field(default=None, description="任务结果描述")
    error: Optional[str] = Field(default=None, description="任务错误信息")
    mode: Optional[Literal["AutoProxy", "ScriptConfig", "Update"]] = Field(
        default=None, description="任务模式"
    )
    isCycle: bool = Field(default=False, description="是否为循环运行任务")
    queueId: Optional[str] = Field(default=None, description="调度队列 ID")
    scriptId: Optional[str] = Field(default=None, description="脚本 ID")
    userId: Optional[str] = Field(default=None, description="用户 ID")
    stopping: bool = Field(default=False, description="任务是否正在停止")
    finishedAt: Optional[str] = Field(
        default=None,
        description="任务结束时间, 格式为YYYY-MM-DD HH:MM:SS, 运行中为空",
    )


class WSTaskCompletedData(BaseModel):
    """任务完成消息数据 (type=task.completed)"""

    result: str = Field(..., description="任务结果描述")
    outcome: Literal["success", "error", "cancelled"] = Field(
        ..., description="机器可读的任务结果"
    )
    error: Optional[str] = Field(default=None, description="任务错误信息")
    task_info: List[WSTaskScriptInfoData] = Field(..., description="任务信息全量快照")


class WSTaskScriptStartedData(BaseModel):
    """一次脚本执行的本地关联信息；同一循环任务的每轮使用新的 runId。"""

    taskId: str
    runId: str
    scriptType: str
    mode: Literal["AutoProxy", "CycleRun"]


class WSTaskScriptFinishedData(WSTaskScriptStartedData):
    outcome: Literal[
        "success", "failed", "skipped", "no_user", "incomplete", "error", "cancelled"
    ]


class WSTaskCreatedData(BaseModel):
    """新任务创建通知数据 (id=TaskManager, type=task.created)"""

    taskId: str = Field(..., description="新任务ID")
    mode: Literal["AutoProxy", "ScriptConfig", "Update", "CycleRun"] = Field(
        ..., description="任务模式, 与创建请求一致"
    )
    scripts: List[WSTaskScriptIdentityData] = Field(
        default_factory=list, description="任务关联的脚本静态标识"
    )
    queueId: Optional[str] = Field(default=None, description="所属调度队列ID")
    taskName: Optional[str] = Field(default=None, description="任务名称")
    taskType: Optional[str] = Field(default=None, description="任务类型")


class WSPowerCountdownData(BaseModel):
    """电源倒计时更新数据 (id=Main, type=power.countdown.updated)"""

    operation: str = Field(..., description="待执行的电源操作")
    remaining: int = Field(..., description="剩余秒数")


class PowerCountdownSnapshot(BaseModel):
    """当前电源倒计时 HTTP 初始快照。"""

    active: bool = Field(default=False, description="是否正在倒计时")
    operation: Optional[str] = Field(default=None, description="待执行电源操作")
    remaining: int = Field(default=0, ge=0, description="剩余秒数")


class WSPowerSignData(BaseModel):
    """电源标志更新数据 (id=Main, type=power.sign.updated)"""

    signal: str = Field(..., description="电源操作信号")


class WSDisplayMonitorRectData(BaseModel):
    """一块显示器的工作区（去掉任务栏），物理像素、桌面坐标。"""

    left: int = Field(..., description="左边界")
    top: int = Field(..., description="上边界")
    right: int = Field(..., description="右边界")
    bottom: int = Field(..., description="下边界")


class WSDisplayDetachPromptData(BaseModel):
    """真实显示器回来了但有任务在跑, 问用户要不要拆虚拟屏 (id=Main, type=display.detach.prompt)

    虚拟屏是主显示器, 回来的真实屏只是第二块, 任务栏和主窗口都留在看不见的那块上,
    所以弹窗必须放到 `monitor` 指的那块屏上, 前端据此把它摆到该屏右下角。
    """

    returned: list[str] = Field(..., description="回来的真实显示设备名列表")
    monitor: Optional[WSDisplayMonitorRectData] = Field(
        default=None,
        description="回来那块屏的工作区; 读不到时为空, 前端自行挑一块非主显示器",
    )


class WSGameSignResultData(BaseModel):
    """游戏签到结果广播数据 (id=GameSign, type=gamesign.result.updated)

    result 为 JSON 序列化后的签到结果合并数据, 与 GET 快照接口返回一致。
    """

    result: str = Field(..., description="JSON 序列化的签到结果数据")


class WSUpdateProgressData(BaseModel):
    """更新下载进度数据 (id=Update, type=update.progress)"""

    downloaded_size: int = Field(..., description="已下载字节数")
    file_size: int = Field(..., description="文件总字节数")
    speed: float = Field(..., description="下载速度 (B/s)")
    source: str = Field(..., description="下载源")


class WSMaaFWEnvPrepareProgressData(BaseModel):
    """MFW 运行环境准备进度 (id=<scriptId>, type=maafw.env-prepare.progress)"""

    stage: str = Field(
        ...,
        description="阶段：resolving / creating_runtime / installing_runtime / runtime_ready / reused / failed 等",
    )
    status: str = Field(..., description="running / success / failed")
    message: str = Field(default="", description="当前阶段的用户可读描述")
    percent: Optional[float] = Field(
        default=None, description="总体进度百分比，未知时为 null"
    )
    log: Optional[str] = Field(default=None, description="本次事件附带的新增日志行")


class WSMaaFWProjectUpdateProgressData(BaseModel):
    """MFW 项目手动更新过程 (id=<scriptId>, type=maafw.project-update.progress)

    检查与应用两条路径共用；``stage="log"`` 只带一行新增日志，其余阶段带
    当前进度。速度由后端按已下载字节的时间差计算并节流，前端不必再算。
    """

    stage: str = Field(
        ...,
        description=(
            "阶段：checking / downloading / downloaded / extracting / plan_validated / "
            "staged / applying / post_validating / committed / rolled_back / "
            "completed / failed / log"
        ),
    )
    status: str = Field(..., description="running / success / failed")
    message: str = Field(default="", description="当前阶段的用户可读描述")
    log: Optional[str] = Field(default=None, description="本次事件附带的新增日志行")
    logLevel: Optional[str] = Field(
        default=None,
        description="新增日志行的级别：alert 为要用户留意的行（面板标红），普通行为 null",
    )
    percent: Optional[float] = Field(
        default=None,
        description="当前阶段进度百分比（下载 / 解压 / 覆盖），未知时为 null",
    )
    downloadedBytes: Optional[int] = Field(default=None, description="已下载字节数")
    totalBytes: Optional[int] = Field(
        default=None, description="更新包总字节数，服务端未给出时为 null"
    )
    speedBytesPerSec: Optional[float] = Field(
        default=None, description="下载速度 (B/s)，首个采样点为 null"
    )
    packageKind: Optional[str] = Field(
        default=None,
        description="更新包类型：full 全量 / incremental 增量，未知时为 null",
    )
    appliedFiles: Optional[int] = Field(default=None, description="已覆盖文件数")
    totalFiles: Optional[int] = Field(default=None, description="本次要覆盖的文件总数")
    extractedFiles: Optional[int] = Field(
        default=None, description="解压阶段：已解压的文件数"
    )
    extractTotalFiles: Optional[int] = Field(
        default=None, description="解压阶段：更新包里的文件总数（不含目录条目）"
    )
    extractedBytes: Optional[int] = Field(
        default=None, description="解压阶段：已写出的字节数"
    )
    extractTotalBytes: Optional[int] = Field(
        default=None, description="解压阶段：更新包声明的解压后总字节数"
    )


class WSUpdateCompletedData(BaseModel):
    """更新下载完成数据 (id=Update, type=update.completed)。"""

    file: str = Field(..., description="已下载更新包路径")


class WSUpdateFailedData(BaseModel):
    """更新下载失败数据 (id=Update, type=update.failed)。"""

    message: str = Field(..., description="失败原因")


class HSRDynamicStageM7A(BaseModel):
    instanceType: Optional[str] = Field(default=None, description="M7A 副本类型")
    instanceName: Optional[str] = Field(default=None, description="M7A 副本名称")


class HSRDynamicStageSRA(BaseModel):
    id: Optional[str] = Field(default=None, description="SRA 体力任务 ID")
    level: Optional[int] = Field(default=None, description="SRA 体力任务层级")


class HSRDynamicStageOption(BaseModel):
    label: str = Field(..., description="副本展示名称")
    detail: Optional[str] = Field(default=None, description="副本说明")
    value: str = Field(..., description="副本选项值")
    categoryKey: str = Field(..., description="副本分类键")
    categoryLabel: str = Field(..., description="副本分类名称")
    cost: Optional[int] = Field(default=None, description="单次体力消耗")
    maxCount: Optional[int] = Field(default=None, description="最大执行次数")
    m7a: Optional[HSRDynamicStageM7A] = Field(default=None, description="M7A 原生字段")
    sra: Optional[HSRDynamicStageSRA] = Field(default=None, description="SRA 原生字段")


class HSRDynamicStageCategory(BaseModel):
    categoryKey: str = Field(..., description="副本分类键")
    categoryLabel: str = Field(..., description="副本分类名称")
    cost: Optional[int] = Field(default=None, description="单次体力消耗")
    maxCount: Optional[int] = Field(default=None, description="最大执行次数")
    options: List[HSRDynamicStageOption] = Field(
        default_factory=list, description="副本选项列表"
    )


class HSRStageOptionsData(BaseModel):
    engine: Literal["M7A", "SRA"] = Field(..., description="体力副本执行脚本")
    source: Optional[str] = Field(default=None, description="选项来源文件或目录")
    categories: List[HSRDynamicStageCategory] = Field(
        default_factory=list, description="体力副本分类列表"
    )


class HSRCapabilityTask(BaseModel):
    key: str = Field(..., description="任务键")
    name: str = Field(..., description="任务名称")
    phase: Literal["daily", "weekly"] = Field(..., description="任务阶段")
    description: str = Field(default="", description="任务说明")
    engines: List[Literal["M7A", "SRA"]] = Field(
        default_factory=list, description="支持的执行引擎"
    )
    strategies: Dict[str, List[str]] = Field(
        default_factory=dict, description="引擎策略"
    )


class HSRCapabilityAdapter(BaseModel):
    engine: Literal["M7A", "SRA"] = Field(..., description="原生脚本引擎")
    display_name: str = Field(..., description="引擎展示名称")
    version: Optional[str] = Field(default=None, description="引擎版本")
    capabilities: Dict[str, Any] = Field(
        default_factory=dict, description="引擎能力集合"
    )
    ready: bool = Field(default=False, description="引擎是否就绪")
    ready_reason: Optional[str] = Field(default=None, description="引擎状态说明")


class HSRCapabilitiesData(BaseModel):
    revision: str = Field(default="old-dev", description="契约版本")
    available: bool = Field(default=False, description="HSR 是否可用")
    unavailable_reason: Optional[str] = Field(default=None, description="不可用原因")
    candidate_engines: List[Literal["M7A", "SRA"]] = Field(
        default_factory=lambda: ["M7A", "SRA"], description="候代引擎"
    )
    configured_engines: List[Literal["M7A", "SRA"]] = Field(
        default_factory=list, description="已配置引擎"
    )
    effective_engines: List[Literal["M7A", "SRA"]] = Field(
        default_factory=list, description="有效引擎"
    )
    adapters: List[HSRCapabilityAdapter] = Field(
        default_factory=list, description="引擎适配器"
    )
    tasks: List[HSRCapabilityTask] = Field(default_factory=list, description="任务列表")
    warnings: List[str] = Field(default_factory=list, description="兼容性警告")
    browser: Optional[Dict[str, Any]] = Field(default=None, description="浏览器能力")


class HSRUpdateData(BaseModel):
    engine: Literal["M7A", "SRA"] = Field(..., description="外部脚本引擎")
    checked: bool = Field(default=False, description="是否成功查到版本信息")
    updated: bool = Field(default=False, description="本次是否真的完成了更新")
    current_version: Optional[str] = Field(default=None, description="当前已安装版本")
    latest_version: Optional[str] = Field(default=None, description="可用的最新版本")
    update_available: bool = Field(default=False, description="是否有新版本")
    installable: bool = Field(
        default=False, description="新版本能否从当前下载源安装（CDK 失效时为假）"
    )
    message: str = Field(default="", description="面向用户的结果说明")


class HSRCloudLoginData(BaseModel):
    logged_in: bool = Field(default=False, description="是否确认已登录")
    last_login: Optional[str] = Field(
        default=None, description="本次确认已登录的时间（ISO 8601）"
    )
    message: str = Field(default="", description="面向用户的结果说明")


class HSRManagedFieldVisibleWhen(BaseModel):
    key: str = Field(..., description="依赖的同模块字段键")
    values: List[Any] = Field(
        default_factory=list, description="该字段取这些值之一时才显示"
    )


class HSRManagedField(BaseModel):
    key: str = Field(..., description="字段键")
    label: str = Field(default="", description="字段名称")
    type: str = Field(default="string", description="字段类型")
    value: Any = Field(default=None, description="字段当前值")
    description: Optional[str] = Field(default=None, description="字段说明")
    options: List[Any] = Field(default_factory=list, description="字段选项")
    minimum: Optional[float] = Field(default=None, description="最小值")
    maximum: Optional[float] = Field(default=None, description="最大值")
    readonly: bool = Field(default=False, description="是否只读")
    group: Literal[
        "common", "team", "support", "activity", "replenish", "reroll", "misc"
    ] = Field(
        default="common",
        description="字段分组：common 平铺，其余各成一个默认收起的折叠面板",
    )
    overridden: bool = Field(
        default=False,
        description="当前计划（plan_owner 指向的那份）对该字段有生效中的覆盖值",
    )
    native_value: Any = Field(default=None, description="引擎原生配置里的值")
    visible_when: Optional[HSRManagedFieldVisibleWhen] = Field(
        default=None,
        description="只有同模块同引擎里字段 key 的当前值在 values 中时才显示",
    )


class HSRManagedDroppedOverride(BaseModel):
    key: str = Field(..., description="被忽略的 Managed.Options 覆盖键")
    reason: Literal["unknown", "type"] = Field(
        ...,
        description=(
            "忽略原因：unknown=当前原生配置没有该字段或该字段已不由 MAS 托管；"
            "type=保存的值类型与原生配置不一致"
        ),
    )
    value: Any = Field(default=None, description="用户保存的覆盖值")
    message: str = Field(default="", description="人类可读说明")


class HSRManagedForm(BaseModel):
    key: Optional[str] = Field(default=None, description="任务键")
    engine: Literal["M7A", "SRA"] = Field(..., description="表单引擎")
    fields: List[HSRManagedField] = Field(default_factory=list, description="表单字段")
    source: Optional[str] = Field(default=None, description="字段来源")
    warnings: List[str] = Field(
        default_factory=list,
        description="表单级人类可读提示（如缺少配置说明文件），不含失效覆盖记录",
    )
    dropped_overrides: List[HSRManagedDroppedOverride] = Field(
        default_factory=list,
        description="在当前原生配置中失效、运行时会被忽略的 Managed.Options 覆盖值",
    )


class HSRManagedTask(BaseModel):
    key: str = Field(..., description="任务键")
    name: str = Field(..., description="任务名称")
    phase: Literal["daily", "weekly"] = Field(..., description="任务阶段")
    description: str = Field(default="", description="任务说明")
    engines: List[Literal["M7A", "SRA"]] = Field(
        default_factory=list, description="支持的执行引擎"
    )
    strategies: Dict[str, List[str]] = Field(
        default_factory=dict, description="引擎策略"
    )
    forms: Dict[str, HSRManagedForm] = Field(
        default_factory=dict, description="动态字段表单"
    )


class HSRManagedConfigData(BaseModel):
    revision: str = Field(default="old-dev", description="契约版本")
    plan_owner: Literal["script", "user"] = Field(
        default="script",
        description=(
            "任务计划的归属：script=脚本共享计划（保存到脚本配置），"
            "user=该用户自己的计划（保存到用户配置）"
        ),
    )
    tasks: List[HSRManagedTask] = Field(default_factory=list, description="托管任务")
    task_mapping: Dict[str, Literal["M7A", "SRA"]] = Field(
        default_factory=dict, description="任务到引擎映射"
    )
    warnings: List[str] = Field(default_factory=list, description="兼容性警告")


class HSRSRAProfile(BaseModel):
    id: str = Field(..., description="档案 id（文件名，不含扩展名）")
    path: str = Field(..., description="档案文件路径")
    selected: bool = Field(default=False, description="是否为当前生效的档案")


class HSRSRAProfilesData(BaseModel):
    engine: Literal["SRA"] = Field(default="SRA", description="原生脚本引擎")
    root: str = Field(..., description="档案目录（%APPDATA%/SRA/configs）")
    available: bool = Field(
        default=False, description="档案目录是否可读且至少有一份档案"
    )
    unavailable_reason: Optional[str] = Field(default=None, description="不可用原因")
    configured: str = Field(default="", description="脚本配置的档案 id；空串表示自动")
    auto_id: str = Field(..., description="自动模式会选中的档案 id")
    selected: str = Field(..., description="当前实际生效的档案 id")
    fallback: bool = Field(
        default=False, description="配置的档案不存在、已回退到自动选择"
    )
    fallback_reason: Optional[str] = Field(default=None, description="回退说明")
    profiles: List[HSRSRAProfile] = Field(default_factory=list, description="可选档案")


class MaaFWGamePackageData(BaseModel):
    reason: Literal["resolved", "not-found", "ambiguous"] = Field(
        ..., description="推断结果：唯一 / 没找到 / 多个互相矛盾"
    )
    package: str = Field(default="", description="推出来的包名，仅 resolved 时非空")
    candidates: List[str] = Field(
        default_factory=list, description="ambiguous 时列出全部候选，供界面提示"
    )


class MaaFWAdbEmulatorExtraCapabilityInfo(BaseModel):
    screencap: bool = Field(default=False, description="ADB EmulatorExtras 截图能力")
    input: bool = Field(default=False, description="ADB EmulatorExtras 输入能力")


class MaaFWControlCapabilitiesInfo(BaseModel):
    emulatorExtras: Dict[str, MaaFWAdbEmulatorExtraCapabilityInfo] = Field(
        default_factory=dict, description="按模拟器类型列出的 EmulatorExtras 能力"
    )


class MaaFWProjectInfo(BaseModel):
    name: str = Field(..., description="项目标识")
    label: Optional[str] = Field(default=None, description="项目显示名称")
    title: Optional[str] = Field(default=None, description="项目标题")
    version: Optional[str] = Field(default=None, description="项目版本")
    github: Optional[str] = Field(default=None, description="项目 GitHub 地址")
    mirrorchyanRid: Optional[str] = Field(default=None, description="MirrorChyan RID")
    mirrorchyanMultiplatform: Optional[bool] = Field(
        default=None, description="MirrorChyan 是否多平台"
    )
    description: Optional[str] = Field(default=None, description="项目描述")
    icon: Optional[str] = Field(default=None, description="项目图标路径")


class MaaFWControllerInfo(BaseModel):
    name: str = Field(..., description="控制器名称")
    label: Optional[str] = Field(default=None, description="控制器显示名称")
    type: str = Field(..., description="控制器类型")
    description: Optional[str] = Field(default=None, description="控制器描述")
    icon: Optional[str] = Field(default=None, description="控制器图标路径")
    option: List[str] = Field(default_factory=list, description="控制器选项")
    permissionRequired: bool = Field(default=False, description="是否需要管理员权限")


class MaaFWResourceInfo(BaseModel):
    name: str = Field(..., description="资源名称")
    label: Optional[str] = Field(default=None, description="资源显示名称")
    description: Optional[str] = Field(default=None, description="资源描述")
    icon: Optional[str] = Field(default=None, description="资源图标路径")
    path: List[str] = Field(default_factory=list, description="资源路径列表")
    controller: List[str] = Field(default_factory=list, description="适用控制器列表")
    option: List[str] = Field(default_factory=list, description="资源选项")


class MaaFWGroupInfo(BaseModel):
    name: str = Field(..., description="任务分组名称")
    label: Optional[str] = Field(default=None, description="任务分组显示名称")
    description: Optional[str] = Field(default=None, description="任务分组描述")
    icon: Optional[str] = Field(default=None, description="任务分组图标路径")
    defaultExpand: bool = Field(default=True, description="是否默认展开")


class MaaFWSettingInfo(BaseModel):
    name: str = Field(..., description="设置分组名称")
    label: Optional[str] = Field(default=None, description="设置分组显示名称")
    description: Optional[str] = Field(default=None, description="设置分组描述")
    icon: Optional[str] = Field(default=None, description="设置分组图标路径")
    option: List[str] = Field(default_factory=list, description="设置分组选项")
    defaultExpand: bool = Field(default=True, description="是否默认展开")


class MaaFWTaskInfo(BaseModel):
    name: str = Field(..., description="任务名称")
    label: Optional[str] = Field(default=None, description="任务显示名称")
    entry: str = Field(..., description="MaaFW pipeline 入口")
    description: Optional[str] = Field(default=None, description="任务描述")
    icon: Optional[str] = Field(default=None, description="任务图标路径")
    group: List[str] = Field(default_factory=list, description="所属分组")
    controller: List[str] = Field(default_factory=list, description="适用控制器")
    resource: List[str] = Field(default_factory=list, description="适用资源")
    option: List[str] = Field(default_factory=list, description="任务选项")
    defaultCheck: bool = Field(default=False, description="是否默认勾选")
    repeatCount: int = Field(
        default=1,
        description="加入任务队列时展开成几份（interface 的 repeatable / repeat_count）",
    )
    unselectableReason: Optional[str] = Field(
        default=None,
        description="特调声明该任务不可选时的原因（不进「添加任务」与预设，运行时跳过）；可选任务为 null",
    )


class MaaFWOptionCaseInfo(BaseModel):
    name: str = Field(..., description="选项 case 名称")
    label: Optional[str] = Field(default=None, description="选项 case 显示名称")
    description: Optional[str] = Field(default=None, description="选项 case 描述")
    icon: Optional[str] = Field(default=None, description="选项 case 图标路径")
    option: List[str] = Field(default_factory=list, description="子选项列表")


class MaaFWOptionInputInfo(BaseModel):
    name: str = Field(..., description="输入项名称")
    label: Optional[str] = Field(default=None, description="输入项显示名称")
    description: Optional[str] = Field(default=None, description="输入项描述")
    icon: Optional[str] = Field(default=None, description="输入项图标路径")
    default: Optional[str] = Field(default=None, description="默认值")
    pipelineType: Optional[str] = Field(default=None, description="pipeline 覆盖值类型")
    verify: Optional[str] = Field(default=None, description="输入校验正则")
    verifyError: Optional[str] = Field(default=None, description="输入校验提示")
    patternMsg: Optional[str] = Field(default=None, description="输入校验提示")
    password: bool = Field(
        default=False, description="是否为密码 / 密钥字段（界面掩码，配置加密存储）"
    )


class MaaFWOptionHotkeyInfo(BaseModel):
    name: str = Field(..., description="热键项名称")
    label: Optional[str] = Field(default=None, description="热键项显示名称")
    description: Optional[str] = Field(default=None, description="热键项描述")
    default: Optional[str] = Field(default=None, description="默认热键")
    modifierCount: int = Field(
        default=0,
        description="项目 pipeline 用到的修饰键个数（0–2）：录制的组合键须恰好这么多修饰键",
    )


class MaaFWOptionInfo(BaseModel):
    name: str = Field(..., description="选项名称")
    type: str = Field(..., description="选项类型")
    label: Optional[str] = Field(default=None, description="选项显示名称")
    description: Optional[str] = Field(default=None, description="选项描述")
    icon: Optional[str] = Field(default=None, description="选项图标路径")
    controller: List[str] = Field(default_factory=list, description="适用控制器")
    resource: List[str] = Field(default_factory=list, description="适用资源")
    cases: List[MaaFWOptionCaseInfo] = Field(
        default_factory=list, description="可选 case"
    )
    inputs: List[MaaFWOptionInputInfo] = Field(
        default_factory=list, description="输入项"
    )
    hotkeys: List[MaaFWOptionHotkeyInfo] = Field(
        default_factory=list, description="热键项"
    )
    defaultCase: Optional[Union[str, List[str]]] = Field(
        default=None, description="默认 case"
    )
    minCount: Optional[int] = Field(
        default=None, description="checkbox 最少选择数，未限制为 None"
    )
    maxCount: Optional[int] = Field(
        default=None, description="checkbox 最多选择数，未限制为 None"
    )


class MaaFWTaskSnapshot(BaseModel):
    """ProjectInterface 预设转换出的任务快照，前三个字段的键都是任务 name。

    与用户自己的任务快照同构。用户队列允许同一个任务加多份，那边的键是任务
    实例 id（首份就是任务 name）；预设里的重复任务会被折叠，因此这里只有 name。
    全局选项（global_option 及其子选项）的值不在 taskOptions 里，在 globalOptions。
    """

    taskOrder: List[str] = Field(default_factory=list, description="任务 name 顺序")
    taskChecked: Dict[str, bool] = Field(
        default_factory=dict, description="任务勾选状态"
    )
    taskOptions: Dict[str, Dict[str, Union[str, List[str], Dict[str, str]]]] = Field(
        default_factory=dict, description="任务选项值"
    )
    globalOptions: Dict[str, Union[str, List[str], Dict[str, str]]] = Field(
        default_factory=dict, description="全局选项值（预设里写了的才有）"
    )


class MaaFWPresetInfo(BaseModel):
    name: str = Field(..., description="预设名称")
    label: Optional[str] = Field(default=None, description="预设显示名称")
    description: Optional[str] = Field(default=None, description="预设描述")
    taskCount: int = Field(default=0, description="预设声明任务数")
    checkedCount: int = Field(default=0, description="转换后勾选任务数")
    snapshot: MaaFWTaskSnapshot = Field(..., description="预设转换后的任务快照")


class MaaFWInterfacePreviewData(BaseModel):
    """MaaFW interface 预览数据。

    外层字段在宿主 schema 中明确建模；各列表条目的字段与 Phase 1
    ``build_interface_preview_data`` 返回的 MaaFWInterfacePreviewData 契约一致。
    """

    path: str = Field(..., description="MaaFW 项目根目录")
    project: MaaFWProjectInfo = Field(..., description="项目基础信息")
    globalOption: List[str] = Field(default_factory=list, description="全局选项")
    controlCapabilities: MaaFWControlCapabilitiesInfo = Field(
        default_factory=MaaFWControlCapabilitiesInfo,
        description="MaaFW control capabilities",
    )
    controllers: List[MaaFWControllerInfo] = Field(
        default_factory=list, description="控制器列表"
    )
    resources: List[MaaFWResourceInfo] = Field(
        default_factory=list, description="资源列表"
    )
    groups: List[MaaFWGroupInfo] = Field(
        default_factory=list, description="任务分组列表"
    )
    settings: List[MaaFWSettingInfo] = Field(
        default_factory=list, description="设置分组列表"
    )
    tasks: List[MaaFWTaskInfo] = Field(default_factory=list, description="任务列表")
    options: List[MaaFWOptionInfo] = Field(default_factory=list, description="选项列表")
    presets: List[MaaFWPresetInfo] = Field(default_factory=list, description="预设列表")
    importCount: int = Field(default=0, description="根 interface import 数量")
    agentCount: int = Field(default=0, description="agent 配置数量")


class MaaFWEmbeddedSourceItem(BaseModel):
    scriptId: str = Field(..., description="可作为克隆来源的 MFW 脚本 ID")
    name: str = Field(default="", description="脚本名")
    type: str = Field(default="MaaFW", description="脚本类型（MaaFW / M9A / MSS）")
    projectName: str = Field(default="", description="副本 interface 里的项目名")
    version: str = Field(default="", description="副本 interface 里的版本")
    busy: bool = Field(default=False, description="源脚本正在运行，此刻不能克隆")


class MaaFWEmbeddedProjection(BaseModel):
    sourceSizeBytes: int = Field(default=0, description="来源目录字节数")
    payloadSizeBytes: int = Field(default=0, description="副本字节数")
    savedBytes: int = Field(default=0, description="省下的字节数")
    savedPercent: float = Field(default=0.0, description="省下的比例")
    excludedCount: int = Field(default=0, description="排除的路径数")
    excludedReasons: Dict[str, str] = Field(
        default_factory=dict, description="排除路径与原因（最多 128 条）"
    )
    excludedTruncated: bool = Field(default=False, description="排除清单是否被截断")
    shellFamilies: List[str] = Field(default_factory=list, description="移除的外壳家族")
    conservative: bool = Field(default=False, description="是否退回保守模式")
    warnings: List[str] = Field(default_factory=list, description="投影警告")
    bundledMaaFWVersion: str = Field(
        default="",
        description="项目自带 MaaFramework 的版本（PEP 440）；原生库目录原样带入副本",
    )
    bundledPythonVersion: str = Field(
        default="",
        description="agent 自带 Python 的大版本（如 3.13）；解释器目录原样带入副本",
    )


class MaaFWEmbeddedStatusData(BaseModel):
    copyPath: str = Field(default="", description="副本目录（只读展示）")
    copyHealthy: bool = Field(default=False, description="副本是否完整")
    sourcePath: str = Field(default="", description="来源目录（Info.Path）")
    sourceExists: bool = Field(
        default=False,
        description="来源目录是否还在；导入完成后来源可以删，不在只是不能重新导入",
    )
    sourceVersion: str = Field(default="", description="导入时来源的 interface 版本")
    importedAt: str = Field(default="", description="导入时间")
    report: Optional[MaaFWEmbeddedProjection] = Field(
        default=None, description="投影报告"
    )
    followSourceSyncedAt: str = Field(
        default="",
        description="跟随来源目录（开发者模式）下视图上次从来源目录同步的时间；没同步过为空",
    )
    sourceForm: bool = Field(
        default=False,
        description="项目按源码形态导入（interface 在 assets/、Agent 在源码目录）：始终跟随来源目录，不做项目更新",
    )


class MaaFWShellInstanceItem(BaseModel):
    id: str = Field(..., description="实例 ID（导入时原样传回）")
    name: str = Field(..., description="外壳里的实例名")
    userName: str = Field(
        ...,
        description="导入后的用户名（与已有用户、同名实例重名时带「 (2)」这类后缀）",
    )
    source: Literal["MFAAvalonia", "MXU", "MFW-PyQt6"] = Field(
        ..., description="实例来自哪个外壳"
    )
    active: bool = Field(default=False, description="是否是外壳上次使用的实例")
    taskCount: int = Field(default=0, description="实例队列里勾选着的任务数")
    controller: str = Field(default="", description="实例的控制方式（给人看的名字）")
    resource: str = Field(default="", description="实例的资源（给人看的名字）")
    hotkeys: Dict[str, Dict[str, str]] = Field(
        default_factory=dict,
        description=(
            "实例里记着的键位：{hotkey 选项名: {字段名: 组合键}}，只含 interface 里声明过的"
            "hotkey 选项与字段、非空的值（全局 / 资源级在前，任务级覆盖），不与默认值比较；"
            "读不到 interface 时为空"
        ),
    )
    sourceDir: str = Field(
        default="", description="扫到这份配置的目录（同一次列表里都一样）"
    )


class MaaFWShellInstanceImportItem(BaseModel):
    instanceId: str = Field(..., description="实例 ID")
    instanceName: str = Field(default="", description="外壳里的实例名")
    success: bool = Field(default=False, description="是否导入成功")
    userId: str = Field(
        default="",
        description="用户 ID：建成新用户时就是它，覆盖已有用户时是那个用户",
    )
    name: str = Field(default="", description="用户名")
    importedTaskCount: int = Field(default=0, description="导入进队列的任务数")
    skipped: List[str] = Field(
        default_factory=list, description="当前项目里对不上、没导入的任务 / 选项 / 取值"
    )
    error: str = Field(default="", description="失败原因（成功时为空）")


class MaaFWProjectUpdateData(BaseModel):
    checked: bool = Field(default=False, description="是否完成了一次更新检查")
    updated: bool = Field(default=False, description="本次是否实际应用了更新")
    updateAvailable: bool = Field(default=False, description="是否存在更新版本")
    installable: bool = Field(default=False, description="更新版本是否有可安装的更新包")
    currentVersion: Optional[str] = Field(
        default=None, description="interface 声明的当前项目版本"
    )
    latestVersion: Optional[str] = Field(default=None, description="发现的最新项目版本")
    source: Optional[str] = Field(
        default=None, description="实际更新包来源：mirrorchyan / github；未下载时为空"
    )
    versionName: Optional[str] = Field(
        default=None, description="Mirror 酱返回的最新版本名；查版本失败时为空"
    )
    cdkStatus: Optional[str] = Field(
        default=None,
        description="CDK 状态：ok / absent / expired / invalid / quota / mismatched / blocked",
    )
    cdkMessage: Optional[str] = Field(
        default=None, description="CDK 状态对应的用户提示；ok / absent 时为空"
    )
    cdkExpiredTime: Optional[int] = Field(
        default=None, description="Mirror 酱返回的 CDK 过期时间（unix 秒），仅 ok 时有"
    )
    skippedReason: Optional[str] = Field(
        default=None, description="未执行更新的原因（无 rid、已最新、锁被占等）"
    )


class MaaFWMirrorCdkData(BaseModel):
    status: str = Field(
        ...,
        description=(
            "CDK 状态：ok / absent（没填）/ unsupported（项目没声明 mirrorchyan_rid 或读不了）/ "
            "error（查询失败）/ expired / invalid / quota / mismatched / blocked"
        ),
    )
    expiredTime: Optional[int] = Field(
        default=None,
        description="Mirror 酱返回的 CDK 到期时间（unix 秒）；没返回时为空",
    )


class MaaFWAgentEnvInfo(BaseModel):
    childExec: str = Field(..., description="interface 声明的 agent child_exec")
    executable: str = Field(..., description="实际使用的解释器或可执行文件")
    runtimeKind: Optional[str] = Field(
        default=None,
        description="agent 运行时类型：project_python / project_binary / "
        "isolated_venv / embedded / external",
    )
    isolatedVenvPath: Optional[str] = Field(
        default=None, description="该 agent 专属隔离 venv 路径"
    )
    fallbackReason: Optional[str] = Field(
        default=None, description="回退原因，供用户排查"
    )


class MaaFWAgentEnvPrepareData(BaseModel):
    path: str = Field(..., description="MFW 项目根目录")
    agentCount: int = Field(default=0, description="agent 数量")
    agents: List[MaaFWAgentEnvInfo] = Field(
        default_factory=list, description="各 agent 的运行环境信息"
    )
    logs: List[str] = Field(default_factory=list, description="准备过程日志")
    runtimeId: Optional[str] = Field(
        default=None, description="Runtime Pool 中的 runtime ID"
    )
    poolId: Optional[str] = Field(default=None, description="Runtime Pool 身份")
    pythonExecutable: Optional[str] = Field(
        default=None, description="Runner 使用的 Python 解释器"
    )
    venvPath: Optional[str] = Field(default=None, description="Runner 虚拟环境路径")
    maafwVersion: Optional[str] = Field(
        default=None, description="实际解析到的 MaaFramework 版本"
    )
    cached: bool = Field(
        default=False,
        description="是否命中指纹缓存，命中时本次未做实际准备",
    )
    previouslyPrepared: bool = Field(
        default=False,
        description="本次准备前该项目已有过就绪环境，即这次是更新而非首次准备",
    )
    preparedAt: Optional[str] = Field(
        default=None, description="缓存命中时，上一次实际完成准备的时间"
    )


class WebhookIndexItem(BaseModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal["Webhook"] = Field(..., description="配置类型")


class ObsReplayCheckOut(OutBase):
    connected: bool = False
    replayActive: bool = False
    version: str = ""
    directory: str = ""


class WebhookInBase(BaseModel):
    scriptId: Optional[str] = Field(
        default=None, description="所属脚本ID, 获取全局设置的Webhook数据时无需携带"
    )
    userId: Optional[str] = Field(
        default=None, description="所属用户ID, 获取全局设置的Webhook数据时无需携带"
    )


class WebhookGetIn(WebhookInBase):
    webhookId: Optional[str] = Field(
        default=None, description="Webhook ID, 未携带时表示获取所有Webhook数据"
    )


ConfigDataT = TypeVar("ConfigDataT")


class WebhookGetOut(OutBase, Generic[ConfigDataT]):
    index: List[WebhookIndexItem] = Field(..., description="Webhook索引列表")
    data: Dict[str, ConfigDataT] = Field(
        ..., description="Webhook数据字典, key来自于index列表的uid"
    )


class WebhookCreateOut(OutBase, Generic[ConfigDataT]):
    webhookId: str = Field(..., description="新创建的Webhook ID")
    data: ConfigDataT = Field(..., description="Webhook配置数据")


class WebhookUpdateIn(WebhookInBase, Generic[ConfigDataT]):
    webhookId: str = Field(..., description="Webhook ID")
    data: ConfigDataT = Field(..., description="Webhook更新数据")


class WebhookDeleteIn(WebhookInBase):
    webhookId: str = Field(..., description="Webhook ID")


class BlueArchiveActivityIn(BaseModel):
    """碧蓝档案活动数据查询参数"""

    line_type: Literal["JP", "Globle", "CN"] = Field(
        ..., description="服务器：JP 日服 / Globle 国际服 / CN 国服（原文拼写如此）"
    )
    page: int = Field(default=1, ge=1, le=20, description="页码，从 1 开始")
    page_size: int = Field(default=50, ge=1, le=100, description="每页条数")


class MSSPlanKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    TribulationStage: str = Field(
        default=MSS_DEFAULT_TRIBULATION_STAGE,
        pattern="^(?:" + "|".join(map(re.escape, MSS_TRIBULATION_STAGES)) + ")$",
        description="悬赏试炼关卡（取值见 constants.MSS_TRIBULATION_STAGES）",
    )
    SkipDifficulty: bool = Field(default=False, description="悬赏试炼是否跳过难度选择")
    Difficulty: int = Field(default=1, ge=1, le=99, description="悬赏试炼难度")
    ConsumeAllEnergy: bool = Field(
        default=False, description="悬赏试炼是否消耗所有干劲"
    )
    FightTimes: int = Field(default=1, ge=1, le=99, description="自定义快速作战次数")


# 脚本管理多个路由共用的请求契约。


class ScriptDeleteIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")


class UserInBase(BaseModel):
    scriptId: str = Field(..., description="所属脚本ID")


class UserDeleteIn(UserInBase):
    userId: str = Field(..., description="用户ID")


__all__ = [
    "ScriptDeleteIn",
    "UserInBase",
    "UserDeleteIn",
    "HistoryCounterValue",
    "HistoryCounterStatistic",
    "HistorySnapshotStatistic",
    "HistoryKeyedSnapshotStatistic",
    "HistoryStatistic",
    "HistoryStatus",
    "HistoryAttachmentKind",
    "HistoryAttachmentInput",
    "HistoryWrite",
    "HistoryStorageIssue",
    "HistoryAttachment",
    "HistoryIndexItem",
    "HistoryRecord",
    "HistoryDetail",
    "HistoryAttachmentFile",
    "HistoryAggregationItem",
    "HistoryAggregateError",
    "HistoryAggregate",
    "HistoryBucket",
    "HistoryRecordQuery",
    "HistoryUserOverview",
    "HistoryCleanupReport",
    "HistoryBackupSnapshot",
    "OutBase",
    "TagItem",
    "ComboBoxItem",
    "ComboBoxOut",
    "VirtualDisplayCheckResultItem",
    "VirtualDisplayCheckOut",
    "DeviceInfo",
    "UpdateDownloadSnapshot",
    "EmulatorDeleteIn",
    "PlanComboxConsumer",
    "MaaEndAutoEssencePlanKey",
    "MaaEndProtocolSpacePlanKey",
    "MaaEndPlanKey",
    "BAAHSlotRule",
    "BAAH_PLAN_KEY_SLOT_RULES",
    "baah_plan_slot_error",
    "fix_baah_plan_slot",
    "BAAH_PLAN_KEY_MIN_LENGTH",
    "BAAHPlanKey",
    "WSEnvelope",
    "WSTaskNoticeData",
    "WSTaskConfigDiscardedData",
    "WSSystemNoticeData",
    "WSAvdUpdateProgressData",
    "WSEmulatorOperationData",
    "WSTaskUserProgressData",
    "WSTaskUserInfoData",
    "WSTaskScriptInfoData",
    "WSTaskCyclePreviewData",
    "WSTaskInfoUpdatedData",
    "WSTaskLogUpdatedData",
    "WSTaskScriptIdentityData",
    "TaskRuntimeSnapshotItem",
    "TaskRuntimeSnapshot",
    "TaskStatusOut",
    "WSTaskCompletedData",
    "WSTaskCreatedData",
    "WSTaskScriptStartedData",
    "WSTaskScriptFinishedData",
    "WSPowerCountdownData",
    "PowerCountdownSnapshot",
    "WSPowerSignData",
    "WSDisplayMonitorRectData",
    "WSDisplayDetachPromptData",
    "WSGameSignResultData",
    "WSUpdateProgressData",
    "WSMaaFWEnvPrepareProgressData",
    "WSMaaFWProjectUpdateProgressData",
    "WSUpdateCompletedData",
    "WSUpdateFailedData",
    "HSRDynamicStageM7A",
    "HSRDynamicStageSRA",
    "HSRDynamicStageOption",
    "HSRDynamicStageCategory",
    "HSRStageOptionsData",
    "HSRCapabilityTask",
    "HSRCapabilityAdapter",
    "HSRCapabilitiesData",
    "HSRUpdateData",
    "HSRCloudLoginData",
    "HSRManagedFieldVisibleWhen",
    "HSRManagedField",
    "HSRManagedDroppedOverride",
    "HSRManagedForm",
    "HSRManagedTask",
    "HSRManagedConfigData",
    "HSRSRAProfile",
    "HSRSRAProfilesData",
    "MaaFWGamePackageData",
    "MaaFWAdbEmulatorExtraCapabilityInfo",
    "MaaFWControlCapabilitiesInfo",
    "MaaFWProjectInfo",
    "MaaFWControllerInfo",
    "MaaFWResourceInfo",
    "MaaFWGroupInfo",
    "MaaFWSettingInfo",
    "MaaFWTaskInfo",
    "MaaFWOptionCaseInfo",
    "MaaFWOptionInputInfo",
    "MaaFWOptionHotkeyInfo",
    "MaaFWOptionInfo",
    "MaaFWTaskSnapshot",
    "MaaFWPresetInfo",
    "MaaFWInterfacePreviewData",
    "MaaFWEmbeddedSourceItem",
    "MaaFWEmbeddedProjection",
    "MaaFWEmbeddedStatusData",
    "MaaFWShellInstanceItem",
    "MaaFWShellInstanceImportItem",
    "MaaFWProjectUpdateData",
    "MaaFWMirrorCdkData",
    "MaaFWAgentEnvInfo",
    "MaaFWAgentEnvPrepareData",
    "WebhookIndexItem",
    "ObsReplayCheckOut",
    "WebhookInBase",
    "WebhookGetIn",
    "ConfigDataT",
    "WebhookGetOut",
    "WebhookCreateOut",
    "WebhookUpdateIn",
    "WebhookDeleteIn",
    "BlueArchiveActivityIn",
    "MSSPlanKey",
]


PLAN_ROTATE_DAYS_DEFAULT = 7
PLAN_ROTATE_DAYS_MAX = 31
BAAH_PLAN_ROTATE_DAYS_DEFAULT = 3
