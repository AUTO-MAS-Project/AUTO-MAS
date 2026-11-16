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

import asyncio
import time
from copy import deepcopy
from dataclasses import dataclass, field

import httpx

from app.utils import get_logger

logger = get_logger("SRA活动")

SRA_ACTIVITY_BASE = "https://starrailassistant.top/api/v1/activity"

## 全部尝试共用总时限，避免弱网重试让首页或日历长时间等候。
SRA_TIMEOUT_SECONDS = 15
SRA_REQUEST_TIMEOUT_SECONDS = 5
SRA_MAX_ATTEMPTS = 3
SRA_RETRY_DELAY_SECONDS = 0.5
SRA_CACHE_SECONDS = 5 * 60
SRA_STALE_SECONDS = 24 * 60 * 60
SRA_FAILURE_RETRY_SECONDS = 60
SRA_WARNING_INTERVAL_SECONDS = 60 * 60

## SRA 的时间是不带时区标记的北京时间，前端按本地时区解析会整体偏移，所以补上偏移量
BEIJING_OFFSET = "+08:00"


@dataclass
class _ActivityState:
    data: dict[str, object] | None = None
    updated_at: float = 0
    refresh_at: float = 0
    warned_at: float | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_states: dict[str, _ActivityState] = {}


def _is_retryable_error(error: Exception) -> bool:
    return isinstance(error, (httpx.TransportError, TimeoutError)) or (
        isinstance(error, httpx.HTTPStatusError)
        and (
            error.response.status_code in (408, 429)
            or error.response.status_code >= 500
        )
    )


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
        ``{"activities": [...]}``，与各游戏的接口形状一致。取数失败时最多沿用
        24 小时内的成功结果；没有可用缓存返回 ``None``，由调用方继续兜底。
    """

    state = _states.setdefault(game, _ActivityState())
    # 首页兜底和后台日历可能同时取同一游戏，共享刷新与失败冷却。
    async with state.lock:
        if time.monotonic() >= state.refresh_at:
            url = f"{SRA_ACTIVITY_BASE}/{game}.json"
            try:
                async with asyncio.timeout(SRA_TIMEOUT_SECONDS):
                    async with httpx.AsyncClient(
                        timeout=SRA_REQUEST_TIMEOUT_SECONDS
                    ) as client:
                        for attempt in range(SRA_MAX_ATTEMPTS):
                            try:
                                response = await client.get(
                                    url, headers={"Accept": "application/json"}
                                )
                                response.raise_for_status()
                                break
                            except httpx.HTTPError as error:
                                if (
                                    not _is_retryable_error(error)
                                    or attempt == SRA_MAX_ATTEMPTS - 1
                                ):
                                    raise
                                await asyncio.sleep(
                                    SRA_RETRY_DELAY_SECONDS * 2**attempt
                                )
                    payload = response.json()

                items = payload.get("activities") if isinstance(payload, dict) else None
                if not isinstance(items, list):
                    raise ValueError("SRA 活动数据缺少 activities 列表")

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
            except Exception as error:
                now = time.monotonic()
                state.refresh_at = now + SRA_FAILURE_RETRY_SECONDS
                if not _is_retryable_error(error) or (
                    state.warned_at is None
                    or now - state.warned_at >= SRA_WARNING_INTERVAL_SECONDS
                ):
                    if _is_retryable_error(error):
                        state.warned_at = now
                    logger.opt(exception=error).warning(
                        f"取 SRA 活动数据失败({game}, {url}): "
                        f"{type(error).__name__}: {error!r}"
                    )
            else:
                state.data = {"activities": activities}
                state.updated_at = time.monotonic()
                state.refresh_at = state.updated_at + SRA_CACHE_SECONDS

        # 回退不延长成功数据的寿命，空活动列表同样是有效结果。
        if state.data is not None:
            if time.monotonic() - state.updated_at <= SRA_STALE_SECONDS:
                return deepcopy(state.data)
            state.data = None
        return None
