import asyncio
import unittest

from app.plugins import EventBus
from app.plugins.event_bus import EventDispatchError


class EventBusTest(unittest.TestCase):
    def setUp(self) -> None:
        self.bus = EventBus()

    def _run(self, coro):
        return asyncio.run(coro)

    def test_emit_dispatches_by_priority_order(self) -> None:
        order: list[str] = []

        async def scenario():
            self.bus.on("task.start", lambda _: order.append("low"), priority=0)
            self.bus.on("task.start", lambda _: order.append("high"), priority=10)
            await self.bus.emit("task.start", {})

        self._run(scenario())
        self.assertEqual(order, ["high", "low"])

    def test_once_listener_removed_after_first_emit(self) -> None:
        hits: list[int] = []

        async def scenario():
            self.bus.on("task.start", lambda _: hits.append(1), once=True)
            await self.bus.emit("task.start", {})
            await self.bus.emit("task.start", {})

        self._run(scenario())
        self.assertEqual(hits, [1])
        self.assertEqual(self.bus.handler_count, {})

    def test_instance_scope_routes_by_instance_id(self) -> None:
        hits: list[str] = []

        async def scenario():
            self.bus.on(
                "script.exit",
                lambda _: hits.append("a"),
                scope="instance",
                owner_instance_id="ins-a",
            )
            self.bus.on(
                "script.exit",
                lambda _: hits.append("b"),
                scope="instance",
                owner_instance_id="ins-b",
            )
            self.bus.on("script.exit", lambda _: hits.append("global"))
            await self.bus.emit(
                "script.exit", {}, scope="instance", source_instance_id="ins-a"
            )

        self._run(scenario())
        self.assertEqual(hits, ["a"])

    def test_global_scope_skips_instance_listeners(self) -> None:
        hits: list[str] = []

        async def scenario():
            self.bus.on(
                "script.exit",
                lambda _: hits.append("instance"),
                scope="instance",
                owner_instance_id="ins-a",
            )
            self.bus.on("script.exit", lambda _: hits.append("global"))
            await self.bus.emit("script.exit", {})

        self._run(scenario())
        self.assertEqual(hits, ["global"])

    def test_continue_policy_swallows_handler_error(self) -> None:
        hits: list[str] = []

        def bad_handler(_):
            raise RuntimeError("boom")

        async def scenario():
            self.bus.on("task.exit", bad_handler, priority=10)
            self.bus.on("task.exit", lambda _: hits.append("ok"))
            await self.bus.emit("task.exit", {}, error_policy="continue")

        self._run(scenario())
        self.assertEqual(hits, ["ok"])

    def test_raise_policy_aggregates_errors(self) -> None:
        def bad_handler(_):
            raise RuntimeError("boom")

        async def scenario():
            self.bus.on("task.exit", bad_handler)
            await self.bus.emit("task.exit", {}, error_policy="raise")

        with self.assertRaises(EventDispatchError):
            self._run(scenario())

    def test_off_by_listener_id(self) -> None:
        hits: list[int] = []

        async def scenario():
            listener_id = self.bus.on("task.start", lambda _: hits.append(1))
            self.bus.off("task.start", listener_id=listener_id)
            await self.bus.emit("task.start", {})

        self._run(scenario())
        self.assertEqual(hits, [])

    def test_off_normalizes_event_name(self) -> None:
        hits: list[int] = []

        async def scenario():
            listener_id = self.bus.on(" task.start ", lambda _: hits.append(1))
            self.bus.off(" task.start ", listener_id=listener_id)
            await self.bus.emit("task.start", {})

        self._run(scenario())
        self.assertEqual(hits, [])

    def test_off_by_instance_unbinds_all(self) -> None:
        hits: list[int] = []

        async def scenario():
            self.bus.on(
                "task.start",
                lambda _: hits.append(1),
                scope="instance",
                owner_instance_id="ins-a",
            )
            self.bus.on(
                "task.exit",
                lambda _: hits.append(2),
                scope="instance",
                owner_instance_id="ins-a",
            )
            self.bus.off_by_instance("ins-a")
            await self.bus.emit(
                "task.start", {}, scope="instance", source_instance_id="ins-a"
            )
            await self.bus.emit(
                "task.exit", {}, scope="instance", source_instance_id="ins-a"
            )

        self._run(scenario())
        self.assertEqual(hits, [])
        self.assertEqual(self.bus.handler_count, {})

    def test_duplicate_registration_returns_existing_id(self) -> None:
        def handler(_):
            pass

        first = self.bus.on("task.start", handler)
        second = self.bus.on("task.start", handler, priority=99)
        self.assertEqual(first, second)
        self.assertEqual(self.bus.handler_count, {"task.start": 1})

    def test_async_handler_supported(self) -> None:
        hits: list[int] = []

        async def async_handler(_):
            hits.append(1)

        async def scenario():
            self.bus.on("task.start", async_handler)
            await self.bus.emit("task.start", {})

        self._run(scenario())
        self.assertEqual(hits, [1])

    def test_instance_emit_requires_source_id(self) -> None:
        async def scenario():
            await self.bus.emit("task.start", {}, scope="instance")

        with self.assertRaises(ValueError):
            self._run(scenario())

    def test_emit_rejects_invalid_scope(self) -> None:
        async def scenario():
            await self.bus.emit("task.start", {}, scope="bad")

        with self.assertRaises(ValueError):
            self._run(scenario())

    def test_emit_rejects_invalid_error_policy_before_dispatch(self) -> None:
        hits: list[int] = []

        def bad_handler(_):
            hits.append(1)
            raise RuntimeError("boom")

        async def scenario():
            self.bus.on("task.start", bad_handler)
            await self.bus.emit("task.start", {}, error_policy="bad")

        with self.assertRaises(ValueError):
            self._run(scenario())
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
