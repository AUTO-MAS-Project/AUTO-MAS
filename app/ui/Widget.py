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

from PySide6.QtCore import Qt, QTime
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget, QHBoxLayout
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
    CheckBox,
    IconWidget,
    FluentIcon,
    CardWidget,
    BodyLabel,
    qconfig,
    ConfigItem,
    TimeEdit,
    OptionsConfigItem,
)
from typing import Union, List

from app.services import Crypto


class LineEditMessageBox(MessageBoxBase):
    """输入对话框"""

    def __init__(self, parent, title: str, content: str, mode: str):
        super().__init__(parent)
        self.title = SubtitleLabel(title)

        if mode == "明文":
            self.input = LineEdit()
            self.input.setClearButtonEnabled(True)
        elif mode == "密码":
            self.input = PasswordLineEdit()

        self.input.setPlaceholderText(content)

        # 将组件添加到布局中
        self.viewLayout.addWidget(self.title)
        self.viewLayout.addWidget(self.input)


class ComboBoxMessageBox(MessageBoxBase):
    """选择对话框"""

    def __init__(self, parent, title: str, content: List[str], list: List[List[str]]):
        super().__init__(parent)
        self.title = SubtitleLabel(title)

        Widget = QWidget()
        Layout = QHBoxLayout(Widget)

        self.input: List[ComboBox] = []

        for i in range(len(content)):

            self.input.append(ComboBox())
            self.input[i].addItems(list[i])
            self.input[i].setCurrentIndex(-1)
            self.input[i].setPlaceholderText(content[i])
            Layout.addWidget(self.input[i])

        # 将组件添加到布局中
        self.viewLayout.addWidget(self.title)
        self.viewLayout.addWidget(Widget)


class LineEditSettingCard(SettingCard):
    """Setting card with LineEdit"""

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


class PasswordLineEditSettingCard(SettingCard):
    """Setting card with PasswordLineEdit"""

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
        self.LineEdit = PasswordLineEdit(self)
        self.LineEdit.setMinimumWidth(250)
        self.LineEdit.setPlaceholderText(text)

        if configItem:
            self.setValue(qconfig.get(configItem))
            configItem.valueChanged.connect(self.setValue)

        self.hBoxLayout.addWidget(self.LineEdit, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.LineEdit.textChanged.connect(self.__textChanged)

    def __textChanged(self, content: str):
        self.setValue(Crypto.win_encryptor(content))
        self.textChanged.emit(content)

    def setValue(self, content: str):
        if self.configItem:
            qconfig.set(self.configItem, content)

        self.LineEdit.setText(Crypto.win_decryptor(content))


class SpinBoxSettingCard(SettingCard):
    """Setting card with SpinBox"""

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


class NoOptionComboBoxSettingCard(SettingCard):

    def __init__(
        self,
        configItem: OptionsConfigItem,
        icon: Union[str, QIcon, FluentIconBase],
        title,
        content=None,
        value=None,
        texts=None,
        parent=None,
    ):

        super().__init__(icon, title, content, parent)
        self.configItem = configItem
        self.comboBox = ComboBox(self)
        self.comboBox.setMinimumWidth(250)
        self.hBoxLayout.addWidget(self.comboBox, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.optionToText = {o: t for o, t in zip(value, texts)}
        for text, option in zip(texts, value):
            self.comboBox.addItem(text, userData=option)

        self.comboBox.setCurrentText(self.optionToText[qconfig.get(configItem)])
        self.comboBox.currentIndexChanged.connect(self._onCurrentIndexChanged)
        configItem.valueChanged.connect(self.setValue)

    def _onCurrentIndexChanged(self, index: int):

        qconfig.set(self.configItem, self.comboBox.itemData(index))

    def setValue(self, value):
        if value not in self.optionToText:
            return

        self.comboBox.setCurrentText(self.optionToText[value])
        qconfig.set(self.configItem, value)


class TimeEditSettingCard(SettingCard):

    enabledChanged = Signal(bool)
    timeChanged = Signal(str)

    def __init__(
        self,
        icon: Union[str, QIcon, FluentIconBase],
        title,
        content=None,
        configItem_bool: ConfigItem = None,
        configItem_time: ConfigItem = None,
        parent=None,
    ):

        super().__init__(icon, title, content, parent)
        self.configItem_bool = configItem_bool
        self.configItem_time = configItem_time
        self.CheckBox = CheckBox(self)
        self.CheckBox.setTristate(False)
        self.TimeEdit = TimeEdit(self)
        self.TimeEdit.setDisplayFormat("HH:mm")
        self.TimeEdit.setMinimumWidth(150)

        if configItem_bool:
            self.setValue_bool(qconfig.get(configItem_bool))
            configItem_bool.valueChanged.connect(self.setValue_bool)

        if configItem_time:
            self.setValue_time(qconfig.get(configItem_time))
            configItem_time.valueChanged.connect(self.setValue_time)

        self.hBoxLayout.addWidget(self.CheckBox, 0, Qt.AlignRight)
        self.hBoxLayout.addWidget(self.TimeEdit, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)

        self.CheckBox.stateChanged.connect(self.__enableChanged)
        self.TimeEdit.timeChanged.connect(self.__timeChanged)

    def __timeChanged(self, value: QTime):
        self.setValue_time(value.toString("HH:mm"))
        self.timeChanged.emit(value.toString("HH:mm"))

    def __enableChanged(self, value: int):
        if value == 0:
            self.setValue_bool(False)
            self.enabledChanged.emit(False)
        else:
            self.setValue_bool(True)
            self.enabledChanged.emit(True)

    def setValue_bool(self, value: bool):
        if self.configItem_bool:
            qconfig.set(self.configItem_bool, value)

        self.CheckBox.setChecked(value)

    def setValue_time(self, value: str):
        if self.configItem_time:
            qconfig.set(self.configItem_time, value)

        self.TimeEdit.setTime(QTime.fromString(value, "HH:mm"))


class StatefulItemCard(CardWidget):

    def __init__(self, item: list, parent=None):
        super().__init__(parent)

        self.Layout = QHBoxLayout(self)

        self.Label = BodyLabel(item[0], self)
        self.icon = IconWidget(FluentIcon.MORE, self)
        self.icon.setFixedSize(16, 16)
        self.update_status(item[1])

        self.Layout.addWidget(self.icon)
        self.Layout.addWidget(self.Label)
        self.Layout.addStretch(1)

    def update_status(self, status: str):

        if status == "完成":
            self.icon.setIcon(FluentIcon.ACCEPT)
            self.Label.setTextColor("#0eb840", "#0eb840")
        elif status == "等待":
            self.icon.setIcon(FluentIcon.MORE)
            self.Label.setTextColor("#161823", "#e3f9fd")
        elif status == "运行":
            self.icon.setIcon(FluentIcon.PLAY)
            self.Label.setTextColor("#177cb0", "#70f3ff")
        elif status == "跳过":
            self.icon.setIcon(FluentIcon.REMOVE)
            self.Label.setTextColor("#75878a", "#7397ab")
        elif status == "异常":
            self.icon.setIcon(FluentIcon.CLOSE)
            self.Label.setTextColor("#ff2121", "#ff2121")


class QuantifiedItemCard(CardWidget):

    def __init__(self, item: list, parent=None):
        super().__init__(parent)

        self.Layout = QHBoxLayout(self)

        self.Name = BodyLabel(item[0], self)
        self.Numb = BodyLabel(str(item[1]), self)

        self.Layout.addWidget(self.Name)
        self.Layout.addStretch(1)
        self.Layout.addWidget(self.Numb)
