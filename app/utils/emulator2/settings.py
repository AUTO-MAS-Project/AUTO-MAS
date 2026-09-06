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

"""四项实例设置的读写规则——纯逻辑，不碰文件也不起进程。

**只有四项**：分辨率（含 DPI）、CPU 核数、内存、帧率。落到雷电 14 是 6 个 JSON 键。

三条实测结论决定了这里的形状：

1. **走文件，不走命令行。** ``ldconsole modify`` 根本没有帧率参数，CPU / 内存只收有限档位
   （``--cpu 1|2|3|4`` 和 8 个内存档），一写就把本机实际生效的 6 核 / 6144 MB 降下去；
   而且命令行没有读取能力。四个字段全在实例的 ``.config`` 里，``.vbox`` 不用碰。
2. **雷电的 config 是懒 materialize 的**：刚 ``add`` 出来 11 键，启动过 28 键，
   在界面里动过设置 90 键。所以「文件里没有这个键」不等于「没有值」——
   28 键的实例没有 ``cpuCount``，但它实际跑在雷电默认的 6 核上。
3. 因此**必须区分四种状态**，见 :data:`FieldState`。把「默认值」混进「已保存」，
   界面就会声称用户保存过一个他从没设过的值。

写入只提交用户真正改过的字段，其余键原样保留——见 :func:`apply_changes`。
"""

import re
from dataclasses import dataclass
from typing import Any, Literal

#: 字段状态。
#:
#: - ``saved``       实例配置里有这个键, 是用户保存过的值
#: - ``default``     实例配置里没有, 从 ``.vbox`` 回落读到的雷电默认值
#: - ``unset``       两边都没有 (从未启动过的实例)
#: - ``unreadable``  配置文件读不出或解析失败
FieldState = Literal["saved", "default", "unset", "unreadable"]

#: 对外字段名 → 实例配置里的路径。
#:
#: **雷电的配置是平铺的，键名自带点号**，不是嵌套对象：顶层就是
#: ``"advancedSettings.resolutionDpi": 240`` 这样的键。唯一的例外是
#: ``advancedSettings.resolution``，它的值才是个 ``{"width":…, "height":…}``。
#:
#: 这点必须照着实测的文件结构来。按"点号=嵌套"去写会在配置里造出一个
#: 雷电根本不认识的 ``advancedSettings`` 对象——文件写进去了，回读也自洽，
#: 但**模拟器一个字都不会读**。
_FIELD_PATHS: dict[str, tuple[str, ...]] = {
    "width": ("advancedSettings.resolution", "width"),
    "height": ("advancedSettings.resolution", "height"),
    "dpi": ("advancedSettings.resolutionDpi",),
    "cpu": ("advancedSettings.cpuCount",),
    "memoryMb": ("advancedSettings.memorySize",),
    "fps": ("basicSettings.fps",),
}

FIELDS: tuple[str, ...] = tuple(_FIELD_PATHS)

#: 合法区间。**这是防呆边界，不是雷电真正接受的取值集合**——
#: 实测只覆盖了 CPU 2→1、内存 2048、960×540、DPI 160 这一组，
#: 边界值与雷电的静默纠正行为都没测过。所以这里只拦明显离谱的输入，
#: 落在区间内也不保证雷电照单全收。
_RANGES: dict[str, tuple[int, int]] = {
    "width": (160, 4096),
    "height": (160, 4096),
    "dpi": (80, 640),
    "cpu": (1, 64),
    "memoryMb": (512, 65536),
    "fps": (1, 240),
}

#: 只有这两项在 ``.vbox`` 里被证实是「雷电默认值」的来源。
#: 分辨率 / DPI / 帧率没有验证过同样的回落关系，宁可报「未设置」也不猜。
_VBOX_PATTERNS: dict[str, re.Pattern[str]] = {
    "cpu": re.compile(r'<CPU\b[^>]*\bcount="(\d+)"'),
    "memoryMb": re.compile(r'<Memory\b[^>]*\bRAMSize="(\d+)"'),
}


class SettingsConflictError(RuntimeError):
    """打开表单之后、保存之前，文件被别人改了。

    「别人」多半是雷电自己的多开器或设置窗口——那两个窗口把配置读进内存、
    关闭时整体写回，我们的实例锁完全管不到。这时候**拒绝写入并要求刷新**，
    绝不能把表单打开时的旧值整片盖回去。
    """

    def __init__(self, fields: list[str]) -> None:
        super().__init__("配置在编辑期间被改动: " + ", ".join(fields))
        self.fields = fields


@dataclass(frozen=True)
class FieldValue:
    value: int | None
    state: FieldState


@dataclass(frozen=True)
class InstanceSettings:
    fields: dict[str, FieldValue]

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return {
            name: {"value": item.value, "state": item.state}
            for name, item in self.fields.items()
        }

    def values(self) -> dict[str, int | None]:
        """只要值，供冲突比对用。"""
        return {name: item.value for name, item in self.fields.items()}


def _dig(data: dict, path: tuple[str, ...]) -> Any:
    cursor: Any = data
    for key in path:
        if not isinstance(cursor, dict) or key not in cursor:
            return None
        cursor = cursor[key]
    return cursor


def _as_int(raw: Any) -> int | None:
    """只认真正的整数值。

    ``bool`` 是 ``int`` 的子类，得单独挡掉；浮点只在恰好是整数时接受
    （雷电偶尔把内存写成 ``2048.0``）。
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    return None


def read_saved(config: dict | None) -> dict[str, int]:
    """从实例配置取用户保存过的字段。缺的键不出现在结果里。"""
    if not isinstance(config, dict):
        return {}
    found: dict[str, int] = {}
    for name, path in _FIELD_PATHS.items():
        value = _as_int(_dig(config, path))
        if value is not None:
            found[name] = value
    return found


def read_vbox_defaults(xml_text: str | None) -> dict[str, int]:
    """从 ``leidian.vbox`` 取雷电默认的 CPU / 内存。

    只有这两项有实测依据：28 键的实例配置里没有 ``cpuCount`` / ``memorySize``，
    而 ``.vbox`` 里是 ``CPU count="6"`` / ``RAMSize="6144"``。
    """
    if not xml_text:
        return {}
    found: dict[str, int] = {}
    for name, pattern in _VBOX_PATTERNS.items():
        match = pattern.search(xml_text)
        if match:
            found[name] = int(match.group(1))
    return found


def build_settings(
    config: dict | None, vbox_text: str | None, readable: bool = True
) -> InstanceSettings:
    """把三层来源合成四态字段表。"""
    if not readable:
        return InstanceSettings(
            fields={name: FieldValue(None, "unreadable") for name in FIELDS}
        )

    saved = read_saved(config)
    defaults = read_vbox_defaults(vbox_text)

    fields: dict[str, FieldValue] = {}
    for name in FIELDS:
        if name in saved:
            fields[name] = FieldValue(saved[name], "saved")
        elif name in defaults:
            fields[name] = FieldValue(defaults[name], "default")
        else:
            fields[name] = FieldValue(None, "unset")
    return InstanceSettings(fields=fields)


def validate_changes(changes: dict[str, Any]) -> dict[str, int]:
    """校验并归一化一批改动。非法输入直接抛，带上人能读的原因。"""
    if not changes:
        raise ValueError("没有要修改的设置项")

    cleaned: dict[str, int] = {}
    for name, raw in changes.items():
        if name not in _FIELD_PATHS:
            raise ValueError(f"未知的设置项: {name}")
        value = _as_int(raw)
        if value is None:
            raise ValueError(f"设置项 {name} 需要一个整数")
        low, high = _RANGES[name]
        if not low <= value <= high:
            raise ValueError(f"设置项 {name} 超出可接受范围 {low}~{high}: {value}")
        cleaned[name] = value

    # 宽高必须成对：只写一半会让雷电按另一半的旧值算比例，出来的分辨率不是用户要的
    if ("width" in cleaned) != ("height" in cleaned):
        raise ValueError("分辨率的宽和高必须同时提供")

    return cleaned


def detect_conflicts(
    current: InstanceSettings, expected: dict[str, Any], changing: list[str]
) -> list[str]:
    """比对「表单打开时看到的值」和「现在文件里的值」，只看要改的字段。

    ``expected`` 里没有的字段不参与比对——批量设置就是这么绕过冲突检查的：
    用户明确要求把所有实例设成同一组值，本来就是覆盖。
    """
    now = current.values()
    changed: list[str] = []
    for name in changing:
        if name not in expected:
            continue
        if now.get(name) != _as_int(expected[name]):
            changed.append(name)
    return changed


def apply_changes(config: dict, changes: dict[str, int]) -> dict:
    """把改动 merge 进一份配置，返回新字典。

    只碰 :data:`_FIELD_PATHS` 里那几个键，其余原样保留——
    28 键的实例保存后仍应是 28 键加上新写的那几个，不能被我们写成一份精简配置。
    """
    merged = {
        key: (dict(value) if isinstance(value, dict) else value)
        for key, value in config.items()
    }
    for name, value in changes.items():
        path = _FIELD_PATHS[name]
        cursor = merged
        for key in path[:-1]:
            existing = cursor.get(key)
            cursor[key] = dict(existing) if isinstance(existing, dict) else {}
            cursor = cursor[key]
        cursor[path[-1]] = value
    return merged
