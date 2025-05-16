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
AUTO_MAA计划管理界面
v4.3
作者：DLmaster_361
"""

from loguru import logger
from PySide6.QtWidgets import (
    QWidget,
    QFileDialog,
    QHBoxLayout,
    QVBoxLayout,
    QStackedWidget,
    QTableWidgetItem,
    QHeaderView,
)
from PySide6.QtGui import QIcon
from qfluentwidgets import (
    Action,
    ScrollArea,
    FluentIcon,
    MessageBox,
    HeaderCardWidget,
    CommandBar,
    ExpandGroupSettingCard,
    PushSettingCard,
    TableWidget,
    PrimaryToolButton,
)
from PySide6.QtCore import Signal
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import List
import shutil
import json

from app.core import Config, MainInfoBar, TaskManager, MaaPlanConfig, Network
from app.services import Crypto
from .downloader import DownloadManager
from .Widget import (
    LineEditMessageBox,
    LineEditSettingCard,
    SpinBoxSettingCard,
    ComboBoxMessageBox,
    EditableComboBoxSettingCard,
    PasswordLineEditSettingCard,
    UserLableSettingCard,
    ComboBoxSettingCard,
    SwitchSettingCard,
    PushAndSwitchButtonSettingCard,
    PushAndComboBoxSettingCard,
    PivotArea,
)


class PlanManager(QWidget):
    """计划管理父界面"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("计划管理")

        layout = QVBoxLayout(self)

        self.tools = CommandBar()

        self.plan_manager = self.PlanSettingBox(self)

        # 逐个添加动作
        self.tools.addActions(
            [
                Action(FluentIcon.ADD_TO, "新建计划表", triggered=self.add_setting_box),
                Action(
                    FluentIcon.REMOVE_FROM, "删除计划表", triggered=self.del_setting_box
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

        layout.addWidget(self.tools)
        layout.addWidget(self.plan_manager)

    def add_setting_box(self):
        """添加一个计划表"""

        choice = ComboBoxMessageBox(
            self.window(),
            "选择一个计划类型以添加相应计划表",
            ["选择计划类型"],
            [["MAA"]],
        )
        if choice.exec() and choice.input[0].currentIndex() != -1:

            if choice.input[0].currentText() == "MAA":

                index = len(Config.plan_dict) + 1

                maa_plan_config = MaaPlanConfig()
                maa_plan_config.load(
                    Config.app_path / f"config/MaaPlanConfig/计划_{index}/config.json",
                    maa_plan_config,
                )
                maa_plan_config.save()

                Config.plan_dict[f"计划_{index}"] = {
                    "Type": "Maa",
                    "Path": Config.app_path / f"config/MaaPlanConfig/计划_{index}",
                    "Config": maa_plan_config,
                }

                self.plan_manager.add_MaaSettingBox(index)
                self.plan_manager.switch_SettingBox(index)

                logger.success(f"计划管理 计划_{index} 添加成功")
                MainInfoBar.push_info_bar(
                    "success", "操作成功", f"添加计划表 计划_{index}", 3000
                )

    def del_setting_box(self):
        """删除一个计划表"""

        name = self.plan_manager.pivot.currentRouteKey()

        if name == None:
            logger.warning("删除计划表时未选择计划表")
            MainInfoBar.push_info_bar(
                "warning", "未选择计划表", "请选择一个计划表", 5000
            )
            return None

        if len(Config.running_list) > 0:
            logger.warning("删除计划表时调度队列未停止运行")
            MainInfoBar.push_info_bar(
                "warning", "调度中心正在执行任务", "请等待或手动中止任务", 5000
            )
            return None

        choice = MessageBox(
            "确认",
            f"确定要删除 {name} 吗？",
            self.window(),
        )
        if choice.exec():

            self.plan_manager.clear_SettingBox()

            shutil.rmtree(Config.plan_dict[name]["Path"])
            Config.change_plan(name, "禁用")
            for i in range(int(name[3:]) + 1, len(Config.plan_dict) + 1):
                if Config.plan_dict[f"计划_{i}"]["Path"].exists():
                    Config.plan_dict[f"计划_{i}"]["Path"].rename(
                        Config.plan_dict[f"计划_{i}"]["Path"].with_name(f"计划_{i-1}")
                    )
                Config.change_queue(f"计划_{i}", f"计划_{i-1}")

            self.plan_manager.show_SettingBox(max(int(name[3:]) - 1, 1))

            logger.success(f"计划表 {name} 删除成功")
            MainInfoBar.push_info_bar("success", "操作成功", f"删除计划表 {name}", 3000)

    def left_setting_box(self):
        """向左移动计划表"""

        name = self.plan_manager.pivot.currentRouteKey()

        if name == None:
            logger.warning("向左移动计划表时未选择计划表")
            MainInfoBar.push_info_bar(
                "warning", "未选择计划表", "请选择一个计划表", 5000
            )
            return None

        index = int(name[3:])

        if index == 1:
            logger.warning("向左移动计划表时已到达最左端")
            MainInfoBar.push_info_bar(
                "warning", "已经是第一个计划表", "无法向左移动", 5000
            )
            return None

        if len(Config.running_list) > 0:
            logger.warning("向左移动计划表时调度队列未停止运行")
            MainInfoBar.push_info_bar(
                "warning", "调度中心正在执行任务", "请等待或手动中止任务", 5000
            )
            return None

        self.plan_manager.clear_SettingBox()

        Config.plan_dict[name]["Path"].rename(
            Config.plan_dict[name]["Path"].with_name("计划_0")
        )
        Config.change_queue(name, "计划_0")
        Config.plan_dict[f"计划_{index-1}"]["Path"].rename(
            Config.plan_dict[name]["Path"]
        )
        Config.change_queue(f"计划_{index-1}", name)
        Config.plan_dict[name]["Path"].with_name("计划_0").rename(
            Config.plan_dict[f"计划_{index-1}"]["Path"]
        )
        Config.change_queue("计划_0", f"计划_{index-1}")

        self.plan_manager.show_SettingBox(index - 1)

        logger.success(f"计划表 {name} 左移成功")
        MainInfoBar.push_info_bar("success", "操作成功", f"左移计划表 {name}", 3000)

    def right_setting_box(self):
        """向右移动计划表"""

        name = self.plan_manager.pivot.currentRouteKey()

        if name == None:
            logger.warning("向右移动计划表时未选择计划表")
            MainInfoBar.push_info_bar(
                "warning", "未选择计划表", "请选择一个计划表", 5000
            )
            return None

        index = int(name[3:])

        if index == len(Config.plan_dict):
            logger.warning("向右移动计划表时已到达最右端")
            MainInfoBar.push_info_bar(
                "warning", "已经是最后一个计划表", "无法向右移动", 5000
            )
            return None

        if len(Config.running_list) > 0:
            logger.warning("向右移动计划表时调度队列未停止运行")
            MainInfoBar.push_info_bar(
                "warning", "调度中心正在执行任务", "请等待或手动中止任务", 5000
            )
            return None

        self.plan_manager.clear_SettingBox()

        Config.plan_dict[name]["Path"].rename(
            Config.plan_dict[name]["Path"].with_name("计划_0")
        )
        Config.change_queue(name, "计划_0")
        Config.plan_dict[f"计划_{index+1}"]["Path"].rename(
            Config.plan_dict[name]["Path"]
        )
        Config.change_queue(f"计划_{index+1}", name)
        Config.plan_dict[name]["Path"].with_name("计划_0").rename(
            Config.plan_dict[f"计划_{index+1}"]["Path"]
        )
        Config.change_queue("计划_0", f"计划_{index+1}")

        self.plan_manager.show_SettingBox(index + 1)

        logger.success(f"计划表 {name} 右移成功")
        MainInfoBar.push_info_bar("success", "操作成功", f"右移计划表 {name}", 3000)

    def refresh_dashboard(self):
        """刷新所有计划表的用户仪表盘"""

        for script in self.plan_manager.script_list:
            script.user_setting.user_manager.user_dashboard.load_info()

    class PlanSettingBox(QWidget):
        """计划管理子页面组"""

        def __init__(self, parent=None):
            super().__init__(parent)

            self.setObjectName("计划管理页面组")

            self.pivotArea = PivotArea(self)
            self.pivot = self.pivotArea.pivot

            self.stackedWidget = QStackedWidget(self)
            self.stackedWidget.setContentsMargins(0, 0, 0, 0)
            self.stackedWidget.setStyleSheet("background: transparent; border: none;")

            self.script_list: List[PlanManager.PlanSettingBox.MaaPlanSettingBox] = []

            self.Layout = QVBoxLayout(self)
            self.Layout.addWidget(self.pivotArea)
            self.Layout.addWidget(self.stackedWidget)
            self.Layout.setContentsMargins(0, 0, 0, 0)

            self.pivot.currentItemChanged.connect(
                lambda index: self.switch_SettingBox(
                    int(index[3:]), if_chang_pivot=False
                )
            )

            self.show_SettingBox(1)

        def show_SettingBox(self, index) -> None:
            """加载所有子界面"""

            Config.search_plan()

            for name, info in Config.plan_dict.items():
                if info["Type"] == "Maa":
                    self.add_MaaSettingBox(int(name[3:]))

            self.switch_SettingBox(index)

        def switch_SettingBox(self, index: int, if_chang_pivot: bool = True) -> None:
            """切换到指定的子界面"""

            if len(Config.plan_dict) == 0:
                return None

            if index > len(Config.plan_dict):
                return None

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

        def add_MaaPlanSettingBox(self, uid: int) -> None:
            """添加一个MAA设置界面"""

            maa_plan_setting_box = self.MaaPlanSettingBox(uid, self)

            self.script_list.append(maa_plan_setting_box)

            self.stackedWidget.addWidget(self.script_list[-1])

            self.pivot.addItem(routeKey=f"计划_{uid}", text=f"计划 {uid}")

        class MaaPlanSettingBox(HeaderCardWidget):
            """MAA类计划设置界面"""

            def __init__(self, uid: int, parent=None):
                super().__init__(parent)

                self.setObjectName(f"计划_{uid}")
                self.config = Config.plan_dict[f"计划_{uid}"]["Config"]

                self.dashboard = TableWidget(self)
                self.dashboard.setColumnCount(11)
                self.dashboard.setHorizontalHeaderLabels(
                    [
                        "吃理智药",
                        "连战次数",
                        "关卡选择",
                        "备选关卡 - 1",
                        "备选关卡 - 2",
                        "剩余理智关卡",
                    ]
                )
                self.dashboard.setEditTriggers(TableWidget.NoEditTriggers)
                self.dashboard.verticalHeader().setVisible(False)
                for col in range(6):
                    self.dashboard.horizontalHeader().setSectionResizeMode(
                        col, QHeaderView.ResizeMode.Stretch
                    )

                self.viewLayout.addWidget(self.dashboard)
                self.viewLayout.setContentsMargins(3, 0, 3, 3)

                Config.PASSWORD_refreshed.connect(self.load_info)

            def load_info(self):

                self.user_data = Config.plan_dict[self.name]["UserData"]

                self.dashboard.setRowCount(len(self.user_data))

                for name, info in self.user_data.items():

                    config = info["Config"]

                    text_list = []
                    if not config.get(config.Data_IfPassCheck):
                        text_list.append("未通过人工排查")
                    text_list.append(
                        f"今日已代理{config.get(config.Data_ProxyTimes)}次"
                        if Config.server_date().strftime("%Y-%m-%d")
                        == config.get(config.Data_LastProxyDate)
                        else "今日未进行代理"
                    )
                    text_list.append(
                        "本周剿灭已完成"
                        if datetime.strptime(
                            config.get(config.Data_LastAnnihilationDate),
                            "%Y-%m-%d",
                        ).isocalendar()[:2]
                        == Config.server_date().isocalendar()[:2]
                        else "本周剿灭未完成"
                    )

                    button = PrimaryToolButton(FluentIcon.CHEVRON_RIGHT, self)
                    button.setFixedSize(32, 32)
                    button.clicked.connect(partial(self.switch_to.emit, name))

                    self.dashboard.setItem(
                        int(name[3:]) - 1,
                        0,
                        QTableWidgetItem(config.get(config.Info_Name)),
                    )
                    self.dashboard.setItem(
                        int(name[3:]) - 1,
                        1,
                        QTableWidgetItem(config.get(config.Info_Id)),
                    )
                    self.dashboard.setItem(
                        int(name[3:]) - 1,
                        2,
                        QTableWidgetItem(
                            Crypto.AUTO_decryptor(
                                config.get(config.Info_Password),
                                Config.PASSWORD,
                            )
                            if Config.PASSWORD
                            else "******"
                        ),
                    )
                    self.dashboard.setItem(
                        int(name[3:]) - 1,
                        3,
                        QTableWidgetItem(
                            "启用"
                            if config.get(config.Info_Status)
                            and config.get(config.Info_RemainedDay) != 0
                            else "禁用"
                        ),
                    )
                    self.dashboard.setItem(
                        int(name[3:]) - 1,
                        4,
                        QTableWidgetItem(" | ".join(text_list)),
                    )
                    self.dashboard.setItem(
                        int(name[3:]) - 1,
                        5,
                        QTableWidgetItem(str(config.get(config.Info_MedicineNumb))),
                    )
                    self.dashboard.setItem(
                        int(name[3:]) - 1,
                        6,
                        QTableWidgetItem(
                            Config.gameid_dict["ALL"]["text"][
                                Config.gameid_dict["ALL"]["value"].index(
                                    config.get(config.Info_GameId)
                                )
                            ]
                            if config.get(config.Info_GameId)
                            in Config.gameid_dict["ALL"]["value"]
                            else config.get(config.Info_GameId)
                        ),
                    )
                    self.dashboard.setItem(
                        int(name[3:]) - 1,
                        7,
                        QTableWidgetItem(
                            Config.gameid_dict["ALL"]["text"][
                                Config.gameid_dict["ALL"]["value"].index(
                                    config.get(config.Info_GameId_1)
                                )
                            ]
                            if config.get(config.Info_GameId_1)
                            in Config.gameid_dict["ALL"]["value"]
                            else config.get(config.Info_GameId_1)
                        ),
                    )
                    self.dashboard.setItem(
                        int(name[3:]) - 1,
                        8,
                        QTableWidgetItem(
                            Config.gameid_dict["ALL"]["text"][
                                Config.gameid_dict["ALL"]["value"].index(
                                    config.get(config.Info_GameId_2)
                                )
                            ]
                            if config.get(config.Info_GameId_2)
                            in Config.gameid_dict["ALL"]["value"]
                            else config.get(config.Info_GameId_2)
                        ),
                    )
                    self.dashboard.setItem(
                        int(name[3:]) - 1,
                        9,
                        QTableWidgetItem(
                            "不使用"
                            if config.get(config.Info_GameId_Remain) == "-"
                            else (
                                (
                                    Config.gameid_dict["ALL"]["text"][
                                        Config.gameid_dict["ALL"]["value"].index(
                                            config.get(config.Info_GameId_Remain)
                                        )
                                    ]
                                )
                                if config.get(config.Info_GameId_Remain)
                                in Config.gameid_dict["ALL"]["value"]
                                else config.get(config.Info_GameId_Remain)
                            )
                        ),
                    )
                    self.dashboard.setCellWidget(int(name[3:]) - 1, 10, button)
