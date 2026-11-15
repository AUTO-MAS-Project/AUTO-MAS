"""MaaEnd 新旧日志格式均应进入当前用户的任务报告。"""

import asyncio

from app.task.MaaEnd.AutoProxy import AutoProxyTask
from tests.runtime_support import RuntimeStub as SimpleNamespace


def test_late_failure_does_not_override_current_task(tmp_path):
    proxy = AutoProxyTask.__new__(AutoProxyTask)
    proxy.user_state = lambda user: user
    proxy.cur_user_item = SimpleNamespace(push_log=[], push_log_mode="汇总")
    proxy.push_log_enabled = True
    path = tmp_path / "run.log"
    messages = [
        "无主采集失败",
        "迟到采集失败",
        "任务开始: 自动囤货",
        "🚨发生严重错误，已停止任务（商品识别结果不可用）",
        "任务失败: 自动囤货",
    ]
    path.write_text(
        "".join(f"[2026-11-02 10:13:00.000] {text}\n" for text in messages),
        encoding="utf-8",
    )
    asyncio.run(proxy._append_stage_log_details([path]))
    assert [entry[1] for entry in proxy.cur_user_item.push_log] == [
        "❌ 失败: 自动囤货（商品识别结果不可用）",
    ]
