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
AUTO_MAA调度队列界面
v4.4
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
    Action,
    ScrollArea,
    FluentIcon,
    MessageBox,
    HeaderCardWidget,
    CommandBar,
)
from typing import List

from app.core import QueueConfig, Config, MainInfoBar, SoundPlayer
from .Widget import (
    SwitchSettingCard,
    ComboBoxSettingCard,
    LineEditSettingCard,
    TimeEditSettingCard,
    NoOptionComboBoxSettingCard,
    HistoryCard,
    PivotArea,
)


class QueueManager(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("调度队列")

        layout = QVBoxLayout(self)

        self.tools = CommandBar()

        self.queue_manager = self.QueueSettingBox(self)

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

        layout.addWidget(self.tools)
        layout.addWidget(self.queue_manager)

    def add_setting_box(self):
        """添加一个调度队列"""

        index = len(Config.queue_dict) + 1

        queue_config = QueueConfig()
        queue_config.load(
            Config.app_path / f"config/QueueConfig/调度队列_{index}.json", queue_config
        )
        queue_config.save()

        Config.queue_dict[f"调度队列_{index}"] = {
            "Path": Config.app_path / f"config/QueueConfig/调度队列_{index}.json",
            "Config": queue_config,
        }

        self.queue_manager.add_SettingBox(index)
        self.queue_manager.switch_SettingBox(index)

        logger.success(f"调度队列_{index} 添加成功")
        MainInfoBar.push_info_bar("success", "操作成功", f"添加 调度队列_{index}", 3000)
        SoundPlayer.play("添加调度队列")

    def del_setting_box(self):
        """删除一个调度队列实例"""

        name = self.queue_manager.pivot.currentRouteKey()

        if name is None:
            logger.warning("未选择调度队列")
            MainInfoBar.push_info_bar(
                "warning", "未选择调度队列", "请先选择一个调度队列", 5000
            )
            return None

        if name in Config.running_list:
            logger.warning("调度队列正在运行")
            MainInfoBar.push_info_bar(
                "warning", "调度队列正在运行", "请先停止调度队列", 5000
            )
            return None

        choice = MessageBox("确认", f"确定要删除 {name} 吗？", self.window())
        if choice.exec():

            self.queue_manager.clear_SettingBox()

            Config.queue_dict[name]["Path"].unlink()
            for i in range(int(name[5:]) + 1, len(Config.queue_dict) + 1):
                if Config.queue_dict[f"调度队列_{i}"]["Path"].exists():
                    Config.queue_dict[f"调度队列_{i}"]["Path"].rename(
                        Config.queue_dict[f"调度队列_{i}"]["Path"].with_name(
                            f"调度队列_{i-1}.json"
                        )
                    )

            self.queue_manager.show_SettingBox(max(int(name[5:]) - 1, 1))

            logger.success(f"{name} 删除成功")
            MainInfoBar.push_info_bar("success", "操作成功", f"删除 {name}", 3000)
            SoundPlayer.play("删除调度队列")

    def left_setting_box(self):
        """向左移动调度队列实例"""

        name = self.queue_manager.pivot.currentRouteKey()

        if name is None:
            logger.warning("未选择调度队列")
            MainInfoBar.push_info_bar(
                "warning", "未选择调度队列", "请先选择一个调度队列", 5000
            )
            return None

        index = int(name[5:])

        if index == 1:
            logger.warning("向左移动调度队列时已到达最左端")
            MainInfoBar.push_info_bar(
                "warning", "已经是第一个调度队列", "无法向左移动", 5000
            )
            return None

        if name in Config.running_list or f"调度队列_{index-1}" in Config.running_list:
            logger.warning("相关调度队列正在运行")
            MainInfoBar.push_info_bar(
                "warning", "相关调度队列正在运行", "请先停止调度队列", 5000
            )
            return None

        self.queue_manager.clear_SettingBox()

        Config.queue_dict[name]["Path"].rename(
            Config.queue_dict[name]["Path"].with_name("调度队列_0.json")
        )
        Config.queue_dict[f"调度队列_{index-1}"]["Path"].rename(
            Config.queue_dict[name]["Path"]
        )
        Config.queue_dict[name]["Path"].with_name("调度队列_0.json").rename(
            Config.queue_dict[f"调度队列_{index-1}"]["Path"]
        )

        self.queue_manager.show_SettingBox(index - 1)

        logger.success(f"{name} 左移成功")
        MainInfoBar.push_info_bar("success", "操作成功", f"左移 {name}", 3000)

    def right_setting_box(self):
        """向右移动调度队列实例"""

        name = self.queue_manager.pivot.currentRouteKey()

        if name is None:
            logger.warning("未选择调度队列")
            MainInfoBar.push_info_bar(
                "warning", "未选择调度队列", "请先选择一个调度队列", 5000
            )
            return None

        index = int(name[5:])

        if index == len(Config.queue_dict):
            logger.warning("向右移动调度队列时已到达最右端")
            MainInfoBar.push_info_bar(
                "warning", "已经是最后一个调度队列", "无法向右移动", 5000
            )
            return None

        if name in Config.running_list or f"调度队列_{index+1}" in Config.running_list:
            logger.warning("相关调度队列正在运行")
            MainInfoBar.push_info_bar(
                "warning", "相关调度队列正在运行", "请先停止调度队列", 5000
            )
            return None

        self.queue_manager.clear_SettingBox()

        Config.queue_dict[name]["Path"].rename(
            Config.queue_dict[name]["Path"].with_name("调度队列_0.json")
        )
        Config.queue_dict[f"调度队列_{index+1}"]["Path"].rename(
            Config.queue_dict[name]["Path"]
        )
        Config.queue_dict[name]["Path"].with_name("调度队列_0.json").rename(
            Config.queue_dict[f"调度队列_{index+1}"]["Path"]
        )

        self.queue_manager.show_SettingBox(index + 1)

        logger.success(f"{name} 右移成功")
        MainInfoBar.push_info_bar("success", "操作成功", f"右移 {name}", 3000)

    def reload_member_name(self):
        """刷新调度队列成员"""

        member_list = [
            ["禁用"] + [_ for _ in Config.member_dict.keys()],
            ["未启用"]
            + [
                (
                    k
                    if v["Config"].get_name() == ""
                    else f"{k} - {v["Config"].get_name()}"
                )
                for k, v in Config.member_dict.items()
            ],
        ]
        for script in self.queue_manager.script_list:

            script.task.card_Member_1.reLoadOptions(
                value=member_list[0], texts=member_list[1]
            )
            script.task.card_Member_2.reLoadOptions(
                value=member_list[0], texts=member_list[1]
            )
            script.task.card_Member_3.reLoadOptions(
                value=member_list[0], texts=member_list[1]
            )
            script.task.card_Member_4.reLoadOptions(
                value=member_list[0], texts=member_list[1]
            )
            script.task.card_Member_5.reLoadOptions(
                value=member_list[0], texts=member_list[1]
            )
            script.task.card_Member_6.reLoadOptions(
                value=member_list[0], texts=member_list[1]
            )
            script.task.card_Member_7.reLoadOptions(
                value=member_list[0], texts=member_list[1]
            )
            script.task.card_Member_8.reLoadOptions(
                value=member_list[0], texts=member_list[1]
            )
            script.task.card_Member_9.reLoadOptions(
                value=member_list[0], texts=member_list[1]
            )
            script.task.card_Member_10.reLoadOptions(
                value=member_list[0], texts=member_list[1]
            )

    class QueueSettingBox(QWidget):

        def __init__(self, parent=None):
            super().__init__(parent)

            self.setObjectName("调度队列管理")

            self.pivotArea = PivotArea()
            self.pivot = self.pivotArea.pivot

            self.stackedWidget = QStackedWidget(self)
            self.stackedWidget.setContentsMargins(0, 0, 0, 0)
            self.stackedWidget.setStyleSheet("background: transparent; border: none;")

            self.script_list: List[
                QueueManager.QueueSettingBox.QueueMemberSettingBox
            ] = []

            self.Layout = QVBoxLayout(self)
            self.Layout.addWidget(self.pivotArea)
            self.Layout.addWidget(self.stackedWidget)
            self.Layout.setContentsMargins(0, 0, 0, 0)

            self.pivot.currentItemChanged.connect(
                lambda index: self.switch_SettingBox(
                    int(index[5:]), if_change_pivot=False
                )
            )

            self.show_SettingBox(1)

        def show_SettingBox(self, index) -> None:
            """加载所有子界面"""

            Config.search_queue()

            for name in Config.queue_dict.keys():
                self.add_SettingBox(int(name[5:]))

            self.switch_SettingBox(index)

        def switch_SettingBox(self, index: int, if_change_pivot: bool = True) -> None:
            """切换到指定的子界面"""

            if len(Config.queue_dict) == 0:
                return None

            if index > len(Config.queue_dict):
                return None

            if if_change_pivot:
                self.pivot.setCurrentItem(self.script_list[index - 1].objectName())
            self.stackedWidget.setCurrentWidget(self.script_list[index - 1])

        def clear_SettingBox(self) -> None:
            """清空所有子界面"""

            for sub_interface in self.script_list:
                self.stackedWidget.removeWidget(sub_interface)
                sub_interface.deleteLater()
            self.script_list.clear()
            self.pivot.clear()

        def add_SettingBox(self, uid: int) -> None:
            """添加一个调度队列设置界面"""

            setting_box = self.QueueMemberSettingBox(uid, self)

            self.script_list.append(setting_box)

            self.stackedWidget.addWidget(self.script_list[-1])

            self.pivot.addItem(routeKey=f"调度队列_{uid}", text=f"调度队列 {uid}")

        class QueueMemberSettingBox(QWidget):

            def __init__(self, uid: int, parent=None):
                super().__init__(parent)

                self.setObjectName(f"调度队列_{uid}")
                self.config = Config.queue_dict[f"调度队列_{uid}"]["Config"]

                self.queue_set = self.QueueSetSettingCard(self.config, self)
                self.time = self.TimeSettingCard(self.config, self)
                self.task = self.TaskSettingCard(self.config, self)
                self.history = HistoryCard(
                    qconfig=self.config,
                    configItem=self.config.Data_LastProxyHistory,
                    parent=self,
                )

                content_widget = QWidget()
                content_layout = QVBoxLayout(content_widget)
                content_layout.setContentsMargins(0, 0, 11, 0)
                content_layout.addWidget(self.queue_set)
                content_layout.addWidget(self.time)
                content_layout.addWidget(self.task)
                content_layout.addWidget(self.history)
                content_layout.addStretch(1)

                scrollArea = ScrollArea()
                scrollArea.setWidgetResizable(True)
                scrollArea.setContentsMargins(0, 0, 0, 0)
                scrollArea.setStyleSheet("background: transparent; border: none;")
                scrollArea.setWidget(content_widget)

                layout = QVBoxLayout(self)
                layout.addWidget(scrollArea)

            class QueueSetSettingCard(HeaderCardWidget):

                def __init__(self, config: QueueConfig, parent=None):
                    super().__init__(parent)

                    self.setTitle("队列设置")
                    self.config = config

                    self.card_Name = LineEditSettingCard(
                        icon=FluentIcon.EDIT,
                        title="调度队列名称",
                        content="用于标识调度队列的名称",
                        text="请输入调度队列名称",
                        qconfig=self.config,
                        configItem=self.config.queueSet_Name,
                        parent=self,
                    )
                    self.card_Enable = SwitchSettingCard(
                        icon=FluentIcon.HOME,
                        title="状态",
                        content="调度队列状态，仅启用时会执行定时任务",
                        qconfig=self.config,
                        configItem=self.config.queueSet_Enabled,
                        parent=self,
                    )
                    self.card_AfterAccomplish = ComboBoxSettingCard(
                        icon=FluentIcon.POWER_BUTTON,
                        title="调度队列结束后",
                        content="选择调度队列结束后的操作",
                        texts=[
                            "无动作",
                            "退出AUTO_MAA",
                            "睡眠（win系统需禁用休眠）",
                            "休眠",
                            "关机",
                        ],
                        qconfig=self.config,
                        configItem=self.config.queueSet_AfterAccomplish,
                        parent=self,
                    )

                    Layout = QVBoxLayout()
                    Layout.addWidget(self.card_Name)
                    Layout.addWidget(self.card_Enable)
                    Layout.addWidget(self.card_AfterAccomplish)

                    self.viewLayout.addLayout(Layout)

            class TimeSettingCard(HeaderCardWidget):

                def __init__(self, config: QueueConfig, parent=None):
                    super().__init__(parent)

                    self.setTitle("定时设置")
                    self.config = config

                    widget_1 = QWidget()
                    Layout_1 = QVBoxLayout(widget_1)
                    widget_2 = QWidget()
                    Layout_2 = QVBoxLayout(widget_2)
                    Layout = QHBoxLayout()

                    self.card_Time_0 = TimeEditSettingCard(
                        icon=FluentIcon.STOP_WATCH,
                        title="定时 1",
                        content=None,
                        qconfig=self.config,
                        configItem_bool=self.config.time_TimeEnabled_0,
                        configItem_time=self.config.time_TimeSet_0,
                        parent=self,
                    )
                    self.card_Time_1 = TimeEditSettingCard(
                        icon=FluentIcon.STOP_WATCH,
                        title="定时 2",
                        content=None,
                        qconfig=self.config,
                        configItem_bool=self.config.time_TimeEnabled_1,
                        configItem_time=self.config.time_TimeSet_1,
                        parent=self,
                    )
                    self.card_Time_2 = TimeEditSettingCard(
                        icon=FluentIcon.STOP_WATCH,
                        title="定时 3",
                        content=None,
                        qconfig=self.config,
                        configItem_bool=self.config.time_TimeEnabled_2,
                        configItem_time=self.config.time_TimeSet_2,
                        parent=self,
                    )
                    self.card_Time_3 = TimeEditSettingCard(
                        icon=FluentIcon.STOP_WATCH,
                        title="定时 4",
                        content=None,
                        qconfig=self.config,
                        configItem_bool=self.config.time_TimeEnabled_3,
                        configItem_time=self.config.time_TimeSet_3,
                        parent=self,
                    )
                    self.card_Time_4 = TimeEditSettingCard(
                        icon=FluentIcon.STOP_WATCH,
                        title="定时 5",
                        content=None,
                        qconfig=self.config,
                        configItem_bool=self.config.time_TimeEnabled_4,
                        configItem_time=self.config.time_TimeSet_4,
                        parent=self,
                    )
                    self.card_Time_5 = TimeEditSettingCard(
                        icon=FluentIcon.STOP_WATCH,
                        title="定时 6",
                        content=None,
                        qconfig=self.config,
                        configItem_bool=self.config.time_TimeEnabled_5,
                        configItem_time=self.config.time_TimeSet_5,
                        parent=self,
                    )
                    self.card_Time_6 = TimeEditSettingCard(
                        icon=FluentIcon.STOP_WATCH,
                        title="定时 7",
                        content=None,
                        qconfig=self.config,
                        configItem_bool=self.config.time_TimeEnabled_6,
                        configItem_time=self.config.time_TimeSet_6,
                        parent=self,
                    )
                    self.card_Time_7 = TimeEditSettingCard(
                        icon=FluentIcon.STOP_WATCH,
                        title="定时 8",
                        content=None,
                        qconfig=self.config,
                        configItem_bool=self.config.time_TimeEnabled_7,
                        configItem_time=self.config.time_TimeSet_7,
                        parent=self,
                    )
                    self.card_Time_8 = TimeEditSettingCard(
                        icon=FluentIcon.STOP_WATCH,
                        title="定时 9",
                        content=None,
                        qconfig=self.config,
                        configItem_bool=self.config.time_TimeEnabled_8,
                        configItem_time=self.config.time_TimeSet_8,
                        parent=self,
                    )
                    self.card_Time_9 = TimeEditSettingCard(
                        icon=FluentIcon.STOP_WATCH,
                        title="定时 10",
                        content=None,
                        qconfig=self.config,
                        configItem_bool=self.config.time_TimeEnabled_9,
                        configItem_time=self.config.time_TimeSet_9,
                        parent=self,
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

            class TaskSettingCard(HeaderCardWidget):

                def __init__(self, config: QueueConfig, parent=None):
                    super().__init__(parent)

                    self.setTitle("任务队列")
                    self.config = config

                    member_list = [
                        ["禁用"] + [_ for _ in Config.member_dict.keys()],
                        ["未启用"]
                        + [
                            (
                                k
                                if v["Config"].get_name() == ""
                                else f"{k} - {v["Config"].get_name()}"
                            )
                            for k, v in Config.member_dict.items()
                        ],
                    ]

                    self.card_Member_1 = NoOptionComboBoxSettingCard(
                        icon=FluentIcon.APPLICATION,
                        title="任务实例 1",
                        content="第一个调起的脚本任务实例",
                        value=member_list[0],
                        texts=member_list[1],
                        qconfig=self.config,
                        configItem=self.config.queue_Member_1,
                        parent=self,
                    )
                    self.card_Member_2 = NoOptionComboBoxSettingCard(
                        icon=FluentIcon.APPLICATION,
                        title="任务实例 2",
                        content="第二个调起的脚本任务实例",
                        value=member_list[0],
                        texts=member_list[1],
                        qconfig=self.config,
                        configItem=self.config.queue_Member_2,
                        parent=self,
                    )
                    self.card_Member_3 = NoOptionComboBoxSettingCard(
                        icon=FluentIcon.APPLICATION,
                        title="任务实例 3",
                        content="第三个调起的脚本任务实例",
                        value=member_list[0],
                        texts=member_list[1],
                        qconfig=self.config,
                        configItem=self.config.queue_Member_3,
                        parent=self,
                    )
                    self.card_Member_4 = NoOptionComboBoxSettingCard(
                        icon=FluentIcon.APPLICATION,
                        title="任务实例 4",
                        content="第四个调起的脚本任务实例",
                        value=member_list[0],
                        texts=member_list[1],
                        qconfig=self.config,
                        configItem=self.config.queue_Member_4,
                        parent=self,
                    )
                    self.card_Member_5 = NoOptionComboBoxSettingCard(
                        icon=FluentIcon.APPLICATION,
                        title="任务实例 5",
                        content="第五个调起的脚本任务实例",
                        value=member_list[0],
                        texts=member_list[1],
                        qconfig=self.config,
                        configItem=self.config.queue_Member_5,
                        parent=self,
                    )
                    self.card_Member_6 = NoOptionComboBoxSettingCard(
                        icon=FluentIcon.APPLICATION,
                        title="任务实例 6",
                        content="第六个调起的脚本任务实例",
                        value=member_list[0],
                        texts=member_list[1],
                        qconfig=self.config,
                        configItem=self.config.queue_Member_6,
                        parent=self,
                    )
                    self.card_Member_7 = NoOptionComboBoxSettingCard(
                        icon=FluentIcon.APPLICATION,
                        title="任务实例 7",
                        content="第七个调起的脚本任务实例",
                        value=member_list[0],
                        texts=member_list[1],
                        qconfig=self.config,
                        configItem=self.config.queue_Member_7,
                        parent=self,
                    )
                    self.card_Member_8 = NoOptionComboBoxSettingCard(
                        icon=FluentIcon.APPLICATION,
                        title="任务实例 8",
                        content="第八个调起的脚本任务实例",
                        value=member_list[0],
                        texts=member_list[1],
                        qconfig=self.config,
                        configItem=self.config.queue_Member_8,
                        parent=self,
                    )
                    self.card_Member_9 = NoOptionComboBoxSettingCard(
                        icon=FluentIcon.APPLICATION,
                        title="任务实例 9",
                        content="第九个调起的脚本任务实例",
                        value=member_list[0],
                        texts=member_list[1],
                        qconfig=self.config,
                        configItem=self.config.queue_Member_9,
                        parent=self,
                    )
                    self.card_Member_10 = NoOptionComboBoxSettingCard(
                        icon=FluentIcon.APPLICATION,
                        title="任务实例 10",
                        content="第十个调起的脚本任务实例",
                        value=member_list[0],
                        texts=member_list[1],
                        qconfig=self.config,
                        configItem=self.config.queue_Member_10,
                        parent=self,
                    )

                    Layout = QVBoxLayout()
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
