import unittest

from app.utils.emulator2.detect import (
    judge,
    major_of,
    parse_ldplayer_version,
    parse_mumu_version,
)

#: 雷电 14.0.25.1 裸跑 ldconsole.exe 的真实输出开头
LDPLAYER_REAL_OUTPUT = """dnplayer v14.0.25.1 Command Line Management Interface
All rights reserved.

Usage:

ldconsole <command> [parameter]
"""

#: MuMu 6.5.9.0 的 `MuMuManager.exe version` 真实输出
MUMU_REAL_OUTPUT = '{\n  "version": "6.5.9.0"\n}\n'


class ParseLDPlayerVersionTest(unittest.TestCase):
    def test_real_output(self) -> None:
        self.assertEqual(parse_ldplayer_version(LDPLAYER_REAL_OUTPUT), "14.0.25.1")

    def test_tolerates_leading_whitespace_and_case(self) -> None:
        self.assertEqual(
            parse_ldplayer_version("  DNPLAYER V9.1.34.0 Command Line"), "9.1.34.0"
        )

    def test_without_v_prefix(self) -> None:
        self.assertEqual(parse_ldplayer_version("dnplayer 14.0.25.1"), "14.0.25.1")

    def test_empty_and_unrecognisable(self) -> None:
        self.assertIsNone(parse_ldplayer_version(""))
        self.assertIsNone(parse_ldplayer_version("命令执行失败"))


class ParseMumuVersionTest(unittest.TestCase):
    def test_real_output(self) -> None:
        self.assertEqual(parse_mumu_version(MUMU_REAL_OUTPUT), "6.5.9.0")

    def test_non_json_output_still_yields_a_version(self) -> None:
        self.assertEqual(parse_mumu_version("MuMuManager 12.0.1.2"), "12.0.1.2")

    def test_empty_and_unrecognisable(self) -> None:
        self.assertIsNone(parse_mumu_version(""))
        self.assertIsNone(parse_mumu_version("{}"))


class MajorOfTest(unittest.TestCase):
    def test_takes_the_leading_component(self) -> None:
        self.assertEqual(major_of("14.0.25.1"), 14)
        self.assertEqual(major_of("6.5.9.0"), 6)

    def test_unparsable(self) -> None:
        self.assertIsNone(major_of(""))
        self.assertIsNone(major_of("v14"))


class JudgeTest(unittest.TestCase):
    """三种「不可加」必须分开——界面上的措辞完全不同。"""

    def test_ldplayer_14_is_accepted(self) -> None:
        self.assertEqual(judge("ldplayer", "14.0.25.1"), (True, "ok"))

    def test_ldplayer_9_is_too_old(self) -> None:
        self.assertEqual(judge("ldplayer", "9.1.34.0"), (False, "version_too_old"))

    def test_ldplayer_newer_major_is_unsupported_not_too_old(self) -> None:
        """比支持的还新，不能提示用户「请升级」。"""
        self.assertEqual(judge("ldplayer", "15.0.0.0"), (False, "unsupported"))

    def test_mumu_6_is_accepted(self) -> None:
        self.assertEqual(judge("mumu", "6.5.9.0"), (True, "ok"))

    def test_mumu_5_is_too_old(self) -> None:
        self.assertEqual(judge("mumu", "5.1.2.0"), (False, "version_too_old"))

    def test_mumu_12_is_unsupported_not_too_old(self) -> None:
        """MuMu 12 是另一条产品线，不是「请升级」能解决的。"""
        self.assertEqual(judge("mumu", "12.0.1.2"), (False, "unsupported"))

    def test_other_brands_are_unsupported(self) -> None:
        self.assertEqual(judge("nox", "7.0.5.8"), (False, "unsupported"))

    def test_unreadable_version_is_probe_failed_not_unsupported(self) -> None:
        """认不出版本 ≠ 不支持，两者的用户提示不一样。"""
        self.assertEqual(judge("ldplayer", ""), (False, "probe_failed"))


if __name__ == "__main__":
    unittest.main()
