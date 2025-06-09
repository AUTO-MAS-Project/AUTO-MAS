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
AUTO_MAA主程序
v4.3
作者：DLmaster_361
"""

# 屏蔽广告
import builtins


def no_print(*args, **kwargs):
    if (
        args
        and isinstance(args[0], str)
        and "QFluentWidgets Pro is now released." in args[0]
    ):
        return
    return __builtins__.print(*args, **kwargs)


builtins.print = no_print


from loguru import logger
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentTranslator
import sys


@logger.catch
def main():

    application = QApplication(sys.argv)

    translator = FluentTranslator()
    application.installTranslator(translator)

    from app.ui.main_window import AUTO_MAA

    window = AUTO_MAA()
    window.show_ui("显示主窗口", if_start=True)
    window.start_up_task()
    sys.exit(application.exec())


if __name__ == "__main__":

    main()
