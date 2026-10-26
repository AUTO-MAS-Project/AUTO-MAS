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
"""脚本管理：HSR 路由与端点专用模型。"""

from typing import (
    Literal,
    Optional,
)

from fastapi import APIRouter
from pydantic import (
    BaseModel,
    Field,
)

from app.models.schema import (
    HSRCapabilitiesData,
    HSRCloudLoginData,
    HSRManagedConfigData,
    HSRSRAProfilesData,
    HSRStageOptionsData,
    HSRUpdateData,
    OutBase,
)
from app.utils import get_logger


class HSRStageOptionsOut(OutBase):
    data: Optional[HSRStageOptionsData] = Field(
        default=None, description="HSR 体力副本动态选项"
    )


class HSRCapabilitiesOut(OutBase):
    data: Optional[HSRCapabilitiesData] = Field(default=None, description="HSR 能力")


class HSRUpdateIn(BaseModel):
    scriptId: str = Field(..., description="HSR 脚本配置 ID")
    engine: Literal["M7A", "SRA"] = Field(..., description="要操作的外部脚本引擎")
    action: Literal["check", "apply"] = Field(
        default="check", description="check 只查版本；apply 查完就装"
    )


class HSRUpdateOut(OutBase):
    data: Optional[HSRUpdateData] = Field(default=None, description="更新结果")


class HSRCloudLoginIn(BaseModel):
    scriptId: str = Field(..., description="HSR 脚本配置 ID")
    userId: str = Field(..., description="要登录云·星穹铁道的用户 ID")


class HSRCloudLoginOut(OutBase):
    data: Optional[HSRCloudLoginData] = Field(default=None, description="登录结果")


class HSRManagedConfigOut(OutBase):
    data: Optional[HSRManagedConfigData] = Field(default=None, description="托管配置")


class HSRSRAProfilesOut(OutBase):
    data: Optional[HSRSRAProfilesData] = Field(
        default=None, description="SRA 配置档案列表"
    )


router = APIRouter()
logger = get_logger("脚本管理 API")


@router.get(
    "/hsr/stage-options",
    tags=["HSR"],
    summary="获取 HSR 体力副本动态选项",
    response_model=HSRStageOptionsOut,
    status_code=200,
)
async def get_hsr_stage_options_api(
    scriptId: str | None = None,
    engine: Literal["M7A", "SRA"] = "M7A",
    userId: str | None = None,
    slot: Literal["main", "eow"] = "main",
) -> HSRStageOptionsOut:
    """返回 M7A/SRA 原生副本字段。

    ``userId`` 仅用于校验用户归属；``slot`` 是兼容参数，动态选项当前
    按引擎统一返回，不按 slot 生成不同结果。
    """

    from app.task.HSR import api_service as hsr_api

    reply = await hsr_api.get_stage_options(scriptId, engine, userId)
    return HSRStageOptionsOut(**reply.out_fields())


@router.get(
    "/hsr/capabilities",
    tags=["HSR"],
    summary="获取内置 HSR 能力快照",
    response_model=HSRCapabilitiesOut,
    status_code=200,
)
async def get_hsr_capabilities_api(scriptId: str | None = None) -> HSRCapabilitiesOut:
    """返回内置 HSR 的能力快照，不暴露原生编辑器会话。"""

    from app.task.HSR import api_service as hsr_api

    reply = await hsr_api.get_capabilities(scriptId)
    return HSRCapabilitiesOut(**reply.out_fields())


@router.post(
    "/hsr/update",
    tags=["HSR"],
    summary="检查或执行 HSR 外部脚本更新",
    response_model=HSRUpdateOut,
    status_code=200,
)
async def post_hsr_update_api(data: HSRUpdateIn) -> HSRUpdateOut:
    """手动检查或安装 M7A / SRA 的更新。

    自动更新只在任务正常跑完后触发（``Update.AutoUpdateMode = AfterRun``），
    这个接口是唯一不必等一轮任务就能更新的入口。
    """

    from app.task.HSR import api_service as hsr_api

    reply = await hsr_api.update_engine(data.scriptId, data.engine, data.action)
    return HSRUpdateOut(**reply.out_fields())


@router.post(
    "/hsr/cloud-login",
    tags=["HSR"],
    summary="为 HSR 用户登录云·星穹铁道",
    response_model=HSRCloudLoginOut,
    status_code=200,
)
async def post_hsr_cloud_login_api(data: HSRCloudLoginIn) -> HSRCloudLoginOut:
    """起该用户的云浏览器并用三月七的 ``game`` 任务等用户在窗口里登录。

    阻塞到三月七退出为止（最长为登录等待 + 最长排队 + 余量），与正在运行的
    任务互斥：脚本运行中或三月七目录被占用时返回 409。成功后写
    ``Cloud.LastLogin``。
    """

    from app.task.HSR import api_service as hsr_api

    reply = await hsr_api.cloud_login(data.scriptId, data.userId)
    return HSRCloudLoginOut(**reply.out_fields())


@router.get(
    "/hsr/managed-config",
    tags=["HSR"],
    summary="获取 HSR 托管配置字段",
    response_model=HSRManagedConfigOut,
    status_code=200,
)
async def get_hsr_managed_config_api(
    scriptId: str | None = None, userId: str | None = None
) -> HSRManagedConfigOut:
    """返回原生动态托管字段。

    传了用户 ID 时先做归属校验，再按该用户的配置来源决定表单读哪份计划：
    「脚本」读脚本共享计划，「用户」读该用户自己的计划；不传用户 ID 时读
    脚本共享计划。响应的 ``plan_owner`` 指明保存目标。
    """

    from app.task.HSR import api_service as hsr_api

    reply = await hsr_api.get_managed_config(scriptId, userId)
    return HSRManagedConfigOut(**reply.out_fields())


@router.get(
    "/hsr/sra-profiles",
    tags=["HSR"],
    summary="获取 HSR 可选的 SRA 配置档案",
    response_model=HSRSRAProfilesOut,
    status_code=200,
)
async def get_hsr_sra_profiles_api(scriptId: str | None = None) -> HSRSRAProfilesOut:
    """列出 ``%APPDATA%/SRA/configs`` 下的配置档案，并标出脚本当前生效的那份。"""

    from app.task.HSR import api_service as hsr_api

    reply = await hsr_api.get_sra_profiles(scriptId)
    return HSRSRAProfilesOut(**reply.out_fields())
