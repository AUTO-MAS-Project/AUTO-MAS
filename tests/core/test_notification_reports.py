"""通知汇总排版与任务完成报告的公共输出。"""

from types import SimpleNamespace

from app.core.notify.report import render_aggregate_push_log
from app.core.task_manager.manager import build_task_result_text
from app.utils import LOG_TYPE_NORMAL


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


def test_no_nodes_and_all_maintenance_keep_existing_completion_layout():
    account = SimpleNamespace(push_log=[], maintenance_skipped=True)
    script = SimpleNamespace(name="脚本", user_list=[account], result="维护跳过")
    assert build_task_result_text([script]) == "脚本：\n\n    维护跳过"
    script.user_list = []
    script.status = "跳过"
    assert build_task_result_text([script]) == "脚本：\n\n    已跳过"
    assert build_task_result_text([]) == "任务未加载"
