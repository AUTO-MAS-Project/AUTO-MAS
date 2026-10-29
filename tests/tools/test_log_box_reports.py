"""节点交付与报告的公共契约；不需要脚本、账号或通知渠道。"""

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.log_box import LogCollect, LogType
from app.log_box.report import (
    build_task_result_text,
    build_user_result_text,
    mirror_report_to_dispatch,
    render_aggregate_push_log,
)
from app.log_box.results import LogEntry, Node


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
        (LogType.NORMAL, "【实例 1】✅ 成功: 邮件", timestamp),
        (LogType.NORMAL, "旧式二元组"),
        (LogType.NORMAL, "⏱ 超时：不应被猜成已知状态", None),
    ]
    assert build_user_result_text([user(entries, "逐条")], False) == (
        "账号 A: 全部完成\n"
        "【实例 1】07:02 - ✅ 成功: 邮件\n"
        "旧式二元组\n⏱ 超时：不应被猜成已知状态"
    )


def test_aggregate_keeps_account_order_duplicates_and_warning_tail():
    entries = [
        (LogType.NORMAL, "【乙】❌ 失败: 邮件"),
        (LogType.NORMAL, "【甲】✅ 成功: 每日任务"),
        (LogType.NORMAL, "【乙】⚠ 异常: 刷本（体力不足）"),
        (LogType.NORMAL, "🔋 剩余体力: 30"),
        (LogType.NORMAL, "【乙】✅ 成功: 邮件"),
        (LogType.NORMAL, "【乙】✅ 成功: 邮件"),
    ]
    assert render_aggregate_push_log(entries) == [
        "【乙】✅ 成功: 邮件, 邮件",
        "【乙】❌ 失败: 邮件",
        "【甲】✅ 成功: 每日任务",
        "🔋 剩余体力: 30",
        "【乙】⚠ 异常: 刷本（体力不足）",
    ]


@pytest.mark.parametrize("mode", ["逐条", "汇总", "未知存量值"])
def test_failure_type_is_independent_from_node_failure(mode):
    entries = [
        (LogType.FAIL, "仅失败报告出现"),
        (LogType.NORMAL, "❌ 失败: 未计入整体失败的节点"),
    ]
    rendered = build_user_result_text([user(entries, mode)], False)
    assert "仅失败报告出现" not in rendered
    assert "❌ 失败: 未计入整体失败的节点" in rendered
    assert "仅失败报告出现" in build_user_result_text([user(entries, mode)], True)


def test_off_keeps_summary_and_does_not_mutate_input():
    entries = [(LogType.NORMAL, "✅ 成功: 邮件", 0.0)]
    assert build_user_result_text([user(entries, "关闭")], False) == "账号 A: 全部完成"
    assert entries == [(LogType.NORMAL, "✅ 成功: 邮件", 0.0)]


def test_typed_and_legacy_entries_render_identically():
    entries = [(LogType.NORMAL, "✅ 成功: 邮件", 0.0)]
    typed = [LogEntry.from_legacy(entry) for entry in entries]
    for mode in ("关闭", "逐条", "汇总"):
        assert build_user_result_text([user(typed, mode)], False) == (
            build_user_result_text([user(entries, mode)], False)
        )


def test_user_groups_and_dispatch_use_same_report():
    first = user([(LogType.NORMAL, "✅ 成功: 邮件")])
    second = user([(LogType.NORMAL, "❌ 失败: 刷本")])
    second.name, second.result, second.status = "账号 B", "未完成", "异常"
    report = build_user_result_text([first, second], True)
    assert report == (
        "账号 A: 全部完成\n✅ 成功: 邮件\n\n账号 B: 未完成\n❌ 失败: 刷本"
    )
    script = SimpleNamespace(
        name="脚本", user_list=[first, second], log="原始日志", result="旧摘要"
    )
    mirror_report_to_dispatch(script, report)
    assert script.log == "原始日志\n" + report
    assert build_task_result_text([script]) == (
        "脚本：\n\n    已完成用户数：1；未完成用户数：1\n\n"
        "    账号 A: 全部完成\n    ✅ 成功: 邮件\n\n"
        "    账号 B: 未完成\n    ❌ 失败: 刷本"
    )


def test_no_nodes_and_all_maintenance_keep_existing_completion_layout():
    account = user([], maintenance_skipped=True)
    script = SimpleNamespace(name="脚本", user_list=[account], result="维护跳过")
    assert build_task_result_text([script]) == "脚本：\n\n    维护跳过"
    script.user_list = []
    script.status = "跳过"
    assert build_task_result_text([script]) == "脚本：\n\n    已跳过"
    assert build_task_result_text([]) == "任务未加载"


def test_node_contract_keeps_legacy_recognition_boundary():
    node = Node(status="success", name="邮件", account="实例 1")
    assert Node.from_text(node.text) == node
    assert Node.from_text("✅ 成功：邮件") is None
    assert Node.from_text("⚠️ 节点采集失败") is None
    with pytest.raises(ValueError):
        Node(status="unknown", name="邮件")


@pytest.mark.parametrize("timestamp", [float("nan"), float("inf"), True, "07:02"])
def test_entry_rejects_invalid_time(timestamp):
    with pytest.raises(ValueError):
        LogEntry(LogType.NORMAL, "邮件", timestamp)


def test_collect_keeps_start_offset_preprocessing_and_close_idempotency(
    tmp_path, monkeypatch
):
    path = tmp_path / "run.log"
    path.write_text("OK: 历史内容\n", encoding="utf-8")
    received = []
    collect = LogCollect(path, sink=lambda *entry: received.append(entry))

    @collect.open()
    def translate(line):
        return line.replace("OK:", "成功:") if "心跳" not in line else None

    collect.collect(r"^成功:", r'"✅ 成功: " + $((?:成功: )(.+))')
    monkeypatch.setattr("app.log_box.pipeline.time.time", lambda: 100.0)
    with path.open("a", encoding="utf-8") as stream:
        stream.write("心跳\nOK: 邮件\nOK: 每日任务\n")

    calls = []

    def resolve(entries):
        calls.append(tuple(entries))
        return list(reversed(entries))

    collect.close(resolve)
    collect.close(resolve)
    assert len(calls) == 1
    assert received == [
        (LogType.NORMAL, "✅ 成功: 每日任务", 100.0),
        (LogType.NORMAL, "✅ 成功: 邮件", 100.0),
    ]


def test_collect_error_keeps_existing_caller_owned_fallback(tmp_path):
    path = tmp_path / "run.log"
    path.write_text("任务完成\n", encoding="utf-8")
    received = []
    collect = LogCollect(
        path, sink=lambda *entry: received.append(entry), start_from_end=False
    )
    collect.collect("任务完成")

    def fail(entries):
        raise RuntimeError("处理器异常")

    with pytest.raises(RuntimeError, match="处理器异常"):
        collect.close(fail)
    collect.close()
    assert received == []
