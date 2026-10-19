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


from typing import (
    Any,
    Dict,
    List,
    Literal,
    Optional,
)

from fastapi import APIRouter, Body
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)

from app.models.schema import OutBase
from app.services import ConfigCenter, ConfigCenterError


class ShareTemplateListIn(BaseModel):
    page: int = Field(default=1, ge=1, description="页码, 从 1 开始")
    pageSize: int = Field(default=20, ge=1, le=100, description="每页条数")
    keyword: Optional[str] = Field(default=None, description="搜索关键字")


class ShareTemplateItem(BaseModel):
    projectKey: str = Field(..., description="配置中心项目标识")
    categoryKey: str = Field(..., description="配置中心分类标识")
    configKey: str = Field(..., description="配置中心配置标识")
    displayName: str = Field(..., description="配置名称")
    description: str = Field(default="", description="配置描述")
    ownerUsername: str = Field(default="", description="分享者用户名")
    publishedVersionNo: Optional[int] = Field(
        default=None, description="已发布的版本号"
    )
    publishedAt: str = Field(default="", description="发布时间")
    updatedAt: str = Field(default="", description="更新时间")


class ShareTemplateListOut(OutBase):
    items: List[ShareTemplateItem] = Field(
        default_factory=list, description="配置模板列表"
    )
    page: int = Field(default=1, description="当前页码")
    pageSize: int = Field(default=20, description="每页条数")
    total: int = Field(default=0, description="模板总数")
    hasNext: bool = Field(default=False, description="是否还有下一页")


class ShareAuthStatusOut(OutBase):
    authStatus: Literal["idle", "pending", "authorized", "denied", "expired"] = Field(
        ..., description="配置中心授权状态"
    )
    username: str = Field(default="", description="已授权用户的用户名")
    displayName: str = Field(default="", description="已授权用户的显示名")
    userCode: str = Field(default="", description="待用户在浏览器确认的短授权码")
    verificationUri: str = Field(default="", description="浏览器授权页地址")
    expiresIn: int = Field(default=0, description="剩余有效秒数")
    interval: int = Field(default=5, description="建议的轮询间隔秒数")


class ShareAppearanceCategoryIn(BaseModel):
    categoryKey: Literal["theme", "mascot"] = Field(
        default="theme", description="资源分类: theme 主题, mascot 独立桌宠"
    )


class ShareAppearanceUploadIn(ShareAppearanceCategoryIn):
    zipPath: str = Field(..., description="本地外观 ZIP 路径")
    displayName: str = Field(
        default="", max_length=60, description="外观名称, 只在新建时使用"
    )
    description: str = Field(default="", max_length=2000, description="外观描述")
    changeNote: str = Field(default="", max_length=500, description="变更说明")
    fileId: Optional[int] = Field(
        default=None, description="已上传文件的 ID, 非空表示给该文件发新版本"
    )
    coverPath: Optional[str] = Field(
        default=None,
        description="封面图片路径, coverMode 为 custom 时使用",
    )
    coverMode: Optional[Literal["package", "custom", "inherit"]] = Field(
        default=None,
        description="封面来源: package 用外观包的 preview, custom 用 coverPath, inherit 沿用分享站上的封面 (只能用于新版本); 为空时有 coverPath 按 custom, 否则按 package",
    )

    @field_validator("displayName", mode="before")
    @classmethod
    def strip_display_name(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def check_target(self) -> "ShareAppearanceUploadIn":
        if self.fileId is None and not self.displayName:
            raise ValueError("新建外观时名称不能为空")
        if self.coverMode == "inherit" and self.fileId is None:
            raise ValueError("只有发新版本时才能沿用分享站上的封面")
        if self.coverMode == "custom" and not self.coverPath:
            raise ValueError("请选择封面图片")
        return self


class ShareAppearanceUploadOut(OutBase):
    fileId: int = Field(default=0, description="分享站文件 ID")
    fileKey: str = Field(default="", description="分享站文件标识")
    versionNo: int = Field(default=0, description="本次上传的版本号")
    reviewStatus: Literal["pending", "approved"] = Field(
        default="pending", description="审核状态, 管理员上传自动通过"
    )
    isNewFile: bool = Field(default=False, description="是否新建了文件")
    appearanceId: str = Field(default="", description="外观 ID")
    reason: Optional[
        Literal["pendingLimit", "conflict", "tooLarge", "categoryMismatch"]
    ] = Field(
        default=None,
        description="上传拒绝的类别: pendingLimit 待审核数超限, conflict 名称被占用或内容未变, tooLarge 超过体积上限, categoryMismatch 更新目标与分类不符",
    )


class ShareAppearanceUploadItem(BaseModel):
    appearanceId: str = Field(..., description="外观 ID")
    fileId: int = Field(..., description="分享站文件 ID")
    fileKey: str = Field(default="", description="分享站文件标识")
    displayName: str = Field(default="", description="外观名称")
    updatedAt: str = Field(default="", description="最近一次上传时间")


class ShareAppearanceUploadsOut(OutBase):
    data: List[ShareAppearanceUploadItem] = Field(
        default_factory=list, description="当前登录账号的外观上传记录"
    )


class ShareAppearanceMineItem(BaseModel):
    fileId: int = Field(..., description="分享站文件 ID")
    fileKey: str = Field(default="", description="分享站文件标识")
    displayName: str = Field(default="", description="外观名称")
    description: str = Field(default="", description="外观描述")
    status: str = Field(default="", description="文件状态")
    publishedVersionNo: Optional[int] = Field(
        default=None, description="已发布的版本号, 没有已发布版本时为空"
    )
    latestVersionNo: int = Field(default=0, description="最新版本号")
    latestReviewStatus: Optional[Literal["pending", "approved", "rejected"]] = Field(
        default=None, description="最新版本的审核状态"
    )
    latestReviewComment: str = Field(
        default="", description="最新版本的审核意见, 没有则为空"
    )
    latestHasCover: bool = Field(default=False, description="最新版本是否带封面")
    updatedAt: str = Field(default="", description="最近更新时间")


class ShareAppearanceMineOut(OutBase):
    data: List[ShareAppearanceMineItem] = Field(
        default_factory=list, description="当前账号在分享站上的全部外观"
    )


class ShareAppearanceCoverIn(BaseModel):
    fileId: int = Field(..., description="分享站文件 ID")
    versionNo: Optional[int] = Field(
        default=None,
        ge=1,
        description="版本号, 为空表示最新版本; inheritable 为真时忽略",
    )
    inheritable: bool = Field(
        default=False,
        description="为真时取发新版本不带封面时分享站会沿用的那张: 最近一个未被驳回且带封面的版本",
    )


class ShareAppearanceCoverOut(OutBase):
    dataUrl: str = Field(default="", description="封面图片的 data URL")
    versionNo: Optional[int] = Field(
        default=None, description="封面所在的版本号, 取最新版本时为空"
    )


class ShareAppearanceDescriptionIn(BaseModel):
    fileId: int = Field(..., description="分享站文件 ID")
    description: str = Field(..., max_length=2000, description="新的外观描述")


class ShareAppearanceDescriptionOut(OutBase):
    data: Optional[ShareAppearanceMineItem] = Field(
        default=None, description="更新后的外观"
    )


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
            category_key=upload.categoryKey,
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
async def list_share_appearance_uploads(
    query: ShareAppearanceCategoryIn = Body(default=ShareAppearanceCategoryIn()),
) -> ShareAppearanceUploadsOut:

    return ShareAppearanceUploadsOut(
        data=[
            ShareAppearanceUploadItem(**_)
            for _ in ConfigCenter.list_appearance_uploads(
                category_key=query.categoryKey
            )
        ]
    )


@router.post(
    "/appearance/mine",
    tags=["Get"],
    summary="获取当前账号在分享站上的全部外观",
    response_model=ShareAppearanceMineOut,
    status_code=200,
)
async def list_my_share_appearances(
    query: ShareAppearanceCategoryIn = Body(default=ShareAppearanceCategoryIn()),
) -> ShareAppearanceMineOut:

    try:
        items = await ConfigCenter.list_my_appearances(category_key=query.categoryKey)
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
        cover = await ConfigCenter.get_my_appearance_cover(
            query.fileId, query.versionNo, inheritable=query.inheritable
        )
    except ConfigCenterError as e:
        return ShareAppearanceCoverOut(
            code=e.status_code, status="error", message=str(e)
        )
    except Exception as e:
        return ShareAppearanceCoverOut(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )

    return ShareAppearanceCoverOut(**cover)


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
