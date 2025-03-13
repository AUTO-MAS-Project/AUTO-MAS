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
AUTO_MAA脚本管理界面
v4.2
作者：DLmaster_361
"""

from loguru import logger
from PySide6.QtWidgets import (
    QWidget,
    QFileDialog,
    QTableWidgetItem,
    QHeaderView,
    QVBoxLayout,
    QStackedWidget,
)
from qfluentwidgets import (
    Action,
    qconfig,
    TableWidget,
    Pivot,
    ComboBox,
    ScrollArea,
    FluentIcon,
    MessageBox,
    HeaderCardWidget,
    CommandBar,
    ExpandGroupSettingCard,
    ComboBoxSettingCard,
    PushSettingCard,
)
from PySide6.QtCore import Qt
import requests
import time
from functools import partial
from pathlib import Path
from typing import List
from datetime import datetime, timedelta
import json
import shutil

from app.core import Config, MainInfoBar, TaskManager
from app.services import Crypto
from app.utils import DownloadManager
from .Widget import (
    LineEditMessageBox,
    LineEditSettingCard,
    SpinBoxSettingCard,
    ComboBoxMessageBox,
)


class MemberManager(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("脚本管理")

        layout = QVBoxLayout(self)

        self.tools = CommandBar()

        self.member_manager = MemberSettingBox(self)

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
        self.tools.addAction(
            Action(
                FluentIcon.HIDE,
                "显示/隐藏密码",
                checkable=True,
                triggered=self.show_password,
            )
        )

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

                index = len(self.member_manager.search_member()) + 1

                qconfig.load(
                    Config.app_path / f"config/MaaConfig/脚本_{index}/config.json",
                    Config.maa_config,
                )
                Config.clear_maa_config()
                Config.maa_config.save()

                Config.open_database("Maa", f"脚本_{index}")
                Config.init_database("Maa")
                self.member_manager.add_MaaSettingBox(index)
                self.member_manager.switch_SettingBox(index)

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

            member_list = self.member_manager.search_member()
            move_list = [_ for _ in member_list if int(_[0][3:]) > int(name[3:])]

            type = [_[1] for _ in member_list if _[0] == name]
            index = max(int(name[3:]) - 1, 1)

            self.member_manager.clear_SettingBox()

            shutil.rmtree(Config.app_path / f"config/{type[0]}Config/{name}")
            self.change_queue(name, "禁用")
            for member in move_list:
                if (Config.app_path / f"config/{member[1]}Config/{member[0]}").exists():
                    (Config.app_path / f"config/{member[1]}Config/{member[0]}").rename(
                        Config.app_path
                        / f"config/{member[1]}Config/脚本_{int(member[0][3:])-1}",
                    )
                self.change_queue(member[0], f"脚本_{int(member[0][3:])-1}")

            self.member_manager.show_SettingBox(index)

    def left_setting_box(self):
        """向左移动脚本实例"""

        name = self.member_manager.pivot.currentRouteKey()

        if name == None:
            logger.warning("向左移动脚本实例时未选择脚本实例")
            MainInfoBar.push_info_bar(
                "warning", "未选择脚本实例", "请选择一个脚本实例", 5000
            )
            return None

        member_list = self.member_manager.search_member()
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

        type_right = [_[1] for _ in member_list if _[0] == name]
        type_left = [_[1] for _ in member_list if _[0] == f"脚本_{index-1}"]

        self.member_manager.clear_SettingBox()

        (Config.app_path / f"config/{type_right[0]}Config/脚本_{index}").rename(
            Config.app_path / f"config/{type_right[0]}Config/脚本_0"
        )
        self.change_queue(f"脚本_{index}", "脚本_0")
        (Config.app_path / f"config/{type_left[0]}Config/脚本_{index-1}").rename(
            Config.app_path / f"config/{type_left[0]}Config/脚本_{index}"
        )
        self.change_queue(f"脚本_{index-1}", f"脚本_{index}")
        (Config.app_path / f"config/{type_right[0]}Config/脚本_0").rename(
            Config.app_path / f"config/{type_right[0]}Config/脚本_{index-1}"
        )
        self.change_queue("脚本_0", f"脚本_{index-1}")

        self.member_manager.show_SettingBox(index - 1)

    def right_setting_box(self):
        """向右移动脚本实例"""

        name = self.member_manager.pivot.currentRouteKey()

        if name == None:
            logger.warning("向右移动脚本实例时未选择脚本实例")
            MainInfoBar.push_info_bar(
                "warning", "未选择脚本实例", "请选择一个脚本实例", 5000
            )
            return None

        member_list = self.member_manager.search_member()
        index = int(name[3:])

        if index == len(member_list):
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

        type_left = [_[1] for _ in member_list if _[0] == name]
        type_right = [_[1] for _ in member_list if _[0] == f"脚本_{index+1}"]

        self.member_manager.clear_SettingBox()

        (Config.app_path / f"config/{type_left[0]}Config/脚本_{index}").rename(
            Config.app_path / f"config/{type_left[0]}Config/脚本_0",
        )
        self.change_queue(f"脚本_{index}", "脚本_0")
        (Config.app_path / f"config/{type_right[0]}Config/脚本_{index+1}").rename(
            Config.app_path / f"config/{type_right[0]}Config/脚本_{index}",
        )
        self.change_queue(f"脚本_{index+1}", f"脚本_{index}")
        (Config.app_path / f"config/{type_left[0]}Config/脚本_0").rename(
            Config.app_path / f"config/{type_left[0]}Config/脚本_{index+1}",
        )
        self.change_queue("脚本_0", f"脚本_{index+1}")

        self.member_manager.show_SettingBox(index + 1)

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
                for _ in range(3):
                    try:
                        response = requests.get(
                            "https://mirrorc.top/api/resources/MAA/latest?user_agent=MaaWpfGui&os=win&arch=x64&channel=stable"
                        )
                        maa_info = response.json()
                        break
                    except Exception as e:
                        err = e
                        time.sleep(0.1)
                else:
                    choice = MessageBox(
                        "错误",
                        f"获取版本信息时出错：\n{err}",
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
                    [],
                    {
                        "thread_numb": Config.global_config.get(
                            Config.global_config.update_ThreadNumb
                        )
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
                self.member_manager.script_list[
                    int(self.member_manager.pivot.currentRouteKey()[3:]) - 1
                ].user_setting.user_list.update_user_info("normal")
                self.key.setIcon(FluentIcon.VIEW)
                self.key.setChecked(True)
            else:
                Config.PASSWORD = ""
                self.member_manager.script_list[
                    int(self.member_manager.pivot.currentRouteKey()[3:]) - 1
                ].user_setting.user_list.update_user_info("normal")
                self.key.setIcon(FluentIcon.HIDE)
                self.key.setChecked(False)
        else:
            Config.PASSWORD = ""
            self.member_manager.script_list[
                int(self.member_manager.pivot.currentRouteKey()[3:]) - 1
            ].user_setting.user_list.update_user_info("normal")
            self.key.setIcon(FluentIcon.HIDE)
            self.key.setChecked(False)

    def change_queue(self, old: str, new: str) -> None:
        """修改调度队列配置文件的队列参数"""

        if (Config.app_path / "config/QueueConfig").exists():
            for json_file in (Config.app_path / "config/QueueConfig").glob("*.json"):
                with json_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)

                for i in range(10):
                    if data["Queue"][f"Member_{i+1}"] == old:
                        data["Queue"][f"Member_{i+1}"] = new

                with json_file.open("w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)

    def refresh(self):
        """刷新脚本实例界面"""

        if len(self.member_manager.search_member()) == 0:
            index = 0
        else:
            index = int(self.member_manager.pivot.currentRouteKey()[3:])
        self.member_manager.switch_SettingBox(index)


class MemberSettingBox(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("脚本管理")

        self.pivot = Pivot(self)
        self.stackedWidget = QStackedWidget(self)
        self.Layout = QVBoxLayout(self)

        self.script_list: List[MaaSettingBox] = []

        self.Layout.addWidget(self.pivot, 0, Qt.AlignHCenter)
        self.Layout.addWidget(self.stackedWidget)
        self.Layout.setContentsMargins(0, 0, 0, 0)

        self.pivot.currentItemChanged.connect(
            lambda index: self.switch_SettingBox(int(index[3:]), if_chang_pivot=False)
        )

        self.show_SettingBox(1)

    def show_SettingBox(self, index) -> None:
        """加载所有子界面"""

        member_list = self.search_member()

        qconfig.load(
            Config.app_path / "config/临时.json",
            Config.maa_config,
        )
        Config.clear_maa_config()
        for member in member_list:
            if member[1] == "Maa":
                Config.open_database(member[1], member[0])
                self.add_MaaSettingBox(int(member[0][3:]))
        if (Config.app_path / "config/临时.json").exists():
            (Config.app_path / "config/临时.json").unlink()

        self.switch_SettingBox(index)

    def switch_SettingBox(self, index: int, if_chang_pivot: bool = True) -> None:
        """切换到指定的子界面"""

        member_list = self.search_member()

        if len(member_list) == 0:
            return None

        if index > len(member_list):
            return None

        type = [_[1] for _ in member_list if _[0] == f"脚本_{index}"]

        qconfig.load(
            Config.app_path
            / f"config/{type[0]}Config/{self.script_list[index-1].objectName()}/config.json",
            Config.maa_config,
        )
        Config.open_database(type[0], self.script_list[index - 1].objectName())
        self.script_list[index - 1].user_setting.user_list.update_user_info("normal")

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
        qconfig.load(
            Config.app_path / "config/临时.json",
            Config.maa_config,
        )
        Config.clear_maa_config()
        if (Config.app_path / "config/临时.json").exists():
            (Config.app_path / "config/临时.json").unlink()
        Config.close_database()

    def add_MaaSettingBox(self, uid: int) -> None:
        """添加一个MAA设置界面"""

        maa_setting_box = MaaSettingBox(uid, self)

        self.script_list.append(maa_setting_box)

        self.stackedWidget.addWidget(self.script_list[-1])

        self.pivot.addItem(routeKey=f"脚本_{uid}", text=f"脚本 {uid}")

    def search_member(self) -> list:
        """搜索所有脚本实例"""

        member_list = []

        if (Config.app_path / "config/MaaConfig").exists():
            for subdir in (Config.app_path / "config/MaaConfig").iterdir():
                if subdir.is_dir():
                    member_list.append([subdir.name, "Maa"])

        return member_list


class MaaSettingBox(QWidget):

    def __init__(self, uid: int, parent=None):
        super().__init__(parent)

        self.setObjectName(f"脚本_{uid}")

        layout = QVBoxLayout()

        scrollArea = ScrollArea()
        scrollArea.setWidgetResizable(True)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)

        self.app_setting = self.AppSettingCard(self, self.objectName())
        self.user_setting = self.UserSettingCard(self, self.objectName())

        content_layout.addWidget(self.app_setting)
        content_layout.addWidget(self.user_setting)
        content_layout.addStretch(1)

        scrollArea.setWidget(content_widget)

        layout.addWidget(scrollArea)

        self.setLayout(layout)

    class AppSettingCard(HeaderCardWidget):

        def __init__(self, parent=None, name: str = None):
            super().__init__(parent)

            self.setTitle("MAA实例")

            self.name = name

            Layout = QVBoxLayout()

            self.card_Name = LineEditSettingCard(
                "请输入实例名称",
                FluentIcon.EDIT,
                "实例名称",
                "用于标识MAA实例的名称",
                Config.maa_config.MaaSet_Name,
            )
            self.card_Path = PushSettingCard(
                "选择文件夹",
                FluentIcon.FOLDER,
                "MAA目录",
                Config.maa_config.get(Config.maa_config.MaaSet_Path),
            )
            self.card_Set = PushSettingCard(
                "设置",
                FluentIcon.HOME,
                "MAA全局配置",
                "简洁模式下MAA将继承全局配置",
            )
            self.RunSet = self.RunSetSettingCard(self)

            self.card_Path.clicked.connect(self.PathClicked)
            Config.maa_config.MaaSet_Path.valueChanged.connect(
                lambda: self.card_Path.setContent(
                    Config.maa_config.get(Config.maa_config.MaaSet_Path)
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
                Config.maa_config.get(Config.maa_config.MaaSet_Path),
            )
            if (
                not folder
                or Config.maa_config.get(Config.maa_config.MaaSet_Path) == folder
            ):
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

            (Config.app_path / f"config/MaaConfig/{self.name}/Default").mkdir(
                parents=True, exist_ok=True
            )
            shutil.copy(
                Path(folder) / "config/gui.json",
                Config.app_path / f"config/MaaConfig/{self.name}/Default/gui.json",
            )
            Config.maa_config.set(Config.maa_config.MaaSet_Path, folder)
            self.card_Path.setContent(folder)

        class RunSetSettingCard(ExpandGroupSettingCard):

            def __init__(self, parent=None):
                super().__init__(FluentIcon.SETTING, "运行", "MAA运行调控选项", parent)

                self.card_TaskTransitionMethod = ComboBoxSettingCard(
                    configItem=Config.maa_config.RunSet_TaskTransitionMethod,
                    icon=FluentIcon.PAGE_RIGHT,
                    title="任务切换方式",
                    content="简洁用户列表下相邻两个任务间的切换方式",
                    texts=["直接切换账号", "重启明日方舟", "重启模拟器"],
                )
                self.ProxyTimesLimit = SpinBoxSettingCard(
                    (0, 1024),
                    FluentIcon.PAGE_RIGHT,
                    "用户单日代理次数上限",
                    "当用户本日代理成功次数超过该阈值时跳过代理，阈值为“0”时视为无代理次数上限",
                    Config.maa_config.RunSet_ProxyTimesLimit,
                )
                self.AnnihilationTimeLimit = SpinBoxSettingCard(
                    (1, 1024),
                    FluentIcon.PAGE_RIGHT,
                    "剿灭代理超时限制",
                    "MAA日志无变化时间超过该阈值视为超时，单位为分钟",
                    Config.maa_config.RunSet_AnnihilationTimeLimit,
                )
                self.RoutineTimeLimit = SpinBoxSettingCard(
                    (1, 1024),
                    FluentIcon.PAGE_RIGHT,
                    "自动代理超时限制",
                    "MAA日志无变化时间超过该阈值视为超时，单位为分钟",
                    Config.maa_config.RunSet_RoutineTimeLimit,
                )
                self.RunTimesLimit = SpinBoxSettingCard(
                    (1, 1024),
                    FluentIcon.PAGE_RIGHT,
                    "代理重试次数限制",
                    "若超过该次数限制仍未完成代理，视为代理失败",
                    Config.maa_config.RunSet_RunTimesLimit,
                )

                widget = QWidget()
                Layout = QVBoxLayout(widget)
                Layout.addWidget(self.card_TaskTransitionMethod)
                Layout.addWidget(self.ProxyTimesLimit)
                Layout.addWidget(self.AnnihilationTimeLimit)
                Layout.addWidget(self.RoutineTimeLimit)
                Layout.addWidget(self.RunTimesLimit)
                self.viewLayout.setContentsMargins(0, 0, 0, 0)
                self.viewLayout.setSpacing(0)
                self.addGroupWidget(widget)

    class UserSettingCard(HeaderCardWidget):

        def __init__(self, parent=None, name: str = None):
            super().__init__(parent)

            self.setTitle("用户列表")

            self.name = name

            Layout = QVBoxLayout()

            self.user_list = self.UserListBox(self.name, self)

            self.tools = CommandBar()
            self.tools.addActions(
                [
                    Action(
                        FluentIcon.ADD, "新建用户", triggered=self.user_list.add_user
                    ),
                    Action(
                        FluentIcon.REMOVE, "删除用户", triggered=self.user_list.del_user
                    ),
                ]
            )
            self.tools.addSeparator()
            self.tools.addActions(
                [
                    Action(FluentIcon.UP, "向上移动", triggered=self.user_list.up_user),
                    Action(
                        FluentIcon.DOWN, "向下移动", triggered=self.user_list.down_user
                    ),
                ]
            )
            self.tools.addSeparator()
            self.tools.addAction(
                Action(
                    FluentIcon.SCROLL, "模式转换", triggered=self.user_list.switch_user
                )
            )
            self.tools.addSeparator()
            self.tools.addAction(
                Action(
                    FluentIcon.DEVELOPER_TOOLS, "用户选项配置", triggered=self.set_more
                )
            )

            Layout.addWidget(self.tools)
            Layout.addWidget(self.user_list)

            self.viewLayout.addLayout(Layout)

        def set_more(self):
            """用户选项配置"""

            if len(Config.running_list) > 0:
                logger.warning("配置用户选项时调度队列未停止运行")
                MainInfoBar.push_info_bar(
                    "warning", "调度中心正在执行任务", "请等待或手动中止任务", 5000
                )
                return None

            Config.cur.execute("SELECT * FROM adminx WHERE True")
            data = Config.cur.fetchall()
            data = sorted(data, key=lambda x: (-len(x[15]), x[16]))

            if self.user_list.pivot.currentRouteKey() == f"{self.name}_简洁用户列表":

                user_list = [_[0] for _ in data if _[15] == "simple"]
                set_list = ["自定义基建"]

                choice = ComboBoxMessageBox(
                    self.window(),
                    "用户选项配置",
                    ["选择要配置的用户", "选择要配置的选项"],
                    [user_list, set_list],
                )
                if (
                    choice.exec()
                    and choice.input[0].currentIndex() != -1
                    and choice.input[1].currentIndex() != -1
                ):

                    if choice.input[1].currentIndex() == 0:
                        file_path, _ = QFileDialog.getOpenFileName(
                            self,
                            "选择自定义基建文件",
                            ".",
                            "JSON 文件 (*.json)",
                        )
                        if file_path != "":
                            (
                                Config.app_path
                                / f"config/MaaConfig/{self.name}/simple/{choice.input[0].currentIndex()}/infrastructure"
                            ).mkdir(parents=True, exist_ok=True)
                            shutil.copy(
                                file_path,
                                Config.app_path
                                / f"config/MaaConfig/{self.name}/simple/{choice.input[0].currentIndex()}/infrastructure/infrastructure.json",
                            )
                        else:
                            logger.warning("未选择自定义基建文件")
                            MainInfoBar.push_info_bar(
                                "warning", "警告", "未选择自定义基建文件", 5000
                            )

            elif self.user_list.pivot.currentRouteKey() == f"{self.name}_高级用户列表":

                user_list = [_[0] for _ in data if _[15] == "beta"]
                set_list = ["MAA日常配置", "MAA剿灭配置"]

                choice = ComboBoxMessageBox(
                    self.window(),
                    "用户选项配置",
                    ["选择要配置的用户", "选择要配置的选项"],
                    [user_list, set_list],
                )
                if (
                    choice.exec()
                    and choice.input[0].currentIndex() != -1
                    and choice.input[1].currentIndex() != -1
                ):

                    set_book = ["routine", "annihilation"]
                    TaskManager.add_task(
                        "设置MAA_用户",
                        self.name,
                        {
                            "SetMaaInfo": {
                                "UserId": choice.input[0].currentIndex(),
                                "SetType": set_book[choice.input[1].currentIndex()],
                            }
                        },
                    )

        class UserListBox(QWidget):

            def __init__(self, name: str, parent=None):
                super().__init__(parent)
                self.setObjectName(f"{name}_用户列表")

                self.name = name

                self.if_user_list_editable = True
                self.if_update_database = True
                self.if_update_config = True

                self.user_mode_list = ["simple", "beta"]
                self.user_column = [
                    "admin",
                    "id",
                    "server",
                    "day",
                    "status",
                    "last",
                    "game",
                    "game_1",
                    "game_2",
                    "routine",
                    "annihilation",
                    "infrastructure",
                    "password",
                    "notes",
                    "numb",
                    "mode",
                    "uid",
                ]
                self.userlist_simple_index = [
                    0,
                    1,
                    2,
                    3,
                    4,
                    5,
                    6,
                    7,
                    8,
                    "-",
                    9,
                    10,
                    11,
                    12,
                    "-",
                    "-",
                    "-",
                ]
                self.userlist_beta_index = [
                    0,
                    "-",
                    "-",
                    1,
                    2,
                    3,
                    "-",
                    "-",
                    "-",
                    4,
                    5,
                    "-",
                    6,
                    7,
                    "-",
                    "-",
                    "-",
                ]

                self.pivot = Pivot(self)
                self.stackedWidget = QStackedWidget(self)
                self.Layout = QVBoxLayout(self)

                self.user_list_simple = TableWidget()
                self.user_list_simple.setObjectName(f"{self.name}_简洁用户列表")
                self.user_list_simple.setColumnCount(13)
                self.user_list_simple.setBorderVisible(True)
                self.user_list_simple.setBorderRadius(10)
                self.user_list_simple.setWordWrap(False)
                self.user_list_simple.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                self.user_list_simple.setHorizontalHeaderLabels(
                    [
                        "用户名",
                        "账号ID",
                        "服务器",
                        "代理天数",
                        "状态",
                        "执行情况",
                        "关卡",
                        "备选关卡-1",
                        "备选关卡-2",
                        "剿灭",
                        "自定义基建",
                        "密码",
                        "备注",
                    ]
                )

                self.user_list_beta = TableWidget()
                self.user_list_beta.setObjectName(f"{name}_高级用户列表")
                self.user_list_beta.setColumnCount(8)
                self.user_list_beta.setBorderVisible(True)
                self.user_list_beta.setBorderRadius(10)
                self.user_list_beta.setWordWrap(False)
                self.user_list_beta.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                self.user_list_beta.setHorizontalHeaderLabels(
                    [
                        "用户名",
                        "代理天数",
                        "状态",
                        "执行情况",
                        "日常",
                        "剿灭",
                        "密码",
                        "备注",
                    ]
                )

                self.user_list_simple.itemChanged.connect(
                    lambda item: self.change_user_Item(item, "simple")
                )
                self.user_list_beta.itemChanged.connect(
                    lambda item: self.change_user_Item(item, "beta")
                )

                self.stackedWidget.addWidget(self.user_list_simple)
                self.pivot.addItem(
                    routeKey=f"{name}_简洁用户列表", text=f"简洁用户列表"
                )
                self.stackedWidget.addWidget(self.user_list_beta)
                self.pivot.addItem(
                    routeKey=f"{name}_高级用户列表", text=f"高级用户列表"
                )

                self.Layout.addWidget(self.pivot, 0, Qt.AlignHCenter)
                self.Layout.addWidget(self.stackedWidget)
                self.Layout.setContentsMargins(0, 0, 0, 0)

                self.update_user_info("normal")
                self.switch_SettingBox(f"{name}_简洁用户列表")
                self.pivot.currentItemChanged.connect(
                    lambda index: self.switch_SettingBox(index)
                )

            def switch_SettingBox(self, index: str) -> None:
                """切换到指定的子界面"""

                self.pivot.setCurrentItem(index)
                if "简洁用户列表" in index:
                    self.stackedWidget.setCurrentWidget(self.user_list_simple)
                elif "高级用户列表" in index:
                    self.stackedWidget.setCurrentWidget(self.user_list_beta)

            def update_user_info(self, operation: str) -> None:
                """将本地数据库中的用户配置同步至GUI的用户管理界面"""

                # 读入本地数据库
                Config.cur.execute("SELECT * FROM adminx WHERE True")
                data = Config.cur.fetchall()

                # 处理部分模式调整
                if operation == "read_only":
                    self.if_user_list_editable = False
                elif operation == "editable":
                    self.if_user_list_editable = True

                # 阻止GUI用户数据被立即写入数据库形成死循环
                self.if_update_database = False

                # user_switch_list = ["转为高级", "转为简洁"]
                # self.user_switch.setText(user_switch_list[index])

                # 同步简洁用户配置列表
                data_simple = [_ for _ in data if _[15] == "simple"]
                self.user_list_simple.setRowCount(len(data_simple))
                height = self.user_list_simple.horizontalHeader().height()

                for i, row in enumerate(data_simple):

                    height += self.user_list_simple.rowHeight(i)

                    for j, value in enumerate(row):

                        if self.userlist_simple_index[j] == "-":
                            continue

                        # 生成表格组件
                        if j == 2:
                            item = ComboBox()
                            item.addItems(["官服", "B服"])
                            if value == "Official":
                                item.setCurrentIndex(0)
                            elif value == "Bilibili":
                                item.setCurrentIndex(1)
                            item.currentIndexChanged.connect(
                                partial(
                                    self.change_user_CellWidget,
                                    data_simple[i][16],
                                    self.user_column[j],
                                )
                            )
                        elif j in [4, 10, 11]:
                            item = ComboBox()
                            item.addItems(["启用", "禁用"])
                            if value == "y":
                                item.setCurrentIndex(0)
                            elif value == "n":
                                item.setCurrentIndex(1)
                            item.currentIndexChanged.connect(
                                partial(
                                    self.change_user_CellWidget,
                                    data_simple[i][16],
                                    self.user_column[j],
                                )
                            )
                        elif j == 3 and value == -1:
                            item = QTableWidgetItem("无限")
                        elif j == 5:
                            curdate = server_date()
                            if curdate != value:
                                item = QTableWidgetItem("未代理")
                            else:
                                item = QTableWidgetItem(f"已代理{data_simple[i][14]}次")
                            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                        elif j == 12:
                            if Config.PASSWORD == "":
                                item = QTableWidgetItem("******")
                                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                            else:
                                result = Crypto.AUTO_decryptor(value, Config.PASSWORD)
                                item = QTableWidgetItem(result)
                                if result == "管理密钥错误":
                                    item.setFlags(
                                        Qt.ItemIsSelectable | Qt.ItemIsEnabled
                                    )
                        else:
                            item = QTableWidgetItem(str(value))

                        # 组件录入表格
                        if j in [2, 4, 10, 11]:
                            if not self.if_user_list_editable:
                                item.setEnabled(False)
                            self.user_list_simple.setCellWidget(
                                data_simple[i][16], self.userlist_simple_index[j], item
                            )
                        else:
                            self.user_list_simple.setItem(
                                data_simple[i][16], self.userlist_simple_index[j], item
                            )
                self.user_list_simple.setFixedHeight(
                    height + self.user_list_simple.frameWidth() * 2 + 10
                )

                # 同步高级用户配置列表
                data_beta = [_ for _ in data if _[15] == "beta"]
                self.user_list_beta.setRowCount(len(data_beta))
                height = self.user_list_beta.horizontalHeader().height()

                for i, row in enumerate(data_beta):

                    height += self.user_list_beta.rowHeight(i)

                    for j, value in enumerate(row):

                        if self.userlist_beta_index[j] == "-":
                            continue

                        # 生成表格组件
                        if j in [4, 9, 10]:
                            item = ComboBox()
                            item.addItems(["启用", "禁用"])
                            if value == "y":
                                item.setCurrentIndex(0)
                            elif value == "n":
                                item.setCurrentIndex(1)
                            item.currentIndexChanged.connect(
                                partial(
                                    self.change_user_CellWidget,
                                    data_beta[i][16],
                                    self.user_column[j],
                                )
                            )
                        elif j == 3 and value == -1:
                            item = QTableWidgetItem("无限")
                        elif j == 5:
                            curdate = server_date()
                            if curdate != value:
                                item = QTableWidgetItem("未代理")
                            else:
                                item = QTableWidgetItem(f"已代理{data_beta[i][14]}次")
                            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                        elif j == 12:
                            if Config.PASSWORD == "":
                                item = QTableWidgetItem("******")
                                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                            else:
                                result = Crypto.AUTO_decryptor(value, Config.PASSWORD)
                                item = QTableWidgetItem(result)
                                if result == "管理密钥错误":
                                    item.setFlags(
                                        Qt.ItemIsSelectable | Qt.ItemIsEnabled
                                    )
                        else:
                            item = QTableWidgetItem(str(value))

                        # 组件录入表格
                        if j in [4, 9, 10]:
                            if not self.if_user_list_editable:
                                item.setEnabled(False)
                            self.user_list_beta.setCellWidget(
                                data_beta[i][16], self.userlist_beta_index[j], item
                            )
                        else:
                            self.user_list_beta.setItem(
                                data_beta[i][16], self.userlist_beta_index[j], item
                            )
                self.user_list_beta.setFixedHeight(
                    height + self.user_list_beta.frameWidth() * 2 + 10
                )

                # 设置列表可编辑状态
                if self.if_user_list_editable:
                    self.user_list_simple.setEditTriggers(TableWidget.AllEditTriggers)
                    self.user_list_beta.setEditTriggers(TableWidget.AllEditTriggers)
                else:
                    self.user_list_simple.setEditTriggers(TableWidget.NoEditTriggers)
                    self.user_list_beta.setEditTriggers(TableWidget.NoEditTriggers)

                # 允许GUI改变被同步到本地数据库
                self.if_update_database = True

                # 设置用户配置列表的标题栏宽度
                self.user_list_simple.horizontalHeader().setSectionResizeMode(
                    QHeaderView.Stretch
                )
                self.user_list_beta.horizontalHeader().setSectionResizeMode(
                    QHeaderView.Stretch
                )

            def change_user_Item(self, item: QTableWidgetItem, mode):
                """将GUI中发生修改的用户配置表中的一般信息同步至本地数据库"""

                # 验证能否写入本地数据库
                if not self.if_update_database:
                    return None

                text = item.text()
                # 简洁用户配置列表
                if mode == "simple":
                    # 待写入信息预处理
                    if item.column() == 3:  # 代理天数
                        try:
                            text = max(int(text), -1)
                        except ValueError:
                            self.update_user_info("normal")
                            return None
                    if item.column() in [6, 7, 8]:  # 关卡号
                        # 导入与应用特殊关卡规则
                        games = {}
                        with Config.gameid_path.open(mode="r", encoding="utf-8") as f:
                            gameids = f.readlines()
                            for line in gameids:
                                if "：" in line:
                                    game_in, game_out = line.split("：", 1)
                                    games[game_in.strip()] = game_out.strip()
                        text = games.get(text, text)
                    if item.column() == 11:  # 密码
                        text = Crypto.AUTO_encryptor(text)

                    # 保存至本地数据库
                    if text != "":
                        Config.cur.execute(
                            f"UPDATE adminx SET {self.user_column[self.userlist_simple_index.index(item.column())]} = ? WHERE mode = 'simple' AND uid = ?",
                            (text, item.row()),
                        )
                # 高级用户配置列表
                elif mode == "beta":
                    # 待写入信息预处理
                    if item.column() == 1:  # 代理天数
                        try:
                            text = max(int(text), -1)
                        except ValueError:
                            self.update_user_info("normal")
                            return None
                    if item.column() == 6:  # 密码
                        text = Crypto.AUTO_encryptor(text)

                    # 保存至本地数据库
                    if text != "":
                        Config.cur.execute(
                            f"UPDATE adminx SET {self.user_column[self.userlist_beta_index.index(item.column())]} = ? WHERE mode = 'beta' AND uid = ?",
                            (text, item.row()),
                        )
                Config.db.commit()

                # 同步一般用户信息更改到GUI
                self.update_user_info("normal")

            def change_user_CellWidget(self, row, column, index):
                """将GUI中发生修改的用户配置表中的CellWidget类信息同步至本地数据库"""

                # 验证能否写入本地数据库
                if not self.if_update_database:
                    return None

                if "简洁用户列表" in self.pivot.currentRouteKey():
                    mode = 0
                elif "高级用户列表" in self.pivot.currentRouteKey():
                    mode = 1

                # 初次开启自定义MAA配置或选择修改MAA配置时调起MAA配置任务
                # if (
                #     mode == 1
                #     and column in ["routine", "annihilation"]
                #     and (
                #         index == 2
                #         or (
                #             index == 0
                #             and not (
                #                 Config.app_path
                #                 / f"data/MAAconfig/{self.user_mode_list[index]}/{row}/{column}/gui.json"
                #             ).exists()
                #         )
                #     )
                # ):
                #     pass
                # self.MaaManager.get_json_path = [
                #     index,
                #     row,
                #     column,
                # ]
                # self.maa_starter("设置MAA_用户")

                # 服务器
                if mode == 0 and column == "server":
                    server_list = ["Official", "Bilibili"]
                    Config.cur.execute(
                        f"UPDATE adminx SET server = ? WHERE mode = 'simple' AND uid = ?",
                        (server_list[index], row),
                    )
                # 其它(启用/禁用)
                elif index in [0, 1]:
                    index_list = ["y", "n"]
                    Config.cur.execute(
                        f"UPDATE adminx SET {column} = ? WHERE mode = ? AND uid = ?",
                        (
                            index_list[index],
                            self.user_mode_list[mode],
                            row,
                        ),
                    )
                Config.db.commit()

                # 同步用户组件信息修改到GUI
                self.update_user_info("normal")

            def add_user(self):
                """添加一位新用户"""

                # 插入预设用户数据
                if "简洁用户列表" in self.pivot.currentRouteKey():
                    set_book = ["simple", self.user_list_simple.rowCount()]
                elif "高级用户列表" in self.pivot.currentRouteKey():
                    set_book = ["beta", self.user_list_beta.rowCount()]
                Config.cur.execute(
                    "INSERT INTO adminx VALUES('新用户','手机号码（官服）/B站ID（B服）','Official',-1,'y','2000-01-01','1-7','-','-','n','n','n',?,'无',0,?,?)",
                    (
                        Crypto.AUTO_encryptor("未设置"),
                        set_book[0],
                        set_book[1],
                    ),
                )
                Config.db.commit(),

                # 同步新用户至GUI
                self.update_user_info("normal")

            def del_user(self) -> None:
                """删除选中的首位用户"""

                if len(Config.running_list) > 0:
                    logger.warning("删除用户时调度队列未停止运行")
                    MainInfoBar.push_info_bar(
                        "warning", "调度中心正在执行任务", "请等待或手动中止任务", 5000
                    )
                    return None

                # 获取对应的行索引
                if "简洁用户列表" in self.pivot.currentRouteKey():
                    row = self.user_list_simple.currentRow()
                    current_numb = self.user_list_simple.rowCount()
                    mode = 0
                elif "高级用户列表" in self.pivot.currentRouteKey():
                    row = self.user_list_beta.currentRow()
                    current_numb = self.user_list_beta.rowCount()
                    mode = 1

                # 判断选择合理性
                if row == -1:
                    logger.warning("删除用户时未选中用户")
                    MainInfoBar.push_info_bar(
                        "warning", "未选择用户", "请先选择一个用户", 5000
                    )
                    return None

                # 确认待删除用户信息
                Config.cur.execute(
                    "SELECT * FROM adminx WHERE mode = ? AND uid = ?",
                    (
                        self.user_mode_list[mode],
                        row,
                    ),
                )
                data = Config.cur.fetchall()
                choice = MessageBox(
                    "确认",
                    f"确定要删除用户 {data[0][0]} 吗？",
                    self.window(),
                )

                # 删除用户
                if choice.exec():
                    # 删除所选用户
                    Config.cur.execute(
                        "DELETE FROM adminx WHERE mode = ? AND uid = ?",
                        (
                            self.user_mode_list[mode],
                            row,
                        ),
                    )
                    Config.db.commit()

                    if (
                        Config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row}"
                    ).exists():
                        shutil.rmtree(
                            Config.app_path
                            / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row}"
                        )
                    # 后续用户补位
                    for i in range(row + 1, current_numb):
                        Config.cur.execute(
                            "UPDATE adminx SET uid = ? WHERE mode = ? AND uid = ?",
                            (
                                i - 1,
                                self.user_mode_list[mode],
                                i,
                            ),
                        )
                        Config.db.commit()
                        if (
                            Config.app_path
                            / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{i}"
                        ).exists():
                            (
                                Config.app_path
                                / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{i}"
                            ).rename(
                                Config.app_path
                                / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{i}"
                            )

                    # 同步最终结果至GUI
                    self.update_user_info("normal")

            def up_user(self):
                """向上移动用户"""

                if len(Config.running_list) > 0:
                    logger.warning("向上移动用户时调度队列未停止运行")
                    MainInfoBar.push_info_bar(
                        "warning", "调度中心正在执行任务", "请等待或手动中止任务", 5000
                    )
                    return None

                # 获取对应的行索引
                if "简洁用户列表" in self.pivot.currentRouteKey():
                    row = self.user_list_simple.currentRow()
                    mode = 0
                elif "高级用户列表" in self.pivot.currentRouteKey():
                    row = self.user_list_beta.currentRow()
                    mode = 1

                # 判断选择合理性
                if row == -1:
                    logger.warning("向上移动用户时未选中用户")
                    MainInfoBar.push_info_bar(
                        "warning", "未选中用户", "请先选择一个用户", 5000
                    )
                    return None

                if row == 0:
                    logger.warning("向上移动用户时已到达最上端")
                    MainInfoBar.push_info_bar(
                        "warning", "已经是第一个用户", "无法向上移动", 5000
                    )
                    return None

                Config.cur.execute(
                    "UPDATE adminx SET uid = ? WHERE mode = ? AND uid = ?",
                    (
                        -1,
                        self.user_mode_list[mode],
                        row,
                    ),
                )
                Config.cur.execute(
                    "UPDATE adminx SET uid = ? WHERE mode = ? AND uid = ?",
                    (
                        row,
                        self.user_mode_list[mode],
                        row - 1,
                    ),
                )
                Config.cur.execute(
                    "UPDATE adminx SET uid = ? WHERE mode = ? AND uid = ?",
                    (
                        row - 1,
                        self.user_mode_list[mode],
                        -1,
                    ),
                )
                Config.db.commit()

                if (
                    Config.app_path
                    / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row}"
                ).exists():
                    (
                        Config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row}"
                    ).rename(
                        Config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{-1}"
                    )
                if (
                    Config.app_path
                    / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row - 1}"
                ).exists():
                    (
                        Config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row - 1}"
                    ).rename(
                        Config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row}"
                    )
                if (
                    Config.app_path
                    / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{-1}"
                ).exists():
                    (
                        Config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{-1}"
                    ).rename(
                        Config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row - 1}"
                    )

                self.update_user_info("normal")
                if "简洁用户列表" in self.pivot.currentRouteKey():
                    self.user_list_simple.selectRow(row - 1)
                elif "高级用户列表" in self.pivot.currentRouteKey():
                    self.user_list_beta.selectRow(row - 1)

            def down_user(self):
                """向下移动用户"""

                if len(Config.running_list) > 0:
                    logger.warning("向下移动用户时调度队列未停止运行")
                    MainInfoBar.push_info_bar(
                        "warning", "调度中心正在执行任务", "请等待或手动中止任务", 5000
                    )
                    return None

                # 获取对应的行索引
                if "简洁用户列表" in self.pivot.currentRouteKey():
                    row = self.user_list_simple.currentRow()
                    current_numb = self.user_list_simple.rowCount()
                    mode = 0
                elif "高级用户列表" in self.pivot.currentRouteKey():
                    row = self.user_list_beta.currentRow()
                    current_numb = self.user_list_beta.rowCount()
                    mode = 1

                # 判断选择合理性
                if row == -1:
                    logger.warning("向下移动用户时未选中用户")
                    MainInfoBar.push_info_bar(
                        "warning", "未选中用户", "请先选择一个用户", 5000
                    )
                    return None

                if row == current_numb - 1:
                    logger.warning("向下移动用户时已到达最下端")
                    MainInfoBar.push_info_bar(
                        "warning", "已经是最后一个用户", "无法向下移动", 5000
                    )
                    return None

                Config.cur.execute(
                    "UPDATE adminx SET uid = ? WHERE mode = ? AND uid = ?",
                    (
                        -1,
                        self.user_mode_list[mode],
                        row,
                    ),
                )
                Config.cur.execute(
                    "UPDATE adminx SET uid = ? WHERE mode = ? AND uid = ?",
                    (
                        row,
                        self.user_mode_list[mode],
                        row + 1,
                    ),
                )
                Config.cur.execute(
                    "UPDATE adminx SET uid = ? WHERE mode = ? AND uid = ?",
                    (
                        row + 1,
                        self.user_mode_list[mode],
                        -1,
                    ),
                )
                Config.db.commit()

                if (
                    Config.app_path
                    / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row}"
                ).exists():
                    (
                        Config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row}"
                    ).rename(
                        Config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{-1}"
                    )
                if (
                    Config.app_path
                    / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row + 1}"
                ).exists():
                    (
                        Config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row + 1}"
                    ).rename(
                        Config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row}"
                    )
                if (
                    Config.app_path
                    / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{-1}"
                ).exists():
                    (
                        Config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{-1}"
                    ).rename(
                        Config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row + 1}"
                    )

                self.update_user_info("normal")
                if "简洁用户列表" in self.pivot.currentRouteKey():
                    self.user_list_simple.selectRow(row + 1)
                elif "高级用户列表" in self.pivot.currentRouteKey():
                    self.user_list_beta.selectRow(row + 1)

            def switch_user(self) -> None:
                """切换用户配置模式"""

                if len(Config.running_list) > 0:
                    logger.warning("切换用户配置模式时调度队列未停止运行")
                    MainInfoBar.push_info_bar(
                        "warning", "调度中心正在执行任务", "请等待或手动中止任务", 5000
                    )
                    return None

                # 获取当前用户配置模式信息
                if "简洁用户列表" in self.pivot.currentRouteKey():
                    row = self.user_list_simple.currentRow()
                    mode = 0
                elif "高级用户列表" in self.pivot.currentRouteKey():
                    row = self.user_list_beta.currentRow()
                    mode = 1

                # 判断选择合理性
                if row == -1:
                    logger.warning("切换用户配置模式时未选中用户")
                    MainInfoBar.push_info_bar(
                        "warning", "未选中用户", "请先选择一个用户", 5000
                    )
                    return None

                # 确认待切换用户信息
                Config.cur.execute(
                    "SELECT * FROM adminx WHERE mode = ? AND uid = ?",
                    (
                        self.user_mode_list[mode],
                        row,
                    ),
                )
                data = Config.cur.fetchall()

                mode_list = ["简洁", "高级"]
                choice = MessageBox(
                    "确认",
                    f"确定要将用户 {data[0][0]} 转为{mode_list[1 - mode]}配置模式吗？",
                    self.window(),
                )

                # 切换用户
                if choice.exec():
                    Config.cur.execute("SELECT * FROM adminx WHERE True")
                    data = Config.cur.fetchall()
                    if mode == 0:
                        current_numb = self.user_list_simple.rowCount()
                    elif mode == 1:
                        current_numb = self.user_list_beta.rowCount()
                    # 切换所选用户
                    other_numb = len(data) - current_numb
                    Config.cur.execute(
                        "UPDATE adminx SET mode = ?, uid = ? WHERE mode = ? AND uid = ?",
                        (
                            self.user_mode_list[1 - mode],
                            other_numb,
                            self.user_mode_list[mode],
                            row,
                        ),
                    )
                    Config.db.commit()
                    if (
                        Config.app_path
                        / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row}"
                    ).exists():
                        shutil.move(
                            Config.app_path
                            / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{row}",
                            Config.app_path
                            / f"config/MaaConfig/{self.name}/{self.user_mode_list[1 - mode]}/{other_numb}",
                        )
                    # 后续用户补位
                    for i in range(row + 1, current_numb):
                        Config.cur.execute(
                            "UPDATE adminx SET uid = ? WHERE mode = ? AND uid = ?",
                            (
                                i - 1,
                                self.user_mode_list[mode],
                                i,
                            ),
                        )
                        Config.db.commit(),
                        if (
                            Config.app_path
                            / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{i}"
                        ).exists():
                            (
                                Config.app_path
                                / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{i}"
                            ).rename(
                                Config.app_path
                                / f"config/MaaConfig/{self.name}/{self.user_mode_list[mode]}/{i - 1}"
                            )

                    self.update_user_info("normal")


def server_date() -> str:
    """获取当前的服务器日期"""

    dt = datetime.now()
    if dt.time() < datetime.min.time().replace(hour=4):
        dt = dt - timedelta(days=1)
    return dt.strftime("%Y-%m-%d")
