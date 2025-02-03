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
AUTO_MAA调度中枢界面
v4.2
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
    CardWidget,
    IconWidget,
    BodyLabel,
    Pivot,
    ScrollArea,
    FluentIcon,
    HeaderCardWidget,
    FluentIcon,
    TextBrowser,
    ComboBox,
    SubtitleLabel,
    PushButton,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from typing import List, Dict
import json


from app.core import Config, Task_manager, Task, MainInfoBar


class DispatchCenter(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("调度中枢")

        self.pivot = Pivot(self)
        self.stackedWidget = QStackedWidget(self)
        self.Layout = QVBoxLayout(self)

        self.script_list: Dict[str, DispatchBox] = {}

        dispatch_box = DispatchBox("主调度台", self)
        self.script_list["主调度台"] = dispatch_box
        self.stackedWidget.addWidget(self.script_list["主调度台"])
        self.pivot.addItem(
            routeKey="主调度台",
            text="主调度台",
            onClick=self.update_top_bar,
            icon=FluentIcon.CAFE,
        )

        self.Layout.addWidget(self.pivot, 0, Qt.AlignHCenter)
        self.Layout.addWidget(self.stackedWidget)
        self.Layout.setContentsMargins(0, 0, 0, 0)

        self.pivot.currentItemChanged.connect(
            lambda index: self.stackedWidget.setCurrentWidget(self.script_list[index])
        )

    def add_board(self, task: Task) -> None:
        """添加一个调度台界面"""

        dispatch_box = DispatchBox(task.name, self)

        dispatch_box.top_bar.button.clicked.connect(
            lambda: Task_manager.stop_task(task.name)
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
        self.script_list["主调度台"].top_bar.button.clicked.disconnect()
        self.script_list["主调度台"].top_bar.button.setText("中止任务")
        self.script_list["主调度台"].top_bar.button.clicked.connect(
            lambda: Task_manager.stop_task(task.name)
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
        task.accomplish.connect(lambda: self.disconnect_main_board(task.name))

    def disconnect_main_board(self, name: str) -> None:
        """断开主调度台"""

        self.script_list["主调度台"].top_bar.Lable.hide()
        self.script_list["主调度台"].top_bar.object.show()
        self.script_list["主调度台"].top_bar.mode.show()
        self.script_list["主调度台"].top_bar.button.clicked.disconnect()
        self.script_list["主调度台"].top_bar.button.setText("开始任务")
        self.script_list["主调度台"].top_bar.button.clicked.connect(
            self.script_list["主调度台"].top_bar.start_task
        )
        self.script_list["主调度台"].info.log_text.text.setText(
            Config.get_history(name)["History"]
        )

    def update_top_bar(self):
        """更新顶栏"""

        list = []

        if (Config.app_path / "config/QueueConfig").exists():
            for json_file in (Config.app_path / "config/QueueConfig").glob("*.json"):
                list.append(f"队列 - {json_file.stem}")

        if (Config.app_path / "config/MaaConfig").exists():
            for subdir in (Config.app_path / "config/MaaConfig").iterdir():
                if subdir.is_dir():
                    list.append(f"实例 - Maa - {subdir.name}")

        self.script_list["主调度台"].top_bar.object.clear()
        self.script_list["主调度台"].top_bar.object.addItems(list)
        self.script_list["主调度台"].top_bar.object.setCurrentIndex(-1)
        self.script_list["主调度台"].top_bar.mode.setCurrentIndex(-1)


class DispatchBox(QWidget):

    def __init__(self, name: str, parent=None):
        super().__init__(parent)

        self.setObjectName(name)

        layout = QVBoxLayout()

        scrollArea = ScrollArea()
        scrollArea.setWidgetResizable(True)

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
                self.mode.addItems(["自动代理", "人工排查"])
                self.mode.setPlaceholderText("请选择调度模式")

                self.button = PushButton("开始任务")
                self.button.clicked.connect(self.start_task)

                Layout.addWidget(self.Lable)
                Layout.addWidget(self.object)
                Layout.addWidget(self.mode)
                Layout.addStretch(1)
                Layout.addWidget(self.button)

            else:

                self.Lable = SubtitleLabel(name, self)
                self.button = PushButton("中止任务")

                Layout.addWidget(self.Lable)
                Layout.addStretch(1)
                Layout.addWidget(self.button)

        def start_task(self):
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

            name = self.object.currentText().split(" - ")[-1]

            if name in Config.running_list:
                logger.warning(f"任务已存在：{name}")
                MainInfoBar.push_info_bar("warning", "任务已存在", name, 5000)
                return None

            if self.object.currentText().split(" - ")[0] == "队列":

                with (Config.app_path / f"config/QueueConfig/{name}.json").open(
                    mode="r", encoding="utf-8"
                ) as f:
                    info = json.load(f)

                logger.info(f"用户添加任务：{name}")
                Task_manager.add_task(f"{self.mode.currentText()}_主调度台", name, info)

            elif self.object.currentText().split(" - ")[0] == "实例":

                if self.object.currentText().split(" - ")[1] == "Maa":

                    info = {"Queue": {"Member_1": name}}

                    logger.info(f"用户添加任务：{name}")
                    Task_manager.add_task(
                        f"{self.mode.currentText()}_主调度台", "用户自定义队列", info
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

                self.task_cards: List[ItemCard] = []

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

                    self.task_cards.append(ItemCard(task))
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

                self.user_cards: List[ItemCard] = []

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

                    self.user_cards.append(ItemCard(user))
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


class ItemCard(CardWidget):

    def __init__(self, task_item: list, parent=None):
        super().__init__(parent)

        self.Layout = QHBoxLayout(self)

        self.Label = BodyLabel(task_item[0], self)
        self.icon = IconWidget(FluentIcon.MORE, self)
        self.icon.setFixedSize(16, 16)
        self.update_status(task_item[1])

        self.Layout.addWidget(self.icon)
        self.Layout.addWidget(self.Label)
        self.Layout.addStretch(1)

    def update_status(self, status: str):

        if status == "完成":
            self.icon.setIcon(FluentIcon.ACCEPT)
            self.Label.setTextColor("#0eb840", "#0eb840")
        elif status == "等待":
            self.icon.setIcon(FluentIcon.MORE)
            self.Label.setTextColor("#7397ab", "#7397ab")
        elif status == "运行":
            self.icon.setIcon(FluentIcon.PLAY)
            self.Label.setTextColor("#2e4e7e", "#2e4e7e")
        elif status == "跳过":
            self.icon.setIcon(FluentIcon.REMOVE)
            self.Label.setTextColor("#606060", "#d2d2d2")
        elif status == "异常":
            self.icon.setIcon(FluentIcon.CLOSE)
            self.Label.setTextColor("#ff2121", "#ff2121")
