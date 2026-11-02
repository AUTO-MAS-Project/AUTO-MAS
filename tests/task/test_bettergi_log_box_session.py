"""BGI 分步结果进入 box 后保持原有节点、统计文本与展示模式。"""

import asyncio
import threading
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.task.BetterGI.AutoProxy import AutoProxyTask
from app.task.BetterGI.tools import push_log
from app.task.general.manager import GeneralManager


def build_user_result_text(users, has_uncompleted):
    manager = SimpleNamespace(script_info=SimpleNamespace(user_list=users))
    return GeneralManager._render_user_results(manager, has_uncompleted=has_uncompleted)


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


@pytest.mark.parametrize("mode", ["关闭", "逐条", "汇总"])
@pytest.mark.parametrize(
    "steps",
    [
        [step()],
        [step(ok=False, issue_count=1, issue_text="操作没有完成")],
        [step(skipped=True, skip_text="未到执行周期")],
        [step(warning_text="需要处理库存")],
        [step(), step(index=2, total=2)],
        [step(task="", start="无法解析的时刻")],
        [],
    ],
)
def test_bgi_report_matches_direct_injection(mode, steps):
    original = deepcopy(steps)
    previous, current = [
        SimpleNamespace(
            name="用户",
            result="执行完成",
            push_log_mode=mode,
            push_log=[],
            status="完成",
        )
        for _ in range(2)
    ]
    if mode != "关闭":
        previous.push_log.extend(push_log.steps_to_push_log(steps))
    proxy = SimpleNamespace(cur_user_item=current)
    asyncio.run(AutoProxyTask._append_step_details(proxy, steps))
    assert steps == original
    assert current.push_log == previous.push_log
    for has_uncompleted in (False, True):
        assert build_user_result_text([current], has_uncompleted) == (
            build_user_result_text([previous], has_uncompleted)
        )


def test_statistics_text_is_unaffected_by_box_delivery():
    import app.core.notify.formats.bettergi as _format_bettergi

    steps = [step(ok=False, issue_count=1, issue_text="操作没有完成")]
    message = dict(
        user_info="用户",
        start_time="开始",
        end_time="结束",
        user_result="未完成",
        one_dragon_steps=steps,
    )
    before = _format_bettergi.build_statistics_payload(
        title="统计", message=message
    ).text
    user = SimpleNamespace(push_log=[], push_log_mode="汇总")
    asyncio.run(
        AutoProxyTask._append_step_details(SimpleNamespace(cur_user_item=user), steps)
    )
    after = _format_bettergi.build_statistics_payload(
        title="统计", message=message
    ).text
    assert after == before


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
