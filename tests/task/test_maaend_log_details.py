"""MaaEnd 新旧日志格式均应进入当前用户的任务报告。"""

import asyncio

from app.task.MaaEnd.AutoProxy import AutoProxyTask
from tests.runtime_support import RuntimeStub as SimpleNamespace


def test_details_do_not_cross_task_or_retry_boundaries(tmp_path):
    proxy = AutoProxyTask.__new__(AutoProxyTask)
    proxy.user_state = lambda user: user
    proxy.cur_user_item = SimpleNamespace(push_log=[], push_log_mode="汇总")
    proxy.push_log_enabled = True
    path = tmp_path / "run.log"
    messages = [
        "无主采集失败",
        "任务开始: 自动采集",
        "岩天使叶采集失败",
        "任务失败: 自动采集",
        "任务开始: 自动采集",
        "任务完成: 自动采集",
        "迟到采集失败",
        "任务开始: 自动囤货",
        "🚨发生严重错误，已停止任务（商品识别结果不可用）",
        "任务失败: 自动囤货",
        "任务开始: 送礼",
        "⚠️ 寻路或寻找干员失败，尝试重试...",
        "任务失败: 送礼",
        "任务开始: 拜访好友",
        "现在游戏时间是周一，根据执行周期跳过任务",
        "任务完成: 拜访好友",
    ]
    path.write_text(
        "".join(f"[2026-11-02 10:13:00.000] {text}\n" for text in messages),
        encoding="utf-8",
    )
    asyncio.run(proxy._append_stage_log_details([path]))
    assert [entry[1] for entry in proxy.cur_user_item.push_log] == [
        "✅ 成功: 自动采集",
        "❌ 失败: 自动囤货（商品识别结果不可用）",
        "❌ 失败: 送礼（寻路或寻找干员失败）",
        "⏭ 跳过: 拜访好友",
    ]
