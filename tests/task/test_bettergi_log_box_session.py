"""BGI 分步结果进入 box 后保持原有节点、统计文本与展示模式。"""

import asyncio
import threading
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.task.BetterGI.AutoProxy import AutoProxyTask
from app.task.BetterGI.tools import push_log


def step(**changes):
    value = dict(
        task="领取邮件",
        start="07:02:00",
        end="07:03:00",
        ok=True,
        index=1,
        total=1,
        issue_count=0,
        issue_text="",
        warning_text="",
    )
    value.update(changes)
    return value


@pytest.fixture(autouse=True)
def frozen_step_clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 29, 7, 20, 0)

    monkeypatch.setattr(push_log, "datetime", Clock)


def test_caller_snapshot_and_delivery_survive_repeated_cancellation(monkeypatch):
    from app.task.BetterGI import AutoProxy as module

    started, release = threading.Event(), threading.Event()
    steps = [step()]
    expected = push_log.steps_to_push_log(steps)
    user = SimpleNamespace(push_log=[], push_log_mode="汇总")
    proxy = SimpleNamespace(cur_user_item=user)
    convert = module.steps_to_push_log

    def blocking_convert(snapshot):
        started.set()
        assert release.wait(5)
        return convert(snapshot)

    monkeypatch.setattr(module, "steps_to_push_log", blocking_convert)

    async def run():
        closing = asyncio.create_task(AutoProxyTask._append_step_details(proxy, steps))
        try:
            assert await asyncio.to_thread(started.wait, 3)
            steps[0]["task"] = "后续账号的新数据"
            proxy.cur_user_item = SimpleNamespace(push_log=[], push_log_mode="汇总")
            closing.cancel()
            await asyncio.sleep(0)
            closing.cancel()
            await asyncio.sleep(0)
            assert not closing.done()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await closing

    asyncio.run(run())
    assert user.push_log == expected
    assert proxy.cur_user_item.push_log == []
