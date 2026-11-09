#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""顺序队列的单项预取；安装仍由专项启动前的入口负责。"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from contextvars import ContextVar

from app.models.task import ScriptItem
from app.utils import get_logger
from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed

logger = get_logger("脚本更新调度")
PREFETCH_GRACE_SECONDS = 60
PREFETCH_POLL_SECONDS = 0.5

script_task_completed: ContextVar[Callable[[], None] | None] = ContextVar(
    "script_task_completed", default=None
)
script_task_retrying: ContextVar[Callable[[], Awaitable[None]] | None] = ContextVar(
    "script_task_retrying", default=None
)


def report_script_task_completed() -> None:
    """由专项既有的成功结果面通知预下载调度。"""
    callback = script_task_completed.get()
    if callback is not None:
        callback()


async def report_script_task_retrying() -> None:
    """真正重登前撤销旧成功时刻，等预下载停写再交还专项。"""
    callback = script_task_retrying.get()
    if callback is not None:
        await callback()


async def _cancel_and_wait(task: asyncio.Task) -> None:
    if not task.done():
        task.cancel()
    # 下载器/线程的取消收尾结束前不能切到下一脚本的登录阶段。
    while not task.done():
        with suppress(asyncio.CancelledError, Exception):
            await asyncio.shield(task)
    if not task.cancelled():
        error = task.exception()
        # FluxDown daemon may still write to its output; never treat this as a
        # harmless cancelled prefetch and start the next script.
        if isinstance(error, FluxdownCancelUnconfirmed):
            raise error


class ScriptUpdateQueue:
    """每轮只看下一项；不创建全队列的后台下载。"""

    def __init__(self) -> None:
        self._watcher: asyncio.Task | None = None
        self._download: asyncio.Task | None = None

    def watch(
        self,
        script: ScriptItem,
        prepare_next: Callable[[], Awaitable[None]],
        *,
        completed_at: Callable[[], float | None],
    ) -> None:
        if self._watcher is not None:
            # 未确认停止的下载必须一直阻断后续托管；不得覆盖其 watcher。
            raise RuntimeError("上一次预下载未完成停止确认，禁止创建新预下载")
        self._watcher = asyncio.create_task(
            self._watch(script, prepare_next, completed_at=completed_at)
        )

    async def _watch(
        self,
        script: ScriptItem,
        prepare_next: Callable[[], Awaitable[None]],
        *,
        completed_at: Callable[[], float | None],
    ) -> None:
        success = completed_at
        while True:
            if script.status == "等待":
                await asyncio.sleep(PREFETCH_POLL_SECONDS)
                continue
            if script.status != "运行":
                # 尚未满 60 秒，当前脚本已经结束/失败：不执行预下载。
                return
            first_success = success()
            if (
                first_success is not None
                and time.monotonic() - first_success >= PREFETCH_GRACE_SECONDS
            ):
                break
            await asyncio.sleep(PREFETCH_POLL_SECONDS)

        self._download = asyncio.create_task(prepare_next())
        try:
            while not self._download.done():
                # 脚本内部正常切号不取消下载；失败或真正重试使成功信号失效。
                if script.status in ("异常", "跳过") or (
                    script.status == "运行" and success() != first_success
                ):
                    await _cancel_and_wait(self._download)
                    return
                await asyncio.wait({self._download}, timeout=PREFETCH_POLL_SECONDS)
            await self._download
        except asyncio.CancelledError:
            await _cancel_and_wait(self._download)
            raise
        except FluxdownCancelUnconfirmed:
            # Unknown daemon writer ownership: block the handoff, not fallback.
            raise
        except Exception:
            # 预下载失败不影响当前任务，后项仍使用自身的启动前更新逻辑。
            logger.opt(exception=True).warning("下一脚本预下载未完成，将在启动前处理")

    async def finish(self, *, cancelled: bool = False) -> None:
        watcher = self._watcher
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
        # 只在确认 watcher 收敛后才清空。若 FluxDown 停止未确认抛出异常，
        # 保留已完成但携带异常的 watcher，账号层即使吞掉该异常，
        # 外层 ScriptExpander.finish() 仍会再次抛出，阻断下一托管。
        self._watcher = None
        self._download = None
        # cancelled 也用于脚本失败后的普通收尾；等待停写期间新到的用户
        # 停止请求必须继续传播，不能因已在撤销预取而继续启动下一脚本。
        if owner is not None and owner.cancelling() > cancelling_before:
            raise asyncio.CancelledError
