#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""M9A B 服登录状态机的可观察边界（按评审意见补齐）。

adb 截图 / 点击与 OCR 属于系统边界，这里用替身喂固定画面，覆盖评审点出的
可观察边界：

1. 既认不出登录记录、也认不出标题页（例如停在别的账号的主界面）→ 明确失败，
   不能把"没认出登录页"当成目标账号已登录；
2. 隐私政策提示 + 全局「同意哔哩哔哩用户协议」关闭 → 不点同意、失败并提示手动处理；
3. 登录面板持续出现时，等待超时后失败；
4. 登录后停在标题页，无需配置 UID，由公开 StartUp 接续；
5. 引擎侧：首次登录失败后重试必须重新调用登录钩子；客户端被重启后清掉「已登录」标记；
6. 标题页信号：完整「REVERSE」、残词 `ERSE`算，`PLAYERS` 这类词不算；
7. 冷启动加载超过固定预算时服从 `Game.WaitTime`，不提前判「无法确认账号」；
8. `Mas` 模式只接受 B 服资源与 B 服包名，配错客户端在碰模拟器之前就报错；
9. 宿主推不出 ADB 路径时按地址用 MaaFW Toolkit 补上，钩子不再退回 PATH 的 `adb`；
10. `adb` 子进程随任务停止被回收，缺可执行文件时给可处理的提示（而不是裸报错）。

真机流程（MuMu + 真实客户端）仍按 ``docs/testing/e2e.md`` 在作者环境验证，不在 CI。
"""

from __future__ import annotations

import asyncio
import sys
import time
import types

import numpy as np
import pytest

from app.task.M9A import login as login_mod
from app.task.M9A.login import Box
from app.task.MaaFW.tools.embedded import runner_task
from app.task.MaaFW.tools.embedded.flavor import MaaFWLoginRequired

# 100x100 的画布：所有替身识别框都放在对应比例区间内
_FRAME_HEIGHT = 100
_FRAME_WIDTH = 100

#: 隐私政策提示（标题 OCR 连成一串，与实机一致）
_PRIVACY_SCREEN = [
    ("bilibili游戏隐私政策提示", (10, 30, 80, 10)),
    ("同意", (55, 70, 10, 10)),
]
#: 登录记录面板（收起态：当前昵称 + 登录 + 切换其他账号）
_PANEL_SCREEN = [
    ("登录记录", (45, 30, 10, 10)),
    ("示例账号", (45, 45, 10, 10)),
    ("登录", (45, 55, 10, 10)),
    ("切换其他账号", (45, 62, 10, 10)),
]
#: 标题页（OCR 能读到的正向信号）
_TITLE_SCREEN = [
    ("START", (45, 50, 10, 10)),
    ("V4.1.0", (5, 2, 20, 5)),
]
#: 无法识别为登录面板或标题页的画面。
_UNKNOWN_SCREEN = [
    ("邮件", (10, 10, 10, 10)),
    ("任务", (30, 10, 10, 10)),
    ("仓库", (50, 10, 10, 10)),
]


_HOME = [("主页菜单", (5, 70, 8, 8))]


class _FakeDevice:
    """adb 替身：只记录点击，画面由 ``screens`` 按顺序喂，抽完后重复最后一屏。"""

    def __init__(self, screens: list[list[tuple[str, Box]]]) -> None:
        self.screens = screens
        self.cursor = 0
        self.taps: list[object] = []

    def next_items(self) -> list[tuple[str, Box]]:
        index = min(self.cursor, len(self.screens) - 1)
        items = self.screens[index]
        self.cursor += 1
        return items

    async def foreground(self, package: str) -> bool:  # noqa: ARG002 - 替身固定在前台
        return True

    async def start(self, package: str) -> None:  # noqa: ARG002 - 替身不拉起
        pass

    async def screencap(self) -> np.ndarray:
        return np.zeros((_FRAME_HEIGHT, _FRAME_WIDTH, 3), dtype=np.uint8)

    async def tap(self, box: Box) -> None:
        self.taps.append(box)

    async def tap_point(self, x: float, y: float) -> None:
        self.taps.append((x, y))


class _Info:
    def __init__(self, account: str) -> None:
        self.Account = account
        self.Notes = ""


class _User:
    def __init__(self, account: str) -> None:
        self.Info = _Info(account)


class _Run:
    LoginMode = "Mas"


class _Game:
    #: 默认不额外放宽「认不出画面」的预算，保持各用例原有的时限；
    #: 需要验证「服从 Game.WaitTime」的用例自己改这一项。
    WaitTime = 0


class _Script:
    Run = _Run()
    Game = _Game()


def _install_fake_device(monkeypatch, screens) -> _FakeDevice:
    device = _FakeDevice(screens)
    monkeypatch.setattr(
        login_mod, "_Device", lambda adb_path, adb_address, host_adb=None: device
    )

    async def fake_ocr(_device):
        return np.zeros(
            (_FRAME_HEIGHT, _FRAME_WIDTH, 3), dtype=np.uint8
        ), device.next_items()

    monkeypatch.setattr(login_mod, "_ocr", fake_ocr)
    monkeypatch.setattr(
        login_mod,
        "_homepage_visible",
        lambda frame: (
            device.screens[min(device.cursor - 1, len(device.screens) - 1)] == _HOME
        ),
    )
    return device


def _fast(monkeypatch) -> None:
    monkeypatch.setattr(login_mod, "_POLL_SECONDS", 0.01)
    monkeypatch.setattr(login_mod, "_LOGIN_TIMEOUT", 0.4)
    monkeypatch.setattr(login_mod, "_UNKNOWN_SCREEN_SECONDS", 0.3)
    monkeypatch.setattr(login_mod, "_TITLE_SETTLE_SECONDS", 0)
    monkeypatch.setattr(login_mod, "_LAUNCH_TIMEOUT", 0.3)


def _run_login(account: str = "示例账号"):
    return login_mod.ensure_logged_in(
        script_config=_Script(),
        user_config=_User(account),
        resource_name="B 服",
        package_name="com.shenlan.m.reverse1999.bilibili",
        adb_path="adb",
        adb_address="127.0.0.1:1",
        progress=None,
    )


def test_unknown_screen_stops_instead_of_assuming_logged_in(monkeypatch) -> None:
    _fast(monkeypatch)
    _install_fake_device(monkeypatch, [_UNKNOWN_SCREEN])
    with pytest.raises(MaaFWLoginRequired, match="无法确认当前账号"):
        asyncio.run(_run_login())


@pytest.mark.parametrize("ambiguous", [False, True])
def test_login_handles_nickname_iteration_mark(monkeypatch, ambiguous):
    """实机把「ゞ」识别为 >；唯一昵称可登录，归一化后重名必须停止。"""
    _fast(monkeypatch)
    monkeypatch.setattr(login_mod, "_LOGIN_TIMEOUT", 5)
    panel = [
        ("测试>账号" if text == "示例账号" else text, box)
        for text, box in _PANEL_SCREEN
    ]
    expanded = [(text, box) for text, box in panel if text != "切换其他账号"]
    if ambiguous:
        expanded.append(("测试ゞ账号", (45, 60, 10, 10)))
    device = _install_fake_device(
        monkeypatch,
        [panel, expanded, panel, _TITLE_SCREEN, _TITLE_SCREEN, _TITLE_SCREEN, _HOME],
    )
    if ambiguous:
        with pytest.raises(MaaFWLoginRequired, match="多个同名账号"):
            asyncio.run(_run_login("测试ゞ账号"))
        assert device.taps == [pytest.approx((60.8, 43.0))]
    else:
        asyncio.run(_run_login("测试ゞ账号"))
        assert (45, 55, 10, 10) in device.taps
        assert device.taps[-1] == (45, 55, 10, 10)


def test_privacy_prompt_requires_agreement_switch(monkeypatch) -> None:
    _fast(monkeypatch)
    _install_fake_device(monkeypatch, [_PRIVACY_SCREEN])
    monkeypatch.setattr(login_mod, "_if_agree_bilibili", lambda: False)
    with pytest.raises(MaaFWLoginRequired, match="未开启"):
        asyncio.run(_run_login())


def test_privacy_prompt_clicked_when_switch_on(monkeypatch) -> None:
    device = _FakeDevice([_PRIVACY_SCREEN])
    frame = np.zeros((_FRAME_HEIGHT, _FRAME_WIDTH, 3), dtype=np.uint8)
    monkeypatch.setattr(login_mod, "_if_agree_bilibili", lambda: True)

    async def fake_ocr(_device):
        return frame, device.next_items()

    monkeypatch.setattr(login_mod, "_ocr", fake_ocr)
    monkeypatch.setattr(
        login_mod,
        "_homepage_visible",
        lambda frame: (
            device.screens[min(device.cursor - 1, len(device.screens) - 1)] == _HOME
        ),
    )
    asyncio.run(login_mod._agree_privacy(device, frame, _PRIVACY_SCREEN, progress=None))
    # 唯一一次点击是「同意」按钮（55,70,10,10）
    assert device.taps == [(55, 70, 10, 10)]


def test_visible_login_panel_blocks_startup(monkeypatch) -> None:
    _fast(monkeypatch)
    device = _install_fake_device(monkeypatch, [_PANEL_SCREEN])
    with pytest.raises(MaaFWLoginRequired, match="登录面板未关闭"):
        asyncio.run(
            login_mod._wait_panel_closed(
                device,
                progress=None,
                deadline=time.monotonic() + login_mod._LOGIN_TIMEOUT,
            )
        )


def test_title_frames_confirm_handover(monkeypatch) -> None:
    _fast(monkeypatch)
    device = _install_fake_device(
        monkeypatch, [_PANEL_SCREEN, [], [], [], _TITLE_SCREEN]
    )
    asyncio.run(
        login_mod._wait_panel_closed(
            device, progress=None, deadline=time.monotonic() + login_mod._LOGIN_TIMEOUT
        )
    )
    assert not device.taps


class _Plan:
    resourceName = "B 服"


def test_login_from_home_stops_if_logout_does_not_leave_home(monkeypatch):
    _fast(monkeypatch)
    device = _install_fake_device(monkeypatch, [_HOME])
    exits = []

    async def logout(device, *, progress):
        exits.append(device)

    monkeypatch.setattr(login_mod, "_logout_from_homepage", logout)
    with pytest.raises(MaaFWLoginRequired, match="退出后仍停在游戏主页"):
        asyncio.run(_run_login())
    assert exits == [device]
    assert not device.taps


@pytest.mark.parametrize("account", ["player", "12345"])
def test_non_han_nickname_requires_unique_exact_match_without_uid(monkeypatch, account):
    _fast(monkeypatch)
    monkeypatch.setattr(login_mod, "_LOGIN_TIMEOUT", 5)
    panel = [
        (account if text == "示例账号" else text, box) for text, box in _PANEL_SCREEN
    ]
    expanded = [(text, box) for text, box in panel if text != "切换其他账号"]
    expanded.append((account + "1", (45, 66, 10, 4)))
    device = _install_fake_device(
        monkeypatch,
        [panel, expanded, panel, _TITLE_SCREEN, _TITLE_SCREEN, _TITLE_SCREEN, _HOME],
    )
    assert isinstance(asyncio.run(_run_login(account)), login_mod.StartupTask)
    assert (45, 66, 10, 4) not in device.taps


def test_home_returns_to_bilibili_selection_without_uid(monkeypatch):
    _fast(monkeypatch)
    monkeypatch.setattr(login_mod, "_LOGIN_TIMEOUT", 5)
    expanded = [(text, box) for text, box in _PANEL_SCREEN if text != "切换其他账号"]
    settings = [
        ("设置", (12, 72, 4, 4)),
        ("账户", (6, 30, 4, 4)),
        ("退出", (65, 71, 4, 4)),
        ("返回登录", (60, 56, 4, 4)),
    ]
    device = _install_fake_device(
        monkeypatch,
        [
            _HOME,
            *([step] for step in settings),
            _PANEL_SCREEN,
            expanded,
            _PANEL_SCREEN,
            *([_TITLE_SCREEN] * 3),
            _HOME,
        ],
    )
    assert isinstance(asyncio.run(_run_login()), login_mod.StartupTask)
    assert device.taps[:4] == [box for _, box in settings]
    assert device.taps[-1] == (45, 55, 10, 10)


def _fake_runner() -> runner_task.MaaFWPluginAutoProxyTask:
    runner = object.__new__(runner_task.MaaFWPluginAutoProxyTask)
    runner._login_checked = False
    runner.script_config = object()
    runner.run_plan = _Plan()
    runner.cur_user_config = object()
    runner._launched_package_name = ""
    runner._append_log = lambda text: None  # noqa: E731 - 测试替身
    return runner


def _fake_hook(fail_first: bool):
    calls: list[dict] = []

    async def hook(**kwargs):
        calls.append(kwargs)
        if fail_first and len(calls) == 1:
            raise MaaFWLoginRequired("B 服登录失败：替身第一次失败")
        return "B 服登录完成"

    return hook, calls


def test_failed_login_is_retried_not_skipped(monkeypatch) -> None:
    runner = _fake_runner()
    hook, calls = _fake_hook(fail_first=True)
    monkeypatch.setattr(runner_task, "resolve_login_hook", lambda config: hook)
    monkeypatch.setattr(runner, "_resolve_adb_path_by_toolkit", lambda address: None)

    with pytest.raises(MaaFWLoginRequired):
        asyncio.run(runner._ensure_logged_in("127.0.0.1:1", None))
    # 失败不能记成已完成，否则下一次尝试会跳过登录
    assert runner._login_checked is False
    assert len(calls) == 1

    asyncio.run(runner._ensure_logged_in("127.0.0.1:1", None))
    assert runner._login_checked is True
    assert len(calls) == 2


def test_startup_pending_retries_selection_with_fresh_deadline(monkeypatch):
    runner = _fake_runner()
    calls = []

    async def hook(**kwargs):
        calls.append(kwargs)
        return login_mod.StartupTask(60.0 + len(calls), "StartUp")

    monkeypatch.setattr(runner_task, "resolve_login_hook", lambda config: hook)
    asyncio.run(runner._ensure_logged_in("127.0.0.1:1", "adb"))
    first = runner._startup_task
    assert not runner._login_checked
    asyncio.run(runner._ensure_logged_in("127.0.0.1:1", "adb"))
    assert len(calls) == 2
    assert runner._startup_task.deadline > first.deadline
    assert not runner._login_checked


def test_client_restart_resets_login_marker(monkeypatch) -> None:
    runner = _fake_runner()
    runner._login_checked = True
    runner.opened_emulator = True
    runner.opened_game = False
    runner._attempt_limit = lambda: 3
    monkeypatch.setattr(runner_task, "resolve_login_hook", lambda config: None)

    async def close_emulator() -> bool:
        runner.opened_emulator = False
        return True

    async def close_game() -> bool:
        return True

    runner._close_emulator = close_emulator
    runner._close_game = close_game
    asyncio.run(runner._restart_client_before_retry(0))
    assert runner._login_checked is False


def test_privacy_prompt_persists_until_timeout(monkeypatch) -> None:
    """隐私提示一直存在、点了同意还回来时，受总时限约束而不是无限循环。"""
    _fast(monkeypatch)
    monkeypatch.setattr(login_mod, "_LOGIN_TIMEOUT", 2.5)
    device = _install_fake_device(monkeypatch, [_PRIVACY_SCREEN])
    monkeypatch.setattr(login_mod, "_if_agree_bilibili", lambda: True)
    with pytest.raises(MaaFWLoginRequired, match="等待登录界面超时"):
        asyncio.run(_run_login())
    # 每轮都点到了「同意」，没有因为点不动就提前判成功
    assert device.taps


@pytest.mark.parametrize("text", ["PLAYERS", "OTHERS", "ERS", "RESTART"])
def test_unrelated_words_are_not_title(text):
    assert not login_mod._title_like(
        [(text, (0, 0, 10, 10))], np.zeros((100, 100, 3), dtype=np.uint8)
    )


def test_title_logout_requires_confirmation(monkeypatch):
    _fast(monkeypatch)
    monkeypatch.setattr(login_mod, "_LOGOUT_DIALOG_SECONDS", 0.1)
    device = _install_fake_device(monkeypatch, [_TITLE_SCREEN] * 3 + [_UNKNOWN_SCREEN])
    with pytest.raises(MaaFWLoginRequired, match="登出确认按钮未出现"):
        asyncio.run(_run_login())
    assert device.taps == [pytest.approx((95.6, 91.0))]


@pytest.mark.parametrize(
    ("version", "rating"),
    [("74.1.0-113.0.1421-180", "适龄提示"), ("J4.1.0-113.0.1421-180", "CADPA")],
)
def test_login_selects_target_after_logging_out(monkeypatch, version, rating):
    _fast(monkeypatch)
    # 实机标题页 OCR 漏掉 START / REVERSE，只读到了版本号和适龄标识。
    title = [(version, (5, 3, 14, 2)), (rating, (4, 89, 3, 2))]
    expanded = [(text, box) for text, box in _PANEL_SCREEN if text != "切换其他账号"]
    device = _install_fake_device(
        monkeypatch,
        [
            title,
            title,
            title,
            [("确认", (40, 50, 10, 10))],
            _PANEL_SCREEN,
            _PANEL_SCREEN,
            expanded,
            _PANEL_SCREEN,
            title,
            title,
            title,
            _HOME,
        ],
    )
    # The real selection flow includes two one-second UI waits.
    monkeypatch.setattr(login_mod, "_LOGIN_TIMEOUT", 5)
    message = asyncio.run(_run_login())
    assert isinstance(message, login_mod.StartupTask)
    assert device.taps == [
        pytest.approx((95.6, 91.0)),
        (40, 50, 10, 10),
        pytest.approx((60.8, 43.0)),
        (45, 45, 10, 10),
        (45, 55, 10, 10),
    ]


def test_mas_login_rejects_non_adb_controller():
    with pytest.raises(MaaFWLoginRequired, match="ADB"):
        asyncio.run(
            login_mod.ensure_logged_in(
                script_config=_Script(),
                user_config=_User("target"),
                resource_name=None,
                package_name=None,
                adb_path=None,
                adb_address="",
                progress=None,
            )
        )


def test_private_adb_transport_and_bgr_screenshot(monkeypatch):
    import io

    from PIL import Image

    png = io.BytesIO()
    Image.new("RGB", (16, 9), (255, 0, 0)).save(png, format="PNG")

    class Host:
        async def screencap_png(self, timeout):
            return png.getvalue()

        async def __call__(self, *args, timeout):
            if args[:2] == ("shell", "dumpsys"):
                return 0, "topResumedActivity= " + login_mod.BILIBILI_PACKAGE + "/Main"
            return 0, ""

    def no_subprocess(*args, **kwargs):
        raise AssertionError("private ADB must not use the default server")

    monkeypatch.setattr(login_mod.subprocess, "run", no_subprocess)

    async def exercise():
        device = login_mod._Device(None, "emulator-5554", Host())
        frame = await device.screencap()
        assert frame[0, 0].tolist() == [0, 0, 255]
        await device.tap_point(10, 20)
        assert await device.foreground(login_mod.BILIBILI_PACKAGE)
        await device.start(login_mod.BILIBILI_PACKAGE)

    asyncio.run(exercise())


def test_win32_device_build_blocks_mas_login_before_window_access(monkeypatch):
    from types import SimpleNamespace

    from app.task.M9A.flavor import FLAVOR

    runner = _fake_runner()
    runner.script_config = _Script()
    runner.cur_user_config = _User("target")
    monkeypatch.setattr(
        runner_task, "resolve_login_hook", lambda config: FLAVOR.ensure_logged_in
    )
    with pytest.raises(MaaFWLoginRequired, match="ADB"):
        asyncio.run(
            runner._build_device_config(SimpleNamespace(controllerType="Win32"), None)
        )
    assert not runner._login_checked


def test_health_warning_is_dismissed_before_login(monkeypatch) -> None:
    """冷启动的健康警告页要先点掉，否则认不出画面会等到超时。"""
    _fast(monkeypatch)
    monkeypatch.setattr(login_mod, "_LOGIN_TIMEOUT", 5.0)
    warning = [("警告：请在游戏前阅读", (20, 20, 60, 10))]
    device = _install_fake_device(
        monkeypatch,
        [
            warning,
            _PANEL_SCREEN,
            _PANEL_SCREEN,
            _PANEL_SCREEN,
            _TITLE_SCREEN,
            _TITLE_SCREEN,
            _TITLE_SCREEN,
            _HOME,
        ],
    )
    message = asyncio.run(_run_login())
    assert isinstance(message, login_mod.StartupTask)
    # 第一下点击是警告页中心（100x100 画布 → 50,50）
    assert device.taps[0] == (50.0, 50.0)


def test_title_logo_fragment_confirms_handover(monkeypatch) -> None:
    """标题页只读到 logo 下的「ERSE」时也算标题页（START 太淡时 OCR 读不到）。"""
    _fast(monkeypatch)
    ers = [("ERSE", (55, 60, 15, 4)), ("V4.1.0-113.0.1421-180", (5, 2, 20, 5))]
    device = _install_fake_device(monkeypatch, [_PANEL_SCREEN, ers, ers])
    asyncio.run(
        login_mod._wait_panel_closed(
            device, progress=None, deadline=time.monotonic() + login_mod._LOGIN_TIMEOUT
        )
    )


def test_title_logo_full_word_confirms_handover(monkeypatch) -> None:
    """OCR 正确读出完整的「REVERSE」时同样是标题页（START 漏识、横幅已消失）。"""
    _fast(monkeypatch)
    reverse = [("REVERSE", (55, 60, 15, 4)), ("V4.1.0-113.0.1421-180", (5, 2, 20, 5))]
    device = _install_fake_device(monkeypatch, [_PANEL_SCREEN, reverse, reverse])
    asyncio.run(
        login_mod._wait_panel_closed(
            device, progress=None, deadline=time.monotonic() + login_mod._LOGIN_TIMEOUT
        )
    )


def test_unknown_screen_budget_follows_game_wait_time(monkeypatch) -> None:
    """认不出画面的预算取 Game.WaitTime，但不超过登录主循环的总时限。"""

    class _Game120:
        WaitTime = 120

    class _Long:
        Game = _Game120()

    class _GameHuge:
        WaitTime = 9999

    class _Huge:
        Game = _GameHuge()

    class _GameTiny:
        WaitTime = 5

    class _Tiny:
        Game = _GameTiny()

    monkeypatch.setattr(login_mod, "_UNKNOWN_SCREEN_SECONDS", 60.0)
    monkeypatch.setattr(login_mod, "_LOGIN_TIMEOUT", 240.0)
    assert login_mod._unknown_screen_budget(_Long()) == 120.0
    assert login_mod._unknown_screen_budget(_Huge()) == 240.0
    assert login_mod._unknown_screen_budget(_Tiny()) == 60.0


def test_slow_loading_is_not_cut_off_by_fixed_budget(monkeypatch) -> None:
    """加载画面超过固定预算但仍在 Game.WaitTime 内时，继续等到登录记录，不提前判失败。"""
    _fast(monkeypatch)
    monkeypatch.setattr(login_mod, "_LOGIN_TIMEOUT", 30.0)
    monkeypatch.setattr(login_mod, "_UNKNOWN_SCREEN_SECONDS", 0.2)
    monkeypatch.setattr(_Script.Game, "WaitTime", 20)
    expanded = [(text, box) for text, box in _PANEL_SCREEN if text != "切换其他账号"]
    device = _install_fake_device(
        monkeypatch,
        [_UNKNOWN_SCREEN] * 60
        + [
            _TITLE_SCREEN,
            _TITLE_SCREEN,
            _TITLE_SCREEN,
            _TITLE_SCREEN,
            [("确认", (40, 50, 10, 10))],
            _PANEL_SCREEN,
            _PANEL_SCREEN,
            expanded,
            _PANEL_SCREEN,
            _TITLE_SCREEN,
            _TITLE_SCREEN,
            _TITLE_SCREEN,
            _HOME,
        ],
    )
    # 固定 0.2 秒预算会先报「无法确认当前账号」；服从 WaitTime 后能等到 0.6 秒后的登录记录。
    message = asyncio.run(_run_login())
    assert isinstance(message, login_mod.StartupTask)
    assert device.taps


def test_mas_login_rejects_official_client() -> None:
    """Mas 模式配了官服包名时立刻报错，不拿官服客户端去走哔哩哔哩登录面板。"""
    with pytest.raises(MaaFWLoginRequired, match="B 服客户端"):
        asyncio.run(
            login_mod.ensure_logged_in(
                script_config=_Script(),
                user_config=_User("示例账号"),
                resource_name="B 服",
                package_name="com.shenlan.m.reverse1999",
                adb_path="adb",
                adb_address="127.0.0.1:1",
                progress=None,
            )
        )


def test_mas_login_rejects_official_resource() -> None:
    """资源还是官服（包名留空、按 B 服包名兜底）时同样在启动客户端前拦下。"""
    with pytest.raises(MaaFWLoginRequired, match="官服"):
        asyncio.run(
            login_mod.ensure_logged_in(
                script_config=_Script(),
                user_config=_User("示例账号"),
                resource_name="官服",
                package_name=None,
                adb_path="adb",
                adb_address="127.0.0.1:1",
                progress=None,
            )
        )


def test_mas_login_rejects_other_server_resource() -> None:
    """Mas 只允许 B 服资源：国际服等其它资源即使包名能兜底也要拦下。"""
    with pytest.raises(MaaFWLoginRequired, match="B 服」资源"):
        asyncio.run(
            login_mod.ensure_logged_in(
                script_config=_Script(),
                user_config=_User("示例账号"),
                resource_name="国际服（EN）",
                package_name=None,
                adb_path="adb",
                adb_address="127.0.0.1:1",
                progress=None,
            )
        )


def test_missing_adb_reports_actionable_error() -> None:
    """ADB 可执行文件不存在时给出可处理的提示，而不是裸 FileNotFoundError。"""
    device = login_mod._Device("/nonexistent/adb-does-not-exist", "127.0.0.1:1")
    with pytest.raises(MaaFWLoginRequired, match="ADB 可执行文件"):
        asyncio.run(device.tap_point(1, 1))


def test_adb_command_is_stopped_when_task_is_cancelled(monkeypatch) -> None:
    """停止任务时取消要真正回收 adb 子进程，不能只停协程。"""
    stopped: list[bool] = []

    class _SlowProcess:
        returncode = None

        async def communicate(self):
            await asyncio.sleep(30)
            return b"", b""

    async def fake_create(*args, **kwargs):
        return _SlowProcess()

    async def fake_stop(process, *, kill_tree=False, deadline=None):
        stopped.append(kill_tree)

    monkeypatch.setattr(login_mod, "create_subprocess", fake_create)
    monkeypatch.setattr(login_mod, "stop_process", fake_stop)

    async def exercise():
        device = login_mod._Device("adb", "127.0.0.1:1")
        task = asyncio.create_task(device.tap_point(10, 20))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
    assert stopped == [True]


def test_login_and_worker_share_toolkit_adb_path(monkeypatch) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    runner = _fake_runner()
    hook, calls = _fake_hook(fail_first=False)
    monkeypatch.setattr(runner_task, "resolve_login_hook", lambda config: hook)
    monkeypatch.setattr(
        runner, "_resolve_adb_path_by_toolkit", lambda address: "/opt/HD-Adb.exe"
    )
    monkeypatch.setattr(
        runner, "_resolve_adb_address", AsyncMock(return_value=("127.0.0.1:1", None))
    )
    monkeypatch.setattr(runner, "_resolve_adb_path", AsyncMock(return_value=None))
    monkeypatch.setattr(runner, "_ensure_game_updated", AsyncMock())
    monkeypatch.setattr(
        runner,
        "_build_adb_control_profile",
        AsyncMock(return_value=SimpleNamespace(config={})),
    )
    monkeypatch.setattr(runner, "_resolve_adb_screencap_methods", lambda profile: 0)
    monkeypatch.setattr(runner, "_resolve_adb_input_methods", lambda profile: 0)
    monkeypatch.setattr(runner, "_resolve_adb_ready_timeout", lambda: 60)
    plan = SimpleNamespace(controllerType="Adb")
    device = asyncio.run(runner._build_device_config(plan, None))
    assert calls[0]["adb_path"] == device.adbPath == "/opt/HD-Adb.exe"
    assert calls[0]["adb_address"] == device.address == "127.0.0.1:1"


def test_toolkit_discovery_matches_device_address(monkeypatch, tmp_path) -> None:
    """按地址匹配 Toolkit 的发现结果；本机没有该地址时返回 None。"""
    adb = tmp_path / "HD-Adb.exe"
    adb.write_bytes(b"")

    class _Found:
        address = "127.0.0.1:5555"
        adb_path = str(adb)

    class _Toolkit:
        @staticmethod
        def find_adb_devices():
            return [_Found()]

    module = types.ModuleType("maa.toolkit")
    module.Toolkit = _Toolkit
    parent = types.ModuleType("maa")
    parent.toolkit = module
    monkeypatch.setitem(sys.modules, "maa", parent)
    monkeypatch.setitem(sys.modules, "maa.toolkit", module)

    runner = _fake_runner()
    assert runner._resolve_adb_path_by_toolkit("127.0.0.1:5555") == str(adb)
    assert runner._resolve_adb_path_by_toolkit("127.0.0.1:5556") is None


@pytest.mark.parametrize("startup_failed", [False, True])
def test_startup_result_gates_daily_without_uid(monkeypatch, startup_failed):
    from types import SimpleNamespace

    from app.task.MaaFW.tools.core.runner.models import MaaFWRunPlan, MaaFWTaskRunPlan
    from app.task.MaaFW.tools.core.runner.runner import MaaFWRunner, MaaFWTaskError

    posted = []

    def post_task(entry):
        posted.append(entry)
        return entry

    def wait_job(job):
        if job == "StartUp" and startup_failed:
            raise MaaFWTaskError("M9A StartUp failed")

    plan = MaaFWRunPlan.model_construct(
        tasks=[
            MaaFWTaskRunPlan(
                name="StartUp", entry="StartUp", abortRoundMessage="启动游戏失败"
            ),
            MaaFWTaskRunPlan(name="Daily", entry="Daily"),
        ]
    )
    runner = MaaFWRunner(plan)
    runner.tasker = SimpleNamespace(post_task=post_task)
    monkeypatch.setattr(runner, "_wait_job", wait_job)
    monkeypatch.setattr(runner, "_external_stop_active", lambda tasker: False)
    monkeypatch.setattr(
        runner, "_capture_failure_screenshot", lambda *args, **kwargs: None
    )
    if startup_failed:
        with pytest.raises(MaaFWTaskError, match="启动游戏失败"):
            runner._run_tasks()
        assert posted == ["StartUp"]
    else:
        assert runner._run_tasks() == ["StartUp", "Daily"]
        assert posted == ["StartUp", "Daily"]
