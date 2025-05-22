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
    QVBoxLayout,
    QStackedWidget,
    QHeaderView,
)
from qfluentwidgets import (
    Action,
    FluentIcon,
    MessageBox,
    HeaderCardWidget,
    CommandBar,
    TableWidget,
)
from typing import List
import shutil

from app.core import Config, MainInfoBar, MaaPlanConfig
from app.services import Crypto
from .Widget import (
    ComboBoxMessageBox,
    SpinBoxSetting,
    EditableComboBoxSetting,
    ComboBoxSetting,
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

                self.plan_manager.add_MaaPlanSettingBox(index)
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

        choice = MessageBox("确认", f"确定要删除 {name} 吗？", self.window())
        if choice.exec():

            self.plan_manager.clear_SettingBox()

            shutil.rmtree(Config.plan_dict[name]["Path"])
            Config.change_plan(name, "禁用")
            for i in range(int(name[3:]) + 1, len(Config.plan_dict) + 1):
                if Config.plan_dict[f"计划_{i}"]["Path"].exists():
                    Config.plan_dict[f"计划_{i}"]["Path"].rename(
                        Config.plan_dict[f"计划_{i}"]["Path"].with_name(f"计划_{i-1}")
                    )
                Config.change_plan(f"计划_{i}", f"计划_{i-1}")

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
        Config.change_plan(name, "计划_0")
        Config.plan_dict[f"计划_{index-1}"]["Path"].rename(
            Config.plan_dict[name]["Path"]
        )
        Config.change_plan(f"计划_{index-1}", name)
        Config.plan_dict[name]["Path"].with_name("计划_0").rename(
            Config.plan_dict[f"计划_{index-1}"]["Path"]
        )
        Config.change_plan("计划_0", f"计划_{index-1}")

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
        Config.change_plan(name, "计划_0")
        Config.plan_dict[f"计划_{index+1}"]["Path"].rename(
            Config.plan_dict[name]["Path"]
        )
        Config.change_plan(f"计划_{index+1}", name)
        Config.plan_dict[name]["Path"].with_name("计划_0").rename(
            Config.plan_dict[f"计划_{index+1}"]["Path"]
        )
        Config.change_plan("计划_0", f"计划_{index+1}")

        self.plan_manager.show_SettingBox(index + 1)

        logger.success(f"计划表 {name} 右移成功")
        MainInfoBar.push_info_bar("success", "操作成功", f"右移计划表 {name}", 3000)

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
                    self.add_MaaPlanSettingBox(int(name[3:]))

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
                self.dashboard.setColumnCount(8)
                self.dashboard.setRowCount(6)
                self.dashboard.setHorizontalHeaderLabels(
                    ["全局", "周一", "周二", "周三", "周四", "周五", "周六", "周日"]
                )
                self.dashboard.setVerticalHeaderLabels(
                    [
                        "吃理智药",
                        "连战次数",
                        "关卡选择",
                        "备选 - 1",
                        "备选 - 2",
                        "剩余理智",
                    ]
                )
                self.dashboard.setEditTriggers(TableWidget.NoEditTriggers)
                for col in range(8):
                    self.dashboard.horizontalHeader().setSectionResizeMode(
                        col, QHeaderView.ResizeMode.Stretch
                    )

                self.viewLayout.addWidget(self.dashboard)
                self.viewLayout.setContentsMargins(3, 0, 3, 3)

                for col, (group, name_dict) in enumerate(
                    self.config.config_item_dict.items()
                ):

                    for row, (name, configItem) in enumerate(name_dict.items()):

                        if name == "MedicineNumb":
                            setting_item = SpinBoxSetting(
                                range=(0, 1024),
                                qconfig=self.config,
                                configItem=configItem,
                                parent=self,
                            )
                        elif name == "SeriesNumb":
                            setting_item = ComboBoxSetting(
                                texts=["AUTO", "6", "5", "4", "3", "2", "1", "不选择"],
                                qconfig=self.config,
                                configItem=configItem,
                                parent=self,
                            )
                        elif "GameId" in name:
                            setting_item = EditableComboBoxSetting(
                                value=Config.gameid_dict[group]["value"],
                                texts=Config.gameid_dict[group]["text"],
                                qconfig=self.config,
                                configItem=configItem,
                                parent=self,
                            )

                        self.dashboard.setCellWidget(row, col, setting_item)
