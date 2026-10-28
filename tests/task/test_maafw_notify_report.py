"""MFW 推送里给人看的运行结果（``tools/embedded/run_report.py``）。

守的是用户在通知里看到的内容：
- 时间线只列最后一次尝试，中途重试过、打转过、超时过但最后成功的不列；
- 前面尝试完成、这次被重试跳过的任务按完成时刻并进来；
- 失败原因只留人话，节点名、画面文字、框架事件、路径、异常原文不进推送；
- 一个任务都没开始时说清楚为什么没跑成，不把 worker 崩溃说成 MAS 出错。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.task.MaaFW.tools.embedded.run_record import MaaFWRunRecorder
from app.task.MaaFW.tools.embedded.run_report import (
    MaaFWAttemptReport,
    failure_summary,
    format_timeline,
    human_reason,
)

# 只给排障看的字样，出现在推送里就是漏了
DIAGNOSTIC_WORDS = (
    "停在",
    "TargetCount",
    "画面文字",
    "Node.",
    "→",
    "Traceback",
    "C:\\",
)


def _at(hour: int, minute: int) -> float:
    return datetime(2026, 10, 28, hour, minute).timestamp()


def _start(index: int, name: str, label: str, at: float) -> dict:
    return {
        "kind": "task_start",
        "index": index,
        "total": 3,
        "name": name,
        "label": label,
        "at": at,
    }


def _end(
    index: int,
    name: str,
    outcome: str,
    at: float,
    category: str | None = None,
    *,
    counted: bool = True,
) -> dict:
    return {
        "kind": "task_end",
        "index": index,
        "name": name,
        "outcome": outcome,
        "category": category,
        "counted": counted,
        "at": at,
    }


THREE = [("Start", "启动游戏"), ("Wild", "收取荒原"), ("Gather", "自动采集")]


def _attempt(
    recorder: MaaFWRunRecorder,
    number: int,
    planned: list[tuple[str, str]],
    events: list[dict],
    *,
    begin: float,
    end: float,
    outcome: str = "failed",
    category: str | None = None,
) -> None:
    recorder.begin_attempt(
        number, attempt=number, title=f"第 {number} 次尝试", planned=planned, now=begin
    )
    for event in events:
        recorder.apply(event)
    recorder.finish_attempt(outcome=outcome, category=category, now=end)  # type: ignore[arg-type]


def _assert_no_diagnostics(*texts: str) -> None:
    for text in texts:
        for word in DIAGNOSTIC_WORDS:
            assert word not in text, (word, text)


def test_retry_then_success_lists_only_final_outcomes() -> None:
    recorder = MaaFWRunRecorder()
    _attempt(
        recorder,
        1,
        THREE,
        [
            _start(0, "Start", "启动游戏", _at(7, 0)),
            _end(0, "Start", "succeeded", _at(7, 2)),
            _start(1, "Wild", "收取荒原", _at(7, 3)),
            _end(1, "Wild", "loop", _at(7, 30), "loop_guard"),
            _start(2, "Gather", "自动采集", _at(7, 31)),
            _end(2, "Gather", "timeout", _at(7, 41), "task_timeout"),
        ],
        begin=_at(7, 0),
        end=_at(7, 42),
    )
    _attempt(
        recorder,
        2,
        THREE,
        [
            _start(0, "Start", "启动游戏", _at(8, 0)),
            _end(0, "Start", "succeeded", _at(8, 1)),
            _start(1, "Wild", "收取荒原", _at(8, 2)),
            _end(1, "Wild", "succeeded", _at(8, 10)),
            _start(2, "Gather", "自动采集", _at(8, 11)),
            _end(2, "Gather", "succeeded", _at(8, 20)),
        ],
        begin=_at(8, 0),
        end=_at(8, 21),
        outcome="success",
    )
    timeline = format_timeline(
        [MaaFWAttemptReport(record=r) for r in recorder.attempts()]
    )
    assert timeline.splitlines() == [
        "08:01 - ✅ 成功：启动游戏",
        "08:10 - ✅ 成功：收取荒原",
        "08:20 - ✅ 成功：自动采集",
    ]


def test_retry_skipped_task_carried_with_its_finish_time() -> None:
    # 重试计划剔掉了前面已完成的收取荒原；时间线按当时完成的时刻把它并进来
    recorder = MaaFWRunRecorder()
    _attempt(
        recorder,
        1,
        THREE,
        [
            _start(0, "Start", "启动游戏", _at(21, 0)),
            _end(0, "Start", "succeeded", _at(21, 1)),
            _start(1, "Wild", "收取荒原", _at(21, 2)),
            _end(1, "Wild", "succeeded", _at(21, 5)),
            _start(2, "Gather", "自动采集", _at(21, 6)),
            _end(2, "Gather", "loop", _at(21, 18), "loop_guard"),
        ],
        begin=_at(21, 0),
        end=_at(21, 19),
    )
    _attempt(
        recorder,
        2,
        [("Start", "启动游戏"), ("Gather", "自动采集")],
        [
            _start(0, "Start", "启动游戏", _at(21, 25)),
            _end(0, "Start", "succeeded", _at(21, 26)),
            _start(1, "Gather", "自动采集", _at(21, 27)),
            _end(1, "Gather", "succeeded", _at(21, 40)),
        ],
        begin=_at(21, 25),
        end=_at(21, 41),
        outcome="success",
    )
    timeline = format_timeline(
        [MaaFWAttemptReport(record=r) for r in recorder.attempts()]
    )
    assert timeline.splitlines() == [
        "21:05 - ✅ 成功：收取荒原",
        "21:26 - ✅ 成功：启动游戏",
        "21:40 - ✅ 成功：自动采集",
    ]


def test_final_failure_shows_last_attempt_with_plain_reasons() -> None:
    recorder = MaaFWRunRecorder()
    planned = [*THREE, ("Close", "关闭游戏")]
    _attempt(
        recorder,
        1,
        planned,
        [
            _start(0, "Start", "启动游戏", _at(7, 0)),
            _end(0, "Start", "succeeded", _at(7, 2)),
            _start(1, "Wild", "收取荒原", _at(7, 3)),
            _end(1, "Wild", "loop", _at(7, 30), "loop_guard"),
        ],
        begin=_at(7, 0),
        end=_at(7, 31),
    )
    _attempt(
        recorder,
        2,
        planned,
        [
            _start(0, "Start", "启动游戏", _at(8, 0)),
            _end(0, "Start", "succeeded", _at(8, 1)),
            _start(1, "Wild", "收取荒原", _at(8, 2)),
            _end(1, "Wild", "failed", _at(8, 15), "task_failed"),
            _start(2, "Gather", "自动采集", _at(8, 16)),
            _end(2, "Gather", "timeout", _at(8, 30), "task_timeout"),
            # 收尾任务失败不计入本轮失败：时间线照列，结果行不写
            _start(3, "Close", "关闭游戏", _at(8, 30)),
            _end(3, "Close", "failed", _at(8, 31), "task_failed", counted=False),
        ],
        begin=_at(8, 0),
        end=_at(8, 32),
    )
    first, second = recorder.attempts()
    attempts = [
        MaaFWAttemptReport(
            record=first,
            user_message="收取荒原：任务失败，MaaFW 任务原地打转（A → B 已循环 200 轮）",
            failed_task="Wild",
        ),
        MaaFWAttemptReport(
            record=second,
            user_message=(
                "2 个任务失败：收取荒原（体力不足；停在 TargetCountAbort，操作没有完成；"
                "画面文字：体力不足，是否购买）；自动采集（MaaFW 单任务超时（限制 10 分钟））"
            ),
            failed_task="Wild",
        ),
    ]
    timeline = format_timeline(attempts)
    assert timeline.splitlines() == [
        "08:01 - ✅ 成功：启动游戏",
        "08:15 - ❌ 失败：收取荒原（体力不足，操作没有完成）",
        "08:30 - ⏱ 超时：自动采集",
        "08:31 - ❌ 失败：关闭游戏",
    ]
    summary = failure_summary(attempts)
    assert summary == "失败：收取荒原（体力不足，操作没有完成）；超时：自动采集"
    _assert_no_diagnostics(timeline, summary)


def test_nothing_started_explains_why() -> None:
    recorder = MaaFWRunRecorder()
    _attempt(
        recorder,
        1,
        THREE,
        [
            {"kind": "stage", "stage": "device", "state": "begin", "at": _at(6, 0)},
            {
                "kind": "stage",
                "stage": "device",
                "state": "end",
                "ok": False,
                "at": _at(6, 1),
            },
        ],
        begin=_at(6, 0),
        end=_at(6, 2),
    )
    (record,) = recorder.attempts()
    # runner 没给人话：按失败在哪一步说
    silent = [MaaFWAttemptReport(record=record)]
    assert format_timeline(silent) == ""
    assert failure_summary(silent) == "MaaFW 运行失败：设备（ADB）没有就绪"
    # 宿主自己那句话是人话：照原话说
    told = [
        MaaFWAttemptReport(
            record=record,
            user_message="当前 controller 需要 ADB，请在脚本管理页选择模拟器",
        )
    ]
    assert failure_summary(told) == (
        "MaaFW 运行失败：当前 controller 需要 ADB，请在脚本管理页选择模拟器"
    )


def test_last_attempt_not_started_keeps_earlier_completions() -> None:
    recorder = MaaFWRunRecorder()
    _attempt(
        recorder,
        1,
        THREE,
        [
            _start(0, "Start", "启动游戏", _at(7, 0)),
            _end(0, "Start", "succeeded", _at(7, 2)),
            _start(1, "Wild", "收取荒原", _at(7, 3)),
            _end(1, "Wild", "loop", _at(7, 30), "loop_guard"),
            _start(2, "Gather", "自动采集", _at(7, 31)),
            _end(2, "Gather", "succeeded", _at(7, 41)),
        ],
        begin=_at(7, 0),
        end=_at(7, 42),
    )
    _attempt(
        recorder,
        2,
        [("Wild", "收取荒原")],
        [
            {"kind": "stage", "stage": "device", "state": "begin", "at": _at(8, 0)},
            {
                "kind": "stage",
                "stage": "device",
                "state": "end",
                "ok": False,
                "at": _at(8, 1),
            },
        ],
        begin=_at(8, 0),
        end=_at(8, 2),
    )
    attempts = [MaaFWAttemptReport(record=r) for r in recorder.attempts()]
    assert format_timeline(attempts).splitlines() == [
        "07:02 - ✅ 成功：启动游戏",
        "07:41 - ✅ 成功：自动采集",
        "08:02 - ⏭ 跳过：收取荒原",
    ]
    assert failure_summary(attempts) == "MaaFW 运行失败：设备（ADB）没有就绪"


def test_same_name_tasks_carried_by_count() -> None:
    # 队列里同一个任务排了两次：前面两次都完成、这次只重跑另一个任务时，两次都要并进来
    recorder = MaaFWRunRecorder()
    planned = [("Fight", "刷关卡"), ("Fight", "刷关卡"), ("Wild", "收取荒原")]
    _attempt(
        recorder,
        1,
        planned,
        [
            _start(0, "Fight", "刷关卡", _at(7, 0)),
            _end(0, "Fight", "succeeded", _at(7, 5)),
            _start(1, "Fight", "刷关卡", _at(7, 6)),
            _end(1, "Fight", "succeeded", _at(7, 9)),
            _start(2, "Wild", "收取荒原", _at(7, 10)),
            _end(2, "Wild", "failed", _at(7, 12), "task_failed"),
        ],
        begin=_at(7, 0),
        end=_at(7, 13),
    )
    _attempt(
        recorder,
        2,
        [("Wild", "收取荒原")],
        [
            _start(0, "Wild", "收取荒原", _at(8, 0)),
            _end(0, "Wild", "succeeded", _at(8, 3)),
        ],
        begin=_at(8, 0),
        end=_at(8, 4),
        outcome="success",
    )
    timeline = format_timeline(
        [MaaFWAttemptReport(record=r) for r in recorder.attempts()]
    )
    assert timeline.splitlines() == [
        "07:05 - ✅ 成功：刷关卡",
        "07:09 - ✅ 成功：刷关卡",
        "08:03 - ✅ 成功：收取荒原",
    ]


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("MaaFW worker 意外退出（退出码 3221225477）", "MaaFW worker 意外退出"),
        ("MaaFW runner worker exited without result: 3221225477", "运行意外中断"),
    ],
)
def test_worker_crash_mid_task_not_blamed_on_mas(message: str, expected: str) -> None:
    recorder = MaaFWRunRecorder()
    _attempt(
        recorder,
        1,
        [("Wild", "收取荒原")],
        [_start(0, "Wild", "收取荒原", _at(7, 1))],
        begin=_at(7, 0),
        end=_at(7, 2),
        category="host_error",
    )
    (record,) = recorder.attempts()
    attempts = [MaaFWAttemptReport(record=record, user_message=message)]
    timeline = format_timeline(attempts)
    summary = failure_summary(attempts)
    assert expected in timeline and expected in summary
    assert "MAS" not in timeline and "MAS" not in summary
    assert "exited without result" not in timeline + summary


def test_human_reason_keeps_only_plain_sentences() -> None:
    # (runner / 宿主原话, 推送里该剩下的话)；每行代表一类只给排障看的片段
    cases = [
        # 节点位置与画面文字，节点名里带逗号
        (
            "体力不足；停在 确认，购买，没认出接下来的画面；画面文字：确定，取消",
            "体力不足，没认出接下来的画面",
        ),
        # 特调关键任务中止本轮：前缀后面才是节点位置
        (
            "切换账号失败，本轮剩余任务已跳过：停在 确认，购买，操作没有完成",
            "切换账号失败，操作没有完成",
        ),
        # 节点名带分号
        (
            "收取荒原：任务失败，停在 确认；购买，操作没有完成",
            "收取荒原：任务失败，操作没有完成",
        ),
        # 框架事件只留冒号前那半句人话
        (
            "运行前设置「启动游戏（PC）」失败：Node.Action.Failed, LaunchGame",
            "运行前设置「启动游戏（PC）」失败",
        ),
        # 英文异常尾巴、日志指引
        ("ADB 连接失败: error: device '127.0.0.1:16384' not found", "ADB 连接失败"),
        (
            "运行前设置「启动」失败：最后一行输出还没换行，完整内容稍后写进后端日志",
            "运行前设置「启动」失败",
        ),
        # 整句都是排障细节：路径、异常类名、键=值（可能是凭据）
        ("找不到文件 C:\\Users\\u\\AppData\\x.png", ""),
        ("RuntimeError: controller 截图失败", ""),
        ("登录失败 password=hunter2", ""),
    ]
    for message, expected in cases:
        assert human_reason(message) == expected, message
