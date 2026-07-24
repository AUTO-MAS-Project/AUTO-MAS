"""队列配置的原生 Config v2 根与 r6 兼容转换。"""

from __future__ import annotations

import calendar
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, Field

from app.configuration import (
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    WireDict,
    collection,
    ref,
)

LEGACY_QUEUE_TYPE = "QueueConfig"
V2_QUEUE_TYPE = "Queue"
TIME_SET_TYPE = "TimeSet"
QUEUE_ITEM_TYPE = "QueueItem"
SCRIPT_COLLECTION_NAME = "ScriptConfig"

WEEKDAYS = tuple(calendar.day_name)
AFTER_ACCOMPLISH_ACTIONS = (
    "NoAction",
    "Shutdown",
    "ShutdownForce",
    "Reboot",
    "Hibernate",
    "Sleep",
    "KillSelf",
    "Logoff",
)

_QUEUE_INFO_DEFAULTS: dict[str, object] = {
    "Name": "新队列",
    "TimeEnabled": False,
    "StartUpEnabled": False,
    "AfterAccomplish": "NoAction",
}
_QUEUE_DATA_DEFAULTS: dict[str, object] = {
    "LastTimedStart": "2000-01-01 00:00",
}
_TIME_SET_DEFAULTS: dict[str, object] = {
    "Enabled": True,
    "Days": list(WEEKDAYS),
    "Time": "00:00",
}
_QUEUE_ITEM_DEFAULTS: dict[str, object] = {"ScriptId": "-"}


def _validate_clock(value: str) -> str:
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError:
        raise ValueError("Time 必须使用 %H:%M 格式") from None
    return value


def _validate_last_timed_start(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d %H:%M")
    except ValueError:
        raise ValueError(
            "LastTimedStart 必须使用 %Y-%m-%d %H:%M 格式"
        ) from None
    return value


def _validate_script_id(value: str) -> str:
    if value == "-":
        return value
    try:
        UUID(value)
    except (ValueError, AttributeError):
        raise ValueError("ScriptId 必须为 '-' 或 UUID 字符串") from None
    return value


class QueueItem(ConfigEntry):
    """队列中的一个脚本引用。"""

    class InfoGroup(ConfigGroup):
        # QueueItem - 脚本配置外键；无选择时使用 "-"
        ScriptId: Annotated[
            str,
            Field(strict=True),
            AfterValidator(_validate_script_id),
            ref(
                SCRIPT_COLLECTION_NAME,
                default="-",
                allow_values=("-",),
            ),
        ] = "-"

    Info: InfoGroup = Field(default_factory=InfoGroup)


class TimeSet(ConfigEntry):
    """队列的一个定时触发条件。"""

    class InfoGroup(ConfigGroup):
        # TimeSet - 是否启用
        Enabled: Annotated[bool, Field(strict=True)] = True
        # TimeSet - 英文星期名称列表；保持 r6 calendar.day_name 语义
        Days: Annotated[
            list[
                Literal[
                    "Monday",
                    "Tuesday",
                    "Wednesday",
                    "Thursday",
                    "Friday",
                    "Saturday",
                    "Sunday",
                ]
            ],
            Field(strict=True),
        ] = Field(default_factory=lambda: list(WEEKDAYS))
        # TimeSet - 每日执行时间
        Time: Annotated[
            str,
            Field(strict=True),
            AfterValidator(_validate_clock),
        ] = "00:00"

    Info: InfoGroup = Field(default_factory=InfoGroup)


class QueueItemCollection(ConfigCollection[QueueItem]):
    """``Queue.QueueItem`` 嵌套集合。"""

    _default_entry_types = (QueueItem,)


class TimeSetCollection(ConfigCollection[TimeSet]):
    """``Queue.TimeSet`` 嵌套集合。"""

    _default_entry_types = (TimeSet,)


class Queue(ConfigEntry):
    """单个队列配置。"""

    class InfoGroup(ConfigGroup):
        # QueueConfig - 队列名称
        Name: Annotated[str, Field(strict=True)] = "新队列"
        # QueueConfig - 是否启用定时启动
        TimeEnabled: Annotated[bool, Field(strict=True)] = False
        # QueueConfig - 是否在宿主启动时运行
        StartUpEnabled: Annotated[bool, Field(strict=True)] = False
        # QueueConfig - 队列完成后的系统动作
        AfterAccomplish: Literal[
            "NoAction",
            "Shutdown",
            "ShutdownForce",
            "Reboot",
            "Hibernate",
            "Sleep",
            "KillSelf",
            "Logoff",
        ] = "NoAction"

    class DataGroup(ConfigGroup):
        # QueueConfig - 上次定时启动到分钟的时间戳
        LastTimedStart: Annotated[
            str,
            Field(strict=True),
            AfterValidator(_validate_last_timed_start),
        ] = "2000-01-01 00:00"

    Info: InfoGroup = Field(default_factory=InfoGroup)
    Data: DataGroup = Field(default_factory=DataGroup)
    TimeSet: TimeSetCollection = collection(TimeSet)
    QueueItem: QueueItemCollection = collection(QueueItem)


class Queues(ConfigCollection[Queue]):
    """独立 ``QueueConfig.json`` 生产根。"""

    _default_entry_types = (Queue,)


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
                "未知队列配置路径: "
                + ", ".join(f"{item_path}.{name}" for name in unknown)
            )
        if set(item) != {"uid", "type"}:
            raise ValueError(f"{item_path} 必须同时包含 uid 和 type")

        uid, canonical_uid = _parse_uid(
            item["uid"],
            path=f"{item_path}.uid",
        )
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
    *,
    expected_type: str,
    path: str,
) -> tuple[list[tuple[UUID, str]], dict[UUID, tuple[str, object]]]:
    root = _require_dict(value, path=path)
    order = _parse_order(
        root.get("instances", []),
        expected_type=expected_type,
        path=f"{path}.instances",
    )
    data = _parse_data_index(
        {key: item for key, item in root.items() if key != "instances"},
        path=path,
    )
    if {uid for uid, _ in order} != set(data):
        raise ValueError(f"{path} 包含缺失或孤儿 uid")
    return order, data


def _parse_v2_collection(
    value: object,
    *,
    expected_type: str,
    path: str,
) -> tuple[list[tuple[UUID, str]], dict[UUID, tuple[str, object]]]:
    root = _require_dict(value, path=path)
    unknown = sorted(set(root) - {"order", "data"})
    if unknown:
        raise ValueError(
            "未知队列配置路径: "
            + ", ".join(f"{path}.{name}" for name in unknown)
        )
    order = _parse_order(
        root.get("order", []),
        expected_type=expected_type,
        path=f"{path}.order",
    )
    data = _parse_data_index(root.get("data", {}), path=f"{path}.data")
    if {uid for uid, _ in order} != set(data):
        raise ValueError(f"{path}.order 与 data 包含缺失或孤儿 uid")
    return order, data


def _normalize_queue_info(value: object, *, path: str) -> WireDict:
    raw = _require_dict(value, path=path)
    unknown = sorted(set(raw) - set(_QUEUE_INFO_DEFAULTS))
    if unknown:
        raise ValueError(
            "未知队列配置路径: "
            + ", ".join(f"{path}.{name}" for name in unknown)
        )
    info = dict(_QUEUE_INFO_DEFAULTS)
    info.update(raw)

    if not isinstance(info["Name"], str):
        raise TypeError(f"{path}.Name 必须是字符串")
    for name in ("TimeEnabled", "StartUpEnabled"):
        if not isinstance(info[name], bool):
            raise TypeError(f"{path}.{name} 必须是布尔值")
    action = info["AfterAccomplish"]
    if not isinstance(action, str) or action not in AFTER_ACCOMPLISH_ACTIONS:
        raise ValueError(
            f"{path}.AfterAccomplish 不在 r6 允许的动作集合中"
        )
    return info


def _normalize_queue_data(value: object, *, path: str) -> WireDict:
    raw = _require_dict(value, path=path)
    unknown = sorted(set(raw) - set(_QUEUE_DATA_DEFAULTS))
    if unknown:
        raise ValueError(
            "未知队列配置路径: "
            + ", ".join(f"{path}.{name}" for name in unknown)
        )
    data = dict(_QUEUE_DATA_DEFAULTS)
    data.update(raw)
    last_timed_start = data["LastTimedStart"]
    if not isinstance(last_timed_start, str):
        raise TypeError(f"{path}.LastTimedStart 必须是字符串")
    _validate_last_timed_start(last_timed_start)
    return data


def _normalize_time_set(value: object, *, path: str) -> WireDict:
    entry = _require_dict(value, path=path)
    unknown_groups = sorted(set(entry) - {"Info"})
    if unknown_groups:
        raise ValueError(
            "未知队列配置路径: "
            + ", ".join(f"{path}.{name}" for name in unknown_groups)
        )
    raw = _require_dict(entry.get("Info", {}), path=f"{path}.Info")
    unknown = sorted(set(raw) - set(_TIME_SET_DEFAULTS))
    if unknown:
        raise ValueError(
            "未知队列配置路径: "
            + ", ".join(f"{path}.Info.{name}" for name in unknown)
        )
    info = {
        "Enabled": _TIME_SET_DEFAULTS["Enabled"],
        "Days": list(WEEKDAYS),
        "Time": _TIME_SET_DEFAULTS["Time"],
    }
    info.update(raw)

    if not isinstance(info["Enabled"], bool):
        raise TypeError(f"{path}.Info.Enabled 必须是布尔值")
    days = info["Days"]
    if not isinstance(days, list):
        raise TypeError(f"{path}.Info.Days 必须是列表")
    for index, day in enumerate(days):
        if not isinstance(day, str) or day not in WEEKDAYS:
            raise ValueError(
                f"{path}.Info.Days[{index}] 必须是英文星期名称"
            )
    time = info["Time"]
    if not isinstance(time, str):
        raise TypeError(f"{path}.Info.Time 必须是字符串")
    _validate_clock(time)
    return {"Info": info}


def _normalize_queue_item(value: object, *, path: str) -> WireDict:
    entry = _require_dict(value, path=path)
    unknown_groups = sorted(set(entry) - {"Info"})
    if unknown_groups:
        raise ValueError(
            "未知队列配置路径: "
            + ", ".join(f"{path}.{name}" for name in unknown_groups)
        )
    raw = _require_dict(entry.get("Info", {}), path=f"{path}.Info")
    unknown = sorted(set(raw) - set(_QUEUE_ITEM_DEFAULTS))
    if unknown:
        raise ValueError(
            "未知队列配置路径: "
            + ", ".join(f"{path}.Info.{name}" for name in unknown)
        )
    info = dict(_QUEUE_ITEM_DEFAULTS)
    info.update(raw)
    script_id = info["ScriptId"]
    if not isinstance(script_id, str):
        raise TypeError(f"{path}.Info.ScriptId 必须是字符串")
    _validate_script_id(script_id)
    return {"Info": info}


def _legacy_nested_to_wire(
    value: object,
    *,
    expected_type: str,
    v2_type: str,
    path: str,
    normalizer: Any,
) -> WireDict:
    order, data = _parse_legacy_collection(
        value,
        expected_type=expected_type,
        path=path,
    )
    return {
        "order": [
            {"uid": canonical_uid, "type": v2_type}
            for _, canonical_uid in order
        ],
        "data": {
            canonical_uid: normalizer(
                data[uid][1],
                path=f"{path}.{canonical_uid}",
            )
            for uid, canonical_uid in order
        },
    }


def _v2_nested_to_legacy(
    value: object,
    *,
    expected_type: str,
    legacy_type: str,
    path: str,
    normalizer: Any,
) -> dict[str, Any]:
    order, data = _parse_v2_collection(
        value,
        expected_type=expected_type,
        path=path,
    )
    legacy: dict[str, Any] = {"instances": []}
    for uid, canonical_uid in order:
        legacy["instances"].append(
            {"uid": canonical_uid, "type": legacy_type}
        )
        legacy[canonical_uid] = normalizer(
            data[uid][1],
            path=f"{path}.data.{canonical_uid}",
        )
    return legacy


def _normalize_legacy_queue(value: object, *, path: str) -> WireDict:
    entry = _require_dict(value, path=path)
    # ``TimeSet``/``QueueItem`` are Config v2 field names, not accepted r6
    # aliases.  A hybrid document carrying them together with canonical
    # SubConfigsInfo is ambiguous and must never silently choose one side.
    direct_nested = sorted(set(entry) & {"TimeSet", "QueueItem"})
    raw_sub_configs = entry.get("SubConfigsInfo", {})
    if direct_nested and isinstance(raw_sub_configs, dict):
        conflicts = [name for name in direct_nested if name in raw_sub_configs]
        if conflicts:
            raise ValueError(
                f"{path} 的 SubConfigsInfo 与非规范嵌套别名冲突: "
                + ", ".join(conflicts)
            )

    unknown_groups = sorted(
        set(entry) - {"Info", "Data", "SubConfigsInfo"}
    )
    if unknown_groups:
        raise ValueError(
            "未知队列配置路径: "
            + ", ".join(f"{path}.{name}" for name in unknown_groups)
        )

    sub_configs = _require_dict(
        raw_sub_configs,
        path=f"{path}.SubConfigsInfo",
    )
    unknown_sub_configs = sorted(
        set(sub_configs) - {"TimeSet", "QueueItem"}
    )
    if unknown_sub_configs:
        raise ValueError(
            "未知队列配置路径: "
            + ", ".join(
                f"{path}.SubConfigsInfo.{name}"
                for name in unknown_sub_configs
            )
        )

    return {
        "Info": _normalize_queue_info(
            entry.get("Info", {}),
            path=f"{path}.Info",
        ),
        "Data": _normalize_queue_data(
            entry.get("Data", {}),
            path=f"{path}.Data",
        ),
        "TimeSet": _legacy_nested_to_wire(
            sub_configs.get("TimeSet", {}),
            expected_type=TIME_SET_TYPE,
            v2_type=TIME_SET_TYPE,
            path=f"{path}.SubConfigsInfo.TimeSet",
            normalizer=_normalize_time_set,
        ),
        "QueueItem": _legacy_nested_to_wire(
            sub_configs.get("QueueItem", {}),
            expected_type=QUEUE_ITEM_TYPE,
            v2_type=QUEUE_ITEM_TYPE,
            path=f"{path}.SubConfigsInfo.QueueItem",
            normalizer=_normalize_queue_item,
        ),
    }


def _normalize_v2_queue_for_rollback(
    value: object,
    *,
    path: str,
) -> dict[str, Any]:
    entry = _require_dict(value, path=path)
    unknown_groups = sorted(
        set(entry) - {"Info", "Data", "TimeSet", "QueueItem"}
    )
    if unknown_groups:
        raise ValueError(
            "未知队列配置路径: "
            + ", ".join(f"{path}.{name}" for name in unknown_groups)
        )
    return {
        "Info": _normalize_queue_info(
            entry.get("Info", {}),
            path=f"{path}.Info",
        ),
        "Data": _normalize_queue_data(
            entry.get("Data", {}),
            path=f"{path}.Data",
        ),
        "SubConfigsInfo": {
            "TimeSet": _v2_nested_to_legacy(
                entry.get("TimeSet", {}),
                expected_type=TIME_SET_TYPE,
                legacy_type=TIME_SET_TYPE,
                path=f"{path}.TimeSet",
                normalizer=_normalize_time_set,
            ),
            "QueueItem": _v2_nested_to_legacy(
                entry.get("QueueItem", {}),
                expected_type=QUEUE_ITEM_TYPE,
                legacy_type=QUEUE_ITEM_TYPE,
                path=f"{path}.QueueItem",
                normalizer=_normalize_queue_item,
            ),
        },
    }


def legacy_queues_to_wire(legacy_data: object) -> WireDict:
    """将 r6 ``QueueConfig.json`` 纯转换为 Config v2 Wire。

    外层队列及两层嵌套集合均保留顺序和 UUID。缺失的已知字段补齐 r6
    默认值；未知字段、孤儿、重复/非法 UUID、非法类型和值均 fail-closed。
    """

    order, data = _parse_legacy_collection(
        legacy_data,
        expected_type=LEGACY_QUEUE_TYPE,
        path="$",
    )
    return {
        "order": [
            {"uid": canonical_uid, "type": V2_QUEUE_TYPE}
            for _, canonical_uid in order
        ],
        "data": {
            canonical_uid: _normalize_legacy_queue(
                data[uid][1],
                path=f"$.{canonical_uid}",
            )
            for uid, canonical_uid in order
        },
    }


def queues_wire_to_legacy(wire_data: object) -> dict[str, Any]:
    """将 Config v2 Wire 纯转换为可回滚的 r6 JSON 形状。"""

    order, data = _parse_v2_collection(
        wire_data,
        expected_type=V2_QUEUE_TYPE,
        path="$",
    )
    legacy: dict[str, Any] = {"instances": []}
    for uid, canonical_uid in order:
        legacy["instances"].append(
            {"uid": canonical_uid, "type": LEGACY_QUEUE_TYPE}
        )
        legacy[canonical_uid] = _normalize_v2_queue_for_rollback(
            data[uid][1],
            path=f"$.data.{canonical_uid}",
        )
    return legacy


__all__ = [
    "AFTER_ACCOMPLISH_ACTIONS",
    "Queue",
    "QueueItem",
    "QueueItemCollection",
    "Queues",
    "SCRIPT_COLLECTION_NAME",
    "TimeSet",
    "TimeSetCollection",
    "WEEKDAYS",
    "legacy_queues_to_wire",
    "queues_wire_to_legacy",
]
