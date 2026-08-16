import unittest

from app.models.config import MaaEndPlanConfig, MaaEndUserConfig


class MaaEndUserConfigTest(unittest.IsolatedAsyncioTestCase):
    async def test_pull_count_calculator_is_disabled_by_default(self) -> None:
        config = MaaEndUserConfig()

        self.assertFalse(config.get("Task", "IfPullCountCalculator"))

    async def test_load_migrates_legacy_protocol_space_tab(self) -> None:
        config = MaaEndUserConfig()

        await config.load(
            {
                "Task": {
                    "SanityTaskType": "ProtocolSpace",
                    "ProtocolSpaceTab": "WeaponProgression",
                }
            }
        )

        self.assertEqual(config.get("Task", "SanityTaskType"), "WeaponProgression")

    async def test_partial_task_load_keeps_existing_sanity_task_type(self) -> None:
        config = MaaEndUserConfig()
        await config.set("Task", "SanityTaskType", "CrisisDrills")

        await config.load({"Task": {"RewardsSetOption": "RewardsSetB"}})

        self.assertEqual(config.get("Task", "SanityTaskType"), "CrisisDrills")
        self.assertEqual(config.get("Task", "RewardsSetOption"), "RewardsSetB")

    async def test_plan_load_migrates_legacy_slot_to_key(self) -> None:
        config = MaaEndPlanConfig()

        await config.load(
            {
                "ALL": {
                    "SanityTaskType": "Essence",
                    "AutoEssenceSpecifiedLocation": "VFTheHub",
                }
            }
        )

        data = await config.toDict()
        self.assertEqual(
            data["ALL"],
            {
                "Key": {
                    "SanityTaskType": "Essence",
                    "AutoEssenceSpecifiedLocation": "VFTheHub",
                }
            },
        )

    async def test_fixed_mode_returns_complete_plan_key(self) -> None:
        config = MaaEndUserConfig()

        key, mode = config.get_effective_sanity_task_key()

        self.assertEqual(mode, "Fixed")
        self.assertEqual(key["SanityTaskType"], "OperatorProgression")
        self.assertEqual(key["OperatorProgression"], "OperatorEXP")


if __name__ == "__main__":
    unittest.main()
