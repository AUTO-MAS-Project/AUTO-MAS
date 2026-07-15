"""AUTO-MAS HSR plugin contracts and orchestration."""

from .contracts import (
    HSRAdapterDescriptor,
    HSRAdapterGroup,
    HSRCapabilitySnapshot,
    HSRController,
    HSRControllerSession,
    HSREngine,
    HSRNativeRunPlan,
    HSRNativeRunResult,
    HSRRunRequest,
    HSRRunResult,
    HSRStageCategory,
    HSRStageOption,
    HSRTaskCatalogProvider,
    HSRTaskDescriptor,
)
from .registry import HSRRegistryService

__all__ = [
    "HSRAdapterDescriptor",
    "HSRAdapterGroup",
    "HSRCapabilitySnapshot",
    "HSRController",
    "HSRControllerSession",
    "HSREngine",
    "HSRNativeRunPlan",
    "HSRNativeRunResult",
    "HSRRegistryService",
    "HSRRunRequest",
    "HSRRunResult",
    "HSRStageCategory",
    "HSRStageOption",
    "HSRTaskCatalogProvider",
    "HSRTaskDescriptor",
]
