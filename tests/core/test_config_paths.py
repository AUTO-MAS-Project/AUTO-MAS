"""Config 区分随源码发布的资源与 Runtime 工作目录中的用户文件。"""

import os
import subprocess
import sys

from app.core import Config


def test_config_resources_are_available_from_the_source_tree() -> None:
    assert (Config.source_path / "main.py").is_file()
    assert (Config.resource_path / "images" / "materials").is_dir()
    assert (Config.resource_path / "version.json").is_file()


def test_notification_reads_image_from_configured_resources(tmp_path, monkeypatch):
    from app.core.notify.formats import maa

    monkeypatch.setattr(Config, "resource_path", tmp_path)
    image = tmp_path / "images" / "notification" / "six_star.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"notification image")
    maa._six_star_image.cache_clear()
    try:
        assert maa._six_star_image() == b"notification image"
    finally:
        maa._six_star_image.cache_clear()


def test_config_keeps_resource_and_user_paths_separate(tmp_path) -> None:
    code = """
import os
from pathlib import Path
import app
os.chdir(os.environ["MAS_TEST_WORK_DIR"])
from app.core import Config
root = Path.cwd()
assert Config.work_path == root
assert Config.resource_path == Config.source_path / "res"
assert (Config.resource_path / "version.json").is_file()
for name, directory in {
    "config_path": "config", "data_path": "data", "debug_path": "debug",
    "history_path": "history", "script_path": "script", "plugins_path": "plugins",
}.items():
    assert getattr(Config, name) == root / directory, name
assert Config.log_path == Config.debug_path / "app.log"
assert Config.database_path == Config.data_path / "data.db"
os.chdir(Config.source_path)
assert Config.config_path == root / "config"
assert Config.data_path == root / "data"
assert Config.resource_path != root / "res"
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={
            **os.environ,
            "PYTHONIOENCODING": "utf-8",
            "MAS_TEST_WORK_DIR": str(tmp_path),
        },
    )
    assert result.returncode == 0, result.stderr
