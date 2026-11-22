#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""M9A 托管的运行、配置、恢复与托管属主接入声明（按确切类型 ``M9AConfig`` 登记）。

第 9 步起 M9A 跑自己的流程：``manager_factory`` 造 ``manager.M9AManager``，配置回调是
``config_hooks.build_m9a_config_handler()``（通用 MFW 那份只换掉保存前准备），恢复池是
``config_hooks.M9A_RESTORE_POOLS``。三样都在函数里现导入：本模块启动期就会被导入，不拉起流程模块。

回退第 9 步（回到 MFW 管理器 + 风味路径）只需要把这三样换回通用 MFW 的
（``MaaFW/registration.build_manager``、``build_maafw_config_handler(M9AConfig, owner=M9A_OWNER)``、
``load_maafw_restore_pools``），即 revert 翻登记的那一个提交。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.config import M9AConfig
from app.task.MaaFW.owner_entry import BuiltinConfigOwner
from app.task.MaaFW.tools.embedded import owners
from app.task.registration import ScriptRegistration

if TYPE_CHECKING:
    from app.models.script_contracts import ScriptConfigHandler
    from app.models.task import ScriptItem, TaskExecuteBase
    from app.utils.common.config.restore import ConfigRestorePool

M9A_OWNER = "m9a_adapter"
_OWNER = BuiltinConfigOwner(M9A_OWNER, lambda: M9AConfig)


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
