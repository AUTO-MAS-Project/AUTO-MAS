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

"""按游戏注册的规格表——新增一款游戏就是往这里加一条。

引擎本体（``api`` / ``sophon`` / ``patch`` / ``install`` / ``versioning``）不含游戏
知识；一款游戏的差异由 :class:`GameSpec` 描述，各 ``games/<game>.py`` 在自己的模块
末尾调 :func:`register` 登记，装配层按 ``game`` 短名查表。规格表只登记装配关系，
不含任何更新逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple, Type

from app.services.gi_updater.install import InstallManagerBase
from app.services.gi_updater.presets import GameKey
from app.services.gi_updater.versioning import GameVersionBase

__all__ = ["GameSpec", "SPECS", "get_spec", "register"]


@dataclass(frozen=True)
class GameSpec:
    """一款游戏的装配信息。

    Attributes:
        key: 注册短名，与 ``presets.PROFILES`` 键的第一项一致（如 ``gi``）。
        display_name: 面向用户的名字，用于日志与报错文案。
        version_cls: 该游戏的版本管理器，负责本地版本与安装态判定。
        installer_cls: 该游戏的安装管理器，覆写安装态判定等专属钩子。
        locale_regions: 区服配置项的中文标签 -> 区服短名，顺序即「自动」的探测顺序，
            第一项同时是空目录（新装）时的默认区服。
        install_marker_files: 判断「这个目录真装了本游戏」的文件名，与可执行文件
            取并集；只有两者都见不到时宿主才按「路径填错」拦下。
    """

    key: str
    display_name: str
    version_cls: Type[GameVersionBase]
    installer_cls: Type[InstallManagerBase]
    locale_regions: Tuple[Tuple[str, str], ...] = ()
    install_marker_files: Tuple[str, ...] = ("config.ini",)

    @property
    def default_region(self) -> str:
        """空目录（新装）时按哪个区服算——取 :attr:`locale_regions` 的第一项。"""
        return self.locale_regions[0][1]

    def region_for_label(self, label: str) -> str:
        """把区服配置项的标签换成区服短名。
        Returns:
            对应的区服短名；标签不认识时退回最后一个区服，与既有口径一致。
        """
        return dict(self.locale_regions).get(label, self.locale_regions[-1][1])


SPECS: Dict[str, GameSpec] = {}


def register(spec: GameSpec) -> GameSpec:
    """登记一款游戏，返回传进来的规格，便于 ``X = register(...)`` 一行写完。
    Raises:
        ValueError: 短名已被占用时——两处注册撞名通常是笔误，静默覆盖会让其中
            一份实现永远走不到。
    """
    if spec.key in SPECS:
        raise ValueError(f"游戏 {spec.key!r} 已注册，拒绝被重复覆盖")
    SPECS[spec.key] = spec
    return spec


def get_spec(game: str) -> GameSpec:
    """按短名取游戏规格。
    Returns:
        对应的 :class:`GameSpec`。

    Raises:
        ValueError: 该游戏未注册时——报错里列出已注册的名字，便于自查拼写。
    """
    key = GameKey.normalize(game)
    if key not in SPECS:
        available = ", ".join(sorted(SPECS)) or "（无）"
        raise ValueError(f"未注册的游戏 {game!r}（已注册: {available}）")
    return SPECS[key]
