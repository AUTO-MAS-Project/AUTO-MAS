from __future__ import annotations

from .service import MaaFWProjectUpdateService
from .apply import UpdateApplyError, recover_update_operation
from .state import (
    cancel_update,
    discard_update_artifact,
    list_recovery_operations,
    request_update_pause,
    resume_update,
    UpdatePlanStore,
)
from .transport import DownloadCancelled, DownloadPaused
from .updater import (
    DOWNLOAD_MAX_BYTES,
    MaaFWDownloadedProjectPackage,
    MaaFWProjectUpdateCandidate,
    MaaFWProjectUpdateDiscovery,
    MaaFWProjectUpdateError,
    MaaFWProjectUpdateResult,
    MaaFWUpdateProviderInfo,
    apply_maafw_project_update,
    check_maafw_project_update,
    detect_maafw_project_shell_hint,
    discover_maafw_project_update,
    persist_maafw_update_plan,
    download_maafw_project_package,
    list_update_providers,
    release_maafw_project_package,
    update_maafw_project_if_needed,
    resolve_maafw_update_plan_candidate,
)

__all__ = [
    "DOWNLOAD_MAX_BYTES",
    "MaaFWDownloadedProjectPackage",
    "MaaFWProjectUpdateCandidate",
    "MaaFWProjectUpdateDiscovery",
    "MaaFWProjectUpdateError",
    "MaaFWProjectUpdateResult",
    "MaaFWProjectUpdateService",
    "MaaFWUpdateProviderInfo",
    "DownloadCancelled",
    "DownloadPaused",
    "UpdateApplyError",
    "apply_maafw_project_update",
    "check_maafw_project_update",
    "detect_maafw_project_shell_hint",
    "discover_maafw_project_update",
    "persist_maafw_update_plan",
    "download_maafw_project_package",
    "list_update_providers",
    "release_maafw_project_package",
    "update_maafw_project_if_needed",
    "resolve_maafw_update_plan_candidate",
    "cancel_update",
    "discard_update_artifact",
    "list_recovery_operations",
    "recover_update_operation",
    "request_update_pause",
    "resume_update",
    "UpdatePlanStore",
]
