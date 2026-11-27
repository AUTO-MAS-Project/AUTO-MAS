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

"""账号管理路由与端点专用模型。"""

import uuid
from typing import (
    Dict,
    List,
    Optional,
    Union,
)

from fastapi import APIRouter, Body, Depends
from pydantic import (
    BaseModel,
    Field,
    SerializeAsAny,
    SkipValidation,
    ValidationError,
)

import app.models.config as _config_models
from app.api._config_editors import (
    config_detail_ui,
    config_update_data,
    require_frontend_activation,
)
from app.api._error_codes import config_error_code
from app.config.errors import ConfigAggregateError
from app.config.wire import ConfigInput, ConfigPayload
from app.core import Config
from app.models.schema import (
    ConfigUpdateOut,
    DeclarativeConfigGetOut,
    OutBase,
    UserDeleteIn,
    UserInBase,
)
from app.models.script_access import script_users
from app.utils import get_logger

BAAHUserConfig = ConfigPayload[_config_models.BAAHUserConfig]


BAAHUserConfigInput = ConfigInput[_config_models.BAAHUserConfig]


GeneralUserConfig = ConfigPayload[_config_models.GeneralUserConfig]


GeneralUserConfigInput = ConfigInput[_config_models.GeneralUserConfig]


HSRUserConfig = ConfigPayload[_config_models.HSRUserConfig]


HSRUserConfigInput = ConfigInput[_config_models.HSRUserConfig]


MaaEndUserConfig = ConfigPayload[_config_models.MaaEndUserConfig]


MaaEndUserConfigInput = ConfigInput[_config_models.MaaEndUserConfig]


OkNteUserConfig = ConfigPayload[_config_models.OkNteUserConfig]


OkNteUserConfigInput = ConfigInput[_config_models.OkNteUserConfig]


OkwwUserConfig = ConfigPayload[_config_models.OkwwUserConfig]


OkwwUserConfigInput = ConfigInput[_config_models.OkwwUserConfig]


ZzzOdUserConfig = ConfigPayload[_config_models.ZzzOdUserConfig]


ZzzOdUserConfigInput = ConfigInput[_config_models.ZzzOdUserConfig]


class UserIndexItem(BaseModel):
    uid: str = Field(..., description="唯一标识符")
    type: str = Field(
        json_schema_extra={
            "enum": [
                "GeneralUserConfig",
                "OkwwUserConfig",
                "OkNteUserConfig",
                "MaaEndUserConfig",
                "HSRUserConfig",
                "ZzzOdUserConfig",
                "BAAHUserConfig",
            ]
        },
        default=...,
        description="配置类型",
    )


class UserConfigDirIn(UserInBase):
    userId: str = Field(..., description="账号ID")


class UserConfigDirOut(OutBase):
    path: Optional[str] = Field(default=None, description="账号配置目录绝对路径")


class UserGetIn(UserInBase):
    userId: Optional[str] = Field(
        default=None, description="账号ID, 未携带时表示获取所有账号数据"
    )


class UserGetOut(DeclarativeConfigGetOut):
    index: List[UserIndexItem] = Field(..., description="账号索引列表")
    data: Dict[
        str,
        Union[
            SerializeAsAny[BaseModel],
            GeneralUserConfig,
            OkwwUserConfig,
            OkNteUserConfig,
            MaaEndUserConfig,
            HSRUserConfig,
            ZzzOdUserConfig,
            BAAHUserConfig,
        ],
    ] = Field(..., description="账号数据字典, key来自于index列表的uid")


class UserCreateIn(UserInBase):
    firstOnly: bool = False


class UserCreateOut(OutBase):
    userId: str = Field(..., description="账号ID")
    data: Union[
        SerializeAsAny[BaseModel],
        GeneralUserConfig,
        OkwwUserConfig,
        OkNteUserConfig,
        MaaEndUserConfig,
        HSRUserConfig,
        ZzzOdUserConfig,
        BAAHUserConfig,
    ] = Field(..., description="账号配置数据")


class UserUpdateIn(UserInBase):
    userId: str = Field(..., description="账号ID")
    data: SkipValidation[
        Union[
            SerializeAsAny[BaseModel],
            GeneralUserConfigInput,
            OkwwUserConfigInput,
            OkNteUserConfigInput,
            MaaEndUserConfigInput,
            HSRUserConfigInput,
            ZzzOdUserConfigInput,
            BAAHUserConfigInput,
        ]
    ] = Field(..., description="账号更新数据")


class UserReorderIn(UserInBase):
    indexList: List[str] = Field(..., description="账号ID列表, 按新顺序排列")


router = APIRouter()
logger = get_logger("托管管理 API")


@router.post(
    "/user/get",
    tags=["Get"],
    summary="查询账号",
    response_model=UserGetOut,
    status_code=200,
)
async def get_user(user: UserGetIn = Body(...)) -> UserGetOut:

    try:
        index, data = await Config.get_user(user.scriptId, user.userId)
        index = [UserIndexItem(**_) for _ in index]
        script = Config.ScriptConfig[uuid.UUID(user.scriptId)]
        user_configs = script_users(script)
        ui = (
            config_detail_ui(
                user_configs[user.userId],
                data,
                parent_script_type=type(script).__name__,
            )
            if user.userId
            else None
        )
        data = {
            uid: ConfigPayload[type(user_configs[uuid.UUID(uid)])](**cfg)
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
    return UserGetOut.model_validate(
        {
            "index": index,
            "data": data,
            "ui": ui,
            "uiSources": [uuid.UUID(user.userId) if user.userId else user_configs.uid],
        }
    )


@router.post(
    "/user/config-dir",
    tags=["Get"],
    summary="获取账号配置目录",
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
    return UserConfigDirOut(message="账号配置目录获取成功", path=str(user_config_dir))


@router.post(
    "/user/add",
    tags=["Add"],
    summary="添加账号",
    response_model=UserCreateOut,
    status_code=200,
)
async def add_user(user: UserCreateIn = Body(...)) -> UserCreateOut:

    try:
        uid, config = await Config.add_user(
            user.scriptId, native_defaults=True, first_only=user.firstOnly
        )
        data = ConfigPayload[type(config)](
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
    summary="更新账号配置信息",
    response_model=ConfigUpdateOut,
    status_code=200,
    dependencies=[Depends(require_frontend_activation, scope="function")],
)
async def update_user(
    user: UserUpdateIn = Body(...),
) -> ConfigUpdateOut:
    try:
        entry = script_users(Config.ScriptConfig[user.scriptId])[user.userId]
        data = config_update_data(entry, user.data)
        await Config.update_user(user.scriptId, user.userId, data=data)
    except (ValidationError, ConfigAggregateError) as e:
        return ConfigUpdateOut.from_validation_error(e, code=config_error_code(e))
    except Exception as e:
        logger.opt(exception=True).warning(f"update_user失败: {type(e).__name__}: {e}")
        return ConfigUpdateOut(
            code=config_error_code(e),
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
        )
    return ConfigUpdateOut()


@router.post(
    "/user/delete",
    tags=["Delete"],
    summary="删除账号",
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
    summary="重新排序账号",
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
