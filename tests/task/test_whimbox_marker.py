#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

"""奇想盒日志面 marker 判定回归测试（纯函数，无 I/O）。

marker 表按上游 v3.0.5 源码定稿；上游版本微调时只改 tools/marker.py 数据，
本表逐行断言其判定语义（fatal 集 / 权威收尾行 / 早退 / 停滞 / 结果块提取）。
"""

from app.task.Whimbox.tools.marker import (
    WhimboxMarkerParser,
    extract_result_block,
    is_benign_marker,
)

PARSER = WhimboxMarkerParser()

SAMPLE_DONE_LOG = """2026-09-14 14:00:00.001 | INFO | main:run_one_dragon:77 - 开始执行一条龙任务...
2026-09-14 14:00:01.000 | INFO | all_in_one_task:step_dig:330 - 美鸭梨挖掘
2026-09-14 14:05:00.000 | INFO | main:run_one_dragon:80 - 一条龙任务完成: 任务结果如下：
✅美鸭梨挖掘已完成
⏭️周本已跳过
❌朝夕心愿未完成
账号1：
================
2026-09-14 14:05:01.000 | INFO | main:run_one_dragon:81 - 任务结束，程序退出"""

# 单步子任务抛异常：上游 catch-all 打 traceback、记 ❌ 后继续跑完后面的步骤
SAMPLE_STEP_EXCEPTION_LOG = """2026-09-14 14:00:00.001 | INFO | main:run_one_dragon:77 - 开始执行一条龙任务...
2026-09-14 14:00:10.000 | ERROR | task_template:task_run:267 - Traceback (most recent call last):
  File "whimbox/task/task_template.py", line 259, in task_run
RuntimeError: 能力方案只能是123
2026-09-14 14:05:00.000 | INFO | main:run_one_dragon:80 - 一条龙任务完成: 任务结果如下：
❌美鸭梨挖掘未完成
✅家园日常已完成
2026-09-14 14:05:01.000 | INFO | main:run_one_dragon:81 - 任务结束，程序退出"""

# 顶层任务提前中止（如「自动启动游戏」失败后跳结束）：收尾行照打，消息是失败原因
SAMPLE_ABORT_LOG = """2026-09-14 14:00:00.001 | INFO | main:run_one_dragon:77 - 开始执行一条龙任务...
2026-09-14 14:00:20.000 | INFO | main:run_one_dragon:80 - 一条龙任务完成: 未能进入游戏
2026-09-14 14:00:21.000 | INFO | main:run_one_dragon:81 - 任务结束，程序退出"""


class TestVerdicts:
    def test_running(self):
        verdict = PARSER.evaluate("", process_running=True)
        assert verdict.status == "running"

    def test_admin_fatal_beats_everything(self):
        # 上游起跑即裸 exit()（退出码 0），必须列 fatal 否则误判秒退
        log = "2026-09-14 14:00:00.001 | ERROR | main:_prepare:29 - 请用管理员权限运行"
        verdict = PARSER.evaluate(log, process_running=True)
        assert verdict.status == "fatal"
        assert "管理员" in verdict.message

    def test_step_exception_is_not_process_failure(self):
        # traceback 由每个 TaskTemplate 的 catch-all 打印，单步子任务异常同样会打；
        # 序列继续跑完并打出结果块 → 仍是 success（结果块透传单步 ❌）
        verdict = PARSER.evaluate(SAMPLE_STEP_EXCEPTION_LOG, process_running=False)
        assert verdict.status == "success"
        assert verdict.result_block is not None
        assert "❌美鸭梨挖掘未完成" in verdict.result_block

    def test_traceback_alone_is_not_fatal_while_running(self):
        # 运行中的 traceback 不判 fatal：否则会杀掉上游本来会继续跑完的一轮
        log = (
            "2026-09-14 14:00:00.001 | ERROR | x:1 - Traceback (most recent call last):"
        )
        verdict = PARSER.evaluate(log, process_running=True)
        assert verdict.status == "running"

    def test_abort_after_done_marker_is_failure(self):
        # 收尾行无论成败都打印，完成行消息不含结果块头 = 上游自己判了失败/中止
        verdict = PARSER.evaluate(SAMPLE_ABORT_LOG, process_running=False)
        assert verdict.status == "failed"
        assert "未能进入游戏" in verdict.message
        # 文案只陈述上游给的原因，不断言完成度（step8 之后的收尾步骤失败时步骤其实跑完了）
        assert verdict.message.startswith("奇想盒运行失败：")

    def test_done_marker_without_completion_line_is_success(self):
        # 完成行整行缺失属日志截断（它与收尾行本就相邻打印）：无从判负，
        # 按成功收口并留空结果块，不把「日志没读全」说成任务失败
        log = "2026-09-14 14:05:01.000 | INFO | main:run_one_dragon:81 - 任务结束，程序退出"
        verdict = PARSER.evaluate(log, process_running=False)
        assert verdict.status == "success"
        assert verdict.result_block is None

    def test_success_with_result_block(self):
        verdict = PARSER.evaluate(SAMPLE_DONE_LOG, process_running=False)
        assert verdict.status == "success"
        assert verdict.result_block is not None
        assert verdict.result_block.startswith("任务结果如下：")
        assert "✅美鸭梨挖掘已完成" in verdict.result_block
        assert "❌朝夕心愿未完成" in verdict.result_block
        assert "任务结束，程序退出" not in verdict.result_block

    def test_single_step_failure_is_not_process_failure(self):
        # 结果块里的 ❌ 行不代表进程失败：收尾行仍在 → success（结果块透传单步失败）
        verdict = PARSER.evaluate(SAMPLE_DONE_LOG, process_running=False)
        assert verdict.status == "success"

    def test_exited_early(self):
        log = "2026-09-14 14:00:00.001 | INFO | main:77 - 开始执行一条龙任务..."
        verdict = PARSER.evaluate(log, process_running=False)
        assert verdict.status == "exited_early"

    def test_stalled(self):
        log = "2026-09-14 14:00:00.001 | INFO | main:77 - 开始执行一条龙任务..."
        verdict = PARSER.evaluate(
            log, process_running=True, stalled=True, stalled_minutes=30
        )
        assert verdict.status == "stalled"
        assert "30" in verdict.message

    def test_stalled_ignored_when_running_without_flag(self):
        log = "2026-09-14 14:00:00.001 | INFO | main:77 - 开始执行一条龙任务..."
        verdict = PARSER.evaluate(log, process_running=True, stalled=False)
        assert verdict.status == "running"


class TestBenignMarkers:
    """「非失败提示」表：上游以 ❌ 打出、实为正常状态的文案不进失败原因段。"""

    def test_digging_in_progress_is_benign(self):
        # dig_task_v2 在挖掘位仍在冷却时打 ❌「正在挖掘，无法收获」，对用户是「今日没得收」
        assert is_benign_marker("❌ 正在挖掘，无法收获")

    def test_real_failures_are_not_benign(self):
        assert not is_benign_marker('❌ 路线"朝夕心愿_采集"不存在，请先下载该路线')
        assert not is_benign_marker("❌ 游戏窗口前置失败")
        assert not is_benign_marker("🛑 任务已停止")


class TestResultBlock:
    def test_missing_head(self):
        assert extract_result_block("任务结束，程序退出") is None

    def test_abort_message_is_not_a_result_block(self):
        # 完成行存在但不是结果块（中止原因）→ 不产出结果块，判定为 failed
        assert extract_result_block(SAMPLE_ABORT_LOG) is None

    def test_multiline_block_tail_trimmed(self):
        log = "x - 一条龙任务完成: 任务结果如下：\n✅A已完成\n任务结束，程序退出"
        block = extract_result_block(log)
        assert block == "任务结果如下：\n✅A已完成"

    def test_logru_done_line_prefix_is_trimmed(self):
        # 真机格式：收尾行自带 loguru 前缀，按行首截断才不会把那半截前缀
        # 当成垃圾尾行留在报告里（报告里出现过「… | INFO | main:run_one_dragon:81 - 」）
        log = (
            "2026-09-24 22:15:26.801 | INFO     | main:run_one_dragon:80 - "
            "一条龙任务完成: 任务结果如下：\n"
            "❌美鸭梨挖掘未完成\n"
            "✅奇迹之旅已完成\n"
            "2026-09-24 22:15:26.802 | INFO     | main:run_one_dragon:81 - "
            "任务结束，程序退出"
        )
        block = extract_result_block(log)
        assert block == "任务结果如下：\n❌美鸭梨挖掘未完成\n✅奇迹之旅已完成"
        assert "INFO" not in block
        assert "run_one_dragon" not in block
