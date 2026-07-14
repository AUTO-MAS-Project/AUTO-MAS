#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..adapter.autoproxy import OkScriptAutoProxyTask


class OkScriptReportHandler:
    """项目专属执行汇报处理器。"""

    async def start(self, runtime: "OkScriptAutoProxyTask") -> None:
        """在当前用户运行开始前启动可选的汇报接管。"""

    async def capture(
        self,
        runtime: "OkScriptAutoProxyTask",
        log: str,
    ) -> None:
        """从脚本日志接管项目专属汇报。"""

    async def apply(self, runtime: "OkScriptAutoProxyTask") -> None:
        """将项目专属汇报结果写入 MAS。"""

    async def stop(self, runtime: "OkScriptAutoProxyTask") -> None:
        """停止当前用户运行关联的可选汇报接管。"""
