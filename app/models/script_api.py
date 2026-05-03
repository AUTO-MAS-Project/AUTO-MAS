from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .schema import OutBase


class ScriptTypeDescriptor(BaseModel):
    """脚本类型描述。"""

    type_key: str = Field(..., description="脚本类型键")
    display_name: str = Field(..., description="脚本类型显示名称")
    icon: str | None = Field(default=None, description="脚本类型图标标识")
    docs_url: str | None = Field(default=None, description="文档地址")
    editor_kind: str = Field(..., description="编辑器类型")
    supported_modes: list[str] = Field(..., description="支持的任务模式")
    script_schema: dict[str, Any] = Field(..., description="脚本配置表单描述")
    user_schema: dict[str, Any] = Field(..., description="用户配置表单描述")
    legacy_config_class_name: str | None = Field(
        default=None, description="旧脚本配置类名"
    )
    legacy_user_config_class_name: str | None = Field(
        default=None, description="旧用户配置类名"
    )
    is_builtin: bool = Field(default=False, description="是否为内建脚本类型")


class ScriptTypeGetOut(OutBase):
    data: list[ScriptTypeDescriptor] = Field(..., description="脚本类型列表")


class ScriptRecord(BaseModel):
    """通用脚本记录。"""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., description="脚本 ID")
    type: str = Field(..., description="脚本类型键")
    name: str = Field(..., description="脚本名称")
    config: dict[str, Any] = Field(..., description="脚本配置内容")
    schema_definition: dict[str, Any] = Field(
        ...,
        alias="schema",
        serialization_alias="schema",
        description="脚本配置表单描述",
    )
    editor_kind: str = Field(..., description="编辑器类型")
    supported_modes: list[str] = Field(..., description="支持的任务模式")
    icon: str | None = Field(default=None, description="图标标识")
    docs_url: str | None = Field(default=None, description="文档地址")
    user_count: int = Field(default=0, description="用户数量")


class ScriptRecordGetIn(BaseModel):
    scriptId: str | None = Field(default=None, description="脚本 ID")


class ScriptRecordCreateIn(BaseModel):
    type: str = Field(..., description="脚本类型键")
    scriptId: str | None = Field(default=None, description="复制来源脚本 ID")


class ScriptRecordUpdateIn(BaseModel):
    scriptId: str = Field(..., description="脚本 ID")
    config: dict[str, Any] = Field(..., description="脚本配置更新内容")


class ScriptRecordDeleteIn(BaseModel):
    scriptId: str = Field(..., description="脚本 ID")


class ScriptRecordReorderIn(BaseModel):
    indexList: list[str] = Field(..., description="脚本 ID 顺序")


class ScriptRecordCreateOut(OutBase):
    record: ScriptRecord = Field(..., description="新建后的脚本记录")


class ScriptRecordGetOut(OutBase):
    records: list[ScriptRecord] = Field(..., description="脚本记录列表")


class ScriptUserRecord(BaseModel):
    """通用脚本用户记录。"""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., description="用户 ID")
    script_id: str = Field(..., description="所属脚本 ID")
    type: str = Field(..., description="脚本类型键")
    name: str = Field(..., description="用户名称")
    config: dict[str, Any] = Field(..., description="用户配置内容")
    schema_definition: dict[str, Any] = Field(
        ...,
        alias="schema",
        serialization_alias="schema",
        description="用户配置表单描述",
    )


class ScriptUserRecordGetIn(BaseModel):
    scriptId: str = Field(..., description="所属脚本 ID")
    userId: str | None = Field(default=None, description="用户 ID")


class ScriptUserRecordCreateIn(BaseModel):
    scriptId: str = Field(..., description="所属脚本 ID")


class ScriptUserRecordUpdateIn(BaseModel):
    scriptId: str = Field(..., description="所属脚本 ID")
    userId: str = Field(..., description="用户 ID")
    config: dict[str, Any] = Field(..., description="用户配置更新内容")


class ScriptUserRecordDeleteIn(BaseModel):
    scriptId: str = Field(..., description="所属脚本 ID")
    userId: str = Field(..., description="用户 ID")


class ScriptUserRecordReorderIn(BaseModel):
    scriptId: str = Field(..., description="所属脚本 ID")
    indexList: list[str] = Field(..., description="用户 ID 顺序")


class ScriptUserRecordCreateOut(OutBase):
    record: ScriptUserRecord = Field(..., description="新建后的用户记录")


class ScriptUserRecordGetOut(OutBase):
    records: list[ScriptUserRecord] = Field(..., description="用户记录列表")
