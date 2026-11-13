"""主程序插件化升级的来源识别、配置迁移与重试语义。"""

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from maa_adapter.config.script import MaaConfig

from app.core.config.plugin_upgrade import (
    migrate_maa_update_channel,
    prepare_plugin_documents,
    required_adapter_plugins,
)
from app.utils import io as config_io


@pytest.mark.parametrize("legacy", [False, True])
def test_plugin_upgrade_preserves_documents_and_backup(tmp_path, legacy):
    """转换 JSON/YAML 类型索引并保留身份、用户输入及原始备份，重复准备不覆盖备份。"""
    sid, uid = str(uuid4()), str(uuid4())
    index = "instances" if legacy else "order"
    user = {index: [{"uid": uid, "type": "MaaPluginUserConfig"}]}
    if legacy:
        user[uid] = {"Info": {"Name": "账号"}}
    else:
        user["data"] = {uid: {"Info": {"Name": "账号"}}}
    script = {"Info": {"Name": "MaaPluginConfig"}, "users": user}
    document = {index: [{"uid": sid, "type": "MaaPluginConfig"}]}
    if legacy:
        document[sid] = script
    else:
        document["data"] = {sid: script}
    path = tmp_path / ("ScriptConfig.json" if legacy else "scripts.yaml")
    config_io.write_file(path, document)
    original = path.read_bytes()
    assert required_adapter_plugins(tmp_path) == {"maa_adapter": "auto-mas-maa"}
    prepare_plugin_documents(tmp_path)
    converted = config_io.read_dict_file(path)
    assert converted[index] == [{"uid": sid, "type": "MaaConfig"}]
    converted_script = (converted if legacy else converted["data"])[sid]
    assert converted_script["Info"]["Name"] == "MaaPluginConfig"
    assert converted_script["users"][index] == [{"uid": uid, "type": "MaaUserConfig"}]
    assert converted_script["Update"] == {
        "TakeoverMigrationVersion": 0,
        "ChannelMigrationVersion": 0,
    }
    once = path.read_bytes()
    prepare_plugin_documents(tmp_path)
    assert path.read_bytes() == once
    assert (tmp_path / "legacy-plugin" / path.name).read_bytes() == original
    config_io.write_file(path, {index: [], "notes": "MaaConfig"})
    assert required_adapter_plugins(tmp_path) == {}


@pytest.mark.parametrize(
    ("failure", "legacy"),
    [("none", False), ("install", False), ("flush", False), ("none", True)],
)
def test_startup_installs_before_loading_and_commits_upgrade(tmp_path, failure, legacy):
    """真实启动链在安装成功后迁移；失败保留旧版本，重启保留用户后续选择。"""
    source_root = Path(__file__).resolve().parents[2]
    code = r"""
import asyncio
import sqlite3
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

source = Path(sys.argv[1])
failure = sys.argv[2]
legacy = sys.argv[3] == "True"
for package in ("auto_mas_core", "maa_adapter"):
    sys.path.insert(0, str(source / "plugins" / package / "src"))

from app.config import NodeState, config_manager
from app.core import Config, Plugin
from app.plugin import uv
from app.plugin.runtime import discover
from app.plugin.types import PluginState
from app.utils import io

sid = "e1821d2b-bbb8-4ac5-ad7c-e445c8324aa0"
uid = "0896c0be-e2a8-4c38-bb3b-10eca7768405"
pid = "5924194a-fcc0-49b6-8a2b-f1d1875def93"
fresh = not Config.database_path.exists()
if fresh:
    native = Path.cwd().with_name(Path.cwd().name + "-maa") / "config"
    native.mkdir(parents=True)
    io.write_file(native / "gui.new.json", {"Update": {"VersionType": "Beta"}})
    io.write_file(Config.config_path / "setting.yaml", {"Update": {"MirrorChyanCDK": "test-cdk"}})
    io.write_file(Config.config_path / "scripts.yaml", {
        "order": [{"uid": sid, "type": "MaaPluginConfig"}],
        "data": {sid: {
            "Info": {"Name": "原托管", "Path": str(native.parent)},
            "users": {
                "order": [{"uid": uid, "type": "MaaPluginUserConfig"}],
                "data": {uid: {"Info": {"Name": "原账号"}, "Stage": {"StageMode": pid}}},
            },
        }},
    })
    io.write_file(Config.config_path / "plans.yaml", {
        "order": [{"uid": pid, "type": "MaaPluginPlanConfig"}],
        "data": {pid: {"Info": {"Name": "原计划"}}},
    })
    if legacy:
        for old, new in (("Config.json", "setting.yaml"), ("ScriptConfig.json", "scripts.yaml"), ("PlanConfig.json", "plans.yaml")):
            document = io.read_dict_file(Config.config_path / new)
            if "order" in document:
                document = {"instances": document["order"], **document["data"]}
            if sid in document:
                user = document[sid].pop("users")
                document[sid]["SubConfigsInfo"] = {"UserData": {"instances": user["order"], **user["data"]}}
            io.write_file(Config.config_path / old, document)
            (Config.config_path / new).unlink()
    if failure == "install":
        # 旧注册记录仍在但安装文件缺失，也必须重新安装，不能只重试 load。
        rid = "95a9f348-8d8e-4d09-9eb8-d954bfdb4cc3"
        io.write_file(Config.config_path / "plugin_registry.yaml", {
            "order": [{"uid": rid, "type": "PluginRecord"}],
            "data": {rid: {"info": {
                "plugin_name": "maa_adapter", "package_name": "auto-mas-maa",
                "import_name": "maa_adapter", "source": "installed", "enabled": False,
            }}},
        })
    with sqlite3.connect(Config.database_path) as db:
        db.execute("CREATE TABLE version(v text)")
        db.execute("INSERT INTO version VALUES (?)", ("v1.11" if legacy else "v2.1",))

script_file = Config.config_path / ("ScriptConfig.json" if fresh and legacy else "scripts.yaml")
original = script_file.read_bytes()
installed_marker = Path.cwd() / "adapter-installed"
visible = installed_marker.exists()
installed_before = visible
with sqlite3.connect(Config.database_path) as db:
    pending = db.execute("SELECT v FROM version").fetchone()[0] != "v2.2"
parse_source = discover._parse_source_package
installs = []

async def available(path):
    if path.name == "maa_adapter" and not visible:
        return None
    return await parse_source(path)

async def install(spec, *, dry_run=False):
    global visible
    assert spec == "auto-mas-maa"
    installs.append(spec)
    if failure == "install":
        raise OSError("installation unavailable")
    visible = True
    installed_marker.touch()

async def prepare():
    await Plugin.initialize()

async def run():
    flush = config_manager.flush if failure != "flush" else AsyncMock(side_effect=OSError("save unavailable"))
    with (
        patch.object(discover, "_parse_source_package", available),
        patch.object(uv, "install", install),
        patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=httpx.Response(200, json={}))),
        patch.object(config_manager, "flush", flush),
    ):
        try:
            try:
                await Config.check_data(prepare_plugins=prepare)
            except OSError as exc:
                assert failure in ("install", "flush")
                if failure == "install":
                    assert str(exc) == "installation unavailable"
                    assert Config.ScriptConfig.activation_state == NodeState.INACTIVE
                    assert (Config.config_path / "scripts.yaml").read_bytes() == original
                else:
                    assert str(exc) == "save unavailable"
                with sqlite3.connect(Config.database_path) as db:
                    assert db.execute("SELECT v FROM version").fetchone()[0] == "v2.1"
                return
            assert failure == "none"
            assert installs == ([] if installed_before else ["auto-mas-maa"])
            script = Config.ScriptConfig[sid]
            assert script.Info.Name == "原托管"
            assert list(map(str, script.users.keys())) == [uid]
            assert str(script.users[uid].Stage.StageMode) == pid
            assert list(map(str, Config.PlanConfig.keys())) == [pid]
            assert script.Update.TakeoverMigrationVersion == 1
            assert script.Update.ChannelMigrationVersion == 1
            assert script.Update.TakeoverEnabled == pending
            assert script.Update.Channel == ("beta" if pending else "stable")
            assert Config.plugin_registry.by_name("maa_adapter").info.state == PluginState.ENABLED
            with sqlite3.connect(Config.database_path) as db:
                assert db.execute("SELECT v FROM version").fetchone()[0] == "v2.2"
            await script.update(type(script).model_validate({"Update": {"TakeoverEnabled": False, "Channel": "stable"}}))
            await config_manager.flush()
        finally:
            await Plugin.shutdown()

asyncio.run(run())
"""
    for attempt in ["none", "none"] if failure == "none" else [failure, "none", "none"]:
        result = subprocess.run(
            [sys.executable, "-c", code, str(source_root), attempt, str(legacy)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={
                **os.environ,
                "PYTHONPATH": str(source_root),
                "PYTHONIOENCODING": "utf-8",
                "AUTO_MAS_ENV": "development",
            },
            timeout=45,
        )
        assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", ["stable", "beta"])
async def test_existing_channel_is_migrated_once(tmp_path, channel):
    from tests.config_support import activate_config

    config_root = tmp_path / "maa" / "config"
    config_root.mkdir(parents=True)
    (config_root / "gui.new.json").write_text(
        json.dumps({"Update": {"VersionType": channel.title()}}), encoding="utf-8"
    )
    config = MaaConfig.build(
        payload={
            "Info": {"Path": str(config_root.parent)},
            "Update": {
                "TakeoverEnabled": True,
                "TakeoverMigrationVersion": 1,
                "ChannelMigrationVersion": 0,
            },
        }
    )
    await activate_config(config)
    assert config.Update.ChannelMigrationVersion == 0
    await migrate_maa_update_channel(config, data_path=tmp_path / "data")
    assert config.Update.Channel == channel
    assert config.Update.ChannelMigrationVersion == 1
    # A later user choice is authoritative even if the native GUI still says Beta.
    await config.update(type(config).model_validate({"Update": {"Channel": "stable"}}))
    await migrate_maa_update_channel(config, data_path=tmp_path / "data")
    assert config.Update.Channel == "stable"


@pytest.mark.asyncio
async def test_explicit_channel_does_not_trigger_migration(tmp_path):
    from tests.config_support import activate_config

    config = MaaConfig.build(payload={"Update": {"Channel": "beta"}})
    await activate_config(config)
    assert config.Update.ChannelMigrationVersion == 1
    await migrate_maa_update_channel(config, data_path=tmp_path / "data")
    assert config.Update.Channel == "beta"
