from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any, Literal, get_args

from pydantic import BaseModel

from app.models.ConfigBase import ConfigBase, JSONValidator
from app.utils.security import dpapi_decrypt, dpapi_encrypt

if TYPE_CHECKING:
    from app.core.script_types import ScriptTypeProvider


ConfigKind = Literal["script", "user"]
_PYDANTIC_SENSITIVE_PREFIX = "dpapi:"


def _config_class(provider: "ScriptTypeProvider", kind: ConfigKind) -> type[Any]:
    if kind == "script":
        return provider.script_config_class
    if kind == "user":
        return provider.user_config_class
    raise ValueError(f"未知配置类型: {kind}")


def _is_configbase_class(config_class: type[Any]) -> bool:
    return isinstance(config_class, type) and issubclass(config_class, ConfigBase)


def _is_pydantic_class(config_class: type[Any]) -> bool:
    return isinstance(config_class, type) and issubclass(config_class, BaseModel)


def _coerce_payload(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, str):
        text = payload.strip()
        if not text or text == "{}":
            return {}
        data = json.loads(text)
        if not isinstance(data, dict):
            raise TypeError("插件脚本配置 JSON 必须是对象")
        return data
    if isinstance(payload, dict):
        return copy.deepcopy(payload)
    raise TypeError(f"插件脚本配置必须是 dict 或 JSON 字符串: {type(payload).__name__}")


def _nested_pydantic_class(annotation: Any) -> type[BaseModel] | None:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    for argument in get_args(annotation):
        nested = _nested_pydantic_class(argument)
        if nested is not None:
            return nested
    return None


def _transform_pydantic_sensitive_fields(
    config_class: type[BaseModel],
    payload: dict[str, Any],
    *,
    decrypt: bool,
) -> dict[str, Any]:
    """Encrypt/decrypt fields declared with ``PluginField(sensitive=True)``.

    ConfigBase fields already receive this treatment from EncryptValidator.
    Pydantic-backed plugin scripts need the equivalent transformation at the
    storage boundary; a prefix distinguishes new ciphertext from legacy
    plaintext and makes corrupt ciphertext fail closed.
    """

    data = copy.deepcopy(payload)
    for name, field_info in config_class.model_fields.items():
        if name not in data:
            continue
        value = data[name]
        extra = field_info.json_schema_extra
        is_sensitive = isinstance(extra, dict) and bool(extra.get("sensitive"))
        if is_sensitive and isinstance(value, str) and value:
            if decrypt:
                if value.startswith(_PYDANTIC_SENSITIVE_PREFIX):
                    try:
                        value = dpapi_decrypt(
                            value[len(_PYDANTIC_SENSITIVE_PREFIX) :]
                        )
                    except Exception as exc:
                        raise ValueError(f"敏感配置字段 {name} 无法解密") from exc
                # Unprefixed values are legacy plaintext and are migrated on
                # the next write.
            elif value.startswith(_PYDANTIC_SENSITIVE_PREFIX):
                try:
                    dpapi_decrypt(value[len(_PYDANTIC_SENSITIVE_PREFIX) :])
                except Exception as exc:
                    raise ValueError(f"敏感配置字段 {name} 的密文无效") from exc
            else:
                value = _PYDANTIC_SENSITIVE_PREFIX + dpapi_encrypt(value)
            data[name] = value

        nested_class = _nested_pydantic_class(field_info.annotation)
        if nested_class is not None and isinstance(value, dict):
            data[name] = _transform_pydantic_sensitive_fields(
                nested_class,
                value,
                decrypt=decrypt,
            )
    return data


def _normalize_pydantic_json_fields(
    config_class: type[BaseModel],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Accept JSON strings left by legacy ConfigBase-backed plugin models."""

    data = copy.deepcopy(payload)
    for name, field_info in config_class.model_fields.items():
        if name not in data:
            continue
        value = data[name]
        extra = field_info.json_schema_extra
        is_json = isinstance(extra, dict) and (
            extra.get("ui_type") == "json" or extra.get("json_type") is not None
        )
        if is_json and isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON 配置字段 {name} 无法解析") from exc
            data[name] = value

        nested_class = _nested_pydantic_class(field_info.annotation)
        if nested_class is not None and isinstance(value, dict):
            data[name] = _normalize_pydantic_json_fields(nested_class, value)
    return data


def _normalize_json_fields_for_storage(
    config_class: type[ConfigBase],
    payload: dict[str, Any],
) -> dict[str, Any]:
    data = copy.deepcopy(payload or {})
    config = config_class()
    for group, items in config._config_item_index.items():
        group_data = data.get(group)
        if not isinstance(group_data, dict):
            continue
        for name, item in items.items():
            if not isinstance(item.validator, JSONValidator) or name not in group_data:
                continue
            value = group_data[name]
            if isinstance(value, str):
                continue
            if value is None:
                value = {} if item.validator.type is dict else []
            group_data[name] = json.dumps(value, ensure_ascii=False)
    return data


def _normalize_json_fields_for_form(
    config_class: type[ConfigBase],
    payload: dict[str, Any],
) -> dict[str, Any]:
    data = copy.deepcopy(payload or {})
    config = config_class()
    for group, items in config._config_item_index.items():
        group_data = data.get(group)
        if not isinstance(group_data, dict):
            continue
        for name, item in items.items():
            if not isinstance(item.validator, JSONValidator):
                continue
            raw_value = group_data.get(name)
            if not isinstance(raw_value, str):
                continue
            try:
                group_data[name] = json.loads(raw_value)
            except json.JSONDecodeError:
                group_data[name] = {} if item.validator.type is dict else []
    return data


def _strip_virtual_fields_for_storage(
    config_class: type[ConfigBase],
    payload: dict[str, Any],
) -> dict[str, Any]:
    data = copy.deepcopy(payload or {})
    field_groups = getattr(config_class, "_field_groups", ())
    for group in field_groups:
        group_data = data.get(group.key)
        if not isinstance(group_data, dict):
            continue
        for field in group.fields:
            if field.virtual_handler is not None:
                group_data.pop(field.name, None)
    return data


async def build_config_model(
    provider: "ScriptTypeProvider",
    raw_payload: Any,
    kind: ConfigKind,
    *,
    from_storage: bool = False,
) -> ConfigBase | BaseModel:
    """从宿主持久化数据构造插件声明的真实配置模型。"""

    config_class = _config_class(provider, kind)
    payload = _coerce_payload(raw_payload)

    if _is_configbase_class(config_class):
        config = config_class()
        await config.load(_normalize_json_fields_for_storage(config_class, payload))
        return config

    if _is_pydantic_class(config_class):
        if from_storage:
            payload = _transform_pydantic_sensitive_fields(
                config_class,
                payload,
                decrypt=True,
            )
            payload = _normalize_pydantic_json_fields(config_class, payload)
        return config_class.model_validate(payload)

    raise TypeError(f"不支持的插件脚本配置类: {config_class!r}")


async def storage_to_form(
    provider: "ScriptTypeProvider",
    raw_payload: Any,
    kind: ConfigKind,
) -> dict[str, Any]:
    """把宿主持久化数据转换成 SchemaForm 使用的表单态数据。"""

    config_class = _config_class(provider, kind)
    model = await build_config_model(
        provider,
        raw_payload,
        kind,
        from_storage=True,
    )

    if isinstance(model, ConfigBase):
        payload = await model.toDict()
        payload.pop("SubConfigsInfo", None)
        return _normalize_json_fields_for_form(config_class, payload)

    return model.model_dump(mode="json")


async def form_to_storage(
    provider: "ScriptTypeProvider",
    form_payload: Any,
    kind: ConfigKind,
) -> dict[str, Any]:
    """把 SchemaForm 表单态数据转换成宿主 PluginData.Config 持久化数据。"""

    model = await build_config_model(provider, form_payload, kind)
    if isinstance(model, ConfigBase):
        payload = await model.toDict(if_decrypt=False)
        return _strip_virtual_fields_for_storage(type(model), payload)
    payload = model.model_dump(mode="json")
    return _transform_pydantic_sensitive_fields(
        type(model),
        payload,
        decrypt=False,
    )
