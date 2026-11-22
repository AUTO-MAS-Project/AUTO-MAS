#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""M9A 托管的运行、配置、恢复与托管属主接入声明（按确切类型 ``M9AConfig`` 登记）。

现在仍由 MFW 管理器运行、共用 MFW 的配置回调与恢复池；第 9 步 M9A 有了自己的流程后，
只改这里的 ``manager_factory``。
"""

from __future__ import annotations

from functools import partial

from app.models.config import M9AConfig
from app.task.MaaFW.owner_entry import BuiltinConfigOwner
from app.task.MaaFW.registration import (
    build_config_handler,
    build_manager,
    load_restore_pools,
)
from app.task.MaaFW.tools.embedded import owners
from app.task.registration import ScriptRegistration

M9A_OWNER = "m9a_adapter"
_OWNER = BuiltinConfigOwner(M9A_OWNER, lambda: M9AConfig)


def _resolve_owner() -> BuiltinConfigOwner:
    return _OWNER


def register_owner() -> None:
    """把 M9A 名下的托管（确切类型 ``M9AConfig``）登记给项目更新一侧。"""

    owners.register_owner(M9A_OWNER, resolve=_resolve_owner)


REGISTRATION = ScriptRegistration(
    config_type=M9AConfig,
    run_types=(M9AConfig,),
    manager_factory=build_manager,
    create_config_handler=partial(build_config_handler, M9AConfig, owner=M9A_OWNER),
    load_restore_pools=load_restore_pools,
    config_priority=5,
    restore_priority=9,
)
