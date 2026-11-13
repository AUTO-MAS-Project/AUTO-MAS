"""MAA 活动库存配置的语义转换，不承担主程序插件化升级。"""

import json
from copy import deepcopy

from auto_mas_core.host.utils import get_logger

logger = get_logger("MAA 配置迁移")


def migrate_maa_stamina_pipeline(data: dict) -> tuple[dict, bool]:
    """保留完整旧配置，将原来启用的两类活动内容合并为动态库存目标。"""

    migrated = deepcopy(data) if isinstance(data, dict) else {}
    if not migrated or migrated.get("Data", {}).get("StaminaPipelineVersion") == 1:
        return migrated, False
    task = migrated.setdefault("Task", {})
    old_task = data.get("Task", {})
    plans = []
    if old_task.get("IfEventDepotMaintain", False):
        saved = old_task.get("EventDepotMaintainPlans", "[]")
        try:
            saved = json.loads(saved) if isinstance(saved, str) else saved
        except (TypeError, ValueError):
            saved = []
            logger.warning("旧活动库存计划无法解析，原内容已保留在迁移前备份")
        if not isinstance(saved, list):
            saved = []
        for index, plan in enumerate(saved, start=1):
            if isinstance(plan, dict):
                plan = deepcopy(plan)
                plan.setdefault("StageType", "material")
                plan.setdefault("StageIndex", index)
                plan["LegacyIndex"] = True
                plans.append(plan)
    if old_task.get("IfActivityFirst", True):
        plans.append(
            {
                "StageType": "activity",
                "StageIndex": old_task.get("ActivityStageIndex", 1),
                "DropCount": 999,
                "OrundumDropCount": 9999,
                "LegacyActivityFirst": True,
            }
        )
    task["IfEventDepotMaintain"] = bool(
        old_task.get("IfEventDepotMaintain", False)
        or old_task.get("IfActivityFirst", True)
    )
    task["EventDepotMaintainPlans"] = json.dumps(plans, ensure_ascii=False)
    state = migrated.setdefault("Data", {})
    state["StaminaPipelineBackup"] = json.dumps(data, ensure_ascii=False)
    state["StaminaPipelineVersion"] = 1
    return migrated, True
