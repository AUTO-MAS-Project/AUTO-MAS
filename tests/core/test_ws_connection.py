import asyncio
import unittest

from fastapi import WebSocketDisconnect

from app.core.ws.manager import _MainConnectionManager
from app.core.ws import manager as manager_module


class FakeWebSocket:
    """模拟 FastAPI WebSocket 的最小实现"""

    def __init__(self):
        self.accepted = False
        self.close_args: tuple | None = None
        self.sent: list[dict] = []
        self.client = ("127.0.0.1", 0)
        self._incoming: asyncio.Queue = asyncio.Queue()

    async def accept(self):
        self.accepted = True

    async def receive_json(self):
        item = await self._incoming.get()
        if isinstance(item, Exception):
            raise item
        return item

    async def send_json(self, message: dict):
        self.sent.append(message)

    async def close(self, code: int = 1000, reason: str = ""):
        self.close_args = (code, reason)
        await self._incoming.put(WebSocketDisconnect(code))

    async def push(self, message):
        await self._incoming.put(message)

    async def disconnect(self, code: int = 1000):
        await self._incoming.put(WebSocketDisconnect(code))


class MainConnectionManagerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.manager = _MainConnectionManager()

    async def _serve(self, websocket: FakeWebSocket) -> asyncio.Task:
        task = asyncio.create_task(self.manager.serve(websocket))
        for _ in range(100):
            if self.manager.is_connected and websocket.accepted:
                break
            await asyncio.sleep(0.01)
        return task

    async def test_single_connection_send_and_disconnect(self):
        websocket = FakeWebSocket()
        serve_task = await self._serve(websocket)

        self.assertTrue(self.manager.is_connected)
        self.assertTrue(
            await self.manager.send({"id": "Main", "type": "t", "data": {}})
        )
        self.assertEqual(len(websocket.sent), 1)

        await websocket.disconnect()
        await asyncio.wait_for(serve_task, timeout=1)
        self.assertFalse(self.manager.is_connected)

    async def test_send_returns_false_when_not_connected(self):
        self.assertFalse(
            await self.manager.send({"id": "Main", "type": "t", "data": {}})
        )

    async def test_second_connection_replaces_first(self):
        first = FakeWebSocket()
        first_task = await self._serve(first)

        second = FakeWebSocket()
        second_task = await self._serve(second)

        # 旧连接被关闭替换，新连接生效
        await asyncio.wait_for(first_task, timeout=1)
        self.assertIsNotNone(first.close_args)
        self.assertTrue(self.manager.is_connected)

        # 旧连接的断开清理不得清掉新连接
        self.assertTrue(
            await self.manager.send({"id": "Main", "type": "t", "data": {}})
        )
        self.assertEqual(len(second.sent), 1)
        self.assertEqual(len(first.sent), 0)

        await second.disconnect()
        await asyncio.wait_for(second_task, timeout=1)
        self.assertFalse(self.manager.is_connected)

    async def test_replaced_connection_gets_app_close_code(self):
        # 被替换的旧连接必须收到专用应用级关闭码与机器可读 reason，
        # 前端据此停止自动重连，而不是当成异常断开反过来踢掉新连接
        from app.core.ws.protocol import CLOSE_CODE_REPLACED, CLOSE_REASON_REPLACED

        first = FakeWebSocket()
        first_task = await self._serve(first)
        second = FakeWebSocket()
        second_task = await self._serve(second)

        await asyncio.wait_for(first_task, timeout=1)
        self.assertEqual(first.close_args, (CLOSE_CODE_REPLACED, CLOSE_REASON_REPLACED))
        self.assertTrue(4000 <= CLOSE_CODE_REPLACED <= 4999)
        self.assertTrue(CLOSE_REASON_REPLACED.isascii())
        self.assertIsNone(second.close_args)

        await second.disconnect()
        await asyncio.wait_for(second_task, timeout=1)

    async def test_connection_rejected_during_shutdown_keeps_1001(self):
        # 关闭流程中拒绝新连接仍走 1001，与"被替换"关闭码区分
        from app.core.ws.protocol import CLOSE_CODE_REPLACED

        await self.manager.begin_shutdown()
        websocket = FakeWebSocket()
        await asyncio.wait_for(self.manager.serve(websocket), timeout=1)

        self.assertIsNotNone(websocket.close_args)
        self.assertEqual(websocket.close_args[0], 1001)
        self.assertNotEqual(websocket.close_args[0], CLOSE_CODE_REPLACED)
        self.assertFalse(self.manager.is_connected)

    async def test_invalid_inbound_message_does_not_kill_connection(self):
        websocket = FakeWebSocket()
        serve_task = await self._serve(websocket)

        await websocket.push({"not": "an envelope"})
        await asyncio.sleep(0.05)
        self.assertTrue(self.manager.is_connected)

        await websocket.disconnect()
        await asyncio.wait_for(serve_task, timeout=1)

    async def test_connect_hooks_run_on_each_connection(self):
        calls: list[int] = []

        async def hook():
            calls.append(1)

        self.manager.on_connect(hook)

        websocket = FakeWebSocket()
        serve_task = await self._serve(websocket)
        await asyncio.sleep(0.05)
        await websocket.disconnect()
        await asyncio.wait_for(serve_task, timeout=1)

        self.assertEqual(len(calls), 1)


class PublisherTest(unittest.IsolatedAsyncioTestCase):
    async def test_publisher_sends_envelope_via_main_connection(self):
        from app.core.ws.publisher import Publisher

        manager = manager_module.MainConnection
        websocket = FakeWebSocket()
        serve_task = asyncio.create_task(manager.serve(websocket))
        for _ in range(100):
            if manager.is_connected:
                break
            await asyncio.sleep(0.01)

        try:
            sent = await Publisher.send(id="Main", type="backend.shutdown.ready")
            self.assertTrue(sent)
            self.assertEqual(
                websocket.sent[-1],
                {"id": "Main", "type": "backend.shutdown.ready", "data": {}},
            )
        finally:
            await websocket.disconnect()
            await asyncio.wait_for(serve_task, timeout=1)

    async def test_publisher_drops_message_when_disconnected(self):
        from app.core.ws.publisher import Publisher

        self.assertFalse(await Publisher.send(id="Main", type="power.sign.updated"))


if __name__ == "__main__":
    unittest.main()
