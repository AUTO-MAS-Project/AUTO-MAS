import asyncio
import unittest
from unittest.mock import patch

from app.models.config import GameSignAccountGroup
from app.models.ConfigBase import ConfigItem, EncryptValidator
from app.utils.community import next_community_account_name


class CommunityAccountNameTest(unittest.TestCase):
    def test_allocates_first_unused_legacy_compatible_name(self) -> None:
        self.assertEqual(
            next_community_account_name(
                ["用户1", "用户 2", "自定义账号", "用户 4"]
            ),
            "用户 3",
        )

    def test_ignores_unrelated_and_invalid_names(self) -> None:
        self.assertEqual(
            next_community_account_name(["用户", "用户 0", "User 1", ""]),
            "用户 1",
        )


class CommunityCredentialStorageTest(unittest.TestCase):
    def test_encrypt_validator_preserves_long_credential(self) -> None:
        credential = f"stoken_v2=v2_{'x' * 4096}.CAE=; mid=mid-value"

        def encrypt(value: str) -> str:
            return f"encrypted:{value}"

        def decrypt(value: str) -> str:
            if value == "":
                return ""
            if value.startswith("encrypted:"):
                return value.removeprefix("encrypted:")
            raise ValueError("not encrypted")

        with (
            patch("app.models.ConfigBase.dpapi_encrypt", side_effect=encrypt),
            patch("app.models.ConfigBase.dpapi_decrypt", side_effect=decrypt),
        ):
            item = ConfigItem("GameSignAccount", "MiyousheToken", "", EncryptValidator())
            item.setValue(credential)

            self.assertEqual(item.getValue(), credential)
            self.assertEqual(len(item.getValue()), len(credential))

    def test_miyoushe_device_pair_uses_independent_encrypted_fields(self) -> None:
        def encrypt(value: str) -> str:
            return f"encrypted:{value}"

        def decrypt(value: str) -> str:
            if value == "":
                return ""
            if value.startswith("encrypted:"):
                return value.removeprefix("encrypted:")
            raise ValueError("not encrypted")

        with (
            patch("app.models.ConfigBase.dpapi_encrypt", side_effect=encrypt),
            patch("app.models.ConfigBase.dpapi_decrypt", side_effect=decrypt),
        ):
            account = GameSignAccountGroup()
            account.MiyousheDeviceId.setValue("android-device-id")
            account.MiyousheDeviceFp.setValue("android-device-fp")

            encrypted = asyncio.run(account.toDict(if_decrypt=False))[
                "GameSignAccount"
            ]
            decrypted = asyncio.run(account.toDict())["GameSignAccount"]

        self.assertIsInstance(
            account.MiyousheDeviceId.validator,
            EncryptValidator,
        )
        self.assertIsInstance(
            account.MiyousheDeviceFp.validator,
            EncryptValidator,
        )
        self.assertEqual(
            encrypted["MiyousheDeviceId"],
            "encrypted:android-device-id",
        )
        self.assertEqual(
            encrypted["MiyousheDeviceFp"],
            "encrypted:android-device-fp",
        )
        self.assertEqual(decrypted["MiyousheDeviceId"], "android-device-id")
        self.assertEqual(decrypted["MiyousheDeviceFp"], "android-device-fp")

if __name__ == "__main__":
    unittest.main()
