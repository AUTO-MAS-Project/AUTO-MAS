"""连接 WS core 单例并注册兼容入口。"""

from __future__ import annotations

from typing import Any, Callable

from app.configuration import (
    CONFIG_V2_MODE,
    CONFIG_V2_MODE_AUTHORITATIVE,
)
from app.models.schema import WSEnvelope
from app.utils import get_logger

from .dialogs import dialog_manager
from .dispatcher import ws_dispatcher
from .lifecycle import WSConnection
from .manager import ws_manager
from .publisher import ws_publisher
from .legacy import ws_legacy

logger = get_logger("WS-init")

_initialized = False
_unregister_hooks: list[Callable[[], None]] = []


async def init_ws_core() -> None:
    global _initialized
    if _initialized:
        return

    ws_dispatcher.reopen()
    ws_manager.set_dispatcher(ws_dispatcher)
    ws_publisher.set_ws_manager(ws_manager)
    ws_legacy.set_ws_manager(ws_manager)
    ws_legacy.set_publisher(ws_publisher)

    async def snapshot_handler(envelope: WSEnvelope) -> dict[str, Any]:
        del envelope
        return ws_publisher.snapshot_payload()

    ws_dispatcher.set_snapshot_handler(snapshot_handler)
    dialog_manager.bind(ws_dispatcher, ws_manager, ws_publisher)

    # 连接建立后恢复可合并状态，并触发原有启动队列逻辑。
    _unregister_hooks.append(ws_manager.on_connect(ws_publisher.send_snapshot))

    async def start_startup_queue() -> None:
        from app.core.task_manager import TaskManager

        await TaskManager.start_startup_queue()

    _unregister_hooks.append(ws_manager.on_connect(start_startup_queue))

    # Native Config v2 直接调用本模块的稳定发送入口。仅旧 AppConfig 需要
    # 注册委托；authoritative 模式不得为了兼容桥重新导入旧配置对象图。
    if CONFIG_V2_MODE != CONFIG_V2_MODE_AUTHORITATIVE:
        from app.core.config import (
            _ws_delegate_send_json,
            _ws_delegate_send_websocket_message,
        )

        _ws_delegate_send_json(ws_legacy.send_json)
        _ws_delegate_send_websocket_message(ws_legacy.send_websocket_message)

    _initialized = True
    logger.info("WS core 已初始化")


async def shutdown_ws_core() -> None:
    global _initialized
    if not _initialized:
        return

    for unregister in _unregister_hooks:
        unregister()
    _unregister_hooks.clear()
    dialog_manager.unbind()
    dialog_manager.cancel_all()
    ws_dispatcher.set_snapshot_handler(None)
    await ws_dispatcher.shutdown()
    await ws_manager.shutdown()
    await ws_publisher.outbox.discard_all()

    _initialized = False
    logger.info("WS core 已关闭")


def get_ws_connection() -> WSConnection | None:
    return ws_manager.connection


async def send_websocket_message(
    id: str,
    type: str,
    data: dict[str, Any],
) -> None:
    await ws_legacy.send_websocket_message(id, type, data)


async def send_json(data: dict[str, Any]) -> None:
    await ws_legacy.send_json(data)
