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


from datetime import datetime, timedelta, timezone

from auto_mas_core.host.core_notify_task_content import (
    prepare_screenshot_images as prepare_screenshot_images,
)
from auto_mas_core.host.core_notify_task_content import (
    screenshot_entries as screenshot_entries,
)
from auto_mas_core.host.utils import get_logger

logger = get_logger("MAA")


def _maa_activity_state(
    raw_data: dict, server: str, *, now: datetime
) -> tuple[bool, bool]:
    """从已有区服活动缓存判断活动与限时资源全开放时段。"""

    server_data = raw_data.get("Official" if server == "Bilibili" else server, {})

    def is_open(activity: dict) -> bool:
        """按活动声明的时区和起止时间判断当前是否处于活动开放期。"""
        if not activity:
            return False
        activity_timezone = timezone(timedelta(hours=activity.get("TimeZone", 8)))
        start = datetime.strptime(
            activity["UtcStartTime"], "%Y/%m/%d %H:%M:%S"
        ).replace(tzinfo=activity_timezone)
        end = datetime.strptime(activity["UtcExpireTime"], "%Y/%m/%d %H:%M:%S").replace(
            tzinfo=activity_timezone
        )
        return start < now < end

    return (
        any(
            is_open(item["Activity"])
            for item in server_data.get("sideStoryStage", {}).values()
        ),
        is_open(server_data.get("resourceCollection", {})),
    )
