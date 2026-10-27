"""公共工具与能力缺省实现。"""


def _get_public_export(name):
    raise AttributeError(name)


_SUBMODULES = {
    "update_files": ".update_files",
    "exception": ".exception",
    "config_restore": ".config_restore",
    "window": ".window",
    "paths": ".paths",
    "registry": ".registry",
    "mirrorchyan": ".mirrorchyan",
    "host": ".host",
    "hpatchz": ".hpatchz",
    "notification": ".notification",
    "tools": ".tools",
    "security": ".security",
    "constants": ".constants",
    "io": ".io",
    "game_apk": ".game_apk",
    "notification_render": ".notification_render",
    "process_runner": ".process_runner",
    "config_archive": ".config_archive",
    "logger": ".logger",
    "display": ".display",
    "fluxdown_cli": ".fluxdown_cli",
    "supervision": ".supervision",
    "community": ".community",
    "secret": ".secret",
    "emulator_native": ".emulator_native",
    "config_document": ".config_document",
    "LogMonitor": ".LogMonitor",
    "environment": ".environment",
    "notification_template": ".notification_template",
    "process": ".process",
    "audio": ".audio",
    "errors": ".errors",
    "process_platform": ".process_platform",
    "LogPatternExtractor": ".LogPatternExtractor",
    "game_update": ".game_update",
    "vdd": ".vdd",
    "websocket": ".websocket",
    "OCR": ".OCR",
    "expression": ".expression",
    "i18n": ".i18n",
    "emulator": ".emulator",
    "emulator2": ".emulator2",
}


def __getattr__(name):
    if name in _SUBMODULES:
        from importlib import import_module

        value = import_module(_SUBMODULES[name], __name__)
        globals()[name] = value
        return value
    return _get_public_export(name)
