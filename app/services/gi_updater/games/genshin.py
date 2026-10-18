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

"""原神（Genshin Impact）的版本管理与安装器——属于这款游戏的钩子都在这。

原神的差异集中在几处：

* **双可执行名**：国际服 ``GenshinImpact.exe``、国服/B 服 ``YuanShen.exe``。每个探测
  都先试主名、再试备选名，并且要求二者**互斥**：``is_exec_data_dir_valid`` 只判定不改
  盘，混装时由宿主门禁停手并提示改用官方启动器。
* **只有 Sophon 一条链路**：官方不再提供 zip 分包，上游的 ``@DisableSophon``
  文件与启动器开关对原神**无效**，版本一律以 ``getGameBranches`` 的 ``main.tag`` 为准。
* **无 DeltaPatch**、无预下载之外的多条链路。

一款游戏的知识集中在本模块。
"""

from __future__ import annotations

import os
from typing import List

from app.services.gi_updater.games.spec import GameSpec, register
from app.services.gi_updater.install import InstallManagerBase
from app.services.gi_updater.presets import GameKey, Region
from app.services.gi_updater.versioning import GameVersionBase

__all__ = [
    "GameTypeGenshinVersion",
    "GLOBAL_EXEC_NAME",
    "ALTERNATIVE_EXEC_NAME",
    "GenshinInstaller",
    "GENSHIN",
]


GLOBAL_EXEC_NAME = "GenshinImpact.exe"
ALTERNATIVE_EXEC_NAME = "YuanShen.exe"

#: 语音类别（清单里的 ``matching_field``）-> 游戏内的语音资源目录名。
#: 目录在不在就是「本机装没装这档语言」的依据；语音清单里连启动器那份
#: ``Audio_<语言>_pkg_version`` 记账文件都在文件名内，照单下载就把账一起换对了。
VOICE_CATEGORY_DIRS = {
    "zh-cn": "Chinese",
    "en-us": "English(US)",
    "ja-jp": "Japanese",
    "ko-kr": "Korean",
}


class GameTypeGenshinVersion(GameVersionBase):
    """原神版本管理。"""

    # ------------------------------------------------------------ 可执行名

    @property
    def alternative_executable_name(self) -> str:
        """与 `preset.executable_name` 互斥的**另一**客户端可执行名。

        原神双可执行名：国际服 ``GenshinImpact.exe``、国服/B 服 ``YuanShen.exe``。
        若当前是 ``YuanShen.exe`` 则备选用 ``GenshinImpact.exe``，反之亦然。

        Returns:
            备选可执行文件名（不含路径）。
        """
        return (
            GLOBAL_EXEC_NAME
            if self.preset.executable_name == ALTERNATIVE_EXEC_NAME
            else ALTERNATIVE_EXEC_NAME
        )

    def _candidate_executable_names(self) -> List[str]:
        """覆写 :meth:`GameVersionBase._candidate_executable_names`。

        原神有两个**互斥**客户端：国际服 ``GenshinImpact.exe`` 与国服/B 服
        ``YuanShen.exe``。每个探测都「主名 -> 备选名」试两遍；这里返回
        ``[主名, 备选名]``，使 `is_game_installed` 命中任一即算已安装。
        """
        return [self.preset.executable_name, self.alternative_executable_name]

    def is_exec_data_dir_valid(self) -> bool:
        """判断当前目录是否「未混装」两个原神客户端。

        原神国际服（``GenshinImpact.exe``）与国服/B 服（``YuanShen.exe``）的数据目录
        互斥，不能放在同一目录。判定：若某客户端的**另一个**客户端可执行文件或其
        ``<名>_Data`` 目录已存在，且**当前**客户端自身也存在，则视为「混装」返回 ``False``。

        Returns:
            未混装（或 `game_path` 为空，视为无需校验）为 ``True``。

        Note:
            混装时由官方启动器纠偏；本包只判定并拒绝放行。
        """
        if not self.game_path:
            return True

        primary = self.preset.executable_name
        alternative = self.alternative_executable_name
        for name in (primary, alternative):
            other = alternative if name == primary else primary
            other_exec = os.path.join(self.game_path, other)
            # 数据文件夹是 ``<程序名>_Data``，只去掉 ``.exe`` 得到的是永远不存在的裸名
            other_dir = os.path.join(
                self.game_path, f"{os.path.splitext(other)[0]}_Data"
            )
            if os.path.isfile(other_exec) or os.path.isdir(other_dir):
                # 只有在当前客户端自身存在时才判定为「混装」
                if os.path.isfile(os.path.join(self.game_path, name)):
                    return False
        return True


class GenshinInstaller(InstallManagerBase):
    """原神安装器。"""

    #: 类型标注，方便 IDE
    version: GameTypeGenshinVersion

    def protected_names(self) -> List[str]:
        """主名之外的 ``YuanShen.exe`` / ``GenshinImpact.exe`` 也不能被清单删掉。"""
        return [
            *super().protected_names(),
            GLOBAL_EXEC_NAME,
            ALTERNATIVE_EXEC_NAME,
        ]

    def installed_voice_categories(self) -> List[str]:
        """按 ``<Data>/StreamingAssets/AudioAssets/<语言>`` 在不在，判本机装了哪几档语音。

        只看目录是否存在，不读语音内容，也不碰启动器的私有格式。
        """
        audio_root = os.path.join(
            self.version.game_data_path, "StreamingAssets", "AudioAssets"
        )
        return [
            category
            for category, folder in VOICE_CATEGORY_DIRS.items()
            if os.path.isdir(os.path.join(audio_root, folder))
        ]

    def validate_exec_data_dir(self) -> bool:
        """判断可执行目录是否有效（防国际服/国服客户端混装）。

        Returns:
            委托 ``version.is_exec_data_dir_valid()`` 判定（混装时为 False）。
        """
        return self.version.is_exec_data_dir_valid()


# ------------------------------------------------------------ 注册

GENSHIN = register(
    GameSpec(
        key=GameKey.Genshin,
        display_name="原神",
        version_cls=GameTypeGenshinVersion,
        installer_cls=GenshinInstaller,
        locale_regions=(("官服", Region.CN), ("国际服", Region.GLOBAL)),
    )
)
