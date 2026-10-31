"""创建并持有主连接、分发和发布组件。"""

from .dispatcher import _WSDispatcher
from .manager import _MainConnectionManager
from .publisher import _WSPublisher

Dispatcher = _WSDispatcher()
MainConnection = _MainConnectionManager()
Publisher = _WSPublisher()

__all__ = ["Dispatcher", "MainConnection", "Publisher"]
