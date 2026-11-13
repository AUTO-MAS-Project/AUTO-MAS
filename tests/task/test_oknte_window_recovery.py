"""异环更新销毁窗口时重新定位，其他截图错误仍向上传递。"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.task.OkNte.tools import account_switch as switch

pytestmark = pytest.mark.skipif(not switch.IS_WINDOWS, reason="Windows 窗口生命周期")


@pytest.mark.parametrize("window_alive", [False, True])
def test_capture_win32_error_recovers_only_destroyed_window(monkeypatch, window_alive):
    error = switch.win32gui.error(1400, "GetClientRect", "Invalid window handle")
    monkeypatch.setattr(switch.win32gui, "IsWindow", lambda hwnd: window_alive)
    monkeypatch.setattr(switch, "_capture_window", Mock(side_effect=[error, object()]))
    monkeypatch.setattr(switch, "_frame_signature", lambda frame: 1)
    monkeypatch.setattr(
        switch,
        "_tool_ocr",
        SimpleNamespace(
            ocr_image=lambda frame: [("使用其他方式登录", (100, 100, 200, 30))]
        ),
    )
    monkeypatch.setattr(switch, "_dump_ocr_items", lambda items: None)
    monkeypatch.setattr(
        switch.win32gui, "EnumWindows", lambda callback, arg: callback(20, arg)
    )
    monkeypatch.setattr(switch.win32gui, "IsWindowVisible", lambda hwnd: True)
    monkeypatch.setattr(
        switch.win32process, "GetWindowThreadProcessId", lambda hwnd: (1, 2)
    )
    monkeypatch.setattr(switch, "_process_name", lambda pid: switch._NTE_CLIENT_PROCESS)
    monkeypatch.setattr(switch, "_window_area", lambda hwnd: 1)
    if window_alive:
        with pytest.raises(switch.win32gui.error) as caught:
            switch._wait_for_actionable_state(10, lambda text: None)
        assert caught.value is error
    else:
        assert switch._wait_for_actionable_state(10, lambda text: None) == 20
