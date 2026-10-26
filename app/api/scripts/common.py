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
"""脚本管理：通用脚本与用户管理 路由与端点专用模型。"""

import uuid
from typing import (
    Dict,
    List,
    Literal,
    Optional,
    Union,
)

from fastapi import APIRouter, Body
from pydantic import (
    BaseModel,
    Field,
    model_validator,
)

import app.models.config as _config_models
from app.config.wire import ConfigInput, ConfigPayload, config_contract
from app.core import Config
from app.core.game_calendar import SCRIPT_CALENDAR_GAMES
from app.models.schema import (
    OutBase,
    ScriptDeleteIn,
    UserDeleteIn,
    UserInBase,
    WebhookDeleteIn,
    WebhookGetIn,
    WebhookInBase,
    WebhookIndexItem,
)
from app.models.schema import (
    WebhookCreateOut as SharedWebhookCreateOut,
)
from app.models.schema import (
    WebhookGetOut as SharedWebhookGetOut,
)
from app.models.schema import (
    WebhookUpdateIn as SharedWebhookUpdateIn,
)
from app.services import ConfigCenterError
from app.task.MAA.tools.update_credentials import query_takeover_cdk
from app.utils import get_logger

BAAHConfig = ConfigPayload[_config_models.BAAHConfig]

BAAHConfigInput = ConfigInput[_config_models.BAAHConfig]

BAAHUserConfig = ConfigPayload[_config_models.BAAHUserConfig]

BAAHUserConfigInput = ConfigInput[_config_models.BAAHUserConfig]

BetterGIConfig = ConfigPayload[_config_models.BetterGIConfig]

BetterGIConfigInput = ConfigInput[_config_models.BetterGIConfig]

BetterGIUserConfig = ConfigPayload[_config_models.BetterGIUserConfig]

BetterGIUserConfigInput = ConfigInput[_config_models.BetterGIUserConfig]

GeneralConfig = ConfigPayload[_config_models.GeneralConfig]

GeneralConfigInput = ConfigInput[_config_models.GeneralConfig]

GeneralUserConfig = ConfigPayload[_config_models.GeneralUserConfig]

GeneralUserConfigInput = ConfigInput[_config_models.GeneralUserConfig]

HSRConfig = ConfigPayload[_config_models.HSRConfig]

HSRConfigInput = ConfigInput[_config_models.HSRConfig]

HSRUserConfig = ConfigPayload[_config_models.HSRUserConfig]

HSRUserConfigInput = ConfigInput[_config_models.HSRUserConfig]

M9AConfig = ConfigPayload[_config_models.M9AConfig]

M9AConfigInput = ConfigInput[_config_models.M9AConfig]

M9AUserConfig = ConfigPayload[_config_models.M9AUserConfig]

M9AUserConfigInput = ConfigInput[_config_models.M9AUserConfig]

MSSConfig = ConfigPayload[_config_models.MSSConfig]

MSSConfigInput = ConfigInput[_config_models.MSSConfig]

MSSUserConfig = ConfigPayload[_config_models.MSSUserConfig]

MSSUserConfigInput = ConfigInput[_config_models.MSSUserConfig]

MaaConfig = ConfigPayload[_config_models.MaaConfig]

MaaConfigInput = ConfigInput[_config_models.MaaConfig]

MaaEndConfig = ConfigPayload[_config_models.MaaEndConfig]

MaaEndConfigInput = ConfigInput[_config_models.MaaEndConfig]

MaaEndUserConfig = ConfigPayload[_config_models.MaaEndUserConfig]

MaaEndUserConfigInput = ConfigInput[_config_models.MaaEndUserConfig]

MaaFWConfig = ConfigPayload[_config_models.MaaFWConfig]

MaaFWConfigInput = ConfigInput[_config_models.MaaFWConfig]

MaaFWUserConfig = ConfigPayload[_config_models.MaaFWUserConfig]

MaaFWUserConfigInput = ConfigInput[_config_models.MaaFWUserConfig]

MaaUserConfig = ConfigPayload[_config_models.MaaUserConfig]

MaaUserConfigInput = ConfigInput[_config_models.MaaUserConfig]

OkNteConfig = ConfigPayload[_config_models.OkNteConfig]

OkNteConfigInput = ConfigInput[_config_models.OkNteConfig]

OkNteUserConfig = ConfigPayload[_config_models.OkNteUserConfig]

OkNteUserConfigInput = ConfigInput[_config_models.OkNteUserConfig]

OkwwConfig = ConfigPayload[_config_models.OkwwConfig]

OkwwConfigInput = ConfigInput[_config_models.OkwwConfig]

OkwwUserConfig = ConfigPayload[_config_models.OkwwUserConfig]

OkwwUserConfigInput = ConfigInput[_config_models.OkwwUserConfig]

SrcConfig = ConfigPayload[_config_models.SrcConfig]

SrcConfigInput = ConfigInput[_config_models.SrcConfig]

SrcUserConfig = ConfigPayload[_config_models.SrcUserConfig]

SrcUserConfigInput = ConfigInput[_config_models.SrcUserConfig]

Webhook = ConfigPayload[_config_models.Webhook]

WebhookInput = ConfigInput[_config_models.Webhook]

WebhookGetOut = SharedWebhookGetOut[Webhook]

WebhookCreateOut = SharedWebhookCreateOut[Webhook]

WebhookUpdateIn = SharedWebhookUpdateIn[WebhookInput]

WhimboxConfig = ConfigPayload[_config_models.WhimboxConfig]

WhimboxConfigInput = ConfigInput[_config_models.WhimboxConfig]

WhimboxUserConfig = ConfigPayload[_config_models.WhimboxUserConfig]

WhimboxUserConfigInput = ConfigInput[_config_models.WhimboxUserConfig]

ZzzOdConfig = ConfigPayload[_config_models.ZzzOdConfig]

ZzzOdConfigInput = ConfigInput[_config_models.ZzzOdConfig]

ZzzOdUserConfig = ConfigPayload[_config_models.ZzzOdUserConfig]

ZzzOdUserConfigInput = ConfigInput[_config_models.ZzzOdUserConfig]


class ScriptIndexItem(BaseModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal[
        "MaaConfig",
        "GeneralConfig",
        "OkwwConfig",
        "OkNteConfig",
        "SrcConfig",
        "MaaEndConfig",
        "M9AConfig",
        "MaaFWConfig",
        "HSRConfig",
        "BetterGIConfig",
        "ZzzOdConfig",
        "BAAHConfig",
        "WhimboxConfig",
        "MSSConfig",
    ] = Field(..., description="配置类型")

    activityGame: str | None = Field(
        default=None, description="对应的游戏活动标识，无游戏归属时为空"
    )


class UserIndexItem(BaseModel):
    uid: str = Field(..., description="唯一标识符")
    type: Literal[
        "MaaUserConfig",
        "GeneralUserConfig",
        "OkwwUserConfig",
        "OkNteUserConfig",
        "SrcUserConfig",
        "MaaEndUserConfig",
        "M9AUserConfig",
        "MaaFWUserConfig",
        "HSRUserConfig",
        "BetterGIUserConfig",
        "ZzzOdUserConfig",
        "BAAHUserConfig",
        "WhimboxUserConfig",
        "MSSUserConfig",
    ] = Field(..., description="配置类型")


class ScriptMirrorCdkIn(BaseModel):
    type: Literal["MAA"] = Field(..., description="脚本类型，决定凭据回退规则")
    cdk: str = Field(
        default="", repr=False, description="待校验的 CDK；留空回退全局 CDK"
    )


class ScriptMirrorCdkData(BaseModel):
    status: str
    expiredTime: int | None = Field(default=None, description="到期时间（unix 秒）")
    usingGlobalCdk: bool = Field(..., description="是否按专用 CDK 留空规则使用全局 CDK")


class ScriptMirrorCdkOut(OutBase):
    data: ScriptMirrorCdkData


class ScriptCreateIn(BaseModel):
    type: Literal[
        "MAA",
        "SRC",
        "General",
        "Okww",
        "OkNte",
        "MaaEnd",
        "M9A",
        "MaaFW",
        "HSR",
        "BetterGI",
        "ZzzOd",
        "BAAH",
        "Whimbox",
        "MSS",
    ] = Field(
        ...,
        description="脚本类型: MAA脚本, 通用脚本, OK-WW脚本, OK-NTE脚本, SRC脚本, MaaEnd脚本, M9A脚本, MaaFW脚本, HSR脚本, BetterGI脚本, ZZZ-OD脚本, BAAH脚本, 奇想盒脚本, MSS脚本",
    )
    scriptId: str | None = Field(
        default=None, description="直接从该脚本ID复制创建, 仅在复制创建时使用"
    )


class ScriptCreateOut(OutBase):
    scriptId: str = Field(..., description="新创建的脚本ID")
    data: Union[
        MaaConfig,
        SrcConfig,
        GeneralConfig,
        OkwwConfig,
        OkNteConfig,
        MaaEndConfig,
        M9AConfig,
        MaaFWConfig,
        HSRConfig,
        BetterGIConfig,
        ZzzOdConfig,
        BAAHConfig,
        WhimboxConfig,
        MSSConfig,
    ] = Field(..., description="脚本配置数据")


class ScriptGetIn(BaseModel):
    scriptId: Optional[str] = Field(
        default=None, description="脚本ID, 未携带时表示获取所有脚本数据"
    )


class ScriptGetOut(OutBase):
    index: List[ScriptIndexItem] = Field(..., description="脚本索引列表")
    data: Dict[
        str,
        Union[
            MaaConfig,
            SrcConfig,
            GeneralConfig,
            OkwwConfig,
            OkNteConfig,
            MaaEndConfig,
            M9AConfig,
            MaaFWConfig,
            HSRConfig,
            BetterGIConfig,
            ZzzOdConfig,
            BAAHConfig,
            WhimboxConfig,
            MSSConfig,
        ],
    ] = Field(..., description="脚本数据字典, key来自于index列表的uid")


class ScriptUpdateIn(BaseModel):
    scriptId: str = Field(..., description="脚本ID")
    data: Union[
        MaaConfigInput,
        SrcConfigInput,
        GeneralConfigInput,
        OkwwConfigInput,
        OkNteConfigInput,
        MaaEndConfigInput,
        M9AConfigInput,
        MaaFWConfigInput,
        HSRConfigInput,
        BetterGIConfigInput,
        ZzzOdConfigInput,
        BAAHConfigInput,
        WhimboxConfigInput,
        MSSConfigInput,
    ] = Field(..., description="脚本更新数据")

    @model_validator(mode="before")
    @classmethod
    def select_config_contract(cls, value):
        """按目标配置选输入类型，避免联合类型丢弃其他专项的同组字段。"""
        if not isinstance(value, dict) or not isinstance(value.get("data"), dict):
            return value
        try:
            target = Config.ScriptConfig[value["scriptId"]]
        except (KeyError, ValueError, TypeError, AttributeError):
            return value
        payload = config_contract(type(target), mode="input").model_validate(
            value["data"]
        )
        return {**value, "data": payload}


class ScriptReorderIn(BaseModel):
    indexList: List[str] = Field(..., description="脚本ID列表, 按新顺序排列")


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


class ScriptConfigImportIn(UserInBase):
    userId: Optional[str] = Field(
        default=None, description="用户ID, 未携带时导入到脚本级配置文件"
    )


class UserConfigDirIn(UserInBase):
    userId: str = Field(..., description="用户ID")


class UserConfigDirOut(OutBase):
    path: Optional[str] = Field(default=None, description="用户配置目录绝对路径")


class UserGetIn(UserInBase):
    userId: Optional[str] = Field(
        default=None, description="用户ID, 未携带时表示获取所有用户数据"
    )


class UserGetOut(OutBase):
    index: List[UserIndexItem] = Field(..., description="用户索引列表")
    data: Dict[
        str,
        Union[
            MaaUserConfig,
            SrcUserConfig,
            GeneralUserConfig,
            OkwwUserConfig,
            OkNteUserConfig,
            MaaEndUserConfig,
            M9AUserConfig,
            MaaFWUserConfig,
            HSRUserConfig,
            BetterGIUserConfig,
            ZzzOdUserConfig,
            BAAHUserConfig,
            WhimboxUserConfig,
            MSSUserConfig,
        ],
    ] = Field(..., description="用户数据字典, key来自于index列表的uid")


class UserCreateOut(OutBase):
    userId: str = Field(..., description="新创建的用户ID")
    data: Union[
        MaaUserConfig,
        SrcUserConfig,
        GeneralUserConfig,
        OkwwUserConfig,
        OkNteUserConfig,
        MaaEndUserConfig,
        M9AUserConfig,
        MaaFWUserConfig,
        HSRUserConfig,
        BetterGIUserConfig,
        ZzzOdUserConfig,
        BAAHUserConfig,
        WhimboxUserConfig,
        MSSUserConfig,
    ] = Field(..., description="用户配置数据")


class UserUpdateIn(UserInBase):
    userId: str = Field(..., description="用户ID")
    data: Union[
        MaaUserConfigInput,
        SrcUserConfigInput,
        GeneralUserConfigInput,
        OkwwUserConfigInput,
        OkNteUserConfigInput,
        MaaEndUserConfigInput,
        M9AUserConfigInput,
        MaaFWUserConfigInput,
        HSRUserConfigInput,
        BetterGIUserConfigInput,
        ZzzOdUserConfigInput,
        BAAHUserConfigInput,
        WhimboxUserConfigInput,
        MSSUserConfigInput,
    ] = Field(..., description="用户更新数据")

    @model_validator(mode="before")
    @classmethod
    def select_config_contract(cls, value):
        """按目标配置选输入类型，避免联合类型丢弃其他专项的同组字段。"""
        if not isinstance(value, dict) or not isinstance(value.get("data"), dict):
            return value
        try:
            target = Config.ScriptConfig[value["scriptId"]].UserData[value["userId"]]
        except (KeyError, ValueError, TypeError, AttributeError):
            return value
        payload = config_contract(type(target), mode="input").model_validate(
            value["data"]
        )
        return {**value, "data": payload}


class UserReorderIn(UserInBase):
    indexList: List[str] = Field(..., description="用户ID列表, 按新顺序排列")


SCRIPT_BOOK = {
    "MaaConfig": MaaConfig,
    "SrcConfig": SrcConfig,
    "MaaEndConfig": MaaEndConfig,
    "M9AConfig": M9AConfig,
    "MaaFWConfig": MaaFWConfig,
    "GeneralConfig": GeneralConfig,
    "OkwwConfig": OkwwConfig,
    "OkNteConfig": OkNteConfig,
    "HSRConfig": HSRConfig,
    "BetterGIConfig": BetterGIConfig,
    "ZzzOdConfig": ZzzOdConfig,
    "BAAHConfig": BAAHConfig,
    "WhimboxConfig": WhimboxConfig,
    "MSSConfig": MSSConfig,
}

USER_BOOK = {
    "MaaConfig": MaaUserConfig,
    "SrcConfig": SrcUserConfig,
    "MaaEndConfig": MaaEndUserConfig,
    "M9AConfig": M9AUserConfig,
    "MaaFWConfig": MaaFWUserConfig,
    "GeneralConfig": GeneralUserConfig,
    "OkwwConfig": OkwwUserConfig,
    "OkNteConfig": OkNteUserConfig,
    "HSRConfig": HSRUserConfig,
    "BetterGIConfig": BetterGIUserConfig,
    "ZzzOdConfig": ZzzOdUserConfig,
    "BAAHConfig": BAAHUserConfig,
    "WhimboxConfig": WhimboxUserConfig,
    "MSSConfig": MSSUserConfig,
}

router = APIRouter()

logger = get_logger("脚本管理 API")


@router.post(
    "/add",
    tags=["Add"],
    summary="添加脚本",
    response_model=ScriptCreateOut,
    status_code=200,
)
async def add_script(script: ScriptCreateIn = Body(...)) -> ScriptCreateOut:

    try:
        uid, config = await Config.add_script(script.type, script.scriptId)
        data = SCRIPT_BOOK[type(config).__name__](
            **config.model_dump(context={"audience": "api"})
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"add_script失败: {type(e).__name__}: {e}")
        return ScriptCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            scriptId="",
            data=GeneralConfig(**{}),
        )
    return ScriptCreateOut(scriptId=str(uid), data=data)


@router.post(
    "/get",
    tags=["Get"],
    summary="查询脚本配置信息",
    response_model=ScriptGetOut,
    status_code=200,
)
async def get_script(script: ScriptGetIn = Body(...)) -> ScriptGetOut:

    try:
        index, data = await Config.get_script(script.scriptId)
        activity_games = {
            config.__name__: game for config, game in SCRIPT_CALENDAR_GAMES.items()
        }
        index = [
            ScriptIndexItem(**item, activityGame=activity_games.get(item["type"]))
            for item in index
        ]
        data = {
            uid: SCRIPT_BOOK[next((_.type for _ in index if _.uid == uid), "General")](
                **cfg
            )
            for uid, cfg in data.items()
        }
    except Exception as e:
        logger.opt(exception=True).warning(f"get_script失败: {type(e).__name__}: {e}")
        return ScriptGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            index=[],
            data={},
        )
    return ScriptGetOut(index=index, data=data)


@router.post(
    "/update",
    tags=["Update"],
    summary="更新脚本配置信息",
    response_model=OutBase,
    status_code=200,
)
async def update_script(script: ScriptUpdateIn = Body(...)) -> OutBase:

    try:
        data = script.data.model_dump(exclude_unset=True)
        # 魔改 AVD 目前只支持 MaaFW 和 MAA：别的脚本选魔改 AVD 设备，保存时就拦下
        from app.core import script_settings

        refusal = await script_settings.update_script(script.scriptId, data)
        if refusal:
            return OutBase(code=500, status="error", message=refusal)

    except Exception as e:
        logger.opt(exception=True).warning(
            f"update_script失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/delete",
    tags=["Delete"],
    summary="删除脚本",
    response_model=OutBase,
    status_code=200,
)
async def delete_script(script: ScriptDeleteIn = Body(...)) -> OutBase:

    try:
        await Config.del_script(script.scriptId)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"delete_script失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/order",
    tags=["Update"],
    summary="重新排序脚本",
    response_model=OutBase,
    status_code=200,
)
async def reorder_script(script: ScriptReorderIn = Body(...)) -> OutBase:

    try:
        await Config.reorder_script(script.indexList)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"reorder_script失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/import/web",
    tags=["Update"],
    summary="从配置中心导入脚本配置",
    response_model=OutBase,
    status_code=200,
)
async def import_script_from_web(script: ScriptTemplateImportIn = Body(...)) -> OutBase:

    try:
        await Config.import_script_from_share(
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
        _, risks = await Config.build_share_config(
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
        await Config.upload_script_to_share(
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


@router.post(
    "/config/import",
    tags=["Action"],
    summary="从脚本目录导入配置文件",
    response_model=OutBase,
    status_code=200,
)
async def import_script_config_file(
    config: ScriptConfigImportIn = Body(...),
) -> OutBase:

    try:
        await Config.import_script_config_file(config.scriptId, config.userId)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"import_script_config_file失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase(message="脚本配置文件已导入")


@router.post(
    "/user/get",
    tags=["Get"],
    summary="查询用户",
    response_model=UserGetOut,
    status_code=200,
)
async def get_user(user: UserGetIn = Body(...)) -> UserGetOut:

    try:
        index, data = await Config.get_user(user.scriptId, user.userId)
        index = [UserIndexItem(**_) for _ in index]
        data = {
            uid: USER_BOOK[
                type(Config.ScriptConfig[uuid.UUID(user.scriptId)]).__name__
            ](**cfg)
            for uid, cfg in data.items()
        }
    except Exception as e:
        logger.opt(exception=True).warning(f"get_user失败: {type(e).__name__}: {e}")
        return UserGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            index=[],
            data={},
        )
    return UserGetOut(index=index, data=data)


@router.post(
    "/user/config-dir",
    tags=["Get"],
    summary="获取用户配置目录",
    response_model=UserConfigDirOut,
    status_code=200,
)
async def get_user_config_dir(user: UserConfigDirIn = Body(...)) -> UserConfigDirOut:

    try:
        user_config_dir = await Config.get_user_config_dir(user.scriptId, user.userId)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"get_user_config_dir失败: {type(e).__name__}: {e}"
        )
        return UserConfigDirOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            path="",
        )
    return UserConfigDirOut(message="用户配置目录获取成功", path=str(user_config_dir))


@router.post(
    "/user/add",
    tags=["Add"],
    summary="添加用户",
    response_model=UserCreateOut,
    status_code=200,
)
async def add_user(user: UserInBase = Body(...)) -> UserCreateOut:

    try:
        uid, config = await Config.add_user(user.scriptId)
        data = USER_BOOK[type(Config.ScriptConfig[uuid.UUID(user.scriptId)]).__name__](
            **config.model_dump(context={"audience": "api"})
        )
    except FileNotFoundError as e:
        return UserCreateOut(
            code=409,
            status="error",
            message=str(e),
            userId="",
            data=GeneralUserConfig(**{}),
        )
    except Exception as e:
        logger.opt(exception=True).warning(f"add_user失败: {type(e).__name__}: {e}")
        return UserCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            userId="",
            data=GeneralUserConfig(**{}),
        )
    return UserCreateOut(userId=str(uid), data=data)


@router.post(
    "/user/update",
    tags=["Update"],
    summary="更新用户配置信息",
    response_model=OutBase,
    status_code=200,
)
async def update_user(user: UserUpdateIn = Body(...)) -> OutBase:
    data = user.data.model_dump(exclude_unset=True)

    try:
        from app.core import script_settings

        await script_settings.update_user(user.scriptId, user.userId, data=data)
    except Exception as e:
        logger.opt(exception=True).warning(f"update_user失败: {type(e).__name__}: {e}")
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/user/delete",
    tags=["Delete"],
    summary="删除用户",
    response_model=OutBase,
    status_code=200,
)
async def delete_user(user: UserDeleteIn = Body(...)) -> OutBase:

    try:
        await Config.del_user(user.scriptId, user.userId)
    except Exception as e:
        logger.opt(exception=True).warning(f"delete_user失败: {type(e).__name__}: {e}")
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/user/order",
    tags=["Update"],
    summary="重新排序用户",
    response_model=OutBase,
    status_code=200,
)
async def reorder_user(user: UserReorderIn = Body(...)) -> OutBase:

    try:
        await Config.reorder_user(user.scriptId, user.indexList)
    except Exception as e:
        logger.opt(exception=True).warning(f"reorder_user失败: {type(e).__name__}: {e}")
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/webhook/get",
    tags=["Get"],
    summary="查询 webhook 配置",
    response_model=WebhookGetOut,
    status_code=200,
)
async def get_webhook(webhook: WebhookGetIn = Body(...)) -> WebhookGetOut:

    try:
        index, data = await Config.get_webhook(
            webhook.scriptId, webhook.userId, webhook.webhookId
        )
        index = [WebhookIndexItem(**_) for _ in index]
        data = {uid: Webhook(**cfg) for uid, cfg in data.items()}
    except Exception as e:
        logger.opt(exception=True).warning(f"get_webhook失败: {type(e).__name__}: {e}")
        return WebhookGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            index=[],
            data={},
        )
    return WebhookGetOut(index=index, data=data)


@router.post(
    "/webhook/add",
    tags=["Add"],
    summary="添加webhook项",
    response_model=WebhookCreateOut,
    status_code=200,
)
async def add_webhook(webhook: WebhookInBase = Body(...)) -> WebhookCreateOut:

    try:
        uid, config = await Config.add_webhook(webhook.scriptId, webhook.userId)
        data = Webhook(**config.model_dump(context={"audience": "api"}))
    except Exception as e:
        logger.opt(exception=True).warning(f"add_webhook失败: {type(e).__name__}: {e}")
        return WebhookCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            webhookId="",
            data=Webhook(**{}),
        )
    return WebhookCreateOut(webhookId=str(uid), data=data)


@router.post(
    "/webhook/update",
    tags=["Update"],
    summary="更新webhook项",
    response_model=OutBase,
    status_code=200,
)
async def update_webhook(webhook: WebhookUpdateIn = Body(...)) -> OutBase:

    try:
        await Config.update_webhook(
            webhook.scriptId,
            webhook.userId,
            webhook.webhookId,
            webhook.data.model_dump(exclude_unset=True),
        )
    except Exception as e:
        logger.opt(exception=True).warning(
            f"update_webhook失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/webhook/delete",
    tags=["Delete"],
    summary="删除webhook项",
    response_model=OutBase,
    status_code=200,
)
async def delete_webhook(webhook: WebhookDeleteIn = Body(...)) -> OutBase:

    try:
        await Config.del_webhook(webhook.scriptId, webhook.userId, webhook.webhookId)
    except Exception as e:
        logger.opt(exception=True).warning(
            f"delete_webhook失败: {type(e).__name__}: {e}"
        )
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/mirror-cdk",
    tags=["Get"],
    summary="查询脚本生效的 Mirror 酱 CDK 状态",
    response_model=ScriptMirrorCdkOut,
)
async def query_script_mirror_cdk(payload: ScriptMirrorCdkIn) -> ScriptMirrorCdkOut:
    """校验编辑框草稿；MAA 专用 CDK 留空时按接管规则查询全局 CDK。"""
    using_global = not payload.cdk.strip()
    try:
        result = await query_takeover_cdk(payload.cdk)
    except Exception as error:
        logger.warning(f"脚本 Mirror 酱 CDK 查询失败: {type(error).__name__}")
        return ScriptMirrorCdkOut(
            data=ScriptMirrorCdkData(status="error", usingGlobalCdk=using_global)
        )
    return ScriptMirrorCdkOut(
        data=ScriptMirrorCdkData(
            status=result.status,
            expiredTime=result.expired_time,
            usingGlobalCdk=using_global,
        )
    )
