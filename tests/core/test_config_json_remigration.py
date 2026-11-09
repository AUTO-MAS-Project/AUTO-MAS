"""回退旧版后按完整 JSON 重新升级，保留失败重试与正常 YAML 启动语义。"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import Field

from app.config import ConfigEntry, ConfigGroup
from app.core.config.upgrade import CONFIG_FILES, MIGRATION_RECORD, upgrade_json_configs
from app.utils import io as config_io


class _Values(ConfigGroup):
    Revision: int = 1


class _Profile(ConfigEntry):
    Values: _Values = Field(default_factory=_Values)


@pytest.fixture
def migrated_profile(tmp_path):
    nodes = {key: _Profile.build() for _, _, key in CONFIG_FILES}
    for old, _, _ in CONFIG_FILES:
        config_io.write_file(tmp_path / old, {"Values": {"Revision": 1}})
    upgrade_json_configs(tmp_path, nodes)
    for _, new, _ in CONFIG_FILES:
        config_io.write_file(tmp_path / new, {"Values": {"Revision": 2}})
    return tmp_path, nodes


def _recreate_json(folder: Path) -> None:
    for old, _, _ in CONFIG_FILES:
        config_io.write_file(folder / old, {"Values": {"Revision": 3}})


def _assert_latest_json_migrated(folder: Path) -> None:
    for old, new, _ in CONFIG_FILES:
        assert config_io.read_dict_file(folder / new) == {"Values": {"Revision": 3}}
        assert not (folder / old).exists()
        assert config_io.read_dict_file(folder / "legacy-json" / old) == {
            "Values": {"Revision": 3}
        }


def test_completed_migration_reimports_recreated_json_without_yaml_backups(
    migrated_profile,
):
    folder, nodes = migrated_profile
    _recreate_json(folder)

    upgrade_json_configs(folder, nodes)

    _assert_latest_json_migrated(folder)
    assert set(folder.rglob("*.yaml")) == {folder / new for _, new, _ in CONFIG_FILES}
    assert {path.name for path in folder.iterdir() if path.is_dir()} == {"legacy-json"}
    assert not list(folder.rglob("*.yaml.*"))
    assert not list(folder.rglob("*.bak"))
    saved = {new: (folder / new).read_bytes() for _, new, _ in CONFIG_FILES}
    upgrade_json_configs(folder, nodes)
    assert saved == {new: (folder / new).read_bytes() for _, new, _ in CONFIG_FILES}


def test_completed_migration_keeps_modified_yaml_without_json(migrated_profile):
    folder, nodes = migrated_profile
    saved = {new: (folder / new).read_bytes() for _, new, _ in CONFIG_FILES}

    upgrade_json_configs(folder, nodes)

    assert saved == {new: (folder / new).read_bytes() for _, new, _ in CONFIG_FILES}


@pytest.mark.parametrize("incomplete", ["record", "sources"])
def test_incomplete_legacy_profile_does_not_remove_yaml(migrated_profile, incomplete):
    folder, nodes = migrated_profile
    _recreate_json(folder)
    if incomplete == "record":
        record = config_io.read_dict_file(folder / MIGRATION_RECORD)
        record["complete"] = False
        config_io.write_file(folder / MIGRATION_RECORD, record)
    else:
        (folder / "GameSignAccounts.json").unlink()
    saved = {new: (folder / new).read_bytes() for _, new, _ in CONFIG_FILES}

    with pytest.raises(ValueError):
        upgrade_json_configs(folder, nodes)

    assert saved == {new: (folder / new).read_bytes() for _, new, _ in CONFIG_FILES}


def test_invalid_json_is_rejected_before_removing_yaml(migrated_profile):
    folder, nodes = migrated_profile
    _recreate_json(folder)
    (folder / "QueueConfig.json").write_text("{", encoding="utf-8")
    saved = {new: (folder / new).read_bytes() for _, new, _ in CONFIG_FILES}
    record = (folder / MIGRATION_RECORD).read_bytes()

    with pytest.raises(config_io.ConfigCorruptedError):
        upgrade_json_configs(folder, nodes)

    assert saved == {new: (folder / new).read_bytes() for _, new, _ in CONFIG_FILES}
    assert (folder / MIGRATION_RECORD).read_bytes() == record


@pytest.mark.parametrize("failure", ["yaml", "archive"])
def test_remigration_resumes_after_file_removal_fails(
    migrated_profile, monkeypatch, failure
):
    folder, nodes = migrated_profile
    _recreate_json(folder)
    failing_path = (
        folder / "emulators.yaml"
        if failure == "yaml"
        else folder / "legacy-json" / "EmulatorConfig.json"
    )
    unlink = Path.unlink

    def fail_removal(path, *args, **kwargs):
        if path == failing_path:
            raise PermissionError("file is occupied")
        return unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_removal)
        with pytest.raises(PermissionError):
            upgrade_json_configs(folder, nodes)

    upgrade_json_configs(folder, nodes)

    _assert_latest_json_migrated(folder)


@pytest.mark.parametrize(
    "database_version, expected_days", [("v1.11", 30), ("v2.1", 15)]
)
def test_startup_uses_the_configuration_format_selected_by_database(
    tmp_path, database_version, expected_days
):
    source_root = Path(__file__).resolve().parents[2]
    code = """
import asyncio
import sqlite3
import sys

from app.core import Config
from app.core.config.upgrade import CONFIG_FILES, upgrade_json_configs
from app.utils import io

def write_legacy(days):
    for old, _, key in CONFIG_FILES:
        if old == 'GameSignAccounts.json':
            (Config.config_path / old).write_bytes(b'')
        else:
            payload = {'Function': {'HistoryRetentionTime': days}} if key == 'setting' else {'instances': []}
            io.write_file(Config.config_path / old, payload)

async def run():
    write_legacy(7)
    upgrade_json_configs(Config.config_path, Config._config_nodes)
    setting_path = Config.config_path / 'setting.yaml'
    yaml_setting = io.read_dict_file(setting_path)
    yaml_setting['Function']['HistoryRetentionTime'] = 15
    io.write_file(setting_path, yaml_setting)
    write_legacy(30)
    with sqlite3.connect(Config.database_path) as database:
        database.execute('CREATE TABLE version(v text)')
        database.execute('INSERT INTO version VALUES (?)', (sys.argv[1],))
    await Config.check_data()
    assert Config.setting.Function.HistoryRetentionTime == int(sys.argv[2])
    assert io.read_dict_file(setting_path)['Function']['HistoryRetentionTime'] == int(sys.argv[2])
    with sqlite3.connect(Config.database_path) as database:
        assert database.execute('SELECT v FROM version').fetchone()[0] == 'v2.1'
    assert (Config.config_path / 'Config.json').exists() == (sys.argv[1] == 'v2.1')

asyncio.run(run())
"""
    result = subprocess.run(
        [sys.executable, "-c", code, database_version, str(expected_days)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={
            **os.environ,
            "PYTHONPATH": str(source_root),
            "PYTHONIOENCODING": "utf-8",
            "AUTO_MAS_ENV": "development",
            "AUTO_MAS_SUPERVISED": "1",
        },
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
