"""游戏签到账号的原生 Config v2 根与 r6 兼容转换。"""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import AfterValidator, Field

from app.configuration import (
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    WireDict,
    encrypted,
)
from app.configuration.v2.support.security import is_probable_dpapi_ciphertext

LEGACY_ENTRY_TYPE = "GameSignAccountGroup"
V2_ENTRY_TYPE = "GameSignAccount"
LEGACY_GROUP_NAME = "GameSignAccount"
LEGACY_EMBEDDED_COLLECTION_NAME = "GameSign_Accounts"

_FIELD_DEFAULTS: dict[str, object] = {
    "Name": "用户 1",
    "Enabled": True,
    "MiyousheToken": "",
    "KuroToken": "",
    "SklandToken": "",
    "LastSignDate": "2000-01-01",
}
_SECRET_FIELDS = ("MiyousheToken", "KuroToken", "SklandToken")


class GameSignAccountsOwnershipConflictError(ValueError):
    """独立根与 ToolsConfig 历史嵌入根存在歧义。"""


def _validate_ymd(value: str) -> str:
    """校验旧 ``DateTimeValidator("%Y-%m-%d")`` 接受的日期格式。"""
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValueError("LastSignDate 必须使用 YYYY-MM-DD 格式") from None
    return value


class GameSignAccount(ConfigEntry):
    """单个游戏签到账号。"""

    class Account(ConfigGroup):
        # GameSignAccount - 账号组名称
        Name: Annotated[str, Field(strict=True)] = "用户 1"
        # GameSignAccount - 是否启用
        Enabled: Annotated[bool, Field(strict=True)] = True
        # GameSignAccount - 米游社登录凭证（DPAPI 加密）
        MiyousheToken: Annotated[str, Field(strict=True), encrypted()] = ""
        # GameSignAccount - 库街区登录凭证（DPAPI 加密）
        KuroToken: Annotated[str, Field(strict=True), encrypted()] = ""
        # GameSignAccount - 森空岛登录凭证（DPAPI 加密）
        SklandToken: Annotated[str, Field(strict=True), encrypted()] = ""
        # GameSignAccount - 上次签到日期
        LastSignDate: Annotated[
            str,
            Field(strict=True),
            AfterValidator(_validate_ymd),
        ] = "2000-01-01"

    GameSignAccount: Account = Field(default_factory=Account)


class GameSignAccounts(ConfigCollection[GameSignAccount]):
    """独立 ``GameSignAccounts`` 生产根。"""

    _default_entry_types = (GameSignAccount,)


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


def _validate_secret_boundary(value: str, *, path: str) -> None:
    if value and not is_probable_dpapi_ciphertext(value):
        raise ValueError(f"{path} 必须为空或为 DPAPI 密文")


def _normalize_account_payload(value: object, *, path: str) -> WireDict:
    entry = _require_dict(value, path=path)
    unknown_groups = sorted(set(entry) - {LEGACY_GROUP_NAME})
    if unknown_groups:
        raise ValueError(
            "未知游戏签到配置路径: "
            + ", ".join(f"{path}.{name}" for name in unknown_groups)
        )

    raw_group = entry.get(LEGACY_GROUP_NAME, {})
    group = _require_dict(raw_group, path=f"{path}.{LEGACY_GROUP_NAME}")
    unknown_fields = sorted(set(group) - set(_FIELD_DEFAULTS))
    if unknown_fields:
        raise ValueError(
            "未知游戏签到配置路径: "
            + ", ".join(
                f"{path}.{LEGACY_GROUP_NAME}.{name}" for name in unknown_fields
            )
        )

    normalized = dict(_FIELD_DEFAULTS)
    normalized.update(group)

    string_fields = (
        "Name",
        "MiyousheToken",
        "KuroToken",
        "SklandToken",
        "LastSignDate",
    )
    for field_name in string_fields:
        if not isinstance(normalized[field_name], str):
            raise TypeError(
                f"{path}.{LEGACY_GROUP_NAME}.{field_name} 必须是字符串"
            )
    if not isinstance(normalized["Enabled"], bool):
        raise TypeError(f"{path}.{LEGACY_GROUP_NAME}.Enabled 必须是布尔值")

    _validate_ymd(str(normalized["LastSignDate"]))
    for field_name in _SECRET_FIELDS:
        _validate_secret_boundary(
            str(normalized[field_name]),
            path=f"{path}.{LEGACY_GROUP_NAME}.{field_name}",
        )

    return {LEGACY_GROUP_NAME: normalized}


def _parse_collection(
    payload: object,
    *,
    order_key: str,
    expected_type: str,
    path: str,
) -> tuple[list[tuple[str, str]], dict[str, WireDict]]:
    root = _require_dict(payload, path=path)
    raw_order = root.get(order_key, [])
    if not isinstance(raw_order, list):
        raise TypeError(f"{path}.{order_key} 必须是列表")

    order: list[tuple[str, str]] = []
    seen_uids: set[UUID] = set()
    raw_uid_keys: set[str] = set()
    for index, item_value in enumerate(raw_order):
        item_path = f"{path}.{order_key}[{index}]"
        item = _require_dict(item_value, path=item_path)
        unknown_item_fields = sorted(set(item) - {"uid", "type"})
        if unknown_item_fields:
            raise ValueError(
                "未知游戏签到配置路径: "
                + ", ".join(f"{item_path}.{name}" for name in unknown_item_fields)
            )
        if set(item) != {"uid", "type"}:
            raise ValueError(f"{item_path} 必须同时包含 uid 和 type")

        parsed_uid, canonical_uid = _parse_uid(item["uid"], path=f"{item_path}.uid")
        if parsed_uid in seen_uids:
            raise ValueError(f"{path}.{order_key} 包含重复 uid")
        if item["type"] != expected_type:
            raise ValueError(f"{item_path}.type 仅允许 {expected_type}")

        seen_uids.add(parsed_uid)
        raw_uid_keys.add(str(item["uid"]))
        order.append((canonical_uid, str(item["uid"])))

    unknown_root_keys = sorted(set(root) - {order_key} - raw_uid_keys)
    if unknown_root_keys:
        raise ValueError(
            f"{path} 包含孤儿或未知字段: " + ", ".join(unknown_root_keys)
        )
    missing = [raw_uid for _, raw_uid in order if raw_uid not in root]
    if missing:
        raise ValueError(f"{path} 缺少 order 引用的数据项")

    data: dict[str, WireDict] = {}
    for canonical_uid, raw_uid in order:
        data[canonical_uid] = _normalize_account_payload(
            root[raw_uid],
            path=f"{path}.{raw_uid}",
        )
    return order, data


def legacy_game_sign_accounts_to_wire(legacy_data: object) -> WireDict:
    """将独立 r6 ``GameSignAccounts.json`` 纯转换为 Config v2 Wire。

    转换只接受 ``GameSignAccountGroup``，保留顺序、UUID 与密文；未知字段、
    孤儿数据、重复/非法 UUID 或非法类型都会 fail-closed。缺失的已知字段
    使用 r6 ``GameSignAccountGroup`` 默认值。
    """

    order, data = _parse_collection(
        legacy_data,
        order_key="instances",
        expected_type=LEGACY_ENTRY_TYPE,
        path="$",
    )
    return {
        "order": [
            {"uid": canonical_uid, "type": V2_ENTRY_TYPE}
            for canonical_uid, _ in order
        ],
        "data": data,
    }


def game_sign_accounts_wire_to_legacy(wire_data: object) -> dict[str, Any]:
    """将 Config v2 Wire 纯转换为可回滚的 r6 JSON 形状。

    非空 token 必须已经是 DPAPI 密文；函数不会将明文写入 rollback 数据。
    """

    root = _require_dict(wire_data, path="$")
    unknown_root = sorted(set(root) - {"order", "data"})
    if unknown_root:
        raise ValueError(
            "未知游戏签到配置路径: "
            + ", ".join(f"$.{name}" for name in unknown_root)
        )
    raw_order = root.get("order", [])
    raw_data = root.get("data", {})
    if not isinstance(raw_order, list):
        raise TypeError("$.order 必须是列表")
    data = _require_dict(raw_data, path="$.data")

    legacy_shape: dict[str, Any] = {"instances": []}
    seen_uids: set[UUID] = set()
    ordered_uids: list[str] = []
    for index, item_value in enumerate(raw_order):
        item_path = f"$.order[{index}]"
        item = _require_dict(item_value, path=item_path)
        unknown_item_fields = sorted(set(item) - {"uid", "type"})
        if unknown_item_fields:
            raise ValueError(
                "未知游戏签到配置路径: "
                + ", ".join(f"{item_path}.{name}" for name in unknown_item_fields)
            )
        if set(item) != {"uid", "type"}:
            raise ValueError(f"{item_path} 必须同时包含 uid 和 type")

        parsed_uid, canonical_uid = _parse_uid(item["uid"], path=f"{item_path}.uid")
        if parsed_uid in seen_uids:
            raise ValueError("$.order 包含重复 uid")
        if item["type"] != V2_ENTRY_TYPE:
            raise ValueError(f"{item_path}.type 仅允许 {V2_ENTRY_TYPE}")
        seen_uids.add(parsed_uid)
        ordered_uids.append(canonical_uid)

    data_by_uid: dict[UUID, tuple[str, object]] = {}
    for raw_uid, value in data.items():
        parsed_uid, canonical_uid = _parse_uid(raw_uid, path="$.data key")
        if parsed_uid in data_by_uid:
            raise ValueError("$.data 包含重复 uid")
        data_by_uid[parsed_uid] = (canonical_uid, value)

    order_uid_set = seen_uids
    data_uid_set = set(data_by_uid)
    if order_uid_set != data_uid_set:
        raise ValueError("$.order 与 $.data 包含缺失或孤儿 uid")

    for canonical_uid in ordered_uids:
        parsed_uid = UUID(canonical_uid)
        _, value = data_by_uid[parsed_uid]
        normalized = _normalize_account_payload(
            value,
            path=f"$.data.{canonical_uid}",
        )
        legacy_shape["instances"].append(
            {"uid": canonical_uid, "type": LEGACY_ENTRY_TYPE}
        )
        legacy_shape[canonical_uid] = normalized
    return legacy_shape


def get_embedded_game_sign_accounts(
    tools_config_legacy: object | None,
) -> dict[str, Any] | None:
    """只读提取 ``ToolsConfig.SubConfigsInfo.GameSign_Accounts`` 历史副本。"""

    if tools_config_legacy is None:
        return None
    tools = _require_dict(tools_config_legacy, path="$.ToolsConfig")
    if "SubConfigsInfo" not in tools:
        return None
    sub_configs = _require_dict(
        tools["SubConfigsInfo"],
        path="$.ToolsConfig.SubConfigsInfo",
    )
    if LEGACY_EMBEDDED_COLLECTION_NAME not in sub_configs:
        return None
    embedded = _require_dict(
        sub_configs[LEGACY_EMBEDDED_COLLECTION_NAME],
        path=(
            "$.ToolsConfig.SubConfigsInfo."
            f"{LEGACY_EMBEDDED_COLLECTION_NAME}"
        ),
    )
    return copy.deepcopy(embedded)


def assert_game_sign_accounts_ownership_consistent(
    *,
    standalone_legacy: object | None,
    tools_config_legacy: object | None,
) -> None:
    """检查独立根与 ToolsConfig 历史嵌入根是否存在双归属冲突。

    ``GameSignAccounts.json`` 始终是历史运行时最终权威源。函数只做检查，
    不选择、不合并也不写入。两份根均非空且规范化后的逻辑或密文结构不
    同时抛出异常，要求调用方执行人工选择。
    """

    standalone_wire = (
        legacy_game_sign_accounts_to_wire(standalone_legacy)
        if standalone_legacy is not None
        else {"order": [], "data": {}}
    )
    embedded_legacy = get_embedded_game_sign_accounts(tools_config_legacy)
    embedded_wire = (
        legacy_game_sign_accounts_to_wire(embedded_legacy)
        if embedded_legacy is not None
        else {"order": [], "data": {}}
    )

    standalone_non_empty = bool(standalone_wire["order"])
    embedded_non_empty = bool(embedded_wire["order"])
    if (
        standalone_non_empty
        and embedded_non_empty
        and standalone_wire != embedded_wire
    ):
        raise GameSignAccountsOwnershipConflictError(
            "GameSignAccounts.json 与 "
            "ToolsConfig.SubConfigsInfo.GameSign_Accounts 均非空且内容不同；"
            "禁止自动覆盖，必须人工选择"
        )


__all__ = [
    "GameSignAccount",
    "GameSignAccounts",
    "GameSignAccountsOwnershipConflictError",
    "assert_game_sign_accounts_ownership_consistent",
    "game_sign_accounts_wire_to_legacy",
    "get_embedded_game_sign_accounts",
    "legacy_game_sign_accounts_to_wire",
]
