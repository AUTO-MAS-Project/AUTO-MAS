#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

from fastapi import APIRouter, Body

from app.core import Config
from app.core.config_edit import ConfigEditError
from app.models.schema import ConfigEditIn, ConfigEditLeaseOut, ConfigEditTokenIn
from app.utils import get_logger

router = APIRouter(prefix="/api/config-edit", tags=["配置编辑"])
logger = get_logger("配置编辑 API")


def _lease_out(
    lease, *, locked: bool = True, include_token: bool = True
) -> ConfigEditLeaseOut:
    return ConfigEditLeaseOut(
        resourceKey=lease.resource_key,
        editLeaseToken=lease.token if include_token else None,
        version=lease.version,
        expiresAt=lease.expires_at,
        locked=locked,
    )


@router.post(
    "/acquire",
    tags=["Action"],
    summary="获取配置编辑租约",
    response_model=ConfigEditLeaseOut,
    status_code=200,
)
async def acquire_config_edit_lease(
    payload: ConfigEditIn = Body(...),
) -> ConfigEditLeaseOut:
    try:
        return _lease_out(Config.acquire_config_edit_lease(payload.resourceKey))
    except ConfigEditError as e:
        return ConfigEditLeaseOut(
            code=e.code,
            status="error",
            message=e.message,
            resourceKey=payload.resourceKey,
            version=Config.config_edit_resource(payload.resourceKey).fingerprint,
            expiresAt=0,
            locked=True,
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"获取配置编辑租约失败: {e}")
        return ConfigEditLeaseOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            resourceKey=payload.resourceKey,
            version="",
            expiresAt=0,
            locked=False,
        )


@router.post(
    "/renew",
    tags=["Action"],
    summary="续租配置编辑租约",
    response_model=ConfigEditLeaseOut,
    status_code=200,
)
async def renew_config_edit_lease(
    payload: ConfigEditTokenIn = Body(...),
) -> ConfigEditLeaseOut:
    try:
        return _lease_out(
            Config.renew_config_edit_lease(
                payload.resourceKey, payload.editLeaseToken
            )
        )
    except ConfigEditError as e:
        return ConfigEditLeaseOut(
            code=e.code,
            status="error",
            message=e.message,
            resourceKey=payload.resourceKey,
            version=Config.config_edit_resource(payload.resourceKey).fingerprint,
            expiresAt=0,
            locked=False,
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"续租配置编辑租约失败: {e}")
        return ConfigEditLeaseOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            resourceKey=payload.resourceKey,
            version="",
            expiresAt=0,
            locked=False,
        )


@router.post(
    "/release",
    tags=["Action"],
    summary="释放配置编辑租约",
    response_model=ConfigEditLeaseOut,
    status_code=200,
)
async def release_config_edit_lease(
    payload: ConfigEditTokenIn = Body(...),
) -> ConfigEditLeaseOut:
    try:
        Config.release_config_edit_lease(payload.resourceKey, payload.editLeaseToken)
        resource = Config.config_edit_resource(payload.resourceKey)
        return ConfigEditLeaseOut(
            resourceKey=payload.resourceKey,
            editLeaseToken=None,
            version=resource.fingerprint,
            expiresAt=0,
            locked=False,
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"释放配置编辑租约失败: {e}")
        return ConfigEditLeaseOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            resourceKey=payload.resourceKey,
            version="",
            expiresAt=0,
            locked=False,
        )


@router.post(
    "/status",
    tags=["Get"],
    summary="查询配置编辑锁状态",
    response_model=ConfigEditLeaseOut,
    status_code=200,
)
async def get_config_edit_status(
    payload: ConfigEditIn = Body(...),
) -> ConfigEditLeaseOut:
    try:
        lease = Config.get_config_edit_status(payload.resourceKey)
        if lease is not None:
            return _lease_out(lease, include_token=False)
        resource = Config.config_edit_resource(payload.resourceKey)
        return ConfigEditLeaseOut(
            resourceKey=payload.resourceKey,
            editLeaseToken=None,
            version=resource.fingerprint,
            expiresAt=0,
            locked=False,
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"查询配置编辑锁失败: {e}")
        return ConfigEditLeaseOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            resourceKey=payload.resourceKey,
            version="",
            expiresAt=0,
            locked=False,
        )
