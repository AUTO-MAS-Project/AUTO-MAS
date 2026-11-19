"""进度只转述专项已确认的模块结论，不由进程退出或旧结果推断成功。"""

from types import SimpleNamespace

import pytest

from app.task.HSR.AutoProxy import HSRAutoProxyTask
from app.task.HSR.tools.run_model import HSRRuntimeState
from app.task.MaaFW.tools.embedded.run_record import MaaFWRunRecorder
from app.task.MaaFW.tools.embedded.runner_task import MaaFWPluginAutoProxyTask
from app.task.run_flow import RunPoint, observe_run


def test_hsr_incomplete_module_does_not_report_success():
    owner = SimpleNamespace(
        runtime=HSRRuntimeState(log_lines=[], completion_writebacks=[])
    )
    seen = []
    with observe_run(lambda _, event: seen.append(event)):
        HSRAutoProxyTask._record_module_result(
            owner,
            user_id="user",
            user_name="User",
            module_key="EchoOfWar",
            module_name="历战余响",
            script="SRA",
            status="incomplete",
        )
    assert seen == [RunPoint("special", "failed", "EchoOfWar")]


@pytest.mark.parametrize(
    ("outcome", "category", "counted", "state"),
    [
        ("timeout", "task_timeout", True, "failed"),
        ("stopped", "script_stopped", True, "failed"),
        ("stopped", "script_stopped", False, "stopped"),
        ("stopped", "signal", True, "stopped"),
        ("stopped", "user_stopped", True, "cancelled"),
    ],
)
def test_maafw_only_reports_worker_task_events_accepted_for_this_attempt(
    outcome, category, counted, state
):
    recorder = MaaFWRunRecorder()
    owner = SimpleNamespace(
        _run_record=recorder, _run_record_call=lambda action: action()
    )
    start = {"kind": "task_start", "index": 0, "total": 1, "name": "daily", "at": 1}
    end = {
        "kind": "task_end",
        "index": 0,
        "name": "daily",
        "outcome": outcome,
        "category": category,
        "counted": counted,
        "at": 2,
    }
    seen = []
    with observe_run(lambda _, event: seen.append(event)):
        MaaFWPluginAutoProxyTask._on_run_record_event(owner, start)
        recorder.begin_attempt(1, attempt=1, title="run", planned=[("daily", None)])
        for event in (start, {"kind": "new_event"}, end):
            MaaFWPluginAutoProxyTask._on_run_record_event(owner, event)
        recorder.finish_attempt(outcome="failed")
        MaaFWPluginAutoProxyTask._on_run_record_event(owner, end)
    assert seen == [
        RunPoint("special", "entered", "daily"),
        RunPoint("special", state, "daily"),
    ]
