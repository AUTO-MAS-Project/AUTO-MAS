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

"""MSS 用户页要的那点运行期信息：个人版「灾变防线」这一期打了没。

编排本身在 ``flavor.py`` 的 ``_arrange_defense`` 里，这里只**只读**地把它的记账摊开给界面看——
用户页上要显示「本期未打 / 已打」，而「这一期」是怎么算的（官网那一篇公告的开始时刻）只在编排
那一处有，不在前端复刻一遍，否则两边的口径早晚会漂。

开关不在这里：那是全局的 ``Function.IfPersonalMss``，前端直接走设置接口读写。
"""

from __future__ import annotations

import json
from typing import Any

from app.core import Config
from app.task.MSS.flavor import DEFENSE_ACTIVITY_NAME, DEFENSE_MAX_FAILED_DAYS
from app.tools.stella_official import permanent_activity_window
from app.utils import get_logger

logger = get_logger("MSS 灾变防线状态")


def _record(raw: Any) -> dict[str, Any]:
    """把 ``Data.PersonalMssDefense`` 读成字典；读不出形状就当空记录。"""

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return raw if isinstance(raw, dict) else {}


def _failed_days(record: dict[str, Any]) -> list[str]:
    """只认字符串元素：被写成字符串的列表会逐字符数出天来，那种记录直接当空。"""

    raw = record.get("failed_days")
    if not isinstance(raw, list):
        return []
    return [day for day in raw if isinstance(day, str)]


async def defense_status(script_id: str, user_id: str) -> dict[str, Any]:
    """这一期打没打：``Data.PersonalMssDefense`` 那份记账 + 官网当前的期。

    记录里的 ``done`` 只在**同一期**里才算数——换期之后上一期的「已打」不该显示成本期的，
    这一点与 ``_arrange_defense`` 里换期就整份作废是同一条口径。
    """

    try:
        _, data = await Config.get_user(script_id, user_id)
    except Exception as exc:  # noqa: BLE001 - 脚本或用户已经不在：按「没有记录」继续，别拦页面
        logger.warning(f"读用户配置失败（{script_id} / {user_id}）：{exc}")
        data = {}
    record = _record((data.get("Data") or {}).get("PersonalMssDefense"))
    period = await permanent_activity_window(DEFENSE_ACTIVITY_NAME)

    same_period = bool(period) and str(record.get("period") or "") == period
    failed_days = _failed_days(record) if same_period else []

    return {
        "period": period or "",
        # 取不到期（官网读不出来）时按「未知」显示，别把它说成「本期没打」
        "known": bool(period),
        "done": bool(record.get("done")) if same_period else False,
        "armed": bool(record.get("armed")) if same_period else False,
        "failedDays": failed_days,
        "givenUp": len(failed_days) >= DEFENSE_MAX_FAILED_DAYS,
    }
