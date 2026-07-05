import unittest

from app.models.config import MaaEndUserConfig


class MaaEndUserConfigTest(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()
