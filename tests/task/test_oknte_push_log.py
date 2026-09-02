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
        # 仅 CUR 且无任何刷本消耗（体力不足直接退出）：剩余即最后一次当前体力
        self.assertEqual(
            oknte_resolve([(LogType.NORMAL, "CUR:30", T)]),
            [(LogType.NORMAL, "⚡ 剩余体力: 30", T)],
        )

    def test_no_cur_yields_no_stamina_line(self) -> None:
        # 没有当前体力作基数（含未知/非法标记），不追加剩余体力行
        self.assertEqual(
            oknte_resolve([(LogType.NORMAL, "CONSUME:60", T)]), []
        )

    def test_stamina_anomaly_single_run(self) -> None:
        # 异象界域刷 1 把单倍（40 体）：76 − 40 = 36（今晚真实场景）
        results = [
            (LogType.NORMAL, "CUR:76", T),
            (LogType.NORMAL, "UNITS:0\n1", T),
        ]
        self.assertEqual(
            oknte_resolve(results),
            [(LogType.NORMAL, "⚡ 剩余体力: 36", T)],
        )

    def test_stamina_anomaly_double_run(self) -> None:
        # 异象界域刷 1 把双倍（=2 把单倍，80 体）：120 − 80 = 40
        results = [
            (LogType.NORMAL, "CUR:120", T),
            (LogType.NORMAL, "UNITS:1\n0", T),
        ]
        self.assertEqual(
            oknte_resolve(results),
            [(LogType.NORMAL, "⚡ 剩余体力: 40", T)],
        )

    def test_stamina_hunter_consume(self) -> None:
        # 异象追猎直接给实际消耗：70 − 60 = 10
        results = [
            (LogType.NORMAL, "CUR:70", T),
            (LogType.NORMAL, "CONSUME:60", T),
        ]
        self.assertEqual(
            oknte_resolve(results),
            [(LogType.NORMAL, "⚡ 剩余体力: 10", T)],
        )

    def test_stamina_reset_on_last_cur(self) -> None:
        # 每个耗体任务重读当前体力：后面的 CUR 已含此前消耗，只减去其后消耗
        results = [
            (LogType.NORMAL, "CUR:120", T),
            (LogType.NORMAL, "UNITS:1\n0", T),  # 异象界域耗 80
            (LogType.NORMAL, "CUR:40", T),  # 异象追猎重读 40
            (LogType.NORMAL, "CONSUME:0", T),  # 未成功不耗体
        ]
        self.assertEqual(
            oknte_resolve(results),
            [(LogType.NORMAL, "⚡ 剩余体力: 40", T)],
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

    def test_no_reward_downgrades_daily_claim_fail_to_skip(self) -> None:
        # 当日已领取（NO_REWARD 标记）：仅「日常领取」的失败降级为跳过，
        # 其他节点的失败不受影响
        results = [
            (LogType.NORMAL, "❌ 失败: 异象界域", T),
            (LogType.NORMAL, "❌ 失败: 日常领取", T),
            (LogType.NORMAL, "NO_REWARD", T),
        ]
        self.assertEqual(
            oknte_resolve(results),
            [
                (LogType.NORMAL, "❌ 失败: 异象界域", T),
                (LogType.NORMAL, "⏭ 跳过: 日常领取（当日已领取）", T),
            ],
        )

    def test_no_reward_without_daily_claim_fail_keeps_states(self) -> None:
        # 有 NO_REWARD 标记但「日常领取」未失败（如成功）时，不改写任何状态
        results = [
            (LogType.NORMAL, "✅ 成功: 日常领取", T),
            (LogType.NORMAL, "NO_REWARD", T),
        ]
        self.assertEqual(
            oknte_resolve(results),
            [(LogType.NORMAL, "✅ 成功: 日常领取", T)],
        )

    def test_no_reward_marker_alone_produces_nothing(self) -> None:
        # 仅 NO_REWARD 标记不产出任何节点
        self.assertEqual(
            oknte_resolve([(LogType.NORMAL, "NO_REWARD", T)]), []
        )


if __name__ == "__main__":
    unittest.main()