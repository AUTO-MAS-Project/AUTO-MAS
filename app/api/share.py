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
    ShareAppearanceCoverIn,
    ShareAppearanceCoverOut,
    ShareAppearanceDescriptionIn,
    ShareAppearanceDescriptionOut,
    ShareAppearanceMineItem,
    ShareAppearanceMineOut,
    ShareAppearanceUploadIn,
    ShareAppearanceUploadItem,
    ShareAppearanceUploadOut,
    ShareAppearanceUploadsOut,
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


@router.post(
    "/appearance/upload",
    tags=["Action"],
    summary="上传外观包到分享站",
    response_model=ShareAppearanceUploadOut,
    status_code=200,
)
async def upload_share_appearance(
    upload: ShareAppearanceUploadIn = Body(...),
) -> ShareAppearanceUploadOut:

    try:
        result = await ConfigCenter.upload_appearance(
            zip_path=upload.zipPath,
            display_name=upload.displayName,
            description=upload.description,
            change_note=upload.changeNote,
            file_id=upload.fileId,
            cover_path=upload.coverPath,
            cover_mode=upload.coverMode,
        )
    except ConfigCenterError as e:
        return ShareAppearanceUploadOut(
            code=e.status_code, status="error", message=str(e), reason=e.reason
        )
    except Exception as e:
        return ShareAppearanceUploadOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )

    return ShareAppearanceUploadOut(**result)


@router.post(
    "/appearance/uploads",
    tags=["Get"],
    summary="获取当前账号的外观上传记录",
    response_model=ShareAppearanceUploadsOut,
    status_code=200,
)
async def list_share_appearance_uploads() -> ShareAppearanceUploadsOut:

    return ShareAppearanceUploadsOut(
        data=[
            ShareAppearanceUploadItem(**_)
            for _ in ConfigCenter.list_appearance_uploads()
        ]
    )


@router.post(
    "/appearance/mine",
    tags=["Get"],
    summary="获取当前账号在分享站上的全部外观",
    response_model=ShareAppearanceMineOut,
    status_code=200,
)
async def list_my_share_appearances() -> ShareAppearanceMineOut:

    try:
        items = await ConfigCenter.list_my_appearances()
    except ConfigCenterError as e:
        return ShareAppearanceMineOut(
            code=e.status_code, status="error", message=str(e)
        )
    except Exception as e:
        return ShareAppearanceMineOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )

    return ShareAppearanceMineOut(data=[ShareAppearanceMineItem(**_) for _ in items])


@router.post(
    "/appearance/cover",
    tags=["Get"],
    summary="获取自己外观某个版本的封面",
    response_model=ShareAppearanceCoverOut,
    status_code=200,
)
async def get_my_share_appearance_cover(
    query: ShareAppearanceCoverIn = Body(...),
) -> ShareAppearanceCoverOut:

    try:
        data_url = await ConfigCenter.get_my_appearance_cover(
            query.fileId, query.versionNo
        )
    except ConfigCenterError as e:
        return ShareAppearanceCoverOut(
            code=e.status_code, status="error", message=str(e)
        )
    except Exception as e:
        return ShareAppearanceCoverOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )

    return ShareAppearanceCoverOut(dataUrl=data_url)


@router.post(
    "/appearance/description",
    tags=["Action"],
    summary="修改自己外观的描述",
    response_model=ShareAppearanceDescriptionOut,
    status_code=200,
)
async def update_my_share_appearance_description(
    update: ShareAppearanceDescriptionIn = Body(...),
) -> ShareAppearanceDescriptionOut:

    try:
        item = await ConfigCenter.update_my_appearance_description(
            update.fileId, update.description
        )
    except ConfigCenterError as e:
        return ShareAppearanceDescriptionOut(
            code=e.status_code, status="error", message=str(e)
        )
    except Exception as e:
        return ShareAppearanceDescriptionOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )

    return ShareAppearanceDescriptionOut(data=ShareAppearanceMineItem(**item))
