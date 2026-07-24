"""Config v2 complete-generation coordination tests."""

from __future__ import annotations

import asyncio
import tempfile
import tomllib
import unittest
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar
from unittest.mock import patch
from uuid import UUID

from pydantic import Field

from app.configuration.persistence.coordinator import (
    ConfigGenerationCoordinator,
    RootDecodeError,
    RootSchemaError,
    RootSnapshotError,
)
from app.configuration.persistence.generation_store import (
    AtomicGenerationStore,
    GenerationConflictError,
    NoCommittedGenerationError,
)
from app.configuration.v2.entry import ConfigEntry
from app.configuration.v2.group import ConfigGroup
from app.configuration.v2.manager import config_manager


class _ValueGroup(ConfigGroup):
    value: str = ""


class _AlphaRoot(ConfigEntry):
    settings: _ValueGroup = Field(default_factory=_ValueGroup)
    export_flags: ClassVar[list[tuple[bool, bool]]] = []

    async def to_dict(
        self,
        *,
        if_decrypt: bool = False,
        include_reactive: bool = False,
    ) -> dict[str, object]:
        type(self).export_flags.append((if_decrypt, include_reactive))
        return await super().to_dict(
            if_decrypt=if_decrypt,
            include_reactive=include_reactive,
        )


class _BetaRoot(ConfigEntry):
    settings: _ValueGroup = Field(default_factory=_ValueGroup)


class _FailingRoot(ConfigEntry):
    settings: _ValueGroup = Field(default_factory=_ValueGroup)

    async def to_dict(
        self,
        *,
        if_decrypt: bool = False,
        include_reactive: bool = False,
    ) -> dict[str, object]:
        del if_decrypt, include_reactive
        raise RuntimeError("plain-and-cipher-secret-must-not-leak")


class _BlockingAlphaRoot(_AlphaRoot):
    export_started: ClassVar[asyncio.Event | None] = None
    export_release: ClassVar[asyncio.Event | None] = None

    async def to_dict(
        self,
        *,
        if_decrypt: bool = False,
        include_reactive: bool = False,
    ) -> dict[str, object]:
        payload = await super().to_dict(
            if_decrypt=if_decrypt,
            include_reactive=include_reactive,
        )
        if type(self).export_started is None or type(self).export_release is None:
            raise RuntimeError("blocking export events are not configured")
        type(self).export_started.set()
        await type(self).export_release.wait()
        return payload


class GenerationCoordinatorTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        _AlphaRoot.export_flags.clear()
        _BlockingAlphaRoot.export_started = None
        _BlockingAlphaRoot.export_release = None

    async def _active_roots(
        self,
        *,
        alpha: str = "alpha",
        beta: str = "beta",
    ) -> dict[str, ConfigEntry]:
        alpha_root = _AlphaRoot(
            wire={"settings": {"value": alpha}},
        )
        beta_root = _BetaRoot(
            wire={"settings": {"value": beta}},
        )
        await alpha_root.activate()
        await beta_root.activate()
        return {"Alpha": alpha_root, "Beta": beta_root}

    @staticmethod
    def _coordinator(
        directory: Path,
    ) -> tuple[AtomicGenerationStore, ConfigGenerationCoordinator]:
        store = AtomicGenerationStore(
            directory,
            required_roots=("Alpha", "Beta"),
        )
        coordinator = ConfigGenerationCoordinator(
            store,
            required_roots=("Beta", "Alpha"),
            schema={"Alpha": _AlphaRoot, "Beta": _BetaRoot},
        )
        return store, coordinator

    async def test_snapshot_and_commit_publish_one_complete_generation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, coordinator = self._coordinator(Path(temp_dir) / "store")
            roots = await self._active_roots(
                alpha="ciphertext-alpha",
                beta="ciphertext-beta",
            )

            captured = await coordinator.snapshot(roots)
            self.assertEqual(captured.required_roots, ("Alpha", "Beta"))
            self.assertEqual(
                tomllib.loads(captured.roots["Alpha"].decode("utf-8")),
                {"settings": {"value": "ciphertext-alpha"}},
            )
            self.assertEqual(_AlphaRoot.export_flags, [(False, False)])

            transaction_id = UUID("11111111-1111-4111-8111-111111111111")
            committed = await coordinator.commit(
                roots,
                expected_generation=None,
                expected_revision=0,
                transaction_id=transaction_id,
            )

            self.assertEqual(set(committed.roots), {"Alpha", "Beta"})
            self.assertEqual(committed.transaction_id, transaction_id.hex)
            self.assertEqual(
                store.read_current().generation,
                committed.generation,
            )

    async def test_commit_keeps_strict_cas_and_idempotent_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _, coordinator = self._coordinator(Path(temp_dir) / "store")
            roots = await self._active_roots()
            transaction_id = UUID("22222222-2222-4222-8222-222222222222")
            first = await coordinator.commit(
                roots,
                expected_generation=None,
                expected_revision=0,
                transaction_id=transaction_id,
            )
            retry = await coordinator.commit(
                roots,
                expected_generation=None,
                expected_revision=0,
                transaction_id=transaction_id,
            )
            self.assertEqual(retry.generation, first.generation)
            self.assertEqual(retry.revision, first.revision)

            with self.assertRaises(GenerationConflictError):
                await coordinator.commit(
                    roots,
                    expected_generation=None,
                    expected_revision=0,
                    transaction_id=UUID(
                        "33333333-3333-4333-8333-333333333333"
                    ),
                )

    async def test_snapshot_failure_never_publishes_or_leaks_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(
                Path(temp_dir) / "store",
                required_roots=("Alpha", "Beta"),
            )
            coordinator = ConfigGenerationCoordinator(
                store,
                required_roots=("Alpha", "Beta"),
                schema={"Alpha": _AlphaRoot, "Beta": _FailingRoot},
            )
            alpha = _AlphaRoot(
                wire={"settings": {"value": "already-exported-secret"}},
            )
            failing = _FailingRoot()
            await alpha.activate()
            await failing.activate()

            with self.assertRaises(RootSnapshotError) as captured:
                await coordinator.commit(
                    {"Alpha": alpha, "Beta": failing},
                    expected_generation=None,
                    expected_revision=0,
                    transaction_id=UUID(
                        "44444444-4444-4444-8444-444444444444"
                    ),
                )

            rendered = f"{captured.exception!s} {captured.exception!r}"
            self.assertNotIn("already-exported-secret", rendered)
            self.assertNotIn("plain-and-cipher-secret-must-not-leak", rendered)
            self.assertIsNone(captured.exception.__cause__)
            self.assertIsNone(captured.exception.__context__)
            with self.assertRaises(NoCommittedGenerationError):
                store.read_current()
            async with config_manager.snapshot_barrier():
                pass
            async with config_manager.transaction():
                pass

            barrier_released = asyncio.Event()

            async def enter_transaction() -> None:
                async with config_manager.transaction():
                    barrier_released.set()

            await asyncio.wait_for(enter_transaction(), timeout=1)
            self.assertTrue(barrier_released.is_set())

    async def test_snapshot_rejects_inactive_deleted_and_wrong_schema(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _, coordinator = self._coordinator(Path(temp_dir) / "store")
            active = await self._active_roots()
            inactive = _BetaRoot()
            with self.assertRaises(RootSnapshotError):
                await coordinator.snapshot(
                    {"Alpha": active["Alpha"], "Beta": inactive}
                )

            await inactive.activate()
            async with config_manager.transaction():
                await inactive._delete()
            with self.assertRaises(RootSnapshotError):
                await coordinator.snapshot(
                    {"Alpha": active["Alpha"], "Beta": inactive}
                )

            wrong_type = _AlphaRoot()
            await wrong_type.activate()
            with self.assertRaises(RootSchemaError):
                await coordinator.snapshot(
                    {"Alpha": active["Alpha"], "Beta": wrong_type}
                )

    async def test_constructor_requires_exact_store_and_schema_roots(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(
                Path(temp_dir) / "store",
                required_roots=("Alpha", "Beta"),
            )
            with self.assertRaises(RootSchemaError):
                ConfigGenerationCoordinator(
                    store,
                    required_roots=("Alpha",),
                    schema={"Alpha": _AlphaRoot},
                )
            with self.assertRaises(RootSchemaError):
                ConfigGenerationCoordinator(
                    store,
                    required_roots=("Alpha", "Beta"),
                    schema={"Alpha": _AlphaRoot, "Extra": _BetaRoot},
                )

    async def test_load_current_is_independent_and_payload_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _, coordinator = self._coordinator(Path(temp_dir) / "store")
            roots = await self._active_roots(alpha="secret-in-generation")
            await coordinator.commit(
                roots,
                expected_generation=None,
                expected_revision=0,
                transaction_id=UUID("55555555-5555-4555-8555-555555555555"),
            )

            first = coordinator.load_current()
            self.assertNotIn("secret-in-generation", repr(first))
            first.roots["Alpha"]["settings"]["value"] = "mutated-copy"
            second = coordinator.load_current()
            self.assertEqual(
                second.roots["Alpha"]["settings"]["value"],
                "secret-in-generation",
            )
            self.assertEqual(
                roots["Alpha"].settings.value,  # type: ignore[attr-defined]
                "secret-in-generation",
            )

    async def test_load_current_rejects_corrupt_payloads_fail_closed(
        self,
    ) -> None:
        cases = (
            b"\xff",
            b"secret-value = [",
        )
        for index, raw in enumerate(cases):
            with self.subTest(index=index):
                with tempfile.TemporaryDirectory() as temp_dir:
                    store, coordinator = self._coordinator(
                        Path(temp_dir) / "store"
                    )
                    store.commit(
                        {
                            "Alpha": raw,
                            "Beta": b'[settings]\nvalue = "ok"\n',
                        },
                        expected_generation=None,
                        expected_revision=0,
                        transaction_id=UUID(
                            f"66666666-6666-4666-8666-{index + 1:012d}"
                        ),
                    )
                    with self.assertRaises(RootDecodeError) as captured:
                        coordinator.load_current()
                    rendered = (
                        f"{captured.exception!s} {captured.exception!r}"
                    )
                    self.assertNotIn("secret-value", rendered)
                    self.assertIsNone(captured.exception.__cause__)
                    self.assertIsNone(captured.exception.__context__)

    async def test_load_current_rejects_missing_extra_nonbytes_and_nonobject(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, coordinator = self._coordinator(Path(temp_dir) / "store")
            baseline = store.commit(
                {
                    "Alpha": b'[settings]\nvalue = "a"\n',
                    "Beta": b'[settings]\nvalue = "b"\n',
                },
                expected_generation=None,
                expected_revision=0,
                transaction_id=UUID("77777777-7777-4777-8777-777777777777"),
            )
            invalid_root_sets = (
                {"Alpha": baseline.roots["Alpha"]},
                {
                    **dict(baseline.roots),
                    "Extra": b'[settings]\nvalue = "x"\n',
                },
            )
            for roots in invalid_root_sets:
                with self.subTest(roots=tuple(roots)):
                    invalid = replace(
                        baseline,
                        roots=MappingProxyType(roots),
                    )
                    with patch.object(
                        store,
                        "read_current",
                        return_value=invalid,
                    ):
                        with self.assertRaises(RootDecodeError):
                            coordinator.load_current()

            nonbytes = replace(
                baseline,
                roots=MappingProxyType(
                    {"Alpha": "not-bytes", "Beta": baseline.roots["Beta"]}
                ),
            )
            with patch.object(store, "read_current", return_value=nonbytes):
                with self.assertRaises(RootDecodeError):
                    coordinator.load_current()

            with patch(
                "app.configuration.persistence.coordinator.tomllib.loads",
                return_value=[],
            ):
                with self.assertRaises(RootDecodeError):
                    coordinator.load_current()

    async def test_rollback_delegates_and_returns_complete_decoded_snapshot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, coordinator = self._coordinator(Path(temp_dir) / "store")
            first_roots = await self._active_roots(alpha="first", beta="one")
            first = await coordinator.commit(
                first_roots,
                expected_generation=None,
                expected_revision=0,
                transaction_id=UUID("88888888-8888-4888-8888-888888888888"),
            )
            second_roots = await self._active_roots(alpha="second", beta="two")
            second = await coordinator.commit(
                second_roots,
                expected_generation=first.generation,
                expected_revision=first.revision,
                transaction_id=UUID("99999999-9999-4999-8999-999999999999"),
            )

            rollback_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
            rolled_back = coordinator.rollback(
                first.generation,
                expected_generation=second.generation,
                expected_revision=second.revision,
                transaction_id=rollback_id,
            )

            self.assertEqual(rolled_back.rollback_of, first.generation)
            self.assertEqual(rolled_back.transaction_id, rollback_id.hex)
            self.assertEqual(set(rolled_back.roots), {"Alpha", "Beta"})
            self.assertEqual(
                rolled_back.roots["Alpha"]["settings"]["value"],
                "first",
            )
            self.assertEqual(
                store.read_current().generation,
                rolled_back.generation,
            )

    async def test_commit_barrier_prevents_cross_transaction_mixed_roots(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AtomicGenerationStore(
                Path(temp_dir) / "store",
                required_roots=("Alpha", "Beta"),
            )
            coordinator = ConfigGenerationCoordinator(
                store,
                required_roots=("Alpha", "Beta"),
                schema={"Alpha": _BlockingAlphaRoot, "Beta": _BetaRoot},
            )
            alpha = _BlockingAlphaRoot(
                wire={"settings": {"value": "old-alpha"}},
            )
            beta = _BetaRoot(
                wire={"settings": {"value": "old-beta"}},
            )
            await alpha.activate()
            await beta.activate()
            _BlockingAlphaRoot.export_started = asyncio.Event()
            _BlockingAlphaRoot.export_release = asyncio.Event()
            transaction_entered = asyncio.Event()

            commit_task = asyncio.create_task(
                coordinator.commit(
                    {"Alpha": alpha, "Beta": beta},
                    expected_generation=None,
                    expected_revision=0,
                    transaction_id=UUID(
                        "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
                    ),
                )
            )
            await asyncio.wait_for(
                _BlockingAlphaRoot.export_started.wait(),
                timeout=1,
            )

            async def mutate_both_roots() -> None:
                async with config_manager.transaction():
                    transaction_entered.set()
                    alpha.settings.value = "new-alpha"
                    beta.settings.value = "new-beta"
                    await alpha.commit()
                    await beta.commit()

            mutation_task = asyncio.create_task(mutate_both_roots())
            await asyncio.sleep(0)
            self.assertFalse(transaction_entered.is_set())

            _BlockingAlphaRoot.export_release.set()
            committed = await asyncio.wait_for(commit_task, timeout=2)
            await asyncio.wait_for(mutation_task, timeout=2)

            persisted = coordinator.load_current()
            self.assertEqual(persisted.generation, committed.generation)
            self.assertEqual(
                persisted.roots["Alpha"]["settings"]["value"],
                "old-alpha",
            )
            self.assertEqual(
                persisted.roots["Beta"]["settings"]["value"],
                "old-beta",
            )
            self.assertEqual(alpha.settings.value, "new-alpha")
            self.assertEqual(beta.settings.value, "new-beta")

    async def test_active_transaction_snapshot_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, coordinator = self._coordinator(Path(temp_dir) / "store")
            roots = await self._active_roots()

            async with config_manager.transaction():
                with self.assertRaisesRegex(
                    RuntimeError,
                    "cannot run inside a transaction",
                ):
                    await coordinator.snapshot(roots)
                with self.assertRaisesRegex(
                    RuntimeError,
                    "cannot run inside a transaction",
                ):
                    await coordinator.commit(
                        roots,
                        expected_generation=None,
                        expected_revision=0,
                        transaction_id=UUID(
                            "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
                        ),
                    )

            with self.assertRaises(NoCommittedGenerationError):
                store.read_current()

    async def test_snapshot_barrier_rejects_reentry_and_sync_transaction(
        self,
    ) -> None:
        async with config_manager.transaction() as before:
            pass

        async with config_manager.snapshot_barrier():
            with self.assertRaisesRegex(RuntimeError, "not re-entrant"):
                async with config_manager.snapshot_barrier():
                    self.fail("nested barrier unexpectedly entered")
            with self.assertRaisesRegex(
                RuntimeError,
                "cannot overlap",
            ):
                with config_manager.transaction_sync():
                    self.fail("sync transaction unexpectedly entered")
            with self.assertRaisesRegex(
                RuntimeError,
                "cannot start inside",
            ):
                async with config_manager.transaction():
                    self.fail("async transaction unexpectedly entered")

        async with config_manager.transaction() as after:
            pass
        self.assertEqual(after.revision, before.revision + 1)


if __name__ == "__main__":
    unittest.main()
