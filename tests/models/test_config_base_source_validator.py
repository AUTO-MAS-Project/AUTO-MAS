"""Base 新字段使用 Literal 校验，历史 Mode 经 Entry 的 legacy 声明转换。"""

import unittest

from pydantic import TypeAdapter, ValidationError
from app.models.config import MaaUserConfig


def base_adapter():
    return TypeAdapter(
        MaaUserConfig.InfoFields.model_fields["Base"].rebuild_annotation()
    )


from app.utils.constants import normalize_base_source


class BaseSourceValidatorTest(unittest.TestCase):
    def test_three_state_accepts_all_bases(self) -> None:
        """三态校验器接受 shared/independent/native 并原样放行。"""

        adapter = base_adapter()

        for base in ("shared", "independent", "native"):
            self.assertEqual(adapter.validate_python(base), base)
            self.assertEqual(adapter.validate_python(base), base)

    def test_legacy_values_normalize_to_bases(self) -> None:
        """旧版「脚本/用户/直控」与「简洁/详细/自定义」在父类校验前归一。"""

        expected = {
            "脚本": "shared",
            "用户": "independent",
            "直控": "native",
            "简洁": "shared",
            "详细": "independent",
            "自定义": "independent",
        }

        for legacy, base in expected.items():
            self.assertEqual(
                MaaUserConfig.model_validate({"Info": {"Mode": legacy}}).Info.Base,
                base,
            )
            self.assertEqual(normalize_base_source(legacy), base)

    def test_unknown_value_is_rejected(self) -> None:
        """新字段的非法值由 Pydantic 拒绝，不再使用旧校验器的回退。"""

        with self.assertRaises(ValidationError):
            base_adapter().validate_python("乱码")
        with self.assertRaises(ValidationError):
            MaaUserConfig.model_validate({"Info": {"Mode": "乱码"}})

    def test_new_bases_are_not_legacy_keys(self) -> None:
        """新字面量不在遗留归一表里，避免迁移自反。"""

        for base in ("shared", "independent", "native"):
            self.assertEqual(normalize_base_source(base), base)


if __name__ == "__main__":
    unittest.main()
