"""General 调用方的报告过滤、账号分组及与调度报告的一致性。"""

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.core.task_manager.manager import build_task_result_text
from app.task.general.manager import GeneralManager
from app.utils import LOG_TYPE_ERROR, LOG_TYPE_NORMAL
from app.utils.common.log_box.results import LogEntry


def build_user_result_text(users, has_uncompleted):
    # Exercise the real caller's filtering policy, not a test copy of that policy.
    manager = SimpleNamespace(script_info=SimpleNamespace(user_list=users))
    return GeneralManager._render_user_results(manager, has_uncompleted=has_uncompleted)


def user(entries, mode="汇总", **kwargs):
    return SimpleNamespace(
        name="账号 A",
        result="全部完成",
        status="完成",
        push_log=entries,
        push_log_mode=mode,
        **kwargs,
    )


def test_scatter_keeps_account_before_time_and_plain_text_unchanged():
    timestamp = datetime(2026, 10, 29, 7, 2).timestamp()
    entries = [
        (LOG_TYPE_NORMAL, "【实例 1】✅ 成功: 邮件", timestamp),
        (LOG_TYPE_NORMAL, "旧式二元组"),
        (LOG_TYPE_NORMAL, "⏱ 超时：不应被猜成已知状态", None),
    ]
    assert build_user_result_text([user(entries, "逐条")], False) == (
        "账号 A: 全部完成\n"
        "【实例 1】07:02 - ✅ 成功: 邮件\n"
        "旧式二元组\n⏱ 超时：不应被猜成已知状态"
    )


@pytest.mark.parametrize("mode", ["逐条", "汇总", "未知存量值"])
def test_failure_type_is_independent_from_node_failure(mode):
    entries = [
        (LOG_TYPE_ERROR, "仅失败报告出现"),
        (LOG_TYPE_NORMAL, "❌ 失败: 未计入整体失败的节点"),
    ]
    rendered = build_user_result_text([user(entries, mode)], False)
    assert "仅失败报告出现" not in rendered
    assert "❌ 失败: 未计入整体失败的节点" in rendered
    assert "仅失败报告出现" in build_user_result_text([user(entries, mode)], True)


def test_off_keeps_summary_and_does_not_mutate_input():
    entries = [(LOG_TYPE_NORMAL, "✅ 成功: 邮件", 0.0)]
    assert build_user_result_text([user(entries, "关闭")], False) == "账号 A: 全部完成"
    assert entries == [(LOG_TYPE_NORMAL, "✅ 成功: 邮件", 0.0)]


def test_typed_and_legacy_entries_render_identically():
    entries = [(LOG_TYPE_NORMAL, "✅ 成功: 邮件", 0.0)]
    typed = [LogEntry.from_legacy(entry) for entry in entries]
    for mode in ("关闭", "逐条", "汇总"):
        assert build_user_result_text([user(typed, mode)], False) == (
            build_user_result_text([user(entries, mode)], False)
        )


def test_user_groups_and_dispatch_use_same_report():
    first = user([(LOG_TYPE_NORMAL, "✅ 成功: 邮件")])
    second = user([(LOG_TYPE_NORMAL, "❌ 失败: 刷本")])
    second.name, second.result, second.status = "账号 B", "未完成", "异常"
    report = build_user_result_text([first, second], True)
    assert report == (
        "账号 A: 全部完成\n✅ 成功: 邮件\n\n账号 B: 未完成\n❌ 失败: 刷本"
    )
    script = SimpleNamespace(
        name="脚本", user_list=[first, second], log="原始日志", result="旧摘要"
    )
    assert build_task_result_text([script]) == (
        "脚本：\n\n    已完成用户数：1；未完成用户数：1\n\n"
        "    账号 A: 全部完成\n    ✅ 成功: 邮件\n\n"
        "    账号 B: 未完成\n    ❌ 失败: 刷本"
    )
