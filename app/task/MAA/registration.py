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

"""Maa 的运行、配置和恢复接入声明。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.config import MaaConfig
from app.models.script_contracts import ScriptConfigHandler, ScriptEmulatorBinding
from app.task.registration import ScriptRegistration

if TYPE_CHECKING:
    from app.models.task import ScriptItem, TaskExecuteBase
    from app.utils.common.config.restore import ConfigRestorePool


def build_manager(script_item: ScriptItem) -> TaskExecuteBase:
    from .manager import MaaManager

    return MaaManager(script_item)


def build_config_handler() -> ScriptConfigHandler:
    from app.models.config import MaaUserConfig
    from app.task.MAA.user_update import prepare_user_update as prepare_maa_user_update
    from app.task.MAA.user_update import resolve_user_config_dir

    return ScriptConfigHandler(
        user_config_class=MaaUserConfig,
        user_config_directory=resolve_user_config_dir,
        prepare_user_update=prepare_maa_user_update,
        emulator_binding=ScriptEmulatorBinding(
            group="Emulator", id_field="Id", index_field="Index"
        ),
        supports_mod_avd=True,
    )


def load_restore_pools() -> list[ConfigRestorePool]:
    from .tools.restore_service import RESTORE_POOLS

    return RESTORE_POOLS


REGISTRATION = ScriptRegistration(
    config_type=MaaConfig,
    run_types=(MaaConfig,),
    manager_factory=build_manager,
    create_config_handler=build_config_handler,
    load_restore_pools=load_restore_pools,
    config_priority=2,
    restore_priority=3,
)
