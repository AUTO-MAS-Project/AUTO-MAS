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
AUTO_MAA历史记录界面
v4.4
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
    TextBrowser,
    CardWidget,
    ComboBox,
    ZhDatePicker,
    SubtitleLabel,
)
from PySide6.QtCore import Signal, QDate
import os
import subprocess
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from typing import List, Dict


from app.core import Config, SoundPlayer
from .Widget import StatefulItemCard, QuantifiedItemCard, QuickExpandGroupCard


class History(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("历史记录")

        self.history_top_bar = self.HistoryTopBar(self)
        self.history_top_bar.search_history.connect(self.reload_history)

        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(0, 0, 11, 0)

        scrollArea = ScrollArea()
        scrollArea.setWidgetResizable(True)
        scrollArea.setContentsMargins(0, 0, 0, 0)
        scrollArea.setStyleSheet("background: transparent; border: none;")
        scrollArea.setWidget(content_widget)

        layout = QVBoxLayout(self)
        layout.addWidget(self.history_top_bar)
        layout.addWidget(scrollArea)

        self.history_card_list = []

    def reload_history(self, mode: str, start_date: QDate, end_date: QDate) -> None:
        """加载历史记录界面"""

        SoundPlayer.play("历史记录查询")

        while self.content_layout.count() > 0:
            item = self.content_layout.takeAt(0)
            if item.spacerItem():
                self.content_layout.removeItem(item.spacerItem())
            elif item.widget():
                item.widget().deleteLater()

        self.history_card_list = []

        history_dict = Config.search_history(
            mode,
            datetime(start_date.year(), start_date.month(), start_date.day()),
            datetime(end_date.year(), end_date.month(), end_date.day()),
        )

        for date, user_dict in history_dict.items():

            self.history_card_list.append(self.HistoryCard(date, user_dict, self))
            self.content_layout.addWidget(self.history_card_list[-1])

        self.content_layout.addStretch(1)

    class HistoryTopBar(CardWidget):
        """历史记录顶部工具栏"""

        search_history = Signal(str, QDate, QDate)

        def __init__(self, parent=None):
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
            self.mode.addItems(["按日合并", "按周合并", "按月合并"])

            self.select_month = PushButton(FluentIcon.TAG, "最近一月")
            self.select_week = PushButton(FluentIcon.TAG, "最近一周")
            self.search = PushButton(FluentIcon.SEARCH, "查询")
            self.select_month.clicked.connect(lambda: self.select_date("month"))
            self.select_week.clicked.connect(lambda: self.select_date("week"))
            self.search.clicked.connect(
                lambda: self.search_history.emit(
                    self.mode.currentText(),
                    self.start_date.getDate(),
                    self.end_date.getDate(),
                )
            )

            Layout.addWidget(self.lable_1)
            Layout.addWidget(self.start_date)
            Layout.addWidget(self.lable_2)
            Layout.addWidget(self.end_date)
            Layout.addWidget(self.mode)
            Layout.addStretch(1)
            Layout.addWidget(self.select_month)
            Layout.addWidget(self.select_week)
            Layout.addWidget(self.search)

        def select_date(self, date: str) -> None:
            """选中最近一段时间并启动查询"""

            server_date = Config.server_date()
            if date == "week":
                begin_date = server_date - timedelta(weeks=1)
            elif date == "month":
                begin_date = server_date - timedelta(days=30)

            self.start_date.setDate(
                QDate(begin_date.year, begin_date.month, begin_date.day)
            )
            self.end_date.setDate(
                QDate(server_date.year, server_date.month, server_date.day)
            )

            self.search.clicked.emit()

    class HistoryCard(QuickExpandGroupCard):
        """历史记录卡片"""

        def __init__(self, date: str, user_dict: Dict[str, List[Path]], parent=None):
            super().__init__(
                FluentIcon.HISTORY, date, f"{date}的历史运行记录与统计信息", parent
            )

            widget = QWidget()
            Layout = QVBoxLayout(widget)
            self.viewLayout.setContentsMargins(0, 0, 0, 0)
            self.viewLayout.setSpacing(0)
            self.addGroupWidget(widget)

            self.user_history_card_list = []

            for user, info in user_dict.items():
                self.user_history_card_list.append(
                    self.UserHistoryCard(user, info, self)
                )
                Layout.addWidget(self.user_history_card_list[-1])

        class UserHistoryCard(HeaderCardWidget):
            """用户历史记录卡片"""

            def __init__(self, name: str, user_history: List[Path], parent=None):
                super().__init__(parent)
                self.setTitle(name)

                self.user_history = user_history

                self.index_card = self.IndexCard(self.user_history, self)
                self.index_card.index_changed.connect(self.update_info)

                self.statistics_card = QHBoxLayout()
                self.log_card = self.LogCard(self)

                self.viewLayout.addWidget(self.index_card)
                self.viewLayout.addLayout(self.statistics_card)
                self.viewLayout.addWidget(self.log_card)
                self.viewLayout.setContentsMargins(0, 0, 0, 0)
                self.viewLayout.setSpacing(0)
                self.viewLayout.setStretch(0, 1)
                self.viewLayout.setStretch(2, 4)

                self.update_info("数据总览")

            def get_statistics(self, mode: str) -> dict:
                """生成GUI相应结构化统计数据"""

                history_info = Config.merge_statistic_info(
                    self.user_history if mode == "数据总览" else [Path(mode)]
                )

                statistics_info = {}

                if "recruit_statistics" in history_info:
                    statistics_info["公招统计"] = list(
                        history_info["recruit_statistics"].items()
                    )

                if "drop_statistics" in history_info:
                    for game_id, drops in history_info["drop_statistics"].items():
                        statistics_info[f"掉落统计：{game_id}"] = list(drops.items())

                if mode == "数据总览" and "error_info" in history_info:
                    statistics_info["报错汇总"] = list(
                        history_info["error_info"].items()
                    )

                return statistics_info

            def update_info(self, index: str) -> None:
                """更新信息"""

                # 移除已有统计信息UI组件
                while self.statistics_card.count() > 0:
                    item = self.statistics_card.takeAt(0)
                    if item.spacerItem():
                        self.statistics_card.removeItem(item.spacerItem())
                    elif item.widget():
                        item.widget().deleteLater()

                if index == "数据总览":

                    for name, item_list in self.get_statistics("数据总览").items():

                        statistics_card = self.StatisticsCard(name, item_list, self)
                        self.statistics_card.addWidget(statistics_card)

                    self.log_card.hide()

                else:

                    single_history = self.get_statistics(index)
                    log_path = Path(index).with_suffix(".log")

                    for name, item_list in single_history.items():
                        statistics_card = self.StatisticsCard(name, item_list, self)
                        self.statistics_card.addWidget(statistics_card)

                    with log_path.open("r", encoding="utf-8") as f:
                        log = f.read()

                    self.log_card.text.setText(log)
                    self.log_card.open_file.clicked.disconnect()
                    self.log_card.open_file.clicked.connect(
                        lambda: os.startfile(log_path)
                    )
                    self.log_card.open_dir.clicked.disconnect()
                    self.log_card.open_dir.clicked.connect(
                        lambda: subprocess.Popen(["explorer", "/select,", log_path])
                    )
                    self.log_card.show()

                self.viewLayout.setStretch(1, self.statistics_card.count())

                self.setMinimumHeight(300)

            class IndexCard(HeaderCardWidget):

                index_changed = Signal(str)

                def __init__(self, history_list: List[Path], parent=None):
                    super().__init__(parent)
                    self.setTitle("记录条目")

                    self.Layout = QVBoxLayout()
                    self.viewLayout.addLayout(self.Layout)
                    self.viewLayout.setContentsMargins(3, 0, 3, 3)

                    self.index_cards: List[StatefulItemCard] = []

                    index_list = Config.merge_statistic_info(history_list)["index"]
                    index_list.insert(0, ["数据总览", "运行", "数据总览"])

                    for index in index_list:

                        self.index_cards.append(StatefulItemCard(index[:2]))
                        self.index_cards[-1].clicked.connect(
                            partial(self.index_changed.emit, str(index[2]))
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
                    self.open_file = PushButton("打开日志文件", self)
                    self.open_file.clicked.connect(lambda: print("打开日志文件"))
                    self.open_dir = PushButton("打开所在目录", self)
                    self.open_dir.clicked.connect(lambda: print("打开所在文件"))

                    Layout = QVBoxLayout()
                    h_layout = QHBoxLayout()
                    h_layout.addWidget(self.open_file)
                    h_layout.addWidget(self.open_dir)
                    Layout.addWidget(self.text)
                    Layout.addLayout(h_layout)
                    self.viewLayout.setContentsMargins(3, 0, 3, 3)
                    self.viewLayout.addLayout(Layout)
