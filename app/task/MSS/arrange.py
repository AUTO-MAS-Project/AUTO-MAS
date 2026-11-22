#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""MSS 的排队列，拆成活动探测前后两段：只吃 interface、队列与调用方取好的值，不读配置。

顺序是「日常 → 活动 → 周常」：

1. :func:`mss_arrange_head`：按计划表当天那一格改写悬赏试炼（队列里没有就补在爬塔之前），再算出要不要
   查活动排期（``probe_needed``）——活动不在队列里、没被排除、开着活动优先时要查「补不补」
   （``want_add``），活动在队列里时要查「留不留、挪不挪」（``want_judge``）。两者互斥，所以最多查一次。
   一个任务都没勾、也没选计划表时 ``finished``：什么都不做，也不查。
2. 调用方按 ``probe_needed`` 查一次活动排期（有进行中的活动 True、确实没有 False、取不到 None）。
3. :func:`mss_arrange_tail`：按查到的结果补上、挪动或摘掉活动任务，最后把爬塔挪到队尾。

两段的判断与日志都与原来一次排完时一字不差：判断条件就在原来的位置算出来，日志的先后不变。
自动补任务时跳过 ``excluded_ids``（引擎判定本轮不跑的实例：红灯、今天不在运行日的），按任务名比。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.task.MaaFW.tools.core.interface.models import (
    MaaFWInterface,
    resolve_task_instance_name,
    task_name_for_entry,
)
from app.task.MSS.rules import ACTIVITY_ENTRY, CLIMB_ENTRY, TRIBULATION_ENTRY

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


@dataclass(frozen=True)
class MSSArrangeState:
    """前半段排完的队列，以及后半段要不要活动排期。"""

    ids: list[str]
    options: dict[str, Any]
    activity: str | None
    tribulation: str | None
    climb: str | None
    finished: bool
    """一个任务都没勾、也没选计划表：原样交回，后半段什么都不做。"""
    want_add: bool
    """活动不在队列里、没被排除、开着活动优先：确认在活动期才补。"""
    want_judge: bool
    """活动在队列里：按活动排期挪到悬赏试炼前，或摘掉。"""

    @property
    def probe_needed(self) -> bool:
        """要不要查一次活动排期（``want_add`` 与 ``want_judge`` 互斥，最多查一次）。"""

        return not self.finished and (self.want_add or self.want_judge)


def _name_reader(interface_model: MaaFWInterface) -> Callable[[str], str]:
    valid_names = {task.name for task in interface_model.task}

    def name_of(task_id: str) -> str:
        return resolve_task_instance_name(task_id, valid_names)

    return name_of


def mss_arrange_head(
    interface_model: MaaFWInterface,
    task_ids: list[str],
    task_options: dict[str, Any],
    *,
    excluded_ids: frozenset[str],
    plan_key: dict[str, Any] | None,
    if_activity_first: Any,
    log: Callable[[str], None],
) -> MSSArrangeState:
    """前半段：套计划表，并记下后半段要不要活动排期。不改入参。

    ``plan_key`` 是账号引用的计划表今天那一格（``Fixed`` 或取不到时为 None）；``if_activity_first`` 是
    ``Info.IfActivityFirst`` 的原值（只有 ``False`` 算关）。
    """

    name_of = _name_reader(interface_model)
    ids = list(task_ids)
    options = dict(task_options)
    ## 自动编排不补回引擎判定本轮不跑的实例（红灯、今天不在运行日），
    ## 也不因为它们去套计划表
    skipped_ids = excluded_ids

    activity = task_name_for_entry(interface_model, ACTIVITY_ENTRY)
    tribulation = task_name_for_entry(interface_model, TRIBULATION_ENTRY)
    climb = task_name_for_entry(interface_model, CLIMB_ENTRY)

    ## 一个任务都没勾、也没选计划表：手上没有任何可执行任务，交给引擎按原有语义报错。
    ## 选了计划表就不算空队列——下面 _apply_plan 会把悬赏试炼补上，和账号页那句
    ## 「队列里没有它时会自动加入」保持一致（这条以前被空队列提前返回挡住了）。
    ## 顺序是「活动 → 日常 → 周常」：先补好悬赏试炼，活动才有锚点插在它前面；爬塔最后归位。
    if not ids and plan_key is None:
        return MSSArrangeState(
            ids=list(ids),
            options=dict(options),
            activity=activity,
            tribulation=tribulation,
            climb=climb,
            finished=True,
            want_add=False,
            want_judge=False,
        )

    if plan_key is not None and (
        tribulation not in skipped_ids
        or any(name_of(task_id) == tribulation for task_id in ids)
    ):
        ids, options = _apply_plan(
            interface_model, ids, options, tribulation, plan_key, name_of, log
        )

    ## 「活动优先」开着时，队列里没加活动任务也补一个——但只有**确认在活动期**才补（后半段判）：
    ## 取不到活动数据时乱加会让这一轮多跑一个本来不该跑的任务。
    in_queue = activity is not None and any(name_of(i) == activity for i in ids)
    want_add = (
        activity is not None
        and activity not in skipped_ids
        and not in_queue
        and if_activity_first is not False
    )
    return MSSArrangeState(
        ids=ids,
        options=options,
        activity=activity,
        tribulation=tribulation,
        climb=climb,
        finished=False,
        want_add=want_add,
        want_judge=in_queue,
    )


def mss_arrange_tail(
    state: MSSArrangeState,
    activity_running: bool | None,
    *,
    interface_model: MaaFWInterface,
    log: Callable[[str], None],
) -> tuple[list[str], dict[str, Any]]:
    """后半段：按活动排期处理活动任务，再把爬塔挪到队尾，返回新的列表与选项。

    ``activity_running`` 是 ``state.probe_needed`` 时查到的结果（有 True、确实没有 False、取不到 None）；
    没查时传 None，后半段也不会用它。
    """

    if state.finished:
        return state.ids, state.options

    name_of = _name_reader(interface_model)
    ids = state.ids
    options = state.options
    activity = state.activity
    tribulation = state.tribulation
    climb = state.climb

    ## 补的位置与已在队列里时同一口径：悬赏试炼之前（先消耗干劲），没有悬赏试炼就在爬塔前。
    added = False
    if state.want_add and activity_running is True:
        ids = _insert_before_climb(ids, activity, interface_model, name_of)
        moved = _move_before(ids, activity, tribulation, name_of)
        ids = moved
        added = True
        if tribulation is not None and any(name_of(i) == tribulation for i in ids):
            log(
                f"[MSS] 活动进行中，已自动加入「{activity}」，排在「{tribulation}」之前"
            )
        else:
            log(f"[MSS] 活动进行中，已自动加入「{activity}」")

    if not added and state.want_judge:
        running = activity_running
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
        ids = _insert_before_climb(ids, tribulation, interface_model, name_of)
        log(f"[MSS] 计划表已选，自动加入「{tribulation}」")
    else:
        ## 队列里手动加了多个同任务实例时只改第一个：剩下的留给用户自己配，
        ## 这样「一个按计划表刷、一个固定刷别的关」还能共存
        targets = targets[:1]

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


def _insert_before_climb(
    ids: list[str],
    task: str,
    interface_model: MaaFWInterface,
    name_of: Callable[[str], str],
) -> list[str]:
    """把 ``task`` 插在爬塔之前（爬塔是那个会被挪到队尾的任务）；没有爬塔就追加到末尾。"""

    climb = task_name_for_entry(interface_model, CLIMB_ENTRY)
    index = next(
        (n for n, i in enumerate(ids) if climb is not None and name_of(i) == climb),
        len(ids),
    )
    return [*ids[:index], task, *ids[index:]]


__all__ = ["MSSArrangeState", "mss_arrange_head", "mss_arrange_tail"]
