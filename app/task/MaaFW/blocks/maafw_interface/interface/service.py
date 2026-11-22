from __future__ import annotations

from pathlib import Path
from typing import Any

from .loader import (
    load_interface_model_cached,
)
from .models import MaaFWInterface
from .preview import (
    MaaFWInterfacePreviewData,
    MaaFWInterfaceValidationReport,
    build_interface_preview_data,
)
from .task_config import (
    MaaFWTaskPresetSnapshot,
    normalize_snapshot,
)


class MaaFWInterfaceService:
    """maafw.interface.v1 service."""

    def load(self, path: str | Path, *, force_reload: bool = False) -> MaaFWInterface:
        return load_interface_model_cached(path, force_reload=force_reload)

    def preview(
        self,
        path: str | Path,
        *,
        force_reload: bool = False,
    ) -> MaaFWInterfacePreviewData:
        root_path = Path(path).resolve()
        interface = self.load(root_path, force_reload=force_reload)
        return build_interface_preview_data(root_path, interface)

    def validate(
        self, interface: MaaFWInterface | dict[str, Any]
    ) -> MaaFWInterfaceValidationReport:
        try:
            self._coerce_interface(interface)
        except Exception as exc:
            return MaaFWInterfaceValidationReport(ok=False, message=str(exc))
        return MaaFWInterfaceValidationReport(ok=True)

    def normalize_snapshot(
        self,
        interface: MaaFWInterface | dict[str, Any],
        snapshot: MaaFWTaskPresetSnapshot | dict[str, Any] | None,
    ) -> MaaFWTaskPresetSnapshot:
        return normalize_snapshot(snapshot, self._coerce_interface(interface))

    @staticmethod
    def _coerce_interface(interface: MaaFWInterface | dict[str, Any]) -> MaaFWInterface:
        if isinstance(interface, MaaFWInterface):
            return interface
        if hasattr(interface, "model_dump"):
            return MaaFWInterface.model_validate(
                interface.model_dump(mode="json", by_alias=True)
            )
        return MaaFWInterface.model_validate(interface)
