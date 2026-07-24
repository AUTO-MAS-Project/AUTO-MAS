"""旧 ``Config`` WebSocket API 的无损兼容适配器。"""

from __future__ import annotations

from typing import Any


class WSLegacyAdapter:
    """只转交稳定旧信封，不依据 ``id`` 猜测或改写消息语义。"""

    def __init__(self) -> None:
        self._ws_manager: Any = None
        self._publisher: Any = None

    def set_ws_manager(self, manager: Any) -> None:
        self._ws_manager = manager

    def set_publisher(self, publisher: Any) -> None:
        self._publisher = publisher

    @property
    def broadcast(self) -> Any:
        """返回真实 ``app.core.Broadcast``，不创建第二套订阅池。"""

        from app.core.broadcast import Broadcast

        return Broadcast

    async def send_websocket_message(
        self,
        id: str,
        type: str,
        data: dict[str, Any],
    ) -> None:
        if self._publisher is not None:
            await self._publisher.send_legacy(id, type, data)

    async def send_json(self, data: dict[str, Any]) -> None:
        if self._ws_manager is not None:
            await self._ws_manager.send_json(data)

    async def handle_inbound(self, data: dict[str, Any]) -> None:
        """兼容入口；主 manager 已统一广播，避免在这里重复扇出。"""

        del data


ws_legacy = WSLegacyAdapter()
