"""interface.json → MFAAvalonia 实例配置（instances/*.json）的映射。

字段分三类：
- A 类：从 interface 派生（本模块实现）。
- B 类：运行编排，给合理默认，调用方可整体覆盖（InstanceOrchestration）。
- C 类：设备连接（AdbDevice / Connect.Address），本模块不实现，走 base 透传。

读-改-写语义：传入 base 就在其副本上覆盖关心的字段，其余原样保留；没有 base
时给最小默认。本模块是纯逻辑，不做任何 IO。
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.task.MaaFW.tools.core.automas_maafw_interface import MaaFWInterface
from app.task.MaaFW.tools.core.automas_maafw_interface.models import MaaFWTask
from app.task.MaaFW.tools.external.models import ShellMappingError, TaskSelection

# 兼容旧导入路径：共享输入模型已迁到 external/models.py，这里保留 re-export。
__all__ = [
    "CONTROLLER_TYPE_CODES",
    "TASK_ENTRY_SEPARATOR",
    "InstanceOrchestration",
    "ShellMappingError",
    "TaskSelection",
    "UnknownControllerTypeError",
    "build_current_tasks",
    "build_instance_config",
    "build_task_items",
    "resolve_controller_code",
]

# CurrentTasks / TaskItems 里任务名与 entry 的字面量分隔符。
TASK_ENTRY_SEPARATOR = "<|||>"

# MFAAvalonia 实例配置 CurrentController 的整数取值。
# 只登记已确认的映射：Adb=2（M9A、MaaKes、Maa_bbb 的实例配置均如此）。
# Win32 / PlayCover 的取值未确认，遇到即 fail-closed，绝不猜测。
CONTROLLER_TYPE_CODES: dict[str, int] = {
    "Adb": 2,
}


class UnknownControllerTypeError(ShellMappingError):
    """遇到未登记的 controller type，无法安全得出 CurrentController。"""

    def __init__(self, controller_name: str, controller_type: str) -> None:
        self.controller_name = controller_name
        self.controller_type = controller_type
        super().__init__(
            f"controller「{controller_name}」的 type「{controller_type}」"
            "未登记 CurrentController 取值，拒绝猜测"
        )


@dataclass(frozen=True)
class InstanceOrchestration:
    """B 类·运行编排字段。默认值只是合理起点，调用方按运行场景覆盖。"""

    instance_name: str = "MAS"
    before_task: str = "None"
    after_task: str = "None"
    # 「启动软件」路径。BeforeTask=StartupSoftwareAndScript 时外壳会在跑队列前
    # 启动此路径；空串表示不启动（外壳日志：「已跳过启动程序，因为 SoftwarePath
    # 为空」）。MAS 侧模拟器由 EmulatorManager 负责，绝不让外壳重复启动，故运行
    # 编排恒为空串。取值来源：reference 实例配置样本中 M9A 侧同样为空串。
    software_path: str = ""
    auto_connect_after_refresh: bool = False
    auto_detect_on_connection_failed: bool = False
    allow_adb_hard_restart: bool = False
    allow_adb_restart: bool = False
    use_fingerprint_matching: bool = False
    remember_adb: bool = True

    def as_config_fields(self) -> dict[str, Any]:
        """展开为 MFAAvalonia 实例配置里的顶层键。"""
        return {
            "InstanceName": self.instance_name,
            "BeforeTask": self.before_task,
            "AfterTask": self.after_task,
            "SoftwarePath": self.software_path,
            "AutoConnectAfterRefresh": self.auto_connect_after_refresh,
            "AutoDetectOnConnectionFailed": self.auto_detect_on_connection_failed,
            "AllowAdbHardRestart": self.allow_adb_hard_restart,
            "AllowAdbRestart": self.allow_adb_restart,
            "UseFingerprintMatching": self.use_fingerprint_matching,
            "RememberAdb": self.remember_adb,
        }


def resolve_controller_code(controller_type: str) -> int | None:
    """把 controller type 映射为 MFAAvalonia 的 CurrentController 整数。

    未登记的 type 返回 None，由调用方决定 fail-closed 策略。
    """
    return CONTROLLER_TYPE_CODES.get(controller_type)


def build_current_tasks(interface: MaaFWInterface) -> list[str]:
    """interface.task[] → CurrentTasks，每项 "{name}<|||>{entry}"。"""
    return [
        f"{task.name}{TASK_ENTRY_SEPARATOR}{task.entry}" for task in interface.task
    ]


def build_task_items(
    interface: MaaFWInterface,
    selections: Iterable[TaskSelection],
) -> list[dict[str, Any]]:
    """选中的任务子集 → TaskItems。

    可选字段（label / group / description / controller / option /
    pipeline_override）在 interface task 里有才带上，没有就不写。

    Raises:
        ShellMappingError: 选中的任务名在 interface.task[] 中不存在。
    """
    task_index: dict[str, MaaFWTask] = {}
    for task in interface.task:
        task_index.setdefault(task.name, task)

    items: list[dict[str, Any]] = []
    for selection in selections:
        task = task_index.get(selection.name)
        if task is None:
            raise ShellMappingError(f"interface 未定义任务：{selection.name}")
        items.append(_build_task_item(task, selection))
    return items


def _build_task_item(task: MaaFWTask, selection: TaskSelection) -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": task.name,
        "entry": task.entry,
        "default_check": selection.checked,
    }
    # MFA 自有的 label：interface task 带了就保留（MaaKes 有、M9A 没有）。
    if task.label:
        item["label"] = task.label
    if task.group:
        item["group"] = list(task.group)
    if task.description:
        item["description"] = task.description
    if task.controller:
        item["controller"] = list(task.controller)

    if selection.options is not None:
        item["option"] = [dict(option) for option in selection.options]
    elif task.option:
        # interface 只给选项名，默认取第 0 项；调用方要精确值就传 selection.options。
        item["option"] = [{"name": name, "index": 0} for name in task.option]

    if selection.pipeline_override is not None:
        item["pipeline_override"] = dict(selection.pipeline_override)
    elif task.pipeline_override:
        item["pipeline_override"] = copy.deepcopy(task.pipeline_override)

    return item


def build_instance_config(
    interface: MaaFWInterface,
    *,
    controller_name: str | None = None,
    resource_name: str | None = None,
    selected_tasks: Iterable[TaskSelection] | None = None,
    base: Mapping[str, Any] | None = None,
    orchestration: InstanceOrchestration | None = None,
) -> dict[str, Any]:
    """把 interface 模型映射成 MFAAvalonia 的 instances/*.json 实例配置。

    Args:
        interface: 已解析的 interface.json 模型（复用 automas_maafw_interface）。
        controller_name: 选中的 controller 名，原样写入 CurrentControllerName，
            并按其 type 得出 CurrentController。省略则不动 base 里的 controller 字段。
        resource_name: 选中的 resource 名，原样写入 Resource。省略则不动 base。
        selected_tasks: 选中的任务子集 → TaskItems。None 表示不动 base 里的 TaskItems。
        base: 已存在的实例配置，作为模板读入并在其副本上覆盖。
        orchestration: B 类运行编排字段。给了就整体覆盖这 10 个键；
            为 None 时只补齐 base 缺失的编排键，不覆盖 base 已有值。

    Returns:
        新的实例配置 dict，不与 base 共享可变引用。

    Raises:
        ShellMappingError: controller / resource 名不在 interface 中，或任务名未定义。
        UnknownControllerTypeError: 选中 controller 的 type 未登记 CurrentController。
    """
    config: dict[str, Any] = copy.deepcopy(dict(base)) if base is not None else {}

    # A 类 · 从 interface 派生
    config["CurrentTasks"] = build_current_tasks(interface)

    if selected_tasks is not None:
        config["TaskItems"] = build_task_items(interface, selected_tasks)
    else:
        config.setdefault("TaskItems", [])

    if controller_name is not None:
        controller = _find_named(interface.controller, controller_name)
        if controller is None:
            raise ShellMappingError(f"interface 未定义 controller：{controller_name}")
        code = resolve_controller_code(controller.type)
        if code is None:
            raise UnknownControllerTypeError(controller_name, controller.type)
        config["CurrentControllerName"] = controller.name
        config["CurrentController"] = code

    if resource_name is not None:
        resource = _find_named(interface.resource, resource_name)
        if resource is None:
            raise ShellMappingError(f"interface 未定义 resource：{resource_name}")
        config["Resource"] = resource.name

    # interface 的 resource option 结构未确认，保持 {}；调用方要覆盖走 base。
    config.setdefault("ResourceOptionItems", {})

    # B 类 · 运行编排
    if orchestration is not None:
        config.update(orchestration.as_config_fields())
    else:
        for key, value in InstanceOrchestration().as_config_fields().items():
            config.setdefault(key, value)

    return config


def _find_named(items: Iterable[Any], name: str) -> Any | None:
    return next((item for item in items if item.name == name), None)
