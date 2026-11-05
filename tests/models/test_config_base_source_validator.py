"""Base 新字段使用 Literal 校验，历史 Mode 经 Entry 的 legacy 声明转换。"""

import unittest


from app.models.config import MaaUserConfig
from app.utils import normalize_base_source


class BaseSourceValidatorTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
