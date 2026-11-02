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
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""OneDragon 启动器发现与选择；不加载任务运行时。"""

from pathlib import Path

from app.utils.common.log import logger as _utils_logger

logger = _utils_logger.get_logger("ZZZ-OD 自动代理")

# 启动器标签 → exe 文件名（集成=WithRuntime 打包的 RuntimeLauncher；原始=旧安装器
# Launcher；.bak 为启动器自更新残留，不参与发现）。元组顺序即默认发现顺序（集成优先）
_ZZZOD_LAUNCHER_BOOK = {
    "集成": "OneDragon-RuntimeLauncher.exe",
    "原始": "OneDragon-Launcher.exe",
}


_ZZZOD_LAUNCHERS = tuple(_ZZZOD_LAUNCHER_BOOK.values())


def find_launcher_exe(root: Path) -> Path:
    """在安装根目录下发现 OneDragon 启动器。

    Raises:
        ValueError: 未找到任何启动器。
    """

    for name in _ZZZOD_LAUNCHERS:
        path = root / name
        if path.is_file():
            return path
    raise ValueError(f"{root} 下未找到 OneDragon 启动器, 请确认绝区零一条龙安装目录")


def find_launchers(root: Path) -> dict[str, Path]:
    """返回安装根目录下实际安装的启动器（标签 → exe 路径，未安装的不在结果中）。"""

    return {
        label: root / name
        for label, name in _ZZZOD_LAUNCHER_BOOK.items()
        if (root / name).is_file()
    }


def resolve_launcher(root: Path, mode: str, last_good: str = "") -> tuple[Path, str]:
    """按用户选择返回 (启动器 exe, 标签)。

    - 自动：优先「上次成功」的启动器（``last_good``），否则按默认顺序（集成优先）；
    - 原始/集成：固定用对应 exe，所选项未安装时回退默认顺序可用项并告警。

    Raises:
        ValueError: 安装根目录下没有任何启动器。
    """

    available = find_launchers(root)
    if available.get(mode):
        return available[mode], mode
    if mode == "自动" and last_good in available:
        return available[last_good], last_good
    # 固定模式所选未安装或无记忆：按默认顺序取首个可用（集成优先）
    for name in _ZZZOD_LAUNCHERS:
        path = root / name
        if path.is_file():
            label = next(
                (tag for tag, exe in _ZZZOD_LAUNCHER_BOOK.items() if exe == name),
                name,
            )
            if mode in ("原始", "集成"):
                logger.warning(f"所选{mode}启动器未安装，已回退使用{label}启动器")
            return path, label
    raise ValueError(f"{root} 下未找到 OneDragon 启动器, 请确认绝区零一条龙安装目录")


def _other_launcher_label(root: Path, label: str) -> str | None:
    """返回另一启动器的标签；未安装返回 None。"""

    other = "原始" if label == "集成" else "集成"
    return other if (root / _ZZZOD_LAUNCHER_BOOK[other]).is_file() else None
