"""通知汇总排版与任务完成报告的公共输出。"""

from unittest.mock import Mock

import pytest

from app.core.notify.report import render_aggregate_push_log
from app.utils import LOG_TYPE_NORMAL


@pytest.mark.asyncio
async def test_task_report_uses_l2_batch_coordinator_and_keeps_tasks_isolated(
    monkeypatch,
):
    import asyncio

    from app.core.notify import task_report
    from app.core.notify.tasks import NotificationTasks
    from app.models.task import TaskItem

    tasks = NotificationTasks()
    monkeypatch.setattr(task_report.Notify, "tasks", tasks)
    monkeypatch.setattr(task_report.Notify, "read_task_report_policy", Mock())
    standalone = object()
    factory = Mock(return_value=standalone)
    monkeypatch.setattr(task_report, "_create_coordinator", factory)
    root, other = TaskItem(), TaskItem()
    coordinator = object()

    async def prepare():
        return task_report.prepare_task_report(root).coordinator

    with tasks.task_notification_batch(task_id=root.task_id, coordinator=coordinator):
        assert await asyncio.create_task(prepare()) is coordinator
        factory.assert_not_called()
        assert task_report.prepare_task_report(other).coordinator is standalone
        assert factory.call_args.kwargs["task_id"] == other.task_id
    assert tasks.current_task_report_coordinator() is None
    assert task_report.prepare_task_report(root).coordinator is standalone


def test_aggregate_keeps_account_order_duplicates_and_warning_tail():
    entries = [
        (LOG_TYPE_NORMAL, "【乙】❌ 失败: 邮件"),
        (LOG_TYPE_NORMAL, "【甲】✅ 成功: 每日任务"),
        (LOG_TYPE_NORMAL, "【乙】⚠ 异常: 刷本（体力不足）"),
        (LOG_TYPE_NORMAL, "🔋 剩余体力: 30"),
        (LOG_TYPE_NORMAL, "【乙】✅ 成功: 邮件"),
        (LOG_TYPE_NORMAL, "【乙】✅ 成功: 邮件"),
    ]
    assert render_aggregate_push_log(entries) == [
        "【乙】✅ 成功: 邮件, 邮件",
        "【乙】❌ 失败: 邮件",
        "【甲】✅ 成功: 每日任务",
        "🔋 剩余体力: 30",
        "【乙】⚠ 异常: 刷本（体力不足）",
    ]
