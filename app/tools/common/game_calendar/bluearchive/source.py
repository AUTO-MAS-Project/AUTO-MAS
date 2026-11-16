#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""碧蓝档案活动共享取数：GameKee 请求、SRA 兜底、格式转换与缓存。"""

import time
from datetime import datetime
from typing import Any, Literal

import httpx

from app.tools.common.game_calendar.sra import fetch_sra_activities
from app.utils import get_logger

logger = get_logger("碧蓝档案活动取数")

## 碧蓝档案活动数据取自 GameKee 的活动表。那个接口靠自定义头识别是哪个游戏，
## 少了会返回 {"code": 403, "msg": "缺少游戏信息"}；它同时给三个服，
## 每条带封面图与中文分类（活动 / 总力大决 / 爬塔 / 多倍活动 …）。
## 前端直连会被跨域挡住（响应里没有 access-control-allow-origin），所以由后端中转。
GAMEKEE_ACTIVITY_URL = "https://www.gamekee.com/v1/activity/page-list"
GAMEKEE_HEADERS = {
    "game-alias": "ba",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://www.gamekee.com/ba/huodong/16",
}

## 对外仍沿用 Kivo 时代的服务器标识，内部换成 GameKee 的 serverId
GAMEKEE_SERVER_IDS = {"JP": 15, "Globle": 17, "CN": 16}

## 兜底数据来自 SRA 时用它自己的游戏标识，与 GameKee 的服务器标识一一对应
SRA_BLUEARCHIVE_IDS = {"JP": "ba-jp", "Globle": "ba-global", "CN": "ba-cn"}

## 活动排期变化很慢，缓存十分钟，避免每个前端反复打这个第三方接口
BLUEARCHIVE_CACHE_TTL = 600

## 缓存条数上限：参数组合本来就有限（3 个服 × 页数 × 每页条数），
## 但接口对调用方是开放的，给个上限免得异常调用把进程内存撑大
BLUEARCHIVE_CACHE_MAX_ENTRIES = 32
_bluearchive_cache: dict[str, tuple[float, dict]] = {}


def _prune_bluearchive_cache(now: float) -> None:
    """先清掉过期项，仍超出上限时按写入时间淘汰最旧的。"""

    for key in [
        k for k, v in _bluearchive_cache.items() if now - v[0] >= BLUEARCHIVE_CACHE_TTL
    ]:
        _bluearchive_cache.pop(key, None)

    while len(_bluearchive_cache) >= BLUEARCHIVE_CACHE_MAX_ENTRIES:
        oldest = min(_bluearchive_cache, key=lambda key: _bluearchive_cache[key][0])
        _bluearchive_cache.pop(oldest, None)


def _epoch_seconds(value: str) -> int:
    """ISO 时间串 → Unix 秒；解析不出来返回 0。"""

    try:
        return int(datetime.fromisoformat(value).timestamp())
    except ValueError:
        return 0


def _to_gamekee_rows(activities: list[dict[str, object]]) -> list[dict[str, object]]:
    """把 SRA 的活动条目换成 GameKee 表的字段形状。

    前端只认 GameKee 那一套（title / activity_kind_name / begin_at…），照着拼一份
    省得让前端认识第二套数据源；SRA 已经滤掉非活动条目，分类固定写「活动」。
    """

    rows: list[dict[str, object]] = []
    for item in activities:
        name = str(item.get("name") or "").strip()
        begin = _epoch_seconds(str(item.get("startTime") or ""))
        end = _epoch_seconds(str(item.get("endTime") or ""))
        if not name or not begin or not end:
            continue
        rows.append(
            {
                "title": name,
                "picture": str(item.get("cover") or ""),
                "description": str(item.get("description") or ""),
                "activity_kind_name": "活动",
                "begin_at": begin,
                "end_at": end,
            }
        )
    return rows


async def fetch_bluearchive_activities(
    *, line_type: Literal["JP", "Globle", "CN"], page: int, page_size: int
) -> dict[str, Any]:
    """取回一页活动数据，供首页路由与后台活动判定共用。

    Args:
        line_type: 服务器标识，沿用 JP / Globle / CN 的原文拼写。
        page: 页码，从 1 开始。
        page_size: 每页条数。

    Returns:
        GameKee 原始响应；兜底时返回转换成相同字段的 SRA 活动列表。

    Raises:
        Exception: GameKee 取数失败且 SRA 没有可用数据时，保留原始取数异常。
    """

    cache_key = f"{line_type}:{page}:{page_size}"
    cached = _bluearchive_cache.get(cache_key)
    if cached is not None and time.time() - cached[0] < BLUEARCHIVE_CACHE_TTL:
        return cached[1]

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                GAMEKEE_ACTIVITY_URL,
                params={
                    "serverId": GAMEKEE_SERVER_IDS[line_type],
                    "page_no": page,
                    "limit": page_size,
                    "status": 0,
                    "importance": 0,
                    "sort": -1,
                    "keyword": "",
                },
                headers=GAMEKEE_HEADERS,
            )
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 0:
            raise ValueError(f"GameKee 返回 {data.get('code')}: {data.get('msg')}")
    except Exception as e:
        logger.opt(exception=True).warning(
            f"获取碧蓝档案活动数据失败({line_type}): {type(e).__name__}: {e}"
        )
        ## SRA 一次给全，翻页请求不再重复给同一批活动
        if page > 1:
            return {"code": 0, "data": []}
        fallback = await fetch_sra_activities(SRA_BLUEARCHIVE_IDS[line_type])
        if fallback is None:
            raise
        logger.info(f"碧蓝档案活动数据改用 SRA 兜底({line_type})")
        data = {"code": 0, "data": _to_gamekee_rows(fallback["activities"])}

    _prune_bluearchive_cache(time.time())
    _bluearchive_cache[cache_key] = (time.time(), data)
    return data
