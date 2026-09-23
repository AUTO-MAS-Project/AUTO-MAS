#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

from .game_launch import MSSGameSession
from .instance_config import (
    EXE_NAME,
    INTERFACE_NAME,
    LOG_DIR_NAME,
    MAS_INSTANCE_ID,
    MAS_INSTANCE_NAME,
    latest_log_file,
    read_app_settings,
    read_instance_config,
    register_mas_instance,
    resolve_active_instance_id,
    resolve_instance_dir,
    resolve_instance_id,
    resolve_instance_path,
    resolve_temp_dir,
    write_instance_config,
)
from .orchestrate import (
    ENTRY_ACTIVITY,
    ENTRY_CLIMB,
    ENTRY_TRIBULATION,
    MSSPlanResult,
    MSSRunPlan,
    apply_run_plan,
    current_week_marker,
    should_run_climb,
)

__all__ = [
    "ENTRY_ACTIVITY",
    "ENTRY_CLIMB",
    "ENTRY_TRIBULATION",
    "EXE_NAME",
    "INTERFACE_NAME",
    "LOG_DIR_NAME",
    "MAS_INSTANCE_ID",
    "MAS_INSTANCE_NAME",
    "MSSGameSession",
    "MSSPlanResult",
    "MSSRunPlan",
    "apply_run_plan",
    "current_week_marker",
    "latest_log_file",
    "read_app_settings",
    "read_instance_config",
    "register_mas_instance",
    "resolve_active_instance_id",
    "resolve_instance_dir",
    "resolve_instance_id",
    "resolve_instance_path",
    "resolve_temp_dir",
    "should_run_climb",
    "write_instance_config",
]
