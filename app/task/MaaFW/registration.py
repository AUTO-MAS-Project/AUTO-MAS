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

"""MaaFW 的运行、配置和恢复接入声明。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.config import M9AConfig, MaaFWConfig, MSSConfig
from app.models.script_contracts import ScriptConfigHandler
from app.task.registration import ManagerBuildContext, ScriptRegistration

if TYPE_CHECKING:
    from app.models.task import ScriptItem, TaskExecuteBase
    from app.utils.common.config.restore import ConfigRestorePool


def build_manager(
    script_item: ScriptItem, context: ManagerBuildContext
) -> TaskExecuteBase:
    from .embedded_manager import MaaFWEmbeddedManager

    return MaaFWEmbeddedManager(script_item)


def build_config_handler() -> ScriptConfigHandler:
    from app.models.config import MaaFWUserConfig
    from app.task.MaaFW.tools.embedded.default_snapshot import (
        initialize_user as initialize_maafw_user,
    )
    from app.task.MaaFW.tools.embedded.default_snapshot import (
        prepare_user_read as prepare_maafw_user_read,
    )
    from app.task.MaaFW.tools.embedded.resources import (
        EMULATOR_BINDING as maafw_emulator_binding,
    )
    from app.task.MaaFW.tools.embedded.resources import (
        SUPPORTS_MOD_AVD as maafw_supports_mod_avd,
    )
    from app.task.MaaFW.tools.embedded.resources import (
        declare_task_resources as maafw_task_resources,
    )
    from app.task.MaaFW.tools.embedded.script_lifecycle import (
        after_script_removal as after_maafw_script_removal,
    )
    from app.task.MaaFW.tools.embedded.script_lifecycle import (
        clone_script as clone_maafw_script,
    )
    from app.task.MaaFW.tools.embedded.user_update import (
        prepare_user_update as prepare_maafw_user_update,
    )

    return ScriptConfigHandler(
        user_config_class=MaaFWUserConfig,
        clone_script=clone_maafw_script,
        after_script_removal=after_maafw_script_removal,
        prepare_user_update=prepare_maafw_user_update,
        prepare_user_read=prepare_maafw_user_read,
        initialize_user=initialize_maafw_user,
        task_resources=maafw_task_resources,
        emulator_binding=maafw_emulator_binding,
        supports_mod_avd=maafw_supports_mod_avd,
    )


def load_restore_pools() -> list[ConfigRestorePool]:
    from .tools.restore_service import RESTORE_POOLS

    return RESTORE_POOLS


REGISTRATION = ScriptRegistration(
    config_type=MaaFWConfig,
    run_types=(MaaFWConfig, M9AConfig, MSSConfig),
    manager_factory=build_manager,
    create_config_handler=build_config_handler,
    load_restore_pools=load_restore_pools,
    config_priority=5,
    restore_priority=9,
)
