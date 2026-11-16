"""登录记录中目标不可见时，不能把近似账号当作目标执行任务。"""

import asyncio

import numpy as np
import pytest

from app.task.M9A import login
from app.task.MaaFW.tools.embedded.flavor import MaaFWLoginRequired


@pytest.mark.parametrize(
    "account, candidates, selected, allowed",
    [
        ("豆芽01", ["豆芽02"], "豆芽02", False),
        ("豆芽O1", ["豆芽01"], "豆芽01", False),
        ("豆芽-★A01", ["豆芽_♡A01"], "豆芽_♡A01", True),
        ("豆芽ゞA01", ["豆芽>A01"], "豆芽>A01", True),
        ("豆芽ゞA01", ["豆芽>A01", "豆芽ゞA01"], "豆芽ゞA01", False),
        ("豆芽01", ["豆芽01", "豆芽01"], "豆芽01", False),
        ("豆芽01", ["豆芽01"], "豆芽02", False),
        ("★ゞ", ["♡>"], "♡>", False),
        ("豆芽a01", ["豆芽A01"], "豆芽A01", False),
    ],
)
def test_account_selection_keeps_identity(
    monkeypatch, account, candidates, selected, allowed
):
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    rows = [(name, (45, 38 + i * 8, 10, 4)) for i, name in enumerate(candidates)]
    button = (45, 72, 10, 4)
    taps = []

    class Device:
        async def tap(self, box):
            taps.append(box)

    async def ocr(device):
        items = [
            (selected, (45, 45, 10, 4)),
            ("登录", button),
            ("切换其他账号", (45, 62, 10, 4)),
        ]
        return frame.copy(), items if taps else rows

    async def sleep(seconds):
        pass

    monkeypatch.setattr(login, "_ocr", ocr)
    monkeypatch.setattr(login.asyncio, "sleep", sleep)
    task = login._select_account(Device(), frame, rows, account, progress=None)
    if allowed:
        asyncio.run(task)
        exact = [box for name, box in rows if name == account]
        assert taps == [exact[0] if exact else rows[0][1], button]
    else:
        with pytest.raises(MaaFWLoginRequired):
            asyncio.run(task)
        assert button not in taps


def test_misread_nickname_can_recover_on_new_screenshots(monkeypatch):
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    target = (45, 42, 10, 4)
    button = (45, 72, 10, 4)
    taps = []
    frames = iter(
        [
            [("豆芽01", target)],
            [("豆芽O1", target), ("登录", button), ("切换其他账号", target)],
            [("豆芽01", target), ("登录", button), ("切换其他账号", target)],
        ]
    )

    class Device:
        async def tap(self, box):
            taps.append(box)

    async def ocr(device):
        assert button not in taps
        return frame.copy(), next(frames)

    async def sleep(seconds):
        pass

    monkeypatch.setattr(login, "_ocr", ocr)
    monkeypatch.setattr(login.asyncio, "sleep", sleep)
    asyncio.run(
        login._select_account(
            Device(), frame, [("豆芽O1", target)], "豆芽01", progress=None
        )
    )
    assert taps == [target, button]
