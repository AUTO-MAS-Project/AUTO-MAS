#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""顺序队列的单项预取；安装仍由专项启动前的入口负责。"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress

from app.models.task import ScriptItem
from app.utils import get_logger

logger = get_logger("脚本更新调度")
PREFETCH_GRACE_SECONDS = 60
PREFETCH_POLL_SECONDS = 0.5


def _first_script_success(script: ScriptItem) -> float | None:
    """跨账号查找本轮首次成功节点；兼容未绑定 TaskItem 的独立脚本对象。"""
    if script.status != "运行":
        return None
    if script.first_task_completed_at is not None:
        return script.first_task_completed_at
    if not any(user.status == "运行" for user in script.user_list):
        return None
    return min(
        (
            user.first_task_completed_at
            for user in script.user_list
            if user.first_task_completed_at is not None
        ),
        default=None,
    )

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
            if script.status != "运行":
                # 尚未满 60 秒，当前脚本已经结束/失败：不执行预下载。
                return
            completed_at = _first_script_success(script)
            if (
                completed_at is not None
                and time.monotonic() - completed_at >= PREFETCH_GRACE_SECONDS
            ):
                break
            await asyncio.sleep(PREFETCH_POLL_SECONDS)

        self._download = asyncio.create_task(prepare_next())
        try:
            while not self._download.done():
                # 脚本内部正常切号不取消下载；失败或真正重试使成功信号失效。
                if script.status in ("异常", "跳过") or (
                    script.status == "运行"
                    and _first_script_success(script) != completed_at
                ):
                    await _cancel_and_wait(self._download)
                    return
                await asyncio.wait({self._download}, timeout=PREFETCH_POLL_SECONDS)
            await self._download
        except asyncio.CancelledError:
            await _cancel_and_wait(self._download)
            raise
        except Exception:
            # 预下载失败不影响当前任务，后项仍使用自身的启动前更新逻辑。
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
