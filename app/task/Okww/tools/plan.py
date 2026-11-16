"""日常计划覆写；未选择的字段继续使用账号本次配置。"""

from app.core import Config
from app.models.config import OkwwPlanConfig, OkwwUserConfig


def task_config(user: OkwwUserConfig) -> dict:
    """将账号覆写与当天计划合并，返回供上游消费的日常参数。"""
    values = user.Task.model_dump() if user.Info.IfQuickConfig else {}
    if user.Info.PlanMode != "Fixed":
        plan = Config.PlanConfig[user.Info.PlanMode]
        if not isinstance(plan, OkwwPlanConfig):
            raise ValueError("所选计划不是 Okww 计划表")
        values.update(plan.get_current_key())
    names = {
        "WhichToFarm": "Which to Farm",
        "WhichTacetSuppressionToFarm": "Which Tacet Suppression to Farm",
        "WhichForgeryChallengeToFarm": "Which Forgery Challenge to Farm",
        "MaterialSelection": "Material Selection",
        "FarmNightmareNestForDailyEcho": "Farm Nightmare Nest for Daily Echo",
        "AdditionalTasks": "Additional Tasks to Run After Daily Task",
    }
    return {
        target: values[name]
        for name, target in names.items()
        if values.get(name) is not None
    }
