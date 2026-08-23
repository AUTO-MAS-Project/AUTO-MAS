import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.task.MAA.AutoProxy import (
    _current_week_marker,
    _parse_annihilation_weekly_progress,
    _should_run_annihilation,
)
from app.utils.constants import UTC4


def test_maa_annihilation_schedule_and_weekly_limit() -> None:
    monday = datetime(2026, 8, 17)
    wednesday = datetime(2026, 8, 19)

    assert not _should_run_annihilation("Wednesday", "2000-W01", monday)
    assert _should_run_annihilation("Wednesday", "2000-W01", wednesday)
    assert not _should_run_annihilation("Monday", "2026-W34", wednesday)
    assert _should_run_annihilation("Monday", "2026-W33", wednesday)

    assert _parse_annihilation_weekly_progress("剿灭模式 : 1800 / 1800") == (
        1800,
        1800,
    )
    assert _parse_annihilation_weekly_progress(
        "Annihilation weekly limit: 1200/1800"
    ) == (1200, 1800)
    assert _parse_annihilation_weekly_progress("剿滅模式 : 1800 / 1800") == (
        1800,
        1800,
    )
    assert _parse_annihilation_weekly_progress("剿灭模式 : 0 / 0") is None
    assert _parse_annihilation_weekly_progress("完成任务: 剿灭作战") is None


@pytest.mark.parametrize(
    "log_content",
    [
        ["剿滅模式 : 1800 / 1800\n", "任务已全部完成！\n"],
        ["完成任务: 剿灭作战\n", "任务已全部完成！\n"],
    ],
)
def test_maa_annihilation_limit_records_the_current_week(
    log_content: list[str],
) -> None:
    writes: list[tuple[str, str, str]] = []

    class UserConfigStub:
        async def set(self, group: str, key: str, value: str) -> None:
            writes.append((group, key, value))

    task = SimpleNamespace(
        mode="Annihilation",
        cur_user_item=SimpleNamespace(name="测试用户"),
        task_dict={"Fight": True},
        cur_user_log=SimpleNamespace(content=[], status=""),
        script_info=SimpleNamespace(log=""),
        cur_user_config=UserConfigStub(),
        _annihilation_weekly_completion_recorded=False,
        run_book={"Annihilation": False},
        wait_event=SimpleNamespace(set=lambda: None),
    )

    from app.task.MAA.AutoProxy import AutoProxyTask

    asyncio.run(
        AutoProxyTask.check_log(
            task,
            log_content,
            datetime.now(),
        )
    )

    assert len(writes) == 1
    group, key, value = writes[0]
    assert (group, key) == ("Data", "AnnihilationCompletedWeek")
    assert value == _current_week_marker(datetime.now(tz=UTC4))
