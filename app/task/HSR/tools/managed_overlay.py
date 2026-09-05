#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.
#
#   Contact: DLmaster_361@163.com


"""把用户 ``Managed.Options`` 覆盖值叠到 SRA / M7A 原生字段上。

用户升级外部脚本或更换 profile 后，覆盖层里可能残留原生配置已不存在的键，
或者值类型对不上。这里不再整体抛错：对不上的键逐个丢弃、用原生值兜底，
并把丢弃记录交给表单和运行日志，用户的任务不该因为一个过期的配置键而失败。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, Mapping

DroppedOverrideReason = Literal["unknown", "type"]

DROPPED_OVERRIDE_WARNING_KIND = "dropped_override"


@dataclass(frozen=True, slots=True)
class DroppedOverride:
    """一条被忽略的 ``Managed.Options`` 覆盖值。"""

    key: str
    reason: DroppedOverrideReason
    value: Any

    def describe(self) -> str:
        if self.reason == "unknown":
            return f"{self.key}：当前原生配置没有该字段"
        return f"{self.key}：保存的值类型与原生配置不一致"

    def as_warning(self) -> str:
        """编码成 ``HSRManagedForm.warnings`` 里的一条。

        托管表单的响应模型只有 ``warnings: list[str]`` 这一个逐表单通道，这里
        用 JSON 字串承载结构化信息，前端按 ``kind`` 识别并还原成键与原因。
        """

        return json.dumps(
            {
                "kind": DROPPED_OVERRIDE_WARNING_KIND,
                "key": self.key,
                "reason": self.reason,
                "value": self.value,
                "message": self.describe(),
            },
            ensure_ascii=False,
            default=str,
        )


def same_value_kind(value: Any, reference: Any) -> bool:
    """覆盖值与原生值是否属于同一类型族。"""

    if isinstance(reference, bool):
        return isinstance(value, bool)
    if isinstance(reference, int):
        return isinstance(value, int) and not isinstance(value, bool)
    if isinstance(reference, float):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(reference, list):
        return isinstance(value, list)
    if isinstance(reference, dict):
        return isinstance(value, dict)
    return isinstance(value, str) if isinstance(reference, str) else True


def overlay_managed_options(
    native: Mapping[str, Any],
    overrides: Mapping[str, Any],
) -> tuple[dict[str, Any], tuple[DroppedOverride, ...]]:
    """返回 ``(生效值, 被丢弃的覆盖)``；不认识或类型不符的键回退到原生值。"""

    effective = dict(native)
    dropped: list[DroppedOverride] = []
    for key, value in overrides.items():
        key = str(key)
        if key not in native:
            dropped.append(DroppedOverride(key, "unknown", value))
            continue
        if not same_value_kind(value, native[key]):
            dropped.append(DroppedOverride(key, "type", value))
            continue
        effective[key] = value
    return effective, tuple(dropped)


def log_dropped_overrides(
    logger: Any,
    engine: str,
    module_key: str,
    dropped: tuple[DroppedOverride, ...],
) -> None:
    """在 MAS 日志里说明本次运行忽略了哪些覆盖值。"""

    if not dropped:
        return
    detail = "；".join(item.describe() for item in dropped)
    logger.warning(
        f"{engine} {module_key} 忽略 {len(dropped)} 项失效的 MAS 覆盖配置，"
        f"已按原生配置运行：{detail}"
    )


__all__ = [
    "DROPPED_OVERRIDE_WARNING_KIND",
    "DroppedOverride",
    "DroppedOverrideReason",
    "log_dropped_overrides",
    "overlay_managed_options",
    "same_value_kind",
]
