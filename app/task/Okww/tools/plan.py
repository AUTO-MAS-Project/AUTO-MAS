"""日常计划覆写；未选择的字段继续使用账号本次配置。"""

from app.core import Config
from app.models.config import OkwwPlanConfig, OkwwUserConfig

DAILY_FIELD_NAMES = {
    "WhichToFarm": "Which to Farm",
    "WhichTacetSuppressionToFarm": "Which Tacet Suppression to Farm",
    "WhichForgeryChallengeToFarm": "Which Forgery Challenge to Farm",
    "MaterialSelection": "Material Selection",
    "FarmNightmareNestForDailyEcho": "Farm Nightmare Nest for Daily Echo",
    "AdditionalTasks": "Additional Tasks to Run After Daily Task",
}


def task_config(user: OkwwUserConfig) -> dict:
    """将账号覆写与当天计划合并，返回供上游消费的日常参数。"""
    values = user.Task.model_dump() if user.Info.IfQuickConfig else {}
    if user.Info.PlanMode != "Fixed":
        plan = Config.PlanConfig[user.Info.PlanMode]
        if not isinstance(plan, OkwwPlanConfig):
            raise ValueError("所选计划不是 Okww 计划表")
        values.update(plan.get_current_key())

    return {
        target: values[name]
        for name, target in DAILY_FIELD_NAMES.items()
        if values.get(name) is not None
    }


def plan_managed_fields(user: OkwwUserConfig) -> set[str]:
    """当天计划明确覆写的原生字段，继承项仍由账号管理。"""
    if user.Info.PlanMode == "Fixed":
        return set()
    plan = Config.PlanConfig[user.Info.PlanMode]
    if not isinstance(plan, OkwwPlanConfig):
        raise ValueError("所选计划不是 Okww 计划表")
    return {
        DAILY_FIELD_NAMES[key]
        for key, value in plan.get_current_key().items()
        if key in DAILY_FIELD_NAMES and value is not None
    }


def daily_panel_patch(user: OkwwUserConfig, values: dict) -> dict:
    """网页与 GUI 保存同样保护计划字段，不将当天值固化进账号默认值。"""
    managed = plan_managed_fields(user)
    account = {
        **user.Task.DailyConfig,
        **{key: value for key, value in values.items() if key not in managed},
    }
    return {
        "DailyConfig": account,
        **{
            name: values[key]
            for name, key in DAILY_FIELD_NAMES.items()
            if key in values and key not in managed
        },
    }
