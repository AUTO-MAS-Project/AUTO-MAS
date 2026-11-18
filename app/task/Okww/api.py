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
"""托管管理：OK-WW 路由与端点专用模型。"""

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import (
    BaseModel,
    Field,
)

from app.models.schema import (
    OutBase,
)
from app.utils import get_logger

from .tools.config_fields import PanelKind


class OkwwClientPathOut(OutBase):
    """OK-WW 客户端路径解码结果（仅用于前端展示）"""

    client_path: str = Field(..., description="解码得到的鸣潮客户端 exe 完整路径")


router = APIRouter()
logger = get_logger("托管管理 API")


class OkwwArgumentsIn(BaseModel):
    scriptId: str
    custom: bool = False
    arguments: str = ""


class OkwwArgumentsOut(OutBase):
    arguments: list[str] = Field(default_factory=list)
    native_switch: bool = False


class OkwwConfigField(BaseModel):
    name: str
    disabled: bool = False
    minimum: float | None = None
    maximum: float | None = None
    integer: bool = False
    type: Literal["bool", "number", "string", "select", "multi_selection", "json"]
    options: list[str] = Field(default_factory=list)
    parent: str | None = None
    choices: list[str] = Field(default_factory=list)


class OkwwTaskConfigOut(OutBase):
    labels: dict[str, str] = Field(default_factory=dict)
    values: dict[str, Any] = Field(default_factory=dict)
    fields: list[OkwwConfigField] = Field(default_factory=list)


class OkwwTaskConfigIn(BaseModel):
    scriptId: str
    userId: str
    kind: PanelKind
    values: dict[str, Any]


@router.get("/okww/task-config", tags=["Get"], response_model=OkwwTaskConfigOut)
async def get_okww_task_config_api(
    scriptId: str,
    userId: str,
    kind: PanelKind,
    locale: Literal["zh_CN", "en_US", "ja_JP"] = "zh_CN",
) -> OkwwTaskConfigOut:
    """读取原生字段及半动态控件描述。"""
    from .api_service import describe_task_config, read_config_labels

    try:
        values, fields = describe_task_config(scriptId, userId, kind)
        return OkwwTaskConfigOut(
            code=200,
            status="success",
            message="",
            values=values,
            fields=fields,
            labels=read_config_labels(scriptId, locale),
        )
    except (ValueError, KeyError, TypeError, OSError) as error:
        return OkwwTaskConfigOut(code=400, status="error", message=str(error))


@router.post("/okww/task-config", tags=["Set"], response_model=OutBase)
async def save_okww_task_config_api(data: OkwwTaskConfigIn) -> OutBase:
    """保存面板及已有日常字段，不修改基础来源。"""
    from .api_service import save_task_config

    try:
        await save_task_config(data.scriptId, data.userId, data.kind, data.values)
        return OutBase(code=200, status="success", message="")
    except (ValueError, KeyError, TypeError, OSError) as error:
        return OutBase(code=400, status="error", message=str(error))


@router.post("/okww/startup-arguments", tags=["Get"], response_model=OkwwArgumentsOut)
async def preview_okww_arguments_api(data: OkwwArgumentsIn) -> OkwwArgumentsOut:
    """按实际启动规则预览参数，不启动脚本。"""
    from .api_service import resolve_startup_arguments

    try:
        arguments, native = resolve_startup_arguments(
            data.scriptId, custom=data.custom, arguments=data.arguments
        )
        return OkwwArgumentsOut(
            code=200,
            status="success",
            message="",
            arguments=arguments,
            native_switch=native,
        )
    except (ValueError, KeyError, TypeError, OSError) as error:
        return OkwwArgumentsOut(code=400, status="error", message=str(error))


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
