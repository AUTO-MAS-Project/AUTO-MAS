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

"""ModAVD 根目录的路径换算：根目录的规范化键、实例锁用的「主管理器程序」路径。

只算路径、不读根目录里的文件：组件齐不齐、版本、端口都问 ModAVD 命令行（``modavd check`` /
``list``，见 :mod:`.cli`）。
"""

from __future__ import annotations

import os
from pathlib import Path

from .constants import SDK_DIR


def root_key(root: str | Path) -> str:
    """根目录的规范化键，按它去重、按它查各张按根目录记的表（开机中、正在换上、更新状态与锁……）。

    按真实路径算（解开目录链接 / 符号链接）：管理器的根目录取自 ``Path(主程序).resolve()``，配置里登记的
    却可能是链接或别的写法，两边必须算出同一个键。路径不在时 ``realpath`` 照样给出规范化的结果。
    """
    try:
        return os.path.normcase(os.path.realpath(str(root)))
    except (OSError, ValueError):
        return os.path.normcase(os.path.abspath(str(root)))


def manager_key_exe(root: str | Path) -> Path:
    """这条安装的「主管理器程序」路径：``<根>\\sdk\\emulator\\emulator.exe``。

    它是 ``DeviceRef.manager_path`` 与实例锁的键，靠它反推根目录（:func:`root_from_manager_exe`），
    所以始终落在根目录下；只当键用，这个文件在不在都不影响（模拟器由 modavd 起）。
    """
    return Path(root) / SDK_DIR / "emulator" / "emulator.exe"


def root_from_manager_exe(manager_exe: str | Path) -> Path:
    """``<根>\\sdk\\emulator\\emulator.exe`` → ``<根>``。"""
    return Path(manager_exe).resolve().parents[2]


__all__ = [
    "manager_key_exe",
    "root_from_manager_exe",
    "root_key",
]
