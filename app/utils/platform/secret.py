from app.utils.platform import IS_WINDOWS

if IS_WINDOWS:
    from .windows.secret import *
else:
    from .common.secret import *
