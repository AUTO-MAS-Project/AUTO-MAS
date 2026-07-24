"""GameSignAccounts 原生 Config v2 根与 r6 兼容边界测试。"""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from app.configuration import ConfigAggregateError
from app.configuration.roots.game_sign import (
    GameSignAccount,
    GameSignAccounts,
    GameSignAccountsOwnershipConflictError,
    assert_game_sign_accounts_ownership_consistent,
    game_sign_accounts_wire_to_legacy,
    legacy_game_sign_accounts_to_wire,
)
from app.configuration.v2.support.security import DPAPIDecryptionResult


def _legacy_account(
    uid: UUID,
    *,
    name: str = "账号 A",
    token: str = "",
) -> dict[str, object]:
    return {
        "instances": [{"uid": str(uid), "type": "GameSignAccountGroup"}],
        str(uid): {
            "GameSignAccount": {
                "Name": name,
                "Enabled": True,
                "MiyousheToken": token,
                "KuroToken": "",
                "SklandToken": "",
                "LastSignDate": "2000-01-01",
            }
        },
    }


class GameSignNativeRootTest(unittest.IsolatedAsyncioTestCase):
    async def test_activation_crud_and_order(self) -> None:
        root = GameSignAccounts()
        await root.activate()

        first = root.add(GameSignAccount)
        second = root.add(
            GameSignAccount,
            wire={"GameSignAccount": {"Name": "账号 B"}},
        )
        await root.commit()

        self.assertEqual(list(root.keys()), [first, second])
        self.assertEqual(root[first].GameSignAccount.Name, "用户 1")
        self.assertEqual(root[second].GameSignAccount.Name, "账号 B")

        root[first].GameSignAccount.Name = "账号 A"
        await root[first].commit()
        root.set_order([second, first])
        await root.commit()
        self.assertEqual(list(root.keys()), [second, first])

        root.remove(second)
        await root.commit()
        self.assertEqual(list(root.keys()), [first])

    async def test_persisted_export_keeps_encrypted_values_out_of_plaintext(
        self,
    ) -> None:
        secret = "secret-must-not-leak"
        ciphertext = "DPAPI:v1:Y2lwaGVydGV4dA=="

        def encrypt(value: str) -> str:
            self.assertEqual(value, secret)
            return ciphertext

        def decrypt(value: str) -> DPAPIDecryptionResult:
            self.assertEqual(value, ciphertext)
            return DPAPIDecryptionResult(
                secret,
                needs_migration=False,
            )

        with (
            patch(
                "app.configuration.v2.encrypted.dpapi_encrypt",
                side_effect=encrypt,
            ),
            patch(
                "app.configuration.v2.encrypted.dpapi_decrypt_with_status",
                side_effect=decrypt,
            ),
        ):
            root = GameSignAccounts()
            await root.activate()
            uid = root.add(GameSignAccount)
            await root.commit()
            root[uid].GameSignAccount.MiyousheToken = secret
            await root[uid].commit()

            persisted = await root.to_dict(if_decrypt=False)
            transport = await root.to_dict(if_decrypt=True)

        self.assertNotIn(secret, repr(persisted))
        self.assertEqual(
            persisted["data"][str(uid)]["GameSignAccount"]["MiyousheToken"],
            ciphertext,
        )
        self.assertEqual(
            transport["data"][str(uid)]["GameSignAccount"]["MiyousheToken"],
            secret,
        )

    async def test_unknown_member_field_fails_activation_atomically(self) -> None:
        uid = uuid4()
        root = GameSignAccounts(
            wire={
                "order": [{"uid": str(uid), "type": "GameSignAccount"}],
                "data": {
                    str(uid): {
                        "GameSignAccount": {
                            "Name": "账号",
                            "Unknown": "must-fail",
                        }
                    }
                },
            }
        )

        with self.assertRaises(ConfigAggregateError):
            await root.activate()
        self.assertEqual(list(root.keys()), [])


class GameSignLegacyConversionTest(unittest.TestCase):
    def test_round_trip_preserves_order_uuid_type_and_ciphertext(self) -> None:
        first = uuid4()
        second = uuid4()
        cipher = "DPAPI:v1:Y2lwaGVydGV4dA=="
        legacy = {
            "instances": [
                {"uid": str(second), "type": "GameSignAccountGroup"},
                {"uid": str(first), "type": "GameSignAccountGroup"},
            ],
            str(first): _legacy_account(first, name="A", token=cipher)[str(first)],
            str(second): _legacy_account(second, name="B")[str(second)],
        }
        before = copy.deepcopy(legacy)

        wire = legacy_game_sign_accounts_to_wire(legacy)
        restored = game_sign_accounts_wire_to_legacy(wire)

        self.assertEqual(legacy, before)
        self.assertEqual(restored, legacy)
        self.assertEqual(
            [item["uid"] for item in wire["order"]],
            [str(second), str(first)],
        )
        self.assertTrue(
            all(item["type"] == "GameSignAccount" for item in wire["order"])
        )
        self.assertEqual(
            restored[str(first)]["GameSignAccount"]["MiyousheToken"],
            cipher,
        )

    def test_missing_known_fields_use_exact_r6_defaults(self) -> None:
        uid = uuid4()
        legacy = {
            "instances": [{"uid": str(uid), "type": "GameSignAccountGroup"}],
            str(uid): {"GameSignAccount": {"Name": "只提供名称"}},
        }

        restored = game_sign_accounts_wire_to_legacy(
            legacy_game_sign_accounts_to_wire(legacy)
        )

        self.assertEqual(
            restored[str(uid)]["GameSignAccount"],
            {
                "Name": "只提供名称",
                "Enabled": True,
                "MiyousheToken": "",
                "KuroToken": "",
                "SklandToken": "",
                "LastSignDate": "2000-01-01",
            },
        )

    def test_empty_legacy_root_is_valid(self) -> None:
        self.assertEqual(
            legacy_game_sign_accounts_to_wire({}),
            {"order": [], "data": {}},
        )
        self.assertEqual(
            game_sign_accounts_wire_to_legacy({"order": [], "data": {}}),
            {"instances": []},
        )

    def test_unknown_or_orphan_data_fails_closed(self) -> None:
        uid = uuid4()
        orphan = uuid4()
        payload = _legacy_account(uid)
        payload[str(orphan)] = {"GameSignAccount": {}}
        with self.assertRaisesRegex(ValueError, "孤儿或未知"):
            legacy_game_sign_accounts_to_wire(payload)

        payload = _legacy_account(uid)
        payload[str(uid)]["GameSignAccount"]["Unknown"] = True
        with self.assertRaisesRegex(ValueError, "Unknown"):
            legacy_game_sign_accounts_to_wire(payload)

    def test_duplicate_invalid_uid_and_type_fail_closed(self) -> None:
        uid = uuid4()
        duplicate = _legacy_account(uid)
        duplicate["instances"].append(
            {"uid": str(uid), "type": "GameSignAccountGroup"}
        )
        with self.assertRaisesRegex(ValueError, "重复 uid"):
            legacy_game_sign_accounts_to_wire(duplicate)

        invalid_uid = {
            "instances": [
                {"uid": "not-a-uuid", "type": "GameSignAccountGroup"}
            ],
            "not-a-uuid": {"GameSignAccount": {}},
        }
        with self.assertRaisesRegex(ValueError, "有效 UUID"):
            legacy_game_sign_accounts_to_wire(invalid_uid)

        invalid_type = _legacy_account(uid)
        invalid_type["instances"][0]["type"] = "OtherAccount"
        with self.assertRaisesRegex(ValueError, "仅允许 GameSignAccountGroup"):
            legacy_game_sign_accounts_to_wire(invalid_type)

    def test_plaintext_can_never_be_exported_to_legacy_rollback(self) -> None:
        uid = uuid4()
        wire = {
            "order": [{"uid": str(uid), "type": "GameSignAccount"}],
            "data": {
                str(uid): {
                    "GameSignAccount": {
                        "MiyousheToken": "plain-secret-must-not-leak"
                    }
                }
            },
        }

        with self.assertRaises(ValueError) as raised:
            game_sign_accounts_wire_to_legacy(wire)
        rendered = f"{raised.exception!s} {raised.exception!r}"
        self.assertNotIn("plain-secret-must-not-leak", rendered)

    def test_v2_orphan_and_duplicate_uid_fail_closed(self) -> None:
        uid = uuid4()
        orphan = uuid4()
        with self.assertRaisesRegex(ValueError, "缺失或孤儿 uid"):
            game_sign_accounts_wire_to_legacy(
                {
                    "order": [{"uid": str(uid), "type": "GameSignAccount"}],
                    "data": {
                        str(uid): {"GameSignAccount": {}},
                        str(orphan): {"GameSignAccount": {}},
                    },
                }
            )

        with self.assertRaisesRegex(ValueError, "重复 uid"):
            game_sign_accounts_wire_to_legacy(
                {
                    "order": [
                        {"uid": str(uid), "type": "GameSignAccount"},
                        {"uid": str(uid), "type": "GameSignAccount"},
                    ],
                    "data": {str(uid): {"GameSignAccount": {}}},
                }
            )


class GameSignOwnershipTest(unittest.TestCase):
    def test_identical_non_empty_roots_are_consistent(self) -> None:
        uid = uuid4()
        standalone = _legacy_account(uid)
        tools = {
            "Other": {"Value": True},
            "SubConfigsInfo": {"GameSign_Accounts": copy.deepcopy(standalone)},
        }
        assert_game_sign_accounts_ownership_consistent(
            standalone_legacy=standalone,
            tools_config_legacy=tools,
        )

    def test_missing_fields_are_compared_by_logical_defaults(self) -> None:
        uid = uuid4()
        standalone = _legacy_account(uid)
        embedded = {
            "instances": [{"uid": str(uid), "type": "GameSignAccountGroup"}],
            str(uid): {"GameSignAccount": {"Name": "账号 A"}},
        }
        tools = {"SubConfigsInfo": {"GameSign_Accounts": embedded}}

        assert_game_sign_accounts_ownership_consistent(
            standalone_legacy=standalone,
            tools_config_legacy=tools,
        )

    def test_different_non_empty_roots_require_manual_choice(self) -> None:
        uid = uuid4()
        standalone = _legacy_account(uid, name="standalone")
        embedded = _legacy_account(uid, name="embedded")
        tools = {"SubConfigsInfo": {"GameSign_Accounts": embedded}}

        with self.assertRaises(GameSignAccountsOwnershipConflictError):
            assert_game_sign_accounts_ownership_consistent(
                standalone_legacy=standalone,
                tools_config_legacy=tools,
            )

    def test_different_ciphertext_requires_manual_choice_without_leak(self) -> None:
        uid = uuid4()
        first_cipher = "DPAPI:v1:Zmlyc3Q="
        second_cipher = "DPAPI:v1:c2Vjb25k"
        standalone = _legacy_account(uid, token=first_cipher)
        embedded = _legacy_account(uid, token=second_cipher)
        tools = {"SubConfigsInfo": {"GameSign_Accounts": embedded}}

        with self.assertRaises(
            GameSignAccountsOwnershipConflictError
        ) as raised:
            assert_game_sign_accounts_ownership_consistent(
                standalone_legacy=standalone,
                tools_config_legacy=tools,
            )
        rendered = f"{raised.exception!s} {raised.exception!r}"
        self.assertNotIn(first_cipher, rendered)
        self.assertNotIn(second_cipher, rendered)

    def test_standalone_empty_remains_authoritative_without_auto_copy(self) -> None:
        uid = uuid4()
        tools = {
            "SubConfigsInfo": {
                "GameSign_Accounts": _legacy_account(uid, name="historical")
            }
        }
        standalone: dict[str, object] = {}
        before = copy.deepcopy(tools)

        assert_game_sign_accounts_ownership_consistent(
            standalone_legacy=standalone,
            tools_config_legacy=tools,
        )

        self.assertEqual(tools, before)
        self.assertEqual(standalone, {})
