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

import re

from app.core.notify.channels.common import RemoteHTTPError, http_delivery_errors
from app.models.notification.channel import HttpDependencies, NotificationDeliveryError


class Sender:
    def __init__(self, dependencies: HttpDependencies) -> None:
        self.dependencies = dependencies

    async def ServerChanPush(self, title: str, content: str, send_key: str) -> None:
        """
        使用Server酱推送通知

        Parameters
        ----------
        title: str
            通知标题
        content: str
            通知内容
        send_key: str
            Server酱的SendKey
        """

        proxy = self.dependencies.read_proxy()
        try:
            if send_key == "":
                raise ValueError("ServerChan SendKey 不能为空")

            # 构造 URL
            if send_key.startswith("sctp"):
                match = re.match(r"^sctp(\d+)t", send_key)
                if match:
                    url = f"https://{match.group(1)}.push.ft07.com/send/{send_key}.send"
                else:
                    raise ValueError("SendKey 格式不正确 (sctp<int>)")
            else:
                url = f"https://sctapi.ftqq.com/{send_key}.send"
        except ValueError as exc:
            self.dependencies.logger.warning(f"ServerChan 配置错误: {exc}")
            raise

        # 请求发送
        params = {"title": title, "desp": content}
        headers = {"Content-Type": "application/json;charset=utf-8"}

        with http_delivery_errors():
            async with self.dependencies.http_factory(proxy=proxy) as client:
                response = await client.post(url, json=params, headers=headers)
                if not response.is_success:
                    raise RemoteHTTPError(
                        response.status_code,
                        f"ServerChan 推送通知失败: HTTP {response.status_code}",
                    )
                try:
                    result = response.json()
                except ValueError as exc:
                    raise NotificationDeliveryError(
                        "ServerChan 响应格式无效", kind="transport", retryable=True
                    ) from exc

        if result.get("code") == 0:
            self.dependencies.logger.success(f"Server酱推送通知成功: {title}")
        else:
            code = result.get("code")
            code_hint = f", code={code}" if type(code) is int else ""
            self.dependencies.logger.warning(
                f"ServerChan 服务端拒绝: HTTP {response.status_code}{code_hint}"
            )
            raise NotificationDeliveryError(
                "ServerChan 服务端拒绝", kind="rejected", retryable=True
            )
