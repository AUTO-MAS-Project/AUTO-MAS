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


from pathlib import Path

# app/utils/paths.py → app/utils → app → 仓库根，与 main.py 里 current_dir 的
# 计算方式同源，只是从这个文件自己的位置往上数三层。
SOURCE_ROOT = Path(__file__).resolve().parents[2]


def resource_path(*parts: str) -> Path:
    """解析源码内置资源（res/ 下的图片、音效、模板、词表等）的绝对路径。

    受 AUTO-MAS-Runtime 监督时，工作目录是 <app-root>/，源码在其
    <app-root>/repo/ 子目录，监督器整体替换 repo/ 来更新，因此两者不再相等，
    不能再用 Path.cwd() 定位内置资源；只有随源码分发、随源码更新的只读资源
    才走这里——用户数据（config/data/history/script/debug/plugins）必须继续
    相对 Path.cwd() 解析，否则监督器更新 repo/ 时会把用户数据一并冲掉。

    Args:
        *parts: 相对 res/ 目录的路径片段，如 resource_path("images", "materials")。

    Returns:
        拼接后的绝对路径，不检查是否存在。
    """

    return SOURCE_ROOT.joinpath("res", *parts)
