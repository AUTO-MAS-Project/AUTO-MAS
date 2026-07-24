from __future__ import annotations

import os
import asyncio
from types import SimpleNamespace
from typing import Any
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.api.plugin_gateway import dispatch_plugin_websocket
from app.api.websocket import websocket_dynamic_channel
from app.core.ws.manager import ws_manager
from app.core.ws.security import build_auth_subprotocol
from app.plugins.server import PluginWebSocketRoute, plugin_server
from app.utils.websocket import (
    ReverseWebSocketSession,
    WSClientManager,
    ws_client_manager,
)


class FakeWebSocket:
    def __init__(
        self,
        *,
        auth_token: str | None = None,
        origin: str = "http://localhost:5173",
        client_host: str = "127.0.0.1",
    ) -> None:
        self.client = SimpleNamespace(host=client_host, port=5173)
        self.headers: dict[str, str] = {"origin": origin}
        if auth_token is not None:
            self.headers["sec-websocket-protocol"] = build_auth_subprotocol(
                auth_token
            )
        self.scope = {"path": "/api/ws/plugin"}
        self.client_state = SimpleNamespace(name="CONNECTED")
        self.application_state = SimpleNamespace(name="CONNECTED")
        self.accepted = False
        self.accepted_subprotocol: str | None = None
        self.closed = False
        self.close_code: int | None = None
        self.close_reason = ""
        self.sent: list[dict[str, Any]] = []
        self.pending_messages: list[dict[str, Any]] = []
        self.pending_events: list[dict[str, Any]] = [
            {"type": "websocket.disconnect"}
        ]

    async def accept(self, subprotocol: str | None = None) -> None:
        self.accepted = True
        self.accepted_subprotocol = subprotocol

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = True
        self.close_code = code
        self.close_reason = reason
        self.application_state = SimpleNamespace(name="DISCONNECTED")

    async def send_json(self, data: dict[str, Any]) -> None:
        self.sent.append(data)

    async def receive_json(self) -> dict[str, Any]:
        return self.pending_messages.pop(0)

    async def receive(self) -> dict[str, Any]:
        return self.pending_events.pop(0)


class ClosedSession:
    async def wait_closed(self) -> None:
        return None


class TestAuxiliaryWebSocketRoute(IsolatedAsyncioTestCase):
    async def test_unauthenticated_core_close_is_rejected_before_accept(self) -> None:
        websocket = FakeWebSocket()
        websocket.pending_messages.append(
            {
                "id": "malicious-request",
                "type": "command",
                "data": {"endpoint": "core.close", "params": {}},
            }
        )

        with (
            patch.object(
                ws_client_manager,
                "openwsr",
                new=AsyncMock(return_value=ClosedSession()),
            ) as open_session,
            patch(
                "app.api.ws_command.execute_ws_command",
                new=AsyncMock(),
            ) as execute,
            patch.object(
                ws_client_manager,
                "get_reverse_channel_config",
            ) as resolve_channel,
        ):
            await websocket_dynamic_channel(websocket, "plugin")

        self.assertFalse(websocket.accepted)
        self.assertTrue(websocket.closed)
        self.assertEqual(websocket.close_code, 1008)
        self.assertEqual(websocket.close_reason, "authentication required")
        open_session.assert_not_awaited()
        execute.assert_not_awaited()
        resolve_channel.assert_not_called()

    async def test_untrusted_origin_is_rejected_even_with_process_token(self) -> None:
        websocket = FakeWebSocket(
            auth_token=ws_manager.auth_token,
            origin="https://example.invalid",
        )

        with patch.object(
            ws_client_manager,
            "openwsr",
            new=AsyncMock(return_value=ClosedSession()),
        ) as open_session:
            await websocket_dynamic_channel(websocket, "plugin")

        self.assertFalse(websocket.accepted)
        self.assertEqual(websocket.close_code, 1008)
        open_session.assert_not_awaited()

    async def test_authenticated_plugin_channel_accepts_matching_subprotocol(self) -> None:
        websocket = FakeWebSocket(auth_token=ws_manager.auth_token)
        expected_protocol = build_auth_subprotocol(ws_manager.auth_token)

        with patch.object(
            ws_client_manager,
            "openwsr",
            new=AsyncMock(return_value=ClosedSession()),
        ) as open_session:
            await websocket_dynamic_channel(websocket, "plugin")

        self.assertTrue(websocket.accepted)
        self.assertEqual(websocket.accepted_subprotocol, expected_protocol)
        self.assertFalse(open_session.await_args.kwargs["allow_commands"])

    async def test_wsdev_is_unavailable_outside_explicit_dev_mode(self) -> None:
        websocket = FakeWebSocket(auth_token=ws_manager.auth_token)

        with (
            patch.dict(os.environ, {"AUTO_MAS_DEV": "0"}),
            patch.object(
                ws_client_manager,
                "openwsr",
                new=AsyncMock(return_value=ClosedSession()),
            ) as open_session,
        ):
            await websocket_dynamic_channel(websocket, "wsdev")

        self.assertFalse(websocket.accepted)
        self.assertEqual(websocket.close_code, 1008)
        self.assertEqual(websocket.close_reason, "channel unavailable")
        open_session.assert_not_awaited()


class TestAuxiliaryWebSocketCommands(IsolatedAsyncioTestCase):
    async def test_builtin_channel_rejects_core_close_command(self) -> None:
        websocket = FakeWebSocket(auth_token=ws_manager.auth_token)
        session = ReverseWebSocketSession(
            websocket=websocket,
            name="plugin",
            allow_commands=False,
        )

        with patch(
            "app.api.ws_command.execute_ws_command",
            new=AsyncMock(),
        ) as execute:
            await session._handle_message(
                {
                    "id": "request-1",
                    "type": "command",
                    "data": {"endpoint": "core.close", "params": {}},
                }
            )

        execute.assert_not_awaited()
        self.assertEqual(websocket.sent[-1]["type"], "response")
        self.assertEqual(websocket.sent[-1]["data"]["endpoint"], "core.close")
        self.assertEqual(websocket.sent[-1]["data"]["code"], 403)

    async def test_custom_channel_keeps_legacy_command_compatibility(self) -> None:
        websocket = FakeWebSocket(auth_token=ws_manager.auth_token)
        session = ReverseWebSocketSession(
            websocket=websocket,
            name="local-plugin-channel",
        )
        execute_result = {
            "success": True,
            "data": {"compatible": True},
            "code": 200,
        }

        with patch(
            "app.api.ws_command.execute_ws_command",
            new=AsyncMock(return_value=execute_result),
        ) as execute:
            await session._handle_message(
                {
                    "id": "request-2",
                    "type": "command",
                    "data": {"endpoint": "local.echo", "params": {}},
                }
            )

        execute.assert_awaited_once_with("local.echo", {})
        self.assertEqual(websocket.sent[-1]["data"]["code"], 200)


class TestReverseWebSocketLifecycle(IsolatedAsyncioTestCase):
    async def test_close_from_owned_task_does_not_cancel_itself(self) -> None:
        websocket = FakeWebSocket()
        session = ReverseWebSocketSession(
            websocket=websocket,
            name="self-close",
        )

        async def close_from_owned_task() -> None:
            session._running = True
            current_task = asyncio.current_task()
            assert current_task is not None
            session._tasks = [current_task]
            await session.close(code=1001, reason="owned task stopped")

        task = asyncio.create_task(close_from_owned_task())
        await asyncio.wait_for(task, timeout=1)

        self.assertFalse(task.cancelled())
        self.assertTrue(session._closed_event.is_set())
        self.assertTrue(websocket.closed)

    async def test_natural_disconnect_removes_exact_reverse_session(self) -> None:
        manager = WSClientManager()
        websocket = FakeWebSocket()

        session = await manager.openwsr(
            name="ephemeral",
            websocket=websocket,
            ping_interval=0.01,
            ping_timeout=0.02,
        )
        await asyncio.wait_for(session.wait_closed(), timeout=1)

        self.assertIsNone(manager.get_session("ephemeral"))
        self.assertTrue(websocket.closed)

    async def test_oversized_message_closes_before_callback(self) -> None:
        websocket = FakeWebSocket()
        websocket.pending_messages.append(
            {
                "id": "oversized",
                "type": "Message",
                "data": {"value": "x" * 256},
            }
        )
        callback = AsyncMock()
        session = ReverseWebSocketSession(
            websocket=websocket,
            name="oversized",
            on_message=callback,
            max_message_bytes=128,
        )

        await session.start()
        await asyncio.wait_for(session.wait_closed(), timeout=1)

        callback.assert_not_awaited()
        self.assertEqual(websocket.close_code, 1009)


class TestPluginWebSocketGateway(IsolatedAsyncioTestCase):
    async def test_unauthenticated_gateway_request_is_rejected_before_lookup(
        self,
    ) -> None:
        websocket = FakeWebSocket()

        with patch.object(plugin_server, "resolve_websocket") as resolve_route:
            await dispatch_plugin_websocket("private-channel", websocket)

        self.assertFalse(websocket.accepted)
        self.assertEqual(websocket.close_code, 1008)
        self.assertEqual(websocket.close_reason, "authentication required")
        resolve_route.assert_not_called()

    async def test_authenticated_gateway_echoes_protocol_before_dispatch(self) -> None:
        websocket = FakeWebSocket(auth_token=ws_manager.auth_token)
        route = PluginWebSocketRoute(
            path="/private-channel",
            instance_id="local-plugin-instance",
            plugin_name="local-plugin",
            on_message=AsyncMock(),
        )

        with patch.object(
            plugin_server,
            "resolve_websocket",
            return_value=route,
        ) as resolve_route:
            await dispatch_plugin_websocket("private-channel", websocket)

        self.assertTrue(websocket.accepted)
        self.assertEqual(
            websocket.accepted_subprotocol,
            build_auth_subprotocol(ws_manager.auth_token),
        )
        resolve_route.assert_called_once_with("/private-channel")
        route.on_message.assert_not_awaited()
