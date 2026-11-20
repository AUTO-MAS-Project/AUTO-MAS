#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
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
"""Okww 安装路径识别入口。"""

import uuid
from pathlib import Path

from app.core import Config
from app.models.config import OkwwConfig as RuntimeOkwwConfig
from app.services import wuthering_waves as _service_wuthering_waves


def resolve_client_path(script_id: str) -> Path:
    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(script_config, RuntimeOkwwConfig):
        raise TypeError("托管配置类型错误, 不是 OK-WW 类型")
    launcher_path = Path(str(script_config.Game.Path or "").strip())
    client_path = _service_wuthering_waves.resolve_wuthering_waves_process_path(
        launcher_path
    )
    return client_path


def resolve_startup_arguments(
    script_id: str, *, custom: bool, arguments: str
) -> tuple[list[str], bool]:
    from .tools.arguments import build_custom_arguments, daily_task_argument

    config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(config, RuntimeOkwwConfig):
        raise TypeError("托管配置类型错误, 不是 OK-WW 类型")
    native = config.Game.AccountSwitchMethod in ("OKWW", "OKWW_SINGLE")
    if custom:
        return build_custom_arguments(arguments), native
    if native:
        return ["-t", "MultiAccountConfigTask", "-e"], True
    if config.Info.RootPath is None:
        raise ValueError("请设置 ok-ww 脚本路径")
    return ["-t", daily_task_argument(config.Info.RootPath), "-e"], False


def read_task_config(
    script_id: str, user_id: str, kind: str, *, include_plan: bool = True
) -> dict:
    """读取面板快照；首次使用时从所选基础来源初始化。"""
    from copy import deepcopy

    from app.task.Okww.tools.backup_archive import mas_config_dir, owner_for_mode
    from app.task.Okww.tools.config_fields import (
        PANEL_DEFAULTS,
        PANEL_FILES,
        panel_values,
    )
    from app.task.Okww.tools.plan import DAILY_FIELD_NAMES, plan_panels
    from app.utils.common.io import read_dict_file

    from .tools.config_paths import _OKWW_REL_CONFIG_DIR

    config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(config, RuntimeOkwwConfig):
        raise ValueError("托管配置类型错误, 不是 OK-WW 类型")
    user = config.UserData[uuid.UUID(user_id)]
    if include_plan and config.is_locked:
        raise ValueError("OK-WW 正在运行，请结束任务后编辑")
    filename = PANEL_FILES[kind]
    saved = panel_values(user, kind)
    values = deepcopy(PANEL_DEFAULTS[kind])
    owner = owner_for_mode(user.Info.Base, user_id)
    root = None
    if owner is None:
        if config.Info.RootPath is None:
            if include_plan and not saved:
                raise ValueError("请先设置 OK-WW 安装路径")
        else:
            root = config.Info.RootPath / _OKWW_REL_CONFIG_DIR
    else:
        root = mas_config_dir(script_id, owner)
    if root is not None:
        path = root / filename
        if path.exists():
            values.update(read_dict_file(path))
    # 新增的来源字段可被发现，账号已保存的字段保持优先。
    values.update(saved)
    if kind == "daily":
        # 总开关关闭时仍显示已保存的账号值；执行时是否下发由 runtime_panels 决定。
        values.update(
            {
                raw_name: getattr(user.Task, name)
                for name, raw_name in DAILY_FIELD_NAMES.items()
            }
        )
    if include_plan:
        values.update(plan_panels(user).get(filename, {}))
    return values


async def save_task_config(
    script_id: str, user_id: str, kind: str, values: dict
) -> None:
    from app.task.Okww.tools.plan import account_panel_values, daily_panel_patch

    config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(config, RuntimeOkwwConfig):
        raise ValueError("托管配置类型错误, 不是 OK-WW 类型")
    if config.is_locked:
        raise ValueError("OK-WW 正在运行，请结束任务后编辑")
    from app.config import config_manager

    from .tools.config_fields import PANEL_FILES

    # 整个面板映射的读、改、写须与其他配置提交处于同一执行门内。
    async with config_manager.execution_gate():
        user = config.UserData[uuid.UUID(user_id)]
        if kind == "monthly" and "Monthly Card Time" in values:
            hour = values["Monthly Card Time"]
            if (
                isinstance(hour, bool)
                or not isinstance(hour, int)
                or not 0 <= hour <= 23
            ):
                raise ValueError("月卡时间应为 0 至 23 的整数")
        if kind == "daily":
            patch = daily_panel_patch(user, values)
        elif kind == "echo":
            patch = {"FarmEchoConfig": account_panel_values(user, kind, values)}
        else:
            patch = {
                "NativeConfigs": {
                    **user.Task.NativeConfigs,
                    PANEL_FILES[kind]: account_panel_values(user, kind, values),
                }
            }
        saved = await Config.update_user(
            script_id,
            user_id,
            {"Task": patch},
            precondition=lambda: not config.is_locked,
        )
        if not saved:
            raise ValueError("配置未保存，请结束任务后重试")


def read_config_labels(script_id: str, locale: str) -> dict[str, str]:
    from .tools.config_fields import load_labels

    config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(config, RuntimeOkwwConfig):
        raise ValueError("托管配置类型错误, 不是 OK-WW 类型")
    return load_labels(config.Info.RootPath, locale)


def describe_task_config(
    script_id: str, user_id: str, kind: str
) -> tuple[dict, list[dict]]:
    from .tools.config_fields import describe_fields
    from .tools.plan import plan_managed_fields

    values = read_task_config(script_id, user_id, kind)
    fields = describe_fields(values, kind)
    user = Config.ScriptConfig[uuid.UUID(script_id)].UserData[uuid.UUID(user_id)]
    managed = plan_managed_fields(user, kind)
    for field in fields:
        field["disabled"] = field["name"] in managed
    return values, fields


def describe_plan_configs(plan_id: str, day: str, locale: str) -> list[dict]:
    """复用账号原生面板描述，未绑定账号时仍能编辑已有标准字段。"""
    from copy import deepcopy

    from .tools.config_fields import (
        PANEL_DEFAULTS,
        PANEL_FILES,
        describe_fields,
        load_labels,
    )
    from .tools.plan import panel_overrides

    plan, group = _plan_day(plan_id, day)
    configs = panel_overrides(getattr(plan, group).Key.model_dump(exclude_none=True))
    reference = next(
        (
            (script_id, script, user_id)
            for script_id, script in Config.ScriptConfig.items()
            if isinstance(script, RuntimeOkwwConfig) and not script.is_locked
            for user_id, user in script.UserData.items()
            if user.Info.PlanMode == plan.uid
        ),
        None,
    )
    labels = load_labels(reference[1].Info.RootPath, locale) if reference else {}
    result = []
    for kind, filename in PANEL_FILES.items():
        values = deepcopy(PANEL_DEFAULTS[kind])
        if reference:
            values.update(
                read_task_config(
                    str(reference[0]), str(reference[2]), kind, include_plan=False
                )
            )
        overrides = configs.get(filename, {})
        fields = describe_fields({**values, **overrides}, kind)
        # 日常退出由 MAS 的启动参数管理；4C 退出不用于日常附加任务。
        fields = [field for field in fields if field["name"] != "Exit After Task"]
        for field in fields:
            if (
                field["name"]
                in {
                    "Which Tacet Suppression to Farm",
                    "Which Forgery Challenge to Farm",
                }
                and kind == "daily"
            ):
                field.update(minimum=1, maximum=99)
        result.append(
            dict(
                kind=kind,
                filename=filename,
                values=values,
                fields=fields,
                overrides=overrides,
                labels=labels,
            )
        )
    return result


def _plan_day(plan_id: str, day: str):
    """校验公共计划槽位，拒绝未知日期及其他专项计划。"""
    import calendar

    from app.models.config import OkwwPlanConfig

    plan = Config.PlanConfig[uuid.UUID(plan_id)]
    if not isinstance(plan, OkwwPlanConfig):
        raise ValueError("不是 Okww 计划表")
    group = (
        day
        if day == "ALL" or day in calendar.day_name
        else plan.day_group_of(day.removeprefix("Day"))
    )
    if group != day:
        raise ValueError("无效的计划日期")
    return plan, group


async def save_plan_configs(plan_id: str, day: str, configs: dict[str, dict]) -> None:
    """将详细页的日常快捷项写回原有字段，避免两份覆写互相覆盖。"""
    from copy import deepcopy

    from app.config import config_manager
    from app.models.config.plan import OkwwPlanKey

    from .tools.config_fields import PANEL_FILES
    from .tools.plan import DAILY_FIELD_NAMES, validate_plan_targets

    if set(configs) - set(PANEL_FILES.values()):
        raise ValueError("不支持的任务配置")
    async with config_manager.execution_gate():
        plan, group = _plan_day(plan_id, day)
        validate_plan_targets(configs)
        native = deepcopy(configs)
        daily = native.get("DailyTask.json", {})
        # 月卡时间沿用账号面板的公共约束。
        hour = native.get(PANEL_FILES["monthly"], {}).get("Monthly Card Time")
        if hour is not None and (
            isinstance(hour, bool) or not isinstance(hour, int) or not 0 <= hour <= 23
        ):
            raise ValueError("月卡时间应为 0 至 23 的整数")
        key = {name: daily.pop(raw, None) for name, raw in DAILY_FIELD_NAMES.items()}
        for values in native.values():
            values.pop("Exit After Task", None)
        key["Configs"] = {name: values for name, values in native.items() if values}
        validated = OkwwPlanKey.model_validate(key)
        await Config.update_plan(
            str(plan.uid), {group: {"Key": validated.model_dump()}}
        )
