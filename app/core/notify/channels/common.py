#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""通知渠道共享的文本分段与 HTTP 错误。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import httpx

from app.models.notification.channel import NotificationDeliveryError


@contextmanager
def http_delivery_errors() -> Iterator[None]:
    """HTTP 渠道在协议边界声明网络和协议配置错误，执行器只消费策略。"""

    try:
        yield
    except (httpx.InvalidURL, httpx.UnsupportedProtocol) as exc:
        raise NotificationDeliveryError(
            "通知地址协议不可用", kind="configuration", retryable=False
        ) from exc
    except (httpx.TransportError, OSError) as exc:
        raise NotificationDeliveryError(
            "通知网络请求失败", kind="transport", retryable=True
        ) from exc


class RemoteHTTPError(NotificationDeliveryError):
    """远端返回明确 HTTP 状态码的请求错误。"""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(
            message,
            kind="rate_limited"
            if status_code == 429
            else "transport"
            if status_code >= 500
            else "rejected",
            retryable=status_code in (408, 429) or status_code >= 500,
        )


def split_text(text: str, limit: int) -> list[str]:
    """将通知文本按字符上限拆分，并尽量在换行处断开。

    各平台网关对过长文本可能返回业务失败；通知正文不能依赖模型自行分段，
    因此在协议适配层做确定性拆分。分段上限由调用方按平台网关限制传入。
    """

    if limit < 1:
        raise ValueError("文本分段长度必须大于 0")
    if not text:
        return [""]
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        boundary = remaining.rfind("\n", 0, limit + 1)
        if boundary <= 0:
            boundary = limit
        chunks.append(remaining[:boundary].rstrip("\n"))
        remaining = remaining[boundary:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks
