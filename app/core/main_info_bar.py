#   <AUTO_MAA:A MAA Multi Account Management and Automation Tool>
#   Copyright © <2024> <DLmaster361>

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

#   DLmaster_361@163.com

"""
AUTO_MAA
AUTO_MAA信息通知栏
v4.2
作者：DLmaster_361
"""

from loguru import logger
from PySide6.QtCore import Qt
from qfluentwidgets import (
    InfoBar,
    InfoBarPosition,
)


class _MainInfoBar:
    """信息通知栏"""

    def __init__(self, main_window=None):

        self.main_window = main_window

    def push_info_bar(self, mode: str, title: str, content: str, time: int):
        """推送到信息通知栏"""

        if self.main_window is None:
            logger.error("信息通知栏未设置父窗口")
            return None

        if mode == "success":
            InfoBar.success(
                title=title,
                content=content,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=time,
                parent=self.main_window,
            )
        elif mode == "warning":
            InfoBar.warning(
                title=title,
                content=content,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=time,
                parent=self.main_window,
            )
        elif mode == "error":
            InfoBar.error(
                title=title,
                content=content,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=time,
                parent=self.main_window,
            )
        elif mode == "info":
            InfoBar.info(
                title=title,
                content=content,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=time,
                parent=self.main_window,
            )


MainInfoBar = _MainInfoBar()
