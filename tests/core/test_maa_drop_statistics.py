"""MAA 日志掉落统计解析：按计划拼接的多链任务（库存保持/养成计划）完成行带 ` #N`
序号后缀，必须剥离后缀后再做目标名比对，否则这些链的掉落会被整体漏计。"""

import unittest

from app.core.config import _parse_maa_drop_statistics


def _fight_chain(name: str, stage: str, drops: list[str]) -> list[str]:
    return [
        f"[2026-09-11 09:55:01.026][INF][TaskQueueViewModel]     <2> 开始任务: {name}",
        "[2026-09-11 09:55:01.026][INF][AsstProxy]              <2> Start Task Chain: Fight, Task ID: 12",
        "[2026-09-11 09:55:01.900][INF][TaskQueueViewModel]     <2> 开始行动 1~6 次, -108理智",
        "理智: 120/206",
        f"[2026-09-11 09:55:02.000][INF][TaskQueueViewModel]     <2> {stage} 掉落统计: ",
        *drops,
        "当前次数 : 6",
        f"[2026-09-11 09:55:02.028][INF][TaskQueueViewModel]     <2> 完成任务: {name}",
    ]


class MaaDropStatisticsTest(unittest.TestCase):
    def test_multi_chain_suffix_is_counted(self) -> None:
        """库存保持/养成计划的 ` #N` 完成行要被识别为理智任务边界。"""

        logs = [
            "[2026-09-11 09:54:48.256][INF][TaskQueueViewModel]     <2> 开始任务: 库存保持 (仓库识别)",
            "[2026-09-11 09:55:00.529][INF][TaskQueueViewModel]     <2> 完成任务: 库存保持 (仓库识别)",
            *_fight_chain(
                "库存保持 #1", "PR-A-1", ["龙门币 : 1296 (+1296)", "医疗芯片 : 2 (+2)"]
            ),
            *_fight_chain("库存保持 #2", "1-7", ["固源岩 : 4 (+4)"]),
            *_fight_chain("养成计划 #1", "1-7", ["固源岩 : 2 (+2)"]),
        ]

        result = _parse_maa_drop_statistics(logs)

        self.assertEqual(result.get("PR-A-1"), {"龙门币": 1296, "医疗芯片": 2})
        self.assertEqual(result.get("1-7"), {"固源岩": 6})

    def test_suffix_and_bare_name_are_equivalent(self) -> None:
        """剥离后缀后的判定与旧版裸任务名完全等价（兼容旧日志）。"""

        suffixed = _parse_maa_drop_statistics(
            _fight_chain("库存保持 #1", "PR-A-1", ["医疗芯片 : 2 (+2)"])
        )
        bare = _parse_maa_drop_statistics(
            _fight_chain("库存保持", "PR-A-1", ["医疗芯片 : 2 (+2)"])
        )

        self.assertEqual(suffixed, bare)
        self.assertEqual(suffixed.get("PR-A-1"), {"医疗芯片": 2})

    def test_recognition_chain_alone_yields_nothing(self) -> None:
        """识别链（带括号后缀）不产出掉落，不应被误当作战斗链。"""

        logs = [
            "[2026-09-11 09:55:00.529][INF][TaskQueueViewModel]     <2> 完成任务: 库存保持 (仓库识别)",
            "[2026-09-11 09:55:00.529][INF][TaskQueueViewModel]     <2> 1-7 掉落统计: ",
            "固源岩 : 9 (+9)",
        ]

        self.assertEqual(_parse_maa_drop_statistics(logs), {})


if __name__ == "__main__":
    unittest.main()
