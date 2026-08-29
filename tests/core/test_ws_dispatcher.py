import asyncio
import unittest

from app.core.ws.dispatcher import _WSDispatcher
from app.core.ws.protocol import parse_envelope
from app.models.schema import WSEnvelope


def _envelope(id: str, type: str, data: dict | None = None) -> WSEnvelope:
    return WSEnvelope(id=id, type=type, data=data or {})


class WSDispatcherTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dispatcher = _WSDispatcher()

    async def test_dispatch_routes_by_id_and_type(self):
        received: list[WSEnvelope] = []
        self.dispatcher.register("task-1", "task.notice", received.append)

        self.dispatcher.dispatch(_envelope("task-1", "task.notice"))
        self.dispatcher.dispatch(_envelope("task-2", "task.notice"))
        self.dispatcher.dispatch(_envelope("task-1", "task.completed"))

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].id, "task-1")

    async def test_same_key_handlers_called_in_registration_order(self):
        order: list[str] = []
        self.dispatcher.register("Main", "test.event", lambda _: order.append("first"))
        self.dispatcher.register("Main", "test.event", lambda _: order.append("second"))

        self.dispatcher.dispatch(_envelope("Main", "test.event"))

        self.assertEqual(order, ["first", "second"])

    async def test_handler_exception_does_not_affect_other_handlers(self):
        received: list[str] = []

        def bad_handler(_):
            raise RuntimeError("boom")

        self.dispatcher.register("Main", "test.event", bad_handler)
        self.dispatcher.register("Main", "test.event", lambda _: received.append("ok"))

        self.dispatcher.dispatch(_envelope("Main", "test.event"))

        self.assertEqual(received, ["ok"])

    async def test_unmatched_message_is_dropped_without_error(self):
        self.dispatcher.dispatch(_envelope("nobody", "no.handler"))

    async def test_unregister_is_idempotent(self):
        received: list[WSEnvelope] = []
        cancel = self.dispatcher.register("task-1", "task.notice", received.append)

        cancel()
        cancel()
        self.dispatcher.unregister("task-1", "task.notice", received.append)

        self.dispatcher.dispatch(_envelope("task-1", "task.notice"))
        self.assertEqual(received, [])

    async def test_async_handler_runs_in_owned_task(self):
        done = asyncio.Event()

        async def handler(_):
            done.set()

        self.dispatcher.register("Main", "test.event", handler)
        self.dispatcher.dispatch(_envelope("Main", "test.event"))

        await asyncio.wait_for(done.wait(), timeout=1)
        await self.dispatcher.shutdown()

    async def test_shutdown_cancels_in_flight_tasks(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def slow_handler(_):
            started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        self.dispatcher.register("Main", "test.event", slow_handler)
        self.dispatcher.dispatch(_envelope("Main", "test.event"))
        await asyncio.wait_for(started.wait(), timeout=1)

        # 关闭流程需取消并等待在途任务，避免其在插件 teardown 期间继续运行
        await asyncio.wait_for(self.dispatcher.shutdown(), timeout=1)
        self.assertTrue(cancelled.is_set())

    async def test_shutdown_blocks_new_dispatch(self):
        received: list[WSEnvelope] = []
        self.dispatcher.register("Main", "test.event", received.append)

        await self.dispatcher.shutdown()
        # 关闭后新入站消息直接丢弃，不再触发处理器与 teardown 并发
        self.dispatcher.dispatch(_envelope("Main", "test.event"))

        self.assertEqual(received, [])


class WSProtocolTest(unittest.TestCase):
    def test_parse_envelope_accepts_valid_message(self):
        envelope = parse_envelope({"id": "Main", "type": "test.event", "data": {"choice": True}})
        self.assertIsNotNone(envelope)
        assert envelope is not None
        self.assertEqual(envelope.id, "Main")
        self.assertEqual(envelope.type, "test.event")
        self.assertEqual(envelope.data, {"choice": True})

    def test_parse_envelope_defaults_missing_data(self):
        envelope = parse_envelope({"id": "Main", "type": "backend.shutdown.ready"})
        self.assertIsNotNone(envelope)
        assert envelope is not None
        self.assertEqual(envelope.data, {})

    def test_parse_envelope_rejects_invalid_message(self):
        self.assertIsNone(parse_envelope("not a dict"))
        self.assertIsNone(parse_envelope({"type": "missing.id"}))
        self.assertIsNone(parse_envelope({"id": "Main"}))


if __name__ == "__main__":
    unittest.main()
