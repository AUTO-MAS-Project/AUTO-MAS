def _get_public_export(name):
    raise AttributeError(name)


_SUBMODULES = {"OCRtool": ".OCRtool"}


def __getattr__(name):
    if name in _SUBMODULES:
        from importlib import import_module

        value = import_module(_SUBMODULES[name], __name__)
        globals()[name] = value
        return value
    return _get_public_export(name)
