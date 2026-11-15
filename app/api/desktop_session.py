"""桌面分身主进程与执行器之间的本机控制接口。"""

import sys
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

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
    app.include_router(router)


def authorize(request: Request) -> None:
    if (
        request.client is None
        or request.client.host not in ("127.0.0.1", "::1")
        or not authenticated(request.headers.get(CONTROL_HEADER))
    ):
        raise HTTPException(status_code=403)


@router.post("/describe")
async def describe(request: Request) -> dict[str, str]:
    from app.core import Config

    authorize(request)
    return {
        "python": sys.executable,
        "source": str(Config.source_path),
        "root": str(Config.work_path),
    }


@router.post("/process-scope")
async def process_scope(request: Request, scope: ParentProcessScope) -> dict[str, bool]:
    authorize(request)
    DesktopSessionLifecycle.set_process_scope(
        session_id=scope.sessionId, connecting=scope.connecting
    )
    return {"updated": True}


@router.post("/queues", response_model=QueueDispatchResult)
async def queues(
    request: Request, selection: QueueSelection
) -> dict[str, list[dict[str, str]]]:
    authorize(request)
    try:
        results = await DesktopSessionLifecycle.start_queues(selection.queueIds)
    except DesktopSessionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"results": results}


@router.post("/state")
async def state(request: Request) -> dict[str, bool]:
    authorize(request)
    return {"idle": await DesktopSessionLifecycle.idle()}


@router.post("/stop")
async def stop(request: Request) -> dict[str, bool]:
    authorize(request)
    return {"idle": await DesktopSessionLifecycle.stop_tasks()}
