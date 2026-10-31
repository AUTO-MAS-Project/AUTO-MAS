#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""连接 MAA 关卡服务与宿主能力，所有入口共享缓存和刷新任务。"""

import asyncio
from datetime import datetime

import httpx

from app.config import config_manager
from app.core import Config
from app.task.MAA.stage_service import MaaStageCache, MaaStageService


def _read_cache() -> MaaStageCache:
    data = Config.setting.Data
    return MaaStageCache(
        content=data.StageData,
        etag=data.StageETag,
        checked_at=data.LastStageUpdated,
    )


async def _write_cache(
    *,
    checked_at: datetime,
    content: str | None = None,
    etag: str | None = None,
) -> None:
    data: dict[str, str | datetime] = {"LastStageUpdated": checked_at}
    if content is not None:
        data["StageData"] = content
    if etag is not None:
        data["StageETag"] = etag
    # 正文、ETag 和检查时间一起提交，不能把旧关卡标记为新缓存。
    async with config_manager.transaction():
        await Config.setting.update(
            type(Config.setting).model_validate({"Data": data}),
            check_visibility=False,
        )


async def _fetch_stage(headers: dict[str, str]) -> httpx.Response:
    async with httpx.AsyncClient(proxy=Config.proxy, follow_redirects=True) as client:
        return await client.get(
            "https://api.maa.plus/MaaAssistantArknights/api/gui/StageActivityV2.json",
            headers=headers,
        )


def _track_task(task: asyncio.Task[None]) -> None:
    Config.temp_task.append(task)

    def _done(t: asyncio.Task[None]) -> None:
        if t in Config.temp_task:
            Config.temp_task.remove(t)

    task.add_done_callback(_done)


maa_stage_service = MaaStageService(
    read_cache=_read_cache,
    write_cache=_write_cache,
    fetch=_fetch_stage,
    now=lambda: datetime.now().astimezone(),
    track_task=_track_task,
)
