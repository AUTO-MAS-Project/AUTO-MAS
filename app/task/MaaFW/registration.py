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

三种托管类型（通用 MFW、M9A、MSS）现在共用 MFW 管理器与同一套配置回调，但各自显式登记
（M9A、MSS 的在 ``app/task/M9A/registration.py``、``app/task/MSS/registration.py``）：回调、恢复池、
属主都按确切类型认，不靠配置类之间的继承。
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from app.models.config import M9AConfig, MaaFWConfig, MSSConfig
from app.models.script_contracts import ScriptConfigHandler
from app.task.MaaFW.owner_entry import BuiltinConfigOwner
from app.task.MaaFW.tools.embedded import owners
from app.task.registration import ScriptRegistration

if TYPE_CHECKING:
    from app.config import ConfigEntry
    from app.models.task import ScriptItem, TaskExecuteBase
    from app.utils.common.config.restore import ConfigRestorePool

# MFW 管理器运行、按「是 MFW 托管」自检的确切类型。第 9、10 步 M9A、MSS 各有自己的流程后
# 从这里删掉；任何地方要判断「是不是 MFW 托管」都用它按确切类型比，不用 isinstance。
MAAFW_RUN_TYPES: tuple[type[ConfigEntry], ...] = (MaaFWConfig, M9AConfig, MSSConfig)

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
    """一种托管类型的配置回调：保存前加密密码、读取前准备、新账号补默认队列、复制托管时克隆
    视图、删除托管时清理视图（只删本属主的视图）与删除后的运行池对账。三种类型各造一份，内容相同。"""

    from app.task.MaaFW.tools.embedded.default_snapshot import (
        initialize_user as initialize_maafw_user,
    )
    from app.task.MaaFW.tools.embedded.default_snapshot import (
        prepare_user_read as prepare_maafw_user_read,
    )
    from app.task.MaaFW.tools.embedded.script_lifecycle import (
        after_script_removal as after_maafw_script_removal,
    )
    from app.task.MaaFW.tools.embedded.script_lifecycle import (
        cleanup_script_files as cleanup_maafw_script_files,
    )
    from app.task.MaaFW.tools.embedded.script_lifecycle import (
        clone_script as clone_maafw_script,
    )
    from app.task.MaaFW.tools.embedded.user_update import (
        prepare_user_update as prepare_maafw_user_update,
    )

    return ScriptConfigHandler(
        # 宿主建号先取类上的 USER_CONFIG_CLASS，这一项只是兜底
        user_config_class=getattr(config_type, "USER_CONFIG_CLASS"),
        clone_script=clone_maafw_script,
        after_script_removal=after_maafw_script_removal,
        cleanup_script_files=partial(cleanup_maafw_script_files, owner=owner),
        prepare_user_update=prepare_maafw_user_update,
        prepare_user_read=prepare_maafw_user_read,
        initialize_user=initialize_maafw_user,
        game_kinds=("emulator", "client"),
        expected_game_kind=expected_game_kind,
        supports_mod_avd=True,
    )


def expected_game_kind(script, patch):
    """显式选择的公开 controller 决定目标类别，未导入项目时保留两类选择。"""
    from .tools.core.interface.loader import load_interface_model_cached
    from .tools.embedded.embedded_project import resolve_maafw_project_root

    controller = patch.get("Info", {}).get("Controller", script.Info.Controller)
    if not controller:
        return None
    root = resolve_maafw_project_root(str(script.uid), script)
    if not root.is_dir():
        return None
    interface = load_interface_model_cached(root)
    selected = next(
        (item for item in interface.controller if item.name == controller), None
    )
    if selected is None:
        return None
    return "emulator" if selected.type == "Adb" else "client"


def load_restore_pools() -> list[ConfigRestorePool]:
    from .tools.restore_service import RESTORE_POOLS

    return RESTORE_POOLS


REGISTRATION = ScriptRegistration(
    config_type=MaaFWConfig,
    run_types=(MaaFWConfig,),
    manager_factory=build_manager,
    create_config_handler=partial(build_config_handler, MaaFWConfig, owner=MAAFW_OWNER),
    load_restore_pools=load_restore_pools,
    config_priority=5,
    restore_priority=9,
)
