#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published
#   by the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster361@gmail.com
#   GitHub: https://github.com/AUTO-MAS-Project

"""SRA 公开活动接口：自建源拿不到活动数据时的兜底。

首页各游戏的活动平时来自各自的自建源（PRTS 活动一览、AKEData、官网公告）。
其中有的站点对访问环境挑剔、有的会挡浏览器直连，取不到数据时改用
StarRailAssistant（https://starrailassistant.top）托管的活动 JSON——它的数据由项目方
定期抓取维护，取数发生在对方服务器上，所以用户本机到不了官方站点时也能拿到活动列表。

代价是字段比自建源少：SRA 不给活动分类，也不收录卡池，所以这里把 ``kind`` 留空，
让前端的分类标签自然不显示；卡池由调用方按空处理。
"""

from __future__ import annotations

import httpx
from loguru import logger

SRA_ACTIVITY_BASE = "https://starrailassistant.top/api/v1/activity"

## 对方是静态站，正常几百毫秒就回来了；超时给宽一点，别让浏览器那头干等
SRA_TIMEOUT_SECONDS = 15

## SRA 的时间是不带时区标记的北京时间，前端按本地时区解析会整体偏移，所以补上偏移量
BEIJING_OFFSET = "+08:00"


def _beijing_time(value: object) -> str:
    """把 SRA 的 ``2026-09-29T16:00:00`` 补成带 ``+08:00`` 的 ISO 串。

    已经带时区标记（``Z`` 或偏移量）的原样返回，取不到值返回空串。
    """

    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""
    if text.endswith("Z") or "+" in text[10:]:
        return text
    return f"{text}{BEIJING_OFFSET}"


async def fetch_sra_activities(game: str) -> dict[str, object] | None:
    """取回某个游戏在 SRA 上的活动列表。

    Args:
        game: SRA 的游戏标识（``ak`` 明日方舟、``end`` 终末地、``xtlr`` 星塔旅人）。

    Returns:
        ``{"activities": [...]}``，与各游戏的接口形状一致；取不到返回 ``None``，
        由调用方决定是回落错误信封还是继续走别的兜底。
    """

    url = f"{SRA_ACTIVITY_BASE}/{game}.json"
    try:
        async with httpx.AsyncClient(timeout=SRA_TIMEOUT_SECONDS) as client:
            response = await client.get(url, headers={"Accept": "application/json"})
        response.raise_for_status()
        payload = response.json()
    except Exception as e:
        logger.opt(exception=True).warning(
            f"取 SRA 活动数据失败({game}): {type(e).__name__}: {e}"
        )
        return None

    items = payload.get("activities") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        logger.warning(f"SRA 活动数据格式不对({game}): {type(payload).__name__}")
        return None

    activities = [
        {
            "name": str(item.get("name") or "").strip(),
            ## 分类留空：SRA 不给活动种类，前端据此不显示标签
            "kind": "",
            "description": str(item.get("description") or "").strip(),
            "startTime": _beijing_time(item.get("startTime")),
            "endTime": _beijing_time(item.get("endTime")),
            "cover": str(item.get("cover") or ""),
        }
        for item in items
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    return {"activities": activities}
