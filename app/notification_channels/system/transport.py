#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


from __future__ import annotations

import asyncio

from app.models.notification_channel import (
    NotificationDeliveryError,
    SystemNoticeDependencies,
)

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


class Sender:
    def __init__(self, dependencies: SystemNoticeDependencies) -> None:
        self.dependencies = dependencies

    async def push_plyer(self, title: str, message: str, ticker: str, t: int) -> None:
        """
        推送系统通知

        Parameters
        ----------
        title: str
            通知标题
        message: str
            通知内容
        ticker: str
            通知横幅
        t: int
            通知持续时间
        """

        config = self.dependencies.config
        if not config.get("IfPushPlyer"):
            return

        self.dependencies.logger.info(f"推送系统通知: {title}")

        if self.dependencies.system_notify is not None:
            await asyncio.to_thread(
                self.dependencies.system_notify,
                title=clip_notify_text(title, PLYER_TITLE_LIMIT),
                message=clip_notify_text(message, PLYER_MESSAGE_LIMIT),
                app_name="AUTO-MAS",
                app_icon=self.dependencies.system_icon,
                timeout=t,
                ticker=ticker,
                toast=True,
            )
        else:
            raise NotificationDeliveryError(
                "plyer.notification 未正确导入，无法推送系统通知",
                kind="unavailable",
                retryable=False,
            )
