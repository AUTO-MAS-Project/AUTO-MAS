"""Plugin SDK exports are lazy to preserve host import boundaries."""

from importlib import import_module

_EXPORTS = {'BasePlugin': ('.plugin', 'BasePlugin'), 'ExtensionPlugin': ('.extension', 'ExtensionPlugin'), 'GameAdapterPlugin': ('.game', 'GameAdapterPlugin'), 'GameControl': ('.game', 'GameControl'), 'GameTypeDecl': ('.game', 'GameTypeDecl'), 'DeviceHandle': ('.game', 'DeviceHandle'), 'DeviceSubscription': ('.game', 'DeviceSubscription'), 'DeviceSubscribeError': ('.game', 'DeviceSubscribeError'), 'EmulatorControl': ('.emulator', 'EmulatorControl'), 'EmulatorExpect': ('.emulator', 'EmulatorExpect'), 'ScriptAdapterPlugin': ('.script', 'ScriptAdapterPlugin'), 'ScriptTypeDecl': ('.script', 'ScriptTypeDecl'), 'DeviceStatus': ('app.models.config.game', 'DeviceStatus'), 'TRIGGER_TICKET': ('app.models.config.game', 'TRIGGER_TICKET'), 'MODE_WORKERS': ('app.task', 'MODE_WORKERS'), 'AutoProxyWorker': ('app.task', 'AutoProxyWorker'), 'ManualReviewWorker': ('app.task', 'ManualReviewWorker'), 'ModeWorker': ('app.task', 'ModeWorker'), 'ScriptConfigWorker': ('app.task', 'ScriptConfigWorker'), 'UserExpander': ('app.task', 'UserExpander')}

def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module, attribute = _EXPORTS[name]
    value = getattr(import_module(module, __package__), attribute)
    globals()[name] = value
    return value

__all__ = list(_EXPORTS)
