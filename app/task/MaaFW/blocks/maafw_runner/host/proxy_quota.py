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

开跑时换没换日（``proxy_day_rolled``）、跑成功后剩余天数与代理次数怎么算（``success_settlement``）
也在这里，只吃原值、返回新值；写字段与逐条提交留在账号流程里，次数与先后不变。
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


def proxy_day_rolled(last_proxy_date: datetime, today: str) -> bool:
    """账号上次代理的日期（``Data.LastProxyDate``）不是 ``today``：这一轮开跑时要把日期改成今天、
    代理次数清零。``today`` 与 ``proxy_times_used_up`` 同一口径（``proxy_today``）。"""

    return last_proxy_date.strftime("%Y-%m-%d") != today


def success_settlement(proxy_times: int, remained_day: int) -> tuple[int | None, int]:
    """账号这一轮跑成功后的结算：``(新的剩余天数, 新的代理次数)``。

    当天第一次成功（``ProxyTimes`` 为 0）才扣一天剩余天数，``RemainedDay`` 为 -1（不限）不扣；
    不扣时第一项是 None（不写）。代理次数总是加 1。写回与逐条提交由调用方按原来的先后做：
    先写剩余天数（要写时），再写代理次数。
    """

    new_remained = remained_day - 1 if proxy_times == 0 and remained_day != -1 else None
    return new_remained, proxy_times + 1


__all__ = [
    "proxy_day_rolled",
    "proxy_times_used_up",
    "proxy_today",
    "success_settlement",
]
