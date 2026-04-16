from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import Field

from .common_contract import (
    ApiModel,
    ResourceCollectionOut,
    ResourceCreateOut,
    ResourceItemOut,
    dump_writable_data,
    project_model,
)
from .general_contract import (
    GeneralConfig,
    GeneralUserConfig,
)
from .maa_contract import MaaConfig, MaaUserConfig
from .maaend_contract import (
    MaaEndConfig,
    MaaEndUserConfig,
)
from .src_contract import SrcConfig, SrcUserConfig


ScriptConfigType = Literal["MaaConfig", "GeneralConfig", "SrcConfig", "MaaEndConfig"]
UserConfigType = Literal[
    "MaaUserConfig", "GeneralUserConfig", "SrcUserConfig", "MaaEndUserConfig"
]
ScriptCreateType = Literal["MAA", "SRC", "General", "MaaEnd"]

ScriptModel = MaaConfig | SrcConfig | GeneralConfig | MaaEndConfig
UserModel = MaaUserConfig | SrcUserConfig | GeneralUserConfig | MaaEndUserConfig
ScriptModelClass = (
    type[MaaConfig] | type[SrcConfig] | type[GeneralConfig] | type[MaaEndConfig]
)
UserModelClass = (
    type[MaaUserConfig]
    | type[SrcUserConfig]
    | type[GeneralUserConfig]
    | type[MaaEndUserConfig]
)
ScriptPatchClass = ScriptModelClass
UserPatchClass = UserModelClass

ScriptReadData = Annotated[
    MaaConfig | SrcConfig | GeneralConfig | MaaEndConfig,
    Field(discriminator="type"),
]
UserReadData = Annotated[
    MaaUserConfig | SrcUserConfig | GeneralUserConfig | MaaEndUserConfig,
    Field(discriminator="type"),
]

SCRIPT_CONTRACT_BY_TYPE: dict[ScriptConfigType, ScriptModelClass] = {
    "MaaConfig": MaaConfig,
    "GeneralConfig": GeneralConfig,
    "SrcConfig": SrcConfig,
    "MaaEndConfig": MaaEndConfig,
}
SCRIPT_PATCH_BY_TYPE: dict[ScriptConfigType, ScriptPatchClass] = {
    "MaaConfig": MaaConfig,
    "GeneralConfig": GeneralConfig,
    "SrcConfig": SrcConfig,
    "MaaEndConfig": MaaEndConfig,
}
USER_CONTRACT_BY_TYPE: dict[UserConfigType, UserModelClass] = {
    "MaaUserConfig": MaaUserConfig,
    "GeneralUserConfig": GeneralUserConfig,
    "SrcUserConfig": SrcUserConfig,
    "MaaEndUserConfig": MaaEndUserConfig,
}
USER_PATCH_BY_TYPE: dict[UserConfigType, UserPatchClass] = {
    "MaaUserConfig": MaaUserConfig,
    "GeneralUserConfig": GeneralUserConfig,
    "SrcUserConfig": SrcUserConfig,
    "MaaEndUserConfig": MaaEndUserConfig,
}
SCRIPT_CREATE_TO_CONFIG_TYPE: dict[ScriptCreateType, ScriptConfigType] = {
    "MAA": "MaaConfig",
    "SRC": "SrcConfig",
    "General": "GeneralConfig",
    "MaaEnd": "MaaEndConfig",
}
SCRIPT_CONFIG_TO_USER_TYPE: dict[ScriptConfigType, UserConfigType] = {
    "MaaConfig": "MaaUserConfig",
    "GeneralConfig": "GeneralUserConfig",
    "SrcConfig": "SrcUserConfig",
    "MaaEndConfig": "MaaEndUserConfig",
}


class ScriptIndexItem(ApiModel):
    uid: str = Field(..., description="唯一标识符")
    type: ScriptConfigType = Field(..., description="配置类型")


class UserIndexItem(ApiModel):
    uid: str = Field(..., description="唯一标识符")
    type: UserConfigType = Field(..., description="配置类型")


class ScriptCreateIn(ApiModel):
    type: ScriptCreateType = Field(
        ..., description="脚本类型: MAA脚本, 通用脚本, SRC脚本, MaaEnd脚本"
    )
    copyFromId: str | None = Field(
        default=None, description="直接从该脚本 ID 复制创建, 仅复制创建时使用"
    )


class ScriptCreateOut(ResourceCreateOut[ScriptReadData]):
    """脚本创建响应模型"""


class ScriptDetailOut(ResourceItemOut[ScriptReadData]):
    """脚本详情响应模型"""


class ScriptGetOut(ResourceCollectionOut[ScriptIndexItem, ScriptReadData]):
    """脚本列表响应模型"""


class ScriptFileBody(ApiModel):
    path: str = Field(..., description="文件路径")


class ScriptUrlBody(ApiModel):
    url: str = Field(..., description="配置文件 URL")


class ScriptUploadBody(ApiModel):
    config_name: str = Field(..., description="配置名称")
    author: str = Field(..., description="作者")
    description: str = Field(..., description="描述")


class UserGetOut(ResourceCollectionOut[UserIndexItem, UserReadData]):
    """用户列表响应模型"""


class UserDetailOut(ResourceItemOut[UserReadData]):
    """用户详情响应模型"""


class UserCreateOut(ResourceCreateOut[UserReadData]):
    """用户创建响应模型"""

ScriptPatchData = Annotated[
    MaaConfig | SrcConfig | GeneralConfig | MaaEndConfig,
    Field(discriminator="type"),
]
UserPatchData = Annotated[
    MaaUserConfig | SrcUserConfig | GeneralUserConfig | MaaEndUserConfig,
    Field(discriminator="type"),
]


class ScriptPatchBody(ApiModel):
    data: ScriptPatchData = Field(..., description="脚本 Patch 数据")


class UserPatchBody(ApiModel):
    data: UserPatchData = Field(..., description="用户 Patch 数据")


class InfrastructureImportBody(ApiModel):
    path: str = Field(..., description="JSON 文件路径, 用于导入自定义基建文件")


def script_contract_type_from_create(create_type: ScriptCreateType) -> ScriptConfigType:
    return SCRIPT_CREATE_TO_CONFIG_TYPE[create_type]


def script_contract_type_from_runtime(type_name: str) -> ScriptConfigType:
    if type_name not in SCRIPT_CONTRACT_BY_TYPE:
        raise KeyError(f"未知脚本 Contract 类型: {type_name}")
    return type_name


def user_contract_type_from_script(script_type: ScriptConfigType) -> UserConfigType:
    return SCRIPT_CONFIG_TO_USER_TYPE[script_type]


def project_script_model(
    script_type: ScriptConfigType,
    raw: Mapping[str, Any] | ApiModel | None,
) -> ScriptModel:
    return project_model(SCRIPT_CONTRACT_BY_TYPE[script_type], raw)


def project_user_model(
    user_type: UserConfigType,
    raw: Mapping[str, Any] | ApiModel | None,
) -> UserModel:
    return project_model(USER_CONTRACT_BY_TYPE[user_type], raw)


def project_script_model_map(
    index_list: list[ScriptIndexItem],
    raw_map: Mapping[str, Mapping[str, Any] | ApiModel],
) -> dict[str, ScriptModel]:
    index_map: dict[str, ScriptConfigType] = {
        item.uid: item.type for item in index_list
    }
    return {
        uid: project_script_model(index_map[uid], raw)
        for uid, raw in raw_map.items()
        if uid in index_map
    }


def project_user_model_map(
    index_list: list[UserIndexItem],
    raw_map: Mapping[str, Mapping[str, Any] | ApiModel],
) -> dict[str, UserModel]:
    index_map: dict[str, UserConfigType] = {item.uid: item.type for item in index_list}
    return {
        uid: project_user_model(index_map[uid], raw)
        for uid, raw in raw_map.items()
        if uid in index_map
    }


def dump_script_patch_data(
    script_type: ScriptConfigType, data: ScriptPatchData
) -> dict[str, Any]:
    if data.type != script_type:
        raise ValueError(f"Patch 类型不匹配: 期望 {script_type}, 实际 {data.type}")
    writable = dump_writable_data(data)
    writable.pop("type", None)
    return writable


def dump_user_patch_data(
    user_type: UserConfigType, data: UserPatchData
) -> dict[str, Any]:
    if data.type != user_type:
        raise ValueError(f"Patch 类型不匹配: 期望 {user_type}, 实际 {data.type}")
    writable = dump_writable_data(data)
    writable.pop("type", None)
    return writable


__all__ = [
    "ScriptConfigType",
    "UserConfigType",
    "ScriptCreateType",
    "ScriptModel",
    "UserModel",
    "ScriptReadData",
    "UserReadData",
    "ScriptPatchData",
    "UserPatchData",
    "SCRIPT_CONTRACT_BY_TYPE",
    "SCRIPT_PATCH_BY_TYPE",
    "USER_CONTRACT_BY_TYPE",
    "USER_PATCH_BY_TYPE",
    "SCRIPT_CREATE_TO_CONFIG_TYPE",
    "SCRIPT_CONFIG_TO_USER_TYPE",
    "ScriptIndexItem",
    "UserIndexItem",
    "ScriptCreateIn",
    "ScriptCreateOut",
    "ScriptDetailOut",
    "ScriptGetOut",
    "ScriptFileBody",
    "ScriptUrlBody",
    "ScriptUploadBody",
    "ScriptPatchBody",
    "UserGetOut",
    "UserDetailOut",
    "UserCreateOut",
    "UserPatchBody",
    "InfrastructureImportBody",
    "script_contract_type_from_create",
    "script_contract_type_from_runtime",
    "user_contract_type_from_script",
    "project_script_model",
    "project_user_model",
    "project_script_model_map",
    "project_user_model_map",
    "dump_script_patch_data",
    "dump_user_patch_data",
]
