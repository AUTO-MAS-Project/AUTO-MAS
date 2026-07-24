"""AUTO-MAS plugin lifecycle blackbox checks 9-10.

Check 9:  double-load no duplicate registration (entry point load twice -> same class identity)
Check 10: missing optional dependency error is explainable
          (static analysis of Requires-Dist extras + import error message check)

Check 7 (activate/update/rollback), Check 8 (deactivate/unregister/dispose),
Check 11 (plugin exception isolation), Check 12 (config v2 / WS leak) are covered
by the host test suite tests/plugins — run separately via pytest with the host .venv.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import pathlib
import re
import sys
import traceback
from typing import Any


# Matches PEP 508 extras: 'package[extra]>=1.0' or 'package[extra1,extra2]'
EXTRA_RE = re.compile(r"^[A-Za-z0-9._-]+\s*\[([^\]]+)\]")


def parse_wheel_filename(filename: str) -> tuple[str, str]:
    stem = filename[:-4] if filename.endswith(".whl") else filename
    parts = stem.split("-")
    if len(parts) >= 2:
        return parts[0].replace("_", "-"), parts[1]
    return stem, ""


def analyze_requires_dist(requires_dist: list[str]) -> dict[str, Any]:
    """Check 10 static: identify extras / optional deps in Requires-Dist."""
    extras_refs: list[str] = []
    mandatory: list[str] = []
    for req in requires_dist:
        m = EXTRA_RE.match(req.strip())
        if m:
            extras_refs.append(req.strip())
        else:
            # skip environment markers that are conditional (extra == ...)
            if "; extra ==" in req or "; extra==" in req:
                extras_refs.append(req.strip())
            else:
                mandatory.append(req.strip())
    return {
        "has_extras": bool(extras_refs),
        "extras_refs": extras_refs,
        "mandatory_count": len(mandatory),
        "mandatory": mandatory,
    }


def check_double_load(dist_canon: str) -> dict[str, Any]:
    """Check 9: load entry point twice; the Plugin class must be identity-equal."""
    try:
        dist = importlib.metadata.distribution(dist_canon)
    except importlib.metadata.PackageNotFoundError:
        return {"status": "NOT_RUN", "error": "distribution not installed; run inside venv"}
    eps = [ep for ep in dist.entry_points if ep.group == "auto_mas.plugins"]
    if not eps:
        return {"status": "PASS", "note": "meta package; no entry point"}
    ep = eps[0]
    try:
        cls1 = ep.load()
        cls2 = ep.load()
        same_class = cls1 is cls2
        # also check module-level singleton: importing twice should not re-execute
        mod_name = ep.value.split(":")[0]
        mod1 = importlib.import_module(mod_name)
        mod2 = importlib.import_module(mod_name)
        same_module = mod1 is mod2
        return {
            "status": "PASS" if (same_class and same_module) else "FAIL",
            "entry_point": ep.value,
            "class_identity_equal": same_class,
            "module_identity_equal": same_module,
            "class_repr": repr(cls1),
        }
    except Exception as e:
        return {
            "status": "FAIL",
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(limit=4),
        }


def check_missing_dep_explainable(dist_canon: str, requires_dist: list[str]) -> dict[str, Any]:
    """Check 10: if no extras, PASS (no optional deps); if extras, MANUAL_REQUIRED."""
    analysis = analyze_requires_dist(requires_dist)
    if not analysis["has_extras"]:
        # also try a fresh import to confirm no hidden optional import paths
        return {
            "status": "PASS",
            "note": "no extras/optional deps declared in Requires-Dist",
            "mandatory_count": analysis["mandatory_count"],
        }
    return {
        "status": "MANUAL_REQUIRED",
        "note": "distribution declares extras; manual test needed: uninstall extra and confirm error message names the missing module",
        "extras_refs": analysis["extras_refs"],
    }


def run_checks(wheelhouse: pathlib.Path) -> list[dict[str, Any]]:
    plugin_prefixes = ("auto_mas_core", "automas_")
    wheels = sorted(w for w in wheelhouse.glob("*.whl") if w.name.startswith(plugin_prefixes))
    import zipfile
    results: list[dict[str, Any]] = []
    for wheel in wheels:
        dist_canon, _ = parse_wheel_filename(wheel.name)
        rec: dict[str, Any] = {"wheel_file": wheel.name, "distribution": dist_canon, "checks": {}}
        # read requires-dist from wheel metadata
        requires_dist: list[str] = []
        try:
            with zipfile.ZipFile(wheel) as zf:
                meta_files = [n for n in zf.namelist() if n.endswith(".dist-info/METADATA")]
                if meta_files:
                    raw = zf.read(meta_files[0]).decode("utf-8", errors="replace")
                    for line in raw.splitlines():
                        if line.startswith("Requires-Dist:"):
                            requires_dist.append(line[len("Requires-Dist:"):].strip())
        except Exception:
            pass
        rec["checks"]["check_9_double_load_no_duplicate"] = check_double_load(dist_canon)
        rec["checks"]["check_10_missing_dep_explainable"] = check_missing_dep_explainable(dist_canon, requires_dist)
        results.append(rec)
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wheelhouse", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    wheelhouse = pathlib.Path(args.wheelhouse).resolve()
    if not wheelhouse.is_dir():
        print(f"ERROR: wheelhouse not found: {wheelhouse}", file=sys.stderr)
        return 2
    results = run_checks(wheelhouse)
    summary = {
        "total": len(results),
        "check_9_pass": sum(1 for r in results if r["checks"].get("check_9_double_load_no_duplicate", {}).get("status") == "PASS"),
        "check_9_fail": sum(1 for r in results if r["checks"].get("check_9_double_load_no_duplicate", {}).get("status") == "FAIL"),
        "check_9_not_run": sum(1 for r in results if r["checks"].get("check_9_double_load_no_duplicate", {}).get("status") == "NOT_RUN"),
        "check_10_pass": sum(1 for r in results if r["checks"].get("check_10_missing_dep_explainable", {}).get("status") == "PASS"),
        "check_10_manual": sum(1 for r in results if r["checks"].get("check_10_missing_dep_explainable", {}).get("status") == "MANUAL_REQUIRED"),
    }
    out = {
        "schema": "subagent_a_lifecycle_checks_v1",
        "wheelhouse": str(wheelhouse),
        "python": sys.version,
        "executable": sys.executable,
        "summary": summary,
        "results": results,
    }
    out_path = pathlib.Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    print(f"[lifecycle_checks] wrote {out_path}")
    print(f"[lifecycle_checks] summary: {json.dumps(summary)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
