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

"""碧蓝档案活动排期查询。

取数复用上游的 Kivo 中转接口（``POST /api/info/bluearchive/activity``），本模块
只负责把它翻译成两个口径：调度侧要「当前有没有进行中的活动」，界面还要活动名与
起止时间。取数失败返回 None，由调用方退回默认行为。
"""

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from app.utils import get_logger

logger = get_logger("碧蓝档案活动")

## 时间轴按开始时间倒序返回，当前进行中的活动必定落在最前面若干条里
ACTIVITY_PAGE_SIZE = 100
ACTIVITY_MAX_PAGES = 2

## 只有「活动」算活动，卡池、掉落加倍、维护等分类不算
WANTED_TYPE = "Event"

BlueArchiveLineType = Literal["JP", "Globle", "CN"]


@dataclass(frozen=True)
class ActivityInfo:
    """一场活动：名称与起止时间（Unix 秒）"""

    name: str
    start_time: float
    end_time: float


def has_running_activity_in(
    items: Sequence[Mapping[str, object]], now_seconds: float
) -> bool:
    """判断给定时间轴上是否存在正在进行中的活动。

    Args:
        items: Kivo 时间轴条目，每项含 ``type`` 与 ``start_time`` / ``end_time``（Unix 秒）。
        now_seconds: 判定时刻的 Unix 秒。

    Returns:
        bool: 存在 ``开始时间 <= 当前时刻 < 结束时间`` 的活动时为 True。
    """

    for item in items:
        if item.get("type") != WANTED_TYPE:
            continue

        start = item.get("start_time")
        end = item.get("end_time")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            continue

        if start <= now_seconds < end:
            return True

    return False


def collect_activities(
    items: Sequence[Mapping[str, object]], now_seconds: float
) -> tuple[ActivityInfo | None, ActivityInfo | None]:
    """挑出进行中的活动与下一个还没开始的活动。

    与前端的取值口径一致：只认「活动」分类；同名条目保留结束最晚的一条；
    没有标题、时间不是数字、开始与结束同一时刻的条目一律跳过。

    Args:
        items: Kivo 时间轴条目。
        now_seconds: 判定时刻的 Unix 秒。

    Returns:
        tuple[ActivityInfo | None, ActivityInfo | None]: 进行中的活动、下一个未开始的活动。
    """

    picked: dict[str, ActivityInfo] = {}

    for item in items:
        if item.get("type") != WANTED_TYPE:
            continue

        start = item.get("start_time")
        end = item.get("end_time")
        name = str(item.get("title") or "").strip()
        if (
            not name
            or not isinstance(start, (int, float))
            or not isinstance(end, (int, float))
            or end <= start
        ):
            continue

        existing = picked.get(name)
        if existing is not None and existing.end_time >= end:
            continue

        picked[name] = ActivityInfo(name, float(start), float(end))

    # 进行中同时有多场时取最早结束的那场，与前端的取值保持一致
    running = sorted(
        (
            item
            for item in picked.values()
            if item.start_time <= now_seconds < item.end_time
        ),
        key=lambda item: item.end_time,
    )
    upcoming = sorted(
        (item for item in picked.values() if item.start_time > now_seconds),
        key=lambda item: item.start_time,
    )

    return (running[0] if running else None, upcoming[0] if upcoming else None)


async def _fetch_page(
    line_type: BlueArchiveLineType, page: int
) -> list[Mapping[str, object]] | None:
    """取回一页时间轴条目。

    取数复用上游 ``POST /api/info/bluearchive/activity`` 的转发逻辑与它自带的缓存，
    本模块不再自己维护 Kivo 的地址、请求头与缓存。

    Args:
        line_type: 服务器标识，取 Kivo 的原文拼写。
        page: 页码，从 1 开始。

    Returns:
        list[Mapping[str, object]] | None: 该页条目；取数失败为 None。
    """

    ## 局部导入：避免模块导入期与 app.api.info 形成环
    from app.api.info import get_bluearchive_activity
    from app.models.schema import BlueArchiveActivityIn

    response = await get_bluearchive_activity(
        BlueArchiveActivityIn(
            line_type=line_type,
            page=page,
            page_size=ACTIVITY_PAGE_SIZE,
        )
    )
    if response.code != 200:
        logger.warning(
            f"获取碧蓝档案活动排期失败({line_type} 第 {page} 页): {response.message}"
        )
        return None

    kivo = response.data.get("data")
    batch = kivo.get("timeline") if isinstance(kivo, Mapping) else None
    if not isinstance(batch, list):
        logger.warning(f"碧蓝档案活动排期结构异常({line_type} 第 {page} 页)")
        return None

    return [item for item in batch if isinstance(item, Mapping)]


async def _timeline(
    line_type: BlueArchiveLineType,
) -> tuple[Mapping[str, object], ...] | None:
    """分页取回指定服的活动时间轴。

    Args:
        line_type: 服务器标识。

    Returns:
        tuple[Mapping[str, object], ...] | None: 时间轴条目；取数失败为 None。
    """

    items: list[Mapping[str, object]] = []

    for page in range(1, ACTIVITY_MAX_PAGES + 1):
        batch = await _fetch_page(line_type, page)
        if batch is None:
            ## 失败不返回半截结果：调用方应当退回默认行为
            return None
        if not batch:
            break

        items.extend(batch)

    return tuple(items)


async def has_running_activity(line_type: BlueArchiveLineType) -> bool | None:
    """查询指定服当前是否有进行中的活动。

    Args:
        line_type: 服务器标识（``JP`` / ``Globle`` / ``CN``）。

    Returns:
        bool: 当前有 / 没有进行中的活动。
        None: 取数失败，调用方应退回默认行为。
    """

    items = await _timeline(line_type)
    if items is None:
        return None

    return has_running_activity_in(items, time.time())


async def resolve_activity_state(
    line_type: BlueArchiveLineType,
) -> tuple[ActivityInfo | None, ActivityInfo | None] | None:
    """查询指定服正在进行的活动与下一个未开始的活动。

    Args:
        line_type: 服务器标识（``JP`` / ``Globle`` / ``CN``）。

    Returns:
        tuple[ActivityInfo | None, ActivityInfo | None] | None: 依次为进行中的
            活动、下一个未开始的活动；取数失败为 None。
    """

    items = await _timeline(line_type)
    if items is None:
        return None

    return collect_activities(items, time.time())
