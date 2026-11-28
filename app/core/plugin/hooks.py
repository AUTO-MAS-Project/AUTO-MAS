"""宿主调用插件扩展点的兼容桥。

插件化迁移分多个版本完成。这个模块让宿主先调用已经登记的插件服务，
在对应插件尚未安装时继续走旧的内置实现，保证升级和回退都能工作。
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from app.utils import get_logger

logger = get_logger("插件扩展点")

BEFORE_AUTO_PROXY_PREFIX = "task.before_auto_proxy:"
VIRTUAL_DISPLAY_HOOK = f"{BEFORE_AUTO_PROXY_PREFIX}virtual_display"
BEFORE_AUTO_PROXY_TIMEOUT = 10.0


def _legacy_virtual_display_hook() -> Callable[[], Awaitable[Any]]:
    """延迟导入旧守卫，避免插件管理器和桌面守卫互相导入。"""

    from app.core.desktop_guard import ensure_desktop_available

    return ensure_desktop_available


async def _invoke(name: str, method: Callable[[], Any], timeout: float | None) -> None:
    """在单独的时间预算内执行一个宿主扩展点。"""

    try:
        result = method()
        if inspect.isawaitable(result):
            if timeout is None:
                await result
            else:
                await asyncio.wait_for(result, timeout=timeout)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            f"插件扩展点 {name} 执行失败，继续任务：{type(exc).__name__}: {exc}"
        )


async def run_before_auto_proxy_hooks(
    *, timeout: float = BEFORE_AUTO_PROXY_TIMEOUT
) -> None:
    """调用 AutoProxy 开跑前的插件钩子。

    钩子按服务名排序逐个调用。插件超时或抛错只记录日志，不改变任务结果。
    ``virtual_display`` 尚未安装时回退到宿主内置守卫，安装后由插件自检并接管，
    避免两套守卫同时巡检同一块显示器。
    """

    from app.core import Plugin

    services = Plugin.services
    hooks = tuple(services.iter_prefix(BEFORE_AUTO_PROXY_PREFIX))
    legacy_fallback = not any(name == VIRTUAL_DISPLAY_HOOK for name, _ in hooks)
    if legacy_fallback:
        hooks = ((VIRTUAL_DISPLAY_HOOK, _legacy_virtual_display_hook()), *hooks)
    for name, method in hooks:
        if not callable(method):
            logger.warning(f"插件扩展点 {name} 不是可调用对象，已跳过")
            continue
        await _invoke(
            name,
            method,
            None if legacy_fallback and name == VIRTUAL_DISPLAY_HOOK else timeout,
        )


__all__ = [
    "BEFORE_AUTO_PROXY_PREFIX",
    "BEFORE_AUTO_PROXY_TIMEOUT",
    "VIRTUAL_DISPLAY_HOOK",
    "run_before_auto_proxy_hooks",
]
