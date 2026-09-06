import unittest

from app.utils.emulator2.bosskey import DEFAULT_BOSS_KEY, decode_boss_key, read_boss_key


class DecodeBossKeyTest(unittest.TestCase):
    """雷电把老板键存成 {"modifiers": 位标志, "key": 虚拟键码}。

    只有 ``2 == Ctrl`` 是实测确认的；Alt / Shift 的位值没有样本，
    所以遇到未知位必须报「认不出」——猜错会按下一个用户没设过的组合键。
    """

    def test_real_sample_ctrl_backslash(self) -> None:
        """用户把 3 号实例的老板键改成 Ctrl+\\ 之后的真实取值。"""
        result = decode_boss_key({"modifiers": 2, "key": 220})

        self.assertEqual(result.hotkey, "ctrl+\\")
        self.assertEqual(result.reason, "ok")

    def test_absent_falls_back_to_ldplayer_default(self) -> None:
        result = decode_boss_key(None)

        self.assertEqual(result.hotkey, "ctrl+q")
        self.assertEqual(result.reason, "default")

    def test_default_constant_matches_ctrl_q(self) -> None:
        self.assertEqual(decode_boss_key(DEFAULT_BOSS_KEY).hotkey, "ctrl+q")

    def test_same_file_hotkeys_decode_consistently(self) -> None:
        """同一份配置里另外几个热键，用来交叉验证 2 == Ctrl 的判断。"""
        cases = {
            (2, 51): "ctrl+3",  # installApkKey
            (2, 70): "ctrl+f",  # keyboardModelKey
            (0, 112): "f1",  # homeKey
            (0, 27): "esc",  # backKey
            (0, 122): "f11",  # fullScreenKey
        }
        for (modifiers, key), expected in cases.items():
            with self.subTest(modifiers=modifiers, key=key):
                self.assertEqual(
                    decode_boss_key({"modifiers": modifiers, "key": key}).hotkey,
                    expected,
                )

    def test_unknown_modifier_bit_is_refused_not_guessed(self) -> None:
        result = decode_boss_key({"modifiers": 9, "key": 81})

        self.assertIsNone(result.hotkey)
        self.assertEqual(result.reason, "unknown_modifier")

    def test_unknown_key_code_is_refused(self) -> None:
        result = decode_boss_key({"modifiers": 2, "key": 0x6B})  # 小键盘加号，故意不收

        self.assertIsNone(result.hotkey)
        self.assertEqual(result.reason, "unknown_key")

    def test_disabled_hotkey_is_not_treated_as_absent(self) -> None:
        """key=0 表示没绑热键，不能当成「没设过」而回落 Ctrl+Q。

        原因也不能混进 malformed：用户主动取消了老板键，和配置文件结构对不上，
        界面要说的是两句完全不同的话。
        """
        result = decode_boss_key({"modifiers": 0, "key": 0})

        self.assertIsNone(result.hotkey)
        self.assertEqual(result.reason, "disabled")

    def test_malformed_payloads(self) -> None:
        for payload in ("ctrl+q", [], {"key": "81"}, {"modifiers": True, "key": 81}):
            with self.subTest(payload=payload):
                result = decode_boss_key(payload)
                self.assertIsNone(result.hotkey)
                self.assertEqual(result.reason, "malformed")


class ReadBossKeyTest(unittest.TestCase):
    def test_instance_without_hotkey_settings_uses_default(self) -> None:
        """本机 0/1/2 号实例就是这种情况——整组 hotkeySettings 都不存在。"""
        result = read_boss_key({"statusSettings.playerName": "0"})

        self.assertEqual(result.hotkey, "ctrl+q")
        self.assertEqual(result.reason, "default")

    def test_instance_with_custom_hotkey(self) -> None:
        result = read_boss_key({"hotkeySettings.bossKey": {"modifiers": 2, "key": 220}})

        self.assertEqual(result.hotkey, "ctrl+\\")

    def test_unreadable_config_is_not_the_same_as_absent(self) -> None:
        """配置读不出来时我们并不知道用户设的是什么，不能回落默认值。"""
        result = read_boss_key(None)

        self.assertIsNone(result.hotkey)
        self.assertEqual(result.reason, "malformed")


if __name__ == "__main__":
    unittest.main()
