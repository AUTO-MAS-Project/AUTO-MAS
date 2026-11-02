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

"""Okww 的运行、配置和恢复接入声明。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.config import OkwwConfig
from app.models.script_contracts import ScriptConfigHandler
from app.task.registration import ManagerBuildContext, ScriptRegistration

if TYPE_CHECKING:
    from app.models.task import ScriptItem, TaskExecuteBase
    from app.utils.common.config.restore import ConfigRestorePool


def build_manager(
    script_item: ScriptItem, context: ManagerBuildContext
) -> TaskExecuteBase:
    from .manager import OkwwManager

    return OkwwManager(script_item)


def build_config_handler() -> ScriptConfigHandler:
    from app.models.config import OkwwUserConfig
    from app.task.Okww.tools.config_dir import import_config as import_okww_config
    from app.task.Okww.tools.config_dir import initialize_user as initialize_okww_user

    return ScriptConfigHandler(
        user_config_class=OkwwUserConfig,
        initialize_user=initialize_okww_user,
        import_config=import_okww_config,
    )


def load_restore_pools() -> list[ConfigRestorePool]:
    from .tools.restore_service import RESTORE_POOLS

    return RESTORE_POOLS


REGISTRATION = ScriptRegistration(
    config_type=OkwwConfig,
    run_types=(OkwwConfig,),
    manager_factory=build_manager,
    create_config_handler=build_config_handler,
    load_restore_pools=load_restore_pools,
    config_priority=6,
    restore_priority=2,
)
