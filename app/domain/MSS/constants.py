#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 ClozyA
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

"""MSS 计划表使用的公开 interface 关卡选项。"""

MSS_TRIBULATION_STAGES = (
    "基础试炼",
    "晋升试炼-怪诞舞者",
    "晋升试炼-终宵萤辉",
    "晋升试炼-热嘟噜噗男爵",
    "技巧试炼-节奏游戏卡带",
    "技巧试炼-射击游戏卡带",
    "技巧试炼-格斗游戏卡带",
    "纹章试炼-好市民点数",
    "纹章试炼-协会贡献证",
    "纹章试炼-恩赐消费券",
)
"""MSS 悬赏试炼关卡：与外壳 interface 的 `悬赏试炼关卡` 选项逐一对应（v1.4.4 共 10 项）

**上游加关卡或改名时必须同步这里**，否则计划表里存的旧关卡会被折算回默认值。
"""

MSS_DEFAULT_TRIBULATION_STAGE = MSS_TRIBULATION_STAGES[0]
"""MSS 悬赏试炼的默认关卡"""
