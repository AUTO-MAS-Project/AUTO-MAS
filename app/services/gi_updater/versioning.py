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

"""版本号值类型与安装状态机。

米哈游使用 4 段版本号（major.minor.patch.revision）。比较语义：允许短版本（缺失的
段按 0 补齐后再比）、逐段数值比较而非字符串比较、未解析或空串视为 ``None``（表示
「未安装」或「未知」）。

状态机（对应上游的 ``.GameApi`` / ``.GameState`` / ``.IniConfig`` 三个分部）：

  * 只读 / 写**本地版本状态**（``config.ini``）
  * 从 API 结果里算**远程版本**（Sophon tag 优先于 zip major.version）
  * 用 ``get_state()`` 给出安装态之一（见 :class:`GameInstallStateEnum`：5 个取值）
  * 按状态给出「本次要下的包清单」（差分优先，退回全量）

它不碰网络、不碰磁盘大文件——那是 :mod:`sophon` / :mod:`install` 的事。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, List, Optional, Tuple

from app.services.gi_updater.common import (
    PROFILE_SECTION,
    VERSION_SECTION,
    IniFile,
    get_logger,
)
from app.services.gi_updater.presets import PresetConfig

__all__ = [
    "GameVersion",
    "VERSION_SEGMENTS",
    "GameInstallStateEnum",
    "GameVersionBase",
    "GAME_STATE_LABELS",
]


#: 版本号段数，米哈游固定为 4 段
VERSION_SEGMENTS = 4

_VERSION_RE = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?$")


@dataclass(frozen=True, order=False)
class GameVersion:
    """不可变、可比较的 4 段版本号。

    比较走显式富运算符：未安装（``None``）在比较时按全 0 空版本参与，因此
    「未知」永远排在任何具体版本之前。
    """

    major: int = 0
    minor: int = 0
    patch: int = 0
    revision: int = 0

    # ------------------------------------------------------------------ 构造

    @classmethod
    def parse(cls, value: "str | int | GameVersion | None") -> Optional["GameVersion"]:
        """宽松解析版本号：支持 str、int 与 ``GameVersion``。

        空串、``None`` 与匹配不上 ``_VERSION_RE`` 的输入都返回 ``None``（语义上是
        「未安装」）而不抛异常——版本号读不出来不该拦住整条更新流程。
        """
        if value is None:
            return None
        if isinstance(value, GameVersion):
            return value
        if isinstance(value, int):
            # 极少见：某些 API 用纯数字表示版本
            return cls.from_segments([value])

        text = str(value).strip()
        if not text:
            return None

        match = _VERSION_RE.match(text)
        if match is None:
            return None

        segments = [int(part) for part in match.groups() if part is not None]
        return cls.from_segments(segments)

    @classmethod
    def from_segments(cls, segments: Iterable[int]) -> "GameVersion":
        """用整数序列构造版本号，超过 4 段截断、不足 4 段补 0。"""
        parts: List[int] = [int(part) for part in segments][:VERSION_SEGMENTS]
        while len(parts) < VERSION_SEGMENTS:
            parts.append(0)
        return cls(*parts)

    @classmethod
    def empty(cls) -> "GameVersion":
        """全 0 版本，语义上是「还没装 / 不知道」。"""
        return cls(0, 0, 0, 0)

    # ------------------------------------------------------------------ 输出

    @property
    def version_string(self) -> str:
        """4 段完整版本号 ``major.minor.patch.revision``。"""
        return f"{self.major}.{self.minor}.{self.patch}.{self.revision}"

    @property
    def sophon_tag(self) -> str:
        """Sophon 侧的 3 段版本串（``major.minor.patch``）。

        Note:
            分支 ``tag`` 与差分清单 ``stats`` 的基线键都是 3 段形态，拿 4 段的
            `version_string` 去对永远对不上：目标版本会被服务端判 ``-202``，
            差分会被当成不存在。
        """
        return f"{self.major}.{self.minor}.{self.patch}"

    def as_tuple(self) -> Tuple[int, int, int, int]:
        """4 段版本号转元组，比较与哈希都以它为准。"""
        return (self.major, self.minor, self.patch, self.revision)

    def __str__(self) -> str:  # pragma: no cover
        """展示成 ``version_string``。"""
        return self.version_string

    def __repr__(self) -> str:  # pragma: no cover
        """调试用的 ``GameVersion(x.y.z.w)`` 形式。"""
        return f"GameVersion({self.version_string})"

    def is_empty(self) -> bool:
        """是否为全 0 的空版本。"""
        return self.as_tuple() == (0, 0, 0, 0)

    # 四个大小比较把右操作数交给 :func:`_coerce`（读不出的一律按全 0 空版本算），
    # 因此「未安装」排在任何具体版本之前；``__eq__`` 是另一套规则，见它的说明。

    def __eq__(self, other: object) -> bool:
        """相等比较。

        ``other`` 是 None 或读不出来时返回 ``NotImplemented``，交给 Python 回退到默认
        对象比较 —— 不能把它当成「与全 0 空版本相等」。
        """
        other_version = (
            self.parse(other) if not isinstance(other, GameVersion) else other
        )
        if other_version is None:
            return NotImplemented
        return self.as_tuple() == other_version.as_tuple()

    def __hash__(self) -> int:
        """按 4 段元组哈希，保证相等的版本必然同哈希。"""
        return hash(self.as_tuple())

    def __lt__(self, other: "GameVersion") -> bool:
        """逐段比较大小。"""
        return self.as_tuple() < _coerce(other).as_tuple()

    def __le__(self, other: "GameVersion") -> bool:
        """逐段比较大小（含相等）。"""
        return self.as_tuple() <= _coerce(other).as_tuple()

    def __gt__(self, other: "GameVersion") -> bool:
        """逐段比较大小。"""
        return self.as_tuple() > _coerce(other).as_tuple()

    def __ge__(self, other: "GameVersion") -> bool:
        """逐段比较大小（含相等）。"""
        return self.as_tuple() >= _coerce(other).as_tuple()


def _coerce(other: object) -> GameVersion:
    """把比较的右操作数转成 :class:`GameVersion`；读不出来按全 0 空版本算。"""
    if isinstance(other, GameVersion):
        return other
    parsed = GameVersion.parse(other)
    if parsed is None:
        # 与 None 比较时，任何具体版本都视为「更大」（已安装 > 未安装）
        return GameVersion.empty()
    return parsed


#: 判定「游戏已安装」时要求可执行文件的最小体积（1 << 16 = 64 KiB）
MIN_EXECUTABLE_SIZE = 1 << 16

GAME_STATE_LABELS = {
    "NotInstalled": "未安装",
    "GameBroken": "安装已损坏",
    "NeedsUpdate": "需要更新",
    "InstalledHavePreload": "已安装（有预下载）",
    "Installed": "已安装且为最新",
}


class GameInstallStateEnum(str, Enum):
    """安装状态机的五个取值。"""

    NotInstalled = "NotInstalled"
    GameBroken = "GameBroken"
    NeedsUpdate = "NeedsUpdate"
    InstalledHavePreload = "InstalledHavePreload"
    Installed = "Installed"

    def __str__(self) -> str:  # pragma: no cover
        """返回面向用户的中文标签，未登记时退回原始枚举值。"""
        return GAME_STATE_LABELS.get(self.value, self.value)


class GameVersionBase:
    """版本管理基类；每款游戏通过子类覆写少量钩子。"""

    def __init__(
        self,
        preset: PresetConfig,
        game_path: Optional[str] = None,
    ) -> None:
        """建立内存态与两份 ini 句柄，惰性加载本地 ``config.ini``。

        传 ``game_path`` 时只加载不写盘；远程版本由调用方经 :meth:`apply_branches` 填进来，
        本类自己不联网。
        """
        self.preset = preset
        self.logger = get_logger()

        #: 游戏安装目录
        self.game_path: str = ""
        #: 启动器 profile 目录（存放 [launcher] config.ini）
        self.profile_dir: Optional[str] = None

        self.game_ini_version = IniFile()
        self.game_ini_profile = IniFile()

        if game_path:
            self.update_game_path(game_path, save=False)

    # ================================================================== 路径

    @property
    def config_file_name(self) -> str:
        """配置文件名；游戏根目录与 profile 目录各有一份同名的。"""
        return "config.ini"

    @property
    def game_ini_version_path(self) -> str:
        """``<game_path>/config.ini`` —— 存 ``game_version`` 的那份。"""
        return os.path.join(self.game_path or "", self.config_file_name)

    @property
    def game_ini_profile_path(self) -> str:
        """``<profile_dir>/config.ini`` —— 存 ``game_install_path`` 的那份。"""
        return os.path.join(self.profile_dir or "", self.config_file_name)

    @property
    def game_data_path(self) -> str:
        """``<game_path>/<ExecName>_Data``。"""
        exec_prefix = os.path.splitext(self.preset.executable_name)[0]
        return os.path.join(self.game_path, f"{exec_prefix}_Data")

    @property
    def game_data_persistent_path(self) -> str:
        """``<Data>/Persistent`` 目录。"""
        return os.path.join(self.game_data_path, "Persistent")

    # ================================================================== ini

    def update_game_path(self, path: str, save: bool = True) -> None:
        """重新指向游戏目录并加载两份 ``config.ini``。

        空串表示取消绑定。``save`` 为真时把 ``game_install_path`` 写回 profile ini，构造期
        调用必须传 ``False``，免得刚加载就把路径写进用户的 profile。只加载不校验目录合法
        性，并且会丢掉此前内存中未保存的修改。
        """
        self.game_path = os.path.abspath(path) if path else ""
        self.game_ini_version = IniFile()
        self.game_ini_profile = IniFile()

        if self.profile_dir:
            self.game_ini_profile = IniFile.load(self.game_ini_profile_path)
        if self.game_path and os.path.isfile(self.game_ini_version_path):
            self.game_ini_version = IniFile.load(self.game_ini_version_path)

        if save and self.profile_dir:
            self.game_ini_profile[PROFILE_SECTION]["game_install_path"] = (
                self.game_path.replace("\\", "/")
            )
            self.game_ini_profile.save(self.game_ini_profile_path)

    def reload(self) -> None:
        """按当前 ``game_path`` 重新加载本地 ini。"""
        self.update_game_path(self.game_path, save=False)

    @property
    def version_section(self):
        """``config.ini`` 里放版本信息的节（``[General]``）。"""
        return self.game_ini_version[VERSION_SECTION]

    # ================================================================== 版本

    @property
    def installed_version(self) -> Optional[GameVersion]:
        """从 ``config.ini [General] game_version`` 读。"""
        raw = self.version_section.get("game_version")
        return GameVersion.parse(raw)

    def update_game_version(
        self, version: Optional[GameVersion], save: bool = True
    ) -> None:
        """写本地 ``game_version``；``None`` 写成空串，等同于「未知 / 未安装」。"""
        self.version_section["game_version"] = version.version_string if version else ""
        if save:
            self.save_version_config()

    def update_game_version_to_latest(self, save: bool = True) -> None:
        """把本地版本同步为远程最新，再回写频道信息。

        顺序固定为先版本后频道；``save=False`` 时两处都只改内存，不会互相带着补写。
        """
        self.update_game_version(self.latest_version, save=save)
        self.update_game_channels(save=save)

    def update_game_channels(self, save: bool = True) -> None:
        """把预设里的 channel / sub_channel / cps 写回 ``config.ini``。

        三个值与游戏实际区域绑定，拿错区服的预设写回去，客户端的渠道就变成另一套。
        """
        self.version_section["channel"] = str(self.preset.channel_id)
        self.version_section["sub_channel"] = str(self.preset.sub_channel_id)
        self.version_section["cps"] = self.preset.cps
        if save:
            self.save_version_config()

    def save_version_config(self) -> None:
        """把版本 ini 落盘；``game_path`` 还没定就什么都不写。"""
        if not self.game_path:
            return
        self.game_ini_version.save(self.game_ini_version_path)

    # ------------------------------------------------------------ 远程版本

    #: 分支接口给出的原始版本串，由调用方经 :meth:`apply_branches` 填进来。形态为什么
    #: 必须是 3 段，见 :attr:`GameVersion.sophon_tag`。
    remote_tag: str = ""
    #: 预下载分支的原始版本串；官方没开预下载时为空串
    preload_tag: str = ""

    def apply_branches(self, main_tag: str, preload_tag: str = "") -> None:
        """记下分支接口给出的两个原始版本串。"""
        self.remote_tag = main_tag or ""
        self.preload_tag = preload_tag or ""

    @property
    def latest_version(self) -> Optional[GameVersion]:
        """远程最新版本；还没拉过分支时为 ``None``。"""
        return GameVersion.parse(self.remote_tag)

    @property
    def preload_version(self) -> Optional[GameVersion]:
        """远程预下载版本；官方没开预下载时为 ``None``。"""
        return GameVersion.parse(self.preload_tag)

    # ================================================================== 状态

    def is_game_installed(self) -> bool:
        """判断游戏是否已安装。

        三重门槛：
            1. `game_path` 非空；
            2. 能从 ``config.ini`` 解析出 `installed_version`（即已记录版本号）；
            3. 候选可执行名中存在一个文件，且体积 ``> MIN_EXECUTABLE_SIZE``（64 KiB）。

        Note:
            可执行文件体积门槛 ``MIN_EXECUTABLE_SIZE = 1 << 16``（64 KiB）
            用来排除残破 / 占位的可执行文件。

            本方法把「有可执行文件、但 ``config.ini`` 里没版本号」也判为未安装；
            :meth:`get_state` 对同一情形判为 ``GameBroken``。两者分工不同：本方法回答
            「能不能当成一个装好的游戏来读」，``get_state`` 回答「该给用户看哪个状态」。
        """
        return self.installed_version is not None and self._has_installed_executable()

    def _has_installed_executable(self) -> bool:
        """探测游戏根目录下是否存在「体积达标」的可执行文件（不看版本号）。

        Returns:
            `game_path` 非空，且 :meth:`_candidate_executable_names` 中任一名字
                对应一个体积 ``> MIN_EXECUTABLE_SIZE`` 的普通文件时为 ``True``。

        Note:
            ``game_path`` 的空判必须留在本方法内：一旦为空，``os.path.join("", name)``
            得到的是相对路径，会误命中当前工作目录下的同名文件。
        """
        if not self.game_path:
            return False
        for executable_name in self._candidate_executable_names():
            path = os.path.join(self.game_path, executable_name)
            if os.path.isfile(path) and os.path.getsize(path) > MIN_EXECUTABLE_SIZE:
                return True
        return False

    def _candidate_executable_names(self) -> List[str]:
        """列出用于「是否存在可执行文件」判定的候选名（模板钩子）。

        基类默认只返回 `preset.executable_name` 一个；子类覆写以容纳多客户端
        （如原神的国服 / 国际服互斥双名）。

        Note:
            子类覆写时应保持语义：返回的每一个名字都代表「同一游戏的不同客户端」，
            `is_game_installed` 只要命中任一即视为已安装。
        """
        return [self.preset.executable_name]

    def is_game_version_match(self) -> bool:
        """本地版本与远程最新是否一致。"""
        return self.installed_version == self.latest_version

    def is_game_has_preload(self) -> bool:
        """是否存在可用的预下载版本。"""
        return bool(self.preload_tag)

    def get_state(self) -> GameInstallStateEnum:
        """唯一的安装态判定入口。

        判定顺序（按实现）：
            1. :meth:`_has_installed_executable` 为 ``False``（没游戏目录 / 找不到
               体积达标的可执行文件）-> ``NotInstalled``；
            2. `is_game_installed()` 为 ``False``——此时可执行文件已在，差的只有
               ``config.ini`` 里的版本号 -> ``GameBroken``；
            3. 版本不一致（非最新）-> ``NeedsUpdate``；
            4. `is_game_has_preload()` 为真 -> ``InstalledHavePreload``；
            5. 其余 -> ``Installed``（已安装且最新）。

        Returns:
            上述 5 个状态之一。

        Note:
            ``GameBroken`` 的含义是「可执行文件在、``config.ini`` 没有版本号」。它与
            ``NotInstalled`` 在下游规划里被归为一档，区别只在给用户看的诊断标签：
            ``GAME_STATE_LABELS`` 会显示「安装已损坏」。
        """
        if not self._has_installed_executable():
            return GameInstallStateEnum.NotInstalled
        if not self.is_game_installed():
            # 有可执行文件但没有版本号 -> 视为损坏
            return GameInstallStateEnum.GameBroken
        if not self.is_game_version_match():
            return GameInstallStateEnum.NeedsUpdate
        if self.is_game_has_preload():
            return GameInstallStateEnum.InstalledHavePreload
        return GameInstallStateEnum.Installed
