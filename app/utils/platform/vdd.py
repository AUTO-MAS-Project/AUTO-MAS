from . import IS_WINDOWS

if IS_WINDOWS:
    from .windows.vdd import *
else:
    from .common.vdd import *
