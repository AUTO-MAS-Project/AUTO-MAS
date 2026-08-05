import json
from pathlib import Path

from app.task.Okww.AutoProxy import (
    _OKWW_REL_APP_JSON,
    _enable_okww_auto_start,
)


def test_enable_okww_auto_start_preserves_launcher_config(tmp_path: Path) -> None:
    app_json_path = tmp_path / _OKWW_REL_APP_JSON
    app_json_path.parent.mkdir(parents=True)
    app_json_path.write_text(
        json.dumps({"name": "ok-ww", "auto_start": False}),
        encoding="utf-8",
    )

    _enable_okww_auto_start(tmp_path)

    assert json.loads(app_json_path.read_text(encoding="utf-8")) == {
        "name": "ok-ww",
        "auto_start": True,
    }
