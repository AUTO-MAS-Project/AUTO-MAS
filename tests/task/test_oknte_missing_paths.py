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


def test_persist_result_after_prepare_failure_does_not_raise():
    """prepare() 在设置 run_book 前抛错时，on_crash 的结果留存不应触发 AttributeError。"""
    uid = uuid.uuid4()
    user_item = SimpleNamespace(
        user_id=str(uid), name="用户", status="运行", maintenance_skipped=False
    )
    user_cfg = SimpleNamespace(
        Data=SimpleNamespace(LastTaskIndex=0, LastProxyStatus=""),
        commit=AsyncMock(),
    )
    script_info = SimpleNamespace(
        task_info=SimpleNamespace(), user_list=[user_item], current_index=0
    )
    proxy = AutoProxyTask(
        script_info=script_info,
        script_config=SimpleNamespace(),
        user_config={uid: user_cfg},
        game_manager=None,
    )

    asyncio.run(proxy._persist_user_run_result())

    assert user_cfg.Data.LastProxyStatus == "失败"
    assert user_item.status == "异常"
