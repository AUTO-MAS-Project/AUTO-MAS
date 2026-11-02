#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster_361@163.com
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""碧蓝航线活动数据：从碧蓝海事局 WIKI 的「活动日历」整理。

官方站（game.bilibili.com）与日服站都是纯前端渲染，HTML 里没有活动内容；
GameKee 没有开放碧蓝航线的活动接口，其它 wiki 又挡爬虫。能稳定拿到的只有
BWIKI：它的「活动日历」页是维基文本，每条写着 ``[[页面|「活动名」]]<small>10.15-11.05</small>``，
正好是卡片要的活动名与起止日期。

那份日历只有月日、没有时刻，所以开始按当天 10:00、结束按 23:59 落到北京时间，
误差最多几个小时——对「还剩几天」的显示足够，精确到分钟的场合不要用它。

活动封面用两张固定图：日历页与条目页都没有能直接用的活动宣传图（头图在维基里
还是红链，条目页里的图是换装立绘和头像），所以「世界巡游」单独一张、其余活动共用
一张。两张都放在 B 站图床，前端引用时带 no-referrer，否则会被对方的防盗链挡掉。
"""

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.utils import get_logger

logger = get_logger("碧蓝航线活动")

WIKI_BASE = "https://wiki.biligame.com/blhx"
WIKI_API = f"{WIKI_BASE}/api.php"
## 日历页的页面名；条目名带书名号，分类与时间都在这一页里
CALENDAR_PAGE = "活动日历"

CACHE_TTL_SECONDS = 600
REQUEST_TIMEOUT_SECONDS = 20

## 那个 WIKI 前面有 WAF：UA 只写到一半、或者缺 Accept 这一套，它直接回 567
WIKI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": f"{WIKI_BASE}/",
}

BEIJING = timezone(timedelta(hours=8))

## 活动封面：「世界巡游」单独一张，其余活动共用一张
DEFAULT_COVER = (
    "https://i0.hdslb.com/bfs/new_dyn/7be0c3be64a99903ee5f13d41236121e233114659.jpg"
)
WORLD_PATROL_COVER = (
    "https://i0.hdslb.com/bfs/new_dyn/67bf8f9d99263e6aef28c0682903ae2f233114659.png"
)
## 名字里带这个的活动（如「世界巡游-第三十一期」）用上面那张单独的图
WORLD_PATROL_KEYWORD = "世界巡游"

## [[页面|「活动名」]]<small>10.15-11.05</small>
## 页面名里可能带 #锚点，显示文本可能缺省（此时退回页面名）
CALENDAR_ROW = re.compile(
    r"\[\[(?P<page>[^\]|]+?)(?:\|(?P<label>[^\]]*))?\]\]\s*"
    r"<small>\s*(?P<start_month>\d{1,2})\.(?P<start_day>\d{1,2})\s*"
    r"-\s*(?P<end_month>\d{1,2})\.(?P<end_day>\d{1,2})\s*</small>"
)
## 活动日历只给活动名和月日，条目页里的图是换装、头像、logo 这类杂图，
## 真正当封面的头图在维基里还是红链（文件没上传），所以这一版不给封面：
## 卡片没有图会走素色样式，比放一张换装立绘好看
WIKI_COMMENT = re.compile(r"<!--.*?-->", re.S)
## 活动名统一从书名号里取，取不到再退回页面名
QUOTED_NAME = re.compile(r"「(?P<name>[^「」]+)」")

_cache: tuple[float, dict[str, Any]] | None = None


def _at(month: int, day: int, hour: int, minute: int, year: int) -> datetime:
    """按北京时间拼一个时刻"""

    return datetime(year, month, day, hour, minute, tzinfo=BEIJING)


async def _wikitext(client: httpx.AsyncClient, page: str) -> str:
    """取某一页的维基文本，页面不存在时给空串"""

    response = await client.get(
        WIKI_API,
        params={
            "action": "parse",
            "page": page,
            "prop": "wikitext",
            "format": "json",
            "formatversion": "2",
        },
    )
    response.raise_for_status()
    payload = response.json()
    parsed = payload.get("parse") if isinstance(payload, dict) else None
    if not isinstance(parsed, dict):
        return ""
    text = parsed.get("wikitext")
    return text if isinstance(text, str) else ""


def _build_activity(row: re.Match[str], now: datetime) -> dict[str, Any] | None:
    """把日历里的一行整理成卡片要的字段；起止不合法就返回 None。

    日历只写月日，年份得自己推：同一组月日在前一年、当年、次年各有一种落法，
    取「现在正好落在区间内」的那种；没有进行中的，就取最近一个还没开始的，
    再没有才取刚刚结束的。跨年（12 月开到 1 月）也在这里一并处理——只按当年
    拼再给结束年 +1 的话，年初读跨年活动会把它整个挪到下一轮。
    """

    page = row.group("page").strip()
    label = (row.group("label") or "").strip()
    matched = QUOTED_NAME.search(label)
    name = matched.group("name").strip() if matched else label or page
    if not name:
        return None

    start_month = int(row.group("start_month"))
    start_day = int(row.group("start_day"))
    end_month = int(row.group("end_month"))
    end_day = int(row.group("end_day"))
    ## 结束的月日写在开始之前（12.20-01.10）就是跨年
    spans_year = (end_month, end_day) < (start_month, start_day)

    candidates: list[tuple[datetime, datetime]] = []
    for start_year in (now.year - 1, now.year, now.year + 1):
        try:
            start = _at(start_month, start_day, 10, 0, start_year)
            end = _at(
                end_month,
                end_day,
                23,
                59,
                start_year + 1 if spans_year else start_year,
            )
        except ValueError:
            ## 2 月 29 日之类的边界，日历写错就跳过这一种落法
            continue
        candidates.append((start, end))

    if not candidates:
        return None

    running = [item for item in candidates if item[0] <= now < item[1]]
    if running:
        start, end = running[-1]
    else:
        ## 没有进行中的就取「离现在最近」的一场：刚结束的和马上要开始的都算。
        ## 不能无条件挑未来那种——日历里已经到期、还没撤下的活动会被推成下一年的
        ## 排期，横幅也会拿它当下一场
        def distance(item: tuple[datetime, datetime]) -> float:
            start_at, end_at = item
            return min(
                abs((start_at - now).total_seconds()),
                abs((now - end_at).total_seconds()),
            )

        start, end = min(candidates, key=distance)

    cover = WORLD_PATROL_COVER if WORLD_PATROL_KEYWORD in name else DEFAULT_COVER

    return {
        "name": name,
        "description": "",
        "startTime": start.isoformat(),
        "endTime": end.isoformat(),
        "cover": cover,
        "kind": "",
        "url": f"{WIKI_BASE}/{quote(page)}",
    }


async def fetch_azurlane_activities(*, force: bool = False) -> dict[str, Any] | None:
    """取回碧蓝航线当前的活动。

    成功时返回与其它活动源一致的形状（``activities`` 里每条含活动名、起止、
    封面与条目页地址）；日历取不到时返回 None，由调用方决定怎么降级。
    """

    global _cache
    if not force and _cache is not None and time.time() - _cache[0] < CACHE_TTL_SECONDS:
        return _cache[1]

    now = datetime.now(BEIJING)
    headers = WIKI_HEADERS
    try:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT_SECONDS, headers=headers, follow_redirects=True
        ) as client:
            text = WIKI_COMMENT.sub("", await _wikitext(client, CALENDAR_PAGE))
            if not text.strip():
                raise ValueError("活动日历页内容为空")

            activities: list[dict[str, Any]] = []
            ## 同名活动可能是不同场次（复刻），去重得连起止一起比
            seen: set[tuple[str, str, str]] = set()
            for row in CALENDAR_ROW.finditer(text):
                activity = _build_activity(row, now)
                if activity is None:
                    continue
                key = (activity["name"], activity["startTime"], activity["endTime"])
                if key in seen:
                    continue
                seen.add(key)
                activities.append(activity)

            if not activities:
                raise ValueError("活动日历页没有解析出活动")

    except Exception as e:
        logger.opt(exception=True).warning(
            f"获取碧蓝航线活动失败: {type(e).__name__}: {e}"
        )
        ## 取不到就给上次成功的结果，但要说清楚这是旧数据：前端据此提示「可能已过期」，
        ## 也不会把它当成一次成功而清掉重试
        if _cache is not None:
            return {**_cache[1], "stale": True}
        return None

    data = {
        "version": "",
        "versionName": "",
        "startTime": "",
        "endTime": "",
        "cover": "",
        "activities": activities,
        # 正常取到就是新鲜数据；回退旧缓存时上面会把它改成 True
        "stale": False,
    }
    _cache = (time.time(), data)
    return data
