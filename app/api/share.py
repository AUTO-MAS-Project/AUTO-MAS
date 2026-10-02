#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
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


from typing import Any, Dict

from fastapi import APIRouter, Body

from app.models.schema import (
    ShareAuthStatusOut,
    ShareTemplateItem,
    ShareTemplateListIn,
    ShareTemplateListOut,
)
from app.services import ConfigCenter, ConfigCenterError

router = APIRouter(prefix="/api/share", tags=["配置中心"])


def _build_auth_status(status: Dict[str, Any]) -> ShareAuthStatusOut:
    """把配置中心客户端的状态字典映射成响应模型"""

    return ShareAuthStatusOut(
        message=status.get("message", "操作成功"),
        authStatus=status.get("status", "idle"),
        username=status.get("username", ""),
        displayName=status.get("displayName", ""),
        userCode=status.get("userCode", ""),
        verificationUri=status.get("verificationUri", ""),
        expiresIn=status.get("expiresIn", 0),
        interval=status.get("interval", 5),
    )


@router.post(
    "/templates",
    tags=["Get"],
    summary="获取配置中心已发布的通用脚本配置",
    response_model=ShareTemplateListOut,
    status_code=200,
)
async def list_share_templates(
    query: ShareTemplateListIn = Body(...),
) -> ShareTemplateListOut:

    try:
        items, pagination = await ConfigCenter.list_templates(
            query.page, query.pageSize, query.keyword
        )
    except ConfigCenterError as e:
        return ShareTemplateListOut(code=500, status="error", message=str(e))
    except Exception as e:
        return ShareTemplateListOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )

    return ShareTemplateListOut(
        items=[ShareTemplateItem(**_) for _ in items],
        page=pagination["page"],
        pageSize=pagination["pageSize"],
        total=pagination["total"],
        hasNext=pagination["hasNext"],
    )


@router.post(
    "/auth/status",
    tags=["Get"],
    summary="获取配置中心授权状态",
    response_model=ShareAuthStatusOut,
    status_code=200,
)
async def get_share_auth_status() -> ShareAuthStatusOut:

    return _build_auth_status(ConfigCenter.get_status())


@router.post(
    "/auth/start",
    tags=["Action"],
    summary="发起配置中心浏览器授权",
    response_model=ShareAuthStatusOut,
    status_code=200,
)
async def start_share_auth() -> ShareAuthStatusOut:

    try:
        data = await ConfigCenter.start_authorization()
    except ConfigCenterError as e:
        return ShareAuthStatusOut(
            code=500, status="error", message=str(e), authStatus="idle"
        )
    except Exception as e:
        return ShareAuthStatusOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            authStatus="idle",
        )

    return _build_auth_status({"status": "pending", **data})


@router.post(
    "/auth/poll",
    tags=["Get"],
    summary="轮询配置中心授权结果",
    response_model=ShareAuthStatusOut,
    status_code=200,
)
async def poll_share_auth() -> ShareAuthStatusOut:

    try:
        status = await ConfigCenter.poll_authorization()
    except ConfigCenterError as e:
        return ShareAuthStatusOut(
            code=500, status="error", message=str(e), authStatus="idle"
        )
    except Exception as e:
        return ShareAuthStatusOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            authStatus="idle",
        )

    return _build_auth_status(status)


@router.post(
    "/auth/cancel",
    tags=["Action"],
    summary="取消等待中的配置中心授权",
    response_model=ShareAuthStatusOut,
    status_code=200,
)
async def cancel_share_auth() -> ShareAuthStatusOut:

    await ConfigCenter.cancel_authorization()
    return _build_auth_status(ConfigCenter.get_status())
