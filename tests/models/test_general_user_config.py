import unittest

from app.models.config import GeneralUserConfig


class GeneralUserConfigTest(unittest.IsolatedAsyncioTestCase):
    async def test_mas_config_is_enabled_by_default(self) -> None:
        config = GeneralUserConfig()

        self.assertTrue(config.get("Info", "IfUseMasConfig"))

    async def test_external_config_can_be_loaded(self) -> None:
        config = GeneralUserConfig()

        await config.load({"Info": {"IfUseMasConfig": False}})

        self.assertFalse(config.get("Info", "IfUseMasConfig"))


if __name__ == "__main__":
    unittest.main()
