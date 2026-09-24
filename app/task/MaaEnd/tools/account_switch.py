#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


"""MaaEnd 内置账号切换任务配置。"""

from typing import Any


def replace_account_switch_task(
    tasks: list[dict[str, Any]],
    account_id: str,
    controller_type: str,
    task_id: str,
) -> None:
    """按当前账号设置唯一的 MaaEnd 切号任务。"""

    tasks[:] = [task for task in tasks if task.get("taskName") != "AccountSwitch"]
    if not account_id:
        return

    tasks.insert(
        0,
        {
            "id": task_id,
            "taskName": "AccountSwitch",
            "enabled": True,
            "enabledByController": {controller_type: True},
            "optionValues": {
                "AccountSwitchLastFourDigits": {
                    "type": "input",
                    "values": {"LastFourDigits": account_id[-4:]},
                }
            },
        },
    )
