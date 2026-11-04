#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""顺序队列的单项预取；安装仍由专项启动前的入口负责。"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress

from app.models.task import ScriptItem, UserItem
from app.utils import get_logger

logger = get_logger("脚本更新调度")
PREFETCH_GRACE_SECONDS = 60
PREFETCH_POLL_SECONDS = 0.5


def _active_user(script: ScriptItem) -> UserItem | None:
    if script.status == "运行" and 0 <= script.current_index < len(script.user_list):
        user = script.user_list[script.current_index]
        if user.status == "运行":
            return user
    return None


async def _cancel_and_wait(task: asyncio.Task) -> None:
    if not task.done():
        task.cancel()
    # 下载器/线程的取消收尾结束前不能切到下一脚本的登录阶段。
    while not task.done():
        with suppress(asyncio.CancelledError, Exception):
            await asyncio.shield(task)
    if not task.cancelled():
        task.exception()


class ScriptUpdateQueue:
    """每轮只看下一项；不创建全队列的后台下载。"""

    def __init__(self) -> None:
        self._watcher: asyncio.Task | None = None
        self._download: asyncio.Task | None = None

    def watch(
        self, script: ScriptItem, prepare_next: Callable[[], Awaitable[None]]
    ) -> None:
        self._watcher = asyncio.create_task(self._watch(script, prepare_next))

    async def _watch(
        self, script: ScriptItem, prepare_next: Callable[[], Awaitable[None]]
    ) -> None:
        while True:
            user = _active_user(script)
            completed_at = user.first_task_completed_at if user is not None else None
            if (
                completed_at is not None
                and time.monotonic() - completed_at >= PREFETCH_GRACE_SECONDS
            ):
                break
            await asyncio.sleep(PREFETCH_POLL_SECONDS)

        self._download = asyncio.create_task(prepare_next())
        user_index = script.current_index
        try:
            while not self._download.done():
                # 切号、失败或重试已开始时停止预取，避免和下一次登录抢网络。
                if script.status in ("异常", "跳过") or (
                    script.status == "运行"
                    and (
                        script.current_index != user_index
                        or user.status in ("异常", "跳过")
                        or user.first_task_completed_at != completed_at
                    )
                ):
                    await _cancel_and_wait(self._download)
                    return
                await asyncio.wait({self._download}, timeout=PREFETCH_POLL_SECONDS)
            await self._download
        except asyncio.CancelledError:
            await _cancel_and_wait(self._download)
            raise
        except Exception:
            # 启动前更新和安全回退仍由专项决定，预取失败不能中断当前任务。
            logger.opt(exception=True).warning("下一脚本预下载未完成，将在启动前处理")

    async def finish(self, *, cancelled: bool = False) -> None:
        watcher, self._watcher = self._watcher, None
        if watcher is None:
            return
        owner = asyncio.current_task()
        cancelling_before = owner.cancelling() if owner is not None else 0
        if cancelled or self._download is None:
            await _cancel_and_wait(watcher)
        else:
            # 前项收尾已经结束：等待预取收敛后，才进入下一项安装和启动。
            try:
                await asyncio.shield(watcher)
            except asyncio.CancelledError:
                await _cancel_and_wait(watcher)
                raise
        self._download = None
        if (
            not cancelled
            and owner is not None
            and owner.cancelling() > cancelling_before
        ):
            raise asyncio.CancelledError
