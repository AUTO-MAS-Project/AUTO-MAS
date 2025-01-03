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
    QStackedWidget,
    QHBoxLayout,
)
from qfluentwidgets import (
    Action,
    PushButton,
    LineEdit,
    PasswordLineEdit,
    qconfig,
    TableWidget,
    Pivot,
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
    CommandBar,
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
import os
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
from app.services import Notification, CryptoHandler
from app.utils import Updater, version_text
from .Widget import InputMessageBox, LineEditSettingCard, SpinBoxSettingCard


class MemberManager(QWidget):

    def __init__(self, config: AppConfig, notify: Notification, crypto: CryptoHandler):
        super(MemberManager, self).__init__()

        self.setObjectName("脚本管理")

        self.config = config
        self.notify = notify
        self.crypto = crypto

        layout = QVBoxLayout(self)

        self.tools = CommandBar()

        self.member_manager = MemberSettingBox(self.config)

        # 逐个添加动作
        self.tools.addActions(
            [
                Action(
                    FluentIcon.ADD_TO, "新建脚本实例", triggered=self.add_setting_box
                ),
                Action(
                    FluentIcon.REMOVE_FROM,
                    "删除脚本实例",
                    triggered=self.del_setting_box,
                ),
            ]
        )
        self.tools.addSeparator()
        self.tools.addActions(
            [
                Action(
                    FluentIcon.LEFT_ARROW, "向左移动", triggered=self.left_setting_box
                ),
                Action(
                    FluentIcon.RIGHT_ARROW,
                    "向右移动",
                    triggered=self.right_setting_box,
                ),
            ]
        )

        # 批量添加动作
        self.tools.addAction(
            Action(
                FluentIcon.HIDE,
                "显示/隐藏密码",
                checkable=True,
                triggered=self.show_password,
            ),
        )

        layout.addWidget(self.tools)
        layout.addWidget(self.member_manager)

    def add_setting_box(self):
        """添加一个脚本实例"""

        choice = InputMessageBox(
            self, "选择一个脚本类型并添加相应脚本实例", "选择脚本类型", "选择", ["MAA"]
        )
        if choice.exec() and choice.input.currentIndex() != -1:

            if choice.input.currentText() == "MAA":

                index = len(self.member_manager.search_member()) + 1

                qconfig.load(
                    self.config.app_path / f"config/MaaConfig/脚本_{index}/config.json",
                    self.config.maa_config,
                )

                self.config.maa_config.set(self.config.maa_config.MaaSet_Name, "")
                self.config.maa_config.set(self.config.maa_config.MaaSet_Path, ".")
                self.config.maa_config.set(
                    self.config.maa_config.RunSet_AnnihilationTimeLimit, 40
                )
                self.config.maa_config.set(
                    self.config.maa_config.RunSet_RoutineTimeLimit, 10
                )
                self.config.maa_config.set(
                    self.config.maa_config.RunSet_RunTimesLimit, 3
                )
                self.config.maa_config.set(self.config.maa_config.MaaSet_Name, "")
                self.config.maa_config.set(self.config.maa_config.MaaSet_Name, "")
                self.config.maa_config.set(self.config.maa_config.MaaSet_Name, "")
                self.config.maa_config.save()

                self.member_manager.add_MaaSettingBox(index)
                self.member_manager.switch_SettingBox(index)

    def del_setting_box(self):
        """删除一个脚本实例"""

        name = self.member_manager.pivot.currentRouteKey()

        if name == None:
            return None

        choice = MessageBox(
            "确认",
            f"确定要删除 {name} 实例吗？",
            self,
        )
        if choice.exec():

            member_list = self.member_manager.search_member()
            move_list = [_ for _ in member_list if int(_[0][3:]) > int(name[3:])]

            type = [_[1] for _ in member_list if _[0] == name]
            index = max(int(name[3:]) - 1, 1)

            shutil.rmtree(self.config.app_path / f"config/{type[0]}Config/{name}")
            for member in move_list:
                if (
                    self.config.app_path / f"config/{member[1]}Config/{member[0]}"
                ).exists():
                    (
                        self.config.app_path / f"config/{member[1]}Config/{member[0]}"
                    ).rename(
                        self.config.app_path
                        / f"config/{member[1]}Config/{member[0][:3]}{int(member[0][3:])-1}",
                    )

            self.member_manager.clear_SettingBox()
            self.member_manager.show_SettingBox()
            self.member_manager.switch_SettingBox(index, if_after_clear=True)

    def left_setting_box(self):
        """向左移动脚本实例"""

        name = self.member_manager.pivot.currentRouteKey()

        if name == None:
            return None

        member_list = self.member_manager.search_member()
        index = int(name[3:])

        if index == 1:
            return None

        type_right = [_[1] for _ in member_list if _[0] == name]
        type_left = [_[1] for _ in member_list if _[0] == f"脚本_{index-1}"]

        (self.config.app_path / f"config/{type_right[0]}Config/脚本_{index}").rename(
            self.config.app_path / f"config/{type_right[0]}Config/脚本_0",
        )
        (self.config.app_path / f"config/{type_left[0]}Config/脚本_{index-1}").rename(
            self.config.app_path / f"config/{type_left[0]}Config/脚本_{index}",
        )
        (self.config.app_path / f"config/{type_right[0]}Config/脚本_0").rename(
            self.config.app_path / f"config/{type_right[0]}Config/脚本_{index-1}",
        )

        self.member_manager.clear_SettingBox()
        self.member_manager.show_SettingBox()
        self.member_manager.switch_SettingBox(index - 1, if_after_clear=True)

    def right_setting_box(self):
        """向左移动脚本实例"""

        name = self.member_manager.pivot.currentRouteKey()

        if name == None:
            return None

        member_list = self.member_manager.search_member()
        index = int(name[3:])

        if index == len(member_list):
            return None

        type_left = [_[1] for _ in member_list if _[0] == name]
        type_right = [_[1] for _ in member_list if _[0] == f"脚本_{index+1}"]

        (self.config.app_path / f"config/{type_left[0]}Config/脚本_{index}").rename(
            self.config.app_path / f"config/{type_left[0]}Config/脚本_0",
        )
        (self.config.app_path / f"config/{type_right[0]}Config/脚本_{index+1}").rename(
            self.config.app_path / f"config/{type_right[0]}Config/脚本_{index}",
        )
        (self.config.app_path / f"config/{type_left[0]}Config/脚本_0").rename(
            self.config.app_path / f"config/{type_left[0]}Config/脚本_{index+1}",
        )

        self.member_manager.clear_SettingBox()
        self.member_manager.show_SettingBox()
        self.member_manager.switch_SettingBox(index + 1, if_after_clear=True)

    def show_password(self):

        pass


class MemberSettingBox(QWidget):

    def __init__(self, config: AppConfig):
        super().__init__()

        self.setObjectName("脚本管理")
        self.config = config

        self.pivot = Pivot(self)
        self.stackedWidget = QStackedWidget(self)
        self.Layout = QVBoxLayout(self)

        self.SubInterface: List[MaaSettingBox] = []

        self.Layout.addWidget(self.pivot, 0, QtCore.Qt.AlignHCenter)
        self.Layout.addWidget(self.stackedWidget)
        self.Layout.setContentsMargins(0, 0, 0, 0)

        self.pivot.currentItemChanged.connect(
            lambda index: self.stackedWidget.setCurrentWidget(
                self.findChild(QWidget, index)
            )
        )
        self.pivot.currentItemChanged.connect(
            lambda index: qconfig.load(
                self.config.app_path / f"config/MaaConfig/{index}/config.json",
                self.config.maa_config,
            )
        )

        self.show_SettingBox()
        self.switch_SettingBox(1)

    def show_SettingBox(self) -> None:
        """加载所有子界面"""

        member_list = self.search_member()

        for member in member_list:
            if member[1] == "Maa":
                self.add_MaaSettingBox(int(member[0][3:]))

    def switch_SettingBox(self, index: int, if_after_clear: bool = False) -> None:
        """切换到指定的子界面"""

        member_list = self.search_member()

        if index > len(member_list):
            return None

        type = [_[1] for _ in member_list if _[0] == f"脚本_{index}"]

        if if_after_clear:
            self.pivot.currentItemChanged.disconnect()

        self.stackedWidget.setCurrentWidget(self.SubInterface[index - 1])
        self.pivot.setCurrentItem(self.SubInterface[index - 1].objectName())
        qconfig.load(
            self.config.app_path
            / f"config/{type[0]}Config/{self.SubInterface[index-1].objectName()}/config.json",
            self.config.maa_config,
        )

        if if_after_clear:
            self.pivot.currentItemChanged.connect(
                lambda index: self.stackedWidget.setCurrentWidget(
                    self.findChild(QWidget, index)
                )
            )
            self.pivot.currentItemChanged.connect(
                lambda index: qconfig.load(
                    self.config.app_path / f"config/MaaConfig/{index}/config.json",
                    self.config.maa_config,
                )
            )

    def clear_SettingBox(self) -> None:
        """清空所有子界面"""

        for sub_interface in self.SubInterface:
            self.stackedWidget.removeWidget(sub_interface)
            sub_interface.deleteLater()
        self.SubInterface.clear()
        self.pivot.clear()

    def add_MaaSettingBox(self, uid: int) -> None:
        """添加一个MAA设置界面"""

        maa_setting_box = MaaSettingBox(self.config, uid)

        self.SubInterface.append(maa_setting_box)

        self.stackedWidget.addWidget(self.SubInterface[-1])

        self.pivot.addItem(routeKey=f"脚本_{uid}", text=f"脚本 {uid}")

    def search_member(self) -> list:
        """搜索所有脚本实例"""

        member_list = []

        if (self.config.app_path / "config/MaaConfig").exists():
            for subdir in (self.config.app_path / "config/MaaConfig").iterdir():
                if subdir.is_dir():
                    member_list.append([subdir.name, "Maa"])

        return member_list


class MaaSettingBox(QWidget):

    def __init__(self, config: AppConfig, uid: int):
        super().__init__()

        self.setObjectName(f"脚本_{uid}")

        self.config = config

        layout = QVBoxLayout()

        scrollArea = ScrollArea()
        scrollArea.setWidgetResizable(True)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)

        self.app_setting = self.AppSettingCard(self, self.config.maa_config)

        content_layout.addWidget(self.app_setting)
        content_layout.addStretch(1)

        scrollArea.setWidget(content_widget)

        layout.addWidget(scrollArea)

        self.setLayout(layout)

    class AppSettingCard(HeaderCardWidget):

        def __init__(self, parent=None, maa_config: MaaConfig = None):
            super().__init__(parent)

            self.setTitle("MAA实例")

            self.maa_config = maa_config

            Layout = QVBoxLayout()

            self.card_Name = LineEditSettingCard(
                "实例名称",
                FluentIcon.EDIT,
                "实例名称",
                "用于标识MAA实例的名称",
                self.maa_config.MaaSet_Name,
            )
            self.card_Path = PushSettingCard(
                "选择文件夹",
                FluentIcon.FOLDER,
                "MAA目录",
                self.maa_config.get(self.maa_config.MaaSet_Path),
            )
            self.card_Set = PushSettingCard(
                "设置",
                FluentIcon.HOME,
                "MAA全局配置",
                "简洁模式下MAA将继承全局配置",
            )
            self.RunSet = self.RunSetSettingCard(self, self.maa_config)

            self.card_Path.clicked.connect(self.PathClicked)

            Layout.addWidget(self.card_Name)
            Layout.addWidget(self.card_Path)
            Layout.addWidget(self.card_Set)
            Layout.addWidget(self.RunSet)

            self.viewLayout.addLayout(Layout)

        def PathClicked(self):

            folder = QFileDialog.getExistingDirectory(self, "选择MAA目录", "./")
            if not folder or self.maa_config.get(self.maa_config.MaaSet_Path) == folder:
                return
            self.maa_config.set(self.maa_config.MaaSet_Path, folder)
            self.card_Path.setContent(folder)

        class RunSetSettingCard(ExpandGroupSettingCard):

            def __init__(self, parent=None, maa_config: MaaConfig = None):
                super().__init__(
                    FluentIcon.SETTING,
                    "运行",
                    "MAA运行调控选项",
                    parent,
                )

                self.maa_config = maa_config

                widget = QWidget()
                Layout = QVBoxLayout(widget)

                self.AnnihilationTimeLimit = SpinBoxSettingCard(
                    (1, 1024),
                    FluentIcon.PAGE_RIGHT,
                    "剿灭代理超时限制",
                    "MAA日志无变化时间超过该阈值视为超时",
                    self.maa_config.RunSet_AnnihilationTimeLimit,
                )

                self.RoutineTimeLimit = SpinBoxSettingCard(
                    (1, 1024),
                    FluentIcon.PAGE_RIGHT,
                    "日常代理超时限制",
                    "MAA日志无变化时间超过该阈值视为超时",
                    self.maa_config.RunSet_RoutineTimeLimit,
                )

                self.RunTimesLimit = SpinBoxSettingCard(
                    (1, 1024),
                    FluentIcon.PAGE_RIGHT,
                    "代理重试次数限制",
                    "若超过该次数限制仍未完成代理，视为代理失败",
                    self.maa_config.RunSet_RunTimesLimit,
                )

                Layout.addWidget(self.AnnihilationTimeLimit)
                Layout.addWidget(self.RoutineTimeLimit)
                Layout.addWidget(self.RunTimesLimit)

                self.viewLayout.setContentsMargins(0, 0, 0, 0)
                self.viewLayout.setSpacing(0)

                self.addGroupWidget(widget)
