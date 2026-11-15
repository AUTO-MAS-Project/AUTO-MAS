"""桌面分身主进程与执行器之间的本机控制接口。"""

import sys
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.desktop_session.lifecycle import (
    CONTROL_HEADER,
    DesktopSessionConflict,
    DesktopSessionLifecycle,
    authenticated,
)


class QueueSelection(BaseModel):
    queueIds: list[UUID] = Field(min_length=1, max_length=100)


class ParentProcessScope(BaseModel):
    sessionId: int | None = Field(gt=0, le=0xFFFFFFFE)
    connecting: bool = False


class QueueResult(BaseModel):
    queueId: str
    taskId: str
    targetKind: Literal["queue", "script", "unknown"]
    code: str
    label: str


class QueueDispatchResult(BaseModel):
    results: list[QueueResult]


router = APIRouter(prefix="/internal/desktop-session", include_in_schema=False)


def install_control(app: FastAPI) -> None:
    DesktopSessionLifecycle.configure_process_scope()
    app.add_middleware(DesktopSessionMiddleware)
    app.include_router(router)


def authorize(request: Request, *, child: bool) -> None:
    if (
        request.client is None
        or request.client.host not in ("127.0.0.1", "::1")
        or DesktopSessionLifecycle.is_child != child
        or not authenticated(request.headers.get(CONTROL_HEADER))
    ):
        raise HTTPException(status_code=403)


@router.post("/describe")
async def describe(request: Request) -> dict[str, str]:
    from app.core import Config

    authorize(request, child=False)
    return {
        "python": sys.executable,
        "source": str(Config.source_path),
        "root": str(Config.work_path),
    }


@router.post("/process-scope")
async def process_scope(request: Request, scope: ParentProcessScope) -> dict[str, bool]:
    authorize(request, child=False)
    DesktopSessionLifecycle.set_process_scope(
        session_id=scope.sessionId, connecting=scope.connecting
    )
    return {"updated": True}


@router.post("/handoff")
async def handoff(request: Request) -> dict[str, bool]:
    authorize(request, child=False)
    try:
        await DesktopSessionLifecycle.handoff(
            background_ready=request.app.state.background_status == "ready"
        )
    except DesktopSessionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"released": True}


@router.post("/queues", response_model=QueueDispatchResult)
async def queues(
    request: Request, selection: QueueSelection
) -> dict[str, list[dict[str, str]]]:
    authorize(request, child=True)
    try:
        results = await DesktopSessionLifecycle.start_queues(selection.queueIds)
    except DesktopSessionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"results": results}


@router.post("/state")
async def state(request: Request) -> dict[str, bool]:
    from app.core import TaskManager

    authorize(request, child=True)
    return {"idle": TaskManager.idle}


@router.post("/exit")
async def exit_executor(request: Request) -> dict[str, bool]:
    authorize(request, child=True)
    await DesktopSessionLifecycle.exit_executor()
    return {"released": True}


class DesktopSessionMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        lifecycle = DesktopSessionLifecycle
        scope_type = scope["type"]
        internal = scope.get("path", "").startswith("/internal/desktop-session/")
        if scope_type not in ("http", "websocket") or internal:
            await self.app(scope, receive, send)
            return
        if lifecycle.is_child:
            headers = dict(scope["headers"])
            if not authenticated(
                headers.get(CONTROL_HEADER.encode(), b"").decode("latin-1")
            ):
                if scope_type == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    await JSONResponse(
                        {"code": 403, "message": "拒绝访问"}, status_code=403
                    )(scope, receive, send)
                return
            if (
                scope_type == "http"
                and scope["method"] != "GET"
                and scope["path"]
                not in (
                    "/api/dispatch/get",
                    "/api/dispatch/stop",
                    "/api/dispatch/get/power",
                    "/api/queue/get",
                    "/api/scripts/get",
                )
            ):
                await JSONResponse(
                    {"code": 409, "message": "桌面分身正在执行队列"}, status_code=409
                )(scope, receive, send)
                return
        if scope_type == "http":
            runtime_close = (
                lifecycle.handed_off
                and scope.get("path") == "/api/core/close"
                and scope.get("client", ("",))[0] in ("127.0.0.1", "::1")
            )
            if lifecycle.draining and not runtime_close:
                await JSONResponse(
                    {"code": 409, "message": "桌面分身正在交接配置"}, status_code=409
                )(scope, receive, send)
                return
            lifecycle.inflight += 1
            try:
                await self.app(scope, receive, send)
            finally:
                lifecycle.inflight -= 1
        else:
            if lifecycle.draining:
                await send({"type": "websocket.close", "code": 1008})
                return
            await self.app(scope, receive, send)
