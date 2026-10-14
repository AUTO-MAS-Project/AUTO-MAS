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
import os
from contextlib import suppress

from fastapi import APIRouter, Request, WebSocket

from app.api.ws_command import ws_command
from app.core import Config, TaskDispatcher
from app.core.lifecycle import ShutdownCoordinator
from app.core.ws import Dialogs, MainConnection, Publisher, protocol
from app.core.ws.protocol import WSDialogRequestData
from app.models.schema import BackendHealthOut, OutBase, WebSocketMetaOut
from app.services import System
from app.utils import get_logger, is_backend_dev_mode, is_supervised

router = APIRouter(prefix="/api/core", tags=["核心信息"])
logger = get_logger("DEV")


# 返回后端实际支持的版本，不回显监督器注入值，以便检出协议不兼容。
HEALTH_PROTOCOL_VERSION = 1


def _resolve_injected_identity(env_name: str) -> str | None:
    """受监督时读取监督器注入的身份，缺失时交由调用方回退。"""

    if not is_supervised():
        return None
    return os.getenv(env_name, "") or None


@router.get(
    "/health",
    summary="获取后端就绪状态",
    response_model=BackendHealthOut,
    status_code=200,
)
async def get_health(request: Request) -> BackendHealthOut:
    """返回后台初始化状态与受监督身份，commit 仅来自监督器注入。"""

    return BackendHealthOut(
        ready=True,
        backgroundStatus=getattr(request.app.state, "background_status", "starting"),
        backgroundError=getattr(request.app.state, "background_error", None),
        backgroundWarnings=list(
            getattr(request.app.state, "background_warnings", None) or []
        ),
        protocol=HEALTH_PROTOCOL_VERSION,
        version=_resolve_injected_identity("AUTO_MAS_EXPECTED_VERSION")
        or Config.VERSION,
        commit=_resolve_injected_identity("AUTO_MAS_EXPECTED_COMMIT") or "",
    )


@router.get(
    "/ws_meta",
    summary="获取主 WebSocket 元信息",
    response_model=WebSocketMetaOut,
    status_code=200,
)
async def get_ws_meta() -> WebSocketMetaOut:
    """返回前端建立主 WebSocket 连接需要的元信息。"""

    return WebSocketMetaOut(
        devMode=is_backend_dev_mode(),
        wsPath="/api/core/ws",
    )


@router.get(
    "/dialogs/pending",
    summary="获取待处理弹窗初始快照",
    response_model=list[WSDialogRequestData],
    status_code=200,
)
async def get_pending_dialogs() -> list[WSDialogRequestData]:
    """返回当前未完成弹窗；WS 只承载后续请求与响应事件。"""

    return Dialogs.pending_requests()


# 主连接建立后触发启动时调度队列
MainConnection.on_connect(TaskDispatcher.start_startup_queue)


@router.websocket("/ws")
async def connect_websocket(websocket: WebSocket):
    """主 WebSocket 端点，接入后整体交给 MainConnection 管理。"""

    await MainConnection.serve(websocket)


# 关闭流程任务由模块持有，重复 /close 请求不重复触发
_shutdown_task: asyncio.Task[None] | None = None


async def _shutdown_backend() -> None:
    """后端正常关闭收尾：完成完整清理后再通知前端可退出，最后置退出标志。"""

    # 开发模式：后端保持存活以复用（插件/定时器等服务不拆除），
    # 只做轻量任务清理后即通知前端可退出
    if is_backend_dev_mode():
        try:
            await TaskDispatcher.stop("ALL")
            with suppress(RuntimeError):
                await System.cancel_power_task()
        except Exception as error:
            logger.error(
                "开发模式轻量清理失败，取消发送退出信号: "
                f"{type(error).__name__}: {error}",
                exc_info=True,
            )
            return
        await Publisher.send(id=protocol.ID_MAIN, type=protocol.BACKEND_SHUTDOWN_READY)
        logger.warning("后端开发模式下忽略退出请求，仅完成任务清理")
        return

    # 执行完整 teardown（任务/插件/定时器/遥测等），失败则不发送完成信号，
    # 避免前端在清理未完成时就认为可以退出
    try:
        await ShutdownCoordinator.run_teardown()
    except Exception as e:
        logger.error(f"后端清理失败，取消发送退出信号: {type(e).__name__}: {e}", exc_info=True)
        return

    # 清理完成后通过主 WS 通知前端可以退出
    await Publisher.send(id=protocol.ID_MAIN, type=protocol.BACKEND_SHUTDOWN_READY)

    if Config.server is not None:
        Config.server.should_exit = True


@ws_command("core.close")
@router.post(
    "/close",
    summary="关闭后端程序",
    response_model=OutBase,
    status_code=200,
)
async def close() -> OutBase:
    """关闭后端程序：启动清理流程，完成后经主 WS 发送 backend.shutdown.ready"""

    global _shutdown_task

    if _shutdown_task is not None and not _shutdown_task.done():
        return OutBase(message="关闭流程已在进行中")

    _shutdown_task = asyncio.create_task(_shutdown_backend())

    def _on_done(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(f"关闭流程异常: {type(exc).__name__}: {exc}")

    _shutdown_task.add_done_callback(_on_done)
    return OutBase()
