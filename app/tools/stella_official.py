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

"""星塔旅人官网活动公告的抓取与解析。

官网 CMS 把活动也当公告发：列表接口一次给 6 条，活动名、分类与开放时间都在
标题和正文摘要里——接口本身没有时间字段，只能读「▌活动时间 / 招募时间 /
开放时间」那一段文本。

首页的活动卡与横幅、以及 MSS 判断「当前有没有活动」，用的都是这里的结果。
判定只认「版本活动」那一类（``VERSION_KIND``）：只有它会开限时活动关，招募与
拼图之类的小玩法没有关卡可打，全算进来的话几乎天天「有活动」。

取数失败返回 None，由调用方退回默认行为。
"""

import asyncio
import re
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.utils import get_logger

logger = get_logger("星塔旅人活动")

NEWS_BASE = "https://stellasora.yostar.cn"
NEWS_LIST_URL = f"{NEWS_BASE}/api/resource/news"
NEWS_DETAIL_URL = f"{NEWS_BASE}/api/resource/news"
## 那个 CMS 认 Referer，不带就只给空壳
NEWS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": f"{NEWS_BASE}/",
}

## 站点固定每页 6 条（size 参数不起作用）；翻 6 页 36 条，够覆盖进行中的
## 活动与最近结束的那批，再多翻也只是更早的历史公告
NEWS_MAX_PAGES = 6
CACHE_TTL_SECONDS = 600
REQUEST_TIMEOUT_SECONDS = 20
## 只留最近结束 14 天以内的，与其它活动源一个口径
RECENT_WINDOW_DAYS = 14
## 补封面要逐条取公告详情，同时最多发这么多个请求
COVER_FETCH_CONCURRENCY = 5

BEIJING = timezone(timedelta(hours=8))

## 「「猎影合围Beta」活动说明」「[奋斗吧！大小姐的旅人修炼手册]活动一览」……
## 书名号各家公告写法不一，半角方括号与【】都是官网自己用过的
ACTIVITY_TITLE = re.compile(
    r"^[「\[【](?P<name>[^「」\[\]【】]+)[」\]】](?P<suffix>.*)$"
)
## 标题后缀 → 卡片上的分类标签
KIND_BY_SUFFIX = (
    ("招募", "招募"),
    ("一览", "版本活动"),
)
## 带活动关的那一类：横幅与 MSS 的活动期判定都只认它
VERSION_KIND = "版本活动"
## 同一期活动往往有两篇公告（活动一览、商品上新），同名去重时按分类定去留：
## 数值小的优先，免得「版本全新商品上新！」把真正的「限时活动一览」顶掉
KIND_RANK = {
    "版本活动": 0,
    "常驻活动": 1,
    "招募": 2,
    "活动": 3,
}
## 长期开放、随版本轮换的活动单独归一类，首页给它们单开一栏。
## 按关键词认而不是整名：猎影合围以后去掉了 Beta 也照样算
PERMANENT_KIND = "常驻活动"
PERMANENT_KEYWORDS = ("灾变防线", "创业激励基金", "猎影合围")


def classify_activity_name(name: str) -> str:
    """按公告标题给活动定分类。

    官网公告没有分类字段，分类只能从标题看：命中常驻关键词的是「常驻活动」，
    带「一览」的是「版本活动」，带「招募」的是「招募」，其余归到「活动」。
    SRA 兜底那份数据也没有分类，同样用它补上，免得前端的横幅与分组筛选落空。
    """

    if any(keyword in name for keyword in PERMANENT_KEYWORDS):
        return PERMANENT_KIND
    for keyword, kind in KIND_BY_SUFFIX:
        if keyword in name:
            return kind
    return "活动"


## 带这些字样的公告不是活动：维护、兑换码、问卷、充值之类
SKIP_TITLE = re.compile(
    r"维护|更新说明|兑换|问卷|举报|封禁|处罚|支付|充值|客服|反馈|补偿|直播|前瞻|预约|测试|下载|问题说明"
)
## 正文里的开放时间段落，标签名各家公告不统一
TIME_SECTION = re.compile(
    r"[▌■]\s*(?:活动时间|开放时间|招募时间|活动期间|卡池时间)[：:]?\s*([^\n▌■]+)"
)
## 正文里的第一张图：官方主视觉，比列表那个方形缩略图更适合当横幅封面
DETAIL_IMAGE = re.compile(r'<img[^>]+src="([^"]+)"')
## 起止都带时刻：2026/09/22 12:00 ~ 2026/09/29 10:59
EXACT_RANGE = re.compile(
    r"(\d{4})/(\d{2})/(\d{2})\s+(\d{2}):(\d{2})\s*[~～至\-]\s*"
    r"(\d{4})/(\d{2})/(\d{2})\s+(\d{2}):(\d{2})"
)
## 开始写成「维护结束后」：只有日期没有时刻，2026/09/29 维护结束后 ~ 2026/10/13 03:59
MAINTENANCE_RANGE = re.compile(
    r"(\d{4})/(\d{2})/(\d{2})\s*维护结束后\s*[~～至\-]\s*"
    r"(\d{4})/(\d{2})/(\d{2})\s+(\d{2}):(\d{2})"
)

_cache: tuple[float, dict[str, Any]] | None = None


def _at(year: str, month: str, day: str, hour: str, minute: str) -> datetime:
    """按北京时间拼一个时刻"""

    return datetime(
        int(year), int(month), int(day), int(hour), int(minute), tzinfo=BEIJING
    )


def parse_open_time(text: str) -> tuple[datetime, datetime] | None:
    """从公告正文里读出活动的开放时间。

    优先认起止都带时刻的写法；开始写成「维护结束后」的，维护多久公告里没有，
    硬猜只会让「距开始」错报，所以按当天零点算——倒计时按结束时间走，不受影响。

    Args:
        text: 公告正文（或摘要）。

    Returns:
        tuple[datetime, datetime] | None: 开始与结束时刻；读不出结束时刻时为 None。
    """

    exact = EXACT_RANGE.search(text)
    if exact is not None:
        return _at(*exact.groups()[:5]), _at(*exact.groups()[5:])

    maintenance = MAINTENANCE_RANGE.search(text)
    if maintenance is not None:
        year, month, day = maintenance.groups()[:3]
        return _at(year, month, day, "0", "0"), _at(*maintenance.groups()[3:])

    return None


def _kind_of(title: str, suffix: str) -> str:
    """标题后缀 → 卡片上的分类标签"""

    for keyword, kind in KIND_BY_SUFFIX:
        if keyword in suffix:
            return kind

    return "活动"


def parse_activities(
    rows: Sequence[Mapping[str, Any]], now: datetime
) -> list[dict[str, Any]]:
    """把公告列表里认得出的活动整理成前端要的形状（按开始时间升序）。

    认活动的方式：标题形如「活动名」后缀，后缀不是维护、兑换码之类的杂项；
    正文里能读出开放时间。同名公告会重复发（活动说明、奖励说明各一篇），
    只留结束最晚的那条。

    Args:
        rows: 官网列表接口返回的公告条目。
        now: 判定时刻（北京时间）。

    Returns:
        list[dict[str, Any]]: 活动条目，字段与明日方舟那条链路一致。
    """

    horizon = now - timedelta(days=RECENT_WINDOW_DAYS)
    picked: dict[str, dict[str, Any]] = {}

    for row in rows:
        title = str(row.get("title") or "").strip()
        matched = ACTIVITY_TITLE.match(title)
        if matched is None or SKIP_TITLE.search(title):
            continue

        text = f"{row.get('description') or ''}\n{title}"
        section = TIME_SECTION.search(text)
        window = parse_open_time(section.group(1) if section is not None else text)
        if window is None:
            continue

        start, end = window
        if end <= start or end < horizon:
            continue

        name = matched.group("name").strip()
        description = re.sub(r"\s+", " ", str(row.get("description") or "")).strip()
        kind = _kind_of(title, matched.group("suffix"))
        if any(keyword in name for keyword in PERMANENT_KEYWORDS):
            kind = PERMANENT_KIND

        existing = picked.get(name)
        if existing is not None:
            # 同一期会有多篇公告：分类更「重」的那篇说了算（版本一览压过商品上新），
            # 分类一样才比结束时间，留最晚的那条
            existing_rank = KIND_RANK.get(existing["kind"], 9)
            new_rank = KIND_RANK.get(kind, 9)
            if existing_rank < new_rank:
                continue
            if (
                existing_rank == new_rank
                and datetime.fromisoformat(existing["endTime"]) >= end
            ):
                continue

        picked[name] = {
            "name": name,
            "kind": kind,
            "startTime": start.isoformat(timespec="minutes"),
            "endTime": end.isoformat(timespec="minutes"),
            "cover": str(row.get("thumbnail") or ""),
            "url": str(row.get("link") or ""),
            "description": description[:80],
            ## 只用来补封面，发给前端前会摘掉
            "_newsId": row.get("id"),
        }

    return sorted(picked.values(), key=lambda item: item["startTime"])


async def _detail_cover(client: httpx.AsyncClient, news_id: object) -> str:
    """取公告详情正文里的第一张图。

    列表给的 ``thumbnail`` 是方形缩略图，铺进 5:1 的横幅只能缩成右边一小块；
    正文开头那张才是官方主视觉（活动名与角色都在上面），所以封面优先用它。
    """

    try:
        response = await client.get(
            f"{NEWS_DETAIL_URL}/{news_id}", headers=NEWS_HEADERS
        )
        response.raise_for_status()
        news = (response.json().get("data") or {}).get("news") or {}
    except Exception as e:
        logger.debug(f"取星塔旅人公告详情失败({news_id}): {type(e).__name__}: {e}")
        return ""

    matched = DETAIL_IMAGE.search(str(news.get("content") or ""))
    return matched.group(1) if matched is not None else ""


async def _fill_covers(
    client: httpx.AsyncClient, activities: list[dict[str, Any]]
) -> None:
    """并发把每场活动的封面换成详情正文里的主视觉，取不到就留着列表缩略图"""

    semaphore = asyncio.Semaphore(COVER_FETCH_CONCURRENCY)

    async def fill(item: dict[str, Any]) -> None:
        async with semaphore:
            cover = await _detail_cover(client, item.get("_newsId"))
        if cover:
            item["cover"] = cover

    await asyncio.gather(*(fill(item) for item in activities))


async def fetch_official_activities(*, force: bool = False) -> dict[str, Any] | None:
    """取回官网的活动一览（带模块级缓存）。

    Args:
        force: 为 True 时忽略缓存。

    Returns:
        dict[str, Any] | None: ``{"activities": [...]}``；取数失败时为 None。
    """

    global _cache

    now = time.time()
    if not force and _cache is not None and now - _cache[0] < CACHE_TTL_SECONDS:
        return _cache[1]

    rows: list[Mapping[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            for index in range(1, NEWS_MAX_PAGES + 1):
                response = await client.get(
                    NEWS_LIST_URL, params={"index": index}, headers=NEWS_HEADERS
                )
                response.raise_for_status()
                payload = response.json()
                batch = (payload.get("data") or {}).get("rows")
                if not isinstance(batch, list) or not batch:
                    break
                rows.extend(item for item in batch if isinstance(item, Mapping))

            if not rows:
                logger.warning("星塔旅人官网活动列表为空，按拿不到处理")
                return None

            activities = parse_activities(rows, datetime.now(BEIJING))
            await _fill_covers(client, activities)
    except Exception as e:
        logger.warning(f"获取星塔旅人官网活动失败: {type(e).__name__}: {e}")
        return None

    for item in activities:
        item.pop("_newsId", None)

    data = {"activities": activities}
    _cache = (now, data)
    return data


async def has_running_official_activity() -> bool | None:
    """当前有没有进行中的「版本活动」。

    只有版本活动会开限时活动关，MSS 据此决定「活动快速战斗」排不排、排在哪；
    招募与拼图之类的小玩法没有关卡可打，算进来几乎天天「有活动」，判定就废了。

    Returns:
        bool | None: 有 True、确实没有 False、取不到数据 None——调用方要把 None
        当成「说不准」跳过编排，不能当成「没有活动」。
    """

    data = await fetch_official_activities()
    if data is None:
        return None

    versions = [item for item in data["activities"] if item["kind"] == VERSION_KIND]
    if not versions:
        # 一条版本活动都没认出来：多半是官网换写法、解析跟不上，按「说不准」处理。
        # 报 False 会让调用方把「活动快速战斗」从队列里摘掉，整轮就漏打了
        logger.warning("星塔旅人这一批公告里没有版本活动，活动期判定按说不准处理")
        return None

    now = datetime.now(BEIJING)
    for item in versions:
        start = datetime.fromisoformat(item["startTime"])
        end = datetime.fromisoformat(item["endTime"])
        if start <= now < end:
            return True

    return False


async def permanent_activity_window(keyword: str) -> str | None:
    """某个常驻活动（如「灾变防线」）当前那一期的开始时刻。

    常驻活动长期开放、随版本轮换：它们每期都会重发一篇同名公告，而
    :func:`parse_activities` 对同名公告只留结束最晚的那条，所以这里拿到的是
    「当前这一期」——正好可以当作「这期」的标识。

    一期一个开始时刻，跨月也认得出是同一期；自然月做不了这件事，因为上游更新
    并不严格按月来。

    Args:
        keyword: 活动名里的关键词，如 ``灾变防线``。

    Returns:
        str | None: 期的开始时刻（ISO 8601，形如 ``2026-09-29T12:00+08:00``）；
        没有这个活动或取不到数据时为 None——调用方要当成「说不准」跳过编排。
    """

    data = await fetch_official_activities()
    if data is None:
        return None

    for item in data["activities"]:
        if item["kind"] == PERMANENT_KIND and keyword in item["name"]:
            return str(item["startTime"])

    return None
