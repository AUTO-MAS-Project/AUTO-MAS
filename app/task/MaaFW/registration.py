#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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

"""通用 MFW 的运行、配置、恢复与托管属主接入声明。

三种托管类型（通用 MFW、M9A、MSS）各自显式登记（M9A、MSS 的在 ``app/task/M9A/registration.py``、
``app/task/MSS/registration.py``）：回调、恢复池、属主都按确切类型认，不靠配置类之间的继承。M9A 第 9 步起
跑自己的流程与配置回调（``app/task/M9A/manager``、``config_hooks``）；MSS 第 10 步起跑自己的流程
（``app/task/MSS/manager``），配置回调与恢复池仍是同一套。这里的 ``build_manager``（MFW 管理器）只跑通用
MFW。配置回调与恢复池的实现在中立模块
``tools/embedded/config_handler``，这里的 ``build_config_handler`` / ``load_restore_pools`` 只是转出名。
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from app.models.config import M9AConfig, MaaFWConfig, MSSConfig
from app.models.script_contracts import ScriptConfigHandler
from app.task.MaaFW.blocks.maafw_project_update.host import owners
from app.task.MaaFW.owner_entry import BuiltinConfigOwner
from app.task.MaaFW.tools.embedded.config_handler import (
    build_maafw_config_handler,
    load_maafw_restore_pools,
)
from app.task.MaaFW.tools.embedded.config_handler import (
    expected_game_kind as expected_game_kind,
)
from app.task.registration import ScriptRegistration

if TYPE_CHECKING:
    from app.config import ConfigEntry
    from app.models.task import ScriptItem, TaskExecuteBase

# 「是 MFW 托管」的确切类型（通用 MFW、M9A、MSS 三个专项都算）：桌面分身判定、外壳配置导入、
# M9A 迁移后归档这类按家族判断的地方都用它按确切类型比，不用 isinstance。M9A、MSS 有了自己的流程后
# 仍在里面；插件形态由各专项的声明取代。
MAAFW_FAMILY_TYPES: tuple[type[ConfigEntry], ...] = (MaaFWConfig, M9AConfig, MSSConfig)

MAAFW_OWNER = "maafw_adapter"
_OWNER = BuiltinConfigOwner(MAAFW_OWNER, lambda: MaaFWConfig)


def _resolve_owner() -> BuiltinConfigOwner:
    return _OWNER


def register_owner() -> None:
    """把通用 MFW 名下的托管（确切类型 ``MaaFWConfig``）登记给项目更新一侧。"""

    owners.register_owner(MAAFW_OWNER, resolve=_resolve_owner)


def build_manager(script_item: ScriptItem) -> TaskExecuteBase:
    from .embedded_manager import MaaFWEmbeddedManager

    return MaaFWEmbeddedManager(script_item)


def build_config_handler(
    config_type: type[ConfigEntry] = MaaFWConfig, *, owner: str = MAAFW_OWNER
) -> ScriptConfigHandler:
    """（转出名）一种托管类型的配置回调，实现在 ``tools/embedded/config_handler``。"""

    return build_maafw_config_handler(config_type, owner=owner)


# （转出名）MFW 的恢复池，实现在 ``tools/embedded/config_handler``
load_restore_pools = load_maafw_restore_pools


REGISTRATION = ScriptRegistration(
    config_type=MaaFWConfig,
    run_types=(MaaFWConfig,),
    manager_factory=build_manager,
    create_config_handler=partial(
        build_maafw_config_handler, MaaFWConfig, owner=MAAFW_OWNER
    ),
    load_restore_pools=load_maafw_restore_pools,
    config_priority=5,
    restore_priority=9,
)
