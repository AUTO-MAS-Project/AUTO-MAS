"""鸣潮登录过程中出现维护弹窗时终止切号，不误报登录成功。"""

import importlib
import os
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from app.models.config.script import OkwwConfig, OkwwUserConfig
from app.models.task import TaskItem, TaskScriptItem, TaskUserItem
from tests.config_support import activate_config

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


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "nt", reason="Windows 分身执行器")
async def test_desktop_login_maintenance_skips_proxy_without_retry(
    monkeypatch, tmp_path, maintenance_screen
):
    from app.task.Okww import AutoProxy as proxy_module
    from app.task.Okww.tools import launcher_start
    from app.utils import ProcessManager

    app_json = tmp_path / "data/apps/ok-ww/app.json"
    app_json.parent.mkdir(parents=True)
    app_json.write_text('{"current_version": "v3.8.0-beta.1"}', encoding="utf-8")

    uid = uuid.uuid4()
    root = TaskItem()
    await root.activate()
    script_id = root.scripts.add(
        TaskScriptItem,
        payload={"info": {"script_id": str(uuid.uuid4()), "name": "Script"}},
    )
    await root.scripts.commit()
    script = root.scripts[script_id]
    user_id = script.users.add(
        TaskUserItem, payload={"info": {"user_id": str(uid), "name": "User"}}
    )
    await script.users.commit()
    await root.set_current_index(0)
    user = script.users[user_id]
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
    monkeypatch.setattr(
        proxy_module, "has_process_window", AsyncMock(return_value=True)
    )
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

    from collections import deque
    from unittest.mock import Mock

    from app.task import desktop_session_worker
    from app.utils.common.process import session
    from app.utils.windows.desktop_session import launcher, native, process_runner

    frames = deque()
    fake_pipe = Mock()
    monkeypatch.setattr(session, "_parent_scope", None)
    monkeypatch.setattr(native, "set_dpi_awareness", lambda: None)
    monkeypatch.setattr(desktop_session_worker, "process_session", lambda pid: 7)
    monkeypatch.setattr(
        desktop_session_worker, "send", lambda pipe, frame: frames.append(frame)
    )
    monkeypatch.setattr(
        process_runner,
        "read_chunk",
        lambda pipe: next(launcher.message_chunks(frames.popleft())),
    )
    monkeypatch.setattr(
        process_runner.win32pipe,
        "PeekNamedPipe",
        lambda pipe, size: (b"", len(frames), 0),
    )
    monkeypatch.setattr(process_runner, "_wait_worker", lambda worker: None)

    async def launch(target, request, *, on_log, worker_module, on_restart):
        monkeypatch.setattr(desktop_session_worker, "receive", lambda pipe: request)
        desktop_session_worker.run_action(fake_pipe)
        return process_runner.DesktopProcess(
            frames.popleft()["pid"], fake_pipe, Mock(), on_log, on_restart=on_restart
        )

    launch_spy = AsyncMock(side_effect=launch)
    monkeypatch.setattr(process_runner, "_launch", launch_spy)
    token = session.desktop_process_target.set(
        session.DesktopProcessTarget(7, tmp_path, tmp_path)
    )

    try:
        await proxy.main_task()
        await proxy._persist_user_run_result()
    finally:
        session.desktop_process_target.reset(token)

    assert user.status == "跳过"
    assert account.Data.LastProxyStatus == "维护中"
    assert len(user.log_record) == 1
    assert "服务器未开放" in proxy.cur_user_log.status
    start.assert_not_awaited()
    assert [call.args[1]["action"] for call in launch_spy.await_args_list] == [
        "okww_detect_maintenance",
        "okww_switch_account",
    ]
