"""ToolsConfig 原生 Config v2 根与 r6 所有权边界测试。"""

from __future__ import annotations

import copy
import json
import unittest
from uuid import UUID, uuid4

from app.configuration import ConfigAggregateError
from app.configuration.roots.game_sign import (
    GameSignAccountsOwnershipConflictError,
)
from app.configuration.roots.tools import (
    ToolsConfig,
    legacy_tools_to_wire,
    tools_wire_to_legacy,
)

_CIPHER_A = "DPAPI:v1:Zmlyc3Q="
_CIPHER_B = "DPAPI:v1:c2Vjb25k"


def _legacy_account(uid: UUID, *, token: str = "") -> dict[str, object]:
    return {
        "instances": [{"uid": str(uid), "type": "GameSignAccountGroup"}],
        str(uid): {
            "GameSignAccount": {
                "Name": "账号 A",
                "Enabled": True,
                "MiyousheToken": token,
                "KuroToken": "",
                "SklandToken": "",
                "LastSignDate": "2000-01-01",
            }
        },
    }


def _legacy_tools(
    *,
    embedded_accounts: object | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "ArknightsPC": {
            "Enabled": True,
            "PauseKey": "f10",
            "SelectDeployedKey": "w",
            "UseSkillKey": "r",
            "RetreatKey": "t",
            "NextFrameKey": "f",
            "AnotherQuitKey": "space",
            "Status": '{"text":"未连接","color":"red"}',
        },
        "GameSign": {
            "Enabled": True,
            "NotifyEnabled": True,
            "WindowStart": "07:15",
            "WindowEnd": "23:45",
            "RunOnStartup": True,
            "ScheduledRun": False,
            "AutoStart": True,
            "LastSignDate": "2026-07-23",
            "ScheduledTime": "09:37",
            "Status": '{"text":"已启用","color":"green"}',
            "Result": '{"米游社":[]}',
        },
    }
    if embedded_accounts is not None:
        payload["SubConfigsInfo"] = {"GameSign_Accounts": embedded_accounts}
    return payload


class ToolsNativeRootTest(unittest.IsolatedAsyncioTestCase):
    async def test_field_matrix_matches_r6_and_keeps_accounts_separate(
        self,
    ) -> None:
        self.assertEqual(
            set(ToolsConfig.ArknightsPCGroup.model_fields),
            {
                "Enabled",
                "PauseKey",
                "SelectDeployedKey",
                "UseSkillKey",
                "RetreatKey",
                "NextFrameKey",
                "AnotherQuitKey",
                "Status",
            },
        )
        self.assertEqual(
            set(ToolsConfig.GameSignGroup.model_fields),
            {
                "Enabled",
                "NotifyEnabled",
                "WindowStart",
                "WindowEnd",
                "RunOnStartup",
                "ScheduledRun",
                "AutoStart",
                "LastSignDate",
                "ScheduledTime",
                "Status",
                "Result",
            },
        )
        self.assertNotIn("GameSign_Accounts", ToolsConfig.model_fields)

    async def test_activation_persistence_and_virtual_runtime_projection(
        self,
    ) -> None:
        wire = legacy_tools_to_wire(
            _legacy_tools(),
            standalone_game_sign_accounts_legacy={},
        )
        root = ToolsConfig.build(wire=wire)
        await root.activate()

        persisted = await root.to_dict()
        transport = await root.to_dict(include_reactive=True)
        self.assertNotIn("Status", persisted["ArknightsPC"])
        self.assertNotIn("Status", persisted["GameSign"])
        self.assertNotIn("Result", persisted["GameSign"])
        self.assertEqual(
            json.loads(transport["ArknightsPC"]["Status"]),
            {"text": "已暂停", "color": "yellow"},
        )
        self.assertEqual(
            json.loads(transport["GameSign"]["Status"]),
            {"text": "已启用", "color": "green"},
        )

        root.arknights_pc_running = True
        root.arknights_pc_get_connected = lambda: True
        root._game_sign_result_data["米游社"] = [{"status": "成功"}]
        transport = await root.to_dict(include_reactive=True)
        self.assertEqual(
            json.loads(transport["ArknightsPC"]["Status"]),
            {"text": "运行中", "color": "green"},
        )
        self.assertEqual(
            json.loads(transport["GameSign"]["Result"]),
            {"米游社": [{"status": "成功"}]},
        )
        self.assertEqual(root.arknights_pc_keys, ["w", "r", "t", "f", "space"])

    async def test_runtime_assignment_is_strict_and_atomic(self) -> None:
        root = ToolsConfig.build(
            wire=legacy_tools_to_wire(
                {},
                standalone_game_sign_accounts_legacy={},
            )
        )
        await root.activate()

        root.ArknightsPC.PauseKey = "not-a-key"
        with self.assertRaises(ConfigAggregateError):
            await root.commit()
        self.assertEqual(root.ArknightsPC.PauseKey, "f10")

        root.GameSign.WindowStart = "25:15"
        with self.assertRaises(ConfigAggregateError):
            await root.commit()
        self.assertEqual(root.GameSign.WindowStart, "08:00")

        root.GameSign.Enabled = 1  # type: ignore[assignment]
        with self.assertRaises(ConfigAggregateError):
            await root.commit()
        self.assertIs(root.GameSign.Enabled, False)

    async def test_v2_unknown_or_virtual_input_fails_activation(self) -> None:
        wire = legacy_tools_to_wire(
            {},
            standalone_game_sign_accounts_legacy={},
        )
        wire["GameSign"]["Status"] = "forged"
        root = ToolsConfig.build(wire=wire)
        with self.assertRaises(ValueError):
            await root.activate()

        wire = legacy_tools_to_wire(
            {},
            standalone_game_sign_accounts_legacy={},
        )
        wire["ArknightsPC"]["Unknown"] = True
        root = ToolsConfig.build(wire=wire)
        with self.assertRaises(ValueError):
            await root.activate()


class ToolsLegacyConversionTest(unittest.TestCase):
    def test_conversion_canonicalizes_virtuals_and_embedded_copy(self) -> None:
        uid = uuid4()
        accounts = _legacy_account(uid, token=_CIPHER_A)
        legacy = _legacy_tools(embedded_accounts=copy.deepcopy(accounts))
        before = copy.deepcopy(legacy)

        wire = legacy_tools_to_wire(
            legacy,
            standalone_game_sign_accounts_legacy=accounts,
        )
        restored = tools_wire_to_legacy(wire)

        self.assertEqual(legacy, before)
        self.assertEqual(
            restored,
            {
                "ArknightsPC": {
                    name: value
                    for name, value in legacy["ArknightsPC"].items()
                    if name != "Status"
                },
                "GameSign": {
                    name: value
                    for name, value in legacy["GameSign"].items()
                    if name not in {"Status", "Result"}
                },
            },
        )
        self.assertNotIn("SubConfigsInfo", wire)
        self.assertNotIn("SubConfigsInfo", restored)
        self.assertNotIn(_CIPHER_A, repr(wire))
        self.assertNotIn(_CIPHER_A, repr(restored))

    def test_missing_fields_use_exact_r6_defaults(self) -> None:
        restored = tools_wire_to_legacy(
            legacy_tools_to_wire(
                {},
                standalone_game_sign_accounts_legacy={},
            )
        )
        self.assertEqual(
            restored,
            {
                "ArknightsPC": {
                    "Enabled": False,
                    "PauseKey": "f10",
                    "SelectDeployedKey": "w",
                    "UseSkillKey": "r",
                    "RetreatKey": "t",
                    "NextFrameKey": "f",
                    "AnotherQuitKey": "space",
                },
                "GameSign": {
                    "Enabled": False,
                    "NotifyEnabled": False,
                    "WindowStart": "08:00",
                    "WindowEnd": "22:00",
                    "RunOnStartup": False,
                    "ScheduledRun": True,
                    "AutoStart": False,
                    "LastSignDate": "2000-01-01",
                    "ScheduledTime": "",
                },
            },
        )

    def test_identical_dual_write_is_accepted_but_not_copied(self) -> None:
        uid = uuid4()
        accounts = _legacy_account(uid, token=_CIPHER_A)
        wire = legacy_tools_to_wire(
            _legacy_tools(embedded_accounts=copy.deepcopy(accounts)),
            standalone_game_sign_accounts_legacy=accounts,
        )
        self.assertEqual(set(wire), {"ArknightsPC", "GameSign"})

    def test_conflicting_dual_write_fails_without_secret_leak(self) -> None:
        uid = uuid4()
        standalone = _legacy_account(uid, token=_CIPHER_A)
        embedded = _legacy_account(uid, token=_CIPHER_B)

        with self.assertRaises(
            GameSignAccountsOwnershipConflictError
        ) as raised:
            legacy_tools_to_wire(
                _legacy_tools(embedded_accounts=embedded),
                standalone_game_sign_accounts_legacy=standalone,
            )
        rendered = f"{raised.exception!s} {raised.exception!r}"
        self.assertNotIn(_CIPHER_A, rendered)
        self.assertNotIn(_CIPHER_B, rendered)

    def test_malformed_or_plaintext_embedded_accounts_fail_closed(self) -> None:
        uid = uuid4()
        duplicate = _legacy_account(uid)
        duplicate["instances"].append(
            {"uid": str(uid), "type": "GameSignAccountGroup"}
        )
        with self.assertRaisesRegex(ValueError, "重复 uid"):
            legacy_tools_to_wire(
                _legacy_tools(embedded_accounts=duplicate),
                standalone_game_sign_accounts_legacy={},
            )

        plaintext = _legacy_account(uid, token="plain-secret-must-not-leak")
        with self.assertRaises(ValueError) as raised:
            legacy_tools_to_wire(
                _legacy_tools(embedded_accounts=plaintext),
                standalone_game_sign_accounts_legacy={},
            )
        rendered = f"{raised.exception!s} {raised.exception!r}"
        self.assertNotIn("plain-secret-must-not-leak", rendered)

    def test_unknown_or_noncanonical_aliases_fail_closed(self) -> None:
        payload = _legacy_tools()
        payload["Unknown"] = {}
        with self.assertRaisesRegex(ValueError, "Unknown"):
            legacy_tools_to_wire(
                payload,
                standalone_game_sign_accounts_legacy={},
            )

        payload = _legacy_tools()
        payload["SubConfigsInfo"] = {"GameSignAccounts": {}}
        with self.assertRaisesRegex(ValueError, "GameSignAccounts"):
            legacy_tools_to_wire(
                payload,
                standalone_game_sign_accounts_legacy={},
            )

        with self.assertRaisesRegex(ValueError, "SubConfigsInfo"):
            tools_wire_to_legacy(
                {
                    "ArknightsPC": {},
                    "GameSign": {},
                    "SubConfigsInfo": {
                        "GameSign_Accounts": {
                            "token": "plain-secret-must-not-leak"
                        }
                    },
                }
            )

    def test_invalid_types_keys_dates_and_virtual_types_fail_closed(self) -> None:
        invalid_cases = (
            ("ArknightsPC", "Enabled", 1),
            ("ArknightsPC", "PauseKey", "F10"),
            ("GameSign", "WindowStart", "25:00"),
            ("GameSign", "LastSignDate", "2026/07/23"),
            ("GameSign", "ScheduledTime", 937),
            ("GameSign", "Result", {}),
        )
        for group, field, value in invalid_cases:
            with self.subTest(group=group, field=field):
                payload = _legacy_tools()
                payload[group][field] = value
                with self.assertRaises((TypeError, ValueError)):
                    legacy_tools_to_wire(
                        payload,
                        standalone_game_sign_accounts_legacy={},
                    )

    def test_wire_rejects_virtual_unknown_and_non_dict_groups(self) -> None:
        with self.assertRaisesRegex(ValueError, "Status"):
            tools_wire_to_legacy(
                {
                    "ArknightsPC": {"Status": "forged"},
                    "GameSign": {},
                }
            )
        with self.assertRaisesRegex(ValueError, "Unknown"):
            tools_wire_to_legacy(
                {
                    "ArknightsPC": {},
                    "GameSign": {"Unknown": True},
                }
            )
        with self.assertRaises(TypeError):
            tools_wire_to_legacy(
                {"ArknightsPC": [], "GameSign": {}}
            )
