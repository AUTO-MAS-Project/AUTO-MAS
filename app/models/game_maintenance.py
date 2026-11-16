#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""公告维护时间窗口，供查询服务与任务调度共用。"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MaintenanceWindow:
    start: datetime
    end: datetime

    def contains(self, now: datetime) -> bool:
        return self.start <= now < self.end

    @property
    def reason(self) -> str:
        # 保留文件时区，避免用户电脑的时区改变公告时间的含义。
        return (
            "游戏维护中，本次跳过（"
            f"{self.start.isoformat(sep=' ', timespec='minutes')} 至 "
            f"{self.end.isoformat(sep=' ', timespec='minutes')}）"
        )
