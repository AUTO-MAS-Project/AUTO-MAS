"""插件系统配置的原生 Config v2 根与 r6 兼容转换。"""

from __future__ import annotations

import json
import re
import uuid
from typing import Annotated, Any
from uuid import UUID

from pydantic import AfterValidator, Field

from app.configuration import (
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    Virtual,
    WireDict,
    collection,
    encrypted,
    virtual_field,
)
from app.configuration.v2.support.security import is_probable_dpapi_ciphertext

LEGACY_ENTRY_TYPE = "PluginInstanceConfig"
V2_ENTRY_TYPE = "PluginInstance"

_PLUGIN_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_@-]*$")
_PLUGIN_INSTANCE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_INFO_DEFAULTS: dict[str, object] = {
    "Plugin": "unknown_plugin",
    "Enabled": True,
    "Name": "插件实例",
}
_DEFAULT_CONFIG_RAW = "{ }"


def _new_plugin_instance_id() -> str:
    """生成与旧 ``PluginInstanceIdValidator`` 默认一致的五位实例号。"""

    return uuid.uuid4().hex[:5]


def _validate_plugin_name(value: str) -> str:
    if not _PLUGIN_NAME_PATTERN.fullmatch(value):
        raise ValueError("Plugin 不符合插件名称格式")
    return value


def _validate_plugin_instance_id(value: str) -> str:
    if not _PLUGIN_INSTANCE_ID_PATTERN.fullmatch(value):
        raise ValueError("Id 不符合插件实例号格式")
    return value


def _validate_json_dict_string(value: str) -> str:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        raise ValueError("ConfigRaw 必须是 JSON 字典字符串") from None
    if not isinstance(parsed, dict):
        raise ValueError("ConfigRaw 必须是 JSON 字典字符串")
    return value


class PluginInstance(ConfigEntry):
    """单个插件实例配置。"""

    class InfoGroup(ConfigGroup):
        # PluginInstance - 插件名称
        Plugin: Annotated[
            str,
            Field(strict=True),
            AfterValidator(_validate_plugin_name),
        ] = "unknown_plugin"
        # PluginInstance - 插件实例号（不含插件名前缀）
        Id: Annotated[
            str,
            Field(strict=True),
            AfterValidator(_validate_plugin_instance_id),
        ] = Field(default_factory=_new_plugin_instance_id)
        # PluginInstance - 是否启用
        Enabled: Annotated[bool, Field(strict=True)] = True
        # PluginInstance - 实例名称
        Name: Annotated[str, Field(strict=True)] = "插件实例"

    class DataGroup(ConfigGroup):
        # PluginInstance - 原始插件配置（DPAPI 加密的 JSON 字典字符串）
        ConfigRaw: Annotated[
            str,
            Field(strict=True),
            AfterValidator(_validate_json_dict_string),
            encrypted(),
        ] = _DEFAULT_CONFIG_RAW
        # PluginInstance - 经插件 schema 校验的前端投影，不参与持久化
        Config: Virtual[str] = None

    Info: InfoGroup = Field(default_factory=InfoGroup)
    Data: DataGroup = Field(default_factory=DataGroup)

    @virtual_field("Data.Config")
    def get_validated_config(self) -> str:
        """返回按插件 schema 补默认值后的逻辑配置 JSON。"""

        try:
            raw = self.Data.ConfigRaw
            raw_config = json.loads(raw) if isinstance(raw, str) else {}
            if not isinstance(raw_config, dict):
                raw_config = {}
        except Exception:
            raw_config = {}

        plugin_name = self.Info.Plugin
        if not isinstance(plugin_name, str) or not plugin_name:
            return json.dumps(raw_config, ensure_ascii=False)

        try:
            from app.plugins.schema import PluginSchemaManager

            schema_manager = PluginSchemaManager()
            schema = schema_manager.load_schema(plugin_name)
            if not schema:
                return json.dumps(raw_config, ensure_ascii=False)
            validated = schema_manager.apply_defaults_and_validate(
                plugin_name,
                raw_config,
            )
            return json.dumps(validated, ensure_ascii=False)
        except Exception:
            return json.dumps(raw_config, ensure_ascii=False)


class PluginInstanceCollection(ConfigCollection[PluginInstance]):
    """``PluginConfig.PluginInstances`` 嵌套集合。"""

    _default_entry_types = (PluginInstance,)


class PluginConfig(ConfigEntry):
    """独立 ``PluginConfig.json`` 生产根。"""

    class DataGroup(ConfigGroup):
        # PluginConfig - 插件配置格式版本
        Version: Annotated[int, Field(strict=True, ge=1, le=9999)] = 1

    Data: DataGroup = Field(default_factory=DataGroup)
    PluginInstances: PluginInstanceCollection = collection(PluginInstance)


def _require_dict(value: object, *, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{path} 必须是对象")
    if not all(isinstance(key, str) for key in value):
        raise TypeError(f"{path} 的键必须是字符串")
    return value


def _parse_uid(value: object, *, path: str) -> tuple[UUID, str]:
    if not isinstance(value, str):
        raise ValueError(f"{path} 必须是 UUID 字符串")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        raise ValueError(f"{path} 不是有效 UUID") from None
    return parsed, str(parsed)


def _normalize_version(value: object, *, path: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 1 <= value <= 9999
    ):
        raise ValueError(f"{path} 必须是 1..9999 的整数")
    return value


def _migration_default_instance_id(uid: UUID) -> str:
    """为缺失的旧动态默认生成稳定、合法的迁移值。"""

    return uid.hex[:5]


def _normalize_info(
    value: object,
    *,
    uid: UUID,
    path: str,
) -> WireDict:
    info = _require_dict(value, path=path)
    allowed = {"Plugin", "Id", "Enabled", "Name"}
    unknown = sorted(set(info) - allowed)
    if unknown:
        raise ValueError(
            "未知插件配置路径: "
            + ", ".join(f"{path}.{name}" for name in unknown)
        )

    normalized = dict(_INFO_DEFAULTS)
    normalized["Id"] = _migration_default_instance_id(uid)
    normalized.update(info)

    for field_name in ("Plugin", "Id", "Name"):
        if not isinstance(normalized[field_name], str):
            raise TypeError(f"{path}.{field_name} 必须是字符串")
    if not isinstance(normalized["Enabled"], bool):
        raise TypeError(f"{path}.Enabled 必须是布尔值")

    _validate_plugin_name(str(normalized["Plugin"]))
    _validate_plugin_instance_id(str(normalized["Id"]))
    return normalized


def _plain_json_dict(value: str, *, path: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        raise ValueError(f"{path} 必须是 JSON 字典字符串") from None
    if not isinstance(parsed, dict):
        raise ValueError(f"{path} 必须是 JSON 字典字符串")
    return parsed


def _config_values_are_logically_equal(first: str, second: str) -> bool:
    if first == second:
        return True
    if is_probable_dpapi_ciphertext(first) or is_probable_dpapi_ciphertext(second):
        return False
    try:
        return _plain_json_dict(first, path="ConfigRaw") == _plain_json_dict(
            second,
            path="Config",
        )
    except ValueError:
        return False


def _normalize_legacy_config_raw(value: object, *, path: str) -> WireDict:
    data = _require_dict(value, path=path)
    allowed = {"ConfigRaw", "Config"}
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValueError(
            "未知插件配置路径: "
            + ", ".join(f"{path}.{name}" for name in unknown)
        )

    raw_present = "ConfigRaw" in data
    alias_present = "Config" in data
    raw = data.get("ConfigRaw", "")
    alias = data.get("Config", "")
    if raw_present and not isinstance(raw, str):
        raise TypeError(f"{path}.ConfigRaw 必须是字符串")
    if alias_present and not isinstance(alias, str):
        raise TypeError(f"{path}.Config 必须是字符串")
    assert isinstance(raw, str) and isinstance(alias, str)

    if raw and alias and not _config_values_are_logically_equal(raw, alias):
        raise ValueError(
            f"{path}.ConfigRaw 与历史别名 {path}.Config 冲突；禁止静默选择"
        )

    selected = raw or alias or _DEFAULT_CONFIG_RAW
    if not is_probable_dpapi_ciphertext(selected):
        _plain_json_dict(selected, path=f"{path}.ConfigRaw")
    return {"ConfigRaw": selected}


def _normalize_v2_config_raw_for_rollback(
    value: object,
    *,
    path: str,
) -> WireDict:
    data = _require_dict(value, path=path)
    unknown = sorted(set(data) - {"ConfigRaw"})
    if unknown:
        raise ValueError(
            "未知插件配置路径: "
            + ", ".join(f"{path}.{name}" for name in unknown)
        )

    raw = data.get("ConfigRaw", "")
    if not isinstance(raw, str):
        raise TypeError(f"{path}.ConfigRaw 必须是字符串")
    if raw and not is_probable_dpapi_ciphertext(raw):
        raise ValueError(
            f"{path}.ConfigRaw 非空时必须为 DPAPI 密文，禁止写入明文"
        )
    return {"ConfigRaw": raw}


def _normalize_legacy_entry(
    value: object,
    *,
    uid: UUID,
    path: str,
) -> WireDict:
    entry = _require_dict(value, path=path)
    unknown = sorted(set(entry) - {"Info", "Data"})
    if unknown:
        raise ValueError(
            "未知插件配置路径: "
            + ", ".join(f"{path}.{name}" for name in unknown)
        )
    return {
        "Info": _normalize_info(entry.get("Info", {}), uid=uid, path=f"{path}.Info"),
        "Data": _normalize_legacy_config_raw(
            entry.get("Data", {}),
            path=f"{path}.Data",
        ),
    }


def _normalize_v2_entry_for_rollback(
    value: object,
    *,
    uid: UUID,
    path: str,
) -> WireDict:
    entry = _require_dict(value, path=path)
    unknown = sorted(set(entry) - {"Info", "Data"})
    if unknown:
        raise ValueError(
            "未知插件配置路径: "
            + ", ".join(f"{path}.{name}" for name in unknown)
        )
    return {
        "Info": _normalize_info(entry.get("Info", {}), uid=uid, path=f"{path}.Info"),
        "Data": _normalize_v2_config_raw_for_rollback(
            entry.get("Data", {}),
            path=f"{path}.Data",
        ),
    }


def _parse_order(
    value: object,
    *,
    expected_type: str,
    path: str,
) -> list[tuple[UUID, str]]:
    if not isinstance(value, list):
        raise TypeError(f"{path} 必须是列表")

    order: list[tuple[UUID, str]] = []
    seen: set[UUID] = set()
    for index, item_value in enumerate(value):
        item_path = f"{path}[{index}]"
        item = _require_dict(item_value, path=item_path)
        unknown = sorted(set(item) - {"uid", "type"})
        if unknown:
            raise ValueError(
                "未知插件配置路径: "
                + ", ".join(f"{item_path}.{name}" for name in unknown)
            )
        if set(item) != {"uid", "type"}:
            raise ValueError(f"{item_path} 必须同时包含 uid 和 type")
        uid, canonical_uid = _parse_uid(item["uid"], path=f"{item_path}.uid")
        if uid in seen:
            raise ValueError(f"{path} 包含重复 uid")
        if item["type"] != expected_type:
            raise ValueError(f"{item_path}.type 仅允许 {expected_type}")
        seen.add(uid)
        order.append((uid, canonical_uid))
    return order


def _parse_data_index(
    value: object,
    *,
    path: str,
) -> dict[UUID, tuple[str, object]]:
    raw = _require_dict(value, path=path)
    data: dict[UUID, tuple[str, object]] = {}
    for raw_uid, entry in raw.items():
        uid, canonical_uid = _parse_uid(raw_uid, path=f"{path} key")
        if uid in data:
            raise ValueError(f"{path} 包含重复 uid")
        data[uid] = (canonical_uid, entry)
    return data


def _parse_legacy_collection(
    value: object,
) -> tuple[list[tuple[UUID, str]], dict[UUID, tuple[str, object]]]:
    collection_data = _require_dict(value, path="$.SubConfigsInfo.PluginInstances")
    order = _parse_order(
        collection_data.get("instances", []),
        expected_type=LEGACY_ENTRY_TYPE,
        path="$.SubConfigsInfo.PluginInstances.instances",
    )

    raw_data = {
        key: item for key, item in collection_data.items() if key != "instances"
    }
    data = _parse_data_index(
        raw_data,
        path="$.SubConfigsInfo.PluginInstances",
    )
    if {uid for uid, _ in order} != set(data):
        raise ValueError(
            "$.SubConfigsInfo.PluginInstances 包含缺失或孤儿 uid"
        )
    return order, data


def _parse_v2_collection(
    value: object,
) -> tuple[list[tuple[UUID, str]], dict[UUID, tuple[str, object]]]:
    collection_data = _require_dict(value, path="$.PluginInstances")
    unknown = sorted(set(collection_data) - {"order", "data"})
    if unknown:
        raise ValueError(
            "未知插件配置路径: "
            + ", ".join(f"$.PluginInstances.{name}" for name in unknown)
        )
    order = _parse_order(
        collection_data.get("order", []),
        expected_type=V2_ENTRY_TYPE,
        path="$.PluginInstances.order",
    )
    data = _parse_data_index(
        collection_data.get("data", {}),
        path="$.PluginInstances.data",
    )
    if {uid for uid, _ in order} != set(data):
        raise ValueError("$.PluginInstances.order 与 data 包含缺失或孤儿 uid")
    return order, data


def legacy_plugin_config_to_wire(legacy_data: object) -> WireDict:
    """将 r6 ``PluginConfig.json`` 纯转换为 Config v2 Wire。

    转换保留成员顺序、UUID、配置文本与密文；只兼容 ``Data.Config`` 到
    ``Data.ConfigRaw`` 的历史别名。未知字段、孤儿、重复 UUID、非法类型、
    非字典 JSON 或双字段冲突均 fail-closed。
    """

    root = _require_dict(legacy_data, path="$")
    unknown_root = sorted(set(root) - {"Data", "SubConfigsInfo"})
    if unknown_root:
        raise ValueError(
            "未知插件配置路径: "
            + ", ".join(f"$.{name}" for name in unknown_root)
        )

    root_data = _require_dict(root.get("Data", {}), path="$.Data")
    unknown_data = sorted(set(root_data) - {"Version"})
    if unknown_data:
        raise ValueError(
            "未知插件配置路径: "
            + ", ".join(f"$.Data.{name}" for name in unknown_data)
        )
    version = _normalize_version(root_data.get("Version", 1), path="$.Data.Version")

    sub_configs = _require_dict(
        root.get("SubConfigsInfo", {}),
        path="$.SubConfigsInfo",
    )
    unknown_sub_configs = sorted(set(sub_configs) - {"PluginInstances"})
    if unknown_sub_configs:
        raise ValueError(
            "未知插件配置路径: "
            + ", ".join(
                f"$.SubConfigsInfo.{name}" for name in unknown_sub_configs
            )
        )
    order, data = _parse_legacy_collection(
        sub_configs.get("PluginInstances", {}),
    )

    wire_data: dict[str, WireDict] = {}
    for uid, canonical_uid in order:
        _, value = data[uid]
        wire_data[canonical_uid] = _normalize_legacy_entry(
            value,
            uid=uid,
            path=f"$.SubConfigsInfo.PluginInstances.{canonical_uid}",
        )

    return {
        "Data": {"Version": version},
        "PluginInstances": {
            "order": [
                {"uid": canonical_uid, "type": V2_ENTRY_TYPE}
                for _, canonical_uid in order
            ],
            "data": wire_data,
        },
    }


def plugin_config_wire_to_legacy(wire_data: object) -> dict[str, Any]:
    """将 Config v2 Wire 纯转换为可回滚的 r6 ``PluginConfig.json``。

    ``Data.Config`` 为虚拟字段，绝不进入 rollback。非空 ``ConfigRaw`` 必须
    已是 DPAPI 密文，函数不会把明文插件配置写入旧根。
    """

    root = _require_dict(wire_data, path="$")
    unknown_root = sorted(set(root) - {"Data", "PluginInstances"})
    if unknown_root:
        raise ValueError(
            "未知插件配置路径: "
            + ", ".join(f"$.{name}" for name in unknown_root)
        )

    root_data = _require_dict(root.get("Data", {}), path="$.Data")
    unknown_data = sorted(set(root_data) - {"Version"})
    if unknown_data:
        raise ValueError(
            "未知插件配置路径: "
            + ", ".join(f"$.Data.{name}" for name in unknown_data)
        )
    version = _normalize_version(root_data.get("Version", 1), path="$.Data.Version")
    order, data = _parse_v2_collection(root.get("PluginInstances", {}))

    legacy_collection: dict[str, Any] = {"instances": []}
    for uid, canonical_uid in order:
        _, value = data[uid]
        normalized = _normalize_v2_entry_for_rollback(
            value,
            uid=uid,
            path=f"$.PluginInstances.data.{canonical_uid}",
        )
        legacy_collection["instances"].append(
            {"uid": canonical_uid, "type": LEGACY_ENTRY_TYPE}
        )
        legacy_collection[canonical_uid] = normalized

    return {
        "Data": {"Version": version},
        "SubConfigsInfo": {"PluginInstances": legacy_collection},
    }


__all__ = [
    "PluginConfig",
    "PluginInstance",
    "PluginInstanceCollection",
    "legacy_plugin_config_to_wire",
    "plugin_config_wire_to_legacy",
]
