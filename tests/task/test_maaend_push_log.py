"""app/task/MaaEnd/push_log.py 规则与后处理回归测试。

规则经 log_box 引擎端到端验证（源 = 模拟 MaaEnd.exe stdout 落盘的历史日志），
后处理验证状态聚合语义（最后一次出现为准；只有开始无终态 = 失败）。
"""

import unittest

from app.log_box import log_box
from app.log_box.logtype import LogType
from app.task.MaaEnd.push_log import MAAEND_PUSH_RULES, maaend_resolve

# 结果元组含采集时间戳；(日志类型, 文本, 时间戳)
T = 1000.0


class MaaEndResolveTest(unittest.TestCase):
    """maaend_resolve 后处理纯逻辑：终态覆盖、重试收束、开始无终态判失败。"""

    def test_success_fail_states(self) -> None:
        results = [
            (LogType.NORMAL, "✅ 成功: 抢委托送货", T),
            (LogType.NORMAL, "❌ 失败: 模拟空间", T),
        ]
        self.assertEqual(maaend_resolve(results), results)

    def test_start_only_marks_failed(self) -> None:
        # 只有开始没有终态（进程中途退出）＝ 失败，与判态语义一致
        self.assertEqual(
            maaend_resolve([(LogType.NORMAL, "模拟空间", T)]),
            [(LogType.NORMAL, "❌ 失败: 模拟空间", T)],
        )

    def test_retry_success_overrides_previous_fail(self) -> None:
        # 先失败后重试成功：最后一次出现为准（与 task_dict 重试收束一致）
        results = [
            (LogType.NORMAL, "❌ 失败: 模拟空间", 1.0),
            (LogType.NORMAL, "✅ 成功: 模拟空间", 2.0),
        ]
        self.assertEqual(
            maaend_resolve(results),
            [(LogType.NORMAL, "✅ 成功: 模拟空间", 2.0)],
        )

    def test_retry_start_only_overrides_previous_success(self) -> None:
        # 已成功任务不会重跑；反向场景（终态后再次开始）按最后一次出现判失败
        results = [
            (LogType.NORMAL, "✅ 成功: 模拟空间", 1.0),
            (LogType.NORMAL, "模拟空间", 2.0),
        ]
        self.assertEqual(
            maaend_resolve(results),
            [(LogType.NORMAL, "❌ 失败: 模拟空间", 2.0)],
        )

    def test_order_keeps_last_occurrence(self) -> None:
        results = [
            (LogType.NORMAL, "✅ 成功: 任务A", 1.0),
            (LogType.NORMAL, "❌ 失败: 任务B", 2.0),
            (LogType.NORMAL, "任务A", 3.0),
        ]
        self.assertEqual(
            [text for _, text, _ in maaend_resolve(results)],
            ["❌ 失败: 任务B", "❌ 失败: 任务A"],
        )

    def test_empty_results(self) -> None:
        self.assertEqual(maaend_resolve([]), [])


class MaaEndRulesEndToEndTest(unittest.TestCase):
    """规则经 log_box 引擎端到端验证（模拟 stdout 历史日志全文采集）。"""

    def _collect(self, lines: list[str]) -> list[tuple[str, str, float]]:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "stage.log"
            log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            collected: list[tuple[str, str, float]] = []
            col = log_box.get_collect(
                paths=[log_file],
                sink=lambda log_type, text, ts: collected.append((log_type, text, ts)),
                start_from_end=False,
            )
            for rule in MAAEND_PUSH_RULES:
                col.collect(*rule)
            col.close(maaend_resolve)
            return collected

    def test_full_pipeline(self) -> None:
        from datetime import datetime

        lines = [
            "[2026-09-17 11:20:34.481] 正在执行预任务: ⚙️游戏设置",
            "[2026-09-17 11:20:52.790] 任务开始: 🏍️抢委托送货",
            "[2026-09-17 11:21:16.852][ERR][Px8848][Tx583][TemplateMatcher.cpp] templ size is too large",
            "[2026-09-17 11:21:40.000] 任务失败: 🏍️抢委托送货",
            "[2026-09-17 11:21:41.000] 任务开始: 模拟空间",
            "[2026-09-17 11:22:00.000] 任务完成: 模拟空间",
        ]
        collected = self._collect(lines)
        # 逐条模式的时间前缀来自规则捕获的行内时间戳（节点真实发生时刻）
        self.assertEqual(
            [(log_type, text) for log_type, text, _ in collected],
            [
                (LogType.NORMAL, "❌ 失败: 抢委托送货"),
                (LogType.NORMAL, "✅ 成功: 模拟空间"),
            ],
        )
        self.assertEqual(
            [
                datetime.fromtimestamp(ts).strftime("%H:%M:%S")
                for _, _, ts in collected
            ],
            ["11:21:40", "11:22:00"],
        )

    def test_crash_mid_task_marks_failed(self) -> None:
        lines = [
            "[2026-09-17 11:20:52.790] 任务开始: 🏍️抢委托送货",
            "[2026-09-17 11:20:59.999] MaaEnd 进程异常退出",
        ]
        self.assertEqual(
            [(text) for _, text, _ in self._collect(lines)],
            ["❌ 失败: 抢委托送货"],
        )

    def test_emoji_stripped_from_node_names(self) -> None:
        # 任务名 emoji 去除（含 ❌ 前缀的关闭游戏名，避免与失败标记混淆）；
        # 状态标记 ✅/❌ 为功能性前缀，保留
        lines = [
            "[2026-09-17 11:21:00.000] 任务完成: 🤝拜访好友",
            "[2026-09-17 11:21:10.000] 任务完成: ❌关闭游戏（PC）",
            "[2026-09-17 11:21:20.000] 任务开始: 🏍️抢委托送货",
        ]
        self.assertEqual(
            [(text) for _, text, _ in self._collect(lines)],
            [
                "✅ 成功: 拜访好友",
                "✅ 成功: 关闭游戏（PC）",
                "❌ 失败: 抢委托送货",
            ],
        )

    def test_pure_emoji_custom_name_keeps_original(self) -> None:
        # 纯 emoji/装饰符任务名剥离后为空：回退原名，不产出空名节点
        lines = [
            "[2026-09-17 11:21:00.000] 任务完成: ⭐",
            "[2026-09-17 11:21:10.000] 任务完成: ⭐",
        ]
        self.assertEqual(
            [(text) for _, text, _ in self._collect(lines)],
            ["✅ 成功: ⭐"],
        )

    def test_tolerates_extra_whitespace(self) -> None:
        # 匹配空白容差与判态正则（\s*）同源：多空格不丢行
        lines = [
            "[2026-09-17 11:21:00.000] 任务完成:  拜访好友",
        ]
        self.assertEqual(
            [(text) for _, text, _ in self._collect(lines)],
            ["✅ 成功: 拜访好友"],
        )

    def test_no_task_lines_yields_nothing(self) -> None:
        lines = [
            "[2026-09-17 10:35:09 INFO  [App] 加载导入文件: tasks/AutoCollect.json",
            "[2026-09-17 11:20:46.949] 窗口连接成功: Endfield",
        ]
        self.assertEqual(self._collect(lines), [])


if __name__ == "__main__":
    unittest.main()
