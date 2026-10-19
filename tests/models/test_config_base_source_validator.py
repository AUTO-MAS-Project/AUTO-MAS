"""base 来源校验器（shared/independent/native 三态）的纯逻辑回归测试

所有设置 base 来源的配置项复用同一套 BaseSourceValidator：新字面量通过，
旧版「脚本/用户/直控」与更早的「简洁/详细/自定义」在父类校验前先归一，
未知值按父类规则回落首选项（shared）。
"""

import unittest

from app.models.config import BaseSourceValidator
from app.utils.constants import normalize_base_source


class BaseSourceValidatorTest(unittest.TestCase):
    def test_three_state_accepts_all_bases(self) -> None:
        """三态校验器接受 shared/independent/native 并原样放行。"""

        validator = BaseSourceValidator()

        for base in ("shared", "independent", "native"):
            self.assertTrue(validator.validate(base))
            self.assertEqual(validator.correct(base), base)

    def test_legacy_values_normalize_to_bases(self) -> None:
        """旧版「脚本/用户/直控」与「简洁/详细/自定义」在父类校验前归一。"""

        validator = BaseSourceValidator()
        expected = {
            "脚本": "shared",
            "用户": "independent",
            "直控": "native",
            "简洁": "shared",
            "详细": "independent",
            "自定义": "independent",
        }

        for legacy, base in expected.items():
            self.assertEqual(validator.correct(legacy), base)
            self.assertEqual(normalize_base_source(legacy), base)

    def test_unknown_value_falls_back_to_first_option(self) -> None:
        """未知值不被迁移，按父类规则回落首选项 shared。"""

        self.assertEqual(BaseSourceValidator().correct("乱码"), "shared")

    def test_new_bases_are_not_legacy_keys(self) -> None:
        """新字面量不在遗留归一表里，避免迁移自反。"""

        for base in ("shared", "independent", "native"):
            self.assertEqual(normalize_base_source(base), base)


if __name__ == "__main__":
    unittest.main()
