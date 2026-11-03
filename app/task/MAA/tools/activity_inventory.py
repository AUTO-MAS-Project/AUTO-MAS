#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""将 MAS 保存的活动选关意图解析为当期 MAA 库存保持计划。"""

import json
from copy import deepcopy


def _is_orundum(stage: dict) -> bool:
    return "玉" in str(stage.get("DropName", "")) or "玉" in str(stage.get("Drop", ""))


def _is_legacy(row: dict) -> bool:
    return bool(row.get("LegacyIndex") or row.get("LegacyActivityFirst"))


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


def _activity_identity(row: dict, position: int) -> tuple[str, int] | None:
    kind = row.get("StageType", "material")
    index = row.get("StageIndex", position + 1 if "Stage" in row else None)
    if (
        kind in ("activity", "material", "orundum")
        and isinstance(index, int)
        and not isinstance(index, bool)
        and index > 0
    ):
        return kind, index
    return None


def _resolve_activity_stage(
    row: dict,
    pools: dict[str, list[dict]],
    *,
    position: int,
    notices: list[tuple[str, str]],
) -> dict | None:
    key = _activity_identity(row, position)
    pool = pools[key[0]] if key is not None else []
    if row.get("Skip"):
        return pool[key[1] - 1] if key is not None and key[1] <= len(pool) else None
    if key is None or not pool:
        notices.append(
            (
                "core.eventDepotPreview.runtimeUnresolved",
                f"第 {position + 1} 个活动选择暂时不可用，已保留原选择",
            )
        )
        return None
    index = key[1]
    if index > len(pool):
        if not _is_legacy(row):
            notices.append(
                (
                    "core.eventDepotPreview.runtimeUnresolved",
                    f"第 {position + 1} 个活动序号暂时越界，已保留原选择",
                )
            )
            return None
        notices.append(
            (
                "core.eventDepotPreview.legacyFallback",
                f"第 {position + 1} 个旧活动序号暂时越界，本轮沿用旧版第一关回退",
            )
        )
        index = 1
    return pool[index - 1]


def _activity_drop_id(stage: dict) -> str | None:
    value = "30012" if _is_orundum(stage) else stage.get("Drop")
    return value if isinstance(value, str) and value.isdigit() else None


def _activity_target_count(row: dict, stage: dict | None = None) -> int | None:
    rock = (
        _is_orundum(stage) if stage is not None else row.get("StageType") == "orundum"
    )
    count = (
        row.get("OrundumDropCount", row.get("DropCount"))
        if rock
        else row.get("DropCount")
    )
    return (
        count
        if isinstance(count, int) and not isinstance(count, bool) and count > 0
        else None
    )


def _build_activity_plan(
    row: dict, stage: dict, *, notices: list[tuple[str, str]]
) -> dict | None:
    drop_id, count = _activity_drop_id(stage), _activity_target_count(row, stage)
    if drop_id is None or count is None:
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


def migrate_activity_inventory_plans(
    plans_json: str, activity_stages: list[dict]
) -> str:
    """保存时逐项迁移；无法解析的项保留，新项优先，成功项不再携带旧标记。"""
    rows = json.loads(plans_json)
    pools = _activity_stage_pools(activity_stages)

    def selection(
        row: dict, position: int
    ) -> tuple[tuple[str, int] | None, dict | None]:
        stage = _resolve_activity_stage(row, pools, position=position, notices=[])
        if stage is None:
            return None, None
        target_kind = "orundum" if _is_orundum(stage) else "material"
        if stage not in pools[target_kind]:
            return None, stage
        return (target_kind, pools[target_kind].index(stage) + 1), stage

    explicit_keys: dict[tuple[str, int], list[int]] = {}
    for position, row in enumerate(rows):
        if not isinstance(row, dict) or _is_legacy(row):
            continue
        key, stage = selection(row, position)
        if not row.get("Skip") and _activity_target_count(row) is None:
            continue
        for key in (_activity_identity(row, position), key):
            if key is not None:
                explicit_keys.setdefault(key, []).append(position)

    result = dict(enumerate(rows))
    migrated_positions: dict[tuple[str, int], int] = {}
    preferred_old_items: dict[int, tuple[tuple[bool, bool, int], dict]] = {}
    for position, row in enumerate(rows):
        if not isinstance(row, dict) or not _is_legacy(row):
            continue
        old_key = _activity_identity(row, position)
        if old_key is None:
            continue
        key, stage = selection(row, position)
        count = (
            _activity_target_count(row, stage)
            if key is not None
            else row.get("DropCount")
        )
        priority = (
            bool(row.get("Skip")),
            not bool(row.get("LegacyActivityFirst")),
            count if isinstance(count, int) and not isinstance(count, bool) else 0,
        )
        replacements = explicit_keys.get(old_key) or (
            explicit_keys.get(key) if key is not None else None
        )
        target: dict | None = row
        if not replacements:
            if key is None or stage is None:
                continue
            target = _build_activity_plan(row, stage, notices=[])
            if target is None:
                continue
            target.pop("Stage", None)
            target.pop("DropId", None)
            target.update(StageType=key[0], StageIndex=key[1])
            if "Skip" in row:
                target["Skip"] = row["Skip"]
            replacements = [migrated_positions.setdefault(key, position)]
        if position not in replacements:
            result.pop(position)
        # 取消优先，其次保留自定义目标；多个旧项回退到同关时取最高目标。
        for replacement in replacements:
            previous = preferred_old_items.get(replacement)
            if previous is None or priority > previous[0]:
                preferred_old_items[replacement] = priority, target
    # 每个输出位置只选一份旧项：迁移旧行，或给已有新行补缺省药石参数。
    for position, (_, source) in preferred_old_items.items():
        if _is_legacy(rows[position]):
            result[position] = source
        else:
            for field in ("UseMedicine", "MedicineCount", "UseStone", "StoneCount"):
                if field in source:
                    rows[position].setdefault(field, deepcopy(source[field]))
    migrated = list(result.values())
    return plans_json if migrated == rows else json.dumps(migrated, ensure_ascii=False)


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

    # 先解析显式行，all 预设不能覆盖任何已保存的自定义目标。
    # 未勾选的关卡只由用户在前端决定，不产生计划也不提示。
    skipped_keys: set[tuple[str, str]] = set()
    selected: dict[int, dict] = {}
    for position, row in enumerate(rows):
        if not isinstance(row, dict) or row.get("StageType") == "all":
            continue
        stage = _resolve_activity_stage(row, pools, position=position, notices=notices)
        if stage is None:
            continue
        if row.get("Skip"):
            drop_id = _activity_drop_id(stage)
            if drop_id is not None:
                skipped_keys.add((stage["Value"], drop_id))
            continue
        plan = _build_activity_plan(row, stage, notices=notices)
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
            for field in ("UseMedicine", "MedicineCount", "UseStone", "StoneCount"):
                if field in source:
                    plan.setdefault(field, source[field])
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
        if not _is_legacy(rows[position])
    }
    plans = []
    for position, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        if row.get("StageType") == "all":
            current = [
                _build_activity_plan(row, stage, notices=notices) for stage in stages
            ]
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
            if _is_legacy(row) and (key in edited_keys or key in skipped_keys):
                # 新选择优先于旧项，包括旧材料序号越界后的第一关回退。
                continue
            plans.append(plan)
    return plans, notices
