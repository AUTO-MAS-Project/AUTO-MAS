"""Config v2 八个生产根注册、转换和全体激活测试。"""

from __future__ import annotations

import unittest
from uuid import uuid4

from app.configuration import config_manager
from app.configuration.production import (
    EMULATOR_ROOT_NAME,
    PRODUCTION_ROOT_FILES,
    PRODUCTION_ROOT_NAMES,
    PRODUCTION_ROOT_SCHEMA,
    SCRIPT_ROOT_NAME,
    ProductionRootSetError,
    ProductionRoots,
    legacy_production_roots_to_wire,
    production_wire_roots_to_legacy,
)
from app.configuration.roots.emulator import Emulator
from app.configuration.roots.script import (
    EMULATOR_COLLECTION_NAME,
    PLAN_COLLECTION_NAME,
    MaaScript,
    SCRIPT_COLLECTION_NAME,
)
from app.configuration.v2.node_state import NodeState


def _empty_legacy_roots() -> dict[str, object]:
    return {file_name: {} for file_name in PRODUCTION_ROOT_FILES.values()}


class ProductionRootConversionTest(unittest.TestCase):
    def test_registry_is_exact_and_uses_all_frozen_legacy_files(self) -> None:
        self.assertEqual(tuple(PRODUCTION_ROOT_SCHEMA), PRODUCTION_ROOT_NAMES)
        self.assertEqual(tuple(PRODUCTION_ROOT_FILES), PRODUCTION_ROOT_NAMES)
        self.assertEqual(
            set(PRODUCTION_ROOT_FILES.values()),
            set(_empty_legacy_roots()),
        )
        self.assertEqual(len(PRODUCTION_ROOT_NAMES), 8)

    def test_empty_legacy_roots_round_trip_through_exact_wire_set(self) -> None:
        wire = legacy_production_roots_to_wire(_empty_legacy_roots())
        self.assertEqual(tuple(wire), PRODUCTION_ROOT_NAMES)

        restored = production_wire_roots_to_legacy(wire)
        self.assertEqual(set(restored), set(_empty_legacy_roots()))
        self.assertEqual(restored["EmulatorConfig.json"], {"instances": []})
        self.assertEqual(restored["PlanConfig.json"], {"instances": []})
        self.assertEqual(restored["ScriptConfig.json"], {"instances": []})
        self.assertEqual(restored["QueueConfig.json"], {"instances": []})
        self.assertEqual(
            restored["GameSignAccounts.json"],
            {"instances": []},
        )

    def test_missing_extra_or_non_mapping_roots_fail_closed(self) -> None:
        missing = _empty_legacy_roots()
        missing.pop("QueueConfig.json")
        with self.assertRaises(ProductionRootSetError):
            legacy_production_roots_to_wire(missing)

        extra = _empty_legacy_roots()
        extra["Unknown.json"] = {}
        with self.assertRaises(ProductionRootSetError):
            legacy_production_roots_to_wire(extra)

        with self.assertRaises(TypeError):
            legacy_production_roots_to_wire([])  # type: ignore[arg-type]


class ProductionRootsActivationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        config_manager.unregister_collection(SCRIPT_COLLECTION_NAME)
        config_manager.unregister_collection(PLAN_COLLECTION_NAME)
        config_manager.unregister_collection(EMULATOR_COLLECTION_NAME)

    async def test_all_roots_activate_with_registered_cross_root_refs(
        self,
    ) -> None:
        wire = legacy_production_roots_to_wire(_empty_legacy_roots())
        roots = ProductionRoots(wire)
        await roots.activate()

        self.assertEqual(tuple(roots.roots), PRODUCTION_ROOT_NAMES)
        for name, root in roots.roots.items():
            self.assertIs(type(root), PRODUCTION_ROOT_SCHEMA[name])
            self.assertEqual(root.activation_state, NodeState.ACTIVE)
        self.assertIs(
            config_manager.get_collection(EMULATOR_COLLECTION_NAME),
            roots.emulators,
        )
        self.assertIs(
            config_manager.get_collection(PLAN_COLLECTION_NAME),
            roots.plans,
        )
        self.assertIs(
            config_manager.get_collection(SCRIPT_COLLECTION_NAME),
            roots.scripts,
        )

        emulator_uid = roots.emulators.add(Emulator)
        await roots.emulators.commit()
        script_uid = roots.scripts.add(
            MaaScript,
            wire={"Emulator": {"Id": str(emulator_uid)}},
        )
        await roots.scripts.commit()
        self.assertEqual(
            roots.scripts[script_uid].Emulator.Id,
            str(emulator_uid),
        )

        roots.close()
        with self.assertRaises(LookupError):
            config_manager.get_collection(EMULATOR_COLLECTION_NAME)
        with self.assertRaises(LookupError):
            config_manager.get_collection(PLAN_COLLECTION_NAME)
        with self.assertRaises(LookupError):
            config_manager.get_collection(SCRIPT_COLLECTION_NAME)

        await roots.activate()
        self.assertIs(
            config_manager.get_collection(EMULATOR_COLLECTION_NAME),
            roots.emulators,
        )
        self.assertIs(
            config_manager.get_collection(PLAN_COLLECTION_NAME),
            roots.plans,
        )
        self.assertIs(
            config_manager.get_collection(SCRIPT_COLLECTION_NAME),
            roots.scripts,
        )
        roots.close()

    async def test_dispose_releases_ref_subscriptions_and_is_final(self) -> None:
        wire = legacy_production_roots_to_wire(_empty_legacy_roots())
        roots = ProductionRoots(wire)
        await roots.activate()

        target = roots.emulators
        before = tuple(type(target).signal.receivers_for(target))
        emulator_uid = target.add(Emulator)
        await target.commit()
        script_uid = roots.scripts.add(
            MaaScript,
            wire={"Emulator": {"Id": str(emulator_uid)}},
        )
        await roots.scripts.commit()
        script = roots.scripts[script_uid]
        self.assertEqual(len(script._ref_receivers), 1)
        self.assertGreater(
            len(tuple(type(target).signal.receivers_for(target))),
            len(before),
        )

        roots.dispose()

        self.assertEqual(script._ref_receivers, [])
        self.assertEqual(tuple(type(target).signal.receivers_for(target)), before)
        target.remove(emulator_uid)
        await target.commit()
        self.assertEqual(script.Emulator.Id, str(emulator_uid))
        with self.assertRaises(LookupError):
            config_manager.get_collection(EMULATOR_COLLECTION_NAME)
        with self.assertRaises(RuntimeError):
            await roots.activate()

    async def test_removed_entry_does_not_keep_ref_listener(self) -> None:
        roots = ProductionRoots(
            legacy_production_roots_to_wire(_empty_legacy_roots())
        )
        await roots.activate()
        try:
            emulator_uid = roots.emulators.add(Emulator)
            await roots.emulators.commit()
            script_uid = roots.scripts.add(
                MaaScript,
                wire={"Emulator": {"Id": str(emulator_uid)}},
            )
            await roots.scripts.commit()

            roots.scripts.remove(script_uid)
            await roots.scripts.commit()
            self.assertNotIn(script_uid, roots.scripts)

            # 若已删除脚本仍订阅 emulator.remove，这里会尝试提交已删除
            # Entry 的 SET_DEFAULT，进而使目标删除失败。
            roots.emulators.remove(emulator_uid)
            await roots.emulators.commit()
            self.assertNotIn(emulator_uid, roots.emulators)
        finally:
            roots.dispose()

    async def test_nonempty_maa_user_resolves_plan_during_activation(
        self,
    ) -> None:
        plan_uid = uuid4()
        script_uid = uuid4()
        user_uid = uuid4()
        legacy = _empty_legacy_roots()
        legacy["PlanConfig.json"] = {
            "instances": [
                {"uid": str(plan_uid), "type": "MaaPlanConfig"}
            ],
            str(plan_uid): {"Info": {"Name": "引用计划"}},
        }
        legacy["ScriptConfig.json"] = {
            "instances": [
                {"uid": str(script_uid), "type": "MaaConfig"}
            ],
            str(script_uid): {
                "SubConfigsInfo": {
                    "UserData": {
                        "instances": [
                            {
                                "uid": str(user_uid),
                                "type": "MaaUserConfig",
                            }
                        ],
                        str(user_uid): {
                            "Info": {"StageMode": str(plan_uid)}
                        },
                    }
                }
            },
        }

        roots = ProductionRoots(legacy_production_roots_to_wire(legacy))
        await roots.activate()

        self.assertEqual(
            roots.scripts[script_uid].UserData[user_uid].Info.StageMode,
            str(plan_uid),
        )
        self.assertIs(
            config_manager.get_collection(PLAN_COLLECTION_NAME),
            roots.plans,
        )
        roots.close()

    async def test_bad_late_root_rolls_back_every_activation_and_registration(
        self,
    ) -> None:
        wire = dict(legacy_production_roots_to_wire(_empty_legacy_roots()))
        wire["QueueConfig"] = {
            "order": [],
            "data": {},
            "Unknown": "must-fail",
        }
        roots = ProductionRoots(wire)

        with self.assertRaises(Exception):
            await roots.activate()

        self.assertTrue(
            all(
                root.activation_state == NodeState.INACTIVE
                for root in roots.roots.values()
            )
        )
        with self.assertRaises(LookupError):
            config_manager.get_collection(EMULATOR_COLLECTION_NAME)
        with self.assertRaises(LookupError):
            config_manager.get_collection(PLAN_COLLECTION_NAME)
        with self.assertRaises(LookupError):
            config_manager.get_collection(SCRIPT_COLLECTION_NAME)

    async def test_duplicate_reference_owner_fails_without_removing_it(
        self,
    ) -> None:
        external = ProductionRoots(
            legacy_production_roots_to_wire(_empty_legacy_roots())
        )
        config_manager.register_collection(
            EMULATOR_COLLECTION_NAME,
            external.emulators,
        )
        roots = ProductionRoots(
            legacy_production_roots_to_wire(_empty_legacy_roots())
        )

        with self.assertRaises(ValueError):
            await roots.activate()

        self.assertIs(
            config_manager.get_collection(EMULATOR_COLLECTION_NAME),
            external.emulators,
        )
        with self.assertRaises(LookupError):
            config_manager.get_collection(PLAN_COLLECTION_NAME)
        with self.assertRaises(LookupError):
            config_manager.get_collection(SCRIPT_COLLECTION_NAME)

    async def test_constructor_rejects_non_object_wire_without_registration(
        self,
    ) -> None:
        wire = dict(legacy_production_roots_to_wire(_empty_legacy_roots()))
        wire[EMULATOR_ROOT_NAME] = []  # type: ignore[assignment]
        with self.assertRaises(TypeError):
            ProductionRoots(wire)

        with self.assertRaises(LookupError):
            config_manager.get_collection(EMULATOR_COLLECTION_NAME)
        with self.assertRaises(LookupError):
            config_manager.get_collection(PLAN_COLLECTION_NAME)
        with self.assertRaises(LookupError):
            config_manager.get_collection(SCRIPT_COLLECTION_NAME)

    async def test_close_rejects_active_transaction(self) -> None:
        roots = ProductionRoots(
            legacy_production_roots_to_wire(_empty_legacy_roots())
        )
        await roots.activate()
        async with config_manager.transaction():
            with self.assertRaises(RuntimeError):
                roots.close()
        roots.close()

    async def test_wire_mapping_is_defensively_copied(self) -> None:
        wire = dict(legacy_production_roots_to_wire(_empty_legacy_roots()))
        roots = ProductionRoots(wire)
        wire[SCRIPT_ROOT_NAME]["order"].append(
            {"uid": str(uuid4()), "type": "MaaScript"}
        )
        await roots.activate()
        self.assertEqual(len(roots.scripts), 0)


if __name__ == "__main__":
    unittest.main()
