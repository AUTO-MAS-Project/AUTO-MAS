import unittest

from app.utils.emulator2.stability import (
    LDPLAYER_ITEMS,
    MUMU_ITEMS,
    evaluate,
    items_for,
    safe_writes,
)


class SpecTest(unittest.TestCase):
    def test_both_families_are_covered(self) -> None:
        self.assertTrue(items_for("ldplayer"))
        self.assertTrue(items_for("mumu"))

    def test_unknown_family_has_no_items(self) -> None:
        """认不出的模拟器不该被硬塞一套别家的键。"""
        self.assertEqual(items_for("nox"), ())

    def test_keep_alive_is_only_a_mumu_concept(self) -> None:
        """后台保活是 MuMu 的设置；雷电这边没有对应键，不能凭空造一个。"""
        self.assertIn("keepAlive", {item.field for item in MUMU_ITEMS})
        self.assertNotIn("keepAlive", {item.field for item in LDPLAYER_ITEMS})

    def test_every_item_declares_its_evidence(self) -> None:
        """推测和实证不能混着讲——每一项都要说清依据是哪一级。"""
        allowed = {"maa_documented", "maa_tracked", "mechanical"}
        for item in LDPLAYER_ITEMS + MUMU_ITEMS:
            with self.subTest(field=item.field):
                self.assertIn(item.evidence, allowed)


class EvaluateTest(unittest.TestCase):
    def test_all_safe_reports_on(self) -> None:
        current = {item.key: item.safe_value for item in LDPLAYER_ITEMS}

        ok, unsafe = evaluate(LDPLAYER_ITEMS, current)

        self.assertTrue(ok)
        self.assertEqual(unsafe, [])

    def test_missing_key_counts_as_unsafe(self) -> None:
        """读不到值就报「已开启」，比报「未开启」糟得多。"""
        ok, unsafe = evaluate(LDPLAYER_ITEMS, {})

        self.assertFalse(ok)
        self.assertEqual(len(unsafe), len(LDPLAYER_ITEMS))

    def test_ldplayer_booleans_compare_as_strings(self) -> None:
        """雷电配置里这几项是真布尔，取出来是 ``True`` / ``False``。"""
        current = {item.key: "False" for item in LDPLAYER_ITEMS}

        ok, _ = evaluate(LDPLAYER_ITEMS, current)

        self.assertTrue(ok)

    def test_high_frame_rate_on_is_unsafe(self) -> None:
        current = {item.key: item.safe_value for item in LDPLAYER_ITEMS}
        current["basicSettings.heightFrameRate"] = "True"

        ok, unsafe = evaluate(LDPLAYER_ITEMS, current)

        self.assertFalse(ok)
        self.assertEqual(unsafe, ["highFrameRate"])


class VramStrategyTest(unittest.TestCase):
    """MAA 只点名了「资源占用更小」，其余档位是用户的性能偏好，不该一并改掉。"""

    def _current(self, strategy: str) -> dict[str, str]:
        current = {item.key: item.safe_value for item in MUMU_ITEMS}
        current["renderer_strategy"] = strategy
        return current

    def test_auto_is_accepted(self) -> None:
        ok, _ = evaluate(MUMU_ITEMS, self._current("auto"))

        self.assertTrue(ok)

    def test_perf_is_accepted_even_though_it_is_not_the_safe_value(self) -> None:
        ok, unsafe = evaluate(MUMU_ITEMS, self._current("perf"))

        self.assertTrue(ok)
        self.assertEqual(unsafe, [])

    def test_only_the_named_one_is_refused(self) -> None:
        ok, unsafe = evaluate(MUMU_ITEMS, self._current("dis"))

        self.assertFalse(ok)
        self.assertEqual(unsafe, ["vramStrategy"])

    def test_perf_is_left_alone_on_write(self) -> None:
        self.assertEqual(safe_writes(MUMU_ITEMS, self._current("perf")), {})


class SafeWritesTest(unittest.TestCase):
    def test_already_safe_items_are_not_rewritten(self) -> None:
        current = {item.key: item.safe_value for item in MUMU_ITEMS}

        self.assertEqual(safe_writes(MUMU_ITEMS, current), {})

    def test_only_the_unsafe_ones_are_written(self) -> None:
        current = {item.key: item.safe_value for item in MUMU_ITEMS}
        current["app_keptlive"] = "true"

        self.assertEqual(safe_writes(MUMU_ITEMS, current), {"app_keptlive": "false"})


if __name__ == "__main__":
    unittest.main()
