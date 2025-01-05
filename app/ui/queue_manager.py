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
AUTO_MAA调度队列界面
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

from app import AppConfig, QueueConfig, MaaConfig
from app.services import Notification, CryptoHandler
from app.utils import Updater, version_text
from .Widget import (
    InputMessageBox,
    LineEditSettingCard,
    SpinBoxSettingCard,
    TimeEditSettingCard,
    NoOptionComboBoxSettingCard,
)


class QueueManager(QWidget):

    def __init__(
        self,
        config: AppConfig,
        notify: Notification,
        parent=None,
    ):
        super().__init__(parent)

        self.setObjectName("调度队列")

        self.config = config
        self.notify = notify

        setTheme(Theme.AUTO)

        layout = QVBoxLayout(self)

        self.tools = CommandBar()

        self.queue_manager = QueueSettingBox(self.config, self)

        # 逐个添加动作
        self.tools.addActions(
            [
                Action(
                    FluentIcon.ADD_TO, "新建调度队列", triggered=self.add_setting_box
                ),
                Action(
                    FluentIcon.REMOVE_FROM,
                    "删除调度队列",
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
        self.tools.addAction(Action(FluentIcon.ROTATE, "刷新", triggered=self.refresh))

        layout.addWidget(self.tools)
        layout.addWidget(self.queue_manager)

    def add_setting_box(self):
        """添加一个调度队列"""

        index = len(self.queue_manager.search_queue()) + 1

        qconfig.load(
            self.config.app_path / f"config/QueueConfig/调度队列_{index}.json",
            self.config.queue_config,
        )

        self.config.queue_config.set(self.config.queue_config.queueSet_Name, "")
        self.config.queue_config.set(self.config.queue_config.queueSet_Enabled, False)

        self.config.queue_config.set(self.config.queue_config.time_TimeEnabled_0, False)
        self.config.queue_config.set(self.config.queue_config.time_TimeSet_0, "00:00")
        self.config.queue_config.set(self.config.queue_config.time_TimeEnabled_1, False)
        self.config.queue_config.set(self.config.queue_config.time_TimeSet_1, "00:00")
        self.config.queue_config.set(self.config.queue_config.time_TimeEnabled_2, False)
        self.config.queue_config.set(self.config.queue_config.time_TimeSet_2, "00:00")
        self.config.queue_config.set(self.config.queue_config.time_TimeEnabled_3, False)
        self.config.queue_config.set(self.config.queue_config.time_TimeSet_3, "00:00")
        self.config.queue_config.set(self.config.queue_config.time_TimeEnabled_4, False)
        self.config.queue_config.set(self.config.queue_config.time_TimeSet_4, "00:00")
        self.config.queue_config.set(self.config.queue_config.time_TimeEnabled_5, False)
        self.config.queue_config.set(self.config.queue_config.time_TimeSet_5, "00:00")
        self.config.queue_config.set(self.config.queue_config.time_TimeEnabled_6, False)
        self.config.queue_config.set(self.config.queue_config.time_TimeSet_6, "00:00")
        self.config.queue_config.set(self.config.queue_config.time_TimeEnabled_7, False)
        self.config.queue_config.set(self.config.queue_config.time_TimeSet_7, "00:00")
        self.config.queue_config.set(self.config.queue_config.time_TimeEnabled_8, False)
        self.config.queue_config.set(self.config.queue_config.time_TimeSet_8, "00:00")
        self.config.queue_config.set(self.config.queue_config.time_TimeEnabled_9, False)
        self.config.queue_config.set(self.config.queue_config.time_TimeSet_9, "00:00")

        self.config.queue_config.set(self.config.queue_config.queue_Member_1, "禁用")
        self.config.queue_config.set(self.config.queue_config.queue_Member_2, "禁用")
        self.config.queue_config.set(self.config.queue_config.queue_Member_3, "禁用")
        self.config.queue_config.set(self.config.queue_config.queue_Member_4, "禁用")
        self.config.queue_config.set(self.config.queue_config.queue_Member_5, "禁用")
        self.config.queue_config.set(self.config.queue_config.queue_Member_6, "禁用")
        self.config.queue_config.set(self.config.queue_config.queue_Member_7, "禁用")
        self.config.queue_config.set(self.config.queue_config.queue_Member_8, "禁用")
        self.config.queue_config.set(self.config.queue_config.queue_Member_9, "禁用")
        self.config.queue_config.set(self.config.queue_config.queue_Member_10, "禁用")

        self.config.queue_config.save()

        self.queue_manager.add_QueueSettingBox(index)
        self.queue_manager.switch_SettingBox(index)

    def del_setting_box(self):
        """删除一个调度队列实例"""

        name = self.queue_manager.pivot.currentRouteKey()

        if name == None:
            return None

        choice = MessageBox(
            "确认",
            f"确定要删除 {name} 吗？",
            self,
        )
        if choice.exec():

            queue_list = self.queue_manager.search_queue()
            move_list = [_ for _ in queue_list if int(_[0][3:]) > int(name[3:])]

            index = max(int(name[3:]) - 1, 1)

            self.queue_manager.clear_SettingBox()

            os.remove(self.config.app_path / f"config/QueueConfig/{name}.json")
            for queue in move_list:
                if (
                    self.config.app_path / f"config/QueueConfig/{queue[0]}.json"
                ).exists():
                    (
                        self.config.app_path / f"config/QueueConfig/{queue[0]}.json"
                    ).rename(
                        self.config.app_path
                        / f"config/QueueConfig/调度队列_{int(queue[0][5:])-1}.json",
                    )

            self.queue_manager.show_SettingBox(index)

    def left_setting_box(self):
        """向左移动调度队列实例"""

        name = self.queue_manager.pivot.currentRouteKey()

        if name == None:
            return None

        index = int(name[5:])

        if index == 1:
            return None

        self.queue_manager.clear_SettingBox()

        (self.config.app_path / f"config/QueueConfig/调度队列_{index}.json").rename(
            self.config.app_path / f"config/QueueConfig/调度队列_0.json",
        )
        shutil.move(
            str(self.config.app_path / f"config/QueueConfig/调度队列_{index-1}.json"),
            str(self.config.app_path / f"config/QueueConfig/调度队列_{index}.json"),
        )
        (self.config.app_path / f"config/QueueConfig/调度队列_0.json").rename(
            self.config.app_path / f"config/QueueConfig/调度队列_{index-1}.json",
        )

        self.queue_manager.show_SettingBox(index - 1)

    def right_setting_box(self):
        """向右移动调度队列实例"""

        name = self.queue_manager.pivot.currentRouteKey()

        if name == None:
            return None

        queue_list = self.queue_manager.search_queue()
        index = int(name[5:])

        if index == len(queue_list):
            return None

        self.queue_manager.clear_SettingBox()

        (self.config.app_path / f"config/QueueConfig/调度队列_{index}.json").rename(
            self.config.app_path / f"config/QueueConfig/调度队列_0.json",
        )
        (self.config.app_path / f"config/QueueConfig/调度队列_{index+1}.json").rename(
            self.config.app_path / f"config/QueueConfig/调度队列_{index}.json",
        )
        (self.config.app_path / f"config/QueueConfig/调度队列_0.json").rename(
            self.config.app_path / f"config/QueueConfig/调度队列_{index+1}.json",
        )

        self.queue_manager.show_SettingBox(index + 1)

    def refresh(self):
        """刷新调度队列界面"""

        index = int(self.queue_manager.pivot.currentRouteKey()[5:])
        self.queue_manager.clear_SettingBox()
        self.queue_manager.show_SettingBox(index)


class QueueSettingBox(QWidget):

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)

        self.setObjectName("调度队列管理")
        self.config = config

        self.pivot = Pivot(self)
        self.stackedWidget = QStackedWidget(self)
        self.Layout = QVBoxLayout(self)

        self.script_list: List[QueueMemberSettingBox] = []

        self.Layout.addWidget(self.pivot, 0, QtCore.Qt.AlignHCenter)
        self.Layout.addWidget(self.stackedWidget)
        self.Layout.setContentsMargins(0, 0, 0, 0)

        self.pivot.currentItemChanged.connect(
            lambda index: self.switch_SettingBox(int(index[5:]), if_chang_pivot=False)
        )

        self.show_SettingBox(1)

    def show_SettingBox(self, index) -> None:
        """加载所有子界面"""

        queue_list = self.search_queue()

        for queue in queue_list:
            self.add_QueueSettingBox(int(queue[0][5:]))

        self.switch_SettingBox(index)

    def switch_SettingBox(self, index: int, if_chang_pivot: bool = True) -> None:
        """切换到指定的子界面"""

        queue_list = self.search_queue()

        if index > len(queue_list):
            return None

        qconfig.load(
            self.config.app_path
            / f"config/QueueConfig/{self.script_list[index-1].objectName()}.json",
            self.config.queue_config,
        )

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

    def add_QueueSettingBox(self, uid: int) -> None:
        """添加一个调度队列设置界面"""

        maa_setting_box = QueueMemberSettingBox(self.config, uid, self)

        self.script_list.append(maa_setting_box)

        self.stackedWidget.addWidget(self.script_list[-1])

        self.pivot.addItem(routeKey=f"调度队列_{uid}", text=f"调度队列 {uid}")

    def search_queue(self) -> list:
        """搜索所有调度队列实例"""

        queue_list = []

        if (self.config.app_path / "config/QueueConfig").exists():
            for json_file in (self.config.app_path / "config/QueueConfig").glob(
                "*.json"
            ):
                with json_file.open("r", encoding="utf-8") as f:
                    info = json.load(f)
                queue_list.append([json_file.stem, info["QueueSet"]["Name"]])

        return queue_list


class QueueMemberSettingBox(QWidget):

    def __init__(self, config: AppConfig, uid: int, parent=None):
        super().__init__(parent)

        self.setObjectName(f"调度队列_{uid}")

        self.config = config

        layout = QVBoxLayout()

        scrollArea = ScrollArea()
        scrollArea.setWidgetResizable(True)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)

        self.queue_set = self.QueueSetSettingCard(self, self.config.queue_config)
        self.time = self.TimeSettingCard(self, self.config.queue_config)
        self.task = self.TaskSettingCard(self, self.config)

        content_layout.addWidget(self.queue_set)
        content_layout.addWidget(self.time)
        content_layout.addWidget(self.task)
        content_layout.addStretch(1)

        scrollArea.setWidget(content_widget)

        layout.addWidget(scrollArea)

        self.setLayout(layout)

    class QueueSetSettingCard(HeaderCardWidget):

        def __init__(self, parent=None, queue_config: QueueConfig = None):
            super().__init__(parent)

            self.setTitle("队列设置")

            self.queue_config = queue_config

            Layout = QVBoxLayout()

            self.card_Name = LineEditSettingCard(
                "调度队列名称",
                FluentIcon.EDIT,
                "调度队列名称",
                "用于标识调度队列的名称",
                self.queue_config.queueSet_Name,
            )
            self.card_Enable = SwitchSettingCard(
                FluentIcon.HOME,
                "状态",
                "调度队列状态",
                self.queue_config.queueSet_Enabled,
            )

            Layout.addWidget(self.card_Name)
            Layout.addWidget(self.card_Enable)

            self.viewLayout.addLayout(Layout)

    class TimeSettingCard(HeaderCardWidget):

        def __init__(self, parent=None, queue_config: QueueConfig = None):
            super().__init__(parent)

            self.setTitle("定时设置")

            self.queue_config = queue_config

            widget_1 = QWidget()
            Layout_1 = QVBoxLayout(widget_1)
            widget_2 = QWidget()
            Layout_2 = QVBoxLayout(widget_2)
            Layout = QHBoxLayout()

            self.card_Time_0 = TimeEditSettingCard(
                FluentIcon.STOP_WATCH,
                "定时 1",
                "",
                self.queue_config.time_TimeEnabled_0,
                self.queue_config.time_TimeSet_0,
            )
            self.card_Time_1 = TimeEditSettingCard(
                FluentIcon.STOP_WATCH,
                "定时 2",
                "",
                self.queue_config.time_TimeEnabled_1,
                self.queue_config.time_TimeSet_1,
            )
            self.card_Time_2 = TimeEditSettingCard(
                FluentIcon.STOP_WATCH,
                "定时 3",
                "",
                self.queue_config.time_TimeEnabled_2,
                self.queue_config.time_TimeSet_2,
            )
            self.card_Time_3 = TimeEditSettingCard(
                FluentIcon.STOP_WATCH,
                "定时 4",
                "",
                self.queue_config.time_TimeEnabled_3,
                self.queue_config.time_TimeSet_3,
            )
            self.card_Time_4 = TimeEditSettingCard(
                FluentIcon.STOP_WATCH,
                "定时 5",
                "",
                self.queue_config.time_TimeEnabled_4,
                self.queue_config.time_TimeSet_4,
            )
            self.card_Time_5 = TimeEditSettingCard(
                FluentIcon.STOP_WATCH,
                "定时 6",
                "",
                self.queue_config.time_TimeEnabled_5,
                self.queue_config.time_TimeSet_5,
            )
            self.card_Time_6 = TimeEditSettingCard(
                FluentIcon.STOP_WATCH,
                "定时 7",
                "",
                self.queue_config.time_TimeEnabled_6,
                self.queue_config.time_TimeSet_6,
            )
            self.card_Time_7 = TimeEditSettingCard(
                FluentIcon.STOP_WATCH,
                "定时 8",
                "",
                self.queue_config.time_TimeEnabled_7,
                self.queue_config.time_TimeSet_7,
            )
            self.card_Time_8 = TimeEditSettingCard(
                FluentIcon.STOP_WATCH,
                "定时 9",
                "",
                self.queue_config.time_TimeEnabled_8,
                self.queue_config.time_TimeSet_8,
            )
            self.card_Time_9 = TimeEditSettingCard(
                FluentIcon.STOP_WATCH,
                "定时 10",
                "",
                self.queue_config.time_TimeEnabled_9,
                self.queue_config.time_TimeSet_9,
            )

            Layout_1.addWidget(self.card_Time_0)
            Layout_1.addWidget(self.card_Time_1)
            Layout_1.addWidget(self.card_Time_2)
            Layout_1.addWidget(self.card_Time_3)
            Layout_1.addWidget(self.card_Time_4)
            Layout_2.addWidget(self.card_Time_5)
            Layout_2.addWidget(self.card_Time_6)
            Layout_2.addWidget(self.card_Time_7)
            Layout_2.addWidget(self.card_Time_8)
            Layout_2.addWidget(self.card_Time_9)
            Layout.addWidget(widget_1)
            Layout.addWidget(widget_2)

            self.viewLayout.addLayout(Layout)

    class QueueSetSettingCard(HeaderCardWidget):

        def __init__(self, parent=None, queue_config: QueueConfig = None):
            super().__init__(parent)

            self.setTitle("队列设置")

            self.queue_config = queue_config

            Layout = QVBoxLayout()

            self.card_Name = LineEditSettingCard(
                "调度队列名称",
                FluentIcon.EDIT,
                "调度队列名称",
                "用于标识调度队列的名称",
                self.queue_config.queueSet_Name,
            )
            self.card_Enable = SwitchSettingCard(
                FluentIcon.HOME,
                "状态",
                "调度队列状态",
                self.queue_config.queueSet_Enabled,
            )

            Layout.addWidget(self.card_Name)
            Layout.addWidget(self.card_Enable)

            self.viewLayout.addLayout(Layout)

    class TaskSettingCard(HeaderCardWidget):

        def __init__(self, parent=None, config: AppConfig = None):
            super().__init__(parent)

            self.setTitle("定时设置")

            self.config = config
            self.queue_config = config.queue_config

            Layout = QVBoxLayout()

            member_list = self.search_member()

            self.card_Member_1 = NoOptionComboBoxSettingCard(
                self.queue_config.queue_Member_1,
                FluentIcon.APPLICATION,
                "任务实例1",
                "第一个调起的脚本任务实例",
                member_list[0],
                member_list[1],
            )
            self.card_Member_2 = NoOptionComboBoxSettingCard(
                self.queue_config.queue_Member_2,
                FluentIcon.APPLICATION,
                "任务实例2",
                "第二个调起的脚本任务实例",
                member_list[0],
                member_list[1],
            )
            self.card_Member_3 = NoOptionComboBoxSettingCard(
                self.queue_config.queue_Member_3,
                FluentIcon.APPLICATION,
                "任务实例3",
                "第三个调起的脚本任务实例",
                member_list[0],
                member_list[1],
            )
            self.card_Member_4 = NoOptionComboBoxSettingCard(
                self.queue_config.queue_Member_4,
                FluentIcon.APPLICATION,
                "任务实例4",
                "第四个调起的脚本任务实例",
                member_list[0],
                member_list[1],
            )
            self.card_Member_5 = NoOptionComboBoxSettingCard(
                self.queue_config.queue_Member_5,
                FluentIcon.APPLICATION,
                "任务实例5",
                "第五个调起的脚本任务实例",
                member_list[0],
                member_list[1],
            )
            self.card_Member_6 = NoOptionComboBoxSettingCard(
                self.queue_config.queue_Member_6,
                FluentIcon.APPLICATION,
                "任务实例6",
                "第六个调起的脚本任务实例",
                member_list[0],
                member_list[1],
            )
            self.card_Member_7 = NoOptionComboBoxSettingCard(
                self.queue_config.queue_Member_7,
                FluentIcon.APPLICATION,
                "任务实例7",
                "第七个调起的脚本任务实例",
                member_list[0],
                member_list[1],
            )
            self.card_Member_8 = NoOptionComboBoxSettingCard(
                self.queue_config.queue_Member_8,
                FluentIcon.APPLICATION,
                "任务实例8",
                "第八个调起的脚本任务实例",
                member_list[0],
                member_list[1],
            )
            self.card_Member_9 = NoOptionComboBoxSettingCard(
                self.queue_config.queue_Member_9,
                FluentIcon.APPLICATION,
                "任务实例9",
                "第九个调起的脚本任务实例",
                member_list[0],
                member_list[1],
            )
            self.card_Member_10 = NoOptionComboBoxSettingCard(
                self.queue_config.queue_Member_10,
                FluentIcon.APPLICATION,
                "任务实例10",
                "第十个调起的脚本任务实例",
                member_list[0],
                member_list[1],
            )

            Layout.addWidget(self.card_Member_1)
            Layout.addWidget(self.card_Member_2)
            Layout.addWidget(self.card_Member_3)
            Layout.addWidget(self.card_Member_4)
            Layout.addWidget(self.card_Member_5)
            Layout.addWidget(self.card_Member_6)
            Layout.addWidget(self.card_Member_7)
            Layout.addWidget(self.card_Member_8)
            Layout.addWidget(self.card_Member_9)
            Layout.addWidget(self.card_Member_10)

            self.viewLayout.addLayout(Layout)

        def search_member(self) -> list:
            """搜索所有脚本实例"""

            member_list_name = ["禁用"]
            member_list_text = ["未启用"]

            if (self.config.app_path / "config/MaaConfig").exists():
                for subdir in (self.config.app_path / "config/MaaConfig").iterdir():
                    if subdir.is_dir():
                        member_list_name.append(subdir.name)
                        with (subdir / "config.json").open("r", encoding="utf-8") as f:
                            info = json.load(f)
                        if info["MaaSet"]["Name"] != "":
                            member_list_text.append(
                                f"{subdir.name} - {info["MaaSet"]["Name"]}"
                            )
                        else:
                            member_list_text.append(subdir.name)

            return [member_list_name, member_list_text]
