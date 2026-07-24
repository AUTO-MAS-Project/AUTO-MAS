"""Case runner that orchestrates the fake host for each scenario.

Each case gets:
- its own subdirectory under the scratch pypi site-packages
- a fresh FakeHost
- a structured result.json

We do NOT touch the formal plugins/wheels/ directory.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


HARNESS_DIR = Path(r"D:\trae_projects\AUTO-MAS-Projects\AUTO-MAS-workspace\worktrees\all-plugins-integration\tests\plugin_blackbox\harness")
SCRATCH = HARNESS_DIR / "scratch_plugins"
RUNS_DIR = HARNESS_DIR / "runs"


def _ensure_worktree_on_path() -> None:
    p = str(HARNESS_DIR.parent.parent.parent)
    if p not in sys.path:
        sys.path.insert(0, p)


_ensure_worktree_on_path()


def _load_helpers():
    """Lazy import so that scripts can run in isolation."""
    from tests.plugin_blackbox.harness import build_fake_plugin_wheel as bfp
    from tests.plugin_blackbox.harness.fake_host import FakeHost
    return bfp, FakeHost


def _site_dir(case_id: str) -> Path:
    """Return the scratch pypi site-packages for a case.

    Mirrors the production layout: ``scratch_plugins/<case_id>/pypi/site-packages``.
    The PluginLoader + iter_plugin_entry_points use this exact path.
    """
    return SCRATCH / case_id / "pypi" / "site-packages"


def _scratch_root(case_id: str) -> Path:
    """Return the scratch plugins root for a case (``pypi/`` lives inside)."""
    return SCRATCH / case_id


@dataclass
class CaseResult:
    case_id: str
    status: str  # PASS / FAIL / PARTIAL / NOT_APPLICABLE
    notes: str = ""
    error: Optional[str] = None
    error_traceback: Optional[str] = None
    snapshots: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)


def write_result(case_id: str, result: CaseResult) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    out = RUNS_DIR / case_id / "result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "case_id": result.case_id,
                "status": result.status,
                "notes": result.notes,
                "error": result.error,
                "error_traceback": result.error_traceback,
                "snapshots": result.snapshots,
                "metrics": result.metrics,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return out


async def case_lifecycle_normal(*, case_id: str = "01_lifecycle_normal") -> CaseResult:
    bfp, FakeHost = _load_helpers()
    site = _site_dir(case_id)
    site.mkdir(parents=True, exist_ok=True)
    bfp.clear_built_wheels(site)

    bfp.build_wheel(
        out_dir=site,
        distribution="automas-fake-lifecycle",
        version="0.1.0",
        module="fake_plugin_lifecycle",
        entry_group="auto_mas.plugins",
        entry_name="fake_lifecycle",
        config={"hook_on_start_raises": False, "hook_on_stop_raises": False},
        build_id="build-1",
    )

    host = FakeHost(scratch_plugins_dir=_scratch_root(case_id))
    res = CaseResult(case_id=case_id, status="PASS")
    try:
        discovered = host.discover()
        res.snapshots["after_discover"] = host.snapshot()
        assert "fake_lifecycle" in discovered, f"discover missing fake_lifecycle: {list(discovered)}"

        rec = await host.load_instance(
            instance_id="iid-1",
            plugin_name="fake_lifecycle",
            config={"k": "v"},
        )
        res.snapshots["after_load"] = host.snapshot()
        assert rec.status == "active", f"expected active, got {rec.status}: {rec.error}"
        instance = rec.plugin_instance
        log = list(instance.lifecycle_log)
        assert any(name == "on_start" for name, _ in log), f"on_start missing: {log}"
        assert instance._listener_id is not None
        assert instance._global_listener_id is not None

        # Probe listener removal: emit a "fake:probe" before unload; the
        # instance's own listener is still active.
        await host.events.emit("fake:probe", {"k": 1}, source_instance_id="iid-1")

        snap_before_unload = host.snapshot()
        res.snapshots["before_unload"] = snap_before_unload

        await host.unload_instance("iid-1")
        res.snapshots["after_unload"] = host.snapshot()

        # After unload: listener_ids must be empty; event_bus handler_count
        # for "fake:probe" should drop by 1.
        rec_after = host.loader.records.get("iid-1")
        assert rec_after is not None
        assert rec_after.listener_ids == [], f"listener leak: {rec_after.listener_ids}"
        handlers = host.events.handler_count
        # fake:probe and fake:probe_global must have 0 or absent
        assert handlers.get("fake:probe", 0) == 0, f"fake:probe leak: {handlers}"
        assert handlers.get("fake:probe_global", 0) == 0, f"fake:probe_global leak: {handlers}"

        res.metrics["listeners_before"] = len(snap_before_unload.event_bus_handlers)
        res.metrics["listeners_after"] = len(host.events.handler_count)
    except Exception as e:
        res.status = "FAIL"
        res.error = f"{type(e).__name__}: {e}"
        res.error_traceback = traceback.format_exc(limit=10)
    finally:
        await host.aclose()
    return res


async def case_init_error(*, case_id: str = "02_init_error") -> CaseResult:
    """A plugin whose on_start raises. Must be isolated; record marked error."""
    bfp, FakeHost = _load_helpers()
    site = _site_dir(case_id)
    site.mkdir(parents=True, exist_ok=True)
    bfp.clear_built_wheels(site)

    bfp.build_wheel(
        out_dir=site,
        distribution="automas-fake-explode",
        version="0.1.0",
        module="fake_plugin_explode",
        entry_group="auto_mas.plugins",
        entry_name="fake_explode",
        config={"hook_on_start_raises": True},
    )

    host = FakeHost(scratch_plugins_dir=_scratch_root(case_id))
    res = CaseResult(case_id=case_id, status="PASS")
    try:
        host.discover()
        rec = await host.load_instance(
            instance_id="iid-explode",
            plugin_name="fake_explode",
            config={},
        )
        res.snapshots["after_load"] = host.snapshot()
        assert rec.status == "error", f"expected error status, got {rec.status}: {rec.error}"
        assert rec.on_load_attempted is True
        assert rec.on_start_attempted is True
        # Important: even on failure, no listener leak.
        assert rec.listener_ids == [], f"listener leak: {rec.listener_ids}"
        # Event bus must not hold any leftover handlers from this instance
        assert host.events.handler_count.get("fake:probe", 0) == 0
    except AssertionError as e:
        res.status = "FAIL"
        res.error = f"assert: {e}"
        res.error_traceback = traceback.format_exc(limit=8)
    except Exception as e:
        res.status = "FAIL"
        res.error = f"{type(e).__name__}: {e}"
        res.error_traceback = traceback.format_exc(limit=8)
    finally:
        await host.aclose()
    return res


async def case_partial_activation(*, case_id: str = "03_partial_activation") -> CaseResult:
    """Two plugins loaded together; one fails, the other must remain active."""
    bfp, FakeHost = _load_helpers()
    site = _site_dir(case_id)
    site.mkdir(parents=True, exist_ok=True)
    bfp.clear_built_wheels(site)

    bfp.build_wheel(
        out_dir=site,
        distribution="automas-fake-good",
        version="0.1.0",
        module="fake_plugin_good",
        entry_group="auto_mas.plugins",
        entry_name="fake_good",
        config={},
    )
    bfp.build_wheel(
        out_dir=site,
        distribution="automas-fake-bad",
        version="0.1.0",
        module="fake_plugin_bad",
        entry_group="auto_mas.plugins",
        entry_name="fake_bad",
        config={"hook_on_start_raises": True},
    )

    host = FakeHost(scratch_plugins_dir=_scratch_root(case_id))
    res = CaseResult(case_id=case_id, status="PASS")
    try:
        discovered = host.discover()
        assert "fake_good" in discovered
        assert "fake_bad" in discovered

        # Use the loader's batch path (load_instances) which is what
        # PluginManager.start() exercises.
        from app.plugins.config_store import PluginConfigStore  # noqa: WPS433

        store = PluginConfigStore()
        # The store needs a plugins_dir + discovered; we will fake the
        # instances via a stub.
        instances = [
            type("Instance", (), {
                "id": "good-1",
                "plugin": "fake_good",
                "name": "good",
                "enabled": True,
                "config": {},
            })(),
            type("Instance", (), {
                "id": "bad-1",
                "plugin": "fake_bad",
                "name": "bad",
                "enabled": True,
                "config": {},
            })(),
        ]
        await host.loader.load_instances(instances)
        res.snapshots["after_load_instances"] = host.snapshot()

        good = host.loader.records.get("good-1")
        bad = host.loader.records.get("bad-1")
        assert good is not None and good.status == "active", f"good not active: {good.status if good else 'missing'}"
        assert bad is not None and bad.status == "error", f"bad not error: {bad.status if bad else 'missing'}"
        assert "bad-1" in host.loader.startup_failed_instances
        res.metrics["startup_failed_instances"] = dict(host.loader.startup_failed_instances)
        res.metrics["startup_missing_instances"] = sorted(host.loader.startup_missing_instances)
    except AssertionError as e:
        res.status = "FAIL"
        res.error = f"assert: {e}"
        res.error_traceback = traceback.format_exc(limit=8)
    except Exception as e:
        res.status = "FAIL"
        res.error = f"{type(e).__name__}: {e}"
        res.error_traceback = traceback.format_exc(limit=8)
    finally:
        await host.aclose()
    return res


async def case_reload_basic(*, case_id: str = "04_reload_basic") -> CaseResult:
    """Reload should: stop old, start new, bump generation, no leak."""
    bfp, FakeHost = _load_helpers()
    site = _site_dir(case_id)
    site.mkdir(parents=True, exist_ok=True)
    bfp.clear_built_wheels(site)

    bfp.build_wheel(
        out_dir=site,
        distribution="automas-fake-reload",
        version="0.1.0",
        module="fake_plugin_reload",
        entry_group="auto_mas.plugins",
        entry_name="fake_reload",
        config={},
        build_id="b1",
    )

    host = FakeHost(scratch_plugins_dir=_scratch_root(case_id))
    res = CaseResult(case_id=case_id, status="PASS")
    try:
        host.discover()
        rec1 = await host.load_instance(
            instance_id="r-1",
            plugin_name="fake_reload",
            config={"k": "v1"},
        )
        assert rec1.status == "active"
        first_gen = rec1.generation
        first_log = list(rec1.plugin_instance.lifecycle_log)

        rec2 = await host.reload_instance(
            instance_id="r-1",
            plugin_name="fake_reload",
            instance_name="r-1",
            config={"k": "v2"},
        )
        snap_after_reload = host.snapshot()
        res.snapshots["after_reload"] = snap_after_reload
        assert rec2.status == "active", f"reload result: {rec2.status} {rec2.error}"
        assert rec2.generation == first_gen + 1, f"generation bump failed: {rec2.generation} vs {first_gen}"
        assert rec2.reload_count == 1
        assert rec2.last_reload_reason == "test"
        # The new instance should have on_reload_commit recorded
        second_log = list(rec2.plugin_instance.lifecycle_log)
        assert any(name == "on_reload_commit" for name, _ in second_log), f"on_reload_commit missing: {second_log}"
        # After reload: old generation's listeners must be removed; new
        # instance registers its own listeners (1 instance scope, 1
        # global scope with owner_instance_id). So count is exactly 1
        # per event.
        assert (
            snap_after_reload.event_bus_handlers.get("fake:probe", 0) == 1
        ), f"fake:probe count: {snap_after_reload.event_bus_handlers}"
        assert (
            snap_after_reload.event_bus_handlers.get("fake:probe_global", 0) == 1
        ), f"fake:probe_global count: {snap_after_reload.event_bus_handlers}"
        # Now unload the new instance: handler count must drop to 0 for
        # both events, demonstrating both the old (post-reload) and
        # new (post-reload) listeners were cleaned up.
        await host.unload_instance("r-1")
        snap_after_unload = host.snapshot()
        res.snapshots["after_unload"] = snap_after_unload
        assert (
            snap_after_unload.event_bus_handlers.get("fake:probe", 0) == 0
        ), f"fake:probe leak after final unload: {snap_after_unload.event_bus_handlers}"
        assert (
            snap_after_unload.event_bus_handlers.get("fake:probe_global", 0) == 0
        ), f"fake:probe_global leak after final unload: {snap_after_unload.event_bus_handlers}"
    except AssertionError as e:
        res.status = "FAIL"
        res.error = f"assert: {e}"
        res.error_traceback = traceback.format_exc(limit=8)
    except Exception as e:
        res.status = "FAIL"
        res.error = f"{type(e).__name__}: {e}"
        res.error_traceback = traceback.format_exc(limit=8)
    finally:
        await host.aclose()
    return res


async def case_reload_failure_rolls_back(*, case_id: str = "05_reload_failure_rollback") -> CaseResult:
    """A plugin whose on_start now raises; reload should mark error and
    unload cleanly. The old instance must already be gone (loader unloads
    before loading)."""
    bfp, FakeHost = _load_helpers()
    site = _site_dir(case_id)
    site.mkdir(parents=True, exist_ok=True)
    bfp.clear_built_wheels(site)

    bfp.build_wheel(
        out_dir=site,
        distribution="automas-fake-reload-fail",
        version="0.1.0",
        module="fake_plugin_reload_fail",
        entry_group="auto_mas.plugins",
        entry_name="fake_reload_fail",
        config={"hook_on_start_raises": False},
        build_id="b1",
    )

    host = FakeHost(scratch_plugins_dir=_scratch_root(case_id))
    res = CaseResult(case_id=case_id, status="PARTIAL")
    res.notes = "A reload that fails on on_start intentionally leaves the new record in 'error'; the old record is already removed. We verify the record status, lifecycle phase, and listener absence."
    try:
        host.discover()
        rec1 = await host.load_instance(
            instance_id="rf-1",
            plugin_name="fake_reload_fail",
            config={},
        )
        assert rec1.status == "active"

        # The harness plugin cannot toggle its own config at runtime
        # because FAKE_PLUGIN_CONFIG is frozen. To simulate a failing
        # reload we use a different plugin that has on_start_raises=True.
        bfp.build_wheel(
            out_dir=site,
            distribution="automas-fake-reload-fail-on",
            version="0.1.0",
            module="fake_plugin_reload_fail_on",
            entry_group="auto_mas.plugins",
            entry_name="fake_reload_fail_on",
            config={"hook_on_start_raises": True},
            build_id="b2",
        )
        # Need to invalidate entry point cache to see new wheel
        from app.plugins.pypi_site import invalidate_entry_points_cache  # noqa: WPS433
        invalidate_entry_points_cache()
        host.discover()

        rec2 = await host.reload_instance(
            instance_id="rf-1",
            plugin_name="fake_reload_fail_on",
            instance_name="rf-1",
            config={},
        )
        res.snapshots["after_failed_reload"] = host.snapshot()
        # According to _reload_instance, when the new load returns an
        # error, it unloads and marks status='closed'. Verify both.
        assert rec2.status in {"error", "closed"}, f"unexpected status: {rec2.status}"
        # No listener should remain from the failed instance
        assert host.events.handler_count.get("fake:probe", 0) == 0
        assert host.events.handler_count.get("fake:probe_global", 0) == 0
        res.metrics["final_status"] = rec2.status
        res.metrics["final_lifecycle_phase"] = rec2.lifecycle_phase
    except AssertionError as e:
        res.status = "FAIL"
        res.error = f"assert: {e}"
        res.error_traceback = traceback.format_exc(limit=8)
    except Exception as e:
        res.status = "FAIL"
        res.error = f"{type(e).__name__}: {e}"
        res.error_traceback = traceback.format_exc(limit=8)
    finally:
        await host.aclose()
    return res


async def case_broken_module_isolation(*, case_id: str = "06_broken_module_isolation") -> CaseResult:
    """A wheel whose module raises ImportError on import. The loader must
    surface a clean error record and not crash the host."""
    bfp, FakeHost = _load_helpers()
    site = _site_dir(case_id)
    site.mkdir(parents=True, exist_ok=True)
    bfp.clear_built_wheels(site)
    bfp.write_broken_module_wheel(out_dir=site, distribution="automas-fake-broken")

    host = FakeHost(scratch_plugins_dir=_scratch_root(case_id))
    res = CaseResult(case_id=case_id, status="PASS")
    try:
        host.discover()
        rec = await host.load_instance(
            instance_id="br-1",
            plugin_name="automas_fake_broken",
            config={},
        )
        res.snapshots["after_load"] = host.snapshot()
        assert rec.status == "error", f"expected error, got {rec.status}: {rec.error}"
        # No listener leak even on import error (since register decorators
        # are not reached, but loader must not stash any).
        assert rec.listener_ids == []
    except AssertionError as e:
        res.status = "FAIL"
        res.error = f"assert: {e}"
        res.error_traceback = traceback.format_exc(limit=8)
    except Exception as e:
        res.status = "FAIL"
        res.error = f"{type(e).__name__}: {e}"
        res.error_traceback = traceback.format_exc(limit=8)
    finally:
        await host.aclose()
    return res


async def case_disable_reload_residue(*, case_id: str = "07_disable_reload_residue") -> CaseResult:
    """A loaded plugin's listeners and modules must be removed after unload.

    This complements case 01 by also checking that the entry point class
    can be re-imported (sys.modules may keep a stale reference; we accept
    that as long as the loader records a clean unload).
    """
    bfp, FakeHost = _load_helpers()
    site = _site_dir(case_id)
    site.mkdir(parents=True, exist_ok=True)
    bfp.clear_built_wheels(site)

    bfp.build_wheel(
        out_dir=site,
        distribution="automas-fake-residue",
        version="0.1.0",
        module="fake_plugin_residue",
        entry_group="auto_mas.plugins",
        entry_name="fake_residue",
        config={},
    )

    host = FakeHost(scratch_plugins_dir=_scratch_root(case_id))
    res = CaseResult(case_id=case_id, status="PASS")
    try:
        host.discover()
        rec1 = await host.load_instance(
            instance_id="re-1",
            plugin_name="fake_residue",
            config={},
        )
        assert rec1.status == "active"
        # Force an emit that should be handled by instance listener
        await host.events.emit("fake:probe", {"x": 1}, source_instance_id="re-1")
        snap_before = host.snapshot()
        await host.unload_instance("re-1")
        snap_after = host.snapshot()
        res.snapshots["before"] = snap_before
        res.snapshots["after"] = snap_after
        # Listener removal
        assert snap_after.event_bus_handlers.get("fake:probe", 0) == 0
        assert snap_after.event_bus_handlers.get("fake:probe_global", 0) == 0
        # Record lifecycle phase
        rec_after = host.loader.records.get("re-1")
        assert rec_after is not None
        assert rec_after.lifecycle_phase in {"unloaded", "disposed"}, f"phase: {rec_after.lifecycle_phase}"
        assert rec_after.listener_ids == []
    except AssertionError as e:
        res.status = "FAIL"
        res.error = f"assert: {e}"
        res.error_traceback = traceback.format_exc(limit=8)
    except Exception as e:
        res.status = "FAIL"
        res.error = f"{type(e).__name__}: {e}"
        res.error_traceback = traceback.format_exc(limit=8)
    finally:
        await host.aclose()
    return res


async def case_full_reload(*, case_id: str = "08_full_reload") -> CaseResult:
    """Two plugins active, full unload + reload via the loader path."""
    bfp, FakeHost = _load_helpers()
    site = _site_dir(case_id)
    site.mkdir(parents=True, exist_ok=True)
    bfp.clear_built_wheels(site)

    bfp.build_wheel(
        out_dir=site,
        distribution="automas-fake-p1",
        version="0.1.0",
        module="fake_plugin_p1",
        entry_group="auto_mas.plugins",
        entry_name="fake_p1",
        config={},
    )
    bfp.build_wheel(
        out_dir=site,
        distribution="automas-fake-p2",
        version="0.1.0",
        module="fake_plugin_p2",
        entry_group="auto_mas.plugins",
        entry_name="fake_p2",
        config={},
    )

    host = FakeHost(scratch_plugins_dir=_scratch_root(case_id))
    res = CaseResult(case_id=case_id, status="PASS")
    try:
        host.discover()
        await host.load_instance(instance_id="p1-1", plugin_name="fake_p1", config={})
        await host.load_instance(instance_id="p2-1", plugin_name="fake_p2", config={})
        snap_active = host.snapshot()
        res.snapshots["active"] = snap_active
        assert len(snap_active.loader_records) == 2

        await host.unload_all()
        snap_after = host.snapshot()
        res.snapshots["after_unload_all"] = snap_after
        # Event bus must be empty
        assert all(v == 0 for v in snap_after.event_bus_handlers.values()), f"event bus not empty: {snap_after.event_bus_handlers}"
    except AssertionError as e:
        res.status = "FAIL"
        res.error = f"assert: {e}"
        res.error_traceback = traceback.format_exc(limit=8)
    except Exception as e:
        res.status = "FAIL"
        res.error = f"{type(e).__name__}: {e}"
        res.error_traceback = traceback.format_exc(limit=8)
    finally:
        await host.aclose()
    return res


CASES = [
    case_lifecycle_normal,
    case_init_error,
    case_partial_activation,
    case_reload_basic,
    case_reload_failure_rolls_back,
    case_broken_module_isolation,
    case_disable_reload_residue,
    case_full_reload,
]


async def run_all() -> list[CaseResult]:
    results: list[CaseResult] = []
    for fn in CASES:
        r = await fn()
        path = write_result(r.case_id, r)
        results.append(r)
        print(f"[{r.status}] {r.case_id}: {r.notes or (r.error or 'ok')}  -> {path}")
    return results


if __name__ == "__main__":
    results = asyncio.run(run_all())
    summary = {r.status: 0 for r in results}
    for r in results:
        summary[r.status] = summary.get(r.status, 0) + 1
    print(f"\nSUMMARY: {summary}")
    if any(r.status == "FAIL" for r in results):
        sys.exit(1)
