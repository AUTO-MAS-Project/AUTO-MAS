"""快速激活的工作区验证；本地一次性验证产物，不纳入实现提交。"""

import asyncio
import threading
import unittest
from contextvars import copy_context
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from pydantic import Field, model_validator

from app.config import (
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    collection,
    config_manager,
)
from app.config.errors import ConfigAggregateError
from app.utils.io import read_dict_file


class Numbers(ConfigGroup):
    A: int = Field(default=0, ge=0, le=10)
    B: int = Field(default=0, ge=0, le=10)


class Child(ConfigEntry):
    Info: Numbers = Field(default_factory=Numbers)


class Parent(Child):
    Children: ConfigCollection[Child] = collection(Child)


class FastActivationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_roots = list(config_manager.iter_persist_roots())
        self.debounce = config_manager._debounce_seconds
        config_manager._debounce_seconds = 3600

    async def asyncTearDown(self):
        for node in list(config_manager.iter_persist_roots()):
            if all(node is not old for old in self.original_roots):
                config_manager.unregister_root(node)
        config_manager._debounce_seconds = self.debounce
        self.assertFalse(config_manager.in_fast_activation)
        self.assertIsNone(config_manager.current)

    async def test_success_preserves_live_identity_and_signal_prefix(self):
        for fast in (False, True):
            node = Child.build(payload={"Info": {"A": 2, "B": 3}})
            held = node.Info
            storage = held.__dict__
            observations = []

            def receive(sender, event):
                observations.append((event.field, sender.Info.A, sender.Info.B))

            node.connect(receive, phase="init", group="Info")
            await node.activate(try_fast=fast)
            self.assertEqual(observations, [("A", 2, 0), ("B", 2, 3)])
            self.assertIs(node.Info, held)
            self.assertIs(held.__dict__, storage)
            self.assertEqual((held.A, held.B), (2, 3))
            self.assertIsNone(node._workspace)

    async def test_strict_sequential_model_validation_is_preserved(self):
        class OrderedFields(ConfigGroup):
            A: int = 0
            B: int = 5

            @model_validator(mode="after")
            def ordered(self):
                if self.A > self.B:
                    raise ValueError("A must not exceed B")
                return self

        class Ordered(ConfigEntry):
            Info: OrderedFields = Field(default_factory=OrderedFields)

        for fast in (False, True):
            node = Ordered.build(payload={"Info": {"A": 7, "B": 8}})
            with self.assertRaises(ConfigAggregateError):
                await node.activate(try_fast=fast)
            self.assertEqual((node.Info.A, node.Info.B), (0, 8))

    async def test_fast_attempt_exits_before_peer_modification(self):
        peer = Child.build()
        await peer.activate()
        node = Child.build(payload={"Info": {"A": 2, "B": 100}})
        held = node.Info
        observed = []

        async def receive(sender, event):
            observed.append((config_manager.in_fast_activation, peer.Info.A))
            peer.Info.A = 5
            await peer.commit()

        node.connect(receive, phase="init", group="Info", field="A")
        with self.assertRaises(ConfigAggregateError):
            await node.activate(try_fast=True)
        self.assertEqual(observed, [(True, 0), (False, 0)])
        self.assertEqual((node.Info.A, node.Info.B, peer.Info.A), (2, 0, 5))
        self.assertIs(node.Info, held)
        self.assertIsNone(peer._workspace)

    async def test_same_node_init_reentry_remains_rejected(self):
        for fast in (False, True):
            node = Child.build(payload={"Info": {"A": 2}})

            async def receive(sender, event):
                sender.Info.B = 7
                await sender.commit()

            node.connect(receive, phase="init", group="Info", field="A")
            with self.assertRaises(ConfigAggregateError):
                await node.activate(try_fast=fast)
            self.assertEqual((node.Info.A, node.Info.B), (0, 0))

    async def test_uncommitted_peer_stage_cannot_cross_field_boundary(self):
        for fast in (False, True):
            peer = Child.build()
            await peer.activate()
            node = Child.build(payload={"Info": {"A": 2, "B": 3}})

            def stage(sender, event):
                peer.Info.A = 5

            async def consume(sender, event):
                await peer.commit()

            node.connect(stage, phase="init", group="Info", field="A")
            node.connect(consume, phase="init", group="Info", field="B")
            with self.assertRaises(ConfigAggregateError):
                await node.activate(try_fast=fast)
            self.assertEqual((node.Info.A, node.Info.B, peer.Info.A), (0, 3, 0))

    async def test_child_tasks_and_threads_cannot_inherit_fast_ownership(self):
        node = Child.build(payload={"Info": {"A": 2}})
        observed = []
        contexts = []
        fast_contexts = []

        def read():
            return (
                node.Info.A,
                config_manager.in_transaction,
                config_manager.in_fast_activation,
            )

        async def receive(sender, event):
            contexts.append(copy_context())
            fast_contexts.append(config_manager._current_fast_init())
            observed.append(await asyncio.create_task(async_read()))
            observed.append(await asyncio.to_thread(read))

        async def async_read():
            return read()

        node.connect(receive, phase="init", group="Info", field="A")
        await node.activate(try_fast=True)
        self.assertEqual(observed, [(0, False, False), (0, False, False)])
        self.assertEqual(contexts[0].run(read), (2, False, False))
        self.assertFalse(fast_contexts[0].context.active)
        self.assertIs(fast_contexts[0].node, node)
        self.assertIsNone(fast_contexts[0].error)

    async def test_nested_init_may_update_parent_after_parent_field_operation(self):
        for fast in (False, True):
            uid = uuid4()
            node = Parent.build(
                payload={
                    "Children": {
                        "order": [{"uid": str(uid), "type": "Child"}],
                        "data": {str(uid): {"Info": {"A": 3}}},
                    }
                }
            )
            held = node.Children

            async def receive(sender, event):
                if sender.parent is held:
                    node.Info.A = 4
                    await node.commit()

            Child.connect(receive, phase="init", group="Info", field="A")
            try:
                await node.activate(try_fast=fast)
            finally:
                Child.disconnect(receive, phase="init", group="Info", field="A")
            self.assertIs(node.Children, held)
            self.assertEqual((node.Info.A, node.Children[uid].Info.A), (4, 3))

    async def test_cancellation_does_not_fallback_or_leak_state(self):
        node = Child.build(payload={"Info": {"A": 2}})
        pending = node._pending_payload
        entered = asyncio.Event()
        calls = []

        async def receive(sender, event):
            calls.append(config_manager.in_fast_activation)
            entered.set()
            await asyncio.Event().wait()

        node.connect(receive, phase="init", group="Info", field="A")
        task = asyncio.create_task(node.activate(try_fast=True))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(calls, [True])
        self.assertEqual(node.activation_state.value, "inactive")
        self.assertEqual(node.Info.A, 0)
        self.assertIsNone(node._workspace)
        self.assertIs(node._pending_payload, pending)

    async def test_failed_attempt_does_not_save_or_increment_revision(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "root.yaml"
            raw = b"Info: {A: 2, B: 100}\n"
            path.write_bytes(raw)
            node = Child.build(file=path)
            observed = []

            def receive(sender, event):
                observed.append(
                    (
                        config_manager.in_fast_activation,
                        config_manager._roots[node.uid].revision,
                        path.read_bytes(),
                    )
                )

            node.connect(receive, phase="init", group="Info", field="A")
            with self.assertRaises(ConfigAggregateError):
                await node.activate(try_fast=True)
            self.assertEqual(observed, [(True, 0, raw), (False, 0, raw)])
            self.assertEqual(config_manager._roots[node.uid].revision, 1)
            await config_manager.flush()
            self.assertEqual(read_dict_file(path)["Info"], {"A": 2, "B": 0})

    async def test_lifecycle_executes_once_outside_field_attempt(self):
        seen = []
        marker = object()

        class MetadataParent(Parent):
            async def _activate_from_payload(self, payload, *, regenerate_uuids=False):
                if config_manager.in_fast_activation:
                    self._ref_receivers.append(marker)
                else:
                    seen.append(
                        (list(self._ref_receivers), self.Children._pending_payload)
                    )
                await super()._activate_from_payload(
                    payload, regenerate_uuids=regenerate_uuids
                )

        uid = uuid4()
        payload = {
            "Children": {
                "order": [{"uid": str(uid), "type": "Child"}],
                "data": {str(uid): {"Info": {"B": 100}}},
            }
        }
        node = MetadataParent.build(payload=payload)
        held = node.Children
        with self.assertRaises(ConfigAggregateError):
            await node.activate(try_fast=True)
        self.assertEqual(seen, [([], None)])
        self.assertIs(node.Children, held)
        self.assertNotIn(marker, node._ref_receivers)
        self.assertEqual(len(node.Children), 0)

    async def test_signal_subscription_is_rolled_back_before_retry(self):
        node = Child.build(payload={"Info": {"A": 2, "B": 100}})
        hits = []

        def late(sender, event):
            hits.append(event.value)

        def subscribe(sender, event):
            node.connect(late, group="Info", field="B")

        node.connect(subscribe, phase="init", group="Info", field="A")
        with self.assertRaises(ConfigAggregateError):
            await node.activate(try_fast=True)
        self.assertEqual(node.Info.A, 2)
        node.Info.B = 3
        await node.commit()
        self.assertEqual(hits, [3])

    async def test_existing_transaction_uses_original_path_and_rolls_back(self):
        node = Child.build(payload={"Info": {"A": 2}})
        observed = []

        def receive(sender, event):
            observed.append(config_manager.in_fast_activation)

        node.connect(receive, phase="init", group="Info", field="A")
        with self.assertRaises(ValueError):
            async with config_manager.transaction():
                await node.activate(try_fast=True)
                raise ValueError("caller rollback")
        self.assertEqual(observed, [False])
        self.assertEqual(node.activation_state.value, "inactive")
        self.assertEqual(node.Info.A, 0)

    async def test_caught_operation_error_aborts_fast_attempt(self):
        peer = Child.build()
        await peer.activate()
        node = Child.build(payload={"Info": {"A": 2, "B": 3}})
        modes = []

        async def receive(sender, event):
            modes.append(config_manager.in_fast_activation)
            try:
                peer.Info.B = 100
                await peer.commit()
            except Exception:
                pass

        node.connect(receive, phase="init", group="Info", field="A")
        await node.activate(try_fast=True)
        self.assertEqual(modes, [True, False])
        self.assertEqual((node.Info.A, node.Info.B, peer.Info.B), (2, 3, 0))

    async def test_commit_failure_does_not_retry_activation(self):
        node = Child.build(payload={"Info": {"A": 2}})
        modes = []

        def receive(sender, event):
            modes.append(config_manager.in_fast_activation)

        node.connect(receive, phase="init", group="Info", field="A")
        with patch.object(
            config_manager, "COMMIT", side_effect=OSError("commit failed")
        ):
            with self.assertRaises(OSError):
                await node.activate(try_fast=True)
        self.assertEqual(modes, [True])
        self.assertEqual(node.activation_state.value, "inactive")

    async def test_fast_context_cleanup_failure_does_not_retry(self):
        node = Child.build(payload={"Info": {"A": 2}})
        modes = []
        original = config_manager._close_context

        def receive(sender, event):
            modes.append(config_manager.in_fast_activation)

        def close(context):
            fast = config_manager._current_fast_init()
            original(context)
            if fast is not None and fast.context is context:
                raise OSError("cleanup failed")

        node.connect(receive, phase="init", group="Info", field="A")
        with patch.object(config_manager, "_close_context", side_effect=close):
            with self.assertRaises(OSError):
                await node.activate(try_fast=True)
        self.assertEqual(modes, [True])
        self.assertEqual(node.activation_state.value, "inactive")

    async def test_locks_require_completed_activation(self):
        for fast in (False, True):
            node = Child.build(payload={"Info": {"A": 2}})
            with self.assertRaises(ValueError):
                await node.lock_s()
            with self.assertRaises(ValueError):
                await node.lock_x()
            self.assertIsNone(await node.try_lock_x())
            await node.activate(try_fast=fast)
            shared = await node.lock_s()
            try:
                with self.assertRaises(ValueError):
                    node.Info.A = 3
                    await node.commit()
                self.assertEqual(node.Info.A, 2)
            finally:
                await node.unlock(shared)
            exclusive = await node.lock_x()
            try:
                node.Info.A = 3
                await node.commit()
                self.assertEqual(node.Info.A, 3)
            finally:
                await node.unlock(exclusive)

    async def test_fast_success_builds_one_init_workspace(self):
        for fast, expected in ((False, 2), (True, 1)):
            node = Child.build(payload={"Info": {"A": 2, "B": 3}})
            builds = []
            original = Child._make_workspace_shell

            def build(sender, *, init=False):
                builds.append(init)
                return original(sender, init=init)

            with patch.object(Child, "_make_workspace_shell", build):
                await node.activate(try_fast=fast)
            self.assertEqual(builds.count(True), expected)
            self.assertEqual(builds.count(False), 1)

    async def test_member_and_group_references_survive_later_member_failure(self):
        for fast in (False, True):
            for regenerate in (False, True):
                first, second = uuid4(), uuid4()
                node = ConfigCollection.build(
                    [Child],
                    payload={
                        "order": [
                            {"uid": str(first), "type": "Child"},
                            {"uid": str(second), "type": "Child"},
                        ],
                        "data": {
                            str(first): {"Info": {"A": 2}},
                            str(second): {"Info": {"B": 100}},
                        },
                    },
                )
                captured = []

                def receive(sender, event):
                    if sender.Info.A == 2:
                        captured.append((sender, sender.Info, sender.Info.__dict__))

                Child.connect(receive, phase="init", group="Info", field="A")
                try:
                    with self.assertRaises(ConfigAggregateError):
                        await node.activate(try_fast=fast, regenerate_uuids=regenerate)
                finally:
                    Child.disconnect(receive, phase="init", group="Info", field="A")
                self.assertEqual(len(captured), 1)
                member, group, storage = captured[0]
                self.assertIs(node[member.uid], member)
                self.assertIs(member.Info, group)
                self.assertIs(group.__dict__, storage)
                self.assertEqual(group.A, 2)
                self.assertEqual(member.activation_state.value, "active")
                self.assertEqual(member.uid != first, regenerate)

    async def test_remove_guard_and_named_collection_register_only_once(self):
        for fast in (False, True):
            target = ConfigCollection.build([Child])
            await target.activate()
            uid = target.add(Child)
            await target.commit()
            name = "FastActivation" + uuid4().hex
            node = Child.build(payload={"Info": {"A": 2, "B": 100}})
            created = []

            async def guard(collection, entry_uid, entry):
                raise ValueError("guarded")

            def receive(sender, event):
                created.append(ConfigCollection.build([Child], name=name))
                target.register_remove_guard(guard)

            node.connect(receive, phase="init", group="Info", field="A")
            with self.assertRaises(ConfigAggregateError):
                await node.activate(try_fast=fast)
            self.assertEqual(node.Info.A, 2)
            self.assertEqual(len(created), 1)
            self.assertIs(config_manager.get_collection(name), created[0])
            target.unregister_remove_guard(guard)
            target.remove(uid)
            await target.commit()
            self.assertNotIn(uid, target)

    async def test_lock_operations_exit_fast_attempt_before_effects(self):
        for operation in ("lock_s", "lock_x", "try_lock_x", "unlock"):
            node = Child.build(payload={"Info": {"A": 2, "B": 100}})
            peer = Child.build()
            await peer.activate()
            ticket = await peer.lock_s() if operation == "unlock" else None
            modes = []
            tickets = []

            async def receive(sender, event):
                modes.append(config_manager.in_fast_activation)
                if operation == "unlock":
                    await peer.unlock(ticket)
                else:
                    tickets.append(await getattr(peer, operation)())

            node.connect(receive, phase="init", group="Info", field="A")
            with self.assertRaises(ConfigAggregateError):
                await node.activate(try_fast=True)
            self.assertEqual(modes, [True, False])
            self.assertEqual(node.Info.A, 2)
            if operation == "unlock":
                self.assertFalse(peer.is_locked)
            else:
                self.assertEqual(len(tickets), 1)
                await peer.unlock(tickets[0])
                self.assertFalse(peer.is_locked)

    async def test_root_reregistration_executes_only_once(self):
        with TemporaryDirectory() as directory:
            peer = Child.build(file=Path(directory) / "peer.yaml")
            await peer.activate()
            node = Child.build(payload={"Info": {"A": 2, "B": 100}})

            def receive(sender, event):
                path = peer.persist_path
                config_manager.register_root(peer, path.with_name("copy-" + path.name))

            node.connect(receive, phase="init", group="Info", field="A")
            with self.assertRaises(ConfigAggregateError):
                await node.activate(try_fast=True)
            self.assertEqual(peer.persist_path.name, "copy-peer.yaml")
            self.assertEqual(node.Info.A, 2)

    async def test_independent_task_cannot_lock_initializing_node(self):
        for fast in (False, True):
            for operation in ("lock_s", "lock_x", "try_lock_x"):
                node = Child.build(payload={"Info": {"A": 2, "B": 3}})
                entered, checked = asyncio.Event(), asyncio.Event()
                errors = []

                async def receive(sender, event):
                    entered.set()
                    await checked.wait()

                async def acquire():
                    await entered.wait()
                    try:
                        ticket = await getattr(node, operation)()
                        self.assertIsNone(ticket)
                    except ValueError:
                        errors.append(operation)
                    finally:
                        checked.set()

                node.connect(receive, phase="init", group="Info", field="A")
                task = asyncio.create_task(acquire())
                await node.activate(try_fast=fast)
                await task
                self.assertEqual((node.Info.A, node.Info.B), (2, 3))
                self.assertFalse(node.is_locked)
                self.assertEqual(len(errors), 0 if operation == "try_lock_x" else 1)
                ticket = await getattr(node, operation)()
                self.assertIsNotNone(ticket)
                await node.unlock(ticket)

    async def test_thread_cannot_lock_during_validation_without_signals(self):
        for fast in (False, True):
            entered, checked = threading.Event(), threading.Event()
            results = []

            class Fields(ConfigGroup):
                A: int = 0
                B: int = 0

                @model_validator(mode="after")
                def coordinate(self):
                    if self.A == 2:
                        entered.set()
                        if not checked.wait(5):
                            raise RuntimeError("thread did not finish")
                    return self

            class ThreadNode(ConfigEntry):
                Info: Fields = Field(default_factory=Fields)

            node = ThreadNode.build(payload={"Info": {"A": 2, "B": 3}})

            def acquire():
                if not entered.wait(5):
                    return
                try:
                    asyncio.run(node.lock_s())
                except ValueError:
                    results.append("rejected")
                finally:
                    checked.set()

            thread = threading.Thread(target=acquire)
            thread.start()
            try:
                await node.activate(try_fast=fast)
            finally:
                thread.join(timeout=5)
            self.assertEqual(results, ["rejected"])
            self.assertEqual((node.Info.A, node.Info.B), (2, 3))
            self.assertFalse(node.is_locked)

    async def test_recursive_members_share_readiness_until_root_commits(self):
        for fast in (False, True):
            first, second = uuid4(), uuid4()
            root = ConfigCollection.build(
                [Child],
                payload={
                    "order": [
                        {"uid": str(first), "type": "Child"},
                        {"uid": str(second), "type": "Child"},
                    ],
                    "data": {str(first): {"Info": {"A": 2}}},
                },
            )
            seen = []

            async def receive(sender, event):
                member = event.entry
                lifecycle = member.effective._activation_lifecycle
                self.assertIs(lifecycle, root.effective._activation_lifecycle)
                self.assertEqual(member.activation_state.value, "active")
                self.assertFalse(member._activation_ready)
                with self.assertRaises(ValueError):
                    await member.lock_s()
                self.assertIsNone(await member.try_lock_x())
                with self.assertRaises(ValueError):
                    await member.to_dict()
                with self.assertRaises(ValueError):
                    member.Info.B = 3
                seen.append(lifecycle)

            root.connect(receive, phase="init", kind="add")
            await root.activate(try_fast=fast)
            self.assertEqual(len(seen), 2)
            self.assertIs(seen[0], seen[1])
            self.assertTrue(seen[0].finished)
            self.assertTrue(seen[0].complete)
            for member in root.values():
                self.assertTrue(member._activation_ready)
                ticket = await member.lock_s()
                await member.unlock(ticket)

    async def test_runtime_add_has_its_own_transactional_lifecycle(self):
        root = ConfigCollection.build([Parent])
        await root.activate()
        old_lifecycle = root._activation_lifecycle
        captured = []

        async def receive(sender, event):
            member = event.entry
            lifecycle = member.effective._activation_lifecycle
            captured.append((member, lifecycle))
            self.assertIsNot(lifecycle, old_lifecycle)
            self.assertIs(lifecycle, member.Children.effective._activation_lifecycle)
            self.assertTrue(root._activation_ready)
            self.assertFalse(member._activation_ready)
            self.assertFalse(member.Children._activation_ready)
            with self.assertRaises(ValueError):
                await member.Children.lock_x()

        root.connect(receive, kind="add")
        uid = root.add(Parent)
        await root.commit()
        member, lifecycle = captured[0]
        self.assertIs(member, root[uid])
        self.assertTrue(lifecycle.complete)
        self.assertTrue(member._activation_ready)
        self.assertTrue(member.Children._activation_ready)

    async def test_lifecycle_rollback_does_not_reopen_abandoned_marker(self):
        node = Parent.build()
        with self.assertRaises(RuntimeError):
            async with config_manager.transaction():
                await node.activate(try_fast=True)
                lifecycle = node.effective._activation_lifecycle
                self.assertTrue(lifecycle.finished)
                self.assertFalse(lifecycle.complete)
                self.assertFalse(node._activation_ready)
                with self.assertRaises(ValueError):
                    await node.lock_x()
                raise RuntimeError("rollback")
        self.assertIsNone(node._activation_lifecycle)
        self.assertIsNone(node.Children._activation_lifecycle)
        self.assertFalse(lifecycle.finished)
        self.assertFalse(lifecycle.complete)
        await node.activate(try_fast=True)
        self.assertIsNot(node._activation_lifecycle, lifecycle)
        self.assertTrue(node._activation_ready)
        self.assertFalse(lifecycle.complete)

    async def test_foreign_task_cannot_mutate_shared_metadata_during_activation(self):
        with TemporaryDirectory() as directory:
            peer = Child.build(file=Path(directory) / "old.yaml")
            await peer.activate()
            target = ConfigCollection.build([Child])
            await target.activate()
            entered, checked = asyncio.Event(), asyncio.Event()
            errors, hits = [], []

            def receiver(sender, event):
                hits.append(event.value)

            async def guard(collection, entry_uid, entry):
                pass

            peer.connect(receiver, group="Info", field="B")
            target.register_remove_guard(guard)
            name = "ForeignMetadata" + uuid4().hex
            source = Child.build(payload={"Info": {"A": 2, "B": 3}})

            async def receive(sender, event):
                entered.set()
                await checked.wait()

            def late(sender, event):
                hits.append("late")

            async def modify():
                await entered.wait()
                operations = [
                    lambda: config_manager.register_root(
                        peer, Path(directory) / "new.yaml"
                    ),
                    lambda: config_manager.unregister_root(peer),
                    lambda: config_manager.register_collection(name, target),
                    lambda: peer.connect(late),
                    lambda: peer.disconnect(receiver, group="Info", field="B"),
                    lambda: target.register_remove_guard(guard),
                    lambda: target.unregister_remove_guard(guard),
                ]
                try:
                    for operation in operations:
                        try:
                            operation()
                        except RuntimeError:
                            errors.append("busy")
                finally:
                    checked.set()

            source.connect(receive, phase="init", group="Info", field="A")
            task = asyncio.create_task(modify())
            await source.activate(try_fast=True)
            await task
            self.assertEqual(len(errors), 7)
            self.assertEqual(peer.persist_path.name, "old.yaml")
            with self.assertRaises(LookupError):
                config_manager.get_collection(name)
            self.assertEqual(len(target._remove_guards), 1)
            peer.Info.B = 3
            await peer.commit()
            self.assertEqual(hits, [3])

    async def test_thread_metadata_change_waits_until_activation_and_retry_finish(self):
        for fast in (False, True):
            with TemporaryDirectory() as directory:
                peer = Child.build(file=Path(directory) / "old.yaml")
                await peer.activate()
                entered, attempted = threading.Event(), threading.Event()
                completed = threading.Event()

                class Fields(ConfigGroup):
                    A: str = ""
                    B: int = Field(default=0, le=10)

                    @model_validator(mode="after")
                    def derive(self):
                        if self.A == "derive":
                            self.__dict__["A"] = peer.persist_path.name
                        return self

                class Source(ConfigEntry):
                    Info: Fields = Field(default_factory=Fields)

                node = Source.build(payload={"Info": {"A": "derive", "B": 100}})

                async def receive(sender, event):
                    entered.set()
                    self.assertTrue(await asyncio.to_thread(attempted.wait, 5))
                    self.assertFalse(completed.is_set())

                def modify():
                    if not entered.wait(5):
                        return
                    attempted.set()
                    config_manager.register_root(peer, Path(directory) / "new.yaml")
                    completed.set()

                node.connect(receive, phase="init", group="Info", field="A")
                thread = threading.Thread(target=modify)
                thread.start()
                try:
                    with self.assertRaises(ConfigAggregateError):
                        await node.activate(try_fast=fast)
                finally:
                    thread.join(timeout=5)
                self.assertTrue(completed.is_set())
                self.assertEqual(node.Info.A, "old.yaml")
                self.assertEqual(peer.persist_path.name, "new.yaml")
