#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""将 MAS 保存的活动选关意图解析为当期 MAA 库存保持计划。"""

import json
from copy import deepcopy


def _is_orundum(stage: dict) -> bool:
    return "玉" in str(stage.get("DropName", "")) or "玉" in str(stage.get("Drop", ""))


def _activity_stage_pools(activity_stages: list[dict]) -> dict[str, list[dict]]:
    stages = [
        item
        for item in activity_stages
        if isinstance(item, dict)
        and isinstance(item.get("Value"), str)
        and item["Value"]
    ]
    return {
        "activity": stages,
        "material": [
            stage
            for stage in stages
            if str(stage.get("Drop", "")).isdigit() and not _is_orundum(stage)
        ],
        "orundum": [stage for stage in stages if _is_orundum(stage)],
    }


def migrate_activity_inventory_plans(
    plans_json: str, activity_stages: list[dict]
) -> str:
    """保存时逐项迁移；无法解析的项保留，新项优先，成功项不再携带旧标记。"""
    rows = json.loads(plans_json)
    pools = _activity_stage_pools(activity_stages)

    def identity(row: dict, position: int) -> tuple[str, int] | None:
        kind = row.get("StageType", "material")
        index = row.get("StageIndex", position + 1 if "Stage" in row else None)
        if (
            not isinstance(kind, str)
            or kind not in pools
            or not isinstance(index, int)
            or isinstance(index, bool)
            or index < 1
        ):
            return None
        return kind, index

    def canonical(row: dict, position: int) -> tuple[str, int] | None:
        key = identity(row, position)
        if key is None:
            return None
        kind, index = key
        pool = pools[kind]
        if not pool:
            return None
        if index > len(pool):
            if row.get("Skip") or not (
                row.get("LegacyIndex") or row.get("LegacyActivityFirst")
            ):
                return None
            index = 1
        stage = pool[index - 1]
        target_kind = "orundum" if _is_orundum(stage) else "material"
        if stage not in pools[target_kind]:
            return None
        return target_kind, pools[target_kind].index(stage) + 1

    explicit_keys: dict[tuple[str, int], list[int]] = {}
    for position, row in enumerate(rows):
        if (
            not isinstance(row, dict)
            or row.get("LegacyIndex")
            or row.get("LegacyActivityFirst")
        ):
            continue
        count = (
            row.get("OrundumDropCount", row.get("DropCount"))
            if row.get("StageType") == "orundum"
            else row.get("DropCount")
        )
        if not row.get("Skip") and (
            not isinstance(count, int) or isinstance(count, bool) or count <= 0
        ):
            continue
        for key in (identity(row, position), canonical(row, position)):
            if key is not None:
                explicit_keys.setdefault(key, []).append(position)

    result: list = []
    converted: dict[tuple[str, int], tuple[int, tuple[bool, bool, int]]] = {}
    inherited: dict[int, tuple[tuple[bool, bool, int], dict]] = {}
    for position, row in enumerate(rows):
        if not isinstance(row, dict) or not (
            row.get("LegacyIndex") or row.get("LegacyActivityFirst")
        ):
            result.append(row)
            continue
        old_key = identity(row, position)
        if old_key is None:
            result.append(deepcopy(row))
            continue
        key = canonical(row, position)
        replacements = explicit_keys.get(old_key) or (
            explicit_keys.get(key) if key is not None else None
        )
        if replacements:
            count = (
                row.get("OrundumDropCount", row.get("DropCount"))
                if key is not None and key[0] == "orundum"
                else row.get("DropCount")
            )
            priority = (
                bool(row.get("Skip")),
                not bool(row.get("LegacyActivityFirst")),
                count if isinstance(count, int) and not isinstance(count, bool) else 0,
            )
            for replacement in replacements:
                previous_source = inherited.get(replacement)
                if previous_source is None or priority > previous_source[0]:
                    inherited[replacement] = priority, row
            continue
        if key is None:
            result.append(deepcopy(row))
            continue
        source = {**row, "StageIndex": old_key[1]}
        source.pop("Skip", None)
        resolved, _ = resolve_activity_inventory_plans(
            json.dumps([source]), activity_stages
        )
        if not resolved:
            result.append(deepcopy(row))
            continue
        target = deepcopy(row)
        for field in (
            "Stage",
            "DropId",
            "LegacyIndex",
            "LegacyActivityFirst",
            "OrundumDropCount",
        ):
            target.pop(field, None)
        target.update(
            StageType=key[0], StageIndex=key[1], DropCount=resolved[0]["DropCount"]
        )
        # 取消优先，其次保留自定义目标；多个旧项回退到同关时取最高目标。
        priority = (
            bool(row.get("Skip")),
            not bool(row.get("LegacyActivityFirst")),
            target["DropCount"],
        )
        previous = converted.get(key)
        if previous is None:
            converted[key] = len(result), priority
            result.append(target)
        elif priority > previous[1]:
            result[previous[0]] = target
            converted[key] = previous[0], priority
    # 新项只接收缺省的逐项药石参数，显式关闭和零额度同样优先。
    for position, (_, source) in inherited.items():
        for field in ("UseMedicine", "MedicineCount", "UseStone", "StoneCount"):
            if field in source:
                rows[position].setdefault(field, deepcopy(source[field]))
    return plans_json if result == rows else json.dumps(result, ensure_ascii=False)


def resolve_activity_inventory_plans(
    plans_json: str,
    activity_stages: list[dict],
    *,
    source_plans: list[dict] | None = None,
) -> tuple[list[dict], list[tuple[str, str]]]:
    """每轮解析当前活动，不把具体关卡、材料或生成的目标写回来源配置。

    material 序号沿用旧活动库存的材料关列表，activity 序号沿用旧活动优先
    的完整列表。all 预设覆盖当期全部可刷关卡，显式目标优先于预设。
    """

    rows = json.loads(plans_json)
    pools = _activity_stage_pools(activity_stages)
    stages = pools["activity"]
    notices: list[tuple[str, str]] = []
    if not stages:
        return [], (
            [
                (
                    "core.eventDepotPreview.expiredHint",
                    "当前没有可用活动关卡，已保留保存的选关与目标",
                )
            ]
            if rows
            else []
        )

    def drop_id_of(stage: dict) -> object:
        return "30012" if _is_orundum(stage) else stage.get("Drop")

    def build(row: dict, stage: dict) -> dict | None:
        rock = _is_orundum(stage)
        drop_id = drop_id_of(stage)
        count = (
            row.get("OrundumDropCount", row.get("DropCount"))
            if rock
            else row.get("DropCount")
        )
        if (
            not isinstance(drop_id, str)
            or not drop_id.isdigit()
            or not isinstance(count, int)
            or isinstance(count, bool)
            or count <= 0
        ):
            notices.append(
                (
                    "core.eventDepotPreview.runtimeUnresolved",
                    f"活动关 {stage['Value']} 的材料或目标不可用，本轮跳过并保留配置",
                )
            )
            return None
        plan = deepcopy(row)
        for key in (
            "StageType",
            "StageIndex",
            "OrundumDropCount",
            "LegacyIndex",
            "LegacyActivityFirst",
            "Skip",
        ):
            plan.pop(key, None)
        plan.update(Stage=stage["Value"], DropId=drop_id, DropCount=count)
        return plan

    # 先解析显式行，all 预设不能覆盖任何已保存的自定义目标。
    # 未勾选的关卡只由用户在前端决定，不产生计划也不提示。
    skipped_keys: set[tuple[str, str]] = set()
    selected: dict[int, dict] = {}
    for position, row in enumerate(rows):
        if not isinstance(row, dict) or row.get("StageType") == "all":
            continue
        kind = row.get("StageType", "material")
        pool = pools.get(kind, [])
        index = row.get("StageIndex", position + 1 if "Stage" in row else None)
        if row.get("Skip"):
            if (
                isinstance(index, int)
                and not isinstance(index, bool)
                and 0 < index <= len(pool)
            ):
                skipped = pool[index - 1]
                skipped_keys.add((skipped["Value"], drop_id_of(skipped)))
            continue
        if (
            not isinstance(index, int)
            or isinstance(index, bool)
            or index < 1
            or not pool
        ):
            notices.append(
                (
                    "core.eventDepotPreview.runtimeUnresolved",
                    f"第 {position + 1} 个活动选择暂时不可用，已保留原选择",
                )
            )
            continue
        if index > len(pool):
            if row.get("LegacyIndex") or row.get("LegacyActivityFirst"):
                notices.append(
                    (
                        "core.eventDepotPreview.legacyFallback",
                        f"第 {position + 1} 个旧活动序号暂时越界，本轮沿用旧版第一关回退",
                    )
                )
                index = 1
            else:
                notices.append(
                    (
                        "core.eventDepotPreview.runtimeUnresolved",
                        f"第 {position + 1} 个活动序号暂时越界，已保留原选择",
                    )
                )
                continue
        plan = build(row, pool[index - 1])
        if plan is not None:
            source = next(
                (
                    item
                    for item in source_plans or []
                    if isinstance(item, dict)
                    and item.get("Stage") == plan["Stage"]
                    and item.get("DropId") == plan["DropId"]
                ),
                {},
            )
            for key in ("UseMedicine", "MedicineCount", "UseStone", "StoneCount"):
                if key in source:
                    plan.setdefault(key, source[key])
            selected[position] = plan
    explicit_keys = {(plan["Stage"], plan["DropId"]) for plan in selected.values()}
    custom_plans = {
        (plan["Stage"], plan["DropId"]): plan
        for position, plan in selected.items()
        if not rows[position].get("LegacyActivityFirst")
    }
    edited_keys = {
        (plan["Stage"], plan["DropId"])
        for position, plan in selected.items()
        if not rows[position].get("LegacyActivityFirst")
        and not rows[position].get("LegacyIndex")
    }
    plans = []
    for position, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        if row.get("StageType") == "all":
            current = [build(row, stage) for stage in stages]
            current = [
                plan
                for plan in current
                if plan is not None
                and (plan["Stage"], plan["DropId"]) not in explicit_keys
                and (plan["Stage"], plan["DropId"]) not in skipped_keys
            ]
        else:
            current = [selected[position]] if position in selected else []
        for plan in current:
            key = (plan["Stage"], plan["DropId"])
            if row.get("LegacyActivityFirst") and key in custom_plans:
                # 默认 999/9999 不能抬高旧自定义目标。
                continue
            if (row.get("LegacyActivityFirst") or row.get("LegacyIndex")) and (
                key in edited_keys or key in skipped_keys
            ):
                # 新选择优先于旧项，包括旧材料序号越界后的第一关回退。
                continue
            plans.append(plan)
    return plans, notices
