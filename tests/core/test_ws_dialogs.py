import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.core.ws import protocol
from app.core.ws.dialogs import Dialogs
from app.models.schema import WSEnvelope


class WSDialogsTest(unittest.IsolatedAsyncioTestCase):
    async def test_ask_resolves_on_matching_response(self):
        with patch("app.core.ws.dialogs.Publisher.send", new_callable=AsyncMock) as send:
            ask_task = asyncio.create_task(
                Dialogs.ask(title="操作提示", message="是否重试？", task_id="task-1")
            )
            await asyncio.sleep(0.01)

            send.assert_awaited_once()
            request_data = send.await_args.kwargs["data"]
            self.assertEqual(send.await_args.kwargs["id"], protocol.ID_MAIN)
            self.assertEqual(send.await_args.kwargs["type"], protocol.DIALOG_REQUEST)
            self.assertEqual(request_data.taskId, "task-1")
            self.assertEqual(request_data.options, ["是", "否"])

            # 不匹配的响应被丢弃，等待不受影响
            Dialogs._on_response(
                WSEnvelope(
                    id=protocol.ID_MAIN,
                    type=protocol.DIALOG_RESPONSE,
                    data={"requestId": "other", "choice": False},
                )
            )
            await asyncio.sleep(0.01)
            self.assertFalse(ask_task.done())

            Dialogs._on_response(
                WSEnvelope(
                    id=protocol.ID_MAIN,
                    type=protocol.DIALOG_RESPONSE,
                    data={"requestId": request_data.requestId, "choice": True},
                )
            )
            self.assertTrue(await asyncio.wait_for(ask_task, timeout=1))

    async def test_ask_returns_false_choice(self):
        with patch("app.core.ws.dialogs.Publisher.send", new_callable=AsyncMock) as send:
            ask_task = asyncio.create_task(Dialogs.ask(title="操作提示", message="确认？"))
            await asyncio.sleep(0.01)
            request_data = send.await_args.kwargs["data"]

            Dialogs._on_response(
                WSEnvelope(
                    id=protocol.ID_MAIN,
                    type=protocol.DIALOG_RESPONSE,
                    data={"requestId": request_data.requestId, "choice": False},
                )
            )
            self.assertFalse(await asyncio.wait_for(ask_task, timeout=1))

    async def test_invalid_response_data_is_dropped(self):
        Dialogs._on_response(
            WSEnvelope(id=protocol.ID_MAIN, type=protocol.DIALOG_RESPONSE, data={"bad": 1})
        )

    async def test_cancelled_ask_cleans_pending(self):
        with patch("app.core.ws.dialogs.Publisher.send", new_callable=AsyncMock):
            ask_task = asyncio.create_task(Dialogs.ask(title="操作提示", message="确认？"))
            await asyncio.sleep(0.01)
            self.assertEqual(len(Dialogs._pending), 1)

            ask_task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await ask_task
            self.assertEqual(len(Dialogs._pending), 0)
            self.assertEqual(len(Dialogs._requests), 0)

    async def test_resend_pending_republishes_open_requests(self):
        with patch("app.core.ws.dialogs.Publisher.send", new_callable=AsyncMock) as send:
            ask_task = asyncio.create_task(Dialogs.ask(title="操作提示", message="重连后重发？"))
            await asyncio.sleep(0.01)
            self.assertEqual(len(Dialogs._requests), 1)
            send.reset_mock()

            # 模拟重连：主连接建立回调重发未完成请求
            await Dialogs._resend_pending()

            send.assert_awaited_once()
            self.assertEqual(send.await_args.kwargs["type"], protocol.DIALOG_REQUEST)

            request_id = next(iter(Dialogs._requests))
            Dialogs._on_response(
                WSEnvelope(
                    id=protocol.ID_MAIN,
                    type=protocol.DIALOG_RESPONSE,
                    data={"requestId": request_id, "choice": True},
                )
            )
            self.assertTrue(await asyncio.wait_for(ask_task, timeout=1))
            self.assertEqual(len(Dialogs._requests), 0)


if __name__ == "__main__":
    unittest.main()
