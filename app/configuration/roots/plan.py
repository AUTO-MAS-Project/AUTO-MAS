"""MAA 计划表的原生 Config v2 根与 r6 兼容转换。"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from pydantic import Field

from app.configuration import ConfigCollection, ConfigEntry, ConfigGroup, WireDict

LEGACY_ENTRY_TYPE = "MaaPlanConfig"
V2_ENTRY_TYPE = "MaaPlan"

WEEKDAYS = tuple(calendar.day_name)
PLAN_GROUPS = ("ALL", *WEEKDAYS)
PLAN_FIELDS = (
    "MedicineNumb",
    "SeriesNumb",
    "Stage",
    "Stage_1",
    "Stage_2",
    "Stage_3",
    "Stage_Remain",
)

SeriesNumber = Literal["0", "6", "5", "4", "3", "2", "1", "-1"]
PlanFieldName = Literal[
    "MedicineNumb",
    "SeriesNumb",
    "Stage",
    "Stage_1",
    "Stage_2",
    "Stage_3",
    "Stage_Remain",
]

_UTC4 = timezone(timedelta(hours=4))
_INFO_DEFAULTS: dict[str, object] = {
    "Name": "新 MAA 计划表",
    "Mode": "ALL",
}
_PLAN_DEFAULTS: dict[str, object] = {
    "MedicineNumb": 0,
    "SeriesNumb": "0",
    "Stage": "-",
    "Stage_1": "-",
    "Stage_2": "-",
    "Stage_3": "-",
    "Stage_Remain": "-",
}
_SERIES_NUMBERS = frozenset({"0", "6", "5", "4", "3", "2", "1", "-1"})


class MaaPlan(ConfigEntry):
    """单个 MAA 计划表配置。"""

    class InfoGroup(ConfigGroup):
        Name: Annotated[str, Field(strict=True)] = "新 MAA 计划表"
        Mode: Literal["ALL", "Weekly"] = "ALL"

    class PlanGroup(ConfigGroup):
        MedicineNumb: Annotated[
            int,
            Field(strict=True, ge=0, le=9999),
        ] = 0
        SeriesNumb: SeriesNumber = "0"
        Stage: Annotated[str, Field(strict=True)] = "-"
        Stage_1: Annotated[str, Field(strict=True)] = "-"
        Stage_2: Annotated[str, Field(strict=True)] = "-"
        Stage_3: Annotated[str, Field(strict=True)] = "-"
        Stage_Remain: Annotated[str, Field(strict=True)] = "-"

    Info: InfoGroup = Field(default_factory=InfoGroup)
    ALL: PlanGroup = Field(default_factory=PlanGroup)
    Monday: PlanGroup = Field(default_factory=PlanGroup)
    Tuesday: PlanGroup = Field(default_factory=PlanGroup)
    Wednesday: PlanGroup = Field(default_factory=PlanGroup)
    Thursday: PlanGroup = Field(default_factory=PlanGroup)
    Friday: PlanGroup = Field(default_factory=PlanGroup)
    Saturday: PlanGroup = Field(default_factory=PlanGroup)
    Sunday: PlanGroup = Field(default_factory=PlanGroup)

    def get_current_group(self, *, weekday: str | None = None) -> PlanGroup:
        """按计划模式返回当前配置组。

        ``weekday`` 使用 ``calendar.day_name`` 的英文名称。调用方可显式传入
        星期以避免测试或 dry-run 依赖系统时间；省略时保持 r6 的 UTC+4
        选择语义。
        """

        if self.Info.Mode == "ALL":
            return self.ALL

        current_weekday = (
            weekday
            if weekday is not None
            else datetime.now(tz=_UTC4).strftime("%A")
        )
        if current_weekday not in WEEKDAYS:
            raise ValueError(
                "weekday 仅允许 calendar.day_name 中的英文星期名称"
            )
        return cast(MaaPlan.PlanGroup, getattr(self, current_weekday))

    def get_current_info(
        self,
        name: PlanFieldName,
        *,
        weekday: str | None = None,
    ) -> int | str:
        """读取 ALL 或指定星期的一个计划字段值。"""

        if name not in PLAN_FIELDS:
            raise KeyError(f"未知 MAA 计划字段: {name}")
        return cast(
            int | str,
            getattr(self.get_current_group(weekday=weekday), name),
        )


class Plans(ConfigCollection[MaaPlan]):
    """独立 ``PlanConfig.json`` 生产根。"""

    _default_entry_types = (MaaPlan,)


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


def _validate_info(info: dict[str, object], *, path: str) -> None:
    if not isinstance(info["Name"], str):
        raise TypeError(f"{path}.Name 必须是字符串")
    mode = info["Mode"]
    if not isinstance(mode, str) or mode not in {"ALL", "Weekly"}:
        raise ValueError(f"{path}.Mode 仅允许 ALL 或 Weekly")


def _validate_plan_group(group: dict[str, object], *, path: str) -> None:
    medicine = group["MedicineNumb"]
    if (
        not isinstance(medicine, int)
        or isinstance(medicine, bool)
        or not 0 <= medicine <= 9999
    ):
        raise ValueError(f"{path}.MedicineNumb 必须是 0..9999 的整数")

    series = group["SeriesNumb"]
    if not isinstance(series, str) or series not in _SERIES_NUMBERS:
        raise ValueError(
            f"{path}.SeriesNumb 仅允许 0、6、5、4、3、2、1 或 -1"
        )

    for name in PLAN_FIELDS[2:]:
        if not isinstance(group[name], str):
            raise TypeError(f"{path}.{name} 必须是字符串")


def _normalize_entry(value: object, *, path: str) -> WireDict:
    entry = _require_dict(value, path=path)
    allowed_groups = {"Info", *PLAN_GROUPS}
    unknown_groups = sorted(set(entry) - allowed_groups)
    if unknown_groups:
        raise ValueError(
            "未知 MAA 计划配置路径: "
            + ", ".join(f"{path}.{name}" for name in unknown_groups)
        )

    raw_info = _require_dict(entry.get("Info", {}), path=f"{path}.Info")
    unknown_info = sorted(set(raw_info) - set(_INFO_DEFAULTS))
    if unknown_info:
        raise ValueError(
            "未知 MAA 计划配置路径: "
            + ", ".join(f"{path}.Info.{name}" for name in unknown_info)
        )
    info = dict(_INFO_DEFAULTS)
    info.update(raw_info)
    _validate_info(info, path=f"{path}.Info")

    normalized: WireDict = {"Info": info}
    for group_name in PLAN_GROUPS:
        raw_group = _require_dict(
            entry.get(group_name, {}),
            path=f"{path}.{group_name}",
        )
        unknown_fields = sorted(set(raw_group) - set(_PLAN_DEFAULTS))
        if unknown_fields:
            raise ValueError(
                "未知 MAA 计划配置路径: "
                + ", ".join(
                    f"{path}.{group_name}.{name}" for name in unknown_fields
                )
            )
        group = dict(_PLAN_DEFAULTS)
        group.update(raw_group)
        _validate_plan_group(group, path=f"{path}.{group_name}")
        normalized[group_name] = group
    return normalized


def legacy_plans_to_wire(legacy_data: object) -> WireDict:
    """将 r6 ``PlanConfig.json`` 纯转换为 Config v2 Wire。

    保留成员顺序和 UUID，并将 ``MaaPlanConfig`` 映射为 ``MaaPlan``。
    缺失的已知字段补齐 r6 默认；未知字段、孤儿数据、重复/非法 UUID、
    非法类型和值均 fail-closed。
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
                "未知 MAA 计划配置路径: "
                + ", ".join(f"{item_path}.{name}" for name in unknown)
            )
        if set(item) != {"uid", "type"}:
            raise ValueError(f"{item_path} 必须同时包含 uid 和 type")

        parsed_uid, canonical_uid = _parse_uid(
            item["uid"],
            path=f"{item_path}.uid",
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
    if any(raw_uid not in root for _, _, raw_uid in order):
        raise ValueError("$.instances 引用了缺失的数据项")

    return {
        "order": [
            {"uid": canonical_uid, "type": V2_ENTRY_TYPE}
            for _, canonical_uid, _ in order
        ],
        "data": {
            canonical_uid: _normalize_entry(
                root[raw_uid],
                path=f"$.{raw_uid}",
            )
            for _, canonical_uid, raw_uid in order
        },
    }


def plans_wire_to_legacy(wire_data: object) -> dict[str, Any]:
    """将 Config v2 Wire 纯转换为可回滚的 r6 JSON 形状。"""

    root = _require_dict(wire_data, path="$")
    unknown_root = sorted(set(root) - {"order", "data"})
    if unknown_root:
        raise ValueError(
            "未知 MAA 计划配置路径: "
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
                "未知 MAA 计划配置路径: "
                + ", ".join(f"{item_path}.{name}" for name in unknown)
            )
        if set(item) != {"uid", "type"}:
            raise ValueError(f"{item_path} 必须同时包含 uid 和 type")

        parsed_uid, canonical_uid = _parse_uid(
            item["uid"],
            path=f"{item_path}.uid",
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
        legacy["instances"].append(
            {"uid": canonical_uid, "type": LEGACY_ENTRY_TYPE}
        )
        legacy[canonical_uid] = _normalize_entry(
            value,
            path=f"$.data.{canonical_uid}",
        )
    return legacy


__all__ = [
    "MaaPlan",
    "PLAN_FIELDS",
    "PLAN_GROUPS",
    "Plans",
    "WEEKDAYS",
    "legacy_plans_to_wire",
    "plans_wire_to_legacy",
]
