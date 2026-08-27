"""interface.json → MXU 外壳容器（config/mxu-<项目名>.json）的映射。

MXU 与 MFAAvalonia 的形状差异（务必看清）：

- 容器是「单文件内嵌 instances 数组」，不是「一实例一文件」。
- 任务只有 ``taskName``，没有 ``entry``。
- 勾选字段是 ``enabled``，不是 ``default_check``。
- 选项是 ``optionValues`` 字典（随类型而异），不是列表。
- controller 只有字符串 ``controllerName``，没有整数枚举，
  因此 **不需要** MFAAvalonia 那套 controller type → 整数的 fail-closed 映射。

核心优势：在已有容器上「追加」实例，绝不改动用户已有的其他实例。

本模块是纯逻辑，不做任何 IO（不读写文件、不起进程），也不修改任何入参。
"""

from __future__ import annotations

import copy
import random
import string
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from app.task.MaaFW.tools.core.automas_maafw_interface import MaaFWInterface
from app.task.MaaFW.tools.core.automas_maafw_interface.models import MaaFWTask
from app.task.MaaFW.tools.external.models import ShellMappingError, TaskSelection

__all__ = [
    "ShellMappingError",
    "TaskSelection",
    "append_instance",
    "build_instance_entry",
    "build_interface_task_snapshot",
    "build_task_entries",
    "build_task_entry",
    "default_instance_id",
]

# MXU 的实例 / 任务 id：小写字母 + 数字，长度 7（实测样本形如 "7ym1fl9"）。
_ID_ALPHABET = string.ascii_lowercase + string.digits
_ID_LENGTH = 7


def default_instance_id() -> str:
    """生成一个 MXU 风格的随机 id。

    仅作为 ``id_factory`` 的默认实现；需要可断言的输出时，调用方传入自己的
    生成器（或直接传 ``instance_id``），本模块不会在别处触碰随机源。
    """
    return "".join(random.choices(_ID_ALPHABET, k=_ID_LENGTH))


def build_interface_task_snapshot(interface: MaaFWInterface) -> list[str]:
    """interface.task[] → 容器级 ``interfaceTaskSnapshot``（任务名列表）。

    容器级簿记键（``interfaceTaskSnapshot`` / ``newTaskNames`` / ``recentlyClosed``）
    的确切刷新时机未知，本模块不代为写入；调用方需要时用这个纯函数自取。
    """
    return [task.name for task in interface.task]


def build_task_entry(
    task: MaaFWTask,
    selection: TaskSelection,
    *,
    entry_id: str,
    controller_name: str | None = None,
    emit_enabled_by_controller: bool = True,
) -> dict[str, Any]:
    """构建单个 MXU ``tasks[]`` 条目。

    只产出 ``taskName``（不产出 ``entry``）。``optionValues`` 整体透传
    ``selection.option_values``，为 None 时给空字典。

    Args:
        task: interface 中匹配到的任务模型。
        selection: 选择意图（勾选 / 选项 / 自定义名）。
        entry_id: 本条目的 id，由调用方注入以便断言。
        controller_name: 活动 controller 名，非空且开启 ``emit_enabled_by_controller``
            时写入 ``enabledByController = {controller_name: enabled}``。
        emit_enabled_by_controller: 是否写 ``enabledByController``。实测新版 MXU
            （MaaEnd）在有 controller 时逐任务写该键并与 ``enabled`` 同值；
            旧样本（MaaYYs）则不写。默认按新版行为，调用方可关。
    """
    enabled = bool(selection.checked)
    entry: dict[str, Any] = {
        "id": entry_id,
        "taskName": task.name,
        "enabled": enabled,
    }
    if selection.custom_name is not None:
        entry["customName"] = selection.custom_name
    if emit_enabled_by_controller and controller_name:
        entry["enabledByController"] = {controller_name: enabled}
    entry["optionValues"] = (
        copy.deepcopy(dict(selection.option_values))
        if selection.option_values is not None
        else {}
    )
    return entry


def build_task_entries(
    interface: MaaFWInterface,
    selections: Iterable[TaskSelection],
    *,
    id_factory: Callable[[], str] = default_instance_id,
    controller_name: str | None = None,
    emit_enabled_by_controller: bool = True,
) -> list[dict[str, Any]]:
    """选中的任务子集 → MXU ``tasks[]``。

    Raises:
        ShellMappingError: 选中的任务名在 interface.task[] 中不存在（不静默跳过）。
    """
    task_index: dict[str, MaaFWTask] = {}
    for task in interface.task:
        task_index.setdefault(task.name, task)

    entries: list[dict[str, Any]] = []
    for selection in selections:
        task = task_index.get(selection.name)
        if task is None:
            raise ShellMappingError(f"interface 未定义任务：{selection.name}")
        entries.append(
            build_task_entry(
                task,
                selection,
                entry_id=id_factory(),
                controller_name=controller_name,
                emit_enabled_by_controller=emit_enabled_by_controller,
            )
        )
    return entries


def build_instance_entry(
    interface: MaaFWInterface,
    *,
    controller_name: str | None = None,
    resource_name: str | None = None,
    selected_tasks: Iterable[TaskSelection] | None = None,
    name: str | None = None,
    base: Mapping[str, Any] | None = None,
    instance_id: str | None = None,
    id_factory: Callable[[], str] = default_instance_id,
    emit_enabled_by_controller: bool = True,
) -> dict[str, Any]:
    """把 interface 模型映射成单个 MXU ``instances[]`` 条目。

    读-改-写语义：给了 ``base`` 就在其深拷贝上覆盖关心的字段，未涉及的字段
    （如 ``preActions`` / ``savedDevice``）原样保留；没有 ``base`` 时给最小骨架。

    Args:
        interface: 已解析的 interface.json 模型（复用 automas_maafw_interface）。
        controller_name: 选中的 controller 名，原样写入 ``controllerName``。
            传入 ``""`` 表示显式留空（实测存在该状态），不做校验；传非空名则
            校验必须在 interface.controller[] 中。``None`` 表示不动 base。
        resource_name: 选中的 resource 名，原样写入 ``resourceName``，
            校验必须在 interface.resource[] 中。``None`` 表示不动 base。
        selected_tasks: 选中的任务子集 → ``tasks[]``。``None`` 表示不动 base 的 tasks。
        name: 实例显示名。``None`` 时取 base 的 ``name``，再无则默认 ``"MAS"``。
        base: 已存在的实例条目，作模板深拷贝后覆盖。
        instance_id: 实例 id。``None`` 时取 base 的 ``id``，再无则用 ``id_factory``。
        id_factory: 无显式 id 时的 id 生成器，也用于逐个 task 条目的 id。
            默认随机；需要可断言输出时注入自己的生成器。
        emit_enabled_by_controller: 透传给 :func:`build_task_entry`。

    Returns:
        新的实例条目 dict，不与 ``base`` 共享可变引用。

    Raises:
        ShellMappingError: controller / resource 名不在 interface 中，或任务名未定义。
    """
    entry: dict[str, Any] = copy.deepcopy(dict(base)) if base is not None else {}

    if instance_id is not None:
        entry["id"] = instance_id
    elif "id" not in entry:
        # 仅在确实需要时才动 id_factory，避免白白消耗调用方的生成器。
        entry["id"] = id_factory()

    if name is not None:
        entry["name"] = name
    else:
        entry.setdefault("name", "MAS")

    if controller_name is not None:
        if controller_name != "" and _find_named(interface.controller, controller_name) is None:
            raise ShellMappingError(f"interface 未定义 controller：{controller_name}")
        entry["controllerName"] = controller_name
    else:
        entry.setdefault("controllerName", "")

    if resource_name is not None:
        if _find_named(interface.resource, resource_name) is None:
            raise ShellMappingError(f"interface 未定义 resource：{resource_name}")
        entry["resourceName"] = resource_name
    else:
        entry.setdefault("resourceName", "")

    effective_controller = entry.get("controllerName") or None
    if selected_tasks is not None:
        entry["tasks"] = build_task_entries(
            interface,
            selected_tasks,
            id_factory=id_factory,
            controller_name=effective_controller,
            emit_enabled_by_controller=emit_enabled_by_controller,
        )
    else:
        entry.setdefault("tasks", [])

    return entry


def append_instance(
    container: Mapping[str, Any],
    instance: Mapping[str, Any],
    *,
    set_active: bool = True,
) -> dict[str, Any]:
    """在容器 dict 的深拷贝上追加一个实例条目，并（可选）设为活动项。

    绝不修改或删除已有实例，也不动容器的其它键（``settings`` / ``customAccents``
    / ``interfaceTaskSnapshot`` 等）。入参 ``container`` 与 ``instance`` 保持原样。

    Args:
        container: 已有的 mxu-*.json 顶层 dict（可能没有 ``instances`` 键）。
        instance: 要追加的实例条目（通常来自 :func:`build_instance_entry`）。
        set_active: 追加后把 ``lastActiveInstanceId`` 指向新实例。

    Raises:
        ShellMappingError: 新实例 id 与容器中已有实例冲突，或 ``set_active`` 时缺 id。
    """
    result: dict[str, Any] = copy.deepcopy(dict(container))
    raw_instances = result.get("instances")
    instances: list[Any] = list(raw_instances) if isinstance(raw_instances, list) else []

    new_instance = copy.deepcopy(dict(instance))
    new_id = new_instance.get("id")
    if new_id is not None and any(
        isinstance(existing, Mapping) and existing.get("id") == new_id
        for existing in instances
    ):
        raise ShellMappingError(f"容器中已存在实例 id：{new_id}")

    instances.append(new_instance)
    result["instances"] = instances

    if set_active:
        if new_id is None:
            raise ShellMappingError("追加的实例缺少 id，无法设为 lastActiveInstanceId")
        result["lastActiveInstanceId"] = new_id

    return result


def _find_named(items: Iterable[Any], name: str) -> Any | None:
    return next((item for item in items if item.name == name), None)
