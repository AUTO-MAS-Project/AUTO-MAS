#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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

"""星塔旅人活动排期查询。

取数走 StellaBase 的公开接口（社区数据库，非官方）：它已经把活动分成
``current`` / ``upcoming`` / ``ended`` 三组。这里提供两个用途——调度侧只问
「当前有没有进行中的活动」，界面端直接取 :func:`fetch_events` 的原始响应
（挑选与展示交给前端，本模块不替界面排版）。

取数失败一律返回 ``None``（判定入口返回 ``None`` 表示「这次说不准」），不能让一个
第三方站点的抖动拦住整轮任务。解析与判定都是纯函数，取数单独放在 :func:`fetch_events`。
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.utils import get_logger

logger = get_logger("星塔旅人活动")

EVENTS_URL = "https://stella.ennead.cc/api/stella/events"
## 站点按语言返回同一批活动的文案；各服同期进行同一个活动，取哪一服的文案都不影响判定
EVENTS_LANG = "CN"
## 响应 100 KB 量级，没必要每轮任务都拉；活动起止都是整点，缓存久一点无妨
CACHE_TTL_SECONDS = 30 * 60
REQUEST_TIMEOUT_SECONDS = 20

## 国服官网（悠星）：`/api/resource/news/banner` 给的是官方当前主推内容，
## 每条含 795×510 的横幅图与对应新闻页。StellaBase 的活动大图时有时无
## （``bg_*_popup.png`` 常 404），拿官网这张当封面兜底。
OFFICIAL_BASE = "https://stellasora.yostar.cn"
OFFICIAL_BANNER_URL = f"{OFFICIAL_BASE}/api/resource/news/banner"
OFFICIAL_NEWS_URL = f"{OFFICIAL_BASE}/api/resource/news"
## 顺带取回标题的横幅条数：卡片要按当前活动名去官网找对应的那条，
## 榜单本身只有十条上下，全取一遍标题最稳（并发发出去，只在缓存过期时做一次）
OFFICIAL_TITLE_LIMIT = 12
## 活动名与公告标题里的标点，比对包含关系前先去掉
_NAME_NOISE = re.compile(
    r"[\s\[\]【】「」『』!！?？。.,，、·\-—~～:：;；'\"“”‘’()（）]"
)

_cache: tuple[float, dict[str, Any]] | None = None
_official_cache: tuple[float, list[dict[str, Any]]] | None = None


@dataclass(frozen=True)
class StellaEvent:
    """一场活动：名称与起止时间（Unix 秒）。"""

    name: str
    start_time: float
    end_time: float


def parse_event_time(value: object) -> float | None:
    """把接口返回的 ISO 8601 时间串折成 Unix 秒。

    Args:
        value: 形如 ``2026-09-08T12:00:00+08:00`` 的时间串。

    Returns:
        float | None: Unix 秒；解析不出来时为 None。
    """

    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _to_event(raw: Mapping[str, Any]) -> StellaEvent | None:
    """把一条原始记录折成 :class:`StellaEvent`；缺名字或缺时间时返回 None。"""

    name = str(raw.get("title") or "").strip()
    start = parse_event_time(raw.get("startTime"))
    end = parse_event_time(raw.get("endTime"))
    if not name or start is None or end is None:
        return None
    return StellaEvent(name=name, start_time=start, end_time=end)


def iter_events(payload: Mapping[str, Any] | None) -> list[StellaEvent]:
    """把接口响应的三组记录拍平成一个列表。

    顺序沿用站点给的「进行中、即将开始、已结束」，不重新排序。

    Args:
        payload: :func:`fetch_events` 的返回值。

    Returns:
        list[StellaEvent]: 解析成功的活动；响应不可用时为空列表。
    """

    if not isinstance(payload, Mapping):
        return []

    events: list[StellaEvent] = []
    for group in ("current", "upcoming", "ended"):
        raw_items = payload.get(group)
        if not isinstance(raw_items, Sequence):
            continue
        for raw in raw_items:
            if not isinstance(raw, Mapping):
                continue
            event = _to_event(raw)
            if event is not None:
                events.append(event)
    return events


def has_running_event(events: Sequence[StellaEvent], now_seconds: float) -> bool:
    """判断是否存在正在进行中的活动。

    Args:
        events: :func:`iter_events` 的输出。
        now_seconds: 判定时刻的 Unix 秒。

    Returns:
        bool: 存在 ``开始时间 <= 当前时刻 < 结束时间`` 的活动时为 True。
    """

    return any(event.start_time <= now_seconds < event.end_time for event in events)


async def fetch_events(*, force: bool = False) -> dict[str, Any] | None:
    """拉取活动数据（带模块级缓存）。

    Args:
        force: 为 True 时忽略缓存。

    Returns:
        dict[str, Any] | None: 接口原始响应；取数失败时为 None。
    """

    global _cache

    now = time.time()
    if not force and _cache is not None and now - _cache[0] < CACHE_TTL_SECONDS:
        return _cache[1]

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(
                EVENTS_URL,
                params={"lang": EVENTS_LANG},
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Accept": "application/json",
                },
            )
        response.raise_for_status()
        payload = response.json()
    except Exception as e:
        logger.warning(f"获取星塔旅人活动数据失败: {type(e).__name__}: {e}")
        return None

    if not isinstance(payload, dict):
        logger.warning("星塔旅人活动数据格式异常，按拿不到处理")
        return None

    _cache = (now, payload)
    return payload


async def fetch_official_banners(*, force: bool = False) -> list[dict[str, Any]] | None:
    """拉国服官网的主推横幅（活动主视觉 + 对应新闻链接 + 前几条的标题）。

    与 :func:`fetch_events` 同一套缓存与降级口径：取不到就返回 ``None``，界面按
    「没有官方图」处理，退回站点自己的小图或主题色底纹。

    Args:
        force: 为 True 时忽略缓存。

    Returns:
        list[dict[str, Any]] | None: ``[{"banner": 图, "url": 新闻页, "title": 标题}, ...]``；
        取不到时为 None，标题取不到时该条没有 ``title`` 键。
    """

    global _official_cache

    now = time.time()
    if (
        not force
        and _official_cache is not None
        and now - _official_cache[0] < CACHE_TTL_SECONDS
    ):
        return _official_cache[1]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json, text/plain, */*",
        "Referer": f"{OFFICIAL_BASE}/",
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.get(OFFICIAL_BANNER_URL, headers=headers)
            response.raise_for_status()
            body = response.json()

            data = body.get("data") if isinstance(body, Mapping) else None
            if not isinstance(data, Sequence):
                logger.warning("星塔旅人官网横幅格式异常，按拿不到处理")
                return None

            banners = [
                {
                    "banner": str(item.get("banner") or ""),
                    "url": str(item.get("url") or ""),
                }
                for item in data
                if isinstance(item, Mapping) and item.get("banner")
            ]

            ## banner 列表只有图和链接，要按活动名对上号就得先有标题；
            ## 并发取回，单条失败只少一个标题，不影响横幅本身
            async def load_title(item: dict[str, Any]) -> None:
                news_id = item["url"].rstrip("/").rsplit("/", 1)[-1]
                if not news_id.isdigit():
                    return
                try:
                    detail = await client.get(
                        f"{OFFICIAL_NEWS_URL}/{news_id}", headers=headers
                    )
                    detail.raise_for_status()
                    news = ((detail.json().get("data") or {}).get("news")) or {}
                    title = str(news.get("title") or "").strip()
                    if title:
                        item["title"] = title
                except Exception as e:
                    logger.warning(
                        f"取星塔旅人官网公告标题失败({news_id}): {type(e).__name__}: {e}"
                    )

            await asyncio.gather(
                *(load_title(item) for item in banners[:OFFICIAL_TITLE_LIMIT])
            )
    except Exception as e:
        logger.warning(f"获取星塔旅人官网横幅失败: {type(e).__name__}: {e}")
        return None

    _official_cache = (now, banners)
    return banners


def current_activity_name(payload: Mapping[str, Any] | None) -> str:
    """当前该显示的那场活动的名字。

    进行中的优先（多条时取最早结束的，与卡片同口径），一场都没进行就取最近结束的那场。

    Args:
        payload: :func:`fetch_events` 的返回值。

    Returns:
        str: 活动名；没有可用活动时为空串。
    """

    events = iter_events(payload)
    if not events:
        return ""

    now = time.time()
    running = [event for event in events if event.start_time <= now < event.end_time]
    if running:
        return min(running, key=lambda event: event.end_time).name

    ended = [event for event in events if event.end_time <= now]
    return max(ended, key=lambda event: event.end_time).name if ended else ""


def match_official_banner(
    banners: Sequence[Mapping[str, Any]], name: str
) -> Mapping[str, Any] | None:
    """在官网横幅里找与活动名对应的那条。

    官网公告标题形如 ``[奋斗吧！大小姐的旅人修炼手册]版本一览``，活动名是
    ``奋斗吧！大小姐的旅人修炼手册！``——去掉标点后互相包含即算对上。

    Args:
        banners: :func:`fetch_official_banners` 的输出。
        name: 活动名（:func:`current_activity_name` 的结果）。

    Returns:
        Mapping[str, Any] | None: 命中的那条横幅；没对上时返回 None。
    """

    target = _normalize_name(name)
    if not target:
        return None

    for item in banners:
        title = _normalize_name(str(item.get("title") or ""))
        if title and (target in title or title in target):
            return item
    return None


def _normalize_name(text: str) -> str:
    """去掉标点与空白，便于活动名与公告标题互相判断包含关系。"""

    return _NAME_NOISE.sub("", text or "")


async def has_running_event_now() -> bool | None:
    """调度侧入口：取数并判定当前是否有活动。

    Returns:
        bool | None: 有活动为 True、确实没有为 False、取不到数据为 None。取不到时
        调用方要**跳过**活动编排，不能当成「没有活动」——真在活动期却按没活动处理，
        会把外壳里的活动勾选摘掉，整轮漏打活动。
    """

    payload = await fetch_events()
    if payload is None:
        return None
    return has_running_event(iter_events(payload), time.time())
