#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361

#   This file is part of AUTO_MAA.

#   AUTO_MAA is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO_MAA is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO_MAA. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""
AUTO_MAA
AUTO_MAA音效播放器
v4.3
作者：DLmaster_361
"""

from loguru import logger
from PySide6.QtCore import QObject, QUrl
from PySide6.QtMultimedia import QSoundEffect
from pathlib import Path


from .config import Config


class _SoundPlayer(QObject):

    def __init__(self):
        super().__init__()

        self.sounds_path = Config.app_path / "resources/sounds"

    def play(self, sound_name: str):

        if not Config.get(Config.voice_Enabled):
            return

        if (self.sounds_path / f"both/{sound_name}.wav").exists():

            self.play_voice(self.sounds_path / f"both/{sound_name}.wav")

        elif (
            self.sounds_path / Config.get(Config.voice_Type) / f"{sound_name}.wav"
        ).exists():

            self.play_voice(
                self.sounds_path / Config.get(Config.voice_Type) / f"{sound_name}.wav"
            )

    def play_voice(self, sound_path: Path):

        effect = QSoundEffect(self)
        effect.setVolume(1)
        effect.setSource(QUrl.fromLocalFile(sound_path))
        effect.play()


SoundPlayer = _SoundPlayer()
