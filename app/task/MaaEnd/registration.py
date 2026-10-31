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

"""MaaEnd 的运行、配置和恢复接入声明。"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from app.models.config import MaaEndConfig
from app.models.script_contracts import ScriptConfigHandler
from app.task.registration import ManagerBuildContext, ScriptRegistration

if TYPE_CHECKING:
    from app.models.task import ScriptItem, TaskExecuteBase
    from app.utils.common.config.restore import ConfigRestorePool

    from .api_service import MaaEndConfigService


def build_manager(
    script_item: ScriptItem, context: ManagerBuildContext
) -> TaskExecuteBase:
    from .manager import MaaEndManager

    return MaaEndManager(script_item)


def build_config_handler(*, maaend: MaaEndConfigService) -> ScriptConfigHandler:
    from app.models.config import MaaEndUserConfig
    from app.task.MaaEnd.resources import EMULATOR_BINDING as maaend_emulator_binding
    from app.task.MaaEnd.resources import (
        declare_task_resources as maaend_task_resources,
    )

    return ScriptConfigHandler(
        user_config_class=MaaEndUserConfig,
        initialize=maaend.initialize,
        validate_update=maaend.validate_update,
        import_config=maaend.import_config,
        task_resources=maaend_task_resources,
        emulator_binding=maaend_emulator_binding,
    )


def load_restore_pools() -> list[ConfigRestorePool]:
    from .tools.restore_service import RESTORE_POOLS

    return RESTORE_POOLS


def registration(*, maaend: MaaEndConfigService) -> ScriptRegistration:
    return ScriptRegistration(
        config_type=MaaEndConfig,
        run_types=(MaaEndConfig,),
        manager_factory=build_manager,
        create_config_handler=partial(build_config_handler, maaend=maaend),
        load_restore_pools=load_restore_pools,
        config_priority=0,
        restore_priority=4,
    )
