"""隔离验证数据版本驱动的一次性配置升级。"""

import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.config import AppConfig
from app.core import config_upgrade
from app.utils.io import read_dict_file, write_file


def prepare_config(tmp_path, monkeypatch, version):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config"
    config_path.mkdir()
    database_path = tmp_path / "data.db"
    if version is not None:
        with sqlite3.connect(database_path) as db:
            db.execute("CREATE TABLE version(v text)")
            db.execute("INSERT INTO version VALUES(?)", (version,))
    return SimpleNamespace(config_path=config_path, database_path=database_path)


def read_version(config):
    with sqlite3.connect(config.database_path) as db:
        return db.execute("SELECT v FROM version").fetchall()


@pytest.mark.asyncio
@pytest.mark.parametrize("version", [None, "v1.9", "v1.10", "v1.11"])
async def test_upgrade_chain_reaches_v2_once(tmp_path, monkeypatch, version):
    config = prepare_config(tmp_path, monkeypatch, version)
    source = config.config_path / "Config.json"
    write_file(source, {"Function": {"IfSilence": True}, "Data": {}})
    upgrade = Mock(wraps=config_upgrade.upgrade_json_configs)
    monkeypatch.setattr(config_upgrade, "upgrade_json_configs", upgrade)

    await AppConfig.check_data(config)

    assert read_version(config) == [("v2.0",)]
    assert read_dict_file(config.config_path / "setting.yaml")["function"]["if_silence"] is True
    assert (config.config_path / "legacy-json/Config.json").is_file()
    upgrade.assert_called_once_with(config.config_path)

    # 即使重新出现 JSON，v2.0 也不能再次调用旧格式迁移。
    write_file(source, {"Function": {"IfSilence": False}})
    await AppConfig.check_data(config)
    upgrade.assert_called_once_with(config.config_path)
    assert source.is_file()
    assert read_dict_file(config.config_path / "setting.yaml")["function"]["if_silence"] is True


@pytest.mark.asyncio
async def test_v2_skips_upgrade(tmp_path, monkeypatch):
    config = prepare_config(tmp_path, monkeypatch, "v2.0")
    upgrade = Mock(side_effect=AssertionError("不应再次迁移"))
    monkeypatch.setattr(config_upgrade, "upgrade_json_configs", upgrade)

    await AppConfig.check_data(config)

    upgrade.assert_not_called()
    assert read_version(config) == [("v2.0",)]


@pytest.mark.asyncio
async def test_failed_upgrade_retains_version_and_can_retry(tmp_path, monkeypatch):
    config = prepare_config(tmp_path, monkeypatch, "v1.11")
    source = config.config_path / "Config.json"
    write_file(source, {"Voice": {"Type": "invalid"}})

    with pytest.raises(ValueError):
        await AppConfig.check_data(config)

    assert read_version(config) == [("v1.11",)]
    assert source.is_file()
    assert not (config.config_path / "legacy-json/Config.json").exists()

    write_file(source, {"Function": {"IfSilence": True}})
    await AppConfig.check_data(config)
    assert read_version(config) == [("v2.0",)]
    assert (config.config_path / "legacy-json/Config.json").is_file()


@pytest.mark.asyncio
async def test_empty_install_advances_to_v2(tmp_path, monkeypatch):
    config = prepare_config(tmp_path, monkeypatch, None)

    await AppConfig.check_data(config)

    assert read_version(config) == [("v2.0",)]
    assert not (config.config_path / "legacy-json").exists()


@pytest.mark.asyncio
async def test_partial_upgrade_retries_remaining_files(tmp_path, monkeypatch):
    config = prepare_config(tmp_path, monkeypatch, "v1.11")
    write_file(config.config_path / "Config.json", {"Function": {"IfSilence": True}})
    write_file(config.config_path / "ToolsConfig.json", {})
    original_write = config_upgrade.write_file

    def fail_tools_write(path, payload):
        if path.name == "tools.yaml":
            raise OSError("模拟写入失败")
        original_write(path, payload)

    monkeypatch.setattr(config_upgrade, "write_file", fail_tools_write)
    with pytest.raises(OSError):
        await AppConfig.check_data(config)

    assert read_version(config) == [("v1.11",)]
    assert (config.config_path / "legacy-json/Config.json").is_file()
    assert (config.config_path / "ToolsConfig.json").is_file()
    write_file(config.config_path / "setting.yaml", {"function": {"if_silence": False}})

    monkeypatch.setattr(config_upgrade, "write_file", original_write)
    await AppConfig.check_data(config)

    assert read_version(config) == [("v2.0",)]
    assert (config.config_path / "legacy-json/ToolsConfig.json").is_file()
    assert read_dict_file(config.config_path / "setting.yaml")["function"]["if_silence"] is False
