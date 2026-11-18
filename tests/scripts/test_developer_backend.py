"""首次复制配置时保留一致数据库，并阻止覆盖已有开发数据。"""

import importlib.util
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest


def test_prepare_backend_copies_active_database_without_sharing_data(tmp_path):
    entry = Path(__file__).parents[2] / "scripts/prepare-developer-backend.py"
    spec = importlib.util.spec_from_file_location("prepare_developer_backend", entry)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source, base = tmp_path / "source", tmp_path / "base"
    source.mkdir()
    base.mkdir()
    for name in ("main.py", "pyproject.toml", "uv.lock"):
        (source / name).write_text("", encoding="utf-8")
    for name in (
        "AUTO-MAS.exe",
        "runtime/environment/venv/Scripts/python.exe",
        "runtime/environment/venv/pyvenv.cfg",
    ):
        target = base / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"external tool boundary")
    (base / "config").mkdir()
    (base / "config/settings.json").write_text('{"value":1}', encoding="utf-8")
    (base / "data").mkdir()
    with closing(sqlite3.connect(base / "data/state.db")) as original:
        original.execute("PRAGMA journal_mode=WAL")
        original.execute("CREATE TABLE example(value INTEGER)")
        original.execute("INSERT INTO example VALUES (7)")
        original.commit()
        assert (base / "data/state.db-wal").is_file()
        module.prepare(source, base, copy_data=True)
        assert not (source / ".venv").exists()
        with closing(sqlite3.connect(source / "data/state.db")) as copied:
            assert copied.execute("SELECT value FROM example").fetchall() == [(7,)]
        assert not (source / "data/state.db-wal").exists()
        (source / "config/settings.json").write_text('{"value":2}', encoding="utf-8")
        with pytest.raises(ValueError, match="已有"):
            module.prepare(source, base, copy_data=True)
        assert json.loads((base / "config/settings.json").read_text()) == {"value": 1}
        assert json.loads((source / "config/settings.json").read_text()) == {"value": 2}
