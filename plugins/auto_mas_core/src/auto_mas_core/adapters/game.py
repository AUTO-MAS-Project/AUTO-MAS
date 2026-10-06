"""auto_mas_core 游戏/模拟器适配再导出。"""

from app.config import (
    ConfigCollection,
    ConfigGroup,
    Trigger,
    UiVisibility,
    Virtual,
    collection,
    trigger_field,
    ui,
    virtual_field,
)
from app.models.config import (
    EmulatorDeviceEntry,
    EmulatorEntry,
    GameDeviceEntry,
    GameEntry,
)
from app.models.config.game import DeviceStatus
from app.models.config.game import TRIGGER_TICKET
from app.plugin.base.emulator import EmulatorControl, EmulatorExpect
from app.plugin.base.game import (
    DeviceHandle,
    DeviceSubscribeError,
    DeviceSubscription,
    GameAdapterPlugin,
    GameControl,
    GameTypeDecl,
)

__all__ = [
    "TRIGGER_TICKET",
    "ConfigCollection",
    "ConfigGroup",
    "DeviceHandle",
    "DeviceStatus",
    "DeviceSubscribeError",
    "DeviceSubscription",
    "EmulatorControl",
    "EmulatorDeviceEntry",
    "EmulatorEntry",
    "EmulatorExpect",
    "GameAdapterPlugin",
    "GameControl",
    "GameTypeDecl",
    "GameDeviceEntry",
    "GameEntry",
    "Trigger",
    "UiVisibility",
    "Virtual",
    "collection",
    "trigger_field",
    "ui",
    "virtual_field",
]
