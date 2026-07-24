"""宿主 Config 原生 Config v2 根与 r6 兼容边界测试。"""

from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from app.configuration import ConfigAggregateError
from app.configuration.roots.config import (
    CUSTOM_WEBHOOKS_NAME,
    GlobalConfig,
    Webhook,
    config_wire_to_legacy,
    legacy_config_to_wire,
)
from app.configuration.v2.support.security import DPAPIDecryptionResult

_CIPHER_KOISHI = "DPAPI:v1:a29pc2hp"
_CIPHER_AUTH = "DPAPI:v1:YXV0aA=="
_CIPHER_SERVER_CHAN = "DPAPI:v1:c2VydmVy"
_CIPHER_PROXY = "DPAPI:v1:cHJveHk="
_CIPHER_MIRROR = "DPAPI:v1:bWlycm9y"
_CIPHER_GITHUB = "DPAPI:v1:Z2l0aHVi"
_CIPHER_URL = "DPAPI:v1:dXJs"
_CIPHER_HEADERS = "DPAPI:v1:aGVhZGVycw=="

_PLAINTEXT_BY_CIPHER = {
    _CIPHER_KOISHI: "koishi-secret",
    _CIPHER_AUTH: "mail-secret",
    _CIPHER_SERVER_CHAN: "server-secret",
    _CIPHER_PROXY: "http://127.0.0.1:7890",
    _CIPHER_MIRROR: "mirror-secret",
    _CIPHER_GITHUB: "github-secret",
    _CIPHER_URL: "https://example.com/hook",
    _CIPHER_HEADERS: '{"Authorization": "secret"}',
}
_CIPHER_BY_PLAINTEXT = {
    value: cipher for cipher, value in _PLAINTEXT_BY_CIPHER.items()
}
_CIPHER_BY_PLAINTEXT["{ }"] = _CIPHER_HEADERS


def _legacy_config(
    webhook_uids: tuple[UUID, ...] = (),
) -> dict[str, object]:
    webhooks: dict[str, object] = {
        "instances": [
            {"uid": str(uid), "type": "Webhook"} for uid in webhook_uids
        ]
    }
    for index, uid in enumerate(webhook_uids, start=1):
        webhooks[str(uid)] = {
            "Info": {
                "Name": f"Webhook {index}",
                "Enabled": index % 2 == 1,
            },
            "Data": {
                "Url": _CIPHER_URL,
                "Template": f"template-{index}",
                "Headers": _CIPHER_HEADERS,
                "Method": "POST" if index % 2 else "GET",
            },
        }

    return {
        "Function": {
            "HistoryRetentionTime": 30,
            "IfAllowSleep": True,
            "IfSilence": False,
            "IfAgreeBilibili": True,
            "IfBlockAd": False,
        },
        "Voice": {"Enabled": True, "Type": "noisy"},
        "Start": {
            "IfSelfStart": True,
            "IfMinimizeDirectly": False,
        },
        "UI": {
            "IfShowTray": True,
            "IfToTray": True,
            "IfHideCloseButton": True,
        },
        "Notify": {
            "SendTaskResultTime": "仅失败时",
            "IfSendStatistic": True,
            "IfSendSixStar": True,
            "IfPushPlyer": True,
            "IfSendMail": True,
            "IfKoishiSupport": True,
            "KoishiServerAddress": "ws://localhost:5140/AUTO_MAS",
            "KoishiToken": _CIPHER_KOISHI,
            "SMTPServerAddress": "smtp.example.com",
            "AuthorizationCode": _CIPHER_AUTH,
            "FromAddress": "from@example.com",
            "ToAddress": "to@example.com",
            "IfServerChan": True,
            "ServerChanKey": _CIPHER_SERVER_CHAN,
        },
        "Update": {
            "IfAutoUpdate": True,
            "Source": "CNB",
            "Channel": "beta",
            "ProxyAddress": _CIPHER_PROXY,
            "MirrorChyanCDK": _CIPHER_MIRROR,
            "GitHubToken": _CIPHER_GITHUB,
        },
        "Data": {
            "UID": str(uuid4()),
            "LastStatisticsUpload": "2026-07-23 01:02:03",
            "LastStageUpdated": "2026-07-23 02:03:04",
            "StageETag": "stage-etag",
            "StageData": "{ }",
            # r6 会持久化这个派生缓存；Config v2 有意不持久化。
            "Stage": '{"Info": []}',
            "LastNoticeUpdated": "2026-07-23 03:04:05",
            "NoticeETag": "notice-etag",
            "IfShowNotice": False,
            "Notice": '{"title": "notice"}',
            "LastWebConfigUpdated": "2026-07-23 04:05:06",
            "WebConfig": '[{"name": "demo"}]',
        },
        "SubConfigsInfo": {CUSTOM_WEBHOOKS_NAME: webhooks},
    }


def _decrypt(value: str) -> DPAPIDecryptionResult:
    return DPAPIDecryptionResult(
        _PLAINTEXT_BY_CIPHER[value],
        needs_migration=False,
    )


def _encrypt(value: str) -> str:
    return _CIPHER_BY_PLAINTEXT[value]


class ConfigNativeRootTest(unittest.IsolatedAsyncioTestCase):
    def test_model_declares_exact_current_root_fields(self) -> None:
        self.assertEqual(
            set(GlobalConfig.model_fields),
            {
                "Function",
                "Voice",
                "Start",
                "UI",
                "Notify",
                "Update",
                "Data",
                CUSTOM_WEBHOOKS_NAME,
            },
        )
        self.assertEqual(
            set(GlobalConfig.FunctionGroup.model_fields),
            {
                "HistoryRetentionTime",
                "IfAllowSleep",
                "IfSilence",
                "IfAgreeBilibili",
                "IfBlockAd",
            },
        )
        self.assertEqual(
            set(GlobalConfig.NotifyGroup.model_fields),
            {
                "SendTaskResultTime",
                "IfSendStatistic",
                "IfSendSixStar",
                "IfPushPlyer",
                "IfSendMail",
                "IfKoishiSupport",
                "KoishiServerAddress",
                "KoishiToken",
                "SMTPServerAddress",
                "AuthorizationCode",
                "FromAddress",
                "ToAddress",
                "IfServerChan",
                "ServerChanKey",
            },
        )
        self.assertEqual(
            set(GlobalConfig.UpdateGroup.model_fields),
            {
                "IfAutoUpdate",
                "Source",
                "Channel",
                "ProxyAddress",
                "MirrorChyanCDK",
                "GitHubToken",
            },
        )
        self.assertEqual(
            set(GlobalConfig.DataGroup.model_fields),
            {
                "UID",
                "LastStatisticsUpload",
                "LastStageUpdated",
                "StageETag",
                "StageData",
                "Stage",
                "LastNoticeUpdated",
                "NoticeETag",
                "IfShowNotice",
                "Notice",
                "LastWebConfigUpdated",
                "WebConfig",
            },
        )

    async def test_activation_encryption_virtual_projection_and_order(self) -> None:
        first = uuid4()
        second = uuid4()
        legacy = _legacy_config((second, first))
        wire = legacy_config_to_wire(legacy)

        with (
            patch(
                "app.configuration.v2.encrypted.dpapi_encrypt",
                side_effect=_encrypt,
            ),
            patch(
                "app.configuration.v2.encrypted.dpapi_decrypt_with_status",
                side_effect=_decrypt,
            ),
        ):
            root = GlobalConfig.build(wire=wire)
            await root.activate()
            persisted = await root.to_dict(if_decrypt=False)
            transport = await root.to_dict(
                if_decrypt=True,
                include_reactive=True,
            )

        self.assertEqual(
            [
                item["uid"]
                for item in persisted[CUSTOM_WEBHOOKS_NAME]["order"]
            ],
            [str(second), str(first)],
        )
        self.assertEqual(persisted["Notify"]["KoishiToken"], _CIPHER_KOISHI)
        self.assertEqual(persisted["Update"]["ProxyAddress"], _CIPHER_PROXY)
        self.assertNotIn("Stage", persisted["Data"])
        self.assertEqual(transport["Notify"]["KoishiToken"], "koishi-secret")
        self.assertEqual(
            transport[CUSTOM_WEBHOOKS_NAME]["data"][str(first)]["Data"]["Url"],
            "https://example.com/hook",
        )
        stage = json.loads(transport["Data"]["Stage"])
        self.assertIn("Info", stage)
        self.assertIn("ALL", stage)
        self.assertIn("Monday", stage)
        self.assertNotIn("koishi-secret", repr(persisted))
        self.assertNotIn("https://example.com/hook", repr(persisted))

    async def test_empty_root_uses_dynamic_uid_only_during_activation(self) -> None:
        wire = legacy_config_to_wire({})
        self.assertNotIn("UID", wire["Data"])
        self.assertEqual(
            wire[CUSTOM_WEBHOOKS_NAME],
            {"order": [], "data": {}},
        )

        root = GlobalConfig.build(wire=wire)
        await root.activate()
        persisted = await root.to_dict()

        self.assertEqual(str(UUID(persisted["Data"]["UID"])), persisted["Data"]["UID"])
        self.assertFalse(persisted["UI"]["IfHideCloseButton"])
        self.assertNotIn("Stage", persisted["Data"])

    async def test_runtime_types_and_unknown_virtual_field_fail_closed(self) -> None:
        root = GlobalConfig.build(wire=legacy_config_to_wire({}))
        await root.activate()
        original = root.Function.HistoryRetentionTime

        root.Function.HistoryRetentionTime = True  # type: ignore[assignment]
        with self.assertRaises(ConfigAggregateError):
            await root.commit()
        self.assertEqual(root.Function.HistoryRetentionTime, original)

        wire = legacy_config_to_wire({})
        wire["Data"]["Stage"] = "{}"
        bad = GlobalConfig.build(wire=wire)
        with self.assertRaises(ValueError):
            await bad.activate()


class ConfigLegacyConversionTest(unittest.TestCase):
    def test_round_trip_preserves_all_persistent_fields_order_and_uuid(self) -> None:
        first = uuid4()
        second = uuid4()
        legacy = _legacy_config((second, first))
        before = copy.deepcopy(legacy)

        wire = legacy_config_to_wire(legacy)
        restored = config_wire_to_legacy(wire)

        self.assertEqual(legacy, before)
        self.assertNotIn("Stage", wire["Data"])
        expected = copy.deepcopy(legacy)
        expected["Data"].pop("Stage")
        self.assertEqual(restored, expected)
        self.assertEqual(
            [item["uid"] for item in wire[CUSTOM_WEBHOOKS_NAME]["order"]],
            [str(second), str(first)],
        )
        self.assertTrue(
            all(
                item["type"] == "Webhook"
                for item in wire[CUSTOM_WEBHOOKS_NAME]["order"]
            )
        )

    def test_historical_stage_alias_is_promoted_only_when_stage_data_missing(
        self,
    ) -> None:
        legacy = _legacy_config()
        legacy["Data"].pop("StageData")
        legacy["Data"]["Stage"] = '{"legacy": {"Activity": {}, "Stages": []}}'

        wire = legacy_config_to_wire(legacy)

        self.assertEqual(
            wire["Data"]["StageData"],
            '{"legacy": {"Activity": {}, "Stages": []}}',
        )
        self.assertNotIn("Stage", wire["Data"])

        current = _legacy_config()
        current["Data"]["StageData"] = '{"authoritative": {}}'
        current["Data"]["Stage"] = '{"derived": []}'
        current_wire = legacy_config_to_wire(current)
        self.assertEqual(
            current_wire["Data"]["StageData"],
            '{"authoritative": {}}',
        )

    def test_plaintext_newly_hardened_fields_are_migration_input_only(self) -> None:
        uid = uuid4()
        legacy = _legacy_config((uid,))
        legacy["Notify"]["KoishiToken"] = "legacy-koishi-plaintext"
        legacy["Notify"]["ServerChanKey"] = "legacy-server-plaintext"
        legacy["Update"]["ProxyAddress"] = "http://127.0.0.1:7890"
        webhook = legacy["SubConfigsInfo"][CUSTOM_WEBHOOKS_NAME][str(uid)]
        webhook["Data"]["Url"] = "https://example.com/plain"
        webhook["Data"]["Headers"] = '{"X-Token": "plain"}'

        wire = legacy_config_to_wire(legacy)

        self.assertEqual(
            wire["Notify"]["KoishiToken"],
            "legacy-koishi-plaintext",
        )
        with self.assertRaises(ValueError) as raised:
            config_wire_to_legacy(wire)
        rendered = f"{raised.exception!s} {raised.exception!r}"
        self.assertNotIn("legacy-koishi-plaintext", rendered)
        self.assertNotIn("legacy-server-plaintext", rendered)

    def test_historically_encrypted_fields_reject_plaintext_without_leak(
        self,
    ) -> None:
        for group_name, field_name in (
            ("Notify", "AuthorizationCode"),
            ("Update", "MirrorChyanCDK"),
            ("Update", "GitHubToken"),
        ):
            with self.subTest(path=f"{group_name}.{field_name}"):
                legacy = _legacy_config()
                legacy[group_name][field_name] = "must-not-leak"
                with self.assertRaises(ValueError) as raised:
                    legacy_config_to_wire(legacy)
                rendered = f"{raised.exception!s} {raised.exception!r}"
                self.assertNotIn("must-not-leak", rendered)

    def test_webhook_plaintext_cannot_cross_rollback_boundary(self) -> None:
        uid = uuid4()
        wire = legacy_config_to_wire(_legacy_config((uid,)))
        wire[CUSTOM_WEBHOOKS_NAME]["data"][str(uid)]["Data"]["Url"] = (
            "https://secret.example/hook"
        )

        with self.assertRaises(ValueError) as raised:
            config_wire_to_legacy(wire)
        rendered = f"{raised.exception!s} {raised.exception!r}"
        self.assertNotIn("secret.example", rendered)

    def test_unknown_root_group_nested_and_reactive_fields_fail_closed(self) -> None:
        cases: list[dict[str, object]] = []

        payload = _legacy_config()
        payload["Future"] = {}
        cases.append(payload)

        payload = _legacy_config()
        payload["Notify"]["Unknown"] = True
        cases.append(payload)

        payload = _legacy_config()
        payload["SubConfigsInfo"]["Other"] = {"instances": []}
        cases.append(payload)

        for payload in cases:
            with self.subTest(keys=sorted(payload)):
                with self.assertRaisesRegex(ValueError, "未知主配置路径"):
                    legacy_config_to_wire(payload)

        wire = legacy_config_to_wire(_legacy_config())
        wire["Data"]["Stage"] = "{}"
        with self.assertRaisesRegex(ValueError, "Stage"):
            config_wire_to_legacy(wire)

    def test_bad_root_types_values_and_json_fail_closed(self) -> None:
        mutations = (
            ("Function", "HistoryRetentionTime", True),
            ("Function", "IfAllowSleep", 1),
            ("Voice", "Type", "loud"),
            ("Notify", "SendTaskResultTime", "sometimes"),
            ("Notify", "KoishiServerAddress", "localhost:5140"),
            ("Update", "Source", "Other"),
            ("Update", "Channel", "nightly"),
            ("Data", "UID", "not-a-uuid"),
            ("Data", "LastStageUpdated", "yesterday"),
            ("Data", "StageData", "[]"),
            ("Data", "Notice", "not-json"),
            ("Data", "WebConfig", "{}"),
        )
        for group_name, field_name, value in mutations:
            with self.subTest(path=f"{group_name}.{field_name}"):
                payload = _legacy_config()
                payload[group_name][field_name] = value
                with self.assertRaises((TypeError, ValueError)):
                    legacy_config_to_wire(payload)

    def test_webhook_orphan_duplicate_missing_wrong_type_and_bad_value_fail(
        self,
    ) -> None:
        uid = uuid4()
        orphan = uuid4()

        payload = _legacy_config((uid,))
        payload["SubConfigsInfo"][CUSTOM_WEBHOOKS_NAME][str(orphan)] = {
            "Info": {},
            "Data": {},
        }
        with self.assertRaisesRegex(ValueError, "孤儿"):
            legacy_config_to_wire(payload)

        payload = _legacy_config((uid,))
        payload["SubConfigsInfo"][CUSTOM_WEBHOOKS_NAME]["instances"].append(
            {"uid": str(uid), "type": "Webhook"}
        )
        with self.assertRaisesRegex(ValueError, "重复 uid"):
            legacy_config_to_wire(payload)

        payload = _legacy_config((uid,))
        payload["SubConfigsInfo"][CUSTOM_WEBHOOKS_NAME].pop(str(uid))
        with self.assertRaisesRegex(ValueError, "缺失"):
            legacy_config_to_wire(payload)

        payload = _legacy_config((uid,))
        payload["SubConfigsInfo"][CUSTOM_WEBHOOKS_NAME]["instances"][0][
            "type"
        ] = "Other"
        with self.assertRaisesRegex(ValueError, "仅允许 Webhook"):
            legacy_config_to_wire(payload)

        payload = _legacy_config((uid,))
        payload["SubConfigsInfo"][CUSTOM_WEBHOOKS_NAME][str(uid)]["Info"][
            "Enabled"
        ] = 1
        with self.assertRaisesRegex(TypeError, "布尔值"):
            legacy_config_to_wire(payload)

        payload = _legacy_config((uid,))
        payload["SubConfigsInfo"][CUSTOM_WEBHOOKS_NAME][str(uid)]["Data"][
            "Headers"
        ] = "[]"
        with self.assertRaisesRegex(ValueError, "JSON 字典"):
            legacy_config_to_wire(payload)

    def test_v2_collection_orphan_duplicate_and_wrong_type_fail_closed(self) -> None:
        uid = uuid4()
        orphan = uuid4()
        wire = legacy_config_to_wire(_legacy_config((uid,)))
        wire[CUSTOM_WEBHOOKS_NAME]["data"][str(orphan)] = copy.deepcopy(
            wire[CUSTOM_WEBHOOKS_NAME]["data"][str(uid)]
        )
        with self.assertRaisesRegex(ValueError, "缺失或孤儿"):
            config_wire_to_legacy(wire)

        wire = legacy_config_to_wire(_legacy_config((uid,)))
        wire[CUSTOM_WEBHOOKS_NAME]["order"].append(
            {"uid": str(uid), "type": "Webhook"}
        )
        with self.assertRaisesRegex(ValueError, "重复 uid"):
            config_wire_to_legacy(wire)

        wire = legacy_config_to_wire(_legacy_config((uid,)))
        wire[CUSTOM_WEBHOOKS_NAME]["order"][0]["type"] = "Other"
        with self.assertRaisesRegex(ValueError, "仅允许 Webhook"):
            config_wire_to_legacy(wire)

    def test_missing_known_fields_use_static_defaults_without_guessing_uid(
        self,
    ) -> None:
        wire = legacy_config_to_wire({})
        restored = config_wire_to_legacy(wire)

        self.assertEqual(wire["Function"]["HistoryRetentionTime"], 0)
        self.assertEqual(wire["Notify"]["SendTaskResultTime"], "不推送")
        self.assertEqual(wire["Update"]["Source"], "GitHub")
        self.assertEqual(wire["Data"]["StageData"], "{ }")
        self.assertNotIn("UID", wire["Data"])
        self.assertNotIn("UID", restored["Data"])
        self.assertEqual(
            restored["SubConfigsInfo"][CUSTOM_WEBHOOKS_NAME],
            {"instances": []},
        )

    def test_webhook_class_defaults_match_current_legacy_model(self) -> None:
        with patch(
            "app.configuration.v2.encrypted.dpapi_encrypt",
            return_value=_CIPHER_HEADERS,
        ):
            webhook = Webhook()
            self.assertEqual(webhook.Info.Name, "新自定义 Webhook 通知")
            self.assertIs(webhook.Info.Enabled, True)
            self.assertEqual(webhook.Data.Method, "POST")


if __name__ == "__main__":
    unittest.main()
