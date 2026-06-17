#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
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


import json
from typing import Any

from . import m7a_config as m7a


def read_native_stage(user_config: Any, field: str) -> dict[str, Any] | None:
    """读取用户配置中保存的脚本原生副本字段。"""

    raw = user_config.get("Stage", field)
    if raw is None:
        return None
    if isinstance(raw, dict):
        data = raw
    elif isinstance(raw, str):
        text = raw.strip()
        if not text or text in {"{}", "{ }"}:
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
    else:
        return None

    if not isinstance(data, dict) or not data:
        return None
    return data


def read_native_main_stage(user_config: Any) -> dict[str, Any] | None:
    return read_native_stage_for_channel(
        user_config,
        str(user_config.get("Stage", "Channel") or "CalyxGolden"),
    )


def read_native_stage_for_channel(
    user_config: Any,
    channel: str,
) -> dict[str, Any] | None:
    """读取用户配置中指定体力类型保存的脚本原生副本字段。"""

    data = read_native_stage(user_config, "ScriptStage")
    if data is None:
        return None

    stages = data.get("stages")
    if isinstance(stages, dict):
        payload = stages.get(channel)
        if isinstance(payload, dict) and payload:
            return payload
    return None


def get_sra_native_stage(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not _matches_native_engine(data, "SRA"):
        return None
    assert data is not None

    nested = data.get("sra")
    if not isinstance(nested, dict):
        return None

    sra_id = str(nested.get("id") or "").strip()
    level = _safe_int(nested.get("level"))
    if not sra_id or level is None or level <= 0:
        return None

    return {
        "id": sra_id,
        "level": level,
        "label": str(data.get("label") or "").strip(),
        "category": str(data.get("category") or "").strip(),
        "categoryLabel": str(data.get("categoryLabel") or "").strip(),
        "value": str(data.get("value") or "").strip(),
    }


def resolve_m7a_main_stage(user_config: Any) -> tuple[str, str] | None:
    native = _get_m7a_native_stage(read_native_main_stage(user_config))
    if native is not None and native[0] in m7a.M7A_INSTANCE_TYPES_DAILY:
        return native
    return None


def resolve_m7a_ornament_stage(user_config: Any) -> str | None:
    native = _get_m7a_native_stage(read_native_stage_for_channel(user_config, "Ornament"))
    if native is not None and native[0] == m7a.M7A_INSTANCE_TYPE_ORNAMENT:
        return native[1]
    return None


def resolve_m7a_eow_stage(user_config: Any) -> str | None:
    native = _get_m7a_native_stage(read_native_stage(user_config, "ScriptEchoOfWar"))
    if native is not None and native[0] == m7a.M7A_EOW_INSTANCE_NAME_KEY:
        return native[1]
    return None


def _get_m7a_native_stage(data: dict[str, Any] | None) -> tuple[str, str] | None:
    if not _matches_native_engine(data, "M7A"):
        return None
    assert data is not None

    nested = data.get("m7a")
    if not isinstance(nested, dict):
        return None

    instance_type = str(nested.get("instanceType") or "").strip()
    instance_name = str(nested.get("instanceName") or "").strip()
    if not instance_type or not instance_name or instance_name == "无":
        return None
    return instance_type, instance_name


def _matches_native_engine(data: dict[str, Any] | None, expected: str) -> bool:
    if not data:
        return False
    engine = str(data.get("engine") or "").strip().upper()
    return engine == expected


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
