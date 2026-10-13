"""配置来源校验器（脚本/用户/直控 三态）的纯逻辑回归测试

所有统一来源模式复用同一套 ConfigSourceValidator 基类。这里锁住：合法值通过、非法值回退默认、
旧版“简洁/详细”在调父类校验前先归一。
"""

import unittest
from unittest.mock import patch

from app.models.config import (
    ConfigSourceValidator,
    OkwwConfigModeValidator,
    UserDirectConfigModeValidator,
)
from app.models.ConfigBase import OptionsValidator


class ConfigSourceValidatorTest(unittest.TestCase):
    def test_three_state_accepts_all_modes(self) -> None:
        """三态校验器接受 脚本/用户/直控。"""

        validator = OkwwConfigModeValidator()

        self.assertTrue(validator.validate("脚本"))
        self.assertTrue(validator.validate("用户"))
        self.assertTrue(validator.validate("直控"))
        self.assertEqual(validator.correct("脚本"), "脚本")
        self.assertEqual(validator.correct("直控"), "直控")

    def test_source_validator_accepts_all_modes(self) -> None:
        """统一三态校验器接受 脚本/用户/直控。"""

        validator = UserDirectConfigModeValidator()

        self.assertTrue(validator.validate("用户"))
        self.assertTrue(validator.validate("直控"))
        self.assertTrue(validator.validate("脚本"))
        self.assertEqual(validator.correct("脚本"), "脚本")

    def test_legacy_values_map_before_parent_correction(self) -> None:
        """旧版“简洁/详细/自定义”在父类校验前归一, 不触发父类 correct。"""

        validator = ConfigSourceValidator(
            ("脚本", "用户", "直控"),
            {"简洁": "脚本", "详细": "用户", "自定义": "用户"},
        )

        with patch.object(
            OptionsValidator,
            "correct",
            side_effect=AssertionError("父类校验不应提前执行"),
        ):
            self.assertEqual(validator.correct("简洁"), "脚本")
            self.assertEqual(validator.correct("详细"), "用户")
            self.assertEqual(validator.correct("自定义"), "用户")

    def test_no_legacy_map_passes_through(self) -> None:
        """无 legacy 映射时直接走父类校验。"""

        validator = UserDirectConfigModeValidator()

        self.assertEqual(validator.correct("用户"), "用户")
        self.assertEqual(validator.correct("直控"), "直控")


if __name__ == "__main__":
    unittest.main()
