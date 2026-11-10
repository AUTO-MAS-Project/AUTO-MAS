import asyncio
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.task.OkNte.AutoProxy import AutoProxyTask


def test_run_book_initialized_before_prepare():
    """prepare() 中途失败时收尾仍可读取 run_book。"""
    uid = uuid.uuid4()
    script_info = SimpleNamespace(
        task_info=SimpleNamespace(),
        user_list=[SimpleNamespace(user_id=str(uid), name="用户")],
        current_index=0,
    )
    proxy = AutoProxyTask(
        script_info=script_info,
        script_config=SimpleNamespace(),
        user_config={uid: SimpleNamespace()},
        game_manager=None,
    )
    assert proxy.run_book is False


def _proxy(tmp_path: Path, log_path, config_path):
    exe = tmp_path / "ok-nte.exe"
    exe.touch()
    proxy = AutoProxyTask.__new__(AutoProxyTask)
    proxy.script_config = SimpleNamespace(
        Info=SimpleNamespace(RootPath=tmp_path),
        Script=SimpleNamespace(
            ScriptPath=exe, LogPath=log_path, ConfigPath=config_path
        ),
        Run=SimpleNamespace(ProxyTimesLimit=0),
        Game=SimpleNamespace(Enabled=False, Type="Client", LaunchBeforeTask=False),
    )
    proxy.task_info = SimpleNamespace(is_queue_task=False)
    proxy.cur_user_config = SimpleNamespace(Info=SimpleNamespace(RemainedDay=-1))
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


@pytest.mark.parametrize(
    ("enabled", "launch", "close", "retry"),
    [
        (False, False, True, True),
        (False, True, True, True),
        (False, True, False, False),
        (True, True, False, True),
        (True, False, False, False),
        (True, False, True, True),
    ],
)
def test_close_policy_is_independent_of_game_launch(enabled, launch, close, retry):
    from app.models.config import OkNteConfig

    proxy = AutoProxyTask.__new__(AutoProxyTask)
    proxy.script_config = OkNteConfig.model_validate(
        {
            "Game": {
                "Enabled": enabled,
                "LaunchBeforeTask": launch,
                "CloseOnFinish": close,
            }
        }
    )
    assert proxy._mas_should_close_game_after_success() is close
    assert proxy._mas_should_close_game_on_retry() is retry
