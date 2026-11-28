"""回退旧版后重迁的来源选择、失败恢复和拒绝覆盖回归。"""

from pathlib import Path

import pytest
from pydantic import Field

from app.config import ConfigCollection, ConfigEntry, ConfigGroup
from app.core.config.upgrade import (
    CONFIG_FILES,
    MIGRATION_RECORD,
    convert_legacy,
    retire_baah_plans,
    upgrade_json_configs,
)
from app.models.config import EmulatorConfig
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
    for old, new, _ in CONFIG_FILES:
        config_io.write_file(tmp_path / new, {"Values": {"Revision": 2}})
        config_io.write_file(tmp_path / old, {"Values": {"Revision": 3}})
    return tmp_path, nodes


@pytest.mark.parametrize("failure", [None, "replace", "checkpoint", "invalid_record"])
def test_remigration_keeps_failed_state_and_resumes_from_current_json(
    migrated_profile, monkeypatch, failure
):
    folder, nodes = migrated_profile
    if failure == "invalid_record":
        record_path = folder / MIGRATION_RECORD
        valid_record = record_path.read_bytes()
        record = config_io.read_dict_file(record_path)
        record["complete"] = False
        config_io.write_file(record_path, record)
        paths = [record_path, *(folder / new for _, new, _ in CONFIG_FILES)]
        saved = {path: path.read_bytes() for path in paths}
        with pytest.raises(ValueError):
            upgrade_json_configs(folder, nodes)
        assert saved == {path: path.read_bytes() for path in paths}
        record_path.write_bytes(valid_record)
    elif failure:
        replace = Path.replace
        write_file = config_io.write_file
        target = folder / "emulators.yaml"
        original = target.read_bytes()

        def fail_replace(path, destination):
            if destination == target:
                raise PermissionError("file is occupied")
            return replace(path, destination)

        def fail_checkpoint(path, *args, **kwargs):
            if (
                path == folder / MIGRATION_RECORD
                and not (folder / "EmulatorConfig.json").exists()
            ):
                raise PermissionError("progress cannot be saved")
            return write_file(path, *args, **kwargs)

        with monkeypatch.context() as patch:
            if failure == "replace":
                patch.setattr(Path, "replace", fail_replace)
            else:
                patch.setattr(config_io, "write_file", fail_checkpoint)
            with pytest.raises(PermissionError):
                upgrade_json_configs(folder, nodes)
        if failure == "replace":
            assert target.read_bytes() == original

    upgrade_json_configs(folder, nodes)

    for old, new, _ in CONFIG_FILES:
        expected = {"Values": {"Revision": 3}}
        assert config_io.read_dict_file(folder / new) == expected
        assert config_io.read_dict_file(folder / "legacy-json" / old) == expected
    # 根目录只留下本轮 YAML 和迁移记录，不额外保存旧 YAML 或遗留 JSON。
    assert set(folder.iterdir()) == {
        folder / MIGRATION_RECORD,
        folder / "legacy-json",
        *(folder / new for _, new, _ in CONFIG_FILES),
    }
    setting = folder / "setting.yaml"
    config_io.write_file(setting, {"Values": {"Revision": 4}})
    upgrade_json_configs(folder, nodes)
    assert config_io.read_dict_file(setting) == {"Values": {"Revision": 4}}


def test_unconvertible_collection_keeps_yaml_and_archive(tmp_path):
    nodes = {key: _Profile.build() for _, _, key in CONFIG_FILES}
    nodes["EmulatorConfig"] = ConfigCollection.build([EmulatorConfig])
    for old, _, _ in CONFIG_FILES:
        config_io.write_file(tmp_path / old, {})
    upgrade_json_configs(tmp_path, nodes)
    for old, _, _ in CONFIG_FILES:
        config_io.write_file(tmp_path / old, {})
    config_io.write_file(tmp_path / "EmulatorConfig.json", {"instances": "bad"})
    paths = [tmp_path / "emulators.yaml", tmp_path / "legacy-json/EmulatorConfig.json"]
    saved = {path: path.read_bytes() for path in paths}

    with pytest.raises(ValueError):
        upgrade_json_configs(tmp_path, nodes)

    assert saved == {path: path.read_bytes() for path in paths}


def test_retired_baah_plans_keep_other_plans_and_original_archive(tmp_path):
    """已升级用户启动时移除停用计划，保留其他专项及可恢复的原文件。"""
    from uuid import uuid4

    retired, retained = str(uuid4()), str(uuid4())
    document = {
        "order": [
            {"uid": retired, "type": "BAAHPlanConfig"},
            {"uid": retained, "type": "MSSPlanConfig"},
        ],
        "data": {
            retired: {"Info": {"Name": "legacy"}, "Day3": {"Key": {"Hard": [1, 2]}}},
            retained: {"Info": {"Name": "keep"}},
        },
    }
    path = tmp_path / "plans.yaml"
    config_io.write_file(path, document)
    original = path.read_bytes()

    retire_baah_plans(tmp_path)
    expected = {
        "order": [document["order"][1]],
        "data": {retained: document["data"][retained]},
    }
    assert config_io.read_dict_file(path) == expected
    archives = list((tmp_path / "retired-baah-plans").glob("*/plans.yaml"))
    assert len(archives) == 1
    assert archives[0].read_bytes() == original
    retire_baah_plans(tmp_path)
    assert config_io.read_dict_file(path) == expected
    assert archives == list((tmp_path / "retired-baah-plans").glob("*/plans.yaml"))


def test_retired_baah_plan_backup_failure_keeps_active_file(tmp_path, monkeypatch):
    """备份失败不能提前丢弃仍在使用的计划数据。"""
    from uuid import uuid4

    uid = str(uuid4())
    path = tmp_path / "plans.yaml"
    config_io.write_file(
        path,
        {"order": [{"uid": uid, "type": "BAAHPlanConfig"}], "data": {uid: {}}},
    )
    original = path.read_bytes()

    def fail_backup(*args, **kwargs):
        raise PermissionError("archive is read-only")

    monkeypatch.setattr(config_io, "atomic_write", fail_backup)
    with pytest.raises(PermissionError):
        retire_baah_plans(tmp_path)
    assert path.read_bytes() == original


def test_old_json_import_skips_retired_baah_plans_without_changing_source():
    """旧版 JSON 升级不再需要停用类型，其他计划照常导入。"""
    from copy import deepcopy
    from uuid import uuid4

    retired, retained = str(uuid4()), str(uuid4())
    document = {
        "instances": [
            {"uid": retired, "type": "BAAHPlanConfig"},
            {"uid": retained, "type": "_Profile"},
        ],
        retired: {"Day3": {"Key": {"Hard": [1, 2]}}},
        retained: {"Values": {"Revision": 7}},
    }
    original = deepcopy(document)
    converted = convert_legacy(document, ConfigCollection.build([_Profile]))
    assert converted == {
        "order": [{"uid": retained, "type": "_Profile"}],
        "data": {retained: {"Values": {"Revision": 7}}},
    }
    assert document == original


def test_startup_resumes_prepared_plan_migration_before_retirement(tmp_path):
    """旧迁移已换 YAML、归档 JSON 但未结账时，重启仍能完成并加载其他计划。"""
    import os
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    code = r"""
import asyncio
import hashlib
import sqlite3
from unittest.mock import AsyncMock

from app.core import Config
from app.config import config_manager
from app.core.config.upgrade import MIGRATION_RECORD
from app.utils import io

retired = '03051d8b-76d1-4e49-a8e1-0d63014e22e5'
retained = 'a958557a-4a37-48f6-af9a-d0c8499f1a92'
order = [{'uid': retired, 'type': 'BAAHPlanConfig'}, {'uid': retained, 'type': 'MaaEndPlanConfig'}]
data = {retired: {'Info': {'Name': 'old BAAH'}}, retained: {'Info': {'Name': 'keep MaaEnd'}}}
source = Config.config_path / 'legacy-json' / 'PlanConfig.json'
target = Config.config_path / 'plans.yaml'
io.write_file(source, {'instances': order, **data})
io.write_file(target, {'order': order, 'data': data})
original_json, original_yaml = source.read_bytes(), target.read_bytes()
io.write_file(Config.config_path / MIGRATION_RECORD, {
    'version': 2,
    'files': {'PlanConfig.json': {
        'target': 'plans.yaml',
        'source_sha256': hashlib.sha256(original_json).hexdigest(),
        'target_sha256': hashlib.sha256(original_yaml).hexdigest(),
        'state': 'prepared',
    }},
})
with sqlite3.connect(Config.database_path) as db:
    db.execute('CREATE TABLE version(v text)')
    db.execute("INSERT INTO version VALUES ('v1.11')")

async def run():
    await Config.check_data(prepare_plugins=AsyncMock())
    assert list(map(str, Config.PlanConfig.keys())) == [retained]
    assert Config.PlanConfig[retained].Info.Name == 'keep MaaEnd'
    record = io.read_dict_file(Config.config_path / MIGRATION_RECORD)
    assert record['complete'] and record['files']['PlanConfig.json']['state'] == 'complete'
    assert source.read_bytes() == original_json
    backups = list((Config.config_path / 'retired-baah-plans').glob('*/plans.yaml'))
    assert len(backups) == 1 and backups[0].read_bytes() == original_yaml
    await config_manager.flush()

asyncio.run(run())
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(root), "AUTO_MAS_ENV": "development"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_startup_finishes_account_migration_written_before_archive(tmp_path):
    """旧版写完账号 YAML 就退出时，重启按进度里的旧目标结账再改名。"""
    import os
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    code = r"""
import asyncio
import hashlib
import sqlite3
from unittest.mock import AsyncMock

from app.config import config_manager
from app.core import Config
from app.core.config.upgrade import MIGRATION_RECORD
from app.utils import io

uid = '6f1c9d3e-2b7a-4c58-9e21-8d4f5a6b7c80'
legacy_target = Config.config_path / 'game_sign_accounts.yaml'
source = Config.config_path / 'GameSignAccounts.json'
io.write_file(legacy_target, {
    'order': [{'uid': uid, 'type': 'GameSignAccountGroup'}],
    'data': {uid: {'GameSignAccount': {'Name': '旧账号'}}},
})
io.write_file(source, {
    'instances': [{'uid': uid, 'type': 'GameSignAccountGroup'}],
    uid: {'GameSignAccount': {'Name': '旧账号'}},
})
io.write_file(Config.config_path / MIGRATION_RECORD, {
    'version': 2,
    'files': {'GameSignAccounts.json': {
        'target': 'game_sign_accounts.yaml',
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'target_sha256': hashlib.sha256(legacy_target.read_bytes()).hexdigest(),
        'state': 'prepared',
    }},
})
with sqlite3.connect(Config.database_path) as db:
    db.execute('CREATE TABLE version(v text)')
    db.execute("INSERT INTO version VALUES ('v1.11')")

async def run():
    await Config.check_data(prepare_plugins=AsyncMock())
    accounts = list(Config.ToolsConfig.SignFlow_Accounts.values())
    assert len(accounts) == 1, accounts
    assert accounts[0].SignFlowAccount.Name == '旧账号'
    assert (Config.config_path / 'sign_flow_accounts.yaml').is_file()
    assert not legacy_target.exists()
    await config_manager.flush()

asyncio.run(run())
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(root), "AUTO_MAS_ENV": "development"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    # 二次启动必须复用已迁移的账号，不能按旧 JSON 重导一次。
    # 必须另起进程：同一进程里再跑 check_data 会重复订阅 (phase, kind, group, field, sender)。
    rerun = """
import asyncio
from unittest.mock import AsyncMock

from app.config import config_manager
from app.core import Config

async def run():
    await Config.check_data(prepare_plugins=AsyncMock())
    accounts = list(Config.ToolsConfig.SignFlow_Accounts.values())
    assert len(accounts) == 1, accounts
    assert accounts[0].SignFlowAccount.Name == '旧账号'
    await config_manager.flush()

asyncio.run(run())
"""
    again = subprocess.run(
        [sys.executable, "-c", rerun],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(root), "AUTO_MAS_ENV": "development"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert again.returncode == 0, again.stdout + again.stderr


def test_startup_finishes_account_migration_archived_before_version(tmp_path):
    """账号 JSON 已归档但数据库版本未推进时，重启仍能加载原账号。"""
    import os
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    code = r"""
import asyncio
import hashlib
import sqlite3
from unittest.mock import AsyncMock

from app.config import config_manager
from app.core import Config
from app.core.config.upgrade import MIGRATION_RECORD
from app.utils import io

uid = '2b8e4a51-9c37-4f60-8a1d-3e5b7c9d0f21'
legacy_target = Config.config_path / 'game_sign_accounts.yaml'
archived = Config.config_path / 'legacy-json' / 'GameSignAccounts.json'
io.write_file(legacy_target, {
    'order': [{'uid': uid, 'type': 'GameSignAccountGroup'}],
    'data': {uid: {'GameSignAccount': {'Name': '归档账号'}}},
})
io.write_file(archived, {
    'instances': [{'uid': uid, 'type': 'GameSignAccountGroup'}],
    uid: {'GameSignAccount': {'Name': '归档账号'}},
})
io.write_file(Config.config_path / MIGRATION_RECORD, {
    'version': 2,
    'files': {'GameSignAccounts.json': {
        'target': 'game_sign_accounts.yaml',
        'source_sha256': hashlib.sha256(archived.read_bytes()).hexdigest(),
        'target_sha256': hashlib.sha256(legacy_target.read_bytes()).hexdigest(),
        'state': 'complete',
    }},
})
with sqlite3.connect(Config.database_path) as db:
    db.execute('CREATE TABLE version(v text)')
    db.execute("INSERT INTO version VALUES ('v1.11')")

async def run():
    await Config.check_data(prepare_plugins=AsyncMock())
    accounts = list(Config.ToolsConfig.SignFlow_Accounts.values())
    assert len(accounts) == 1, accounts
    assert accounts[0].SignFlowAccount.Name == '归档账号'
    assert (Config.config_path / 'sign_flow_accounts.yaml').is_file()
    assert not legacy_target.exists()
    await config_manager.flush()

asyncio.run(run())
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(root), "AUTO_MAS_ENV": "development"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "recorded",
    ["sign_flow_accounts.yaml", "game_sign_accounts.yaml"],
    ids=["recorded-new-name", "recorded-legacy-name"],
)
def test_startup_resumes_remigration_written_to_legacy_name(tmp_path, recorded):
    """重迁内容落在旧名下时，续跑要按实际文件结账，不按进度里的名字判缺失。"""
    import os
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    code = r"""
import asyncio
import hashlib
import sqlite3
from unittest.mock import AsyncMock

from app.config import config_manager
from app.core import Config
from app.core.config.upgrade import MIGRATION_RECORD
from app.utils import io

recorded = __RECORDED__
uid = '9c4f0a17-3d52-4b6e-8f10-27ae5d3c9b64'
legacy_target = Config.config_path / 'game_sign_accounts.yaml'
source = Config.config_path / 'GameSignAccounts.json'
payload = {
    'order': [{'uid': uid, 'type': 'GameSignAccountGroup'}],
    'data': {uid: {'GameSignAccount': {'Name': '重迁账号'}}},
}
# 旧版中断形态：内容已经写进改名前的目标，进度停在 prepared。
io.write_file(legacy_target, payload)
io.write_file(source, {
    'instances': [{'uid': uid, 'type': 'GameSignAccountGroup'}],
    uid: {'GameSignAccount': {'Name': '重迁账号'}},
})
record_path = Config.config_path / MIGRATION_RECORD
io.write_file(record_path, {
    'version': 2,
    'files': {'GameSignAccounts.json': {
        'target': recorded,
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'target_sha256': hashlib.sha256(legacy_target.read_bytes()).hexdigest(),
        'state': 'prepared',
    }},
})
with sqlite3.connect(Config.database_path) as db:
    db.execute('CREATE TABLE version(v text)')
    db.execute("INSERT INTO version VALUES ('v1.11')")

async def run():
    await Config.check_data(prepare_plugins=AsyncMock())
    accounts = list(Config.ToolsConfig.SignFlow_Accounts.values())
    assert len(accounts) == 1, accounts
    assert accounts[0].SignFlowAccount.Name == '重迁账号'
    migrated = Config.config_path / 'sign_flow_accounts.yaml'
    assert migrated.is_file()
    assert not legacy_target.exists()
    entry = io.read_dict_file(record_path)['files']['GameSignAccounts.json']
    assert entry['state'] == 'complete', entry
    assert entry['target'] == 'game_sign_accounts.yaml', entry
    await config_manager.flush()

asyncio.run(run())
""".replace("__RECORDED__", repr(recorded))
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(root), "AUTO_MAS_ENV": "development"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_reset_targets_resume_keeps_written_documents(tmp_path):
    """reset_targets 重迁在归档之后中断时，续跑要保留已经写好的内容。"""
    import hashlib

    (tmp_path / "legacy-json").mkdir()

    nodes = {key: _Profile.build() for _, _, key in CONFIG_FILES}
    record = {"version": 2, "files": {}, "reset_targets": True}
    for old, new, _ in CONFIG_FILES:
        config_io.write_file(tmp_path / new, {"Values": {"Revision": 7}})
        config_io.write_file(
            tmp_path / "legacy-json" / old, {"Values": {"Revision": 5}}
        )
        record["files"][old] = {
            "target": new,
            "source_sha256": None,
            "target_sha256": hashlib.sha256((tmp_path / new).read_bytes()).hexdigest(),
            "state": "prepared",
        }
    config_io.write_file(tmp_path / MIGRATION_RECORD, record)

    upgrade_json_configs(tmp_path, nodes)

    for _, new, _ in CONFIG_FILES:
        assert config_io.read_dict_file(tmp_path / new) == {"Values": {"Revision": 7}}
    assert config_io.read_dict_file(tmp_path / MIGRATION_RECORD)["complete"] is True
