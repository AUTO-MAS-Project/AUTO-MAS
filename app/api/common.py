from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from functools import wraps
import inspect
from typing import Any, ParamSpec, TypeVar, cast

from fastapi import APIRouter

from app.models.common_contract import ComboBoxItem, ComboBoxOut, OutBase


OutT = TypeVar("OutT", bound=OutBase)
P = ParamSpec("P")


def _docstring_summary(func: Callable[..., Any]) -> str | None:
    doc = inspect.getdoc(func)
    if not doc:
        return None
    first_line = doc.splitlines()[0].strip()
    return first_line or None


def _resolve_model_cls(
    *,
    model_cls: type[OutBase] | None,
    response_model: type[Any] | None,
) -> type[OutBase]:
    if model_cls is not None:
        return model_cls
    if isinstance(response_model, type) and issubclass(response_model, OutBase):
        return response_model
    raise TypeError("model_cls 为空时，response_model 必须是 OutBase 的子类")


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
    model_cls: type[OutBase] | None = None,
    ws_endpoint: str | None = None,
    message: str | None = None,
    on_error: Callable[[Exception], None] | None = None,
    response_model: type[Any] | None = None,
    route_kwargs: dict[str, object] | None = None,
    **fallback_kwargs: object,
) -> Callable[[Callable[P, Awaitable[Any]]], Callable[P, Awaitable[Any]]]:
    """统一 POST 路由注册装饰器（兼容入口）。"""

    return cast(Any, bind_api(router).post)(
        path,
        model_cls=model_cls,
        ws_endpoint=ws_endpoint,
        message=message,
        on_error=on_error,
        response_model=response_model,
        route_kwargs=route_kwargs,
        **fallback_kwargs,
    )


class ApiRegistrar:
    """接近 FastAPI 原生声明风格的 API 装饰器注册器。"""

    def __init__(self, router: APIRouter):
        self.router = router

    def route(
        self,
        path: str,
        *,
        methods: Iterable[str],
        model_cls: type[OutBase] | None = None,
        ws_endpoint: str | None = None,
        message: str | None = None,
        on_error: Callable[[Exception], None] | None = None,
        tags: list[str] | None = None,
        summary: str | None = None,
        response_model: type[Any] | None = None,
        status_code: int = 200,
        route_kwargs: dict[str, object] | None = None,
        **fallback_kwargs: object,
    ) -> Callable[[Callable[P, Awaitable[Any]]], Callable[P, Awaitable[Any]]]:
        """统一路由注册：路由 + 守卫 + 可选 WS 命令。"""

        resolved_model_cls = _resolve_model_cls(
            model_cls=model_cls,
            response_model=response_model,
        )

        guard = api_guard(
            model_cls=resolved_model_cls,
            message=message,
            on_error=on_error,
            **fallback_kwargs,
        )

        def decorator(func: Callable[P, Awaitable[Any]]) -> Callable[P, Awaitable[Any]]:
            resolved_summary = summary or _docstring_summary(func)
            final_route_kwargs: dict[str, Any] = dict(route_kwargs or {})

            final_route_kwargs.setdefault("status_code", status_code)
            final_route_kwargs.setdefault(
                "response_model", response_model or resolved_model_cls
            )
            if tags is not None:
                final_route_kwargs["tags"] = tags
            if resolved_summary is not None:
                final_route_kwargs.setdefault("summary", resolved_summary)

            route = self.router.api_route(
                path,
                methods=list(methods),
                **final_route_kwargs,
            )

            wrapped = cast(Any, guard)(func)
            if ws_endpoint is not None:
                from app.api.ws_command import ws_command

                wrapped = ws_command(ws_endpoint)(wrapped)
            return route(wrapped)

        return decorator

    def get(
        self,
        path: str,
        *,
        model_cls: type[OutBase] | None = None,
        ws_endpoint: str | None = None,
        message: str | None = None,
        on_error: Callable[[Exception], None] | None = None,
        tags: list[str] | None = None,
        summary: str | None = None,
        response_model: type[Any] | None = None,
        status_code: int = 200,
        route_kwargs: dict[str, object] | None = None,
        **fallback_kwargs: object,
    ) -> Callable[[Callable[P, Awaitable[Any]]], Callable[P, Awaitable[Any]]]:
        return self.route(
            path,
            methods=("GET",),
            model_cls=model_cls,
            ws_endpoint=ws_endpoint,
            message=message,
            on_error=on_error,
            tags=tags,
            summary=summary,
            response_model=response_model,
            status_code=status_code,
            route_kwargs=route_kwargs,
            **fallback_kwargs,
        )

    def post(
        self,
        path: str,
        *,
        model_cls: type[OutBase] | None = None,
        ws_endpoint: str | None = None,
        message: str | None = None,
        on_error: Callable[[Exception], None] | None = None,
        tags: list[str] | None = None,
        summary: str | None = None,
        response_model: type[Any] | None = None,
        status_code: int = 200,
        route_kwargs: dict[str, object] | None = None,
        **fallback_kwargs: object,
    ) -> Callable[[Callable[P, Awaitable[Any]]], Callable[P, Awaitable[Any]]]:
        return self.route(
            path,
            methods=("POST",),
            model_cls=model_cls,
            ws_endpoint=ws_endpoint,
            message=message,
            on_error=on_error,
            tags=tags,
            summary=summary,
            response_model=response_model,
            status_code=status_code,
            route_kwargs=route_kwargs,
            **fallback_kwargs,
        )

    def patch(
        self,
        path: str,
        *,
        model_cls: type[OutBase] | None = None,
        ws_endpoint: str | None = None,
        message: str | None = None,
        on_error: Callable[[Exception], None] | None = None,
        tags: list[str] | None = None,
        summary: str | None = None,
        response_model: type[Any] | None = None,
        status_code: int = 200,
        route_kwargs: dict[str, object] | None = None,
        **fallback_kwargs: object,
    ) -> Callable[[Callable[P, Awaitable[Any]]], Callable[P, Awaitable[Any]]]:
        return self.route(
            path,
            methods=("PATCH",),
            model_cls=model_cls,
            ws_endpoint=ws_endpoint,
            message=message,
            on_error=on_error,
            tags=tags,
            summary=summary,
            response_model=response_model,
            status_code=status_code,
            route_kwargs=route_kwargs,
            **fallback_kwargs,
        )

    def delete(
        self,
        path: str,
        *,
        model_cls: type[OutBase] | None = None,
        ws_endpoint: str | None = None,
        message: str | None = None,
        on_error: Callable[[Exception], None] | None = None,
        tags: list[str] | None = None,
        summary: str | None = None,
        response_model: type[Any] | None = None,
        status_code: int = 200,
        route_kwargs: dict[str, object] | None = None,
        **fallback_kwargs: object,
    ) -> Callable[[Callable[P, Awaitable[Any]]], Callable[P, Awaitable[Any]]]:
        return self.route(
            path,
            methods=("DELETE",),
            model_cls=model_cls,
            ws_endpoint=ws_endpoint,
            message=message,
            on_error=on_error,
            tags=tags,
            summary=summary,
            response_model=response_model,
            status_code=status_code,
            route_kwargs=route_kwargs,
            **fallback_kwargs,
        )


def bind_api(router: APIRouter) -> ApiRegistrar:
    """绑定一个 APIRouter 并返回声明式 API 注册器。"""

    return ApiRegistrar(router)


def api_route(
    router: APIRouter,
    path: str,
    *,
    methods: Iterable[str],
    model_cls: type[OutBase] | None = None,
    ws_endpoint: str | None = None,
    message: str | None = None,
    on_error: Callable[[Exception], None] | None = None,
    response_model: type[Any] | None = None,
    route_kwargs: dict[str, object] | None = None,
    **fallback_kwargs: object,
) -> Callable[[Callable[P, Awaitable[Any]]], Callable[P, Awaitable[Any]]]:
    """统一路由注册装饰器（兼容入口）。"""

    return cast(Any, bind_api(router).route)(
        path,
        methods=methods,
        model_cls=model_cls,
        ws_endpoint=ws_endpoint,
        message=message,
        on_error=on_error,
        response_model=response_model,
        route_kwargs=route_kwargs,
        **fallback_kwargs,
    )


def api_get(
    router: APIRouter,
    path: str,
    *,
    model_cls: type[OutBase] | None = None,
    ws_endpoint: str | None = None,
    message: str | None = None,
    on_error: Callable[[Exception], None] | None = None,
    response_model: type[Any] | None = None,
    route_kwargs: dict[str, object] | None = None,
    **fallback_kwargs: object,
) -> Callable[[Callable[P, Awaitable[Any]]], Callable[P, Awaitable[Any]]]:
    """统一 GET 路由注册装饰器（兼容入口）。"""

    return cast(Any, bind_api(router).get)(
        path,
        model_cls=model_cls,
        ws_endpoint=ws_endpoint,
        message=message,
        on_error=on_error,
        response_model=response_model,
        route_kwargs=route_kwargs,
        **fallback_kwargs,
    )


def api_patch(
    router: APIRouter,
    path: str,
    *,
    model_cls: type[OutBase] | None = None,
    ws_endpoint: str | None = None,
    message: str | None = None,
    on_error: Callable[[Exception], None] | None = None,
    response_model: type[Any] | None = None,
    route_kwargs: dict[str, object] | None = None,
    **fallback_kwargs: object,
) -> Callable[[Callable[P, Awaitable[Any]]], Callable[P, Awaitable[Any]]]:
    """统一 PATCH 路由注册装饰器（兼容入口）。"""

    return cast(Any, bind_api(router).patch)(
        path,
        model_cls=model_cls,
        ws_endpoint=ws_endpoint,
        message=message,
        on_error=on_error,
        response_model=response_model,
        route_kwargs=route_kwargs,
        **fallback_kwargs,
    )


def api_delete(
    router: APIRouter,
    path: str,
    *,
    model_cls: type[OutBase] | None = None,
    ws_endpoint: str | None = None,
    message: str | None = None,
    on_error: Callable[[Exception], None] | None = None,
    response_model: type[Any] | None = None,
    route_kwargs: dict[str, object] | None = None,
    **fallback_kwargs: object,
) -> Callable[[Callable[P, Awaitable[Any]]], Callable[P, Awaitable[Any]]]:
    """统一 DELETE 路由注册装饰器（兼容入口）。"""

    return cast(Any, bind_api(router).delete)(
        path,
        model_cls=model_cls,
        ws_endpoint=ws_endpoint,
        message=message,
        on_error=on_error,
        response_model=response_model,
        route_kwargs=route_kwargs,
        **fallback_kwargs,
    )


__all__ = [
    "OutBase",
    "ComboBoxItem",
    "ComboBoxOut",
    "error_out",
    "run_api",
    "bind_api",
    "ApiRegistrar",
    "api_guard",
    "api_route",
    "api_get",
    "api_post",
    "api_patch",
    "api_delete",
]
