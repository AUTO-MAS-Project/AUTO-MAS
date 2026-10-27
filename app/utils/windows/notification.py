"""Windows 基础 Toast 通知。"""

from collections.abc import Callable


def prepare_sender() -> Callable[..., None]:
    """启动装配时导入依赖；发送失败由通知服务报告，不切换后端。"""
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
