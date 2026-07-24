from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter


@dataclass(frozen=True)
class SystemPluginSpec:
    plugin_name: str
    distribution_name: str
    package_name: str
    source_dir: Path
    default_instance_name: str
    visible: bool = True


SYSTEM_PLUGIN_SPECS: dict[str, SystemPluginSpec] = {
    "auto_mas_core": SystemPluginSpec(
        plugin_name="auto_mas_core",
        distribution_name="auto-mas-core",
        package_name="auto-mas-core",
        source_dir=Path.cwd() / "plugins" / "auto_mas_core",
        default_instance_name="AUTO-MAS Core",
    ),
    "browser": SystemPluginSpec(
        plugin_name="browser",
        distribution_name="automas-plugin-browser",
        package_name="automas-plugin-browser",
        source_dir=Path.cwd() / "plugins" / "browser",
        default_instance_name="浏览器能力",
    ),
    "emulator": SystemPluginSpec(
        plugin_name="emulator",
        distribution_name="automas-plugin-emulator",
        package_name="automas-plugin-emulator",
        source_dir=Path.cwd() / "plugins" / "emulator",
        default_instance_name="模拟器管理",
    ),
}

SYSTEM_PLUGIN_PACKAGES = {
    spec.package_name.lower().replace("-", "_")
    for spec in SYSTEM_PLUGIN_SPECS.values()
}


def normalize_package_name(name: str) -> str:
    return str(name or "").strip().lower().replace("-", "_")


def get_system_plugin_spec(plugin_name: str) -> SystemPluginSpec | None:
    return SYSTEM_PLUGIN_SPECS.get(str(plugin_name or "").strip())


def is_system_plugin(plugin_name: str) -> bool:
    return get_system_plugin_spec(plugin_name) is not None


def is_system_plugin_package(package_name: str) -> bool:
    return normalize_package_name(package_name) in SYSTEM_PLUGIN_PACKAGES


def ensure_system_plugin_source_on_path() -> None:
    for spec in SYSTEM_PLUGIN_SPECS.values():
        src_dir = spec.source_dir / "src"
        if src_dir.exists() and str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))


def get_system_plugin_default_instances() -> dict[str, dict[str, Any]]:
    return {
        name: {
            "id": f"{name}:system",
            "name": spec.default_instance_name,
            "enabled": True,
            "config": {},
            "system": True,
            "locked": True,
        }
        for name, spec in SYSTEM_PLUGIN_SPECS.items()
    }


def get_core_plugin_routers() -> list[APIRouter]:
    ensure_system_plugin_source_on_path()
    from auto_mas_core.routers import get_routers

    return list(get_routers())
