#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""明日方舟公开活动：PRTS 解析、SRA 回退与十分钟缓存。"""

import re
import time
from datetime import datetime, timedelta, timezone

import httpx

from app.tools.sra_activity import fetch_sra_activities
from app.utils import get_logger

logger = get_logger("明日方舟活动")

## 明日方舟的活动一览取自 PRTS wiki。那个站对「声称自己是 Chrome」的请求一律 403，
## 换个朴素 UA 反而畅通；页面是服务端渲染的表格，每行带
## <span class="TLDcontainer" data-time="开始时间戳,结束时间戳">，起止时间都在 HTML 里。
PRTS_ACTIVITY_URL = "https://prts.wiki/w/%E6%B4%BB%E5%8A%A8%E4%B8%80%E8%A7%88"
PRTS_HEADERS = {"User-Agent": "AUTO-MAS"}

## 活动排期变化慢，与碧蓝档案一样缓存十分钟
ARKNIGHTS_CACHE_TTL = 600
ARKNIGHTS_RECENT_WINDOW_DAYS = 14
_arknights_cache: tuple[float, dict] | None = None


## PRTS 活动一览的表格：一行一场活动，四列依次是开始时间、活动、分类、官网公告
_PRTS_ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
_PRTS_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_PRTS_END_TIME = re.compile(r'data-time="\d+,(\d+)"')
## data-time 的第一个值每行都一样，是页面渲染时刻
_PRTS_RENDER_TIME = re.compile(r'data-time="(\d+),\d+"')
_PRTS_START_TIME = re.compile(r"(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})")
_PRTS_NAME = re.compile(r"<a[^>]*>(.*?)</a>", re.S)
_PRTS_IMAGE = re.compile(r'src="(https://media\.prts\.wiki/[^"]+)"')
## 页面给的是 650px 缩略图，铺不满横幅（前端按宽度判铺法），换成 1300px
_PRTS_THUMB_WIDTH = re.compile(r"/\d+px-")
_PRTS_TAG = re.compile(r"<[^>]+>")


def _prts_text(fragment: str) -> str:
    """把一小段 HTML 压成纯文本"""

    return re.sub(r"\s+", " ", _PRTS_TAG.sub("", fragment)).strip()


def _parse_prts_activities(page: str, now: datetime) -> list[dict]:
    """从活动一览页里抽出本次活动相关的条目。"""

    horizon = now - timedelta(days=ARKNIGHTS_RECENT_WINDOW_DAYS)
    activities: list[dict] = []

    ## 页面渲染时刻：PRTS 对已经结束的活动会把结束时间填成它，这种条目直接丢掉
    render_match = _PRTS_RENDER_TIME.search(page)
    render_seconds = int(render_match.group(1)) if render_match else 0

    for row in _PRTS_ROW.findall(page):
        end_match = _PRTS_END_TIME.search(row)
        cells = _PRTS_CELL.findall(row)
        if end_match is None or len(cells) < 3:
            continue

        end = int(end_match.group(1))
        if datetime.fromtimestamp(end, timezone.utc) < horizon:
            continue

        ## 已结束的历史活动不要
        if render_seconds and abs(end - render_seconds) <= 60:
            continue

        ## 开始时间在首列（形如 2026-09-29 16:00）。data-time 的第一个值不是它，
        ## 页面上所有行的那个值都一样，是渲染时刻
        start_match = _PRTS_START_TIME.search(_prts_text(cells[0]))
        ## 活动名取单元格里的链接文本：后面还跟着状态徽标和内联脚本，直接取文本会带上它们
        name_match = _PRTS_NAME.search(cells[1])
        if start_match is None or name_match is None:
            continue

        name = _prts_text(name_match.group(1))
        if not name:
            continue

        year, month, day, hour, minute = (int(value) for value in start_match.groups())
        start_time = datetime(
            year, month, day, hour, minute, tzinfo=timezone(timedelta(hours=8))
        )
        end_time = datetime.fromtimestamp(end, timezone(timedelta(hours=8)))
        if end_time <= start_time:
            continue

        cover = _PRTS_IMAGE.search(row)
        cover_url = _PRTS_THUMB_WIDTH.sub("/1300px-", cover.group(1)) if cover else ""

        activities.append(
            {
                "name": name,
                "kind": _prts_text(cells[2]),
                "startTime": start_time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                "endTime": end_time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
                "cover": cover_url,
            }
        )

    activities.sort(key=lambda item: item["startTime"])
    return activities


async def fetch_arknights_activities() -> dict:
    """优先 PRTS，失败时复用 SRA；合法空列表也照常缓存。"""

    global _arknights_cache

    now = datetime.now(timezone.utc)
    if (
        _arknights_cache is not None
        and time.time() - _arknights_cache[0] < ARKNIGHTS_CACHE_TTL
    ):
        return _arknights_cache[1]

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(PRTS_ACTIVITY_URL, headers=PRTS_HEADERS)
        response.raise_for_status()
        data = {"activities": _parse_prts_activities(response.text, now)}
    except Exception as e:
        logger.opt(exception=True).warning(
            f"获取明日方舟活动数据失败: {type(e).__name__}: {e}"
        )
        fallback = await fetch_sra_activities("ak")
        if fallback is None:
            raise
        logger.info("明日方舟活动数据改用 SRA 兜底")
        data = fallback

    _arknights_cache = (time.time(), data)
    return data
