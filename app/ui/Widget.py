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
AUTO_MAA组件
v4.2
作者：DLmaster_361
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from qfluentwidgets import (
    LineEdit,
    PasswordLineEdit,
    MessageBoxBase,
    SubtitleLabel,
    SettingCard,
    SpinBox,
    FluentIconBase,
    Signal,
    ComboBox,
    qconfig,
    ConfigItem,
)

from typing import Union


class InputMessageBox(MessageBoxBase):
    """输入对话框"""

    def __init__(self, parent, title: str, content: str, mode: str, list: list = None):
        super().__init__(parent)
        self.title = SubtitleLabel(title)

        if mode == "明文":
            self.input = LineEdit()
            self.input.setClearButtonEnabled(True)
        elif mode == "密码":
            self.input = PasswordLineEdit()
        elif mode == "选择":
            self.input = ComboBox()
            self.input.addItems(list)
            self.input.setCurrentIndex(-1)

        self.input.setPlaceholderText(content)

        # 将组件添加到布局中
        self.viewLayout.addWidget(self.title)
        self.viewLayout.addWidget(self.input)


class LineEditSettingCard(SettingCard):
    """Setting card with switch button"""

    textChanged = Signal(str)

    def __init__(
        self,
        text,
        icon: Union[str, QIcon, FluentIconBase],
        title,
        content=None,
        configItem: ConfigItem = None,
        parent=None,
    ):

        super().__init__(icon, title, content, parent)
        self.configItem = configItem
        self.LineEdit = LineEdit(self)
        self.LineEdit.setMinimumWidth(250)
        self.LineEdit.setPlaceholderText(text)

        if configItem:
            self.setValue(qconfig.get(configItem))
            configItem.valueChanged.connect(self.setValue)

        self.hBoxLayout.addWidget(self.LineEdit, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.LineEdit.textChanged.connect(self.__textChanged)

    def __textChanged(self, content: str):
        self.setValue(content)
        self.textChanged.emit(content)

    def setValue(self, content: str):
        if self.configItem:
            qconfig.set(self.configItem, content)

        self.LineEdit.setText(content)


class SpinBoxSettingCard(SettingCard):

    textChanged = Signal(int)

    def __init__(
        self,
        range: tuple[int, int],
        icon: Union[str, QIcon, FluentIconBase],
        title,
        content=None,
        configItem: ConfigItem = None,
        parent=None,
    ):

        super().__init__(icon, title, content, parent)
        self.configItem = configItem
        self.SpinBox = SpinBox(self)
        self.SpinBox.setRange(range[0], range[1])
        self.SpinBox.setMinimumWidth(150)

        if configItem:
            self.setValue(qconfig.get(configItem))
            configItem.valueChanged.connect(self.setValue)

        self.hBoxLayout.addWidget(self.SpinBox, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.SpinBox.valueChanged.connect(self.__valueChanged)

    def __valueChanged(self, value: int):
        self.setValue(value)
        self.textChanged.emit(value)

    def setValue(self, value: int):
        if self.configItem:
            qconfig.set(self.configItem, value)

        self.SpinBox.setValue(value)
