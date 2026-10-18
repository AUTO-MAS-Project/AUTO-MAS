import sys
from functools import lru_cache

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import ctypes

    def is_admin() -> bool:
        """当前进程是否已以管理员权限运行（Windows UAC 提权）。

        ``IsUserAnAdmin`` 在进程令牌已提权时返回 True；MAS 自身已提权时，
        子进程会自动继承管理员令牌，无需再走 ShellExecute "runas" 触发 UAC。
        """
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
else:

    def is_admin() -> bool:
        """非 Windows 平台无 UAC 概念，视为已以管理员权限运行。"""
        return True


# 模块加载时求值一次：子进程会继承本进程的管理员令牌，据此决定是否走 runas
IS_ELEVATED = is_admin()


@lru_cache(maxsize=1)
def is_long_path_supported() -> bool:
    """当前系统是否已开启长路径支持（``LongPathsEnabled``）。

    非 Windows 无此限制，视为已支持；Windows 上读注册表开关，读不到（键不
    存在、无权限）按**未开启**处理。开关改完要重启才生效，故只求值一次。
    """

    if not IS_WINDOWS:
        return True
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem"
        ) as key:
            return int(winreg.QueryValueEx(key, "LongPathsEnabled")[0]) == 1
    except OSError:
        return False


__all__ = ["IS_WINDOWS", "IS_ELEVATED", "is_admin", "is_long_path_supported"]
