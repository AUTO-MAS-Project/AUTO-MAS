from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from types import SimpleNamespace
from typing import Any
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.broadcast import Broadcast
from app.core.ws import protocol
from app.core.ws.dialogs import DialogManager
from app.core.ws.dispatcher import WSDispatcher
from app.core.ws.legacy import WSLegacyAdapter
from app.core.ws.lifecycle import WSConnection
from app.core.ws.manager import WSManager
from app.core.ws.publisher import WSPublisher
from app.core.ws.security import build_auth_subprotocol
from app.models.schema import WSEnvelope


class FakeWebSocket:
    def __init__(
        self,
        *,
        auth_token: str = "test-token",
        origin: str = "http://localhost:5173",
        client_host: str = "127.0.0.1",
    ) -> None:
        self.accepted = False
        self.accepted_subprotocol: str | None = None
        self.closed = False
        self.close_code: int | None = None
        self.close_reason = ""
        self.sent: list[dict[str, Any]] = []
        self.incoming: asyncio.Queue[Any] = asyncio.Queue()
        self.client = SimpleNamespace(host=client_host)
        self.headers = {
            "origin": origin,
            "sec-websocket-protocol": build_auth_subprotocol(auth_token),
        }

    async def accept(self, subprotocol: str | None = None) -> None:
        self.accepted = True
        self.accepted_subprotocol = subprotocol

    async def send_json(self, data: dict[str, Any]) -> None:
        if self.closed:
            raise RuntimeError("websocket closed")
        self.sent.append(data)

    async def receive_json(self) -> Any:
        item = await self.incoming.get()
        if isinstance(item, BaseException):
            raise item
        return item

    async def close(self, code: int = 1000, reason: str = "") -> None:
        if self.closed:
            return
        self.closed = True
        self.close_code = code
        self.close_reason = reason
        self.incoming.put_nowait(RuntimeError("websocket closed"))

    def feed(self, data: dict[str, Any]) -> None:
        self.incoming.put_nowait(data)

    def disconnect(self) -> None:
        self.incoming.put_nowait(RuntimeError("client disconnected"))


class BlockingSendWebSocket(FakeWebSocket):
    def __init__(self) -> None:
        super().__init__()
        self.send_started = asyncio.Event()
        self.release_send = asyncio.Event()

    async def send_json(self, data: dict[str, Any]) -> None:
        self.send_started.set()
        await self.release_send.wait()
        await super().send_json(data)


class BlockingCloseWebSocket(FakeWebSocket):
    def __init__(self) -> None:
        super().__init__()
        self.close_started = asyncio.Event()
        self.release_close = asyncio.Event()

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.close_started.set()
        await self.release_close.wait()
        await super().close(code=code, reason=reason)


class RecordingManager:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_json(self, data: dict[str, Any]) -> bool:
        self.sent.append(data)
        return True


class RecordingPublisher:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict[str, Any]]] = []

    async def send(self, id: str, type: str, data: Any = None) -> bool:
        payload = data.model_dump() if hasattr(data, "model_dump") else dict(data or {})
        self.sent.append((id, type, payload))
        return True

    async def send_legacy(self, id: str, type: str, data: dict[str, Any]) -> bool:
        self.sent.append((id, type, dict(data)))
        return True


class HookManager:
    def __init__(self) -> None:
        self.hooks: list[Any] = []

    def on_connect(self, hook: Any):
        self.hooks.append(hook)

        def unregister() -> None:
            if hook in self.hooks:
                self.hooks.remove(hook)

        return unregister

    async def fire_connect(self) -> None:
        for hook in tuple(self.hooks):
            await hook()


class BlockingSubscriber:
    """让 Broadcast.put 可控地停在一次 await 上，复现连接替换竞态。"""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.messages: list[dict[str, Any]] = []

    async def put(self, item: dict[str, Any]) -> None:
        self.messages.append(item)
        self.started.set()
        await self.release.wait()


async def wait_until(predicate: Any, attempts: int = 50) -> None:
    for _ in range(attempts):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition was not reached")


class TestWSEnvelope(TestCase):
    def test_build_message_always_uses_stable_envelope(self) -> None:
        self.assertEqual(
            protocol.build_message("Main", protocol.POWER_SIGN_UPDATED, {"value": "Sleep"}),
            {
                "id": "Main",
                "type": "power.sign.updated",
                "data": {"value": "Sleep"},
            },
        )

    def test_frontend_heartbeat_without_id_is_valid(self) -> None:
        envelope = protocol.parse_envelope(
            {"type": "Signal", "data": {"Ping": 123}}
        )
        self.assertIsNotNone(envelope)
        assert envelope is not None
        self.assertEqual(envelope.id, "")
        self.assertEqual(envelope.type, "Signal")


class TestWSManager(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.manager = WSManager(
            sync_config_compat=False,
            auth_token="test-token",
        )
        self.dispatcher = WSDispatcher()
        self.manager.set_dispatcher(self.dispatcher)

    async def test_unauthenticated_connection_cannot_replace_current(self) -> None:
        current_ws = FakeWebSocket()
        current_task = asyncio.create_task(self.manager.serve(current_ws))
        await wait_until(lambda: self.manager.is_connected)

        rejected_ws = FakeWebSocket(auth_token="wrong-token")
        await self.manager.serve(rejected_ws)

        self.assertFalse(rejected_ws.accepted)
        self.assertTrue(rejected_ws.closed)
        self.assertEqual(rejected_ws.close_code, 1008)
        self.assertIsNotNone(self.manager.connection)
        assert self.manager.connection is not None
        self.assertIs(self.manager.connection.websocket, current_ws)

        current_ws.disconnect()
        await current_task

    async def test_new_connection_replaces_old_without_old_cleanup_clearing_new(self) -> None:
        old_ws = FakeWebSocket()
        old_task = asyncio.create_task(self.manager.serve(old_ws))
        await wait_until(lambda: self.manager.connection is not None)

        new_ws = FakeWebSocket()
        new_task = asyncio.create_task(self.manager.serve(new_ws))
        await wait_until(
            lambda: self.manager.connection is not None
            and self.manager.connection.websocket is new_ws
        )
        await wait_until(lambda: old_ws.closed)
        await old_task

        self.assertEqual(
            old_ws.close_code,
            protocol.CONNECTION_REPLACED_CLOSE_CODE,
        )
        self.assertEqual(
            old_ws.close_reason,
            protocol.CONNECTION_REPLACED_CLOSE_REASON,
        )
        self.assertIsNotNone(self.manager.connection)
        assert self.manager.connection is not None
        self.assertIs(self.manager.connection.websocket, new_ws)

        new_ws.disconnect()
        await new_task
        self.assertIsNone(self.manager.connection)

    async def test_only_current_owner_token_can_replace_connection(self) -> None:
        manager = WSManager(sync_config_compat=False)
        manager.set_owner_token("owner-a")
        owner_a_auth_token = manager.auth_token
        old_ws = FakeWebSocket(auth_token=owner_a_auth_token)
        old_task = asyncio.create_task(manager.serve(old_ws))
        await wait_until(lambda: manager.is_connected)

        manager.set_owner_token("owner-b")
        stale_owner_ws = FakeWebSocket(auth_token=owner_a_auth_token)
        await manager.serve(stale_owner_ws)

        self.assertEqual(stale_owner_ws.close_code, 1008)
        self.assertIsNotNone(manager.connection)
        assert manager.connection is not None
        self.assertIs(manager.connection.websocket, old_ws)

        current_owner_ws = FakeWebSocket(auth_token=manager.auth_token)
        current_owner_task = asyncio.create_task(manager.serve(current_owner_ws))
        await wait_until(
            lambda: manager.connection is not None
            and manager.connection.websocket is current_owner_ws
        )
        await asyncio.wait_for(old_task, timeout=1)

        self.assertEqual(
            old_ws.close_code,
            protocol.CONNECTION_REPLACED_CLOSE_CODE,
        )
        current_owner_ws.disconnect()
        await current_owner_task

    async def test_superseded_connection_does_not_run_connect_hooks(self) -> None:
        hook_calls: list[str] = []

        async def record_hook() -> None:
            connection = self.manager.connection
            assert connection is not None
            hook_calls.append(str(id(connection.websocket)))

        self.manager.on_connect(record_hook)
        first_ws = BlockingCloseWebSocket()
        first_task = asyncio.create_task(self.manager.serve(first_ws))
        await wait_until(lambda: len(hook_calls) == 1)

        second_ws = FakeWebSocket()
        second_task = asyncio.create_task(self.manager.serve(second_ws))
        await asyncio.wait_for(first_ws.close_started.wait(), timeout=1)

        third_ws = FakeWebSocket()
        third_task = asyncio.create_task(self.manager.serve(third_ws))
        await wait_until(
            lambda: self.manager.connection is not None
            and self.manager.connection.websocket is third_ws
        )
        await wait_until(lambda: len(hook_calls) >= 2)

        first_ws.release_close.set()
        await asyncio.wait_for(first_task, timeout=1)
        await asyncio.wait_for(second_task, timeout=1)

        self.assertEqual(
            hook_calls,
            [str(id(first_ws)), str(id(third_ws))],
        )

        third_ws.disconnect()
        await third_task

    async def test_no_id_ping_replies_and_enters_real_broadcast(self) -> None:
        queue: asyncio.Queue = asyncio.Queue()
        await Broadcast.subscribe(queue)
        websocket = FakeWebSocket()
        serve_task = asyncio.create_task(self.manager.serve(websocket))
        await wait_until(lambda: self.manager.is_connected)

        websocket.feed(
            {
                "type": "Signal",
                "data": {"Ping": 321, "connectionId": "renderer-1"},
            }
        )
        await wait_until(lambda: bool(websocket.sent))

        self.assertEqual(
            websocket.sent[-1],
            {
                "id": "Main",
                "type": "Signal",
                "data": {"Pong": 321, "connectionId": "renderer-1"},
            },
        )
        broadcast_message = await asyncio.wait_for(queue.get(), timeout=1)
        self.assertEqual(broadcast_message["id"], "")
        self.assertEqual(broadcast_message["type"], "Signal")

        await Broadcast.unsubscribe(queue)
        websocket.disconnect()
        await serve_task

    async def test_replaced_connection_inflight_ping_never_reaches_new_connection(
        self,
    ) -> None:
        subscriber = BlockingSubscriber()
        dispatched: list[WSEnvelope] = []
        self.dispatcher.register("", "Signal", dispatched.append)
        await Broadcast.subscribe(subscriber)

        old_ws = FakeWebSocket()
        old_task = asyncio.create_task(self.manager.serve(old_ws))
        await wait_until(lambda: self.manager.is_connected)
        new_task: asyncio.Task | None = None
        new_ws = FakeWebSocket()

        try:
            old_ws.feed({"type": "Signal", "data": {"Ping": 99}})
            await asyncio.wait_for(subscriber.started.wait(), timeout=1)

            new_task = asyncio.create_task(self.manager.serve(new_ws))
            await wait_until(
                lambda: self.manager.connection is not None
                and self.manager.connection.websocket is new_ws
            )
            subscriber.release.set()
            await asyncio.wait_for(old_task, timeout=1)

            self.assertEqual(dispatched, [])
            self.assertEqual(new_ws.sent, [])
            self.assertEqual(
                old_ws.close_code,
                protocol.CONNECTION_REPLACED_CLOSE_CODE,
            )
            self.assertEqual(
                old_ws.close_reason,
                protocol.CONNECTION_REPLACED_CLOSE_REASON,
            )
        finally:
            subscriber.release.set()
            await Broadcast.unsubscribe(subscriber)
            if not old_task.done():
                if new_task is None:
                    old_ws.disconnect()
                with suppress(Exception):
                    await asyncio.wait_for(old_task, timeout=1)
            if new_task is not None:
                new_ws.disconnect()
                with suppress(Exception):
                    await asyncio.wait_for(new_task, timeout=1)

    async def test_replaced_connection_waiting_for_dispatch_is_dropped(self) -> None:
        queue: asyncio.Queue = asyncio.Queue()
        dispatched: list[WSEnvelope] = []
        self.dispatcher.register("", "ordered", dispatched.append)
        await Broadcast.subscribe(queue)

        old_ws = FakeWebSocket()
        old_task = asyncio.create_task(self.manager.serve(old_ws))
        await wait_until(lambda: self.manager.connection is not None)
        old_connection = self.manager.connection
        assert old_connection is not None
        new_ws = FakeWebSocket()
        new_task: asyncio.Task | None = None

        await self.manager._dispatch_lock.acquire()
        try:
            old_ws.feed(
                {
                    "id": "old-request",
                    "type": "ordered",
                    "data": {"sequence": 1},
                }
            )
            await wait_until(
                lambda: bool(self.manager._inflight_messages.get(old_connection))
            )

            new_task = asyncio.create_task(self.manager.serve(new_ws))
            await wait_until(
                lambda: self.manager.connection is not None
                and self.manager.connection.websocket is new_ws
            )
        finally:
            self.manager._dispatch_lock.release()

        try:
            await asyncio.wait_for(old_task, timeout=1)
            await wait_until(
                lambda: not self.manager._inflight_messages.get(old_connection)
            )
            self.assertTrue(queue.empty())
            self.assertEqual(dispatched, [])
        finally:
            await Broadcast.unsubscribe(queue)
            if new_task is not None:
                new_ws.disconnect()
                with suppress(Exception):
                    await asyncio.wait_for(new_task, timeout=1)

    async def test_inbound_messages_keep_arrival_order_and_duplicates(self) -> None:
        received: list[int] = []

        async def record(envelope: WSEnvelope) -> None:
            received.append(int(envelope.data["sequence"]))

        self.dispatcher.register(protocol.ID_MAIN, "ordered", record)
        websocket = FakeWebSocket()
        serve_task = asyncio.create_task(self.manager.serve(websocket))
        await wait_until(lambda: self.manager.is_connected)

        for sequence in (1, 2, 2, 3):
            websocket.feed(
                {
                    "id": protocol.ID_MAIN,
                    "type": "ordered",
                    "data": {"sequence": sequence},
                }
            )

        await wait_until(lambda: len(received) == 4)
        self.assertEqual(received, [1, 2, 2, 3])

        websocket.disconnect()
        await serve_task

    async def test_slow_consumer_is_disconnected_after_send_timeout(self) -> None:
        manager = WSManager(
            sync_config_compat=False,
            auth_token="test-token",
            max_outbound_queue_size=1,
            send_timeout=0.01,
        )
        websocket = BlockingSendWebSocket()
        serve_task = asyncio.create_task(manager.serve(websocket))
        await wait_until(lambda: manager.is_connected)

        sent = await manager.send_json(
            protocol.build_message(protocol.ID_MAIN, "slow", {"value": 1})
        )

        self.assertFalse(sent)
        self.assertTrue(websocket.closed)
        self.assertIsNone(manager.connection)
        await asyncio.wait_for(serve_task, timeout=1)

    async def test_oversized_inbound_message_closes_without_dispatch(self) -> None:
        manager = WSManager(
            sync_config_compat=False,
            auth_token="test-token",
            max_message_bytes=128,
        )
        dispatcher = WSDispatcher()
        dispatched: list[WSEnvelope] = []
        dispatcher.register("", "oversized", dispatched.append)
        manager.set_dispatcher(dispatcher)
        websocket = FakeWebSocket()
        serve_task = asyncio.create_task(manager.serve(websocket))
        await wait_until(lambda: manager.is_connected)

        websocket.feed(
            {
                "id": protocol.ID_MAIN,
                "type": "oversized",
                "data": {"value": "x" * 256},
            }
        )

        await asyncio.wait_for(serve_task, timeout=1)
        self.assertTrue(websocket.closed)
        self.assertEqual(websocket.close_code, protocol.MESSAGE_TOO_BIG_CLOSE_CODE)
        self.assertEqual(dispatched, [])
        self.assertIsNone(manager.connection)

    async def test_oversized_outbound_message_closes_without_sending(self) -> None:
        manager = WSManager(
            sync_config_compat=False,
            auth_token="test-token",
            max_message_bytes=128,
        )
        websocket = FakeWebSocket()
        serve_task = asyncio.create_task(manager.serve(websocket))
        await wait_until(lambda: manager.is_connected)

        sent = await manager.send_json(
            protocol.build_message(
                protocol.ID_MAIN,
                "oversized",
                {"value": "x" * 256},
            )
        )

        self.assertFalse(sent)
        self.assertEqual(websocket.sent, [])
        self.assertEqual(websocket.close_code, protocol.MESSAGE_TOO_BIG_CLOSE_CODE)
        await asyncio.wait_for(serve_task, timeout=1)

    async def test_outbound_queue_is_bounded(self) -> None:
        websocket = BlockingSendWebSocket()
        connection = WSConnection(
            websocket,
            max_outbound_queue_size=1,
            send_timeout=1,
        )
        await connection.accept()

        first = asyncio.create_task(
            connection.send_json(
                protocol.build_message(protocol.ID_MAIN, "queued", {"value": 1})
            )
        )
        await asyncio.wait_for(websocket.send_started.wait(), timeout=1)
        second = asyncio.create_task(
            connection.send_json(
                protocol.build_message(protocol.ID_MAIN, "queued", {"value": 2})
            )
        )
        await wait_until(lambda: connection.outbound_queue_size == 1)

        third = await connection.send_json(
            protocol.build_message(protocol.ID_MAIN, "queued", {"value": 3})
        )
        self.assertFalse(third)
        self.assertEqual(connection.outbound_queue_size, 1)

        websocket.release_send.set()
        self.assertEqual(await asyncio.gather(first, second), [True, True])
        await connection.close()

    async def test_close_cancels_blocked_writer_and_resolves_waiters(self) -> None:
        websocket = BlockingSendWebSocket()
        connection = WSConnection(
            websocket,
            max_outbound_queue_size=1,
            send_timeout=1,
        )
        await connection.accept()

        sending = asyncio.create_task(
            connection.send_json(
                protocol.build_message(protocol.ID_MAIN, "blocked", {"value": 1})
            )
        )
        await asyncio.wait_for(websocket.send_started.wait(), timeout=1)
        queued = asyncio.create_task(
            connection.send_json(
                protocol.build_message(protocol.ID_MAIN, "queued", {"value": 2})
            )
        )
        await wait_until(lambda: connection.outbound_queue_size == 1)

        await connection.close(code=1001, reason="test shutdown")

        self.assertEqual(await asyncio.gather(sending, queued), [False, False])
        self.assertEqual(connection.outbound_queue_size, 0)
        self.assertTrue(websocket.closed)

    async def test_replaced_connection_inflight_command_response_stays_on_source(
        self,
    ) -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        finished = asyncio.Event()
        calls: list[str] = []

        async def delayed(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
            calls.append(endpoint)
            started.set()
            await release.wait()
            finished.set()
            return {"success": True, "data": params, "code": 200}

        self.dispatcher.register_command("test.delayed", delayed)
        old_ws = FakeWebSocket()
        old_task = asyncio.create_task(self.manager.serve(old_ws))
        await wait_until(lambda: self.manager.is_connected)
        new_ws = FakeWebSocket()
        new_task: asyncio.Task | None = None

        try:
            old_ws.feed(
                {
                    "id": "old-request",
                    "type": "command",
                    "data": {
                        "endpoint": "test.delayed",
                        "params": {"value": 5},
                    },
                }
            )
            await asyncio.wait_for(started.wait(), timeout=1)

            new_task = asyncio.create_task(self.manager.serve(new_ws))
            await wait_until(
                lambda: self.manager.connection is not None
                and self.manager.connection.websocket is new_ws
            )
            release.set()
            await asyncio.wait_for(finished.wait(), timeout=1)
            await asyncio.wait_for(old_task, timeout=1)

            self.assertEqual(calls, ["test.delayed"])
            self.assertTrue(finished.is_set())
            self.assertEqual(new_ws.sent, [])
            self.assertFalse(
                any(message.get("type") == "response" for message in new_ws.sent)
            )
        finally:
            release.set()
            if not old_task.done():
                if new_task is None:
                    old_ws.disconnect()
                with suppress(Exception):
                    await asyncio.wait_for(old_task, timeout=1)
            if new_task is not None:
                new_ws.disconnect()
                with suppress(Exception):
                    await asyncio.wait_for(new_task, timeout=1)

    async def test_command_returns_client_response_envelope(self) -> None:
        async def echo(endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
            return {"success": True, "data": params, "code": 200}

        self.dispatcher.register_command("test.echo", echo)
        websocket = FakeWebSocket()
        serve_task = asyncio.create_task(self.manager.serve(websocket))
        await wait_until(lambda: self.manager.is_connected)

        websocket.feed(
            {
                "id": "request-1",
                "type": "command",
                "data": {"endpoint": "test.echo", "params": {"value": 7}},
            }
        )
        await wait_until(lambda: bool(websocket.sent))
        self.assertEqual(
            websocket.sent[-1],
            {
                "id": "Client",
                "type": "response",
                "data": {
                    "endpoint": "test.echo",
                    "request_id": "request-1",
                    "success": True,
                    "data": {"value": 7},
                    "code": 200,
                },
            },
        )

        websocket.disconnect()
        await serve_task

    async def test_blocking_command_does_not_delay_heartbeat(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def blocking(_endpoint: str, _params: dict[str, Any]) -> dict[str, Any]:
            started.set()
            await release.wait()
            return {"success": True, "data": None, "code": 200}

        self.dispatcher.register_command("test.blocking", blocking)
        websocket = FakeWebSocket()
        serve_task = asyncio.create_task(self.manager.serve(websocket))
        await wait_until(lambda: self.manager.is_connected)

        websocket.feed(
            {
                "id": "slow-request",
                "type": "command",
                "data": {"endpoint": "test.blocking", "params": {}},
            }
        )
        await asyncio.wait_for(started.wait(), timeout=1)
        websocket.feed(
            {
                "type": "Signal",
                "data": {"Ping": 987, "connectionId": "heartbeat-during-command"},
            }
        )
        await wait_until(
            lambda: any(
                message.get("type") == "Signal"
                and message.get("data", {}).get("Pong") == 987
                for message in websocket.sent
            )
        )

        release.set()
        await wait_until(
            lambda: any(message.get("type") == "response" for message in websocket.sent)
        )
        websocket.disconnect()
        await serve_task


class TestASGIWSRoute(TestCase):
    def test_real_route_negotiation_and_legacy_heartbeat(self) -> None:
        from app.api.core import router
        from app.core.ws.bootstrap import init_ws_core, shutdown_ws_core

        @asynccontextmanager
        async def lifespan(_app: FastAPI):
            await init_ws_core()
            try:
                yield
            finally:
                await shutdown_ws_core()

        app = FastAPI(lifespan=lifespan)
        app.include_router(router)

        with TestClient(app) as client:
            response = client.get("/api/core/ws_meta")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["wsPath"], "/api/core/ws")
            auth_token = response.json()["wsAuthToken"]
            self.assertIsInstance(auth_token, str)

            untrusted = client.get(
                "/api/core/ws_meta",
                headers={"Origin": "https://example.invalid"},
            )
            self.assertIsNone(untrusted.json()["wsAuthToken"])
            self.assertNotIn("x-auto-mas-owner-token", untrusted.headers)

            electron_renderer = client.get(
                "/api/core/ws_meta",
                headers={"Origin": "null"},
            )
            self.assertIsNone(electron_renderer.json()["wsAuthToken"])
            self.assertNotIn("x-auto-mas-owner-token", electron_renderer.headers)

            with client.websocket_connect(
                "/api/core/ws",
                subprotocols=[build_auth_subprotocol(auth_token)],
            ) as websocket:
                websocket.send_json(
                    {
                        "type": "Signal",
                        "data": {"Ping": 456, "connectionId": "asgi-test"},
                    }
                )
                for _ in range(3):
                    message = websocket.receive_json()
                    self.assertEqual(set(message), {"id", "type", "data"})
                    if message["type"] == "Signal":
                        self.assertEqual(
                            message,
                            {
                                "id": "Main",
                                "type": "Signal",
                                "data": {
                                    "Pong": 456,
                                    "connectionId": "asgi-test",
                                },
                            },
                        )
                        break
                else:
                    self.fail("real /api/core/ws route did not answer the heartbeat")


class TestPublisherAndLegacy(IsolatedAsyncioTestCase):
    async def test_legacy_message_is_not_reclassified(self) -> None:
        publisher = RecordingPublisher()
        adapter = WSLegacyAdapter()
        adapter.set_publisher(publisher)

        await adapter.send_websocket_message(
            "Main",
            "Update",
            {"PowerSign": "Sleep"},
        )
        self.assertEqual(
            publisher.sent,
            [("Main", "Update", {"PowerSign": "Sleep"})],
        )

    async def test_config_legacy_delegate_keeps_exact_envelope(self) -> None:
        import app.core.config as config_module

        publisher = RecordingPublisher()
        adapter = WSLegacyAdapter()
        adapter.set_publisher(publisher)
        previous = config_module._ws_send_websocket_message_fn
        config_module._ws_delegate_send_websocket_message(
            adapter.send_websocket_message
        )
        try:
            await config_module.Config.send_websocket_message(
                id="PluginSystem",
                type="Update",
                data={"kind": "snapshot"},
            )
        finally:
            config_module._ws_delegate_send_websocket_message(previous)

        self.assertEqual(
            publisher.sent,
            [("PluginSystem", "Update", {"kind": "snapshot"})],
        )

    async def test_cache_isolated_by_id_and_type(self) -> None:
        manager = RecordingManager()
        publisher = WSPublisher()
        publisher.set_ws_manager(manager)

        await publisher.send("task-a", protocol.TASK_INFO_UPDATED, {"status": "running"})
        await publisher.send("task-b", protocol.TASK_INFO_UPDATED, {"status": "done"})

        snapshot = publisher.cache.snapshot()
        self.assertEqual(snapshot[protocol.TASK_INFO_UPDATED]["task-a"]["status"], "running")
        self.assertEqual(snapshot[protocol.TASK_INFO_UPDATED]["task-b"]["status"], "done")

    async def test_oversized_state_is_not_cached_or_sent(self) -> None:
        manager = RecordingManager()
        publisher = WSPublisher()
        publisher.set_ws_manager(manager)

        with patch.object(protocol, "DEFAULT_MAX_MESSAGE_BYTES", 128):
            sent = await publisher.send(
                "task-oversized",
                protocol.TASK_INFO_UPDATED,
                {"log": "x" * 256},
            )

        self.assertFalse(sent)
        self.assertEqual(manager.sent, [])
        self.assertIsNone(
            publisher.cache.get(
                "task-oversized",
                protocol.TASK_INFO_UPDATED,
            )
        )

    async def test_non_json_state_is_not_cached_or_sent(self) -> None:
        manager = RecordingManager()
        publisher = WSPublisher()
        publisher.set_ws_manager(manager)

        sent = await publisher.send(
            "task-invalid",
            protocol.TASK_INFO_UPDATED,
            {"value": object()},
        )

        self.assertFalse(sent)
        self.assertEqual(manager.sent, [])
        self.assertIsNone(
            publisher.cache.get(
                "task-invalid",
                protocol.TASK_INFO_UPDATED,
            )
        )

    async def test_outbox_flush_and_discard_are_transaction_scoped(self) -> None:
        manager = RecordingManager()
        publisher = WSPublisher()
        publisher.set_ws_manager(manager)

        await publisher.enqueue(
            "task-a",
            protocol.TASK_INFO_UPDATED,
            {"status": "running"},
            transaction_id="txn-a",
        )
        await publisher.enqueue(
            "task-b",
            protocol.TASK_INFO_UPDATED,
            {"status": "pending"},
            transaction_id="txn-b",
        )

        await publisher.flush_outbox("txn-a")
        self.assertEqual(len(manager.sent), 1)
        self.assertEqual(manager.sent[0]["id"], "task-a")
        self.assertEqual(len(publisher.outbox._pending), 1)

        await publisher.discard_outbox("txn-b")
        self.assertEqual(len(publisher.outbox._pending), 0)

    async def test_publish_with_transaction_id_is_accepted_into_exact_bucket(
        self,
    ) -> None:
        manager = RecordingManager()
        publisher = WSPublisher()
        publisher.set_ws_manager(manager)

        accepted = await publisher.publish(
            protocol.TASK_INFO_UPDATED,
            {"status": "queued"},
            root_id="task-transactional",
            transaction_id="txn-publish",
        )

        self.assertTrue(accepted)
        self.assertEqual(manager.sent, [])
        self.assertEqual(
            set(publisher.outbox._buckets),
            {"transaction:txn-publish"},
        )

        await publisher.flush_outbox("txn-other")
        self.assertEqual(manager.sent, [])
        self.assertEqual(len(publisher.outbox._pending), 1)

        await publisher.flush_outbox("txn-publish")
        self.assertEqual(
            manager.sent,
            [
                {
                    "id": "task-transactional",
                    "type": protocol.TASK_INFO_UPDATED,
                    "data": {"status": "queued"},
                }
            ],
        )
        self.assertEqual(len(publisher.outbox._pending), 0)


class TestDialogs(IsolatedAsyncioTestCase):
    async def test_pending_dialog_resends_and_response_resolves(self) -> None:
        dispatcher = WSDispatcher()
        manager = HookManager()
        publisher = RecordingPublisher()
        dialogs = DialogManager()
        dialogs.bind(dispatcher, manager, publisher)

        ask_task = asyncio.create_task(
            dialogs.ask("确认", "继续吗？", options=["继续", "取消"])
        )
        await wait_until(lambda: bool(publisher.sent))
        first = publisher.sent[-1]
        self.assertEqual(first[0:2], ("Main", "dialog.request"))
        request_id = first[2]["requestId"]

        publisher.sent.clear()
        await manager.fire_connect()
        self.assertEqual(publisher.sent[-1][2]["requestId"], request_id)

        await dispatcher.dispatch(
            WSEnvelope(
                id="Main",
                type="dialog.response",
                data={"requestId": request_id, "choice": True},
            )
        )
        self.assertTrue(await asyncio.wait_for(ask_task, timeout=1))
        dialogs.unbind()

    async def test_concurrent_dialogs_resolve_only_matching_request(self) -> None:
        dispatcher = WSDispatcher()
        manager = HookManager()
        publisher = RecordingPublisher()
        dialogs = DialogManager()
        dialogs.bind(dispatcher, manager, publisher)

        first_task = asyncio.create_task(dialogs.ask("第一条", "继续吗？"))
        second_task = asyncio.create_task(dialogs.ask("第二条", "继续吗？"))
        await wait_until(lambda: len(publisher.sent) == 2)
        first_id = publisher.sent[0][2]["requestId"]
        second_id = publisher.sent[1][2]["requestId"]

        await dispatcher.dispatch(
            WSEnvelope(
                id="Main",
                type=protocol.DIALOG_RESPONSE,
                data={"requestId": second_id, "choice": False},
            )
        )
        self.assertFalse(await asyncio.wait_for(second_task, timeout=1))
        self.assertFalse(first_task.done())

        await dispatcher.dispatch(
            WSEnvelope(
                id="Main",
                type=protocol.DIALOG_RESPONSE,
                data={"requestId": first_id, "choice": True},
            )
        )
        self.assertTrue(await asyncio.wait_for(first_task, timeout=1))
        dialogs.unbind()

    async def test_dialog_request_timeout_returns_false_and_cleans_pending(self) -> None:
        dispatcher = WSDispatcher()
        manager = HookManager()
        publisher = RecordingPublisher()
        dialogs = DialogManager()
        dialogs.bind(dispatcher, manager, publisher)

        result = await dialogs.request(
            "manual-review",
            title="超时测试",
            message="无人响应",
            timeout=0.001,
        )

        self.assertFalse(result)
        self.assertEqual(dialogs._pending, {})
        self.assertEqual(dialogs._requests, {})
        dialogs.unbind()
