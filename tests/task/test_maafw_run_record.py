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
