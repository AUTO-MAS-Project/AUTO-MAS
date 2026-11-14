"""General 通知报告的过滤、账号分组与排版策略。"""

import pytest

from app.task.general.manager import GeneralManager
from app.utils import LOG_TYPE_ERROR, LOG_TYPE_NORMAL
from tests.runtime_support import RuntimeStub as SimpleNamespace


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


def test_user_groups_keep_account_order():
    first = user([(LOG_TYPE_NORMAL, "✅ 成功: 邮件")])
    second = user([(LOG_TYPE_NORMAL, "❌ 失败: 刷本")])
    second.name, second.result, second.status = "账号 B", "未完成", "异常"
    report = build_user_result_text([first, second], True)
    assert report == (
        "账号 A: 全部完成\n✅ 成功: 邮件\n\n账号 B: 未完成\n❌ 失败: 刷本"
    )
