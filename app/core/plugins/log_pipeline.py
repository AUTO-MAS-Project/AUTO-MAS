#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from __future__ import annotations

import asyncio
import inspect
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Final

from app.utils import get_logger


logger = get_logger("日志管道")

LOG_HANDLER_ATTR: Final[str] = "__mas_log_handler__"


# ── 元数据 ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class LogHandlerSpec:
    """``@on_log_line`` 装饰器声明的元数据。"""

    priority: int = 0
    pattern: re.Pattern[str] | None = None
    source_filter: str | None = None


def get_log_handlers(target: Any) -> list[LogHandlerSpec]:
    """从函数或方法上提取 ``@on_log_line`` 声明。"""
    specs: list[LogHandlerSpec] = getattr(target, LOG_HANDLER_ATTR, [])
    return list(specs)


# ── 装饰器 ──────────────────────────────────────────────────────────────


def on_log_line(
    *,
    priority: int = 0,
    pattern: str | re.Pattern[str] | None = None,
    source: str | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """标记方法为日志行处理器。

    处理器签名支持以下形式::

        async def handler(line: str, ctx: LogContext) -> None: ...
        async def handler(line: str, match: re.Match, ctx: LogContext) -> None: ...

    当 ``pattern`` 不为 None 时，仅匹配的日志行会触发此处理器，
    且 ``match`` 参数会传入正则匹配结果。

    Args:
        priority: 优先级，值越大越先执行。
        pattern: 可选的正则表达式过滤器。
        source: 可选的日志源过滤器（如 ``"file"``、``"process"``）。
    """
    compiled: re.Pattern[str] | None = None
    if pattern is not None:
        compiled = re.compile(pattern) if isinstance(pattern, str) else pattern

    spec = LogHandlerSpec(priority=priority, pattern=compiled, source_filter=source)

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        handlers: list[LogHandlerSpec] = list(getattr(func, LOG_HANDLER_ATTR, []))
        handlers.append(spec)
        setattr(func, LOG_HANDLER_ATTR, handlers)
        return func

    return decorator


# ── LogContext ──────────────────────────────────────────────────────────


@dataclass
class LogContext:
    """传递给每个日志处理器的可变上下文。"""

    line: str
    timestamp: datetime | None
    source: str
    log_contents: list[str]
    latest_time: datetime
    _stopped: bool = field(default=False, init=False, repr=False)
    _status: str | None = field(default=None, init=False, repr=False)
    _status_detail: str | None = field(default=None, init=False, repr=False)
    _metadata: dict[str, Any] = field(default_factory=dict, init=False, repr=False)

    def set_status(self, status: str, detail: str | None = None) -> None:
        """设置任务状态。后续处理器仍可覆盖此值（除非 ``stop_propagation``）。"""
        self._status = status
        self._status_detail = detail

    def stop_propagation(self) -> None:
        """停止向后续处理器传播。"""
        self._stopped = True

    @property
    def status(self) -> str | None:
        """当前状态值。"""
        return self._status

    @property
    def status_detail(self) -> str | None:
        """当前状态详情。"""
        return self._status_detail

    @property
    def is_stopped(self) -> bool:
        """是否已停止传播。"""
        return self._stopped

    @property
    def metadata(self) -> dict[str, Any]:
        """扩展元数据字典。"""
        return self._metadata


# ── 已注册处理器 ────────────────────────────────────────────────────────


@dataclass(slots=True)
class _BoundLogHandler:
    handler_id: str
    handler: Callable[..., Awaitable[None]]
    priority: int
    pattern: re.Pattern[str] | None
    source_filter: str | None
    owner: str | None


# ── LogPipeline ─────────────────────────────────────────────────────────


class LogPipeline:
    """优先级排序的日志处理器链。

    处理器按优先级降序执行。当处理器调用 ``ctx.stop_propagation()`` 时，
    后续处理器将被跳过。
    """

    def __init__(self) -> None:
        self._handlers: list[_BoundLogHandler] = []
        self._sorted = True

    def add_handler(
        self,
        handler: Callable[..., Awaitable[None]],
        *,
        priority: int = 0,
        pattern: re.Pattern[str] | None = None,
        source_filter: str | None = None,
        owner: str | None = None,
    ) -> str:
        """注册日志处理器。

        Returns:
            处理器 ID，可用于 ``remove_handler``。
        """
        handler_id = str(uuid.uuid4())
        self._handlers.append(
            _BoundLogHandler(
                handler_id=handler_id,
                handler=handler,
                priority=priority,
                pattern=pattern,
                source_filter=source_filter,
                owner=owner,
            )
        )
        self._sorted = False
        return handler_id

    def remove_handler(self, handler_id: str) -> None:
        """按 ID 移除处理器。"""
        self._handlers = [h for h in self._handlers if h.handler_id != handler_id]

    def remove_by_owner(self, owner: str) -> None:
        """按 owner 批量移除处理器。"""
        self._handlers = [h for h in self._handlers if h.owner != owner]

    def clear_default_handlers(self) -> None:
        """移除所有 ``owner=None`` 的默认处理器。

        供插件调用以完全自定义日志处理。
        """
        self._handlers = [h for h in self._handlers if h.owner is not None]

    async def process_line(self, ctx: LogContext) -> None:
        """按优先级顺序执行匹配的处理器，直到 ``stop_propagation``。"""
        if not self._sorted:
            self._handlers.sort(key=lambda h: h.priority, reverse=True)
            self._sorted = True

        for bound in self._handlers:
            if ctx.is_stopped:
                break

            if bound.source_filter is not None and bound.source_filter != ctx.source:
                continue

            match: re.Match[str] | None = None
            if bound.pattern is not None:
                match = bound.pattern.search(ctx.line)
                if match is None:
                    continue

            try:
                if match is not None:
                    result = bound.handler(ctx.line, match, ctx)
                else:
                    result = bound.handler(ctx.line, ctx)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.opt(exception=True).warning(
                    f"日志处理器执行异常: handler_id={bound.handler_id}, "
                    f"owner={bound.owner}"
                )

    async def process_batch(
        self,
        lines: list[str],
        source: str,
        latest_time: datetime,
    ) -> LogContext | None:
        """处理一批日志行。

        Returns:
            最后一个设置了 status 的 LogContext，或 None。
        """
        last_status_ctx: LogContext | None = None
        for line in lines:
            ctx = LogContext(
                line=line,
                timestamp=None,
                source=source,
                log_contents=lines,
                latest_time=latest_time,
            )
            await self.process_line(ctx)
            if ctx.status is not None:
                last_status_ctx = ctx
        return last_status_ctx


# ── LogMonitorAdapter ──────────────────────────────────────────────────


class LogMonitorAdapter:
    """桥接 ``LogMonitor`` 的回调到 ``LogPipeline`` 的处理器链。

    作为 ``LogMonitor(callback=adapter.callback)`` 传入。每次回调时
    识别新增日志行，逐行调用 ``LogPipeline.process_line()``。
    如果任一处理器设置了 status，则设置 ``wait_event``。
    """

    def __init__(
        self,
        pipeline: LogPipeline,
        wait_event: asyncio.Event,
        source: str = "file",
    ) -> None:
        self._pipeline = pipeline
        self._wait_event = wait_event
        self._source = source
        self._prev_count = 0

    async def callback(self, log_contents: list[str], latest_time: datetime) -> None:
        """``LogMonitor`` 回调入口。"""
        new_lines = log_contents[self._prev_count :]
        self._prev_count = len(log_contents)

        if not new_lines:
            return

        for line in new_lines:
            ctx = LogContext(
                line=line,
                timestamp=None,
                source=self._source,
                log_contents=log_contents,
                latest_time=latest_time,
            )
            await self._pipeline.process_line(ctx)

            if ctx.status is not None:
                self._wait_event.set()
                return


# ── LogFacade ──────────────────────────────────────────────────────────


class _LogPipelineHolder:
    """可变容器，在任务执行时由 PluginScriptManager 注入 LogPipeline 实例。"""

    def __init__(self) -> None:
        self._pipeline: LogPipeline | None = None
        self._pending_handlers: list[
            tuple[Callable[..., Awaitable[None]], int, re.Pattern[str] | None, str | None, str | None]
        ] = []

    @property
    def pipeline(self) -> LogPipeline | None:
        return self._pipeline

    @pipeline.setter
    def pipeline(self, value: LogPipeline | None) -> None:
        self._pipeline = value
        if value is not None:
            for handler, priority, pattern, source_filter, owner in self._pending_handlers:
                value.add_handler(
                    handler,
                    priority=priority,
                    pattern=pattern,
                    source_filter=source_filter,
                    owner=owner,
                )
            self._pending_handlers.clear()

    def add_pending_handler(
        self,
        handler: Callable[..., Awaitable[None]],
        *,
        priority: int = 0,
        pattern: re.Pattern[str] | None = None,
        source_filter: str | None = None,
        owner: str | None = None,
    ) -> str:
        """如果 pipeline 已就绪则立即注册，否则缓存到 pending 列表。"""
        if self._pipeline is not None:
            return self._pipeline.add_handler(
                handler,
                priority=priority,
                pattern=pattern,
                source_filter=source_filter,
                owner=owner,
            )
        handler_id = str(uuid.uuid4())
        self._pending_handlers.append(
            (handler, priority, pattern, source_filter, owner)
        )
        return handler_id


class LogFacade:
    """插件日志管道门面，暴露在 ``ctx.log`` 上。"""

    def __init__(self, instance_id: str, pipeline_holder: _LogPipelineHolder) -> None:
        self._instance_id = instance_id
        self._holder = pipeline_holder
        self._handler_ids: list[str] = []

    def add_handler(
        self,
        handler: Callable[..., Awaitable[None]],
        *,
        priority: int = 0,
        pattern: re.Pattern[str] | str | None = None,
        source_filter: str | None = None,
    ) -> str:
        """注册日志处理器。"""
        compiled: re.Pattern[str] | None = None
        if pattern is not None:
            compiled = re.compile(pattern) if isinstance(pattern, str) else pattern

        handler_id = self._holder.add_pending_handler(
            handler,
            priority=priority,
            pattern=compiled,
            source_filter=source_filter,
            owner=self._instance_id,
        )
        self._handler_ids.append(handler_id)
        return handler_id

    def remove_handler(self, handler_id: str) -> None:
        """移除处理器。"""
        if self._holder.pipeline is not None:
            self._holder.pipeline.remove_handler(handler_id)
        self._handler_ids = [h for h in self._handler_ids if h != handler_id]

    def clear_default_handlers(self) -> None:
        """移除所有默认处理器，使用自定义处理器替代。"""
        if self._holder.pipeline is not None:
            self._holder.pipeline.clear_default_handlers()

    @property
    def pipeline(self) -> LogPipeline | None:
        """当前活跃的 LogPipeline 实例（任务执行期间才有值）。"""
        return self._holder.pipeline
