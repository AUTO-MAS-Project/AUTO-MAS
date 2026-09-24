#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""MSS（MaaStellaSora / 星塔旅人）特调：运行前的「活动 → 日常 → 周常」队列装饰。

运行前在用户勾选的任务实例列表上做三件事，其余与通用 MaaFW 没有任何运行期差别：

1. 活动：队列里有「活动快速战斗」（entry ``活动快速战斗_入口``）时查一次活动排期
   （``app/tools/stella_activity.py``）。有进行中的活动就把它挪到悬赏试炼前面先打；确实
   没有活动就把它摘掉；取不到数据时按队列原样跑——真在活动期却摘掉，整轮就漏打了活动。
2. 日常：用户选了 MSS 计划表（``Info.PlanMode`` 不是 ``Fixed``）时，按当天槽位改写
   「悬赏试炼快速战斗」（entry ``战斗_入口``）的关卡、是否跳过难度选择与难度、是否消耗
   所有干劲与作战次数；队列里没有这个任务就补上。``Fixed`` 时一个选项都不动。
3. 周常：「新版爬塔」（entry ``星塔_入口_agent``）挪到队尾——爬塔不消耗干劲，上游爬塔
   偶发卡住，放最后不拖累前面的任务。每周只跑一次用 MaaFW 通用的「每周仅一次」。

按 entry 找任务、按 interface 里真实的选项名与 case 名写值（取自 MaaStellaSora v1.4.4 的
``resource/tasks/{activity,fight,climb_tower}.json``）；找不到就写一行用户日志跳过那一项。
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Callable
from typing import Any

from app.task.MaaFW.tools.core.interface.models import (
    MaaFWInterface,
    resolve_task_instance_name,
)

TYPE_KEY = "MSS"
ACTIVITY_ENTRY = "活动快速战斗_入口"
TRIBULATION_ENTRY = "战斗_入口"
CLIMB_ENTRY = "星塔_入口_agent"

## 悬赏试炼的五个选项（后两对是 switch 的 No 分支带出来的子选项，值与父选项平铺在一起）
OPTION_TRIBULATION_STAGE = "悬赏试炼关卡"
OPTION_SKIP_DIFFICULTY = "悬赏试炼跳过难度选择"
OPTION_DIFFICULTY = "选择悬赏试炼难度"
INPUT_DIFFICULTY = "难度"
OPTION_CONSUME_ALL = "悬赏试炼消耗所有干劲"
OPTION_FIGHT_TIMES = "自定义快速作战次数"
INPUT_FIGHT_TIMES = "次数"
SWITCH_ON = "Yes"
SWITCH_OFF = "No"

PLAN_MODE_FIXED = "Fixed"

_GITHUB_MSS_RE = re.compile(
    r"(^|[/:])MaaStellaSora/MaaStellaSora(\.git)?/?$", re.IGNORECASE
)


def task_name_for_entry(interface_model: MaaFWInterface, entry: str) -> str | None:
    """interface 里第一个 ``entry`` 等于给定值的任务名；找不到返回 None。"""

    for task in interface_model.task:
        if str(task.entry or "") == entry:
            return task.name
    return None


def is_mss_project(interface_model: MaaFWInterface | dict[str, Any]) -> bool:
    """三条判据任一命中：``mirrorchyan_rid == SSAH``、``github`` 指向 MaaStellaSora、``name == MaaStellaSora``。"""

    if isinstance(interface_model, dict):
        rid = interface_model.get("mirrorchyan_rid")
        github = interface_model.get("github")
        name = interface_model.get("name")
    else:
        rid = getattr(interface_model, "mirrorchyan_rid", None)
        github = getattr(interface_model, "github", None)
        name = getattr(interface_model, "name", None)
    if str(rid or "").strip().casefold() == "ssah":
        return True
    if _GITHUB_MSS_RE.search(str(github or "").strip()):
        return True
    return str(name or "").strip().casefold() == "maastellasora"


def activity_running() -> bool | None:
    """当前有没有进行中的活动：有 True、确实没有 False、取不到数据 None。

    钩子在建运行计划的工作线程里被调，那里没有事件循环，自己起一个跑完就收；
    万一在事件循环线程里被调，拿不到结果，按「说不准」处理。
    """

    from app.tools.stella_activity import has_running_event_now

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(has_running_event_now())
    return None


class MSSFlavor:
    """满足 ``MaaFWFlavor`` 协议的 MSS 特调对象。"""

    type_key = TYPE_KEY

    def __init__(
        self, *, activity_probe: Callable[[], bool | None] = activity_running
    ) -> None:
        self._activity_probe = activity_probe

    def matches_project(self, interface_model: MaaFWInterface) -> bool:
        return is_mss_project(interface_model)

    def decorate_selection(
        self,
        interface_model: MaaFWInterface,
        task_ids: list[str],
        task_options: dict[str, Any],
        *,
        script_config: Any,
        user_config: Any,
        resource_name: str | None,
        send_log: Callable[[str], None] | None,
    ) -> tuple[list[str], dict[str, Any]]:
        del script_config, resource_name  # MSS 的装饰只看用户配置与活动排期

        def log(message: str) -> None:
            if send_log is not None:
                send_log(message)

        if not task_ids:
            # 一个任务都没勾：不替用户补任务，空队列交给引擎原有处理。
            return list(task_ids), dict(task_options)

        valid_names = {task.name for task in interface_model.task}

        def name_of(task_id: str) -> str:
            return resolve_task_instance_name(task_id, valid_names)

        ids = list(task_ids)
        options = dict(task_options)

        activity = task_name_for_entry(interface_model, ACTIVITY_ENTRY)
        tribulation = task_name_for_entry(interface_model, TRIBULATION_ENTRY)
        climb = task_name_for_entry(interface_model, CLIMB_ENTRY)

        ## 最终顺序是「活动 → 日常 → 周常」。先按计划表补上 / 改好悬赏试炼，活动才有锚点
        ## 可以插在它前面；爬塔最后挪到队尾。
        plan_key = _current_plan_key(user_config, log)
        if plan_key is not None:
            ids, options = _apply_plan(
                interface_model, ids, options, tribulation, plan_key, name_of, log
            )

        if activity is not None and any(name_of(i) == activity for i in ids):
            running = self._activity_probe()
            if running is False:
                remaining = [i for i in ids if name_of(i) != activity]
                if remaining:
                    ids = remaining
                    log(f"[MSS] 当前没有进行中的活动，本轮跳过「{activity}」")
                else:
                    ## 队列里只有活动任务：摘空后引擎会把这一轮判成「无法构建运行计划」的异常，
                    ## 比照活动数据取不到的处理，按队列原样执行。
                    log(
                        f"[MSS] 当前没有进行中的活动，但队列里只有「{activity}」，按队列原样执行"
                    )
            elif running is None:
                log(f"[MSS] 取不到星塔旅人活动数据，「{activity}」按队列原样执行")
            else:
                moved = _move_before(ids, activity, tribulation, name_of)
                if moved != ids:
                    ids = moved
                    log(f"[MSS] 活动进行中，「{activity}」已挪到「{tribulation}」之前")
                else:
                    log(f"[MSS] 活动进行中，「{activity}」按队列顺序执行")

        if climb is not None and any(name_of(i) == climb for i in ids):
            reordered = [i for i in ids if name_of(i) != climb] + [
                i for i in ids if name_of(i) == climb
            ]
            if reordered != ids:
                ids = reordered
                log(f"[MSS] 「{climb}」已挪到队尾")

        return ids, options


def _move_before(
    ids: list[str],
    target: str,
    anchor: str | None,
    name_of: Callable[[str], str],
) -> list[str]:
    """把 ``target`` 的所有实例挪到 ``anchor`` 第一次出现之前；锚点不在队列里就不动。"""

    if anchor is None:
        return ids
    anchor_index = next((n for n, i in enumerate(ids) if name_of(i) == anchor), None)
    if anchor_index is None:
        return ids
    moving = [i for i in ids if name_of(i) == target]
    rest = [i for i in ids if name_of(i) != target]
    position = next(n for n, i in enumerate(rest) if name_of(i) == anchor)
    return [*rest[:position], *moving, *rest[position:]]


def _current_plan_key(
    user_config: Any, log: Callable[[str], None]
) -> dict[str, Any] | None:
    """用户引用的 MSS 计划表今天那一格；``Fixed`` 或取不到时返回 None（不改悬赏试炼）。"""

    mode = str(_get(user_config, "Info", "PlanMode") or PLAN_MODE_FIXED)
    if mode == PLAN_MODE_FIXED:
        return None
    try:
        plan = type(user_config).related_config["PlanConfig"][uuid.UUID(mode)]
        key = plan.get_current_key()
    except Exception as exc:  # noqa: BLE001 - 计划表被删或类型不对：按固定处理
        log(f"[MSS] 引用的计划表不可用，本轮不改悬赏试炼：{exc}")
        return None
    if not isinstance(key, dict) or not str(key.get("TribulationStage") or ""):
        return None
    return key


def _apply_plan(
    interface_model: MaaFWInterface,
    ids: list[str],
    options: dict[str, Any],
    tribulation: str | None,
    plan_key: dict[str, Any],
    name_of: Callable[[str], str],
    log: Callable[[str], None],
) -> tuple[list[str], dict[str, Any]]:
    """按计划表当天那一格改写悬赏试炼的选项；队列里没有这个任务就补在爬塔之前。"""

    if tribulation is None:
        log(f"[MSS] interface 里没有 entry 为 {TRIBULATION_ENTRY} 的任务，计划表未生效")
        return ids, options

    option_book = interface_model.option or {}
    stage = str(plan_key.get("TribulationStage"))
    stage_option = option_book.get(OPTION_TRIBULATION_STAGE)
    stage_cases = {case.name for case in (getattr(stage_option, "cases", None) or [])}
    if stage not in stage_cases:
        log(
            f"[MSS] 悬赏试炼没有「{stage}」这个关卡（项目可能改了名），计划表本轮未生效"
        )
        return ids, options

    targets = [i for i in ids if name_of(i) == tribulation]
    if not targets:
        targets = [tribulation]
        ids = _insert_before_tail(ids, tribulation, interface_model, name_of)
        log(f"[MSS] 计划表已选，自动加入「{tribulation}」")

    values: dict[str, Any] = {
        OPTION_TRIBULATION_STAGE: stage,
        OPTION_SKIP_DIFFICULTY: SWITCH_ON
        if plan_key.get("SkipDifficulty")
        else SWITCH_OFF,
        OPTION_DIFFICULTY: {INPUT_DIFFICULTY: str(plan_key.get("Difficulty") or 1)},
        OPTION_CONSUME_ALL: SWITCH_ON
        if plan_key.get("ConsumeAllEnergy")
        else SWITCH_OFF,
        OPTION_FIGHT_TIMES: {INPUT_FIGHT_TIMES: str(plan_key.get("FightTimes") or 1)},
    }
    missing = [name for name in values if name not in option_book]
    if missing:
        log(f"[MSS] interface 里缺少选项 {' / '.join(missing)}，这几项按队列原样")
    patch = {name: value for name, value in values.items() if name in option_book}
    for task_id in targets:
        options[task_id] = {**(options.get(task_id) or {}), **patch}
    log(f"[MSS] 按计划表设置悬赏试炼：{stage}")
    return ids, options


def _insert_before_tail(
    ids: list[str],
    tribulation: str,
    interface_model: MaaFWInterface,
    name_of: Callable[[str], str],
) -> list[str]:
    """把悬赏试炼插在爬塔之前（爬塔稍后会被挪到队尾）；没有爬塔就追加到末尾。"""

    climb = task_name_for_entry(interface_model, CLIMB_ENTRY)
    index = next(
        (n for n, i in enumerate(ids) if climb is not None and name_of(i) == climb),
        len(ids),
    )
    return [*ids[:index], tribulation, *ids[index:]]


def _get(config: Any, group: str, name: str) -> Any:
    try:
        return config.get(group, name)
    except Exception:  # noqa: BLE001 - 假配置对象缺项时按空处理
        return None


FLAVOR = MSSFlavor()

__all__ = [
    "ACTIVITY_ENTRY",
    "CLIMB_ENTRY",
    "FLAVOR",
    "MSSFlavor",
    "TRIBULATION_ENTRY",
    "TYPE_KEY",
    "activity_running",
    "is_mss_project",
    "task_name_for_entry",
]
