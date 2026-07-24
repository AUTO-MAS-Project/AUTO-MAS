"""模拟器配置的原生 Config v2 根与 r6 兼容转换。"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, Field

from app.configuration import ConfigCollection, ConfigEntry, ConfigGroup, WireDict

LEGACY_ENTRY_TYPE = "EmulatorConfig"
V2_ENTRY_TYPE = "Emulator"

_INFO_DEFAULTS: dict[str, object] = {
    "Name": "新模拟器",
    "Type": "general",
    "Path": "",
    "BossKey": "[ ]",
    "MaxWaitTime": 300,
    "ForceKillOnClose": True,
}
_LEGACY_DATA_ALIASES = frozenset({"Type", "BossKey", "MaxWaitTime"})


def _validate_boss_key(value: str) -> str:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        raise ValueError("BossKey 必须是 JSON 列表字符串") from None
    if not isinstance(parsed, list):
        raise ValueError("BossKey 必须是 JSON 列表字符串")
    return value


class Emulator(ConfigEntry):
    """单个模拟器配置。"""

    class InfoGroup(ConfigGroup):
        Name: Annotated[str, Field(strict=True)] = "新模拟器"
        Type: Literal["general", "mumu", "ldplayer"] = "general"
        # 路径是否存在由模拟器发现/操作链验证。迁移层必须原样保留离线、
        # 已卸载或盘符暂不可用的历史路径，不能在配置激活时静默清空。
        Path: Annotated[str, Field(strict=True)] = ""
        BossKey: Annotated[
            str,
            Field(strict=True),
            AfterValidator(_validate_boss_key),
        ] = "[ ]"
        MaxWaitTime: Annotated[
            int,
            Field(strict=True, ge=1, le=9999),
        ] = 300
        ForceKillOnClose: Annotated[bool, Field(strict=True)] = True

    Info: InfoGroup = Field(default_factory=InfoGroup)


class Emulators(ConfigCollection[Emulator]):
    """独立 ``EmulatorConfig`` 生产根。"""

    _default_entry_types = (Emulator,)


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


def _validate_info_types(info: dict[str, object], *, path: str) -> None:
    for field_name in ("Name", "Type", "Path", "BossKey"):
        if not isinstance(info[field_name], str):
            raise TypeError(f"{path}.{field_name} 必须是字符串")
    if info["Type"] not in {"general", "mumu", "ldplayer"}:
        raise ValueError(
            f"{path}.Type 仅允许 general、mumu 或 ldplayer"
        )
    _validate_boss_key(str(info["BossKey"]))
    max_wait_time = info["MaxWaitTime"]
    if (
        not isinstance(max_wait_time, int)
        or isinstance(max_wait_time, bool)
        or not 1 <= max_wait_time <= 9999
    ):
        raise ValueError(f"{path}.MaxWaitTime 必须是 1..9999 的整数")
    if not isinstance(info["ForceKillOnClose"], bool):
        raise TypeError(f"{path}.ForceKillOnClose 必须是布尔值")


def _normalize_legacy_entry(value: object, *, path: str) -> WireDict:
    """规范化一个 r6 EmulatorConfig，兼容更早的 Data 字段别名。"""

    entry = _require_dict(value, path=path)
    unknown_groups = sorted(set(entry) - {"Info", "Data"})
    if unknown_groups:
        raise ValueError(
            "未知模拟器配置路径: "
            + ", ".join(f"{path}.{name}" for name in unknown_groups)
        )

    raw_info = _require_dict(entry.get("Info", {}), path=f"{path}.Info")
    raw_data = _require_dict(entry.get("Data", {}), path=f"{path}.Data")
    unknown_info = sorted(set(raw_info) - set(_INFO_DEFAULTS))
    unknown_data = sorted(set(raw_data) - _LEGACY_DATA_ALIASES)
    if unknown_info or unknown_data:
        paths = [
            *(f"{path}.Info.{name}" for name in unknown_info),
            *(f"{path}.Data.{name}" for name in unknown_data),
        ]
        raise ValueError("未知模拟器配置路径: " + ", ".join(paths))

    normalized = dict(_INFO_DEFAULTS)
    for field_name in _INFO_DEFAULTS:
        if field_name in raw_info:
            normalized[field_name] = raw_info[field_name]
        elif field_name in _LEGACY_DATA_ALIASES and field_name in raw_data:
            normalized[field_name] = raw_data[field_name]

    for field_name in _LEGACY_DATA_ALIASES:
        if (
            field_name in raw_info
            and field_name in raw_data
            and raw_info[field_name] != raw_data[field_name]
        ):
            raise ValueError(
                f"{path}.Info.{field_name} 与历史 Data.{field_name} 冲突；"
                "禁止静默选择"
            )

    _validate_info_types(normalized, path=f"{path}.Info")
    return {"Info": normalized}


def _normalize_v2_entry(value: object, *, path: str) -> WireDict:
    entry = _require_dict(value, path=path)
    unknown_groups = sorted(set(entry) - {"Info"})
    if unknown_groups:
        raise ValueError(
            "未知模拟器配置路径: "
            + ", ".join(f"{path}.{name}" for name in unknown_groups)
        )
    raw_info = _require_dict(entry.get("Info", {}), path=f"{path}.Info")
    unknown_info = sorted(set(raw_info) - set(_INFO_DEFAULTS))
    if unknown_info:
        raise ValueError(
            "未知模拟器配置路径: "
            + ", ".join(f"{path}.Info.{name}" for name in unknown_info)
        )
    normalized = dict(_INFO_DEFAULTS)
    normalized.update(raw_info)
    _validate_info_types(normalized, path=f"{path}.Info")
    return {"Info": normalized}


def legacy_emulators_to_wire(legacy_data: object) -> WireDict:
    """将 r6 ``EmulatorConfig.json`` 纯转换为 Config v2 Wire。

    保留成员顺序和 UUID；兼容旧 ``Data.Type/BossKey/MaxWaitTime``，但
    新旧位置同时存在且不一致时 fail-closed。未知字段、孤儿数据、重复
    UUID、非法类型和值均不会被静默纠正。
    """

    root = _require_dict(legacy_data, path="$")
    raw_order = root.get("instances", [])
    if not isinstance(raw_order, list):
        raise TypeError("$.instances 必须是列表")

    order: list[tuple[UUID, str, str]] = []
    seen_uids: set[UUID] = set()
    raw_uid_keys: set[str] = set()
    for index, item_value in enumerate(raw_order):
        item_path = f"$.instances[{index}]"
        item = _require_dict(item_value, path=item_path)
        unknown = sorted(set(item) - {"uid", "type"})
        if unknown:
            raise ValueError(
                "未知模拟器配置路径: "
                + ", ".join(f"{item_path}.{name}" for name in unknown)
            )
        if set(item) != {"uid", "type"}:
            raise ValueError(f"{item_path} 必须同时包含 uid 和 type")
        parsed_uid, canonical_uid = _parse_uid(
            item["uid"], path=f"{item_path}.uid"
        )
        if parsed_uid in seen_uids:
            raise ValueError("$.instances 包含重复 uid")
        if item["type"] != LEGACY_ENTRY_TYPE:
            raise ValueError(
                f"{item_path}.type 仅允许 {LEGACY_ENTRY_TYPE}"
            )
        seen_uids.add(parsed_uid)
        raw_uid = str(item["uid"])
        raw_uid_keys.add(raw_uid)
        order.append((parsed_uid, canonical_uid, raw_uid))

    unknown_root = sorted(set(root) - {"instances"} - raw_uid_keys)
    if unknown_root:
        raise ValueError(
            "$ 包含孤儿或未知字段: " + ", ".join(unknown_root)
        )
    missing = [raw_uid for _, _, raw_uid in order if raw_uid not in root]
    if missing:
        raise ValueError("$.instances 引用了缺失的数据项")

    return {
        "order": [
            {"uid": canonical_uid, "type": V2_ENTRY_TYPE}
            for _, canonical_uid, _ in order
        ],
        "data": {
            canonical_uid: _normalize_legacy_entry(
                root[raw_uid],
                path=f"$.{raw_uid}",
            )
            for _, canonical_uid, raw_uid in order
        },
    }


def emulators_wire_to_legacy(wire_data: object) -> dict[str, Any]:
    """将 Config v2 Wire 纯转换为可回滚的 r6 JSON 形状。"""

    root = _require_dict(wire_data, path="$")
    unknown_root = sorted(set(root) - {"order", "data"})
    if unknown_root:
        raise ValueError(
            "未知模拟器配置路径: "
            + ", ".join(f"$.{name}" for name in unknown_root)
        )
    raw_order = root.get("order", [])
    raw_data = _require_dict(root.get("data", {}), path="$.data")
    if not isinstance(raw_order, list):
        raise TypeError("$.order 必须是列表")

    seen_uids: set[UUID] = set()
    ordered_uids: list[tuple[UUID, str]] = []
    for index, item_value in enumerate(raw_order):
        item_path = f"$.order[{index}]"
        item = _require_dict(item_value, path=item_path)
        unknown = sorted(set(item) - {"uid", "type"})
        if unknown:
            raise ValueError(
                "未知模拟器配置路径: "
                + ", ".join(f"{item_path}.{name}" for name in unknown)
            )
        if set(item) != {"uid", "type"}:
            raise ValueError(f"{item_path} 必须同时包含 uid 和 type")
        parsed_uid, canonical_uid = _parse_uid(
            item["uid"], path=f"{item_path}.uid"
        )
        if parsed_uid in seen_uids:
            raise ValueError("$.order 包含重复 uid")
        if item["type"] != V2_ENTRY_TYPE:
            raise ValueError(f"{item_path}.type 仅允许 {V2_ENTRY_TYPE}")
        seen_uids.add(parsed_uid)
        ordered_uids.append((parsed_uid, canonical_uid))

    data_by_uid: dict[UUID, tuple[str, object]] = {}
    for raw_uid, value in raw_data.items():
        parsed_uid, canonical_uid = _parse_uid(raw_uid, path="$.data key")
        if parsed_uid in data_by_uid:
            raise ValueError("$.data 包含重复 uid")
        data_by_uid[parsed_uid] = (canonical_uid, value)
    if seen_uids != set(data_by_uid):
        raise ValueError("$.order 与 $.data 包含缺失或孤儿 uid")

    legacy: dict[str, Any] = {"instances": []}
    for parsed_uid, canonical_uid in ordered_uids:
        _, value = data_by_uid[parsed_uid]
        normalized = _normalize_v2_entry(
            value,
            path=f"$.data.{canonical_uid}",
        )
        legacy["instances"].append(
            {"uid": canonical_uid, "type": LEGACY_ENTRY_TYPE}
        )
        legacy[canonical_uid] = normalized
    return legacy


__all__ = [
    "Emulator",
    "Emulators",
    "emulators_wire_to_legacy",
    "legacy_emulators_to_wire",
]
