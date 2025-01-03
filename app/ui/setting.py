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
AUTO_MAA设置界面
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
    QComboBox,  #
    QTableWidgetItem,  #
    QHeaderView,  #
    QVBoxLayout,
    QHBoxLayout,
)
from qfluentwidgets import (
    Action,
    PushButton,
    LineEdit,
    PasswordLineEdit,
    TextBrowser,
    TableWidget,
    TimePicker,
    ComboBox,
    CheckBox,
    ScrollArea,
    SpinBox,
    FluentIcon,
    SwitchButton,
    RoundMenu,
    MessageBox,
    MessageBoxBase,
    HeaderCardWidget,
    BodyLabel,
    Dialog,
    SubtitleLabel,
    GroupHeaderCardWidget,
    SwitchSettingCard,
    ExpandGroupSettingCard,
    SingleDirectionScrollArea,
    PushSettingCard,
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

from app import AppConfig
from app.services import Notification, CryptoHandler
from app.utils import Updater, version_text
from .Widget import InputMessageBox, LineEditSettingCard


class Setting(QWidget):

    def __init__(self, config: AppConfig, notify: Notification, crypto: CryptoHandler):
        super(Setting, self).__init__()

        self.setObjectName("设置")

        self.config = config
        self.notify = notify
        self.crypto = crypto

        layout = QVBoxLayout()

        scrollArea = ScrollArea()
        scrollArea.setWidgetResizable(True)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)

        self.function = FunctionSettingCard(self, self.config)
        self.start = StartSettingCard(self, self.config)
        self.ui = UiSettingCard(self, self.config)
        self.notification = NotifySettingCard(self, self.config)
        self.security = SecuritySettingCard(self)
        self.updater = UpdaterSettingCard(self, self.config)
        self.other = OtherSettingCard(self, self.config)

        self.security.card_changePASSWORD.clicked.connect(self.change_PASSWORD)
        self.updater.card_CheckUpdate.clicked.connect(self.check_version)
        self.other.card_Tips.clicked.connect(self.show_tips)

        content_layout.addWidget(self.function)
        content_layout.addWidget(self.start)
        content_layout.addWidget(self.ui)
        content_layout.addWidget(self.notification)
        content_layout.addWidget(self.security)
        content_layout.addWidget(self.updater)
        content_layout.addWidget(self.other)

        scrollArea.setWidget(content_widget)

        layout.addWidget(scrollArea)

        self.setLayout(layout)

    def check_PASSWORD(self) -> None:
        """检查并配置管理密钥"""

        if self.config.key_path.exists():
            return None

        while True:

            choice = InputMessageBox(
                self,
                "未检测到管理密钥，请设置您的管理密钥",
                "管理密钥",
                "密码",
            )
            if choice.exec() and choice.input.text() != "":
                self.crypto.get_PASSWORD(choice.input.text())
                break
            else:
                choice = MessageBox(
                    "确认", "您没有输入管理密钥，确定要暂时跳过这一步吗？", self
                )
                if choice.exec():
                    break

    def change_PASSWORD(self) -> None:
        """修改管理密钥"""

        # 获取用户信息
        self.config.cur.execute("SELECT * FROM adminx WHERE True")
        data = self.config.cur.fetchall()

        if len(data) == 0:

            choice = MessageBox("验证通过", "当前无用户，验证自动通过", self)
            choice.cancelButton.hide()
            choice.buttonLayout.insertStretch(1)

            # 获取新的管理密钥
            if choice.exec():

                while True:

                    a = InputMessageBox(
                        self, "请输入新的管理密钥", "新管理密钥", "密码"
                    )
                    if a.exec() and a.input.text() != "":
                        # 修改管理密钥
                        self.crypto.get_PASSWORD(a.input.text())
                        choice = MessageBox("操作成功", "管理密钥修改成功", self)
                        choice.cancelButton.hide()
                        choice.buttonLayout.insertStretch(1)
                        if choice.exec():
                            break
                    else:
                        choice = MessageBox(
                            "确认",
                            "您没有输入新的管理密钥，是否取消修改管理密钥？",
                            self,
                        )
                        if choice.exec():
                            break

        else:
            # 验证管理密钥
            if_change = True

            while if_change:

                choice = InputMessageBox(
                    self, "请输入旧的管理密钥", "旧管理密钥", "密码"
                )
                if choice.exec() and choice.input.text() != "":

                    # 验证旧管理密钥
                    if self.crypto.check_PASSWORD(choice.input.text()):

                        PASSWORD_old = choice.input.text()
                        # 获取新的管理密钥
                        while True:

                            choice = InputMessageBox(
                                self, "请输入新的管理密钥", "新管理密钥", "密码"
                            )
                            if choice.exec() and choice.input.text() != "":

                                # 修改管理密钥
                                self.crypto.change_PASSWORD(
                                    data, PASSWORD_old, choice.input.text()
                                )
                                choice = MessageBox(
                                    "操作成功", "管理密钥修改成功", self
                                )
                                choice.cancelButton.hide()
                                choice.buttonLayout.insertStretch(1)
                                if choice.exec():
                                    if_change = False
                                    break

                            else:

                                choice = MessageBox(
                                    "确认",
                                    "您没有输入新的管理密钥，是否取消修改管理密钥？",
                                    self,
                                )
                                if choice.exec():
                                    if_change = False
                                    break

                    else:
                        choice = MessageBox("错误", "管理密钥错误", self)
                        choice.cancelButton.hide()
                        choice.buttonLayout.insertStretch(1)
                        if choice.exec():
                            pass
                else:
                    choice = MessageBox(
                        "确认",
                        "您没有输入管理密钥，是否取消修改管理密钥？",
                        self,
                    )
                    if choice.exec():
                        break

    def check_version(self):
        """检查版本更新，调起文件下载进程"""

        # 从本地版本信息文件获取当前版本信息
        with self.config.version_path.open(mode="r", encoding="utf-8") as f:
            version_current = json.load(f)
        main_version_current = list(
            map(int, version_current["main_version"].split("."))
        )
        updater_version_current = list(
            map(int, version_current["updater_version"].split("."))
        )
        # 检查更新器是否存在
        if not (self.config.app_path / "Updater.exe").exists():
            updater_version_current = [0, 0, 0, 0]

        # 从远程服务器获取最新版本信息
        for _ in range(3):
            try:
                response = requests.get(
                    "https://gitee.com/DLmaster_361/AUTO_MAA/raw/main/resources/version.json"
                )
                version_remote = response.json()
                break
            except Exception as e:
                err = e
                time.sleep(0.1)
        else:
            choice = MessageBox(
                "错误",
                f"获取版本信息时出错：\n{err}",
                self,
            )
            choice.cancelButton.hide()
            choice.buttonLayout.insertStretch(1)
            if choice.exec():
                return None

        main_version_remote = list(map(int, version_remote["main_version"].split(".")))
        updater_version_remote = list(
            map(int, version_remote["updater_version"].split("."))
        )

        # 有版本更新
        if (main_version_remote > main_version_current) or (
            updater_version_remote > updater_version_current
        ):

            # 生成版本更新信息
            if main_version_remote > main_version_current:
                main_version_info = f"    主程序：{version_text(main_version_current)} --> {version_text(main_version_remote)}\n"
            else:
                main_version_info = (
                    f"    主程序：{version_text(main_version_current)}\n"
                )
            if updater_version_remote > updater_version_current:
                updater_version_info = f"    更新器：{version_text(updater_version_current)} --> {version_text(updater_version_remote)}\n"
            else:
                updater_version_info = (
                    f"    更新器：{version_text(updater_version_current)}\n"
                )

            # 询问是否开始版本更新
            choice = MessageBox(
                "版本更新",
                f"发现新版本：\n{main_version_info}{updater_version_info}    更新说明：\n{version_remote['announcement'].replace("\n# ","\n   ！").replace("\n## ","\n        - ").replace("\n- ","\n            · ")}\n\n是否开始更新？\n\n    注意：主程序更新时AUTO_MAA将自动关闭",
                self,
            )
            if not choice.exec():
                return None

            # 更新更新器
            if updater_version_remote > updater_version_current:
                # 创建更新进程
                self.updater = Updater(
                    self.config.app_path,
                    "AUTO_MAA更新器",
                    main_version_remote,
                    updater_version_remote,
                )
                # 完成更新器的更新后更新主程序
                if main_version_remote > main_version_current:
                    self.updater.update_process.accomplish.connect(self.update_main)
                # 显示更新页面
                self.updater.ui.show()

            # 更新主程序
            elif main_version_remote > main_version_current:
                self.update_main()

        # 无版本更新
        else:
            self.notify.push_notification("已是最新版本~", " ", " ", 3)

    def update_main(self):
        """更新主程序"""

        subprocess.Popen(
            str(self.config.app_path / "Updater.exe"),
            shell=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.close()
        QApplication.quit()

    def show_tips(self):
        """显示小贴士"""

        choice = MessageBox("小贴士", "这里什么都没有~", self)
        choice.cancelButton.hide()
        choice.buttonLayout.insertStretch(1)
        if choice.exec():
            pass


class FunctionSettingCard(HeaderCardWidget):

    def __init__(self, parent=None, config: AppConfig = None):
        super().__init__(parent)

        self.setTitle("功能")

        self.config = config.global_config

        Layout = QVBoxLayout()

        self.card_IfSleep = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="启动时阻止系统休眠",
            content="仅阻止电脑自动休眠，不会影响屏幕是否熄灭",
            configItem=self.config.function_IfSleep,
        )

        self.card_IfSilence = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="静默模式",
            content="将各代理窗口置于后台运行，减少对前台的干扰",
            configItem=self.config.function_IfSilence,
        )

        # 添加各组到设置卡中
        Layout.addWidget(self.card_IfSleep)
        Layout.addWidget(self.card_IfSilence)

        self.viewLayout.addLayout(Layout)


class StartSettingCard(HeaderCardWidget):

    def __init__(self, parent=None, config: AppConfig = None):
        super().__init__(parent)

        self.setTitle("启动")

        self.config = config.global_config

        Layout = QVBoxLayout()

        self.card_IfSelfStart = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="开机时自动启动",
            content="将AUTO_MAA添加到开机启动项",
            configItem=self.config.start_IfSelfStart,
        )

        self.card_IfRunDirectly = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="启动后直接运行",
            content="启动AUTO_MAA后自动运行任务",
            configItem=self.config.start_IfRunDirectly,
        )

        # 添加各组到设置卡中
        Layout.addWidget(
            self.card_IfSelfStart,
        )
        Layout.addWidget(self.card_IfRunDirectly)

        self.viewLayout.addLayout(Layout)


class UiSettingCard(HeaderCardWidget):

    def __init__(self, parent=None, config: AppConfig = None):
        super().__init__(parent)

        self.setTitle("界面")

        self.config = config.global_config

        Layout = QVBoxLayout()

        self.card_IfShowTray = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="显示托盘图标",
            content="常态显示托盘图标",
            configItem=self.config.ui_IfShowTray,
        )

        self.card_IfToTray = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="最小化到托盘",
            content="最小化时隐藏到托盘",
            configItem=self.config.ui_IfToTray,
        )

        # 添加各组到设置卡中
        Layout.addWidget(self.card_IfShowTray)
        Layout.addWidget(self.card_IfToTray)

        self.viewLayout.addLayout(Layout)


class NotifySettingCard(HeaderCardWidget):

    def __init__(self, parent=None, config: AppConfig = None):
        super().__init__(parent)

        self.setTitle("通知")

        self.config = config

        Layout = QVBoxLayout()

        self.card_IfPushPlyer = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="推送系统通知",
            content="推送系统级通知，不会在通知中心停留",
            configItem=self.config.global_config.notify_IfPushPlyer,
        )

        self.card_SendMail = self.SendMailSettingCard(self, self.config)

        Layout.addWidget(self.card_IfPushPlyer)
        Layout.addWidget(self.card_SendMail)

        self.viewLayout.addLayout(Layout)

    class SendMailSettingCard(ExpandGroupSettingCard):

        def __init__(self, parent=None, config: AppConfig = None):
            super().__init__(
                FluentIcon.SETTING,
                "推送邮件通知",
                "通过AUTO_MAA官方通知服务邮箱推送任务结果",
                parent,
            )

            self.config = config.global_config

            widget = QWidget()
            Layout = QVBoxLayout(widget)

            self.card_IfSendMail = SwitchSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="推送邮件通知",
                content="是否启用邮件通知功能",
                configItem=self.config.notify_IfSendMail,
            )

            self.MailAddress = LineEditSettingCard(
                text="请输入邮箱地址",
                icon=FluentIcon.PAGE_RIGHT,
                title="邮箱地址",
                content="接收通知的邮箱地址",
                configItem=self.config.notify_MailAddress,
            )

            self.card_IfSendErrorOnly = SwitchSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="仅推送异常信息",
                content="仅在任务出现异常时推送通知",
                configItem=self.config.notify_IfSendErrorOnly,
            )

            Layout.addWidget(self.card_IfSendMail)
            Layout.addWidget(self.MailAddress)
            Layout.addWidget(self.card_IfSendErrorOnly)

            # 调整内部布局
            self.viewLayout.setContentsMargins(0, 0, 0, 0)
            self.viewLayout.setSpacing(0)

            self.addGroupWidget(widget)


class SecuritySettingCard(HeaderCardWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setTitle("安全")

        Layout = QVBoxLayout()

        self.card_changePASSWORD = PushSettingCard(
            text="修改",
            icon=FluentIcon.VPN,
            title="修改管理密钥",
            content="修改用于解密用户密码的管理密钥",
        )

        Layout.addWidget(self.card_changePASSWORD)

        self.viewLayout.addLayout(Layout)


class UpdaterSettingCard(HeaderCardWidget):

    def __init__(self, parent=None, config: AppConfig = None):
        super().__init__(parent)

        self.setTitle("更新")

        self.config = config.global_config

        Layout = QVBoxLayout()

        self.card_IfAutoUpdate = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="自动检查更新",
            content="将在启动时自动检查AUTO_MAA是否有新版本",
            configItem=self.config.update_IfAutoUpdate,
        )

        self.card_CheckUpdate = PushSettingCard(
            text="检查更新",
            icon=FluentIcon.UPDATE,
            title="获取最新版本",
            content="检查AUTO_MAA是否有新版本",
        )

        Layout.addWidget(self.card_IfAutoUpdate)
        Layout.addWidget(self.card_CheckUpdate)

        self.viewLayout.addLayout(Layout)


class OtherSettingCard(HeaderCardWidget):

    def __init__(self, parent=None, config: AppConfig = None):
        super().__init__(parent)

        self.setTitle("其他")

        self.config = config.global_config

        Layout = QVBoxLayout()

        self.card_Tips = PushSettingCard(
            text="查看",
            icon=FluentIcon.PAGE_RIGHT,
            title="小贴士",
            content="查看AUTO_MAA的小贴士",
        )

        Layout.addWidget(self.card_Tips)

        self.viewLayout.addLayout(Layout)
