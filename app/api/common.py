from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
import asyncio
from typing import ParamSpec, TypeVar

from app.contracts.common_contract import ComboBoxItem, ComboBoxOut, OutBase


OutT = TypeVar("OutT", bound=OutBase)
P = ParamSpec("P")


RECOVERABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    ValueError,
    TypeError,
    KeyError,
    RuntimeError,
    LookupError,
    OSError,
    asyncio.TimeoutError,
)


def error_out(
    model_cls: type[OutT],
    exc: Exception,
    *,
    message: str | None = None,
    **kwargs: object,
) -> OutT:
    return model_cls(
        code=500,
        status="error",
        message=message or f"{type(exc).__name__}: {str(exc)}",
        **kwargs,
    )


async def run_api(
    success_factory: Callable[[], Awaitable[OutT]],
    *,
    model_cls: type[OutT],
    message: str | None = None,
    on_error: Callable[[Exception], None] | None = None,
    **fallback_kwargs: object,
) -> OutT:
    try:
        return await success_factory()
    except RECOVERABLE_EXCEPTIONS as exc:
        if on_error is not None:
            on_error(exc)
        return error_out(
            model_cls,
            exc,
            message=message,
            **fallback_kwargs,
        )


def api_guard(
    *,
    model_cls: type[OutT],
    message: str | None = None,
    on_error: Callable[[Exception], None] | None = None,
    **fallback_kwargs: object,
) -> Callable[[Callable[P, Awaitable[OutT]]], Callable[P, Awaitable[OutT]]]:
    """为 FastAPI 路由提供统一异常包装的装饰器。"""

    def decorator(func: Callable[P, Awaitable[OutT]]) -> Callable[P, Awaitable[OutT]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> OutT:
            return await run_api(
                lambda: func(*args, **kwargs),
                model_cls=model_cls,
                message=message,
                on_error=on_error,
                **fallback_kwargs,
            )

        return wrapper

    return decorator


__all__ = [
    "OutBase",
    "ComboBoxItem",
    "ComboBoxOut",
    "error_out",
    "run_api",
    "api_guard",
]
