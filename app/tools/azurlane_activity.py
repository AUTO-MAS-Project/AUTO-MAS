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

活动封面这一版不给：日历页本身不带图，条目页里的图不是换装立绘就是头像、logo，
真正当封面的头图在维基里还是红链（文件没上传）。卡片拿不到图会走素色样式，
比塞一张换装立绘顺眼。活动条目仍然带 ``url``，点开能看到对应页。
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


def _build_activity(row: re.Match[str], year: int) -> dict[str, Any] | None:
    """把日历里的一行整理成卡片要的字段；起止不合法就返回 None"""

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

    try:
        start = _at(start_month, start_day, 10, 0, year)
        end = _at(end_month, end_day, 23, 59, year)
    except ValueError:
        ## 2 月 29 日之类的边界，日历写错就跳过这条
        return None
    ## 12 月开到 1 月的活动跨年
    if end <= start:
        try:
            end = _at(end_month, end_day, 23, 59, year + 1)
        except ValueError:
            return None

    return {
        "name": name,
        "description": "",
        "startTime": start.isoformat(),
        "endTime": end.isoformat(),
        "cover": "",
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

    headers = WIKI_HEADERS
    try:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT_SECONDS, headers=headers, follow_redirects=True
        ) as client:
            text = WIKI_COMMENT.sub("", await _wikitext(client, CALENDAR_PAGE))
            if not text.strip():
                logger.warning("碧蓝航线活动日历页内容为空")
                return None

            year = datetime.now(BEIJING).year
            activities: list[dict[str, Any]] = []
            seen: set[str] = set()
            for row in CALENDAR_ROW.finditer(text):
                activity = _build_activity(row, year)
                if activity is None or activity["name"] in seen:
                    continue
                seen.add(activity["name"])
                activities.append(activity)

            if not activities:
                logger.warning("碧蓝航线活动日历页没有解析出活动")
                return None

    except Exception as e:
        logger.opt(exception=True).warning(
            f"获取碧蓝航线活动失败: {type(e).__name__}: {e}"
        )
        return None

    data = {
        "version": "",
        "versionName": "",
        "startTime": "",
        "endTime": "",
        "cover": "",
        "activities": activities,
    }
    _cache = (time.time(), data)
    return data
