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

import calendar
from datetime import datetime

from auto_mas_core.host.core_notify_task_content import (
    prepare_screenshot_images as prepare_screenshot_images,
)
from auto_mas_core.host.core_notify_task_content import (
    screenshot_entries as screenshot_entries,
)
from auto_mas_core.host.utils import constants as _utils_constants
from auto_mas_core.host.utils import get_logger

logger = get_logger("MAA")


def _current_week_marker(now: datetime) -> str:
    """返回 ISO 周标记。"""

    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year:04d}-W{iso_week:02d}"


def _current_month_marker(now: datetime) -> str:
    """按 UTC+4 返回月份标记。"""

    # TODO: 动态时区适配时按账号 Info.Server 的 get_game_day_tz() 判断绿票月份；
    # 同步 GreenTicketStoreMonth 的时区声明及前端完成态，保留完整 UTC 时间存储。
    # 固定 UTC+4 在 EN、JP/KR 的月界存在误判，待上述适配统一处理。
    return now.astimezone(_utils_constants.UTC4).strftime("%Y-%m")


def _should_run_annihilation(
    start_weekday: str,
    completed_week: str,
    now: datetime,
) -> bool:
    """判断当前账号本次是否应执行剿灭。"""

    if completed_week == _current_week_marker(now):
        return False
    return now.weekday() >= getattr(calendar, start_weekday.upper())
