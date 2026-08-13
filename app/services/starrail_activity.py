import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx

from app.utils import get_logger

logger = get_logger("星穹铁道活动服务")

ACTIVITY_URL = "https://starrailassistant.top/api/v1/activities.json"
CACHE_PATH = Path.cwd() / "data/cache/starrail_activity.json"
CACHE_SECONDS = 10 * 60
RETRY_SECONDS = 5 * 60
REQUEST_TIMEOUT_SECONDS = 20


class StarRailActivityService:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._etag = ""
        self._last_error = ""
        self._next_check = 0.0
        self._refresh_task: asyncio.Task[None] | None = None
        self._load_cache()

    async def get_overview(self) -> dict[str, Any]:
        if time.monotonic() >= self._next_check and self._refresh_task is None:
            self._refresh_task = asyncio.create_task(self._refresh())
        refresh_task = self._refresh_task
        if not self._data and refresh_task is not None:
            await asyncio.shield(refresh_task)
        return {
            "Available": bool(self._data),
            "Stale": bool(self._data and self._last_error),
            "Message": (
                "正在使用上次成功获取的活动数据"
                if self._data and self._last_error
                else ("星穹铁道活动数据暂不可用" if self._last_error else "")
            ),
            **self._data,
        }

    async def _refresh(self) -> None:
        try:
            headers = {"If-None-Match": self._etag} if self._etag else {}
            async with httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT_SECONDS,
                follow_redirects=True,
            ) as client:
                response = await client.get(ACTIVITY_URL, headers=headers)
            if response.status_code == 304:
                self._next_check = time.monotonic() + CACHE_SECONDS
                self._last_error = ""
                return
            response.raise_for_status()
            self._data = response.json()
            self._etag = response.headers.get("ETag", "")
            self._last_error = ""
            self._next_check = time.monotonic() + CACHE_SECONDS
            self._save_cache()
        except Exception as error:
            self._last_error = f"{type(error).__name__}: {error}"
            self._next_check = time.monotonic() + RETRY_SECONDS
            logger.warning(f"更新星穹铁道活动数据失败: {self._last_error}")
        finally:
            self._refresh_task = None

    def _load_cache(self) -> None:
        if not CACHE_PATH.exists():
            return
        try:
            cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            self._data = cache["data"]
            self._etag = cache.get("etag", "")
        except (OSError, KeyError, TypeError, ValueError) as error:
            logger.warning(f"加载星穹铁道活动缓存失败: {error}")

    def _save_cache(self) -> None:
        temporary_path = CACHE_PATH.with_suffix(".tmp")
        try:
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text(
                json.dumps({"etag": self._etag, "data": self._data}, ensure_ascii=False),
                encoding="utf-8",
            )
            temporary_path.replace(CACHE_PATH)
        except OSError as error:
            logger.warning(f"保存星穹铁道活动缓存失败: {error}")


starrail_activity_service = StarRailActivityService()
