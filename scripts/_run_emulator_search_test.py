"""Minimal harness: mumu_adapter.search without loading FastAPI app."""

import asyncio
import json
import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "plugins" / "auto_mas_core" / "src"
MUMU_SRC = ROOT / "plugins" / "mumu_adapter" / "src"


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
    ("app.utils.constants", "app/utils/constants.py"),
]:
    if pkg.endswith(".py") or rel.endswith(".py"):
        continue
    m = types.ModuleType(pkg)
    m.__path__ = [str(ROOT / rel)]
    sys.modules[pkg] = m

logger_mod = load("app.utils.logger", "app/utils/logger.py")
sys.modules["app.utils"].get_logger = logger_mod.get_logger
constants_mod = load("app.utils.constants", "app/utils/constants.py")

# Minimal host utils stand-in for search only
class _Utils:
    ProcessManager = object
    ProcessRunner = object
    ProcessResult = object

    def get_logger(self, name: str):
        return logger_mod.get_logger(name)

    def get_setting(self, group: str, name: str, default=None):
        return default

    @property
    def emulator_path_book(self):
        return constants_mod.EMULATOR_PATH_BOOK


sys.path.insert(0, str(CORE_SRC))
sys.path.insert(0, str(MUMU_SRC))

from mumu_adapter.search import search_mumu  # noqa: E402

if __name__ == "__main__":
    results = asyncio.run(search_mumu(_Utils()))
    print("=== count:", len(results), "===")
    for r in results:
        print(json.dumps(r, ensure_ascii=False))
    types_found = {x["type"] for x in results}
    print("=== types found:", sorted(types_found), "===")
    sys.exit(0)
