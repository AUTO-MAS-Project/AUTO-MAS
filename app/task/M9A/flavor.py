#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""M9A 特调：MaaFW 引擎之上唯一的运行期专项逻辑，以及"这是不是 M9A 项目"的判据。

「启动游戏」（entry ``StartUp``）、「切换账号」（entry ``SwitchAccount``）、「关闭游戏」
（entry ``Close1999``）由 MAS 全权控制（规则见 ``managed.py``）。运行前先把勾选列表里这三类
全部剔掉，再按固定顺序补：启动放队首；脚本资源为官服且有账号时切号紧跟启动，账号填进它唯一的
input 选项；关闭放队尾。用户排的顺序不影响这三项。队列里有多个有效切号的用户拒绝运行。

按 entry 而不是按任务名找：任务名会随 M9A 的版本与语言变，entry 是它的 pipeline 入口，稳定。

另实现了引擎的可选钩子 ``sanitize_task_snapshot``（写用户任务快照前按同一规则整理）。
除此之外 M9A 与通用 MaaFW 没有任何运行期差别。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from app.task.M9A.managed import (
    CLOSE_ENTRY,
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
)
from app.task.MaaFW.tools.core.interface.models import (
    MaaFWInterface,
    resolve_task_instance_name,
)

TYPE_KEY = "M9A"

# 旧版 M9A 专项按名字记任务；名字随版本变过（「每日心相」→「每日心相（意志解析）」），
# 迁移时按 entry 反查。这张表只服务迁移与无 interface 降级，运行期不用。
LEGACY_ENTRY_ALIASES: dict[str, str] = {
    "每日心相（意志解析）": "Psychube",
    "每日心相": "Psychube",
    "自动深眠": "Limbo",
    "自动醒梦": "Lucidscape",
    "启动游戏": STARTUP_ENTRY,
    "关闭游戏": CLOSE_ENTRY,
    "切换账号": SWITCH_ACCOUNT_ENTRY,
}
# 没有 interface 可查时（迁移的降级路径）按 v4.9 的名字兜底。
FALLBACK_TASK_NAMES: dict[str, str] = {
    "Psychube": "每日心相（意志解析）",
    "Limbo": "自动深眠",
    "Lucidscape": "自动醒梦",
    STARTUP_ENTRY: "启动游戏",
    CLOSE_ENTRY: "关闭游戏",
    SWITCH_ACCOUNT_ENTRY: "切换账号",
}

_GITHUB_M9A_RE = re.compile(r"(^|[/:])MAA1999/M9A(\.git)?/?$", re.IGNORECASE)


def task_name_for_entry(interface_model: MaaFWInterface, entry: str) -> str | None:
    """interface 里第一个 ``entry`` 等于给定值的任务名；找不到返回 None。"""

    for task in interface_model.task:
        if str(task.entry or "") == entry:
            return task.name
    return None


def is_m9a_project(interface_model: MaaFWInterface | dict[str, Any]) -> bool:
    """三条判据任一命中：``mirrorchyan_rid == M9A``、``github`` 指向 MAA1999/M9A、``name == m9a``。"""

    if isinstance(interface_model, dict):
        rid = interface_model.get("mirrorchyan_rid")
        github = interface_model.get("github")
        name = interface_model.get("name")
    else:
        rid = getattr(interface_model, "mirrorchyan_rid", None)
        github = getattr(interface_model, "github", None)
        name = getattr(interface_model, "name", None)
    if str(rid or "").strip().casefold() == "m9a":
        return True
    if _GITHUB_M9A_RE.search(str(github or "").strip()):
        return True
    return str(name or "").strip().casefold() == "m9a"


class M9AFlavor:
    """满足 ``MaaFWFlavor`` 协议的 M9A 特调对象。"""

    type_key = TYPE_KEY

    def matches_project(self, interface_model: MaaFWInterface) -> bool:
        return is_m9a_project(interface_model)

    def decorate_selection(
        self,
        interface_model: MaaFWInterface,
        task_ids: list[str],
        task_options: dict[str, Any],
        *,
        script_config: Any,
        user_config: Any,
        resource_name: str | None,
        send_log: Callable[[str], None] | None,
    ) -> tuple[list[str], dict[str, Any]]:
        del script_config  # 资源名由引擎按脚本配置解析后传入，这里不再读配置

        def log(message: str) -> None:
            if send_log is not None:
                send_log(message)

        entry_of, account_of = _entry_and_account_readers(interface_model)
        official = str(resource_name or "").strip() == OFFICIAL_RESOURCE_NAME
        queued_accounts = effective_switch_accounts(
            task_ids, task_options, entry_of=entry_of, account_of=account_of
        )
        if official and len(queued_accounts) >= 2:
            # 一个用户对应一个账号：MAS 没法替用户决定这一轮切到哪个号，整个用户不跑
            message = split_message(queued_accounts)
            log(f"[M9A] {message}")
            raise M9ASplitRequiredError(message)

        # 三类受管任务一律剔掉，下面按固定顺序补；它们的选项也不再下发
        ids = [
            task_id for task_id in task_ids if entry_of(task_id) not in MANAGED_ENTRIES
        ]
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
        account = (
            queued_accounts[0]
            if len(queued_accounts) == 1
            else str(_get(user_config, "Info", "Account") or "").strip()
        )
        if account and official:
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
            log(
                f"[M9A] 资源不是{OFFICIAL_RESOURCE_NAME}，Info.Account 只作备注，不自动切换账号"
            )

        close = task_name_for_entry(interface_model, CLOSE_ENTRY)
        if close is None:
            log(
                f"[M9A] interface 里没有 entry 为 {CLOSE_ENTRY} 的任务，未自动加入关闭游戏"
            )
        else:
            ids.append(close)
            added.append(close)
        if added:
            log(f"[M9A] 已自动加入：{' / '.join(added)}")
        return ids, options

    def sanitize_task_snapshot(
        self,
        interface_model: MaaFWInterface,
        snapshot: dict[str, Any],
        *,
        script_config: Any,
        resource_name: str | None,
        user_info: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """引擎的可选钩子：写 ``Task.TaskSnapshot`` 前按 ``managed.py`` 的规则整理。

        返回（整理后的快照, 要写进 ``Info`` 的字段）。多个有效切号的保留态原样放行，
        备注只由启动整理写，这里不写（用户页上有常驻提示）。
        """

        del script_config  # 资源由引擎按建运行计划的同一口径解析后传入
        entry_of, account_of = _entry_and_account_readers(interface_model)
        settlement = settle_snapshot(
            snapshot,
            entry_of=entry_of,
            account_of=account_of,
            official=str(resource_name or "").strip() == OFFICIAL_RESOURCE_NAME,
        )
        change = settle_user_info(
            settlement,
            account=str(user_info.get("Account") or ""),
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


def _get(config: Any, group: str, name: str) -> Any:
    try:
        return config.get(group, name)
    except Exception:  # noqa: BLE001 - 假配置对象缺项时按空处理
        return None


FLAVOR = M9AFlavor()

__all__ = [
    "CLOSE_ENTRY",
    "FALLBACK_TASK_NAMES",
    "FLAVOR",
    "LEGACY_ENTRY_ALIASES",
    "M9AFlavor",
    "MANAGED_ENTRIES",
    "OFFICIAL_RESOURCE_NAME",
    "STARTUP_ENTRY",
    "SWITCH_ACCOUNT_ENTRY",
    "TYPE_KEY",
    "is_m9a_project",
    "task_name_for_entry",
]
