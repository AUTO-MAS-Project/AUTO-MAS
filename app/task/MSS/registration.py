#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""MSS 托管的运行、配置、恢复与托管属主接入声明（按确切类型 ``MSSConfig`` 登记）。

现在仍由 MFW 管理器运行、共用 MFW 的配置回调与恢复池；第 10 步 MSS 有了自己的流程后，
只改这里的 ``manager_factory``。
"""

from __future__ import annotations

from functools import partial

from app.models.config import MSSConfig
from app.task.MaaFW.owner_entry import BuiltinConfigOwner
from app.task.MaaFW.registration import (
    build_config_handler,
    build_manager,
    load_restore_pools,
)
from app.task.MaaFW.tools.embedded import owners
from app.task.registration import ScriptRegistration

MSS_OWNER = "mss_adapter"
_OWNER = BuiltinConfigOwner(MSS_OWNER, lambda: MSSConfig)


def _resolve_owner() -> BuiltinConfigOwner:
    return _OWNER


def register_owner() -> None:
    """把 MSS 名下的托管（确切类型 ``MSSConfig``）登记给项目更新一侧。"""

    owners.register_owner(MSS_OWNER, resolve=_resolve_owner)


REGISTRATION = ScriptRegistration(
    config_type=MSSConfig,
    run_types=(MSSConfig,),
    manager_factory=build_manager,
    create_config_handler=partial(build_config_handler, MSSConfig, owner=MSS_OWNER),
    load_restore_pools=load_restore_pools,
    config_priority=5,
    restore_priority=9,
)
