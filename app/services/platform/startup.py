from app.utils import IS_WINDOWS

if IS_WINDOWS:
    from .windows.startup import WindowsStartupManager

    startup = WindowsStartupManager()
else:
    from .common.startup import CommonStartupManager

    startup = CommonStartupManager()
