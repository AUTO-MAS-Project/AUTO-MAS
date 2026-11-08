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
3. 登录后只出现空帧 / 面板帧 → 不提前判成功（有界等待后失败）；
4. 登录后连续两帧标题页 → 成功；
5. 引擎侧：首次登录失败后重试必须重新调用登录钩子；客户端被重启后清掉「已登录」标记。

真机流程（MuMu + 真实客户端）仍按 ``docs/testing/e2e.md`` 在作者环境验证，不在 CI。
"""

from __future__ import annotations

import asyncio

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
    ("小逗芽呀", (45, 45, 10, 10)),
    ("登录", (45, 55, 10, 10)),
    ("切换其他账号", (45, 62, 10, 10)),
]
#: 标题页（OCR 能读到的正向信号）
_TITLE_SCREEN = [
    ("START", (45, 50, 10, 10)),
    ("V4.1.0", (5, 2, 20, 5)),
]
#: 认不出的画面（主界面截图里没有 START / 登录记录）
_UNKNOWN_SCREEN = [
    ("邮件", (10, 10, 10, 10)),
    ("任务", (30, 10, 10, 10)),
    ("仓库", (50, 10, 10, 10)),
]


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

    def foreground(self, package: str) -> bool:  # noqa: ARG002 - 替身固定在前台
        return True

    def start(self, package: str) -> None:  # noqa: ARG002 - 替身不拉起
        pass

    def screencap(self) -> np.ndarray:
        return np.zeros((_FRAME_HEIGHT, _FRAME_WIDTH, 3), dtype=np.uint8)

    def tap(self, box: Box) -> None:
        self.taps.append(box)

    def tap_point(self, x: float, y: float) -> None:
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


class _Script:
    Run = _Run()


def _install_fake_device(monkeypatch, screens) -> _FakeDevice:
    device = _FakeDevice(screens)
    monkeypatch.setattr(login_mod, "_Device", lambda adb_path, adb_address: device)

    async def fake_ocr(_device):
        return np.zeros(
            (_FRAME_HEIGHT, _FRAME_WIDTH, 3), dtype=np.uint8
        ), device.next_items()

    monkeypatch.setattr(login_mod, "_ocr", fake_ocr)
    return device


def _fast(monkeypatch) -> None:
    monkeypatch.setattr(login_mod, "_POLL_SECONDS", 0.01)
    monkeypatch.setattr(login_mod, "_LOGIN_TIMEOUT", 0.4)
    monkeypatch.setattr(login_mod, "_UNKNOWN_SCREEN_SECONDS", 0.3)
    monkeypatch.setattr(login_mod, "_TITLE_SETTLE_SECONDS", 0)
    monkeypatch.setattr(login_mod, "_LAUNCH_TIMEOUT", 0.3)


def _run_login(account: str = "小逗芽呀"):
    return login_mod.ensure_logged_in(
        script_config=_Script(),
        user_config=_User(account),
        resource_name="官服",
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
    asyncio.run(login_mod._agree_privacy(device, frame, _PRIVACY_SCREEN, progress=None))
    # 唯一一次点击是「同意」按钮（55,70,10,10）
    assert device.taps == [(55, 70, 10, 10)]


def test_empty_frames_do_not_declare_success(monkeypatch) -> None:
    _fast(monkeypatch)
    device = _install_fake_device(monkeypatch, [_PANEL_SCREEN, _UNKNOWN_SCREEN])
    with pytest.raises(MaaFWLoginRequired, match="未确认回到游戏标题页"):
        asyncio.run(login_mod._wait_panel_closed(device, progress=None))


def test_title_frames_confirm_handover(monkeypatch) -> None:
    _fast(monkeypatch)
    device = _install_fake_device(
        monkeypatch, [_PANEL_SCREEN, _TITLE_SCREEN, _TITLE_SCREEN]
    )
    message = asyncio.run(login_mod._wait_panel_closed(device, progress=None))
    assert "已确认回到游戏标题页" in message


class _Plan:
    resourceName = "官服"


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

    with pytest.raises(MaaFWLoginRequired):
        asyncio.run(runner._ensure_logged_in("127.0.0.1:1", None))
    # 失败不能记成已完成，否则下一次尝试会跳过登录
    assert runner._login_checked is False
    assert len(calls) == 1

    asyncio.run(runner._ensure_logged_in("127.0.0.1:1", None))
    assert runner._login_checked is True
    assert len(calls) == 2


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
