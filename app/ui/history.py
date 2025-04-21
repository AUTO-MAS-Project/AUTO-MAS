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
AUTO_MAA历史记录界面
v4.3
作者：DLmaster_361
"""

from loguru import logger
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
)
from qfluentwidgets import (
    ScrollArea,
    FluentIcon,
    HeaderCardWidget,
    PushButton,
    ExpandGroupSettingCard,
    TextBrowser,
    CardWidget,
    ComboBox,
    ZhDatePicker,
    SubtitleLabel,
)
from PySide6.QtCore import Signal, QDate
import os
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import List


from app.core import Config
from .Widget import StatefulItemCard, QuantifiedItemCard


class History(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("历史记录")

        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.history_top_bar = self.HistoryTopBar(self)

        self.history_top_bar.search_history.connect(self.reload_history)

        scrollArea = ScrollArea()
        scrollArea.setWidgetResizable(True)
        scrollArea.setWidget(content_widget)
        layout = QVBoxLayout()
        layout.addWidget(self.history_top_bar)
        layout.addWidget(scrollArea)
        self.setLayout(layout)

        self.history_card_list = []

    def reload_history(self, start_date: QDate, end_date: QDate, mode: str) -> None:
        """加载历史记录界面"""

        while self.content_layout.count() > 0:
            item = self.content_layout.takeAt(0)
            if item.spacerItem():
                self.content_layout.removeItem(item.spacerItem())
            elif item.widget():
                item.widget().deleteLater()

        self.history_card_list = []

        history_dict = Config.search_history()

        selected_history = filter(
            lambda item: datetime(
                start_date.year(), start_date.month(), start_date.day()
            )
            <= datetime.strptime(item[0], "%Y年 %m月 %d日")
            <= datetime(end_date.year(), end_date.month(), end_date.day()),
            history_dict.items(),
        )
        for date, user_list in selected_history:

            self.history_card_list.append(HistoryCard(date, user_list, self))
            self.content_layout.addWidget(self.history_card_list[-1])

        self.content_layout.addStretch(1)

    class HistoryTopBar(CardWidget):
        """历史记录顶部工具栏"""

        search_history = Signal(QDate, QDate, str)

        def __init__(self, parent=None, name: str = None):
            super().__init__(parent)

            Layout = QHBoxLayout(self)

            self.lable_1 = SubtitleLabel("查询范围：")
            self.start_date = ZhDatePicker()
            self.start_date.setDate(QDate(2019, 5, 1))
            self.lable_2 = SubtitleLabel("→")
            self.end_date = ZhDatePicker()
            server_date = Config.server_date()
            self.end_date.setDate(
                QDate(server_date.year, server_date.month, server_date.day)
            )
            self.mode = ComboBox()
            self.mode.setPlaceholderText("请选择查询模式")
            self.mode.addItems(["按日期分类"])

            self.button = PushButton(FluentIcon.SEARCH, "查询")
            self.button.clicked.connect(
                lambda: self.search_history.emit(
                    self.start_date.getDate(),
                    self.end_date.getDate(),
                    self.mode.currentText(),
                )
            )

            Layout.addWidget(self.lable_1)
            Layout.addWidget(self.start_date)
            Layout.addWidget(self.lable_2)
            Layout.addWidget(self.end_date)
            Layout.addWidget(self.mode)
            Layout.addStretch(1)
            Layout.addWidget(self.button)


class HistoryCard(ExpandGroupSettingCard):

    def __init__(self, date: str, user_list: List[Path], parent=None):
        super().__init__(
            FluentIcon.HISTORY, date, f"{date}的历史运行记录与统计信息", parent
        )

        widget = QWidget()
        Layout = QVBoxLayout(widget)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.viewLayout.setSpacing(0)
        self.addGroupWidget(widget)

        self.user_history_card_list = []

        for user_path in user_list:

            self.user_history_card_list.append(self.UserHistoryCard(user_path, self))
            Layout.addWidget(self.user_history_card_list[-1])

    class UserHistoryCard(HeaderCardWidget):

        def __init__(
            self,
            user_history_path: Path,
            parent=None,
        ):
            super().__init__(parent)

            self.setTitle(user_history_path.name.replace(".json", ""))

            self.user_history_path = user_history_path
            self.main_history = Config.load_maa_logs("总览", user_history_path)

            self.index_card = self.IndexCard(self.main_history["条目索引"], self)
            self.statistics_card = QHBoxLayout()
            self.log_card = self.LogCard(self)

            self.index_card.index_changed.connect(self.update_info)

            self.viewLayout.addWidget(self.index_card)
            self.viewLayout.addLayout(self.statistics_card)
            self.viewLayout.addWidget(self.log_card)
            self.viewLayout.setContentsMargins(0, 0, 0, 0)
            self.viewLayout.setSpacing(0)
            self.viewLayout.setStretch(0, 1)
            self.viewLayout.setStretch(2, 4)

            self.update_info("数据总览")

        def update_info(self, index: str) -> None:
            """更新信息"""

            if index == "数据总览":

                while self.statistics_card.count() > 0:
                    item = self.statistics_card.takeAt(0)
                    if item.spacerItem():
                        self.statistics_card.removeItem(item.spacerItem())
                    elif item.widget():
                        item.widget().deleteLater()

                for name, item_list in self.main_history["统计数据"].items():

                    statistics_card = self.StatisticsCard(name, item_list, self)
                    self.statistics_card.addWidget(statistics_card)

                self.log_card.hide()

            else:

                single_history = Config.load_maa_logs(
                    "单项",
                    self.user_history_path.with_suffix("")
                    / f"{index.replace(":","-")}.json",
                )

                while self.statistics_card.count() > 0:
                    item = self.statistics_card.takeAt(0)
                    if item.spacerItem():
                        self.statistics_card.removeItem(item.spacerItem())
                    elif item.widget():
                        item.widget().deleteLater()

                for name, item_list in single_history["统计数据"].items():

                    statistics_card = self.StatisticsCard(name, item_list, self)
                    self.statistics_card.addWidget(statistics_card)

                self.log_card.text.setText(single_history["日志信息"])
                self.log_card.button.clicked.disconnect()
                self.log_card.button.clicked.connect(
                    lambda: os.startfile(
                        self.user_history_path.with_suffix("")
                        / f"{index.replace(":","-")}.log"
                    )
                )
                self.log_card.show()

            self.viewLayout.setStretch(1, self.statistics_card.count())

            self.setMinimumHeight(300)

        class IndexCard(HeaderCardWidget):

            index_changed = Signal(str)

            def __init__(self, index_list: list, parent=None):
                super().__init__(parent)
                self.setTitle("记录条目")

                self.Layout = QVBoxLayout()
                self.viewLayout.addLayout(self.Layout)
                self.viewLayout.setContentsMargins(3, 0, 3, 3)

                self.index_cards: List[StatefulItemCard] = []

                for index in index_list:

                    self.index_cards.append(StatefulItemCard(index))
                    self.index_cards[-1].clicked.connect(
                        partial(self.index_changed.emit, index[0])
                    )
                    self.Layout.addWidget(self.index_cards[-1])

                self.Layout.addStretch(1)

        class StatisticsCard(HeaderCardWidget):

            def __init__(self, name: str, item_list: list, parent=None):
                super().__init__(parent)
                self.setTitle(name)

                self.Layout = QVBoxLayout()
                self.viewLayout.addLayout(self.Layout)
                self.viewLayout.setContentsMargins(3, 0, 3, 3)

                self.item_cards: List[QuantifiedItemCard] = []

                for item in item_list:

                    self.item_cards.append(QuantifiedItemCard(item))
                    self.Layout.addWidget(self.item_cards[-1])

                if len(item_list) == 0:
                    self.Layout.addWidget(QuantifiedItemCard(["暂无记录", ""]))

                self.Layout.addStretch(1)

        class LogCard(HeaderCardWidget):

            def __init__(self, parent=None):
                super().__init__(parent)
                self.setTitle("日志")

                self.text = TextBrowser(self)
                self.button = PushButton("打开日志文件", self)
                self.button.clicked.connect(lambda: print("打开日志文件"))

                Layout = QVBoxLayout()
                Layout.addWidget(self.text)
                Layout.addWidget(self.button)
                self.viewLayout.setContentsMargins(3, 0, 3, 3)
                self.viewLayout.addLayout(Layout)
