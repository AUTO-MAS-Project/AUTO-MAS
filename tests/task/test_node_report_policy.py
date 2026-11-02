"""各调用方拥有过滤和展示模式，公共服务只排版已选定的数据。"""

import importlib
from types import SimpleNamespace

import pytest

import app.core.notify.report as notification_report
from app.models.notification.report import UserReportText


@pytest.mark.parametrize(
    "adapter", ["general", "Okww", "OkNte", "BAAH", "MaaEnd", "BetterGI", "ZzzOd"]
)
@pytest.mark.parametrize("mode", ["关闭", "逐条", "汇总", "未知存量值"])
@pytest.mark.parametrize("has_uncompleted", [False, True])
def test_each_manager_keeps_its_own_failure_filter_and_display_mode(
    adapter, mode, has_uncompleted
):
    module = importlib.import_module(f"app.task.{adapter}.manager")
    manager_type = getattr(
        module, "GeneralManager" if adapter == "general" else adapter + "Manager"
    )
    entries = [("普通", "❌ 失败: 节点"), ("失败", "失败时展示的详情")]
    user = SimpleNamespace(
        name="账号", result="运行结果", push_log=entries, push_log_mode=mode
    )
    manager = SimpleNamespace(script_info=SimpleNamespace(user_list=[user]))
    result = manager_type._render_user_results(manager, has_uncompleted=has_uncompleted)
    if mode == "关闭":
        assert result == "账号: 运行结果"
    else:
        assert "❌ 失败: 节点" in result
        assert ("失败时展示的详情" in result) == has_uncompleted
    assert entries == [("普通", "❌ 失败: 节点"), ("失败", "失败时展示的详情")]


def test_public_renderer_only_joins_supplied_rows():
    rows = [
        UserReportText("甲", "运行结果", ("调用方选定的详情",)),
        UserReportText("乙", "跳过"),
    ]
    assert (
        notification_report.render_user_result_text(rows)
        == "甲: 运行结果\n调用方选定的详情\n\n乙: 跳过"
    )
    assert notification_report.render_user_result_text([]) == ""
