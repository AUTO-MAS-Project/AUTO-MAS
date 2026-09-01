import unittest

from app.log_box.logtype import LogType
from app.task.OkNte.push_log import oknte_resolve

# 结果元组含采集时间戳；(日志类型, 文本, 时间戳)
T = 1000.0


class OkNteResolveTest(unittest.TestCase):
    """oknte_resolve 后处理纯逻辑：状态优先级、跳过列表、体力计算、未知文本过滤。"""

    def test_success_fail_skip_merge_with_priority(self) -> None:
        # 同一节点先成功、后跳过、再失败：最终状态取 失败 > 跳过 > 成功 最高者
        results = [
            (LogType.NORMAL, "✅ 成功: 节点A", T),
            (LogType.NORMAL, "⏭ 跳过: 节点B", T),
            (LogType.NORMAL, "❌ 失败: 节点A", T),
            (LogType.NORMAL, "✅ 成功: 节点C", T),
        ]
        self.assertEqual(
            oknte_resolve(results),
            [
                (LogType.NORMAL, "⏭ 跳过: 节点B", T),
                (LogType.NORMAL, "❌ 失败: 节点A", T),
                (LogType.NORMAL, "✅ 成功: 节点C", T),
            ],
        )

    def test_order_keeps_last_occurrence(self) -> None:
        # 节点再次出现时移到末尾，状态按优先级覆盖
        results = [
            (LogType.NORMAL, "✅ 成功: 节点A", T),
            (LogType.NORMAL, "✅ 成功: 节点B", T),
            (LogType.NORMAL, "❌ 失败: 节点A", T),
        ]
        self.assertEqual(
            [text for _, text, _ in oknte_resolve(results)],
            ["✅ 成功: 节点B", "❌ 失败: 节点A"],
        )

    def test_timestamp_follows_winning_occurrence(self) -> None:
        # 节点最终状态由最高优先级那次决定，时间戳跟随该次采集时刻
        results = [
            (LogType.NORMAL, "✅ 成功: 节点A", 1.0),
            (LogType.NORMAL, "⏭ 跳过: 节点A", 2.0),
            (LogType.NORMAL, "❌ 失败: 节点A", 3.0),
        ]
        self.assertEqual(
            oknte_resolve(results),
            [(LogType.NORMAL, "❌ 失败: 节点A", 3.0)],
        )

    def test_skip_list_expands_and_does_not_override_fail(self) -> None:
        results = [
            (LogType.NORMAL, "❌ 失败: 节点A", T),
            (LogType.NORMAL, "SKIP:'节点A', '节点B'", T),
        ]
        self.assertEqual(
            oknte_resolve(results),
            [
                (LogType.NORMAL, "❌ 失败: 节点A", T),
                (LogType.NORMAL, "⏭ 跳过: 节点B", T),
            ],
        )

    def test_skip_list_same_priority_dedupes(self) -> None:
        results = [
            (LogType.NORMAL, "⏭ 跳过: 节点A", T),
            (LogType.NORMAL, "SKIP:'节点A'", T),
        ]
        self.assertEqual(
            oknte_resolve(results),
            [(LogType.NORMAL, "⏭ 跳过: 节点A", T)],
        )

    def test_invalid_skip_list_is_ignored(self) -> None:
        # 非法/非列表/非字符串元素均不产出节点，也不抛异常；
        # 注意裸逗号分隔载荷（如 '节点A', '节点B'）是合法输入，见 expand 用例
        for payload in (
            "not a list",
            "",
            "[123]",
            "{'节点X': 1}",
        ):
            with self.subTest(payload=payload):
                self.assertEqual(
                    oknte_resolve([(LogType.NORMAL, f"SKIP:{payload}", T)]), []
                )

    def test_skip_list_filters_non_string_items(self) -> None:
        results = [(LogType.NORMAL, "SKIP:'节点A', 123", T)]
        self.assertEqual(
            oknte_resolve(results),
            [(LogType.NORMAL, "⏭ 跳过: 节点A", T)],
        )

    def test_cur_only_shows_current_as_remaining(self) -> None:
        # 仅 CUR（如体力不足被中止、未设消耗目标）：直接展示当前体力
        self.assertEqual(
            oknte_resolve([(LogType.NORMAL, "CUR:30", T)]),
            [(LogType.NORMAL, "⚡ 剩余体力: 30", T)],
        )

    def test_tgt_only_yields_no_stamina_line(self) -> None:
        # 仅 TGT：没有当前体力作基数，不追加剩余体力行
        self.assertEqual(oknte_resolve([(LogType.NORMAL, "TGT:60", T)]), [])

    def test_stamina_uses_last_cur_and_tgt(self) -> None:
        results = [
            (LogType.NORMAL, "CUR:120", T),
            (LogType.NORMAL, "CUR:90", T),
            (LogType.NORMAL, "TGT:60", T),
        ]
        self.assertEqual(
            oknte_resolve(results),
            [(LogType.NORMAL, "⚡ 剩余体力: 30", T)],
        )

    def test_stamina_clamps_to_zero(self) -> None:
        results = [
            (LogType.NORMAL, "CUR:40", T),
            (LogType.NORMAL, "TGT:60", T),
        ]
        self.assertEqual(
            oknte_resolve(results),
            [(LogType.NORMAL, "⚡ 剩余体力: 0", T)],
        )

    def test_unknown_text_and_bad_stamina_are_dropped(self) -> None:
        # 未知文本/非数字体力不纳入报告，也不抛异常（未知文本不默认判为成功）
        results = [
            (LogType.NORMAL, "一些意外的提取结果", T),
            (LogType.NORMAL, "CUR:abc", T),
            (LogType.NORMAL, "✅ 成功: 节点A", T),
        ]
        self.assertEqual(
            oknte_resolve(results),
            [(LogType.NORMAL, "✅ 成功: 节点A", T)],
        )

    def test_empty_results(self) -> None:
        self.assertEqual(oknte_resolve([]), [])


if __name__ == "__main__":
    unittest.main()