"""MAA gui.json 排班与方案名（从非插件版 config 模型抽出）。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from auto_mas_core.utils import get_logger, read_file

logger = get_logger("MAA 原生配置")


def infrast_plan_mode(plans: list[dict]) -> str:
    if not plans:
        return "empty"
    has_period = [bool(plan.get("period")) for plan in plans]
    if all(has_period):
        return "period"
    if any(has_period):
        return "mixed"
    return "rotate"


def _is_infrast_time(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    value = value.strip()
    for time_format in ("%H:%M", "%H:%M:%S", "%H:%M:%S.%f"):
        try:
            datetime.strptime(value, time_format)
        except ValueError:
            continue
        return True
    return False


def _is_infrast_period(period: Any) -> bool:
    if period is None:
        return True
    if not isinstance(period, list):
        return False
    return all(
        isinstance(segment, list)
        and len(segment) == 2
        and all(_is_infrast_time(value) for value in segment)
        for segment in period
    )


def infrast_plan_state(custom_infrast: str | None) -> str:
    try:
        data = json.loads(custom_infrast)
    except (json.JSONDecodeError, TypeError):
        return "empty"
    plans = data.get("plans") if isinstance(data, dict) else None
    if not isinstance(plans, list) or not all(isinstance(plan, dict) for plan in plans):
        return "empty"
    if not all(_is_infrast_period(plan.get("period")) for plan in plans):
        return "empty"
    return infrast_plan_mode(plans)


def infrast_format_problem(infrast_data: Any) -> str | None:
    if not isinstance(infrast_data, dict):
        return "排班表不是有效的 JSON 对象"
    plans = infrast_data.get("plans")
    if not isinstance(plans, list) or not plans:
        return "排班表没有任何班次"
    if not all(isinstance(plan, dict) for plan in plans):
        return "排班表的班次格式不正确"
    if not all(_is_infrast_period(plan.get("period")) for plan in plans):
        return "排班表的时间段格式不正确（每段应为起止两个 HH:MM 时间）"
    if infrast_plan_mode(plans) == "mixed":
        return "排班表时段配置不一致（部分班次有时间段、部分没有）"
    return None


def load_infrast_plans(custom_infrast: str | None) -> tuple[list[dict], str | None]:
    try:
        data = json.loads(custom_infrast)
    except (json.JSONDecodeError, TypeError):
        return [], "排班表不是有效的 JSON"
    problem = infrast_format_problem(data)
    if problem is not None:
        return [], problem
    return data.get("plans", []), None


def read_maa_config(path: Path) -> dict | None:
    try:
        data = read_file(path)
    except (OSError, json.JSONDecodeError):
        logger.opt(exception=True).warning(f"读取 MAA 配置失败: {path}")
        return None
    return data if isinstance(data, dict) and data else None


def maa_scheme_name(config_dir: Path, data: dict) -> str:
    try:
        gui = read_file(config_dir / "gui.json")
    except (OSError, json.JSONDecodeError):
        return "Default"
    current = gui.get("Current") if isinstance(gui, dict) else None
    configurations = data.get("Configurations")
    if (
        isinstance(current, str)
        and current not in ("", "Default")
        and isinstance(configurations, dict)
        and isinstance(configurations.get(current), dict)
    ):
        return current
    return "Default"


def maa_task_queue(data: dict, scheme: str) -> Any:
    configurations = data.get("Configurations")
    if not isinstance(configurations, dict):
        return None
    configuration = configurations.get(scheme)
    if not isinstance(configuration, dict):
        return None
    return configuration.get("TaskQueue")
