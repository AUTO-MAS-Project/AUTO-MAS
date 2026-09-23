from __future__ import annotations

from .apply import (
    UpdateApplyError,
    UpdatePostValidateRejected,
    UpdateProjectLockBusy,
    project_state_dir_for,
)
from .precheck_memo import (
    classify_precheck_failure,
    clear_runtime_precheck,
    precheck_memo_path,
    read_runtime_precheck,
    write_runtime_precheck,
)
from .updater import (
    MaaFWProjectUpdateCandidate,
    MaaFWProjectUpdateDiscovery,
    MaaFWProjectUpdateError,
    MaaFWProjectUpdateResult,
    apply_maafw_project_update,
    detect_maafw_project_shell_hint,
    discover_maafw_project_update,
    update_maafw_project_if_needed,
)

__all__ = [
    "MaaFWProjectUpdateCandidate",
    "MaaFWProjectUpdateDiscovery",
    "MaaFWProjectUpdateError",
    "MaaFWProjectUpdateResult",
    "UpdateApplyError",
    "UpdatePostValidateRejected",
    "UpdateProjectLockBusy",
    "apply_maafw_project_update",
    "classify_precheck_failure",
    "clear_runtime_precheck",
    "detect_maafw_project_shell_hint",
    "discover_maafw_project_update",
    "precheck_memo_path",
    "project_state_dir_for",
    "read_runtime_precheck",
    "update_maafw_project_if_needed",
    "write_runtime_precheck",
]
