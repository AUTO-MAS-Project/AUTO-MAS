#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""终末地官方启动器（鹰角多游戏启动器）路径发现与反推。

启动器实测安装布局::

    <启动器根>/Launcher.exe                        稳定入口，配置里存的就是它
    <启动器根>/<版本>/Games.exe                     界面窗口进程；版本目录随自更新变化
    <启动器根>/games/EndField Game/Endfield.exe     游戏客户端（Game.Path）

用户配置的是游戏客户端（Endfield.exe），启动器位置由它反推：从客户端目录向上找到含
``Launcher.exe`` 且带版本子目录（内含 ``Games.exe``）的层即为启动器根。版本子目录
是自动识别必须的证据——``Launcher.exe`` 是常见文件名，只按名匹配会误认无关程序。

只回答「在哪」：不改配置，调用方决定是展示、落盘还是运行期兜底。
"""

from pathlib import Path

_LAUNCHER_EXE = "Launcher.exe"
# 版本目录内的界面程序，用作安装布局哨兵。
_VERSION_MARKER = "Games.exe"


def launcher_root(launcher_path: Path) -> Path:
    """所选启动器程序所在目录，不扩大到用户指定目录之外。"""
    return launcher_path.parent


def _has_version_dir(root: Path) -> bool:
    """根目录下存在版本子目录（内有 Games.exe）时才算启动器安装根。"""

    try:
        return any(
            (child / _VERSION_MARKER).is_file()
            for child in root.iterdir()
            if child.is_dir()
        )
    except OSError:
        return False


def discover_launcher_exe(client_exe: Path) -> Path | None:
    """从游戏客户端 exe 反推启动器根目录下的 ``Launcher.exe``。

    自近向远逐级上溯，取第一个同时满足「直接含 Launcher.exe」与「带版本子目录」的
    祖先作为启动器根；客户端已被移走或布局不符时返回 ``None``，由调用方决定是否提示
    用户手动选择。
    """

    if not client_exe.is_file():
        return None
    for ancestor in client_exe.parents:
        candidate = ancestor / _LAUNCHER_EXE
        if candidate.is_file() and _has_version_dir(ancestor):
            return candidate
    return None


def is_launcher_exe(path: Path) -> bool:
    """手动指定只要求现存的 exe，避免安装布局变化后无法兜底。"""

    return path.suffix.casefold() == ".exe" and path.is_file()


def resolve_launcher_exe(client_exe: Path, configured_path: str = "") -> Path | None:
    """手动路径必须有效；未指定时才随客户端位置自动识别。"""

    if configured_path.strip():
        path = Path(configured_path.strip())
        if not is_launcher_exe(path):
            raise ValueError(
                "终末地启动器路径无效，请选择存在的启动器可执行文件（.exe）"
            )
        return path
    return discover_launcher_exe(client_exe)
