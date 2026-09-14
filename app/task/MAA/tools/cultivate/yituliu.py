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

"""一图流数据源适配器：下载、解析、规范化为内核契约类型。

本模块是一图流字段名唯一允许出现的边界（规则：内核只认 CultivateDataSet
契约）。解析函数全部为纯函数；下载与快照读写是仅有的 IO。
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import httpx

from .types import (
    CultivateDataSet,
    DemandEntry,
    DropEntry,
    MaterialClass,
    Recipe,
    StageMeta,
)

# 一图流现架构为"静态 COS + 前端本地计算"，旧 API（/stage/t3 等）已 404
_DEMAND_URL = (
    "https://cdn.jsdelivr.net/gh/Arknights-yituliu/frontend-v2-plus@main"
    "/src/static/json/operator/character_table_simple.v2.json"
)
_MATRIX_URL = "https://cos.yituliu.cn/arknights/stage-drop/matrix.json"
_STAGE_INFO_URL = "https://backend.yituliu.cn/stage/info"
_RECIPE_URL = (
    "https://cdn.jsdelivr.net/gh/Arknights-yituliu/frontend-v2-plus@main"
    "/src/static/json/material/composite_table.v2.json"
)
_ITEM_INFO_URL = (
    "https://cdn.jsdelivr.net/gh/Arknights-yituliu/frontend-v2-plus@main"
    "/src/static/json/material/item_info.json"
)

# 资源本/芯片本在 /stage/info 中整类缺席（实测 2026-09-10），
# apCost 与星期开放规则用常量表补齐，口径对齐 MAA StageManager.AddPermanentStages。
# 星期以 0=周一..6=周日 表达；None = 无星期限制（LS-6）。
_PERMANENT_STAGES: tuple[StageMeta, ...] = (
    StageMeta("wk_kc_6", "LS-6", 36, None),
    StageMeta("wk_melee_6", "CE-6", 36, (1, 3, 5, 6)),
    StageMeta("wk_toxic_5", "AP-5", 30, (0, 3, 5, 6)),
    StageMeta("wk_armor_5", "SK-5", 30, (0, 2, 4, 5)),
    StageMeta("wk_fly_5", "CA-5", 30, (1, 2, 4, 6)),
    StageMeta("pro_a_1", "PR-A-1", 18, (0, 3, 4, 6)),
    StageMeta("pro_a_2", "PR-A-2", 36, (0, 3, 4, 6)),
    StageMeta("pro_b_1", "PR-B-1", 18, (0, 1, 4, 5)),
    StageMeta("pro_b_2", "PR-B-2", 36, (0, 1, 4, 5)),
    StageMeta("pro_c_1", "PR-C-1", 18, (2, 3, 5, 6)),
    StageMeta("pro_c_2", "PR-C-2", 36, (2, 3, 5, 6)),
    StageMeta("pro_d_1", "PR-D-1", 18, (1, 2, 5, 6)),
    StageMeta("pro_d_2", "PR-D-2", 36, (1, 2, 5, 6)),
)

# 资源关的固定产出映射：这些材料在掉落矩阵与 MAA stages.json 中都没有
# 掉落条目（固定产出不计入概率掉落统计），但确实由对应资源关产出。
# 映射为"物品 → 资源关 stageId"，直接给出唯一候选，不参与效率排序。
_FIXED_SOURCE_STAGES: dict[str, str] = {
    "4006": "wk_toxic_5",  # 采购凭证 ← AP-5
    "4001": "wk_melee_6",  # 龙门币   ← CE-6
}

# 实测 matrix 0 条直掉关且不在 MAA 排除表（2026-09-11）：模组凭证类属
# "不可获取"，绝不进 PlanList，否则 MaxTimes=∞ 无限刷。龙门币（4001）与
# 采购凭证（4006）不在其中——它们有确定的资源关产出（见 _FIXED_SOURCE_STAGES）。
_UNOBTAINABLE_ITEM_IDS = frozenset(
    {"mod_unlock_token", "mod_update_token_1", "mod_update_token_2"}
)

# 生息演算（RI）是独立模式：MAA 普通 Fight 无法导航到 RI 关卡（且"2字母+
# 数字"代码会被 StageManager 判为过期活动关拒绝），矩阵里的 RI 掉落数据
# 对自动刷取无意义，数据层直接剔除。
_EXCLUDED_STAGE_CODE_PREFIXES = ("RI-",)

# 插曲/别传常驻（一图流 stageType=ACT_PERM，游戏内长期开放，end 是远期占位
# 时间）不在 MAA 常驻关卡表内：StageManager.GetStageInfo 把不在表内、形如
# "2字母+数字"的编号判为过期活动关，库存保持/养成计划随即整条跳过（日志记
# "关卡未开放"）。这类关永远刷不到，会让材料缺口恒存在并持续抑制库存保持，
# 故数据层直接剔除。stageType 缺失时按 stageId 的 _perm 后缀兜底（实测两侧
# 158/158 完全等价）。
_EXCLUDED_STAGE_TYPES = frozenset({"ACT_PERM"})
_EXCLUDED_STAGE_ID_SUFFIXES = ("_perm",)


class YituliuDataError(RuntimeError):
    """一图流数据不可用（下载失败且无快照可回退）。"""


def _positive_items(raw: Any) -> dict[str, int]:
    """把 {itemId: count} 形态的消耗清洗为正整数字典。"""

    if not isinstance(raw, dict):
        return {}
    items: dict[str, int] = {}
    for item_id, count in raw.items():
        if (
            isinstance(item_id, str)
            and item_id
            and isinstance(count, int)
            and count > 0
        ):
            items[item_id] = count
    return items


def parse_demand_table(raw: Mapping[str, Any]) -> dict[str, tuple[DemandEntry, ...]]:
    """解析干员养成需求表（character_table_simple.v2.json）。

    elite 按相位下标即目标等级；skills 的 skillLevelUpCost 为专精 1..3 档
    （可能为 null，表示该技能无专精）；equip 的 itemCost 为模组 1..3 档。
    """

    demands: dict[str, tuple[DemandEntry, ...]] = {}
    for char_id, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        entries: list[DemandEntry] = []

        # 精英化：下标即目标等级（0 为精 0 基础态，无消耗）
        for level, cost in enumerate(entry.get("elite") or [], start=0):
            items = _positive_items(cost)
            if level > 0 and items:
                entries.append(DemandEntry("elite", "", level, items))

        # 专精：每个技能 1..3 档，skillLevelUpCost 可为 null
        for skill in entry.get("skills") or []:
            if not isinstance(skill, dict) or not skill.get("skillId"):
                continue
            costs = skill.get("skillLevelUpCost")
            if not isinstance(costs, list):
                continue
            for level, cost in enumerate(costs, start=1):
                items = _positive_items(
                    {
                        c.get("id"): c.get("count")
                        for c in cost or []
                        if isinstance(c, dict)
                    }
                )
                if items:
                    entries.append(
                        DemandEntry("mastery", skill["skillId"], level, items)
                    )

        # 模组：每个模组 1..3 档，itemCost 为 {itemId: count} 列表
        for equip in entry.get("equip") or []:
            if not isinstance(equip, dict) or not equip.get("uniEquipId"):
                continue
            costs = equip.get("itemCost")
            if not isinstance(costs, list):
                continue
            for level, cost in enumerate(costs, start=1):
                items = _positive_items(cost)
                if items:
                    entries.append(
                        DemandEntry("module", equip["uniEquipId"], level, items)
                    )

        if entries:
            demands[char_id] = tuple(entries)
    return demands


def parse_drop_matrix(raw: Mapping[str, Any] | list) -> tuple[DropEntry, ...]:
    """解析掉落矩阵；非数字物品 ID（随机材料/家具等占位）直接丢弃。"""

    entries = raw if isinstance(raw, list) else raw.get("matrix", [])
    drops: list[DropEntry] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        item_id = entry.get("itemId")
        stage_id = entry.get("stageId")
        times = entry.get("times")
        quantity = entry.get("quantity")
        if not isinstance(item_id, str) or not item_id.isdigit():
            continue
        if not isinstance(stage_id, str) or not stage_id:
            continue
        if not isinstance(times, (int, float)) or not isinstance(
            quantity, (int, float)
        ):
            continue
        if times <= 0:
            continue
        end = entry.get("end")
        drops.append(
            DropEntry(
                stage_id=stage_id,
                item_id=item_id,
                expected_per_run=quantity / times,
                start_ms=entry.get("start") or 0,
                end_ms=end if isinstance(end, int) else None,
            )
        )
    return tuple(drops)


def parse_stage_info(raw: Mapping[str, Any] | list) -> dict[str, StageMeta]:
    """解析关卡信息并合并 13 关常量表（资源本/芯片本在源数据中整类缺席）。"""

    entries: Any = (
        raw if isinstance(raw, list) else (raw.get("data") or raw.get("stages") or [])
    )
    stages: dict[str, StageMeta] = {
        meta.stage_id: meta
        for meta in (
            StageMeta(
                stage_id=str(entry.get("stageId") or ""),
                stage_code=str(entry.get("stageCode") or ""),
                ap_cost=entry.get("apCost") or 0,
                open_weekdays=None,
            )
            for entry in entries
            if isinstance(entry, dict) and entry.get("stageId")
        )
    }
    for meta in _PERMANENT_STAGES:
        stages.setdefault(meta.stage_id, meta)
    return stages


def parse_recipes(raw: Any) -> tuple[Recipe, ...]:
    """解析合成表为正向合成边（result ← ingredients）。

    composite 表是双形态 schema（实测 2026-09-12）：
    - ``resolve: true``（T2 等低级条目）：分解向——1×pathway 高级材料可
      分解为 count×itemId；逆向即合成边 result=高级, ingredients={低级: count}
      （与 MAA item_index 的 formula 一致）。
    - ``resolve: false``（T5 等高级条目）：合成向——pathway 直接就是配方
      （可多原料），result=itemId, ingredients={pathway: count}。
    """

    ingredients_by_result: dict[str, dict[str, int]] = {}

    def add_recipe(result: Any, ingredients: Mapping[Any, Any]) -> None:
        if not isinstance(result, str) or not result:
            return
        slot = ingredients_by_result.setdefault(result, {})
        for ingredient_id, count in ingredients.items():
            if isinstance(ingredient_id, str) and ingredient_id and count > 0:
                slot[ingredient_id] = count

    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict):
            continue
        item_id = entry.get("itemId")
        pathway = entry.get("pathway")
        if not isinstance(item_id, str) or not isinstance(pathway, list):
            continue
        steps = [
            step
            for step in pathway
            if isinstance(step, dict)
            and isinstance(step.get("itemId"), str)
            and isinstance(step.get("count"), int)
            and step["count"] > 0
        ]
        if not steps:
            continue
        if entry.get("resolve"):
            # 分解向：1×steps[k] 高级 → steps[k].count×itemId（逐条建合成边）
            for step in steps:
                add_recipe(step["itemId"], {item_id: step["count"]})
        else:
            # 合成向：count×steps 各项 → 1×itemId
            add_recipe(item_id, {step["itemId"]: step["count"] for step in steps})
    return tuple(
        Recipe(result_item_id=result, ingredients=dict(ingredients))
        for result, ingredients in sorted(ingredients_by_result.items())
    )


def build_material_class(
    demands: Mapping[str, tuple[DemandEntry, ...]],
    drops: tuple[DropEntry, ...],
    stages: Mapping[str, StageMeta],
    recipes: tuple[Recipe, ...],
) -> dict[str, MaterialClass]:
    """按三分类规则预计算物品类别（可直刷 > 可合成折算 > 不可获取）。

    _FIXED_SOURCE_STAGES 中的物品（采购凭证、龙门币）由资源关固定产出，
    与有掉落统计的材料同为可直刷，不因缺掉落条目被判为不可获取。
    """

    farmable = {drop.item_id for drop in drops if drop.stage_id in stages}
    farmable |= {
        item_id
        for item_id, stage_id in _FIXED_SOURCE_STAGES.items()
        if stage_id in stages
    }
    craftable = {recipe.result_item_id for recipe in recipes}
    demand_items = {
        item_id
        for entries in demands.values()
        for entry in entries
        for item_id in entry.items
    }
    classes: dict[str, MaterialClass] = {}
    for item_id in sorted(farmable | craftable | demand_items):
        if item_id in _UNOBTAINABLE_ITEM_IDS:
            classes[item_id] = "unobtainable"
        elif item_id in farmable:
            classes[item_id] = "farmable"
        elif item_id in craftable:
            classes[item_id] = "synthesizable"
        else:
            # 只出现在需求里、既无可直掉关也无配方（如未收录的新材料），按不可获取兜底
            classes[item_id] = "unobtainable"
    return classes


def parse_item_value(raw: Any) -> dict[str, float]:
    """解析一图流物品价值表（itemValue 为理智等价价值，综合效率用）。"""

    values: dict[str, float] = {}
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict):
            continue
        item_id, value = entry.get("itemId"), entry.get("itemValue")
        if isinstance(item_id, str) and item_id and isinstance(value, (int, float)):
            values[item_id] = float(value)
    return values


def apply_composite(
    stages: Mapping[str, StageMeta],
    drops: tuple[DropEntry, ...],
    item_value: Mapping[str, float],
) -> dict[str, StageMeta]:
    """计算各关卡综合效率（Σ(每次掉落期望×物品价值)/理智，1-7≈100% 基线）。"""

    value_rate: dict[str, float] = {}
    for drop in drops:
        value = item_value.get(drop.item_id)
        if value is None:
            continue
        value_rate[drop.stage_id] = (
            value_rate.get(drop.stage_id, 0.0) + drop.expected_per_run * value
        )
    result: dict[str, StageMeta] = {}
    for stage_id, meta in stages.items():
        ap = meta.ap_cost
        composite = value_rate.get(stage_id, 0.0) / ap if ap > 0 else 0.0
        result[stage_id] = StageMeta(
            stage_id=meta.stage_id,
            stage_code=meta.stage_code,
            ap_cost=meta.ap_cost,
            open_weekdays=meta.open_weekdays,
            composite=round(composite, 4),
        )
    return result


def _excluded_stage_ids(stage_raw: Mapping[str, Any] | list) -> set[str]:
    """MAA 无法导航的关卡 stageId 集（别传常驻；stageType 缺失时按后缀兜底）。"""

    entries: Any = (
        stage_raw
        if isinstance(stage_raw, list)
        else (stage_raw.get("data") or stage_raw.get("stages") or [])
    )
    excluded: set[str] = set()
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        stage_id = str(entry.get("stageId") or "")
        if not stage_id:
            continue
        if entry.get("stageType") in _EXCLUDED_STAGE_TYPES or stage_id.endswith(
            _EXCLUDED_STAGE_ID_SUFFIXES
        ):
            excluded.add(stage_id)
    return excluded


def normalize_dataset(
    demand_raw: Mapping[str, Any],
    matrix_raw: Mapping[str, Any] | list,
    stage_raw: Mapping[str, Any],
    recipe_raw: Any,
    item_info_raw: Any = None,
    *,
    data_version: str,
) -> CultivateDataSet:
    """把五个源数据规范化为内核契约数据集。"""

    demands = parse_demand_table(demand_raw)
    drops = parse_drop_matrix(matrix_raw)
    stages = parse_stage_info(stage_raw)
    recipes = parse_recipes(recipe_raw)
    excluded_stage_ids = _excluded_stage_ids(stage_raw)
    drops = tuple(
        drop
        for drop in drops
        if drop.stage_id not in excluded_stage_ids
        and not (
            drop.stage_id in stages
            and stages[drop.stage_id].stage_code.startswith(
                _EXCLUDED_STAGE_CODE_PREFIXES
            )
        )
    )
    item_value = parse_item_value(item_info_raw) if item_info_raw is not None else {}
    stages = apply_composite(stages, drops, item_value)
    return CultivateDataSet(
        demands=demands,
        drops=drops,
        stages=stages,
        recipes=recipes,
        material_class=build_material_class(demands, drops, stages, recipes),
        fixed_source_stages=dict(_FIXED_SOURCE_STAGES),
        item_value=item_value,
        data_version=data_version,
    )


def stage_candidates(
    dataset: CultivateDataSet, now_ms: int | None = None, *, limit: int | None = 10
) -> dict[str, list[dict[str, Any]]]:
    """按物品聚合可刷关卡候选，按该材料的单件期望理智升序（库存保持选择器用）。

    统计口径：单件期望理智 = 关卡理智 ÷ 该材料每次期望掉落，即"刷到
    一件要多少理智"，越小越优（1-7 刷固源岩 4.82 理智/件）。

    判据只针对该材料本身，不用关卡综合效率：综合效率含副产物价值，会
    把副产品值钱的关排前面（固源岩 14-20 综合 194.5% 但单件 12.95 理智，
    1-7 综合 95.7% 却只要 4.82 理智）。下拉首项即自动填关结果，二者
    必须同判据。

    now_ms 提供时过滤时间窗已结束的活动关（编辑器里选了过期关会被
    MAA 直接跳过，没有意义）。

    limit 截断排序去重后的候选（默认 10）：排名靠后的关单件理智全面
    更差，下拉只留噪音；首项（自动填关结果）不受影响。传 None 取全量。

    资源关的固定产出材料（采购凭证 ← AP-5 等）没有概率掉落数据，按
    dataset.fixed_source_stages 直接给出唯一候选，保证选中物品后一定有
    可选关卡。此类关卡不做星期过滤——资源关有固定开放日，按当天过滤会
    让用户在不开放的日子选不了该材料，开放时间交由 MAA 执行时判断。
    """

    candidates: dict[str, list[dict[str, Any]]] = {}
    for drop in dataset.drops:
        if now_ms is not None and not _window_open(drop, now_ms):
            continue
        meta = dataset.stages.get(drop.stage_id)
        if meta is None or not meta.stage_code or meta.ap_cost <= 0:
            continue
        if drop.expected_per_run <= 0:
            continue
        candidates.setdefault(drop.item_id, []).append(
            {
                "stage": meta.stage_code,
                "apCost": meta.ap_cost,
                "expectedPerRun": round(drop.expected_per_run, 4),
                "sanityPerItem": round(meta.ap_cost / drop.expected_per_run, 2),
                "composite": round(meta.composite * 100, 1),
            }
        )

    # 固定产出资源关：无概率掉落数据，直接映射为唯一候选
    for item_id, stage_id in dataset.fixed_source_stages.items():
        if candidates.get(item_id):
            continue  # 若数据源将来补上掉落统计，以真实数据为准
        meta = dataset.stages.get(stage_id)
        if meta is None or not meta.stage_code:
            continue
        candidates[item_id] = [
            {
                "stage": meta.stage_code,
                "apCost": meta.ap_cost,
                # 固定产出无单次期望，单件理智未知：置 None 表示"不适用"
                "expectedPerRun": None,
                "sanityPerItem": None,
                "composite": round(meta.composite * 100, 1),
                "fixed": True,
            }
        ]

    for item_id_key, option_list in candidates.items():
        # 固定产出项无单件理智（None），恒无同级可比对象，排在数值项之后
        option_list.sort(
            key=lambda option: (
                option["sanityPerItem"] is None,
                option["sanityPerItem"] if option["sanityPerItem"] is not None else 0.0,
                option["stage"],
            )
        )
        # 同关名可能有多组掉落统计（不同 stage_id 同 stage_code，如 14-20）：
        # 选择器里只保留单件期望理智最低的一条，避免下拉出现同关两项
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for option in option_list:
            if option["stage"] in seen:
                continue
            seen.add(option["stage"])
            deduped.append(option)
        candidates[item_id_key] = deduped[:limit] if limit is not None else deduped
    return candidates


def _window_open(drop: DropEntry, now_ms: int) -> bool:
    if drop.start_ms and drop.start_ms > now_ms:
        return False
    return drop.end_ms is None or drop.end_ms == 0 or now_ms <= drop.end_ms


def dataset_to_json(dataset: CultivateDataSet) -> dict[str, Any]:
    """契约数据集 → JSON 可序列化结构（快照存储用）。"""

    return {
        "data_version": dataset.data_version,
        "demands": {
            char_id: [
                {
                    "kind": entry.kind,
                    "target_id": entry.target_id,
                    "level": entry.level,
                    "items": dict(entry.items),
                }
                for entry in entries
            ]
            for char_id, entries in dataset.demands.items()
        },
        "drops": [
            {
                "stage_id": drop.stage_id,
                "item_id": drop.item_id,
                "expected_per_run": drop.expected_per_run,
                "start_ms": drop.start_ms,
                "end_ms": drop.end_ms,
            }
            for drop in dataset.drops
        ],
        "stages": [
            {
                "stage_id": meta.stage_id,
                "stage_code": meta.stage_code,
                "ap_cost": meta.ap_cost,
                "open_weekdays": meta.open_weekdays,
                "composite": meta.composite,
            }
            for meta in dataset.stages.values()
        ],
        "recipes": [
            {"result": recipe.result_item_id, "ingredients": dict(recipe.ingredients)}
            for recipe in dataset.recipes
        ],
        "material_class": dict(dataset.material_class),
        "fixed_source_stages": dict(dataset.fixed_source_stages),
        "item_value": dict(dataset.item_value),
    }


def dataset_from_json(raw: Mapping[str, Any]) -> CultivateDataSet:
    """快照 JSON → 契约数据集。

    快照可能写于剔除规则生效之前，故加载时同样剔除 MAA 无法导航的别传常驻
    关：stageType 不进快照，按 _perm 后缀判定（与 stageType 等价，见上方常量）。
    """

    return CultivateDataSet(
        demands={
            char_id: tuple(
                DemandEntry(
                    kind=entry["kind"],
                    target_id=entry["target_id"],
                    level=entry["level"],
                    items=entry["items"],
                )
                for entry in raw.get("demands", {}).get(char_id, [])
            )
            for char_id in raw.get("demands", {})
        },
        drops=tuple(
            DropEntry(
                stage_id=drop["stage_id"],
                item_id=drop["item_id"],
                expected_per_run=drop["expected_per_run"],
                start_ms=drop["start_ms"],
                end_ms=drop["end_ms"],
            )
            for drop in raw.get("drops", [])
            if not drop["stage_id"].endswith(_EXCLUDED_STAGE_ID_SUFFIXES)
        ),
        stages={
            meta["stage_id"]: StageMeta(
                stage_id=meta["stage_id"],
                stage_code=meta["stage_code"],
                ap_cost=meta["ap_cost"],
                open_weekdays=tuple(meta["open_weekdays"])
                if meta["open_weekdays"] is not None
                else None,
                composite=meta.get("composite", 0.0),
            )
            for meta in raw.get("stages", [])
        },
        recipes=tuple(
            Recipe(
                result_item_id=recipe["result"],
                ingredients=recipe["ingredients"],
            )
            for recipe in raw.get("recipes", [])
        ),
        material_class=dict(raw.get("material_class", {})),
        fixed_source_stages=dict(raw.get("fixed_source_stages", {})),
        item_value=dict(raw.get("item_value", {})),
        data_version=raw.get("data_version", ""),
    )


async def download_dataset(
    proxy: httpx.Proxy | str | None = None, *, timeout: float = 60.0
) -> CultivateDataSet:
    """并发下载五个数据源并规范化；任何一路失败整体失败。"""

    async def fetch_json(client: httpx.AsyncClient, url: str) -> Any:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

    async with httpx.AsyncClient(
        proxy=proxy, timeout=timeout, follow_redirects=True
    ) as client:
        (
            demand_raw,
            matrix_raw,
            stage_raw,
            recipe_raw,
            item_info_raw,
        ) = await asyncio.gather(
            fetch_json(client, _DEMAND_URL),
            fetch_json(client, _MATRIX_URL),
            fetch_json(client, _STAGE_INFO_URL),
            fetch_json(client, _RECIPE_URL),
            fetch_json(client, _ITEM_INFO_URL),
        )
    return normalize_dataset(
        demand_raw,
        matrix_raw,
        stage_raw,
        recipe_raw,
        item_info_raw,
        data_version=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )


def parse_operator_catalog(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    """解析干员选择器目录：id/名称/稀有度/职业（一图流全量表，决策 11）。

    只取展示字段，不进内核契约（CultivateDataSet 保持中性领域词汇）；
    排序为稀有度降序、名称升序。
    """

    catalog: list[dict[str, Any]] = []
    for char_id, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not char_id or not isinstance(name, str) or not name:
            continue
        rarity = entry.get("rarity")
        profession = entry.get("profession")
        catalog.append(
            {
                "value": char_id,
                "label": name,
                "rarity": rarity if isinstance(rarity, int) else 0,
                "profession": profession if isinstance(profession, str) else "",
            }
        )
    catalog.sort(key=lambda item: (-item["rarity"], item["label"]))
    return catalog


async def load_operator_catalog(
    cache_dir: Path,
    proxy: httpx.Proxy | str | None = None,
    *,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """加载干员选择器目录：快照直读，缺失则拉取需求表并并回快照。

    目录存在快照的 ``operators`` 键，与数据集共用保鲜机制；数据集刷新
    （write_snapshot 重写快照）会丢弃该键，下次调用自动重拉自愈。拉取
    失败抛 YituliuDataError，由调用方兜底。
    """

    snapshot = read_snapshot(cache_dir)
    operators = snapshot.get("operators") if isinstance(snapshot, dict) else None
    if isinstance(operators, list) and operators:
        return operators

    try:
        async with httpx.AsyncClient(
            proxy=proxy, timeout=timeout, follow_redirects=True
        ) as client:
            response = await client.get(_DEMAND_URL)
            response.raise_for_status()
            raw = response.json()
    except Exception as e:
        raise YituliuDataError(f"干员目录拉取失败: {e}") from e
    if not isinstance(raw, Mapping):
        raise YituliuDataError("干员目录数据格式异常（根不是对象）")

    catalog = parse_operator_catalog(raw)
    payload = snapshot if isinstance(snapshot, dict) else {}
    payload["operators"] = catalog
    payload.setdefault("saved_at", time.time())
    path = snapshot_path(cache_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # 目录只是缓存，写失败不影响本次返回
    return catalog


def snapshot_path(cache_dir: Path) -> Path:
    """快照文件路径（版本化目录由调用方决定，本模块只管单个文件）。"""

    return cache_dir / "yituliu" / "cultivate_dataset.json"


def read_snapshot(cache_dir: Path) -> dict[str, Any] | None:
    """读取快照；不存在或损坏时返回 None（回退链的最后一环）。"""

    path = snapshot_path(cache_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_snapshot(cache_dir: Path, dataset: CultivateDataSet) -> None:
    """写入快照；失败不抛出（快照只是缓存，写失败不影响本次结果）。"""

    path = snapshot_path(cache_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "saved_at": time.time(),
            "dataset": dataset_to_json(dataset),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _is_fresh(snapshot: Mapping[str, Any], max_age_hours: float, now: float) -> bool:
    saved_at = snapshot.get("saved_at")
    return isinstance(saved_at, (int, float)) and now - saved_at < max_age_hours * 3600


async def load_dataset(
    cache_dir: Path,
    proxy: httpx.Proxy | str | None = None,
    *,
    max_age_hours: float = 24.0,
    now: float | None = None,
) -> CultivateDataSet:
    """加载数据集：新鲜快照直读，过期/缺失则下载，失败回退旧快照。

    Args:
        cache_dir: 快照缓存目录（MAS 配置目录）。
        proxy: 代理配置，透传给 httpx。
        max_age_hours: 快照保鲜期，超过则尝试重新下载。
        now: 当前时间戳（epoch 秒），测试注入用。

    Returns:
        内核契约数据集。

    Raises:
        YituliuDataError: 下载失败且没有可回退的快照。
    """

    current = time.time() if now is None else now
    snapshot = read_snapshot(cache_dir)
    if snapshot is not None and _is_fresh(snapshot, max_age_hours, current):
        raw = snapshot.get("dataset")
        if isinstance(raw, Mapping):
            try:
                return dataset_from_json(raw)
            except (KeyError, TypeError, ValueError):
                pass  # 快照结构损坏：当作无快照处理，走下载路径
    try:
        dataset = await download_dataset(proxy)
    except Exception as e:
        if snapshot is not None and isinstance(snapshot.get("dataset"), Mapping):
            try:
                return dataset_from_json(snapshot["dataset"])
            except (KeyError, TypeError, ValueError):
                pass  # 回退快照同样损坏：只能报错
        raise YituliuDataError(f"一图流数据不可用且无快照可回退: {e}") from e
    write_snapshot(cache_dir, dataset)
    return dataset


_dataset_cache: tuple[float, CultivateDataSet] | None = None
_dataset_lock: asyncio.Lock | None = None


async def get_dataset_cached(
    cache_dir: Path,
    proxy: httpx.Proxy | str | None = None,
    *,
    max_age_hours: float = 24.0,
) -> CultivateDataSet:
    """带进程内缓存的数据集加载（避免每次请求重复反序列化快照）。"""

    global _dataset_cache, _dataset_lock
    if _dataset_lock is None:
        _dataset_lock = asyncio.Lock()
    current = time.time()
    if (
        _dataset_cache is not None
        and current - _dataset_cache[0] < max_age_hours * 3600
    ):
        return _dataset_cache[1]
    async with _dataset_lock:
        if (
            _dataset_cache is not None
            and time.time() - _dataset_cache[0] < max_age_hours * 3600
        ):
            return _dataset_cache[1]
        dataset = await load_dataset(cache_dir, proxy, max_age_hours=max_age_hours)
        _dataset_cache = (time.time(), dataset)
        return dataset
