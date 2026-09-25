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
原神（Genshin Impact）安装器 。

原神的特有三处：

1. **强制 Sophon**：自 5.6 起官方不再提供 zip 包，
   ``PresetConfig.IsForceRedirectToSophon = true``，
   因此 ``@DisableSophon`` / 启动器开关对原神**无效**。
2. **3.6 语音目录迁移**：安装前把
   ``<Data>/StreamingAssets/Audio/GeneratedSoundBanks/Windows``
   搬到 ``<Data>/StreamingAssets/AudioAssets``。
3. **语音清单用语言全名**：``audio_lang_14`` 里写的是
   ``Chinese`` / ``English(US)`` / ``Japanese`` / ``Korean``，
   读回时要映射成 locale code。
"""

from __future__ import annotations

import os
import shutil
from typing import List

from app.services.gi_updater.install.base import InstallManagerBase, UpdatePlan
from app.services.gi_updater.versioning import GameTypeGenshinVersion

__all__ = ["GenshinInstaller", "LANGUAGE_STRING_TO_LOCALE"]

#: 语言全名 -> locale code；原神语音清单里存的是全名
LANGUAGE_STRING_TO_LOCALE = {
    "Chinese": "zh-cn",
    "Chinese(PRC)": "zh-cn",
    "English": "en-us",
    "English(US)": "en-us",
    "Korean": "ko-kr",
    "Japanese": "ja-jp",
}

LOCALE_TO_LANGUAGE_STRING = {
    "zh-cn": "Chinese",
    "en-us": "English(US)",
    "ja-jp": "Japanese",
    "ko-kr": "Korean",
}


class GenshinInstaller(InstallManagerBase):
    """原神安装器。"""

    #: 类型标注，方便 IDE
    version: GameTypeGenshinVersion

    # ------------------------------------------------------------ 语音

    def locale_code_from_language_string(self, text: str) -> str:
        """把语言全名映射成 locale code（覆写 :meth:`InstallManagerBase.locale_code_from_language_string`）。

        Args:
            text: 清单里的一行（如 ``Chinese`` / ``English(US)``）。

        Returns:
            对应的 locale code（如 ``zh-cn`` / ``en-us``）；未知全名退化为
            ``text.lower()``。

        Note:
            原神清单里存的是 ``Chinese`` 这类全名，而基类默认直接 ``lower()``；
            本覆写通过 ``LANGUAGE_STRING_TO_LOCALE`` 做显式映射。
        """
        key = text.strip()
        return LANGUAGE_STRING_TO_LOCALE.get(key, key.lower())

    def language_string_from_locale_code(self, locale_code: str) -> str:
        """把 locale code 映射回语言全名（``locale_code_from_language_string`` 的逆函数）。

        Args:
            locale_code: locale code（如 ``zh-cn`` / ``en-us``）。

        Returns:
            语言全名（如 ``Chinese`` / ``English(US)``）；未知 code 原样返回。
        """
        return LOCALE_TO_LANGUAGE_STRING.get(locale_code.lower(), locale_code)

    def write_audio_lang_list(self, languages) -> None:
        """覆写：写回 ``audio_lang_14``（内容是语言全名而非 locale code）。

        Args:
            languages: 要写入的语音 locale code 列表。

        Note:
            与基类不同，原神把每个 locale code 经 :meth:`language_string_from_locale_code`
            转成 ``Chinese`` / ``English(US)`` 等全名再写盘；``dry_run`` 或拿不到路径时
            直接跳过（不写盘）。
        """
        path = self.version.audio_lang_list_path_static()
        if not path or self.dry_run:
            return
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            for language in languages:
                handle.write(f"{self.language_string_from_locale_code(language)}\n")

    # ------------------------------------------------------------ 迁移

    def before_install(self, plan: UpdatePlan) -> None:
        """覆写：安装前做 3.6 语音目录迁移的前置检查。

        Args:
            plan: 当前执行计划（本覆写未使用，仅保持接口一致）。

        Note:
            仅在非 ``dry_run`` 时调用 :meth:`migrate_audio_directory`；迁移的具体动作
            与搬移计数由该方法负责。
        """
        if self.dry_run:
            return
        self.migrate_audio_directory()

    def migrate_audio_directory(self) -> int:
        """把 3.6 之前的语音目录搬到新目录，返回搬移的文件数。

        Returns:
            实际搬移的文件数；旧目录不存在时返回 0。
        """
        version = self.version
        old_path = version.audio_old_path
        new_path = version.audio_new_path
        if not os.path.isdir(old_path):
            return 0

        moved = 0
        offset = len(old_path) + 1
        for root, _dirs, files in os.walk(old_path):
            for name in files:
                source = os.path.join(root, name)
                relative = source[offset:]
                target = os.path.join(new_path, relative)
                os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
                if os.path.isfile(target):
                    os.remove(target)
                shutil.move(source, target)
                moved += 1

        self.logger.info("已迁移 %d 个语音文件：%s -> %s", moved, old_path, new_path)
        return moved

    # ------------------------------------------------------------ 可执行名纠偏

    def validate_exec_data_dir(self) -> bool:
        """判断可执行目录是否有效（防国际服/国服客户端混装）。

        Returns:
            委托 ``version.is_exec_data_dir_valid()`` 判定（混装时为 False）。
        """
        return self.version.is_exec_data_dir_valid()

    def candidate_executable_names(self) -> List[str]:
        """返回可能的游戏可执行文件名列表（用于校验安装完整性）。

        Returns:
            委托 ``version._candidate_executable_names()``（原神是国服/国际服互斥双名）。
        """
        return self.version._candidate_executable_names()
