#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""MFW 账号「今日代理次数已达上限」的唯一判据。

账号任务的运行前检查（``runner_task.check``）据此把账号记「跳过」；管理器筛账号时
据此判断这一轮还有没有账号真会跑，全员都到上限就不做运行前更新与环境确认。两处
必须同一口径，「今天」也只按这里算（游戏日界 UTC+4，与结算代理次数时写的
``LastProxyDate`` 一致）。不 import maa，管理器可以直接用。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.utils import UTC4


def proxy_today(now: datetime | None = None) -> str:
    """代理次数按天计的「今天」：``YYYY-MM-DD``（UTC+4）。"""

    return (now or datetime.now(tz=UTC4)).astimezone(UTC4).strftime("%Y-%m-%d")


def proxy_times_used_up(user_config: Any, script_config: Any, today: str) -> bool:
    """这个账号今天的代理次数是否已用完（``Run.ProxyTimesLimit`` 为 0 表示不限）。"""

    limit = script_config.Run.ProxyTimesLimit
    if limit == 0:
        return False
    data = user_config.Data
    proxy_times = (
        data.ProxyTimes if data.LastProxyDate.strftime("%Y-%m-%d") == today else 0
    )
    return proxy_times >= limit


__all__ = ["proxy_times_used_up", "proxy_today"]
