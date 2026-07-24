"""ScriptConfig 原生 Config v2 多态根与 r6 兼容边界测试。"""

from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from app.configuration import (
    ConfigAggregateError,
    ConfigCollection,
    ConfigEntry,
    config_manager,
)
from app.configuration.roots.script import (
    EMULATOR_COLLECTION_NAME,
    GeneralScript,
    GeneralUser,
    M9AScript,
    M9AUser,
    MaaEndScript,
    MaaEndUser,
    MaaFWScript,
    MaaFWUser,
    MaaScript,
    MaaUser,
    NATIVE_SCRIPT_TYPES,
    NATIVE_USER_TYPES,
    OkwwScript,
    OkwwUser,
    PLAN_COLLECTION_NAME,
    PluginScript,
    Scripts,
    SrcScript,
    SrcUser,
    legacy_scripts_to_wire,
    scripts_wire_to_legacy,
)
from app.configuration.v2.support.security import DPAPIDecryptionResult
from app.models.ConfigBase import VirtualConfigValidator
from app.models.config import (
    GeneralUserConfig as LegacyGeneralUser,
    M9AUserConfig as LegacyM9AUser,
    MaaEndUserConfig as LegacyMaaEndUser,
    MaaFWUserConfig as LegacyMaaFWUser,
    MaaUserConfig as LegacyMaaUser,
    OkwwUserConfig as LegacyOkwwUser,
    SrcUserConfig as LegacySrcUser,
)

_CIPHERTEXT = "DPAPI:v1:Y2lwaGVydGV4dA=="


class _EmulatorTarget(ConfigEntry):
    pass


class _PlanTarget(ConfigEntry):
    pass


def _legacy_root(
    uid: UUID,
    *,
    type_name: str = "MaaConfig",
    entry: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "instances": [{"uid": str(uid), "type": type_name}],
        str(uid): entry or {},
    }


def _user_collection(
    uid: UUID,
    *,
    type_name: str,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "instances": [{"uid": str(uid), "type": type_name}],
        str(uid): payload or {},
    }


class ScriptNativeRootTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.emulators = ConfigCollection(
            _EmulatorTarget,
            name=EMULATOR_COLLECTION_NAME,
        )
        await self.emulators.activate()
        self.plans = ConfigCollection(
            _PlanTarget,
            name=PLAN_COLLECTION_NAME,
        )
        await self.plans.activate()

    async def asyncTearDown(self) -> None:
        config_manager.unregister_collection(EMULATOR_COLLECTION_NAME)
        config_manager.unregister_collection(PLAN_COLLECTION_NAME)

    async def test_all_builtin_script_types_activate_with_exact_defaults(
        self,
    ) -> None:
        root = Scripts()
        await root.activate()
        classes = (
            MaaScript,
            MaaEndScript,
            SrcScript,
            M9AScript,
            MaaFWScript,
            GeneralScript,
            OkwwScript,
        )
        uids = [root.add(entry_type) for entry_type in classes]
        await root.commit()

        self.assertEqual(len(root), 7)
        self.assertEqual(
            [type(root[uid]).__name__ for uid in uids],
            [entry_type.__name__ for entry_type in classes],
        )
        self.assertEqual(root[uids[0]].Info.Name, "新 MAA 脚本")
        self.assertEqual(root[uids[1]].Game.WaitTime, 60)
        self.assertEqual(root[uids[2]].Run.TaskTransitionMethod, "ExitGame")
        self.assertEqual(root[uids[3]].Run.RunTimesLimit, 3)
        self.assertEqual(root[uids[4]].Device.AdbScreencapMethods, -57)
        self.assertEqual(root[uids[5]].Script.ConfigPathMode, "File")
        self.assertEqual(root[uids[6]].Run.RunTimeLimit, 60)

    async def test_crud_update_order_and_strict_runtime_validation(self) -> None:
        root = Scripts()
        await root.activate()
        first = root.add(MaaScript)
        second = root.add(
            GeneralScript,
            wire={
                "Info": {"Name": "通用脚本"},
                "Run": {"RunTimesLimit": 5},
            },
        )
        await root.commit()

        root[first].Info.Name = "MAA 一号"
        await root[first].commit()
        self.assertEqual(root[first].Info.Name, "MAA 一号")

        root[first].Run.RunTimesLimit = 0
        with self.assertRaises(ConfigAggregateError):
            await root[first].commit()
        self.assertEqual(root[first].Run.RunTimesLimit, 3)

        root[second].Game.Enabled = 1  # type: ignore[assignment]
        with self.assertRaises(ConfigAggregateError):
            await root[second].commit()
        self.assertIs(root[second].Game.Enabled, False)

        root.set_order([second, first])
        await root.commit()
        self.assertEqual(list(root.keys()), [second, first])

        root.remove(second)
        await root.commit()
        self.assertEqual(list(root.keys()), [first])

    async def test_all_builtin_users_are_native_typed_and_have_virtuals(
        self,
    ) -> None:
        root = Scripts()
        await root.activate()
        pairs = (
            (MaaScript, MaaUser),
            (MaaEndScript, MaaEndUser),
            (SrcScript, SrcUser),
            (M9AScript, M9AUser),
            (MaaFWScript, MaaFWUser),
            (GeneralScript, GeneralUser),
            (OkwwScript, OkwwUser),
        )
        script_uids = [root.add(script_type) for script_type, _ in pairs]
        await root.commit()
        user_uids = []
        for script_uid, (_, user_type) in zip(script_uids, pairs, strict=True):
            user_uid = root[script_uid].UserData.add(user_type)
            await root[script_uid].UserData.commit()
            user_uids.append(user_uid)
            user = root[script_uid].UserData[user_uid]
            self.assertEqual(user.Info.Name, "新用户")
            self.assertIsInstance(json.loads(user.Info.Tag), list)
        persisted = await root.to_dict(if_decrypt=False)
        for script_uid, user_uid in zip(
            script_uids, user_uids, strict=True
        ):
            stored = persisted["data"][str(script_uid)]["UserData"]["data"][
                str(user_uid)
            ]
            self.assertNotIn("Compat", stored)
            self.assertNotIn("Tag", stored["Info"])

    async def test_native_user_encrypts_secret_without_leaking_plaintext(
        self,
    ) -> None:
        secret = "must-not-leak"

        def encrypt(_value: str) -> str:
            return _CIPHERTEXT

        def decrypt(_value: str) -> DPAPIDecryptionResult:
            return DPAPIDecryptionResult(secret, needs_migration=False)

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
            root = Scripts()
            await root.activate()
            script_uid = root.add(MaaScript)
            await root.commit()
            user_uid = root[script_uid].UserData.add(
                MaaUser,
                wire={"Info": {"Name": "博士", "Password": secret}},
            )
            await root[script_uid].UserData.commit()
            persisted = await root.to_dict(if_decrypt=False)
            transport = await root.to_dict(if_decrypt=True)

        stored = persisted["data"][str(script_uid)]["UserData"]["data"][
            str(user_uid)
        ]
        shown = transport["data"][str(script_uid)]["UserData"]["data"][
            str(user_uid)
        ]
        self.assertEqual(stored["Info"]["Password"], _CIPHERTEXT)
        self.assertNotIn(secret, json.dumps(stored, ensure_ascii=False))
        self.assertEqual(shown["Info"]["Password"], secret)

    async def test_plugin_container_encrypts_script_and_user_config(
        self,
    ) -> None:
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
            root = Scripts()
            await root.activate()
            script_uid = root.add(
                PluginScript,
                wire={
                    "Meta": {"PluginTypeKey": "demo"},
                    "Info": {"Name": "插件脚本"},
                    "PluginData": {"Config": '{"token":"logical"}'},
                },
            )
            await root.commit()
            user_uid = root[script_uid].UserData.add(
                "PluginUser",
                wire={
                    "Meta": {"PluginTypeKey": "demo"},
                    "Info": {"Name": "插件用户"},
                    "PluginData": {"Config": '{"enabled":true}'},
                },
            )
            await root[script_uid].UserData.commit()

            persisted = await root.to_dict(if_decrypt=False)
            transport = await root.to_dict(if_decrypt=True)

        persisted_script = persisted["data"][str(script_uid)]
        persisted_user = persisted_script["UserData"]["data"][str(user_uid)]
        self.assertEqual(
            persisted_script["PluginData"]["Config"],
            _CIPHERTEXT,
        )
        self.assertEqual(
            persisted_user["PluginData"]["Config"],
            _CIPHERTEXT,
        )
        self.assertEqual(
            json.loads(
                transport["data"][str(script_uid)]["PluginData"]["Config"]
            ),
            {},
        )

    async def test_unknown_native_field_fails_activation_atomically(self) -> None:
        uid = uuid4()
        root = Scripts(
            wire={
                "order": [{"uid": str(uid), "type": "MaaScript"}],
                "data": {
                    str(uid): {
                        "Info": {
                            "Name": "测试",
                            "Unknown": "must-fail",
                        }
                    }
                },
            }
        )

        with self.assertRaises(ConfigAggregateError):
            await root.activate()
        self.assertEqual(list(root.keys()), [])


class ScriptLegacyConversionTest(unittest.TestCase):
    def test_builtin_round_trip_preserves_order_uuid_and_typed_user(
        self,
    ) -> None:
        first = uuid4()
        second = uuid4()
        user = uuid4()
        legacy = {
            "instances": [
                {"uid": str(second), "type": "GeneralConfig"},
                {"uid": str(first), "type": "MaaConfig"},
            ],
            str(first): {
                "Info": {"Name": "MAA 测试"},
                "Run": {"RunTimesLimit": 8},
                "SubConfigsInfo": {
                    "UserData": _user_collection(
                        user,
                        type_name="MaaUserConfig",
                        payload={
                            "Info": {
                                "Name": "用户 A",
                                "Password": _CIPHERTEXT,
                            },
                            "Data": {
                                "CustomInfrast": '{"title":"A"}'
                            },
                            "SubConfigsInfo": {
                                "Notify_CustomWebhooks": {}
                            },
                        },
                    )
                },
            },
            str(second): {
                "Info": {"Name": "通用测试"},
                "Script": {"ConfigPathMode": "Folder"},
            },
        }
        before = copy.deepcopy(legacy)

        wire = legacy_scripts_to_wire(legacy)
        restored = scripts_wire_to_legacy(wire)

        self.assertEqual(legacy, before)
        self.assertEqual(
            [item["uid"] for item in wire["order"]],
            [str(second), str(first)],
        )
        self.assertEqual(
            [item["type"] for item in wire["order"]],
            ["GeneralScript", "MaaScript"],
        )
        maa = restored[str(first)]
        self.assertEqual(maa["Info"]["Name"], "MAA 测试")
        self.assertEqual(maa["Run"]["RunTimesLimit"], 8)
        restored_user = maa["SubConfigsInfo"]["UserData"][str(user)]
        self.assertEqual(
            restored_user["Info"]["Password"],
            _CIPHERTEXT,
        )
        self.assertEqual(
            restored_user["Data"]["CustomInfrast"],
            '{"title":"A"}',
        )
        self.assertIn(
            "Notify_CustomWebhooks",
            restored_user["SubConfigsInfo"],
        )

    def test_all_builtin_missing_fields_get_exact_outer_defaults(self) -> None:
        cases = (
            ("MaaConfig", "MaaScript", "新 MAA 脚本"),
            ("MaaEndConfig", "MaaEndScript", "新 MaaEnd 脚本"),
            ("SrcConfig", "SrcScript", "新 SRC 脚本"),
            ("M9AConfig", "M9AScript", "新 M9A 脚本"),
            ("MaaFWConfig", "MaaFWScript", "新 MaaFW 脚本"),
            ("GeneralConfig", "GeneralScript", "新通用脚本"),
            ("OkwwConfig", "OkwwScript", "鸣潮"),
        )
        for legacy_type, v2_type, default_name in cases:
            with self.subTest(type=legacy_type):
                uid = uuid4()
                wire = legacy_scripts_to_wire(
                    _legacy_root(uid, type_name=legacy_type)
                )
                self.assertEqual(wire["order"][0]["type"], v2_type)
                entry = wire["data"][str(uid)]
                self.assertEqual(entry["Info"]["Name"], default_name)
                self.assertEqual(
                    entry["UserData"],
                    {"order": [], "data": {}},
                )
                restored = scripts_wire_to_legacy(wire)
                self.assertEqual(
                    restored["instances"][0]["type"],
                    legacy_type,
                )

    def test_plugin_script_and_user_round_trip_keep_ciphertext(self) -> None:
        script_uid = uuid4()
        user_uid = uuid4()
        legacy = _legacy_root(
            script_uid,
            type_name="PluginScriptConfig",
            entry={
                "Meta": {"PluginTypeKey": "demo"},
                "Info": {"Name": "插件脚本"},
                "PluginData": {"Config": _CIPHERTEXT},
                "SubConfigsInfo": {
                    "UserData": _user_collection(
                        user_uid,
                        type_name="PluginUserConfig",
                        payload={
                            "Meta": {"PluginTypeKey": "demo"},
                            "Info": {"Name": "插件用户"},
                            "PluginData": {"Config": _CIPHERTEXT},
                        },
                    )
                },
            },
        )

        wire = legacy_scripts_to_wire(legacy)
        restored = scripts_wire_to_legacy(wire)

        self.assertEqual(restored, legacy)
        self.assertEqual(wire["order"][0]["type"], "PluginScript")
        user_wire = wire["data"][str(script_uid)]["UserData"]
        self.assertEqual(user_wire["order"][0]["type"], "PluginUser")

    def test_dynamic_class_without_plugin_container_fails_closed(self) -> None:
        uid = uuid4()
        with self.assertRaisesRegex(ValueError, "尚无原生类型"):
            legacy_scripts_to_wire(
                _legacy_root(
                    uid,
                    type_name="ThirdPartyDynamicConfig",
                    entry={
                        "Meta": {"PluginTypeKey": "third_party"},
                        "PluginData": {"Config": _CIPHERTEXT},
                    },
                )
            )

    def test_outer_unknown_alias_and_bad_values_fail_closed(self) -> None:
        uid = uuid4()
        payload = _legacy_root(
            uid,
            entry={
                "Info": {"Name": "MAA", "AliasName": "other"},
            },
        )
        with self.assertRaisesRegex(ValueError, "AliasName"):
            legacy_scripts_to_wire(payload)

        payload = _legacy_root(
            uid,
            entry={"Run": {"RunTimesLimit": True}},
        )
        with self.assertRaisesRegex(TypeError, "必须是整数"):
            legacy_scripts_to_wire(payload)

        payload = _legacy_root(
            uid,
            entry={"Run": {"RunTimesLimit": 10000}},
        )
        with self.assertRaisesRegex(ValueError, "1..9999"):
            legacy_scripts_to_wire(payload)

        payload = _legacy_root(
            uid,
            entry={
                "SubConfigsInfo": {"UserData": {}},
                "UserData": {},
            },
        )
        with self.assertRaisesRegex(ValueError, "别名冲突"):
            legacy_scripts_to_wire(payload)

    def test_duplicate_orphan_missing_and_wrong_nested_type_fail_closed(
        self,
    ) -> None:
        uid = uuid4()
        duplicate = _legacy_root(uid)
        duplicate["instances"].append(
            {"uid": str(uid), "type": "MaaConfig"}
        )
        with self.assertRaisesRegex(ValueError, "重复 uid"):
            legacy_scripts_to_wire(duplicate)

        orphan = _legacy_root(uid)
        orphan[str(uuid4())] = {}
        with self.assertRaisesRegex(ValueError, "孤儿或未知"):
            legacy_scripts_to_wire(orphan)

        missing = {
            "instances": [{"uid": str(uid), "type": "MaaConfig"}]
        }
        with self.assertRaisesRegex(ValueError, "缺失"):
            legacy_scripts_to_wire(missing)

        user_uid = uuid4()
        wrong_nested = _legacy_root(
            uid,
            entry={
                "SubConfigsInfo": {
                    "UserData": _user_collection(
                        user_uid,
                        type_name="GeneralUserConfig",
                    )
                }
            },
        )
        with self.assertRaisesRegex(ValueError, "仅允许 MaaUserConfig"):
            legacy_scripts_to_wire(wrong_nested)

    def test_plaintext_secret_cannot_cross_legacy_or_rollback_boundary(
        self,
    ) -> None:
        uid = uuid4()
        user_uid = uuid4()
        secret = "must-not-leak"
        legacy = _legacy_root(
            uid,
            entry={
                "SubConfigsInfo": {
                    "UserData": _user_collection(
                        user_uid,
                        type_name="MaaUserConfig",
                        payload={"Info": {"Password": secret}},
                    )
                }
            },
        )
        with self.assertRaises(ValueError) as raised:
            legacy_scripts_to_wire(legacy)
        rendered = f"{raised.exception!s} {raised.exception!r}"
        self.assertNotIn(secret, rendered)

        plugin = _legacy_root(
            uid,
            type_name="PluginScriptConfig",
            entry={"PluginData": {"Config": "{}"}},
        )
        with self.assertRaises(ValueError) as raised:
            legacy_scripts_to_wire(plugin)
        rendered = f"{raised.exception!s} {raised.exception!r}"
        self.assertNotIn("{}", rendered)

    def test_v2_duplicate_orphan_wrong_type_and_unknown_path_fail_closed(
        self,
    ) -> None:
        uid = uuid4()
        valid_entry = legacy_scripts_to_wire(_legacy_root(uid))["data"][
            str(uid)
        ]
        with self.assertRaisesRegex(ValueError, "重复 uid"):
            scripts_wire_to_legacy(
                {
                    "order": [
                        {"uid": str(uid), "type": "MaaScript"},
                        {"uid": str(uid), "type": "MaaScript"},
                    ],
                    "data": {str(uid): valid_entry},
                }
            )

        with self.assertRaisesRegex(ValueError, "缺失或孤儿"):
            scripts_wire_to_legacy(
                {
                    "order": [],
                    "data": {str(uid): valid_entry},
                }
            )

        with self.assertRaisesRegex(ValueError, "原生类型"):
            scripts_wire_to_legacy(
                {
                    "order": [
                        {"uid": str(uid), "type": "MaaConfig"}
                    ],
                    "data": {str(uid): valid_entry},
                }
            )

        with self.assertRaisesRegex(ValueError, "unknown"):
            scripts_wire_to_legacy(
                {
                    "order": [],
                    "data": {},
                    "unknown": True,
                }
            )

    def test_native_type_matrix_is_explicit_and_has_no_opaque_type(
        self,
    ) -> None:
        self.assertEqual(len(NATIVE_SCRIPT_TYPES), 8)
        self.assertEqual(len(NATIVE_USER_TYPES), 7)
        self.assertIn("PluginScriptConfig", NATIVE_SCRIPT_TYPES)
        self.assertIn("MaaUserConfig", NATIVE_USER_TYPES)
        self.assertFalse(any("Opaque" in name for name in NATIVE_USER_TYPES))

    def test_native_user_field_and_default_matrix_matches_legacy(self) -> None:
        pairs = (
            (LegacyMaaUser, MaaUser),
            (LegacyMaaEndUser, MaaEndUser),
            (LegacySrcUser, SrcUser),
            (LegacyM9AUser, M9AUser),
            (LegacyMaaFWUser, MaaFWUser),
            (LegacyGeneralUser, GeneralUser),
            (LegacyOkwwUser, OkwwUser),
        )
        for legacy_type, native_type in pairs:
            with self.subTest(type=legacy_type.__name__):
                legacy = legacy_type()
                old_fields = {
                    (group_name, field_name): item
                    for group_name, fields in legacy._config_item_index.items()
                    for field_name, item in fields.items()
                    if not isinstance(
                        item.validator,
                        VirtualConfigValidator,
                    )
                }
                virtual = set(native_type._cfg_virtual_specs)
                new_fields = {
                    (group_name, field_name): field_info
                    for group_name in native_type._cfg_group_fields
                    for field_name, field_info in (
                        native_type.model_fields[
                            group_name
                        ].annotation.model_fields.items()
                    )
                    if (group_name, field_name) not in virtual
                }
                self.assertEqual(
                    set(new_fields),
                    set(old_fields),
                )
                for path, item in old_fields.items():
                    self.assertEqual(
                        new_fields[path].default,
                        item.getValue(),
                        path,
                    )

    def test_empty_roots_have_exact_shapes(self) -> None:
        self.assertEqual(
            legacy_scripts_to_wire({}),
            {"order": [], "data": {}},
        )
        self.assertEqual(
            scripts_wire_to_legacy({}),
            {"instances": []},
        )
