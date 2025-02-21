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

from PySide6.QtWidgets import QWidget, QHBoxLayout
from PySide6.QtCore import Qt, QTime, QEvent
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPainterPath
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
    TeachingTip,
    TransparentToolButton,
    TeachingTipTailPosition,
)
from qfluentwidgets.common.overload import singledispatchmethod
import os
from typing import Optional, Union, List

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


class IconButton(TransparentToolButton):
    """包含下拉框的自定义设置卡片类。"""

    @singledispatchmethod
    def __init__(self, parent: QWidget = None):
        TransparentToolButton.__init__(self, parent)

        self._tooltip: Optional[TeachingTip] = None

    @__init__.register
    def _(self, icon: Union[str, QIcon, FluentIconBase], parent: QWidget = None):
        self.__init__(parent)
        self.setIcon(icon)

    @__init__.register
    def _(
        self,
        icon: Union[str, QIcon, FluentIconBase],
        isTooltip: bool,
        tip_title: str,
        tip_content: str,
        parent: QWidget = None,
    ):
        self.__init__(parent)
        self.setIcon(icon)

        # 处理工具提示
        if isTooltip:
            self.installEventFilter(self)

        self.tip_title: str = tip_title
        self.tip_content: str = tip_content

    def eventFilter(self, obj, event: QEvent) -> bool:
        """处理鼠标事件。"""
        if event.type() == QEvent.Type.Enter:
            self._show_tooltip()
        elif event.type() == QEvent.Type.Leave:
            self._hide_tooltip()
        return super().eventFilter(obj, event)

    def _show_tooltip(self) -> None:
        """显示工具提示。"""
        self._tooltip = TeachingTip.create(
            target=self,
            title=self.tip_title,
            content=self.tip_content,
            tailPosition=TeachingTipTailPosition.RIGHT,
            isClosable=False,
            duration=-1,
            parent=self,
        )
        # 设置偏移
        if self._tooltip:
            tooltip_pos = self.mapToGlobal(self.rect().topRight())

            tooltip_pos.setX(
                tooltip_pos.x() - self._tooltip.size().width() - 40
            )  # 水平偏移
            tooltip_pos.setY(
                tooltip_pos.y() - self._tooltip.size().height() / 2 + 35
            )  # 垂直偏移

            self._tooltip.move(tooltip_pos)

    def _hide_tooltip(self) -> None:
        """隐藏工具提示。"""
        if self._tooltip:
            self._tooltip.close()
            self._tooltip = None

    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self is other


class Banner(QWidget):
    """展示带有圆角的固定大小横幅小部件"""

    def __init__(self, image_path: str, parent=None):
        QWidget.__init__(self, parent)
        self.image_path = image_path
        self.banner_image = self.load_banner_image(image_path)
        self.scaled_image = None
        self.update_scaled_image()

    def load_banner_image(self, image_path: str):
        """加载横幅图片，或创建渐变备用图片"""
        if os.path.isfile(image_path):
            return QPixmap(image_path)
        return self._create_fallback_image()

    def _create_fallback_image(self):
        """创建渐变备用图片"""
        fallback_image = QPixmap(2560, 1280)  # 使用原始图片的大小
        fallback_image.fill(Qt.GlobalColor.gray)
        return fallback_image

    def update_scaled_image(self):
        """按高度缩放图片，宽度保持比例，超出裁剪"""
        if self.banner_image:
            self.scaled_image = self.banner_image.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        self.update()

    def paintEvent(self, event):
        """重载 paintEvent 以绘制缩放后的图片"""
        if self.scaled_image:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

            # 创建圆角路径
            path = QPainterPath()
            path.addRoundedRect(self.rect(), 20, 20)
            painter.setClipPath(path)

            # 计算绘制位置，使图片居中
            x = (self.width() - self.scaled_image.width()) // 2
            y = (self.height() - self.scaled_image.height()) // 2

            # 绘制缩放后的图片
            painter.drawPixmap(x, y, self.scaled_image)

    def resizeEvent(self, event):
        """重载 resizeEvent 以更新缩放后的图片"""
        self.update_scaled_image()
        QWidget.resizeEvent(self, event)

    def set_percentage_size(self, width_percentage, height_percentage):
        """设置 Banner 的大小为窗口大小的百分比"""
        parent = self.parentWidget()
        if parent:
            new_width = int(parent.width() * width_percentage)
            new_height = int(parent.height() * height_percentage)
            self.setFixedSize(new_width, new_height)
            self.update_scaled_image()
