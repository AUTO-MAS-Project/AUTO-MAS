"""Safety regressions for the Config v2 experimental integration."""

from __future__ import annotations

import asyncio
import base64
import gc
import json
import os
import sys
import tempfile
import weakref
from pathlib import Path
from typing import Annotated, Any
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import AfterValidator, Field, TypeAdapter, ValidationError

from app.configuration import (
    ConfigAggregateError,
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    ConfigManager,
    EncryptedValue,
    EncryptedValueError,
    FieldChangeEvent,
    NodeState,
    RefDeleteAction,
    Trigger,
    Virtual,
    config_manager,
    encrypted,
    read_wire_toml,
    ref,
    trigger_field,
    virtual_field,
    write_wire_toml,
)
from app.configuration.compat import LegacyWireAdapter
from app.configuration.runtime import (
    CONFIG_CHANGED,
    configure_outbox_hooks,
    get_current_transaction,
    transaction,
)
from app.configuration.v2.support.security import DPAPI_CONFIG_PREFIX, dpapi_encrypt
from app.core.config_service import _SchemaBoundLegacyCodec, _snapshot_legacy_config
from app.models.config import GlobalConfig
from app.models.ConfigBase import (
    ConfigBase as LegacyConfigBase,
)
from app.models.ConfigBase import (
    ConfigItem as LegacyConfigItem,
)
from app.models.ConfigBase import (
    EncryptedJSONValidator,
    EncryptedValidator,
    StringValidator,
    URLValidator,
    configure_config_save_observer,
)
from app.models.ConfigBase import (
    MultipleConfig as LegacyMultipleConfig,
)
from app.utils.atomic_file import atomic_write_json


class ExampleGroup(ConfigGroup):
    first: int = 1
    second: int = 2


class ExampleEntry(ConfigEntry):
    settings: ExampleGroup = Field(default_factory=ExampleGroup)


class FailingActivationEntry(ExampleEntry):
    async def _activate_from_payload(self, payload: dict[str, Any]) -> None:
        del payload
        raise RuntimeError("activation failed")


class SecretGroup(ConfigGroup):
    token: Annotated[str, encrypted()] = ""


class SecretEntry(ConfigEntry):
    secrets: SecretGroup = Field(default_factory=SecretGroup)


def _validate_secret_prefix(value: str) -> str:
    if value and not value.startswith("ok-"):
        raise ValueError("invalid encrypted value")
    return value


class ValidatedSecretGroup(ConfigGroup):
    token: Annotated[
        str,
        AfterValidator(_validate_secret_prefix),
        encrypted(),
    ] = ""


class ValidatedSecretEntry(ConfigEntry):
    secrets: ValidatedSecretGroup = Field(default_factory=ValidatedSecretGroup)


class TransportGroup(ConfigGroup):
    token: Annotated[str, encrypted()] = ""
    status: Virtual[str] = None
    refresh: Trigger = False


class TransportEntry(ConfigEntry):
    transport: TransportGroup = Field(default_factory=TransportGroup)

    @virtual_field("transport.status")
    def transport_status(self) -> str:
        return "ready"

    @trigger_field("transport.refresh")
    def refresh(self) -> None:
        pass


class NullableGroup(ConfigGroup):
    value: str | None = "fallback"
    items: list[str | None] = Field(default_factory=lambda: ["fallback"])


class NullableEntry(ConfigEntry):
    nullable: NullableGroup = Field(default_factory=NullableGroup)


class MutableGroup(ConfigGroup):
    items: list[int] = Field(default_factory=lambda: [1])
    mapping: dict[str, int] = Field(default_factory=lambda: {"one": 1})


class MutableEntry(ConfigEntry):
    mutable: MutableGroup = Field(default_factory=MutableGroup)


class LegacyExampleConfig(LegacyConfigBase):
    def __init__(self) -> None:
        self.Data_Value = LegacyConfigItem("Data", "Value", "default")
        super().__init__()


class LegacyEncryptedJSONConfig(LegacyConfigBase):
    def __init__(self) -> None:
        self.Data_Config = LegacyConfigItem(
            "Data",
            "Config",
            "{}",
            EncryptedJSONValidator(),
        )
        super().__init__()


class LegacyEncryptedWebhookConfig(LegacyConfigBase):
    def __init__(self) -> None:
        self.Data_Url = LegacyConfigItem(
            "Data",
            "Url",
            "",
            EncryptedValidator(URLValidator()),
        )
        self.Data_Headers = LegacyConfigItem(
            "Data",
            "Headers",
            "{}",
            EncryptedJSONValidator(),
        )
        super().__init__()


class LegacyAtomicSecretConfig(LegacyConfigBase):
    def __init__(self) -> None:
        self.Data_Token = LegacyConfigItem(
            "Data",
            "Token",
            "old-secret",
            EncryptedValidator(StringValidator()),
        )
        super().__init__()


class LegacyDetachedChildConfig(LegacyConfigBase):
    def __init__(self) -> None:
        self.Data_Value = LegacyConfigItem("Data", "Value", "child")
        super().__init__()


class LegacyDetachedParentConfig(LegacyConfigBase):
    def __init__(self) -> None:
        self.Data_Value = LegacyConfigItem("Data", "Value", "parent")
        self.Children = LegacyMultipleConfig([LegacyDetachedChildConfig])
        super().__init__()


class TestTaskOwnership(IsolatedAsyncioTestCase):
    async def test_child_task_cannot_reuse_manager_transaction(self) -> None:
        manager = ConfigManager()

        async def child() -> None:
            async with manager.transaction():
                self.fail("copied transaction context was accepted")

        async with manager.transaction():
            with self.assertRaisesRegex(RuntimeError, "another task"):
                await asyncio.create_task(child())

    async def test_child_task_cannot_reuse_node_commit_frame(self) -> None:
        manager = ConfigManager()
        node = ExampleEntry()

        async def child() -> None:
            async with manager.node_commit(node):
                self.fail("copied node commit frame was accepted")

        async with manager.transaction():
            async with manager.node_commit(node):
                with self.assertRaisesRegex(RuntimeError, "another task"):
                    await asyncio.create_task(child())

    async def test_sync_transaction_rejects_overlap_with_other_async_task(
        self,
    ) -> None:
        manager = ConfigManager()
        entered = asyncio.Event()
        release = asyncio.Event()

        async def hold_transaction() -> None:
            async with manager.transaction():
                entered.set()
                await release.wait()

        holder = asyncio.create_task(hold_transaction())
        await entered.wait()
        try:
            with self.assertRaisesRegex(RuntimeError, "cannot overlap"):
                with manager.transaction_sync():
                    self.fail("sync transaction overlapped async owner")
        finally:
            release.set()
            await holder


class TestTaskIsolatedStaging(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.entry = ExampleEntry()
        await self.entry.activate()

    async def test_failed_task_does_not_consume_another_task_batch(self) -> None:
        b_staged = asyncio.Event()
        c_staged = asyncio.Event()
        allow_b_commit = asyncio.Event()
        allow_c_commit = asyncio.Event()

        async def reject_b(_sender: object, event: FieldChangeEvent) -> None:
            if event.field == "first" and event.value == 10:
                raise RuntimeError("B listener failed")

        self.entry.connect_validator(reject_b, group="settings")

        async def task_b() -> str:
            self.entry.settings.first = 10
            b_staged.set()
            await allow_b_commit.wait()
            try:
                await self.entry.commit()
            except ConfigAggregateError:
                return "failed"
            return "succeeded"

        async def task_c() -> str:
            await b_staged.wait()
            self.entry.settings.second = 20
            c_staged.set()
            await allow_c_commit.wait()
            await self.entry.commit()
            return "succeeded"

        b = asyncio.create_task(task_b())
        c = asyncio.create_task(task_c())
        await c_staged.wait()

        allow_b_commit.set()
        self.assertEqual(await b, "failed")
        allow_c_commit.set()
        self.assertEqual(await c, "succeeded")

        self.assertEqual(self.entry.settings.first, 1)
        self.assertEqual(self.entry.settings.second, 20)

    async def test_legacy_staged_ops_view_is_scoped_to_the_current_task(self) -> None:
        first_staged = asyncio.Event()
        allow_first = asyncio.Event()

        async def first() -> None:
            self.entry.settings.first = 10
            self.assertEqual(len(self.entry._staged_ops), 1)
            first_staged.set()
            await allow_first.wait()
            await self.entry.commit()

        async def second() -> None:
            await first_staged.wait()
            self.assertEqual(self.entry._staged_ops, [])
            self.entry.settings.second = 20
            self.assertEqual(len(self.entry._staged_ops), 1)
            await self.entry.commit()
            allow_first.set()

        await asyncio.gather(first(), second())
        self.assertEqual(self.entry.settings.first, 10)
        self.assertEqual(self.entry.settings.second, 20)


class TestSignalReceiverShapes(IsolatedAsyncioTestCase):
    async def test_function_bound_method_and_callable_object_are_supported(
        self,
    ) -> None:
        entry = ExampleEntry()
        await entry.activate()
        calls: list[str] = []

        async def function_receiver(
            _sender: object, _event: FieldChangeEvent
        ) -> None:
            calls.append("function")

        class BoundListener:
            async def receive(
                self, _sender: object, _event: FieldChangeEvent
            ) -> None:
                calls.append("bound")

        class CallableListener:
            async def __call__(
                self, _sender: object, _event: FieldChangeEvent
            ) -> None:
                calls.append("callable")

        bound = BoundListener()
        callable_receiver = CallableListener()
        entry.connect_validator(
            function_receiver, group="settings", field="first"
        )
        entry.connect_validator(
            bound.receive, group="settings", field="first"
        )
        entry.connect_validator(
            callable_receiver, group="settings", field="first"
        )

        entry.settings.first = 10
        await entry.commit()
        self.assertCountEqual(calls, ["function", "bound", "callable"])

        calls.clear()
        # Attribute lookup creates a new bound method object; disconnect must
        # still find the original subscription by (instance, function).
        entry.disconnect_validator(
            bound.receive, group="settings", field="first"
        )
        entry.settings.first = 11
        await entry.commit()
        self.assertCountEqual(calls, ["function", "callable"])

    async def test_default_weak_bound_method_does_not_keep_instance_alive(
        self,
    ) -> None:
        entry = ExampleEntry()
        await entry.activate()
        calls: list[str] = []

        class Listener:
            async def receive(
                self, _sender: object, _event: FieldChangeEvent
            ) -> None:
                calls.append("called")

        listener = Listener()
        listener_ref = weakref.ref(listener)
        entry.connect_validator(
            listener.receive, group="settings", field="first"
        )
        del listener
        gc.collect()
        self.assertIsNone(listener_ref())

        entry.settings.first = 10
        await entry.commit()
        self.assertEqual(calls, [])


class TestTransactionLockOrder(IsolatedAsyncioTestCase):
    async def test_cross_node_listener_commit_cannot_deadlock(self) -> None:
        node_a = ExampleEntry()
        node_b = ExampleEntry()
        await node_a.activate()
        await node_b.activate()

        start_b = asyncio.Event()
        b_entered_commit = asyncio.Event()

        async def update_b(_sender: object, event: FieldChangeEvent) -> None:
            if event.field != "first" or event.value != 10:
                return
            start_b.set()
            await b_entered_commit.wait()
            node_b.settings.first = 11
            await node_b.commit()

        node_a.connect_validator(update_b, group="settings")

        async def task_one() -> None:
            async with transaction():
                node_a.settings.first = 10
                await node_a.commit()

        async def task_two() -> None:
            await start_b.wait()
            node_b.settings.second = 22
            b_entered_commit.set()
            await node_b.commit()

        first = asyncio.create_task(task_one())
        second = asyncio.create_task(task_two())
        await asyncio.wait_for(asyncio.gather(first, second), timeout=2.0)

        self.assertEqual(node_a.settings.first, 10)
        self.assertEqual(node_b.settings.first, 11)
        self.assertEqual(node_b.settings.second, 22)

    async def test_validator_wait_cycle_does_not_cancel_shared_task(self) -> None:
        node = ExampleEntry()
        await node.activate()
        start_worker = asyncio.Event()

        async def worker() -> None:
            await start_worker.wait()
            node.settings.second = 20
            await node.commit()

        worker_task = asyncio.create_task(worker())

        async def await_worker(_sender: object, event: FieldChangeEvent) -> None:
            if event.field == "first":
                start_worker.set()
                await worker_task

        node.connect_validator(await_worker, group="settings")
        node.settings.first = 10

        with (
            patch(
                "app.configuration.v2.signals.SIGNAL_CALLBACK_TIMEOUT_SECONDS",
                0.05,
            ),
            self.assertRaisesRegex(ConfigAggregateError, "validator timed out"),
        ):
            await asyncio.wait_for(node.commit(), timeout=1.0)

        self.assertEqual(node.settings.first, 1)
        self.assertFalse(worker_task.cancelled())
        await asyncio.wait_for(worker_task, timeout=1.0)
        self.assertEqual(node.settings.second, 20)


class TestTransactionCancellationOutcome(IsolatedAsyncioTestCase):
    async def test_cancel_during_post_commit_hook_does_not_restore_batch(
        self,
    ) -> None:
        entry = ExampleEntry()
        await entry.activate()
        hook_started = asyncio.Event()
        never = asyncio.Event()
        old_commit = config_manager._post_commit_hook
        old_rollback = config_manager._post_rollback_hook

        async def post_commit(_transaction_id: object) -> None:
            hook_started.set()
            await never.wait()

        config_manager.configure_transaction_hooks(
            post_commit=post_commit,
            post_rollback=old_rollback,
        )
        try:
            async def commit_change() -> None:
                entry.settings.first = 10
                await entry.commit()

            commit_task = asyncio.create_task(commit_change())
            await hook_started.wait()
            commit_task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await commit_task

            self.assertEqual(entry.settings.first, 10)
            self.assertEqual(entry._staged_ops_by_task.get(commit_task, []), [])
        finally:
            config_manager.configure_transaction_hooks(
                post_commit=old_commit,
                post_rollback=old_rollback,
            )

    async def test_cancel_during_precommit_rolls_back_and_restores_batch(
        self,
    ) -> None:
        entry = ExampleEntry()
        await entry.activate()
        receiver_started = asyncio.Event()
        never = asyncio.Event()

        async def block_receiver(
            _sender: object, event: FieldChangeEvent
        ) -> None:
            if event.field == "first":
                receiver_started.set()
                await never.wait()

        entry.connect_validator(
            block_receiver, group="settings", field="first"
        )

        async def commit_change() -> None:
            entry.settings.first = 10
            await entry.commit()

        commit_task = asyncio.create_task(commit_change())
        await receiver_started.wait()
        commit_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await commit_task

        self.assertEqual(entry.settings.first, 1)
        self.assertEqual(
            len(entry._staged_ops_by_task.get(commit_task, [])),
            1,
        )


class AlternateEntry(ExampleEntry):
    pass


class TestCollectionWireIntegrity(IsolatedAsyncioTestCase):
    async def assert_wire_rejected(self, wire: dict[str, Any]) -> None:
        collection = ConfigCollection(
            [ExampleEntry, AlternateEntry],
            wire=wire,
        )
        with self.assertRaises(ValueError):
            await collection.activate()
        self.assertEqual(collection.activation_state, NodeState.INACTIVE)
        self.assertIsNone(collection._workspace)
        self.assertEqual(collection.order, [])
        self.assertEqual(collection.data, {})

    async def test_orphan_data_uid_is_rejected(self) -> None:
        uid = uuid4()
        await self.assert_wire_rejected(
            {"order": [], "data": {str(uid): {}}},
        )

    async def test_missing_data_uid_is_rejected(self) -> None:
        uid = uuid4()
        await self.assert_wire_rejected(
            {
                "order": [{"uid": str(uid), "type": "ExampleEntry"}],
                "data": {},
            },
        )

    async def test_duplicate_order_uid_is_rejected(self) -> None:
        uid = uuid4()
        item = {"uid": str(uid), "type": "ExampleEntry"}
        await self.assert_wire_rejected(
            {
                "order": [dict(item), dict(item)],
                "data": {str(uid): {}},
            },
        )

    async def test_order_type_must_match_materialized_data(self) -> None:
        uid = uuid4()
        await self.assert_wire_rejected(
            {
                "order": [{"uid": str(uid), "type": "ExampleEntry"}],
                "data": {str(uid): AlternateEntry.build(uid=uid)},
            },
        )

    async def test_collection_rejects_unknown_top_level_path(self) -> None:
        collection = ConfigCollection(
            [ExampleEntry],
            wire={"order": [], "data": {}, "future": {}},
        )

        with self.assertRaisesRegex(ValueError, r"\$\.future"):
            await collection.activate()

        self.assertEqual(collection.activation_state, NodeState.INACTIVE)

    async def test_collection_member_rejects_unknown_group_field(self) -> None:
        uid = uuid4()
        collection = ConfigCollection(
            [ExampleEntry],
            wire={
                "order": [{"uid": str(uid), "type": "ExampleEntry"}],
                "data": {
                    str(uid): {
                        "settings": {"first": 1, "second": 2, "future": 3}
                    }
                },
            },
        )

        with self.assertRaisesRegex(ConfigAggregateError, r"settings\.future"):
            await collection.activate()

        self.assertEqual(collection.activation_state, NodeState.INACTIVE)
        self.assertEqual(collection.data, {})

    async def test_public_containers_and_order_events_are_defensive_snapshots(
        self,
    ) -> None:
        collection = ConfigCollection([ExampleEntry])
        await collection.activate()
        first = collection.add(ExampleEntry)
        second = collection.add(ExampleEntry)
        await collection.commit()

        order_snapshot = collection.order
        order_snapshot[0].type = "Mutated"
        order_snapshot.clear()
        data_snapshot = collection.data
        data_snapshot.clear()
        serialized = collection.model_dump()
        serialized["order"].clear()

        self.assertEqual([item.uid for item in collection.order], [first, second])
        self.assertEqual(set(collection.data), {first, second})
        with self.assertRaisesRegex(AttributeError, "只读"):
            collection.order = []  # type: ignore[misc]
        with self.assertRaisesRegex(AttributeError, "只读"):
            collection.data = {}  # type: ignore[misc]

        async def mutate_order_event(
            _sender: object, event: object
        ) -> None:
            old_order = getattr(event, "old_order", None)
            new_order = getattr(event, "order", None)
            if isinstance(old_order, list):
                old_order.clear()
            if isinstance(new_order, list):
                new_order.clear()

        collection.connect_validator(mutate_order_event)
        collection.set_order([collection.order[1], collection.order[0]])
        await collection.commit()
        self.assertEqual([item.uid for item in collection.order], [second, first])

        await collection.lock()
        locked_snapshot = collection.data
        locked_snapshot.pop(first)
        self.assertIn(first, collection)


class TestTransactionalRefDelete(IsolatedAsyncioTestCase):
    async def _build_fixture(
        self,
    ) -> tuple[
        ConfigCollection[ExampleEntry],
        ConfigEntry,
        object,
        object,
    ]:
        target_name = f"test-ref-target-{uuid4()}"

        class LinkGroup(ConfigGroup):
            target: Annotated[
                str,
                ref(
                    target_name,
                    default="-",
                    on_delete=RefDeleteAction.RESTRICT,
                ),
            ] = "-"

        class LinkEntry(ConfigEntry):
            links: LinkGroup = Field(default_factory=LinkGroup)

        target = ConfigCollection([ExampleEntry], name=target_name)
        await target.activate()
        uid_a = target.add(ExampleEntry)
        uid_b = target.add(ExampleEntry)
        await target.commit()
        link = LinkEntry.build(wire={"links": {"target": str(uid_b)}})
        await link.activate()
        return target, link, uid_a, uid_b

    async def test_staged_b_to_a_then_delete_a_is_restricted_and_rolled_back(
        self,
    ) -> None:
        target, link, uid_a, uid_b = await self._build_fixture()
        try:
            with self.assertRaises(ConfigAggregateError):
                async with config_manager.transaction():
                    link.links.target = str(uid_a)  # type: ignore[attr-defined]
                    await link.commit()
                    target.remove(uid_a)
                    await target.commit()

            self.assertEqual(link.links.target, str(uid_b))  # type: ignore[attr-defined]
            self.assertIn(uid_a, target)
        finally:
            await config_manager.dispose_node(target)

    async def test_staged_a_to_default_then_delete_a_succeeds(self) -> None:
        target, link, uid_a, _uid_b = await self._build_fixture()
        try:
            link.links.target = str(uid_a)  # type: ignore[attr-defined]
            await link.commit()

            async with config_manager.transaction():
                link.links.target = "-"  # type: ignore[attr-defined]
                await link.commit()
                target.remove(uid_a)
                await target.commit()

            self.assertEqual(link.links.target, "-")  # type: ignore[attr-defined]
            self.assertNotIn(uid_a, target)
        finally:
            await config_manager.dispose_node(target)


class TestNativeWireUnknownFields(IsolatedAsyncioTestCase):
    async def test_entry_rejects_unknown_top_level_group(self) -> None:
        entry = ExampleEntry.build(
            wire={
                "settings": {"first": 1, "second": 2},
                "future": {"token": "not-imported"},
            }
        )

        with self.assertRaisesRegex(ValueError, r"\$\.future"):
            await entry.activate()

        self.assertEqual(entry.activation_state, NodeState.INACTIVE)

    async def test_entry_rejects_unknown_field_without_rewriting_source(
        self,
    ) -> None:
        source = "[settings]\nfirst = 1\nsecond = 2\nfuture = 3\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "native-v2.toml"
            path.write_text(source, encoding="utf-8")
            entry = ExampleEntry.build(file=path)
            try:
                with self.assertRaisesRegex(ValueError, r"settings\.future"):
                    await entry.activate()

                await config_manager.flush()
                self.assertEqual(path.read_text(encoding="utf-8"), source)
                self.assertEqual(entry.activation_state, NodeState.INACTIVE)
            finally:
                await config_manager.dispose_node(entry)


class TestRootIdentityAndPathRegistry(IsolatedAsyncioTestCase):
    async def test_explicit_uid_is_registered_before_file_and_survives_flush(
        self,
    ) -> None:
        uid = uuid4()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "root.toml"
            entry = ExampleEntry.build(uid=uid, file=path)
            try:
                self.assertEqual(entry.uid, uid)
                self.assertEqual(entry.persist_path, path.resolve())
                await entry.activate()
                entry.settings.first = 42
                await entry.commit()
                await config_manager.flush()
                self.assertEqual(read_wire_toml(path)["settings"]["first"], 42)
            finally:
                await config_manager.dispose_node(entry)
            self.assertIsNone(entry.persist_path)

    async def test_constructor_and_uid_conflict_fail_without_registry_leak(
        self,
    ) -> None:
        uid = uuid4()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = ExampleEntry.build(uid=uid, file=root / "first.toml")
            try:
                before = list(config_manager.iter_persist_roots())
                with self.assertRaisesRegex(ValueError, "different root"):
                    ExampleEntry.build(uid=uid, file=root / "second.toml")
                with self.assertRaises(ValueError):
                    ExampleEntry.build(uid="not-a-uuid", file=root / "bad.toml")
                self.assertEqual(list(config_manager.iter_persist_roots()), before)
                self.assertEqual(first.persist_path, (root / "first.toml").resolve())
            finally:
                await config_manager.dispose_node(first)

    def test_relative_case_alias_and_hot_reload_path_ownership(self) -> None:
        manager = ConfigManager()
        absolute = (Path.cwd() / f".path-alias-{uuid4()}" / "Config.toml").resolve()
        relative = Path(os.path.relpath(absolute, Path.cwd()))
        first = ExampleEntry()
        second = ExampleEntry()
        manager.register_root(first, relative, owner="plugin")

        with self.assertRaisesRegex(ValueError, "path is already registered"):
            manager.register_root(second, absolute)
        if sys.platform == "win32":
            with self.assertRaisesRegex(
                ValueError, "path is already registered"
            ):
                manager.register_root(second, Path(str(absolute).swapcase()))

        manager.disconnect_owner("plugin")
        manager.register_root(second, absolute, owner="plugin-reloaded")
        self.assertEqual(manager.get_file(second), absolute)
        manager.unregister_root(second)
        self.assertIsNone(manager.get_file(second))


class TestPydanticTransportContracts(IsolatedAsyncioTestCase):
    async def test_all_pydantic_and_fastapi_outputs_use_frontend_boundary(
        self,
    ) -> None:
        with (
            patch(
                "app.configuration.v2.encrypted.dpapi_encrypt",
                side_effect=lambda value: f"cipher:{value}",
            ),
            patch(
                "app.configuration.v2.encrypted.dpapi_decrypt",
                side_effect=lambda value: value.removeprefix("cipher:"),
            ),
            tempfile.TemporaryDirectory() as temp_dir,
        ):
            path = Path(temp_dir) / "transport.toml"
            entry = TransportEntry.build(file=path)
            try:
                await entry.activate()
                entry.transport.token = "frontend-secret"
                await entry.commit()

                expected = {
                    "token": "frontend-secret",
                    "status": "ready",
                    "refresh": False,
                }
                self.assertEqual(entry.model_dump()["transport"], expected)
                self.assertEqual(
                    json.loads(entry.model_dump_json())["transport"],
                    expected,
                )

                adapter = TypeAdapter(TransportEntry)
                self.assertEqual(
                    adapter.dump_python(entry)["transport"],
                    expected,
                )
                self.assertEqual(
                    json.loads(adapter.dump_json(entry))["transport"],
                    expected,
                )

                app = FastAPI()

                @app.get("/config", response_model=TransportEntry)
                async def get_config() -> TransportEntry:
                    return entry

                response = TestClient(app).get("/config")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["transport"], expected)

                await config_manager.flush()
                disk = read_wire_toml(path)["transport"]
                self.assertEqual(disk["token"], "DPAPI:cipher:frontend-secret")
                self.assertNotIn("status", disk)
                self.assertNotIn("refresh", disk)
            finally:
                await config_manager.dispose_node(entry)

    def test_model_validate_and_json_forbid_unknown_paths(self) -> None:
        with self.assertRaises(ValidationError):
            ExampleEntry.model_validate({"future": 1})
        with self.assertRaises(ValidationError):
            ExampleEntry.model_validate(
                {"settings": {"first": 1, "second": 2, "future": 3}}
            )
        with self.assertRaises(ValidationError):
            ExampleEntry.model_validate_json(
                '{"settings":{"first":1,"second":2,"future":3}}'
            )
        with self.assertRaises(ValidationError):
            ConfigCollection.model_validate(
                {
                    "order": [
                        {
                            "uid": str(uuid4()),
                            "type": "ExampleEntry",
                            "future": True,
                        }
                    ],
                    "data": {},
                }
            )

    def test_fastapi_body_forbids_unknown_top_and_nested_paths(self) -> None:
        app = FastAPI()

        @app.post("/config")
        async def post_config(config: ExampleEntry) -> dict[str, bool]:
            del config
            return {"ok": True}

        client = TestClient(app)
        self.assertEqual(client.post("/config", json={"future": 1}).status_code, 422)
        self.assertEqual(
            client.post(
                "/config",
                json={"settings": {"first": 1, "second": 2, "future": 3}},
            ).status_code,
            422,
        )

        @app.post("/secret")
        async def post_secret(config: ValidatedSecretEntry) -> dict[str, bool]:
            del config
            return {"ok": True}

        plaintext = "TOP-SECRET-MUST-NOT-LEAK"
        secret_response = client.post(
            "/secret",
            json={"secrets": {"token": plaintext}},
        )
        self.assertEqual(secret_response.status_code, 422)
        self.assertNotIn(plaintext, secret_response.text)

    def test_custom_build_parameters_remain_available_with_extra_forbid(self) -> None:
        uid = uuid4()
        entry = ExampleEntry.build(
            uid=uid,
            wire={"settings": {"first": 5}},
        )
        self.assertEqual(entry.uid, uid)
        self.assertEqual(entry._pending_wire, {"settings": {"first": 5}})


class TestAtomicNodeChanges(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.entry = ExampleEntry()
        await self.entry.activate()

    async def test_commit_batch_rolls_back_earlier_fields(self) -> None:
        async def fail_second(_sender: object, event: FieldChangeEvent) -> None:
            if event.field == "second":
                raise RuntimeError("listener rejected second")

        self.entry.connect_validator(fail_second, group="settings")
        self.entry.settings.first = 10
        self.entry.settings.second = 20

        with self.assertRaises(ConfigAggregateError):
            await self.entry.commit()

        self.assertEqual(self.entry.settings.first, 1)
        self.assertEqual(self.entry.settings.second, 2)

    async def test_lock_rejection_preserves_staged_batch_for_retry(self) -> None:
        self.entry.settings.first = 10
        await self.entry.lock()
        with self.assertRaisesRegex(ValueError, "已锁定"):
            await self.entry.commit()

        self.assertEqual(len(self.entry._staged_ops), 1)
        self.assertEqual(self.entry.settings.first, 1)
        await self.entry.unlock()
        await self.entry.commit()
        self.assertEqual(self.entry.settings.first, 10)

    async def test_update_has_no_partial_result(self) -> None:
        async def fail_second(_sender: object, event: FieldChangeEvent) -> None:
            if event.field == "second":
                raise RuntimeError("listener rejected update")

        self.entry.connect_validator(fail_second, group="settings")
        replacement = ExampleEntry(
            settings=ExampleGroup(first=100, second=200),
        )

        with self.assertRaises(ConfigAggregateError):
            await self.entry.update(replacement)

        self.assertEqual(self.entry.settings.first, 1)
        self.assertEqual(self.entry.settings.second, 2)

    async def test_atomic_update_does_not_execute_trigger_side_effects(self) -> None:
        class Actions(ConfigGroup):
            run: Trigger = False

        class TriggerEntry(ConfigEntry):
            actions: Actions = Field(default_factory=Actions)
            runs: int = 0

            @trigger_field("actions.run")
            def run_action(self) -> None:
                self.runs += 1

        entry = TriggerEntry()
        await entry.activate()
        body = TriggerEntry.model_validate({"actions": {"run": True}})
        await entry.update(body)
        self.assertEqual(entry.runs, 0)

        entry.actions.run = True
        self.assertEqual(entry.runs, 1)

    async def test_activation_failure_leaves_live_node_inactive(self) -> None:
        node = FailingActivationEntry()

        with self.assertRaisesRegex(RuntimeError, "activation failed"):
            await node.activate()

        self.assertEqual(node.activation_state, NodeState.INACTIVE)
        self.assertIsNone(node._workspace)


class TestPatchUpdateSemantics(IsolatedAsyncioTestCase):
    async def test_update_only_applies_explicit_groups_and_fields(self) -> None:
        entry = ExampleEntry()
        await entry.activate()
        entry.settings.first = 10
        entry.settings.second = 20
        await entry.commit()

        await entry.update(ExampleEntry.model_validate({}))
        self.assertEqual((entry.settings.first, entry.settings.second), (10, 20))

        await entry.update(
            ExampleEntry.model_validate({"settings": {"first": 30}})
        )
        self.assertEqual((entry.settings.first, entry.settings.second), (30, 20))

        # An explicit default remains a real PATCH value.
        await entry.update(
            ExampleEntry.model_validate({"settings": {"first": 1}})
        )
        self.assertEqual((entry.settings.first, entry.settings.second), (1, 20))

    async def test_update_preserves_explicit_none_and_encrypted_fields(self) -> None:
        nullable = NullableEntry()
        await nullable.activate()
        nullable.nullable.value = "live"
        await nullable.commit()
        await nullable.update(
            NullableEntry.model_validate({"nullable": {"value": None}})
        )
        self.assertIsNone(nullable.nullable.value)

        with (
            patch(
                "app.configuration.v2.encrypted.dpapi_encrypt",
                side_effect=lambda value: f"cipher:{value}",
            ),
            patch(
                "app.configuration.v2.encrypted.dpapi_decrypt",
                side_effect=lambda value: value.removeprefix("cipher:"),
            ),
        ):
            secret = ValidatedSecretEntry()
            await secret.activate()
            secret.secrets.token = "ok-old"
            await secret.commit()
            await secret.update(
                ValidatedSecretEntry.model_validate(
                    {"secrets": {"token": "ok-new"}}
                )
            )
            self.assertEqual(secret.secrets.token, "ok-new")


class TestMutableValueIsolation(IsolatedAsyncioTestCase):
    async def test_reads_locked_nodes_and_events_do_not_expose_live_references(
        self,
    ) -> None:
        entry = MutableEntry()
        await entry.activate()

        read_items = entry.mutable.items
        read_items.append(99)
        self.assertEqual(entry.mutable.items, [1])

        await entry.lock()
        read_mapping = entry.mutable.mapping
        read_mapping["two"] = 2
        self.assertEqual(entry.mutable.mapping, {"one": 1})
        await entry.unlock()

        async def mutate_event(
            _sender: object, event: FieldChangeEvent
        ) -> None:
            if isinstance(event.value, list):
                event.value.append(999)
            if isinstance(event.old_value, list):
                event.old_value.append(888)

        entry.connect_validator(
            mutate_event,
            group="mutable",
            field="items",
        )
        entry.mutable.items = [2]
        await entry.commit()
        self.assertEqual(entry.mutable.items, [2])


class TestEncryptedBoundaries(IsolatedAsyncioTestCase):
    async def test_constrained_ciphertext_round_trip_reuses_persisted_cipher(
        self,
    ) -> None:
        encrypt_calls = 0

        def encrypt(value: str) -> str:
            nonlocal encrypt_calls
            encrypt_calls += 1
            return f"cipher:{encrypt_calls}:{value}"

        def decrypt(value: str) -> str:
            return value.split(":", 2)[2]

        with (
            patch(
                "app.configuration.v2.encrypted.dpapi_encrypt",
                side_effect=encrypt,
            ),
            patch(
                "app.configuration.v2.encrypted.dpapi_decrypt",
                side_effect=decrypt,
            ),
        ):
            original = ValidatedSecretEntry.build(
                wire={"secrets": {"token": "ok-round-trip"}}
            )
            await original.activate()
            persisted = await original.to_dict(if_decrypt=False)
            cipher = persisted["secrets"]["token"]
            self.assertEqual(encrypt_calls, 1)

            restored = ValidatedSecretEntry.build(wire=persisted)
            await restored.activate()
            self.assertEqual(restored.secrets.token, "ok-round-trip")
            self.assertEqual(
                (await restored.to_dict(if_decrypt=False))["secrets"]["token"],
                cipher,
            )
            self.assertEqual(encrypt_calls, 1)

    def test_bad_constrained_ciphertext_error_is_redacted(self) -> None:
        cipher = "DPAPI:BAD-CIPHER-MUST-NOT-LEAK"
        with patch(
            "app.configuration.v2.encrypted.dpapi_decrypt",
            side_effect=ValueError("decoder included sensitive input"),
        ):
            with self.assertRaises(ValidationError) as raised:
                ValidatedSecretGroup(token=cipher)
        rendered = (
            f"{raised.exception!s} {raised.exception!r} "
            f"{raised.exception.errors()!r}"
        )
        self.assertNotIn(cipher, rendered)
        self.assertNotIn("sensitive input", rendered)

    async def test_update_copies_encrypted_fields_through_plaintext_validation(
        self,
    ) -> None:
        with (
            patch(
                "app.configuration.v2.encrypted.dpapi_encrypt",
                side_effect=lambda value: f"cipher:{value}",
            ),
            patch(
                "app.configuration.v2.encrypted.dpapi_decrypt",
                side_effect=lambda value: value.removeprefix("cipher:"),
            ),
        ):
            entry = ValidatedSecretEntry()
            await entry.activate()
            replacement = ValidatedSecretEntry(
                secrets=ValidatedSecretGroup(token="ok-replacement")
            )

            await entry.update(replacement)

            self.assertEqual(entry.secrets.token, "ok-replacement")

    async def test_invalid_encrypted_input_is_redacted_from_aggregate_error(
        self,
    ) -> None:
        plaintext = "TOP-SECRET-MUST-NOT-LEAK"
        entry = ValidatedSecretEntry()
        await entry.activate()
        entry.secrets.token = plaintext

        with self.assertRaises(ConfigAggregateError) as raised:
            await entry.commit()

        self.assertNotIn(plaintext, str(raised.exception))
        self.assertNotIn(plaintext, repr(raised.exception.errors))
        self.assertIsInstance(raised.exception.errors[0], EncryptedValueError)

    async def test_same_plaintext_does_not_emit_for_randomized_ciphertext(self) -> None:
        events: list[FieldChangeEvent] = []
        counter = 0

        def encrypt(value: str) -> str:
            nonlocal counter
            counter += 1
            return f"cipher:{counter}:{value}"

        def decrypt(value: str) -> str:
            return value.split(":", 2)[2]

        async def capture(_sender: object, event: FieldChangeEvent) -> None:
            events.append(event)

        with (
            patch(
                "app.configuration.v2.encrypted.dpapi_encrypt",
                side_effect=encrypt,
            ),
            patch(
                "app.configuration.v2.encrypted.dpapi_decrypt",
                side_effect=decrypt,
            ),
        ):
            entry = SecretEntry()
            await entry.activate()
            entry.connect_validator(capture, group="secrets", field="token")
            entry.secrets.token = "same-secret"
            await entry.commit()
            entry.secrets.token = "same-secret"
            await entry.commit()

        self.assertEqual(len(events), 1)

    async def test_event_has_no_plaintext_and_export_defaults_match_their_boundary(
        self,
    ) -> None:
        events: list[FieldChangeEvent] = []

        async def capture(_sender: object, event: FieldChangeEvent) -> None:
            events.append(event)

        with (
            patch(
                "app.configuration.v2.encrypted.dpapi_encrypt",
                side_effect=lambda value: f"cipher:{value}",
            ),
            patch(
                "app.configuration.v2.encrypted.dpapi_decrypt",
                side_effect=lambda value: value.removeprefix("cipher:"),
            ),
        ):
            entry = SecretEntry()
            await entry.activate()
            entry.connect_validator(capture, group="secrets", field="token")
            entry.secrets.token = "do-not-leak"
            await entry.commit()

            self.assertEqual(len(events), 1)
            event = events[0]
            self.assertTrue(event.encrypted)
            self.assertTrue(event.changed)
            self.assertIsNone(event.value)
            self.assertIsNone(event.old_value)
            self.assertNotIn("do-not-leak", repr(event))

            frontend_payload = entry.model_dump()
            self.assertEqual(frontend_payload["secrets"]["token"], "do-not-leak")
            persisted_payload = await entry.to_dict()
            self.assertEqual(
                persisted_payload["secrets"]["token"],
                "DPAPI:cipher:do-not-leak",
            )
            explicit_ciphertext = entry.model_dump(context={"if_decrypt": False})
            self.assertEqual(
                explicit_ciphertext["secrets"]["token"],
                "DPAPI:cipher:do-not-leak",
            )

    async def test_decrypt_failure_is_explicit(self) -> None:
        value = EncryptedValue.from_string("DPAPI:not-valid")
        with patch(
            "app.configuration.v2.encrypted.dpapi_decrypt",
            side_effect=ValueError("bad ciphertext"),
        ):
            with self.assertRaisesRegex(EncryptedValueError, "cannot be decrypted"):
                value.plaintext()


class TestWindowsDPAPIShape(TestCase):
    def test_encrypt_base64_encodes_the_payload_from_pywin32_tuple(self) -> None:
        protected_payload = b"\x00\xffprotected"
        fake_win32crypt = Mock()
        fake_win32crypt.CryptProtectData.return_value = (
            "AUTO-MAS configuration",
            protected_payload,
        )

        with patch(
            "app.utils.security.win32crypt",
            fake_win32crypt,
        ):
            encoded = dpapi_encrypt("secret")

        self.assertTrue(encoded.startswith(DPAPI_CONFIG_PREFIX))
        self.assertEqual(
            base64.b64decode(encoded.removeprefix(DPAPI_CONFIG_PREFIX)),
            protected_payload,
        )

    def test_encrypt_accepts_native_pywin32_bytes_result(self) -> None:
        protected_payload = b"native-pywin32-bytes"
        fake_win32crypt = Mock()
        fake_win32crypt.CryptProtectData.return_value = protected_payload

        with patch(
            "app.utils.security.win32crypt",
            fake_win32crypt,
        ):
            encoded = dpapi_encrypt("secret")

        self.assertTrue(encoded.startswith(DPAPI_CONFIG_PREFIX))
        self.assertEqual(
            base64.b64decode(encoded.removeprefix(DPAPI_CONFIG_PREFIX)),
            protected_payload,
        )

    def test_real_windows_dpapi_round_trip(self) -> None:
        if sys.platform != "win32":
            self.skipTest("Windows DPAPI is platform-specific")

        from app.configuration.v2.support.security import dpapi_decrypt

        plaintext = f"auto-mas-config-v2-{uuid4()}"
        self.assertEqual(dpapi_decrypt(dpapi_encrypt(plaintext)), plaintext)


class TestPersistentRootLifecycle(IsolatedAsyncioTestCase):
    async def test_failed_activation_root_does_not_block_flush_or_dispose(
        self,
    ) -> None:
        manager = ConfigManager()
        healthy = ExampleEntry()
        failed = FailingActivationEntry()
        await healthy.activate()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            healthy_path = temp_root / "healthy.toml"
            failed_path = temp_root / "failed.toml"
            manager.register_root(healthy, healthy_path)
            manager.register_root(failed, failed_path)

            with self.assertRaisesRegex(RuntimeError, "activation failed"):
                await failed.activate()

            self.assertTrue(manager.is_persist_root(failed))
            await manager.flush()
            self.assertTrue(healthy_path.is_file())
            self.assertFalse(failed_path.exists())

            await manager.dispose_node(failed)
            self.assertFalse(manager.is_persist_root(failed))


class TestNativeNonePersistence(IsolatedAsyncioTestCase):
    async def _assert_lossy_update_preserves_source(
        self,
        *,
        update_items: bool,
    ) -> None:
        source = '[nullable]\nvalue = "original"\nitems = ["original"]\n'
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nullable.toml"
            path.write_text(source, encoding="utf-8")
            entry = NullableEntry.build(file=path)
            try:
                await entry.activate()
                if update_items:
                    entry.nullable.items = ["first", None, "last"]
                else:
                    entry.nullable.value = None
                await entry.commit()

                with self.assertRaises(ConfigAggregateError) as raised:
                    await config_manager.flush()
                self.assertIn(str(entry.uid), str(raised.exception))
                self.assertEqual(path.read_text(encoding="utf-8"), source)
            finally:
                # The active in-memory value is intentionally unpersistable;
                # unregister directly so cleanup cannot rewrite the source.
                config_manager.unregister_root(entry)

    async def test_optional_nondefault_none_fails_closed(self) -> None:
        await self._assert_lossy_update_preserves_source(update_items=False)

    async def test_list_none_fails_closed_without_index_shift(self) -> None:
        await self._assert_lossy_update_preserves_source(update_items=True)


class TestMultiRootPersistence(IsolatedAsyncioTestCase):
    async def _run_case(self, failing_indexes: set[int]) -> None:
        manager = ConfigManager()
        roots = [ExampleEntry() for _ in range(3)]
        for root in roots:
            await root.activate()

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = [Path(temp_dir) / f"root-{index}.toml" for index in range(3)]
            for root, path in zip(roots, paths, strict=True):
                manager.register_root(root, path)

            real_writer = write_wire_toml

            def selective_writer(path: Path, payload: dict[str, Any]) -> None:
                index = paths.index(path)
                if index in failing_indexes:
                    raise RuntimeError("SUPER-SECRET-WRITER-DETAIL")
                real_writer(path, payload)

            with (
                patch(
                    "app.configuration.v2.manager.write_wire_toml",
                    side_effect=selective_writer,
                ),
                self.assertRaises(ConfigAggregateError) as raised,
            ):
                await manager.flush()

            rendered = str(raised.exception)
            self.assertNotIn("SUPER-SECRET-WRITER-DETAIL", rendered)
            for index, (root, path) in enumerate(
                zip(roots, paths, strict=True)
            ):
                if index in failing_indexes:
                    self.assertFalse(path.exists())
                    self.assertIn(str(root.uid), rendered)
                    self.assertIn(str(path), rendered)
                else:
                    self.assertTrue(path.is_file())

    async def test_failure_before_healthy_root_does_not_block_it(self) -> None:
        await self._run_case({0})

    async def test_failure_after_healthy_root_is_still_reported(self) -> None:
        await self._run_case({2})

    async def test_multiple_failures_are_aggregated_after_healthy_write(
        self,
    ) -> None:
        await self._run_case({0, 2})


class TestAtomicPersistence(TestCase):
    def test_replace_failure_preserves_original_and_recovery_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.toml"
            original = 'value = "old"\n'
            path.write_text(original, encoding="utf-8")

            with patch(
                "app.configuration.v2.wire.os.replace",
                side_effect=OSError("replace denied"),
            ):
                with self.assertRaisesRegex(OSError, "replace denied"):
                    write_wire_toml(path, {"value": "new"})

            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertTrue(path.with_name("config.toml.bak").exists())

    def test_legacy_json_replace_failure_preserves_original_and_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "Config.json"
            original = '{"value": "old"}'
            path.write_text(original, encoding="utf-8")

            with patch(
                "app.utils.atomic_file.os.replace",
                side_effect=OSError("replace denied"),
            ):
                with self.assertRaisesRegex(OSError, "replace denied"):
                    atomic_write_json(path, {"value": "new"})

            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertTrue(path.with_name("Config.json.bak").exists())


class TestLegacyEncryptedSetValueAtomicity(IsolatedAsyncioTestCase):
    @staticmethod
    def _encrypt(value: str) -> str:
        return f"cipher::{value}"

    @staticmethod
    def _decrypt(value: str) -> str:
        if not value.startswith("cipher::"):
            raise ValueError("bad cipher")
        return value.removeprefix("cipher::")

    async def test_non_string_and_encrypt_failure_preserve_old_cipher(
        self,
    ) -> None:
        with (
            patch("app.models.ConfigBase.dpapi_encrypt", side_effect=self._encrypt),
            patch("app.models.ConfigBase.dpapi_decrypt", side_effect=self._decrypt),
        ):
            config = LegacyAtomicSecretConfig()
            old_cipher = config.Data_Token.value

            with self.assertRaises(TypeError):
                config.Data_Token.setValue({"secret": "plaintext"})
            self.assertEqual(config.Data_Token.value, old_cipher)

            with patch(
                "app.models.ConfigBase.dpapi_encrypt",
                side_effect=RuntimeError("encrypt failed"),
            ):
                with self.assertRaisesRegex(RuntimeError, "encrypt failed"):
                    config.Data_Token.setValue("new-secret")
            self.assertEqual(config.Data_Token.value, old_cipher)
            self.assertEqual(
                (await config.toDict(if_decrypt=False))["Data"]["Token"],
                old_cipher,
            )

    async def test_damaged_current_cipher_can_be_reset(self) -> None:
        with (
            patch("app.models.ConfigBase.dpapi_encrypt", side_effect=self._encrypt),
            patch("app.models.ConfigBase.dpapi_decrypt", side_effect=self._decrypt),
        ):
            config = LegacyAtomicSecretConfig()
            config.Data_Token.value = "damaged-current-cipher"
            self.assertTrue(config.Data_Token.setValue("replacement"))
            self.assertEqual(config.Data_Token.getValue(), "replacement")
            self.assertEqual(
                config.Data_Token.getValue(if_decrypt=False),
                "cipher::replacement",
            )

    async def test_failed_set_then_save_keeps_old_cipher_on_disk(self) -> None:
        with (
            patch("app.models.ConfigBase.dpapi_encrypt", side_effect=self._encrypt),
            patch("app.models.ConfigBase.dpapi_decrypt", side_effect=self._decrypt),
            tempfile.TemporaryDirectory() as temp_dir,
        ):
            path = Path(temp_dir) / "Config.json"
            config = LegacyAtomicSecretConfig()
            await config.connect(path)
            old_cipher = config.Data_Token.value

            with patch(
                "app.models.ConfigBase.dpapi_encrypt",
                side_effect=RuntimeError("encrypt failed"),
            ):
                with self.assertRaises(RuntimeError):
                    config.Data_Token.setValue("never-persist")
            await config.save()

            disk = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(disk["Data"]["Token"], old_cipher)
            self.assertNotIn("never-persist", path.read_text(encoding="utf-8"))


class TestLegacySaveObserver(IsolatedAsyncioTestCase):
    async def test_proxy_credentials_are_decrypted_for_runtime_and_encrypted_on_disk(
        self,
    ) -> None:
        plaintext = "http://proxy-user:proxy-password@127.0.0.1:8080"
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch(
                "app.models.ConfigBase.dpapi_encrypt",
                side_effect=lambda value: f"cipher:{value[::-1]}",
            ),
            patch(
                "app.models.ConfigBase.dpapi_decrypt",
                side_effect=lambda value: value.removeprefix("cipher:")[::-1]
                if value.startswith("cipher:")
                else (_ for _ in ()).throw(ValueError("plaintext")),
            ),
        ):
            path = Path(temp_dir) / "Config.json"
            config = GlobalConfig()
            await config.connect(path)
            await config.set("Update", "ProxyAddress", plaintext)

            self.assertEqual(config.get("Update", "ProxyAddress"), plaintext)
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn("proxy-user", raw)
            self.assertNotIn("proxy-password", raw)
            persisted = json.loads(raw)
            self.assertTrue(
                persisted["Update"]["ProxyAddress"].startswith("cipher:")
            )

    async def test_successful_save_notifies_shadow_bridge_with_disk_payload(
        self,
    ) -> None:
        observed: list[tuple[Path, dict[str, Any]]] = []

        async def capture(path: Path, payload: dict[str, Any]) -> None:
            observed.append((path, payload))

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "Config.json"
            config = LegacyExampleConfig()
            await config.connect(path)
            configure_config_save_observer(capture)
            try:
                await config.set("Data", "Value", "saved")
            finally:
                configure_config_save_observer(None)

            payload = {"Data": {"Value": "saved"}}
            self.assertEqual(observed, [(path, payload)])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), payload)

    async def test_encrypted_json_migrates_plaintext_and_never_writes_it_back(
        self,
    ) -> None:
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch(
                "app.models.ConfigBase.dpapi_encrypt",
                side_effect=lambda value: f"cipher:{value[::-1]}",
            ),
            patch(
                "app.models.ConfigBase.dpapi_decrypt",
                side_effect=lambda value: value.removeprefix("cipher:")[::-1]
                if value.startswith("cipher:")
                else (_ for _ in ()).throw(ValueError("plaintext")),
            ),
        ):
            path = Path(temp_dir) / "PluginConfig.json"
            path.write_text(
                json.dumps({"Data": {"Config": '{"token":"secret"}'}}),
                encoding="utf-8",
            )
            config = LegacyEncryptedJSONConfig()
            await config.connect(path)

            self.assertEqual(config.get("Data", "Config"), '{"token":"secret"}')
            persisted = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                persisted["Data"]["Config"],
                'cipher:}"terces":"nekot"{',
            )
            self.assertNotIn("secret", path.read_text(encoding="utf-8"))

    async def test_composite_encryption_keeps_frontend_plaintext_and_disk_ciphertext(
        self,
    ) -> None:
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch(
                "app.models.ConfigBase.dpapi_encrypt",
                side_effect=lambda value: f"cipher:{value[::-1]}",
            ),
            patch(
                "app.models.ConfigBase.dpapi_decrypt",
                side_effect=lambda value: value.removeprefix("cipher:")[::-1]
                if value.startswith("cipher:")
                else (_ for _ in ()).throw(ValueError("plaintext")),
            ),
        ):
            path = Path(temp_dir) / "Webhook.json"
            path.write_text("{}", encoding="utf-8")
            config = LegacyEncryptedWebhookConfig()
            await config.connect(path)

            url = "https://example.invalid/hook?token=do-not-store"
            headers = '{"Authorization":"Bearer do-not-store"}'
            await config.set("Data", "Url", url)
            await config.set("Data", "Headers", headers)

            frontend = await config.toDict()
            persisted = await config.toDict(if_decrypt=False)
            disk_text = path.read_text(encoding="utf-8")
            self.assertEqual(frontend["Data"], {"Url": url, "Headers": headers})
            self.assertTrue(persisted["Data"]["Url"].startswith("cipher:"))
            self.assertTrue(persisted["Data"]["Headers"].startswith("cipher:"))
            self.assertNotIn("do-not-store", disk_text)


class TestFlush(IsolatedAsyncioTestCase):
    async def test_flush_awaits_cancelled_debounce_cleanup(self) -> None:
        manager = ConfigManager()
        cleanup_finished = False

        async def pending_save() -> None:
            nonlocal cleanup_finished
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                cleanup_finished = True

        task = asyncio.create_task(pending_save())
        await asyncio.sleep(0)
        manager._save_handle = task
        durable_write = AsyncMock()

        with patch.object(manager, "_debounced_save_impl", new=durable_write):
            await manager.flush()

        self.assertTrue(task.done())
        self.assertTrue(cleanup_finished)
        durable_write.assert_awaited_once_with()


class TestRuntimeTransactionOutbox(IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        configure_outbox_hooks(flush=None, discard=None)

    async def test_nested_transaction_reuses_id_and_flushes_only_that_id(
        self,
    ) -> None:
        flushed: list[str] = []
        discarded: list[str] = []

        async def flush(transaction_id: str) -> None:
            flushed.append(transaction_id)

        async def discard(transaction_id: str) -> None:
            discarded.append(transaction_id)

        configure_outbox_hooks(flush=flush, discard=discard)
        async with transaction() as outer:
            async with transaction() as inner:
                self.assertEqual(inner.transaction_id, outer.transaction_id)

        self.assertEqual(flushed, [str(outer.transaction_id)])
        self.assertEqual(discarded, [])


class RecordingOutbox:
    """In-memory implementation of the production injection contract."""

    def __init__(self) -> None:
        self.buckets: dict[str, list[dict[str, Any]]] = {}
        self.sent: list[dict[str, Any]] = []
        self.flushed_ids: list[str] = []
        self.discarded_ids: list[str] = []
        self.enqueue_runtime_active: list[bool] = []

    async def enqueue(
        self,
        id: str,
        type: str,
        data: dict[str, Any],
        *,
        transaction_id: str | None = None,
    ) -> None:
        if transaction_id is None:
            raise AssertionError("configuration must pass an explicit transaction ID")
        self.enqueue_runtime_active.append(get_current_transaction() is not None)
        self.buckets.setdefault(transaction_id, []).append(
            {"id": id, "type": type, "data": dict(data)}
        )

    async def flush(self, transaction_id: str) -> None:
        self.flushed_ids.append(transaction_id)
        self.sent.extend(self.buckets.pop(transaction_id, []))

    async def discard(self, transaction_id: str) -> None:
        self.discarded_ids.append(transaction_id)
        self.buckets.pop(transaction_id, None)

    def clear_trace(self) -> None:
        self.buckets.clear()
        self.sent.clear()
        self.flushed_ids.clear()
        self.discarded_ids.clear()
        self.enqueue_runtime_active.clear()


class TestProductionConfigOutbox(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.outbox = RecordingOutbox()
        configure_outbox_hooks(
            enqueue=self.outbox.enqueue,
            flush=self.outbox.flush,
            discard=self.outbox.discard,
        )
        self.entry = ExampleEntry()
        await self.entry.activate()
        self.outbox.clear_trace()

    async def asyncTearDown(self) -> None:
        configure_outbox_hooks(enqueue=None, flush=None, discard=None)

    async def test_direct_commit_enqueues_and_flushes_explicit_transaction(
        self,
    ) -> None:
        # Production callers need not create a RuntimeTransactionContext: the
        # Manager transaction still provides an explicit isolated bucket ID.
        self.assertIsNone(get_current_transaction())
        self.entry.settings.first = 42
        await self.entry.commit()

        self.assertEqual(self.outbox.enqueue_runtime_active, [False])
        self.assertEqual(len(self.outbox.sent), 1)
        envelope = self.outbox.sent[0]
        data = envelope["data"]
        self.assertEqual(envelope["id"], str(self.entry.uid))
        self.assertEqual(envelope["type"], CONFIG_CHANGED)
        self.assertEqual(data["rootId"], str(self.entry.uid))
        self.assertEqual(data["nodeId"], str(self.entry.uid))
        self.assertEqual(data["group"], "settings")
        self.assertEqual(data["field"], "first")
        self.assertEqual(data["oldValue"], 1)
        self.assertEqual(data["value"], 42)
        self.assertTrue(data["changed"])
        self.assertFalse(data["encrypted"])
        self.assertGreater(data["revision"], 0)
        self.assertEqual(self.outbox.flushed_ids, [data["transactionId"]])
        self.assertEqual(self.outbox.discarded_ids, [])
        self.assertEqual(self.outbox.buckets, {})

    async def test_failed_batch_discards_transaction_without_sending(self) -> None:
        async def reject_second(_sender: object, event: FieldChangeEvent) -> None:
            if event.field == "second":
                raise RuntimeError("reject transaction")

        self.entry.connect_validator(reject_second, group="settings")
        self.entry.settings.first = 10
        self.entry.settings.second = 20

        with self.assertRaises(ConfigAggregateError):
            await self.entry.commit()

        self.assertEqual(self.outbox.sent, [])
        self.assertEqual(self.outbox.flushed_ids, [])
        self.assertEqual(len(self.outbox.discarded_ids), 1)
        self.assertEqual(self.outbox.buckets, {})
        self.assertEqual(self.entry.settings.first, 1)
        self.assertEqual(self.entry.settings.second, 2)

    async def test_encrypted_payload_never_contains_values(self) -> None:
        with (
            patch(
                "app.configuration.v2.encrypted.dpapi_encrypt",
                side_effect=lambda value: f"cipher:{value}",
            ),
            patch(
                "app.configuration.v2.encrypted.dpapi_decrypt",
                side_effect=lambda value: value.removeprefix("cipher:"),
            ),
        ):
            entry = SecretEntry()
            await entry.activate()
            self.outbox.clear_trace()
            entry.secrets.token = "never-on-the-wire"
            await entry.commit()

        self.assertEqual(len(self.outbox.sent), 1)
        data = self.outbox.sent[0]["data"]
        self.assertTrue(data["changed"])
        self.assertTrue(data["encrypted"])
        self.assertNotIn("value", data)
        self.assertNotIn("oldValue", data)
        self.assertNotIn("never-on-the-wire", repr(data))
        self.assertGreater(data["revision"], 0)

    async def test_successive_commits_have_monotonic_revisions(self) -> None:
        self.entry.settings.first = 10
        await self.entry.commit()
        self.entry.settings.first = 20
        await self.entry.commit()

        revisions = [entry["data"]["revision"] for entry in self.outbox.sent]
        self.assertEqual(len(revisions), 2)
        self.assertLess(revisions[0], revisions[1])


class TestLegacyPreflight(IsolatedAsyncioTestCase):
    async def test_service_registers_loaded_schema_and_writes_encrypted_shadow(
        self,
    ) -> None:
        from app.core.config_service import ConfigService

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch(
                "app.models.ConfigBase.dpapi_encrypt",
                side_effect=lambda value: f"cipher:{value[::-1]}",
            ),
            patch(
                "app.models.ConfigBase.dpapi_decrypt",
                side_effect=lambda value: value.removeprefix("cipher:")[::-1]
                if value.startswith("cipher:")
                else (_ for _ in ()).throw(ValueError("plaintext")),
            ),
        ):
            root_path = Path(temp_dir)
            config_dir = root_path / "config"
            config_dir.mkdir()
            legacy_path = config_dir / "PluginConfig.json"
            legacy_path.write_text(
                json.dumps({"Data": {"Config": '{"token":"secret"}'}}),
                encoding="utf-8",
            )
            root = LegacyEncryptedJSONConfig()
            await root.connect(legacy_path)
            service = ConfigService()

            try:
                with (
                    patch.object(
                        service,
                        "_legacy_config_roots",
                        return_value=(root,),
                    ),
                    patch("app.core.config_service.CONFIG_V2_MODE", "shadow"),
                    patch("app.configuration.compat.CONFIG_V2_MODE", "shadow"),
                    patch(
                        "app.core.config_service.Path.cwd",
                        return_value=root_path,
                    ),
                ):
                    service._register_legacy_codecs()
                    await service._shadow_migrate_existing()
            finally:
                service._unregister_legacy_codecs()

            shadow_path = legacy_path.with_suffix(".v2.shadow.toml")
            shadow = read_wire_toml(shadow_path)
            self.assertTrue(shadow["Data"]["Config"].startswith("cipher:"))
            self.assertNotIn("secret", shadow_path.read_text(encoding="utf-8"))

    async def test_authoritative_mode_initializes_without_legacy_hooks(
        self,
    ) -> None:
        from app.core.config_service import ConfigService

        service = ConfigService()
        with (
            patch("app.core.config_service.CONFIG_V2_MODE", "authoritative"),
            patch.object(
                service, "_register_legacy_codecs"
            ) as register_codecs,
            patch.object(
                service, "_unregister_legacy_codecs"
            ) as unregister_codecs,
            patch.object(
                service, "_authoritative_load", AsyncMock()
            ) as auth_load,
            patch(
                "app.core.config_service.configure_outbox_hooks",
                Mock(),
            ) as configure_hooks,
            patch(
                "app.core.config_service.configure_config_save_observer",
                Mock(),
            ) as configure_observer,
            patch(
                "app.core.config_service.shutdown_runtime",
                AsyncMock(),
            ),
        ):
            await service.initialize()
            await service.shutdown()

        auth_load.assert_not_awaited()
        register_codecs.assert_not_called()
        unregister_codecs.assert_called_once_with()
        self.assertEqual(configure_hooks.call_count, 2)
        configure_observer.assert_not_called()
        self.assertFalse(service._initialized)
        self.assertEqual(service._lifecycle_state, "idle")

    async def test_shadow_failure_does_not_turn_a_durable_json_save_into_failure(
        self,
    ) -> None:
        from app.core.config_service import ConfigService

        with (
            patch("app.core.config_service.CONFIG_V2_MODE", "shadow"),
            patch("app.configuration.compat.CONFIG_V2_MODE", "shadow"),
            patch(
                "app.core.config_service.legacy_adapter.shadow_write",
                side_effect=OSError("must not escape"),
            ),
        ):
            await ConfigService().save_config(
                Path("Config.json"),
                {"Data": {"Value": "already-saved"}},
            )

    async def test_schema_bound_codec_accepts_only_the_loaded_ciphertext_shape(
        self,
    ) -> None:
        with (
            patch(
                "app.models.ConfigBase.dpapi_encrypt",
                side_effect=lambda value: f"cipher:{value[::-1]}",
            ),
            patch(
                "app.models.ConfigBase.dpapi_decrypt",
                side_effect=lambda value: value.removeprefix("cipher:")[::-1]
                if value.startswith("cipher:")
                else (_ for _ in ()).throw(ValueError("plaintext")),
            ),
        ):
            root = LegacyEncryptedJSONConfig()
            root.Data_Config.setValue('{"token":"secret"}')
            payload = _snapshot_legacy_config(root)
            adapter = LegacyWireAdapter()
            adapter.register_codec(
                "PluginConfig.json",
                _SchemaBoundLegacyCodec(root),
                secrets_protected=True,
            )

            with patch("app.configuration.compat.CONFIG_V2_MODE", "shadow"):
                ready = adapter.preflight(Path("PluginConfig.json"), payload)
                unknown = adapter.preflight(
                    Path("PluginConfig.json"),
                    {**payload, "Unknown": {"token": "plaintext"}},
                )

            self.assertTrue(ready.can_write)
            self.assertNotIn("secret", repr(ready.wire))
            self.assertEqual(unknown.status, "round_trip_mismatch")
            self.assertEqual(unknown.diff_paths, ("$.Unknown",))

    def test_schema_snapshot_excludes_collection_owned_by_another_root(
        self,
    ) -> None:
        parent = LegacyDetachedParentConfig()
        child_uid = uuid4()
        parent.Children.order = [child_uid]
        parent.Children.data = {child_uid: LegacyDetachedChildConfig()}

        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            parent.file = config_dir / "ToolsConfig.json"
            parent.Children.file = config_dir / "GameSignAccounts.json"

            parent_payload = _snapshot_legacy_config(parent)
            child_payload = _snapshot_legacy_config(parent.Children)

        self.assertNotIn("SubConfigsInfo", parent_payload)
        self.assertEqual(
            child_payload["instances"],
            [
                {
                    "uid": str(child_uid),
                    "type": "LegacyDetachedChildConfig",
                }
            ],
        )
        self.assertEqual(
            child_payload[str(child_uid)],
            {"Data": {"Value": "child"}},
        )

    async def test_preflight_detects_values_lost_by_toml_serialization(self) -> None:
        class IdentityCodec:
            def encode(self, legacy_data: dict[str, Any]) -> dict[str, Any]:
                return dict(legacy_data)

            def decode(self, wire_data: dict[str, Any]) -> dict[str, Any]:
                return dict(wire_data)

        adapter = LegacyWireAdapter()
        adapter.register_codec(
            "Config.json",
            IdentityCodec(),
            secrets_protected=True,
        )

        with patch("app.configuration.compat.CONFIG_V2_MODE", "shadow"):
            result = adapter.preflight(Path("Config.json"), {"value": None})

        self.assertEqual(result.status, "round_trip_mismatch")
        self.assertEqual(result.diff_paths, ("$.value",))

    async def test_no_codec_never_writes_or_deletes_existing_shadow(self) -> None:
        adapter = LegacyWireAdapter()
        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_path = Path(temp_dir) / "ScriptConfig.json"
            shadow_path = legacy_path.with_suffix(".v2.shadow.toml")
            shadow_path.write_text("existing = true\n", encoding="utf-8")

            with patch("app.configuration.compat.CONFIG_V2_MODE", "shadow"):
                result = adapter.shadow_write(
                    legacy_path,
                    {"token": "plain-secret", "unknown": {"value": 1}},
                )

            self.assertIsNone(result)
            self.assertEqual(
                shadow_path.read_text(encoding="utf-8"),
                "existing = true\n",
            )
            self.assertEqual(
                list(Path(temp_dir).glob("*.toml")),
                [shadow_path],
            )

    async def test_empty_json_is_skipped_without_calling_adapter(self) -> None:
        from app.core.config_service import ConfigService

        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            config_dir.mkdir()
            (config_dir / "empty.json").write_text(" \r\n\t", encoding="utf-8")
            adapter_write = Mock()

            with (
                patch("app.core.config_service.CONFIG_V2_MODE", "shadow"),
                patch("app.core.config_service.Path.cwd", return_value=Path(temp_dir)),
                patch(
                    "app.core.config_service.legacy_adapter.shadow_write",
                    new=adapter_write,
                ),
            ):
                await ConfigService()._shadow_migrate_existing()

            adapter_write.assert_not_called()


class TestAuthoritativeMode(IsolatedAsyncioTestCase):
    """authoritative 不得重新进入已移除的 legacy 投影链。"""

    async def test_authoritative_load_rejects_legacy_backed_v2_projection(
        self,
    ) -> None:
        from app.core.config_service import ConfigService

        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_path = Path(temp_dir) / "Config.json"
            legacy_path.write_text(
                json.dumps({"Data": {"Value": "original"}}),
                encoding="utf-8",
            )
            v2_path = Path(temp_dir) / "Config.v2.toml"
            v2_path.write_text('[Data]\nValue = "overridden"\n', encoding="utf-8")

            root = LegacyExampleConfig()
            await root.connect(legacy_path)
            self.assertEqual(root.Data_Value.value, "original")

            service = ConfigService()
            try:
                with (
                    patch.object(
                        service,
                        "_legacy_config_roots",
                        return_value=(root,),
                    ),
                    patch("app.core.config_service.CONFIG_V2_MODE", "authoritative"),
                    patch("app.configuration.compat.CONFIG_V2_MODE", "authoritative"),
                ):
                    service._register_legacy_codecs()
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "initialized by NativeConfigFacade",
                    ):
                        await service._authoritative_load()

                self.assertEqual(root.Data_Value.value, "original")
                self.assertEqual(
                    v2_path.read_text(encoding="utf-8"),
                    '[Data]\nValue = "overridden"\n',
                )
            finally:
                service._unregister_legacy_codecs()

    async def test_authoritative_load_does_not_migrate_legacy_json_first(
        self,
    ) -> None:
        from app.core.config_service import ConfigService

        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_path = Path(temp_dir) / "Config.json"
            legacy_path.write_text(
                json.dumps({"Data": {"Value": "r6-saved"}}),
                encoding="utf-8",
            )
            v2_path = Path(temp_dir) / "Config.v2.toml"
            self.assertFalse(v2_path.exists())

            root = LegacyExampleConfig()
            await root.connect(legacy_path)
            self.assertEqual(root.Data_Value.value, "r6-saved")

            service = ConfigService()
            try:
                with (
                    patch.object(
                        service,
                        "_legacy_config_roots",
                        return_value=(root,),
                    ),
                    patch("app.core.config_service.CONFIG_V2_MODE", "authoritative"),
                    patch("app.configuration.compat.CONFIG_V2_MODE", "authoritative"),
                ):
                    service._register_legacy_codecs()
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "initialized by NativeConfigFacade",
                    ):
                        await service._authoritative_load()

                self.assertFalse(v2_path.exists())
                self.assertEqual(root.Data_Value.value, "r6-saved")
            finally:
                service._unregister_legacy_codecs()

    async def test_authoritative_gate_runs_before_legacy_preflight(self) -> None:
        from app.configuration.compat import LegacyPreflight
        from app.core.config_service import ConfigService

        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_path = Path(temp_dir) / "Config.json"
            legacy_path.write_text(
                json.dumps({"Data": {"Value": "will-fail"}}),
                encoding="utf-8",
            )
            v2_path = Path(temp_dir) / "Config.v2.toml"

            root = LegacyExampleConfig()
            await root.connect(legacy_path)

            service = ConfigService()
            try:
                with (
                    patch.object(
                        service,
                        "_legacy_config_roots",
                        return_value=(root,),
                    ),
                    patch("app.core.config_service.CONFIG_V2_MODE", "authoritative"),
                    patch("app.configuration.compat.CONFIG_V2_MODE", "authoritative"),
                    patch(
                        "app.core.config_service.legacy_adapter.preflight",
                        return_value=LegacyPreflight(
                            status="round_trip_mismatch",
                            diff_paths=("$.Data.Value",),
                        ),
                    ) as preflight,
                ):
                    service._register_legacy_codecs()
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "initialized by NativeConfigFacade",
                    ):
                        await service._authoritative_load()

                self.assertFalse(v2_path.exists())
                preflight.assert_not_called()
            finally:
                service._unregister_legacy_codecs()

    async def test_authoritative_load_does_not_fallback_on_invalid_v2_toml(
        self,
    ) -> None:
        from app.core.config_service import ConfigService

        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_path = Path(temp_dir) / "Config.json"
            legacy_path.write_text(
                json.dumps({"Data": {"Value": "legacy-safe"}}),
                encoding="utf-8",
            )
            v2_path = Path(temp_dir) / "Config.v2.toml"
            v2_path.write_text("not-valid-toml [[[", encoding="utf-8")

            root = LegacyExampleConfig()
            await root.connect(legacy_path)
            self.assertEqual(root.Data_Value.value, "legacy-safe")

            service = ConfigService()
            try:
                with (
                    patch.object(
                        service,
                        "_legacy_config_roots",
                        return_value=(root,),
                    ),
                    patch("app.core.config_service.CONFIG_V2_MODE", "authoritative"),
                    patch("app.configuration.compat.CONFIG_V2_MODE", "authoritative"),
                ):
                    service._register_legacy_codecs()
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "initialized by NativeConfigFacade",
                    ):
                        await service._authoritative_load()

                self.assertEqual(root.Data_Value.value, "legacy-safe")
                self.assertEqual(
                    v2_path.read_text(encoding="utf-8"),
                    "not-valid-toml [[[",
                )
            finally:
                service._unregister_legacy_codecs()

    async def test_authoritative_gate_runs_before_root_discovery(self) -> None:
        from app.core.config_service import ConfigService

        root = LegacyExampleConfig()
        self.assertIsNone(root.file)

        service = ConfigService()
        with (
            patch.object(
                service,
                "_legacy_config_roots",
                return_value=(root,),
            ) as legacy_roots,
            patch("app.core.config_service.CONFIG_V2_MODE", "authoritative"),
            patch("app.configuration.compat.CONFIG_V2_MODE", "authoritative"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "initialized by NativeConfigFacade",
            ):
                await service._authoritative_load()

        legacy_roots.assert_not_called()

    async def test_authoritative_load_does_not_treat_empty_v2_as_legacy_fallback(
        self,
    ) -> None:
        from app.core.config_service import ConfigService

        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_path = Path(temp_dir) / "Config.json"
            legacy_path.write_text(
                json.dumps({"Data": {"Value": "keep-legacy"}}),
                encoding="utf-8",
            )
            v2_path = Path(temp_dir) / "Config.v2.toml"
            v2_path.write_text("", encoding="utf-8")

            root = LegacyExampleConfig()
            await root.connect(legacy_path)
            self.assertEqual(root.Data_Value.value, "keep-legacy")

            service = ConfigService()
            try:
                with (
                    patch.object(
                        service,
                        "_legacy_config_roots",
                        return_value=(root,),
                    ),
                    patch("app.core.config_service.CONFIG_V2_MODE", "authoritative"),
                    patch("app.configuration.compat.CONFIG_V2_MODE", "authoritative"),
                ):
                    service._register_legacy_codecs()
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "initialized by NativeConfigFacade",
                    ):
                        await service._authoritative_load()

                self.assertEqual(root.Data_Value.value, "keep-legacy")
                self.assertEqual(v2_path.read_bytes(), b"")
            finally:
                service._unregister_legacy_codecs()

    async def test_save_config_rejects_authoritative_legacy_json_first_write(
        self,
    ) -> None:
        from app.core.config_service import ConfigService

        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_path = Path(temp_dir) / "Config.json"
            root = LegacyExampleConfig()
            await root.connect(legacy_path)
            root.Data_Value.setValue("authoritative-write")

            service = ConfigService()
            try:
                with (
                    patch.object(
                        service,
                        "_legacy_config_roots",
                        return_value=(root,),
                    ),
                    patch("app.core.config_service.CONFIG_V2_MODE", "authoritative"),
                    patch("app.configuration.compat.CONFIG_V2_MODE", "authoritative"),
                    patch(
                        "app.core.config_service.legacy_adapter.shadow_write"
                    ) as shadow_write,
                ):
                    service._register_legacy_codecs()
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "rejects legacy JSON-first saves",
                    ):
                        await service.save_config(
                            legacy_path,
                            {"Data": {"Value": "authoritative-write"}},
                        )

                v2_path = legacy_path.with_suffix(".v2.toml")
                self.assertFalse(v2_path.exists())
                shadow_write.assert_not_called()
            finally:
                service._unregister_legacy_codecs()


if __name__ == "__main__":
    import unittest

    unittest.main()
