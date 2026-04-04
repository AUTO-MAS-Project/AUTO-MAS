from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import Field, TypeAdapter

from .common_contract import ApiModel, OutBase, project_model
from .general_contract import GeneralConfig, GeneralUserConfig
from .maa_contract import MaaConfig, MaaUserConfig
from .maaend_contract import MaaEndConfig, MaaEndUserConfig
from .src_contract import SrcConfig, SrcUserConfig

ScriptConfigType = Literal["MaaConfig", "GeneralConfig", "SrcConfig", "MaaEndConfig"]
UserConfigType = Literal[
    "MaaUserConfig", "GeneralUserConfig", "SrcUserConfig", "MaaEndUserConfig"
]
ScriptCreateType = Literal["MAA", "SRC", "General", "MaaEnd"]
JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
PatchPayload: TypeAlias = dict[str, JsonValue]

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
USER_CONTRACT_BY_TYPE: dict[UserConfigType, UserModelClass] = {
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
PATCH_PAYLOAD_ADAPTER: TypeAdapter[PatchPayload] = TypeAdapter(dict[str, JsonValue])


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
    scriptId: str | None = Field(
        default=None, description="直接从该脚本ID复制创建, 仅在复制创建时使用"
    )


class ScriptCreateOut(OutBase):
    scriptId: str = Field(..., description="新创建的脚本ID")
    data: ScriptReadData = Field(..., description="脚本配置数据")


class ScriptGetIn(ApiModel):
    scriptId: str | None = Field(
        default=None, description="脚本ID, 未携带时表示获取所有脚本数据"
    )


class ScriptGetOut(OutBase):
    index: list[ScriptIndexItem] = Field(..., description="脚本索引列表")
    data: dict[str, ScriptReadData] = Field(
        ..., description="脚本数据字典, key来自于index列表的uid"
    )


class ScriptUpdateIn(ApiModel):
    scriptId: str = Field(..., description="脚本ID")
    data: PatchPayload = Field(
        ..., description="脚本更新数据, 由后端根据 scriptId 选择对应 Patch 模型校验"
    )


class ScriptDeleteIn(ApiModel):
    scriptId: str = Field(..., description="脚本ID")


class ScriptReorderIn(ApiModel):
    indexList: list[str] = Field(..., description="脚本ID列表, 按新顺序排列")


class ScriptFileIn(ApiModel):
    scriptId: str = Field(..., description="脚本ID")
    jsonFile: str = Field(..., description="配置文件路径")


class ScriptUrlIn(ApiModel):
    scriptId: str = Field(..., description="脚本ID")
    url: str = Field(..., description="配置文件URL")


class ScriptUploadIn(ApiModel):
    scriptId: str = Field(..., description="脚本ID")
    config_name: str = Field(..., description="配置名称")
    author: str = Field(..., description="作者")
    description: str = Field(..., description="描述")


class UserInBase(ApiModel):
    scriptId: str = Field(..., description="所属脚本ID")


class UserGetIn(UserInBase):
    userId: str | None = Field(
        default=None, description="用户ID, 未携带时表示获取所有用户数据"
    )


class UserGetOut(OutBase):
    index: list[UserIndexItem] = Field(..., description="用户索引列表")
    data: dict[str, UserReadData] = Field(
        ..., description="用户数据字典, key来自于index列表的uid"
    )


class UserCreateOut(OutBase):
    userId: str = Field(..., description="新创建的用户ID")
    data: UserReadData = Field(..., description="用户配置数据")


class UserUpdateIn(UserInBase):
    userId: str = Field(..., description="用户ID")
    data: PatchPayload = Field(
        ..., description="用户更新数据, 由后端根据 scriptId 选择对应 Patch 模型校验"
    )


class UserDeleteIn(UserInBase):
    userId: str = Field(..., description="用户ID")


class UserReorderIn(UserInBase):
    indexList: list[str] = Field(..., description="用户ID列表, 按新顺序排列")


class UserSetIn(UserInBase):
    userId: str = Field(..., description="用户ID")
    jsonFile: str = Field(..., description="JSON文件路径, 用于导入自定义基建文件")


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
    index_map: dict[str, ScriptConfigType] = {item.uid: item.type for item in index_list}
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


def validate_script_patch_data(
    script_type: ScriptConfigType, raw: Mapping[str, JsonValue]
) -> dict[str, Any]:
    normalized = PATCH_PAYLOAD_ADAPTER.validate_python(raw)
    validated = SCRIPT_CONTRACT_BY_TYPE[script_type].model_validate(normalized)
    return validated.model_dump(exclude_unset=True, exclude={"type"})


def validate_user_patch_data(
    user_type: UserConfigType, raw: Mapping[str, JsonValue]
) -> dict[str, Any]:
    normalized = PATCH_PAYLOAD_ADAPTER.validate_python(raw)
    validated = USER_CONTRACT_BY_TYPE[user_type].model_validate(normalized)
    return validated.model_dump(exclude_unset=True, exclude={"type"})


__all__ = [
    "ScriptConfigType",
    "UserConfigType",
    "ScriptCreateType",
    "JsonValue",
    "PatchPayload",
    "ScriptModel",
    "UserModel",
    "ScriptReadData",
    "UserReadData",
    "SCRIPT_CONTRACT_BY_TYPE",
    "USER_CONTRACT_BY_TYPE",
    "SCRIPT_CREATE_TO_CONFIG_TYPE",
    "SCRIPT_CONFIG_TO_USER_TYPE",
    "ScriptIndexItem",
    "UserIndexItem",
    "ScriptCreateIn",
    "ScriptCreateOut",
    "ScriptGetIn",
    "ScriptGetOut",
    "ScriptUpdateIn",
    "ScriptDeleteIn",
    "ScriptReorderIn",
    "ScriptFileIn",
    "ScriptUrlIn",
    "ScriptUploadIn",
    "UserInBase",
    "UserGetIn",
    "UserGetOut",
    "UserCreateOut",
    "UserUpdateIn",
    "UserDeleteIn",
    "UserReorderIn",
    "UserSetIn",
    "script_contract_type_from_create",
    "script_contract_type_from_runtime",
    "user_contract_type_from_script",
    "project_script_model",
    "project_user_model",
    "project_script_model_map",
    "project_user_model_map",
    "validate_script_patch_data",
    "validate_user_patch_data",
]
