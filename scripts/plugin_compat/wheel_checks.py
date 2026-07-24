"""AUTO-MAS plugin wheel blackbox checks 1-6.

Run with r6 Python 3.12 (static phase works anywhere; runtime phase needs wheels installed):

    python.exe scripts/plugin_compat/wheel_checks.py \
        --wheelhouse "plugins/wheels" \
        --output "subagent_a/logs/wheel_checks.json"

Checks:
  1. wheel metadata readable (zipfile METADATA)
  2. entry point discoverable (entry_points.txt + importlib.metadata)
  3. installable in isolated env (observed via importlib.metadata.distribution present)
  4. import smoke (importlib.import_module of the import package)
  5. plugin discover/register (load entry point -> Plugin class, inspect DEFAULT_INSTANCE/provides/wants)
  6. schema/config dump (module-level schema / DEFAULT_INSTANCE / Plugin.schema)
"""
from __future__ import annotations

import argparse
import configparser
import importlib
import importlib.metadata
import io
import json
import pathlib
import sys
import traceback
import zipfile
from typing import Any


def parse_wheel_filename(filename: str) -> tuple[str, str]:
    """Return (distribution_normalized, version) from a wheel filename.

    distribution_normalized uses '-' (PEP 503 canonical) so it matches
    importlib.metadata distribution names.
    """
    stem = filename[:-4] if filename.endswith(".whl") else filename
    parts = stem.split("-")
    # {dist}-{ver}-{pytag}-{abitag}-{plat}  (5 parts) or {dist}-{ver}-{pytag}-{plat} (4)
    if len(parts) >= 2:
        dist = parts[0].replace("_", "-")
        ver = parts[1]
        return dist, ver
    return stem, ""


def read_wheel_metadata(wheel: pathlib.Path) -> dict[str, Any]:
    """Check 1: read METADATA from wheel via zipfile. Returns parsed fields."""
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
        meta_files = [n for n in names if n.endswith(".dist-info/METADATA")]
        if not meta_files:
            raise RuntimeError(f"no METADATA in {wheel.name}")
        raw = zf.read(meta_files[0]).decode("utf-8", errors="replace")
        entry_files = [n for n in names if n.endswith("entry_points.txt")]
        entry_text = ""
        if entry_files:
            entry_text = zf.read(entry_files[0]).decode("utf-8", errors="replace")
    # parse METADATA headers (RFC 822-ish)
    fields: dict[str, str] = {}
    body_lines: list[str] = []
    in_body = False
    for line in raw.splitlines():
        if in_body:
            body_lines.append(line)
            continue
        if line.strip() == "":
            in_body = True
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            k = k.strip().lower()
            v = v.strip()
            if k in fields:
                fields[k] = fields[k] + "\n" + v
            else:
                fields[k] = v
    requires_dist = []
    if "requires-dist" in fields:
        requires_dist = [r.strip() for r in fields["requires-dist"].split("\n") if r.strip()]
    return {
        "raw_metadata_preview": raw[:2000],
        "name": fields.get("name", ""),
        "version": fields.get("version", ""),
        "requires_python": fields.get("requires-python", ""),
        "requires_dist": requires_dist,
        "summary": fields.get("summary", ""),
        "entry_points_txt": entry_text,
    }


def parse_entry_points_txt(text: str) -> list[dict[str, str]]:
    """Check 2: parse entry_points.txt -> list of {group, name, value}."""
    if not text.strip():
        return []
    cp = configparser.ConfigParser(delimiters=("=",), strict=False)
    cp.read_string(text)
    out: list[dict[str, str]] = []
    for group in cp.sections():
        for name in cp.options(group):
            value = cp.get(group, name).strip()
            out.append({"group": group, "name": name, "value": value})
    return out


def infer_import_package(entry_points: list[dict[str, str]]) -> str | None:
    """Infer the top-level import package from the first auto_mas.plugins entry point."""
    for ep in entry_points:
        if ep["group"] == "auto_mas.plugins" and ":" in ep["value"]:
            return ep["value"].split(":")[0]
    return None


def run_checks(wheelhouse: pathlib.Path) -> list[dict[str, Any]]:
    plugin_prefixes = ("auto_mas_core", "automas_")
    wheels = sorted(w for w in wheelhouse.glob("*.whl") if w.name.startswith(plugin_prefixes))
    results: list[dict[str, Any]] = []
    for wheel in wheels:
        dist_canon, ver_from_filename = parse_wheel_filename(wheel.name)
        rec: dict[str, Any] = {
            "wheel_file": wheel.name,
            "distribution": dist_canon,
            "version_from_filename": ver_from_filename,
            "checks": {},
        }
        # ---- Check 1: metadata readable ----
        try:
            meta = read_wheel_metadata(wheel)
            rec["checks"]["check_1_metadata_readable"] = {
                "status": "PASS",
                "name": meta["name"],
                "version_metadata": meta["version"],
                "requires_python": meta["requires_python"],
                "requires_dist": meta["requires_dist"],
                "summary": meta["summary"],
            }
            rec["metadata"] = meta
        except Exception as e:
            rec["checks"]["check_1_metadata_readable"] = {
                "status": "FAIL",
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc(limit=3),
            }
            results.append(rec)
            continue

        # ---- Check 2: entry point discoverable (static, from entry_points.txt) ----
        eps_static = parse_entry_points_txt(meta["entry_points_txt"])
        has_ep = any(ep["group"] == "auto_mas.plugins" for ep in eps_static)
        is_meta = dist_canon in ("automas-m9a", "automas-hsr")
        if is_meta:
            rec["checks"]["check_2_entry_point_discoverable"] = {
                "status": "PASS",
                "note": "meta package; no entry_points.txt expected",
                "entry_points_static": eps_static,
            }
        elif has_ep:
            rec["checks"]["check_2_entry_point_discoverable"] = {
                "status": "PASS",
                "entry_points_static": eps_static,
            }
        else:
            rec["checks"]["check_2_entry_point_discoverable"] = {
                "status": "FAIL",
                "error": "no auto_mas.plugins entry point in entry_points.txt",
                "entry_points_static": eps_static,
            }

        # ---- Check 3: installable / installed metadata ----
        try:
            dist = importlib.metadata.distribution(dist_canon)
            rec["checks"]["check_3_installed_metadata"] = {
                "status": "PASS",
                "version": dist.version,
                "note": "distribution discoverable via importlib.metadata in current env",
            }
        except importlib.metadata.PackageNotFoundError:
            rec["checks"]["check_3_installed_metadata"] = {
                "status": "NOT_RUN",
                "error": "distribution not installed in current env; run inside venv with wheels installed",
            }
        except Exception as e:
            rec["checks"]["check_3_installed_metadata"] = {
                "status": "FAIL",
                "error": f"{type(e).__name__}: {e}",
            }

        # ---- Check 4: import smoke ----
        import_pkg = infer_import_package(eps_static)
        if import_pkg is None:
            rec["checks"]["check_4_import_smoke"] = {
                "status": "PASS",
                "note": "meta package; no import target",
            }
        else:
            try:
                mod = importlib.import_module(import_pkg)
                rec["checks"]["check_4_import_smoke"] = {
                    "status": "PASS",
                    "import_package": import_pkg,
                    "module_file": getattr(mod, "__file__", None),
                }
            except Exception as e:
                rec["checks"]["check_4_import_smoke"] = {
                    "status": "FAIL",
                    "import_package": import_pkg,
                    "error": f"{type(e).__name__}: {e}",
                    "traceback": traceback.format_exc(limit=4),
                }

        # ---- Check 5: plugin discover/register (load entry point -> Plugin class) ----
        if not has_ep:
            rec["checks"]["check_5_plugin_discover_register"] = {
                "status": "PASS",
                "note": "meta package; no entry point to load",
            }
        else:
            try:
                # use importlib.metadata entry_points for the installed dist
                dist = importlib.metadata.distribution(dist_canon)
                eps_obj = [ep for ep in dist.entry_points if ep.group == "auto_mas.plugins"]
                if not eps_obj:
                    raise RuntimeError("entry point not discoverable via importlib.metadata")
                ep = eps_obj[0]
                plugin_cls = ep.load()
                cls_attrs: dict[str, Any] = {
                    "class": f"{plugin_cls.__module__}:{plugin_cls.__qualname__}",
                    "has_on_start": hasattr(plugin_cls, "on_start"),
                    "has_on_stop": hasattr(plugin_cls, "on_stop"),
                }
                for attr in ("provides", "wants", "schema", "DEFAULT_INSTANCE"):
                    if hasattr(plugin_cls, attr):
                        val = getattr(plugin_cls, attr)
                        try:
                            json.dumps(val)
                            cls_attrs[attr] = val
                        except (TypeError, ValueError):
                            cls_attrs[attr] = repr(val)
                # also check module-level DEFAULT_INSTANCE / schema
                if import_pkg:
                    mod = importlib.import_module(import_pkg)
                    for attr in ("DEFAULT_INSTANCE", "schema"):
                        if hasattr(mod, attr):
                            val = getattr(mod, attr)
                            try:
                                json.dumps(val)
                                cls_attrs[f"module_{attr}"] = val
                            except (TypeError, ValueError):
                                cls_attrs[f"module_{attr}"] = repr(val)
                rec["checks"]["check_5_plugin_discover_register"] = {
                    "status": "PASS",
                    "entry_point_name": ep.name,
                    "entry_point_value": ep.value,
                    **cls_attrs,
                }
            except importlib.metadata.PackageNotFoundError:
                rec["checks"]["check_5_plugin_discover_register"] = {
                    "status": "NOT_RUN",
                    "error": "distribution not installed; run inside venv",
                }
            except Exception as e:
                rec["checks"]["check_5_plugin_discover_register"] = {
                    "status": "FAIL",
                    "error": f"{type(e).__name__}: {e}",
                    "traceback": traceback.format_exc(limit=5),
                }

        # ---- Check 6: schema/config dump ----
        c5 = rec["checks"].get("check_5_plugin_discover_register", {})
        schema_found = False
        schema_data = None
        for key in ("schema", "module_schema"):
            if key in c5:
                schema_found = True
                schema_data = c5[key]
                break
        default_instance_found = any(k in c5 for k in ("DEFAULT_INSTANCE", "module_DEFAULT_INSTANCE"))
        if not has_ep:
            rec["checks"]["check_6_schema_config_dump"] = {
                "status": "PASS",
                "note": "meta package; no schema",
            }
        elif schema_found:
            rec["checks"]["check_6_schema_config_dump"] = {
                "status": "PASS",
                "schema_present": True,
                "default_instance_present": default_instance_found,
                "schema_keys": list(schema_data.keys()) if isinstance(schema_data, dict) else None,
                "schema_sample": schema_data if isinstance(schema_data, dict) else repr(schema_data),
            }
        elif default_instance_found:
            rec["checks"]["check_6_schema_config_dump"] = {
                "status": "PASS",
                "schema_present": False,
                "default_instance_present": True,
                "note": "no explicit schema; DEFAULT_INSTANCE present",
            }
        else:
            rec["checks"]["check_6_schema_config_dump"] = {
                "status": "FAIL",
                "error": "neither schema nor DEFAULT_INSTANCE found on Plugin class or module",
            }

        results.append(rec)
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wheelhouse", required=True, help="path to plugins/wheels directory")
    ap.add_argument("--output", required=True, help="output JSON path")
    args = ap.parse_args()

    wheelhouse = pathlib.Path(args.wheelhouse).resolve()
    if not wheelhouse.is_dir():
        print(f"ERROR: wheelhouse not found: {wheelhouse}", file=sys.stderr)
        return 2

    results = run_checks(wheelhouse)

    summary = {
        "total": len(results),
        "check_1_pass": sum(1 for r in results if r["checks"].get("check_1_metadata_readable", {}).get("status") == "PASS"),
        "check_2_pass": sum(1 for r in results if r["checks"].get("check_2_entry_point_discoverable", {}).get("status") == "PASS"),
        "check_3_pass": sum(1 for r in results if r["checks"].get("check_3_installed_metadata", {}).get("status") == "PASS"),
        "check_3_not_run": sum(1 for r in results if r["checks"].get("check_3_installed_metadata", {}).get("status") == "NOT_RUN"),
        "check_4_pass": sum(1 for r in results if r["checks"].get("check_4_import_smoke", {}).get("status") == "PASS"),
        "check_4_fail": sum(1 for r in results if r["checks"].get("check_4_import_smoke", {}).get("status") == "FAIL"),
        "check_5_pass": sum(1 for r in results if r["checks"].get("check_5_plugin_discover_register", {}).get("status") == "PASS"),
        "check_5_fail": sum(1 for r in results if r["checks"].get("check_5_plugin_discover_register", {}).get("status") == "FAIL"),
        "check_6_pass": sum(1 for r in results if r["checks"].get("check_6_schema_config_dump", {}).get("status") == "PASS"),
        "check_6_fail": sum(1 for r in results if r["checks"].get("check_6_schema_config_dump", {}).get("status") == "FAIL"),
    }

    out = {
        "schema": "subagent_a_wheel_checks_v1",
        "wheelhouse": str(wheelhouse),
        "python": sys.version,
        "executable": sys.executable,
        "summary": summary,
        "results": results,
    }
    out_path = pathlib.Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    print(f"[wheel_checks] wrote {out_path}")
    print(f"[wheel_checks] summary: {json.dumps(summary)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
