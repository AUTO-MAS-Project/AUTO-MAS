from __future__ import annotations

from pathlib import Path
from typing import Any

from .loader import (
    MaaFWInterfaceLoadError,
    load_interface_model_cached,
    rescan_scan_select_option,
)
from .models import MaaFWInterface
from .preview import (
    MaaFWInterfacePreviewData,
    MaaFWInterfaceValidationReport,
    build_interface_preview_data,
)
from .task_config import (
    MaaFWTaskPresetSnapshot,
    build_interface_preset_snapshot,
    normalize_snapshot,
    normalize_task_execution_payload,
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

    def build_default_snapshot(
        self,
        interface: MaaFWInterface | dict[str, Any],
        *,
        preset: str | None = None,
    ) -> MaaFWTaskPresetSnapshot:
        interface_model = self._coerce_interface(interface)
        preset_model = None
        if preset is not None:
            preset_model = next(
                (item for item in interface_model.preset if item.name == preset), None
            )
            if preset_model is None:
                raise MaaFWInterfaceLoadError(f"preset not found: {preset}")
        elif interface_model.preset:
            preset_model = interface_model.preset[0]

        if preset_model is None:
            return normalize_snapshot(
                {
                    "taskOrder": [task.name for task in interface_model.task],
                    "taskChecked": {
                        task.name: bool(task.default_check)
                        for task in interface_model.task
                    },
                    "taskOptions": {},
                },
                interface_model,
            )

        return normalize_snapshot(
            build_interface_preset_snapshot(interface_model, preset_model),
            interface_model,
        )

    def normalize_snapshot(
        self,
        interface: MaaFWInterface | dict[str, Any],
        snapshot: MaaFWTaskPresetSnapshot | dict[str, Any] | None,
    ) -> MaaFWTaskPresetSnapshot:
        return normalize_snapshot(snapshot, self._coerce_interface(interface))

    def normalize_execution_payload(
        self,
        interface: MaaFWInterface | dict[str, Any],
        tasks: Any,
        options: Any,
        *,
        controller: str | None = None,
        resource: str | None = None,
    ) -> tuple[list[str], dict[str, dict[str, Any]]]:
        return normalize_task_execution_payload(
            tasks,
            options,
            self._coerce_interface(interface),
            controller_name=controller,
            resource_name=resource,
        )

    def rescan_option(self, path: str | Path, option_name: str) -> list[dict[str, str]]:
        root_path = Path(path).resolve()
        interface = self.load(root_path, force_reload=True)
        return rescan_scan_select_option(interface, option_name, root_path)

    @staticmethod
    def _coerce_interface(interface: MaaFWInterface | dict[str, Any]) -> MaaFWInterface:
        if isinstance(interface, MaaFWInterface):
            return interface
        if hasattr(interface, "model_dump"):
            return MaaFWInterface.model_validate(
                interface.model_dump(mode="json", by_alias=True)
            )
        return MaaFWInterface.model_validate(interface)
