#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""引擎对外的领域异常。

上层只需要区分两类：``UpdateAborted``（用户主动中止，保留现场可续传）
与其它异常（流程失败）。
"""

from __future__ import annotations

__all__ = ["UpdateAborted"]


class UpdateAborted(RuntimeError):
    """用户中止了本轮更新。

    由 ``should_abort`` 判定在下载与打补丁的边界抛出；已落盘的合法文件不回滚，
    ``config.ini`` 也不会被写，因此重新发起即可从断点继续。
    """
