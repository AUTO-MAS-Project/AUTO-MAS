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

"""读外壳程序（MFAAvalonia / MXU）在项目目录里保存的配置实例，换成 MAS 用户的任务快照。

新建 MFW 脚本的引导最后一步用它：用户在外壳里已经配好了几份任务队列，勾选哪几份就建
哪几个用户，不用在 MAS 里再排一遍。**只读**：外壳文件一个字节不改。

两种格式都照真实发行包里的文件写（2026-09 实测），不认识的文件跳过并记日志：

- **MFAAvalonia**：``config/instances/<实例 id>.json`` 一份一个实例。实例名在
  ``InstanceName``；任务在 ``TaskItems``（``default_check`` 为真的才在队列里），选项是
  ``{name, index}``——``index`` 是 case 的下标；checkbox 另有 ``selected_cases``；input
  是 ``data: {输入名: 值}``；嵌套选项在 ``sub_options`` 里，checkbox 的 ``sub_options``
  是各个 case 的容器（名字就是 case 名），容器里再挂的才是选项。上次使用的实例记在
  项目根（老版本在 ``config/``）的 ``appsettings.json`` 的 ``Instances.LastActive``，
  它可能是 ``default`` 而文件名是别的 hex id——对不上就不标「当前使用中」。
- **MXU**：``config/mxu-<项目名>.json`` 里的 ``instances[]``，每个实例
  ``{id, name, controllerName, resourceName, tasks[]}``；任务是
  ``{taskName, enabled, enabledByController?, optionValues}``，选项值带类型：
  ``{type, caseName}`` / ``{type, caseNames}`` / ``{type, value: bool}``（switch）/
  ``{type, values: {输入名: 值}}``（input / hotkey），嵌套选项平铺在同一张表里；
  ``globalOptionValues`` 是所有实例共用的全局选项；上次使用的是 ``lastActiveInstanceId``。

这是在外壳私有格式上做的一次性映射（黑箱规范里的「私有格式」条目）：外壳改了格式，表现是
扫不到实例（只记日志）或导入时跳过项变多（结果里逐项列出），不会写坏任何东西。
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.models.ConfigBase import UserNameValidator
from app.task.MaaFW.tools.core.interface.models import (
    MaaFWInterface,
    MaaFWOption,
    MaaFWPreset,
    MaaFWPresetTask,
    MaaFWTask,
    MaaFWTaskOptionValue,
    build_pretask_task_name,
    iter_pretasks,
)
from app.task.MaaFW.tools.core.interface.task_config import (
    build_interface_preset_snapshot,
    build_task_option_maps,
    normalize_task_options_by_task,
)
from app.utils import get_logger

logger = get_logger("MFW 外壳配置导入")

ShellSource = Literal["MFAAvalonia", "MXU"]
SOURCE_MFAA: ShellSource = "MFAAvalonia"
SOURCE_MXU: ShellSource = "MXU"

_MFAA_SETTINGS_FILE = "appsettings.json"
#: switch 的布尔值按 case 名对应（PI v2 的 switch 两个 case 通常叫 Yes / No，顺序不固定，
#: M9A 就同时有 [Yes, No] 与 [No, Yes]），不按下标猜。
_SWITCH_TRUE_NAMES = frozenset({"yes", "y", "true", "on", "1", "是", "开"})
_SWITCH_FALSE_NAMES = frozenset({"no", "n", "false", "off", "0", "否", "关"})
_CHOICE_TYPES = frozenset({"select", "scan_select", "switch"})
_FIELD_TYPES = frozenset({"input", "hotkey"})


@dataclass(frozen=True)
class ShellTask:
    """实例队列里勾选着的一条任务，选项原样保留、按来源格式解释。"""

    name: str
    entry: str = ""
    raw_options: Any = None


@dataclass
class ShellInstance:
    """外壳里的一份配置实例（只含勾选着的任务）。"""

    id: str
    name: str
    source: ShellSource
    active: bool = False
    controller: str = ""
    resource: str = ""
    tasks: list[ShellTask] = field(default_factory=list)
    global_options: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class ShellImportPlan:
    """一份实例换算出来的用户配置：任务快照形状与用户页保存的一致（只有队列里的任务）。"""

    snapshot: dict[str, Any]
    task_count: int
    controller: str = ""
    resource: str = ""
    skipped: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 扫描
# ---------------------------------------------------------------------------


def scan_shell_instances(root: Path) -> list[ShellInstance]:
    """扫一个项目目录里的外壳配置实例，MFAAvalonia 在前、MXU 在后。

    单个文件读不了或不认识只跳过并记日志，不影响其它文件。
    """

    config_dir = root / "config"
    if not config_dir.is_dir():
        return []
    return [*_scan_mfaa(root, config_dir), *_scan_mxu(config_dir)]


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        logger.warning(f"读不了外壳配置文件，已跳过：{path}（{exc}）")
        return None
    if not isinstance(payload, dict):
        logger.warning(f"外壳配置文件不是 JSON 对象，已跳过：{path}")
        return None
    return payload


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on"}
    return value is True or (isinstance(value, int) and value == 1)


def _mfaa_settings(root: Path, config_dir: Path) -> dict[str, Any]:
    for candidate in (root / _MFAA_SETTINGS_FILE, config_dir / _MFAA_SETTINGS_FILE):
        if candidate.is_file():
            return _read_json_object(candidate) or {}
    return {}


def _split_ids(value: Any) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _scan_mfaa(root: Path, config_dir: Path) -> list[ShellInstance]:
    instances_dir = config_dir / "instances"
    if not instances_dir.is_dir():
        return []
    settings = _mfaa_settings(root, config_dir)
    last_active = str(settings.get("Instances.LastActive") or "").strip()
    # 外壳里的排列顺序；没写或对不上的文件排在后面，按文件名
    order = {
        instance_id: position
        for position, instance_id in enumerate(
            _split_ids(settings.get("Instances.Order"))
            or _split_ids(settings.get("Instances.List"))
        )
    }
    files = sorted(
        instances_dir.glob("*.json"),
        key=lambda path: (order.get(path.stem, len(order)), path.stem),
    )

    instances: list[ShellInstance] = []
    for path in files:
        payload = _read_json_object(path)
        if payload is None:
            continue
        task_items = payload.get("TaskItems")
        if not isinstance(task_items, list):
            logger.warning(
                f"不认识的 MFAAvalonia 实例文件（没有 TaskItems），已跳过：{path}"
            )
            continue
        tasks: list[ShellTask] = []
        for item in task_items:
            if not isinstance(item, dict) or not _truthy(item.get("default_check")):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            raw_options = item.get("option")
            tasks.append(
                ShellTask(
                    name=name,
                    entry=str(item.get("entry") or "").strip(),
                    raw_options=[
                        option for option in raw_options if isinstance(option, dict)
                    ]
                    if isinstance(raw_options, list)
                    else [],
                )
            )
        instances.append(
            ShellInstance(
                id=f"mfaa:{path.stem}",
                name=str(payload.get("InstanceName") or "").strip() or path.stem,
                source=SOURCE_MFAA,
                active=bool(last_active) and last_active == path.stem,
                controller=str(payload.get("CurrentControllerName") or "").strip(),
                resource=str(payload.get("Resource") or "").strip(),
                tasks=tasks,
            )
        )
    return instances


def _scan_mxu(config_dir: Path) -> list[ShellInstance]:
    instances: list[ShellInstance] = []
    for path in sorted(config_dir.glob("mxu-*.json")):
        payload = _read_json_object(path)
        if payload is None:
            continue
        raw_instances = payload.get("instances")
        if not isinstance(raw_instances, list):
            logger.warning(f"不认识的 MXU 配置文件（没有 instances），已跳过：{path}")
            continue
        last_active = str(payload.get("lastActiveInstanceId") or "").strip()
        global_options = payload.get("globalOptionValues")
        if not isinstance(global_options, dict):
            global_options = {}
        for raw in raw_instances:
            if not isinstance(raw, dict):
                continue
            instance_id = str(raw.get("id") or "").strip()
            if not instance_id:
                continue
            controller = str(raw.get("controllerName") or "").strip()
            tasks: list[ShellTask] = []
            for task in raw.get("tasks") or []:
                if not isinstance(task, dict):
                    continue
                # MXU 按控制方式分别记勾选状态：实例当前控制方式那一格优先
                enabled = task.get("enabled")
                by_controller = task.get("enabledByController")
                if (
                    controller
                    and isinstance(by_controller, dict)
                    and controller in by_controller
                ):
                    enabled = by_controller[controller]
                name = str(task.get("taskName") or "").strip()
                if not name or not _truthy(enabled):
                    continue
                values = task.get("optionValues")
                tasks.append(
                    ShellTask(
                        name=name,
                        raw_options=values if isinstance(values, dict) else {},
                    )
                )
            instances.append(
                ShellInstance(
                    id=f"mxu:{path.name}:{instance_id}",
                    name=str(raw.get("name") or "").strip() or instance_id,
                    source=SOURCE_MXU,
                    active=bool(last_active) and last_active == instance_id,
                    controller=controller,
                    resource=str(raw.get("resourceName") or "").strip(),
                    tasks=tasks,
                    global_options=global_options,
                )
            )
    return instances


# ---------------------------------------------------------------------------
# 用户名
# ---------------------------------------------------------------------------


def assign_user_names(names: Sequence[str], existing: Iterable[str]) -> list[str]:
    """按实例顺序给每份实例定用户名：与已有用户、与前面的实例重名时加「 (2)」「 (3)」。

    实例名先按用户名规则修正（去掉文件名非法字符等），比较不分大小写。
    """

    validator = UserNameValidator()
    taken = {str(name).casefold() for name in existing}
    assigned: list[str] = []
    for raw in names:
        base = raw if validator.validate(raw) else validator.correct(raw)
        candidate = base
        suffix = 2
        while candidate.casefold() in taken:
            candidate = f"{base} ({suffix})"
            suffix += 1
        taken.add(candidate.casefold())
        assigned.append(candidate)
    return assigned


# ---------------------------------------------------------------------------
# 实例 → 任务快照
# ---------------------------------------------------------------------------


def _named_item(items: Sequence[Any], raw: str) -> str:
    """controller / resource 按名字（其次按显示名）对上 interface 里的一项，对不上返回空串。"""

    text = raw.strip()
    if not text:
        return ""
    for item in items:
        if item.name == text:
            return item.name
    folded = text.casefold()
    for item in items:
        if item.name.casefold() == folded or (item.label or "").casefold() == folded:
            return item.name
    return ""


def display_name(items: Sequence[Any], raw: str) -> str:
    """给人看的 controller / resource 名：interface 里有显示名（且不是 ``$`` 词条键）就用它。"""

    name = _named_item(items, raw)
    if not name:
        return raw.strip()
    item = next(item for item in items if item.name == name)
    label = (item.label or "").strip()
    return label if label and not label.startswith("$") else name


def plan_instance_import(
    instance: ShellInstance,
    interface: MaaFWInterface,
    *,
    script_controller: str = "",
    script_resource: str = "",
) -> ShellImportPlan:
    """把一份实例换算成用户的任务快照，当前项目里对不上的任务 / 选项 / 取值记进 ``skipped``。

    选项值先换成 interface 预设的形状（case 名、case 名列表、``{输入名: 值}``），再交给
    ``build_interface_preset_snapshot``——与「应用预设」同一条路：未导入的选项按项目默认值
    补齐，同一任务在队列里多次出现展开成重复实例。结果只留队列里的任务，与用户页保存的
    快照同形。

    ``script_controller`` / ``script_resource`` 是脚本当前的控制方式与资源（interface 里的
    名字，空串表示不限）：用户页只显示这两者下可用的任务，限定在别处的任务在这里就跳过并
    记下来，不让它们进了快照又在页面上悄悄消失。
    """

    skipped: list[str] = []
    option_maps = build_task_option_maps(interface)
    tasks_by_name: dict[str, MaaFWTask] = {}
    names_by_entry: dict[str, list[str]] = {}
    for task in interface.task:
        if task.name in tasks_by_name:
            continue
        tasks_by_name[task.name] = task
        names_by_entry.setdefault(task.entry, []).append(task.name)

    global_values: dict[str, MaaFWTaskOptionValue] = {}
    if instance.source == SOURCE_MXU and instance.global_options:
        global_values = _mxu_option_values(
            instance.global_options, interface.option, "全局选项", skipped
        )

    # MXU 把前置任务（pretask）当成队列里的一条 ``__MXU_PRETASK__<名>`` 存，MAS 的队列也认
    pretasks = {
        build_pretask_task_name(item): item for item in iter_pretasks(interface)
    }
    pretask_values: dict[str, dict[str, MaaFWTaskOptionValue]] = {}
    preset_tasks: list[MaaFWPresetTask] = []
    for shell_task in instance.tasks:
        task_name = shell_task.name
        pretask = pretasks.get(task_name)
        if pretask is not None:
            if (
                script_controller
                and pretask.controller
                and script_controller not in pretask.controller
            ):
                skipped.append(f"任务「{shell_task.name}」（当前控制方式下不可用）")
                continue
            if (
                script_resource
                and pretask.resource
                and script_resource not in pretask.resource
            ):
                skipped.append(f"任务「{shell_task.name}」（当前资源下不可用）")
                continue
            option_map = option_maps.get(task_name, {})
            values = {k: v for k, v in global_values.items() if k in option_map}
            values.update(
                _mxu_option_values(
                    shell_task.raw_options or {},
                    option_map,
                    f"「{task_name}」的选项",
                    skipped,
                )
            )
            pretask_values.setdefault(task_name, values)
            continue
        if task_name not in tasks_by_name:
            # 任务改过名但入口没变（MFAA 实例里记着 entry）：入口唯一时按入口认
            candidates = (
                names_by_entry.get(shell_task.entry, []) if shell_task.entry else []
            )
            if len(candidates) != 1:
                skipped.append(f"任务「{shell_task.name}」")
                continue
            task_name = candidates[0]
        task = tasks_by_name[task_name]
        if (
            script_controller
            and task.controller
            and script_controller not in task.controller
        ):
            skipped.append(f"任务「{shell_task.name}」（当前控制方式下不可用）")
            continue
        if script_resource and task.resource and script_resource not in task.resource:
            skipped.append(f"任务「{shell_task.name}」（当前资源下不可用）")
            continue

        option_map = option_maps.get(task_name, {})
        values: dict[str, MaaFWTaskOptionValue] = {
            name: value for name, value in global_values.items() if name in option_map
        }
        if instance.source == SOURCE_MFAA:
            _mfaa_collect_options(
                shell_task.raw_options or [],
                option_map,
                interface.option,
                task_name,
                values,
                skipped,
            )
        else:
            values.update(
                _mxu_option_values(
                    shell_task.raw_options or {},
                    option_map,
                    f"「{task_name}」的选项",
                    skipped,
                )
            )
        preset_tasks.append(
            MaaFWPresetTask(name=task_name, enabled=True, option=values)
        )

    snapshot = build_interface_preset_snapshot(
        interface,
        MaaFWPreset(name="__auto_mas_shell_import__", task=preset_tasks),
        task_option_maps=option_maps,
    )
    queued = [
        task_id for task_id in snapshot.taskOrder if snapshot.taskChecked.get(task_id)
    ]
    task_options = {
        task_id: snapshot.taskOptions.get(task_id, {}) for task_id in queued
    }
    if pretask_values:
        # 前置任务排在队列最前（与用户页一致）；选项按项目默认值补齐
        task_options.update(
            normalize_task_options_by_task(
                pretask_values, list(pretask_values), interface
            )
        )
        queued = [*pretask_values, *queued]
    return ShellImportPlan(
        snapshot={
            "taskOrder": queued,
            "taskChecked": {task_id: True for task_id in queued},
            "taskOptions": {task_id: task_options[task_id] for task_id in queued},
        },
        task_count=len(queued),
        controller=_named_item(interface.controller, instance.controller),
        resource=_named_item(interface.resource, instance.resource),
        skipped=skipped,
    )


def _case_names(definition: MaaFWOption) -> list[str]:
    return [case.name for case in definition.cases or []]


def _field_values(
    raw: Any,
    definition: MaaFWOption,
    owner: str,
    skipped: list[str],
) -> dict[str, str] | None:
    """input / hotkey 的 ``{字段名: 值}``：只留 interface 里声明了的字段，值按字符串存。"""

    if not isinstance(raw, dict):
        return None
    declared = (
        [item.name for item in definition.inputs or []]
        if definition.type == "input"
        else [item.name for item in definition.hotkeys or []]
    )
    fields: dict[str, str] = {}
    for key, value in raw.items():
        if str(key) not in declared:
            skipped.append(f"{owner}的「{key}」")
            continue
        if value is None or isinstance(value, (dict, list)):
            continue
        if isinstance(value, bool):
            fields[str(key)] = "true" if value else "false"
        else:
            fields[str(key)] = str(value)
    return fields


def _mfaa_collect_options(
    raw_options: Sequence[Any],
    option_map: Mapping[str, MaaFWOption],
    all_options: Mapping[str, MaaFWOption],
    task_name: str,
    values: dict[str, MaaFWTaskOptionValue],
    skipped: list[str],
) -> None:
    """MFAAvalonia 的 ``[{name, index, selected_cases?, data?, sub_options?}]`` 逐层展平。"""

    for raw in raw_options:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        owner = f"「{task_name}」的选项「{name}」"
        definition = option_map.get(name)
        if definition is None:
            skipped.append(owner)
            continue
        value = _mfaa_option_value(raw, definition, owner, skipped)
        if value is not None:
            values[name] = value
        sub_options = raw.get("sub_options")
        if not isinstance(sub_options, list):
            continue
        case_names = set(_case_names(definition))
        nested: list[Any] = []
        for sub in sub_options:
            if not isinstance(sub, dict):
                continue
            sub_name = str(sub.get("name") or "")
            # checkbox 的 sub_options 是各个 case 的容器（勾选另记在 selected_cases），
            # 容器自己再挂的 sub_options 才是选项
            if sub_name in case_names and sub_name not in all_options:
                inner = sub.get("sub_options")
                if isinstance(inner, list):
                    nested.extend(inner)
                continue
            nested.append(sub)
        _mfaa_collect_options(
            nested, option_map, all_options, task_name, values, skipped
        )


def _mfaa_option_value(
    raw: Mapping[str, Any],
    definition: MaaFWOption,
    owner: str,
    skipped: list[str],
) -> MaaFWTaskOptionValue | None:
    cases = _case_names(definition)
    if definition.type in _CHOICE_TYPES:
        index = raw.get("index")
        if index is None:
            return None  # 外壳没记取值（没有 case 的占位选项就是这样），按项目默认
        if (
            isinstance(index, int)
            and not isinstance(index, bool)
            and 0 <= index < len(cases)
        ):
            return cases[index]
        skipped.append(f"{owner}的取值")
        return None
    if definition.type == "checkbox":
        selected = raw.get("selected_cases")
        if not isinstance(selected, list):
            return None
        chosen: list[str] = []
        for item in selected:
            if str(item) in cases:
                chosen.append(str(item))
            else:
                skipped.append(f"{owner}的取值「{item}」")
        return chosen
    if definition.type in _FIELD_TYPES:
        return _field_values(raw.get("data"), definition, owner, skipped)
    skipped.append(f"{owner}的取值")
    return None


def _mxu_option_values(
    option_values: Mapping[str, Any],
    option_map: Mapping[str, MaaFWOption],
    owner_prefix: str,
    skipped: list[str],
) -> dict[str, MaaFWTaskOptionValue]:
    """MXU 的 ``{选项名: {type, caseName | caseNames | value | values}}``（嵌套选项已平铺）。"""

    values: dict[str, MaaFWTaskOptionValue] = {}
    for name, raw in option_values.items():
        owner = f"{owner_prefix}「{name}」"
        definition = option_map.get(str(name))
        if definition is None:
            skipped.append(owner)
            continue
        value = _mxu_option_value(raw, definition, owner, skipped)
        if value is not None:
            values[str(name)] = value
    return values


def _mxu_option_value(
    raw: Any,
    definition: MaaFWOption,
    owner: str,
    skipped: list[str],
) -> MaaFWTaskOptionValue | None:
    if not isinstance(raw, dict):
        skipped.append(f"{owner}的取值")
        return None
    cases = _case_names(definition)
    if definition.type in _CHOICE_TYPES:
        if "caseName" in raw:
            case = str(raw.get("caseName") or "")
        elif isinstance(raw.get("value"), bool):
            wanted = _SWITCH_TRUE_NAMES if raw["value"] else _SWITCH_FALSE_NAMES
            case = next((name for name in cases if name.casefold() in wanted), "")
        else:
            case = str(raw.get("value") or "")
        # scan_select 的候选是运行时扫出来的，interface 里可能一个都没写
        if case and (case in cases or (definition.type == "scan_select" and not cases)):
            return case
        skipped.append(f"{owner}的取值" + (f"「{case}」" if case else ""))
        return None
    if definition.type == "checkbox":
        selected = raw.get("caseNames")
        if not isinstance(selected, list):
            skipped.append(f"{owner}的取值")
            return None
        chosen: list[str] = []
        for item in selected:
            if str(item) in cases:
                chosen.append(str(item))
            else:
                skipped.append(f"{owner}的取值「{item}」")
        return chosen
    if definition.type in _FIELD_TYPES:
        fields = _field_values(raw.get("values"), definition, owner, skipped)
        if fields is None:
            skipped.append(f"{owner}的取值")
        return fields
    skipped.append(f"{owner}的取值")
    return None


__all__ = [
    "SOURCE_MFAA",
    "SOURCE_MXU",
    "ShellImportPlan",
    "ShellInstance",
    "ShellTask",
    "assign_user_names",
    "display_name",
    "plan_instance_import",
    "scan_shell_instances",
]
