"""MFW 任务选项里密码字段（PI v2.10.0 ``password: true``）的加密存储。

账号配置 ``Task.TaskSnapshot`` 是一整份 JSON，密码字段的值在
``taskOptions[任务实例][option][字段]``，全局选项的在 ``globalOptions[option][字段]``（两处
一起处理，``_SECRET_SECTIONS``）。写入账号配置前加密（``prepare_user_task_snapshot``，
``Config.update_user`` 调），建运行计划前在内存里解密（``open_task_snapshot``，
``runner_task`` 调）；前端读到的永远是密文，只据此显示「已设置」，不回显原文。

加密用 MAS 现有的 DPAPI（与 ``EncryptValidator`` 同一对 ``dpapi_encrypt`` / ``dpapi_decrypt``），
密文前面加固定前缀 ``SECRET_PREFIX``，好与旧版本留下的明文区分：

- 带前缀：是密文。解不开（换了 Windows 账户 / 电脑、配置从别处恢复）就报错请用户重填，
  不能把密文当密码发出去。
- 不带前缀：旧版本存下的明文，照常使用，下次保存该账号的任务配置时加密。

运行时解密出来的原文会随 ``pipeline_override`` 进 MaaFramework 的原生调试日志
（``MaaTaskerPostTask`` 按 DBG 级别记下整份 override）；``plan_run`` 复制原生日志、
转发 worker 输出、摘录失败原因时把它们换成占位。

密码字段这件事分三处（迁移方案 §3.7），本模块只管宿主这一处——加解密，以及从配置对象里取出
任务快照的原值（``user_task_snapshot`` / ``script_task_snapshots``）：哪些选项是密码、从快照里
收集要打码的值在解析一侧（``tools/core/interface/password_values``，密文经 ``DPAPI_SECRET_OPENER``
交给它认读）；按值打码在运行一侧（``run_redaction``）。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.task.MaaFW.blocks.maafw_interface.interface.loader import (
    load_interface_model_cached,
)
from app.task.MaaFW.blocks.maafw_interface.interface.models import (
    MaaFWInterface,
    map_password_values,
    password_input_names,
)
from app.task.MaaFW.blocks.maafw_interface.interface.password_values import (
    SNAPSHOT_SECRET_SECTIONS,
    sealed_leaves,
    section_as_task_options,
)
from app.task.MaaFW.blocks.maafw_interface.interface.task_config import (
    mirror_global_options_to_tasks,
)
from app.task.MaaFW.blocks.maafw_interface.runner.pipeline_override import (
    SECRET_INPUTS_SNAPSHOT_KEY,
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
            "请在账号配置的任务队列里重新填写"
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


class _DpapiSecretOpener:
    """解析一侧收集函数用的密文认读（``password_values.MaaFWSecretOpener``）：带
    ``SECRET_PREFIX`` 的是密文，DPAPI 解开；解不开的返回 None，不是密文的原样返回。"""

    def is_sealed(self, value: str) -> bool:
        return is_sealed_secret(value)

    def open_value(self, value: str) -> str | None:
        try:
            return _open_value(value, "", "")
        except MaaFWSecretError:
            return None


DPAPI_SECRET_OPENER = _DpapiSecretOpener()

#: 快照里存选项值的两处（定义在解析一侧，见 ``password_values``）。
_SECRET_SECTIONS = SNAPSHOT_SECRET_SECTIONS
_section_as_task_options = section_as_task_options


def _sealed_leaves(value: Any) -> list[str]:
    return sealed_leaves(value, DPAPI_SECRET_OPENER)


def _map_snapshot_secrets(
    snapshot: dict[str, Any],
    fields: dict[str, frozenset[str]],
    transform: Callable[[str, str, str], str],
) -> dict[str, Any]:
    """对快照两处选项值里的密码字段套 ``transform``，返回新快照（不改入参）。"""

    mapped = dict(snapshot)
    for key in _SECRET_SECTIONS:
        section = _section_as_task_options(snapshot, key)
        if not isinstance(section, dict):
            continue
        result = map_password_values(section, fields, transform)
        mapped[key] = result["_"] if key == "globalOptions" else result
    return mapped


def _snapshot_has_plaintext_secret(
    snapshot: dict[str, Any], fields: dict[str, frozenset[str]]
) -> bool:
    return any(
        _has_plaintext_secret(_section_as_task_options(snapshot, key), fields)
        for key in _SECRET_SECTIONS
    )


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
    if not _snapshot_has_plaintext_secret(parsed, fields):
        return snapshot

    sealed = _map_snapshot_secrets(parsed, fields, _seal_value)
    if isinstance(snapshot, str):
        return json.dumps(sealed, ensure_ascii=False)
    return sealed


def open_task_snapshot(
    snapshot: dict[str, Any], interface: MaaFWInterface
) -> dict[str, Any]:
    """返回一份密码字段已解密的快照副本（只在内存里用，不得写回配置）。

    旧版本留下的明文原样使用（下次保存时加密）；带前缀却解不开的抛 ``MaaFWSecretError``。
    当前 interface 已不再声明为 password 的字段（项目更新撤掉了标记）里留着的密文同样解开：
    不解的话 ``mas-dpapi:…`` 原样进 pipeline_override。所有实例与全局表都解——建计划时归一会
    补回不在队列里的勾选实例、旧配置迁移会从未勾选实例上取全局值，只解一部分就会漏；解不开
    的告警后丢掉这个值（按默认值跑），不让整轮失败，这类字段界面上已经不按密码显示，用户未必
    找得到去重填。只在内存里解，保存时不动它：interface 降级读丢了选项时也会「看不到」password
    声明，那时写回明文就泄露了。解出的值要进运行日志的打码集合
    （``password_values.collect_run_password_values``），
    字段记进 ``SECRET_INPUTS_SNAPSHOT_KEY``，下发失败的计划提示同样不带原值。
    """

    if not isinstance(snapshot, dict):
        return snapshot
    fields = password_input_names(interface)
    opened = snapshot
    if fields:
        if _snapshot_has_plaintext_secret(snapshot, fields):
            logger.info(
                "该账号的任务配置里有旧版本存下的未加密密码字段，本次照常使用；"
                "下次保存任务配置时会自动加密"
            )
        opened = _map_snapshot_secrets(snapshot, fields, _open_value)
    return _open_orphan_secrets(opened)


_DROPPED = object()


def _open_orphan_secrets(snapshot: dict[str, Any]) -> dict[str, Any]:
    """两处选项值里剩下的带 ``SECRET_PREFIX`` 的值全部解开（返回新快照，不改入参）。"""

    if not any(_sealed_leaves(snapshot.get(key)) for key in _SECRET_SECTIONS):
        return snapshot
    dropped: list[str] = []
    secret_inputs: dict[tuple[str, str], None] = {}

    def open_tree(value: Any, option_name: str, field_name: str) -> Any:
        if isinstance(value, str):
            if not is_sealed_secret(value):
                return value
            try:
                opened_value = _open_value(value, option_name, field_name)
            except MaaFWSecretError:
                dropped.append(
                    f"{option_name}.{field_name}" if field_name else option_name
                )
                return _DROPPED
            secret_inputs.setdefault((option_name, field_name), None)
            return opened_value
        if isinstance(value, dict):
            opened_items = {
                key: open_tree(item, option_name or str(key), str(key))
                for key, item in value.items()
            }
            return {
                key: item for key, item in opened_items.items() if item is not _DROPPED
            }
        if isinstance(value, list):
            return [
                item
                for item in (open_tree(item, option_name, field_name) for item in value)
                if item is not _DROPPED
            ]
        return value

    opened = dict(snapshot)
    global_options = snapshot.get("globalOptions")
    if isinstance(global_options, dict) and _sealed_leaves(global_options):
        opened["globalOptions"] = open_tree(global_options, "", "")
    task_options = snapshot.get("taskOptions")
    if isinstance(task_options, dict) and _sealed_leaves(task_options):
        opened["taskOptions"] = {
            task_id: open_tree(options, "", "")
            for task_id, options in task_options.items()
        }
    if secret_inputs:
        opened[SECRET_INPUTS_SNAPSHOT_KEY] = [list(pair) for pair in secret_inputs]
        logger.info(
            "该账号的任务配置里有项目已不再标为密码的字段仍是密文"
            f"（{'、'.join(f'{option}.{field}' for option, field in secret_inputs)}），"
            "本次运行按解密后的值使用"
        )
    if dropped:
        logger.warning(
            "该账号的任务配置里有项目已不再标为密码、本机又解不开的密文"
            f"（{'、'.join(dict.fromkeys(dropped))}），本次按默认值运行；"
            "需要的话在账号配置的任务队列里重新填写"
        )
    return opened


def user_task_snapshot(user_config: Any | None) -> Any | None:
    """账号配置里 ``Task.TaskSnapshot`` 的原值（JSON 字符串或 dict），交给解析一侧收集要打码的值；
    没有账号配置、或读不出来就是 None。"""

    if user_config is None:
        return None
    try:
        return user_config.Task.TaskSnapshot
    except Exception:  # noqa: BLE001 - 读不出就没有可收的
        return None


def script_task_snapshots(script_config: Any) -> list[Any]:
    """脚本下全部账号 ``Task.TaskSnapshot`` 的原值，按账号顺序；读不出的账号跳过。

    交给解析一侧的 ``collect_snapshots_password_values``，给不在某次运行里的日志打码用
    （问题包收项目自己写的日志）。
    """

    try:
        users = list(script_config.UserData.items())
    except Exception as exc:  # noqa: BLE001 - 读不出账号列表就没有可打码的值
        logger.debug(f"读取脚本账号列表失败，没有可打码的密码值：{exc}")
        return []
    snapshots: list[Any] = []
    for _, user in users:
        try:
            snapshots.append(user.Task.TaskSnapshot)
        except Exception:  # noqa: BLE001 - 坏账号跳过
            continue
    return snapshots


def prepare_user_task_snapshot(
    script_id: str, script_config: Any, snapshot: Any
) -> Any:
    """``Config.update_user`` 写 ``Task.TaskSnapshot`` 前调，按脚本当前的 interface 做两步：

    1. 只属于全局的选项把全局表的值双写到各任务实例上（``mirror_global_options_to_tasks``，
       降级兼容：旧版本按任务读这些值）；
    2. 加密密码字段（任务上的副本与全局表一并加密）。

    视图不在或 interface 读不出来时原样放行——那时前端也打不开任务选项编辑器，
    快照里不会有新填的密码；视图恢复后下一次保存照常处理。
    """

    root = Path(resolve_maafw_project_root(script_id, script_config))
    if not root.is_dir():
        return snapshot
    try:
        interface = load_interface_model_cached(root)
    except Exception as exc:  # noqa: BLE001 - 读不出 interface 不该挡住保存其它配置
        logger.debug(f"保存任务配置时读取 interface 失败，任务快照未处理：{exc}")
        return snapshot
    return seal_task_snapshot(
        mirror_global_options_to_tasks(snapshot, interface), interface
    )


__all__ = [
    "DPAPI_SECRET_OPENER",
    "SECRET_PREFIX",
    "MaaFWSecretError",
    "is_sealed_secret",
    "open_task_snapshot",
    "prepare_user_task_snapshot",
    "script_task_snapshots",
    "seal_task_snapshot",
    "user_task_snapshot",
]
