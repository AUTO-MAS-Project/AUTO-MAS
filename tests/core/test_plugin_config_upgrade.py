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
    backup_legacy_adapter_users,
    backup_legacy_maafw_documents,
    migrate_maa_update_channel,
    prepare_plugin_documents,
    required_adapter_plugins,
)
from app.utils import io as config_io


@pytest.mark.parametrize("filename", ["scripts.yaml", "ScriptConfig.json"])
@pytest.mark.parametrize(
    ("config_type", "name", "package"),
    [
        ("WhimboxConfig", "whimbox_adapter", "auto-mas-whimbox-adapter"),
        ("BetterGIConfig", "bettergi_adapter", "auto-mas-bettergi-adapter"),
        ("SrcConfig", "src_adapter", "auto-mas-src-adapter"),
        ("MaaFWConfig", "maafw_adapter", "auto-mas-maafw-adapter"),
        ("M9AConfig", "m9a_adapter", "auto-mas-m9a-adapter"),
        ("MSSConfig", "mss_adapter", "auto-mas-mss-adapter"),
        ("MSSPlanConfig", "mss_adapter", "auto-mas-mss-adapter"),
    ],
)
def test_upgrade_detects_only_collection_types(
    tmp_path, filename, config_type, name, package
):
    """仅实际旧托管触发安装，普通业务字符串不触发。"""
    path = tmp_path / filename
    config_io.write_file(path, {"order": [{"uid": str(uuid4()), "type": config_type}]})
    assert required_adapter_plugins(tmp_path) == {name: package}
    config_io.write_file(path, {"order": [], "notes": config_type})
    assert required_adapter_plugins(tmp_path) == {}


@pytest.mark.parametrize(
    ("adapter", "config_type"), [("src", "SrcConfig"), ("bettergi", "BetterGIConfig")]
)
def test_adapter_backup_preserves_original_even_without_indexed_body(
    tmp_path, adapter, config_type
):
    path = tmp_path / "scripts.yaml"
    sid = str(uuid4())
    config_io.write_file(
        path, {"order": [{"uid": sid, "type": config_type}], "data": {}}
    )
    original = path.read_bytes()
    backup_legacy_adapter_users(tmp_path, adapter, config_type)
    config_io.write_file(
        path,
        {"order": [{"uid": sid, "type": config_type}], "data": {sid: {"users": {}}}},
    )
    backup_legacy_adapter_users(tmp_path, adapter, config_type)
    assert (tmp_path / f"legacy-{adapter}-plugin" / path.name).read_bytes() == original


@pytest.mark.parametrize(
    ("filename", "config_type"),
    [("scripts.yaml", "M9AConfig"), ("plans.yaml", "MSSPlanConfig")],
)
def test_maafw_backup_preserves_first_original(tmp_path, filename, config_type):
    """MFW 一族首次接手前按字节备份，重试不覆盖；别的类型不备份。"""
    path = tmp_path / filename
    sid = str(uuid4())
    config_io.write_file(path, {"order": [{"uid": sid, "type": "OkwwConfig"}]})
    backup_legacy_maafw_documents(tmp_path)
    assert not (tmp_path / "legacy-maafw-plugin").exists()
    config_io.write_file(
        path, {"order": [{"uid": sid, "type": config_type}], "data": {sid: {}}}
    )
    original = path.read_bytes()
    backup_legacy_maafw_documents(tmp_path)
    config_io.write_file(
        path,
        {"order": [{"uid": sid, "type": config_type}], "data": {sid: {"users": {}}}},
    )
    backup_legacy_maafw_documents(tmp_path)
    assert (tmp_path / "legacy-maafw-plugin" / filename).read_bytes() == original


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
    assert required_adapter_plugins(tmp_path) == {"maa_adapter": "auto-mas-maa-adapter"}
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
    ("failure", "legacy", "current"),
    [
        ("none", False, False),
        ("install", False, False),
        ("flush", False, False),
        ("none", True, False),
        ("none", False, True),
        ("install", False, True),
    ],
)
def test_startup_installs_before_loading_and_commits_upgrade(
    tmp_path, failure, legacy, current
):
    """真实启动链在安装成功后迁移；失败保留旧版本，重启保留用户后续选择。"""
    source_root = Path(__file__).resolve().parents[2]
    code = r"""
import asyncio
import base64
import shutil
import sqlite3
import sys
from importlib import metadata
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

source = Path(sys.argv[1])
failure = sys.argv[2]
legacy = sys.argv[3] == "True"
current = sys.argv[4] == "True"
sys.path.insert(0, str(source / "plugins/auto_mas_core/src"))

from app.config import NodeState, config_manager
from app.core import Config, Plugin
from app.plugin import uv
from app.plugin.runtime import discover
from app.plugin.types import PluginState
from app.utils import io

# 发行包安装测试不应命中开发者源码目录中的同名插件。
source_projects = discover._source_projects
checkout_plugins = (source / "plugins").resolve()
discover._source_projects = lambda: {
    project for project in source_projects()
    if project.parent != checkout_plugins or project.name == "auto_mas_core"
}

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
        "order": [{"uid": sid, "type": "MaaConfig" if current else "MaaPluginConfig"}],
        "data": {sid: {
            "Info": {"Name": "原托管", "Path": str(native.parent)},
            **({"Update": {"TakeoverEnabled": False, "TakeoverMigrationVersion": 1, "Channel": "beta", "ChannelMigrationVersion": 1}} if current else {}),
            "users": {
                "order": [{"uid": uid, "type": "MaaUserConfig" if current else "MaaPluginUserConfig"}],
                "data": {uid: {"Info": {"Name": "原账号"}, "Stage": {"StageMode": pid}}},
            },
        }},
    })
    io.write_file(Config.config_path / "plans.yaml", {
        "order": [{"uid": pid, "type": "MaaPlanConfig" if current else "MaaPluginPlanConfig"}],
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
    if failure == "install" or current:
        # 已升级用户曾使用随附源码，来源移除后也应保留配置并改用发行包。
        rid = "95a9f348-8d8e-4d09-9eb8-d954bfdb4cc3"
        io.write_file(Config.config_path / "plugin_registry.yaml", {
            "order": [{"uid": rid, "type": "PluginRecord"}],
            "data": {rid: {"info": {
                "plugin_name": "maa_adapter", "package_name": "auto-mas-maa-adapter",
                "import_name": "maa_adapter", "source": "local" if current else "installed", "enabled": current,
            }}},
        })
    with sqlite3.connect(Config.database_path) as db:
        db.execute("CREATE TABLE version(v text)")
        db.execute("INSERT INTO version VALUES (?)", ("v2.2" if current else "v1.11" if legacy else "v2.1",))

script_file = Config.config_path / ("ScriptConfig.json" if fresh and legacy else "scripts.yaml")
original = script_file.read_bytes()
original_document = io.read_dict_file(script_file)
installed_marker = Path.cwd() / "adapter-installed"
visible = installed_marker.exists()
installed_before = visible
with sqlite3.connect(Config.database_path) as db:
    pending = db.execute("SELECT v FROM version").fetchone()[0] != "v2.2"
installs = []

async def install(spec, *, plugin_name, meta_id, dry_run=False, minimum=None):
    global visible
    assert spec == "auto-mas-maa-adapter>=0.1.4"
    installs.append(spec)
    if failure == "install":
        raise OSError("installation unavailable")
    site = uv.site_dir()
    shutil.copytree(source / ".test-plugins/maa_adapter", site / "maa_adapter", dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    distribution = next(item for item in metadata.distributions(path=[str(source / ".test-plugins")]) if item.metadata["Name"] == "auto-mas-maa-adapter")
    project = {"version": distribution.version, "dependencies": distribution.requires or []}
    info = site / f"auto_mas_maa_adapter-{project['version']}.dist-info"
    info.mkdir(exist_ok=True)
    (info / "METADATA").write_text("\n".join([
        "Metadata-Version: 2.1", "Name: auto-mas-maa-adapter", f"Version: {project['version']}",
        "Keywords: auto-mas-plugin, auto-mas-id:maa_adapter",
        *[f"Requires-Dist: {item}" for item in project["dependencies"]], "", "",
    ]), encoding="utf-8")
    (info / "RECORD").write_text("maa_adapter/__init__.py,,\n", encoding="utf-8")
    visible = True
    installed_marker.touch()

async def prepare():
    await Plugin.initialize()

async def run():
    flush = config_manager.flush if failure != "flush" else AsyncMock(side_effect=OSError("save unavailable"))
    # 迁移与生命周期走真实入口；依赖环境、装包传输及平台加解密在各自集成测试中覆盖。
    with (
        patch("app.config.fields.encrypted.dpapi_encrypt", side_effect=lambda value: base64.b64encode(value.encode()).decode()),
        patch("app.config.fields.encrypted.dpapi_decrypt", side_effect=lambda value: base64.b64decode(value).decode()),
        patch.object(uv, "install", install),
        patch.object(uv, "prepare_environment", AsyncMock()),
        patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=httpx.Response(200, json={}))),
        patch.object(config_manager, "flush", flush),
    ):
        try:
            if failure == "install" and current:
                # 已是插件化格式的数据：专项插件装不上不挡启动，托管与计划原样保留。
                await Config.check_data(prepare_plugins=prepare)
                assert Config.ScriptConfig.is_unresolved(sid)
                assert Config.PlanConfig.is_unresolved(pid)
                assert not Config.managed_configs_loaded()
                assert io.read_dict_file(script_file) == original_document
                with sqlite3.connect(Config.database_path) as db:
                    assert db.execute("SELECT v FROM version").fetchone()[0] == "v2.2"
                return
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
                    assert db.execute("SELECT v FROM version").fetchone()[0] == ("v2.2" if current else "v2.1")
                return
            assert failure == "none"
            if not current:
                backup = Config.config_path / "legacy-json/pre-upgrade"
                assert (backup / ("ScriptConfig.json" if legacy else "scripts.yaml")).is_file()
                with sqlite3.connect(backup / Config.database_path.name) as db:
                    assert db.execute("SELECT v FROM version").fetchone()[0] in ("v1.11", "v2.1")
            assert installs == ([] if installed_before else ["auto-mas-maa-adapter>=0.1.4"])
            script = Config.ScriptConfig[sid]
            assert script.Info.Name == "原托管"
            assert list(map(str, script.users.keys())) == [uid]
            assert str(script.users[uid].Stage.StageMode) == pid
            assert list(map(str, Config.PlanConfig.keys())) == [pid]
            assert script.Update.TakeoverMigrationVersion == 1
            assert script.Update.ChannelMigrationVersion == 1
            assert script.Update.TakeoverEnabled == pending
            assert script.Update.Channel == ("beta" if pending or current and not installed_before else "stable")
            assert Config.plugin_registry.by_name("maa_adapter").info.state == PluginState.ENABLED
            assert Config.plugin_registry.by_name("maa_adapter").info.source == "installed"
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
            [
                sys.executable,
                "-c",
                code,
                str(source_root),
                attempt,
                str(legacy),
                str(current),
            ],
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
