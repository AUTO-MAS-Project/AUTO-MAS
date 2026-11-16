#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""ModAVD 开机前检查项的数据类型。

检查本身由 ModAVD 命令行做（``modavd check`` / ``start`` / ``create``）；这里只留 MAS 用来表示
检查项、拦截开机的类型：:func:`~.cli.map_cli_error` 和管理器据此把命令行的拦截项还原成
:class:`PrecheckFailed`，``/avd/status`` 把命令行给的检查项原样交给前端。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PrecheckItem:
    #: path / components / emulator / acceleration / vulkan / disk / memory
    id: str
    title: str
    #: ``None`` = 这项现在查不了（比如模拟器组件还没装）
    ok: bool | None
    #: 不满足时是否拒绝开机
    blocking: bool
    reason: str
    advice: str = ""

    def message(self) -> str:
        return f"{self.reason}。{self.advice}" if self.advice else self.reason


class PrecheckFailed(RuntimeError):
    """开机前检查有拦截项不满足。"""

    def __init__(self, item: PrecheckItem):
        super().__init__(item.message())
        self.item = item


__all__ = [
    "PrecheckFailed",
    "PrecheckItem",
]
