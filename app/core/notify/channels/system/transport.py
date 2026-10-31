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

from app.models.notification.channel import (
    NotificationDeliveryError,
    SystemNoticeDependencies,
)


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
                title=title,
                message=message,
                app_name="AUTO-MAS",
                app_icon=self.dependencies.system_icon,
                timeout=t,
                ticker=ticker,
                toast=True,
            )
        else:
            raise NotificationDeliveryError(
                "系统通知依赖不可用，无法推送系统通知",
                kind="unavailable",
                retryable=False,
            )
