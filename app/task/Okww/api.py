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
"""脚本管理：OK-WW 路由与端点专用模型。"""

from fastapi import APIRouter
from pydantic import (
    Field,
)

from app.models.schema import (
    OutBase,
)
from app.utils import get_logger


class OkwwClientPathOut(OutBase):
    """OK-WW 客户端路径解码结果（仅用于前端展示）"""

    client_path: str = Field(..., description="解码得到的鸣潮客户端 exe 完整路径")


router = APIRouter()
logger = get_logger("脚本管理 API")


@router.get(
    "/okww/client-path",
    tags=["Get"],
    summary="解码鸣潮启动器，返回客户端 exe 路径",
    response_model=OkwwClientPathOut,
    status_code=200,
)
async def get_okww_client_path_api(scriptId: str) -> OkwwClientPathOut:
    """解码鸣潮启动器记录，返回客户端 exe 完整路径（仅直启模式的前端展示用）。

    任务期的启动与自动更新链路由后端自行解码，不经过本端点。
    """

    try:
        from app.task.Okww import api_service as domain_api

        client_path = domain_api.resolve_client_path(scriptId)
        return OkwwClientPathOut(
            code=200,
            status="success",
            message="",
            client_path=client_path.as_posix(),
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_okww_client_path_api失败: {type(e).__name__}: {e}"
        )
        return OkwwClientPathOut(
            code=(
                400
                if isinstance(e, (ValueError, KeyError, TypeError, FileNotFoundError))
                else 500
            ),
            status="error",
            # message 直接展示给用户，不带异常类名前缀（类名只进上面的日志）
            message=str(e),
            client_path="",
        )
