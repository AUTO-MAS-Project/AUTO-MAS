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
AUTO_MAA脚本管理界面
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
    setTheme,
    Theme,
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
import json
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
from .Widget import (
    InputMessageBox,
    LineEditSettingCard,
    SpinBoxSettingCard,
    SetMessageBox,
)


class MemberManager(QWidget):

    def __init__(
        self,
        config: AppConfig,
        notify: Notification,
        crypto: CryptoHandler,
        parent=None,
    ):
        super().__init__(parent)

        self.setObjectName("脚本管理")

        self.config = config
        self.notify = notify
        self.crypto = crypto

        setTheme(Theme.AUTO)

        layout = QVBoxLayout(self)

        self.tools = CommandBar()

        self.member_manager = MemberSettingBox(self.config, self.crypto, self)

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
                    FluentIcon.RIGHT_ARROW, "向右移动", triggered=self.right_setting_box
                ),
            ]
        )
        self.tools.addSeparator()
        self.key = Action(
            FluentIcon.HIDE,
            "显示/隐藏密码",
            checkable=True,
            triggered=self.show_password,
        )
        self.tools.addAction(
            self.key,
        )

        layout.addWidget(self.tools)
        layout.addWidget(self.member_manager)

    def add_setting_box(self):
        """添加一个脚本实例"""

        choice = InputMessageBox(
            self,
            "选择一个脚本类型并添加相应脚本实例",
            "选择脚本类型",
            "选择",
            ["MAA"],
        )
        if choice.exec() and choice.input.currentIndex() != -1:

            if choice.input.currentText() == "MAA":

                index = len(self.member_manager.search_member()) + 1

                qconfig.load(
                    self.config.app_path / f"config/MaaConfig/脚本_{index}/config.json",
                    self.config.maa_config,
                )
                self.config.clear_maa_config()
                self.config.maa_config.save()

                self.config.open_database("Maa", f"脚本_{index}")
                self.config.init_database("Maa")
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

            self.member_manager.clear_SettingBox()

            shutil.rmtree(self.config.app_path / f"config/{type[0]}Config/{name}")
            self.change_queue(name, "禁用")
            for member in move_list:
                if (
                    self.config.app_path / f"config/{member[1]}Config/{member[0]}"
                ).exists():
                    (
                        self.config.app_path / f"config/{member[1]}Config/{member[0]}"
                    ).rename(
                        self.config.app_path
                        / f"config/{member[1]}Config/脚本_{int(member[0][3:])-1}",
                    )
                self.change_queue(member[0], f"脚本_{int(member[0][3:])-1}")

            self.member_manager.show_SettingBox(index)

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

        self.member_manager.clear_SettingBox()

        (self.config.app_path / f"config/{type_right[0]}Config/脚本_{index}").rename(
            self.config.app_path / f"config/{type_right[0]}Config/脚本_0"
        )
        self.change_queue(f"脚本_{index}", "脚本_0")
        (self.config.app_path / f"config/{type_left[0]}Config/脚本_{index-1}").rename(
            self.config.app_path / f"config/{type_left[0]}Config/脚本_{index}"
        )
        self.change_queue(f"脚本_{index-1}", f"脚本_{index}")
        (self.config.app_path / f"config/{type_right[0]}Config/脚本_0").rename(
            self.config.app_path / f"config/{type_right[0]}Config/脚本_{index-1}"
        )
        self.change_queue("脚本_0", f"脚本_{index-1}")

        self.member_manager.show_SettingBox(index - 1)

    def right_setting_box(self):
        """向右移动脚本实例"""

        name = self.member_manager.pivot.currentRouteKey()

        if name == None:
            return None

        member_list = self.member_manager.search_member()
        index = int(name[3:])

        if index == len(member_list):
            return None

        type_left = [_[1] for _ in member_list if _[0] == name]
        type_right = [_[1] for _ in member_list if _[0] == f"脚本_{index+1}"]

        self.member_manager.clear_SettingBox()

        (self.config.app_path / f"config/{type_left[0]}Config/脚本_{index}").rename(
            self.config.app_path / f"config/{type_left[0]}Config/脚本_0",
        )
        self.change_queue(f"脚本_{index}", "脚本_0")
        (self.config.app_path / f"config/{type_right[0]}Config/脚本_{index+1}").rename(
            self.config.app_path / f"config/{type_right[0]}Config/脚本_{index}",
        )
        self.change_queue(f"脚本_{index+1}", f"脚本_{index}")
        (self.config.app_path / f"config/{type_left[0]}Config/脚本_0").rename(
            self.config.app_path / f"config/{type_left[0]}Config/脚本_{index+1}",
        )
        self.change_queue("脚本_0", f"脚本_{index+1}")

        self.member_manager.show_SettingBox(index + 1)

    def show_password(self):

        if self.config.PASSWORD == "":
            choice = InputMessageBox(
                self,
                "请输入管理密钥",
                "管理密钥",
                "密码",
            )
            if choice.exec() and choice.input.text() != "":
                self.config.PASSWORD = choice.input.text()
                self.member_manager.script_list[
                    int(self.member_manager.pivot.currentRouteKey()[3:]) - 1
                ].user_setting.user_list.update_user_info("normal")
                self.key.setIcon(FluentIcon.VIEW)
                self.key.setChecked(True)
            else:
                self.config.PASSWORD = ""
                self.member_manager.script_list[
                    int(self.member_manager.pivot.currentRouteKey()[3:]) - 1
                ].user_setting.user_list.update_user_info("normal")
                self.key.setIcon(FluentIcon.HIDE)
                self.key.setChecked(False)
        else:
            self.config.PASSWORD = ""
            self.member_manager.script_list[
                int(self.member_manager.pivot.currentRouteKey()[3:]) - 1
            ].user_setting.user_list.update_user_info("normal")
            self.key.setIcon(FluentIcon.HIDE)
            self.key.setChecked(False)

    def change_queue(self, old: str, new: str) -> None:
        """修改调度队列配置文件的队列参数"""

        if (self.config.app_path / "config/QueueConfig").exists():
            for json_file in (self.config.app_path / "config/QueueConfig").glob(
                "*.json"
            ):
                with json_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)

                for i in range(10):
                    if data["Queue"][f"Member_{i+1}"] == old:
                        data["Queue"][f"Member_{i+1}"] = new

                with json_file.open("w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)


class MemberSettingBox(QWidget):

    def __init__(self, config: AppConfig, crypto: CryptoHandler, parent=None):
        super().__init__(parent)

        self.setObjectName("脚本管理")
        self.config = config
        self.crypto = crypto

        self.pivot = Pivot(self)
        self.stackedWidget = QStackedWidget(self)
        self.Layout = QVBoxLayout(self)

        self.script_list: List[MaaSettingBox] = []

        self.Layout.addWidget(self.pivot, 0, QtCore.Qt.AlignHCenter)
        self.Layout.addWidget(self.stackedWidget)
        self.Layout.setContentsMargins(0, 0, 0, 0)

        self.pivot.currentItemChanged.connect(
            lambda index: self.switch_SettingBox(int(index[3:]), if_chang_pivot=False)
        )

        self.show_SettingBox(1)

    def show_SettingBox(self, index) -> None:
        """加载所有子界面"""

        member_list = self.search_member()

        qconfig.load(
            self.config.app_path / "config/临时.json",
            self.config.maa_config,
        )
        self.config.clear_maa_config()
        for member in member_list:
            if member[1] == "Maa":
                self.config.open_database(member[1], member[0])
                self.add_MaaSettingBox(int(member[0][3:]))
        if (self.config.app_path / "config/临时.json").exists():
            (self.config.app_path / "config/临时.json").unlink()

        self.switch_SettingBox(index)

    def switch_SettingBox(self, index: int, if_chang_pivot: bool = True) -> None:
        """切换到指定的子界面"""

        member_list = self.search_member()

        if index > len(member_list):
            return None

        type = [_[1] for _ in member_list if _[0] == f"脚本_{index}"]

        qconfig.load(
            self.config.app_path
            / f"config/{type[0]}Config/{self.script_list[index-1].objectName()}/config.json",
            self.config.maa_config,
        )
        self.config.open_database(type[0], self.script_list[index - 1].objectName())
        self.script_list[index - 1].user_setting.user_list.update_user_info("normal")

        if if_chang_pivot:
            self.pivot.setCurrentItem(self.script_list[index - 1].objectName())
        self.stackedWidget.setCurrentWidget(self.script_list[index - 1])

    def clear_SettingBox(self) -> None:
        """清空所有子界面"""

        for sub_interface in self.script_list:
            self.stackedWidget.removeWidget(sub_interface)
            sub_interface.deleteLater()
        self.script_list.clear()
        self.pivot.clear()
        qconfig.load(
            self.config.app_path / "config/临时.json",
            self.config.maa_config,
        )
        self.config.clear_maa_config()
        if (self.config.app_path / "config/临时.json").exists():
            (self.config.app_path / "config/临时.json").unlink()
        self.config.close_database()

    def add_MaaSettingBox(self, uid: int) -> None:
        """添加一个MAA设置界面"""

        maa_setting_box = MaaSettingBox(self.config, self.crypto, uid, self)

        self.script_list.append(maa_setting_box)

        self.stackedWidget.addWidget(self.script_list[-1])

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

    def __init__(self, config: AppConfig, crypto: CryptoHandler, uid: int, parent=None):
        super().__init__(parent)

        self.setObjectName(f"脚本_{uid}")

        self.config = config
        self.crypto = crypto

        layout = QVBoxLayout()

        scrollArea = ScrollArea()
        scrollArea.setWidgetResizable(True)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)

        self.app_setting = self.AppSettingCard(self, self.config.maa_config)
        self.user_setting = self.UserSettingCard(
            self, self.objectName(), self.config, self.crypto
        )

        content_layout.addWidget(self.app_setting)
        content_layout.addWidget(self.user_setting)
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
                "请输入实例名称",
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
                    "MAA日志无变化时间超过该阈值视为超时，单位为分钟",
                    self.maa_config.RunSet_AnnihilationTimeLimit,
                )

                self.RoutineTimeLimit = SpinBoxSettingCard(
                    (1, 1024),
                    FluentIcon.PAGE_RIGHT,
                    "日常代理超时限制",
                    "MAA日志无变化时间超过该阈值视为超时，单位为分钟",
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

    class UserSettingCard(HeaderCardWidget):

        def __init__(
            self,
            parent=None,
            name: str = None,
            config: AppConfig = None,
            crypto: CryptoHandler = None,
        ):
            super().__init__(parent)

            self.setTitle("用户列表")

            self.config = config
            self.crypto = crypto
            self.name = name

            Layout = QVBoxLayout()

            self.user_list = self.UserListBox(self.name, self.config, self.crypto, self)

            self.tools = CommandBar()
            self.tools.addActions(
                [
                    Action(
                        FluentIcon.ADD, "新建用户", triggered=self.user_list.add_user
                    ),
                    Action(
                        FluentIcon.REMOVE, "删除用户", triggered=self.user_list.del_user
                    ),
                ]
            )
            self.tools.addSeparator()
            self.tools.addActions(
                [
                    Action(FluentIcon.UP, "向上移动", triggered=self.user_list.up_user),
                    Action(
                        FluentIcon.DOWN, "向下移动", triggered=self.user_list.down_user
                    ),
                ]
            )
            self.tools.addSeparator()
            self.tools.addAction(
                Action(
                    FluentIcon.SCROLL, "模式转换", triggered=self.user_list.switch_user
                )
            )
            self.tools.addSeparator()
            self.tools.addAction(
                Action(
                    FluentIcon.DEVELOPER_TOOLS, "用户选项配置", triggered=self.set_more
                )
            )

            Layout.addWidget(self.tools)
            Layout.addWidget(self.user_list)

            self.viewLayout.addLayout(Layout)

        def set_more(self):

            self.config.cur.execute("SELECT * FROM adminx WHERE True")
            data = self.config.cur.fetchall()

            if self.user_list.pivot.currentRouteKey() == f"{self.name}_简洁用户列表":

                user_list = [_[0] for _ in data if _[15] == "simple"]
                set_list = ["自定义基建"]

                choice = SetMessageBox(
                    self.parent().parent().parent().parent().parent().parent().parent(),
                    "用户选项配置",
                    ["选择要配置的用户", "选择要配置的选项"],
                    [user_list, set_list],
                )
                if (
                    choice.exec()
                    and choice.input[0].currentIndex() != -1
                    and choice.input[1].currentIndex() != -1
                ):

                    if choice.input[1].currentIndex() == 0:
                        file_path, _ = QFileDialog.getOpenFileName(
                            self,
                            "选择自定义基建文件",
                            ".",
                            "JSON 文件 (*.json)",
                        )
                        if file_path != "":
                            (
                                self.config.app_path
                                / f"config/MaaConfig/{self.name}/simple/{choice.input[0].currentIndex()}/infrastructure"
                            ).mkdir(parents=True, exist_ok=True)
                            shutil.copy(
                                file_path,
                                self.config.app_path
                                / f"config/MaaConfig/{self.name}/simple/{choice.input[0].currentIndex()}/infrastructure",
                            )
                        else:
                            choice = MessageBox(
                                "错误",
                                "未选择自定义基建文件",
                                self.parent()
                                .parent()
                                .parent()
                                .parent()
                                .parent()
                                .parent()
                                .parent(),
                            )
                            choice.cancelButton.hide()
                            choice.buttonLayout.insertStretch(1)
                            if choice.exec():
                                pass

        class UserListBox(QWidget):

            def __init__(
                self, name: str, config: AppConfig, crypto: CryptoHandler, parent=None
            ):
                super().__init__(parent)
                self.setObjectName(f"{name}_用户列表")
                self.config = config
                self.crypto = crypto

                self.name = name

                self.if_user_list_editable = True
                self.if_update_database = True
                self.if_update_config = True

                self.user_mode_list = ["simple", "beta"]
                self.user_column = [
                    "admin",
                    "id",
                    "server",
                    "day",
                    "status",
                    "last",
                    "game",
                    "game_1",
                    "game_2",
                    "routine",
                    "annihilation",
                    "infrastructure",
                    "password",
                    "notes",
                    "numb",
                    "mode",
                    "uid",
                ]
                self.userlist_simple_index = [
                    0,
                    1,
                    2,
                    3,
                    4,
                    5,
                    6,
                    7,
                    8,
                    "-",
                    9,
                    10,
                    11,
                    12,
                    "-",
                    "-",
                    "-",
                ]
                self.userlist_beta_index = [
                    0,
                    "-",
                    "-",
                    1,
                    2,
                    3,
                    "-",
                    "-",
                    "-",
                    4,
                    5,
                    "-",
                    6,
                    7,
                    "-",
                    "-",
                    "-",
                ]

                self.pivot = Pivot(self)
                self.stackedWidget = QStackedWidget(self)
                self.Layout = QVBoxLayout(self)

                self.user_list_simple = TableWidget()
                self.user_list_simple.setObjectName(f"{self.name}_简洁用户列表")
                self.user_list_simple.setColumnCount(13)
                self.user_list_simple.setBorderVisible(True)
                self.user_list_simple.setBorderRadius(10)
                self.user_list_simple.setWordWrap(False)
                self.user_list_simple.setVerticalScrollBarPolicy(
                    QtCore.Qt.ScrollBarAlwaysOff
                )
                self.user_list_simple.setHorizontalHeaderLabels(
                    [
                        "用户名",
                        "账号ID",
                        "服务器",
                        "代理天数",
                        "状态",
                        "执行情况",
                        "关卡",
                        "备选关卡-1",
                        "备选关卡-2",
                        "剿灭",
                        "自定义基建",
                        "密码",
                        "备注",
                    ]
                )

                self.user_list_beta = TableWidget()
                self.user_list_beta.setObjectName(f"{name}_高级用户列表")
                self.user_list_beta.setColumnCount(8)
                self.user_list_beta.setBorderVisible(True)
                self.user_list_beta.setBorderRadius(10)
                self.user_list_beta.setWordWrap(False)
                self.user_list_beta.setVerticalScrollBarPolicy(
                    QtCore.Qt.ScrollBarAlwaysOff
                )
                self.user_list_beta.setHorizontalHeaderLabels(
                    [
                        "用户名",
                        "代理天数",
                        "状态",
                        "执行情况",
                        "日常",
                        "剿灭",
                        "密码",
                        "备注",
                    ]
                )

                self.user_list_simple.itemChanged.connect(
                    lambda item: self.change_user_Item(item, "simple")
                )

                self.stackedWidget.addWidget(self.user_list_simple)
                self.pivot.addItem(
                    routeKey=f"{name}_简洁用户列表", text=f"简洁用户列表"
                )
                self.stackedWidget.addWidget(self.user_list_beta)
                self.pivot.addItem(
                    routeKey=f"{name}_高级用户列表", text=f"高级用户列表"
                )

                self.Layout.addWidget(self.pivot, 0, QtCore.Qt.AlignHCenter)
                self.Layout.addWidget(self.stackedWidget)
                self.Layout.setContentsMargins(0, 0, 0, 0)

                self.update_user_info("normal")
                self.switch_SettingBox(f"{name}_简洁用户列表")
                self.pivot.currentItemChanged.connect(
                    lambda index: self.switch_SettingBox(index)
                )

            def switch_SettingBox(self, index: str) -> None:
                """切换到指定的子界面"""

                self.pivot.setCurrentItem(index)
                if "简洁用户列表" in index:
                    self.stackedWidget.setCurrentWidget(self.user_list_simple)
                elif "高级用户列表" in index:
                    self.stackedWidget.setCurrentWidget(self.user_list_beta)

            def update_user_info(self, operation: str) -> None:
                """将本地数据库中的用户配置同步至GUI的用户管理界面"""

                # 读入本地数据库
                self.config.cur.execute("SELECT * FROM adminx WHERE True")
                data = self.config.cur.fetchall()

                # 处理部分模式调整
                if operation == "read_only":
                    self.if_user_list_editable = False
                elif operation == "editable":
                    self.if_user_list_editable = True

                # 阻止GUI用户数据被立即写入数据库形成死循环
                self.if_update_database = False

                # user_switch_list = ["转为高级", "转为简洁"]
                # self.user_switch.setText(user_switch_list[index])

                # 同步简洁用户配置列表
                data_simple = [_ for _ in data if _[15] == "simple"]
                self.user_list_simple.setRowCount(len(data_simple))
                height = self.user_list_simple.horizontalHeader().height()

                for i, row in enumerate(data_simple):

                    height += self.user_list_simple.rowHeight(i)

                    for j, value in enumerate(row):

                        if self.userlist_simple_index[j] == "-":
                            continue

                        # 生成表格组件
                        if j == 2:
                            item = ComboBox()
                            item.addItems(["官服", "B服"])
                            if value == "Official":
                                item.setCurrentIndex(0)
                            elif value == "Bilibili":
                                item.setCurrentIndex(1)
                            item.currentIndexChanged.connect(
                                partial(
                                    self.change_user_CellWidget,
                                    data_simple[i][16],
                                    self.user_column[j],
                                )
                            )
                        elif j in [4, 10, 11]:
                            item = ComboBox()
                            item.addItems(["启用", "禁用"])
                            if value == "y":
                                item.setCurrentIndex(0)
                            elif value == "n":
                                item.setCurrentIndex(1)
                            item.currentIndexChanged.connect(
                                partial(
                                    self.change_user_CellWidget,
                                    data_simple[i][16],
                                    self.user_column[j],
                                )
                            )
                        elif j == 3 and value == -1:
                            item = QTableWidgetItem("无限")
                        elif j == 5:
                            curdate = server_date()
                            if curdate != value:
                                item = QTableWidgetItem("今日未代理")
                            else:
                                item = QTableWidgetItem(
                                    f"今日已代理{data_simple[i][14]}次"
                                )
                            item.setFlags(
                                QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
                            )
                        elif j == 12:
                            if self.config.PASSWORD == "":
                                item = QTableWidgetItem("******")
                                item.setFlags(
                                    QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
                                )
                            else:
                                result = self.crypto.decryptx(
                                    value, self.config.PASSWORD
                                )
                                item = QTableWidgetItem(result)
                                if result == "管理密钥错误":
                                    item.setFlags(
                                        QtCore.Qt.ItemIsSelectable
                                        | QtCore.Qt.ItemIsEnabled
                                    )
                        else:
                            item = QTableWidgetItem(str(value))

                        # 组件录入表格
                        if j in [2, 4, 10, 11]:
                            if not self.if_user_list_editable:
                                item.setEnabled(False)
                            self.user_list_simple.setCellWidget(
                                data_simple[i][16], self.userlist_simple_index[j], item
                            )
                        else:
                            self.user_list_simple.setItem(
                                data_simple[i][16], self.userlist_simple_index[j], item
                            )
                self.user_list_simple.setFixedHeight(
                    height + self.user_list_simple.frameWidth() * 2 + 10
                )

                # 同步高级用户配置列表
                data_beta = [_ for _ in data if _[15] == "beta"]
                self.user_list_beta.setRowCount(len(data_beta))
                height = self.user_list_beta.horizontalHeader().height()

                for i, row in enumerate(data_beta):

                    height += self.user_list_beta.rowHeight(i)

                    for j, value in enumerate(row):

                        if self.userlist_beta_index[j] == "-":
                            continue

                        # 生成表格组件
                        if j in [4, 9, 10]:
                            item = ComboBox()
                            item.addItems(["启用", "禁用"])
                            if value == "y":
                                item.setCurrentIndex(0)
                            elif value == "n":
                                item.setCurrentIndex(1)
                            item.currentIndexChanged.connect(
                                partial(
                                    self.change_user_CellWidget,
                                    data_beta[i][16],
                                    self.user_column[j],
                                )
                            )
                        elif j == 3 and value == -1:
                            item = QTableWidgetItem("无限")
                        elif j == 5:
                            curdate = server_date()
                            if curdate != value:
                                item = QTableWidgetItem("今日未代理")
                            else:
                                item = QTableWidgetItem(
                                    f"今日已代理{data_beta[i][14]}次"
                                )
                            item.setFlags(
                                QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
                            )
                        elif j == 12:
                            if self.config.PASSWORD == "":
                                item = QTableWidgetItem("******")
                                item.setFlags(
                                    QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
                                )
                            else:
                                result = self.crypto.decryptx(
                                    value, self.config.PASSWORD
                                )
                                item = QTableWidgetItem(result)
                                if result == "管理密钥错误":
                                    item.setFlags(
                                        QtCore.Qt.ItemIsSelectable
                                        | QtCore.Qt.ItemIsEnabled
                                    )
                        else:
                            item = QTableWidgetItem(str(value))

                        # 组件录入表格
                        if j in [4, 9, 10]:
                            if not self.if_user_list_editable:
                                item.setEnabled(False)
                            self.user_list_beta.setCellWidget(
                                data_beta[i][16], self.userlist_beta_index[j], item
                            )
                        else:
                            self.user_list_beta.setItem(
                                data_beta[i][16], self.userlist_beta_index[j], item
                            )
                self.user_list_beta.setFixedHeight(
                    height + self.user_list_beta.frameWidth() * 2 + 10
                )

                # 设置列表可编辑状态
                if self.if_user_list_editable:
                    self.user_list_simple.setEditTriggers(TableWidget.AllEditTriggers)
                    self.user_list_beta.setEditTriggers(TableWidget.AllEditTriggers)
                else:
                    self.user_list_simple.setEditTriggers(TableWidget.NoEditTriggers)
                    self.user_list_beta.setEditTriggers(TableWidget.NoEditTriggers)

                # 允许GUI改变被同步到本地数据库
                self.if_update_database = True

                # 设置用户配置列表的标题栏宽度
                self.user_list_simple.horizontalHeader().setSectionResizeMode(
                    QHeaderView.Stretch
                )
                self.user_list_beta.horizontalHeader().setSectionResizeMode(
                    QHeaderView.Stretch
                )

            def change_user_Item(self, item: QTableWidgetItem, mode):
                """将GUI中发生修改的用户配置表中的一般信息同步至本地数据库"""

                # 验证能否写入本地数据库
                if not self.if_update_database:
                    return None

                text = item.text()
                # 简洁用户配置列表
                if mode == "simple":
                    # 待写入信息预处理
                    if item.column() == 3:  # 代理天数
                        try:
                            text = max(int(text), -1)
                        except ValueError:
                            self.update_user_info("normal")
                            return None
                    if item.column() in [6, 7, 8]:  # 关卡号
                        # 导入与应用特殊关卡规则
                        games = {}
                        with self.config.gameid_path.open(
                            mode="r", encoding="utf-8"
                        ) as f:
                            gameids = f.readlines()
                            for line in gameids:
                                if "：" in line:
                                    game_in, game_out = line.split("：", 1)
                                    games[game_in.strip()] = game_out.strip()
                        text = games.get(text, text)
                    if item.column() == 11:  # 密码
                        text = self.crypto.encryptx(text)

                    # 保存至本地数据库
                    if text != "":
                        self.config.cur.execute(
                            f"UPDATE adminx SET {self.user_column[self.userlist_simple_index.index(item.column())]} = ? WHERE mode = 'simple' AND uid = ?",
                            (text, item.row()),
                        )
                # 高级用户配置列表
                elif mode == "beta":
                    # 待写入信息预处理
                    if item.column() == 1:  # 代理天数
                        try:
                            text = max(int(text), -1)
                        except ValueError:
                            self.update_user_info("normal")
                            return None
                    if item.column() == 6:  # 密码
                        text = self.crypto.encryptx(text)

                    # 保存至本地数据库
                    if text != "":
                        self.config.cur.execute(
                            f"UPDATE adminx SET {self.user_column[self.userlist_beta_index.index(item.column())]} = ? WHERE mode = 'beta' AND uid = ?",
                            (text, item.row()),
                        )
                self.config.db.commit()

                # 同步一般用户信息更改到GUI
                self.update_user_info("normal")

            def change_user_CellWidget(self, row, column, index):
                """将GUI中发生修改的用户配置表中的CellWidget类信息同步至本地数据库"""

                # 验证能否写入本地数据库
                if not self.if_update_database:
                    return None

                if "简洁用户列表" in self.pivot.currentRouteKey():
                    mode = 0
                elif "高级用户列表" in self.pivot.currentRouteKey():
                    mode = 1

                # 初次开启自定义MAA配置或选择修改MAA配置时调起MAA配置任务
                # if (
                #     mode == 1
                #     and column in ["routine", "annihilation"]
                #     and (
                #         index == 2
                #         or (
                #             index == 0
                #             and not (
                #                 self.config.app_path
                #                 / f"data/MAAconfig/{self.user_mode_list[index]}/{row}/{column}/gui.json"
                #             ).exists()
                #         )
                #     )
                # ):
                #     pass
                # self.MaaManager.get_json_path = [
                #     index,
                #     row,
                #     column,
                # ]
                # self.maa_starter("设置MAA_用户")

                # 服务器
                if mode == 0 and column == "server":
                    server_list = ["Official", "Bilibili"]
                    self.config.cur.execute(
                        f"UPDATE adminx SET server = ? WHERE mode = 'simple' AND uid = ?",
                        (server_list[index], row),
                    )
                # 其它(启用/禁用)
                elif index in [0, 1]:
                    index_list = ["y", "n"]
                    self.config.cur.execute(
                        f"UPDATE adminx SET {column} = ? WHERE mode = ? AND uid = ?",
                        (
                            index_list[index],
                            self.user_mode_list[mode],
                            row,
                        ),
                    )
                self.config.db.commit()

                # 同步用户组件信息修改到GUI
                self.update_user_info("normal")

            def add_user(self):
                """添加一位新用户"""

                # 插入预设用户数据
                if "简洁用户列表" in self.pivot.currentRouteKey():
                    set_book = ["simple", self.user_list_simple.rowCount()]
                elif "高级用户列表" in self.pivot.currentRouteKey():
                    set_book = ["beta", self.user_list_beta.rowCount()]
                self.config.cur.execute(
                    "INSERT INTO adminx VALUES('新用户','手机号码（官服）/B站ID（B服）','Official',-1,'y','2000-01-01','1-7','-','-','n','n','n',?,'无',0,?,?)",
                    (
                        self.crypto.encryptx("未设置"),
                        set_book[0],
                        set_book[1],
                    ),
                )
                self.config.db.commit(),

                # 同步新用户至GUI
                self.update_user_info("normal")

            def del_user(self) -> None:
                """删除选中的首位用户"""

                # 获取对应的行索引
                if "简洁用户列表" in self.pivot.currentRouteKey():
                    row = self.user_list_simple.currentRow()
                    current_numb = self.user_list_simple.rowCount()
                    mode = 0
                elif "高级用户列表" in self.pivot.currentRouteKey():
                    row = self.user_list_beta.currentRow()
                    current_numb = self.user_list_beta.rowCount()
                    mode = 1

                # 判断选择合理性
                if row == -1:
                    choice = MessageBox(
                        "错误",
                        "请选中一个用户后再执行删除操作",
                        self.parent()
                        .parent()
                        .parent()
                        .parent()
                        .parent()
                        .parent()
                        .parent()
                        .parent()
                        .parent(),
                    )
                    choice.cancelButton.hide()
                    choice.buttonLayout.insertStretch(1)
                    if choice.exec():
                        return None

                # 确认待删除用户信息
                self.config.cur.execute(
                    "SELECT * FROM adminx WHERE mode = ? AND uid = ?",
                    (
                        self.user_mode_list[mode],
                        row,
                    ),
                )
                data = self.config.cur.fetchall()
                choice = MessageBox(
                    "确认",
                    f"确定要删除用户 {data[0][0]} 吗？",
                    self.parent()
                    .parent()
                    .parent()
                    .parent()
                    .parent()
                    .parent()
                    .parent()
                    .parent()
                    .parent(),
                )

                # 删除用户
                if choice.exec():
                    # 删除所选用户
                    self.config.cur.execute(
                        "DELETE FROM adminx WHERE mode = ? AND uid = ?",
                        (
                            self.user_mode_list[mode],
                            row,
                        ),
                    )
                    self.config.db.commit()

                    if (
                        self.config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row}"
                    ).exists():
                        shutil.rmtree(
                            self.config.app_path
                            / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row}"
                        )
                    # 后续用户补位
                    for i in range(row + 1, current_numb):
                        self.config.cur.execute(
                            "UPDATE adminx SET uid = ? WHERE mode = ? AND uid = ?",
                            (
                                i - 1,
                                self.user_mode_list[mode],
                                i,
                            ),
                        )
                        self.config.db.commit()
                        if (
                            self.config.app_path
                            / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{i}"
                        ).exists():
                            (
                                self.config.app_path
                                / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{i}"
                            ).rename(
                                self.config.app_path
                                / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{i}"
                            )

                    # 同步最终结果至GUI
                    self.update_user_info("normal")

            def up_user(self):
                """向上移动用户"""

                # 获取对应的行索引
                if "简洁用户列表" in self.pivot.currentRouteKey():
                    row = self.user_list_simple.currentRow()
                    mode = 0
                elif "高级用户列表" in self.pivot.currentRouteKey():
                    row = self.user_list_beta.currentRow()
                    mode = 1

                # 判断选择合理性
                if row == -1:
                    choice = MessageBox(
                        "错误",
                        "请选中一个用户后再执行向下移动操作",
                        self.parent()
                        .parent()
                        .parent()
                        .parent()
                        .parent()
                        .parent()
                        .parent()
                        .parent()
                        .parent(),
                    )
                    choice.cancelButton.hide()
                    choice.buttonLayout.insertStretch(1)
                    if choice.exec():
                        return None

                if row == 0:
                    return None

                self.config.cur.execute(
                    "UPDATE adminx SET uid = ? WHERE mode = ? AND uid = ?",
                    (
                        -1,
                        self.user_mode_list[mode],
                        row,
                    ),
                )
                self.config.cur.execute(
                    "UPDATE adminx SET uid = ? WHERE mode = ? AND uid = ?",
                    (
                        row,
                        self.user_mode_list[mode],
                        row - 1,
                    ),
                )
                self.config.cur.execute(
                    "UPDATE adminx SET uid = ? WHERE mode = ? AND uid = ?",
                    (
                        row - 1,
                        self.user_mode_list[mode],
                        -1,
                    ),
                )
                self.config.db.commit()

                if (
                    self.config.app_path
                    / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row}"
                ).exists():
                    (
                        self.config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row}"
                    ).rename(
                        self.config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{-1}"
                    )
                if (
                    self.config.app_path
                    / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row - 1}"
                ).exists():
                    (
                        self.config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row - 1}"
                    ).rename(
                        self.config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row}"
                    )
                if (
                    self.config.app_path
                    / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{-1}"
                ).exists():
                    (
                        self.config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{-1}"
                    ).rename(
                        self.config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row - 1}"
                    )

                self.update_user_info("normal")
                if "简洁用户列表" in self.pivot.currentRouteKey():
                    self.user_list_simple.selectRow(row - 1)
                elif "高级用户列表" in self.pivot.currentRouteKey():
                    self.user_list_beta.selectRow(row - 1)

            def down_user(self):
                """向下移动用户"""

                # 获取对应的行索引
                if "简洁用户列表" in self.pivot.currentRouteKey():
                    row = self.user_list_simple.currentRow()
                    current_numb = self.user_list_simple.rowCount()
                    mode = 0
                elif "高级用户列表" in self.pivot.currentRouteKey():
                    row = self.user_list_beta.currentRow()
                    current_numb = self.user_list_beta.rowCount()
                    mode = 1

                # 判断选择合理性
                if row == -1:
                    choice = MessageBox(
                        "错误",
                        "请选中一个用户后再执行向下移动操作",
                        self.parent()
                        .parent()
                        .parent()
                        .parent()
                        .parent()
                        .parent()
                        .parent()
                        .parent()
                        .parent(),
                    )
                    choice.cancelButton.hide()
                    choice.buttonLayout.insertStretch(1)
                    if choice.exec():
                        return None

                if row == current_numb - 1:
                    return None

                self.config.cur.execute(
                    "UPDATE adminx SET uid = ? WHERE mode = ? AND uid = ?",
                    (
                        -1,
                        self.user_mode_list[mode],
                        row,
                    ),
                )
                self.config.cur.execute(
                    "UPDATE adminx SET uid = ? WHERE mode = ? AND uid = ?",
                    (
                        row,
                        self.user_mode_list[mode],
                        row + 1,
                    ),
                )
                self.config.cur.execute(
                    "UPDATE adminx SET uid = ? WHERE mode = ? AND uid = ?",
                    (
                        row + 1,
                        self.user_mode_list[mode],
                        -1,
                    ),
                )
                self.config.db.commit()

                if (
                    self.config.app_path
                    / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row}"
                ).exists():
                    (
                        self.config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row}"
                    ).rename(
                        self.config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{-1}"
                    )
                if (
                    self.config.app_path
                    / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row + 1}"
                ).exists():
                    (
                        self.config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row + 1}"
                    ).rename(
                        self.config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row}"
                    )
                if (
                    self.config.app_path
                    / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{-1}"
                ).exists():
                    (
                        self.config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{-1}"
                    ).rename(
                        self.config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row + 1}"
                    )

                self.update_user_info("normal")
                if "简洁用户列表" in self.pivot.currentRouteKey():
                    self.user_list_simple.selectRow(row + 1)
                elif "高级用户列表" in self.pivot.currentRouteKey():
                    self.user_list_beta.selectRow(row + 1)

            def switch_user(self) -> None:
                """切换用户配置模式"""

                # 获取当前用户配置模式信息
                if "简洁用户列表" in self.pivot.currentRouteKey():
                    row = self.user_list_simple.currentRow()
                    mode = 0
                elif "高级用户列表" in self.pivot.currentRouteKey():
                    row = self.user_list_beta.currentRow()
                    mode = 1

                # 判断选择合理性
                if row == -1:
                    choice = MessageBox(
                        "错误",
                        "请选中一个用户后再执行切换操作",
                        self.parent()
                        .parent()
                        .parent()
                        .parent()
                        .parent()
                        .parent()
                        .parent()
                        .parent()
                        .parent(),
                    )
                    choice.cancelButton.hide()
                    choice.buttonLayout.insertStretch(1)
                    if choice.exec():
                        return None

                # 确认待切换用户信息
                self.config.cur.execute(
                    "SELECT * FROM adminx WHERE mode = ? AND uid = ?",
                    (
                        self.user_mode_list[mode],
                        row,
                    ),
                )
                data = self.config.cur.fetchall()

                mode_list = ["简洁", "高级"]
                choice = MessageBox(
                    "确认",
                    f"确定要将用户 {data[0][0]} 转为{mode_list[1 - mode]}配置模式吗？",
                    self.parent()
                    .parent()
                    .parent()
                    .parent()
                    .parent()
                    .parent()
                    .parent()
                    .parent()
                    .parent(),
                )

                # 切换用户
                if choice.exec():
                    self.config.cur.execute("SELECT * FROM adminx WHERE True")
                    data = self.config.cur.fetchall()
                    if mode == 0:
                        current_numb = self.user_list_simple.rowCount()
                    elif mode == 1:
                        current_numb = self.user_list_beta.rowCount()
                    # 切换所选用户
                    other_numb = len(data) - current_numb
                    self.config.cur.execute(
                        "UPDATE adminx SET mode = ?, uid = ? WHERE mode = ? AND uid = ?",
                        (
                            self.user_mode_list[1 - mode],
                            other_numb,
                            self.user_mode_list[mode],
                            row,
                        ),
                    )
                    self.config.db.commit()
                    if (
                        self.config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row}"
                    ).exists():
                        shutil.move(
                            self.config.app_path
                            / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row}",
                            self.config.app_path
                            / f"config/MaaConfig/{self.name}/{self.user_mode_list[1 - mode]}/{other_numb}",
                        )
                    # 后续用户补位
                    for i in range(row + 1, current_numb):
                        self.config.cur.execute(
                            "UPDATE adminx SET uid = ? WHERE mode = ? AND uid = ?",
                            (
                                i - 1,
                                self.user_mode_list[mode],
                                i,
                            ),
                        )
                        self.config.db.commit(),
                        if (
                            self.config.app_path
                            / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{i}"
                        ).exists():
                            (
                                self.config.app_path
                                / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{i}"
                            ).rename(
                                self.config.app_path
                                / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{i - 1}"
                            )

                    self.update_user_info("normal")


def server_date() -> str:
    """获取当前的服务器日期"""

    dt = datetime.datetime.now()
    if dt.time() < datetime.datetime.min.time().replace(hour=4):
        dt = dt - datetime.timedelta(days=1)
    return dt.strftime("%Y-%m-%d")
