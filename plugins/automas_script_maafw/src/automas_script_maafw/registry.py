from __future__ import annotations

from typing import Any


class MaaFWRegistryService:
    """Registry for MaaFW controller providers and project packs."""

    def __init__(self) -> None:
        self._controller_providers: dict[str, dict[str, Any]] = {}
        self._project_packs: dict[str, dict[str, Any]] = {}

    def register_controller_provider(self, definition: Any) -> None:
        payload = _dump_definition(definition)
        key = str(payload.get("key") or "").strip()
        if not key:
            raise ValueError("MaaFW controller provider key cannot be empty")
        self._controller_providers[key] = payload

    def unregister_controller_provider(self, key: str) -> None:
        self._controller_providers.pop(str(key or "").strip(), None)

    def list_controller_providers(self) -> list[dict[str, Any]]:
        return list(self._controller_providers.values())

    def get_controller_provider(self, key: str) -> dict[str, Any] | None:
        return self._controller_providers.get(str(key or "").strip())

    def register_project_pack(self, definition: Any) -> None:
        payload = _dump_definition(definition)
        key = str(payload.get("key") or "").strip()
        if not key:
            raise ValueError("MaaFW project pack key cannot be empty")
        self._project_packs[key] = payload

    def unregister_project_pack(self, key: str) -> None:
        self._project_packs.pop(str(key or "").strip(), None)

    def list_project_packs(self) -> list[dict[str, Any]]:
        return list(self._project_packs.values())

    def get_project_pack(self, key: str) -> dict[str, Any] | None:
        return self._project_packs.get(str(key or "").strip())


def _dump_definition(definition: Any) -> dict[str, Any]:
    if hasattr(definition, "model_dump"):
        data = definition.model_dump(mode="json")
    elif isinstance(definition, dict):
        data = definition
    else:
        data = {
            name: getattr(definition, name)
            for name in dir(definition)
            if not name.startswith("_") and not callable(getattr(definition, name))
        }
    if not isinstance(data, dict):
        raise TypeError("MaaFW project pack definition must be a mapping")
    return dict(data)
