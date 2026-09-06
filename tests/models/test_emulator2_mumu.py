import unittest

from app.utils.emulator2.mumu6 import (
    _MODE_GATES,
    _WRITE_KEYS,
    _gb_to_mb,
    _to_int,
    parse_mem_list,
)


class ParseValueTest(unittest.TestCase):
    """MuMu 把所有值都当字符串返回，数值还常带六位小数。"""

    def test_decimal_string_becomes_an_int(self) -> None:
        self.assertEqual(_to_int("1280.000000"), 1280)

    def test_plain_string_works(self) -> None:
        self.assertEqual(_to_int("60"), 60)

    def test_missing_or_garbage_is_none(self) -> None:
        # nan / inf 能被 float() 接受但会让 round() 抛，必须挡在解析里
        for raw in (None, "", "auto", "custom", "nan", "inf"):
            with self.subTest(raw=raw):
                self.assertIsNone(_to_int(raw))


class GbToMbTest(unittest.TestCase):
    """回归：不能先把 GB 取整再乘 1024。

    先取整会让所有非整数档位全错——1.5 GB 变成 2 GB = 2048 MB，
    而正确答案是 1536 MB。显示出来的值既不是实际值，
    也对不上拒绝写入时列出的档位表。
    """

    def test_fractional_gb_survives(self) -> None:
        self.assertEqual(_gb_to_mb("1.500000"), 1536)
        self.assertEqual(_gb_to_mb("0.750000"), 768)
        self.assertEqual(_gb_to_mb("1.750000"), 1792)

    def test_whole_gb_still_works(self) -> None:
        self.assertEqual(_gb_to_mb("6.000000"), 6144)

    def test_garbage_is_none(self) -> None:
        for raw in (None, "", "auto", "nan", "inf"):
            with self.subTest(raw=raw):
                self.assertIsNone(_gb_to_mb(raw))


class MemoryLadderTest(unittest.TestCase):
    """``performance_mem.list`` 是 GB 浮点，对外统一换算成 MB。"""

    RAW = (
        "[0.750000,1.000000,1.500000,1.750000,2.000000,3.000000,4.000000,"
        "5.000000,6.000000,7.000000,8.000000](best=6.000000)"
    )

    def test_parses_to_mb(self) -> None:
        self.assertEqual(
            parse_mem_list(self.RAW),
            [768, 1024, 1536, 1792, 2048, 3072, 4096, 5120, 6144, 7168, 8192],
        )

    def test_best_marker_is_not_swallowed_as_a_value(self) -> None:
        self.assertNotIn(6144, parse_mem_list(self.RAW)[-1:])

    def test_missing_list_is_empty(self) -> None:
        self.assertEqual(parse_mem_list(None), [])
        self.assertEqual(parse_mem_list(""), [])


class ModeGateTest(unittest.TestCase):
    """实测的坑：不切 mode 的话，写进去的 ``.custom`` 值一个都不生效。"""

    def test_resolution_fields_are_gated_by_resolution_mode(self) -> None:
        self.assertEqual(
            set(_MODE_GATES["resolution_mode"]), {"width", "height", "dpi"}
        )

    def test_cpu_and_memory_are_gated_by_performance_mode(self) -> None:
        self.assertEqual(set(_MODE_GATES["performance_mode"]), {"cpu", "memoryMb"})

    def test_frame_rate_has_no_gate(self) -> None:
        gated = {name for owned in _MODE_GATES.values() for name in owned}

        self.assertNotIn("fps", gated)

    def test_every_writable_field_maps_to_a_key(self) -> None:
        self.assertEqual(
            set(_WRITE_KEYS),
            {"width", "height", "dpi", "cpu", "memoryMb", "fps"},
        )


if __name__ == "__main__":
    unittest.main()
