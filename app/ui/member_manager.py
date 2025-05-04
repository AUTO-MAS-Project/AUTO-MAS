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
AUTO_MAA脚本管理界面
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
from qfluentwidgets import (
    Action,
    Pivot,
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
from PySide6.QtCore import Qt, Signal
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import List
import shutil

from app.core import Config, MainInfoBar, TaskManager, MaaConfig, MaaUserConfig, Network
from app.services import Crypto
from app.utils import DownloadManager
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
)


class MemberManager(QWidget):
    """脚本管理父界面"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("脚本管理")

        layout = QVBoxLayout(self)

        self.tools = CommandBar()

        self.member_manager = self.MemberSettingBox(self)

        # 逐个添加动作
        self.tools.addActions(
            [
                Action(
                    FluentIcon.ADD_TO, "新建脚本实例", triggered=self.add_setting_box
                ),
                Action(
                    FluentIcon.REMOVE_FROM,
                    "删除脚本实例",
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
        self.tools.addSeparator()
        self.tools.addAction(
            Action(
                FluentIcon.DOWNLOAD,
                "脚本下载器",
                triggered=self.member_downloader,
            )
        )
        self.tools.addSeparator()
        self.key = Action(
            FluentIcon.HIDE,
            "显示/隐藏密码",
            checkable=True,
            triggered=self.show_password,
        )
        self.tools.addAction(self.key)

        layout.addWidget(self.tools)
        layout.addWidget(self.member_manager)

    def add_setting_box(self):
        """添加一个脚本实例"""

        choice = ComboBoxMessageBox(
            self.window(),
            "选择一个脚本类型以添加相应脚本实例",
            ["选择脚本类型"],
            [["MAA"]],
        )
        if choice.exec() and choice.input[0].currentIndex() != -1:

            if choice.input[0].currentText() == "MAA":

                index = len(Config.member_dict) + 1

                maa_config = MaaConfig()
                maa_config.load(
                    Config.app_path / f"config/MaaConfig/脚本_{index}/config.json",
                    maa_config,
                )
                maa_config.save()
                (Config.app_path / f"config/MaaConfig/脚本_{index}/UserData").mkdir(
                    parents=True, exist_ok=True
                )

                Config.member_dict[f"脚本_{index}"] = {
                    "Type": "Maa",
                    "Path": Config.app_path / f"config/MaaConfig/脚本_{index}",
                    "Config": maa_config,
                    "UserData": {},
                }

                self.member_manager.add_MaaSettingBox(index)
                self.member_manager.switch_SettingBox(index)

                logger.success(f"脚本实例 脚本_{index} 添加成功")
                MainInfoBar.push_info_bar(
                    "success", "操作成功", f"添加脚本实例 脚本_{index}", 3000
                )

    def del_setting_box(self):
        """删除一个脚本实例"""

        name = self.member_manager.pivot.currentRouteKey()

        if name == None:
            logger.warning("删除脚本实例时未选择脚本实例")
            MainInfoBar.push_info_bar(
                "warning", "未选择脚本实例", "请选择一个脚本实例", 5000
            )
            return None

        if len(Config.running_list) > 0:
            logger.warning("删除脚本实例时调度队列未停止运行")
            MainInfoBar.push_info_bar(
                "warning", "调度中心正在执行任务", "请等待或手动中止任务", 5000
            )
            return None

        choice = MessageBox(
            "确认",
            f"确定要删除 {name} 实例吗？",
            self.window(),
        )
        if choice.exec():

            self.member_manager.clear_SettingBox()

            shutil.rmtree(Config.member_dict[name]["Path"])
            Config.change_queue(name, "禁用")
            for i in range(int(name[3:]) + 1, len(Config.member_dict) + 1):
                if Config.member_dict[f"脚本_{i}"]["Path"].exists():
                    Config.member_dict[f"脚本_{i}"]["Path"].rename(
                        Config.member_dict[f"脚本_{i}"]["Path"].with_name(f"脚本_{i-1}")
                    )
                Config.change_queue(f"脚本_{i}", f"脚本_{i-1}")

            self.member_manager.show_SettingBox(max(int(name[3:]) - 1, 1))

            logger.success(f"脚本实例 {name} 删除成功")
            MainInfoBar.push_info_bar(
                "success", "操作成功", f"删除脚本实例 {name}", 3000
            )

    def left_setting_box(self):
        """向左移动脚本实例"""

        name = self.member_manager.pivot.currentRouteKey()

        if name == None:
            logger.warning("向左移动脚本实例时未选择脚本实例")
            MainInfoBar.push_info_bar(
                "warning", "未选择脚本实例", "请选择一个脚本实例", 5000
            )
            return None

        index = int(name[3:])

        if index == 1:
            logger.warning("向左移动脚本实例时已到达最左端")
            MainInfoBar.push_info_bar(
                "warning", "已经是第一个脚本实例", "无法向左移动", 5000
            )
            return None

        if len(Config.running_list) > 0:
            logger.warning("向左移动脚本实例时调度队列未停止运行")
            MainInfoBar.push_info_bar(
                "warning", "调度中心正在执行任务", "请等待或手动中止任务", 5000
            )
            return None

        self.member_manager.clear_SettingBox()

        Config.member_dict[name]["Path"].rename(
            Config.member_dict[name]["Path"].with_name("脚本_0")
        )
        Config.change_queue(name, "脚本_0")
        Config.member_dict[f"脚本_{index-1}"]["Path"].rename(
            Config.member_dict[name]["Path"]
        )
        Config.change_queue(f"脚本_{index-1}", name)
        Config.member_dict[name]["Path"].with_name("脚本_0").rename(
            Config.member_dict[f"脚本_{index-1}"]["Path"]
        )
        Config.change_queue("脚本_0", f"脚本_{index-1}")

        self.member_manager.show_SettingBox(index - 1)

        logger.success(f"脚本实例 {name} 左移成功")
        MainInfoBar.push_info_bar("success", "操作成功", f"左移脚本实例 {name}", 3000)

    def right_setting_box(self):
        """向右移动脚本实例"""

        name = self.member_manager.pivot.currentRouteKey()

        if name == None:
            logger.warning("向右移动脚本实例时未选择脚本实例")
            MainInfoBar.push_info_bar(
                "warning", "未选择脚本实例", "请选择一个脚本实例", 5000
            )
            return None

        index = int(name[3:])

        if index == len(Config.member_dict):
            logger.warning("向右移动脚本实例时已到达最右端")
            MainInfoBar.push_info_bar(
                "warning", "已经是最后一个脚本实例", "无法向右移动", 5000
            )
            return None

        if len(Config.running_list) > 0:
            logger.warning("向右移动脚本实例时调度队列未停止运行")
            MainInfoBar.push_info_bar(
                "warning", "调度中心正在执行任务", "请等待或手动中止任务", 5000
            )
            return None

        self.member_manager.clear_SettingBox()

        Config.member_dict[name]["Path"].rename(
            Config.member_dict[name]["Path"].with_name("脚本_0")
        )
        Config.change_queue(name, "脚本_0")
        Config.member_dict[f"脚本_{index+1}"]["Path"].rename(
            Config.member_dict[name]["Path"]
        )
        Config.change_queue(f"脚本_{index+1}", name)
        Config.member_dict[name]["Path"].with_name("脚本_0").rename(
            Config.member_dict[f"脚本_{index+1}"]["Path"]
        )
        Config.change_queue("脚本_0", f"脚本_{index+1}")

        self.member_manager.show_SettingBox(index + 1)

        logger.success(f"脚本实例 {name} 右移成功")
        MainInfoBar.push_info_bar("success", "操作成功", f"右移脚本实例 {name}", 3000)

    def member_downloader(self):
        """脚本下载器"""

        choice = ComboBoxMessageBox(
            self.window(),
            "选择一个脚本类型以下载相应脚本",
            ["选择脚本类型"],
            [["MAA"]],
        )
        if choice.exec() and choice.input[0].currentIndex() != -1:

            if choice.input[0].currentText() == "MAA":

                (Config.app_path / "script/MAA").mkdir(parents=True, exist_ok=True)
                folder = QFileDialog.getExistingDirectory(
                    self, "选择MAA下载目录", str(Config.app_path / "script/MAA")
                )
                if not folder:
                    logger.warning("选择MAA下载目录时未选择文件夹")
                    MainInfoBar.push_info_bar(
                        "warning", "警告", "未选择MAA下载目录", 5000
                    )
                    return None

                # 从mirrorc服务器获取最新版本信息
                Network.set_info(
                    mode="get",
                    url="https://mirrorchyan.com/api/resources/MAA/latest?user_agent=AutoMaaGui&os=win&arch=x64&channel=stable",
                )
                Network.start()
                Network.loop.exec()
                if Network.stutus_code == 200:
                    maa_info = Network.response_json
                else:
                    choice = MessageBox(
                        "错误",
                        f"获取版本信息时出错：\n{Network.error_message}",
                        self.window(),
                    )
                    choice.cancelButton.hide()
                    choice.buttonLayout.insertStretch(1)
                    if choice.exec():
                        return None
                maa_version = list(
                    map(
                        int,
                        maa_info["data"]["version_name"][1:]
                        .replace("-beta", "")
                        .split("."),
                    )
                )
                while len(maa_version) < 4:
                    maa_version.append(0)

                self.downloader = DownloadManager(
                    Path(folder),
                    "MAA",
                    maa_version,
                    {
                        "mode": "Proxy",
                        "thread_numb": Config.get(Config.update_ThreadNumb),
                    },
                )
                self.downloader.show()
                self.downloader.run()

    def show_password(self):

        if Config.PASSWORD == "":
            choice = LineEditMessageBox(
                self.window(),
                "请输入管理密钥",
                "管理密钥",
                "密码",
            )
            if choice.exec() and choice.input.text() != "":
                Config.PASSWORD = choice.input.text()
                Config.PASSWORD_refreshed.emit()
                self.key.setIcon(FluentIcon.VIEW)
                self.key.setChecked(True)
            else:
                Config.PASSWORD = ""
                Config.PASSWORD_refreshed.emit()
                self.key.setIcon(FluentIcon.HIDE)
                self.key.setChecked(False)
        else:
            Config.PASSWORD = ""
            Config.PASSWORD_refreshed.emit()
            self.key.setIcon(FluentIcon.HIDE)
            self.key.setChecked(False)

    def refresh_dashboard(self):
        """刷新所有脚本实例的用户仪表盘"""

        for script in self.member_manager.script_list:
            script.user_setting.user_manager.user_dashboard.load_info()

    class MemberSettingBox(QWidget):
        """脚本管理子页面组"""

        def __init__(self, parent=None):
            super().__init__(parent)

            self.setObjectName("脚本管理页面组")

            self.pivot = Pivot(self)
            self.stackedWidget = QStackedWidget(self)
            self.Layout = QVBoxLayout(self)

            self.script_list: List[MemberManager.MemberSettingBox.MaaSettingBox] = []

            self.Layout.addWidget(self.pivot, 0, Qt.AlignHCenter)
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

            Config.search_member()

            for name, info in Config.member_dict.items():
                if info["Type"] == "Maa":
                    self.add_MaaSettingBox(int(name[3:]))

            self.switch_SettingBox(index)

        def switch_SettingBox(self, index: int, if_chang_pivot: bool = True) -> None:
            """切换到指定的子界面"""

            if len(Config.member_dict) == 0:
                return None

            if index > len(Config.member_dict):
                return None

            if if_chang_pivot:
                self.pivot.setCurrentItem(self.script_list[index - 1].objectName())
            self.stackedWidget.setCurrentWidget(self.script_list[index - 1])
            self.script_list[index - 1].user_setting.user_manager.switch_SettingBox(
                "用户仪表盘"
            )

        def clear_SettingBox(self) -> None:
            """清空所有子界面"""

            for sub_interface in self.script_list:
                self.stackedWidget.removeWidget(sub_interface)
                sub_interface.deleteLater()
            self.script_list.clear()
            self.pivot.clear()

        def add_MaaSettingBox(self, uid: int) -> None:
            """添加一个MAA设置界面"""

            maa_setting_box = self.MaaSettingBox(uid, self)

            self.script_list.append(maa_setting_box)

            self.stackedWidget.addWidget(self.script_list[-1])

            self.pivot.addItem(routeKey=f"脚本_{uid}", text=f"脚本 {uid}")

        class MaaSettingBox(QWidget):
            """MAA类脚本设置界面"""

            def __init__(self, uid: int, parent=None):
                super().__init__(parent)

                self.setObjectName(f"脚本_{uid}")
                self.config = Config.member_dict[f"脚本_{uid}"]["Config"]

                layout = QVBoxLayout()

                scrollArea = ScrollArea()
                scrollArea.setWidgetResizable(True)

                content_widget = QWidget()
                content_layout = QVBoxLayout(content_widget)

                self.app_setting = self.AppSettingCard(f"脚本_{uid}", self.config, self)
                self.user_setting = self.UserManager(f"脚本_{uid}", self)

                content_layout.addWidget(self.app_setting)
                content_layout.addWidget(self.user_setting)
                content_layout.addStretch(1)

                scrollArea.setWidget(content_widget)

                layout.addWidget(scrollArea)

                self.setLayout(layout)

            class AppSettingCard(HeaderCardWidget):

                def __init__(self, name: str, config: MaaConfig, parent=None):
                    super().__init__(parent)

                    self.setTitle("MAA实例")

                    self.name = name
                    self.config = config

                    Layout = QVBoxLayout()

                    self.card_Name = LineEditSettingCard(
                        icon=FluentIcon.EDIT,
                        title="实例名称",
                        content="用于标识MAA实例的名称",
                        text="请输入实例名称",
                        qconfig=self.config,
                        configItem=self.config.MaaSet_Name,
                        parent=self,
                    )
                    self.card_Path = PushSettingCard(
                        text="选择文件夹",
                        icon=FluentIcon.FOLDER,
                        title="MAA目录",
                        content=self.config.get(self.config.MaaSet_Path),
                        parent=self,
                    )
                    self.card_Set = PushSettingCard(
                        text="设置",
                        icon=FluentIcon.HOME,
                        title="MAA全局配置",
                        content="简洁模式下MAA将继承全局配置",
                        parent=self,
                    )
                    self.RunSet = self.RunSetSettingCard(self.config, self)

                    self.card_Path.clicked.connect(self.PathClicked)
                    self.config.MaaSet_Path.valueChanged.connect(
                        lambda: self.card_Path.setContent(
                            self.config.get(self.config.MaaSet_Path)
                        )
                    )
                    self.card_Set.clicked.connect(
                        lambda: TaskManager.add_task("设置MAA_全局", self.name, None)
                    )

                    Layout.addWidget(self.card_Name)
                    Layout.addWidget(self.card_Path)
                    Layout.addWidget(self.card_Set)
                    Layout.addWidget(self.RunSet)

                    self.viewLayout.addLayout(Layout)

                def PathClicked(self):

                    folder = QFileDialog.getExistingDirectory(
                        self,
                        "选择MAA目录",
                        self.config.get(self.config.MaaSet_Path),
                    )
                    if not folder or self.config.get(self.config.MaaSet_Path) == folder:
                        logger.warning("选择MAA目录时未选择文件夹或未更改文件夹")
                        MainInfoBar.push_info_bar(
                            "warning", "警告", "未选择文件夹或未更改文件夹", 5000
                        )
                        return None
                    elif (
                        not (Path(folder) / "config/gui.json").exists()
                        or not (Path(folder) / "MAA.exe").exists()
                    ):
                        logger.warning("选择MAA目录时未找到MAA程序或配置文件")
                        MainInfoBar.push_info_bar(
                            "warning", "警告", "未找到MAA程序或配置文件", 5000
                        )
                        return None

                    (Config.member_dict[self.name]["Path"] / "Default").mkdir(
                        parents=True, exist_ok=True
                    )
                    shutil.copy(
                        Path(folder) / "config/gui.json",
                        Config.member_dict[self.name]["Path"] / "Default/gui.json",
                    )
                    self.config.set(self.config.MaaSet_Path, folder)

                class RunSetSettingCard(ExpandGroupSettingCard):

                    def __init__(self, config: MaaConfig, parent=None):
                        super().__init__(
                            FluentIcon.SETTING, "运行", "MAA运行调控选项", parent
                        )
                        self.config = config

                        self.card_TaskTransitionMethod = ComboBoxSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="任务切换方式",
                            content="相邻两个任务间的切换方式，使用“详细”配置的用户固定为“重启模拟器”",
                            texts=["直接切换账号", "重启明日方舟", "重启模拟器"],
                            qconfig=self.config,
                            configItem=self.config.RunSet_TaskTransitionMethod,
                            parent=self,
                        )
                        self.card_ProxyTimesLimit = SpinBoxSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="用户单日代理次数上限",
                            content="当用户本日代理成功次数达到该阈值时跳过代理，阈值为“0”时视为无代理次数上限",
                            range=(0, 1024),
                            qconfig=self.config,
                            configItem=self.config.RunSet_ProxyTimesLimit,
                            parent=self,
                        )
                        self.card_RunTimesLimit = SpinBoxSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="代理重试次数限制",
                            content="若超过该次数限制仍未完成代理，视为代理失败",
                            range=(1, 1024),
                            qconfig=self.config,
                            configItem=self.config.RunSet_RunTimesLimit,
                            parent=self,
                        )
                        self.card_AnnihilationTimeLimit = SpinBoxSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="剿灭代理超时限制",
                            content="MAA日志无变化时间超过该阈值视为超时，单位为分钟",
                            range=(1, 1024),
                            qconfig=self.config,
                            configItem=self.config.RunSet_AnnihilationTimeLimit,
                            parent=self,
                        )
                        self.card_RoutineTimeLimit = SpinBoxSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="自动代理超时限制",
                            content="MAA日志无变化时间超过该阈值视为超时，单位为分钟",
                            range=(1, 1024),
                            qconfig=self.config,
                            configItem=self.config.RunSet_RoutineTimeLimit,
                            parent=self,
                        )
                        self.card_AnnihilationWeeklyLimit = SwitchSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="每周剿灭仅执行到上限",
                            content="每周剿灭模式执行到上限，本周剩下时间不再执行剿灭任务",
                            qconfig=self.config,
                            configItem=self.config.RunSet_AnnihilationWeeklyLimit,
                            parent=self,
                        )
                        self.card_AutoUpdateMaa = SwitchSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="自动代理时自动更新MAA",
                            content="执行自动代理任务时自动更新MAA，关闭后仍会进行MAA版本检查",
                            qconfig=self.config,
                            configItem=self.config.RunSet_AutoUpdateMaa,
                            parent=self,
                        )

                        widget = QWidget()
                        Layout = QVBoxLayout(widget)
                        Layout.addWidget(self.card_TaskTransitionMethod)
                        Layout.addWidget(self.card_ProxyTimesLimit)
                        Layout.addWidget(self.card_RunTimesLimit)
                        Layout.addWidget(self.card_AnnihilationTimeLimit)
                        Layout.addWidget(self.card_RoutineTimeLimit)
                        Layout.addWidget(self.card_AnnihilationWeeklyLimit)
                        Layout.addWidget(self.card_AutoUpdateMaa)
                        self.viewLayout.setContentsMargins(0, 0, 0, 0)
                        self.viewLayout.setSpacing(0)
                        self.addGroupWidget(widget)

            class UserManager(HeaderCardWidget):
                """用户管理父页面"""

                def __init__(self, name: str, parent=None):
                    super().__init__(parent)

                    self.setObjectName(f"{name}_用户管理")
                    self.setTitle("下属用户")
                    self.name = name

                    self.tools = CommandBar()
                    self.user_manager = self.UserSettingBox(self.name, self)

                    # 逐个添加动作
                    self.tools.addActions(
                        [
                            Action(
                                FluentIcon.ADD_TO, "新建用户", triggered=self.add_user
                            ),
                            Action(
                                FluentIcon.REMOVE_FROM,
                                "删除用户",
                                triggered=self.del_user,
                            ),
                        ]
                    )
                    self.tools.addSeparator()
                    self.tools.addActions(
                        [
                            Action(
                                FluentIcon.LEFT_ARROW,
                                "向前移动",
                                triggered=self.left_user,
                            ),
                            Action(
                                FluentIcon.RIGHT_ARROW,
                                "向后移动",
                                triggered=self.right_user,
                            ),
                        ]
                    )

                    layout = QVBoxLayout()
                    layout.addWidget(self.tools)
                    layout.addWidget(self.user_manager)
                    self.viewLayout.addLayout(layout)

                def add_user(self):
                    """添加一个用户"""

                    index = len(Config.member_dict[self.name]["UserData"]) + 1

                    user_config = MaaUserConfig()
                    user_config.load(
                        Config.member_dict[self.name]["Path"]
                        / f"UserData/用户_{index}/config.json",
                        user_config,
                    )
                    user_config.save()

                    Config.member_dict[self.name]["UserData"][f"用户_{index}"] = {
                        "Path": Config.member_dict[self.name]["Path"]
                        / f"UserData/用户_{index}",
                        "Config": user_config,
                    }

                    self.user_manager.add_userSettingBox(index)
                    self.user_manager.switch_SettingBox(f"用户_{index}")

                    logger.success(f"{self.name} 用户_{index} 添加成功")
                    MainInfoBar.push_info_bar(
                        "success", "操作成功", f"{self.name} 添加 用户_{index}", 3000
                    )

                def del_user(self):
                    """删除一个用户"""

                    name = self.user_manager.pivot.currentRouteKey()

                    if name == None:
                        logger.warning("未选择用户")
                        MainInfoBar.push_info_bar(
                            "warning", "未选择用户", "请先选择一个用户", 5000
                        )
                        return None
                    if name == "用户仪表盘":
                        logger.warning("试图删除用户仪表盘")
                        MainInfoBar.push_info_bar(
                            "warning", "未选择用户", "请勿尝试删除用户仪表盘", 5000
                        )
                        return None

                    if self.name in Config.running_list:
                        logger.warning("所属脚本正在运行")
                        MainInfoBar.push_info_bar(
                            "warning", "所属脚本正在运行", "请先停止任务", 5000
                        )
                        return None

                    choice = MessageBox(
                        "确认",
                        f"确定要删除 {name} 吗？",
                        self.window(),
                    )
                    if choice.exec():

                        self.user_manager.clear_SettingBox()

                        shutil.rmtree(
                            Config.member_dict[self.name]["UserData"][name]["Path"]
                        )
                        for i in range(
                            int(name[3:]) + 1,
                            len(Config.member_dict[self.name]["UserData"]) + 1,
                        ):
                            if Config.member_dict[self.name]["UserData"][f"用户_{i}"][
                                "Path"
                            ].exists():
                                Config.member_dict[self.name]["UserData"][f"用户_{i}"][
                                    "Path"
                                ].rename(
                                    Config.member_dict[self.name]["UserData"][
                                        f"用户_{i}"
                                    ]["Path"].with_name(f"用户_{i-1}")
                                )

                        self.user_manager.show_SettingBox(
                            f"用户_{max(int(name[3:]) - 1, 1)}"
                        )

                        logger.success(f"{self.name} {name} 删除成功")
                        MainInfoBar.push_info_bar(
                            "success", "操作成功", f"{self.name} 删除 {name}", 3000
                        )

                def left_user(self):
                    """向前移动用户"""

                    name = self.user_manager.pivot.currentRouteKey()

                    if name == None:
                        logger.warning("未选择用户")
                        MainInfoBar.push_info_bar(
                            "warning", "未选择用户", "请先选择一个用户", 5000
                        )
                        return None
                    if name == "用户仪表盘":
                        logger.warning("试图移动用户仪表盘")
                        MainInfoBar.push_info_bar(
                            "warning", "未选择用户", "请勿尝试移动用户仪表盘", 5000
                        )
                        return None

                    index = int(name[3:])

                    if index == 1:
                        logger.warning("向前移动用户时已到达最左端")
                        MainInfoBar.push_info_bar(
                            "warning", "已经是第一个用户", "无法向前移动", 5000
                        )
                        return None

                    if self.name in Config.running_list:
                        logger.warning("所属脚本正在运行")
                        MainInfoBar.push_info_bar(
                            "warning", "所属脚本正在运行", "请先停止任务", 5000
                        )
                        return None

                    self.user_manager.clear_SettingBox()

                    Config.member_dict[self.name]["UserData"][name]["Path"].rename(
                        Config.member_dict[self.name]["UserData"][name][
                            "Path"
                        ].with_name("用户_0")
                    )
                    Config.member_dict[self.name]["UserData"][f"用户_{index-1}"][
                        "Path"
                    ].rename(Config.member_dict[self.name]["UserData"][name]["Path"])
                    Config.member_dict[self.name]["UserData"][name]["Path"].with_name(
                        "用户_0"
                    ).rename(
                        Config.member_dict[self.name]["UserData"][f"用户_{index-1}"][
                            "Path"
                        ]
                    )

                    self.user_manager.show_SettingBox(f"用户_{index - 1}")

                    logger.success(f"{self.name} {name} 前移成功")
                    MainInfoBar.push_info_bar(
                        "success", "操作成功", f"{self.name} 前移 {name}", 3000
                    )

                def right_user(self):
                    """向后移动用户"""

                    name = self.user_manager.pivot.currentRouteKey()

                    if name == None:
                        logger.warning("未选择用户")
                        MainInfoBar.push_info_bar(
                            "warning", "未选择用户", "请先选择一个用户", 5000
                        )
                        return None
                    if name == "用户仪表盘":
                        logger.warning("试图删除用户仪表盘")
                        MainInfoBar.push_info_bar(
                            "warning", "未选择用户", "请勿尝试移动用户仪表盘", 5000
                        )
                        return None

                    index = int(name[3:])

                    if index == len(Config.member_dict[self.name]["UserData"]):
                        logger.warning("向后移动用户时已到达最右端")
                        MainInfoBar.push_info_bar(
                            "warning", "已经是最后一个用户", "无法向后移动", 5000
                        )
                        return None

                    if self.name in Config.running_list:
                        logger.warning("所属脚本正在运行")
                        MainInfoBar.push_info_bar(
                            "warning", "所属脚本正在运行", "请先停止任务", 5000
                        )
                        return None

                    self.user_manager.clear_SettingBox()

                    Config.member_dict[self.name]["UserData"][name]["Path"].rename(
                        Config.member_dict[self.name]["UserData"][name][
                            "Path"
                        ].with_name("用户_0")
                    )
                    Config.member_dict[self.name]["UserData"][f"用户_{index+1}"][
                        "Path"
                    ].rename(Config.member_dict[self.name]["UserData"][name]["Path"])
                    Config.member_dict[self.name]["UserData"][name]["Path"].with_name(
                        "用户_0"
                    ).rename(
                        Config.member_dict[self.name]["UserData"][f"用户_{index+1}"][
                            "Path"
                        ]
                    )

                    self.user_manager.show_SettingBox(f"用户_{index + 1}")

                    logger.success(f"{self.name} {name} 后移成功")
                    MainInfoBar.push_info_bar(
                        "success", "操作成功", f"{self.name} 后移 {name}", 3000
                    )

                class UserSettingBox(QWidget):
                    """用户管理子页面组"""

                    def __init__(self, name: str, parent=None):
                        super().__init__(parent)

                        self.setObjectName("用户管理")
                        self.name = name

                        self.pivot = Pivot(self)
                        self.stackedWidget = QStackedWidget(self)
                        self.Layout = QVBoxLayout(self)

                        self.script_list: List[
                            MemberManager.MemberSettingBox.MaaSettingBox.UserManager.UserSettingBox.UserMemberSettingBox
                        ] = []

                        self.user_dashboard = self.UserDashboard(self.name, self)
                        self.user_dashboard.switch_to.connect(self.switch_SettingBox)
                        self.stackedWidget.addWidget(self.user_dashboard)
                        self.pivot.addItem(routeKey="用户仪表盘", text="用户仪表盘")

                        self.Layout.addWidget(self.pivot, 0, Qt.AlignHCenter)
                        self.Layout.addWidget(self.stackedWidget)
                        self.Layout.setContentsMargins(0, 0, 0, 0)

                        self.pivot.currentItemChanged.connect(
                            lambda index: self.switch_SettingBox(
                                index, if_change_pivot=False
                            )
                        )

                        self.show_SettingBox("用户仪表盘")

                    def show_SettingBox(self, index: str) -> None:
                        """加载所有子界面"""

                        Config.search_maa_user(self.name)

                        for name in Config.member_dict[self.name]["UserData"].keys():
                            self.add_userSettingBox(name[3:])

                        self.switch_SettingBox(index)

                    def switch_SettingBox(
                        self, index: str, if_change_pivot: bool = True
                    ) -> None:
                        """切换到指定的子界面"""

                        if len(Config.member_dict[self.name]["UserData"]) == 0:
                            index = "用户仪表盘"

                        if index != "用户仪表盘" and int(index[3:]) > len(
                            Config.member_dict[self.name]["UserData"]
                        ):
                            return None

                        if index == "用户仪表盘":
                            self.user_dashboard.load_info()

                        if if_change_pivot:
                            self.pivot.setCurrentItem(index)
                        self.stackedWidget.setCurrentWidget(
                            self.user_dashboard
                            if index == "用户仪表盘"
                            else self.script_list[int(index[3:]) - 1]
                        )

                    def clear_SettingBox(self) -> None:
                        """清空所有子界面"""

                        for sub_interface in self.script_list:
                            Config.gameid_refreshed.disconnect(
                                sub_interface.refresh_gameid
                            )
                            Config.PASSWORD_refreshed.disconnect(
                                sub_interface.refresh_password
                            )
                            self.stackedWidget.removeWidget(sub_interface)
                            sub_interface.deleteLater()
                        self.script_list.clear()
                        self.pivot.clear()
                        self.user_dashboard.dashboard.setRowCount(0)
                        self.stackedWidget.addWidget(self.user_dashboard)
                        self.pivot.addItem(routeKey="用户仪表盘", text="用户仪表盘")

                    def add_userSettingBox(self, uid: int) -> None:
                        """添加一个用户设置界面"""

                        maa_setting_box = self.UserMemberSettingBox(
                            self.name, uid, self
                        )

                        self.script_list.append(maa_setting_box)

                        self.stackedWidget.addWidget(self.script_list[-1])

                        self.pivot.addItem(routeKey=f"用户_{uid}", text=f"用户 {uid}")

                    class UserDashboard(HeaderCardWidget):
                        """用户仪表盘页面"""

                        switch_to = Signal(str)

                        def __init__(self, name: str, parent=None):
                            super().__init__(parent)
                            self.setObjectName("用户仪表盘")
                            self.setTitle("用户仪表盘")
                            self.name = name

                            self.dashboard = TableWidget(self)
                            self.dashboard.setColumnCount(11)
                            self.dashboard.setHorizontalHeaderLabels(
                                [
                                    "用户名",
                                    "账号ID",
                                    "密码",
                                    "状态",
                                    "代理情况",
                                    "给药量",
                                    "关卡选择",
                                    "备选 - 1",
                                    "备选 - 2",
                                    "剩余理智",
                                    "详",
                                ]
                            )
                            self.dashboard.setEditTriggers(TableWidget.NoEditTriggers)
                            self.dashboard.verticalHeader().setVisible(False)
                            for col in range(6):
                                self.dashboard.horizontalHeader().setSectionResizeMode(
                                    col, QHeaderView.ResizeMode.ResizeToContents
                                )
                            for col in range(6, 10):
                                self.dashboard.horizontalHeader().setSectionResizeMode(
                                    col, QHeaderView.ResizeMode.Stretch
                                )
                            self.dashboard.horizontalHeader().setSectionResizeMode(
                                10, QHeaderView.ResizeMode.Fixed
                            )
                            self.dashboard.setColumnWidth(10, 32)

                            self.viewLayout.addWidget(self.dashboard)
                            self.viewLayout.setContentsMargins(3, 0, 3, 3)

                            Config.PASSWORD_refreshed.connect(self.load_info)

                        def load_info(self):

                            self.user_data = Config.member_dict[self.name]["UserData"]

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

                                button = PrimaryToolButton(
                                    FluentIcon.CHEVRON_RIGHT, self
                                )
                                button.setFixedSize(32, 32)
                                button.clicked.connect(
                                    partial(self.switch_to.emit, name)
                                )

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
                                    QTableWidgetItem(
                                        str(config.get(config.Info_MedicineNumb))
                                    ),
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
                                                    Config.gameid_dict["ALL"][
                                                        "value"
                                                    ].index(
                                                        config.get(
                                                            config.Info_GameId_Remain
                                                        )
                                                    )
                                                ]
                                            )
                                            if config.get(config.Info_GameId_Remain)
                                            in Config.gameid_dict["ALL"]["value"]
                                            else config.get(config.Info_GameId_Remain)
                                        )
                                    ),
                                )
                                self.dashboard.setCellWidget(
                                    int(name[3:]) - 1, 10, button
                                )

                    class UserMemberSettingBox(HeaderCardWidget):
                        """用户管理子页面"""

                        def __init__(self, name: str, uid: int, parent=None):
                            super().__init__(parent)

                            self.setObjectName(f"用户_{uid}")
                            self.setTitle(f"用户 {uid}")
                            self.name = name
                            self.config = Config.member_dict[self.name]["UserData"][
                                f"用户_{uid}"
                            ]["Config"]
                            self.user_path = Config.member_dict[self.name]["UserData"][
                                f"用户_{uid}"
                            ]["Path"]

                            self.card_Name = LineEditSettingCard(
                                icon=FluentIcon.PEOPLE,
                                title="用户名",
                                content="用户的昵称",
                                text="请输入用户名",
                                qconfig=self.config,
                                configItem=self.config.Info_Name,
                                parent=self,
                            )
                            self.card_Id = LineEditSettingCard(
                                icon=FluentIcon.PEOPLE,
                                title="账号ID",
                                content="官服输入手机号，B服输入B站ID",
                                text="请输入账号ID",
                                qconfig=self.config,
                                configItem=self.config.Info_Id,
                                parent=self,
                            )
                            self.card_Mode = ComboBoxSettingCard(
                                icon=FluentIcon.DICTIONARY,
                                title="用户配置模式",
                                content="用户信息配置模式",
                                texts=["简洁", "详细"],
                                qconfig=self.config,
                                configItem=self.config.Info_Mode,
                                parent=self,
                            )
                            self.card_GameIdMode = ComboBoxSettingCard(
                                icon=FluentIcon.DICTIONARY,
                                title="关卡配置模式",
                                content="刷理智关卡号的配置模式",
                                texts=["固定"],
                                qconfig=self.config,
                                configItem=self.config.Info_GameIdMode,
                                parent=self,
                            )
                            self.card_Server = ComboBoxSettingCard(
                                icon=FluentIcon.PROJECTOR,
                                title="服务器",
                                content="选择服务器类型",
                                texts=["官服", "B服"],
                                qconfig=self.config,
                                configItem=self.config.Info_Server,
                                parent=self,
                            )
                            self.card_Status = SwitchSettingCard(
                                icon=FluentIcon.CHECKBOX,
                                title="用户状态",
                                content="启用或禁用该用户",
                                qconfig=self.config,
                                configItem=self.config.Info_Status,
                                parent=self,
                            )
                            self.card_RemainedDay = SpinBoxSettingCard(
                                icon=FluentIcon.CALENDAR,
                                title="剩余天数",
                                content="剩余代理天数，-1表示无限代理",
                                range=(-1, 1024),
                                qconfig=self.config,
                                configItem=self.config.Info_RemainedDay,
                                parent=self,
                            )
                            self.card_Annihilation = PushAndSwitchButtonSettingCard(
                                icon=FluentIcon.CAFE,
                                title="剿灭代理",
                                content="剿灭代理子任务相关设置",
                                text="设置具体配置",
                                qconfig=self.config,
                                configItem=self.config.Info_Annihilation,
                                parent=self,
                            )
                            self.card_Routine = PushAndSwitchButtonSettingCard(
                                icon=FluentIcon.CAFE,
                                title="日常代理",
                                content="日常代理子任务相关设置",
                                text="设置具体配置",
                                qconfig=self.config,
                                configItem=self.config.Info_Routine,
                                parent=self,
                            )
                            self.card_InfrastMode = PushAndComboBoxSettingCard(
                                icon=FluentIcon.CAFE,
                                title="基建模式",
                                content="配置文件仅在自定义基建中生效",
                                text="选择配置文件",
                                texts=[
                                    "常规模式",
                                    "一键轮休",
                                    "自定义基建",
                                ],
                                qconfig=self.config,
                                configItem=self.config.Info_InfrastMode,
                                parent=self,
                            )
                            self.card_Password = PasswordLineEditSettingCard(
                                icon=FluentIcon.VPN,
                                title="密码",
                                content="仅用于用户密码记录",
                                text="请输入用户密码",
                                algorithm="AUTO",
                                qconfig=self.config,
                                configItem=self.config.Info_Password,
                                parent=self,
                            )
                            self.card_Notes = LineEditSettingCard(
                                icon=FluentIcon.PENCIL_INK,
                                title="备注",
                                content="用户备注信息",
                                text="请输入备注",
                                qconfig=self.config,
                                configItem=self.config.Info_Notes,
                                parent=self,
                            )
                            self.card_MedicineNumb = SpinBoxSettingCard(
                                icon=FluentIcon.GAME,
                                title="吃理智药",
                                content="吃理智药次数，输入0以关闭",
                                range=(0, 1024),
                                qconfig=self.config,
                                configItem=self.config.Info_MedicineNumb,
                                parent=self,
                            )
                            self.card_SeriesNumb = SpinBoxSettingCard(
                                icon=FluentIcon.GAME,
                                title="连战次数",
                                content="连战次数较大时建议搭配剩余理智关卡使用",
                                range=(1, 6),
                                qconfig=self.config,
                                configItem=self.config.Info_SeriesNumb,
                                parent=self,
                            )
                            self.card_GameId = EditableComboBoxSettingCard(
                                icon=FluentIcon.GAME,
                                title="关卡选择",
                                content="按下回车以添加自定义关卡号",
                                value=Config.gameid_dict["ALL"]["value"],
                                texts=Config.gameid_dict["ALL"]["text"],
                                qconfig=self.config,
                                configItem=self.config.Info_GameId,
                                parent=self,
                            )
                            self.card_GameId_1 = EditableComboBoxSettingCard(
                                icon=FluentIcon.GAME,
                                title="备选关卡 - 1",
                                content="按下回车以添加自定义关卡号",
                                value=Config.gameid_dict["ALL"]["value"],
                                texts=Config.gameid_dict["ALL"]["text"],
                                qconfig=self.config,
                                configItem=self.config.Info_GameId_1,
                                parent=self,
                            )
                            self.card_GameId_2 = EditableComboBoxSettingCard(
                                icon=FluentIcon.GAME,
                                title="备选关卡 - 2",
                                content="按下回车以添加自定义关卡号",
                                value=Config.gameid_dict["ALL"]["value"],
                                texts=Config.gameid_dict["ALL"]["text"],
                                qconfig=self.config,
                                configItem=self.config.Info_GameId_2,
                                parent=self,
                            )
                            self.card_GameId_Remain = EditableComboBoxSettingCard(
                                icon=FluentIcon.GAME,
                                title="剩余理智关卡",
                                content="按下回车以添加自定义关卡号",
                                value=Config.gameid_dict["ALL"]["value"],
                                texts=[
                                    "不使用" if _ == "当前/上次" else _
                                    for _ in Config.gameid_dict["ALL"]["text"]
                                ],
                                qconfig=self.config,
                                configItem=self.config.Info_GameId_Remain,
                                parent=self,
                            )

                            self.card_UserLable = UserLableSettingCard(
                                icon=FluentIcon.INFO,
                                title="状态信息",
                                content="用户的代理情况汇总",
                                qconfig=self.config,
                                configItems={
                                    "LastProxyDate": self.config.Data_LastProxyDate,
                                    "LastAnnihilationDate": self.config.Data_LastAnnihilationDate,
                                    "ProxyTimes": self.config.Data_ProxyTimes,
                                    "IfPassCheck": self.config.Data_IfPassCheck,
                                },
                                parent=self,
                            )

                            h1_layout = QHBoxLayout()
                            h1_layout.addWidget(self.card_Name)
                            h1_layout.addWidget(self.card_Id)
                            h2_layout = QHBoxLayout()
                            h2_layout.addWidget(self.card_Mode)
                            h2_layout.addWidget(self.card_GameIdMode)
                            h2_layout.addWidget(self.card_Server)
                            h3_layout = QHBoxLayout()
                            h3_layout.addWidget(self.card_Status)
                            h3_layout.addWidget(self.card_RemainedDay)
                            h4_layout = QHBoxLayout()
                            h4_layout.addWidget(self.card_Annihilation)
                            h4_layout.addWidget(self.card_Routine)
                            h4_layout.addWidget(self.card_InfrastMode)
                            h5_layout = QHBoxLayout()
                            h5_layout.addWidget(self.card_Password)
                            h5_layout.addWidget(self.card_Notes)
                            h6_layout = QHBoxLayout()
                            h6_layout.addWidget(self.card_MedicineNumb)
                            h6_layout.addWidget(self.card_SeriesNumb)
                            h7_layout = QHBoxLayout()
                            h7_layout.addWidget(self.card_GameId)
                            h7_layout.addWidget(self.card_GameId_1)
                            h8_layout = QHBoxLayout()
                            h8_layout.addWidget(self.card_GameId_2)
                            h8_layout.addWidget(self.card_GameId_Remain)

                            Layout = QVBoxLayout()
                            Layout.addLayout(h1_layout)
                            Layout.addLayout(h2_layout)
                            Layout.addLayout(h3_layout)
                            Layout.addWidget(self.card_UserLable)
                            Layout.addLayout(h4_layout)
                            Layout.addLayout(h5_layout)
                            Layout.addLayout(h6_layout)
                            Layout.addLayout(h7_layout)
                            Layout.addLayout(h8_layout)

                            self.viewLayout.addLayout(Layout)
                            self.viewLayout.setContentsMargins(3, 0, 3, 3)

                            self.card_Mode.comboBox.currentIndexChanged.connect(
                                self.switch_mode
                            )
                            self.card_Annihilation.clicked.connect(
                                lambda: self.set_maa("Annihilation")
                            )
                            self.card_Routine.clicked.connect(
                                lambda: self.set_maa("Routine")
                            )
                            self.card_InfrastMode.clicked.connect(
                                self.set_infrastructure
                            )
                            Config.gameid_refreshed.connect(self.refresh_gameid)
                            Config.PASSWORD_refreshed.connect(self.refresh_password)

                            self.switch_mode()

                        def switch_mode(self) -> None:

                            if self.config.get(self.config.Info_Mode) == "简洁":

                                self.card_Routine.setVisible(False)
                                self.card_Server.setVisible(True)
                                self.card_Annihilation.button.setVisible(False)
                                self.card_InfrastMode.setVisible(True)

                            elif self.config.get(self.config.Info_Mode) == "详细":

                                self.card_Server.setVisible(False)
                                self.card_InfrastMode.setVisible(False)
                                self.card_Annihilation.button.setVisible(True)
                                self.card_Routine.setVisible(True)

                        def refresh_gameid(self):

                            self.card_GameId.reLoadOptions(
                                Config.gameid_dict["ALL"]["value"],
                                Config.gameid_dict["ALL"]["text"],
                            )
                            self.card_GameId_1.reLoadOptions(
                                Config.gameid_dict["ALL"]["value"],
                                Config.gameid_dict["ALL"]["text"],
                            )
                            self.card_GameId_2.reLoadOptions(
                                Config.gameid_dict["ALL"]["value"],
                                Config.gameid_dict["ALL"]["text"],
                            )
                            self.card_GameId_Remain.reLoadOptions(
                                Config.gameid_dict["ALL"]["value"],
                                [
                                    "不使用" if _ == "当前/上次" else _
                                    for _ in Config.gameid_dict["ALL"]["text"]
                                ],
                            )

                        def refresh_password(self):

                            self.card_Password.setValue(
                                self.card_Password.qconfig.get(
                                    self.card_Password.configItem
                                )
                            )

                        def set_infrastructure(self) -> None:
                            """配置自定义基建"""

                            if self.name in Config.running_list:
                                logger.warning("所属脚本正在运行")
                                MainInfoBar.push_info_bar(
                                    "warning", "所属脚本正在运行", "请先停止任务", 5000
                                )
                                return None

                            file_path, _ = QFileDialog.getOpenFileName(
                                self,
                                "选择自定义基建文件",
                                ".",
                                "JSON 文件 (*.json)",
                            )
                            if file_path != "":
                                (self.user_path / "Infrastructure").mkdir(
                                    parents=True, exist_ok=True
                                )
                                shutil.copy(
                                    file_path,
                                    self.user_path
                                    / "Infrastructure/infrastructure.json",
                                )
                            else:
                                logger.warning("未选择自定义基建文件")
                                MainInfoBar.push_info_bar(
                                    "warning", "警告", "未选择自定义基建文件", 5000
                                )

                        def set_maa(self, mode: str) -> None:
                            """配置MAA子配置"""

                            if self.name in Config.running_list:
                                logger.warning("所属脚本正在运行")
                                MainInfoBar.push_info_bar(
                                    "warning", "所属脚本正在运行", "请先停止任务", 5000
                                )
                                return None

                            TaskManager.add_task(
                                "设置MAA_用户",
                                self.name,
                                {
                                    "SetMaaInfo": {
                                        "Path": self.user_path / mode,
                                    }
                                },
                            )
