import sys

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

__all__ = ["IS_WINDOWS", "IS_ELEVATED", "is_admin"]
