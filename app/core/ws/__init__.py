"""AUTO-MAS 主 WebSocket 子系统。"""

from __future__ import annotations

# 这两个名称表示当前构建具备的兼容能力，不是可切换的第二套运行栈。
# Legacy 桥和事务 outbox 必须始终启用，否则现有插件或 Config v2 提交链会断开。
WS_LEGACY_BRIDGE = True
WS_OUTBOX = True

from . import protocol
from .dialogs import dialog_manager as Dialogs
from .dispatcher import ws_dispatcher as Dispatcher
from .manager import ws_manager as MainConnection
from .publisher import ws_publisher as Publisher

__all__ = [
    "Dialogs",
    "Dispatcher",
    "MainConnection",
    "Publisher",
    "WS_LEGACY_BRIDGE",
    "WS_OUTBOX",
    "protocol",
]
