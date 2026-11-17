"""Plugin SDK exports are lazy to preserve host import boundaries."""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base.extension import ExtensionPlugin as ExtensionPlugin
    from .base.game import GameAdapterPlugin as GameAdapterPlugin
    from .base.game import GameControl as GameControl
    from .base.game import GameTypeDecl as GameTypeDecl
    from .base.plugin import BasePlugin as BasePlugin
    from .base.script import ScriptAdapterPlugin as ScriptAdapterPlugin
    from .base.script import ScriptTypeDecl as ScriptTypeDecl

_EXPORTS = {
    "BasePlugin": (".base.plugin", "BasePlugin"),
    "ExtensionPlugin": (".base.extension", "ExtensionPlugin"),
    "GameAdapterPlugin": (".base.game", "GameAdapterPlugin"),
    "GameControl": (".base.game", "GameControl"),
    "GameTypeDecl": (".base.game", "GameTypeDecl"),
    "ScriptAdapterPlugin": (".base.script", "ScriptAdapterPlugin"),
    "ScriptTypeDecl": (".base.script", "ScriptTypeDecl"),
}


def __getattr__(name: str):
    """按公开导出表惰性加载插件基类并缓存，避免仅导入框架入口就初始化宿主依赖。"""
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
    "ScriptAdapterPlugin",
    "ScriptTypeDecl",
]
