"""运行设置的原值解析：配置里读出的原值（JSON 字符串、分钟数、开关）换成运行要的普通数据。

只吃原值、不读配置对象：调用方（各专项的账号流程）从脚本 / 账号配置里取出原值交进来，这里
换算成 ``plan_run`` 的入参（单任务时限秒数、原地打转检测开关）、建计划用的托管级键位，以及
周期任务的三张名单。坏 JSON、不是对象 / 列表、写坏的分钟数都按「没有 / 不限」处理，不报错。
"""

from __future__ import annotations

import json
from contextlib import suppress
from typing import Any

from app.task.MaaFW.tools.core.runner.plan_transforms import MaaFWPeriodLimits


def load_json_dict(value: Any) -> dict[str, Any]:
    """配置里的 JSON 对象原值（dict 或 JSON 字符串）→ dict；不成形就是空 dict。"""

    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        with suppress(json.JSONDecodeError):
            data = json.loads(value)
            if isinstance(data, dict):
                return data
    return {}


def load_json_list(value: Any) -> list[str]:
    """配置里的 JSON 列表原值（list 或 JSON 字符串）→ 非空白的字符串列表；不成形就是空列表。"""

    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        with suppress(json.JSONDecodeError):
            data = json.loads(value)
            if isinstance(data, list):
                return [str(item) for item in data if str(item).strip()]
    return []


def load_script_hotkeys(value: Any) -> dict[str, dict[str, str]]:
    """``Game.Hotkeys`` → ``{option 名: {字段名: 组合键}}``；不成形的部分丢掉。"""

    result: dict[str, dict[str, str]] = {}
    for option_name, fields in load_json_dict(value).items():
        if not isinstance(option_name, str) or not isinstance(fields, dict):
            continue
        cleaned = {
            field_name: field_value
            for field_name, field_value in fields.items()
            if isinstance(field_name, str) and isinstance(field_value, str)
        }
        if cleaned:
            result[option_name] = cleaned
    return result


def minutes_to_seconds(minutes: Any) -> int:
    """配置里的分钟数换算成秒。0 / 负数 / 写坏的值都当「不限」（返回 0）。"""

    try:
        value = int(minutes)
    except (TypeError, ValueError):
        return 0
    return value * 60 if value > 0 else 0


def task_time_limits(
    task_time_limit_raw: Any, overrides_raw: Any
) -> tuple[int, dict[str, int]]:
    """``Run.TaskTimeLimit`` / ``Run.TaskTimeLimitOverrides`` 的原值换算成秒。

    宿主在拉起 worker 之前算一次，随 job 下发：worker 是独立进程，读不到 Config，
    核心包也只收秒数，不认宿主的配置键。

    Returns:
        (默认单任务时限秒数, {任务名: 时限秒数})，0 表示不限。
    """

    default_seconds = minutes_to_seconds(task_time_limit_raw)
    # 配置系统里 JSON 项存的是字符串（JSONValidator），读出来再解析一次。
    overrides = {
        str(name): minutes_to_seconds(minutes)
        for name, minutes in load_json_dict(overrides_raw).items()
    }
    return default_seconds, overrides


def loop_guard(raw: Any) -> bool:
    """``Run.LoopGuard``（原地打转检测，配置默认开）的原值；不是 ``True`` 就按关。"""

    return raw is True


def period_limits(
    daily_raw: Any, weekly_raw: Any, monthly_raw: Any
) -> MaaFWPeriodLimits:
    """``Run.DailyOnceTasks`` / ``WeeklyOnceTasks`` / ``MonthlyOnceTasks`` 的原值 → 三张名单。"""

    return MaaFWPeriodLimits.of(
        load_json_list(daily_raw),
        load_json_list(weekly_raw),
        load_json_list(monthly_raw),
    )


__all__ = [
    "load_json_dict",
    "load_json_list",
    "load_script_hotkeys",
    "loop_guard",
    "minutes_to_seconds",
    "period_limits",
    "task_time_limits",
]
