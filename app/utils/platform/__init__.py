import sys

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import ctypes

    def _is_elevated() -> bool:
        """当前进程是否已以管理员权限运行（Windows UAC 提权）。

        ``IsUserAnAdmin`` 在进程令牌已提权时返回 True；MAS 自身已提权时，
        子进程会自动继承管理员令牌，无需再走 ShellExecute "runas" 触发 UAC。
        """
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    IS_ELEVATED = _is_elevated()
else:
    IS_ELEVATED = False

__all__ = ["IS_WINDOWS", "IS_ELEVATED"]
