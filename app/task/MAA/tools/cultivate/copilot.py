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

"""按公开作业要求比较整表练度，并生成可合并的养成建议。"""

from __future__ import annotations

import heapq
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .types import Progression

_ROLES = {
    "guard": "WARRIOR",
    "defender": "TANK",
    "vanguard": "PIONEER",
    "supporter": "SUPPORT",
    "specialist": "SPECIAL",
}
_MODULES = {1: "X", 2: "Y", 3: "A", 4: "D"}


@dataclass(frozen=True)
class Requirement:
    operator_id: str
    elite: int = 0
    level: int = 0
    skill: int = 0
    mastery_id: str = ""
    mastery: int = 0
    module_id: str = ""
    module: int = 0


def _integer(value: object, default: int = 0) -> int:
    return value if type(value) is int else default


def _requirement(
    slot: dict[str, Any],
    catalog: Mapping[str, list[dict[str, Any]]],
    *,
    modules: bool,
    protocol_version: int | None,
    module_orders: Mapping[str, list[str]],
) -> Requirement | None:
    name = slot.get("name")
    role = str(slot.get("role") or "").lower()
    profession = _ROLES.get(role, role.upper())
    matches = [
        op
        for op in catalog.get(str(name), [])
        if not role or op["profession"] == profession
    ]
    if len(matches) != 1:
        return None
    op = matches[0]
    raw = slot.get("requirements")
    if not isinstance(raw, dict):
        return None
    if any(
        key in raw and type(raw[key]) is not int
        for key in (
            "elite",
            "level",
            "skill_level",
            "module",
            "module_level",
            "potentiality",
        )
    ):
        return None
    # 当前练度契约不含潜能观测；明确要求高潜时不能伪装成已满足。
    if "potentiality" in raw and raw["potentiality"] != 1:
        return None
    # 未填写要求和字段格式异常不能视为零要求，更不能自动推荐满练。
    if not any(
        _integer(raw.get(key), -1) >= 0 for key in ("elite", "level", "skill_level")
    ):
        return None
    elite = max(0, _integer(raw.get("elite")))
    level = max(0, _integer(raw.get("level")))
    # 公开协议省略 skill 时默认一技能，不得连带忽略技能等级与专精要求。
    skill_index = slot.get("skill", 1)
    skill = max(0, _integer(raw.get("skill_level")))
    if (
        type(skill_index) is not int
        or not 1 <= skill_index <= 3
        or elite > 2
        or level > 90
        or skill > 10
    ):
        return None
    elite = max(
        elite, max(0, skill_index - 1), 2 if skill > 7 else 1 if skill > 4 else 0
    )
    caps = {
        1: (30,),
        2: (30,),
        3: (40, 55),
        4: (45, 60, 70),
        5: (50, 70, 80),
        6: (50, 80, 90),
    }.get(op["rarity"])
    if caps is None:
        return None
    if _integer(raw.get("elite"), -1) < 0:
        # 未指定精英化时，等级超过前一阶段上限会隐含更高阶段。
        elite = max(
            elite, next((i for i, cap in enumerate(caps) if level <= cap), len(caps))
        )
    if elite >= len(caps) or level > caps[elite]:
        return None
    mastery_id = ""
    if skill > 7:
        entry = next(
            (s for s in op["skills"] if s.get("skillIndex") == skill_index), None
        )
        if entry is None or skill - 7 > entry["maxLevel"]:
            return None
        mastery_id = entry["value"]
    module_id, module_level = "", 0
    module_type = _integer(raw.get("module"), -1)
    if modules and module_type > 0:
        if protocol_version == 2:
            order = module_orders.get(op["value"], [])
            branch = order[module_type] if module_type < len(order) else None
        else:
            branch = _MODULES.get(module_type)
        module = next(
            (
                m
                for m in op["modules"]
                if branch and re.search(rf"[（(]{branch}[）)]", m["label"])
            ),
            None,
        )
        if module is None:
            return None
        module_id = module["value"]
        module_level = max(1, _integer(raw.get("module_level"), 1))
        if module_level > module["maxLevel"]:
            return None
        elite = 2
    if elite > (1 if op["rarity"] == 3 else 0 if op["rarity"] < 3 else 2):
        return None
    return Requirement(
        op["value"],
        elite,
        level,
        min(skill, 7),
        mastery_id,
        max(0, skill - 7),
        module_id,
        module_level,
    )


def _raised(current: Progression, requirements: Sequence[Requirement]) -> Progression:
    elite, level = current.elite, current.level
    skill = current.skill_level or 1
    masteries, modules = dict(current.masteries), dict(current.modules)
    for req in requirements:
        if (req.elite, req.level) > (elite, level):
            elite, level = req.elite, max(1, req.level)
        skill = max(skill, req.skill)
        if req.mastery_id:
            masteries[req.mastery_id] = max(
                masteries.get(req.mastery_id, 0), req.mastery
            )
        if req.module_id:
            modules[req.module_id] = max(modules.get(req.module_id, 0), req.module)
    return Progression(elite, level, masteries, modules, skill)


def _gap(req: Requirement, current: Progression) -> float:
    """只作优先级排序的缺口权重，不宣称是真实材料成本。"""
    level_gap = (
        max(0, req.level - current.level)
        if current.elite == req.elite
        else req.level
        if current.elite < req.elite
        else 0
    )
    return (
        max(0, req.elite - current.elite) * 120
        + level_gap
        + max(0, req.skill - (current.skill_level or 1)) * 15
        + max(0, req.mastery - current.masteries.get(req.mastery_id, 0)) * 80
        + max(0, req.module - current.modules.get(req.module_id, 0)) * 100
    )


def _matched_slots(
    slots: list[list[Requirement]],
    progressions: Mapping[str, Progression],
    *,
    ready_only: bool,
) -> dict[int, Requirement]:
    """最大匹配保留槽位归属，缺人提示与完整匹配共用同一分配约束。"""
    choices = [
        [
            r
            for r in slot
            if r.operator_id in progressions
            and (not ready_only or _gap(r, progressions[r.operator_id]) == 0)
        ]
        for slot in slots
    ]
    for candidates in choices:
        candidates.sort(
            key=lambda r: (_gap(r, progressions[r.operator_id]), r.operator_id)
        )
    assigned: dict[str, tuple[int, Requirement]] = {}

    def augment(index: int, seen: set[str]) -> bool:
        for requirement in choices[index]:
            operator = requirement.operator_id
            if operator in seen:
                continue
            seen.add(operator)
            previous = assigned.get(operator)
            if previous is None or augment(previous[0], seen):
                assigned[operator] = (index, requirement)
                return True
        return False

    for index in sorted(range(len(choices)), key=lambda i: len(choices[i])):
        augment(index, set())
    return {index: req for index, req in assigned.values()}


def _match(
    slots: list[list[Requirement]],
    progressions: Mapping[str, Progression],
    *,
    ready_only: bool,
) -> list[Requirement] | None:
    """增广路保证不同槽位不重复使用同一干员；按缺口优先尝试候选。"""
    matched = _matched_slots(slots, progressions, ready_only=ready_only)
    return list(matched.values()) if len(matched) == len(slots) else None


def analyze_copilots(
    assignments: Sequence[dict[str, Any]],
    catalog: Sequence[dict[str, Any]],
    progressions: Mapping[str, Progression],
    *,
    coverage: int = 90,
    require_modules: bool = True,
) -> dict[str, Any]:
    """按整份作业的联合缺口规划；缺人及要求不明确者不伪装为可培养完成。"""
    by_id = {op["value"]: op for op in catalog}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for op in catalog:
        by_name.setdefault(op["label"], []).append(op)
    requirement_cache: dict[str, Requirement | None] = {}

    def requirement(
        slot: dict[str, Any],
        protocol_version: int | None,
        module_orders: dict[str, list[str]],
    ) -> Requirement | None:
        key = json.dumps(
            [slot, protocol_version, module_orders], sort_keys=True, ensure_ascii=False
        )
        if key not in requirement_cache:
            requirement_cache[key] = _requirement(
                slot,
                by_name,
                modules=require_modules,
                protocol_version=protocol_version,
                module_orders=module_orders,
            )
        return requirement_cache[key]

    parsed: list[tuple[dict[str, Any], list[list[Requirement]]]] = []
    jobs: list[dict[str, Any]] = []
    training: list[tuple[list[list[Requirement]], list[Requirement]]] = []
    missing: Counter[str] = Counter()
    required_missing: set[str] = set()
    frequency: Counter[str] = Counter()
    ready = 0
    for assignment in assignments:
        protocol_version = assignment.get("protocolVersion")
        module_orders = assignment.get("moduleOrders", {})
        raw_slots = [[slot] for slot in assignment["opers"]] + assignment["groups"]
        slots = [
            [requirement(s, protocol_version, module_orders) for s in group]
            for group in raw_slots
        ]
        known_slots = [[r for r in group if r is not None] for group in slots]
        unsupported = protocol_version not in (None, 1, 2, 3) or not raw_slots
        uncertain = any(
            not group or len(group) != len(raw)
            for group, raw in zip(known_slots, slots)
        )
        # 任选组只需一个有效候选；已知组合可满足时，不受其它未知候选影响。
        current = (
            None if unsupported else _match(known_slots, progressions, ready_only=True)
        )
        possible = (
            None if unsupported else _match(known_slots, progressions, ready_only=False)
        )
        unknown = unsupported or (possible is None and uncertain)
        missing_operators: list[str] = []
        missing_alternatives: list[list[str]] = []
        if unknown:
            state = "unknown"
        elif current is not None:
            state = "ready"
            ready += 1
        elif possible is None:
            state = "missing"
            matched = _matched_slots(known_slots, progressions, ready_only=False)
            reserved = {
                r.operator_id
                for group in known_slots[: len(assignment["opers"])]
                for r in group
            }
            absent: set[str] = set()
            for index, group in enumerate(known_slots):
                if index in matched:
                    continue
                candidates = sorted(
                    {
                        r.operator_id
                        for r in group
                        if r.operator_id not in progressions
                        and (
                            index < len(assignment["opers"])
                            or r.operator_id not in reserved
                        )
                    }
                )
                absent.update(candidates)
                names = [by_id[operator]["label"] for operator in candidates]
                if index < len(assignment["opers"]):
                    required_missing.update(candidates)
                    missing_operators.extend(names)
                elif names:
                    missing_alternatives.append(names)
            missing.update(absent)
        else:
            state = "training"
            training.append((known_slots, possible))
        if not unknown:
            parsed.append((assignment, known_slots))
            frequency.update({r.operator_id for group in known_slots for r in group})
        jobs.append(
            {
                "id": assignment["id"],
                "title": assignment["title"],
                "stage": assignment["stage"],
                "author": assignment["author"],
                "state": state,
                "missingOperators": sorted(set(missing_operators)),
                "missingAlternatives": missing_alternatives,
                "gaps": [
                    f"{slot.get('name', '')}：潜能要求未核实"
                    for group in raw_slots
                    for slot in group
                    if isinstance(slot.get("requirements"), dict)
                    and type(slot["requirements"].get("potentiality")) is int
                    and slot["requirements"]["potentiality"] > 1
                ]
                if unknown
                else [],
            }
        )

    virtual = dict(progressions)
    planned: dict[str, list[Requirement]] = {}
    wanted = math.ceil(len(parsed) * coverage / 100)
    remaining = set(range(len(training)))
    maximum = ready + len(remaining)
    covered = ready
    revisions = [0] * len(training)
    bundles = [bundle for _, bundle in training]
    affected_by: dict[str, set[int]] = {}
    candidates: list[tuple[float, int, int]] = []

    def enqueue(index: int) -> None:
        bundle = bundles[index]
        cost = sum(_gap(r, virtual[r.operator_id]) for r in bundle)
        benefit = sum(
            frequency[r.operator_id]
            for r in bundle
            if _gap(r, virtual[r.operator_id]) > 0
        )
        revisions[index] += 1
        heapq.heappush(candidates, (-benefit / max(1, cost), index, revisions[index]))

    for index, (slots, _) in enumerate(training):
        for operator_id in {r.operator_id for slot in slots for r in slot}:
            affected_by.setdefault(operator_id, set()).add(index)
        enqueue(index)
    # 每次加入整份作业的联合培养组合，只重新匹配受影响的作业与任选组。
    # 堆里的旧版本失效后跳过，避免全站数据在每轮规划时被完整遍历。
    while covered < wanted and candidates:
        _, index, revision = heapq.heappop(candidates)
        if index not in remaining or revision != revisions[index]:
            continue
        affected: set[int] = set()
        for req in bundles[index]:
            if _gap(req, virtual[req.operator_id]) > 0:
                planned.setdefault(req.operator_id, []).append(req)
                virtual[req.operator_id] = _raised(virtual[req.operator_id], [req])
                affected.update(affected_by[req.operator_id])
        for other in sorted(affected & remaining):
            slots = training[other][0]
            if _match(slots, virtual, ready_only=True) is not None:
                remaining.remove(other)
                covered += 1
            else:
                updated = _match(slots, virtual, ready_only=False)
                if updated is not None:
                    bundles[other] = updated
                    enqueue(other)

    rows = []
    for operator, requirements in planned.items():
        op, current = by_id[operator], progressions[operator]
        target = _raised(current, requirements)
        goals = []
        if target.elite > current.elite and target.elite <= op["maxElite"]:
            goals.append({"kind": "elite", "target_id": "", "to_level": target.elite})
        if (target.skill_level or 1) > (current.skill_level or 1):
            goals.append(
                {"kind": "skill", "target_id": "", "to_level": target.skill_level}
            )
        for kind, targets, existing in (
            ("mastery", target.masteries, current.masteries),
            ("module", target.modules, current.modules),
        ):
            for target_id, level in targets.items():
                if level > existing.get(target_id, 0):
                    goals.append(
                        {"kind": kind, "target_id": target_id, "to_level": level}
                    )
        # 专精目标同时保留技能七级前置，复用现有养成计划的语义。
        if (
            any(g["kind"] == "mastery" for g in goals)
            and not any(g["kind"] == "skill" for g in goals)
            and (current.skill_level or 0) < 7
        ):
            goals.append({"kind": "skill", "target_id": "", "to_level": 7})
        rows.append(
            {
                "operatorId": operator,
                "name": op["label"],
                "owned": True,
                "demand": frequency[operator],
                "currentElite": current.elite,
                "currentLevel": current.level,
                "targetElite": target.elite,
                "targetLevel": target.level,
                "goals": goals,
                "manualLevel": (target.elite, target.level)
                > (current.elite, current.level),
            }
        )
    for operator, demand in missing.most_common():
        rows.append(
            {
                "operatorId": operator,
                "name": by_id[operator]["label"],
                "owned": False,
                "optional": operator not in required_missing,
                "demand": demand,
                "goals": [],
            }
        )

    for job, (_, slots) in zip([j for j in jobs if j["state"] != "unknown"], parsed):
        bundle = _match(slots, progressions, ready_only=False)
        if bundle:
            job["gaps"] = [
                by_id[r.operator_id]["label"]
                for r in bundle
                if _gap(r, progressions[r.operator_id]) > 0
            ]
        job["plannedReady"] = _match(slots, virtual, ready_only=True) is not None
    return {
        "total": len(assignments),
        "analyzable": len(parsed),
        "ready": ready,
        "trainable": maximum - ready,
        "projectedReady": covered,
        "missing": sum(j["state"] == "missing" for j in jobs),
        "unknown": sum(j["state"] == "unknown" for j in jobs),
        "stageCount": len({j["stage"] for j in jobs if j["stage"]}),
        "operators": rows,
        "assignments": jobs,
    }
