import asyncio
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.task.OkNte.AutoProxy import AutoProxyTask


def _proxy(tmp_path: Path, log_path, config_path):
    exe = tmp_path / "ok-nte.exe"
    exe.touch()
    proxy = AutoProxyTask.__new__(AutoProxyTask)
    proxy.script_config = SimpleNamespace(
        Info=SimpleNamespace(RootPath=tmp_path),
        Script=SimpleNamespace(
            ScriptPath=exe,
            LogPath=log_path,
            ConfigPath=config_path,
            ConfigPathMode="Folder",
        ),
        Run=SimpleNamespace(ProxyTimesLimit=0),
        Game=SimpleNamespace(Enabled=False, Type="Client", LaunchBeforeTask=False),
    )
    proxy.task_info = SimpleNamespace(is_queue_task=False)
    proxy.cur_user_config = SimpleNamespace(
        Info=SimpleNamespace(RemainedDay=-1, PlanMode="Fixed")
    )
    proxy.native_base = False
    proxy._reset_daily_proxy_count = AsyncMock()
    return proxy


@pytest.mark.parametrize(
    ("log_path", "config_path", "expected"),
    [
        (None, "cfg", "请设置 OK-NTE 日志路径"),
        ("log", None, "请设置 OK-NTE 配置文件路径"),
        ("log", "cfg", "Pass"),
    ],
)
def test_check_rejects_missing_paths(tmp_path, log_path, config_path, expected):
    proxy = _proxy(
        tmp_path,
        tmp_path / log_path if log_path else None,
        tmp_path / config_path if config_path else None,
    )
    assert asyncio.run(proxy.check()) == expected


def test_file_plan_is_rejected_before_injection(tmp_path):
    proxy = _proxy(tmp_path, tmp_path / "log", tmp_path / "DailyRoutineTask.json")
    proxy.script_config.Script.ConfigPathMode = "File"
    proxy.cur_user_config.Info.PlanMode = str(uuid.uuid4())
    assert (
        asyncio.run(proxy.check())
        == "OK-NTE 计划需要文件夹配置模式，请选择日常配置所在文件夹"
    )
    assert not (tmp_path / "DailyRoutineTaskConfigs.json").exists()


@pytest.mark.parametrize("launch_before_task", [False, True])
def test_close_only_does_not_require_launcher(tmp_path, launch_before_task):
    proxy = _proxy(tmp_path, tmp_path / "log", tmp_path / "cfg")
    proxy.script_config.Game = SimpleNamespace(
        Enabled=True,
        Type="Client",
        LaunchBeforeTask=launch_before_task,
        CloseOnFinish=True,
        Path=None,
    )
    expected = "请设置异环启动器路径" if launch_before_task else "Pass"
    assert asyncio.run(proxy.check()) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("game", "expected"),
    [
        ({"Enabled": False, "LaunchBeforeTask": False, "CloseOnFinish": True}, False),
        ({"Enabled": True, "CloseOnFinish": True}, True),
        ({"Enabled": True, "CloseOnFinish": False}, False),
        ({}, False),
    ],
)
async def test_legacy_close_choice_survives_upgrade_and_later_opt_in(
    tmp_path, game, expected
):
    import json

    from app.models.config import OkNteConfig
    from tests.config_support import activate_config

    path = tmp_path / "oknte.yaml"
    path.write_text(json.dumps({"Game": game}), encoding="utf-8")
    config = await activate_config(OkNteConfig(), path)
    proxy = AutoProxyTask.__new__(AutoProxyTask)
    proxy.script_config = config
    assert proxy._mas_should_close_game_after_success() is expected
    assert proxy._mas_should_close_game_on_retry() is expected

    config.Game.Enabled = False
    config.Game.CloseOnFinish = True
    await config.commit()
    reloaded = await activate_config(OkNteConfig(), path)
    proxy.script_config = reloaded
    assert reloaded.Game.Enabled is False
    assert proxy._mas_should_close_game_after_success() is True
    assert proxy._mas_should_close_game_on_retry() is True
