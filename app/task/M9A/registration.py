#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""M9A 托管的运行、配置、恢复与托管属主接入声明（按确切类型 ``M9AConfig`` 登记）。

第 9 步起 M9A 跑自己的流程：``manager_factory`` 造 ``manager.M9AManager``，配置回调是
``config_hooks.build_m9a_config_handler()``（通用 MFW 那份只换掉保存前准备），恢复池是
``config_hooks.M9A_RESTORE_POOLS``。三样都在函数里现导入：本模块启动期就会被导入，不拉起流程模块。

托管属主还给出预览的规则表（``rules.M9A_PLAN_RULES``）与导入 / 克隆前的项目校验（只收 M9A 项目）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.config import M9AConfig
from app.task.M9A.rules import M9A_PLAN_RULES, TYPE_KEY, is_m9a_project
from app.task.MaaFW.blocks.maafw_project_update.host import owners
from app.task.MaaFW.owner_entry import BuiltinConfigOwner
from app.task.registration import ScriptRegistration

if TYPE_CHECKING:
    from app.models.script_contracts import ScriptConfigHandler
    from app.models.task import ScriptItem, TaskExecuteBase
    from app.utils.common.config.restore import ConfigRestorePool

M9A_OWNER = "m9a_adapter"
# 预览与建计划同一份规则表；导入 / 克隆只收 M9A 项目
_OWNER = BuiltinConfigOwner(
    M9A_OWNER,
    lambda: M9AConfig,
    plan_rules=M9A_PLAN_RULES,
    claims_project=is_m9a_project,
    project_label=TYPE_KEY,
)


def _resolve_owner() -> BuiltinConfigOwner:
    return _OWNER


def register_owner() -> None:
    """把 M9A 名下的托管（确切类型 ``M9AConfig``）登记给项目更新一侧。"""

    owners.register_owner(M9A_OWNER, resolve=_resolve_owner)


def build_manager(script_item: ScriptItem) -> TaskExecuteBase:
    """M9A 自己的脚本级管理器（现导入，启动期不拉起流程模块）。"""

    from .manager import M9AManager

    return M9AManager(script_item)


def build_handler() -> ScriptConfigHandler:
    """M9A 的配置回调：通用 MFW 那份只换掉保存前准备（``config_hooks``）。"""

    from .config_hooks import build_m9a_config_handler

    return build_m9a_config_handler()


def load_pools() -> list[ConfigRestorePool]:
    """M9A 的恢复池：mas 池的恢复那一步换成 M9A 自己的整理，native 池原样（``config_hooks``）。"""

    from .config_hooks import M9A_RESTORE_POOLS

    return M9A_RESTORE_POOLS


REGISTRATION = ScriptRegistration(
    config_type=M9AConfig,
    run_types=(M9AConfig,),
    manager_factory=build_manager,
    create_config_handler=build_handler,
    load_restore_pools=load_pools,
    config_priority=5,
    restore_priority=9,
)
