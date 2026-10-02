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

"""M9A 受管任务：「启动游戏」「切换账号」「关闭游戏」由 MAS 全权控制，不在用户队列里。

运行期由特调按固定顺序补（启动 → 切号 → …… → 关闭），账号取用户的 ``Info.Account``。
队列里残留的这三类任务（beta.1 迁移留下的、#1012 补回的、预设带进来的、手加的、通用 MaaFW
脚本换成 M9A 带过来的）一律按同一套规则整理，规则只写在这里，四个入口共用：

- 运行前装饰（``flavor.decorate_selection``）；
- 每次启动对全部 M9A 用户的整理（``migration.normalize_m9a_managed_entries``）；
- 旧版专项迁移与 beta.1 补救（``migration.py``）；
- 保存用户配置、导入外壳配置、恢复备份时写 ``Task.TaskSnapshot`` 的入口（经引擎的可选钩子
  ``sanitize_task_snapshot``，见 ``flavor.py``）。

规则（按 entry 判，不按任务名）：

1. 启动游戏、关闭游戏：移除。
2. 切换账号：只数「勾选且账号非空」的（有效切号）。

   - 恰好 1 个：账号进 ``Info.Account``，从队列移除。``Info.Account`` 原来非空且不同时以
     队列里的为准（旧版与之前的运行实际切的都是它），原值记进备注。
   - 0 个（未勾选或账号为空）：直接移除，不动 ``Info.Account``。
   - 2 个及以上、脚本资源是官服：队列原样保留（切号连同选项一个不动），备注与通知里写明要拆成
     几个用户；运行期拒绝运行该用户。M9A 一个用户对应一个账号，这种队列 MAS 没法替用户拆。
   - 2 个及以上、资源不是官服：切号任务只在官服生效，它们从来没跑过，直接移除。

这份保留状态的判据是**队列内容本身**（有效切号 ≥ 2 且官服），不是某个标记：普通保存把同一份
队列交回来，照样判成保留，不会被抹掉；用户删到只剩 1 个时下一次保存就把它收进「账号」。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

STARTUP_ENTRY = "StartUp"
SWITCH_ACCOUNT_ENTRY = "SwitchAccount"
CLOSE_ENTRY = "Close1999"
#: 由 MAS 控制、不许留在用户队列里的三类任务（按 entry）。
MANAGED_ENTRIES = frozenset({STARTUP_ENTRY, SWITCH_ACCOUNT_ENTRY, CLOSE_ENTRY})
OFFICIAL_RESOURCE_NAME = "官服"
#: 写进用户备注的前缀，备注里有同一句就不再追加（启动整理幂等靠它）。
NOTE_TAG = "[M9A]"
_EMPTY_NOTES = ("", "无")


class M9ASplitRequiredError(ValueError):
    """用户队列里有多个有效切号：M9A 一个用户对应一个账号，要先拆成多个用户。"""


def split_message(accounts: list[str]) -> str:
    """多个切号要拆用户的那句话；用户备注、启动通知、运行日志都用它。"""

    count = len(accounts)
    return (
        f"该用户队列里有 {count} 个切换账号（账号 {'、'.join(accounts)}），"
        f"M9A 一个用户对应一个账号，请拆成 {count} 个用户"
        "（每个用户在上方「账号」填一个）后才能正常运行"
    )


def replaced_account_note(old: str, new: str) -> str:
    return f"{NOTE_TAG} 原「账号」{old} 已换成队列里切换账号的目标账号 {new}"


def append_note(notes: str, message: str) -> str:
    """备注里追加一句；原来是空或「无」就直接换成这句。"""

    text = str(notes or "").strip()
    return message if text in _EMPTY_NOTES else f"{text} {message}"


@dataclass
class Settlement:
    """一份快照按规则整理后的结果。"""

    snapshot: dict[str, Any]
    changed: bool = False
    #: 移除的任务实例 id（队列顺序）。
    removed: list[str] = field(default_factory=list)
    #: 恰好一个有效切号时要进 ``Info.Account`` 的账号；否则为空。
    account: str = ""
    #: 有效切号 ≥ 2 且保留在队列里时，各自的账号（队列顺序）。
    split_accounts: list[str] = field(default_factory=list)


def settle_snapshot(
    snapshot: dict[str, Any],
    *,
    entry_of: Callable[[str], str],
    account_of: Callable[[str, Any], str],
    official: bool,
) -> Settlement:
    """按模块说明的规则整理一份 ``{taskOrder, taskChecked, taskOptions}``，不改入参。

    ``entry_of(task_id)`` 给出实例的 entry（重复实例 id 由调用方还原成任务名）；
    ``account_of(task_id, 该实例的选项)`` 给出切号实例的目标账号。
    """

    order = [str(task_id) for task_id in snapshot.get("taskOrder") or []]
    raw_checked = snapshot.get("taskChecked")
    checked = raw_checked if isinstance(raw_checked, dict) else {}
    raw_options = snapshot.get("taskOptions")
    options = raw_options if isinstance(raw_options, dict) else {}

    switches: list[tuple[str, str]] = []  # (实例 id, 账号) —— 只收有效切号
    for task_id in order:
        if entry_of(task_id) != SWITCH_ACCOUNT_ENTRY:
            continue
        if not checked.get(task_id, False):
            continue  # 与运行期同一口径：taskChecked 里没有的算没勾
        account = str(account_of(task_id, options.get(task_id)) or "").strip()
        if account:
            switches.append((task_id, account))

    keep_switches = official and len(switches) >= 2
    removed = [
        task_id
        for task_id in order
        if entry_of(task_id) in MANAGED_ENTRIES
        and not (keep_switches and entry_of(task_id) == SWITCH_ACCOUNT_ENTRY)
    ]
    removed_set = set(removed)
    kept_order = [task_id for task_id in order if task_id not in removed_set]
    kept_set = set(kept_order)

    def keep_key(task_id: Any) -> bool:
        key = str(task_id)
        if key in removed_set:
            return False
        # 不在队列里的孤儿键：受管任务的一并清掉（保留态的切号都在队列里）
        return key in kept_set or entry_of(key) not in MANAGED_ENTRIES

    new_checked = {key: value for key, value in checked.items() if keep_key(key)}
    new_options = {key: value for key, value in options.items() if keep_key(key)}
    changed = bool(removed) or new_checked != checked or new_options != options

    settled = dict(snapshot)
    if changed:
        settled["taskOrder"] = kept_order
        settled["taskChecked"] = new_checked
        settled["taskOptions"] = new_options
    return Settlement(
        snapshot=settled,
        changed=changed,
        removed=removed,
        account=switches[0][1] if len(switches) == 1 else "",
        split_accounts=[account for _, account in switches] if keep_switches else [],
    )


@dataclass
class InfoChange:
    """整理结果落到用户 ``Info`` 上的改动。"""

    account: str | None = None
    notes: str | None = None
    #: 被队列里的切号账号取代的原「账号」（没有取代就是空串）。
    replaced_account: str = ""
    #: 这次新写进备注的拆分提示（备注里已经有同一句就是空串）。
    split_note: str = ""

    def updates(self) -> dict[str, str]:
        result: dict[str, str] = {}
        if self.account is not None:
            result["Account"] = self.account
        if self.notes is not None:
            result["Notes"] = self.notes
        return result


def settle_user_info(
    settlement: Settlement,
    *,
    account: str,
    notes: str,
    note_split: bool,
) -> InfoChange:
    """整理结果对 ``Info.Account`` / ``Info.Notes`` 的改动；``note_split`` 为假时不写拆分提示。"""

    change = InfoChange()
    current_account = str(account or "").strip()
    current_notes = str(notes or "")
    if settlement.account and settlement.account != current_account:
        change.account = settlement.account
        if current_account:
            change.replaced_account = current_account
            current_notes = append_note(
                current_notes,
                replaced_account_note(current_account, settlement.account),
            )
            change.notes = current_notes
    if settlement.split_accounts and note_split:
        message = f"{NOTE_TAG} {split_message(settlement.split_accounts)}"
        if message not in current_notes:
            change.split_note = message
            change.notes = append_note(current_notes, message)
    return change


def effective_switch_accounts(
    task_ids: Iterable[str],
    task_options: dict[str, Any],
    *,
    entry_of: Callable[[str], str],
    account_of: Callable[[str, Any], str],
) -> list[str]:
    """运行期的勾选列表里有效切号的账号（队列顺序）。"""

    accounts: list[str] = []
    for task_id in task_ids:
        if entry_of(task_id) != SWITCH_ACCOUNT_ENTRY:
            continue
        account = str(account_of(task_id, task_options.get(task_id)) or "").strip()
        if account:
            accounts.append(account)
    return accounts


def first_text_value(value: Any) -> str:
    """input 选项的值里第一个非空字符串（找不到约定字段时的兜底）。"""

    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for item in value.values():
            text = first_text_value(item)
            if text:
                return text
    return ""


__all__ = [
    "CLOSE_ENTRY",
    "InfoChange",
    "M9ASplitRequiredError",
    "MANAGED_ENTRIES",
    "NOTE_TAG",
    "OFFICIAL_RESOURCE_NAME",
    "STARTUP_ENTRY",
    "SWITCH_ACCOUNT_ENTRY",
    "Settlement",
    "append_note",
    "effective_switch_accounts",
    "first_text_value",
    "replaced_account_note",
    "settle_snapshot",
    "settle_user_info",
    "split_message",
]
