"""Compatibility access to the emulator service.

The upstream emulator plugin is optional and is not present in every AUTO-MAS
distribution.  The host still owns the legacy emulator configuration and
runtime implementation, so keep that implementation as a deterministic
fallback instead of making the emulator page permanently unavailable.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any


class LegacyEmulatorService:
    """Adapter exposing the retained host emulator implementation as a service."""

    async def get_config(self, emulator_id: str | None):
        from app.core import Config

        return await Config.get_emulator(emulator_id)

    async def add(self):
        from app.core import Config

        return await Config.add_emulator()

    async def update(self, emulator_id: str, data: dict[str, dict[str, Any]]) -> None:
        from app.core import Config

        await Config.update_emulator(emulator_id, data)

    async def delete(self, emulator_id: str) -> None:
        from app.core import Config

        await Config.del_emulator(emulator_id)

    async def reorder(self, index_list: list[str]) -> None:
        from app.core import Config

        await Config.reorder_emulator(index_list)

    async def operate(self, operate: str, emulator_id: str, index: str) -> str:
        from app.core import EmulatorManager

        return await EmulatorManager.operate_emulator(operate, emulator_id, index)

    async def status(self, emulator_id: str | None = None):
        from app.core import EmulatorManager

        return await EmulatorManager.get_status(emulator_id)

    async def search_installed(self) -> list[dict[str, str]]:
        from app.utils import search_all_emulators

        # Registry enumeration is synchronous and can be slow on damaged
        # uninstall entries.  Do not block the FastAPI event loop.
        return await asyncio.to_thread(search_all_emulators)

    async def list_options(self):
        from app.core import Config

        return await Config.get_emulator_combox()

    async def list_device_options(self, emulator_id: str):
        from app.core import Config

        return await Config.get_emulator_devices_combox(emulator_id)

    async def get_instance(self, emulator_id: str):
        from app.core import EmulatorManager

        return await EmulatorManager.get_emulator_instance(emulator_id)

    async def resolve_options_provider(
        self,
        *,
        options_provider: dict[str, Any],
        config_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        source = str(options_provider.get("source") or "").strip()
        if source == "emulator_options":
            return await self.list_options()
        if source != "emulator_device_options":
            return []

        emulator_id = _resolve_emulator_id(options_provider, config_data)
        if not emulator_id or emulator_id == "-":
            return []
        return await self.list_device_options(emulator_id)


_legacy_emulator_service = LegacyEmulatorService()


def get_emulator_service() -> Any:
    """Return the installed emulator plugin service or the host fallback."""

    try:
        from app.plugins.manager import PluginManager

        service = PluginManager.service.get("emulator")
    except Exception:
        service = None
    return service if service is not None else _legacy_emulator_service


def _resolve_emulator_id(
    options_provider: Mapping[str, Any],
    config_data: Mapping[str, Any],
) -> str:
    for key in (
        "emulator_id",
        "emulatorId",
        "emulator_id_path",
        "depends_on",
        "related_field",
        "source_field",
    ):
        raw = options_provider.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        value = _read_path(config_data, raw)
        if value is not None:
            return str(value).strip()

    emulator_group = config_data.get("Emulator")
    if isinstance(emulator_group, Mapping):
        value = emulator_group.get("Id") or emulator_group.get("id")
        if value is not None:
            return str(value).strip()

    for key in ("EmulatorId", "emulatorId", "emulator_id"):
        value = _find_nested_value(config_data, key)
        if value is not None:
            return str(value).strip()
    return ""


def _read_path(data: Mapping[str, Any], raw_path: str) -> Any:
    current: Any = data
    for part in raw_path.replace("[", ".").replace("]", "").split("."):
        key = part.strip()
        if not key:
            continue
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _find_nested_value(data: Mapping[str, Any], target_key: str) -> Any:
    for key, value in data.items():
        if str(key) == target_key:
            return value
        if isinstance(value, Mapping):
            found = _find_nested_value(value, target_key)
            if found is not None:
                return found
    return None


__all__ = ["LegacyEmulatorService", "get_emulator_service"]
