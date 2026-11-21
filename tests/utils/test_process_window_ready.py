"""等游戏窗口就绪：窗口可见但客户区还是 0×0 时不能放行。

回归的是真实故障：游戏拉起后主窗口已经可见，引擎仍在初始化，客户区还是 0×0，
此时脚本截图拿到空图、识别全失败却仍被记成成功。等待必须等客户区有面积。
"""

import asyncio

import pytest

from app.utils.common.process import manager


class _FakeWindow:
    """按调用次序返回客户区尺寸的窗口替身。"""

    def __init__(self, sizes: list[tuple[int, int]]) -> None:
        self.sizes = sizes
        self.calls = 0

    def is_visible(self, hwnd: int) -> bool:
        return True

    def get_client_size(self, hwnd: int) -> tuple[int, int]:
        index = min(self.calls, len(self.sizes) - 1)
        self.calls += 1
        return self.sizes[index]


def _prepare(monkeypatch: pytest.MonkeyPatch, fake: _FakeWindow, hwnd: int) -> None:
    monkeypatch.setattr(manager, "IS_WINDOWS", True)
    monkeypatch.setattr(manager, "window", fake)
    monkeypatch.setattr(manager, "get_main_window_handle", lambda pid: hwnd)


@pytest.mark.asyncio
async def test_zero_client_area_is_not_ready(monkeypatch):
    """客户区 0×0 时继续等，画出面积后才放行。"""

    fake = _FakeWindow([(0, 0), (0, 0), (1280, 720)])
    _prepare(monkeypatch, fake, hwnd=4242)

    ready = await manager.wait_process_window_ready(
        manager.ProcessInfo(pid=4242), 2.0, poll_interval=0.01
    )

    assert ready is True
    assert fake.calls >= 3


@pytest.mark.asyncio
async def test_ready_timeout_raises(monkeypatch):
    """客户区一直不出面积时按上限报错，而不是放行。"""

    fake = _FakeWindow([(0, 0)])
    _prepare(monkeypatch, fake, hwnd=4242)

    with pytest.raises(RuntimeError):
        await asyncio.wait_for(
            manager.wait_process_window_ready(
                manager.ProcessInfo(pid=4242), 0.2, poll_interval=0.01
            ),
            timeout=5,
        )


@pytest.mark.asyncio
async def test_missing_identifier_returns_without_waiting(monkeypatch):
    """通用脚本允许不填进程名：没有可等的目标时直接放行。"""

    fake = _FakeWindow([(0, 0)])
    _prepare(monkeypatch, fake, hwnd=4242)

    ready = await manager.wait_process_window_ready(
        manager.ProcessInfo(), timeout_seconds=5.0
    )

    assert ready is False
    assert fake.calls == 0


@pytest.mark.asyncio
async def test_zero_timeout_falls_back_to_default_cap(monkeypatch):
    """启动等待时间填 0 仍然等窗口，用的是兜底上限而不是「不等」。"""

    fake = _FakeWindow([(0, 0)])
    _prepare(monkeypatch, fake, hwnd=4242)
    monkeypatch.setattr(manager, "_WINDOW_READY_FALLBACK_SECONDS", 0.3)

    started = manager.time.monotonic()
    with pytest.raises(RuntimeError):
        await manager.wait_process_window_ready(
            manager.ProcessInfo(pid=4242), 0, poll_interval=0.01
        )
    elapsed = manager.time.monotonic() - started

    assert elapsed >= 0.25
