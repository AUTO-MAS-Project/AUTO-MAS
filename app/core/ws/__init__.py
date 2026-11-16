"""创建并持有主连接、命令、分发和发布组件。"""

from .commands import _WSCommandRegistry
from .dispatcher import _WSDispatcher
from .manager import _MainConnectionManager
from .publisher import _WSPublisher

Commands = _WSCommandRegistry()
Dispatcher = _WSDispatcher()
MainConnection = _MainConnectionManager()
Publisher = _WSPublisher()

__all__ = ["Commands", "Dispatcher", "MainConnection", "Publisher"]
