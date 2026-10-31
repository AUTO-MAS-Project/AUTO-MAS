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

"""用户管理路由与端点专用模型。"""

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
from app.models.schema import (
    OutBase,
    UserDeleteIn,
    UserInBase,
)
from app.utils import get_logger

BAAHUserConfig = ConfigPayload[_config_models.BAAHUserConfig]


BAAHUserConfigInput = ConfigInput[_config_models.BAAHUserConfig]


BetterGIUserConfig = ConfigPayload[_config_models.BetterGIUserConfig]


BetterGIUserConfigInput = ConfigInput[_config_models.BetterGIUserConfig]


GeneralUserConfig = ConfigPayload[_config_models.GeneralUserConfig]


GeneralUserConfigInput = ConfigInput[_config_models.GeneralUserConfig]


HSRUserConfig = ConfigPayload[_config_models.HSRUserConfig]


HSRUserConfigInput = ConfigInput[_config_models.HSRUserConfig]


M9AUserConfig = ConfigPayload[_config_models.M9AUserConfig]


M9AUserConfigInput = ConfigInput[_config_models.M9AUserConfig]


MSSUserConfig = ConfigPayload[_config_models.MSSUserConfig]


MSSUserConfigInput = ConfigInput[_config_models.MSSUserConfig]


MaaEndUserConfig = ConfigPayload[_config_models.MaaEndUserConfig]


MaaEndUserConfigInput = ConfigInput[_config_models.MaaEndUserConfig]


MaaFWUserConfig = ConfigPayload[_config_models.MaaFWUserConfig]


MaaFWUserConfigInput = ConfigInput[_config_models.MaaFWUserConfig]


MaaUserConfig = ConfigPayload[_config_models.MaaUserConfig]


MaaUserConfigInput = ConfigInput[_config_models.MaaUserConfig]


OkNteUserConfig = ConfigPayload[_config_models.OkNteUserConfig]


OkNteUserConfigInput = ConfigInput[_config_models.OkNteUserConfig]


OkwwUserConfig = ConfigPayload[_config_models.OkwwUserConfig]


OkwwUserConfigInput = ConfigInput[_config_models.OkwwUserConfig]


SrcUserConfig = ConfigPayload[_config_models.SrcUserConfig]


SrcUserConfigInput = ConfigInput[_config_models.SrcUserConfig]


WhimboxUserConfig = ConfigPayload[_config_models.WhimboxUserConfig]


WhimboxUserConfigInput = ConfigInput[_config_models.WhimboxUserConfig]


ZzzOdUserConfig = ConfigPayload[_config_models.ZzzOdUserConfig]


ZzzOdUserConfigInput = ConfigInput[_config_models.ZzzOdUserConfig]


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


router = APIRouter()
logger = get_logger("脚本管理 API")


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
        user_configs = Config.ScriptConfig[uuid.UUID(user.scriptId)].UserData
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
    summary="更新用户配置信息",
    response_model=OutBase,
    status_code=200,
)
async def update_user(
    user: UserUpdateIn = Body(...),
) -> OutBase:
    data = user.data.model_dump(exclude_unset=True)

    try:
        await Config.update_user(user.scriptId, user.userId, data=data)
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
