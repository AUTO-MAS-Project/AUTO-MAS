"""Config v2 validator and after-commit observer semantics."""

from __future__ import annotations

import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from pydantic import Field

from app.configuration import (
    ConfigAggregateError,
    ConfigEntry,
    ConfigGroup,
    FieldChangeEvent,
    config_manager,
)


class SignalGroup(ConfigGroup):
    first: int = 1
    second: int = 2


class SignalEntry(ConfigEntry):
    settings: SignalGroup = Field(default_factory=SignalGroup)


class TestPreCommitValidatorOwnership(IsolatedAsyncioTestCase):
    async def test_legacy_connect_is_deprecated_validator_alias(self) -> None:
        entry = SignalEntry()
        await entry.activate()

        async def reject(
            _sender: object,
            _event: FieldChangeEvent,
        ) -> None:
            raise RuntimeError("rejected")

        with self.assertWarns(DeprecationWarning):
            entry.connect(reject, group="settings", field="first")
        entry.settings.first = 10
        with self.assertRaises(ConfigAggregateError):
            await entry.commit()

        with self.assertWarns(DeprecationWarning):
            entry.disconnect(reject, group="settings", field="first")
        entry.settings.first = 11
        await entry.commit()
        self.assertEqual(entry.settings.first, 11)

    async def test_validator_timeout_does_not_cancel_shared_task(self) -> None:
        entry = SignalEntry()
        await entry.activate()
        release_shared = asyncio.Event()

        async def shared_work() -> None:
            await release_shared.wait()

        shared_task = asyncio.create_task(shared_work())

        def return_shared_task(
            _sender: object,
            event: FieldChangeEvent,
        ) -> asyncio.Task[None] | None:
            if event.field == "first":
                return shared_task
            return None

        entry.connect_validator(
            return_shared_task,
            group="settings",
            field="first",
        )
        entry.settings.first = 10

        try:
            with (
                patch(
                    "app.configuration.v2.signals."
                    "SIGNAL_CALLBACK_TIMEOUT_SECONDS",
                    0.02,
                ),
                self.assertRaisesRegex(
                    ConfigAggregateError,
                    "validator timed out",
                ),
            ):
                await entry.commit()

            self.assertFalse(shared_task.cancelled())
            self.assertFalse(shared_task.done())
            self.assertEqual(entry.settings.first, 1)
        finally:
            release_shared.set()
            await shared_task

    async def test_cancelling_commit_does_not_cancel_shared_validator_task(
        self,
    ) -> None:
        entry = SignalEntry()
        await entry.activate()
        validator_started = asyncio.Event()
        release_shared = asyncio.Event()

        async def shared_work() -> None:
            validator_started.set()
            await release_shared.wait()

        shared_task = asyncio.create_task(shared_work())

        def return_shared_task(
            _sender: object,
            _event: FieldChangeEvent,
        ) -> asyncio.Task[None]:
            return shared_task

        entry.connect_validator(
            return_shared_task,
            group="settings",
            field="first",
        )

        async def commit_change() -> None:
            entry.settings.first = 10
            await entry.commit()

        commit_task = asyncio.create_task(commit_change())
        await validator_started.wait()
        commit_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await commit_task

        try:
            self.assertFalse(shared_task.cancelled())
            self.assertEqual(entry.settings.first, 1)
            self.assertEqual(
                len(entry._staged_ops_by_task.get(commit_task, [])),
                1,
            )
        finally:
            release_shared.set()
            await shared_task

    async def test_owned_validator_coroutine_is_finalized_on_timeout(self) -> None:
        entry = SignalEntry()
        await entry.activate()
        finalized = asyncio.Event()
        never = asyncio.Event()

        async def block(
            _sender: object,
            _event: FieldChangeEvent,
        ) -> None:
            try:
                await never.wait()
            finally:
                finalized.set()

        entry.connect_validator(block, group="settings", field="first")
        entry.settings.first = 10

        with (
            patch(
                "app.configuration.v2.signals.SIGNAL_CALLBACK_TIMEOUT_SECONDS",
                0.02,
            ),
            self.assertRaises(ConfigAggregateError),
        ):
            await entry.commit()

        self.assertTrue(finalized.is_set())
        self.assertEqual(entry.settings.first, 1)

    async def test_validator_delegation_is_revoked_after_commit(self) -> None:
        entry = SignalEntry()
        await entry.activate()
        callback_tasks: list[asyncio.Task[object]] = []

        async def capture_task(
            _sender: object,
            _event: FieldChangeEvent,
        ) -> None:
            task = asyncio.current_task()
            assert task is not None
            callback_tasks.append(task)
            self.assertTrue(config_manager.in_transaction)

        entry.connect_validator(
            capture_task,
            group="settings",
            field="first",
        )

        async with config_manager.transaction() as context:
            entry.settings.first = 10
            await entry.commit()

        self.assertEqual(len(callback_tasks), 1)
        self.assertTrue(callback_tasks[0].done())
        self.assertEqual(context.delegated_tasks, set())

    async def test_owned_zero_sleep_coroutine_is_finalized_on_timeout(
        self,
    ) -> None:
        entry = SignalEntry()
        await entry.activate()
        finalized = asyncio.Event()

        async def yield_forever(
            _sender: object,
            _event: FieldChangeEvent,
        ) -> None:
            try:
                while True:
                    await asyncio.sleep(0)
            finally:
                finalized.set()

        entry.connect_validator(
            yield_forever,
            group="settings",
            field="first",
        )
        entry.settings.first = 10

        with (
            patch(
                "app.configuration.v2.signals."
                "SIGNAL_CALLBACK_TIMEOUT_SECONDS",
                0.02,
            ),
            self.assertRaises(ConfigAggregateError),
        ):
            await entry.commit()

        self.assertTrue(finalized.is_set())
        self.assertEqual(entry.settings.first, 1)

    async def test_sync_validator_cancelled_error_is_validation_failure(
        self,
    ) -> None:
        entry = SignalEntry()
        await entry.activate()

        def cancel(
            _sender: object,
            _event: FieldChangeEvent,
        ) -> None:
            raise asyncio.CancelledError

        entry.connect_validator(cancel, group="settings", field="first")
        entry.settings.first = 10

        with self.assertRaisesRegex(
            ConfigAggregateError,
            "validator raised CancelledError",
        ):
            await entry.commit()
        self.assertEqual(entry.settings.first, 1)


class TestAfterCommitObserverSemantics(IsolatedAsyncioTestCase):
    async def test_observer_registration_uses_transaction_workspace(
        self,
    ) -> None:
        entry = SignalEntry()
        await entry.activate()
        calls: list[int] = []

        async def observer(
            _sender: object,
            event: FieldChangeEvent,
        ) -> None:
            calls.append(int(event.value))

        with self.assertRaises(RuntimeError):
            async with config_manager.transaction():
                entry.connect_observer(
                    observer,
                    group="settings",
                    field="first",
                )
                raise RuntimeError("rollback registration")

        entry.settings.first = 10
        await entry.commit()
        self.assertEqual(calls, [])

        async with config_manager.transaction():
            entry.connect_observer(
                observer,
                group="settings",
                field="first",
            )

        entry.settings.first = 11
        await entry.commit()
        self.assertEqual(calls, [11])

    async def test_observer_runs_after_unlock_and_can_reenter(self) -> None:
        entry = SignalEntry()
        await entry.activate()
        observations: list[tuple[bool, bool, int]] = []

        async def observer(
            _sender: object,
            event: FieldChangeEvent,
        ) -> None:
            lock = entry._commit_lock
            observations.append(
                (
                    config_manager.in_transaction,
                    bool(lock and lock.locked()),
                    entry.settings.first,
                )
            )
            if event.field == "first":
                entry.settings.second = 20
                await entry.commit()

        entry.connect_observer(observer, group="settings")
        entry.settings.first = 10
        await asyncio.wait_for(entry.commit(), timeout=1.0)

        self.assertEqual(entry.settings.first, 10)
        self.assertEqual(entry.settings.second, 20)
        self.assertEqual(
            observations,
            [(False, False, 10), (False, False, 10)],
        )

    async def test_observer_exception_and_timeout_do_not_rollback(self) -> None:
        entry = SignalEntry()
        await entry.activate()
        slow_finalized = asyncio.Event()
        later_called = asyncio.Event()
        never = asyncio.Event()

        async def fail(
            _sender: object,
            _event: FieldChangeEvent,
        ) -> None:
            raise RuntimeError("observer failed")

        async def slow(
            _sender: object,
            _event: FieldChangeEvent,
        ) -> None:
            try:
                await never.wait()
            finally:
                slow_finalized.set()

        async def later(
            _sender: object,
            _event: FieldChangeEvent,
        ) -> None:
            later_called.set()

        entry.connect_observer(fail, group="settings", field="first")
        entry.connect_observer(slow, group="settings", field="first")
        entry.connect_observer(later, group="settings", field="first")
        entry.settings.first = 10

        with patch(
            "app.configuration.v2.signals."
            "OBSERVER_CALLBACK_TIMEOUT_SECONDS",
            0.02,
        ):
            await entry.commit()

        self.assertEqual(entry.settings.first, 10)
        self.assertTrue(slow_finalized.is_set())
        self.assertTrue(later_called.is_set())

    async def test_outer_transaction_exposes_structured_observer_report(
        self,
    ) -> None:
        entry = SignalEntry()
        await entry.activate()

        async def fail(
            _sender: object,
            _event: FieldChangeEvent,
        ) -> None:
            raise RuntimeError("do not expose this detail")

        entry.connect_observer(fail, group="settings", field="first")

        async with config_manager.transaction() as context:
            entry.settings.first = 10
            await entry.commit()

        self.assertEqual(len(context.observer_reports), 1)
        report = context.observer_reports[0]
        self.assertEqual(report.transaction_id, context.transaction_id)
        self.assertEqual(report.revision, context.revision)
        self.assertEqual(report.event_kind, "set")
        self.assertEqual(len(report.results), 1)
        self.assertEqual(report.results[0].outcome, "failed")
        self.assertEqual(report.results[0].error_type, "RuntimeError")
        self.assertNotIn("do not expose this detail", repr(report))

    async def test_shared_observer_task_survives_timeout(self) -> None:
        entry = SignalEntry()
        await entry.activate()
        release_shared = asyncio.Event()

        async def shared_work() -> None:
            await release_shared.wait()

        shared_task = asyncio.create_task(shared_work())

        def return_shared_task(
            _sender: object,
            _event: FieldChangeEvent,
        ) -> asyncio.Task[None]:
            return shared_task

        entry.connect_observer(
            return_shared_task,
            group="settings",
            field="first",
        )
        entry.settings.first = 10

        try:
            with patch(
                "app.configuration.v2.signals."
                "OBSERVER_CALLBACK_TIMEOUT_SECONDS",
                0.02,
            ):
                await entry.commit()

            self.assertEqual(entry.settings.first, 10)
            self.assertFalse(shared_task.cancelled())
            self.assertFalse(shared_task.done())
        finally:
            release_shared.set()
            await shared_task

    async def test_cancelling_observer_wait_keeps_commit_and_joins_owned_task(
        self,
    ) -> None:
        entry = SignalEntry()
        await entry.activate()
        observer_started = asyncio.Event()
        observer_finalized = asyncio.Event()
        never = asyncio.Event()

        async def block(
            _sender: object,
            _event: FieldChangeEvent,
        ) -> None:
            observer_started.set()
            try:
                await never.wait()
            finally:
                observer_finalized.set()

        entry.connect_observer(block, group="settings", field="first")

        async def commit_change() -> None:
            entry.settings.first = 10
            await entry.commit()

        commit_task = asyncio.create_task(commit_change())
        await observer_started.wait()
        commit_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await commit_task

        self.assertEqual(entry.settings.first, 10)
        self.assertTrue(observer_finalized.is_set())
        self.assertEqual(entry._staged_ops_by_task.get(commit_task, []), [])

    async def test_sync_observer_cancelled_error_is_reported_as_failure(
        self,
    ) -> None:
        entry = SignalEntry()
        await entry.activate()

        def cancel(
            _sender: object,
            _event: FieldChangeEvent,
        ) -> None:
            raise asyncio.CancelledError

        entry.connect_observer(cancel, group="settings", field="first")
        async with config_manager.transaction() as context:
            entry.settings.first = 10
            await entry.commit()

        self.assertEqual(entry.settings.first, 10)
        self.assertEqual(len(context.observer_reports), 1)
        self.assertEqual(
            context.observer_reports[0].results[0].error_type,
            "CancelledError",
        )
