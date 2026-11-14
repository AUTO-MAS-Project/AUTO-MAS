"""协调桌面分身数据交接的后端入口。"""

import os
from hmac import compare_digest
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from starlette.responses import JSONResponse

from .ownership import CONTROL_TOKEN, EXECUTOR_SESSION, EXECUTOR_TOKEN

# 普通 API 和上下游进程不需要知道控制凭据。
_control_token = os.environ.pop(CONTROL_TOKEN, "")
_executor_token = os.environ.pop(EXECUTOR_TOKEN, "")
_executor_session = os.environ.pop(EXECUTOR_SESSION, "")
_handoff = False
_commands_inflight = 0
CONTROL_HEADER = "x-mas-desktop-session"


class QueueSelection(BaseModel):
    queueIds: list[UUID] = Field(min_length=1, max_length=100)


def executor_session() -> int | None:
    return int(_executor_session) if _executor_session else None


def admit_command() -> bool:
    """跟踪绕过 HTTP 中间件执行的调度命令。"""
    global _commands_inflight
    if _executor_session or _handoff:
        return False
    _commands_inflight += 1
    return True


def release_command() -> None:
    global _commands_inflight
    _commands_inflight -= 1


def authenticated(value: str | None) -> bool:
    expected = _executor_token if _executor_session else _control_token
    return bool(
        expected and value and value.isascii() and compare_digest(expected, value)
    )


def install_control(app: FastAPI) -> None:
    """注册桌面进程专用端点，不加入 OpenAPI 或 MCP。"""
    import asyncio
    import sys

    from app.core import Config, Power, ShutdownCoordinator, TaskManager
    from app.models.task import TaskMode
    from app.utils import get_logger
    from app.utils.contracts.power import PowerSignal

    lock = asyncio.Lock()
    draining = False
    inflight = 0
    logger = get_logger("桌面分身")

    async def guard(scope, receive, send, application):
        nonlocal inflight
        scope_type = scope["type"]
        internal = scope.get("path", "").startswith("/internal/desktop-session/")
        if scope_type not in ("http", "websocket") or internal:
            await application(scope, receive, send)
            return
        if _executor_token:
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
                _handoff
                and scope.get("path") == "/api/core/close"
                and scope.get("client", ("",))[0] in ("127.0.0.1", "::1")
            )
            if draining and not runtime_close:
                await JSONResponse(
                    {"code": 409, "message": "桌面分身正在交接配置"}, status_code=409
                )(scope, receive, send)
                return
            inflight += 1
            try:
                await application(scope, receive, send)
            finally:
                inflight -= 1
        else:
            if draining:
                await send({"type": "websocket.close", "code": 1008})
                return
            await application(scope, receive, send)

    class Middleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            await guard(scope, receive, send, self.app)

    app.add_middleware(Middleware)

    def authorize(request: Request, *, child: bool) -> None:
        if (
            request.client is None
            or request.client.host not in ("127.0.0.1", "::1")
            or bool(_executor_session) != child
            or not authenticated(request.headers.get(CONTROL_HEADER))
        ):
            raise HTTPException(status_code=403)

    @app.post("/internal/desktop-session/describe", include_in_schema=False)
    async def describe(request: Request):
        authorize(request, child=False)
        return {
            "python": sys.executable,
            "source": str(Config.source_path),
            "root": str(Config.work_path),
        }

    @app.post("/internal/desktop-session/handoff", include_in_schema=False)
    async def handoff(request: Request):
        global _handoff
        nonlocal draining
        authorize(request, child=False)
        async with lock:
            if (
                draining
                or inflight
                or _commands_inflight
                or not TaskManager.idle
                or Power.power_task is not None
            ):
                raise HTTPException(
                    status_code=409, detail="主会话有任务、更新或配置操作正在运行"
                )
            if app.state.background_status != "ready":
                raise HTTPException(status_code=409, detail="主会话尚未完成后台初始化")
            draining = True
            _handoff = True
            TaskManager.pause_admission()
            await ShutdownCoordinator.run_teardown()
            # Runtime 在关闭指令前会把自行退出的后端重新拉起。
        return {"released": True}

    @app.post("/internal/desktop-session/queues", include_in_schema=False)
    async def queues(request: Request):
        authorize(request, child=True)
        try:
            selection = QueueSelection.model_validate_json(await request.body())
        except ValidationError:
            raise HTTPException(status_code=422, detail="队列选择无效") from None
        results = []
        async with lock:
            if draining:
                raise HTTPException(status_code=409, detail="桌面分身正在关闭")
            from app.utils.windows.desktop_session.native import session_state

            if session_state(int(_executor_session)) != 0:
                raise HTTPException(status_code=409, detail="桌面分身连接已断开")
            for uid in dict.fromkeys(selection.queueIds):
                queue = Config.QueueConfig.get(uid)
                script = Config.ScriptConfig.get(uid) if queue is None else None
                target = queue if queue is not None else script
                item = {
                    "queueId": str(uid),
                    "taskId": "",
                    "code": "",
                    "label": target.Info.Name if target is not None else str(uid),
                }
                results.append(item)
                if target is None:
                    item["code"] = "target_missing"
                    continue
                if (
                    queue is not None
                    and queue.Info.AfterAccomplish != PowerSignal.NO_ACTION
                ):
                    item["code"] = "power_action"
                    continue
                try:
                    node = (
                        {"uid": str(uid)}
                        if queue is not None
                        else {"uid": "-", "children": {0: {"uid": str(uid)}}}
                    )
                    task_id = await TaskManager.start(TaskMode.AUTO_PROXY, {0: node})
                    item["taskId"] = str(task_id)
                except (RuntimeError, ValueError) as exc:
                    logger.warning(f"任务 {uid} 派发失败: {exc}")
                    item["code"] = "dispatch_failed"
        return {"results": results}

    @app.post("/internal/desktop-session/state", include_in_schema=False)
    async def state(request: Request):
        authorize(request, child=True)
        return {"idle": TaskManager.idle}

    @app.post("/internal/desktop-session/exit", include_in_schema=False)
    async def exit_executor(request: Request):
        nonlocal draining
        authorize(request, child=True)
        async with lock:
            draining = True
            TaskManager.pause_admission()
            await ShutdownCoordinator.run_teardown()
            Config.server.should_exit = True
        return {"released": True}
