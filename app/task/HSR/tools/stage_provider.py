#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright (C) 2024-2025 DLmaster361
#   Copyright (C) 2025-2026 AUTO-MAS Team
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

"""HSR 体力副本动态选项读取器。

本模块只负责把 M7A / SRA 暴露的原生副本配置整理成前端可消费的统一结构。
执行层按脚本原生字段落盘和构造任务。
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from app.task.HSR.tools.m7a_config import (
    M7A_ATTEMPTS_PER_RUN_MAX,
    M7A_EOW_INSTANCE_NAME_KEY,
    M7A_INSTANCE_TYPE_CALYX_CRIMSON,
    M7A_INSTANCE_TYPE_CALYX_GOLDEN,
    M7A_INSTANCE_TYPE_ORNAMENT,
    M7A_INSTANCE_TYPE_RELIC,
    M7A_INSTANCE_TYPE_STAGNANT_SHADOW,
)

HSR_STAGE_ENGINE_M7A = "M7A"
HSR_STAGE_ENGINE_SRA = "SRA"

SRA_TP_TASK_ORDER = (
    "calyx_golden",
    "calyx_crimson",
    "stagnant_shadow",
    "caver_of_corrosion",
    "ornament_extraction",
    "echo_of_war",
)

SRA_TP_TASK_LABELS = {
    "calyx_golden": "拟造花萼（金）",
    "calyx_crimson": "拟造花萼（赤）",
    "stagnant_shadow": "凝滞虚影",
    "caver_of_corrosion": "侵蚀隧洞",
    "ornament_extraction": "饰品提取",
    "echo_of_war": "历战余响",
}

SRA_TP_COSTS = {
    "calyx_golden": 10,
    "calyx_crimson": 10,
    "stagnant_shadow": 30,
    "caver_of_corrosion": 40,
    "ornament_extraction": 40,
    "echo_of_war": 30,
}

M7A_CATEGORY_ORDER = (
    M7A_INSTANCE_TYPE_CALYX_GOLDEN,
    M7A_INSTANCE_TYPE_CALYX_CRIMSON,
    M7A_INSTANCE_TYPE_STAGNANT_SHADOW,
    M7A_INSTANCE_TYPE_RELIC,
    M7A_INSTANCE_TYPE_ORNAMENT,
    M7A_EOW_INSTANCE_NAME_KEY,
)

M7A_COSTS = {
    M7A_INSTANCE_TYPE_CALYX_GOLDEN: 10,
    M7A_INSTANCE_TYPE_CALYX_CRIMSON: 10,
    M7A_INSTANCE_TYPE_STAGNANT_SHADOW: 30,
    M7A_INSTANCE_TYPE_RELIC: 40,
    M7A_INSTANCE_TYPE_ORNAMENT: 40,
    M7A_EOW_INSTANCE_NAME_KEY: 30,
}

HSR_STAGE_CATEGORY_LABELS = {
    **SRA_TP_TASK_LABELS,
    M7A_INSTANCE_TYPE_CALYX_GOLDEN: "拟造花萼（金）",
    M7A_INSTANCE_TYPE_CALYX_CRIMSON: "拟造花萼（赤）",
    M7A_INSTANCE_TYPE_STAGNANT_SHADOW: "凝滞虚影",
    M7A_INSTANCE_TYPE_RELIC: "侵蚀隧洞",
    M7A_INSTANCE_TYPE_ORNAMENT: "饰品提取",
    M7A_EOW_INSTANCE_NAME_KEY: "历战余响",
}

def get_hsr_stage_options(script_config: Any, engine: str) -> dict[str, Any]:
    """返回指定执行脚本的体力副本选项。"""

    normalized = str(engine or "").strip().upper()
    if normalized == HSR_STAGE_ENGINE_M7A:
        return get_m7a_stage_options(script_config)
    if normalized == HSR_STAGE_ENGINE_SRA:
        return get_sra_stage_options(script_config)
    raise ValueError(f"不支持的 HSR 体力执行脚本: {engine!r}")


def get_m7a_stage_options(script_config: Any) -> dict[str, Any]:
    """从 M7A assets/config 读取副本选项。"""

    assets_dir = _m7a_assets_config_dir(script_config)
    return _build_m7a_options_from_assets(assets_dir)


def get_sra_stage_options(script_config: Any) -> dict[str, Any]:
    """从 SRA trailblaze_power.toml 读取副本选项。"""

    toml_path = _sra_trailblaze_power_toml_path(script_config)
    return _build_sra_options_from_toml(toml_path)


def _m7a_assets_config_dir(script_config: Any) -> Path:
    root = str(script_config.get("Info", "M7APath") or "").strip()
    if not root:
        raise RuntimeError("未配置三月七路径，无法读取副本配置")
    path = Path(root)
    candidates = [
        path / "assets" / "config",
        path.parent / "assets" / "config",
    ]
    for candidate in candidates:
        if (
            (candidate / "instance_names.json").exists()
            and (candidate / "instance_drops.json").exists()
        ):
            return candidate
    checked = "、".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"未找到三月七 assets/config 副本配置文件，已检查: {checked}")


def _sra_trailblaze_power_toml_path(script_config: Any) -> Path:
    root = str(script_config.get("Info", "SRAPath") or "").strip()
    if not root:
        raise RuntimeError("未配置 SRA 路径，无法读取体力副本配置")
    path = Path(root)
    candidates = [
        path / "tasks" / "config" / "trailblaze_power.toml",
        path.parent / "tasks" / "config" / "trailblaze_power.toml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    checked = "、".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"未找到 SRA trailblaze_power.toml，已检查: {checked}")


def _build_m7a_options_from_assets(assets_dir: Path) -> dict[str, Any]:
    names_path = assets_dir / "instance_names.json"
    drops_path = assets_dir / "instance_drops.json"
    names_data = json.loads(names_path.read_text(encoding="utf-8"))
    drops_data = json.loads(drops_path.read_text(encoding="utf-8"))
    if not isinstance(names_data, dict):
        raise ValueError("instance_names.json 顶层不是 JSON 对象")
    if not isinstance(drops_data, dict):
        drops_data = {}

    categories: list[dict[str, Any]] = []
    for category_key in M7A_CATEGORY_ORDER:
        raw_items = names_data.get(category_key)
        if raw_items is None:
            continue
        category_label = _stage_category_label(category_key)
        options = _m7a_options_from_raw_items(category_key, raw_items, drops_data)
        if not options:
            continue
        categories.append(
            _stage_category(
                category_key=category_key,
                category_label=category_label,
                options=options,
                cost=M7A_COSTS.get(category_key),
                max_count=M7A_ATTEMPTS_PER_RUN_MAX.get(category_key),
            )
        )

    if not categories:
        raise ValueError("M7A 动态副本配置为空")

    return {
        "engine": HSR_STAGE_ENGINE_M7A,
        "source": str(assets_dir),
        "categories": categories,
    }


def _m7a_options_from_raw_items(
    category_key: str,
    raw_items: Any,
    drops_data: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[tuple[str, Any]] = []
    if isinstance(raw_items, dict):
        items = [(str(name), detail) for name, detail in raw_items.items()]
    elif isinstance(raw_items, list):
        items = [(str(name), "") for name in raw_items]

    seen: set[str] = set()
    options: list[dict[str, Any]] = []
    category_label = _stage_category_label(category_key)
    for name, raw_detail in items:
        if not name or name == "无" or name in seen:
            continue
        seen.add(name)
        detail = _m7a_option_detail(category_key, name, raw_detail, drops_data)
        options.append(
            _stage_option(
                label=name,
                value=f"M7A::{category_key}::{name}",
                category_key=category_key,
                category_label=category_label,
                detail=detail,
                m7a={"instanceType": category_key, "instanceName": name},
                cost=M7A_COSTS.get(category_key),
                max_count=M7A_ATTEMPTS_PER_RUN_MAX.get(category_key),
            )
        )
    return options


def _m7a_option_detail(
    category_key: str,
    name: str,
    raw_detail: Any,
    drops_data: dict[str, Any],
) -> str:
    drops = drops_data.get(category_key, {})
    if isinstance(drops, dict):
        value = drops.get(name)
        if isinstance(value, list):
            return " / ".join(str(item) for item in value if str(item).strip())
        if value:
            return str(value)
    if isinstance(raw_detail, list):
        return " / ".join(str(item) for item in raw_detail if str(item).strip())
    if raw_detail:
        return str(raw_detail)
    return ""


def _build_sra_options_from_toml(toml_path: Path) -> dict[str, Any]:
    with toml_path.open("rb") as f:
        data = tomllib.load(f)

    subtasks = data.get("subtasks")
    if not isinstance(subtasks, dict):
        raise ValueError("trailblaze_power.toml 缺少 [subtasks]")

    categories: list[dict[str, Any]] = []
    for task_id in SRA_TP_TASK_ORDER:
        raw = subtasks.get(task_id)
        if not isinstance(raw, dict):
            continue
        category = _sra_category_from_subtask(task_id, raw)
        if category["options"]:
            categories.append(category)

    if not categories:
        raise ValueError("SRA 动态体力副本配置为空")

    return {
        "engine": HSR_STAGE_ENGINE_SRA,
        "source": str(toml_path),
        "categories": categories,
    }


def _sra_category_from_subtask(task_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    category_label = _stage_category_label(task_id, raw.get("name"))
    cost = _safe_int(raw.get("cost"), SRA_TP_COSTS.get(task_id))
    max_count = _safe_int(raw.get("max_count"), None)

    levels = raw.get("levels")
    results = raw.get("results")
    if isinstance(levels, list) and levels:
        source_items = levels
        detail_items = results if isinstance(results, list) else []
    elif isinstance(results, list) and results:
        source_items = results
        detail_items = []
    else:
        source_items = []
        detail_items = []

    options: list[dict[str, Any]] = []
    for index, item in enumerate(source_items, start=1):
        label = str(item).strip()
        if not label:
            continue
        detail = ""
        if len(detail_items) == len(source_items):
            detail = str(detail_items[index - 1]).strip()
        options.append(
            _stage_option(
                label=label,
                value=f"SRA::{task_id}::{index}",
                category_key=task_id,
                category_label=category_label,
                detail=detail,
                sra={"id": task_id, "level": index},
                cost=cost,
                max_count=max_count,
            )
        )

    return _stage_category(
        category_key=task_id,
        category_label=category_label,
        options=options,
        cost=cost,
        max_count=max_count,
    )


def _stage_category_label(category_key: str, fallback: Any = None) -> str:
    fallback_text = str(fallback or "").strip()
    return HSR_STAGE_CATEGORY_LABELS.get(category_key) or fallback_text or category_key


def _stage_category(
    *,
    category_key: str,
    category_label: str,
    options: list[dict[str, Any]],
    cost: int | None,
    max_count: int | None,
) -> dict[str, Any]:
    return {
        "categoryKey": category_key,
        "categoryLabel": category_label,
        "cost": cost,
        "maxCount": max_count,
        "options": options,
    }


def _stage_option(
    *,
    label: str,
    value: str,
    category_key: str,
    category_label: str,
    detail: str = "",
    m7a: dict[str, Any] | None = None,
    sra: dict[str, Any] | None = None,
    cost: int | None = None,
    max_count: int | None = None,
) -> dict[str, Any]:
    option: dict[str, Any] = {
        "label": label,
        "detail": detail,
        "value": value,
        "categoryKey": category_key,
        "categoryLabel": category_label,
        "cost": cost,
        "maxCount": max_count,
    }
    if m7a is not None:
        option["m7a"] = m7a
    if sra is not None:
        option["sra"] = sra
    return option


def _safe_int(value: Any, default: int | None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
