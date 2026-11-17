#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
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


import json
from collections.abc import Sequence
from copy import deepcopy

from auto_mas_core.host.core_notify_task_content import (
    prepare_screenshot_images as prepare_screenshot_images,
)
from auto_mas_core.host.core_notify_task_content import (
    screenshot_entries as screenshot_entries,
)
from auto_mas_core.host.utils import get_logger

from maa_adapter.constants import _MAA_CULTIVATE_TASK_NAME
from maa_adapter.cultivate import (
    CultivatePlan,
    OperatorTarget,
    dump_cultivate_targets,
)
from maa_adapter.cultivate.activity_inventory import resolve_activity_inventory_plans
from maa_adapter.native.runtime_config import _MAA_DEPOT_QUOTA_KEYS, _with_type_first

logger = get_logger("MAA")

# 养成注入的任务名（语言无关，日志锚定与来源查找都用它，方案决策 27/30）


_MAA_AUTO_CULTIVATE_TASK_NAME = "干员培养"


_MAA_DATA_UPDATE_TASK_NAME = "更新数据"


# 识别链完成标记：锚定注入的任务名 + 链后缀（MAS 强制 zh-cn，方案 §4.2/T0.3）
_MAA_DEPOT_CHAIN_COMPLETION_MARKERS = (
    "完成任务: 活动关均衡理智 (仓库识别)",
    "完成任务: 库存保持与干员养成 (仓库识别)",
    "完成任务: 活动库存保持 (仓库识别)",
    "完成任务: 库存保持 (仓库识别)",
    f"完成任务: {_MAA_CULTIVATE_TASK_NAME} (仓库识别)",
    f"完成任务: {_MAA_DATA_UPDATE_TASK_NAME} (仓库识别)",
)


_MAA_OPER_BOX_CHAIN_COMPLETION_MARKERS = (
    f"完成任务: {_MAA_DATA_UPDATE_TASK_NAME} (干员识别)",
)


def _copy_matching_depot_plan(source_task: dict, *, stage: str, drop_id: str) -> dict:
    """按关卡与材料匹配来源计划，复制其高级参数供各类库存任务透传。"""

    source_plans = source_task.get("PlanList") or []
    if not isinstance(source_plans, list):
        return {}
    return deepcopy(
        next(
            (
                item
                for item in source_plans
                if isinstance(item, dict)
                and item.get("Stage") == stage
                and item.get("DropId") == drop_id
            ),
            {},
        )
    )


def _build_depot_maintain_task(
    plans_json: str,
    source_task: dict | None = None,
    *,
    name: str = "库存保持与干员养成",
) -> dict:
    """生成 MAA 库存保持任务配置。

    只覆盖 MAS 面板管理的 Stage/DropId/DropCount；其余字段（含用户在 MAA 里设的
    UseMedicine/UseStone 等）从来源任务整条透传——上游私有格式只做值经手，
    不按 MAS 口径改写其语义。
    """

    source_task = source_task or {}

    plans = []
    source_plans = deepcopy(source_task.get("PlanList") or [])
    for plan in json.loads(plans_json):
        if (
            isinstance(plan, dict)
            and isinstance(plan.get("Stage"), str)
            and bool(plan["Stage"])
            and isinstance(plan.get("DropId"), str)
            and bool(plan["DropId"])
            and isinstance(plan.get("DropCount"), int)
            and not isinstance(plan.get("DropCount"), bool)
            and plan["DropCount"] > 0
        ):
            source_index = next(
                (
                    index
                    for index, item in enumerate(source_plans)
                    if isinstance(item, dict)
                    and item.get("Stage") == plan["Stage"]
                    and item.get("DropId") == plan["DropId"]
                ),
                None,
            )
            source_plan = (
                source_plans.pop(source_index) if source_index is not None else {}
            )
            plans.append(
                {
                    **source_plan,
                    "Stage": plan["Stage"],
                    "DropId": plan["DropId"],
                    "DropCount": plan["DropCount"],
                }
            )

    # 必须走 _with_type_first：MAA 用 System.Text.Json 的多态元数据读条目，
    # $type 不在第一个属性就整个配置反序列化失败并静默退回 .bak（旧值）。
    # 下方注入点在 _repair_maa_task_queue 之后执行，不能指望队列级修复兜底。
    return _with_type_first(
        {
            **deepcopy(source_task),
            "Name": name,
            "IsEnable": True,
            "TaskType": "DepotMaintain",
            "PlanList": plans,
        }
    )


def _write_depot_plan_quota(task: dict, gate: str, count_key: str, count: int) -> None:
    """把一段额度写到本组每条计划；MAA 的数量字段只存在于计划级。"""

    for plan in task.get("PlanList") or []:
        if isinstance(plan, dict):
            plan.update({gate: count > 0, count_key: count})


def _apply_depot_quota_override(
    task: dict | None, *, medicine: int | None, stone: int | None
) -> None:
    """按 MAS 填写的数量覆盖该组每条计划的理智药与源石额度。

    MAA 的任务级 UseMedicine/UseStone 是整组总开关，关闭时序列化会把计划数量强制
    写成 0，所以填正数时一并打开；填 0 只落到计划上，不影响共用任务的另一组。
    留空表示沿用 MAA 原设置，整段不动。
    """

    if task is None:
        return
    for (gate, count_key), count in zip(
        _MAA_DEPOT_QUOTA_KEYS, (medicine, stone), strict=True
    ):
        if count is None:
            continue
        if count > 0:
            task[gate] = True
        _write_depot_plan_quota(task, gate, count_key, count)


def _build_auto_cultivate_task(
    targets: Sequence[OperatorTarget], catalog: list[dict], source_task: dict | None
) -> dict | None:
    """用现有养成目标驱动 MAA 原生培养任务，游戏操作与结果判定交给 MAA。

    任务参数沿用 MAA v6.19.0-beta.1 的 OperProgressTask 配置入口；模组
    尚无原生培养入口，保留在材料计划中，不下发给培养任务。
    """

    operators = {item["value"]: item for item in catalog}
    plans = []
    for target in targets:
        goals = [
            goal
            for goal in target.goals
            if goal.kind != "module"
            and goal.state not in ("achieved", "pending_confirm")
        ]
        if not goals:
            continue
        operator = operators.get(target.operator_id)
        if operator is None:
            raise ValueError(f"干员 {target.operator_id} 的培养数据缺失")
        mastery_levels = [0, 0, 0]
        skill_indices = {
            skill["value"]: skill["skillIndex"] for skill in operator["skills"]
        }
        elite_level = skill_level = 0
        for goal in goals:
            if goal.kind == "elite":
                elite_level = goal.to_level
            elif goal.kind == "skill":
                skill_level = goal.to_level
            elif goal.kind == "mastery":
                index = skill_indices.get(goal.target_id)
                if index not in (1, 2, 3):
                    raise ValueError(f"干员 {operator['label']} 的专精技能序号缺失")
                mastery_levels[index - 1] = goal.to_level
        plans.append(
            {
                "Role": operator["profession"].title() or "Unknown",
                "Name": operator["label"],
                "Elite": elite_level,
                "SkillLevel": skill_level,
                "SkillMastery": mastery_levels,
                "ShowRole": False,
            }
        )
    if not plans:
        return None
    return _with_type_first(
        {
            **deepcopy(source_task or {}),
            "$type": "OperProgressTask",
            "Name": _MAA_AUTO_CULTIVATE_TASK_NAME,
            "IsEnable": True,
            "TaskType": "OperProgress",
            "Plans": plans,
        }
    )


def _build_event_depot_maintain_task(
    plans_json: str,
    activity_stages: list[dict],
    source_task: dict | None,
) -> tuple[dict | None, list[tuple[str, str]]]:
    """解析活动目标，保留原生任务身份与高级参数。"""

    source_task = source_task or {}
    plans, notices = resolve_activity_inventory_plans(
        plans_json,
        activity_stages,
        source_plans=source_task.get("PlanList", []),
    )
    if not plans:
        return None, notices
    return (
        _with_type_first(
            {
                **deepcopy(source_task),
                "Name": "活动关均衡理智",
                "IsEnable": True,
                "TaskType": "DepotMaintain",
                "PlanList": [
                    {
                        **_copy_matching_depot_plan(
                            source_task, stage=plan["Stage"], drop_id=plan["DropId"]
                        ),
                        **plan,
                    }
                    for plan in plans
                ],
            }
        ),
        notices,
    )


def _build_cultivate_task(
    plan: "CultivatePlan",
    source_task: dict | None,
    *,
    skip_during_activity: bool,
    skip_during_resource_collection: bool,
) -> dict | None:
    """把内核养成计划映射为 MAA 养成任务（MAA 字段名唯一出现点，方案 §4.1）。

    药石与临期药设置整段沿用 MAA 原任务与计划，MAS 只在显式填写数量时覆盖；
    计划无可用刷取条目时不生成任务。
    DropCount 是 MAA 的"保有量目标"语义（need = DropCount − 该材料现存，
    只比对本材料），故写净缺口 + 档案现存，MAA 现算后落回净缺口。
    """

    source_task = source_task or {}
    plans = []
    for entry in plan.entries:
        source_plan = _copy_matching_depot_plan(
            source_task, stage=entry.stage_code, drop_id=entry.item_id
        )
        plans.append(
            {
                **source_plan,
                "Stage": entry.stage_code,
                "DropId": entry.item_id,
                "DropCount": entry.amount + entry.held,
            }
        )
    if not plans:
        return None

    return {
        "$type": source_task.get("$type", "DepotMaintainTask"),
        "Name": "库存保持与干员养成",
        "IsEnable": True,
        "TaskType": "DepotMaintain",
        # 仓库识别随养成任务执行，缺口由 MAA 按最新库存现算（方案 §9）
        "UpdateDepot": True,
        "IsStageManually": True,
        "SkipDuringActivity": skip_during_activity,
        "SkipDuringResourceCollection": skip_during_resource_collection,
        "OnlyFirstInsufficientPlan": False,
        "SortByProgress": False,
        "UseAutoSeries": source_task.get("UseAutoSeries", False),
        **{
            key: source_task[key]
            for key in (
                "UseMedicine",
                "UseStone",
                "UseExpiringMedicine",
                "MedicineExpireDays",
                "UseExpireMedicineForActivity",
            )
            if key in source_task
        },
        "PlanList": plans,
    }


def _materialize_depot_quota_gates(task: dict) -> None:
    """把任务级药石总开关摊平到本组计划。

    MAA 的 DepotMaintain 用任务级 UseMedicine/UseStone 当整组开关，关闭时序列化
    会把每条计划的数量强制写成 0。合并后的任务只剩一个总开关，先摊平才能让一组
    原本关闭的额度在另一组打开总开关时不复活。
    """

    for gate, count_key in _MAA_DEPOT_QUOTA_KEYS:
        if not task.get(gate, True):
            _write_depot_plan_quota(task, gate, count_key, 0)


def _build_stock_cultivate_task(
    stock_task: dict | None, cultivate_task: dict | None, plan: CultivatePlan
) -> dict | None:
    """先备养成材料，再按完整消耗提高各条常备库存的保有量目标。"""

    if stock_task is None:
        return cultivate_task
    stock = deepcopy(stock_task)
    cultivate = deepcopy(cultivate_task) if cultivate_task is not None else None
    for group in (stock, cultivate):
        if group is not None:
            _materialize_depot_quota_gates(group)
    reservations = {item.item_id: item.amount for item in plan.reservations}
    for item in stock["PlanList"]:
        item["DropCount"] += reservations.get(item["DropId"], 0)
    stock["PlanList"] = (
        cultivate["PlanList"] if cultivate is not None else []
    ) + stock["PlanList"]
    stock.update(
        {
            "OnlyFirstInsufficientPlan": False,
            "SortByProgress": False,
            "SkipDuringActivity": False,
            "SkipDuringResourceCollection": False,
            **{
                gate: stock.get(gate, True)
                or (cultivate is not None and cultivate.get(gate, True))
                for gate, _ in _MAA_DEPOT_QUOTA_KEYS
            },
        }
    )
    return stock


def _merge_cultivate_target_updates(
    raw_targets: object,
    updated_targets: tuple[OperatorTarget, ...] | list[OperatorTarget],
    deferred_targets: Sequence[OperatorTarget],
) -> list[dict]:
    """按原顺序合并已知目标更新，延期干员的配置原文继续保留。"""

    updated = {
        item["operator_id"]: item for item in dump_cultivate_targets(updated_targets)
    }
    deferred_ids = {target.operator_id for target in deferred_targets}
    merged = []
    for item in raw_targets if isinstance(raw_targets, list) else []:
        if not isinstance(item, dict):
            continue
        operator_id = item.get("operator_id")
        if operator_id in deferred_ids:
            merged.append(deepcopy(item))
        elif operator_id in updated:
            merged.append(deepcopy(updated[operator_id]))
    return merged


def _build_data_update_task(
    source_task: dict | None, *, update_oper_box: bool = True
) -> dict:
    """构建更新数据任务，按需识别干员并始终识别仓库。

    识别结果供 check_log 采集落用户档案，缺口始终由 MAA 执行时现算。
    """

    source_task = source_task or {}
    return {
        **deepcopy(source_task),
        "$type": source_task.get("$type", "UserDataUpdateTask"),
        "Name": _MAA_DATA_UPDATE_TASK_NAME,
        "IsEnable": True,
        "TaskType": "UserDataUpdate",
        "UpdateOperBox": update_oper_box,
        "UpdateDepot": True,
        "TriggerInterval": "EveryTime",
    }
