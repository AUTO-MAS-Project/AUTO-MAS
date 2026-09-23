#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""按「活动 → 日常 → 周常」改写外壳实例配置。

MFAAvalonia 的命令行只有 ``--autostart`` / ``-i`` / ``-q`` / ``-f``，没有传任务的
入口，所以「活动期打活动、否则按计划表打悬赏试炼、周常爬塔」只能改外壳的
``config/instances/<实例>.json``。**这是临时补位**：上游一旦给出动态任务入口，
本模块整体移除，那时 MAS 只保留 ``instance_config`` 里那点只读路径解析。

改动面刻死在三处，其余一律不碰（用户在外壳里配的其它任务与选项原样保留）：

- ``CurrentTasks``：任务的勾选与顺序，元素形如 ``"任务名<|||>入口"``；
- ``悬赏试炼快速战斗`` 的 ``悬赏试炼关卡``（select，值按 cases 下标写）；
- ``新版爬塔`` 的 ``新版爬塔_爬塔次数``（input，值按 ``{输入名: 值}`` 写）。

模块里全是纯函数：拿到实例配置的字典与一份 :class:`MSSRunPlan`，返回改写后的新
字典与「哪几项没做成」，不碰磁盘，便于直接用真实样本做回归。
"""

from __future__ import annotations

import calendar
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.utils.constants import MSS_TRIBULATION_STAGES

## CurrentTasks 元素的连接符号，由外壳自己定义（实测形如 "登录游戏<|||>登录_登录"）
TASK_SEPARATOR = "<|||>"

## 要接管的三个任务：名字与入口都取自外壳默认实例（interface v1.4.4）
TASK_ACTIVITY = "活动快速战斗"
ENTRY_ACTIVITY = "活动快速战斗_入口"
TASK_TRIBULATION = "悬赏试炼快速战斗"
ENTRY_TRIBULATION = "战斗_入口"
TASK_CLIMB = "新版爬塔"
ENTRY_CLIMB = "星塔_入口_agent"

## 要改的选项名，以及 input 型选项的输入项名
OPTION_TRIBULATION_STAGE = "悬赏试炼关卡"
OPTION_SKIP_DIFFICULTY = "悬赏试炼跳过难度选择"
SUB_DIFFICULTY = "选择悬赏试炼难度"
INPUT_DIFFICULTY = "难度"
OPTION_CONSUME_ALL = "悬赏试炼消耗所有干劲"
SUB_FIGHT_TIMES = "自定义快速作战次数"
INPUT_FIGHT_TIMES = "次数"
OPTION_CLIMB_TIMES = "新版爬塔_爬塔次数"
INPUT_CLIMB_TIMES = "爬塔次数"

## 外壳的 switch 型选项 cases 是 ["No", "Yes"]，值就是下标
SWITCH_OFF = 0
SWITCH_ON = 1

## 实例配置里承载任务与选项的两个键
KEY_CURRENT_TASKS = "CurrentTasks"
KEY_TASK_ITEMS = "TaskItems"


def join_task(name: str, entry: str) -> str:
    """拼出 ``CurrentTasks`` 里的元素。"""

    return f"{name}{TASK_SEPARATOR}{entry}"


def split_task(raw: str) -> tuple[str, str]:
    """拆开 ``CurrentTasks`` 里的元素；没有分隔符时入口为空串。"""

    name, _, entry = str(raw).partition(TASK_SEPARATOR)
    return name, entry


@dataclass(frozen=True)
class MSSRunPlan:
    """本轮要在外壳实例配置上做的改动。

    Attributes:
        activity: 是否处于活动期间。``None`` 表示取不到活动数据、本轮不接管活动
            任务——取数失败时若按「没活动」把勾选摘掉，真在活动期就会漏打。
        tribulation_stage: 悬赏试炼关卡；``None`` 表示不接管（用外壳里用户自己配的）。
            下面四项只在它不为 None 时一起写进去。
        skip_difficulty: 悬赏试炼是否跳过难度选择。
        difficulty: 悬赏试炼难度（``skip_difficulty`` 关掉时生效）。
        consume_all_energy: 悬赏试炼是否消耗所有干劲。
        fight_times: 自定义快速作战次数（``consume_all_energy`` 关掉时生效）。
        climb_times: 周常爬塔次数；``None`` 表示不接管爬塔（周常模式为 Close）。
    """

    activity: bool | None = None
    tribulation_stage: str | None = None
    skip_difficulty: bool = False
    difficulty: int = 1
    consume_all_energy: bool = False
    fight_times: int = 1
    climb_times: int | None = None

    @property
    def touches_tasks(self) -> bool:
        """本轮是否需要改动任务列表；三项都不接管时调用方应完全跳过写入。"""

        return (
            self.activity is not None
            or self.tribulation_stage is not None
            or self.climb_times is not None
        )


@dataclass(frozen=True)
class MSSPlanResult:
    """改写结果。

    Attributes:
        config: 改写后的实例配置（入参的深拷贝）。
        skipped: 想在实例配置上做、但因为外壳里找不到对应任务条目而放弃的项，
            交给调用方记日志——静默少做一件事比报错更难查。
    """

    config: dict[str, Any]
    skipped: tuple[str, ...] = ()


def current_week_marker(now: datetime) -> str:
    """返回 ISO 周标记（形如 ``2026-W34``）。"""

    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year:04d}-W{iso_week:02d}"


def should_run_climb(
    mode: str,
    start_weekday: str,
    completed_week: str,
    now: datetime,
) -> bool:
    """判断本轮是否该跑周常。

    口径与 MAA 的剿灭一致：一周只跑一次，且要到了允许开始的星期才跑。

    Args:
        mode: 用户配置里的周常模式，``Auto`` 才参与判定。
        start_weekday: 允许开始的星期名（``Monday`` 起）。
        completed_week: 上次跑完时记下的 ISO 周标记。
        now: 判定时刻（调用方按东四区取）。

    Returns:
        bool: 是否该在本次运行里加上周常。
    """

    if mode != "Auto":
        return False
    if completed_week == current_week_marker(now):
        return False

    start_index = getattr(calendar, str(start_weekday).upper(), calendar.MONDAY)
    return now.weekday() >= start_index


def apply_run_plan(config: Mapping[str, Any], plan: MSSRunPlan) -> MSSPlanResult:
    """按运行计划改写实例配置。

    实例配置结构不认识时（``CurrentTasks`` 或 ``TaskItems`` 不是列表）原样返回并
    在 ``skipped`` 里说明，由调用方决定是照常启动还是放弃——半懂的结构上猜着写
    比不写更危险。

    Args:
        config: 外壳实例配置的原始内容。
        plan: 本轮运行计划。

    Returns:
        MSSPlanResult: 改写后的配置，以及没做成的项。
    """

    result: dict[str, Any] = deepcopy(dict(config))
    if not plan.touches_tasks:
        return MSSPlanResult(result)

    raw_tasks = result.get(KEY_CURRENT_TASKS)
    items = result.get(KEY_TASK_ITEMS)
    if not isinstance(raw_tasks, list) or not isinstance(items, list):
        return MSSPlanResult(result, ("实例配置结构不认识，本轮不改任务",))

    tasks = [item for item in raw_tasks if isinstance(item, str)]
    skipped: list[str] = []

    ## 活动 → 日常 → 周常。先摘掉活动再按需插回，最后摆爬塔，三步之间不会互相踩
    if plan.activity is not None:
        tasks = _drop_task(tasks, TASK_ACTIVITY)
        _set_default_check(items, TASK_ACTIVITY, bool(plan.activity))
        if plan.activity:
            if _find_item(items, TASK_ACTIVITY) is None:
                skipped.append(TASK_ACTIVITY)
            else:
                tasks = _insert_before(
                    tasks, TASK_TRIBULATION, join_task(TASK_ACTIVITY, ENTRY_ACTIVITY)
                )

    if plan.tribulation_stage is not None:
        if _set_tribulation(items, plan):
            tasks = _ensure_task(tasks, TASK_TRIBULATION, ENTRY_TRIBULATION)
            _set_default_check(items, TASK_TRIBULATION, True)
        else:
            skipped.append(TASK_TRIBULATION)

    if plan.climb_times is not None:
        tasks = _drop_task(tasks, TASK_CLIMB)
        if _set_climb_times(items, plan.climb_times):
            ## 周常放最后：爬塔不消耗干劲，且上游爬塔偶发卡住，不拖累前面的任务
            tasks.append(join_task(TASK_CLIMB, ENTRY_CLIMB))
            _set_default_check(items, TASK_CLIMB, True)
        else:
            skipped.append(TASK_CLIMB)

    result[KEY_CURRENT_TASKS] = tasks
    return MSSPlanResult(result, tuple(skipped))


def _drop_task(tasks: Sequence[str], name: str) -> list[str]:
    """摘掉该任务的**所有**条目。

    外壳的 ``CurrentTasks`` 里同一个任务可以挂多个入口——样本里「活动快速战斗」就同时有
    ``活动快速战斗_入口`` 与 ``活动_入口`` 两条。只摘其中一条的话，外壳界面上那一行
    （按任务名显示）仍然是勾着的，用户看到的就还是「活动快速战斗开着」。
    """

    return [task for task in tasks if split_task(task)[0] != name]


def _ensure_task(tasks: Sequence[str], name: str, entry: str) -> list[str]:
    """确保任务在列表里；已经在（不论哪个入口）就保持原位，不在才追加到末尾。"""

    if any(split_task(task)[0] == name for task in tasks):
        return list(tasks)
    return [*tasks, join_task(name, entry)]


def _insert_before(tasks: Sequence[str], before_name: str, target: str) -> list[str]:
    """把任务插到 ``before_name`` 那条之前；找不到参照就追加到末尾。"""

    result = list(tasks)
    for index, task in enumerate(result):
        if split_task(task)[0] == before_name:
            result.insert(index, target)
            return result
    result.append(target)
    return result


def _set_default_check(items: Sequence[Any], name: str, checked: bool) -> None:
    """同步任务的「默认勾选」。

    外壳在打开、切换实例、退出这些时机，会按 ``TaskItems[].default_check`` 重建
    ``CurrentTasks``（实测：三个实例文件的 mtime 被同一时刻刷成一致，内容也回到了
    default_check 的样子）。只写 ``CurrentTasks`` 的话，那些时机一过就被冲掉，
    两处一起写才稳。

    Args:
        items: ``TaskItems`` 列表。
        name: 任务名。
        checked: 该任务的默认勾选状态。
    """

    item = _find_item(items, name)
    if item is not None:
        item["default_check"] = checked


def _find_item(items: Sequence[Any], name: str) -> dict[str, Any] | None:
    """在 ``TaskItems`` 里按名字找任务条目。"""

    for item in items:
        if isinstance(item, dict) and item.get("name") == name:
            return item
    return None


def _find_option(item: Mapping[str, Any], option_name: str) -> dict[str, Any] | None:
    """在任务条目的 option 列表里按名字找选项。"""

    options = item.get("option")
    if not isinstance(options, list):
        return None
    for option in options:
        if isinstance(option, dict) and option.get("name") == option_name:
            return option
    return None


def _set_tribulation(items: Sequence[Any], plan: MSSRunPlan) -> bool:
    """把悬赏试炼的关卡与两个开关写进任务选项。

    实测结构：``悬赏试炼关卡`` 是 select（值按 cases 下标）；``悬赏试炼跳过难度选择`` 与
    ``悬赏试炼消耗所有干劲`` 是 switch（cases ``["No","Yes"]``，值同样按下标），它们的
    子选项 ``选择悬赏试炼难度`` / ``自定义快速作战次数`` 里各放一个 input。

    Args:
        items: ``TaskItems`` 列表。
        plan: 本轮运行计划。

    Returns:
        bool: 关卡写成功为 True；找不到任务或选项时为 False（调用方据此跳过整个任务）。
    """

    if plan.tribulation_stage not in MSS_TRIBULATION_STAGES:
        return False

    item = _find_item(items, TASK_TRIBULATION)
    if item is None:
        return False
    option = _find_option(item, OPTION_TRIBULATION_STAGE)
    if option is None:
        return False

    option["index"] = MSS_TRIBULATION_STAGES.index(str(plan.tribulation_stage))
    _set_switch(item, OPTION_SKIP_DIFFICULTY, plan.skip_difficulty)
    _set_sub_input(
        item, OPTION_SKIP_DIFFICULTY, SUB_DIFFICULTY, INPUT_DIFFICULTY, plan.difficulty
    )
    _set_switch(item, OPTION_CONSUME_ALL, plan.consume_all_energy)
    _set_sub_input(
        item, OPTION_CONSUME_ALL, SUB_FIGHT_TIMES, INPUT_FIGHT_TIMES, plan.fight_times
    )
    return True


def _set_switch(item: Mapping[str, Any], option_name: str, on: bool) -> bool:
    """按 ``["No", "Yes"]`` 的下标写 switch 型选项。"""

    option = _find_option(item, option_name)
    if option is None:
        return False
    option["index"] = SWITCH_ON if on else SWITCH_OFF
    return True


def _set_sub_input(
    item: Mapping[str, Any],
    option_name: str,
    sub_name: str,
    input_name: str,
    value: int,
) -> bool:
    """写选项的子选项里的 input；外壳里还没有这个子选项时补一个出来。"""

    option = _find_option(item, option_name)
    if option is None:
        return False

    subs = option.get("sub_options")
    if not isinstance(subs, list):
        subs = []
        option["sub_options"] = subs

    for sub in subs:
        if isinstance(sub, dict) and sub.get("name") == sub_name:
            data = sub.get("data")
            sub["data"] = {
                **(data if isinstance(data, dict) else {}),
                input_name: str(value),
            }
            return True

    subs.append({"name": sub_name, "index": None, "data": {input_name: str(value)}})
    return True


def _set_climb_times(items: Sequence[Any], times: int) -> bool:
    """把爬塔次数写成指定值；input 型选项的 index 不动，其它输入项保持原样。"""

    item = _find_item(items, TASK_CLIMB)
    if item is None:
        return False
    option = _find_option(item, OPTION_CLIMB_TIMES)
    if option is None:
        return False

    data = option.get("data")
    option["data"] = {
        **(data if isinstance(data, dict) else {}),
        INPUT_CLIMB_TIMES: str(times),
    }
    return True
