"""官方启动器更新到可启动状态即结束，停止任务后不再留后台点击。"""

import asyncio
import base64
import json
from pathlib import PureWindowsPath
from threading import Event
from types import SimpleNamespace

import pytest

from app.task.Okww.tools import launcher_start as launcher


@pytest.fixture
def desktop(tmp_path, monkeypatch):
    clock = SimpleNamespace(now=0.0)
    state = SimpleNamespace(
        frames=[], clicks=[], game_window=None, reads=0, last_frame=[], clock=clock
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(launcher, "IS_WINDOWS", True)
    monkeypatch.setattr(
        launcher, "pyautogui", SimpleNamespace(FAILSAFE=True), raising=False
    )
    monkeypatch.setattr(
        launcher,
        "time",
        SimpleNamespace(
            monotonic=lambda: clock.now, sleep=lambda delay: advance(delay)
        ),
    )

    def advance(delay):
        clock.now += delay

    monkeypatch.setattr(launcher, "dismiss_screensaver", lambda **kwargs: None)
    monkeypatch.setattr(launcher, "_wait_launcher_hwnd", lambda *args, **kwargs: 1)
    monkeypatch.setattr(launcher, "_activate_window", lambda *args, **kwargs: None)
    monkeypatch.setattr(launcher, "_describe_window", lambda hwnd: "launcher")
    monkeypatch.setattr(launcher, "_save_error_screenshot", lambda hwnd: None)
    monkeypatch.setattr(launcher, "_find_game_hwnd", lambda: state.game_window)
    monkeypatch.setattr(
        launcher,
        "_click_box",
        lambda hwnd, box, **kwargs: state.clicks.append(box),
    )

    def read(hwnd):
        state.reads += 1
        if state.frames:
            state.last_frame = state.frames.pop(0)
        return state.last_frame

    monkeypatch.setattr(launcher, "_read_texts", read)
    state.path = tmp_path / "launcher.exe"
    return state


UPDATE = (1400, 920, 160, 60)
START = (1420, 920, 160, 60)


def test_update_waits_for_download_and_stops_before_start(desktop):
    desktop.frames = [
        [("更新", UPDATE)],
        [("下载中 20%", UPDATE)],
        [("校验解压文件 99%", UPDATE)],
        [("进入游戏", START)],
    ]

    assert launcher.start_game_via_launcher(desktop.path, update_only=True)
    assert desktop.clicks == [UPDATE]


@pytest.mark.parametrize("ready", [True, False])
def test_open_game_does_not_confirm_update_or_bypass_launcher(
    desktop, monkeypatch, ready
):
    desktop.game_window = 9
    desktop.frames = [[("进入游戏", START)]] if ready else [[]]
    monkeypatch.setattr(launcher, "_FIND_BUTTON_TIMEOUT", 20 if ready else 1)

    if ready:
        assert launcher.start_game_via_launcher(desktop.path, update_only=True)
    else:
        with pytest.raises(RuntimeError):
            launcher.start_game_via_launcher(desktop.path, update_only=True)
    assert desktop.clicks == []


def test_initial_ready_frame_does_not_skip_pending_update(desktop):
    desktop.frames = [
        [("进入游戏", START)],
        [("更新", UPDATE)],
        [("下载中 20%", UPDATE)],
        [("进入游戏", START)],
    ]

    assert launcher.start_game_via_launcher(desktop.path, update_only=True)
    assert desktop.clicks == [UPDATE]


@pytest.mark.parametrize("recover", [True, False])
def test_platform_read_failure_waits_without_clicking(desktop, monkeypatch, recover):
    platform = desktop.path.parent / "kr_game_cache/platform_ui_state.bin"
    platform.parent.mkdir()
    platform.write_bytes(b"partial base64!")
    desktop.frames = [[("更新", UPDATE)], [("进入游戏", START)]]
    original_read = launcher._read_texts

    def read(hwnd):
        if desktop.reads == 1 and recover:
            assert desktop.clicks == []
            raw = json.dumps(
                {"activeGameScope": {"gameIdentity": "Aki", "bundleName": "HD"}}
            ).encode()
            platform.write_bytes(base64.b64encode(bytes(value ^ 0x63 for value in raw)))
        return original_read(hwnd)

    monkeypatch.setattr(launcher, "_read_texts", read)
    if recover:
        assert launcher.start_game_via_launcher(desktop.path, update_only=True)
    else:
        with pytest.raises(ValueError):
            launcher.start_game_via_launcher(desktop.path, update_only=True)
        assert desktop.clock.now < 20
    assert desktop.clicks == []


def test_normal_start_still_clicks_start(desktop, monkeypatch):
    desktop.frames = [[("进入游戏", START)]]

    def click(hwnd, box, **kwargs):
        desktop.clicks.append(box)
        desktop.game_window = 9

    monkeypatch.setattr(launcher, "_click_box", click)
    assert launcher.start_game_via_launcher(desktop.path)
    assert desktop.clicks == [START]


def test_stop_before_update_prevents_any_desktop_click(desktop):
    desktop.frames = [[("更新", UPDATE)]]
    stop = Event()
    stop.set()

    with pytest.raises(launcher._LaunchCancelled):
        launcher.start_game_via_launcher(
            desktop.path, update_only=True, stop_event=stop
        )
    assert desktop.clicks == []
    assert desktop.reads == 0


def test_launcher_window_requires_verified_install_path(monkeypatch):
    # 模拟的是 Windows 窗口进程，在 Linux CI 中同样使用 Windows 路径。
    selected = PureWindowsPath("C:/selected/launcher.exe")
    monkeypatch.setattr(
        launcher,
        "win32gui",
        SimpleNamespace(
            EnumWindows=lambda callback, param: [
                callback(hwnd, param) for hwnd in (1, 2, 3)
            ],
            IsWindowVisible=lambda hwnd: True,
        ),
        raising=False,
    )
    monkeypatch.setattr(
        launcher,
        "win32process",
        SimpleNamespace(GetWindowThreadProcessId=lambda hwnd: (0, hwnd)),
        raising=False,
    )
    monkeypatch.setattr(launcher, "_process_name", lambda pid: "launcher_main.exe")
    paths = {
        1: None,
        2: str(PureWindowsPath("C:/other/launcher_main.exe")),
        3: str(selected.parent / "2.7.0" / "launcher_main.exe"),
    }
    monkeypatch.setattr(launcher, "_process_exe", paths.__getitem__)
    monkeypatch.setattr(launcher, "_window_area", lambda hwnd: 1000 - hwnd)

    assert launcher._wait_launcher_hwnd(selected, timeout=1) == 3


@pytest.mark.parametrize("switch_on_read", [1, 2])
def test_update_refuses_other_game_selection(desktop, monkeypatch, switch_on_read):
    platform = desktop.path.parent / "kr_game_cache" / "platform_ui_state.bin"
    platform.parent.mkdir()

    def select(game):
        raw = json.dumps(
            {"activeGameScope": {"gameIdentity": game, "bundleName": "HD"}}
        ).encode("utf-8")
        platform.write_bytes(base64.b64encode(bytes(value ^ 0x63 for value in raw)))

    select("Aki")
    desktop.frames = [[("更新", UPDATE)], [("进入游戏", START)]]
    original_read = launcher._read_texts

    def read(hwnd):
        items = original_read(hwnd)
        if desktop.reads == switch_on_read:
            select("OtherGame")
        return items

    monkeypatch.setattr(launcher, "_read_texts", read)
    with pytest.raises(ValueError):
        launcher.start_game_via_launcher(desktop.path, update_only=True)
    assert desktop.clicks == ([] if switch_on_read == 1 else [UPDATE])


@pytest.mark.asyncio
async def test_cancel_waits_until_interaction_thread_has_stopped(monkeypatch, tmp_path):
    entered = Event()
    release = Event()
    exited = Event()
    stopped = Event()

    def interaction(*args, **kwargs):
        entered.set()
        try:
            release.wait(2)
            stop_event = kwargs.get("stop_event")
            if stop_event is not None and stop_event.is_set():
                stopped.set()
        finally:
            exited.set()
        return True

    monkeypatch.setattr(launcher, "start_game_via_launcher", interaction)
    task = asyncio.create_task(
        launcher.async_start_game_via_launcher(tmp_path / "launcher.exe")
    )
    assert await asyncio.to_thread(entered.wait, 1)
    task.cancel()
    try:
        await asyncio.sleep(0.02)
        assert not task.done()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await asyncio.to_thread(exited.wait, 1)
        assert stopped.is_set()
