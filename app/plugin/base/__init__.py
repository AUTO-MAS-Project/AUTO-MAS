"""Plugin SDK exports are lazy to preserve host import boundaries."""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.config.game import TRIGGER_TICKET as TRIGGER_TICKET
    from app.models.config.game import DeviceStatus as DeviceStatus
    from app.task import (
        MODE_WORKERS as MODE_WORKERS,
    )
    from app.task import (
        AutoProxyWorker as AutoProxyWorker,
    )
    from app.task import (
        ModeWorker as ModeWorker,
    )
    from app.task import (
        ScriptConfigWorker as ScriptConfigWorker,
    )
    from app.task import (
        ScriptViewWorker as ScriptViewWorker,
    )
    from app.task import (
        UserExpander as UserExpander,
    )

    from .emulator import EmulatorControl as EmulatorControl
    from .emulator import EmulatorExpect as EmulatorExpect
    from .extension import ExtensionPlugin as ExtensionPlugin
    from .game import (
        DeviceHandle as DeviceHandle,
    )
    from .game import (
        DeviceSubscribeError as DeviceSubscribeError,
    )
    from .game import (
        DeviceSubscription as DeviceSubscription,
    )
    from .game import (
        GameAdapterPlugin as GameAdapterPlugin,
    )
    from .game import (
        GameControl as GameControl,
    )
    from .game import (
        GameTypeDecl as GameTypeDecl,
    )
    from .plugin import BasePlugin as BasePlugin
    from .script import ScriptAdapterPlugin as ScriptAdapterPlugin
    from .script import ScriptTypeDecl as ScriptTypeDecl

_EXPORTS = {
    "BasePlugin": (".plugin", "BasePlugin"),
    "ExtensionPlugin": (".extension", "ExtensionPlugin"),
    "GameAdapterPlugin": (".game", "GameAdapterPlugin"),
    "GameControl": (".game", "GameControl"),
    "GameTypeDecl": (".game", "GameTypeDecl"),
    "DeviceHandle": (".game", "DeviceHandle"),
    "DeviceSubscription": (".game", "DeviceSubscription"),
    "DeviceSubscribeError": (".game", "DeviceSubscribeError"),
    "EmulatorControl": (".emulator", "EmulatorControl"),
    "EmulatorExpect": (".emulator", "EmulatorExpect"),
    "ScriptAdapterPlugin": (".script", "ScriptAdapterPlugin"),
    "ScriptTypeDecl": (".script", "ScriptTypeDecl"),
    "DeviceStatus": ("app.models.config.game", "DeviceStatus"),
    "TRIGGER_TICKET": ("app.models.config.game", "TRIGGER_TICKET"),
    "MODE_WORKERS": ("app.task", "MODE_WORKERS"),
    "AutoProxyWorker": ("app.task", "AutoProxyWorker"),
    "ScriptViewWorker": ("app.task", "ScriptViewWorker"),
    "ModeWorker": ("app.task", "ModeWorker"),
    "ScriptConfigWorker": ("app.task", "ScriptConfigWorker"),
    "UserExpander": ("app.task", "UserExpander"),
}


def __getattr__(name: str):
    """按需加载并缓存插件基础类型，未公开的名称按普通模块属性缺失处理。"""
    if name not in _EXPORTS:
        raise AttributeError(name)
    module, attribute = _EXPORTS[name]
    value = getattr(import_module(module, __package__), attribute)
    globals()[name] = value
    return value


__all__ = [
    "BasePlugin",
    "ExtensionPlugin",
    "GameAdapterPlugin",
    "GameControl",
    "GameTypeDecl",
    "DeviceHandle",
    "DeviceSubscription",
    "DeviceSubscribeError",
    "EmulatorControl",
    "EmulatorExpect",
    "ScriptAdapterPlugin",
    "ScriptTypeDecl",
    "DeviceStatus",
    "TRIGGER_TICKET",
    "MODE_WORKERS",
    "AutoProxyWorker",
    "ScriptViewWorker",
    "ModeWorker",
    "ScriptConfigWorker",
    "UserExpander",
]
