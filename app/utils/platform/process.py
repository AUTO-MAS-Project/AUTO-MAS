from . import IS_WINDOWS
from .common.process_platform import CommonProcessPlatform

if IS_WINDOWS:
    from .windows.process import WindowsProcessPlatform

    platform_process = WindowsProcessPlatform()
else:
    platform_process = CommonProcessPlatform()
