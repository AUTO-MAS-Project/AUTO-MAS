"""应用侧插件基类公开面。"""

from app.models.config.game import TRIGGER_TICKET, DeviceStatus
from app.task import (
    MODE_WORKERS,
    AutoProxyWorker,
    ManualReviewWorker,
    ModeWorker,
    ScriptConfigWorker,
    UserExpander,
)

from .extension import ExtensionPlugin
from .emulator import EmulatorControl, EmulatorExpect
from .game import (
    DeviceHandle,
    DeviceSubscribeError,
    DeviceSubscription,
    GameAdapterPlugin,
    GameControl,
    GameTypeDecl,
)
from .plugin import BasePlugin
from .script import ScriptAdapterPlugin, ScriptTypeDecl

__all__ = [
    "MODE_WORKERS",
    "TRIGGER_TICKET",
    "AutoProxyWorker",
    "BasePlugin",
    "DeviceHandle",
    "DeviceStatus",
    "DeviceSubscribeError",
    "DeviceSubscription",
    "EmulatorControl",
    "EmulatorExpect",
    "ExtensionPlugin",
    "GameAdapterPlugin",
    "GameControl",
    "GameTypeDecl",
    "ManualReviewWorker",
    "ModeWorker",
    "ScriptAdapterPlugin",
    "ScriptConfigWorker",
    "UserExpander",
    "ScriptTypeDecl",
]
