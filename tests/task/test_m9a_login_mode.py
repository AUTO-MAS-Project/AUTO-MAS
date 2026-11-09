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

"""M9A「MAS 登录 B 服」（``Run.LoginMode == "Mas"``）的可观察契约。

可达场景：编辑页把「登录方式」切到「由 MAS 登录 B 服」，账号填登录记录里显示的完整昵称。
守护三件事：

1. 该模式下切号任务不再下发（``decorate_selection`` / ``settle_snapshot``），账号只作为
   MAS 登录要选中的昵称——这是用户能看到的行为差异（队列里不再出现「切换账号」）；
2. 会话内的多个有效切号不再判「要拆用户」：队列里的切号会被直接移出队列；
3. 登录钩子只在 Mas 模式真正做事，非 Mas 直接返回空串；Mas 且账号为空时响亮失败
   （都在任何 adb 操作之前判定，测试不需要模拟器）。

不覆盖：引擎 ``runner_task._ensure_logged_in`` 的调用点与真实 adb 登录流程（前者是
一行动调用，后者按 ``docs/testing/e2e.md`` 在作者环境用真实模拟器验证）。
"""

from __future__ import annotations

import asyncio

import pytest

from app.task.M9A.flavor import FLAVOR
from app.task.M9A.managed import (
    LOGIN_MODE_MAS,
    SWITCH_ACCOUNT_ENTRY,
    settle_snapshot,
    supports_account_switch,
)
from app.task.MaaFW.tools.core.interface.models import MaaFWInterface
from app.task.MaaFW.tools.embedded.flavor import MaaFWLoginRequired

INTERFACE = MaaFWInterface.model_validate(
    {
        "interface_version": 2,
        "name": "m9a",
        "controller": [{"name": "ADB", "type": "Adb"}],
        "resource": [
            {
                "name": "官服",
                "path": ["./resource/base"],
                "controller": ["ADB"],
            }
        ],
        "task": [
            {"name": "启动游戏", "entry": "StartUp"},
            {"name": "切换账号", "entry": "SwitchAccount", "option": ["目标账号"]},
            {"name": "关闭游戏", "entry": "Close1999"},
            {"name": "每日心相", "entry": "Psychube"},
        ],
        "option": {
            "目标账号": {"type": "input", "inputs": [{"name": "账号"}]},
        },
    }
)
ENTRY_BY_NAME = {task.name: task.entry for task in INTERFACE.task}


class _Info:
    def __init__(self, account: str) -> None:
        self.Account = account
        self.Notes = ""


class _User:
    def __init__(self, account: str) -> None:
        self.Info = _Info(account)


class _Run:
    def __init__(self, mode: str) -> None:
        self.LoginMode = mode


class _Script:
    def __init__(self, mode: str) -> None:
        self.Run = _Run(mode)


def _decorate(
    mode: str, account: str = "示例账号"
) -> tuple[list[str], dict, list[str]]:
    logs: list[str] = []
    ids, options = FLAVOR.decorate_selection(
        INTERFACE,
        ["每日心相"],
        {},
        script_config=_Script(mode),
        user_config=_User(account),
        resource_name="官服",
        send_log=logs.append,
    )
    return [ENTRY_BY_NAME.get(task_id, task_id) for task_id in ids], options, logs


def test_mas_mode_does_not_queue_switch_account() -> None:
    entries, options, logs = _decorate(LOGIN_MODE_MAS)
    assert entries == ["StartUp", "Psychube", "Close1999"]
    assert SWITCH_ACCOUNT_ENTRY not in entries
    assert all(SWITCH_ACCOUNT_ENTRY not in entry for entry in entries)
    assert any("MAS 登录" in line for line in logs)
    assert options == {}


def test_project_mode_keeps_switch_account_with_nickname() -> None:
    entries, options, _ = _decorate("Project")
    assert entries == ["StartUp", "SwitchAccount", "Psychube", "Close1999"]
    switch_id = next(
        task_id
        for task_id, entry in ENTRY_BY_NAME.items()
        if entry == SWITCH_ACCOUNT_ENTRY
    )
    assert options[switch_id] == {"目标账号": {"账号": "示例账号"}}


def test_supports_account_switch_reads_login_mode() -> None:
    assert supports_account_switch("官服") is True
    assert supports_account_switch("官服", login_mode="Project") is True
    assert supports_account_switch("官服", login_mode=LOGIN_MODE_MAS) is False
    assert supports_account_switch("B 服") is False
    assert supports_account_switch("", login_mode=LOGIN_MODE_MAS) is False


def test_startup_failure_aborts_round() -> None:
    # Mas 模式下 StartUp 就是「从标题页进游戏」那一步，失败后继续跑任务只会跑在错的位置上
    assert "StartUp" in FLAVOR.abort_round_entries
    assert SWITCH_ACCOUNT_ENTRY in FLAVOR.abort_round_entries


def test_settle_snapshot_drops_switches_in_mas_mode() -> None:
    snapshot = {
        "taskOrder": ["心相", "切号甲", "切号乙"],
        "taskChecked": {"心相": True, "切号甲": True, "切号乙": True},
        "taskOptions": {
            "切号甲": {"目标账号": {"账号": "甲"}},
            "切号乙": {"目标账号": {"账号": "乙"}},
        },
    }
    entry_of = {
        "心相": "Psychube",
        "切号甲": SWITCH_ACCOUNT_ENTRY,
        "切号乙": SWITCH_ACCOUNT_ENTRY,
    }.get

    def account_of(task_id: str, options: object) -> str:
        value = (options or {}).get("目标账号", {}) if isinstance(options, dict) else {}
        return str(value.get("账号") or "")

    settled = settle_snapshot(
        snapshot,
        entry_of=entry_of,
        account_of=account_of,
        supports_switch=False,
    )
    assert settled.removed == ["切号甲", "切号乙"]
    assert settled.snapshot["taskOrder"] == ["心相"]
    assert settled.split_accounts == []
    assert settled.account == ""


def test_login_hook_skips_in_project_mode() -> None:
    message = asyncio.run(
        FLAVOR.ensure_logged_in(
            script_config=_Script("Project"),
            user_config=_User("示例账号"),
            resource_name="官服",
            package_name="",
            adb_path=None,
            adb_address="127.0.0.1:1",
            progress=None,
        )
    )
    assert message == ""


def test_login_hook_requires_account_in_mas_mode() -> None:
    with pytest.raises(MaaFWLoginRequired):
        asyncio.run(
            FLAVOR.ensure_logged_in(
                script_config=_Script(LOGIN_MODE_MAS),
                user_config=_User(""),
                resource_name="官服",
                package_name="",
                adb_path=None,
                adb_address="127.0.0.1:1",
                progress=None,
            )
        )
