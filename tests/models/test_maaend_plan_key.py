import unittest

from app.models.config import (
    MaaEndPlanKeyValidator,
    normalize_maaend_plan_key,
    validate_maaend_plan_key,
)

PROTOCOL_SPACE_DEFAULT_KEY = {
    "SanityTaskType": "OperatorProgression",
    "OperatorProgression": "OperatorEXP",
    "WeaponProgression": "WeaponEXP",
    "CrisisDrills": "AdvancedProgression1",
    "RewardsSetOption": "RewardsSetA",
}

ESSENCE_DEFAULT_KEY = {
    "SanityTaskType": "Essence",
    "AutoEssenceSpecifiedLocation": "",
}


class NormalizeMaaEndPlanKeyTest(unittest.TestCase):
    """normalize_maaend_plan_key：任意输入归一为 canonical key"""

    def test_empty_input_returns_protocol_space_defaults(self) -> None:
        self.assertEqual(normalize_maaend_plan_key({}), PROTOCOL_SPACE_DEFAULT_KEY)
        self.assertEqual(normalize_maaend_plan_key(None), PROTOCOL_SPACE_DEFAULT_KEY)
        self.assertEqual(
            normalize_maaend_plan_key("非法输入"), PROTOCOL_SPACE_DEFAULT_KEY
        )

    def test_wrapped_key_is_unwrapped(self) -> None:
        self.assertEqual(
            normalize_maaend_plan_key({"Key": {"SanityTaskType": "Essence"}}),
            ESSENCE_DEFAULT_KEY,
        )

    def test_legacy_protocol_space_tab_migrates_to_task_type(self) -> None:
        key = normalize_maaend_plan_key(
            {"SanityTaskType": "ProtocolSpace", "ProtocolSpaceTab": "WeaponProgression"}
        )
        self.assertEqual(key["SanityTaskType"], "WeaponProgression")
        self.assertEqual(key["WeaponProgression"], "WeaponEXP")

    def test_legacy_essence_aliases_migrate_to_essence(self) -> None:
        for alias in ("Matrix", "AutoEssence"):
            with self.subTest(alias=alias):
                key = normalize_maaend_plan_key(
                    {
                        "SanityTaskType": alias,
                        "AutoEssenceSpecifiedLocation": "VFTheHub",
                    }
                )
                self.assertEqual(
                    key,
                    {
                        "SanityTaskType": "Essence",
                        "AutoEssenceSpecifiedLocation": "VFTheHub",
                    },
                )

    def test_essence_keeps_location_and_drops_protocol_fields(self) -> None:
        key = normalize_maaend_plan_key(
            {
                "SanityTaskType": "Essence",
                "AutoEssenceSpecifiedLocation": "VFPine",
                "OperatorProgression": "Promotions",
            }
        )
        self.assertEqual(
            key,
            {"SanityTaskType": "Essence", "AutoEssenceSpecifiedLocation": "VFPine"},
        )

    def test_partial_protocol_space_fields_fill_defaults(self) -> None:
        key = normalize_maaend_plan_key(
            {"SanityTaskType": "CrisisDrills", "CrisisDrills": "AdvancedProgression3"}
        )
        self.assertEqual(
            key,
            {
                "SanityTaskType": "CrisisDrills",
                "OperatorProgression": "OperatorEXP",
                "WeaponProgression": "WeaponEXP",
                "CrisisDrills": "AdvancedProgression3",
                "RewardsSetOption": "RewardsSetA",
            },
        )

    def test_unknown_task_type_falls_back_to_default(self) -> None:
        key = normalize_maaend_plan_key({"SanityTaskType": "不存在"})
        self.assertEqual(key, PROTOCOL_SPACE_DEFAULT_KEY)

    def test_invalid_field_value_falls_back_to_full_default(self) -> None:
        key = normalize_maaend_plan_key(
            {"SanityTaskType": "OperatorProgression", "OperatorProgression": "非法值"}
        )
        self.assertEqual(key, PROTOCOL_SPACE_DEFAULT_KEY)


class ValidateMaaEndPlanKeyTest(unittest.TestCase):
    """validate_maaend_plan_key：schema 校验并返回规范化结果"""

    def test_canonical_protocol_space_key_round_trips(self) -> None:
        self.assertEqual(
            validate_maaend_plan_key(PROTOCOL_SPACE_DEFAULT_KEY),
            PROTOCOL_SPACE_DEFAULT_KEY,
        )

    def test_canonical_essence_key_round_trips(self) -> None:
        essence_key = {
            "SanityTaskType": "Essence",
            "AutoEssenceSpecifiedLocation": "VFTheHub",
        }
        self.assertEqual(validate_maaend_plan_key(essence_key), essence_key)

    def test_incomplete_key_fills_defaults(self) -> None:
        self.assertEqual(
            validate_maaend_plan_key({"SanityTaskType": "Essence"}),
            ESSENCE_DEFAULT_KEY,
        )

    def test_unknown_task_type_raises(self) -> None:
        with self.assertRaises(ValueError):
            validate_maaend_plan_key({"SanityTaskType": "Matrix"})

    def test_invalid_field_value_raises(self) -> None:
        with self.assertRaises(ValueError):
            validate_maaend_plan_key(
                {
                    "SanityTaskType": "OperatorProgression",
                    "OperatorProgression": "非法值",
                }
            )

    def test_non_dict_raises(self) -> None:
        with self.assertRaises(ValueError):
            validate_maaend_plan_key("非法输入")


class MaaEndPlanKeyValidatorTest(unittest.TestCase):
    """MaaEndPlanKeyValidator：validate 只放行 canonical 值，correct 归一其余输入"""

    def setUp(self) -> None:
        self.validator = MaaEndPlanKeyValidator()

    def test_canonical_value_validates(self) -> None:
        self.assertTrue(self.validator.validate(PROTOCOL_SPACE_DEFAULT_KEY))
        self.assertTrue(
            self.validator.validate(
                {
                    "SanityTaskType": "Essence",
                    "AutoEssenceSpecifiedLocation": "VFTheHub",
                }
            )
        )

    def test_legacy_alias_fails_validate(self) -> None:
        self.assertFalse(
            self.validator.validate(
                {"SanityTaskType": "Matrix", "AutoEssenceSpecifiedLocation": "VFTheHub"}
            )
        )

    def test_incomplete_value_fails_validate(self) -> None:
        self.assertFalse(self.validator.validate({"SanityTaskType": "Essence"}))

    def test_non_dict_fails_validate(self) -> None:
        self.assertFalse(self.validator.validate("非法输入"))

    def test_correct_normalizes_legacy_alias(self) -> None:
        self.assertEqual(
            self.validator.correct(
                {"SanityTaskType": "Matrix", "AutoEssenceSpecifiedLocation": "VFTheHub"}
            ),
            {"SanityTaskType": "Essence", "AutoEssenceSpecifiedLocation": "VFTheHub"},
        )

    def test_correct_completes_incomplete_value(self) -> None:
        self.assertEqual(
            self.validator.correct({"SanityTaskType": "Essence"}),
            ESSENCE_DEFAULT_KEY,
        )


if __name__ == "__main__":
    unittest.main()
