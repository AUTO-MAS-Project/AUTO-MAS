"""计划覆写；原生字段透传，未设置的项目继续使用账号配置。"""

from datetime import datetime

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


def plan_panels(
    user: OkwwUserConfig, *, now: datetime | None = None
) -> dict[str, dict]:
    """当天计划按北京时间 04:00 切日，与既有周计划及轮换共用入口。"""
    if user.Info.PlanMode == "Fixed":
        return {}
    plan = Config.PlanConfig[user.Info.PlanMode]
    if not isinstance(plan, OkwwPlanConfig):
        raise ValueError("所选计划不是 Okww 计划表")
    if now is None:
        return panel_overrides(plan.get_current_key())
    key = getattr(plan, plan.current_group(now)).Key
    return panel_overrides(key.model_dump(exclude_none=True))


def panel_overrides(key: dict) -> dict[str, dict]:
    """将快捷项与其余覆写合为原生面板值。"""
    result = {
        name: {
            field: value
            for field, value in values.items()
            if field != "Exit After Task"
        }
        for name, values in key["Configs"].items()
    }
    daily = result.setdefault("DailyTask.json", {})
    daily.update(
        {raw: key[name] for name, raw in DAILY_FIELD_NAMES.items() if name in key}
    )
    return result


def account_daily_fields(user: OkwwUserConfig) -> dict:
    """读取启用叠加的账号快捷字段。"""
    return (
        {raw: getattr(user.Task, name) for name, raw in DAILY_FIELD_NAMES.items()}
        if user.Info.IfQuickConfig
        else {}
    )


def plan_managed_fields(user: OkwwUserConfig, kind: str = "daily") -> set[str]:
    """当天计划明确覆写的字段，账号网页与 GUI 均保持只读。"""
    from .config_fields import PANEL_FILES

    return set(plan_panels(user).get(PANEL_FILES[kind], {}))


def account_panel_values(user: OkwwUserConfig, kind: str, values: dict) -> dict:
    """保留账号默认值，过滤 GUI 回读中的当天计划显示值。"""
    from .config_fields import panel_values

    managed = plan_managed_fields(user, kind)
    return {
        **panel_values(user, kind),
        **{name: value for name, value in values.items() if name not in managed},
    }


def daily_panel_patch(user: OkwwUserConfig, values: dict) -> dict:
    """网页与 GUI 保存同样保护计划字段，不将当天值固化进账号默认值。"""
    managed = plan_managed_fields(user)
    return {
        "DailyConfig": account_panel_values(user, "daily", values),
        **{
            name: values[key]
            for name, key in DAILY_FIELD_NAMES.items()
            if key in values and key not in managed
        },
    }


def validate_plan_targets(configs: dict[str, dict]) -> None:
    """拒绝只有部分目标字段的计划，避免混用账号目标。"""
    from .config_fields import CONDITIONS, OPTIONS

    for filename, root, label, required in (
        ("DailyTask.json", "Which to Farm", "日常刷取目标", ()),
        ("FarmEchoTask.json", "Teleport to Boss", "4C 首领目标", ("Boss",)),
    ):
        values = configs.get(filename, {})
        dependent = {
            name: modes
            for name, (parent, modes) in CONDITIONS.items()
            if parent == root
        }
        if not ({root, *required, *dependent} & values.keys()):
            continue
        mode = values.get(root)
        active = (
            *required,
            *(name for name, modes in dependent.items() if mode in modes),
        )
        if mode not in OPTIONS[root] or any(
            values.get(name) is None for name in active
        ):
            raise ValueError(
                f"计划表的{label}配置不完整，请在详细配置中一起设置或恢复继承"
            )
