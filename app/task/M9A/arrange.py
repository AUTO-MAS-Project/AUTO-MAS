#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""M9A 的排队列与保存前整理：只吃 interface、队列与普通值，不读配置。

- :func:`arrange_m9a_queue`：建计划时，在展开任务快照（剔掉不可选任务与今天不在运行日的实例）之后、
  建计划之前调。三类受管任务（规则见 ``managed.py``）一律剔掉，再按固定顺序补：启动放队首；脚本资源为
  官服、账号非空且没开「MAS 登录」时切号紧跟启动，账号填进它唯一的 input 选项；关闭放队尾。队列里有多个
  有效切号时先写一行再抛 ``M9ASplitRequiredError``，整个账号不跑。
- :func:`settle_m9a_snapshot`：写 ``Task.TaskSnapshot`` 前按同一规则整理，返回整理后的快照与要并进
  ``Info`` 的字段。

登录方式、账号这些值由调用方从配置里取好传进来；``log`` 写一行账号运行日志。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.task.M9A.managed import (
    CLOSE_ENTRY,
    LOGIN_MODE_MAS,
    MANAGED_ENTRIES,
    OFFICIAL_RESOURCE_NAME,
    STARTUP_ENTRY,
    SWITCH_ACCOUNT_ENTRY,
    M9ASplitRequiredError,
    effective_switch_accounts,
    first_text_value,
    settle_snapshot,
    settle_user_info,
    split_message,
    supports_account_switch,
)
from app.task.MaaFW.blocks.maafw_interface.interface.models import (
    MaaFWInterface,
    resolve_task_instance_name,
    task_name_for_entry,
)


def arrange_m9a_queue(
    interface_model: MaaFWInterface,
    task_ids: list[str],
    task_options: dict[str, Any],
    *,
    resource_name: str | None,
    login_mode: str,
    user_account: str,
    log: Callable[[str], None],
) -> tuple[list[str], dict[str, Any]]:
    """按 M9A 的固定顺序重排队列，返回新的列表与选项；不改入参。

    ``resource_name`` 是运行时实际生效的资源（脚本资源留空时已按控制器回落）；``login_mode`` 是
    ``Run.LoginMode`` 去掉首尾空白；``user_account`` 是账号的 ``Info.Id`` 去掉首尾空白（队列里恰好一个
    有效切号时以队列里的为准）。
    """

    entry_of, account_of = _entry_and_account_readers(interface_model)
    supported = supports_account_switch(resource_name, login_mode=login_mode)
    queued_accounts = effective_switch_accounts(
        task_ids, task_options, entry_of=entry_of, account_of=account_of
    )
    if supported and len(queued_accounts) >= 2:
        # 一个账号对应一个账号：MAS 没法替用户决定这一轮切到哪个号，整个账号不跑
        message = split_message(queued_accounts)
        log(f"[M9A] {message}")
        raise M9ASplitRequiredError(message)

    # 三类受管任务一律剔掉，下面按固定顺序补；它们的选项也不再下发
    ids = [task_id for task_id in task_ids if entry_of(task_id) not in MANAGED_ENTRIES]
    options = {
        key: value
        for key, value in task_options.items()
        if entry_of(key) not in MANAGED_ENTRIES
    }
    if len(ids) != len(task_ids):
        log(
            "[M9A] 启动游戏、切换账号、关闭游戏由 MAS 控制，"
            "队列里的这几项已忽略并按固定顺序重新加入"
        )

    if not ids:
        # 除受管任务外一个都没勾：不补首尾，免得白白启动再关闭一次游戏；空队列交给引擎原有处理。
        return ids, options

    added: list[str] = []
    startup = task_name_for_entry(interface_model, STARTUP_ENTRY)
    if startup is None:
        log(
            f"[M9A] interface 里没有 entry 为 {STARTUP_ENTRY} 的任务，未自动加入启动游戏"
        )
    else:
        ids.insert(0, startup)
        added.append(startup)

    # 队列里恰好一个有效切号时以它为准，与启动整理的结果一致（整理会把它收进「账号」）
    account = queued_accounts[0] if len(queued_accounts) == 1 else user_account
    if account and supported:
        switch = task_name_for_entry(interface_model, SWITCH_ACCOUNT_ENTRY)
        if switch is None:
            log(
                f"[M9A] interface 里没有 entry 为 {SWITCH_ACCOUNT_ENTRY} 的任务，"
                "未自动加入切换账号"
            )
        else:
            # 紧跟在「启动游戏」后面；interface 里没有启动任务时放队首
            ids.insert(1 if startup is not None else 0, switch)
            added.append(switch)
            account_option = _account_option(interface_model, switch, account)
            if account_option is not None:
                options[switch] = account_option
            else:
                log("[M9A] 切换账号任务没有 input 类型的账号选项，账号未能填入")
    elif account:
        if login_mode == LOGIN_MODE_MAS:
            log(
                "[M9A] 已开启 MAS 登录：Info.Id 是 MAS 登录要选中的账号昵称，"
                "不再加入切换账号"
            )
        else:
            log(
                f"[M9A] 资源不是{OFFICIAL_RESOURCE_NAME}，Info.Id 只作备注，不自动切换账号"
            )

    close = task_name_for_entry(interface_model, CLOSE_ENTRY)
    if close is None:
        log(f"[M9A] interface 里没有 entry 为 {CLOSE_ENTRY} 的任务，未自动加入关闭游戏")
    else:
        ids.append(close)
        added.append(close)
    if added:
        log(f"[M9A] 已自动加入：{' / '.join(added)}")
    return ids, options


def settle_m9a_snapshot(
    interface_model: MaaFWInterface,
    snapshot: dict[str, Any],
    *,
    resource_name: str | None,
    login_mode: str,
    user_info: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """写 ``Task.TaskSnapshot`` 前按 ``managed.py`` 的规则整理。

    返回（整理后的快照, 要写进 ``Info`` 的字段）。多个有效切号的保留态原样放行，
    备注只由启动整理写，这里不写（账号页上有常驻提示）。``user_info`` 是这次写入之后该账号
    ``Info`` 的样子（``Id`` / ``Notes``）。
    """

    entry_of, account_of = _entry_and_account_readers(interface_model)
    settlement = settle_snapshot(
        snapshot,
        entry_of=entry_of,
        account_of=account_of,
        supports_switch=supports_account_switch(resource_name, login_mode=login_mode),
    )
    change = settle_user_info(
        settlement,
        account=str(user_info.get("Id") or ""),
        notes=str(user_info.get("Notes") or ""),
        note_split=False,
    )
    return (
        settlement.snapshot if settlement.changed else snapshot,
        change.updates(),
    )


def _account_field(
    interface_model: MaaFWInterface, task_name: str
) -> tuple[str, str] | None:
    """切换账号任务上第一个 input 型选项与它的第一个输入字段：``(选项名, 字段名)``。"""

    task = next((item for item in interface_model.task if item.name == task_name), None)
    if task is None:
        return None
    option_book = interface_model.option or {}
    for option_name in task.option or []:
        option = option_book.get(option_name)
        if option is None or getattr(option, "type", None) != "input":
            continue
        inputs = getattr(option, "inputs", None) or []
        if not inputs:
            continue
        return option_name, getattr(inputs[0], "name", None) or "账号"
    return None


def _account_option(
    interface_model: MaaFWInterface, task_name: str, account: str
) -> dict[str, Any] | None:
    """切换账号任务的账号选项值：``{选项名: {第一个输入字段: 账号}}``。"""

    found = _account_field(interface_model, task_name)
    if found is None:
        return None
    option_name, field_name = found
    return {option_name: {field_name: account}}


def _entry_and_account_readers(
    interface_model: MaaFWInterface,
) -> tuple[Callable[[str], str], Callable[[str, Any], str]]:
    """按 interface 读实例 entry 与切号目标账号的两个函数（``managed.py`` 的规则要用）。"""

    task_by_name = {task.name: task for task in interface_model.task}
    field_cache: dict[str, tuple[str, str] | None] = {}

    def name_of(task_id: str) -> str:
        return resolve_task_instance_name(str(task_id), task_by_name)

    def entry_of(task_id: str) -> str:
        task = task_by_name.get(name_of(task_id))
        return str(task.entry or "") if task is not None else ""

    def account_of(task_id: str, options: Any) -> str:
        if not isinstance(options, dict):
            return ""
        name = name_of(task_id)
        if name not in field_cache:
            field_cache[name] = _account_field(interface_model, name)
        found = field_cache[name]
        if found is not None:
            value = options.get(found[0])
            if isinstance(value, dict):
                return str(value.get(found[1]) or "").strip()
            return first_text_value(value)
        return first_text_value(options)

    return entry_of, account_of


__all__ = ["arrange_m9a_queue", "settle_m9a_snapshot"]
