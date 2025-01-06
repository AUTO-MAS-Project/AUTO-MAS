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

from PySide6.QtWidgets import (
    QWidget,  #
    QMainWindow,  #
    QApplication,  #
    QSystemTrayIcon,  #
    QFileDialog,  #
    QTabWidget,  #
    QToolBox,  #
    QTableWidgetItem,  #
    QHeaderView,  #
    QVBoxLayout,
)
from qfluentwidgets import (
    Action,
    PushButton,
    LineEdit,
    PasswordLineEdit,
    TextBrowser,
    TableWidget,
    TimePicker,
    SystemTrayMenu,
    ComboBox,
    CheckBox,
    SpinBox,
    SplashScreen,
    FluentIcon,
    RoundMenu,
    MessageBox,
    MessageBoxBase,
    InfoBar,
    InfoBarPosition,
    BodyLabel,
    Dialog,
    setTheme,
    Theme,
    SystemThemeListener,
    qconfig,
    MSFluentWindow,
    NavigationItemPosition,
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtGui import QIcon, QCloseEvent
from PySide6 import QtCore
from functools import partial
from typing import List, Tuple
from pathlib import Path
import json
import datetime
import ctypes
import subprocess
import shutil
import win32gui
import win32process
import psutil
import pyautogui
import time
import winreg
import requests

uiLoader = QUiLoader()

from app import AppConfig, MaaConfig
from app.services import Notification, CryptoHandler, SystemHandler
from app.utils import Updater, version_text
from .Widget import InputMessageBox, LineEditSettingCard, SpinBoxSettingCard
from .setting import Setting
from .member_manager import MemberManager
from .queue_manager import QueueManager


class AUTO_MAA(MSFluentWindow):

    if_save = True

    def __init__(
        self,
        config: AppConfig,
        notify: Notification,
        crypto: CryptoHandler,
        system: SystemHandler,
    ):
        super().__init__()

        self.config = config
        self.notify = notify
        self.crypto = crypto
        self.system = system

        self.setWindowIcon(
            QIcon(str(self.config.app_path / "resources/icons/AUTO_MAA.ico"))
        )
        self.setWindowTitle("AUTO_MAA")

        setTheme(Theme.AUTO)

        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.show()

        # 创建主窗口
        self.setting = Setting(self.config, self.notify, self.crypto, self.system, self)
        self.member_manager = MemberManager(self.config, self.notify, self.crypto, self)
        self.queue_manager = QueueManager(self.config, self.notify, self)

        self.addSubInterface(
            self.setting,
            FluentIcon.SETTING,
            "设置",
            FluentIcon.SETTING,
            NavigationItemPosition.BOTTOM,
        )
        self.addSubInterface(
            self.member_manager,
            FluentIcon.ROBOT,
            "脚本管理",
            FluentIcon.ROBOT,
            NavigationItemPosition.TOP,
        )
        self.addSubInterface(
            self.queue_manager,
            FluentIcon.BOOK_SHELF,
            "调度队列",
            FluentIcon.BOOK_SHELF,
            NavigationItemPosition.TOP,
        )
        self.stackedWidget.currentChanged.connect(
            lambda index: self.queue_manager.refresh() if index == 2 else None
        )

        # 创建系统托盘及其菜单
        self.tray = QSystemTrayIcon(
            QIcon(str(self.config.app_path / "resources/icons/AUTO_MAA.ico")),
            self,
        )
        self.tray.setToolTip("AUTO_MAA")
        self.tray_menu = SystemTrayMenu("AUTO_MAA", self)

        # 显示主界面菜单项
        self.tray_menu.addAction(
            Action(FluentIcon.CAFE, "显示主界面", triggered=self.show_main)
        )
        self.tray_menu.addSeparator()

        # 开始任务菜单项
        # self.tray_menu.addActions(
        #     [
        #         Action(
        #             FluentIcon.PLAY,
        #             "运行日常代理",
        #             triggered=lambda: self.start_task("日常代理"),
        #         ),
        #         Action(
        #             FluentIcon.PLAY,
        #             "运行人工排查",
        #             triggered=lambda: self.start_task("人工排查"),
        #         ),
        #         Action(FluentIcon.PAUSE, "中止当前任务", triggered=self.stop_task),
        #     ]
        # )
        # self.tray_menu.addSeparator()

        # 退出主程序菜单项
        self.tray_menu.addAction(
            Action(FluentIcon.POWER_BUTTON, "退出主程序", triggered=self.kill_main)
        )

        # 设置托盘菜单
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.setting.ui.card_IfShowTray.checkedChanged.connect(
            lambda x: self.tray.show() if x else self.tray.hide()
        )

        self.splashScreen.finish()
        self.show_main()

        if self.config.global_config.get(self.config.global_config.update_IfAutoUpdate):
            result = self.setting.check_update()
            if result == "已是最新版本~":
                InfoBar.success(
                    title="更新检查",
                    content=result,
                    orient=QtCore.Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=3000,
                    parent=self,
                )
            else:
                info = InfoBar.info(
                    title="更新检查",
                    content=result,
                    orient=QtCore.Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.BOTTOM_LEFT,
                    duration=-1,
                    parent=self,
                )
                Up = PushButton("更新")
                Up.clicked.connect(
                    lambda: self.setting.check_version(if_question=False)
                )
                Up.clicked.connect(info.close)
                info.addWidget(Up)
                info.show()

    def show_tray(self):
        """最小化到托盘"""
        if self.if_save:
            self.set_ui("保存")
        self.hide()
        self.tray.show()

    def show_main(self):
        """显示主界面"""
        self.set_ui("配置")
        if self.config.global_config.get(self.config.global_config.ui_IfShowTray):
            self.tray.show()
        else:
            self.tray.hide()

    def on_tray_activated(self, reason):
        """双击返回主界面"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_main()

    def start_task(self, mode):
        """调起对应任务"""
        if self.main.MaaManager.isRunning():
            self.notify.push_notification(
                f"无法运行{mode}！",
                "当前已有任务正在运行，请在该任务结束后重试",
                "当前已有任务正在运行，请在该任务结束后重试",
                3,
            )
        else:
            self.main.maa_starter(mode)

    def stop_task(self):
        """中止当前任务"""
        if self.main.MaaManager.isRunning():
            if (
                self.main.MaaManager.mode == "日常代理"
                or self.main.MaaManager.mode == "人工排查"
            ):
                self.main.maa_ender(f"{self.main.MaaManager.mode}_结束")
            elif "设置MAA" in self.main.MaaManager.mode:
                self.notify.push_notification(
                    "正在设置MAA！",
                    "正在运行设置MAA任务，无法中止",
                    "正在运行设置MAA任务，无法中止",
                    3,
                )
        else:
            self.notify.push_notification(
                "无任务运行！",
                "当前无任务正在运行，无需中止",
                "当前无任务正在运行，无需中止",
                3,
            )

    def kill_main(self):
        """退出主程序"""
        self.close()
        QApplication.quit()

    def set_ui(self, mode):
        """设置窗口相关属性"""

        # 保存窗口相关属性
        if mode == "保存":

            self.config.global_config.set(
                self.config.global_config.ui_size,
                f"{self.geometry().width()}x{self.geometry().height()}",
            )
            self.config.global_config.set(
                self.config.global_config.ui_location,
                f"{self.geometry().x()}x{self.geometry().y()}",
            )
            if self.isMaximized():
                self.config.global_config.set(
                    self.config.global_config.ui_maximized, True
                )
            else:
                self.config.global_config.set(
                    self.config.global_config.ui_maximized, False
                )
            self.config.global_config.save()

        # 配置窗口相关属性
        elif mode == "配置":

            self.if_save = False

            size = list(
                map(
                    int,
                    self.config.global_config.get(
                        self.config.global_config.ui_size
                    ).split("x"),
                )
            )
            location = list(
                map(
                    int,
                    self.config.global_config.get(
                        self.config.global_config.ui_location
                    ).split("x"),
                )
            )
            self.setGeometry(location[0], location[1], size[0], size[1])
            if self.config.global_config.get(self.config.global_config.ui_maximized):
                self.showMaximized()
            else:
                self.showNormal()

            self.if_save = True

    def changeEvent(self, event: QtCore.QEvent):
        """重写后的 changeEvent"""

        # 最小化到托盘功能实现
        if event.type() == QtCore.QEvent.WindowStateChange:
            if self.windowState() & QtCore.Qt.WindowMinimized:
                if self.config.global_config.get(self.config.global_config.ui_IfToTray):
                    self.show_tray()

        # 保留其它 changeEvent 方法
        return super().changeEvent(event)

    def closeEvent(self, event: QCloseEvent):
        """清理残余进程"""

        self.set_ui("保存")

        # 清理各功能线程
        # self.main.Timer.stop()
        # self.main.Timer.deleteLater()
        # self.main.MaaManager.requestInterruption()
        # self.main.MaaManager.quit()
        # self.main.MaaManager.wait()

        # 关闭数据库连接
        self.config.close_database()

        event.accept()
