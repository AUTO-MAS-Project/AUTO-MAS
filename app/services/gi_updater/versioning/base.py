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

"""
版本管理基类
（含 ``.GameApi`` / ``.GameState`` / ``.IniConfig`` 三个分部）。

职责边界：
  * 只读 / 写**本地版本状态**（``config.ini``）
  * 从 API 结果里算**远程版本**（Sophon tag 优先于 zip major.version）
  * 用 ``get_state()`` 给出安装态之一（见 :class:`GameInstallStateEnum`：6 个取值，
    当前全部可达）
  * 按状态给出「本次要下的包清单」（差分优先，退回全量）

它不碰网络、不碰磁盘大文件——那是 download / install 层的事。
"""

from __future__ import annotations

import os
from enum import Enum
from typing import List, Optional

from app.services.gi_updater.api.launcher_api import LauncherApi
from app.services.gi_updater.api.models import GamePackageResult
from app.services.gi_updater.api.profiles import PresetConfig
from app.services.gi_updater.common.ini import PROFILE_SECTION, VERSION_SECTION, IniFile
from app.services.gi_updater.common.logging import get_logger
from app.services.gi_updater.common.version import GameVersion

__all__ = [
    "GameInstallStateEnum",
    "GameVersionBase",
    "GAME_STATE_LABELS",
]

#: 判定「游戏已安装」时要求可执行文件的最小体积（1 << 16 = 64 KiB）
MIN_EXECUTABLE_SIZE = 1 << 16

GAME_STATE_LABELS = {
    "NotInstalled": "未安装",
    "GameBroken": "安装已损坏",
    "NeedsUpdate": "需要更新",
    "InstalledHavePreload": "已安装（有预下载）",
    "InstalledHavePlugin": "已安装（有插件更新）",
    "Installed": "已安装且为最新",
}


class GameInstallStateEnum(str, Enum):
    """安装状态机的六个取值。"""

    NotInstalled = "NotInstalled"
    GameBroken = "GameBroken"
    NeedsUpdate = "NeedsUpdate"
    InstalledHavePreload = "InstalledHavePreload"
    InstalledHavePlugin = "InstalledHavePlugin"
    Installed = "Installed"

    def __str__(self) -> str:  # pragma: no cover
        """返回本地化中文标签（来自 `GAME_STATE_LABELS`），未登记时退回原始枚举值。

        Note:
            标记 ``# pragma: no cover``：只是枚举值的展示别名，不参与任何逻辑分支。
        """
        return GAME_STATE_LABELS.get(self.value, self.value)


class GameVersionBase:
    """版本管理基类；三款游戏通过子类覆写少量钩子。"""

    def __init__(
        self,
        preset: PresetConfig,
        launcher_api: Optional[LauncherApi] = None,
        game_path: Optional[str] = None,
    ) -> None:
        """初始化版本管理实例并惰性加载本地 ``config.ini``。

        Args:
            preset: 启动器 profile 配置（`PresetConfig`），提供可执行名 / 频道 / 区域等。
            launcher_api: 已初始化的 `LauncherApi`（含远程版本与 Sophon 分支）；
                传 ``None`` 时本实例只能读本地状态、算不出远程版本。
            game_path: 游戏安装根目录；非空时立即调用 `update_game_path` 载入 ini
                （``save=False``，构造阶段不写盘）。

        Note:
            仅建立内存态与 ini 句柄；真正写盘发生在 `update_game_path` /
            `update_game_version` 等显式调用时。
        """
        self.preset = preset
        self.launcher_api = launcher_api
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
        """磁盘配置文件名，固定为 ``config.ini``（本地版本与 profile 共用此名）。

        Returns:
            文件名；游戏根目录与 profile 目录各持有一份同名文件。
        """
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
        """重新指向游戏目录并（重新）加载本地 ``config.ini``。

        Args:
            path: 新的游戏根目录；空串会清空 `game_path`（用于取消绑定）。
            save: 为 ``True`` 且 `profile_dir` 存在时，把 ``game_install_path`` 写回
                ``<profile_dir>/config.ini``；构造期调用传 ``False`` 避免误写。

        Note:
            仅加载、不校验目录是否合法；会重建 `game_ini_version` / `game_ini_profile`
            两个句柄（丢弃此前内存中的未保存修改）。
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
        """`game_ini_version` 中存放版本信息的节（``[General]`` 即 `VERSION_SECTION`）。

        Returns:
            mapping: ini 节视图；读写它等价于直接读写本地 ``config.ini`` 的版本字段。
        """
        return self.game_ini_version[VERSION_SECTION]

    # ================================================================== 版本

    @property
    def installed_version(self) -> Optional[GameVersion]:
        """从 ``config.ini [General] game_version`` 读。"""
        raw = self.version_section.get("game_version")
        return GameVersion.parse(raw)

    @installed_version.setter
    def installed_version(self, value: Optional[GameVersion]) -> None:
        """setter，等价于调用 ``UpdateGameVersion``。

        Args:
            value: 要写入的版本；为 ``None`` 时回落到 `latest_version`。
        """
        self.update_game_version(value if value is not None else self.latest_version)

    def update_game_version(
        self, version: Optional[GameVersion], save: bool = True
    ) -> None:
        """把本地 ``game_version`` 写入 ``config.ini``。

        Args:
            version: 目标版本；``None`` 时写入空串（等同于「未知 / 未安装」）。
            save: 为 ``True`` 立即落盘，否则只改内存。

        Note:
            仅改 ``[General] game_version`` 一个字段；写盘委托 `save_version_config`。
        """
        self.version_section["game_version"] = version.version_string if version else ""
        if save:
            self.save_version_config()

    def update_game_version_to_latest(self, save: bool = True) -> None:
        """把本地版本同步为远程最新，并回写频道信息。

        Args:
            save: 传给 `update_game_version` / `update_game_channels` 的落盘开关。

        Note:
            顺序固定为先写版本、后写 channel / sub_channel / cps；
            跳过写盘时不会引发后续逻辑自动补写。
        """
        self.update_game_version(self.latest_version, save=save)
        self.update_game_channels(save=save)

    def update_game_channels(self, save: bool = True) -> None:
        """把当前 profile 的 channel / sub_channel / cps 写回 ``config.ini``。

        Args:
            save: 为 ``True`` 立即落盘，否则只改内存中的 `version_section`。

        Note:
            三个值来自 `preset`，与游戏实际区域绑定；改完需落盘才对后续启动生效。
        """
        self.version_section["channel"] = str(self.preset.channel_id)
        self.version_section["sub_channel"] = str(self.preset.sub_channel_id)
        self.version_section["cps"] = self.preset.cps
        if save:
            self.save_version_config()

    def save_version_config(self) -> None:
        """把内存中的 `game_ini_version` 落盘到 ``<game_path>/config.ini``。

        Note:
            `game_path` 为空时直接返回、不写盘。`update_game_version` /
            `update_game_channels` 默认都会调用本方法（受各自 ``save`` 形参控制）。
        """
        if not self.game_path:
            return
        self.game_ini_version.save(self.game_ini_version_path)

    # ------------------------------------------------------------ 远程版本

    @property
    def sophon_branch(self):
        """主版本 Sophon 分支（`launcher_api.sophon_branches.main`）。

        Returns:
            Optional[...]: 分支对象；`launcher_api` 未初始化或尚无 Sophon 数据时返回 ``None``。

        Note:
            其 ``tag`` 是 API 返回的原始 3 段版本串（如 ``7.0.0``），`latest_version`
            直接解析它，切勿补成 4 段（服务端会以 ``-202 not found`` 拒绝）。
        """
        if self.launcher_api is None or self.launcher_api.sophon_branches is None:
            return None
        return self.launcher_api.sophon_branches.main

    @property
    def sophon_preload_branch(self):
        """预下载 Sophon 分支（`launcher_api.sophon_branches.pre_download`）。

        Returns:
            Optional[...]: 预下载分支；无预下载或 API 未初始化时返回 ``None``。

        Note:
            与 `sophon_branch` 同源，仅在游戏开放预下载期间非空；
            其 ``tag`` 同样是原始 3 段版本串。
        """
        if self.launcher_api is None or self.launcher_api.sophon_branches is None:
            return None
        return self.launcher_api.sophon_branches.pre_download

    @property
    def zip_package(self):
        """主版本 zip 资源包（`resource_package.main_package`）。

        Returns:
            Optional[HypPackageData]: 全量 / 差分 zip 包元数据；API 未初始化或无数据时
                返回 ``None``（此时 `latest_version` 只能依赖 Sophon）。

        Note:
            自原神 5.6 起官方不再提供 zip 包，该字段可能为 ``None``，
            因此远程版本判定以 Sophon 为主、zip 为辅。
        """
        if self.launcher_api is None or self.launcher_api.resource_package is None:
            return None
        return self.launcher_api.resource_package.main_package

    @property
    def zip_preload_package(self):
        """预下载 zip 资源包（`resource_package.pre_download`）。

        Returns:
            Optional[HypPackageData]: 预下载 zip 包；无预下载或 API 未初始化时返回 ``None``。
        """
        if self.launcher_api is None or self.launcher_api.resource_package is None:
            return None
        return self.launcher_api.resource_package.pre_download

    @property
    def latest_version(self) -> Optional[GameVersion]:
        """远程最新版本。

        综合 Sophon 分支 ``tag`` 与 zip 包的 ``current_version`` 取较大者：
        若 Sophon 版本更高则返回 Sophon，否则返回两者中非空的那一个
        （Sophon 与 zip 相等时偏 Sophon）。

        Returns:
            解析出的版本；Sophon 与 zip 双双缺失时返回 ``None``
                （表示拿不到远程版本）。

        Note:
            自原神 5.6 起官方只发 Sophon、不再提供 zip 包，zip 的 major 可能滞后甚至
            被伪造，因此以 Sophon 为主、zip 为辅。Sophon ``tag`` 必须是 API 返回的
            **原始 3 段版本串**（如 ``7.0.0``）；补成 4 段（``7.0.0.0``）会被服务端以
            ``-202 not found`` 拒绝。
        """
        version_from_sophon = (
            GameVersion.parse(self.sophon_branch.tag) if self.sophon_branch else None
        )
        version_from_zip = (
            GameVersion.parse(self.zip_package.current_version.version)
            if self.zip_package and self.zip_package.current_version
            else None
        )

        if (
            version_from_sophon is not None
            and version_from_zip is not None
            and version_from_sophon > version_from_zip
        ):
            return version_from_sophon
        return version_from_sophon or version_from_zip

    @property
    def preload_version(self) -> Optional[GameVersion]:
        """远程预下载版本。

        与 `latest_version` 同源，只是换成预下载分支 / 预下载 zip 包；
        取 Sophon 与 zip 的较大者。

        Returns:
            有预下载时返回版本，否则 ``None``。

        Note:
            仅当官方开放预下载期间非空（见 `is_game_has_preload`）；
            Sophon ``tag`` 同样是原始 3 段版本串。
        """
        version_from_sophon = (
            GameVersion.parse(self.sophon_preload_branch.tag)
            if self.sophon_preload_branch
            else None
        )
        version_from_zip = (
            GameVersion.parse(self.zip_preload_package.current_version.version)
            if self.zip_preload_package and self.zip_preload_package.current_version
            else None
        )
        if (
            version_from_sophon is not None
            and version_from_zip is not None
            and version_from_sophon > version_from_zip
        ):
            return version_from_sophon
        return version_from_sophon or version_from_zip

    # ================================================================== 状态

    def is_game_installed(self) -> bool:
        """判断游戏是否已安装。

        三重门槛：
            1. `game_path` 非空；
            2. 能从 ``config.ini`` 解析出 `installed_version`（即已记录版本号）；
            3. 候选可执行名中存在一个文件，且体积 ``> MIN_EXECUTABLE_SIZE``（64 KiB）。

        Returns:
            三者同时满足为 ``True``。

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

        Returns:
            候选可执行文件名（不含路径）。

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
        if self.is_use_sophon():
            return self.sophon_preload_branch is not None
        return bool(
            self.zip_preload_package and self.zip_preload_package.current_version
        )

    def is_use_sophon(self) -> bool:
        """版本侧「是否具备 / 应使用 Sophon」的能力判定。

        判定顺序：
            1. `preset.launcher_resource_chunks_url` 为 ``None``（无分块资源地址）
               -> 直接 ``False``（根本用不了 Sophon）；
            2. `preset.is_force_redirect_to_sophon` 为真 -> ``True``（强制重定向）；
            3. 否则看 `launcher_api.is_force_redirect_to_sophon`（服务端假版本触发）。

        Returns:
            上述逻辑结果。

        Note:
            实际的「用户是否关闭 / 是否存在 ``@DisableSophon`` 文件」等运行期开关
            在 install 层叠加，本方法只负责「能力与强制」这一半。
        """
        if self.preset.launcher_resource_chunks_url is None:
            return False
        if self.preset.is_force_redirect_to_sophon:
            return True
        return (
            self.launcher_api is not None
            and self.launcher_api.is_force_redirect_to_sophon
        )

    def is_force_redirect_to_sophon(self) -> bool:
        """是否「强制」走 Sophon（能力判断为真 **且** profile 显式开启强制）。

        Returns:
            ``is_use_sophon() and preset.is_force_redirect_to_sophon``。

        Note:
            其中的强制标志由 `LauncherApi._initialize_fake_version_info` 在
            服务端下发假版本信息时设置，用于把原本走 zip 的游戏也重定向到 Sophon。
        """
        return self.is_use_sophon() and self.preset.is_force_redirect_to_sophon

    def get_state(self) -> GameInstallStateEnum:
        """唯一的安装态判定入口。

        判定顺序（按实现）：
            1. :meth:`_has_installed_executable` 为 ``False``（没游戏目录 / 找不到
               体积达标的可执行文件）-> ``NotInstalled``；
            2. `is_game_installed()` 为 ``False``——此时可执行文件已在，差的只有
               ``config.ini`` 里的版本号 -> ``GameBroken``；
            3. 版本不一致（非最新）-> ``NeedsUpdate``；
            4. `is_game_has_preload()` 为真 -> ``InstalledHavePreload``；
            5. `_has_pending_plugin_update()` 为真 -> ``InstalledHavePlugin``；
            6. 其余 -> ``Installed``（已安装且最新）。

        Returns:
            上述 6 个状态之一，全部可达。

        Note:
            ``GameBroken`` 的含义是「可执行文件在、``config.ini`` 没有版本号」。它与
            ``NotInstalled`` 后续走**同一条全量安装**路径（``install/base.py`` 的
            :meth:`~install.base.InstallManagerBase.build_plan` 与
            :meth:`~versioning.base.GameVersionBase.get_latest_zip` 都把两者归为一档），
            区别只在给用户看的诊断标签：``GAME_STATE_LABELS`` 会显示「安装已损坏」。
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
        if self._has_pending_plugin_update():
            return GameInstallStateEnum.InstalledHavePlugin
        return GameInstallStateEnum.Installed

    def _has_pending_plugin_update(self) -> bool:
        """简化版：只比对插件版本，不逐个校验文件哈希。"""
        return False

    # ================================================================== 包清单

    def get_latest_zip(self, state: GameInstallStateEnum) -> GamePackageResult:
        """计算「本次更新要下载的 zip 包清单」。

        Args:
            state: `get_state` 得出的当前安装态，决定走全量还是差分。

        Returns:
            命中时含主包 / 语音包 / 资源清单 URL / 版本号；
                `zip_package` 为 ``None`` 或缺少 ``current_version`` 时返回**空**
                ``GamePackageResult()``（全部字段为空，调用方据此判断「无可用 zip 包」）。

        Note:
            本方法**必须**传入 ``state``（据此区分未安装 / 损坏 / 增量场景）；
            与之相对，`get_preload_zip` **不接收** ``state`` —— 这是有意为之的不对称，
            因为预下载不存在「已安装态」的概念。
        """
        package = self.zip_package
        if package is None or package.current_version is None:
            return GamePackageResult()

        if state in (
            GameInstallStateEnum.NotInstalled,
            GameInstallStateEnum.GameBroken,
        ):
            return GamePackageResult(
                main_package=list(package.current_version.game_packages),
                audio_package=list(package.current_version.audio_packages),
                uncompressed_url=package.current_version.resource_list_url,
                version=package.current_version.version,
            )

        installed = self.installed_version
        for patch in package.patches:
            if installed is not None and GameVersion.parse(patch.version) == installed:
                return GamePackageResult(
                    main_package=list(patch.game_packages),
                    audio_package=list(patch.audio_packages),
                    uncompressed_url=patch.resource_list_url,
                    version=patch.version,
                )

        return GamePackageResult(
            main_package=list(package.current_version.game_packages),
            audio_package=list(package.current_version.audio_packages),
            uncompressed_url=package.current_version.resource_list_url,
            version=package.current_version.version,
        )

    def get_preload_zip(self) -> GamePackageResult:
        """计算「预下载要下载的 zip 包清单」。

        Returns:
            命中时含主包 / 语音包 / 资源 URL / 版本号；
                `zip_preload_package` 为 ``None``、或其 ``patches`` 与 ``current_version``
                皆缺失时返回**空** ``GamePackageResult()``。

        Note:
            与 `get_latest_zip` 不同，本方法**不接收** ``state`` 形参——预下载没有
            「已安装态」概念，只按「先差分补丁、后全量」的同一套逻辑选包。
        """
        package = self.zip_preload_package
        if package is None:
            return GamePackageResult()

        installed = self.installed_version
        for patch in package.patches:
            if installed is not None and GameVersion.parse(patch.version) == installed:
                return GamePackageResult(
                    main_package=list(patch.game_packages),
                    audio_package=list(patch.audio_packages),
                    uncompressed_url=patch.resource_list_url,
                    version=patch.version,
                )

        if package.current_version is None:
            return GamePackageResult()

        return GamePackageResult(
            main_package=list(package.current_version.game_packages),
            audio_package=list(package.current_version.audio_packages),
            uncompressed_url=package.current_version.resource_list_url,
            version=package.current_version.version,
        )

    def is_delta_patch_available(self) -> bool:
        """游戏是否支持自研 DeltaPatch（模板钩子）。

        基类默认返回 ``False``；只有崩铁覆写为「存在可用 ``.patch`` 文件时返回 ``True``」。

        Returns:
            基类恒为 ``False``（原神 / 绝区零沿用），崩铁按实际补丁判定。

        Note:
        """
        return False

    # ================================================================== 本地探测

    @classmethod
    def find_game_installation_path(
        cls, preset: PresetConfig, root: str
    ) -> Optional[str]:
        """在 ``root`` 下两级探测游戏安装目录。

        Args:
            preset: 提供 `executable_name` 与 `game_directory_name` 的 profile 配置。
            root: 待搜索的顶层目录（如启动器默认安装盘根）。

        Returns:
            命中时返回含可执行文件且存在 ``config.ini`` 的目录；
                两级都未命中返回 ``None``（表示没找到）。

        Note:
            探测门槛与 `is_game_installed` 一致：可执行文件须存在且 ``> MIN_EXECUTABLE_SIZE``；
            两级分别是「根目录直放」与「``Games/<GameDirectoryName>`` 子目录」。
        """
        for base in (root, os.path.join(root, preset.game_directory_name or "Games")):
            exe_path = os.path.join(base, preset.executable_name)
            ini_path = os.path.join(base, "config.ini")
            if (
                os.path.isfile(exe_path)
                and os.path.getsize(exe_path) > MIN_EXECUTABLE_SIZE
            ):
                if os.path.isfile(ini_path):
                    return base
        return None

    # ================================================================== 语音

    @property
    def voice_language_id(self) -> int:
        """子类可按自己的存储方式覆写。"""
        return self.preset.voice_id_by_locale_code(self.preset.default_voice_language)

    def audio_lang_list_path(self) -> Optional[str]:
        """返回「已安装语音清单」文件的**实际路径**（仅当文件存在时）。

        Returns:
            实例方法，会探测文件是否真实存在；不存在返回 ``None``。
                基类默认返回 ``None``，由子类覆写指向各自清单文件（如原神的
                ``audio_lang_14``、崩铁的 ``AudioLaucherRecord.txt``）。

        Note:
            与 `audio_lang_list_path_static` 的区别：本方法是「探测 + 返回」，
            后者是「纯拼路径、不检查存在性」。写盘时用 static 拿目标路径，
            读盘 / 校验时用本方法确认文件真的在。
        """
        return None

    def audio_lang_list_path_static(self) -> str:
        """返回语音清单文件的**规范路径**（不检查文件是否存在）。

        Returns:
            总是返回拼好的全路径；基类默认返回空串，子类覆写。

        Note:
            纯路径计算、无副作用；与 `audio_lang_list_path`（探测实际存在）
            形成「目标路径 vs 实际路径」的对照，安装写入阶段多用本方法。
        """
        return ""
