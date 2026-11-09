"""任务运行树：独立运行 UUID、原配置身份和提交驱动的状态变更。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal
from uuid import UUID
from weakref import ReferenceType

from pydantic import (
    BaseModel,
    Field,
    PrivateAttr,
    WithJsonSchema,
)

from app.config import (
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    Virtual,
    collection,
    config_manager,
    virtual_field,
)
from app.config.signals import ConfigEvent, FieldChangeEvent
from app.models.notification.report import TaskNotificationState
from app.utils.contracts.power import PowerSignal

if TYPE_CHECKING:
    # [兼容旧专项] 旧类型导出；新执行器直接使用 app.task.lifecycle.TaskBase。
    from app.task.legacy import TaskExecuteBase as TaskExecuteBase

# 数组保留递归类型；对象的文档投影展开为开放字典，避开生成器的循环 Record 别名。
# 实际参数仍递归校验全部 JSON 值。
type TaskParamValue = (
    str
    | int
    | float
    | bool
    | None
    | list[TaskParamValue]
    | Annotated[
        dict[str, TaskParamValue],
        WithJsonSchema({"type": "object", "additionalProperties": {}}),
    ]
)
type TaskParams = dict[str, TaskParamValue]

# 仅限制 WS 替换包；不裁剪运行树或查询正文。
_LOG_PUSH_MAX_CHARS = 200_000


class TaskMode(StrEnum):
    AUTO_PROXY = "AutoProxy"
    SCRIPT_CONFIG = "ScriptConfig"
    SCRIPT_VIEW = "ScriptView"


class TaskTriggerReason(StrEnum):
    """一次创建对应一个独立触发原因。"""

    MANUAL = "manual"
    STARTUP = "startup"
    TIMED = "timed"
    CYCLE = "cycle"


class RuntimeEntry(ConfigEntry):
    if TYPE_CHECKING:
        # 各具体节点声明自己的 info；保留 ConfigEntry 的开放字段构造签名。
        def __init__(self, **field_values: object) -> None: ...

    async def set_state(self, **fields: object) -> None:
        if self.activation_state.value == "inactive":
            await self.activate()
        for name, value in fields.items():
            # ConfigEntry 不固定分组类型；按公开分组名执行通用字段提交。
            setattr(getattr(self, "info"), name, value)
        await self.commit()

    @property
    def task_info(self) -> TaskItem | None:
        """[兼容旧专项] 旧任务根别名；新代码通过 root 或执行层显式上下文获取任务根。"""
        return self.root if isinstance(self.root, TaskItem) else None

    @property
    def name(self) -> str:
        """[兼容旧专项] 旧平铺名称；新代码读取具体节点的 info.name。"""
        # 旧专项平铺属性兼容；日志 info 无此字段，待旧专项移除后一并删除别名。
        return self.info.name  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

    @property
    def status(self) -> str:
        """[兼容旧专项] 旧平铺状态；新代码读取具体节点的 info.status。"""
        # 旧专项状态别名；各节点的具体 info 分组由子类声明。
        return self.info.status  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

    @property
    def result(self) -> str:
        """[兼容旧专项] 旧平铺结果；新代码读取具体节点的 info.result。"""
        # 旧专项兼容：具体任务节点才声明虚拟 result，基础日志节点不提供。
        return self.info.result  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]


class LogRecord(RuntimeEntry):
    class Info(ConfigGroup):
        content: list[str] = Field(default_factory=list, description="按行存储的日志")
        status: str = "未开始监看日志"
        phase: str = ""
        start_time: datetime = Field(
            default_factory=lambda: datetime.now().astimezone()
        )

    info: Info = Field(default_factory=Info)

    def __init__(self, content=None, status=None, phase=None, **values):
        """[兼容旧专项] 旧平铺日志构造参数；新代码使用 info 分组载荷或 logs.add()。"""
        info = dict(values.pop("info", {}) or {})
        info.update(
            {
                key: value
                for key, value in {
                    "content": content,
                    "status": status,
                    "phase": phase,
                }.items()
                if value is not None
            }
        )
        super().__init__(info=info, **values)

    async def append_content(self, *lines):
        async with config_manager.transaction():
            await self.set_state(content=[*self.info.content, *lines])

    @property
    def content(self) -> list[str]:
        """[兼容旧专项] 旧正文别名；新代码读取 info.content，追加使用 append_content()。"""
        return self.info.content

    @property
    def phase(self) -> str:
        """[兼容旧专项] 旧阶段别名；新代码读取 info.phase。"""
        return self.info.phase


class TaskUserItem(RuntimeEntry):
    class Info(ConfigGroup):
        user_id: str = Field(
            default="", description="原用户 UUID，default 表示共享配置"
        )
        name: str = ""
        status: str = "等待"
        params: TaskParams = Field(default_factory=dict)
        result: Virtual[str] = None

    info: Info = Field(default_factory=Info)
    logs: ConfigCollection[LogRecord] = collection(LogRecord)
    _config_ref: ReferenceType | None = PrivateAttr(default=None)

    def __init__(self, user_id=None, name=None, status=None, **values):
        """[兼容旧专项] 旧平铺用户构造及 Default 归一；新代码使用 info 载荷和 default。"""
        info = dict(values.pop("info", {}) or {})
        info.update(
            {
                key: value
                for key, value in {
                    "user_id": user_id,
                    "name": name,
                    "status": status,
                }.items()
                if value is not None
            }
        )
        if info.get("user_id") == "Default":
            info["user_id"] = "default"
        super().__init__(info=info, **values)

    def iter_history_logs(self) -> list[tuple[datetime, LogRecord]]:
        """[兼容旧专项] 旧按本地时间读取日志的投影；新代码遍历 logs 并读取各记录的 info。"""
        return [
            (entry.info.start_time.astimezone(), entry) for entry in self.logs.values()
        ]

    async def add_log_record(self, started_at, record):
        """[兼容旧专项] 旧时间加记录的登记签名；新代码使用 logs.add(LogRecord, payload=...) 后提交。"""
        if self.activation_state.value == "inactive":
            await self.activate()
        payload = record.model_dump(context={"audience": "persist"})
        payload["info"]["start_time"] = started_at
        uid = self.logs.add(LogRecord, payload=payload)
        await self.logs.commit()
        return self.logs[uid]

    @virtual_field("info.result")
    def compute_result(self):
        return (
            " | ".join(
                f"{at:%H:%M} - {entry.status}" for at, entry in self.iter_history_logs()
            )
            or "未开始运行"
        )

    @property
    def user_id(self) -> str:
        """[兼容旧专项] 旧用户标识及 Default 大小写；新代码读取 info.user_id，使用 default。"""
        return "Default" if self.info.user_id == "default" else self.info.user_id

    @property
    def log_record(self):
        """[兼容旧专项] 旧按时间索引的日志字典；新代码使用有序 logs 集合和运行 UUID。"""
        return dict(self.iter_history_logs())


class TaskScriptItem(RuntimeEntry):
    class Info(ConfigGroup):
        script_id: str = ""
        script_type: str = ""
        name: str = ""
        status: str = "等待"
        params: TaskParams = Field(default_factory=dict)
        result: Virtual[str] = None

    class Current(ConfigGroup):
        index: UUID | None = None
        log: str = ""

    info: Info = Field(default_factory=Info)
    current: Current = Field(default_factory=Current)
    users: ConfigCollection[TaskUserItem] = collection(TaskUserItem)
    _config_ref: ReferenceType | None = PrivateAttr(default=None)
    _run_days: tuple[str, ...] | None = PrivateAttr(default=None)
    # [兼容旧专项] 只允许旧 manager 重建用户；新 L3/L4 不使用此权限。
    _manager_controls_users: bool = PrivateAttr(default=False)

    def __init__(self, script_id=None, name=None, status=None, **values):
        """[兼容旧专项] 旧平铺托管构造参数；新代码使用 info 分组载荷。"""
        details = dict(values.pop("info", {}) or {})
        details.update(
            {
                key: value
                for key, value in {
                    "script_id": script_id,
                    "name": name,
                    "status": status,
                }.items()
                if value is not None
            }
        )
        super().__init__(info=details, **values)

    async def set_current_index(self, index):
        """[兼容旧专项] 旧整数位置转运行 UUID；新代码设置 current.index 为用户运行 UUID 后提交。"""
        self.current.index = self.user_list[index].uid if index >= 0 else None
        await self.commit()

    async def set_users(self, users: Sequence[TaskUserItem]):
        """[兼容旧专项] 仅旧 manager 可重建用户列表；新执行链消费 L1 固定的 users 快照。"""
        if self.activation_state.value == "inactive":
            await self.activate()
        if (
            self.task_info
            and self.task_info.info.status != "pending"
            and not self._manager_controls_users
        ):
            raise RuntimeError("发布后的插件用户快照不可替换")
        params = {u.user_id: u.info.params for u in self.users.values()}
        async with config_manager.transaction():
            for uid in list(self.users.keys()):
                self.users.remove(uid)
            await self.users.commit()
            for user in users:
                payload = user.model_dump(context={"audience": "persist"})
                payload["info"]["params"] = params.get(user.user_id, user.info.params)
                self.users.add(TaskUserItem, payload=payload)
            await self.users.commit()
            self.current.index = None
            await self.commit()

    async def set_log(self, value):
        """[兼容旧专项] 旧托管字符串日志写法；新代码写当前 LogRecord，流程日志按 current.log 提交。"""
        self.current.log = value
        await self.commit()

    async def append_log(self, value):
        """[兼容旧专项] 旧托管字符串日志追加；新代码追加当前 LogRecord 的按行正文。"""
        await self.set_log(self.log + value)

    @virtual_field("info.result")
    def compute_result(self) -> str:
        if not self.users:
            return "用户未加载"
        return "\n".join(
            f"{user.info.name or uid}: {user.info.result}"
            for uid, user in self.users.items()
        )

    @property
    def script_id(self) -> str:
        """[兼容旧专项] 旧平铺配置 ID；新代码读取 info.script_id，运行身份使用 uid。"""
        return self.info.script_id

    @property
    def script_type(self) -> str:
        """[兼容旧专项] 旧平铺类型；新代码读取 info.script_type。"""
        return self.info.script_type

    @property
    def user_list(self) -> list[TaskUserItem]:
        """[兼容旧专项] 旧列表投影；新代码使用 users 有序集合。"""
        return list(self.users.values())

    @property
    def current_index(self) -> int:
        """[兼容旧专项] 旧整数进度位置；新代码使用 current.index 的用户运行 UUID。"""
        return next(
            (i for i, uid in enumerate(self.users.keys()) if uid == self.current.index),
            -1,
        )

    @property
    def log(self):
        """[兼容旧专项] 旧字符串日志别名；新代码根据当前来源读取日志记录或 current.log。"""
        return self.current.log


class WSTaskPrefetchData(BaseModel):
    """独立于脚本日志的临时预下载展示状态。"""

    target: str = Field(default="", description="下一托管名称")
    status: str = Field(default="", description="检查、下载或准备状态")
    package: str = Field(default="", description="当前包名")
    method: str = Field(default="", description="实际下载方式 httpx 或 FluxDown")
    progress: str = Field(default="", description="当前文件进度，总大小未知时为空")
    size: str = Field(default="", description="已下载量与总大小")
    rate: str = Field(default="", description="当前下载速率")


class TaskItem(RuntimeEntry):
    class Info(ConfigGroup):
        # L1 受理时生成的名称快照；查询与推送统一从这里读取。
        name: str = ""
        mode: TaskMode = TaskMode.AUTO_PROXY
        status: Literal["pending", "running", "success", "error", "cancelled"] = (
            "pending"
        )
        trigger: TaskTriggerReason = TaskTriggerReason.MANUAL
        result: Virtual[str] = None

    class Execution(ConfigGroup):
        """L1 保存的本轮附加动作；不保留原队列身份或结束时重读配置。"""

        script_before: Path | None = Field(default=None, description="本轮运行前脚本")
        script_after: Path | None = Field(default=None, description="本轮运行后脚本")
        after_accomplish: PowerSignal = Field(
            default=PowerSignal.NO_ACTION, description="本轮完成后操作"
        )
        after_accomplish_delay: int = Field(
            default=1, ge=1, le=1440, description="完成后操作倒计时，单位分钟"
        )

    class Current(ConfigGroup):
        index: UUID | None = None
        log: Virtual[str] = None
        prefetch: WSTaskPrefetchData | None = Field(
            default=None, description="下一托管预下载状态"
        )

    info: Info = Field(default_factory=Info)
    execution: Execution = Field(default_factory=Execution)
    current: Current = Field(default_factory=Current)
    scripts: ConfigCollection[TaskScriptItem] = collection(TaskScriptItem)
    _notification_state: TaskNotificationState = PrivateAttr(
        default_factory=TaskNotificationState
    )

    # 传输记录仅写 live 节点，不参与配置字段提交与回滚。
    _log_source: UUID | None = PrivateAttr(default=None)
    _log_content: str | list[str] | None = PrivateAttr(default=None)
    _log_seq: int = PrivateAttr(default=0)

    def clear_log_cursor(self) -> None:
        """清理已发送日志的私有基线，运行树正文继续保留。"""
        self._log_source = self._log_content = None
        self._log_seq = 0

    def get_log_snapshot(self) -> dict[str, Any]:
        source = self.current_log_source()
        content = (
            source.info.content
            if isinstance(source, LogRecord)
            else source.current.log
            if source is not None
            else ""
        )
        matches = (
            self._log_source == (source.uid if source is not None else None)
            and self._log_content == content
        )
        # 事务过程态可能回滚；只有正文与发送基线匹配才能继续追加。
        seq = self._log_seq if matches else 0 if self._log_content is None else None
        return {
            "log": "".join(content) if isinstance(content, list) else content,
            "logSeq": seq,
            "logFirstLine": 1,
        }

    def get_update(self) -> dict[str, Any]:
        """只导出元数据，避免先复制、校验整棵树的日志正文。"""

        def metadata(
            node: TaskItem | TaskScriptItem | TaskUserItem | LogRecord,
        ) -> dict[str, Any]:
            # 信号在提交前触发；读取基类工作区视图，让元数据独立携带本次过程态。
            node = node.effective
            data: dict[str, Any] = {
                "info": node.info.model_dump(
                    mode="json",
                    exclude={"content"} if isinstance(node, LogRecord) else None,
                )
            }
            if isinstance(node, TaskItem):
                data["execution"] = node.execution.model_dump(mode="json")
            if isinstance(node, LogRecord):
                return data
            children: (
                ConfigCollection[LogRecord]
                | ConfigCollection[TaskUserItem]
                | ConfigCollection[TaskScriptItem]
            )
            if isinstance(node, TaskUserItem):
                name, children = "logs", node.logs
            else:
                data["current"] = node.current.model_dump(exclude={"log"})
                name, children = (
                    ("scripts", node.scripts)
                    if isinstance(node, TaskItem)
                    else ("users", node.users)
                )
            data[name] = {
                "order": [
                    item.model_dump()
                    for item in children.order
                    if (child := children.get(item.uid)) is not None
                    and not child.deleted
                ],
                "data": {
                    str(uid): metadata(child)
                    for uid, child in children.items()
                    if not child.deleted
                },
            }
            return data

        return metadata(self)

    async def set_current_index(self, index):
        """[兼容旧专项] 旧整数位置转运行 UUID；新代码设置 current.index 为托管运行 UUID 后提交。"""
        self.current.index = self.script_list[index].uid if index >= 0 else None
        await self.commit()

    @property
    def instance_idx(self) -> int | None:
        """[兼容旧专项] 旧平铺启动参数；新代码从对应托管 info.params 或执行上下文读取。"""
        value = (
            self.script_list[self.current_index].info.params.get("instance_idx")
            if self.current_index >= 0
            else None
        )
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError("instance_idx 必须为非负整数")
        return value

    def is_target_user(self, user_id):
        """[兼容旧专项] 供旧 manager 再展开时筛选；新 L3 直接派发 L1 已选定的用户运行节点。"""
        return (
            self.mode != TaskMode.AUTO_PROXY
            or self.current_index < 0
            or any(
                u.user_id == user_id
                for u in self.script_list[self.current_index].users.values()
            )
        )

    @virtual_field("info.result")
    def compute_result(self) -> str:
        if not self.scripts:
            return "任务未加载"
        # 来源的托管摘要在任务根动态聚合，不在任务完成时另算一份结果。
        blocks: list[str] = []
        for uid, script in self.scripts.items():
            users = list(script.users.values())
            name = script.info.name or str(uid)
            body = (script.info.result or "").replace("\n", "\n    ")
            completed = sum(user.info.status == "完成" for user in users)
            uncompleted = sum(user.info.status != "完成" for user in users)
            blocks.append(
                f"{name}：\n\n"
                f"    已完成用户数：{completed}；未完成用户数：{uncompleted}\n\n"
                f"    {body}"
            )
        return "\n\n\n".join(blocks)

    def current_log_source(self) -> LogRecord | TaskScriptItem | None:
        script = self.scripts.get(self.current.index) if self.current.index else None
        if script is None:
            return None
        # [兼容旧专项] manager 的 set_log 同时承接流程提示和原生日志镜像；
        # 不能被提前建立的用户日志记录遮住。插件仍直接使用当前 LogRecord。
        if script._manager_controls_users:
            return script
        user = script.users.get(script.current.index) if script.current.index else None
        if user is not None and user.logs:
            return max(user.logs.values(), key=lambda record: record.info.start_time)
        return script

    @virtual_field("current.log")
    def compute_log(self) -> str:
        source = self.current_log_source()
        if isinstance(source, LogRecord):
            return "".join(source.info.content)
        return source.current.log if source is not None else ""

    @property
    def mode(self) -> TaskMode:
        """[兼容旧专项] 旧平铺模式别名；新代码使用 info.mode 的 TaskMode 枚举。"""
        return self.info.mode

    @property
    def task_id(self) -> str:
        """[兼容旧调用方] 旧字符串任务 ID 投影；新代码以 uid 保存身份，在接口边界转字符串。"""
        return str(self.uid)

    @property
    def view_only(self) -> bool:
        """[兼容旧专项] 旧查看开关；新代码比较 info.mode 与 TaskMode.SCRIPT_VIEW。"""
        return self.mode == TaskMode.SCRIPT_VIEW

    @property
    def script_list(self) -> list[TaskScriptItem]:
        """[兼容旧专项] 旧托管列表投影；新代码使用 scripts 有序集合。"""
        return list(self.scripts.values())

    @property
    def current_index(self) -> int:
        """[兼容旧专项] 旧整数进度位置；新代码使用 current.index 的托管运行 UUID。"""
        return next(
            (
                i
                for i, uid in enumerate(self.scripts.keys())
                if uid == self.current.index
            ),
            -1,
        )

    @property
    def script_id(self) -> str | None:
        """[兼容旧调用方] 首个托管的旧平铺 ID；新代码按 scripts 各运行节点读取 info.script_id。"""
        return self.script_list[0].script_id if self.script_list else None

    @property
    def current_script_id(self):
        """[兼容旧专项] 旧当前配置 ID 投影；新代码用 current.index 定位运行节点后读取 info。"""
        return (
            self.script_list[self.current_index].script_id
            if self.current_index >= 0
            else None
        )

    @property
    def user_id(self) -> str | None:
        """[兼容旧调用方] 单目标会话的旧平铺用户 ID；新代码从目标用户运行节点读取 info.user_id。"""
        return (
            self.script_list[0].user_list[0].user_id
            if self.mode != TaskMode.AUTO_PROXY
            and self.script_list
            and len(self.script_list[0].user_list) == 1
            else None
        )

    @property
    def notification_state(self) -> TaskNotificationState:
        return self._notification_state

    @property
    def is_queue_task(self) -> bool:
        """[兼容旧专项] 仅供旧专项次数策略识别队列项；新框架在所属层处理准入和执行条件。"""
        # 旧专项的次数上限仍区分队列与直接运行；复用已有执行条件，不保存队列身份。
        script = self.scripts.get(self.current.index) if self.current.index else None
        return (
            script._run_days is not None
            if script is not None
            else any(s._run_days is not None for s in self.scripts.values())
        )


# 模型定义完成即声明推送业务订阅；不依赖管理器实例或任务启动路径绑定。
@TaskItem.connect(phase="runtime")
@TaskScriptItem.connect(phase="runtime")
@TaskUserItem.connect(phase="runtime")
@LogRecord.connect(phase="runtime")
@ConfigCollection.connect(phase="runtime")
async def _info_changed(sender: object, event: ConfigEvent) -> None:
    node = event.node if isinstance(event, FieldChangeEvent) else event.collection
    root = node.root
    if not isinstance(root, TaskItem):
        return
    # 绑定随模型导入完成；仅执行回调时访问宿主，避免 WS 契约反向导入模型形成循环。
    from app.core import Publisher
    from app.core.task_manager import TaskManager
    from app.core.ws import protocol
    from app.models.schema import TaskTreeData

    if root.uid not in TaskManager._running:
        return
    if isinstance(event, FieldChangeEvent) and (
        (
            isinstance(node, LogRecord)
            and event.group == "info"
            and event.field == "content"
        )
        or (
            isinstance(node, (TaskItem, TaskScriptItem))
            and event.group == "current"
            and event.field == "log"
        )
        or event.value == event.old_value
    ):
        return
    await Publisher.send(
        id=root.task_id,
        type=protocol.TASK_INFO_UPDATED,
        data=TaskTreeData.model_validate(root.get_update()).model_dump(mode="json"),
    )


@TaskItem.connect(phase="runtime")
@TaskScriptItem.connect(phase="runtime")
@TaskUserItem.connect(phase="runtime")
@LogRecord.connect(phase="runtime")
@ConfigCollection.connect(phase="runtime")
async def _log_changed(sender: object, event: ConfigEvent) -> None:
    """按配置信号发送日志增量，正常返回后推进模型私有游标。"""
    node = event.node if isinstance(event, FieldChangeEvent) else event.collection
    root = node.root
    if not isinstance(root, TaskItem):
        return
    from app.core.task_manager import TaskManager

    if root.uid not in TaskManager._running:
        return
    script = root.scripts.get(root.current.index) if root.current.index else None
    if not isinstance(event, FieldChangeEvent):
        parent = node.parent
        if isinstance(parent, TaskUserItem) and (
            script is None or script.current.index != parent.uid
        ):
            return
        if isinstance(parent, TaskScriptItem) and root.current.index != parent.uid:
            return
    elif not (
        isinstance(node, LogRecord)
        and event.group == "info"
        and event.field in ("content", "start_time")
        or isinstance(node, (TaskItem, TaskScriptItem))
        and event.group == "current"
        and event.field in ("index", "log")
    ):
        return
    source = root.current_log_source()
    if isinstance(event, FieldChangeEvent):
        if (
            isinstance(node, LogRecord)
            and event.field == "content"
            and node is not source
        ):
            return
        if isinstance(node, TaskScriptItem) and node.uid != root.current.index:
            return
    # [兼容旧专项] 托管镜像日志仍可通知当前用户记录变化，正文始终取实际来源。
    source_id = source.uid if source is not None else None
    content = (
        source.info.content
        if isinstance(source, LogRecord)
        else source.current.log
        if source is not None
        else ""
    )
    previous = root._log_content
    if root._log_source == source_id and previous == content:
        return
    same_source = root._log_source == source_id
    # 事件旧值与已发基线不符，说明中间有回滚或未发布变化，本次改发完整替换。
    if (
        isinstance(event, FieldChangeEvent)
        and node is source
        and event.field in ("content", "log")
        and event.old_value != previous
    ):
        same_source = False
    append = False
    payload: str
    if same_source and isinstance(content, list) and isinstance(previous, list):
        append = content[: len(previous)] == previous and len(content) > len(previous)
        payload = "".join(content[len(previous) :] if append else content)
    elif same_source and isinstance(content, str) and isinstance(previous, str):
        append = bool(content) and content.startswith(previous)
        payload = content[len(previous) :] if append else content
    else:
        payload = "".join(content) if isinstance(content, list) else content
    offset = 1
    if len(payload) > _LOG_PUSH_MAX_CHARS:
        append = False
        text = "".join(content) if isinstance(content, list) else content
        payload = text[-_LOG_PUSH_MAX_CHARS:]
        offset += text.count("\n", 0, len(text) - len(payload))
    seq = root._log_seq + 1
    from app.core import Publisher
    from app.core.ws import protocol
    from app.models.schema import WSTaskLogUpdatedData

    await Publisher.send(
        id=root.task_id,
        type=protocol.TASK_LOG_UPDATED,
        data=WSTaskLogUpdatedData(
            log=payload, seq=seq, append=append, firstLine=offset
        ),
    )
    # 行列表只复制容器，不复制正文；兼容旧专项原地追加后用托管镜像触发通知。
    root._log_content = list(content) if isinstance(content, list) else content
    root._log_source, root._log_seq = source_id, seq


# [兼容旧专项] 旧类型别名；新代码使用 TaskUserItem／TaskScriptItem。
UserItem = TaskUserItem
ScriptItem = TaskScriptItem


def __getattr__(name):
    """[兼容旧专项] 仅保留 TaskExecuteBase 的旧导入路径；新执行器继承 app.task.lifecycle.TaskBase。"""
    if name == "TaskExecuteBase":
        from app.task.legacy import TaskExecuteBase

        return TaskExecuteBase
    raise AttributeError(name)
