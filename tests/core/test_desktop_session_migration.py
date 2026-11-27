"""桌面分身清单：升级时并入托管旧的执行会话设置，删除托管或队列后清理条目。"""

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

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
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


_SEED = """
import asyncio, json
from app.config import config_manager
from app.core import Config
from app.models.config import GeneralConfig

async def run():
    await Config.check_data()
    ids = [
        Config.ScriptConfig.add(
            GeneralConfig,
            payload={"Info": {"Name": name}, "Run": {"ExecutionSession": session}},
        )
        for name, session in __SCRIPTS__
    ]
    await Config.ScriptConfig.commit()
    await config_manager.flush()
    (Config.work_path / "ids.json").write_text(json.dumps([str(i) for i in ids]))

asyncio.run(run())
"""

_START = """
import asyncio
from app.config import config_manager
from app.core import Config

# 专项配置回调由 main.py 绑定，这里只走配置启动链。
Config._get_script_config_handler = lambda script: None

async def run():
    await Config.check_data()
    await config_manager.flush()

asyncio.run(run())
"""


def _seed(profile: Path, scripts: list[tuple[str, str]]) -> list[str]:
    _run_config_startup(profile, _SEED.replace("__SCRIPTS__", repr(scripts)))
    return json.loads((profile / "ids.json").read_text())


def _as_upgraded_from_beta(config: Path, targets: list[str] | None = None) -> None:
    """旧版本的设置文件里没有桌面分身组。"""
    setting = config_io.read_dict_file(config / "setting.yaml")
    setting.pop("DesktopSession", None)
    if targets is not None:
        setting["DesktopSession"] = {"Targets": targets}
    config_io.write_file(config / "setting.yaml", setting)


def _desktop_session(config: Path) -> dict:
    return config_io.read_dict_file(config / "setting.yaml")["DesktopSession"]


def test_upgrade_absorbs_legacy_execution_session_once(tmp_path):
    config = tmp_path / "config"
    desktop, main, second = _seed(
        tmp_path, [("D1", "desktop"), ("M", "main"), ("D2", "desktop")]
    )
    # 新装：没有托管时直接置位，清单为空。
    assert _desktop_session(config) == {"Targets": [], "LegacyMigrated": True}

    # 插件不可用的托管旁挂保留，盘上原始数据里的设置同样并入。
    scripts = config_io.read_dict_file(config / "scripts.yaml")
    hidden = str(uuid4())
    scripts["order"].append({"uid": hidden, "type": "UnavailablePluginConfig"})
    scripts["data"][hidden] = {
        "Info": {"Name": "P"},
        "Run": {"ExecutionSession": "desktop"},
    }
    config_io.write_file(config / "scripts.yaml", scripts)
    _as_upgraded_from_beta(config)

    _run_config_startup(tmp_path, _START)
    assert _desktop_session(config) == {
        "Targets": [desktop, second, hidden],
        "LegacyMigrated": True,
    }
    # 托管上的字段原样保留，降级后旧版本照旧按它路由。
    saved = config_io.read_dict_file(config / "scripts.yaml")["data"]
    assert [saved[uid]["Run"]["ExecutionSession"] for uid in (desktop, main)] == [
        "desktop",
        "main",
    ]
    assert saved[hidden]["Run"]["ExecutionSession"] == "desktop"

    # 用户之后移出清单的托管，重启不会被加回来。
    setting = config_io.read_dict_file(config / "setting.yaml")
    setting["DesktopSession"]["Targets"] = [second]
    config_io.write_file(config / "setting.yaml", setting)
    _run_config_startup(tmp_path, _START)
    assert _desktop_session(config) == {"Targets": [second], "LegacyMigrated": True}


def test_upgrade_keeps_existing_targets_and_truncates_at_limit(tmp_path):
    config = tmp_path / "config"
    first, extra = _seed(tmp_path, [("D1", "desktop"), ("D2", "desktop")])
    existing = [str(uuid4()) for _ in range(99)]
    _as_upgraded_from_beta(config, targets=[*existing, first])

    _run_config_startup(tmp_path, _START)
    # 已有的条目不重复，超出上限的不并入。
    assert _desktop_session(config) == {
        "Targets": [*existing, first],
        "LegacyMigrated": True,
    }
    assert extra not in _desktop_session(config)["Targets"]


def test_deleting_targets_cleans_list_without_failing_deletion(tmp_path):
    code = """
import asyncio
from unittest.mock import patch
from app.config import config_manager
from app.core import Config
from app.models.config import GeneralConfig, GlobalConfig

Config._get_script_config_handler = lambda script: None

async def add_targets():
    sid = Config.ScriptConfig.add(GeneralConfig, payload={"Info": {"Name": "S"}})
    await Config.ScriptConfig.commit()
    qid, _queue = await Config.add_queue(payload={"Info": {"Name": "Q"}})
    keep = Config.ScriptConfig.add(GeneralConfig, payload={"Info": {"Name": "K"}})
    await Config.ScriptConfig.commit()
    await Config.update_setting(
        {"DesktopSession": {"Targets": [str(sid), str(qid), str(keep)]}}
    )
    return sid, qid, keep

async def run():
    await Config.check_data()
    sid, qid, keep = await add_targets()
    await Config.del_script(str(sid))
    await Config.del_queue(str(qid))
    assert Config.setting.DesktopSession.Targets == [str(keep)]

    # 清理失败只记日志，删除本身照常完成。
    sid, qid, _ = await add_targets()

    async def broken(*args, **kwargs):
        raise OSError("disk full")

    with patch.object(GlobalConfig, "update", broken):
        await Config.del_script(str(sid))
        await Config.del_queue(str(qid))
    assert sid not in Config.ScriptConfig and qid not in Config.QueueConfig
    assert str(sid) in Config.setting.DesktopSession.Targets
    await config_manager.flush()

asyncio.run(run())
"""
    _run_config_startup(tmp_path, code)
