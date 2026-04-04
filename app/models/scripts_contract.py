from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import Field, TypeAdapter

from .common_contract import (
    ApiModel,
    ResourceCollectionOut,
    ResourceCreateOut,
    ResourceItemOut,
    project_model,
)
from .general_contract import (
    GeneralConfig,
    GeneralConfigPatch,
    GeneralUserConfig,
    GeneralUserConfigPatch,
)
from .maa_contract import MaaConfig, MaaConfigPatch, MaaUserConfig, MaaUserConfigPatch
from .maaend_contract import (
    MaaEndConfig,
    MaaEndConfigPatch,
    MaaEndUserConfig,
    MaaEndUserConfigPatch,
)
from .src_contract import SrcConfig, SrcConfigPatch, SrcUserConfig, SrcUserConfigPatch


ScriptConfigType = Literal["MaaConfig", "GeneralConfig", "SrcConfig", "MaaEndConfig"]
UserConfigType = Literal[
    "MaaUserConfig", "GeneralUserConfig", "SrcUserConfig", "MaaEndUserConfig"
]
ScriptCreateType = Literal["MAA", "SRC", "General", "MaaEnd"]
PatchPayload: TypeAlias = dict[str, object]

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
ScriptPatchClass = (
    type[MaaConfigPatch]
    | type[SrcConfigPatch]
    | type[GeneralConfigPatch]
    | type[MaaEndConfigPatch]
)
UserPatchClass = (
    type[MaaUserConfigPatch]
    | type[SrcUserConfigPatch]
    | type[GeneralUserConfigPatch]
    | type[MaaEndUserConfigPatch]
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
SCRIPT_PATCH_BY_TYPE: dict[ScriptConfigType, ScriptPatchClass] = {
    "MaaConfig": MaaConfigPatch,
    "GeneralConfig": GeneralConfigPatch,
    "SrcConfig": SrcConfigPatch,
    "MaaEndConfig": MaaEndConfigPatch,
}
USER_CONTRACT_BY_TYPE: dict[UserConfigType, UserModelClass] = {
    "MaaUserConfig": MaaUserConfig,
    "GeneralUserConfig": GeneralUserConfig,
    "SrcUserConfig": SrcUserConfig,
    "MaaEndUserConfig": MaaEndUserConfig,
}
USER_PATCH_BY_TYPE: dict[UserConfigType, UserPatchClass] = {
    "MaaUserConfig": MaaUserConfigPatch,
    "GeneralUserConfig": GeneralUserConfigPatch,
    "SrcUserConfig": SrcUserConfigPatch,
    "MaaEndUserConfig": MaaEndUserConfigPatch,
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
PATCH_PAYLOAD_ADAPTER: TypeAdapter[PatchPayload] = TypeAdapter(dict[str, object])


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


ScriptCreateOut = ResourceCreateOut[ScriptReadData]
ScriptDetailOut = ResourceItemOut[ScriptReadData]
ScriptGetOut = ResourceCollectionOut[ScriptIndexItem, ScriptReadData]


class ScriptFileBody(ApiModel):
    path: str = Field(..., description="文件路径")


class ScriptUrlBody(ApiModel):
    url: str = Field(..., description="配置文件 URL")


class ScriptUploadBody(ApiModel):
    config_name: str = Field(..., description="配置名称")
    author: str = Field(..., description="作者")
    description: str = Field(..., description="描述")


UserGetOut = ResourceCollectionOut[UserIndexItem, UserReadData]
UserDetailOut = ResourceItemOut[UserReadData]
UserCreateOut = ResourceCreateOut[UserReadData]


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


def validate_script_patch_data(
    script_type: ScriptConfigType, raw: Mapping[str, object]
) -> dict[str, Any]:
    normalized = PATCH_PAYLOAD_ADAPTER.validate_python(raw)
    validated = SCRIPT_PATCH_BY_TYPE[script_type].model_validate(normalized)
    return validated.model_dump(exclude_unset=True, exclude_none=True, exclude={"type"})


def validate_user_patch_data(
    user_type: UserConfigType, raw: Mapping[str, object]
) -> dict[str, Any]:
    normalized = PATCH_PAYLOAD_ADAPTER.validate_python(raw)
    validated = USER_PATCH_BY_TYPE[user_type].model_validate(normalized)
    return validated.model_dump(exclude_unset=True, exclude_none=True, exclude={"type"})


__all__ = [
    "ScriptConfigType",
    "UserConfigType",
    "ScriptCreateType",
    "PatchPayload",
    "ScriptModel",
    "UserModel",
    "ScriptReadData",
    "UserReadData",
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
    "UserGetOut",
    "UserDetailOut",
    "UserCreateOut",
    "InfrastructureImportBody",
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
