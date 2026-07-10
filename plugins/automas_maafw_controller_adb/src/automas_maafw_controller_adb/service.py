from __future__ import annotations

from typing import Any


class MaaFWAdbControllerService:
    """maafw.controller.adb service."""

    key = "adb"
    display_name = "ADB"
    controller_types = ["Adb"]

    def get_provider_definition(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "displayName": self.display_name,
            "controllerTypes": list(self.controller_types),
            "capabilities": [
                "device_spec",
                "emulator_service_consumption",
            ],
        }

    def build_device_spec(
        self,
        *,
        adb_path: str | None = None,
        address: str | None = None,
        screencap_methods: int = 0,
        input_methods: int = 0,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "type": "Adb",
            "adbPath": adb_path,
            "address": address,
            "screencapMethods": screencap_methods,
            "inputMethods": input_methods,
            "config": dict(config or {}),
        }
