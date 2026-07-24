"""应用内弹窗的稳定 WS 请求-响应关联。"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Callable

from pydantic import ValidationError

from app.models.schema import WSEnvelope, WSDialogRequestData, WSDialogResponseData
from app.utils import get_logger

from . import protocol

logger = get_logger("WS弹窗")


class DialogManager:
    """使用 ``Main/dialog.request|response`` 和 ``data.requestId`` 关联。"""

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[bool]] = {}
        self._requests: dict[str, WSDialogRequestData] = {}
        self._publisher: Any = None
        self._unbind_dispatcher: Callable[[], None] | None = None
        self._unbind_connect: Callable[[], None] | None = None

    def bind(self, dispatcher: Any, manager: Any, publisher: Any) -> None:
        if self._unbind_dispatcher is not None:
            return
        self._publisher = publisher
        self._unbind_dispatcher = dispatcher.register(
            protocol.ID_MAIN,
            protocol.DIALOG_RESPONSE,
            self._on_response,
        )
        self._unbind_connect = manager.on_connect(self._resend_pending)

    def unbind(self) -> None:
        if self._unbind_dispatcher is not None:
            self._unbind_dispatcher()
            self._unbind_dispatcher = None
        if self._unbind_connect is not None:
            self._unbind_connect()
            self._unbind_connect = None
        self._publisher = None

    async def ask(
        self,
        title: str,
        message: str,
        options: list[str] | None = None,
        task_id: str | None = None,
        timeout: float | None = None,
    ) -> bool:
        request_id = str(uuid.uuid4())
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        request = WSDialogRequestData(
            requestId=request_id,
            taskId=task_id,
            title=title,
            message=message,
            options=options or ["是", "否"],
        )
        self._pending[request_id] = future
        self._requests[request_id] = request

        if self._publisher is not None:
            await self._publisher.send(
                protocol.ID_MAIN,
                protocol.DIALOG_REQUEST,
                request,
            )

        try:
            if timeout is None:
                return await future
            return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
        finally:
            self._pending.pop(request_id, None)
            self._requests.pop(request_id, None)
            if not future.done():
                future.cancel()

    async def request(
        self,
        kind: str,
        title: str = "",
        message: str = "",
        options: list[str] | None = None,
        timeout: float | None = 30.0,
        task_id: str | None = None,
    ) -> bool:
        """兼容 Experimental Alpha 的 ``request`` 名称。"""

        del kind
        try:
            return await self.ask(
                title=title,
                message=message,
                options=options,
                task_id=task_id,
                timeout=timeout,
            )
        except TimeoutError:
            return False

    async def _resend_pending(self) -> None:
        if self._publisher is None:
            return
        for request in list(self._requests.values()):
            await self._publisher.send(
                protocol.ID_MAIN,
                protocol.DIALOG_REQUEST,
                request,
            )

    def _on_response(self, envelope: WSEnvelope) -> None:
        try:
            response = WSDialogResponseData.model_validate(envelope.data)
        except ValidationError:
            logger.warning("弹窗响应数据不合法，已丢弃")
            return
        future = self._pending.get(response.requestId)
        if future is None or future.done():
            logger.debug(f"弹窗响应无等待方: requestId={response.requestId}")
            return
        future.set_result(response.choice)

    def resolve(self, request_id: str, result: str, value: Any = None) -> None:
        """兼容旧测试入口。"""

        future = self._pending.get(request_id)
        if future is not None and not future.done():
            future.set_result(bool(value if value is not None else result))

    def cancel_all(self) -> None:
        for future in list(self._pending.values()):
            if not future.done():
                future.cancel()
        self._pending.clear()
        self._requests.clear()


dialog_manager = DialogManager()
Dialogs = dialog_manager
