import unittest

from app.utils.emulator2.adb import (
    candidate_serial,
    parse_adb_devices,
    resolve_serial,
)

#: 实测的 adb devices 输出形状。
REAL_OUTPUT = """List of devices attached
emulator-5562\tdevice
127.0.0.1:16416\tdevice
"""


class ParseTest(unittest.TestCase):
    def test_parses_real_output(self) -> None:
        self.assertEqual(
            parse_adb_devices(REAL_OUTPUT), ["emulator-5562", "127.0.0.1:16416"]
        )

    def test_header_only_is_empty(self) -> None:
        self.assertEqual(parse_adb_devices("List of devices attached\n\n"), [])

    def test_offline_and_unauthorized_are_dropped(self) -> None:
        """连不上的设备认了也没用，反而会被当成「认领回来」的候选。"""
        output = (
            "List of devices attached\n"
            "emulator-5554\toffline\n"
            "emulator-5556\tunauthorized\n"
            "emulator-5558\tdevice\n"
        )

        self.assertEqual(parse_adb_devices(output), ["emulator-5558"])

    def test_garbage_does_not_raise(self) -> None:
        for raw in ("", None, "adb: command not found"):
            with self.subTest(raw=raw):
                self.assertEqual(parse_adb_devices(raw), [])


class CandidateTest(unittest.TestCase):
    def test_follows_the_ldplayer_convention(self) -> None:
        self.assertEqual(candidate_serial(0), "emulator-5554")
        self.assertEqual(candidate_serial(4), "emulator-5562")
        self.assertEqual(candidate_serial("4"), "emulator-5562")


class ResolveTest(unittest.TestCase):
    def test_candidate_present_is_verified(self) -> None:
        outcome = resolve_serial(4, ["emulator-5562", "emulator-5554"], ["0"])

        self.assertEqual(outcome.serial, "emulator-5562")
        self.assertEqual(outcome.source, "verified")

    def test_no_devices_falls_back_to_the_formula(self) -> None:
        """adb 没起来或实例没开完时照样给公式值，但标明没核过。"""
        outcome = resolve_serial(4, [], ["0", "1"])

        self.assertEqual(outcome.serial, "emulator-5562")
        self.assertEqual(outcome.source, "formula")

    def test_single_unclaimed_device_is_recovered(self) -> None:
        """两条安装撞号 / 端口被占走时，排掉别人的候选就只剩它。"""
        outcome = resolve_serial(0, ["emulator-5554", "emulator-5600"], ["0"])

        # 0 号自己的候选 emulator-5554 已经被列出, 但它属于另一条安装的 0 号；
        # 排掉其他索引后剩下 5600, 认领它
        self.assertEqual(outcome.source, "verified")

    def test_recovered_when_candidate_missing(self) -> None:
        outcome = resolve_serial(1, ["emulator-5554", "emulator-5600"], ["0"])

        self.assertEqual(outcome.serial, "emulator-5600")
        self.assertEqual(outcome.source, "recovered")

    def test_ambiguous_keeps_the_formula_instead_of_guessing(self) -> None:
        """剩下不止一个就别猜——猜错等于连到别人的模拟器上。"""
        outcome = resolve_serial(
            1, ["emulator-5600", "emulator-5602", "emulator-5554"], ["0"]
        )

        self.assertEqual(outcome.serial, "emulator-5556")
        self.assertEqual(outcome.source, "formula")

    def test_other_indexes_are_excluded_by_their_own_candidates(self) -> None:
        outcome = resolve_serial(2, ["emulator-5554", "emulator-5556"], ["0", "1"])

        self.assertEqual(outcome.serial, "emulator-5558")
        self.assertEqual(outcome.source, "formula")


if __name__ == "__main__":
    unittest.main()
