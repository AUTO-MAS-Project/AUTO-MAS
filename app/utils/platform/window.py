from . import IS_WINDOWS

if IS_WINDOWS:
    from .windows.window import *
else:
    from .common.window import *
