from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from app.utils import get_logger
from app.utils.common.process.scope import detached_process_context

# 账号运行交回预约时的两行告警沿用任务类的 logger 名（原先就在 runner_task 里记）
_logger = get_logger("MaaFW 插件自动代理")

# 用户点停止后，等核对 / 清理线程收尾的上限：到点就不等了，预约交给它完成后再放。
RELEASE_CHECK_CANCEL_GRACE_SECONDS = 30.0

_ACTIVE_PROJECT_PATHS: set[str] = set()
_ACTIVE_PROJECT_PATHS_LOCK = threading.Lock()


def normalize_project_path(path: str | Path) -> str:
    """Return the process-wide key used by update and execution reservations."""

    return os.path.normcase(str(Path(path).resolve())).casefold()


async def try_reserve_project_path(path: str | Path) -> str | None:
    """Reserve a project directory without blocking the event loop.

    The critical section only mutates an in-memory set, so a process-wide
    threading lock also keeps separate event loops/worker threads consistent.
    Callers deliberately fail fast instead of waiting: AUTO-MAS already skips a
    second MaaFW run for the same external directory.
    """

    key = normalize_project_path(path)
    with _ACTIVE_PROJECT_PATHS_LOCK:
        if key in _ACTIVE_PROJECT_PATHS:
            return None
        _ACTIVE_PROJECT_PATHS.add(key)
    return key


async def release_project_path(key: str | None) -> None:
    release_project_path_sync(key)


async def release_run_reservation(
    key: str,
    *,
    scope: Any,
    pretask_exit_confirmation: Callable[[], Callable[[], Awaitable[bool]]],
    pending: asyncio.Task[Any] | None,
    grace: float = RELEASE_CHECK_CANCEL_GRACE_SECONDS,
) -> None:
    """账号运行结束时交回它的项目预约（``key`` 是 :func:`try_reserve_project_path` 给的键）。

    调用方先把自己记的键置空再调（同一份预约只放一次）。``scope`` 是此刻的进程作用域
    （``current_process_scope.get()``）；``pending`` 是资源包失败后还在跑的发行包核对 / 清理任务。

    - **作用域已请求停止**：此刻调一次 ``pretask_exit_confirmation()``（运行前设置的
      ``MaaFWPretaskRunner.exit_confirmation``，传方法本身，只在这条分支里调），把「等作用域收尾 → 清理
      没失败 → 运行前设置的进程确认退出 → 核对任务做完」交给作用域保留的后台任务，都确认了才放；
      统一进程清理失败、运行前设置没确认退出、核对出错时保留占用。
    - **否则**：核对任务还在改视图（用户停止时）就最多等 ``grace`` 秒；等不到就把释放交给它的完成回调，
      预约不能先放。
    """

    if scope is not None and scope.requested:
        # #1871 的新收尾确认可能早于统一进程清理结束，不能此时
        # 放开预约；后面的强杀若失败，还可能有旧 pretask 在写目录。
        # 此刻要等的运行前设置清理与正在结束的 pretask 进程
        pretasks_exited = pretask_exit_confirmation()

        async def release_after_confirmed_stop() -> None:
            await scope.finished.wait()
            if scope.cleanup_failed:
                _logger.error("MaaFW 任务进程未确认停止，保留项目占用，拒绝并发修改")
                return
            # 清理没确认时 pretask_run 记一句，这里保留占用
            if not await pretasks_exited():
                return
            if pending is not None:
                try:
                    await asyncio.shield(pending)
                except asyncio.CancelledError:
                    # 核对通过停止令牌退出也算完成；它由 scope 保留，
                    # 不会在文件操作尚未结束时被统一取消。
                    # 若只是当前释放任务被取消，核对仍在运行，则继续保留预约。
                    if not pending.cancelled():
                        raise
                except Exception as error:
                    _logger.warning(f"MaaFW 项目核对未确认，保留占用: {error}")
                    return
            release_project_path_sync(key)

        worker = asyncio.create_task(
            release_after_confirmed_stop(),
            name="maafw-confirmed-project-release",
            context=detached_process_context(),
        )
        scope.retain_worker(worker)
        return

    if pending is not None and not pending.done():
        # 资源加载失败后的核对 / 清理还在工作线程里改视图（用户停止时）：等它收尾，等不到就
        # 把释放交给它的完成回调，预约不能先放。
        with suppress(BaseException):
            await asyncio.wait_for(asyncio.shield(pending), timeout=grace)
        if not pending.done():

            def _release_later(task: asyncio.Task[Any]) -> None:
                # 顺手取走异常，免得报「never retrieved」（同 manager 的 _release_after_work）
                if not task.cancelled():
                    task.exception()
                release_project_path_sync(key)

            pending.add_done_callback(_release_later)
            return
    await release_project_path(key)


def try_reserve_project_path_sync(path: str | Path) -> str | None:
    """同一张表的同步版：给已经在工作线程里跑的服务层代码用（它拿不到事件循环）。"""

    key = normalize_project_path(path)
    with _ACTIVE_PROJECT_PATHS_LOCK:
        if key in _ACTIVE_PROJECT_PATHS:
            return None
        _ACTIVE_PROJECT_PATHS.add(key)
    return key


def release_project_path_sync(key: str | None) -> None:
    if not key:
        return
    with _ACTIVE_PROJECT_PATHS_LOCK:
        _ACTIVE_PROJECT_PATHS.discard(key)


# 正在更新的视图（计数：手动更新整段标一次，里面的 run_view_update 再标一次）。
# 只是给「为什么拿不到预约 / 为什么现在不能更新」配文案用的旁证，不参与预约与谱系锁。
_UPDATING_PROJECT_PATHS: dict[str, int] = {}


def begin_project_updating(path: str | Path) -> str:
    """把该视图登记为「正在更新」，返回给 :func:`end_project_updating` 的键；可嵌套。"""

    key = normalize_project_path(path)
    with _ACTIVE_PROJECT_PATHS_LOCK:
        _UPDATING_PROJECT_PATHS[key] = _UPDATING_PROJECT_PATHS.get(key, 0) + 1
    return key


def end_project_updating(key: str) -> None:
    with _ACTIVE_PROJECT_PATHS_LOCK:
        remaining = _UPDATING_PROJECT_PATHS.get(key, 0) - 1
        if remaining > 0:
            _UPDATING_PROJECT_PATHS[key] = remaining
        else:
            _UPDATING_PROJECT_PATHS.pop(key, None)


@contextmanager
def mark_project_updating(path: str | Path) -> Iterator[None]:
    """在这段里把该视图登记为「正在更新」；可嵌套。"""

    key = begin_project_updating(path)
    try:
        yield
    finally:
        end_project_updating(key)


def is_project_updating(path: str | Path) -> bool:
    key = normalize_project_path(path)
    with _ACTIVE_PROJECT_PATHS_LOCK:
        return key in _UPDATING_PROJECT_PATHS
