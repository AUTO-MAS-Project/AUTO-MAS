"""Plugin SDK exports are lazy to preserve host import boundaries."""

from importlib import import_module

_EXPORTS = {'BasePlugin': ('.base.plugin', 'BasePlugin'), 'ExtensionPlugin': ('.base.extension', 'ExtensionPlugin'), 'GameAdapterPlugin': ('.base.game', 'GameAdapterPlugin'), 'GameControl': ('.base.game', 'GameControl'), 'GameTypeDecl': ('.base.game', 'GameTypeDecl'), 'ScriptAdapterPlugin': ('.base.script', 'ScriptAdapterPlugin'), 'ScriptTypeDecl': ('.base.script', 'ScriptTypeDecl')}

def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module, attribute = _EXPORTS[name]
    value = getattr(import_module(module, __package__), attribute)
    globals()[name] = value
    return value

__all__ = list(_EXPORTS)
