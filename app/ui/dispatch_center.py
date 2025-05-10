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
AUTO_MAA调度中枢界面
v4.3
作者：DLmaster_361
"""

from loguru import logger
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QStackedWidget,
    QHBoxLayout,
)
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    ScrollArea,
    FluentIcon,
    HeaderCardWidget,
    FluentIcon,
    TextBrowser,
    ComboBox,
    SubtitleLabel,
    PushButton,
)
from PySide6.QtGui import QTextCursor
from typing import List, Dict


from app.core import Config, TaskManager, Task, MainInfoBar
from .Widget import StatefulItemCard, ComboBoxMessageBox, PivotArea


class DispatchCenter(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("调度中枢")

        self.multi_button = PushButton(FluentIcon.ADD, "添加任务", self)
        self.multi_button.setToolTip("添加任务")
        self.multi_button.clicked.connect(self.start_multi_task)

        self.power_combox = ComboBox()
        self.power_combox.addItem("无动作", userData="NoAction")
        self.power_combox.addItem("退出软件", userData="KillSelf")
        self.power_combox.addItem("睡眠", userData="Sleep")
        self.power_combox.addItem("休眠", userData="Hibernate")
        self.power_combox.addItem("关机", userData="Shutdown")
        self.power_combox.setCurrentText("无动作")
        self.power_combox.currentIndexChanged.connect(self.set_power_sign)

        self.pivotArea = PivotArea(self)
        self.pivot = self.pivotArea.pivot

        self.stackedWidget = QStackedWidget(self)
        self.stackedWidget.setContentsMargins(0, 0, 0, 0)
        self.stackedWidget.setStyleSheet("background: transparent; border: none;")

        self.script_list: Dict[str, DispatchCenter.DispatchBox] = {}

        dispatch_box = self.DispatchBox("主调度台", self)
        self.script_list["主调度台"] = dispatch_box
        self.stackedWidget.addWidget(self.script_list["主调度台"])
        self.pivot.addItem(
            routeKey="主调度台",
            text="主调度台",
            onClick=self.update_top_bar,
            icon=FluentIcon.CAFE,
        )

        h_layout = QHBoxLayout()
        h_layout.addWidget(self.multi_button)
        h_layout.addWidget(self.pivotArea)
        h_layout.addWidget(BodyLabel("全部完成后", self))
        h_layout.addWidget(self.power_combox)
        h_layout.setContentsMargins(11, 5, 11, 0)

        self.Layout = QVBoxLayout(self)
        self.Layout.addLayout(h_layout)
        self.Layout.addWidget(self.stackedWidget)
        self.Layout.setContentsMargins(0, 0, 0, 0)

        self.pivot.currentItemChanged.connect(
            lambda index: self.stackedWidget.setCurrentWidget(self.script_list[index])
        )

    def add_board(self, task: Task) -> None:
        """添加一个调度台界面"""

        dispatch_box = self.DispatchBox(task.name, self)

        dispatch_box.top_bar.main_button.clicked.connect(
            lambda: TaskManager.stop_task(task.name)
        )

        task.create_task_list.connect(dispatch_box.info.task.create_task)
        task.create_user_list.connect(dispatch_box.info.user.create_user)
        task.update_task_list.connect(dispatch_box.info.task.update_task)
        task.update_user_list.connect(dispatch_box.info.user.update_user)
        task.update_log_text.connect(dispatch_box.info.log_text.text.setText)
        task.accomplish.connect(lambda: self.del_board(f"调度台_{task.name}"))

        self.script_list[f"调度台_{task.name}"] = dispatch_box

        self.stackedWidget.addWidget(self.script_list[f"调度台_{task.name}"])

        self.pivot.addItem(routeKey=f"调度台_{task.name}", text=f"调度台 {task.name}")

    def del_board(self, name: str) -> None:
        """删除指定子界面"""

        self.pivot.setCurrentItem("主调度台")
        self.stackedWidget.removeWidget(self.script_list[name])
        self.script_list[name].deleteLater()
        self.pivot.removeWidget(name)

    def connect_main_board(self, task: Task) -> None:
        """连接主调度台"""

        self.script_list["主调度台"].top_bar.Lable.setText(
            f"{task.name} - {task.mode.replace("_主调度台","")}模式"
        )
        self.script_list["主调度台"].top_bar.Lable.show()
        self.script_list["主调度台"].top_bar.object.hide()
        self.script_list["主调度台"].top_bar.mode.hide()
        self.script_list["主调度台"].top_bar.main_button.clicked.disconnect()
        self.script_list["主调度台"].top_bar.main_button.setText("中止任务")
        self.script_list["主调度台"].top_bar.main_button.clicked.connect(
            lambda: TaskManager.stop_task(task.name)
        )
        task.create_task_list.connect(
            self.script_list["主调度台"].info.task.create_task
        )
        task.create_user_list.connect(
            self.script_list["主调度台"].info.user.create_user
        )
        task.update_task_list.connect(
            self.script_list["主调度台"].info.task.update_task
        )
        task.update_user_list.connect(
            self.script_list["主调度台"].info.user.update_user
        )
        task.update_log_text.connect(
            self.script_list["主调度台"].info.log_text.text.setText
        )
        task.accomplish.connect(
            lambda logs: self.disconnect_main_board(task.name, logs)
        )

    def disconnect_main_board(self, name: str, logs: list) -> None:
        """断开主调度台"""

        self.script_list["主调度台"].top_bar.Lable.hide()
        self.script_list["主调度台"].top_bar.object.show()
        self.script_list["主调度台"].top_bar.mode.show()
        self.script_list["主调度台"].top_bar.main_button.clicked.disconnect()
        self.script_list["主调度台"].top_bar.main_button.setText("开始任务")
        self.script_list["主调度台"].top_bar.main_button.clicked.connect(
            self.script_list["主调度台"].top_bar.start_main_task
        )
        if len(logs) > 0:
            history = ""
            for log in logs:
                history += (
                    f"任务名称：{log[0]}，{log[1]["History"].replace("\n","\n    ")}\n"
                )
            self.script_list["主调度台"].info.log_text.text.setText(history)
        else:
            self.script_list["主调度台"].info.log_text.text.setText("没有任务被执行")

    def update_top_bar(self):
        """更新顶栏"""

        self.script_list["主调度台"].top_bar.object.clear()

        for name, info in Config.queue_dict.items():
            self.script_list["主调度台"].top_bar.object.addItem(
                (
                    "队列"
                    if info["Config"].get(info["Config"].queueSet_Name) == ""
                    else f"队列 - {info["Config"].get(info["Config"].queueSet_Name)}"
                ),
                userData=name,
            )

        for name, info in Config.member_dict.items():
            self.script_list["主调度台"].top_bar.object.addItem(
                (
                    f"实例 - {info['Type']}"
                    if info["Config"].get(info["Config"].MaaSet_Name) == ""
                    else f"实例 - {info['Type']} - {info["Config"].get(info["Config"].MaaSet_Name)}"
                ),
                userData=name,
            )

        if len(Config.queue_dict) == 1:
            self.script_list["主调度台"].top_bar.object.setCurrentIndex(0)
        elif len(Config.member_dict) == 1:
            self.script_list["主调度台"].top_bar.object.setCurrentIndex(
                len(Config.queue_dict)
            )
        else:
            self.script_list["主调度台"].top_bar.object.setCurrentIndex(-1)

        self.script_list["主调度台"].top_bar.mode.clear()
        self.script_list["主调度台"].top_bar.mode.addItems(["自动代理", "人工排查"])
        self.script_list["主调度台"].top_bar.mode.setCurrentIndex(0)

    def update_power_sign(self) -> None:
        """更新电源设置"""

        mode_book = {
            "NoAction": "无动作",
            "KillSelf": "退出软件",
            "Sleep": "睡眠",
            "Hibernate": "休眠",
            "Shutdown": "关机",
        }
        self.power_combox.currentIndexChanged.disconnect()
        self.power_combox.setCurrentText(mode_book[Config.power_sign])
        self.power_combox.currentIndexChanged.connect(self.set_power_sign)

    def set_power_sign(self) -> None:
        """设置所有任务完成后动作"""

        if not Config.running_list:

            self.power_combox.currentIndexChanged.disconnect()
            self.power_combox.setCurrentText("无动作")
            self.power_combox.currentIndexChanged.connect(self.set_power_sign)
            logger.warning("没有正在运行的任务，无法设置任务完成后动作")
            MainInfoBar.push_info_bar(
                "warning",
                "没有正在运行的任务",
                "无法设置任务完成后动作",
                5000,
            )

        else:

            Config.set_power_sign(self.power_combox.currentData())

    def start_multi_task(self) -> None:
        """开始任务"""

        # 获取所有可用的队列和实例
        text_list = []
        data_list = []
        for name, info in Config.queue_dict.items():
            if name in Config.running_list:
                continue
            text_list.append(
                "队列"
                if info["Config"].get(info["Config"].queueSet_Name) == ""
                else f"队列 - {info["Config"].get(info["Config"].queueSet_Name)}"
            )
            data_list.append(name)

        for name, info in Config.member_dict.items():
            if name in Config.running_list:
                continue
            text_list.append(
                f"实例 - {info['Type']}"
                if info["Config"].get(info["Config"].MaaSet_Name) == ""
                else f"实例 - {info['Type']} - {info["Config"].get(info["Config"].MaaSet_Name)}"
            )
            data_list.append(name)

        choice = ComboBoxMessageBox(
            self.window(),
            "选择一个对象以添加相应多开任务",
            ["选择调度对象"],
            [text_list],
            [data_list],
        )

        if choice.exec() and choice.input[0].currentIndex() != -1:

            if choice.input[0].currentData() in Config.running_list:
                logger.warning(f"任务已存在：{choice.input[0].currentData()}")
                MainInfoBar.push_info_bar(
                    "warning", "任务已存在", choice.input[0].currentData(), 5000
                )
                return None

            if "调度队列" in choice.input[0].currentData():

                logger.info(f"用户添加任务：{choice.input[0].currentData()}")
                TaskManager.add_task(
                    "自动代理_新调度台",
                    choice.input[0].currentData(),
                    Config.queue_dict[choice.input[0].currentData()]["Config"].toDict(),
                )

            elif "脚本" in choice.input[0].currentData():

                if Config.member_dict[choice.input[0].currentData()]["Type"] == "Maa":

                    logger.info(f"用户添加任务：{choice.input[0].currentData()}")
                    TaskManager.add_task(
                        "自动代理_新调度台",
                        f"自定义队列 - {choice.input[0].currentData()}",
                        {"Queue": {"Member_1": choice.input[0].currentData()}},
                    )

    class DispatchBox(QWidget):

        def __init__(self, name: str, parent=None):
            super().__init__(parent)

            self.setObjectName(name)

            layout = QVBoxLayout()

            scrollArea = ScrollArea()
            scrollArea.setWidgetResizable(True)
            scrollArea.setContentsMargins(0, 0, 0, 0)
            scrollArea.setStyleSheet("background: transparent; border: none;")

            content_widget = QWidget()
            content_layout = QVBoxLayout(content_widget)

            self.top_bar = self.DispatchTopBar(self, name)
            self.info = self.DispatchInfoCard(self)

            content_layout.addWidget(self.top_bar)
            content_layout.addWidget(self.info)

            scrollArea.setWidget(content_widget)

            layout.addWidget(scrollArea)

            self.setLayout(layout)

        class DispatchTopBar(CardWidget):

            def __init__(self, parent=None, name: str = None):
                super().__init__(parent)

                Layout = QHBoxLayout(self)

                if name == "主调度台":

                    self.Lable = SubtitleLabel("", self)
                    self.Lable.hide()
                    self.object = ComboBox()
                    self.object.setPlaceholderText("请选择调度对象")
                    self.mode = ComboBox()
                    self.mode.setPlaceholderText("请选择调度模式")

                    self.main_button = PushButton("开始任务")
                    self.main_button.clicked.connect(self.start_main_task)

                    Layout.addWidget(self.Lable)
                    Layout.addWidget(self.object)
                    Layout.addWidget(self.mode)
                    Layout.addStretch(1)
                    Layout.addWidget(self.main_button)

                else:

                    self.Lable = SubtitleLabel(name, self)
                    self.main_button = PushButton("中止任务")

                    Layout.addWidget(self.Lable)
                    Layout.addStretch(1)
                    Layout.addWidget(self.main_button)

            def start_main_task(self):
                """开始任务"""

                if self.object.currentIndex() == -1:
                    logger.warning("未选择调度对象")
                    MainInfoBar.push_info_bar(
                        "warning", "未选择调度对象", "请选择后再开始任务", 5000
                    )
                    return None

                if self.mode.currentIndex() == -1:
                    logger.warning("未选择调度模式")
                    MainInfoBar.push_info_bar(
                        "warning", "未选择调度模式", "请选择后再开始任务", 5000
                    )
                    return None

                if self.object.currentData() in Config.running_list:
                    logger.warning(f"任务已存在：{self.object.currentData()}")
                    MainInfoBar.push_info_bar(
                        "warning", "任务已存在", self.object.currentData(), 5000
                    )
                    return None

                if "调度队列" in self.object.currentData():

                    logger.info(f"用户添加任务：{self.object.currentData()}")
                    TaskManager.add_task(
                        f"{self.mode.currentText()}_主调度台",
                        self.object.currentData(),
                        Config.queue_dict[self.object.currentData()]["Config"].toDict(),
                    )

                elif "脚本" in self.object.currentData():

                    if Config.member_dict[self.object.currentData()]["Type"] == "Maa":

                        logger.info(f"用户添加任务：{self.object.currentData()}")
                        TaskManager.add_task(
                            f"{self.mode.currentText()}_主调度台",
                            "自定义队列",
                            {"Queue": {"Member_1": self.object.currentData()}},
                        )

        class DispatchInfoCard(HeaderCardWidget):

            def __init__(self, parent=None):
                super().__init__(parent)

                self.setTitle("调度信息")

                self.task = self.TaskInfoCard(self)
                self.user = self.UserInfoCard(self)
                self.log_text = self.LogCard(self)

                self.viewLayout.addWidget(self.task)
                self.viewLayout.addWidget(self.user)
                self.viewLayout.addWidget(self.log_text)

                self.viewLayout.setStretch(0, 1)
                self.viewLayout.setStretch(1, 1)
                self.viewLayout.setStretch(2, 5)

            def update_board(self, task_list: list, user_list: list, log: str):
                """更新调度信息"""

                self.task.update_task(task_list)
                self.user.update_user(user_list)
                self.log_text.text.setText(log)

            class TaskInfoCard(HeaderCardWidget):

                def __init__(self, parent=None):
                    super().__init__(parent)
                    self.setTitle("任务队列")

                    self.Layout = QVBoxLayout()
                    self.viewLayout.addLayout(self.Layout)
                    self.viewLayout.setContentsMargins(3, 0, 3, 3)

                    self.task_cards: List[StatefulItemCard] = []

                def create_task(self, task_list: list):
                    """创建任务队列"""

                    while self.Layout.count() > 0:
                        item = self.Layout.takeAt(0)
                        if item.spacerItem():
                            self.Layout.removeItem(item.spacerItem())
                        elif item.widget():
                            item.widget().deleteLater()

                    self.task_cards = []

                    for task in task_list:

                        self.task_cards.append(StatefulItemCard(task))
                        self.Layout.addWidget(self.task_cards[-1])

                    self.Layout.addStretch(1)

                def update_task(self, task_list: list):
                    """更新任务队列"""

                    for i in range(len(task_list)):

                        self.task_cards[i].update_status(task_list[i][1])

            class UserInfoCard(HeaderCardWidget):

                def __init__(self, parent=None):
                    super().__init__(parent)
                    self.setTitle("用户队列")

                    self.Layout = QVBoxLayout()
                    self.viewLayout.addLayout(self.Layout)
                    self.viewLayout.setContentsMargins(3, 0, 3, 3)

                    self.user_cards: List[StatefulItemCard] = []

                def create_user(self, user_list: list):
                    """创建用户队列"""

                    while self.Layout.count() > 0:
                        item = self.Layout.takeAt(0)
                        if item.spacerItem():
                            self.Layout.removeItem(item.spacerItem())
                        elif item.widget():
                            item.widget().deleteLater()

                    self.user_cards = []

                    for user in user_list:

                        self.user_cards.append(StatefulItemCard(user))
                        self.Layout.addWidget(self.user_cards[-1])

                    self.Layout.addStretch(1)

                def update_user(self, user_list: list):
                    """更新用户队列"""

                    for i in range(len(user_list)):

                        self.user_cards[i].Label.setText(user_list[i][0])
                        self.user_cards[i].update_status(user_list[i][1])

            class LogCard(HeaderCardWidget):

                def __init__(self, parent=None):
                    super().__init__(parent)
                    self.setTitle("日志")

                    self.text = TextBrowser()
                    self.viewLayout.setContentsMargins(3, 0, 3, 3)
                    self.viewLayout.addWidget(self.text)

                    self.text.textChanged.connect(self.to_end)

                def to_end(self):
                    """滚动到底部"""

                    self.text.moveCursor(QTextCursor.End)
                    self.text.ensureCursorVisible()
