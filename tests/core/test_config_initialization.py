"""空白用户目录的配置启动与落盘，资源仍从源码目录读取。"""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.utils import io as config_io


def _run_config_startup(profile: Path, code: str) -> None:
    source_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=profile,
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


@pytest.mark.parametrize("power_supported", [True, False])
def test_empty_profile_initializes_user_data_separately_from_source(
    tmp_path, power_supported
):
    code = """
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from app.config import NodeState
from app.core import Config
from app.utils import power, startup as startup_tool
from app.services import telemetry

root = Path.cwd()
assert Config.work_path == root
assert Config.resource_path == Config.source_path / "res"
assert (Config.resource_path / "version.json").is_file()
for name, directory in {
    "config_path": "config", "data_path": "data", "debug_path": "debug", "temp_path": "temp",
    "history_path": "history", "script_path": "script", "plugins_path": "plugins",
}.items():
    assert getattr(Config, name) == root / directory, name
assert Config.log_path == Config.debug_path / "app.log"
assert Config.database_path == Config.data_path / "data.db"
os.chdir(Config.source_path)
assert Config.config_path == root / "config"
assert Config.data_path == root / "data"
assert Config.temp_path == root / "temp"
assert Config.resource_path != root / "res"
os.chdir(root)

async def run():
    with (
        patch.object(startup_tool, 'set_enabled', new_callable=AsyncMock) as startup,
        patch.object(power, 'supported', __POWER_SUPPORTED__),
        patch.object(power, 'set_sleep_prevention', new_callable=AsyncMock) as sleep,
        patch.object(telemetry, 'set_telemetry_enabled', new_callable=Mock),
    ):
        await Config.init_config()
        if Config.temp_task:
            await asyncio.gather(*tuple(Config.temp_task))
        await Config.flush()
        startup.assert_not_awaited()
        if power.supported:
            sleep.assert_awaited_once_with(Config.setting.Function.IfAllowSleep)
        else:
            sleep.assert_not_awaited()
        assert Config.setting.activation_state == NodeState.ACTIVE
        assert Config.ToolsConfig.activation_state == NodeState.ACTIVE
        assert Config.config_path == Path.cwd() / 'config'
        assert (Config.config_path / 'setting.yaml').is_file()
        assert (Config.config_path / 'tools.yaml').is_file()
        assert not Config.ScriptConfig
        assert not Config.ToolsConfig.SignFlow_Accounts
        assert 'app.core.maa_manager' not in sys.modules

asyncio.run(run())
"""
    _run_config_startup(
        tmp_path, code.replace("__POWER_SUPPORTED__", repr(power_supported))
    )


def test_offline_first_start_does_not_retry_default_plugins_on_restart(tmp_path):
    code = """
import asyncio
from unittest.mock import AsyncMock, patch

from app.core import Config, Plugin
from app.plugin import uv
from app.plugin.errors import PluginError
from app.plugin.runtime import discover
from app.utils import power

attempted = set()

async def unavailable(spec, **kwargs):
    attempted.add(spec)
    raise PluginError("PyPI unavailable")

async def run():
    core = Config.source_path / "plugins" / "auto_mas_core"
    with (
        patch.object(discover, "_source_projects", return_value={core}),
        patch.object(uv, "install", unavailable),
        patch.object(power, "set_sleep_prevention", AsyncMock()),
    ):
        try:
            await Config.init_config(prepare_plugins=Plugin.initialize)
            assert Config.database_path.is_file()
            assert attempted == __EXPECTED_SPECS__, attempted
        finally:
            await Plugin.shutdown()

asyncio.run(run())
"""
    expected = {
        "auto-mas-mumu-adapter>=0.1.1",
        "auto-mas-ldplayer-adapter>=0.1.1",
        "auto-mas-general-emulator-adapter",
        "auto-mas-win-process-adapter",
    }
    _run_config_startup(tmp_path, code.replace("__EXPECTED_SPECS__", repr(expected)))
    _run_config_startup(tmp_path, code.replace("__EXPECTED_SPECS__", "set()"))


def test_one_unreadable_managed_does_not_block_startup(tmp_path):
    """已升级数据里一条托管读不进来只隔离它，照常启动；旧格式升级照旧拒绝推进版本。"""
    seed = """
import asyncio, json
from app.config import config_manager
from app.core import Config
from app.models.config import GeneralConfig, QueueItem

async def run():
    await Config.check_data()
    ids = [
        Config.ScriptConfig.add(GeneralConfig, payload={"Info": {"Name": name}})
        for name in ("G1", "BAD", "G2")
    ]
    await Config.ScriptConfig.commit()
    qid, queue = await Config.add_queue(payload={"Info": {"Name": "Q"}})
    for target in ids:
        queue.QueueItem.add(QueueItem, payload={"Info": {"ScriptId": str(target)}})
    await queue.QueueItem.commit()
    await config_manager.flush()
    (Config.work_path / "ids.json").write_text(json.dumps([str(i) for i in ids] + [str(qid)]))

asyncio.run(run())
"""
    start = """
import asyncio, json
from app.config import config_manager
from app.core import Config

# 专项配置回调由 main.py 绑定，这里只走配置启动链。
Config._get_script_config_handler = lambda script: None
g1, bad, g2, qid = json.loads((Config.work_path / "ids.json").read_text())

async def run():
    try:
        await Config.check_data()
    except Exception as exc:
        # 拒绝时要点名是哪一条，用户才知道去修哪份配置。
        assert __LEGACY__ and bad in str(exc), exc
        return
    assert not __LEGACY__
    assert [str(uid) for uid in Config.ScriptConfig.keys()] == [g1, g2]
    assert [(i["uid"], i["reason"]) for i in Config.unavailable_scripts()] == [
        (bad, "load_failed")
    ]
    assert not Config.managed_configs_loaded()
    assert [
        str(item.Info.ScriptId) for item in Config.QueueConfig[qid].QueueItem.values()
    ] == [g1, bad, g2]
    await config_manager.flush()

asyncio.run(run())
"""
    _run_config_startup(tmp_path, seed)
    ids = json.loads((tmp_path / "ids.json").read_text())
    config = tmp_path / "config"
    scripts = config_io.read_dict_file(config / "scripts.yaml")
    # 类型照旧是已登记的 GeneralConfig，只是这一条的值读不进来。
    scripts["data"][ids[1]]["Game"]["WaitTime"] = "oops"
    config_io.write_file(config / "scripts.yaml", scripts)
    files = ("scripts.yaml", "queues.yaml")
    original = {name: (config / name).read_bytes() for name in files}

    def data_version(value=None):
        with sqlite3.connect(tmp_path / "data" / "data.db") as db:
            if value is not None:
                db.execute("UPDATE version SET v = ?", (value,))
            return db.execute("SELECT v FROM version").fetchone()[0]

    assert data_version("v2.1") == "v2.1"
    _run_config_startup(tmp_path, start.replace("__LEGACY__", "True"))
    assert data_version() == "v2.1"
    assert {name: (config / name).read_bytes() for name in files} == original

    assert data_version("v2.2") == "v2.2"
    _run_config_startup(tmp_path, start.replace("__LEGACY__", "False"))
    assert {name: (config / name).read_bytes() for name in files} == original


def test_unreadable_managed_summary_omits_config_values(tmp_path):
    """读不了的托管：给界面、启动提示、日志和升级拒绝的原因只有字段路径和错误类别，不带原值。"""
    secret = "whsec-LEAK-0123456789abcdef"
    seed = """
import asyncio, json
from app.config import config_manager
from app.core import Config
from app.models.config import GeneralConfig

async def run():
    await Config.check_data()
    uid = Config.ScriptConfig.add(GeneralConfig, payload={"Info": {"Name": "BAD"}})
    await Config.ScriptConfig.commit()
    await config_manager.flush()
    (Config.work_path / "ids.json").write_text(json.dumps([str(uid)]))

asyncio.run(run())
"""
    start = """
import asyncio, json
from app.config import config_manager
from app.core import Config

Config._get_script_config_handler = lambda script: None
(bad,) = json.loads((Config.work_path / "ids.json").read_text())
SECRET = __SECRET__

async def run():
    try:
        await Config.check_data()
    except Exception as exc:
        assert __LEGACY__, exc
        text = str(exc)
        assert SECRET not in text, text
        assert bad in text and "WaitTime" in text and "int_parsing" in text, text
        return
    assert not __LEGACY__
    (item,) = Config.unavailable_scripts()
    assert item["reason"] == "load_failed"
    assert SECRET not in item["detail"], item["detail"]
    assert "WaitTime" in item["detail"] and "int_parsing" in item["detail"], item
    notices = json.dumps(Config.startup_notices, ensure_ascii=False)
    assert SECRET not in notices, notices
    await config_manager.flush()

asyncio.run(run())
""".replace("__SECRET__", repr(secret))
    _run_config_startup(tmp_path, seed)
    (bad,) = json.loads((tmp_path / "ids.json").read_text())
    config = tmp_path / "config"
    scripts = config_io.read_dict_file(config / "scripts.yaml")
    scripts["data"][bad]["Game"]["WaitTime"] = secret
    config_io.write_file(config / "scripts.yaml", scripts)
    log = tmp_path / "debug" / "app.log"

    with sqlite3.connect(tmp_path / "data" / "data.db") as db:
        db.execute("UPDATE version SET v = ?", ("v2.1",))
    _run_config_startup(tmp_path, start.replace("__LEGACY__", "True"))

    with sqlite3.connect(tmp_path / "data" / "data.db") as db:
        db.execute("UPDATE version SET v = ?", ("v2.2",))
    _run_config_startup(tmp_path, start.replace("__LEGACY__", "False"))
    # 原文照旧原样留在盘上，供恢复。
    saved = config_io.read_dict_file(config / "scripts.yaml")
    assert saved["data"][bad]["Game"]["WaitTime"] == secret
    text = log.read_text(encoding="utf-8", errors="replace")
    assert f"配置读不了，原样保留：GeneralConfig {bad}" in text
    assert "WaitTime" in text
    assert secret not in text


_QUEUE_UID = "a63ae3c5-4edd-4e21-bb35-a1ab009e8498"
_QUEUE_ORDER = [{"uid": _QUEUE_UID, "type": "QueueConfig"}]


@pytest.mark.parametrize(
    ("filename", "payload", "field"),
    [
        ("setting.yaml", {"Function": False}, "Function"),
        ("queues.yaml", {"order": {}, "data": {}}, "order"),
        ("queues.yaml", {"order": _QUEUE_ORDER, "data": []}, "data"),
        ("queues.yaml", {"order": _QUEUE_ORDER, "data": {_QUEUE_UID: 0}}, _QUEUE_UID),
        (
            "queues.yaml",
            {"order": _QUEUE_ORDER, "data": {_QUEUE_UID: {"QueueItem": []}}},
            "QueueItem",
        ),
    ],
    ids=["group", "order", "data", "member", "nested-collection"],
)
def test_malformed_config_blocks_upgrade_and_preserves_file(
    tmp_path, filename, payload, field
):
    code = f"""
import asyncio
import sqlite3
from contextlib import closing

from app.config import config_manager
from app.config.errors import ConfigAggregateError
from app.core import Config
from app.utils import io

path = Config.config_path / {filename!r}
io.write_file(path, {payload!r})
original = path.read_bytes()
with closing(sqlite3.connect(Config.database_path)) as db:
    db.execute("CREATE TABLE version(v text)")
    db.execute("INSERT INTO version VALUES ('v2.1')")
    db.commit()

async def run():
    try:
        await Config.check_data()
    except (ConfigAggregateError, TypeError) as error:
        assert {field!r} in str(error), error
        assert isinstance(error, TypeError) or "TypeError" in str(error), error
    else:
        raise AssertionError("错型配置未阻断迁移")
    assert path.read_bytes() == original
    with closing(sqlite3.connect(Config.database_path)) as db:
        assert db.execute("SELECT v FROM version").fetchone() == ("v2.1",)

    # 退出时也会 flush，不能把部分激活结果覆盖到原配置。
    await config_manager.flush()
    assert path.read_bytes() == original

asyncio.run(run())
"""
    _run_config_startup(tmp_path, code)
