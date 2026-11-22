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

"""内置 MaaEnd 复用的 interface 标签可读化与 MXU 选项值换算（解析一侧）。

从 ``shell_instances.py`` 原样切出，私有名 ``_Labels``、
``_mxu_option_values`` 改成公开名 ``Labels``、``mxu_option_values``；外壳文件扫描与宿主依赖
留在 ``shell_instances``，它从这里导入这几样。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .interface.models import (
    MaaFWInterface,
    MaaFWOption,
    MaaFWTaskOptionValue,
    build_pretask_task_name,
    iter_pretasks,
)

#: switch 的布尔值按 case 名对应（PI v2 的 switch 两个 case 通常叫 Yes / No，顺序不固定，
#: M9A 就同时有 [Yes, No] 与 [No, Yes]），不按下标猜。
_SWITCH_TRUE_NAMES = frozenset({"yes", "y", "true", "on", "1", "是", "开"})
_SWITCH_FALSE_NAMES = frozenset({"no", "n", "false", "off", "0", "否", "关"})
_CHOICE_TYPES = frozenset({"select", "scan_select", "switch"})
_FIELD_TYPES = frozenset({"input", "hotkey"})


#: 把 interface 里的 ``$键`` 文案按项目语言文件翻成给人看的字，翻不出来原样返回。
Translate = Callable[[str | None], str | None]


def _readable(raw: str | None, fallback: str, translate: Translate | None) -> str:
    """显示名：先按语言文件翻，翻不出来（空、仍是 ``$键``）就用 ``fallback``。"""

    text = translate(raw) if translate is not None else raw
    text = (text or "").strip()
    return text if text and not text.startswith("$") else fallback


class Labels:
    """跳过项里写给人看的任务 / 选项 / 取值名：interface 的 label 按语言文件翻过，拿不到才用 name。"""

    def __init__(self, interface: MaaFWInterface, translate: Translate | None) -> None:
        self._interface = interface
        self._translate = translate
        self._tasks: dict[str, str | None] = {}
        for task in interface.task:
            self._tasks.setdefault(task.name, task.label)
        for pretask in iter_pretasks(interface):
            self._tasks.setdefault(build_pretask_task_name(pretask), pretask.label)

    def task(self, name: str) -> str:
        return _readable(self._tasks.get(name), name, self._translate)

    def option(self, name: str) -> str:
        definition = self._interface.option.get(name)
        label = definition.label if definition is not None else None
        return _readable(label, name, self._translate)

    def case(self, definition: MaaFWOption, name: str) -> str:
        case = next(
            (item for item in definition.cases or [] if item.name == name), None
        )
        return _readable(case.label if case else None, name, self._translate)

    def field(self, definition: MaaFWOption, name: str) -> str:
        fields = [*(definition.inputs or []), *(definition.hotkeys or [])]
        item = next((item for item in fields if item.name == name), None)
        return _readable(item.label if item else None, name, self._translate)


def _case_names(definition: MaaFWOption) -> list[str]:
    return [case.name for case in definition.cases or []]


def _field_values(
    raw: Any,
    definition: MaaFWOption,
    owner: str,
    labels: Labels,
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
            skipped.append(f"{owner}的「{labels.field(definition, str(key))}」")
            continue
        if value is None or isinstance(value, (dict, list)):
            continue
        if isinstance(value, bool):
            fields[str(key)] = "true" if value else "false"
        elif isinstance(value, float) and value.is_integer():
            fields[str(key)] = str(int(value))
        else:
            fields[str(key)] = str(value)
    return fields


def mxu_option_values(
    option_values: Mapping[str, Any],
    option_map: Mapping[str, MaaFWOption],
    owner_prefix: str,
    labels: Labels,
    skipped: list[str],
) -> dict[str, MaaFWTaskOptionValue]:
    """MXU 的 ``{选项名: {type, caseName | caseNames | value | values}}``（嵌套选项已平铺）。"""

    values: dict[str, MaaFWTaskOptionValue] = {}
    for name, raw in option_values.items():
        owner = f"{owner_prefix}「{labels.option(str(name))}」"
        definition = option_map.get(str(name))
        if definition is None:
            skipped.append(owner)
            continue
        value = _mxu_option_value(raw, definition, owner, labels, skipped)
        if value is not None:
            values[str(name)] = value
    return values


def _mxu_option_value(
    raw: Any,
    definition: MaaFWOption,
    owner: str,
    labels: Labels,
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
        skipped.append(
            f"{owner}的取值" + (f"「{labels.case(definition, case)}」" if case else "")
        )
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
                skipped.append(f"{owner}的取值「{labels.case(definition, str(item))}」")
        return chosen
    if definition.type in _FIELD_TYPES:
        fields = _field_values(raw.get("values"), definition, owner, labels, skipped)
        if fields is None:
            skipped.append(f"{owner}的取值")
        return fields
    skipped.append(f"{owner}的取值")
    return None


__all__ = ["Labels", "Translate", "mxu_option_values"]
