"""BGI 分步结果进入 box 后保持原有节点、统计文本与展示模式。"""

import asyncio
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.log_box import log_box
from app.log_box.report import build_user_result_text
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
    session = log_box.get_user_session(
        push_log.make_bettergi_log_spec(steps), user=current, mode=mode
    )
    asyncio.run(session.close())
    assert steps == original
    assert current.push_log == previous.push_log
    for has_uncompleted in (False, True):
        assert build_user_result_text([current], has_uncompleted) == (
            build_user_result_text([previous], has_uncompleted)
        )


def test_step_snapshot_does_not_follow_later_mutation():
    steps = [step()]
    expected = push_log.steps_to_push_log(steps)
    spec = push_log.make_bettergi_log_spec(steps)
    steps[0]["task"] = "后续变化"
    steps[0]["ok"] = False
    user = SimpleNamespace(push_log=[], push_log_mode="汇总")
    session = log_box.get_user_session(spec, user=user, mode="汇总")
    asyncio.run(session.close())
    assert user.push_log == expected


def test_statistics_text_is_unaffected_by_box_delivery():
    from app.task.BetterGI.tools.notify import build_statistics_payload

    steps = [step(ok=False, issue_count=1, issue_text="操作没有完成")]
    message = dict(
        user_info="用户",
        start_time="开始",
        end_time="结束",
        user_result="未完成",
        one_dragon_steps=steps,
    )
    before = build_statistics_payload(title="统计", message=message).text
    user = SimpleNamespace(push_log=[], push_log_mode="汇总")
    asyncio.run(
        log_box.get_user_session(
            push_log.make_bettergi_log_spec(steps), user=user, mode="汇总"
        ).close()
    )
    after = build_statistics_payload(title="统计", message=message).text
    assert after == before
