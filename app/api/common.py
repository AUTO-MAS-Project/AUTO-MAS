from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from functools import wraps
from typing import Any, ParamSpec, TypeVar, cast

from fastapi import APIRouter

from app.models.common_contract import ComboBoxItem, ComboBoxOut, OutBase


OutT = TypeVar("OutT", bound=OutBase)
P = ParamSpec("P")


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
    except Exception as exc:
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


def api_post(
    router: APIRouter,
    path: str,
    *,
    model_cls: type[OutT],
    ws_endpoint: str | None = None,
    message: str | None = None,
    on_error: Callable[[Exception], None] | None = None,
    route_kwargs: dict[str, object] | None = None,
    **fallback_kwargs: object,
) -> Callable[[Callable[P, Awaitable[OutT]]], Callable[P, Awaitable[OutT]]]:
    """统一 POST 路由注册装饰器。"""

    return api_route(
        router,
        path,
        methods=("POST",),
        model_cls=model_cls,
        ws_endpoint=ws_endpoint,
        message=message,
        on_error=on_error,
        route_kwargs=route_kwargs,
        **fallback_kwargs,
    )


def api_route(
    router: APIRouter,
    path: str,
    *,
    methods: Iterable[str],
    model_cls: type[OutT],
    ws_endpoint: str | None = None,
    message: str | None = None,
    on_error: Callable[[Exception], None] | None = None,
    route_kwargs: dict[str, object] | None = None,
    **fallback_kwargs: object,
) -> Callable[[Callable[P, Awaitable[OutT]]], Callable[P, Awaitable[OutT]]]:
    """统一路由注册装饰器：路由 + 守卫 + 可选 WS 命令。"""

    guard = api_guard(
        model_cls=model_cls,
        message=message,
        on_error=on_error,
        **fallback_kwargs,
    )
    route = router.api_route(
        path,
        methods=list(methods),
        **cast(dict[str, Any], route_kwargs or {}),
    )

    def decorator(func: Callable[P, Awaitable[OutT]]) -> Callable[P, Awaitable[OutT]]:
        wrapped = guard(func)
        if ws_endpoint is not None:
            from app.api.ws_command import ws_command

            wrapped = ws_command(ws_endpoint)(wrapped)
        return route(wrapped)

    return decorator


def api_get(
    router: APIRouter,
    path: str,
    *,
    model_cls: type[OutT],
    ws_endpoint: str | None = None,
    message: str | None = None,
    on_error: Callable[[Exception], None] | None = None,
    route_kwargs: dict[str, object] | None = None,
    **fallback_kwargs: object,
) -> Callable[[Callable[P, Awaitable[OutT]]], Callable[P, Awaitable[OutT]]]:
    """统一 GET 路由注册装饰器。"""

    return api_route(
        router,
        path,
        methods=("GET",),
        model_cls=model_cls,
        ws_endpoint=ws_endpoint,
        message=message,
        on_error=on_error,
        route_kwargs=route_kwargs,
        **fallback_kwargs,
    )


def api_patch(
    router: APIRouter,
    path: str,
    *,
    model_cls: type[OutT],
    ws_endpoint: str | None = None,
    message: str | None = None,
    on_error: Callable[[Exception], None] | None = None,
    route_kwargs: dict[str, object] | None = None,
    **fallback_kwargs: object,
) -> Callable[[Callable[P, Awaitable[OutT]]], Callable[P, Awaitable[OutT]]]:
    """统一 PATCH 路由注册装饰器。"""

    return api_route(
        router,
        path,
        methods=("PATCH",),
        model_cls=model_cls,
        ws_endpoint=ws_endpoint,
        message=message,
        on_error=on_error,
        route_kwargs=route_kwargs,
        **fallback_kwargs,
    )


def api_delete(
    router: APIRouter,
    path: str,
    *,
    model_cls: type[OutT],
    ws_endpoint: str | None = None,
    message: str | None = None,
    on_error: Callable[[Exception], None] | None = None,
    route_kwargs: dict[str, object] | None = None,
    **fallback_kwargs: object,
) -> Callable[[Callable[P, Awaitable[OutT]]], Callable[P, Awaitable[OutT]]]:
    """统一 DELETE 路由注册装饰器。"""

    return api_route(
        router,
        path,
        methods=("DELETE",),
        model_cls=model_cls,
        ws_endpoint=ws_endpoint,
        message=message,
        on_error=on_error,
        route_kwargs=route_kwargs,
        **fallback_kwargs,
    )


__all__ = [
    "OutBase",
    "ComboBoxItem",
    "ComboBoxOut",
    "error_out",
    "run_api",
    "api_guard",
    "api_route",
    "api_get",
    "api_post",
    "api_patch",
    "api_delete",
]
