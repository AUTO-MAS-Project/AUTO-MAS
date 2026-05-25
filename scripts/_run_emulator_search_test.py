"""Minimal harness: search_all_emulators without loading FastAPI app."""
import json
import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_BRANDS = frozenset({"mumu", "ldplayer", "nox", "memu", "bluestacks"})


def load(name: str, rel: str):
    path = ROOT / rel
    spec = spec_from_file_location(name, path)
    mod = module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


for pkg, rel in [
    ("app", "app"),
    ("app.utils", "app/utils"),
    ("app.utils.emulator", "app/utils/emulator"),
]:
    m = types.ModuleType(pkg)
    m.__path__ = [str(ROOT / rel)]
    sys.modules[pkg] = m

logger_mod = load("app.utils.logger", "app/utils/logger.py")
sys.modules["app.utils"].get_logger = logger_mod.get_logger

load("app.utils.constants", "app/utils/constants.py")
tools_mod = load("app.utils.emulator.tools", "app/utils/emulator/tools.py")

if __name__ == "__main__":
    results = tools_mod.search_all_emulators()
    print("=== count:", len(results), "===")
    for r in results:
        print(json.dumps(r, ensure_ascii=False))
    types_found = {x["type"] for x in results}
    print("=== types found:", sorted(types_found), "===")
    missing = sorted(EXPECTED_BRANDS - types_found)
    print("=== missing brands:", missing or "(none)", "===")
    sys.exit(1 if missing else 0)
