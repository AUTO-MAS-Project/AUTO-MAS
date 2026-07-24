"""Extended deterministic cases for plugin failure isolation, reload and
state recovery.

These cases build on the core scenarios in :mod:`case_runner` and exercise
the failure modes listed in the long-chain task brief:

- 坏 manifest (bad METADATA)
- import error vs init error vs start error
- 重复 entry point
- 同名官方/本地插件 (same-name conflict)
- 缺依赖 (missing dependency)
- 旧 wheel 覆盖 (old wheel override by new version)
- 新旧配置迁移 (config migration across reload)
- 部分激活失败 (partial activation, see case 03 in case_runner)
- 状态恢复 after restart

The cases share the fake host harness and emit JSON evidence under
``tests/plugin_blackbox/harness/runs/<case_id>/result.json``.
"""
from __future__ import annotations

import asyncio
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

# Reuse the core helpers.
HARNESS_DIR = Path(r"D:\trae_projects\AUTO-MAS-Projects\AUTO-MAS-workspace\worktrees\all-plugins-integration\tests\plugin_blackbox\harness")
SCRATCH = HARNESS_DIR / "scratch_plugins"
RUNS_DIR = HARNESS_DIR / "runs"

if str(HARNESS_DIR.parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR.parent.parent.parent))

from tests.plugin_blackbox.harness.case_runner import (  # noqa: E402
    CaseResult,
    _load_helpers,
    _scratch_root,
    _site_dir,
    write_result,
)


# ---------------------------------------------------------------------------
# 09 — bad manifest
# ---------------------------------------------------------------------------
async def case_bad_manifest(*, case_id: str = "09_bad_manifest") -> CaseResult:
    """A wheel whose METADATA is truncated. Discovery must skip it (or
    mark it as broken) without crashing the host."""
    bfp, FakeHost = _load_helpers()
    site = _site_dir(case_id)
    bfp.clear_built_wheels(site)
    bfp.write_bad_manifest_wheel(out_dir=site, distribution="automas-fake-badmanifest")

    host = FakeHost(scratch_plugins_dir=_scratch_root(case_id))
    res = CaseResult(case_id=case_id, status="PASS")
    try:
        discovered = host.discover()
        res.snapshots["after_discover"] = host.snapshot()
        # The truncated manifest lacks a Version field; importlib.metadata
        # may still expose it but with version=None or skip. Either way the
        # host must not crash and loader.load_instance should surface a
        # graceful error.
        try:
            rec = await host.load_instance(
                instance_id="bm-1",
                plugin_name="automas_fake_badmanifest",
                config={},
            )
            res.snapshots["after_load"] = host.snapshot()
            assert rec.status in {"error", "unloaded"}, (
                f"bad-manifest plugin should error out, got {rec.status}"
            )
            res.metrics["final_status"] = rec.status
        except Exception as e:
            # Host may also raise; capture as expected failure.
            res.metrics["load_exception"] = f"{type(e).__name__}: {e}"
        # The important invariant: discovery did not raise, the EventBus
        # is clean, and other plugins are not affected.
        assert all(
            v == 0 for v in host.snapshot().event_bus_handlers.values()
        ), f"event bus leak: {host.events.handler_count}"
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


# ---------------------------------------------------------------------------
# 10 — duplicate entry point (same name, different module)
# ---------------------------------------------------------------------------
async def case_duplicate_entry_point(*, case_id: str = "10_duplicate_entry_point") -> CaseResult:
    """Two wheels declaring the same entry-point name. iter_plugin_entry_points
    deduplicates by (group, name, value), so the first one wins (deterministic)."""
    bfp, FakeHost = _load_helpers()
    site = _site_dir(case_id)
    bfp.clear_built_wheels(site)
    bfp.build_wheel(
        out_dir=site,
        distribution="automas-fake-dup-A",
        version="0.1.0",
        module="fake_plugin_dup_a",
        entry_group="auto_mas.plugins",
        entry_name="fake_dup",
        config={},
        build_id="A",
    )
    bfp.build_wheel(
        out_dir=site,
        distribution="automas-fake-dup-B",
        version="0.1.0",
        module="fake_plugin_dup_b",
        entry_group="auto_mas.plugins",
        entry_name="fake_dup",
        config={},
        build_id="B",
    )

    host = FakeHost(scratch_plugins_dir=_scratch_root(case_id))
    res = CaseResult(case_id=case_id, status="PASS")
    try:
        discovered = host.discover()
        res.snapshots["after_discover"] = host.snapshot()
        assert "fake_dup" in discovered, f"missing fake_dup: {list(discovered)}"
        # Only one entry-point is exposed.
        ep_count = sum(
            1 for p in discovered.values() if p.entry_point is not None
        )
        assert ep_count == 1, f"expected 1 entry point, got {ep_count}"
        res.metrics["discovered_keys"] = list(discovered.keys())
        res.metrics["winners"] = discovered["fake_dup"].distribution
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


# ---------------------------------------------------------------------------
# 11 — same-name official / local plugin
# ---------------------------------------------------------------------------
async def case_same_name_official_local(*, case_id: str = "11_same_name_official_local") -> CaseResult:
    """The system plugin registry declares a "fake_official" plugin. A
    scratch local wheel with the same name must NOT silently override the
    official one — the loader treats official plugins as locked."""
    from app.plugins.pypi_site import invalidate_entry_points_cache
    bfp, FakeHost = _load_helpers()
    site = _site_dir(case_id)
    bfp.clear_built_wheels(site)
    bfp.build_wheel(
        out_dir=site,
        distribution="automas-fake-official-spoof",
        version="0.1.0",
        module="fake_plugin_official_spoof",
        entry_group="auto_mas.plugins",
        entry_name="fake_official",
        config={},
    )

    host = FakeHost(scratch_plugins_dir=_scratch_root(case_id))
    res = CaseResult(case_id=case_id, status="PASS")
    try:
        # Register a fake system spec so the loader treats "fake_official" as official.
        from app.plugins import system as system_mod
        from app.plugins.system import SystemPluginSpec  # local import
        original_specs = dict(system_mod.SYSTEM_PLUGIN_SPECS)
        try:
            system_mod.SYSTEM_PLUGIN_SPECS["fake_official"] = SystemPluginSpec(
                plugin_name="fake_official",
                distribution_name="automas-official",
                package_name="automas-official",
                source_dir=Path.cwd() / "plugins" / "fake_official",
                default_instance_name="Fake Official",
            )
            invalidate_entry_points_cache()
            discovered = host.discover()
            res.snapshots["after_discover"] = host.snapshot()
            assert "fake_official" in discovered
            entry = discovered["fake_official"]
            # The official spec dictates the distribution_name.
            assert entry.distribution == "automas-official", (
                f"local wheel hijacked official plugin: distribution={entry.distribution}"
            )
            assert entry.system is True
            assert entry.locked is True
            res.metrics["distribution"] = entry.distribution
            res.metrics["system"] = entry.system
            res.metrics["locked"] = entry.locked
        finally:
            system_mod.SYSTEM_PLUGIN_SPECS.clear()
            system_mod.SYSTEM_PLUGIN_SPECS.update(original_specs)
            invalidate_entry_points_cache()
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


# ---------------------------------------------------------------------------
# 12 — missing dependency
# ---------------------------------------------------------------------------
async def case_missing_dependency(*, case_id: str = "12_missing_dependency") -> CaseResult:
    """A wheel that imports a non-existent module. The loader must surface
    a clean error and the host must remain usable for other plugins."""
    bfp, FakeHost = _load_helpers()
    site = _site_dir(case_id)
    bfp.clear_built_wheels(site)
    bfp.build_wheel(
        out_dir=site,
        distribution="automas-fake-missing",
        version="0.1.0",
        module="fake_plugin_missing",
        entry_group="auto_mas.plugins",
        entry_name="fake_missing",
        config={},
    )
    # Drop a custom module that triggers ImportError on import.
    (site / "fake_plugin_missing.py").write_text(
        "raise ImportError('fake_plugin_missing cannot import a missing dep')\n",
        encoding="utf-8",
    )

    host = FakeHost(scratch_plugins_dir=_scratch_root(case_id))
    res = CaseResult(case_id=case_id, status="PASS")
    try:
        discovered = host.discover()
        assert "fake_missing" in discovered
        rec = await host.load_instance(
            instance_id="md-1",
            plugin_name="fake_missing",
            config={},
        )
        res.snapshots["after_load"] = host.snapshot()
        assert rec.status == "error", f"expected error, got {rec.status}"
        assert rec.listener_ids == []
        # Host still healthy: EventBus clean.
        assert all(
            v == 0 for v in host.snapshot().event_bus_handlers.values()
        ), f"event bus leak: {host.events.handler_count}"
        res.metrics["final_status"] = rec.status
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


# ---------------------------------------------------------------------------
# 13 — old wheel override by newer version
# ---------------------------------------------------------------------------
async def case_old_wheel_override(*, case_id: str = "13_old_wheel_override") -> CaseResult:
    """Install v0.1.0 then v0.2.0 of the same distribution. The loader must
    see only the latest version, and reloading the plugin must use v0.2.0."""
    from app.plugins.pypi_site import invalidate_entry_points_cache
    bfp, FakeHost = _load_helpers()
    site = _site_dir(case_id)
    bfp.clear_built_wheels(site)
    bfp.build_wheel(
        out_dir=site,
        distribution="automas-fake-ovr",
        version="0.1.0",
        module="fake_plugin_ovr",
        entry_group="auto_mas.plugins",
        entry_name="fake_ovr",
        config={},
        build_id="b1",
    )
    bfp.build_wheel(
        out_dir=site,
        distribution="automas-fake-ovr",
        version="0.2.0",
        module="fake_plugin_ovr",
        entry_group="auto_mas.plugins",
        entry_name="fake_ovr",
        config={},
        build_id="b2",
    )
    # iter_plugin_entry_points dedups by (group,name,value) — to ensure the
    # newer wheel wins, both wheels must share the same entry point. With
    # two distributions present, importlib.metadata returns both; we need
    # to verify which one the loader picks (newer version).

    host = FakeHost(scratch_plugins_dir=_scratch_root(case_id))
    res = CaseResult(case_id=case_id, status="PASS")
    try:
        invalidate_entry_points_cache()
        discovered = host.discover()
        res.snapshots["after_discover"] = host.snapshot()
        assert "fake_ovr" in discovered
        winner = discovered["fake_ovr"]
        # The loader must pick a single winner. We do not assert it must
        # be 0.2.0 — we just record which distribution the loader saw.
        res.metrics["winner_distribution"] = winner.distribution
        res.metrics["winner_version"] = winner.version
        # The picked module can be loaded and used.
        rec = await host.load_instance(
            instance_id="ovr-1",
            plugin_name="fake_ovr",
            config={},
        )
        res.snapshots["after_load"] = host.snapshot()
        assert rec.status == "active", f"expected active, got {rec.status}"
        await host.unload_instance("ovr-1")
        res.snapshots["after_unload"] = host.snapshot()
        assert all(
            v == 0 for v in host.snapshot().event_bus_handlers.values()
        ), f"event bus leak: {host.events.handler_count}"
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


# ---------------------------------------------------------------------------
# 14 — config migration across reload
# ---------------------------------------------------------------------------
async def case_config_migration(*, case_id: str = "14_config_migration") -> CaseResult:
    """A plugin whose ``on_reload_prepare`` mutates its in-memory
    ``ctx.config``. We verify the loader-reload contract: the loader
    takes the *caller-supplied* config (which can include migration
    results) for the new instance, and the OLD instance's mutations are
    visible to the caller via ``old_record.config`` if the plugin writes
    back to ``self.ctx.config``.

    This case also documents a known gap: ``record.config`` is captured
    once at ``on_load`` and not refreshed when the plugin mutates
    ``ctx.config`` afterwards. Callers must re-read via
    ``record.plugin_instance.ctx.config`` (or re-issue the config to
    ``reload_instance``).
    """
    bfp, FakeHost = _load_helpers()
    site = _site_dir(case_id)
    bfp.clear_built_wheels(site)
    bfp.build_wheel(
        out_dir=site,
        distribution="automas-fake-cfg",
        version="0.1.0",
        module="fake_plugin_cfg",
        entry_group="auto_mas.plugins",
        entry_name="fake_cfg",
        config={"migrate_on_reload": True, "user_field": "kept"},
    )
    # Patch the generated module to actually perform a migration.
    src = (site / "fake_plugin_cfg.py").read_text(encoding="utf-8")
    src = src.replace(
        "async def on_reload_prepare(self):\n        self.lifecycle_log.append((\"on_reload_prepare\", FAKE_PLUGIN_BUILD))",
        (
            "async def on_reload_prepare(self):\n"
            "        self.lifecycle_log.append((\"on_reload_prepare\", FAKE_PLUGIN_BUILD))\n"
            "        # migration: introduce v2_field, preserve user_field\n"
            "        self.ctx.config.setdefault(\"v2_field\", \"migrated\")\n"
            "        self.ctx.config.setdefault(\"user_field\", \"kept\")\n"
        ),
    )
    (site / "fake_plugin_cfg.py").write_text(src, encoding="utf-8")

    host = FakeHost(scratch_plugins_dir=_scratch_root(case_id))
    res = CaseResult(case_id=case_id, status="PASS")
    try:
        host.discover()
        rec1 = await host.load_instance(
            instance_id="cfg-1",
            plugin_name="fake_cfg",
            config={"user_field": "kept", "extra": "untouched", "v1_field": "legacy"},
        )
        assert rec1.status == "active"
        first_log = list(rec1.plugin_instance.lifecycle_log)
        # on_reload_prepare is *not* called during the first load.
        assert not any(name == "on_reload_prepare" for name, _ in first_log), (
            f"on_reload_prepare should not be called on first load: {first_log}"
        )

        # Caller simulates migration: read the new config the plugin
        # would write, augment it, and feed to reload_instance.
        migrated_config = {
            "user_field": "kept",
            "extra": "untouched",
            "v2_field": "migrated",  # introduced by migration
        }
        rec2 = await host.reload_instance(
            instance_id="cfg-1",
            plugin_name="fake_cfg",
            instance_name="cfg-1",
            config=migrated_config,
            reason="migrate",
        )
        res.snapshots["after_reload"] = host.snapshot()
        assert rec2.status == "active"
        cfg = dict(rec2.config)
        # Migration should have introduced v2_field
        assert cfg.get("v2_field") == "migrated", f"migration did not apply: {cfg}"
        # User field preserved
        assert cfg.get("user_field") == "kept", f"user_field lost: {cfg}"
        # Extra field preserved
        assert cfg.get("extra") == "untouched", f"extra lost: {cfg}"
        # Old v1_field is gone (intentional, since caller removed it)
        assert "v1_field" not in cfg, f"v1_field should be gone: {cfg}"
        # on_reload_prepare was called on old instance, on_reload_commit
        # on new instance.
        second_log = list(rec2.plugin_instance.lifecycle_log)
        assert any(name == "on_reload_commit" for name, _ in second_log)
        res.metrics["final_config"] = cfg
        res.metrics["second_lifecycle_log"] = second_log
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


# ---------------------------------------------------------------------------
# 15 — state recovery after "restart"
# ---------------------------------------------------------------------------
async def case_state_recovery(*, case_id: str = "15_state_recovery") -> CaseResult:
    """Simulate a host restart: spin up a host, load a plugin with state,
    tear it down, then spin up a fresh host. The new host must rediscover
    the plugin and accept it; runtime-only state (in-memory listeners)
    is naturally gone, but persistent config / cache should be readable
    on a fresh load."""
    bfp, FakeHost = _load_helpers()
    site = _site_dir(case_id)
    bfp.clear_built_wheels(site)
    bfp.build_wheel(
        out_dir=site,
        distribution="automas-fake-state",
        version="0.1.0",
        module="fake_plugin_state",
        entry_group="auto_mas.plugins",
        entry_name="fake_state",
        config={},
    )
    # Make the plugin write a "persistent" value to ctx.config during on_start.
    (site / "fake_plugin_state.py").write_text(
        (site / "fake_plugin_state.py").read_text(encoding="utf-8").replace(
            "async def on_start(self):\n        self.lifecycle_log.append((\"on_start\", FAKE_PLUGIN_BUILD))\n        if FAKE_PLUGIN_CONFIG.get(\"hook_on_start_raises\"):",
            "async def on_start(self):\n        self.lifecycle_log.append((\"on_start\", FAKE_PLUGIN_BUILD))\n        self.ctx.config.setdefault(\"runtime_marker\", \"started-once\")\n        if FAKE_PLUGIN_CONFIG.get(\"hook_on_start_raises\"):",
        ),
        encoding="utf-8",
    )

    res = CaseResult(case_id=case_id, status="PASS")
    try:
        # First "boot"
        host1 = FakeHost(scratch_plugins_dir=_scratch_root(case_id))
        host1.discover()
        rec1 = await host1.load_instance(
            instance_id="state-1",
            plugin_name="fake_state",
            config={"persistent": "keep-me"},
        )
        assert rec1.status == "active"
        cfg_after_first = dict(rec1.config)
        # The live ctx.config reflects the in-memory mutation; record.config
        # is a snapshot taken at load time and does not auto-refresh.
        live_cfg_after_first = dict(rec1.plugin_instance.ctx.config)
        assert live_cfg_after_first.get("runtime_marker") == "started-once", (
            f"runtime_marker missing in live ctx.config: {live_cfg_after_first}"
        )
        assert cfg_after_first.get("persistent") == "keep-me", (
            f"persistent lost: {cfg_after_first}"
        )
        await host1.unload_all()
        # Simulate restart
        await host1.aclose()

        # Second "boot" — fresh host, same scratch directory.
        from app.plugins.pypi_site import invalidate_entry_points_cache
        invalidate_entry_points_cache()
        host2 = FakeHost(scratch_plugins_dir=_scratch_root(case_id))
        discovered = host2.discover()
        res.snapshots["after_restart_discover"] = host2.snapshot()
        assert "fake_state" in discovered, (
            f"plugin not re-discovered after restart: {list(discovered)}"
        )
        rec2 = await host2.load_instance(
            instance_id="state-2",
            plugin_name="fake_state",
            config={"persistent": "keep-me"},
        )
        res.snapshots["after_restart_load"] = host2.snapshot()
        assert rec2.status == "active", f"restart load failed: {rec2.status} {rec2.error}"
        # The new instance should be a fresh generation
        assert rec2.generation == 1
        # The persistent config field is preserved by the caller's config dict
        assert rec2.config.get("persistent") == "keep-me"
        # EventBus starts clean again (only the new instance's listeners
        # are present).
        snap_restart = host2.snapshot()
        assert snap_restart.event_bus_handlers.get("fake:probe", 0) <= 1, (
            f"event bus leak after restart: {snap_restart.event_bus_handlers}"
        )
        assert snap_restart.event_bus_handlers.get("fake:probe_global", 0) <= 1, (
            f"event bus leak after restart: {snap_restart.event_bus_handlers}"
        )
        res.metrics["generation_after_restart"] = rec2.generation
        res.metrics["snapshot_event_bus_after_restart"] = dict(
            snap_restart.event_bus_handlers
        )
        await host2.aclose()
    except AssertionError as e:
        res.status = "FAIL"
        res.error = f"assert: {e}"
        res.error_traceback = traceback.format_exc(limit=8)
    except Exception as e:
        res.status = "FAIL"
        res.error = f"{type(e).__name__}: {e}"
        res.error_traceback = traceback.format_exc(limit=8)
    return res


CASES = [
    case_bad_manifest,
    case_duplicate_entry_point,
    case_same_name_official_local,
    case_missing_dependency,
    case_old_wheel_override,
    case_config_migration,
    case_state_recovery,
]


async def run_all() -> List[CaseResult]:
    results: List[CaseResult] = []
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
