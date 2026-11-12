"""鸣潮登录过程中出现维护弹窗时终止切号，不误报登录成功。"""

import asyncio
import importlib
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from app.models.config.script import OkwwConfig, OkwwUserConfig
from tests.config_support import activate_config
from tests.runtime_support import create_runtime_tree

switch = importlib.import_module("app.task.Okww.tools.account_switch")


@pytest.fixture
def maintenance_screen(monkeypatch):
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(
        switch,
        "time",
        SimpleNamespace(
            monotonic=lambda: clock.now,
            sleep=lambda seconds: setattr(clock, "now", clock.now + seconds),
        ),
    )
    monkeypatch.setattr(switch, "_capture_window", lambda *args, **kwargs: frame)
    monkeypatch.setattr(
        switch._tool_ocr,
        "ocr_image",
        lambda image, roi=None: (
            [] if roi is not None else [("服务器未开放", (600, 450, 600, 60))]
        ),
    )
    return clock


def test_switch_stops_before_interacting_with_maintenance(
    monkeypatch, maintenance_screen
):
    def unexpected_input(*args, **kwargs):
        pytest.fail("维护弹窗出现后不应继续尝试返回登录")

    monkeypatch.setattr(switch, "_press_escape", unexpected_input)
    with pytest.raises(RuntimeError, match="服务器未开放") as error:
        switch._switch_to_login(123, lambda message: None)
    assert isinstance(error.value, switch.GameMaintenanceDetected)
    assert error.value.text == "服务器未开放"
    assert maintenance_screen.now < 3


def test_maintenance_after_login_is_not_login_success(maintenance_screen):
    with pytest.raises(RuntimeError, match="服务器未开放") as error:
        switch._wait_login_success(123)
    assert isinstance(error.value, switch.GameMaintenanceDetected)
    assert error.value.text == "服务器未开放"
    assert maintenance_screen.now < 3


@pytest.mark.asyncio
@pytest.mark.parametrize("inflight", [False, True])
async def test_login_maintenance_skips_proxy_without_retry(
    monkeypatch, tmp_path, maintenance_screen, inflight
):
    from app.task import base
    from app.task.Okww import AutoProxy as proxy_module
    from app.task.Okww.tools import launcher_start
    from app.utils import ProcessManager

    app_json = tmp_path / "data/apps/ok-ww/app.json"
    app_json.parent.mkdir(parents=True)
    app_json.write_text('{"current_version": "v3.8.0-beta.1"}', encoding="utf-8")

    uid = uuid.uuid4()
    _, script, user = await create_runtime_tree(
        script_id=str(uuid.uuid4()), user_id=str(uid)
    )
    config = OkwwConfig.model_validate(
        {
            "Info": {"RootPath": str(tmp_path)},
            "Game": {"Enabled": True, "AccountSwitchMethod": "MAS"},
            "Run": {"RunTimesLimit": 3},
        }
    )
    account = OkwwUserConfig.model_validate(
        {"Info": {"Id": "13012346220"}, "Notify": {"PushLogMode": "关闭"}}
    )
    await activate_config(config)
    await activate_config(account)
    game = ProcessManager()
    monkeypatch.setattr(game, "search_process", AsyncMock())
    monkeypatch.setattr(game, "kill", AsyncMock())
    monkeypatch.setattr(
        proxy_module.process, "kill_process", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        proxy_module.process, "is_process_stopped", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(proxy_module, "is_process_running", lambda name: True)
    monkeypatch.setattr(proxy_module, "find_client_pids", lambda *args: {123})
    # 游戏刚起窗的预检尚无维护画面；随后切号 OCR 才读到维护弹窗。
    monkeypatch.setattr(launcher_start, "_find_game_hwnd", lambda pids=None: None)
    monkeypatch.setattr(switch, "IS_WINDOWS", True)
    monkeypatch.setattr(switch, "pyautogui", SimpleNamespace(), raising=False)
    monkeypatch.setattr(switch, "_find_game_hwnd", lambda **kwargs: 123)
    monkeypatch.setattr(switch, "_activate_window", lambda hwnd: None)
    monkeypatch.setattr(switch, "_save_error_screenshot", lambda hwnd: None)
    monkeypatch.setattr(proxy_module.Publisher, "send", AsyncMock())
    monkeypatch.setattr(proxy_module.Notify, "send_notice", AsyncMock())
    start = AsyncMock()
    monkeypatch.setattr(proxy_module, "start_okww", start)
    monkeypatch.chdir(tmp_path)
    proxy = proxy_module.AutoProxyTask(script, config, {uid: account}, game)
    proxy.game_process_path = tmp_path / "Client-Win64-Shipping.exe"

    pending = None
    if inflight:
        # 前一账号的后台截图超时后仍在执行；切号已有明确维护结果，不能被采样门槛丢掉。
        pending = asyncio.create_task(asyncio.Event().wait())
        monkeypatch.setitem(base._INFLIGHT_DETECTIONS, script.script_id, pending)
    try:
        await proxy.main_task()
        await proxy._persist_user_run_result()
    finally:
        if pending is not None:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)

    assert user.status == "跳过"
    assert proxy.user_state(user).maintenance_skipped
    assert account.Data.LastProxyStatus == "维护中"
    assert not proxy.run_book
    assert len(user.log_record) == 1
    assert "服务器未开放" in proxy.cur_user_log.status
    start.assert_not_awaited()
