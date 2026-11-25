"""空白用户目录的配置启动与落盘，资源仍从源码目录读取。"""

import os
import subprocess
import sys
from pathlib import Path

import pytest


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
        assert not Config.ToolsConfig.GameSign_Accounts
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
