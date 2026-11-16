"""Windows 基础 Toast 通知。"""

import ctypes

from .contracts import NotificationSender


def prepare_sender() -> NotificationSender:
    """启动装配时导入依赖；发送失败由通知服务报告，不切换后端。"""
    # winrt-runtime 3.2.1 随包带的旧版 MSVCP140 会抢先加载，导致后续
    # ONNX Runtime 初始化失败。先加载系统运行库，让通知与 OCR 共用新版。
    # LOAD_LIBRARY_SEARCH_SYSTEM32：不从当前目录或 PATH 中寻找同名 DLL。
    ctypes.WinDLL("msvcp140.dll", winmode=0x00000800)

    from windows_toasts import Toast, WindowsToaster

    def send(
        *,
        title: str,
        message: str,
        app_name: str,
        app_icon: str,
        timeout: int,
        ticker: str,
        toast: bool,
    ) -> None:
        notice = Toast()
        notice.text_fields = [title, message]
        WindowsToaster(app_name).show_toast(notice)

    return send
