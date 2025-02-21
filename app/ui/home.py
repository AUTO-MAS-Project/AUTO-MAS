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
AUTO_MAA主界面
v4.2
作者：DLmaster_361
"""

from loguru import logger
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
)
from qframelesswindow.webengine import FramelessWebEngineView
from PySide6.QtCore import QUrl

from app.core import Config


class Home(QFrame):

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("主界面")

        self.webView = FramelessWebEngineView(self)

        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.addWidget(self.webView)

        self.current_url = None

        self.refresh()

    def refresh(self):

        if (
            Config.global_config.get(Config.global_config.function_HomePage)
            != self.current_url
        ):

            self.webView.load(
                QUrl(Config.global_config.get(Config.global_config.function_HomePage))
            )
            self.current_url = Config.global_config.get(
                Config.global_config.function_HomePage
            )
