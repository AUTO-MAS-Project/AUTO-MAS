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


from fastapi import APIRouter, Body
from app.core import Config
from app.models.dto import ToolsGetOut, ToolsConfig, OutBase, ToolsUpdateIn

router = APIRouter(prefix="/api/tools", tags=["工具设置"])


@router.post(
    "/get",
    tags=["Get"],
    summary="查询工具配置",
    response_model=ToolsGetOut,
    status_code=200,
)
async def get_tools() -> ToolsGetOut:
    """查询工具配置"""

    try:
        data = await Config.get_tools()
    except Exception as e:
        return ToolsGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=ToolsConfig(**{}),
        )
    return ToolsGetOut(data=ToolsConfig(**data))


@router.post(
    "/update",
    tags=["Update"],
    summary="更新工具配置",
    response_model=OutBase,
    status_code=200,
)
async def update_tools(script: ToolsUpdateIn = Body(...)) -> OutBase:
    """更新工具配置"""

    try:
        data = script.data.model_dump(exclude_unset=True)
        await Config.update_tools(data)

    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()
