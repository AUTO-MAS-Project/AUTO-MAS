"""系统通知的公共 plyer 实现。"""

from .contracts import NotificationSender

# Windows 通知字段分别保留 63 和 255 个 UTF-16 代码单元，余下一位给结尾空字符。
PLYER_TITLE_LIMIT = 63
PLYER_MESSAGE_LIMIT = 255


def clip_notify_text(text: str, limit: int) -> str:
    """
    按 Windows 通知字段上限截断文本，超出部分以省略号收尾

    ``ctypes.c_wchar`` 数组按 UTF-16 代码单元计数，而 ``len()`` 数的是码位：
    emoji 等非 BMP 字符占 1 个码位却要 2 个代码单元，按码位截断仍会溢出，因此
    这里按编码后的代码单元数裁剪。截断点落在代理对中间时，``errors="ignore"``
    会丢弃残缺的那一半。

    Args:
        text: 待截断的文本
        limit: 目标字段可用的 UTF-16 代码单元数（已扣除结尾空字符）

    Returns:
        str: 编码后不超过 ``limit`` 个 UTF-16 代码单元的文本
    """

    encoded = text.encode("utf-16-le")
    if len(encoded) // 2 <= limit:
        return text

    clipped = encoded[: (limit - 1) * 2].decode("utf-16-le", errors="ignore")

    return f"{clipped}…"


def prepare_sender() -> NotificationSender:
    """在启动线程解析可选后端，再将同步发送函数交给工作线程。"""
    from plyer import notification

    notify = notification.notify

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
        notify(
            title=clip_notify_text(title, PLYER_TITLE_LIMIT),
            message=clip_notify_text(message, PLYER_MESSAGE_LIMIT),
            app_name=app_name,
            app_icon=app_icon,
            timeout=timeout,
            ticker=ticker,
            toast=toast,
        )

    return send
