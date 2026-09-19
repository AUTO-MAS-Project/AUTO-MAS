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

运行前把用户勾选的任务列表装饰一遍：队列头加「启动游戏」（entry ``StartUp``），脚本资源
为官服且用户填了 ``Info.Account`` 时紧接着加「切换账号」（entry ``SwitchAccount``，账号填进
它唯一的 input 选项），队列尾加「关闭游戏」（entry ``Close1999``）。队列里已经有的不重复加、
也不改用户自己配的选项。除此之外 M9A 与通用 MaaFW 没有任何运行期差别。

按 entry 而不是按任务名找：任务名会随 M9A 的版本与语言变，entry 是它的 pipeline 入口，稳定。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from app.task.MaaFW.tools.core.automas_maafw_interface.models import (
    MaaFWInterface,
    resolve_task_instance_name,
)

TYPE_KEY = "M9A"
STARTUP_ENTRY = "StartUp"
SWITCH_ACCOUNT_ENTRY = "SwitchAccount"
CLOSE_ENTRY = "Close1999"
OFFICIAL_RESOURCE_NAME = "官服"

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

        if not task_ids:
            # 一个任务都没勾：不补首尾，免得白白启动再关闭一次游戏；空队列交给引擎原有处理。
            return list(task_ids), dict(task_options)

        valid_names = {task.name for task in interface_model.task}
        present = {
            resolve_task_instance_name(task_id, valid_names) for task_id in task_ids
        }
        ids = list(task_ids)
        options = dict(task_options)
        added: list[str] = []

        startup = task_name_for_entry(interface_model, STARTUP_ENTRY)
        if startup is None:
            log(
                f"[M9A] interface 里没有 entry 为 {STARTUP_ENTRY} 的任务，未自动加入启动游戏"
            )
        elif startup not in present:
            ids.insert(0, startup)
            present.add(startup)
            added.append(startup)
        elif ids and resolve_task_instance_name(ids[0], valid_names) != startup:
            log(
                f"[M9A] 队列里已有「{startup}」但不在开头，按你排的顺序执行；"
                "它前面的任务会在游戏未启动时运行"
            )

        account = str(_get(user_config, "Info", "Account") or "").strip()
        if account and str(resource_name or "").strip() == OFFICIAL_RESOURCE_NAME:
            switch = task_name_for_entry(interface_model, SWITCH_ACCOUNT_ENTRY)
            if switch is None:
                log(
                    f"[M9A] interface 里没有 entry 为 {SWITCH_ACCOUNT_ENTRY} 的任务，"
                    "未自动加入切换账号"
                )
            elif switch not in present:
                # 紧跟在「启动游戏」后面：它在哪就插在它后面，不在队列里就插到队首。
                position = 0
                if startup is not None:
                    for i, task_id in enumerate(ids):
                        if resolve_task_instance_name(task_id, valid_names) == startup:
                            position = i + 1
                            break
                ids.insert(position, switch)
                present.add(switch)
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
        elif close not in present:
            ids.append(close)
            present.add(close)
            added.append(close)
        if added:
            log(f"[M9A] 已自动补上：{' / '.join(added)}")
        return ids, options


def _account_option(
    interface_model: MaaFWInterface, task_name: str, account: str
) -> dict[str, Any] | None:
    """切换账号任务上第一个 input 型选项：``{选项名: {第一个输入字段: 账号}}``。"""

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
        field_name = getattr(inputs[0], "name", None) or "账号"
        return {option_name: {field_name: account}}
    return None


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
    "OFFICIAL_RESOURCE_NAME",
    "STARTUP_ENTRY",
    "SWITCH_ACCOUNT_ENTRY",
    "TYPE_KEY",
    "is_m9a_project",
    "task_name_for_entry",
]
