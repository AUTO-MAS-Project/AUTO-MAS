"""订阅拒绝变更时，信号分发关闭尚未执行的协程并保留原异常。"""

import inspect

import pytest
from blinker import Signal

from app.config import FieldChangeEvent
from app.config.core.node import _dispatch
from app.models.config import QueueConfig


@pytest.mark.asyncio
@pytest.mark.parametrize("async_rejection", [False, True])
async def test_signal_rejection_closes_created_coroutines(monkeypatch, async_rejection):
    signal = Signal()
    sender = QueueConfig()
    event = FieldChangeEvent(
        kind="set",
        node=sender,
        group="Info",
        field="Name",
        value="new",
        old_value="old",
    )
    created = []
    observed = []

    async def observe(label):
        observed.append(label)

    async def reject():
        raise ValueError("rejected")

    def before(*args, **kwargs):
        created.append(observe("before"))
        return created[-1]

    def veto(*args, **kwargs):
        if not async_rejection:
            raise ValueError("rejected")
        created.append(reject())
        return created[-1]

    def after(*args, **kwargs):
        created.append(observe("after"))
        return created[-1]

    # 仅固定接收顺序，覆盖同步收集阶段和异步执行阶段两种拒绝。
    monkeypatch.setattr(signal, "receivers_for", lambda _: iter((before, veto, after)))
    try:
        with pytest.raises(ValueError, match="rejected"):
            await _dispatch(signal, sender, event)
        assert observed == (["before"] if async_rejection else [])
        assert all(
            inspect.getcoroutinestate(coro) == inspect.CORO_CLOSED for coro in created
        )
    finally:
        for coro in created:
            coro.close()
    count = len(created)
    with signal.muted():
        await _dispatch(signal, sender, event)
    assert len(created) == count
