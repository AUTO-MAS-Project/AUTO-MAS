"""鸣潮更新重启时允许新窗口延迟出现，并保持有界等待。"""

from importlib import import_module
from types import SimpleNamespace

import pytest

switch = import_module("app.task.Okww.tools.account_switch")
pytestmark = pytest.mark.skipif(not switch.IS_WINDOWS, reason="Windows 窗口生命周期")


@pytest.fixture
def desktop(monkeypatch):
    clock = SimpleNamespace(now=0.0, windows=[])

    def sleep(seconds):
        clock.now += seconds

    monkeypatch.setattr(
        switch, "time", SimpleNamespace(monotonic=lambda: clock.now, sleep=sleep)
    )
    monkeypatch.setattr(switch.win32gui, "IsWindow", lambda hwnd: False)

    def enumerate_windows(callback, arg):
        for hwnd in clock.windows():
            callback(hwnd, arg)

    monkeypatch.setattr(switch.win32gui, "EnumWindows", enumerate_windows)
    monkeypatch.setattr(switch.win32gui, "IsWindowVisible", lambda hwnd: True)
    monkeypatch.setattr(
        switch.win32gui, "GetClassName", lambda hwnd: switch._WUWA_CLASS
    )
    monkeypatch.setattr(
        switch.win32process, "GetWindowThreadProcessId", lambda hwnd: (1, 2)
    )
    monkeypatch.setattr(switch, "_process_name", lambda pid: switch._WUWA_PROCESS)
    monkeypatch.setattr(switch, "_window_area", lambda hwnd: hwnd)
    monkeypatch.setattr(switch, "_activate_window", lambda hwnd: None)
    return clock


def test_restart_waits_for_delayed_new_window(desktop):
    desktop.windows = lambda: [20] if desktop.now >= 3 else []
    assert switch._wait_game_restart(10, lambda text: None) == 20
    assert desktop.now == 3


def test_restart_missing_window_times_out(desktop):
    desktop.windows = lambda: []
    with pytest.raises(RuntimeError):
        switch._wait_game_restart(10, lambda text: None)
    assert desktop.now == switch._GAME_WINDOW_WAIT_SECONDS


def test_strict_single_lookup_still_raises_without_window(desktop):
    desktop.windows = lambda: []
    with pytest.raises(RuntimeError):
        switch._find_game_hwnd(wait=False)
    assert desktop.now == 0
