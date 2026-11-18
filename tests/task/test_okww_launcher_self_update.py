"""官方启动器换窗口后仍能继续检查更新或启动鸣潮。"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.task.Okww.tools import launcher_start


@pytest.mark.parametrize(
    ("window_flow", "update_only"),
    [
        ("reopen", True),
        ("reopen", False),
        ("same_window", True),
        ("second_popup", False),
    ],
)
def test_launcher_self_update_resumes(monkeypatch, tmp_path, window_flow, update_only):
    monkeypatch.chdir(tmp_path)
    clock = SimpleNamespace(now=0)
    update_box = (1123, 642, 42, 23)
    start_box = (1598, 942, 121, 31)
    clicks = []
    foreground = 10
    new_window_activation_attempted = False
    second_update_progress_seen = False
    popup = [
        ("启动器版本更新", (712, 430, 185, 26)),
        ("更新", update_box),
        ("进入游戏", start_box),
    ]
    progress = [("资源校验中", (422, 773, 131, 31))]
    ready = [("进入游戏", start_box)]

    def sleep(seconds):
        clock.now += seconds

    def find_launcher(_path):
        if window_flow == "same_window" or not clicks or clock.now < 4:
            return 10
        if clock.now < 8:
            return None
        return 20

    def read_texts(hwnd):
        nonlocal second_update_progress_seen
        assert hwnd == foreground
        if hwnd == 20:
            if window_flow == "second_popup":
                if (20, update_box) not in clicks:
                    return popup
                if not second_update_progress_seen:
                    second_update_progress_seen = True
                    return progress
            return ready
        if not clicks:
            return popup
        if window_flow == "same_window" and clock.now >= 4:
            return ready
        return progress

    def activate_window(hwnd, **_):
        nonlocal foreground, new_window_activation_attempted
        if hwnd == 20 and not new_window_activation_attempted:
            # Windows can ignore the first foreground request while the window opens.
            new_window_activation_attempted = True
            return
        foreground = hwnd

    monkeypatch.setattr(launcher_start, "IS_WINDOWS", True)
    monkeypatch.setattr(launcher_start, "pyautogui", SimpleNamespace(), raising=False)
    monkeypatch.setattr(
        launcher_start,
        "win32gui",
        SimpleNamespace(error=OSError, GetForegroundWindow=lambda: foreground),
        raising=False,
    )
    monkeypatch.setattr(
        launcher_start,
        "time",
        SimpleNamespace(monotonic=lambda: clock.now, sleep=sleep),
    )
    monkeypatch.setattr(launcher_start, "dismiss_screensaver", lambda **_: None)
    monkeypatch.setattr(launcher_start, "_activate_window", activate_window)
    monkeypatch.setattr(launcher_start, "_describe_window", lambda _hwnd: "")
    monkeypatch.setattr(launcher_start, "_find_launcher_hwnd", find_launcher)
    monkeypatch.setattr(launcher_start, "_read_texts", read_texts)
    monkeypatch.setattr(
        launcher_start, "read_wuthering_waves_launcher_selection", lambda _path: None
    )
    monkeypatch.setattr(
        launcher_start, "_click_box", lambda hwnd, box, **_: clicks.append((hwnd, box))
    )
    monkeypatch.setattr(
        launcher_start,
        "_find_game_hwnd",
        lambda: 30 if (20, start_box) in clicks else None,
    )

    assert launcher_start.start_game_via_launcher(
        Path("launcher.exe"), update_only=update_only
    )
    expected = [(10, update_box)]
    if window_flow == "second_popup":
        expected.append((20, update_box))
    if not update_only:
        expected.append((20, start_box))
    assert clicks == expected
