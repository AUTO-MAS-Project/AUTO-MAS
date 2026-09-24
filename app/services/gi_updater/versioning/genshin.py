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
原神（Genshin Impact）版本管理 。

原神的差异非常集中：

* **双可执行名**：国际服 ``GenshinImpact.exe``、国服/B 服 ``YuanShen.exe``。
   每个探测都先试主名、再试备选名，并且要求二者**互斥**
  （``IsGameExecDataDirValid``），不一致时由 ``FixInvalidGameExecDataDir`` 自动纠偏。
* **语音清单**：``<GenshinImpact_Data|YuanShen_Data>/Persistent/audio_lang_14``。
* **3.6 语音目录迁移**：``StreamingAssets/Audio/GeneratedSoundBanks/Windows``
  -> ``StreamingAssets/AudioAssets``（安装阶段执行）。
* **无 DeltaPatch**：``IsGameHasDeltaPatch() == false``。
* **5.6 起无 zip 包**：``pkg_version`` 只能从 Sophon 清单伪造（见 install 层）。
"""

from __future__ import annotations

import os
from typing import List, Optional

from app.services.gi_updater.versioning.base import GameVersionBase

__all__ = ["GameTypeGenshinVersion", "GLOBAL_EXEC_NAME", "ALTERNATIVE_EXEC_NAME"]

GLOBAL_EXEC_NAME = "GenshinImpact.exe"
ALTERNATIVE_EXEC_NAME = "YuanShen.exe"

#: 原神语音清单里写的语言全名表
AUDIO_VOICE_LANGUAGE_LIST = ["Chinese", "English(US)", "Japanese", "Korean"]


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
            other_dir = os.path.join(self.game_path, os.path.splitext(other)[0])
            if os.path.isfile(other_exec) or os.path.isdir(other_dir):
                # 只有在当前客户端自身存在时才判定为「混装」
                if os.path.isfile(os.path.join(self.game_path, name)):
                    return False
        return True

    # ------------------------------------------------------------ 语音

    def audio_lang_list_path(self) -> Optional[str]:
        """覆写 :meth:`GameVersionBase.audio_lang_list_path`。

        原神不固定清单文件名：直接扫描 ``<GameName>_Data/Persistent`` 下首个
        以 ``audio_lang_`` 开头的文件（兼容 ``audio_lang_14`` 等版本相关命名）。

        Returns:
            找到则返回该文件路径，目录不存在或无匹配文件时返回 ``None``。
        """
        persistent = self.game_data_persistent_path
        if not os.path.isdir(persistent):
            return None
        for name in os.listdir(persistent):
            if name.startswith("audio_lang_"):
                return os.path.join(persistent, name)
        return None

    def audio_lang_list_path_static(self) -> str:
        """覆写 :meth:`GameVersionBase.audio_lang_list_path_static`，固定指向 ``audio_lang_14``。"""
        return os.path.join(self.game_data_persistent_path, "audio_lang_14")

    # ------------------------------------------------------------ 3.6 迁移

    @property
    def audio_old_path(self) -> str:
        """3.6 迁移前的旧语音目录 ``<Data>/StreamingAssets/Audio/GeneratedSoundBanks/Windows``。"""
        return os.path.join(
            self.game_data_path,
            "StreamingAssets",
            "Audio",
            "GeneratedSoundBanks",
            "Windows",
        )

    @property
    def audio_new_path(self) -> str:
        """3.6 迁移后的新语音目录 ``<Data>/StreamingAssets/AudioAssets``。"""
        return os.path.join(self.game_data_path, "StreamingAssets", "AudioAssets")

    def needs_audio_migration(self) -> bool:
        """判断是否需要执行 3.6 语音目录迁移（前置）。

        3.6 起原神把语音从 ``StreamingAssets/Audio/GeneratedSoundBanks/Windows``
        迁到 ``StreamingAssets/AudioAssets``。触发条件：旧目录 `audio_old_path` 仍存在
        （说明尚未迁移）。

        Returns:
            旧目录存在为 ``True``，迁移完成后返回 ``False``。
        """
        return os.path.isdir(self.audio_old_path)

    # ------------------------------------------------------------ 差分

    def is_delta_patch_available(self) -> bool:
        """覆写 :meth:`GameVersionBase.is_delta_patch_available`，原神恒返 ``False``。

        原神没有自研 DeltaPatch；其增量完全走 Sophon。
        """
        return False
