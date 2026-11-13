#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""[兼容旧专项] 保留原成功/重试报告调用，已移除旧预下载队列。

预下载实际由 L2 的 PrefetchSession 管理，不再依赖首次成功后的计时。
TODO(脚本更新迁移)：旧专项完成 L2 统一接入后删除这些报告函数和对应调用。
"""

from collections.abc import Awaitable, Callable
from contextvars import ContextVar

# [兼容旧专项] 仅保留旧调用协议；新 L2 不登记这些回调，也不由它们启动下载。
script_task_completed: ContextVar[Callable[[], None] | None] = ContextVar(
    "script_task_completed", default=None
)
script_task_retrying: ContextVar[Callable[[], Awaitable[None]] | None] = ContextVar(
    "script_task_retrying", default=None
)


def report_script_task_completed() -> None:
    """[兼容旧专项] 转交已有成功回调；L2 新预下载不订阅此回调。"""
    callback = script_task_completed.get()
    if callback is not None:
        callback()


async def report_script_task_retrying() -> None:
    """[兼容旧专项] 等待旧调用方登记的重试回调，新预下载不以重登撤销引用。"""
    callback = script_task_retrying.get()
    if callback is not None:
        await callback()
