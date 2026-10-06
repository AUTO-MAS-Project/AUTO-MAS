from . import IS_WINDOWS

if IS_WINDOWS:
    from .windows.display import *
else:
    from .common.display import *
