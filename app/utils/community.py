#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
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

#   Contact: DLmaster_361@163.com


"""游戏社区账号组的纯逻辑辅助函数。"""

import re
from collections.abc import Iterable


_DEFAULT_ACCOUNT_NAME_PATTERN = re.compile(r"^用户\s*(\d+)$")


def next_community_account_name(existing_names: Iterable[object]) -> str:
    """返回首个未占用的默认账号组名称。

    历史版本同时出现过 ``用户1`` 和 ``用户 1``，两种写法视为同一编号。
    自定义名称不参与默认编号占用。
    """

    occupied: set[int] = set()
    for value in existing_names:
        match = _DEFAULT_ACCOUNT_NAME_PATTERN.fullmatch(str(value or "").strip())
        if match is not None:
            occupied.add(int(match.group(1)))

    index = 1
    while index in occupied:
        index += 1
    return f"用户 {index}"
