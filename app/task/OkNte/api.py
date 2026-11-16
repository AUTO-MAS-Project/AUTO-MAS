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
"""托管管理：OK-NTE 路由与端点专用模型。"""

from typing import Any

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.models.schema import OutBase
from app.utils import get_logger

router = APIRouter()
logger = get_logger("托管管理 API")


class OkNtePlanRoutineItem(BaseModel):
    id: str
    label: str
    exclusiveGroup: str | None = None


class OkNtePlanField(BaseModel):
    name: str
    label: str | None = None
    type: str
    value: Any = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list[str] | None = None
    children: list["OkNtePlanField"] | None = None
    itemDefinitions: list[OkNtePlanRoutineItem] | None = None


class OkNtePlanFile(BaseModel):
    filename: str
    displayName: str
    taskIndex: int | None
    fields: list[OkNtePlanField]
    currentData: dict[str, Any]
    parseError: bool = False
    overrides: dict[str, Any]


class OkNtePlanConfigsOut(OutBase):
    data: list[OkNtePlanFile] = Field(default_factory=list)


@router.post(
    "/oknte/configs/list",
    tags=["OKNTE"],
    summary="获取 OK-NTE 配置文件列表及 schema",
    status_code=200,
)
async def get_oknte_configs_list(script_id: str, user_id: str):
    """
    获取 OK-NTE 配置文件列表及 schema 定义。
    读写用户覆写常规配置目录，首次从已有来源初始化，不修改来源文件。

    Args:
        script_id: OK-NTE 托管 ID
        user_id: 账号 ID

    Returns:
        dict: 包含配置文件列表和 schema 的响应
    """
    try:
        from app.task.OkNte import api_service as oknte_api

        result, option_labels, mas_config_dir = oknte_api.list_configs(
            script_id, user_id
        )

        return {
            "code": 200,
            "status": "success",
            "message": f"共 {len(result)} 个配置文件",
            "data": result,
            "optionLabels": option_labels,
            "configPath": str(mas_config_dir) if mas_config_dir else None,
        }
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_oknte_configs_list失败: {type(e).__name__}: {e}"
        )
        return {
            "code": 500,
            "status": "error",
            "message": f"{type(e).__name__}: {str(e)}",
            "data": [],
        }


@router.post(
    "/oknte/configs/batch-update",
    tags=["OKNTE"],
    summary="批量更新 OK-NTE 配置文件",
    status_code=200,
)
async def batch_update_oknte_configs(
    script_id: str = Body(...),
    user_id: str = Body(...),
    configs: dict = Body(...),
):
    """
    批量更新 OK-NTE 配置文件

    Args:
        script_id: OK-NTE 托管 ID
        user_id: 账号 ID
        configs: { filename: data } 格式的配置数据

    Returns:
        dict: 操作结果
    """
    try:
        from app.task.OkNte import api_service as oknte_api

        updated_files = oknte_api.save_configs(script_id, user_id, configs=configs)

        return {
            "code": 200,
            "status": "success",
            "message": f"已更新 {len(updated_files)} 个配置文件",
            "data": updated_files,
        }
    except Exception as e:
        logger.opt(exception=True).warning(
            f"batch_update_oknte_configs失败: {type(e).__name__}: {e}"
        )
        return {
            "code": 500,
            "status": "error",
            "message": f"{type(e).__name__}: {str(e)}",
        }


@router.post("/oknte/plan/configs", tags=["OKNTE"], response_model=OkNtePlanConfigsOut)
async def get_oknte_plan_configs(plan_id: str, day: str):
    from .api_service import plan_configs

    try:
        return OkNtePlanConfigsOut(data=plan_configs(plan_id, day))
    except (ValueError, KeyError, OSError) as e:
        logger.opt(exception=True).warning(f"读取 OK-NTE 计划配置失败: {e}")
        return OkNtePlanConfigsOut(code=400, status="error", message=str(e))


@router.post("/oknte/plan/save", tags=["OKNTE"], response_model=OutBase)
async def save_oknte_plan_configs(
    plan_id: str = Body(...),
    day: str = Body(...),
    configs: dict = Body(...),
    replace: bool = Body(False),
):
    from app.core import Config

    from .api_service import plan_configs

    try:
        group, key = plan_configs(plan_id, day, configs, replace=replace)
        await Config.update_plan(plan_id, {group: {"Key": key}})
        return OutBase()
    except (ValueError, KeyError, OSError) as e:
        logger.opt(exception=True).warning(f"保存 OK-NTE 计划配置失败: {e}")
        return OutBase(code=400, status="error", message=str(e))
