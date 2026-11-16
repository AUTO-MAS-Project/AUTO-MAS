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

"""特调钩子的选择上下文与几个共用小工具。

单独成一个模块，是因为特调包（``app/task/M9A``、``app/task/MSS``）在启动早期就会被配置迁移
导入，导入期不能拉起建计划的核心 runner；``flavor.py`` 引了它，这里只依赖标准库与 interface
模型。契约写在 ``flavor.py`` 的模块说明里，``flavor.py`` 原样转出这里的名字。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.task.MaaFW.tools.core.interface.models import MaaFWInterface


@dataclass(frozen=True)
class MaaFWSelectionContext:
    """引擎调 ``decorate_selection`` 时交给钩子的只读上下文。"""

    script_config: Any
    """脚本（托管）配置。"""

    user_config: Any
    """本次运行的账号配置。"""

    resource_name: str | None
    """运行时实际生效的资源（``resolve_run_selection``；脚本资源留空时已按控制器回落）。"""

    excluded_task_ids: frozenset[str]
    """引擎判定本轮不跑的实例 id：用户设成红灯的、今天不在运行日的。"""

    log: Callable[[str], None]
    """写一行账号运行日志；钩子在工作线程里跑，这个回调可以直接调。"""


def task_name_for_entry(interface_model: MaaFWInterface, entry: str) -> str | None:
    """interface 里第一个 ``entry`` 等于给定值的任务名；找不到返回 None。"""

    for task in interface_model.task:
        if str(task.entry or "") == entry:
            return task.name
    return None


def config_value(config: Any, group: str, name: str) -> Any:
    """``config.<group>.<name>``；缺分组或缺字段时返回 None。"""

    try:
        return getattr(getattr(config, group), name)
    except Exception:  # noqa: BLE001 - 假配置对象缺项时按空处理
        return None


__all__ = [
    "MaaFWSelectionContext",
    "config_value",
    "task_name_for_entry",
]
