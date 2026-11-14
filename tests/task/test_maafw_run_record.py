"""专项子任务记录保留在 MaaFW 历史中，不向调度器返回进度对象。"""

from app.task.MaaFW.tools.embedded.run_record import MaaFWRunRecorder


def test_task_events_remain_in_specialized_history_without_public_progress():
    recorder = MaaFWRunRecorder()
    recorder.begin_attempt(
        1,
        attempt=2,
        title="第二次尝试",
        planned=[("daily", "日常")],
        retry_skipped=3,
        now=10.0,
    )
    assert (
        recorder.apply(
            {"kind": "task_start", "index": 0, "total": 1, "name": "daily", "at": 11.0}
        )
        is None
    )
    recorder.apply(
        {
            "kind": "task_end",
            "index": 0,
            "name": "daily",
            "outcome": "succeeded",
            "at": 12.0,
        }
    )
    history = recorder.history_value(1)
    assert history is not None
    assert history["attempt"] == 2
    assert history["retrySkipped"] == 3
    assert history["tasks"] == [
        {
            "index": 0,
            "name": "daily",
            "label": "日常",
            "startedAt": 11.0,
            "endedAt": 12.0,
            "outcome": "succeeded",
            "category": None,
            "counted": True,
        }
    ]


def test_first_daily_task_timeout_after_host_startup_keeps_history(monkeypatch):
    from types import SimpleNamespace

    from app.task.MaaFW.tools.core.runner.models import MaaFWRunPlan, MaaFWTaskRunPlan
    from app.task.MaaFW.tools.core.runner.runner import MaaFWRunner

    plan = MaaFWRunPlan.model_construct(
        tasks=[
            MaaFWTaskRunPlan(name=name, entry=name) for name in ("StartUp", "A", "B")
        ],
    )
    recorder = MaaFWRunRecorder()
    recorder.begin_attempt(
        1, attempt=1, title="M9A", planned=[("StartUp", None), ("A", None), ("B", None)]
    )
    runner = MaaFWRunner(plan, send_record=recorder.apply)
    posted = []

    def post_task(entry, *args):
        posted.append(entry)
        return entry

    def wait_job(job):
        if job == "A":
            runner._task_deadline_hit.set()

    runner.tasker = SimpleNamespace(post_task=post_task)
    monkeypatch.setattr(runner, "_wait_job", wait_job)
    monkeypatch.setattr(runner, "_wait_task_deadline_stop", lambda: True)
    monkeypatch.setattr(runner, "_external_stop_active", lambda tasker: False)
    monkeypatch.setattr(
        runner, "_capture_failure_screenshot", lambda *args, **kwargs: None
    )
    assert runner._run_tasks() == ["StartUp", "B"]
    assert posted == ["StartUp", "A", "B"]
    assert [
        (task.index, task.name, task.outcome) for task in recorder.current.tasks
    ] == [
        (0, "StartUp", "succeeded"),
        (1, "A", "timeout"),
        (2, "B", "succeeded"),
    ]
