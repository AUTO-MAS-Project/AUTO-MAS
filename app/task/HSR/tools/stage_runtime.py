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


import ast
import json
from typing import Any

from . import m7a_config as m7a


def read_native_stage(
    user_config: Any,
    field: str,
    engine: str | None = None,
) -> dict[str, Any] | None:
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
    return _select_engine_stage(data, engine)


def read_native_main_stage(
    user_config: Any,
    engine: str | None = None,
) -> dict[str, Any] | None:
    return read_native_stage_for_channel(
        user_config,
        str(user_config.get("Stage", "Channel") or "CalyxGolden"),
        engine,
    )


def read_native_stage_for_channel(
    user_config: Any,
    channel: str,
    engine: str | None = None,
) -> dict[str, Any] | None:
    """读取用户配置中指定体力类型保存的脚本原生副本字段。"""

    data = read_native_stage(user_config, "ScriptStage", engine)
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
    native = _get_m7a_native_stage(read_native_main_stage(user_config, "M7A"))
    if native is not None and native[0] in m7a.M7A_INSTANCE_TYPES_DAILY:
        return native
    return None


def resolve_m7a_ornament_stage(user_config: Any) -> str | None:
    native = _get_m7a_native_stage(
        read_native_stage_for_channel(user_config, "Ornament", "M7A")
    )
    if native is not None and native[0] == m7a.M7A_INSTANCE_TYPE_ORNAMENT:
        return native[1]
    return None


def resolve_m7a_eow_stage(user_config: Any) -> str | None:
    native = _get_m7a_native_stage(
        read_native_stage(user_config, "ScriptEchoOfWar", "M7A")
    )
    if native is not None and native[0] == m7a.M7A_EOW_INSTANCE_NAME_KEY:
        return native[1]
    return None


def resolve_configured_daily_stages(user_config: Any, engine: str) -> tuple[bool, bool]:
    """返回指定引擎名下 (是否配置了体力主关卡, 是否配置了历战余响关卡)。

    关卡按引擎分桶保存，这里只看 ``engine`` 自己那一份。自动代理决定体力模块
    是否跳过与任务预检共用这一处判定，避免两边口径漂移。
    """

    normalized = str(engine or "").strip().upper()
    if normalized == "SRA":
        main_configured = (
            get_sra_native_stage(read_native_main_stage(user_config, "SRA")) is not None
        )
        eow_configured = (
            get_sra_native_stage(
                read_native_stage(user_config, "ScriptEchoOfWar", "SRA")
            )
            is not None
        )
        return main_configured, eow_configured
    return (
        resolve_m7a_main_stage(user_config) is not None,
        resolve_m7a_eow_stage(user_config) is not None,
    )


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


def _select_engine_stage(
    data: dict[str, Any],
    engine: str | None,
) -> dict[str, Any] | None:
    """选择新版分引擎 stage 容器，同时兼容旧版单引擎对象。"""

    if engine is None:
        return data

    normalized = str(engine).strip().upper()
    by_engine = data.get("byEngine")
    if isinstance(by_engine, dict):
        selected = by_engine.get(normalized)
        return selected if isinstance(selected, dict) and selected else None

    stored_engine = str(data.get("engine") or "").strip().upper()
    if stored_engine:
        return data if stored_engine == normalized else None

    # 早期版本只在各 selected stage 上记录 engine 标记；迁移期间继续支持。
    stages = data.get("stages")
    if isinstance(stages, dict):
        for payload in stages.values():
            if isinstance(payload, dict) and _matches_native_engine(
                payload, normalized
            ):
                return data
    return None


_SRA_LEGACY_LABEL_PREFIX = "{'id':"


def migrate_sra_legacy_stage_labels(raw: Any) -> tuple[str | None, int, int]:
    """把旧版误读 SRA toml 留下的副本载荷迁成真实关卡编号。

    旧版把 ``trailblaze_power.toml`` 的内联表 ``{ id, name, result }`` 当成字符串，
    存下的 ``label`` 是 Python 字典 repr、``level`` 是数组位置。repr 里带着真实
    ``id``，据此改写 ``level`` / ``label`` / ``detail`` / ``value``，一次性且无损。
    ``label`` 不是 repr 形态的载荷无从判断编号是否正确，一律不动；按位置重排
    正是要修的错误，不能再犯一遍。

    Args:
        raw: ``Stage.ScriptStage`` 或 ``Stage.ScriptEchoOfWar`` 的原始值。

    Returns:
        ``(迁移后的 JSON 字符串或 None, 迁移条数, 无法确认的旧载荷条数)``；
        没有需要改写的载荷时第一项为 None。无法确认的只统计 ``detail`` 为空、
        ``label`` 又不是 repr 的 SRA 载荷——新版选项都带掉落说明。
    """

    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None, 0, 0
    elif isinstance(raw, dict):
        data = raw
    else:
        return None, 0, 0
    if not isinstance(data, dict):
        return None, 0, 0

    counts = {"migrated": 0, "unresolved": 0}

    def visit(node: Any) -> None:
        if isinstance(node, list):
            for child in node:
                visit(child)
            return
        if not isinstance(node, dict):
            return
        nested = node.get("sra")
        if isinstance(nested, dict):
            _migrate_sra_payload(node, nested, counts)
            return
        for child in node.values():
            visit(child)

    visit(data)
    if not counts["migrated"]:
        return None, 0, counts["unresolved"]
    return (
        json.dumps(data, ensure_ascii=False),
        counts["migrated"],
        counts["unresolved"],
    )


def _migrate_sra_payload(
    payload: dict[str, Any], nested: dict[str, Any], counts: dict[str, int]
) -> None:
    label = str(payload.get("label") or "").strip()
    if not label.startswith(_SRA_LEGACY_LABEL_PREFIX):
        if not str(payload.get("detail") or "").strip():
            counts["unresolved"] += 1
        return
    try:
        item = ast.literal_eval(label)
    except (ValueError, SyntaxError):
        counts["unresolved"] += 1
        return
    level = _safe_int(item.get("id")) if isinstance(item, dict) else None
    name = str(item.get("name") or "").strip() if isinstance(item, dict) else ""
    if level is None or level <= 0 or not name:
        counts["unresolved"] += 1
        return

    nested["level"] = level
    payload["label"] = name
    payload["detail"] = str(item.get("result") or "").strip()
    task_id = str(nested.get("id") or payload.get("category") or "").strip()
    if task_id:
        payload["value"] = f"SRA::{task_id}::{level}"
    counts["migrated"] += 1


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
