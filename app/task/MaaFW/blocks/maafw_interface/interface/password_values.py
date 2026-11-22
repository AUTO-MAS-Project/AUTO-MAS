"""按 interface 认出密码字段（PI v2.10.0 ``password: true``），从任务快照的普通数据里收集要打码的值。

密码字段这件事分三处（迁移方案 §3.7）：哪些选项是密码、从快照里收集值归解析（本模块）；
加解密（DPAPI）在宿主（``seams/option_secrets``）；按值打码归运行
（``blocks/maafw_runner/host/run_redaction``）。本模块只依赖标准库与 interface 的模型，**不引宿主的
加解密**：快照里的密文怎么认、怎么解开，由调用方经 ``MaaFWSecretOpener`` 交进来。

快照是一整份 ``Task.TaskSnapshot``（JSON 字符串或 dict）：密码字段的值在
``taskOptions[任务实例][option][字段]``，全局选项的在 ``globalOptions[option][字段]``
（两处一起看，``SNAPSHOT_SECRET_SECTIONS``）。
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any, Protocol

from .models import MaaFWInterface, map_password_values, password_input_names

#: 快照里存选项值的两处：``taskOptions`` 是 ``{任务实例: {option: 值}}``，``globalOptions``
#: 是 ``{option: 值}``（全局选项每个账号一份）；后者套一层 ``{"_": …}`` 后与前者同形。
SNAPSHOT_SECRET_SECTIONS = ("taskOptions", "globalOptions")


class MaaFWSecretOpener(Protocol):
    """调用方给的密文认读：``is_sealed`` 认出密文；``open_value`` 返回原文——不是密文的原样
    返回，解不开的返回 None（这些值本机本来也跑不了，跳过即可）。"""

    def is_sealed(self, value: str) -> bool: ...

    def open_value(self, value: str) -> str | None: ...


def section_as_task_options(snapshot: dict[str, Any], key: str) -> Any:
    """快照里 ``key`` 那一处，``globalOptions`` 套成 ``{"_": …}`` 与 ``taskOptions`` 同形。"""

    value = snapshot.get(key)
    if key == "globalOptions":
        return {"_": value} if isinstance(value, dict) else None
    return value


def sealed_leaves(value: Any, opener: MaaFWSecretOpener) -> list[str]:
    """``value`` 里任意深度、全部是密文的字符串叶子（按出现顺序，不去重）。"""

    if isinstance(value, str):
        return [value] if opener.is_sealed(value) else []
    if isinstance(value, dict):
        return [leaf for item in value.values() for leaf in sealed_leaves(item, opener)]
    if isinstance(value, list):
        return [leaf for item in value for leaf in sealed_leaves(item, opener)]
    return []


def _parse_snapshot(raw: Any) -> dict[str, Any] | None:
    try:
        snapshot = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:  # noqa: BLE001 - 坏快照就没有可收的
        return None
    return snapshot if isinstance(snapshot, dict) else None


def collect_plan_password_values(plan: Any, interface: MaaFWInterface) -> list[str]:
    """运行计划里所有 password 字段（PI v2.10.0）的实际值（已解密），去重。

    任务与前置任务的 ``options`` 都看：``{option 名: {字段: 值}}``；再加计划的
    ``globalOptions``（用户的全局表）——同一选项任务自己也有值时，任务 ``options`` 里只有
    任务那一层，全局那一层的密码只在这里。
    """

    fields = password_input_names(interface)
    if not fields:
        return []
    values: list[str] = []

    def collect(value: str, _option_name: str, _field_name: str) -> str:
        if value not in values:
            values.append(value)
        return value

    for item in [*getattr(plan, "tasks", []), *getattr(plan, "pretasks", [])]:
        options = getattr(item, "options", None)
        if isinstance(options, dict):
            map_password_values({"_": options}, fields, collect)
    global_options = getattr(plan, "globalOptions", None)
    if isinstance(global_options, dict):
        map_password_values({"_": global_options}, fields, collect)
    return values


def snapshot_sealed_values(raw_snapshot: Any, opener: MaaFWSecretOpener) -> list[str]:
    """一份任务快照两处选项值里全部密文解开后的值，去重；解不开的、空的跳过。"""

    snapshot = _parse_snapshot(raw_snapshot)
    if snapshot is None:
        return []
    values: list[str] = []
    for key in SNAPSHOT_SECRET_SECTIONS:
        for sealed in sealed_leaves(snapshot.get(key), opener):
            value = opener.open_value(sealed)
            if value is None:
                continue
            if value and value not in values:
                values.append(value)
    return values


def collect_run_password_values(
    plan: Any,
    interface: MaaFWInterface,
    user_snapshot: Any | None,
    opener: MaaFWSecretOpener,
) -> list[str]:
    """本次运行要打码的密码值：计划里 password 字段的值（``collect_plan_password_values``），
    再并上该账号任务快照（``user_snapshot``，``Task.TaskSnapshot`` 原值；没有就 None）里所有
    密文解开的值。

    后者兜住项目更新撤掉了 password 标记的字段：建计划前照样把它们解开交给计划，只看当前
    声明的话这些原文会不打码地进 ``.worker.log`` / ``.maafw.log``。
    """

    values = collect_plan_password_values(plan, interface)
    if user_snapshot is not None:
        for value in snapshot_sealed_values(user_snapshot, opener):
            if value not in values:
                values.append(value)
    return values


def collect_snapshots_password_values(
    snapshots: Iterable[Any],
    interface: MaaFWInterface | None,
    opener: MaaFWSecretOpener,
) -> list[str]:
    """一组任务快照（如一个托管下全部账号的 ``Task.TaskSnapshot`` 原值）里 password 字段的值
    （已解密），去重。

    给不在某次运行里的日志打码用（问题包收项目自己写的日志）：那些日志可能是任何一个账号
    跑出来的。``interface`` 读不出来（None）时只认密文——它们一定是密码；旧版本存下的明文要靠
    interface 才认得出。解不开的密文跳过、坏快照跳过。
    """

    fields = password_input_names(interface) if interface is not None else {}
    values: list[str] = []

    def collect(value: str, _option_name: str, _field_name: str) -> str:
        opened = opener.open_value(value)
        if opened and opened not in values:
            values.append(opened)
        return value

    for raw in snapshots:
        snapshot = _parse_snapshot(raw)
        if snapshot is None:
            continue
        # 任务选项与全局选项表两处都收（全局选项的密码只存在后者里）
        for key in SNAPSHOT_SECRET_SECTIONS:
            section = section_as_task_options(snapshot, key)
            if not isinstance(section, dict):
                continue
            if fields:
                map_password_values(section, fields, collect)
            for sealed in sealed_leaves(section, opener):
                collect(sealed, "", "")
    return values


__all__ = [
    "SNAPSHOT_SECRET_SECTIONS",
    "MaaFWSecretOpener",
    "collect_plan_password_values",
    "collect_run_password_values",
    "collect_snapshots_password_values",
    "section_as_task_options",
    "sealed_leaves",
    "snapshot_sealed_values",
]
