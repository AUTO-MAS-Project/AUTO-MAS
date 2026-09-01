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
from typing import Optional

from fastapi import APIRouter, Request, WebSocket
from pydantic import BaseModel, Field

from app.core import Config, TaskManager
from app.core.lifecycle import ShutdownCoordinator
from app.core.ws import MainConnection, Publisher, protocol
from app.services import System
from app.models.schema import *
from app.api.ws_command import ws_command
from app.utils import get_logger, is_supervised

router = APIRouter(prefix="/api/core", tags=["核心信息"])
logger = get_logger("DEV")


class WebSocketMetaOut(BaseModel):
    """前端协商主 WebSocket 链接时使用的元信息。"""

    devMode: bool = Field(description="后端当前是否处于开发模式")
    wsPath: str = Field(default="/api/core/ws", description="主 WebSocket 路径")


# AUTO-MAS-Runtime 健康检查协议版本：固定返回后端自身支持的版本，不回显监督器注入值，
# 协议升级后只有如此监督器才能检出版本不兼容。
HEALTH_PROTOCOL_VERSION = 1


class BackendHealthOut(BaseModel):
    """后端核心服务与后台初始化状态。"""

    ready: bool = Field(description="核心 API 是否可用")
    backgroundStatus: str = Field(description="后台初始化状态")
    backgroundError: str | None = Field(default=None, description="后台初始化失败原因")
    protocol: int = Field(description="后端自身支持的健康检查协议版本")
    version: str = Field(description="后端版本号")
    commit: str = Field(description="后端所在提交哈希，未受监督或监督器未注入时为空")


def is_supervised_by_runtime() -> bool:
    """判断后端是否由 AUTO-MAS-Runtime 等外部进程监督器拉起。"""

    return os.getenv("AUTO_MAS_SUPERVISED") == "1"


def _resolve_injected_identity(env_name: str) -> str | None:
    """受监督时读取监督器注入的期望身份值。

    未受监督、或对应环境变量缺失/为空字符串时返回 None，交由调用方回退默认值。
    """

    if not is_supervised_by_runtime():
        return None
    return os.getenv(env_name, "") or None


@router.get(
    "/health",
    summary="获取后端就绪状态",
    response_model=BackendHealthOut,
    status_code=200,
)
async def get_health(request: Request) -> BackendHealthOut:
    """返回核心 API 与后台初始化状态，供 AUTO-MAS-Runtime 等外部监督器判定就绪与身份。

    version/commit 受监督且监督器注入了期望值时原样回显，否则分别回退到本地版本号
    与空字符串；commit 不通过 Git 推断，只能来自监督器注入。
    """

    return BackendHealthOut(
        ready=True,
        backgroundStatus=getattr(request.app.state, "background_status", "starting"),
        backgroundError=getattr(request.app.state, "background_error", None),
        protocol=HEALTH_PROTOCOL_VERSION,
        version=_resolve_injected_identity("AUTO_MAS_EXPECTED_VERSION")
        or Config.VERSION,
        commit=_resolve_injected_identity("AUTO_MAS_EXPECTED_COMMIT") or "",
    )


def is_backend_dev_mode() -> bool:
    """判断后端是否处于开发模式（后端由开发者独立管理，前端不得强杀）。

    dev 分支的 AUTO_MAS_DEV 标记“由前端拉起”（跳过自行提权），生产环境同样为 1，
    不能作为开发模式依据；以 main.py 启动时归一化的 AUTO_MAS_ENV 为准。

    受 AUTO-MAS-Runtime 监督时优先级高于 AUTO_MAS_DEV 与 AUTO_MAS_ENV，恒为
    False：监督器依赖 /api/core/close 真正退出进程，若判定为开发模式，
    _shutdown_backend() 只做轻量清理、不设 should_exit，关闭请求就会永远
    不生效，5 秒后被监督器硬杀。
    """

    if is_supervised():
        return False

    raw = str(os.getenv("AUTO_MAS_ENV", "")).strip().lower()
    return raw in {"dev", "development"}


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


# 主连接建立后触发启动时调度队列
MainConnection.on_connect(TaskManager.start_startup_queue)


@router.websocket("/ws")
async def connect_websocket(websocket: WebSocket):
    """主 WebSocket 端点，接入后整体交给 MainConnection 管理。"""

    await MainConnection.serve(websocket)


# 关闭流程任务由模块持有，重复 /close 请求不重复触发
_shutdown_task: Optional[asyncio.Task] = None


async def _shutdown_backend() -> None:
    """后端正常关闭收尾：完成完整清理后再通知前端可退出，最后置退出标志。"""

    # 开发模式：后端保持存活以复用（定时器等服务不拆除），
    # 只做轻量任务清理后即通知前端可退出
    if is_backend_dev_mode():
        try:
            await TaskManager.stop_task("ALL")
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

    # 执行完整 teardown（任务/定时器/遥测等），失败则不发送完成信号，
    # 避免前端在清理未完成时就认为可以退出
    try:
        await ShutdownCoordinator.run_teardown()
    except Exception as e:
        logger.error(
            f"后端清理失败，取消发送退出信号: {type(e).__name__}: {e}", exc_info=True
        )
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

    def _on_done(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(f"关闭流程异常: {type(exc).__name__}: {exc}")

    _shutdown_task.add_done_callback(_on_done)
    return OutBase()
