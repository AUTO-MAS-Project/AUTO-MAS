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
AUTO_MAA主程序
v4.2
作者：DLmaster_361
"""

from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentTranslator
import sys

from app.config import AppConfig
from app.services.notification import Notification
from app.services.security import CryptoHandler
from app.services.system import SystemHandler
from app.ui.main_window import AUTO_MAA

if __name__ == "__main__":

    config = AppConfig()
    notify = Notification(config)
    crypto = CryptoHandler(config)
    system = SystemHandler(config)

    application = QApplication(sys.argv)

    translator = FluentTranslator()
    application.installTranslator(translator)

    window = AUTO_MAA(config=config, notify=notify, crypto=crypto, system=system)
    window.setting.check_PASSWORD()
    sys.exit(application.exec())
