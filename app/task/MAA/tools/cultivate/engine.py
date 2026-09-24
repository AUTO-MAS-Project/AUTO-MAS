#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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

"""养成计算内核：需求 → 聚合 → 折算 → 选关 → 达成判定 → 状态流转。

全部为纯函数：输入契约类型、输出契约类型，零 IO、零日志、零 app.* 依赖
（规则 1.3-3）。任何外部数据都由调用方（AutoProxy / API）注入。
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import date, datetime
from datetime import time as dt_time
from typing import Mapping

from .types import (
    Achievement,
    CultivateDataSet,
    CultivatePlan,
    DropEntry,
    FarmEntry,
    Goal,
    GoalRef,
    OperatorTarget,
    Progression,
    ProgressionSnapshot,
    Recipe,
    Requirement,
)

# 合成路径搜索的深度上限（composite 表无环，防御性限制）
_MAX_PATH_DEPTH = 5

# 专精/模组维度只有这些源携带真实观测值。local（OperBoxData 结构性无
# 专精/模组字段）与 default（兜底全零）的空表是"未观测"而不是"没养成"：
# 按 0 起算会把已达档位的材料重刷一遍，并虚增缺口抑制库存保持。森空岛
# 拉取失败降级 local 时，专精/模组目标应暂停展开而不是从头补刷。
_MASTERY_MODULE_SOURCES = frozenset({"skland", "manual"})


def _mastery_module_observed(snapshot: ProgressionSnapshot | None) -> bool:
    """快照是否携带真实专精/模组观测（未观测时该维度不参与需求计算）。"""

    return snapshot is not None and snapshot.source in _MASTERY_MODULE_SOURCES


def _goal_current_level(progression: Progression, goal: Goal) -> int:
    """从练度取目标维度的当前等级（干员未拥有时用 default 全 0 起算）。"""

    if goal.kind == "elite":
        return progression.elite
    if goal.kind == "mastery":
        return progression.masteries.get(goal.target_id, 0)
    return progression.modules.get(goal.target_id, 0)


def build_requirements(
    targets: list[OperatorTarget] | tuple[OperatorTarget, ...],
    snapshots: Mapping[str, ProgressionSnapshot],
    demands: Mapping[str, tuple],
) -> list[Requirement]:
    """把目标展开为逐材料区间需求（current → to 的逐档求和）。

    等级路径严格顺序不可跳级：区间=逐档求和，天然包含中间档材料
    （中间档是要真实消耗的，属正确行为）。已达成（achieved）与待确认
    （pending_confirm，可能已养成但无法自证）的目标不参与计算；专精/模组
    目标在快照未携带该维度观测（森空岛降级 local/default）时同样不参与
    ——达成检测不受影响，目标保留，观测恢复后自动续刷。
    """

    requirements: dict[str, Requirement] = {}
    for target in targets:
        snapshot = snapshots.get(target.operator_id)
        progression = snapshot.data if snapshot is not None else Progression.default()
        for goal_index, goal in enumerate(target.goals):
            # 已达成不参与计算；待确认（可能已养成但无法自证）暂停刷取，
            # 避免用户确认前无限补刷——确认后移除，否认则恢复 in_progress
            if goal.state in ("achieved", "pending_confirm"):
                continue
            # 专精/模组未观测时 current 恒为 0，展开会从第一档重算需求
            if goal.kind != "elite" and not _mastery_module_observed(snapshot):
                continue
            current = _goal_current_level(progression, goal)
            for entry in demands.get(target.operator_id, ()):
                if (
                    entry.kind != goal.kind
                    or entry.target_id != goal.target_id
                    or not current < entry.level <= goal.to_level
                ):
                    continue
                for item_id, amount in entry.items.items():
                    existing = requirements.get(item_id)
                    if existing is None:
                        requirements[item_id] = Requirement(
                            item_id=item_id,
                            amount=amount,
                            sources=(GoalRef(target.operator_id, goal_index, amount),),
                        )
                    else:
                        requirements[item_id] = Requirement(
                            item_id=item_id,
                            amount=existing.amount + amount,
                            sources=existing.sources
                            + (GoalRef(target.operator_id, goal_index, amount),),
                        )
    return list(requirements.values())


def aggregate(requirements: list[Requirement]) -> list[Requirement]:
    """多目标需求按物品 ID 求和（取 sum 不取 max：养完 A 还得够 B）。"""

    merged: dict[str, Requirement] = {}
    for requirement in requirements:
        existing = merged.get(requirement.item_id)
        if existing is None:
            merged[requirement.item_id] = requirement
        else:
            merged[requirement.item_id] = Requirement(
                item_id=requirement.item_id,
                amount=existing.amount + requirement.amount,
                sources=existing.sources + requirement.sources,
            )
    return list(merged.values())


def _build_recipe_map(data: CultivateDataSet) -> dict[str, Recipe]:
    return {recipe.result_item_id: recipe for recipe in data.recipes}


def _stage_unusable(
    stage_id: str, data: CultivateDataSet, blacklist: frozenset[str]
) -> bool:
    """关卡是否结构性不可用（缺失/无关卡代码/被黑名单排除）。

    只做与时间、星期无关的结构判定；当天是否开放（星期关、活动窗）由调用
    方按 today 另行判断——MAA 对"认识但今天不开"的关不做次日顺延，整条
    跳过（v6.17.5 实测）。
    """

    meta = data.stages.get(stage_id)
    return meta is None or not meta.stage_code or meta.stage_code in blacklist


def _stage_closed_today(
    stage_id: str, data: CultivateDataSet, weekday: int | None
) -> bool:
    """关卡今天是否未开放（星期关，weekday 为 None 时不判断）。"""

    if weekday is None:
        return False
    meta = data.stages.get(stage_id)
    return (
        meta is not None
        and meta.open_weekdays is not None
        and weekday not in meta.open_weekdays
    )


def _direct_cost(
    item_id: str,
    data: CultivateDataSet,
    now_ms: int | None = None,
    weekday: int | None = None,
    blacklist: frozenset[str] = frozenset(),
) -> float | None:
    """直刷获得 1 个物品的期望理智成本 = 关卡理智 ÷ 该物品每次期望掉落。

    单件口径（副产品不抵扣），与 recommend_stages 选关判据同源——路径层
    与定关层必须同口径，否则会出现"按 A 口径判直刷、按 B 口径定关执行"
    的错配（综合效率口径与多目标联合折算留 P3 完整版）。取各候选关
    最小值；今天无开放关（now_ms/weekday 提供时）返回 None。
    """

    best: float | None = None
    for drop in data.drops:
        if drop.item_id != item_id:
            continue
        meta = data.stages.get(drop.stage_id)
        if meta is None or meta.ap_cost <= 0 or meta.stage_code in blacklist:
            continue
        if now_ms is not None and not _window_open(drop, now_ms):
            continue
        if weekday is not None and meta.open_weekdays is not None:
            if weekday not in meta.open_weekdays:
                continue
        if drop.expected_per_run <= 0:
            continue
        cost = meta.ap_cost / drop.expected_per_run
        best = cost if best is None else min(best, cost)
    return best


def _best_path(
    item_id: str,
    data: CultivateDataSet,
    recipe_map: Mapping[str, Recipe],
    memo: dict[str, tuple[float, dict[str, float]] | None],
    now_ms: int | None = None,
    weekday: int | None = None,
    blacklist: frozenset[str] = frozenset(),
    depth: int = 0,
) -> tuple[float, dict[str, float]] | None:
    """计算获得 1 个物品的最低理智成本与对应路径（{可刷材料: 数量}）。

    直刷与合成按每理智成本择优，直刷只计今天实际开放的关卡；不可获取
    返回 None。返回的路径中数量为浮点倍率，调用方在最终条目上取整。
    """

    if depth > _MAX_PATH_DEPTH:
        return None
    if item_id in memo:
        return memo[item_id]

    candidates: list[tuple[float, dict[str, float]]] = []
    # 资源关固定产出（采购凭证/龙门币等）：无掉落统计、单次产量未知，按 0
    # 中性成本视为"可获取"——用于配方路径可行性（如芯片助剂 ← 采购凭证×90）；
    # 实际刷取与理智估算仍由 acquire/build_plan 的固定产出关分支处理
    if item_id in data.fixed_source_stages:
        candidates.append((0.0, {item_id: 1.0}))
    direct_cost = _direct_cost(item_id, data, now_ms, weekday, blacklist)
    if direct_cost is not None:
        candidates.append((direct_cost, {item_id: 1.0}))

    recipe = recipe_map.get(item_id)
    if recipe is not None:
        total_cost = 0.0
        path: dict[str, float] = {}
        feasible = True
        for ingredient_id, count in recipe.ingredients.items():
            sub = _best_path(
                ingredient_id,
                data,
                recipe_map,
                memo,
                now_ms,
                weekday,
                blacklist,
                depth + 1,
            )
            if sub is None:
                feasible = False
                break
            total_cost += sub[0] * count
            for farm_item, multiplier in sub[1].items():
                path[farm_item] = path.get(farm_item, 0.0) + multiplier * count
        if feasible:
            candidates.append((total_cost, path))

    result = min(candidates, key=lambda candidate: candidate[0]) if candidates else None
    memo[item_id] = result
    return result


def synthesize(
    requirements: list[Requirement],
    data: CultivateDataSet,
    today: date | None = None,
    blacklist: frozenset[str] = frozenset(),
) -> tuple[list[Requirement], list[Requirement]]:
    """把需求折算到可刷取材料（金色 T5 等按合成路径展开到原料）。

    资源关固定产出材料（龙门币 ← CE-6、采购凭证 ← AP-5 等）只按资源关
    处理：无掉落统计、无配方，直接进入刷取需求，钉到对应资源关，固定
    产出关被黑名单排除时才归入不可获取。

    不可获取类（模组凭证等）原样返回，供 UI 单列"需另行获取"，
    绝不进刷取条目。路径选择为 P1 基础版：每理智成本择优，不计现有库存
    对路径选择的影响（完整口径 P3 对齐）。数量是路径总量：本函数只管
    "折算到哪里刷"，扣减库存得到净需求由 _farm_demand_net 负责。

    today 提供时直刷可行性按当天开放性评估——直刷关今天没开（限时关
    过期/星期关未开）的材料自动落到合成路径；连合成路径今天也走不通的，
    保留为未展开的刷取需求（recommend_stages 自然不产条目，demands 仍
    展示缺口）；结构性不可获取（无直掉关且无配方）才进不可获取清单。
    不提供 today 则不做开放性过滤（仅限测试）。
    """

    recipe_map = _build_recipe_map(data)
    structural_memo: dict[str, tuple[float, dict[str, float]] | None] = {}
    today_memo: dict[str, tuple[float, dict[str, float]] | None] = {}
    now_ms = (
        int(datetime.combine(today, dt_time.min).timestamp()) * 1000
        if today is not None
        else None
    )
    weekday = today.weekday() if today is not None else None
    farm_totals: dict[str, float] = {}
    unobtainable_totals: dict[str, int] = {}
    sources_by_item: dict[str, tuple[GoalRef, ...]] = {}

    for requirement in requirements:
        item_id = requirement.item_id
        if data.material_class.get(item_id) == "unobtainable":
            unobtainable_totals[item_id] = (
                unobtainable_totals.get(item_id, 0) + requirement.amount
            )
            sources_by_item.setdefault(item_id, requirement.sources)
            continue
        # 资源关固定产出（龙门币 ← CE-6、采购凭证 ← AP-5 等）：只按资源关
        # 处理，不参与掉落统计与合成折算。本函数只决定"折算到哪里刷"，
        # 需求原样保留；当天是否产刷取条目由 recommend_stages 按开放日判断。
        fixed_stage_id = data.fixed_source_stages.get(item_id)
        if fixed_stage_id is not None:
            if _stage_unusable(fixed_stage_id, data, blacklist):
                unobtainable_totals[item_id] = (
                    unobtainable_totals.get(item_id, 0) + requirement.amount
                )
                sources_by_item.setdefault(item_id, requirement.sources)
            else:
                farm_totals[item_id] = (
                    farm_totals.get(item_id, 0.0) + requirement.amount
                )
                sources_by_item[item_id] = (
                    sources_by_item.get(item_id, ()) + requirement.sources
                )
            continue
        # 结构可行性（不看今天）：决定该材料是"可刷/可合成"还是"不可获取"
        structural = _best_path(item_id, data, recipe_map, structural_memo)
        if structural is None:
            unobtainable_totals[item_id] = (
                unobtainable_totals.get(item_id, 0) + requirement.amount
            )
            sources_by_item.setdefault(item_id, requirement.sources)
            continue
        # 今日可行性：直刷关今天没开 → 落到合成路径；合成也走不通 →
        # 按原物品保留需求（不产条目，不误标不可获取）
        path = (
            _best_path(
                item_id, data, recipe_map, today_memo, now_ms, weekday, blacklist
            )
            if now_ms is not None
            else structural
        )
        if path is None:
            farm_totals[item_id] = farm_totals.get(item_id, 0.0) + requirement.amount
            sources_by_item[item_id] = (
                sources_by_item.get(item_id, ()) + requirement.sources
            )
            continue
        for farm_item, multiplier in path[1].items():
            farm_totals[farm_item] = (
                farm_totals.get(farm_item, 0.0) + multiplier * requirement.amount
            )
            # 折算到同一材料的多个需求项，来源档案合并（UI 展开来源明细需完整）
            sources_by_item[farm_item] = (
                sources_by_item.get(farm_item, ()) + requirement.sources
            )

    farm = sorted(
        (
            Requirement(
                item_id=item_id,
                amount=math.ceil(total),
                sources=sources_by_item.get(item_id, ()),
            )
            for item_id, total in farm_totals.items()
        ),
        key=lambda requirement: requirement.item_id,
    )
    unobtainable = sorted(
        (
            Requirement(item_id=item_id, amount=amount)
            for item_id, amount in unobtainable_totals.items()
        ),
        key=lambda requirement: requirement.item_id,
    )
    return farm, unobtainable


def _window_open(drop: DropEntry, now_ms: int) -> bool:
    if drop.start_ms and drop.start_ms > now_ms:
        return False
    return drop.end_ms is None or drop.end_ms == 0 or now_ms <= drop.end_ms


def recommend_stages(
    requirements: list[Requirement],
    data: CultivateDataSet,
    today: date,
    blacklist: frozenset[str] = frozenset(),
) -> list[FarmEntry]:
    """为每个可直刷材料选最优关（单件期望理智最低者）。

    统计口径与库存保持选择器一致：单件期望理智 = 理智 ÷ 每次期望掉落，
    只衡量目标材料本身，不计关卡副产物。

    过滤：活动关时间窗、资源本/芯片本星期开放规则（含固定产出资源关）、
    用户黑名单。无可用候选的材料不产条目（仍保留在 demands 供 UI 展示缺口）；
    星期关今天不开同样不产条目——缺口判定以本函数结果为准，敞开的话会让
    刷不到的材料持续抑制库存保持。
    """

    now_ms = int(datetime.combine(today, dt_time.min).timestamp()) * 1000
    weekday = today.weekday()
    entries: list[FarmEntry] = []
    for requirement in requirements:
        best_stage: str | None = None
        best_sanity_per_item: float | None = None
        best_per_run = 0.0
        best_cost = 0
        seen: set[str] = set()
        for drop in data.drops:
            if drop.item_id != requirement.item_id or drop.stage_id in seen:
                continue
            seen.add(drop.stage_id)
            meta = data.stages.get(drop.stage_id)
            if meta is None or not meta.stage_code or meta.stage_code in blacklist:
                continue
            if meta.ap_cost <= 0 or not _window_open(drop, now_ms):
                continue
            if drop.expected_per_run <= 0:
                continue
            if meta.open_weekdays is not None and weekday not in meta.open_weekdays:
                continue
            # 判据是单件期望理智而非每次期望：后者会把"期望高但理智也高"
            # 的关排前面（如固源岩 S2-12 每次 2.29/15 理智 vs 1-7 每次
            # 1.245/6 理智），总理智消耗更高
            sanity_per_item = meta.ap_cost / drop.expected_per_run
            if best_sanity_per_item is None or sanity_per_item < best_sanity_per_item:
                best_sanity_per_item = sanity_per_item
                best_per_run = drop.expected_per_run
                best_cost = meta.ap_cost
                best_stage = meta.stage_code

        # 资源关固定产出（龙门币 ← CE-6、采购凭证 ← AP-5 等）：无掉落统计，
        # 直接给出对应关。期望次数/理智不可算（产出恒定但单次产量未知），
        # 保持 0.0 中性值，由 MAA 按保有量目标执行时现算。
        #
        # 星期关今天不开放时不产条目：MAA 对"认识但今天不开"的关整条跳过
        # （不做次日顺延），产条目只会让缺口判定成立、白白抑制库存保持，
        # 开放日下一轮自然回来（编辑器候选仍给出该关，供用户提前保存计划）。
        if best_stage is None:
            fixed_stage_id = data.fixed_source_stages.get(requirement.item_id)
            if fixed_stage_id is None or _stage_unusable(
                fixed_stage_id, data, blacklist
            ):
                continue
            if _stage_closed_today(fixed_stage_id, data, weekday):
                continue
            entries.append(
                FarmEntry(
                    item_id=requirement.item_id,
                    amount=requirement.amount,
                    stage_code=data.stages[fixed_stage_id].stage_code,
                    sources=requirement.sources,
                )
            )
            continue

        expected_runs = requirement.amount / best_per_run
        entries.append(
            FarmEntry(
                item_id=requirement.item_id,
                amount=requirement.amount,
                stage_code=best_stage,
                expected_runs=round(expected_runs, 1),
                expected_sanity=round(expected_runs * best_cost, 1),
                sources=requirement.sources,
            )
        )
    return entries


def build_plan(
    *,
    targets: list[OperatorTarget] | tuple[OperatorTarget, ...],
    snapshots: Mapping[str, ProgressionSnapshot],
    data: CultivateDataSet,
    today: date,
    blacklist: frozenset[str] = frozenset(),
    inventory: Mapping[str, int] | None = None,
) -> CultivatePlan:
    """完整管线：目标 + 观测 + 库存 → 中性养成计划。

    条目数量是按库存抵扣后的净缺口（还需刷多少），与 has_material_gap
    同一份结果；MAA 的保有量目标由构建器加上档案现存（FarmEntry.held），
    落地到 MAA 仍是净缺口。不传库存时退化为路径总量（仅测试用）。
    demands 保留目标全量材料需求（含暂无可刷关的材料）供 UI 展示。
    """

    requirements = aggregate(build_requirements(targets, snapshots, data.demands))
    gross, unobtainable = synthesize(requirements, data, today, blacklist)
    held = dict(inventory or {})
    net, _ = _farm_demand_net(requirements, held, data, today, blacklist)
    entries = tuple(
        replace(entry, held=held.get(entry.item_id, 0))
        for entry in recommend_stages(net, data, today, blacklist)
    )

    # 排序不变量：精英化条目最前（专精/模组的前置）→ 按用户添加目标顺序
    # → 折算原料条目紧随其目标材料（按最早来源目标排序即自然满足）
    sort_keys: dict[tuple[str, int], tuple[int, int, int]] = {
        (target.operator_id, goal_index): (
            0 if goal.kind == "elite" else 1,
            target_index,
            goal_index,
        )
        for target_index, target in enumerate(targets)
        for goal_index, goal in enumerate(target.goals)
    }

    def sort_key(entry: FarmEntry) -> tuple[int, int, int, str]:
        first_goal_order = min(
            (
                sort_keys.get((ref.operator_id, ref.goal_index), (2, 10**9, 10**9))
                for ref in entry.sources
            ),
            default=(2, 10**9, 10**9),
        )
        return (*first_goal_order, entry.item_id)

    entries = sorted(entries, key=sort_key)

    # demands 是目标全量材料需求（路径总量，含暂无可刷关的材料），供 UI
    # 展示"这个目标要什么"；entries 是净缺口（还需刷多少），只含有可用推荐关的材料
    demands = tuple(gross) + tuple(unobtainable)
    return CultivatePlan(
        entries=tuple(entries),
        demands=demands,
        unobtainable=tuple(unobtainable),
    )


def _farm_demand_net(
    requirements: list[Requirement],
    inventory: Mapping[str, int],
    data: CultivateDataSet,
    today: date | None = None,
    blacklist: frozenset[str] = frozenset(),
) -> tuple[list[Requirement], list[Requirement]]:
    """按库存抵扣后的净需求，折算到可刷取材料（与 synthesize 同分支同选路）。

    每层先扣库存：本体 → 配方原料逐级往下（等价于立即合成消耗），只有真正
    要刷的叶子材料留下数量，因此返回值就是"还需要刷多少"。路径选择仍按每
    理智成本择优、只看今天开放的直刷关，与 synthesize 完全同源；唯一区别
    是这里接收库存做抵扣（synthesize 产出路径总量）。

    贪心按需求顺序消耗、不求解最优分配：缺口判定与计划数量都建立在这一份
    结果上，两者不会互相打架。
    """

    recipe_map = _build_recipe_map(data)
    structural_memo: dict[str, tuple[float, dict[str, float]] | None] = {}
    today_memo: dict[str, tuple[float, dict[str, float]] | None] = {}
    now_ms = (
        int(datetime.combine(today, dt_time.min).timestamp()) * 1000
        if today is not None
        else None
    )
    weekday = today.weekday() if today is not None else None
    stock = dict(inventory)
    farm_totals: dict[str, float] = {}
    unobtainable_totals: dict[str, float] = {}
    sources_by_item: dict[str, tuple[GoalRef, ...]] = {}

    def record(
        totals: dict[str, float],
        item_id: str,
        amount: float,
        sources: tuple[GoalRef, ...],
    ) -> None:
        totals[item_id] = totals.get(item_id, 0.0) + amount
        sources_by_item[item_id] = sources_by_item.get(item_id, ()) + sources

    def acquire(
        item_id: str, amount: float, sources: tuple[GoalRef, ...], depth: int
    ) -> None:
        """获得 amount 个 item：先扣库存，余量按最优路径生产或留作刷取需求。"""

        if amount <= 0:
            return
        use = min(amount, stock.get(item_id, 0))
        if use:
            stock[item_id] -= use
        amount -= use
        if amount <= 0:
            return
        if data.material_class.get(item_id) == "unobtainable":
            record(unobtainable_totals, item_id, amount, sources)
            return
        fixed_stage_id = data.fixed_source_stages.get(item_id)
        if fixed_stage_id is not None:
            if _stage_unusable(fixed_stage_id, data, blacklist):
                record(unobtainable_totals, item_id, amount, sources)
            else:
                record(farm_totals, item_id, amount, sources)
            return
        structural = _best_path(item_id, data, recipe_map, structural_memo)
        if structural is None:
            record(unobtainable_totals, item_id, amount, sources)
            return
        if depth > _MAX_PATH_DEPTH:
            record(farm_totals, item_id, amount, sources)
            return
        path = (
            _best_path(
                item_id, data, recipe_map, today_memo, now_ms, weekday, blacklist
            )
            if now_ms is not None
            else structural
        )
        if path is None:
            # 今天不可直刷且无可行的合成链：留作刷取需求（选关时自然过滤）
            record(farm_totals, item_id, amount, sources)
            return
        if list(path[1]) == [item_id] and path[1][item_id] == 1.0:
            # 直刷本体：路径即它自己，不再往下展开
            record(farm_totals, item_id, amount, sources)
            return
        recipe = recipe_map.get(item_id)
        if recipe is None:
            record(farm_totals, item_id, amount, sources)
            return
        for ingredient_id, count in recipe.ingredients.items():
            acquire(ingredient_id, amount * count, sources, depth + 1)

    for requirement in requirements:
        acquire(requirement.item_id, float(requirement.amount), requirement.sources, 0)

    def to_requirements(totals: Mapping[str, float]) -> list[Requirement]:
        return [
            Requirement(
                item_id=item_id,
                amount=math.ceil(total),
                sources=sources_by_item.get(item_id, ()),
            )
            for item_id, total in sorted(totals.items())
        ]

    return to_requirements(farm_totals), to_requirements(unobtainable_totals)


def has_material_gap(
    targets: list[OperatorTarget] | tuple[OperatorTarget, ...],
    snapshots: Mapping[str, ProgressionSnapshot],
    inventory: Mapping[str, int],
    data: CultivateDataSet,
    today: date,
    blacklist: frozenset[str] = frozenset(),
) -> bool:
    """注入时接管判定第三步：存在今日可刷、且库存（含沿配方立即合成）
    满足不了的材料缺口。

    净需求由 _farm_demand_net 给出（本体直用 → 原料逐级合成），再走选关
    过滤（时间窗/星期/黑名单，与 build_plan 同口径、同一份结果）。因此
    "当前无开放关"的材料不计入缺口——它们即使缺也刷不了，不应抑制库存
    保持；不可获取类（模组凭证等）靠用户游戏内获取，同样不计入。
    """

    requirements = aggregate(build_requirements(targets, snapshots, data.demands))
    farm, _ = _farm_demand_net(requirements, inventory, data, today, blacklist)
    return bool(recommend_stages(farm, data, today, blacklist))


def judge_achievements(
    targets: list[OperatorTarget] | tuple[OperatorTarget, ...],
    snapshots: Mapping[str, ProgressionSnapshot],
) -> list[Achievement]:
    """按练度观测逐目标判定达成；来源不可自证时 confident=False。

    快照缺失（干员不在练度数据中）= 未达成，计划继续挂起等待。
    """

    achievements: list[Achievement] = []
    for target in targets:
        snapshot = snapshots.get(target.operator_id)
        confident = snapshot is not None and snapshot.source in ("local", "skland")
        progression = snapshot.data if snapshot is not None else Progression.default()
        for goal_index, goal in enumerate(target.goals):
            achieved = _goal_current_level(progression, goal) >= goal.to_level
            achievements.append(
                Achievement(
                    operator_id=target.operator_id,
                    goal_index=goal_index,
                    achieved=achieved,
                    confident=confident,
                )
            )
    return achievements


def apply_achievements(
    targets: list[OperatorTarget] | tuple[OperatorTarget, ...],
    achievements: list[Achievement],
    snapshots: Mapping[str, ProgressionSnapshot] | None = None,
    inventory: Mapping[str, int] | None = None,
    data: CultivateDataSet | None = None,
    today: date | None = None,
) -> list[OperatorTarget]:
    """按判定结果流转目标状态：达成移除 / 不可自证转待确认。

    snapshots + inventory + data（+today）同时提供时，剩余目标按缺口
    刷新 not_started / in_progress；共享材料的重聚合在下一次 build_plan
    由剩余目标自然重建，无需在此单独处理。
    """

    def refresh_state(goal: Goal, goal_has_gap: bool) -> Goal:
        if goal.state in ("not_started", "in_progress"):
            return Goal(
                goal.kind,
                goal.target_id,
                goal.to_level,
                "in_progress" if goal_has_gap else "not_started",
            )
        return goal

    gap_index: set[tuple[str, int]] = set()
    should_refresh = (
        snapshots is not None
        and inventory is not None
        and data is not None
        and today is not None
    )
    if should_refresh:
        requirements = aggregate(build_requirements(targets, snapshots, data.demands))
        # 库存递归抵扣后折算：已有高阶材料库存能抵掉目标，材料备齐的
        # 目标回到 not_started 而不是被反复刷取（与 has_material_gap 同源）
        farm, _ = _farm_demand_net(requirements, inventory, data, today)
        for requirement in farm:
            for ref in requirement.sources:
                gap_index.add((ref.operator_id, ref.goal_index))

    removed_achievements = {
        (achievement.operator_id, achievement.goal_index)
        for achievement in achievements
        if achievement.achieved
    }
    new_targets: list[OperatorTarget] = []
    for target in targets:
        new_goals: list[Goal] = []
        for goal_index, goal in enumerate(target.goals):
            if (target.operator_id, goal_index) in removed_achievements:
                achievement = next(
                    achievement
                    for achievement in achievements
                    if achievement.operator_id == target.operator_id
                    and achievement.goal_index == goal_index
                )
                if achievement.confident:
                    continue  # 达成且可自证：移除
                new_goals.append(
                    Goal(goal.kind, goal.target_id, goal.to_level, "pending_confirm")
                )
                continue
            if should_refresh:
                new_goals.append(
                    refresh_state(goal, (target.operator_id, goal_index) in gap_index)
                )
            else:
                new_goals.append(goal)
        if new_goals:
            new_targets.append(OperatorTarget(target.operator_id, tuple(new_goals)))
    return new_targets


_GOAL_LABELS: Mapping[str, str] = {
    "elite": "精",
    "mastery": "专精",
    "module": "模组",
}


def summarize_achievements(
    targets: list[OperatorTarget] | tuple[OperatorTarget, ...],
    achievements: list[Achievement],
    names: Mapping[str, str] | None = None,
) -> list[str]:
    """把"达成且可自证"（apply_achievements 将移除）的目标拼成用户文案。

    pending_confirm（来源不可自证）不在此列：目标仍保留，仅状态流转。
    名字映射缺失时回退 char_id；本函数只产出文本，不做任何流转。
    """

    goal_by_key = {
        (target.operator_id, goal_index): goal
        for target in targets
        for goal_index, goal in enumerate(target.goals)
    }
    lines: list[str] = []
    for achievement in achievements:
        if not (achievement.achieved and achievement.confident):
            continue
        goal = goal_by_key.get((achievement.operator_id, achievement.goal_index))
        if goal is None:
            continue
        name = (names or {}).get(achievement.operator_id, achievement.operator_id)
        lines.append(f"{name} 已达到{_GOAL_LABELS[goal.kind]}{goal.to_level}")
    return lines
