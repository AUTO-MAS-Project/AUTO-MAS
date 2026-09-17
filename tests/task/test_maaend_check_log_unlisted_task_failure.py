"""MaaEnd：本轮任务表之外的任务（关闭游戏、MXU 内部任务）失败，不能让结果解析整段失效。"""

import asyncio
from datetime import datetime

from app.models.task import LogRecord, ScriptItem
from app.task.MaaEnd.AutoProxy import AutoProxyTask


def _task_with_daily() -> AutoProxyTask:
    task = AutoProxyTask.__new__(AutoProxyTask)
    task.cur_user_log = LogRecord()
    task.script_info = ScriptItem(script_id="s", name="测试 MaaEnd", status="运行")
    task.retryable = True
    task.color_match_failed_message = None
    task.account_switch_task_name = "切换账号"
    task.task_dict = {"日常任务": {"daily-1": True}}
    task.task_name_map = {"日常任务": "Daily"}
    task.wait_event = asyncio.Event()

    async def _noop(_completed: set[str]) -> None:
        return None

    task._mark_daily_once_tasks_completed = _noop  # type: ignore[method-assign]
    return task


def test_unlisted_task_failure_does_not_break_result_parsing():
    task = _task_with_daily()
    asyncio.run(
        task.check_log(
            [
                "任务开始: 日常任务",
                "任务完成: 日常任务",
                "任务开始: ❌关闭游戏（PC）",
                "任务失败: ❌关闭游戏（PC）",
            ],
            datetime.now(),
            if_stream_end=True,
        )
    )
    assert task.cur_user_log.status == "Success!"
    assert task.task_dict == {"日常任务": {"daily-1": False}}


def test_listed_task_failure_still_marks_unfinished():
    task = _task_with_daily()
    asyncio.run(
        task.check_log(
            ["任务开始: 日常任务", "任务失败: 日常任务"],
            datetime.now(),
            if_stream_end=True,
        )
    )
    assert task.cur_user_log.status == "MaaEnd 部分任务执行失败: 日常任务"
