"""请求模型对旧 ``Info.Mode`` 来源字段的兼容回归测试

旧「脚本/用户/直控」请求体在解析阶段归一为 ``Info.Base``（shared/independent/native），
避免字段被静默丢弃、接口返回成功但来源未变；显式 ``Base`` 优先，未知值仍按旧
Literal 语义拒绝。
"""

import unittest

from pydantic import ValidationError

from app.models.schema import (
    GeneralUserConfig_Info,
    HSRUserConfig_Info,
    MaaFWUserConfig_Info,
    MaaUserConfig_Info,
    UserUpdateIn,
)


class LegacyInfoModeCompatTest(unittest.TestCase):
    def test_legacy_mode_migrates_to_base(self) -> None:
        """旧来源字面量在解析前归一为 Base 三态。"""

        expected = {
            "脚本": "shared",
            "用户": "independent",
            "直控": "native",
            "简洁": "shared",
            "详细": "independent",
            "自定义": "independent",
        }
        for info_cls in (
            MaaUserConfig_Info,
            GeneralUserConfig_Info,
            HSRUserConfig_Info,
            MaaFWUserConfig_Info,
        ):
            for legacy, base in expected.items():
                self.assertEqual(info_cls.model_validate({"Mode": legacy}).Base, base)

    def test_explicit_base_wins_and_unknown_mode_rejected(self) -> None:
        """显式 Base 优先；未知 Mode 与旧 Literal 语义一致地拒绝。"""

        self.assertEqual(
            MaaUserConfig_Info.model_validate({"Mode": "脚本", "Base": "native"}).Base,
            "native",
        )
        self.assertIsNone(MaaUserConfig_Info.model_validate({"Mode": None}).Base)
        with self.assertRaises(ValidationError):
            MaaUserConfig_Info.model_validate({"Mode": "乱码"})

    def test_update_user_request_keeps_legacy_source(self) -> None:
        """update_user 请求体里的旧 Info.Mode 能落到 Base。"""

        request = UserUpdateIn(
            scriptId="s",
            userId="u",
            data={"Type": "MaaUserConfig", "Info": {"Mode": "直控"}},
        )
        self.assertEqual(request.data.model_dump()["Info"]["Base"], "native")


if __name__ == "__main__":
    unittest.main()
