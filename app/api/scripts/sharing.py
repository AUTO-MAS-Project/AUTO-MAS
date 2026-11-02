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

"""配置中心导入与分享路由与端点专用模型。"""

from typing import (
    List,
    Optional,
)

from fastapi import APIRouter, Body
from pydantic import (
    BaseModel,
    Field,
)

from app.models.schema import (
    OutBase,
)
from app.services import ConfigCenterError
from app.task.general.sharing import general_share_service
from app.utils import get_logger


class ScriptShareInspectIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")
    config_name: str = Field(..., min_length=1, max_length=64, description="配置名称")


class ScriptTemplateImportIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")
    configKey: str = Field(..., description="配置中心配置标识")
    versionNo: Optional[int] = Field(
        default=None, ge=1, description="版本号, 为空表示已发布的最新版本"
    )


class ScriptUploadIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")
    config_name: str = Field(..., min_length=1, max_length=64, description="配置名称")
    description: str = Field(..., min_length=1, max_length=500, description="描述")
    acknowledged: bool = Field(
        default=False, description="是否已确认分享前检查出的隐私风险项"
    )


class ShareRiskItem(BaseModel):
    field: str = Field(..., description="存在风险的配置项")
    reason: str = Field(..., description="风险说明")


class ShareInspectOut(OutBase):
    risks: List[ShareRiskItem] = Field(
        default_factory=list, description="分享前检查出的隐私风险项"
    )


router = APIRouter()
logger = get_logger("脚本管理 API")


@router.post(
    "/import/web",
    tags=["Update"],
    summary="从配置中心导入脚本配置",
    response_model=OutBase,
    status_code=200,
)
async def import_script_from_web(script: ScriptTemplateImportIn = Body(...)) -> OutBase:

    try:
        await general_share_service.import_script_from_share(
            script.scriptId, config_key=script.configKey, version_no=script.versionNo
        )
    except ConfigCenterError as e:
        return OutBase(code=500, status="error", message=str(e))
    except Exception as e:
        logger.opt(exception=True).warning(
            f"import_script_from_web失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/share/inspect",
    tags=["Get"],
    summary="分享前检查脚本配置中的隐私风险",
    response_model=ShareInspectOut,
    status_code=200,
)
async def inspect_script_share(
    script: ScriptShareInspectIn = Body(...),
) -> ShareInspectOut:

    try:
        _, risks = general_share_service.build_share_config(
            script.scriptId, config_name=script.config_name
        )
    except Exception as e:
        return ShareInspectOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return ShareInspectOut(risks=[ShareRiskItem(**_) for _ in risks])


@router.post(
    "/Upload/web",
    tags=["Action"],
    summary="分享脚本配置到配置中心",
    response_model=OutBase,
    status_code=200,
)
async def upload_script_to_web(script: ScriptUploadIn = Body(...)) -> OutBase:

    try:
        await general_share_service.upload_script_to_share(
            script.scriptId,
            config_name=script.config_name,
            description=script.description,
            acknowledged=script.acknowledged,
        )
    except ConfigCenterError as e:
        return OutBase(code=500, status="error", message=str(e))
    except Exception as e:
        logger.opt(exception=True).warning(
            f"upload_script_to_web失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()
