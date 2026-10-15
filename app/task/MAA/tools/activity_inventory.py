#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""将 MAS 保存的活动选关意图解析为当期 MAA 库存保持计划。"""

import json
from copy import deepcopy


def resolve_activity_inventory_plans(
    plans_json: str,
    activity_stages: list[dict],
    *,
    medicine_count: int = 0,
    source_plans: list[dict] | None = None,
    priority_source: dict | None = None,
) -> tuple[list[dict], list[tuple[str, str]]]:
    """每轮解析当前活动，不把具体关卡、材料或生成的目标写回来源配置。

    material 序号沿用旧活动库存的材料关列表，activity 序号沿用旧活动优先
    的完整列表。all 预设覆盖当期全部可刷关卡，显式目标优先于预设。
    返回的 _ActivityOrigin 只供组装段级设置，写入 MAA 前由调用者移除。
    """

    rows = json.loads(plans_json)
    stages = [
        item
        for item in activity_stages
        if isinstance(item, dict)
        and isinstance(item.get("Value"), str)
        and item["Value"]
    ]
    notices: list[tuple[str, str]] = []
    if not stages:
        return [], (
            [
                (
                    "eventDepotPreview.expiredHint",
                    "当前没有可用活动关卡，已保留保存的选关与目标",
                )
            ]
            if rows
            else []
        )

    def is_orundum(stage: dict) -> bool:
        return "玉" in str(stage.get("DropName", "")) or "玉" in str(
            stage.get("Drop", "")
        )

    materials = [
        stage
        for stage in stages
        if str(stage.get("Drop", "")).isdigit() and not is_orundum(stage)
    ]
    orundum = [stage for stage in stages if is_orundum(stage)]

    def drop_id_of(stage: dict) -> object:
        return "30012" if is_orundum(stage) else stage.get("Drop")

    def build(row: dict, stage: dict) -> dict | None:
        rock = is_orundum(stage)
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
                    "eventDepotPreview.runtimeUnresolved",
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
        plan["_ActivityOrigin"] = (
            "priority" if row.get("LegacyActivityFirst") else "inventory"
        )
        return plan

    # 先解析显式行，all 预设不能覆盖任何已保存的自定义目标。
    # 未勾选的关卡只由用户在前端决定，不产生计划也不提示。
    skipped_keys: set[tuple[str, str]] = set()
    selected: dict[int, dict] = {}
    for position, row in enumerate(rows):
        if not isinstance(row, dict) or row.get("StageType") == "all":
            continue
        kind = row.get("StageType", "material")
        pool = {"material": materials, "activity": stages, "orundum": orundum}.get(
            kind, []
        )
        index = row.get("StageIndex", position + 1 if "Stage" in row else None)
        if row.get("Skip"):
            if (
                isinstance(index, int)
                and not isinstance(index, bool)
                and index > len(pool)
                and pool
                and (row.get("LegacyIndex") or row.get("LegacyActivityFirst"))
            ):
                index = 1
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
                    "eventDepotPreview.runtimeUnresolved",
                    f"第 {position + 1} 个活动选择暂时不可用，已保留原选择",
                )
            )
            continue
        if index > len(pool):
            if row.get("LegacyIndex") or row.get("LegacyActivityFirst"):
                notices.append(
                    (
                        "eventDepotPreview.legacyFallback",
                        f"第 {position + 1} 个旧活动序号暂时越界，本轮沿用旧版第一关回退",
                    )
                )
                index = 1
            else:
                notices.append(
                    (
                        "eventDepotPreview.runtimeUnresolved",
                        f"第 {position + 1} 个活动序号暂时越界，已保留原选择",
                    )
                )
                continue
        plan = build(row, pool[index - 1])
        if plan is not None:
            if row.get("LegacyActivityFirst"):
                plan.update(
                    UseMedicine=medicine_count > 0,
                    MedicineCount=medicine_count,
                    UseStone=(priority_source or {}).get("UseStone") is True,
                    StoneCount=(priority_source or {}).get("StoneCount", 0),
                )
            else:
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
    # 同一关卡可能同时保留旧活动优先与库存行，取消勾选必须覆盖两份来源。
    selected = {
        position: plan
        for position, plan in selected.items()
        if (plan["Stage"], plan["DropId"]) not in skipped_keys
    }
    explicit_keys = {(plan["Stage"], plan["DropId"]) for plan in selected.values()}
    custom_plans = {
        (plan["Stage"], plan["DropId"]): plan
        for position, plan in selected.items()
        if not rows[position].get("LegacyActivityFirst")
    }
    plans = []
    budget_assigned = any(
        "MedicineCount" in plan or "UseMedicine" in plan for plan in selected.values()
    )
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
                # 默认 999/9999 不能抬高旧自定义目标；旧优先药量仅转交这一个关卡。
                target = custom_plans[key]
                target["_ActivityOrigin"] = "mixed"
                conflict = False
                for enabled, count in (
                    ("UseMedicine", "MedicineCount"),
                    ("UseStone", "StoneCount"),
                ):
                    if count not in target and enabled not in target:
                        target.update({enabled: plan[enabled], count: plan[count]})
                    elif (
                        target.get(enabled) != plan[enabled]
                        or target.get(count, 0) != plan[count]
                    ):
                        conflict = True
                if conflict:
                    notices.append(
                        (
                            "eventDepotPreview.budgetConflict",
                            "旧活动选关与库存目标重合，沿用自定义目标及已有药石额度，另一份原额度保留在迁移前备份",
                        )
                    )
                continue
            if (
                not budget_assigned
                and not row.get("LegacyIndex")
                and not row.get("LegacyActivityFirst")
                and "MedicineCount" not in plan
                and "UseMedicine" not in plan
            ):
                plan.update(
                    UseMedicine=medicine_count > 0, MedicineCount=medicine_count
                )
                budget_assigned = True
            plans.append(plan)
    return plans, notices
