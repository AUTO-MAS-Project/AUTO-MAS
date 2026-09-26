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

from .config_manager import (
    CONFIG_DIR_NAME,
    LOG_DIR_RELATIVE,
    SOFTWARE_CONFIG_RELATIVE,
    ManagedConfigBackup,
    apply_managed_config,
    latest_log_file,
    list_config_names,
    read_json,
    resolve_config_name,
    resolve_log_time_range,
    resolve_user_config_path,
    restore_managed_config,
)
from .notify import push_notification
from .push_log import BAAH_PUSH_RULES, baah_resolve

__all__ = [
    "BAAH_PUSH_RULES",
    "CONFIG_DIR_NAME",
    "LOG_DIR_RELATIVE",
    "SOFTWARE_CONFIG_RELATIVE",
    "ManagedConfigBackup",
    "apply_managed_config",
    "baah_resolve",
    "latest_log_file",
    "list_config_names",
    "push_notification",
    "read_json",
    "resolve_config_name",
    "resolve_log_time_range",
    "resolve_user_config_path",
    "restore_managed_config",
]
