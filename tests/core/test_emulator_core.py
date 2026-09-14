"""emulator_core.close_emulator 的最小回归测试。"""

import asyncio

from app.task.emulator_core import close_emulator


class _Config:
    def __init__(self, index: str = "0") -> None:
        self._index = index
        self.reads: list[tuple[str, str]] = []

    def get(self, section: str, key: str) -> str:
        self.reads.append((section, key))
        return self._index


class _Manager:
    def __init__(self, *, delay: float = 0.0, error: Exception | None = None) -> None:
        self.delay = delay
        self.error = error
        self.closed: list[str] = []

    async def close(self, index: str) -> None:
        self.closed.append(index)
        await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error


class _Owner:
    def __init__(self, manager=None, index: str = "0") -> None:
        self.emulator_manager = manager
        self.script_config = _Config(index)


def _run(awaitable):
    return asyncio.run(awaitable)


def test_closes_instance_and_reports_success() -> None:
    manager = _Manager()
    assert _run(close_emulator(_Owner(manager, "3"))) is True
    assert manager.closed == ["3"]


def test_without_taken_emulator_is_not_a_failure() -> None:
    # 未接管模拟器 = 无需关闭，不能被调用方误判成关闭失败
    assert _run(close_emulator(_Owner(None))) is True


def test_failure_returns_false() -> None:
    manager = _Manager(error=RuntimeError("设备无响应"))
    assert _run(close_emulator(_Owner(manager))) is False


def test_timeout_does_not_hang_and_counts_as_failure() -> None:
    # 模拟器无响应时关闭动作必须超时返回，不能让任务收尾无限挂起
    manager = _Manager(delay=5)
    assert _run(close_emulator(_Owner(manager), timeout=0.01)) is False
    assert manager.closed == ["0"]


def test_index_can_be_overridden_without_reading_config() -> None:
    manager = _Manager()
    owner = _Owner(manager, "0")
    assert _run(close_emulator(owner, index="7")) is True
    assert manager.closed == ["7"]
    assert owner.script_config.reads == []
