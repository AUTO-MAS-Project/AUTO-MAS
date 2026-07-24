"""Build PLUGIN_INVENTORY from manifest.json + runtime-lock.json + plugins/ tree.

Read-only. Outputs to:
  D:\trae_projects\AUTO-MAS-Projects\_alpha_build\a1\plugin-lifecycle-reload-cert-20260723\runs\inventory_extraction.json
"""
from __future__ import annotations

import json
from pathlib import Path

WORKTREE = Path(r"D:\trae_projects\AUTO-MAS-Projects\AUTO-MAS-workspace\worktrees\all-plugins-integration")
MANIFEST = WORKTREE / "plugins" / "wheels" / "manifest.json"
LOCK = WORKTREE / "plugins" / "wheels" / "runtime-lock.json"
PLUGINS_DIR = WORKTREE / "plugins"
OUT = Path(r"D:\trae_projects\AUTO-MAS-Projects\_alpha_build\a1\plugin-lifecycle-reload-cert-20260723\runs\inventory_extraction.json")


def load(p: Path) -> dict:
    with p.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def main() -> None:
    manifest = load(MANIFEST)
    lock = load(LOCK)

    plugin_wheels = [w for w in manifest["wheels"] if w.get("kind") == "plugin"]
    runtime_wheels = [w for w in manifest["wheels"] if w.get("kind") == "runtime_dependency"]
    expected = manifest.get("expected_plugin_distribution_count")
    expected_ep = manifest.get("expected_plugin_entry_point_count")

    # Build distribution -> entry points map from manifest
    dist_eps: dict[str, list[dict]] = {}
    for w in plugin_wheels:
        d = w["distribution"]
        dist_eps.setdefault(d, []).extend(w.get("entry_points", []))

    # Lock plugins list
    lock_plugins = lock.get("plugins", [])
    lock_eps = lock.get("expected_plugin_entry_points", [])

    # Group entry points by (group, name) to detect duplicate entry points
    ep_keys: dict[tuple[str, str], list[dict]] = {}
    for ep in lock_eps:
        key = (ep["group"], ep["name"])
        ep_keys.setdefault(key, []).append(ep)

    duplicates = {k: v for k, v in ep_keys.items() if len(v) > 1}

    # Local source checkout
    local_sources: dict[str, dict] = {}
    if PLUGINS_DIR.exists():
        for child in sorted(PLUGINS_DIR.iterdir()):
            if not child.is_dir() or child.name in {"wheels", "pypi", "browser_data"}:
                continue
            if child.name.startswith("_") or child.name.startswith("."):
                continue
            pytoml = child / "pyproject.toml"
            if pytoml.exists():
                local_sources[child.name] = {
                    "path": str(child),
                    "pyproject": str(pytoml),
                }

    # Plugin-name collision: same entry point name across different distributions
    ep_name_to_dists: dict[str, set[str]] = {}
    for d, eps in dist_eps.items():
        for ep in eps:
            ep_name_to_dists.setdefault(ep["name"], set()).add(d)

    name_collisions = {
        ep_name: sorted(dists)
        for ep_name, dists in ep_name_to_dists.items()
        if len(dists) > 1
    }

    # System plugin match
    SYSTEM = {"auto_mas_core", "browser", "emulator"}
    system_overlap = sorted(
        ep_name for ep_name in ep_name_to_dists.keys() if ep_name in SYSTEM
    )

    out = {
        "manifest": {
            "schema_version": manifest.get("schema_version"),
            "generator": manifest.get("generator"),
            "generated_at": manifest.get("generated_at"),
            "artifact_scope": manifest.get("artifact_scope"),
            "expected_plugin_distribution_count": expected,
            "expected_plugin_entry_point_count": expected_ep,
            "runtime_lock_sha256": manifest.get("runtime_lock", {}).get("sha256"),
            "plugin_wheel_count": len(plugin_wheels),
            "runtime_dependency_wheel_count": len(runtime_wheels),
        },
        "runtime_lock": {
            "schema_version": lock.get("schema_version"),
            "generated_at": lock.get("generated_at"),
            "target": lock.get("target"),
            "host_runtime_count": len(lock.get("host_runtime", [])),
            "plugin_record_count": len(lock_plugins),
            "expected_plugin_entry_point_count": len(lock_eps),
        },
        "plugin_distributions": [
            {
                "distribution": w["distribution"],
                "version": w["version"],
                "filename": w["filename"],
                "size_bytes": w.get("size_bytes"),
                "sha256": w.get("sha256"),
                "scopes": w.get("scopes"),
                "entry_points": w.get("entry_points", []),
            }
            for w in plugin_wheels
        ],
        "entry_points": [
            {
                "group": ep["group"],
                "name": ep["name"],
                "value": ep["value"],
                "distribution": ep.get("distribution"),
                "version": ep.get("version"),
            }
            for ep in lock_eps
        ],
        "duplicate_entry_points": [
            {"key": list(k), "occurrences": v} for k, v in duplicates.items()
        ],
        "name_collisions_across_distributions": name_collisions,
        "system_plugin_overlap_with_wheel_entry_points": system_overlap,
        "local_source_checkouts": local_sources,
        "wheel_files_present": sorted(
            p.name for p in (WORKTREE / "plugins" / "wheels").glob("*.whl")
            if p.name.startswith(("auto_mas_core", "automas_"))
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # Sanity print
    print(f"manifest schema_version={manifest.get('schema_version')}")
    print(f"expected plugin distributions: manifest={expected}  manifest_plugin_wheels={len(plugin_wheels)}  lock_records={len(lock_plugins)}")
    print(f"expected plugin entry points: manifest={expected_ep}  lock_eps={len(lock_eps)}")
    print(f"duplicate entry point keys: {len(duplicates)}")
    print(f"name collisions across distributions: {len(name_collisions)}")
    print(f"system overlap (entry point name matches a system plugin spec): {system_overlap}")
    print(f"local source checkouts: {sorted(local_sources)}")
    print(f"wrote: {OUT}")


if __name__ == "__main__":
    main()
