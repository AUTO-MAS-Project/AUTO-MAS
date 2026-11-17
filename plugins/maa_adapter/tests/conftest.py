import sys
from pathlib import Path

root = Path(__file__).resolve().parents[3]
for path in (
    root,
    root / "plugins/auto_mas_core/src",
    root / "plugins/maa_adapter/src",
):
    sys.path.insert(0, str(path))

from tests.conftest import isolated_app_paths as isolated_app_paths  # noqa: E402
from tests.conftest import isolated_config_roots as isolated_config_roots  # noqa: E402
