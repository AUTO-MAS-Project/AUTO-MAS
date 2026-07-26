"""PluginConfig 原生 Config v2 根与 r6 兼容边界测试。"""

from __future__ import annotations

import copy
import json
import re
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from app.configuration import ConfigAggregateError
from app.configuration.roots.plugin_config import (
    PluginConfig,
    PluginInstance,
    legacy_plugin_config_to_wire,
    plugin_config_wire_to_legacy,
)
from app.configuration.v2.support.security import DPAPIDecryptionResult
from app.plugins.config_store import PluginConfigStore

_CIPHERTEXT = "DPAPI:v1:Y2lwaGVydGV4dA=="


def _legacy_plugin_config(
    uid: UUID,
    *,
    plugin: str = "demo_plugin@local",
    instance_id: str = "instance_1",
    config_raw: str = _CIPHERTEXT,
) -> dict[str, object]:
    return {
        "Data": {"Version": 1},
        "SubConfigsInfo": {
            "PluginInstances": {
                "instances": [
                    {"uid": str(uid), "type": "PluginInstanceConfig"}
                ],
                str(uid): {
                    "Info": {
                        "Plugin": plugin,
                        "Id": instance_id,
                        "Enabled": True,
                        "Name": "测试插件实例",
                    },
                    "Data": {"ConfigRaw": config_raw},
                },
            }
        },
    }


class PluginConfigNativeRootTest(unittest.IsolatedAsyncioTestCase):
    async def test_plugin_store_writes_authoritative_native_root(self) -> None:
        """Plugin bootstrap must not call the removed legacy ``load`` API."""

        with (
            patch(
                "app.configuration.v2.encrypted.dpapi_encrypt",
                return_value=_CIPHERTEXT,
            ),
            patch(
                "app.configuration.v2.encrypted.dpapi_decrypt_with_status",
                return_value=DPAPIDecryptionResult('{"answer": 42}', False),
            ),
        ):
            root = PluginConfig()
            await root.activate()
            stale_uid = root.PluginInstances.add(
                PluginInstance,
                wire={
                    "Info": {"Plugin": "stale", "Id": "old"},
                    "Data": {"ConfigRaw": "{}"},
                },
            )
            await root.PluginInstances.commit()

            store = PluginConfigStore(schema_manager=MagicMock())
            store._resolve_storage_config = MagicMock(  # type: ignore[method-assign]
                side_effect=lambda _name, config, **_kwargs: config
            )
            compatibility_load = AsyncMock()
            native_facade = SimpleNamespace(
                PluginConfig=SimpleNamespace(
                    Data=root.Data,
                    PluginInstances=root.PluginInstances,
                    commit=root.commit,
                    load=compatibility_load,
                )
            )
            with patch("app.core.Config", native_facade):
                await store._write_root(
                    {
                        "version": 3,
                        "instances": [
                            {
                                "id": "demo:primary",
                                "plugin": "demo",
                                "enabled": True,
                                "name": "主实例",
                                "config": {"answer": 42},
                            }
                        ],
                    }
                )

            compatibility_load.assert_not_awaited()
            self.assertEqual(root.Data.Version, 3)
            self.assertNotIn(stale_uid, root.PluginInstances)
            self.assertEqual(len(root.PluginInstances), 1)
            instance = next(iter(root.PluginInstances.values()))
            self.assertEqual(instance.Info.Plugin, "demo")
            self.assertEqual(instance.Info.Id, "primary")
            self.assertEqual(instance.Info.Name, "主实例")
            self.assertEqual(json.loads(instance.Data.ConfigRaw), {"answer": 42})

    async def test_activation_crud_update_and_order(self) -> None:
        def encrypt(_value: str) -> str:
            return _CIPHERTEXT

        def decrypt(_value: str) -> DPAPIDecryptionResult:
            return DPAPIDecryptionResult("{}", needs_migration=False)

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
            root = PluginConfig()
            await root.activate()
            first = root.PluginInstances.add(PluginInstance)
            second = root.PluginInstances.add(
                PluginInstance,
                wire={
                    "Info": {
                        "Plugin": "background",
                        "Id": "second",
                        "Name": "背景插件",
                    },
                    "Data": {"ConfigRaw": "{}"},
                },
            )
            await root.PluginInstances.commit()

            self.assertEqual(list(root.PluginInstances.keys()), [first, second])
            self.assertEqual(
                root.PluginInstances[first].Info.Plugin,
                "unknown_plugin",
            )
            self.assertRegex(
                root.PluginInstances[first].Info.Id,
                r"^[a-zA-Z0-9_-]{1,64}$",
            )
            self.assertEqual(
                root.PluginInstances[second].Info.Plugin,
                "background",
            )

            root.PluginInstances[first].Info.Name = "第一个实例"
            await root.PluginInstances[first].commit()
            root.PluginInstances.set_order([second, first])
            await root.PluginInstances.commit()
            self.assertEqual(list(root.PluginInstances.keys()), [second, first])

            root.PluginInstances.remove(second)
            await root.PluginInstances.commit()
            self.assertEqual(list(root.PluginInstances.keys()), [first])

    async def test_encryption_virtual_projection_and_persistence_boundary(
        self,
    ) -> None:
        plaintext = '{"token": "must-not-leak"}'
        schema_manager = MagicMock()
        schema_manager.load_schema.return_value = {"token": {"type": "string"}}
        schema_manager.apply_defaults_and_validate.return_value = {
            "token": "validated"
        }

        def encrypt(value: str) -> str:
            self.assertIn(value, {"{ }", plaintext})
            return _CIPHERTEXT

        def decrypt(value: str) -> DPAPIDecryptionResult:
            self.assertEqual(value, _CIPHERTEXT)
            return DPAPIDecryptionResult(plaintext, needs_migration=False)

        with (
            patch(
                "app.configuration.v2.encrypted.dpapi_encrypt",
                side_effect=encrypt,
            ),
            patch(
                "app.configuration.v2.encrypted.dpapi_decrypt_with_status",
                side_effect=decrypt,
            ),
            patch(
                "app.plugins.schema.PluginSchemaManager",
                return_value=schema_manager,
            ),
        ):
            root = PluginConfig()
            await root.activate()
            uid = root.PluginInstances.add(
                PluginInstance,
                wire={
                    "Info": {"Plugin": "demo", "Id": "one"},
                    "Data": {"ConfigRaw": plaintext},
                },
            )
            await root.PluginInstances.commit()

            self.assertEqual(
                json.loads(root.PluginInstances[uid].Data.Config),
                {"token": "validated"},
            )
            persisted = await root.to_dict(if_decrypt=False)
            transport = await root.to_dict(
                if_decrypt=True,
                include_reactive=True,
            )

        persisted_data = persisted["PluginInstances"]["data"][str(uid)]["Data"]
        transport_data = transport["PluginInstances"]["data"][str(uid)]["Data"]
        self.assertNotIn(plaintext, repr(persisted))
        self.assertEqual(persisted_data["ConfigRaw"], _CIPHERTEXT)
        self.assertNotIn("Config", persisted_data)
        self.assertEqual(transport_data["ConfigRaw"], plaintext)
        self.assertEqual(
            json.loads(transport_data["Config"]),
            {"token": "validated"},
        )

    async def test_runtime_regex_types_and_version_bounds_are_strict(self) -> None:
        with (
            patch(
                "app.configuration.v2.encrypted.dpapi_encrypt",
                return_value=_CIPHERTEXT,
            ),
            patch(
                "app.configuration.v2.encrypted.dpapi_decrypt_with_status",
                return_value=DPAPIDecryptionResult("{}", False),
            ),
        ):
            root = PluginConfig()
            await root.activate()
            uid = root.PluginInstances.add(PluginInstance)
            await root.PluginInstances.commit()

            root.Data.Version = True  # type: ignore[assignment]
            with self.assertRaises(ConfigAggregateError):
                await root.commit()
            self.assertEqual(root.Data.Version, 1)

            root.PluginInstances[uid].Info.Plugin = "bad/plugin"
            with self.assertRaises(ConfigAggregateError):
                await root.PluginInstances[uid].commit()
            self.assertEqual(
                root.PluginInstances[uid].Info.Plugin,
                "unknown_plugin",
            )

            root.PluginInstances[uid].Info.Id = "x" * 65
            with self.assertRaises(ConfigAggregateError):
                await root.PluginInstances[uid].commit()
            self.assertTrue(
                re.fullmatch(
                    r"[a-zA-Z0-9_-]{1,64}",
                    root.PluginInstances[uid].Info.Id,
                )
            )

    async def test_unknown_virtual_or_member_field_fails_activation_atomically(
        self,
    ) -> None:
        uid = uuid4()
        root = PluginConfig(
            wire={
                "Data": {"Version": 1},
                "PluginInstances": {
                    "order": [{"uid": str(uid), "type": "PluginInstance"}],
                    "data": {
                        str(uid): {
                            "Info": {
                                "Plugin": "demo",
                                "Id": "one",
                                "Unknown": True,
                            },
                            "Data": {
                                "ConfigRaw": _CIPHERTEXT,
                                "Config": "{}",
                            },
                        }
                    },
                },
            }
        )

        with self.assertRaises(ConfigAggregateError):
            await root.activate()
        self.assertEqual(list(root.PluginInstances.keys()), [])


class PluginConfigLegacyConversionTest(unittest.TestCase):
    def test_round_trip_preserves_order_uuid_type_version_and_ciphertext(
        self,
    ) -> None:
        first = uuid4()
        second = uuid4()
        legacy = {
            "Data": {"Version": 7},
            "SubConfigsInfo": {
                "PluginInstances": {
                    "instances": [
                        {
                            "uid": str(second),
                            "type": "PluginInstanceConfig",
                        },
                        {
                            "uid": str(first),
                            "type": "PluginInstanceConfig",
                        },
                    ],
                    str(first): _legacy_plugin_config(first)[
                        "SubConfigsInfo"
                    ]["PluginInstances"][str(first)],
                    str(second): _legacy_plugin_config(
                        second,
                        plugin="other-plugin",
                        instance_id="two",
                    )["SubConfigsInfo"]["PluginInstances"][str(second)],
                }
            },
        }
        before = copy.deepcopy(legacy)

        wire = legacy_plugin_config_to_wire(legacy)
        restored = plugin_config_wire_to_legacy(wire)

        self.assertEqual(legacy, before)
        self.assertEqual(restored, legacy)
        self.assertEqual(wire["Data"]["Version"], 7)
        self.assertEqual(
            [item["uid"] for item in wire["PluginInstances"]["order"]],
            [str(second), str(first)],
        )
        self.assertTrue(
            all(
                item["type"] == "PluginInstance"
                for item in wire["PluginInstances"]["order"]
            )
        )
        self.assertEqual(
            restored["SubConfigsInfo"]["PluginInstances"][str(first)]["Data"][
                "ConfigRaw"
            ],
            _CIPHERTEXT,
        )

    def test_historical_config_alias_is_promoted_without_virtual_persistence(
        self,
    ) -> None:
        uid = uuid4()
        legacy = _legacy_plugin_config(uid)
        data = legacy["SubConfigsInfo"]["PluginInstances"][str(uid)]["Data"]
        data.pop("ConfigRaw")
        data["Config"] = _CIPHERTEXT

        wire = legacy_plugin_config_to_wire(legacy)
        instance_data = wire["PluginInstances"]["data"][str(uid)]["Data"]
        self.assertEqual(instance_data, {"ConfigRaw": _CIPHERTEXT})

        restored = plugin_config_wire_to_legacy(wire)
        rollback_data = restored["SubConfigsInfo"]["PluginInstances"][str(uid)][
            "Data"
        ]
        self.assertEqual(rollback_data, {"ConfigRaw": _CIPHERTEXT})
        self.assertNotIn("Config", rollback_data)

    def test_equivalent_dual_plaintext_aliases_are_not_a_conflict(self) -> None:
        uid = uuid4()
        legacy = _legacy_plugin_config(uid, config_raw='{"value": 1}')
        data = legacy["SubConfigsInfo"]["PluginInstances"][str(uid)]["Data"]
        data["Config"] = '{ "value": 1 }'

        wire = legacy_plugin_config_to_wire(legacy)

        self.assertEqual(
            wire["PluginInstances"]["data"][str(uid)]["Data"]["ConfigRaw"],
            '{"value": 1}',
        )

    def test_conflicting_dual_fields_fail_closed_without_value_leak(self) -> None:
        uid = uuid4()
        first = '{"first": "secret-one"}'
        second = '{"second": "secret-two"}'
        legacy = _legacy_plugin_config(uid, config_raw=first)
        legacy["SubConfigsInfo"]["PluginInstances"][str(uid)]["Data"][
            "Config"
        ] = second

        with self.assertRaisesRegex(ValueError, "冲突") as raised:
            legacy_plugin_config_to_wire(legacy)
        rendered = f"{raised.exception!s} {raised.exception!r}"
        self.assertNotIn("secret-one", rendered)
        self.assertNotIn("secret-two", rendered)

    def test_unknown_or_orphan_fields_fail_closed(self) -> None:
        uid = uuid4()
        orphan = uuid4()
        legacy = _legacy_plugin_config(uid)
        legacy["SubConfigsInfo"]["PluginInstances"][str(orphan)] = {
            "Info": {},
            "Data": {},
        }
        with self.assertRaisesRegex(ValueError, "缺失或孤儿"):
            legacy_plugin_config_to_wire(legacy)

        legacy = _legacy_plugin_config(uid)
        legacy["SubConfigsInfo"]["PluginInstances"][str(uid)]["Info"][
            "Unknown"
        ] = True
        with self.assertRaisesRegex(ValueError, "Unknown"):
            legacy_plugin_config_to_wire(legacy)

        legacy = _legacy_plugin_config(uid)
        legacy["Future"] = {}
        with self.assertRaisesRegex(ValueError, "Future"):
            legacy_plugin_config_to_wire(legacy)

    def test_duplicate_invalid_uid_type_and_bad_types_fail_closed(self) -> None:
        uid = uuid4()
        duplicate = _legacy_plugin_config(uid)
        duplicate["SubConfigsInfo"]["PluginInstances"]["instances"].append(
            {"uid": str(uid), "type": "PluginInstanceConfig"}
        )
        with self.assertRaisesRegex(ValueError, "重复 uid"):
            legacy_plugin_config_to_wire(duplicate)

        invalid_uid = _legacy_plugin_config(uid)
        collection = invalid_uid["SubConfigsInfo"]["PluginInstances"]
        collection["instances"][0]["uid"] = "not-a-uuid"
        collection["not-a-uuid"] = collection.pop(str(uid))
        with self.assertRaisesRegex(ValueError, "有效 UUID"):
            legacy_plugin_config_to_wire(invalid_uid)

        invalid_type = _legacy_plugin_config(uid)
        invalid_type["SubConfigsInfo"]["PluginInstances"]["instances"][0][
            "type"
        ] = "Other"
        with self.assertRaisesRegex(ValueError, "仅允许 PluginInstanceConfig"):
            legacy_plugin_config_to_wire(invalid_type)

        bad_version = _legacy_plugin_config(uid)
        bad_version["Data"]["Version"] = True
        with self.assertRaisesRegex(ValueError, "1..9999"):
            legacy_plugin_config_to_wire(bad_version)

        bad_enabled = _legacy_plugin_config(uid)
        bad_enabled["SubConfigsInfo"]["PluginInstances"][str(uid)]["Info"][
            "Enabled"
        ] = 1
        with self.assertRaisesRegex(TypeError, "布尔值"):
            legacy_plugin_config_to_wire(bad_enabled)

    def test_invalid_json_and_plugin_identifiers_fail_closed(self) -> None:
        uid = uuid4()
        invalid_json = _legacy_plugin_config(uid, config_raw="not-json")
        with self.assertRaisesRegex(ValueError, "JSON 字典"):
            legacy_plugin_config_to_wire(invalid_json)

        json_list = _legacy_plugin_config(uid, config_raw="[]")
        with self.assertRaisesRegex(ValueError, "JSON 字典"):
            legacy_plugin_config_to_wire(json_list)

        invalid_plugin = _legacy_plugin_config(uid, plugin="bad/plugin")
        with self.assertRaisesRegex(ValueError, "插件名称"):
            legacy_plugin_config_to_wire(invalid_plugin)

        invalid_id = _legacy_plugin_config(uid, instance_id="x" * 65)
        with self.assertRaisesRegex(ValueError, "实例号"):
            legacy_plugin_config_to_wire(invalid_id)

    def test_missing_known_fields_use_compatible_defaults(self) -> None:
        uid = uuid4()
        legacy = {
            "SubConfigsInfo": {
                "PluginInstances": {
                    "instances": [
                        {"uid": str(uid), "type": "PluginInstanceConfig"}
                    ],
                    str(uid): {},
                }
            }
        }

        wire = legacy_plugin_config_to_wire(legacy)
        instance = wire["PluginInstances"]["data"][str(uid)]

        self.assertEqual(wire["Data"]["Version"], 1)
        self.assertEqual(instance["Info"]["Plugin"], "unknown_plugin")
        self.assertEqual(instance["Info"]["Id"], uid.hex[:5])
        self.assertIs(instance["Info"]["Enabled"], True)
        self.assertEqual(instance["Info"]["Name"], "插件实例")
        self.assertEqual(instance["Data"]["ConfigRaw"], "{ }")

    def test_rollback_rejects_plaintext_and_virtual_config_without_leak(
        self,
    ) -> None:
        uid = uuid4()
        plaintext = '{"token": "must-not-leak"}'
        wire = legacy_plugin_config_to_wire(
            _legacy_plugin_config(uid, config_raw=plaintext)
        )

        with self.assertRaises(ValueError) as raised:
            plugin_config_wire_to_legacy(wire)
        rendered = f"{raised.exception!s} {raised.exception!r}"
        self.assertNotIn("must-not-leak", rendered)

        wire["PluginInstances"]["data"][str(uid)]["Data"] = {
            "ConfigRaw": _CIPHERTEXT,
            "Config": "{}",
        }
        with self.assertRaisesRegex(ValueError, "Config"):
            plugin_config_wire_to_legacy(wire)

    def test_v2_orphan_duplicate_and_wrong_type_fail_closed(self) -> None:
        uid = uuid4()
        orphan = uuid4()
        valid_entry = {
            "Info": {
                "Plugin": "demo",
                "Id": "one",
                "Enabled": True,
                "Name": "实例",
            },
            "Data": {"ConfigRaw": _CIPHERTEXT},
        }
        with self.assertRaisesRegex(ValueError, "缺失或孤儿"):
            plugin_config_wire_to_legacy(
                {
                    "Data": {"Version": 1},
                    "PluginInstances": {
                        "order": [
                            {"uid": str(uid), "type": "PluginInstance"}
                        ],
                        "data": {
                            str(uid): valid_entry,
                            str(orphan): valid_entry,
                        },
                    },
                }
            )

        with self.assertRaisesRegex(ValueError, "重复 uid"):
            plugin_config_wire_to_legacy(
                {
                    "Data": {"Version": 1},
                    "PluginInstances": {
                        "order": [
                            {"uid": str(uid), "type": "PluginInstance"},
                            {"uid": str(uid), "type": "PluginInstance"},
                        ],
                        "data": {str(uid): valid_entry},
                    },
                }
            )

        with self.assertRaisesRegex(ValueError, "仅允许 PluginInstance"):
            plugin_config_wire_to_legacy(
                {
                    "Data": {"Version": 1},
                    "PluginInstances": {
                        "order": [{"uid": str(uid), "type": "Other"}],
                        "data": {str(uid): valid_entry},
                    },
                }
            )

    def test_empty_roots_have_exact_shapes(self) -> None:
        self.assertEqual(
            legacy_plugin_config_to_wire({}),
            {
                "Data": {"Version": 1},
                "PluginInstances": {"order": [], "data": {}},
            },
        )
        self.assertEqual(
            plugin_config_wire_to_legacy(
                {
                    "Data": {"Version": 1},
                    "PluginInstances": {"order": [], "data": {}},
                }
            ),
            {
                "Data": {"Version": 1},
                "SubConfigsInfo": {
                    "PluginInstances": {"instances": []}
                },
            },
        )
