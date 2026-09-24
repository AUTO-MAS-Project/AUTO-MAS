"""MFW 任务选项里密码字段（PI v2.10.0 ``password: true``）的加密存储。

用户配置 ``Task.TaskSnapshot`` 是一整份 JSON，密码字段的值在
``taskOptions[任务实例][option][字段]``。写入用户配置前加密（``seal_user_task_snapshot``，
``Config.update_user`` 调），建运行计划前在内存里解密（``open_task_snapshot``，
``runner_task`` 调）；前端读到的永远是密文，只据此显示「已设置」，不回显原文。

加密用 MAS 现有的 DPAPI（与 ``EncryptValidator`` 同一对 ``dpapi_encrypt`` / ``dpapi_decrypt``），
密文前面加固定前缀 ``SECRET_PREFIX``，好与旧版本留下的明文区分：

- 带前缀：是密文。解不开（换了 Windows 账户 / 电脑、配置从别处恢复）就报错请用户重填，
  不能把密文当密码发出去。
- 不带前缀：旧版本存下的明文，照常使用，下次保存该用户的任务配置时加密。

运行时解密出来的原文会随 ``pipeline_override`` 进 MaaFramework 的原生调试日志
（``MaaTaskerPostTask`` 按 DBG 级别记下整份 override）；``runner_task`` 复制原生日志、
转发 worker 输出、摘录失败原因时用 ``redact_secret_text`` 把它们换成占位。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.task.MaaFW.tools.core.interface.loader import load_interface_model_cached
from app.task.MaaFW.tools.core.interface.models import (
    MaaFWInterface,
    map_password_values,
    password_input_names,
)
from app.utils import dpapi_decrypt, dpapi_encrypt, get_logger

from .embedded_project import resolve_maafw_project_root

logger = get_logger("MaaFW 密码字段")

SECRET_PREFIX = "mas-dpapi:"


class MaaFWSecretError(ValueError):
    """已加密的密码字段在本机解不开。"""


def is_sealed_secret(value: str) -> bool:
    return value.startswith(SECRET_PREFIX)


def _seal_value(value: str, _option_name: str = "", _field_name: str = "") -> str:
    if is_sealed_secret(value):
        return value
    return SECRET_PREFIX + dpapi_encrypt(value)


def _open_value(value: str, option_name: str, field_name: str) -> str:
    if not is_sealed_secret(value):
        return value
    try:
        return dpapi_decrypt(value[len(SECRET_PREFIX) :])
    except Exception as exc:
        raise MaaFWSecretError(
            f"选项 {option_name} 的密码字段 {field_name} 无法解密"
            "（可能换了电脑或 Windows 账户，或配置是从别处恢复的），"
            "请在用户配置的任务队列里重新填写"
        ) from exc


def _has_plaintext_secret(task_options: Any, fields: dict[str, frozenset[str]]) -> bool:
    found = False

    def probe(value: str, _option_name: str, _field_name: str) -> str:
        nonlocal found
        if not is_sealed_secret(value):
            found = True
        return value

    map_password_values(task_options, fields, probe)
    return found


def seal_task_snapshot(snapshot: Any, interface: MaaFWInterface) -> Any:
    """把快照里明文的密码字段加密；已是密文的、非密码字段原样不动。

    接受 JSON 字符串或 dict，返回同一种。没有要加密的就**原样返回入参**（字符串不重排）。
    加密失败（平台不支持 DPAPI 之类）直接抛出：协议要求不得明文落盘，宁可这次保存失败。
    """

    fields = password_input_names(interface)
    if not fields:
        return snapshot
    parsed = snapshot
    if isinstance(snapshot, str):
        try:
            parsed = json.loads(snapshot)
        except (TypeError, ValueError):
            return snapshot
    if not isinstance(parsed, dict):
        return snapshot
    task_options = parsed.get("taskOptions")
    if not _has_plaintext_secret(task_options, fields):
        return snapshot

    sealed = {
        **parsed,
        "taskOptions": map_password_values(task_options, fields, _seal_value),
    }
    if isinstance(snapshot, str):
        return json.dumps(sealed, ensure_ascii=False)
    return sealed


def open_task_snapshot(
    snapshot: dict[str, Any], interface: MaaFWInterface
) -> dict[str, Any]:
    """返回一份密码字段已解密的快照副本（只在内存里用，不得写回配置）。

    旧版本留下的明文原样使用（下次保存时加密）；带前缀却解不开的抛 ``MaaFWSecretError``。
    """

    fields = password_input_names(interface)
    task_options = snapshot.get("taskOptions") if isinstance(snapshot, dict) else None
    if not fields or not isinstance(task_options, dict):
        return snapshot
    if _has_plaintext_secret(task_options, fields):
        logger.info(
            "该用户的任务配置里有旧版本存下的未加密密码字段，本次照常使用；"
            "下次保存任务配置时会自动加密"
        )
    return {
        **snapshot,
        "taskOptions": map_password_values(task_options, fields, _open_value),
    }


#: 日志里替换密码原文用的占位。
REDACTED_SECRET_TEXT = "<已隐藏>"
#: 短于这个长度的密码不做全文替换：一两个字符的值会把日志里所有同样的字符都换掉，
#: 日志就没法看了；这么短的密码本身也谈不上保密。
MIN_REDACTED_SECRET_LENGTH = 4


def collect_plan_password_values(plan: Any, interface: MaaFWInterface) -> list[str]:
    """运行计划里所有 password 字段（PI v2.10.0）的实际值（已解密），去重。

    任务与前置任务的 ``options`` 都看：``{option 名: {字段: 值}}``。
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
    return values


def secret_log_variants(values: list[str]) -> list[str]:
    """一个密码在日志里可能出现的写法：原文，以及 JSON 转义后的两种（中文原样 / \\u 转义）。

    MaaFramework 原生日志把 ``pipeline_override`` 按 JSON 记下来（``MaaTaskerPostTask``
    的 ``[pipeline_override={...}]``），带引号、反斜杠或中文的密码在那里是转义后的样子。
    过短的值不收（见 ``MIN_REDACTED_SECRET_LENGTH``）；长的在前，免得先替换掉子串。
    """

    variants: set[str] = set()
    for value in values:
        if len(value) < MIN_REDACTED_SECRET_LENGTH:
            continue
        variants.add(value)
        variants.add(json.dumps(value, ensure_ascii=False)[1:-1])
        variants.add(json.dumps(value, ensure_ascii=True)[1:-1])
    return sorted(variants, key=len, reverse=True)


def redact_secret_text(text: str, variants: list[str]) -> str:
    """把 ``text`` 里出现的密码（``secret_log_variants`` 给出的写法）换成占位。"""

    for variant in variants:
        if variant in text:
            text = text.replace(variant, REDACTED_SECRET_TEXT)
    return text


def seal_user_task_snapshot(script_id: str, script_config: Any, snapshot: Any) -> Any:
    """``Config.update_user`` 写 ``Task.TaskSnapshot`` 前调：按脚本当前的 interface 加密密码字段。

    视图不在或 interface 读不出来时原样放行——那时前端也打不开任务选项编辑器，
    快照里不会有新填的密码；视图恢复后下一次保存照常加密。
    """

    root = Path(resolve_maafw_project_root(script_id, script_config))
    if not root.is_dir():
        return snapshot
    try:
        interface = load_interface_model_cached(root)
    except Exception as exc:  # noqa: BLE001 - 读不出 interface 不该挡住保存其它配置
        logger.debug(f"保存任务配置时读取 interface 失败，密码字段未处理：{exc}")
        return snapshot
    return seal_task_snapshot(snapshot, interface)


__all__ = [
    "REDACTED_SECRET_TEXT",
    "SECRET_PREFIX",
    "MaaFWSecretError",
    "collect_plan_password_values",
    "is_sealed_secret",
    "open_task_snapshot",
    "redact_secret_text",
    "seal_task_snapshot",
    "seal_user_task_snapshot",
    "secret_log_variants",
]
