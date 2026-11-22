#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""MSS 托管的运行、配置、恢复与托管属主接入声明（按确切类型 ``MSSConfig`` 登记）。

第 10 步起 MSS 跑自己的流程：``manager_factory`` 造 ``manager.MSSManager``（在函数里现导入：本模块启动期就会
被导入，不拉起流程模块）。配置回调与恢复池仍用中立的通用版（``MaaFW/seams/config_handler``，不经
``MaaFW/registration``）：MSS 没有保存前整理。

托管属主只收 MSS 项目（导入 / 克隆前的项目校验）；MSS 没有规则表，预览用空表。
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from app.models.config import MSSConfig
from app.task.MaaFW.blocks.maafw_project_update.host import owners
from app.task.MaaFW.seams.config_handler import (
    build_maafw_config_handler,
    load_maafw_restore_pools,
)
from app.task.MaaFW.seams.owner_entry import BuiltinConfigOwner
from app.task.MSS.rules import TYPE_KEY, is_mss_project
from app.task.registration import ScriptRegistration

if TYPE_CHECKING:
    from app.models.task import ScriptItem, TaskExecuteBase

MSS_OWNER = "mss_adapter"
# 导入 / 克隆只收 MSS 项目；规则表是空表
_OWNER = BuiltinConfigOwner(
    MSS_OWNER,
    lambda: MSSConfig,
    claims_project=is_mss_project,
    project_label=TYPE_KEY,
)


def _resolve_owner() -> BuiltinConfigOwner:
    return _OWNER


def register_owner() -> None:
    """把 MSS 名下的托管（确切类型 ``MSSConfig``）登记给项目更新一侧。"""

    owners.register_owner(MSS_OWNER, resolve=_resolve_owner)


def build_manager(script_item: ScriptItem) -> TaskExecuteBase:
    """MSS 自己的脚本级管理器（现导入，启动期不拉起流程模块）。"""

    from .manager import MSSManager

    return MSSManager(script_item)


REGISTRATION = ScriptRegistration(
    config_type=MSSConfig,
    run_types=(MSSConfig,),
    manager_factory=build_manager,
    create_config_handler=partial(
        build_maafw_config_handler, MSSConfig, owner=MSS_OWNER
    ),
    load_restore_pools=load_maafw_restore_pools,
    config_priority=5,
    restore_priority=9,
)
