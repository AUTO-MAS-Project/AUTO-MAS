#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

from .instance_config import (
    APP_SETTINGS_NAME,
    DEFAULT_INSTANCE_ID,
    EXE_NAME,
    INSTANCE_DIR_RELATIVE,
    INTERFACE_NAME,
    LOG_DIR_NAME,
    apply_adb_device,
    apply_queue_to_config,
    build_default_option_items,
    build_task_ref,
    commit_instance_snapshot,
    discard_instance_snapshot,
    latest_log_file,
    mark_instance_config_injected,
    normalize_user_queue,
    read_instance_config,
    read_instance_template,
    recover_previous_instance_snapshot,
    resolve_instance_dir,
    resolve_instance_id,
    resolve_instance_path,
    restore_instance_snapshot,
    split_task_ref,
    write_instance_config,
)
from .task_loader import (
    MssTaskCatalog,
    interface_exists,
    load_task_catalog,
    load_task_catalog_or_error,
)

__all__ = [
    "APP_SETTINGS_NAME",
    "DEFAULT_INSTANCE_ID",
    "EXE_NAME",
    "INSTANCE_DIR_RELATIVE",
    "INTERFACE_NAME",
    "LOG_DIR_NAME",
    "MssTaskCatalog",
    "apply_adb_device",
    "apply_queue_to_config",
    "build_default_option_items",
    "build_task_ref",
    "commit_instance_snapshot",
    "discard_instance_snapshot",
    "interface_exists",
    "latest_log_file",
    "load_task_catalog",
    "load_task_catalog_or_error",
    "mark_instance_config_injected",
    "normalize_user_queue",
    "read_instance_config",
    "read_instance_template",
    "recover_previous_instance_snapshot",
    "resolve_instance_dir",
    "resolve_instance_id",
    "resolve_instance_path",
    "restore_instance_snapshot",
    "split_task_ref",
    "write_instance_config",
]
