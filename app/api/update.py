#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import asyncio
import json

from fastapi import APIRouter, Body, Query
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core import Config, MainTimer, TaskManager
from app.core.lifecycle import BackendBusyError
from app.models.schema import *
from app.services import Updater
from app.utils import get_logger

router = APIRouter(prefix="/api/update", tags=["软件更新"])
logger = get_logger("软件更新 API")


class BackendOperationMiddleware:
    """保护完整 API 请求，包括 GET 触发的回读、导入与恢复落盘。"""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] == "http" and path == "/api/core/health":
            status = 0
            body = bytearray()
            complete = False

            async def send_health(message: Message) -> None:
                nonlocal status, complete
                await send(message)
                if message["type"] == "http.response.start":
                    status = message["status"]
                elif message["type"] == "http.response.body":
                    body.extend(message.get("body", b""))
                    complete = not message.get("more_body", False)

            await self.app(scope, receive, send_health)
            if status == 200 and complete:
                health = json.loads(body)
                if (
                    health.get("ready") is True
                    and health.get("backgroundStatus") == "ready"
                ):
                    MainTimer.confirm_hot_update_checkpoint()
            return
        if (
            scope["type"] != "http"
            or not path.startswith("/api/")
            or path
            in {
                "/api/core/ws_meta",
                "/api/core/close",
                "/api/update/hot-update",
            }
        ):
            await self.app(scope, receive, send)
            return
        try:
            await TaskManager.run_backend_operation(
                lambda: self.app(scope, receive, send)
            )
        except BackendBusyError as error:
            response = JSONResponse(
                status_code=409,
                content=OutBase(
                    code=409, status="error", message=str(error)
                ).model_dump(),
            )
            await response(scope, receive, send)


@router.get(
    "/download/status",
    tags=["Get"],
    summary="获取更新下载初始快照",
    response_model=UpdateDownloadSnapshot,
    status_code=200,
)
async def get_update_download_status() -> UpdateDownloadSnapshot:
    """返回当前下载权威状态；WS 只承载后续进度与终态事件。"""

    return Updater.get_download_snapshot()


@router.post(
    "/check",
    tags=["Get"],
    summary="检查更新",
    response_model=UpdateCheckOut,
    status_code=200,
)
async def check_update(version: UpdateCheckIn = Body(...)) -> UpdateCheckOut:

    try:
        if_need, latest_version, update_info = await Updater.check_update(
            current_version=version.current_version, if_force=version.if_force
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"check_update失败: {type(e).__name__}: {e}")
        return UpdateCheckOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            if_need_update=False,
            latest_version="",
            update_info={},
        )
    return UpdateCheckOut(
        if_need_update=if_need, latest_version=latest_version, update_info=update_info
    )


@router.post(
    "/download",
    tags=["Action"],
    summary="下载更新",
    response_model=OutBase,
    status_code=200,
)
async def download_update(
    target_version: str | None = Query(default=None, alias="version"),
) -> OutBase:

    try:
        if not await Updater.start_download(target_version=target_version):
            return OutBase(
                code=409,
                status="error",
                message="已有更新任务在进行中, 请勿重复操作",
            )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"download_update失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/cancel-download",
    tags=["Action"],
    summary="取消下载更新",
    response_model=OutBase,
    status_code=200,
)
async def cancel_update_download() -> OutBase:

    try:
        if not await Updater.cancel_download():
            return OutBase(
                code=409, status="error", message="当前没有正在进行中的下载任务"
            )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"cancel_update_download失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500,
            status="error",
            message=f"取消更新下载失败: {type(e).__name__}: {str(e)}",
        )
    return OutBase()


@router.post(
    "/switch-to-cnb",
    tags=["Action"],
    summary="切换下载源到 CNB",
    response_model=OutBase,
    status_code=200,
)
async def switch_update_download_to_cnb() -> OutBase:

    try:
        if not await Updater.switch_to_cnb():
            return OutBase(
                code=409,
                status="error",
                message="当前无法切换到 CNB 下载源, 请确认正在从 GitHub 源下载",
            )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"switch_update_download_to_cnb失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500,
            status="error",
            message=f"切换至 CNB 源失败: {type(e).__name__}: {str(e)}",
        )
    return OutBase()


@router.post(
    "/install",
    tags=["Action"],
    summary="安装更新",
    response_model=OutBase,
    status_code=200,
)
async def install_update() -> OutBase:

    try:
        task = asyncio.create_task(Updater.install_update())
        Config.temp_task.append(task)
        task.add_done_callback(lambda t: Config.temp_task.remove(t))
    except Exception as e:
        logger.opt(exception=True).warning(
            f"install_update失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/hot-update",
    tags=["Action"],
    summary="后端热更协调准入",
    response_model=HotUpdatePrepareOut,
    status_code=200,
)
async def prepare_hot_update(
    params: HotUpdatePrepareIn = Body(...),
) -> HotUpdatePrepareOut:
    """
    申请或撤销后端热更保护。

    prepare: 检查空闲、避让窗口，准入后进入更新状态；
    drain: 复核同一准备操作并完成关闭清理，不退出进程；
    cancel: 撤销对应操作的保护。

    忙、临近定时、暂停是正常的延期决策，不产生用户失败通知；
    参数或执行异常仍走现有 OutBase 错误契约。
    """
    try:
        if params.action in {"prepare", "drain"}:
            action = (
                TaskManager.check_hot_update_admission
                if params.action == "prepare"
                else TaskManager.drain_hot_update
            )
            (
                ready,
                reason,
                next_scheduled,
            ) = await action(
                operation_id=params.operationId,
                base_commit=params.baseCommit.lower(),
                target_commit=params.targetCommit.lower(),
            )

            return HotUpdatePrepareOut(
                ready=ready,
                reason=reason,
                nextScheduledTime=next_scheduled.isoformat()
                if next_scheduled
                else None,
            )

        cancelled = await TaskManager.cancel_hot_update_guard(
            operation_id=params.operationId,
            base_commit=params.baseCommit.lower(),
            target_commit=params.targetCommit.lower(),
        )
        return HotUpdatePrepareOut(ready=False, reason=None if cancelled else "closing")
    except ValueError as error:
        return HotUpdatePrepareOut(code=409, status="error", message=str(error))
    except Exception as e:
        logger.opt(exception=True).error(f"热更准入失败: {type(e).__name__}: {e}")
        return HotUpdatePrepareOut(
            code=500,
            status="error",
            message="后端热更准备失败，请稍后重试",
            ready=False,
            reason="closing" if params.action == "drain" else None,
        )
