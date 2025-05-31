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
AUTO_MAA信息通知栏
v4.3
作者：DLmaster_361
"""

from loguru import logger
from PySide6.QtCore import Qt
from qfluentwidgets import InfoBar, InfoBarPosition

from .config import Config
from .sound_player import SoundPlayer


class _MainInfoBar:
    """信息通知栏"""

    # 模式到 InfoBar 方法的映射
    mode_mapping = {
        "success": InfoBar.success,
        "warning": InfoBar.warning,
        "error": InfoBar.error,
        "info": InfoBar.info,
    }

    def push_info_bar(
        self, mode: str, title: str, content: str, time: int, if_force: bool = False
    ):
        """推送到信息通知栏"""
        if Config.main_window is None:
            logger.error("信息通知栏未设置父窗口")
            return None

        # 根据 mode 获取对应的 InfoBar 方法
        info_bar_method = self.mode_mapping.get(mode)

        if not info_bar_method:
            logger.error(f"未知的通知栏模式: {mode}")
            return None

        if Config.main_window.isVisible():
            info_bar_method(
                title=title,
                content=content,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=time,
                parent=Config.main_window,
            )
        elif if_force:
            # 如果主窗口不可见且强制推送，则录入消息队列等待窗口显示后推送
            info_bar_item = {
                "mode": mode,
                "title": title,
                "content": content,
                "time": time,
            }
            if info_bar_item not in Config.info_bar_list:
                Config.info_bar_list.append(info_bar_item)

        if mode == "warning":
            SoundPlayer.play("发生异常")
        if mode == "error":
            SoundPlayer.play("发生错误")


MainInfoBar = _MainInfoBar()
