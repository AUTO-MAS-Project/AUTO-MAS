"""桌面分身主进程与执行器之间的本机控制接口。"""

import sys
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.desktop_session.lifecycle import (
    CONTROL_HEADER,
    DesktopSessionConflict,
    DesktopSessionLifecycle,
    authenticated,
)
from app.plugin.errors import PluginBusyError


class QueueSelection(BaseModel):
    queueIds: list[UUID] = Field(min_length=1, max_length=100)
    previewOnly: bool = False
    mainSessionQueueIds: set[UUID] = Field(default_factory=set, max_length=100)


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


class QueueDispatchConflictOut(BaseModel):
    code: Literal["session_changed"] = "session_changed"
    status: Literal["error"] = "error"
    message: str


class RuntimeDescriptionOut(BaseModel):
    python: str
    source: str
    root: str
    launcher: str


class ScopeUpdateOut(BaseModel):
    updated: bool


class PreviewClosingIn(BaseModel):
    closing: bool


class SessionStateOut(BaseModel):
    idle: bool


router = APIRouter(prefix="/internal/desktop-session", include_in_schema=False)


def install_control(app: FastAPI) -> None:
    DesktopSessionLifecycle.configure_process_scope()
    app.include_router(router)


def authorize(request: Request) -> None:
    if (
        request.client is None
        or request.client.host not in ("127.0.0.1", "::1")
        or not authenticated(request.headers.get(CONTROL_HEADER))
    ):
        raise HTTPException(status_code=403)


@router.post("/describe", response_model=RuntimeDescriptionOut)
async def describe(request: Request, reserve: bool = False) -> RuntimeDescriptionOut:
    from app.core import Config, Plugin

    authorize(request)
    if Plugin.installation_restart_reserved:
        raise HTTPException(status_code=503)
    launcher = Plugin.services.get("desktop_session.launcher")
    if launcher is None:
        raise HTTPException(status_code=404)
    try:
        path = launcher()
    except PluginBusyError as exc:
        raise HTTPException(status_code=503) from exc
    if reserve:
        DesktopSessionLifecycle.reserve_preview()
    return RuntimeDescriptionOut(
        python=sys.executable,
        source=str(Config.source_path),
        root=str(Config.work_path),
        launcher=str(path),
    )


@router.post("/release", response_model=ScopeUpdateOut)
async def release(request: Request) -> ScopeUpdateOut:
    authorize(request)
    DesktopSessionLifecycle.release_preview()
    return ScopeUpdateOut(updated=True)


@router.post("/process-scope", response_model=ScopeUpdateOut)
async def process_scope(request: Request, scope: ParentProcessScope) -> ScopeUpdateOut:
    authorize(request)
    await DesktopSessionLifecycle.set_process_scope(
        session_id=scope.sessionId, connecting=scope.connecting
    )
    return ScopeUpdateOut(updated=True)


@router.post(
    "/queues",
    response_model=QueueDispatchResult,
    responses={409: {"model": QueueDispatchConflictOut}},
)
async def queues(
    request: Request, selection: QueueSelection
) -> QueueDispatchResult | JSONResponse:
    authorize(request)
    try:
        results = await DesktopSessionLifecycle.dispatch_queues(
            selection.queueIds,
            preview_only=selection.previewOnly,
            main_session_queue_ids=selection.mainSessionQueueIds,
        )
    except DesktopSessionConflict as exc:
        return JSONResponse(
            status_code=409,
            content=QueueDispatchConflictOut(message=str(exc)).model_dump(),
        )
    return QueueDispatchResult(results=[QueueResult(**item) for item in results])


@router.post("/state", response_model=SessionStateOut)
async def state(request: Request) -> SessionStateOut:
    authorize(request)
    return SessionStateOut(idle=await DesktopSessionLifecycle.idle())


@router.post("/preview-closing", response_model=SessionStateOut)
async def preview_closing(request: Request, data: PreviewClosingIn) -> SessionStateOut:
    authorize(request)
    return SessionStateOut(
        idle=await DesktopSessionLifecycle.set_preview_closing(closing=data.closing)
    )


@router.post("/stop", response_model=SessionStateOut)
async def stop(request: Request) -> SessionStateOut:
    authorize(request)
    return SessionStateOut(idle=await DesktopSessionLifecycle.stop_tasks())
