"""Fake host harness for plugin lifecycle blackbox.

Goals
-----
- Wire up EventBus, ServiceRegistry, PluginLoader without the FastAPI
  process, without FastAPI app, without any GUI / Electron / frontend.
- Operate against a *scratch* plugins_dir (no shared state with the
  formal plugins/wheels/ directory). The formal wheelhouse is **never
  modified** by this harness.
- Provide hooks to: discover, load_instance, reload_instance, unload,
  and read back state from the loader / event_bus / records so callers
  can assert leak-free behaviour.

The harness lives in tests/plugin_blackbox/harness/. It must not import
from app.*; instead it reuses the plugin subsystem under test via the
loader / event_bus / manager modules. We do NOT touch main.py or the
real PluginManager singleton — we instantiate fresh components so that
the formal auto_mas runtime is not affected.

Usage
-----

    from tests.plugin_blackbox.harness.fake_host import FakeHost

    host = FakeHost(scratch_plugins_dir=Path(".../harness/scratch_plugins"))
    discovered = await host.discover()
    record = await host.load_instance(
        instance_id="demo",
        plugin_name="my_demo",
        config={},
    )
    snapshot = host.snapshot()  # JSON-serializable for evidence
    await host.unload_instance("demo")
    await host.aclose()
"""
from __future__ import annotations

import asyncio
import importlib
import importlib.metadata as importlib_metadata
import json
import sys
import time
import types
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

# Make the worktree importable. We use a copy of the live source — never
# edit it. We just want the same module objects to exercise real behavior.
WORKTREE = Path(r"D:\trae_projects\AUTO-MAS-Projects\AUTO-MAS-workspace\worktrees\all-plugins-integration")


def _ensure_worktree_on_path() -> None:
    p = str(WORKTREE)
    if p not in sys.path:
        sys.path.insert(0, p)


_ensure_worktree_on_path()


def _ensure_minimal_optional_dependencies() -> None:
    """Inject stubs for heavy optional dependencies so we can exercise
    the plugin loader subsystem without booting the full FastAPI host.

    We never modify the real `app.*` modules. We only fill sys.modules
    with sentinel modules when a third-party dependency is missing.
    """
    # websockets is required by app.utils.websocket at import time
    try:
        importlib.import_module("websockets")
    except Exception:
        ws_stub = types.ModuleType("websockets")
        ws_asyncio = types.ModuleType("websockets.asyncio")
        ws_asyncio_client = types.ModuleType("websockets.asyncio.client")
        ws_asyncio_client.connect = lambda *a, **kw: None
        ws_asyncio_client.ClientConnection = type("ClientConnection", (), {})
        ws_asyncio.client = ws_asyncio_client
        ws_stub.asyncio = ws_asyncio
        sys.modules["websockets"] = ws_stub
        sys.modules["websockets.asyncio"] = ws_asyncio
        sys.modules["websockets.asyncio.client"] = ws_asyncio_client

    # mcp is required by app.core ... do not stub unless needed; the
    # loader doesn't pull mcp.  Skip.


_ensure_minimal_optional_dependencies()


@dataclass
class Snapshot:
    """JSON-serializable snapshot of the fake host's runtime state."""

    at: float
    event_bus_handlers: Dict[str, int]
    loader_records: Dict[str, Dict[str, Any]]
    discovered_plugins: Dict[str, Dict[str, Any]]
    service_owners: Dict[str, list[str]]
    sys_modules_keys_sample: list[str]


class FakeHost:
    """In-memory fake host over the real plugin subsystem."""

    def __init__(
        self,
        scratch_plugins_dir: Path,
        *,
        host_id: str = "fake-host",
    ) -> None:
        self.scratch_plugins_dir = scratch_plugins_dir.resolve()
        self.scratch_plugins_dir.mkdir(parents=True, exist_ok=True)
        self.pypi_site = self.scratch_plugins_dir / "pypi" / "site-packages"
        self.pypi_site.mkdir(parents=True, exist_ok=True)
        self.host_id = host_id

        # Lazy import so that sys.path tweak above is in place.
        from app.plugins.event_bus import EventBus  # noqa: WPS433
        from app.plugins.loader import PluginLoader  # noqa: WPS433
        from app.plugins.service_registry import ServiceRegistry  # noqa: WPS433

        self.events = EventBus()
        self.service = ServiceRegistry()
        self.loader = PluginLoader(
            events=self.events,
            runtime={},
            plugins_dir=self.scratch_plugins_dir,
            service=self.service,
        )
        # Make sure the pypi site-packages is on sys.path; do not load host.
        from app.plugins.pypi_site import (  # noqa: WPS433
            ensure_pypi_site_packages_on_syspath,
            invalidate_entry_points_cache,
        )
        invalidate_entry_points_cache()
        ensure_pypi_site_packages_on_syspath(self.scratch_plugins_dir)

    @property
    def pypi_site_path(self) -> Path:
        return self.pypi_site

    def discover(self) -> Dict[str, Any]:
        return self.loader.discover()

    async def load_instance(
        self,
        *,
        instance_id: str,
        plugin_name: str,
        instance_name: str = "",
        config: Optional[Dict[str, Any]] = None,
        provides: Optional[set[str]] = None,
        needs: Optional[set[str]] = None,
        wants: Optional[set[str]] = None,
        clear_pypi_cache: bool = True,
    ) -> Any:
        rec = await self.loader.load_instance(
            instance_id=instance_id,
            plugin_name=plugin_name,
            instance_name=instance_name or instance_id,
            config=dict(config or {}),
            provides=provides,
            needs=needs,
            wants=wants,
            clear_pypi_cache=clear_pypi_cache,
        )
        return rec

    async def reload_instance(
        self,
        *,
        instance_id: str,
        plugin_name: str,
        instance_name: str = "",
        config: Optional[Dict[str, Any]] = None,
        reason: str = "test",
    ) -> Any:
        return await self.loader.reload_instance(
            instance_id=instance_id,
            plugin_name=plugin_name,
            instance_name=instance_name or instance_id,
            config=dict(config or {}),
            reason=reason,
        )

    async def unload_instance(self, instance_id: str, *, reason: str = "stop") -> None:
        await self.loader.unload_instance(instance_id, stop_reason=reason)

    async def unload_all(self) -> None:
        await self.loader.unload_all()
        self.events.clear()

    def snapshot(self) -> Snapshot:
        records = {}
        for iid, rec in self.loader.records.items():
            records[iid] = {
                "instance_id": rec.instance_id,
                "plugin_name": rec.plugin_name,
                "status": rec.status,
                "lifecycle_phase": rec.lifecycle_phase,
                "error": rec.error,
                "listener_ids": list(rec.listener_ids),
                "generation": rec.generation,
                "reload_count": rec.reload_count,
                "last_reload_reason": rec.last_reload_reason,
                "on_load_attempted": rec.on_load_attempted,
                "on_start_attempted": rec.on_start_attempted,
                "on_stop_completed": rec.on_stop_completed,
                "on_unload_completed": rec.on_unload_completed,
                "provides": sorted(rec.provides),
                "needs": sorted(rec.needs),
                "missing": sorted(rec.missing),
            }
        service_owners = {}
        for name in self.service.owners.__self__ if False else []:  # placeholder
            service_owners[name] = sorted(self.service.owners(name))
        discovered = {
            pname: {
                "source": ps.source,
                "distribution": ps.distribution,
                "version": ps.version,
                "system": ps.system,
                "locked": ps.locked,
            }
            for pname, ps in self.loader.discovered_plugins.items()
        }
        # Service owner map: enumerate known service names
        for name in sorted({name for rec in records.values() for name in rec["provides"]}):
            service_owners[name] = sorted(self.service.owners(name))
        return Snapshot(
            at=time.time(),
            event_bus_handlers=dict(self.events.handler_count),
            loader_records=records,
            discovered_plugins=discovered,
            service_owners=service_owners,
            sys_modules_keys_sample=sorted(
                k for k in sys.modules
                if k.startswith(("automas_", "auto_mas_core", "maaend_adapter",
                                 "ok_script_adapter", "okww_adapter", "mxu_import",
                                 "fake_plugin_"))
            ),
        )

    async def aclose(self) -> None:
        await self.unload_all()
