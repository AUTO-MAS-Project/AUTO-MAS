#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
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


from .backup_archive import (
    archive_mas_backup,
    archive_mas_runtime_backup,
    archive_native_backup,
    build_native_preview,
    build_overlay_preview,
    get_mas_backup_dir,
    get_native_backup_dir,
    group_overlay,
    list_mas_backups,
    list_native_backups,
    mas_backup_root,
    mas_config_dir,
    read_overlay_sidecar,
    read_overlay_values,
    restore_mas_backup,
    restore_native_backup,
)
from .config import (
    SrcConfigSnapshotState,
    has_committed_src_user_config_transaction,
    is_src_config_available,
    promote_src_config_update,
    read_src_config_snapshot_state,
    read_src_installation_id,
    recover_interrupted_src_config_swap,
    recover_src_user_config,
    save_src_user_config,
    stage_src_config_update,
    validate_src_installation,
    write_src_config_snapshot_state,
)
from .login import login
from .notify import push_notification
from .poor_yaml import poor_yaml_read, poor_yaml_write
from .process import (
    SrcProcessState,
    kill_src_processes,
    kill_src_webui_process,
    read_src_process_state,
    read_src_webui_port,
    validate_src_cleanup_paths,
    write_src_process_state,
)

__all__ = [
    "kill_src_processes",
    "kill_src_webui_process",
    "read_src_process_state",
    "read_src_webui_port",
    "SrcProcessState",
    "validate_src_cleanup_paths",
    "write_src_process_state",
    "login",
    "push_notification",
    "poor_yaml_read",
    "poor_yaml_write",
    "has_committed_src_user_config_transaction",
    "is_src_config_available",
    "read_src_installation_id",
    "read_src_config_snapshot_state",
    "recover_interrupted_src_config_swap",
    "recover_src_user_config",
    "save_src_user_config",
    "promote_src_config_update",
    "stage_src_config_update",
    "SrcConfigSnapshotState",
    "validate_src_installation",
    "write_src_config_snapshot_state",
    "archive_mas_backup",
    "archive_mas_runtime_backup",
    "archive_native_backup",
    "build_native_preview",
    "build_overlay_preview",
    "get_mas_backup_dir",
    "get_native_backup_dir",
    "group_overlay",
    "list_mas_backups",
    "list_native_backups",
    "mas_backup_root",
    "mas_config_dir",
    "read_overlay_sidecar",
    "read_overlay_values",
    "restore_mas_backup",
    "restore_native_backup",
]
