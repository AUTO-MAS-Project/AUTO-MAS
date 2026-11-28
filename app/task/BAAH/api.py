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
"""托管管理：BAAH 路由与端点专用模型。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.models.schema import (
    ComboBoxItem,
    ComboBoxOut,
    OutBase,
)
from app.utils import get_logger

from .api_service import BAAHConfigService


def get_baah_config_service(request: Request) -> BAAHConfigService:
    return request.app.state.baah_config_service


BAAHService = Annotated[BAAHConfigService, Depends(get_baah_config_service)]

router = APIRouter()
logger = get_logger("托管管理 API")


class BAAHRecommendedConfigIn(BaseModel):
    scriptId: str = Field(description="BAAH 托管 ID")


class BAAHRecommendedConfigOut(OutBase):
    configName: str = Field(default="", description="新建配置名，不含 .json 后缀")


@router.post(
    "/baah/config/create-recommended",
    tags=["BAAH"],
    summary="生成 BAAH 推荐配置",
    response_model=BAAHRecommendedConfigOut,
)
async def create_baah_recommended_config_api(
    data: BAAHRecommendedConfigIn, service: BAAHService
) -> BAAHRecommendedConfigOut:
    try:
        name = await service.create_recommended_config(data.scriptId)
        return BAAHRecommendedConfigOut(configName=name, message="推荐配置已生成")
    except Exception as e:
        logger.opt(exception=True).warning(
            f"create_baah_recommended_config_api失败: {type(e).__name__}: {e}"
        )
        return BAAHRecommendedConfigOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )


@router.get(
    "/baah/config-names",
    tags=["BAAH"],
    summary="获取 BAAH 配置文件名列表",
    response_model=ComboBoxOut,
    status_code=200,
)
async def get_baah_config_names_api(scriptId: str, service: BAAHService) -> ComboBoxOut:
    """返回 BAAH 配置目录下已有的配置文件名（不含 ``.json`` 后缀）。"""

    try:
        data = [
            ComboBoxItem(label=name, value=name)
            for name in service.get_config_names(scriptId)
        ]
        return ComboBoxOut(
            code=200,
            status="success",
            message=f"共 {len(data)} 份 BAAH 配置",
            data=data,
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_baah_config_names_api失败: {type(e).__name__}: {e}"
        )
        return ComboBoxOut(
            code=400
            if isinstance(e, (ValueError, KeyError, TypeError, RuntimeError))
            else 500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=[],
        )
