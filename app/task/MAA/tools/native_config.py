#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""MAA 原生配置与基建排班解析。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.utils import get_logger
from app.utils.io import read_file

logger = get_logger("配置模型")


def infrast_plan_mode(plans: list[dict]) -> str:
    """排班表的时段形态: period=全带时段, rotate=全不带, mixed=混合, empty=无班次。

    前提: ``plans`` 元素为 dict(``infrast_format_problem`` 已先行校验)。
    """

    if not plans:
        return "empty"
    has_period = [bool(plan.get("period")) for plan in plans]
    if all(has_period):
        return "period"
    if any(has_period):
        return "mixed"
    return "rotate"


def _is_infrast_time(value: Any) -> bool:
    """是否为 MAA 时间字段可解析的值(TimeOnly.Parse 接受 HH:MM[:SS[.fff]])。

    不用 ``time.fromisoformat``: 它拒绝上游接受的 ``8:00``, 却接受上游拒绝的
    ``2000`` / ``20-00``, 两边松紧正好相反。先 strip 对齐 .NET Parse 会跳过
    首尾空白的行为, 避免把上游能解析的值误判为坏值。
    """

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
    """period 是否为 MAA 可解析的时段表: 每段恰两个时间字符串(TimeOnly[])。

    MAA 的 TimeOnlyArrayListConverter 只接受 ``[["HH:MM", "HH:MM"], ...]``,
    段长不为 2 或时间无法解析都会抛异常, 连累整份排班在 MAA 侧反序列化失败
    (自愈为 0 且班次表为空), 因此这里按上游契约严格校验。
    """

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
    """排班表状态: period/rotate/mixed(时段不一致, 不可用)/empty(缺省或不可解析)。

    与 ``infrast_format_problem`` 用同一把尺子: 时段形态不合法的表同样按
    empty 处理, 否则运行期已判不可用, 下拉提示却还在宣称按时间段换班。
    """

    if custom_infrast is None:
        return "empty"
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
    """校验自定义基建排班表的格式不变量, 返回问题描述; None 表示格式可用。

    不变量: plans 非空且元素为对象, 各班次要么全部带 period 要么全部不带,
    且 period 是 MAA 可解析的时段表(每段恰两个时间字符串)。
    混合格式在 MAA 侧会被静默按"有时段的班按时段命中, 其余永不命中"解释,
    MAS 不猜测这种意图, 统一按无效处理。
    """
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
    """解析自定义基建排班 JSON, 返回 (plans, problem); problem 非 None 时 plans 为 []。"""
    if custom_infrast is None:
        return [], "排班表不是有效的 JSON"
    try:
        data = json.loads(custom_infrast)
    except (json.JSONDecodeError, TypeError):
        return [], "排班表不是有效的 JSON"
    problem = infrast_format_problem(data)
    if problem is not None:
        return [], problem
    return data.get("plans", []), None


def read_maa_config(path: Path) -> dict | None:
    """读取 MAA gui.new.json 配置; 缺失或损坏返回 None(损坏另记警告)。"""

    try:
        data = read_file(path)
    except (OSError, json.JSONDecodeError):
        logger.opt(exception=True).warning(f"读取 MAA 配置失败: {path}")
        return None
    return data if isinstance(data, dict) and data else None


def maa_scheme_name(data: dict) -> str:
    """MAA 配置的生效方案名。

    ``data`` 为已读取的 gui.new.json 内容; ``Current`` 指向的方案存在时用它,
    否则回落到 ``Default``。
    """

    current = data.get("Current")
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
    """取 MAA 配置中指定方案的任务队列; 结构不符返回 None。"""

    configurations = data.get("Configurations")
    if not isinstance(configurations, dict):
        return None
    configuration = configurations.get(scheme)
    if not isinstance(configuration, dict):
        return None
    return configuration.get("TaskQueue")
