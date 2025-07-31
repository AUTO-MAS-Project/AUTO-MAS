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
v4.4
作者：DLmaster_361
"""

from PySide6.QtWidgets import (
    QWidget,
    QFileDialog,
    QHBoxLayout,
    QVBoxLayout,
    QStackedWidget,
    QTableWidgetItem,
    QHeaderView,
)
from PySide6.QtGui import QIcon, Qt
from qfluentwidgets import (
    Action,
    ConfigItem,
    ScrollArea,
    FluentIcon,
    MessageBox,
    HeaderCardWidget,
    CommandBar,
    ExpandGroupSettingCard,
    PushSettingCard,
    TableWidget,
    PrimaryToolButton,
    Flyout,
    FlyoutAnimationType,
)
from PySide6.QtCore import Signal
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import List, Dict, Union, Type
import shutil
import json

from app.core import (
    Config,
    logger,
    MainInfoBar,
    TaskManager,
    MaaConfig,
    MaaUserConfig,
    GeneralConfig,
    GeneralSubConfig,
    Network,
    SoundPlayer,
)
from app.services import Crypto
from .downloader import DownloadManager
from .Widget import (
    LineEditMessageBox,
    LineEditSettingCard,
    SpinBoxSettingCard,
    ComboBoxMessageBox,
    SettingFlyoutView,
    NoOptionComboBoxSettingCard,
    ComboBoxWithPlanSettingCard,
    EditableComboBoxWithPlanSettingCard,
    SpinBoxWithPlanSettingCard,
    PasswordLineEditSettingCard,
    PasswordLineAndSwitchButtonSettingCard,
    UserLableSettingCard,
    UserTaskSettingCard,
    SubLableSettingCard,
    ComboBoxSettingCard,
    SwitchSettingCard,
    PathSettingCard,
    PushAndSwitchButtonSettingCard,
    PushAndComboBoxSettingCard,
    StatusSwitchSetting,
    UserNoticeSettingCard,
    NoticeMessageBox,
    PivotArea,
)


class ScriptManager(QWidget):
    """脚本管理父界面"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("脚本管理")

        layout = QVBoxLayout(self)

        self.tools = CommandBar()
        self.script_manager = self.ScriptSettingBox(self)

        # 逐个添加动作
        self.tools.addActions(
            [
                Action(FluentIcon.ADD_TO, "新建脚本实例", triggered=self.add_script),
                Action(
                    FluentIcon.REMOVE_FROM, "删除脚本实例", triggered=self.del_script
                ),
            ]
        )
        self.tools.addSeparator()
        self.tools.addActions(
            [
                Action(FluentIcon.LEFT_ARROW, "向左移动", triggered=self.left_script),
                Action(FluentIcon.RIGHT_ARROW, "向右移动", triggered=self.right_script),
            ]
        )
        self.tools.addSeparator()
        self.tools.addAction(
            Action(
                FluentIcon.DOWNLOAD,
                "脚本下载器",
                triggered=self.script_downloader,
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
        layout.addWidget(self.script_manager)

    def add_script(self):
        """添加一个脚本实例"""

        choice = ComboBoxMessageBox(
            self.window(),
            "选择一个脚本类型以添加相应脚本实例",
            ["选择脚本类型"],
            [["MAA", "通用"]],
        )
        if choice.exec() and choice.input[0].currentIndex() != -1:

            logger.info(
                f"添加脚本实例: {choice.input[0].currentText()}", module="脚本管理"
            )

            if choice.input[0].currentText() == "MAA":

                index = len(Config.script_dict) + 1

                # 初始化 MAA 配置
                maa_config = MaaConfig()
                maa_config.load(
                    Config.app_path / f"config/MaaConfig/脚本_{index}/config.json",
                    maa_config,
                )
                maa_config.save()
                (Config.app_path / f"config/MaaConfig/脚本_{index}/UserData").mkdir(
                    parents=True, exist_ok=True
                )

                Config.script_dict[f"脚本_{index}"] = {
                    "Type": "Maa",
                    "Path": Config.app_path / f"config/MaaConfig/脚本_{index}",
                    "Config": maa_config,
                    "UserData": {},
                }

                # 添加 MAA 实例设置界面
                self.script_manager.add_SettingBox(
                    index, self.ScriptSettingBox.MaaSettingBox
                )
                self.script_manager.switch_SettingBox(index)

                logger.success(f"MAA实例 脚本_{index} 添加成功", module="脚本管理")
                MainInfoBar.push_info_bar(
                    "success", "操作成功", f"添加 MAA 实例 脚本_{index}", 3000
                )
                SoundPlayer.play("添加脚本实例")

            elif choice.input[0].currentText() == "通用":

                index = len(Config.script_dict) + 1

                # 初始化通用配置
                general_config = GeneralConfig()
                general_config.load(
                    Config.app_path / f"config/GeneralConfig/脚本_{index}/config.json",
                    general_config,
                )
                general_config.save()
                (Config.app_path / f"config/GeneralConfig/脚本_{index}/SubData").mkdir(
                    parents=True, exist_ok=True
                )

                Config.script_dict[f"脚本_{index}"] = {
                    "Type": "General",
                    "Path": Config.app_path / f"config/GeneralConfig/脚本_{index}",
                    "Config": general_config,
                    "SubData": {},
                }

                # 添加通用实例设置界面
                self.script_manager.add_SettingBox(
                    index, self.ScriptSettingBox.GeneralSettingBox
                )
                self.script_manager.switch_SettingBox(index)

                logger.success(f"通用实例 脚本_{index} 添加成功", module="脚本管理")
                MainInfoBar.push_info_bar(
                    "success", "操作成功", f"添加通用实例 脚本_{index}", 3000
                )
                SoundPlayer.play("添加脚本实例")

    def del_script(self):
        """删除一个脚本实例"""

        name = self.script_manager.pivot.currentRouteKey()

        if name is None:
            logger.warning("删除脚本实例时未选择脚本实例", module="脚本管理")
            MainInfoBar.push_info_bar(
                "warning", "未选择脚本实例", "请选择一个脚本实例", 5000
            )
            return None

        if len(Config.running_list) > 0:
            logger.warning("删除脚本实例时调度队列未停止运行", module="脚本管理")
            MainInfoBar.push_info_bar(
                "warning", "调度中心正在执行任务", "请等待或手动中止任务", 5000
            )
            return None

        choice = MessageBox("确认", f"确定要删除 {name} 实例吗？", self.window())
        if choice.exec():

            logger.info(f"正在删除脚本实例: {name}", module="脚本管理")

            self.script_manager.clear_SettingBox()

            # 删除脚本实例的配置文件并同步修改相应配置项
            shutil.rmtree(Config.script_dict[name]["Path"])
            Config.change_queue(name, "禁用")
            for i in range(int(name[3:]) + 1, len(Config.script_dict) + 1):
                if Config.script_dict[f"脚本_{i}"]["Path"].exists():
                    Config.script_dict[f"脚本_{i}"]["Path"].rename(
                        Config.script_dict[f"脚本_{i}"]["Path"].with_name(f"脚本_{i-1}")
                    )
                Config.change_queue(f"脚本_{i}", f"脚本_{i-1}")

            self.script_manager.show_SettingBox(max(int(name[3:]) - 1, 1))

            logger.success(f"脚本实例 {name} 删除成功", module="脚本管理")
            MainInfoBar.push_info_bar(
                "success", "操作成功", f"删除脚本实例 {name}", 3000
            )
            SoundPlayer.play("删除脚本实例")

    def left_script(self):
        """向左移动脚本实例"""

        name = self.script_manager.pivot.currentRouteKey()

        if name is None:
            logger.warning("向左移动脚本实例时未选择脚本实例", module="脚本管理")
            MainInfoBar.push_info_bar(
                "warning", "未选择脚本实例", "请选择一个脚本实例", 5000
            )
            return None

        index = int(name[3:])

        if index == 1:
            logger.warning("向左移动脚本实例时已到达最左端", module="脚本管理")
            MainInfoBar.push_info_bar(
                "warning", "已经是第一个脚本实例", "无法向左移动", 5000
            )
            return None

        if len(Config.running_list) > 0:
            logger.warning("向左移动脚本实例时调度队列未停止运行", module="脚本管理")
            MainInfoBar.push_info_bar(
                "warning", "调度中心正在执行任务", "请等待或手动中止任务", 5000
            )
            return None

        logger.info(f"正在向左移动脚本实例: {name}", module="脚本管理")

        self.script_manager.clear_SettingBox()

        # 移动脚本实例配置文件并同步修改配置项
        Config.script_dict[name]["Path"].rename(
            Config.script_dict[name]["Path"].with_name("脚本_0")
        )
        Config.change_queue(name, "脚本_0")
        Config.script_dict[f"脚本_{index-1}"]["Path"].rename(
            Config.script_dict[f"脚本_{index-1}"]["Path"].with_name(name)
        )
        Config.change_queue(f"脚本_{index-1}", name)
        Config.script_dict[name]["Path"].with_name("脚本_0").rename(
            Config.script_dict[name]["Path"].with_name(f"脚本_{index-1}")
        )
        Config.change_queue("脚本_0", f"脚本_{index-1}")

        self.script_manager.show_SettingBox(index - 1)

        logger.success(f"脚本实例 {name} 左移成功", module="脚本管理")
        MainInfoBar.push_info_bar("success", "操作成功", f"左移脚本实例 {name}", 3000)

    def right_script(self):
        """向右移动脚本实例"""

        name = self.script_manager.pivot.currentRouteKey()

        if name is None:
            logger.warning("向右移动脚本实例时未选择脚本实例", module="脚本管理")
            MainInfoBar.push_info_bar(
                "warning", "未选择脚本实例", "请选择一个脚本实例", 5000
            )
            return None

        index = int(name[3:])

        if index == len(Config.script_dict):
            logger.warning("向右移动脚本实例时已到达最右端", module="脚本管理")
            MainInfoBar.push_info_bar(
                "warning", "已经是最后一个脚本实例", "无法向右移动", 5000
            )
            return None

        if len(Config.running_list) > 0:
            logger.warning("向右移动脚本实例时调度队列未停止运行", module="脚本管理")
            MainInfoBar.push_info_bar(
                "warning", "调度中心正在执行任务", "请等待或手动中止任务", 5000
            )
            return None

        logger.info(f"正在向右移动脚本实例: {name}", module="脚本管理")

        self.script_manager.clear_SettingBox()

        # 移动脚本实例配置文件并同步修改配置项
        Config.script_dict[name]["Path"].rename(
            Config.script_dict[name]["Path"].with_name("脚本_0")
        )
        Config.change_queue(name, "脚本_0")
        Config.script_dict[f"脚本_{index+1}"]["Path"].rename(
            Config.script_dict[f"脚本_{index+1}"]["Path"].with_name(name)
        )
        Config.change_queue(f"脚本_{index+1}", name)
        Config.script_dict[name]["Path"].with_name("脚本_0").rename(
            Config.script_dict[name]["Path"].with_name(f"脚本_{index+1}")
        )
        Config.change_queue("脚本_0", f"脚本_{index+1}")

        self.script_manager.show_SettingBox(index + 1)

        logger.success(f"脚本实例 {name} 右移成功", module="脚本管理")
        MainInfoBar.push_info_bar("success", "操作成功", f"右移脚本实例 {name}", 3000)

    def script_downloader(self):
        """脚本下载器"""

        if not Config.get(Config.update_MirrorChyanCDK):

            logger.warning("脚本下载器未设置CDK", module="脚本管理")
            MainInfoBar.push_info_bar(
                "warning",
                "未设置Mirror酱CDK",
                "下载器依赖于Mirror酱，未设置CDK时无法使用",
                5000,
            )
            return None

        # 从远程服务器获取应用列表
        network = Network.add_task(
            mode="get",
            url="http://221.236.27.82:10197/d/AUTO_MAA/Server/apps_info.json",
        )
        network.loop.exec()
        network_result = Network.get_result(network)
        if network_result["status_code"] == 200:
            apps_info = network_result["response_json"]
        else:
            logger.warning(
                f"获取应用列表时出错：{network_result['error_message']}",
                module="脚本管理",
            )
            MainInfoBar.push_info_bar(
                "warning",
                "获取应用列表时出错",
                f"网络错误：{network_result['status_code']}",
                5000,
            )
            return None

        choice = ComboBoxMessageBox(
            self.window(),
            "选择一个脚本类型以下载相应脚本",
            ["选择脚本类型"],
            [list(apps_info.keys())],
        )
        if choice.exec() and choice.input[0].currentIndex() != -1:

            app_name = choice.input[0].currentText()
            app_rid = apps_info[app_name]["rid"]

            (Config.app_path / f"script/{app_rid}").mkdir(parents=True, exist_ok=True)
            folder = QFileDialog.getExistingDirectory(
                self,
                f"选择{app_name}下载目录",
                str(Config.app_path / f"script/{app_rid}"),
            )
            if not folder:
                logger.warning(
                    f"选择{app_name}下载目录时未选择文件夹", module="脚本管理"
                )
                MainInfoBar.push_info_bar(
                    "warning", "警告", f"未选择{app_name}下载目录", 5000
                )
                return None

            # 从mirrorc服务器获取最新版本信息
            network = Network.add_task(
                mode="get",
                url=f"https://mirrorchyan.com/api/resources/{app_rid}/latest?user_agent=AutoMaaGui&cdk={Crypto.win_decryptor(Config.get(Config.update_MirrorChyanCDK))}&os={apps_info[app_name]["os"]}&arch={apps_info[app_name]["arch"]}&channel=stable",
            )
            network.loop.exec()
            network_result = Network.get_result(network)
            if network_result["status_code"] == 200:
                app_info = network_result["response_json"]
            else:

                if network_result["response_json"]:

                    app_info = network_result["response_json"]

                    if app_info["code"] != 0:

                        logger.error(
                            f"获取应用版本信息时出错：{app_info["msg"]}",
                            module="脚本管理",
                        )

                        error_remark_dict = {
                            1001: "获取版本信息的URL参数不正确",
                            7001: "填入的 CDK 已过期",
                            7002: "填入的 CDK 错误",
                            7003: "填入的 CDK 今日下载次数已达上限",
                            7004: "填入的 CDK 类型和待下载的资源不匹配",
                            7005: "填入的 CDK 已被封禁",
                            8001: "对应架构和系统下的资源不存在",
                            8002: "错误的系统参数",
                            8003: "错误的架构参数",
                            8004: "错误的更新通道参数",
                            1: app_info["msg"],
                        }

                        if app_info["code"] in error_remark_dict:
                            MainInfoBar.push_info_bar(
                                "error",
                                "获取版本信息时出错",
                                error_remark_dict[app_info["code"]],
                                -1,
                            )
                        else:
                            MainInfoBar.push_info_bar(
                                "error",
                                "获取版本信息时出错",
                                "意料之外的错误，请及时联系项目组以获取来自 Mirror 酱的技术支持",
                                -1,
                            )

                        return None

                logger.warning(
                    f"获取版本信息时出错：{network_result['error_message']}",
                    module="脚本管理",
                )
                MainInfoBar.push_info_bar(
                    "warning",
                    "获取版本信息时出错",
                    f"网络错误：{network_result['status_code']}",
                    5000,
                )
                return None

            # 创建下载管理器并开始下载
            logger.info(f"开始下载{app_name}，下载目录：{folder}", module="脚本管理")
            self.downloader = DownloadManager(
                Path(folder),
                app_rid,
                [],
                {
                    "mode": "MirrorChyan",
                    "thread_numb": 1,
                    "url": app_info["data"]["url"],
                },
            )
            self.downloader.setWindowTitle("AUTO_MAA下载器 - Mirror酱渠道")
            self.downloader.setWindowIcon(
                QIcon(str(Config.app_path / "resources/icons/MirrorChyan.ico"))
            )
            self.downloader.show()
            self.downloader.run()

    def show_password(self):
        """显示或隐藏密码"""

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

    def reload_plan_name(self):
        """刷新计划表名称"""

        # 生成计划列表信息
        plan_list = [
            ["固定"] + [_ for _ in Config.plan_dict.keys()],
            ["固定"]
            + [
                (
                    k
                    if v["Config"].get(v["Config"].Info_Name) == ""
                    else f"{k} - {v["Config"].get(v["Config"].Info_Name)}"
                )
                for k, v in Config.plan_dict.items()
            ],
        ]

        # 刷新所有脚本实例的计划表名称
        for script in self.script_manager.script_list:

            if isinstance(script, ScriptManager.ScriptSettingBox.MaaSettingBox):

                for user_setting in script.user_setting.user_manager.script_list:

                    user_setting.card_StageMode.comboBox.currentIndexChanged.disconnect(
                        user_setting.switch_stage_mode
                    )
                    user_setting.card_StageMode.reLoadOptions(
                        plan_list[0], plan_list[1]
                    )
                    user_setting.card_StageMode.comboBox.currentIndexChanged.connect(
                        user_setting.switch_stage_mode
                    )

        self.refresh_plan_info()

    def refresh_dashboard(self):
        """刷新所有脚本实例的仪表盘"""

        for script in self.script_manager.script_list:

            if isinstance(script, ScriptManager.ScriptSettingBox.MaaSettingBox):
                script.user_setting.user_manager.user_dashboard.load_info()
            elif isinstance(script, ScriptManager.ScriptSettingBox.GeneralSettingBox):
                script.branch_manager.sub_manager.sub_dashboard.load_info()

    def refresh_plan_info(self):
        """刷新所有计划信息"""

        for script in self.script_manager.script_list:

            if isinstance(script, ScriptManager.ScriptSettingBox.MaaSettingBox):

                script.user_setting.user_manager.user_dashboard.load_info()
                for user_setting in script.user_setting.user_manager.script_list:
                    user_setting.switch_stage_mode()

    class ScriptSettingBox(QWidget):
        """脚本管理子页面组"""

        def __init__(self, parent=None):
            super().__init__(parent)

            self.setObjectName("脚本管理页面组")

            self.pivotArea = PivotArea(self)
            self.pivot = self.pivotArea.pivot

            self.stackedWidget = QStackedWidget(self)
            self.stackedWidget.setContentsMargins(0, 0, 0, 0)
            self.stackedWidget.setStyleSheet("background: transparent; border: none;")

            self.script_list: List[
                Union[
                    ScriptManager.ScriptSettingBox.MaaSettingBox,
                    ScriptManager.ScriptSettingBox.GeneralSettingBox,
                ]
            ] = []

            self.Layout = QVBoxLayout(self)
            self.Layout.addWidget(self.pivotArea)
            self.Layout.addWidget(self.stackedWidget)
            self.Layout.setContentsMargins(0, 0, 0, 0)

            self.pivot.currentItemChanged.connect(
                lambda index: self.switch_SettingBox(
                    int(index[3:]), if_chang_pivot=False
                )
            )

            self.show_SettingBox(1)

        def show_SettingBox(self, index) -> None:
            """
            加载所有子界面并切换到指定子界面

            :param index: 要切换到的子界面索引
            :type index: int
            """

            Config.search_script()

            for name, info in Config.script_dict.items():
                if info["Type"] == "Maa":
                    self.add_SettingBox(int(name[3:]), self.MaaSettingBox)
                elif info["Type"] == "General":
                    self.add_SettingBox(int(name[3:]), self.GeneralSettingBox)

            self.switch_SettingBox(index)

        def switch_SettingBox(self, index: int, if_chang_pivot: bool = True) -> None:
            """
            切换到指定的子界面

            :param index: 要切换到的子界面索引
            :type index: int
            :param if_chang_pivot: 是否更改导航栏的当前项
            :type if_chang_pivot: bool
            """

            if len(Config.script_dict) == 0:
                return None

            if index > len(Config.script_dict):
                return None

            if if_chang_pivot:
                self.pivot.setCurrentItem(self.script_list[index - 1].objectName())
            self.stackedWidget.setCurrentWidget(self.script_list[index - 1])

            if isinstance(
                self.script_list[index - 1],
                ScriptManager.ScriptSettingBox.MaaSettingBox,
            ):
                self.script_list[index - 1].user_setting.user_manager.switch_SettingBox(
                    "用户仪表盘"
                )
            elif isinstance(
                self.script_list[index - 1],
                ScriptManager.ScriptSettingBox.GeneralSettingBox,
            ):
                self.script_list[
                    index - 1
                ].branch_manager.sub_manager.switch_SettingBox("配置仪表盘")

        def clear_SettingBox(self) -> None:
            """清空所有子界面"""

            for sub_interface in self.script_list:
                self.stackedWidget.removeWidget(sub_interface)
                sub_interface.deleteLater()
            self.script_list.clear()
            self.pivot.clear()

        def add_SettingBox(self, uid: int, type: Type) -> None:
            """
            添加指定类型设置子界面

            :param uid: 脚本实例的唯一标识符
            :type uid: int
            :param type: 要添加的设置子界面类型
            :type type: Type
            """

            if type == self.MaaSettingBox:
                setting_box = self.MaaSettingBox(uid, self)
            elif type == self.GeneralSettingBox:
                setting_box = self.GeneralSettingBox(uid, self)
            else:
                return None

            self.script_list.append(setting_box)
            self.stackedWidget.addWidget(self.script_list[-1])
            self.pivot.addItem(routeKey=f"脚本_{uid}", text=f"脚本 {uid}")

        class MaaSettingBox(QWidget):
            """MAA类脚本设置界面"""

            def __init__(self, uid: int, parent=None):
                super().__init__(parent)

                self.setObjectName(f"脚本_{uid}")
                self.config = Config.script_dict[f"脚本_{uid}"]["Config"]

                self.app_setting = self.AppSettingCard(f"脚本_{uid}", self.config, self)
                self.user_setting = self.UserManager(f"脚本_{uid}", self)

                content_widget = QWidget()
                content_layout = QVBoxLayout(content_widget)
                content_layout.setContentsMargins(0, 0, 11, 0)
                content_layout.addWidget(self.app_setting)
                content_layout.addWidget(self.user_setting)
                content_layout.addStretch(1)

                scrollArea = ScrollArea()
                scrollArea.setWidgetResizable(True)
                scrollArea.setContentsMargins(0, 0, 0, 0)
                scrollArea.setStyleSheet("background: transparent; border: none;")
                scrollArea.setWidget(content_widget)

                layout = QVBoxLayout(self)
                layout.addWidget(scrollArea)

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
                    """选择MAA目录并验证"""

                    folder = QFileDialog.getExistingDirectory(
                        self,
                        "选择MAA目录",
                        self.config.get(self.config.MaaSet_Path),
                    )
                    if not folder or self.config.get(self.config.MaaSet_Path) == folder:
                        logger.warning(
                            "选择MAA目录时未选择文件夹或未更改文件夹", module="脚本管理"
                        )
                        MainInfoBar.push_info_bar(
                            "warning", "警告", "未选择文件夹或未更改文件夹", 5000
                        )
                        return None
                    elif (
                        not (Path(folder) / "config/gui.json").exists()
                        or not (Path(folder) / "MAA.exe").exists()
                    ):
                        logger.warning(
                            "选择MAA目录时未找到MAA程序或配置文件", module="脚本管理"
                        )
                        MainInfoBar.push_info_bar(
                            "warning", "警告", "未找到MAA程序或配置文件", 5000
                        )
                        return None

                    (Config.script_dict[self.name]["Path"] / "Default").mkdir(
                        parents=True, exist_ok=True
                    )
                    shutil.copy(
                        Path(folder) / "config/gui.json",
                        Config.script_dict[self.name]["Path"] / "Default/gui.json",
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
                            content="相邻两个任务间的切换方式，使用「详细」配置的用户固定为「重启模拟器」",
                            texts=["直接切换账号", "重启明日方舟", "重启模拟器"],
                            qconfig=self.config,
                            configItem=self.config.RunSet_TaskTransitionMethod,
                            parent=self,
                        )
                        self.card_ProxyTimesLimit = SpinBoxSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="用户单日代理次数上限",
                            content="当用户本日代理成功次数达到该阈值时跳过代理，阈值为「0」时视为无代理次数上限",
                            range=(0, 1024),
                            qconfig=self.config,
                            configItem=self.config.RunSet_ProxyTimesLimit,
                            parent=self,
                        )
                        self.card_ADBSearchRange = SpinBoxSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="ADB端口号搜索范围",
                            content="在【±端口号范围】内搜索实际ADB端口号",
                            range=(0, 3),
                            qconfig=self.config,
                            configItem=self.config.RunSet_ADBSearchRange,
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

                        widget = QWidget()
                        Layout = QVBoxLayout(widget)
                        Layout.addWidget(self.card_TaskTransitionMethod)
                        Layout.addWidget(self.card_ProxyTimesLimit)
                        Layout.addWidget(self.card_ADBSearchRange)
                        Layout.addWidget(self.card_RunTimesLimit)
                        Layout.addWidget(self.card_AnnihilationTimeLimit)
                        Layout.addWidget(self.card_RoutineTimeLimit)
                        Layout.addWidget(self.card_AnnihilationWeeklyLimit)
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

                    index = len(Config.script_dict[self.name]["UserData"]) + 1

                    logger.info(f"正在添加 {self.name} 用户_{index}", module="脚本管理")

                    # 初始化用户配置信息
                    user_config = MaaUserConfig()
                    user_config.load(
                        Config.script_dict[self.name]["Path"]
                        / f"UserData/用户_{index}/config.json",
                        user_config,
                    )
                    user_config.save()

                    Config.script_dict[self.name]["UserData"][f"用户_{index}"] = {
                        "Path": Config.script_dict[self.name]["Path"]
                        / f"UserData/用户_{index}",
                        "Config": user_config,
                    }

                    # 添加用户设置面板
                    self.user_manager.add_userSettingBox(index)
                    self.user_manager.switch_SettingBox(f"用户_{index}")

                    logger.success(
                        f"{self.name} 用户_{index} 添加成功", module="脚本管理"
                    )
                    MainInfoBar.push_info_bar(
                        "success", "操作成功", f"{self.name} 添加 用户_{index}", 3000
                    )
                    SoundPlayer.play("添加用户")

                def del_user(self):
                    """删除一个用户"""

                    name = self.user_manager.pivot.currentRouteKey()

                    if name is None:
                        logger.warning("未选择用户", module="脚本管理")
                        MainInfoBar.push_info_bar(
                            "warning", "未选择用户", "请先选择一个用户", 5000
                        )
                        return None
                    if name == "用户仪表盘":
                        logger.warning("试图删除用户仪表盘", module="脚本管理")
                        MainInfoBar.push_info_bar(
                            "warning", "未选择用户", "请勿尝试删除用户仪表盘", 5000
                        )
                        return None

                    if self.name in Config.running_list:
                        logger.warning("所属脚本正在运行", module="脚本管理")
                        MainInfoBar.push_info_bar(
                            "warning", "所属脚本正在运行", "请先停止任务", 5000
                        )
                        return None

                    choice = MessageBox(
                        "确认", f"确定要删除 {name} 吗？", self.window()
                    )
                    if choice.exec():

                        logger.info(f"正在删除 {self.name} {name}", module="脚本管理")

                        self.user_manager.clear_SettingBox()

                        # 删除用户配置文件并同步修改相应配置项
                        shutil.rmtree(
                            Config.script_dict[self.name]["UserData"][name]["Path"]
                        )
                        for i in range(
                            int(name[3:]) + 1,
                            len(Config.script_dict[self.name]["UserData"]) + 1,
                        ):
                            if Config.script_dict[self.name]["UserData"][f"用户_{i}"][
                                "Path"
                            ].exists():
                                Config.script_dict[self.name]["UserData"][f"用户_{i}"][
                                    "Path"
                                ].rename(
                                    Config.script_dict[self.name]["UserData"][
                                        f"用户_{i}"
                                    ]["Path"].with_name(f"用户_{i-1}")
                                )

                        self.user_manager.show_SettingBox(
                            f"用户_{max(int(name[3:]) - 1, 1)}"
                        )

                        logger.success(
                            f"{self.name} {name} 删除成功", module="脚本管理"
                        )
                        MainInfoBar.push_info_bar(
                            "success", "操作成功", f"{self.name} 删除 {name}", 3000
                        )
                        SoundPlayer.play("删除用户")

                def left_user(self):
                    """向前移动用户"""

                    name = self.user_manager.pivot.currentRouteKey()

                    if name is None:
                        logger.warning("未选择用户", module="脚本管理")
                        MainInfoBar.push_info_bar(
                            "warning", "未选择用户", "请先选择一个用户", 5000
                        )
                        return None
                    if name == "用户仪表盘":
                        logger.warning("试图移动用户仪表盘", module="脚本管理")
                        MainInfoBar.push_info_bar(
                            "warning", "未选择用户", "请勿尝试移动用户仪表盘", 5000
                        )
                        return None

                    index = int(name[3:])

                    if index == 1:
                        logger.warning("向前移动用户时已到达最左端", module="脚本管理")
                        MainInfoBar.push_info_bar(
                            "warning", "已经是第一个用户", "无法向前移动", 5000
                        )
                        return None

                    if self.name in Config.running_list:
                        logger.warning("所属脚本正在运行", module="脚本管理")
                        MainInfoBar.push_info_bar(
                            "warning", "所属脚本正在运行", "请先停止任务", 5000
                        )
                        return None

                    logger.info(f"正在向前移动 {self.name} {name}", module="脚本管理")

                    self.user_manager.clear_SettingBox()

                    # 移动用户配置文件并同步修改配置项
                    Config.script_dict[self.name]["UserData"][name]["Path"].rename(
                        Config.script_dict[self.name]["UserData"][name][
                            "Path"
                        ].with_name("用户_0")
                    )
                    Config.script_dict[self.name]["UserData"][f"用户_{index-1}"][
                        "Path"
                    ].rename(Config.script_dict[self.name]["UserData"][name]["Path"])
                    Config.script_dict[self.name]["UserData"][name]["Path"].with_name(
                        "用户_0"
                    ).rename(
                        Config.script_dict[self.name]["UserData"][f"用户_{index-1}"][
                            "Path"
                        ]
                    )

                    self.user_manager.show_SettingBox(f"用户_{index - 1}")

                    logger.success(f"{self.name} {name} 前移成功", module="脚本管理")
                    MainInfoBar.push_info_bar(
                        "success", "操作成功", f"{self.name} 前移 {name}", 3000
                    )

                def right_user(self):
                    """向后移动用户"""

                    name = self.user_manager.pivot.currentRouteKey()

                    if name is None:
                        logger.warning("未选择用户", module="脚本管理")
                        MainInfoBar.push_info_bar(
                            "warning", "未选择用户", "请先选择一个用户", 5000
                        )
                        return None
                    if name == "用户仪表盘":
                        logger.warning("试图删除用户仪表盘", module="脚本管理")
                        MainInfoBar.push_info_bar(
                            "warning", "未选择用户", "请勿尝试移动用户仪表盘", 5000
                        )
                        return None

                    index = int(name[3:])

                    if index == len(Config.script_dict[self.name]["UserData"]):
                        logger.warning("向后移动用户时已到达最右端", module="脚本管理")
                        MainInfoBar.push_info_bar(
                            "warning", "已经是最后一个用户", "无法向后移动", 5000
                        )
                        return None

                    if self.name in Config.running_list:
                        logger.warning("所属脚本正在运行", module="脚本管理")
                        MainInfoBar.push_info_bar(
                            "warning", "所属脚本正在运行", "请先停止任务", 5000
                        )
                        return None

                    logger.info(f"正在向后移动 {self.name} {name}", module="脚本管理")

                    self.user_manager.clear_SettingBox()

                    Config.script_dict[self.name]["UserData"][name]["Path"].rename(
                        Config.script_dict[self.name]["UserData"][name][
                            "Path"
                        ].with_name("用户_0")
                    )
                    Config.script_dict[self.name]["UserData"][f"用户_{index+1}"][
                        "Path"
                    ].rename(Config.script_dict[self.name]["UserData"][name]["Path"])
                    Config.script_dict[self.name]["UserData"][name]["Path"].with_name(
                        "用户_0"
                    ).rename(
                        Config.script_dict[self.name]["UserData"][f"用户_{index+1}"][
                            "Path"
                        ]
                    )

                    self.user_manager.show_SettingBox(f"用户_{index + 1}")

                    logger.success(f"{self.name} {name} 后移成功", module="脚本管理")
                    MainInfoBar.push_info_bar(
                        "success", "操作成功", f"{self.name} 后移 {name}", 3000
                    )

                class UserSettingBox(QWidget):
                    """用户管理子页面组"""

                    def __init__(self, name: str, parent=None):
                        super().__init__(parent)

                        self.setObjectName("用户管理")
                        self.name = name

                        self.pivotArea = PivotArea(self)
                        self.pivot = self.pivotArea.pivot

                        self.stackedWidget = QStackedWidget(self)
                        self.stackedWidget.setContentsMargins(0, 0, 0, 0)
                        self.stackedWidget.setStyleSheet(
                            "background: transparent; border: none;"
                        )

                        self.script_list: List[
                            ScriptManager.ScriptSettingBox.MaaSettingBox.UserManager.UserSettingBox.UserMemberSettingBox
                        ] = []

                        self.user_dashboard = self.UserDashboard(self.name, self)
                        self.user_dashboard.switch_to.connect(self.switch_SettingBox)
                        self.stackedWidget.addWidget(self.user_dashboard)
                        self.pivot.addItem(routeKey="用户仪表盘", text="用户仪表盘")

                        self.Layout = QVBoxLayout(self)
                        self.Layout.addWidget(self.pivotArea)
                        self.Layout.addWidget(self.stackedWidget)
                        self.Layout.setContentsMargins(0, 0, 0, 0)

                        self.pivot.currentItemChanged.connect(
                            lambda index: self.switch_SettingBox(
                                index, if_change_pivot=False
                            )
                        )

                        self.show_SettingBox("用户仪表盘")

                    def show_SettingBox(self, index: str) -> None:
                        """
                        加载所有子界面并切换到指定子界面

                        :param index: 要切换到的子界面索引或名称
                        :type index: str
                        """

                        Config.search_maa_user(self.name)

                        for name in Config.script_dict[self.name]["UserData"].keys():
                            self.add_userSettingBox(name[3:])

                        self.switch_SettingBox(index)

                    def switch_SettingBox(
                        self, index: str, if_change_pivot: bool = True
                    ) -> None:
                        """
                        切换到指定的子界面

                        :param index: 要切换到的子界面索引或名称
                        :type index: str
                        :param if_change_pivot: 是否更改导航栏的当前项
                        :type if_change_pivot: bool
                        """

                        if len(Config.script_dict[self.name]["UserData"]) == 0:
                            index = "用户仪表盘"

                        if index != "用户仪表盘" and int(index[3:]) > len(
                            Config.script_dict[self.name]["UserData"]
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
                        """清空除用户仪表盘外所有子界面"""

                        for sub_interface in self.script_list:
                            Config.stage_refreshed.disconnect(
                                sub_interface.refresh_stage
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
                        """
                        添加一个用户设置界面

                        :param uid: 用户的唯一标识符
                        :type uid: int
                        """

                        setting_box = self.UserMemberSettingBox(self.name, uid, self)

                        self.script_list.append(setting_box)

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
                            self.dashboard.setColumnCount(12)
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
                                    "备选 - 3",
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
                            for col in range(6, 11):
                                self.dashboard.horizontalHeader().setSectionResizeMode(
                                    col, QHeaderView.ResizeMode.Stretch
                                )
                            self.dashboard.horizontalHeader().setSectionResizeMode(
                                11, QHeaderView.ResizeMode.Fixed
                            )
                            self.dashboard.setColumnWidth(11, 32)

                            self.viewLayout.addWidget(self.dashboard)
                            self.viewLayout.setContentsMargins(3, 0, 3, 3)

                            Config.PASSWORD_refreshed.connect(self.load_info)

                        def load_info(self):
                            """加载用户信息到仪表盘"""

                            logger.info(
                                f"正在加载 {self.name} 用户信息到仪表盘",
                                module="脚本管理",
                            )

                            self.user_data = Config.script_dict[self.name]["UserData"]

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

                                stage_info = config.get_plan_info()

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
                                self.dashboard.setCellWidget(
                                    int(name[3:]) - 1,
                                    3,
                                    StatusSwitchSetting(
                                        qconfig=config,
                                        configItem_check=config.Info_Status,
                                        configItem_enable=config.Info_RemainedDay,
                                        parent=self,
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
                                    QTableWidgetItem(str(stage_info["MedicineNumb"])),
                                )
                                self.dashboard.setItem(
                                    int(name[3:]) - 1,
                                    6,
                                    QTableWidgetItem(
                                        Config.stage_dict["ALL"]["text"][
                                            Config.stage_dict["ALL"]["value"].index(
                                                stage_info["Stage"]
                                            )
                                        ]
                                        if stage_info["Stage"]
                                        in Config.stage_dict["ALL"]["value"]
                                        else stage_info["Stage"]
                                    ),
                                )
                                self.dashboard.setItem(
                                    int(name[3:]) - 1,
                                    7,
                                    QTableWidgetItem(
                                        Config.stage_dict["ALL"]["text"][
                                            Config.stage_dict["ALL"]["value"].index(
                                                stage_info["Stage_1"]
                                            )
                                        ]
                                        if stage_info["Stage_1"]
                                        in Config.stage_dict["ALL"]["value"]
                                        else stage_info["Stage_1"]
                                    ),
                                )
                                self.dashboard.setItem(
                                    int(name[3:]) - 1,
                                    8,
                                    QTableWidgetItem(
                                        Config.stage_dict["ALL"]["text"][
                                            Config.stage_dict["ALL"]["value"].index(
                                                stage_info["Stage_2"]
                                            )
                                        ]
                                        if stage_info["Stage_2"]
                                        in Config.stage_dict["ALL"]["value"]
                                        else stage_info["Stage_2"]
                                    ),
                                )
                                self.dashboard.setItem(
                                    int(name[3:]) - 1,
                                    9,
                                    QTableWidgetItem(
                                        Config.stage_dict["ALL"]["text"][
                                            Config.stage_dict["ALL"]["value"].index(
                                                stage_info["Stage_3"]
                                            )
                                        ]
                                        if stage_info["Stage_3"]
                                        in Config.stage_dict["ALL"]["value"]
                                        else stage_info["Stage_3"]
                                    ),
                                )
                                self.dashboard.setItem(
                                    int(name[3:]) - 1,
                                    10,
                                    QTableWidgetItem(
                                        "不使用"
                                        if stage_info["Stage_Remain"] == "-"
                                        else (
                                            (
                                                Config.stage_dict["ALL"]["text"][
                                                    Config.stage_dict["ALL"][
                                                        "value"
                                                    ].index(stage_info["Stage_Remain"])
                                                ]
                                            )
                                            if stage_info["Stage_Remain"]
                                            in Config.stage_dict["ALL"]["value"]
                                            else stage_info["Stage_Remain"]
                                        )
                                    ),
                                )
                                self.dashboard.setCellWidget(
                                    int(name[3:]) - 1, 11, button
                                )

                            logger.success(
                                f"{self.name} 用户仪表盘成功加载信息", module="脚本管理"
                            )

                    class UserMemberSettingBox(HeaderCardWidget):
                        """用户管理子页面"""

                        def __init__(self, name: str, uid: int, parent=None):
                            super().__init__(parent)

                            self.setObjectName(f"用户_{uid}")
                            self.setTitle(f"用户 {uid}")
                            self.name = name
                            self.config = Config.script_dict[self.name]["UserData"][
                                f"用户_{uid}"
                            ]["Config"]
                            self.user_path = Config.script_dict[self.name]["UserData"][
                                f"用户_{uid}"
                            ]["Path"]

                            plan_list = [
                                ["固定"] + [_ for _ in Config.plan_dict.keys()],
                                ["固定"]
                                + [
                                    (
                                        k
                                        if v["Config"].get(v["Config"].Info_Name) == ""
                                        else f"{k} - {v["Config"].get(v["Config"].Info_Name)}"
                                    )
                                    for k, v in Config.plan_dict.items()
                                ],
                            ]

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
                            self.card_Server = ComboBoxSettingCard(
                                icon=FluentIcon.PROJECTOR,
                                title="服务器",
                                content="选择服务器类型",
                                texts=[
                                    "官服",
                                    "B服",
                                    "悠星国际服",
                                    "悠星日服",
                                    "悠星韩服",
                                    "繁中服",
                                ],
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
                            self.card_Annihilation = ComboBoxSettingCard(
                                icon=FluentIcon.CAFE,
                                title="剿灭代理",
                                content="剿灭代理子任务相关设置",
                                texts=[
                                    "关闭",
                                    "当期剿灭",
                                    "切尔诺伯格",
                                    "龙门外环",
                                    "龙门市区",
                                ],
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
                                content="自定义基建配置文件未生效",
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
                            self.card_MedicineNumb = SpinBoxWithPlanSettingCard(
                                icon=FluentIcon.GAME,
                                title="吃理智药",
                                content="吃理智药次数，输入0以关闭",
                                range=(0, 1024),
                                qconfig=self.config,
                                configItem=self.config.Info_MedicineNumb,
                                parent=self,
                            )
                            self.card_SeriesNumb = ComboBoxWithPlanSettingCard(
                                icon=FluentIcon.GAME,
                                title="连战次数",
                                content="连战次数较大时建议搭配剩余理智关卡使用",
                                texts=["AUTO", "6", "5", "4", "3", "2", "1", "不选择"],
                                qconfig=self.config,
                                configItem=self.config.Info_SeriesNumb,
                                parent=self,
                            )
                            self.card_SeriesNumb.comboBox.setMinimumWidth(150)
                            self.card_StageMode = NoOptionComboBoxSettingCard(
                                icon=FluentIcon.DICTIONARY,
                                title="关卡配置模式",
                                content="刷理智关卡号的配置模式",
                                value=plan_list[0],
                                texts=plan_list[1],
                                qconfig=self.config,
                                configItem=self.config.Info_StageMode,
                                parent=self,
                            )
                            self.card_StageMode.comboBox.setMinimumWidth(150)
                            self.card_Stage = EditableComboBoxWithPlanSettingCard(
                                icon=FluentIcon.GAME,
                                title="关卡选择",
                                content="按下回车以添加自定义关卡号",
                                value=Config.stage_dict["ALL"]["value"],
                                texts=Config.stage_dict["ALL"]["text"],
                                qconfig=self.config,
                                configItem=self.config.Info_Stage,
                                parent=self,
                            )
                            self.card_Stage_1 = EditableComboBoxWithPlanSettingCard(
                                icon=FluentIcon.GAME,
                                title="备选关卡 - 1",
                                content="按下回车以添加自定义关卡号",
                                value=Config.stage_dict["ALL"]["value"],
                                texts=Config.stage_dict["ALL"]["text"],
                                qconfig=self.config,
                                configItem=self.config.Info_Stage_1,
                                parent=self,
                            )
                            self.card_Stage_2 = EditableComboBoxWithPlanSettingCard(
                                icon=FluentIcon.GAME,
                                title="备选关卡 - 2",
                                content="按下回车以添加自定义关卡号",
                                value=Config.stage_dict["ALL"]["value"],
                                texts=Config.stage_dict["ALL"]["text"],
                                qconfig=self.config,
                                configItem=self.config.Info_Stage_2,
                                parent=self,
                            )
                            self.card_Stage_3 = EditableComboBoxWithPlanSettingCard(
                                icon=FluentIcon.GAME,
                                title="备选关卡 - 3",
                                content="按下回车以添加自定义关卡号",
                                value=Config.stage_dict["ALL"]["value"],
                                texts=Config.stage_dict["ALL"]["text"],
                                qconfig=self.config,
                                configItem=self.config.Info_Stage_3,
                                parent=self,
                            )
                            self.card_Stage_Remain = (
                                EditableComboBoxWithPlanSettingCard(
                                    icon=FluentIcon.GAME,
                                    title="剩余理智关卡",
                                    content="按下回车以添加自定义关卡号",
                                    value=Config.stage_dict["ALL"]["value"],
                                    texts=[
                                        "不使用" if _ == "当前/上次" else _
                                        for _ in Config.stage_dict["ALL"]["text"]
                                    ],
                                    qconfig=self.config,
                                    configItem=self.config.Info_Stage_Remain,
                                    parent=self,
                                )
                            )
                            self.card_Skland = PasswordLineAndSwitchButtonSettingCard(
                                icon=FluentIcon.CERTIFICATE,
                                title="森空岛签到",
                                content="此功能具有一定风险，请谨慎使用！获取登录凭证请查阅「文档-进阶功能」。",
                                text="鹰角网络通行证登录凭证",
                                algorithm="DPAPI",
                                qconfig=self.config,
                                configItem_bool=self.config.Info_IfSkland,
                                configItem_info=self.config.Info_SklandToken,
                                parent=self,
                            )
                            self.card_Skland.LineEdit.setMinimumWidth(250)

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
                                    "IfSkland": self.config.Info_IfSkland,
                                    "LastSklandDate": self.config.Data_LastSklandDate,
                                },
                                parent=self,
                            )

                            # 单独任务卡片
                            self.card_TaskSet = UserTaskSettingCard(
                                icon=FluentIcon.LIBRARY,
                                title="自动日常代理任务序列",
                                content="未启用任何任务项",
                                text="设置",
                                qconfig=self.config,
                                configItems={
                                    "IfWakeUp": self.config.Task_IfWakeUp,
                                    "IfRecruiting": self.config.Task_IfRecruiting,
                                    "IfBase": self.config.Task_IfBase,
                                    "IfCombat": self.config.Task_IfCombat,
                                    "IfMall": self.config.Task_IfMall,
                                    "IfMission": self.config.Task_IfMission,
                                    "IfAutoRoguelike": self.config.Task_IfAutoRoguelike,
                                    "IfReclamation": self.config.Task_IfReclamation,
                                },
                                parent=self,
                            )
                            self.card_IfWakeUp = SwitchSettingCard(
                                icon=FluentIcon.TILES,
                                title="开始唤醒",
                                content="",
                                qconfig=self.config,
                                configItem=self.config.Task_IfWakeUp,
                                parent=self,
                            )
                            self.card_IfRecruiting = SwitchSettingCard(
                                icon=FluentIcon.TILES,
                                title="自动公招",
                                content="",
                                qconfig=self.config,
                                configItem=self.config.Task_IfRecruiting,
                                parent=self,
                            )
                            self.card_IfBase = SwitchSettingCard(
                                icon=FluentIcon.TILES,
                                title="基建换班",
                                content="",
                                qconfig=self.config,
                                configItem=self.config.Task_IfBase,
                                parent=self,
                            )
                            self.card_IfCombat = SwitchSettingCard(
                                icon=FluentIcon.TILES,
                                title="刷理智",
                                content="",
                                qconfig=self.config,
                                configItem=self.config.Task_IfCombat,
                                parent=self,
                            )
                            self.card_IfMall = SwitchSettingCard(
                                icon=FluentIcon.TILES,
                                title="获取信用及购物",
                                content="",
                                qconfig=self.config,
                                configItem=self.config.Task_IfMall,
                                parent=self,
                            )
                            self.card_IfMission = SwitchSettingCard(
                                icon=FluentIcon.TILES,
                                title="领取奖励",
                                content="",
                                qconfig=self.config,
                                configItem=self.config.Task_IfMission,
                                parent=self,
                            )
                            self.card_IfAutoRoguelike = SwitchSettingCard(
                                icon=FluentIcon.TILES,
                                title="自动肉鸽",
                                content="",
                                qconfig=self.config,
                                configItem=self.config.Task_IfAutoRoguelike,
                                parent=self,
                            )
                            self.card_IfReclamation = SwitchSettingCard(
                                icon=FluentIcon.TILES,
                                title="生息演算",
                                content="",
                                qconfig=self.config,
                                configItem=self.config.Task_IfReclamation,
                                parent=self,
                            )

                            self.TaskSetCard = SettingFlyoutView(
                                self,
                                "自动日常代理任务序列设置",
                                [
                                    self.card_IfWakeUp,
                                    self.card_IfRecruiting,
                                    self.card_IfBase,
                                    self.card_IfCombat,
                                    self.card_IfMall,
                                    self.card_IfMission,
                                    self.card_IfAutoRoguelike,
                                    self.card_IfReclamation,
                                ],
                            )

                            # 单独通知卡片
                            self.card_NotifySet = UserNoticeSettingCard(
                                icon=FluentIcon.MAIL,
                                title="用户单独通知设置",
                                content="未启用任何通知项",
                                text="设置",
                                qconfig=self.config,
                                configItem=self.config.Notify_Enabled,
                                configItems={
                                    "IfSendStatistic": self.config.Notify_IfSendStatistic,
                                    "IfSendSixStar": self.config.Notify_IfSendSixStar,
                                    "IfSendMail": self.config.Notify_IfSendMail,
                                    "ToAddress": self.config.Notify_ToAddress,
                                    "IfServerChan": self.config.Notify_IfServerChan,
                                    "ServerChanKey": self.config.Notify_ServerChanKey,
                                    "IfCompanyWebHookBot": self.config.Notify_IfCompanyWebHookBot,
                                    "CompanyWebHookBotUrl": self.config.Notify_CompanyWebHookBotUrl,
                                },
                                parent=self,
                            )
                            self.card_NotifyContent = self.NotifyContentSettingCard(
                                self.config, self
                            )
                            self.card_EMail = self.EMailSettingCard(self.config, self)
                            self.card_ServerChan = self.ServerChanSettingCard(
                                self.config, self
                            )
                            self.card_CompanyWebhookBot = (
                                self.CompanyWechatPushSettingCard(self.config, self)
                            )

                            self.NotifySetCard = SettingFlyoutView(
                                self,
                                "用户通知设置",
                                [
                                    self.card_NotifyContent,
                                    self.card_EMail,
                                    self.card_ServerChan,
                                    self.card_CompanyWebhookBot,
                                ],
                            )

                            h1_layout = QHBoxLayout()
                            h1_layout.addWidget(self.card_Name)
                            h1_layout.addWidget(self.card_Id)
                            h2_layout = QHBoxLayout()
                            h2_layout.addWidget(self.card_Mode)
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
                            h7_layout.addWidget(self.card_StageMode)
                            h7_layout.addWidget(self.card_Stage)
                            h8_layout = QHBoxLayout()
                            h8_layout.addWidget(self.card_Stage_1)
                            h8_layout.addWidget(self.card_Stage_2)
                            h9_layout = QHBoxLayout()
                            h9_layout.addWidget(self.card_Stage_3)
                            h9_layout.addWidget(self.card_Stage_Remain)

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
                            Layout.addLayout(h9_layout)
                            Layout.addWidget(self.card_Skland)
                            Layout.addWidget(self.card_TaskSet)
                            Layout.addWidget(self.card_NotifySet)

                            self.viewLayout.addLayout(Layout)
                            self.viewLayout.setContentsMargins(3, 0, 3, 3)

                            self.card_Mode.comboBox.currentIndexChanged.connect(
                                self.switch_mode
                            )
                            self.card_InfrastMode.comboBox.currentIndexChanged.connect(
                                self.switch_infrastructure
                            )
                            self.card_Routine.clicked.connect(
                                lambda: self.set_maa("Routine")
                            )
                            self.card_InfrastMode.clicked.connect(
                                self.set_infrastructure
                            )
                            self.card_TaskSet.clicked.connect(self.set_task)
                            self.card_NotifySet.clicked.connect(self.set_notify)
                            self.card_StageMode.comboBox.currentIndexChanged.connect(
                                self.switch_stage_mode
                            )
                            Config.stage_refreshed.connect(self.refresh_stage)
                            Config.PASSWORD_refreshed.connect(self.refresh_password)

                            self.switch_mode()
                            self.switch_stage_mode()
                            self.switch_infrastructure()

                        def switch_mode(self) -> None:
                            """切换用户配置模式"""

                            if self.config.get(self.config.Info_Mode) == "简洁":

                                self.card_Routine.setVisible(False)
                                self.card_InfrastMode.setVisible(True)

                            elif self.config.get(self.config.Info_Mode) == "详细":

                                self.card_InfrastMode.setVisible(False)
                                self.card_Routine.setVisible(True)

                        def switch_stage_mode(self) -> None:
                            """切换关卡配置模式"""

                            for card, name in zip(
                                [
                                    self.card_MedicineNumb,
                                    self.card_SeriesNumb,
                                    self.card_Stage,
                                    self.card_Stage_1,
                                    self.card_Stage_2,
                                    self.card_Stage_3,
                                    self.card_Stage_Remain,
                                ],
                                [
                                    "MedicineNumb",
                                    "SeriesNumb",
                                    "Stage",
                                    "Stage_1",
                                    "Stage_2",
                                    "Stage_3",
                                    "Stage_Remain",
                                ],
                            ):

                                card.switch_mode(
                                    self.config.get(self.config.Info_StageMode)[:2]
                                )
                                if (
                                    self.config.get(self.config.Info_StageMode)
                                    != "固定"
                                ):
                                    card.change_plan(
                                        Config.plan_dict[
                                            self.config.get(self.config.Info_StageMode)
                                        ]["Config"].get_current_info(name)
                                    )

                        def switch_infrastructure(self) -> None:
                            """切换基建配置模式"""

                            if (
                                self.config.get(self.config.Info_InfrastMode)
                                == "Custom"
                            ):
                                self.card_InfrastMode.button.setVisible(True)
                                with (
                                    self.user_path
                                    / "Infrastructure/infrastructure.json"
                                ).open(mode="r", encoding="utf-8") as f:
                                    infrastructure = json.load(f)
                                self.card_InfrastMode.setContent(
                                    f"当前基建配置：{infrastructure.get("title","未命名")}"
                                )
                            else:
                                self.card_InfrastMode.button.setVisible(False)
                                self.card_InfrastMode.setContent(
                                    "自定义基建配置文件未生效"
                                )

                        def refresh_stage(self):
                            """刷新关卡配置"""

                            self.card_Stage.reLoadOptions(
                                Config.stage_dict["ALL"]["value"],
                                Config.stage_dict["ALL"]["text"],
                            )
                            self.card_Stage_1.reLoadOptions(
                                Config.stage_dict["ALL"]["value"],
                                Config.stage_dict["ALL"]["text"],
                            )
                            self.card_Stage_2.reLoadOptions(
                                Config.stage_dict["ALL"]["value"],
                                Config.stage_dict["ALL"]["text"],
                            )
                            self.card_Stage_3.reLoadOptions(
                                Config.stage_dict["ALL"]["value"],
                                Config.stage_dict["ALL"]["text"],
                            )
                            self.card_Stage_Remain.reLoadOptions(
                                Config.stage_dict["ALL"]["value"],
                                Config.stage_dict["ALL"]["text"],
                            )

                        def refresh_password(self):
                            """刷新密码配置"""

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
                                self.switch_infrastructure()
                            else:
                                logger.warning("未选择自定义基建文件")
                                MainInfoBar.push_info_bar(
                                    "warning", "警告", "未选择自定义基建文件", 5000
                                )

                        def set_maa(self, mode: str) -> None:
                            """配置MAA子配置"""

                            if self.name in Config.running_list:
                                logger.warning("所属脚本正在运行", module="脚本管理")
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

                        def set_task(self) -> None:
                            """设置用户任务序列相关配置"""

                            self.TaskSetCard.setVisible(True)
                            Flyout.make(
                                self.TaskSetCard,
                                self.card_TaskSet,
                                self,
                                aniType=FlyoutAnimationType.PULL_UP,
                                isDeleteOnClose=False,
                            )

                        def set_notify(self) -> None:
                            """设置用户通知相关配置"""

                            self.NotifySetCard.setVisible(True)
                            Flyout.make(
                                self.NotifySetCard,
                                self.card_NotifySet,
                                self,
                                aniType=FlyoutAnimationType.PULL_UP,
                                isDeleteOnClose=False,
                            )

                        class NotifyContentSettingCard(HeaderCardWidget):

                            def __init__(self, config: MaaUserConfig, parent=None):
                                super().__init__(parent)
                                self.setTitle("用户通知内容选项")

                                self.config = config

                                self.card_IfSendStatistic = SwitchSettingCard(
                                    icon=FluentIcon.PAGE_RIGHT,
                                    title="推送统计信息",
                                    content="推送自动代理统计信息的通知",
                                    qconfig=self.config,
                                    configItem=self.config.Notify_IfSendStatistic,
                                    parent=self,
                                )
                                self.card_IfSendSixStar = SwitchSettingCard(
                                    icon=FluentIcon.PAGE_RIGHT,
                                    title="推送公招高资喜报",
                                    content="公招出现六星词条时推送喜报",
                                    qconfig=self.config,
                                    configItem=self.config.Notify_IfSendSixStar,
                                    parent=self,
                                )

                                Layout = QVBoxLayout()
                                Layout.addWidget(self.card_IfSendStatistic)
                                Layout.addWidget(self.card_IfSendSixStar)
                                self.viewLayout.addLayout(Layout)
                                self.viewLayout.setSpacing(3)
                                self.viewLayout.setContentsMargins(3, 0, 3, 3)

                        class EMailSettingCard(HeaderCardWidget):

                            def __init__(self, config: MaaUserConfig, parent=None):
                                super().__init__(parent)
                                self.setTitle("用户邮箱通知")

                                self.config = config

                                self.card_IfSendMail = SwitchSettingCard(
                                    icon=FluentIcon.PAGE_RIGHT,
                                    title="推送用户邮件通知",
                                    content="是否启用用户邮件通知功能",
                                    qconfig=self.config,
                                    configItem=self.config.Notify_IfSendMail,
                                    parent=self,
                                )
                                self.card_ToAddress = LineEditSettingCard(
                                    icon=FluentIcon.PAGE_RIGHT,
                                    title="用户收信邮箱地址",
                                    content="接收用户通知的邮箱地址",
                                    text="请输入用户收信邮箱地址",
                                    qconfig=self.config,
                                    configItem=self.config.Notify_ToAddress,
                                    parent=self,
                                )

                                Layout = QVBoxLayout()
                                Layout.addWidget(self.card_IfSendMail)
                                Layout.addWidget(self.card_ToAddress)
                                self.viewLayout.addLayout(Layout)
                                self.viewLayout.setSpacing(3)
                                self.viewLayout.setContentsMargins(3, 0, 3, 3)

                        class ServerChanSettingCard(HeaderCardWidget):

                            def __init__(self, config: MaaUserConfig, parent=None):
                                super().__init__(parent)
                                self.setTitle("用户ServerChan通知")

                                self.config = config

                                self.card_IfServerChan = SwitchSettingCard(
                                    icon=FluentIcon.PAGE_RIGHT,
                                    title="推送用户Server酱通知",
                                    content="是否启用用户Server酱通知功能",
                                    qconfig=self.config,
                                    configItem=self.config.Notify_IfServerChan,
                                    parent=self,
                                )
                                self.card_ServerChanKey = LineEditSettingCard(
                                    icon=FluentIcon.PAGE_RIGHT,
                                    title="用户SendKey",
                                    content="SC3与SCT均须填写",
                                    text="请输入用户SendKey",
                                    qconfig=self.config,
                                    configItem=self.config.Notify_ServerChanKey,
                                    parent=self,
                                )
                                self.card_ServerChanChannel = LineEditSettingCard(
                                    icon=FluentIcon.PAGE_RIGHT,
                                    title="用户ServerChanChannel代码",
                                    content="留空则默认，多个请使用「|」隔开",
                                    text="请输入Channel代码，仅SCT生效",
                                    qconfig=self.config,
                                    configItem=self.config.Notify_ServerChanChannel,
                                    parent=self,
                                )
                                self.card_ServerChanTag = LineEditSettingCard(
                                    icon=FluentIcon.PAGE_RIGHT,
                                    title="用户Tag内容",
                                    content="留空则默认，多个请使用「|」隔开",
                                    text="请输入加入推送的Tag，仅SC3生效",
                                    qconfig=self.config,
                                    configItem=self.config.Notify_ServerChanTag,
                                    parent=self,
                                )

                                Layout = QVBoxLayout()
                                Layout.addWidget(self.card_IfServerChan)
                                Layout.addWidget(self.card_ServerChanKey)
                                Layout.addWidget(self.card_ServerChanChannel)
                                Layout.addWidget(self.card_ServerChanTag)
                                self.viewLayout.addLayout(Layout)
                                self.viewLayout.setSpacing(3)
                                self.viewLayout.setContentsMargins(3, 0, 3, 3)

                        class CompanyWechatPushSettingCard(HeaderCardWidget):

                            def __init__(self, config: MaaUserConfig, parent=None):
                                super().__init__(parent)
                                self.setTitle("用户企业微信推送")

                                self.config = config

                                self.card_IfCompanyWebHookBot = SwitchSettingCard(
                                    icon=FluentIcon.PAGE_RIGHT,
                                    title="推送用户企业微信机器人通知",
                                    content="是否启用用户企微机器人通知功能",
                                    qconfig=self.config,
                                    configItem=self.config.Notify_IfCompanyWebHookBot,
                                    parent=self,
                                )
                                self.card_CompanyWebHookBotUrl = LineEditSettingCard(
                                    icon=FluentIcon.PAGE_RIGHT,
                                    title="WebhookUrl",
                                    content="用户企微群机器人Webhook地址",
                                    text="请输入用户Webhook的Url",
                                    qconfig=self.config,
                                    configItem=self.config.Notify_CompanyWebHookBotUrl,
                                    parent=self,
                                )

                                Layout = QVBoxLayout()
                                Layout.addWidget(self.card_IfCompanyWebHookBot)
                                Layout.addWidget(self.card_CompanyWebHookBotUrl)
                                self.viewLayout.addLayout(Layout)
                                self.viewLayout.setSpacing(3)
                                self.viewLayout.setContentsMargins(3, 0, 3, 3)

        class GeneralSettingBox(QWidget):
            """通用脚本设置界面"""

            def __init__(self, uid: int, parent=None):
                super().__init__(parent)

                self.setObjectName(f"脚本_{uid}")
                self.config = Config.script_dict[f"脚本_{uid}"]["Config"]

                self.app_setting = self.AppSettingCard(f"脚本_{uid}", self.config, self)
                self.branch_manager = self.BranchManager(f"脚本_{uid}", self)

                content_widget = QWidget()
                content_layout = QVBoxLayout(content_widget)
                content_layout.setContentsMargins(0, 0, 11, 0)
                content_layout.addWidget(self.app_setting)
                content_layout.addWidget(self.branch_manager)
                content_layout.addStretch(1)

                scrollArea = ScrollArea()
                scrollArea.setWidgetResizable(True)
                scrollArea.setContentsMargins(0, 0, 0, 0)
                scrollArea.setStyleSheet("background: transparent; border: none;")
                scrollArea.setWidget(content_widget)

                layout = QVBoxLayout(self)
                layout.addWidget(scrollArea)

            class AppSettingCard(HeaderCardWidget):

                def __init__(self, name: str, config: GeneralConfig, parent=None):
                    super().__init__(parent)

                    self.setTitle("通用实例")

                    self.name = name
                    self.config = config

                    Layout = QVBoxLayout()

                    self.card_Name = LineEditSettingCard(
                        icon=FluentIcon.EDIT,
                        title="实例名称",
                        content="用于标识通用实例的名称",
                        text="请输入实例名称",
                        qconfig=self.config,
                        configItem=self.config.Script_Name,
                        parent=self,
                    )
                    self.card_Script = self.ScriptSettingCard(self.config, self)
                    self.card_Game = self.GameSettingCard(self.config, self)
                    self.card_Run = self.RunSettingCard(self.config, self)
                    self.card_Config = self.ConfigSettingCard(
                        self.name, self.config, self
                    )

                    Layout.addWidget(self.card_Name)
                    Layout.addWidget(self.card_Script)
                    Layout.addWidget(self.card_Game)
                    Layout.addWidget(self.card_Run)
                    Layout.addWidget(self.card_Config)
                    self.viewLayout.addLayout(Layout)

                class ScriptSettingCard(ExpandGroupSettingCard):

                    def __init__(self, config: GeneralConfig, parent=None):
                        super().__init__(
                            FluentIcon.SETTING, "脚本设置", "脚本属性配置选项", parent
                        )
                        self.config = config

                        self.card_RootPath = PathSettingCard(
                            icon=FluentIcon.FOLDER,
                            title="脚本根目录 - [必填]",
                            mode="文件夹",
                            text="选择文件夹",
                            qconfig=self.config,
                            configItem=self.config.Script_RootPath,
                            parent=self,
                        )
                        self.card_ScriptPath = PathSettingCard(
                            icon=FluentIcon.FOLDER,
                            title="脚本路径 - [必填]",
                            mode="可执行文件 (*.exe *.bat)",
                            text="选择程序",
                            qconfig=self.config,
                            configItem=self.config.Script_ScriptPath,
                            parent=self,
                        )
                        self.card_Arguments = LineEditSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="脚本启动参数",
                            content="脚本启动时的附加参数",
                            text="请输入脚本参数",
                            qconfig=self.config,
                            configItem=self.config.Script_Arguments,
                            parent=self,
                        )
                        self.card_IfTrackProcess = SwitchSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="追踪脚本子进程",
                            content="启用后将在脚本启动后 60s 内追踪其子进程，并仅在所有子进程结束后判定脚本中止",
                            qconfig=self.config,
                            configItem=self.config.Script_IfTrackProcess,
                            parent=self,
                        )
                        self.card_ConfigPath = PathSettingCard(
                            icon=FluentIcon.FOLDER,
                            title="脚本配置文件路径 - [必填]",
                            mode=self.config.Script_ConfigPathMode,
                            text="选择路径",
                            qconfig=self.config,
                            configItem=self.config.Script_ConfigPath,
                            parent=self,
                        )
                        self.card_UpdateConfigMode = ComboBoxSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="脚本配置文件更新时机",
                            content="在选定的时机自动更新配置文件",
                            texts=[
                                "从不",
                                "仅任务成功后",
                                "仅任务失败后",
                                "任务完成后",
                            ],
                            qconfig=self.config,
                            configItem=self.config.Script_UpdateConfigMode,
                            parent=self,
                        )
                        self.card_LogPath = PathSettingCard(
                            icon=FluentIcon.FOLDER,
                            title="脚本日志文件路径 - [必填]",
                            mode="所有文件 (*)",
                            text="选择文件",
                            qconfig=self.config,
                            configItem=self.config.Script_LogPath,
                            parent=self,
                        )
                        self.card_LogPathFormat = LineEditSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="脚本日志文件名格式",
                            content="若脚本日志文件名中随时间变化，请填入时间格式，留空则不启用",
                            text="请输入脚本日志文件名格式",
                            qconfig=self.config,
                            configItem=self.config.Script_LogPathFormat,
                            parent=self,
                        )
                        self.card_LogTimeStart = SpinBoxSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="脚本日志时间起始位置 - [必填]",
                            content="脚本日志中时间的起始位置，单位为字符",
                            range=(1, 1024),
                            qconfig=self.config,
                            configItem=self.config.Script_LogTimeStart,
                            parent=self,
                        )
                        self.card_LogTimeEnd = SpinBoxSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="脚本日志时间结束位置 - [必填]",
                            content="脚本日志中时间的结束位置，单位为字符",
                            range=(1, 1024),
                            qconfig=self.config,
                            configItem=self.config.Script_LogTimeEnd,
                            parent=self,
                        )
                        self.card_LogTimeFormat = LineEditSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="脚本日志时间格式 - [必填]",
                            content="脚本日志中时间的格式",
                            text="请输入脚本日志时间格式",
                            qconfig=self.config,
                            configItem=self.config.Script_LogTimeFormat,
                            parent=self,
                        )
                        self.card_SuccessLog = LineEditSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="脚本成功日志",
                            content="任务成功完成时出现的日志，多条请使用「|」隔开",
                            text="请输入脚本成功日志内容",
                            qconfig=self.config,
                            configItem=self.config.Script_SuccessLog,
                            parent=self,
                        )
                        self.card_ErrorLog = LineEditSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="脚本异常日志 - [必填]",
                            content="脚本运行异常时的日志内容，多条请使用「|」隔开",
                            text="请输入脚本异常日志内容",
                            qconfig=self.config,
                            configItem=self.config.Script_ErrorLog,
                            parent=self,
                        )

                        self.card_RootPath.pathChanged.connect(self.change_path)
                        self.card_ScriptPath.pathChanged.connect(
                            lambda old, new: self.check_path(
                                self.config.Script_ScriptPath, old, new
                            )
                        )
                        self.card_ConfigPath.pathChanged.connect(
                            lambda old, new: self.check_path(
                                self.config.Script_ConfigPath, old, new
                            )
                        )
                        self.card_LogPath.pathChanged.connect(
                            lambda old, new: self.check_path(
                                self.config.Script_LogPath, old, new
                            )
                        )

                        h_layout = QHBoxLayout()
                        h_layout.addWidget(self.card_LogTimeStart)
                        h_layout.addWidget(self.card_LogTimeEnd)

                        widget = QWidget()
                        Layout = QVBoxLayout(widget)
                        Layout.addWidget(self.card_RootPath)
                        Layout.addWidget(self.card_ScriptPath)
                        Layout.addWidget(self.card_Arguments)
                        Layout.addWidget(self.card_IfTrackProcess)
                        Layout.addWidget(self.card_ConfigPath)
                        Layout.addWidget(self.card_UpdateConfigMode)
                        Layout.addWidget(self.card_LogPath)
                        Layout.addWidget(self.card_LogPathFormat)
                        Layout.addLayout(h_layout)
                        Layout.addWidget(self.card_LogTimeFormat)
                        Layout.addWidget(self.card_SuccessLog)
                        Layout.addWidget(self.card_ErrorLog)
                        self.viewLayout.setContentsMargins(0, 0, 0, 0)
                        self.viewLayout.setSpacing(0)
                        self.addGroupWidget(widget)

                    def change_path(self, old_path: Path, new_path: Path) -> None:
                        """
                        根据脚本根目录重新计算配置文件路径

                        :param old_path: 旧路径
                        :param new_path: 新路径
                        """

                        path_list = [
                            self.config.Script_ScriptPath,
                            self.config.Script_ConfigPath,
                            self.config.Script_LogPath,
                        ]

                        for path in path_list:

                            if Path(self.config.get(path)).is_relative_to(old_path):

                                relative_path = Path(self.config.get(path)).relative_to(
                                    old_path
                                )
                                self.config.set(path, str(new_path / relative_path))

                    def check_path(
                        self, configItem: ConfigItem, old_path: Path, new_path: Path
                    ) -> None:
                        """检查配置路径是否合法"""

                        if not new_path.is_relative_to(
                            Path(self.config.get(self.config.Script_RootPath))
                        ):

                            self.config.set(configItem, str(old_path))
                            logger.warning(
                                f"配置路径 {new_path} 不在脚本根目录下，已重置为 {old_path}",
                                module="脚本管理",
                            )
                            MainInfoBar.push_info_bar(
                                "warning", "路径异常", "所选路径不在脚本根目录下", 5000
                            )

                class GameSettingCard(ExpandGroupSettingCard):

                    def __init__(self, config: GeneralConfig, parent=None):
                        super().__init__(
                            FluentIcon.SETTING,
                            "游戏设置",
                            "游戏/模拟器属性配置选项",
                            parent,
                        )
                        self.config = config

                        self.card_Enabled = SwitchSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="游戏/模拟器相关功能",
                            content="是否由AUTO_MAA管理游戏/模拟器相关进程",
                            qconfig=self.config,
                            configItem=self.config.Game_Enabled,
                            parent=self,
                        )
                        self.card_Style = ComboBoxSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="游戏平台类型",
                            content="游戏运行在安卓模拟器还是客户端上",
                            texts=["安卓模拟器", "客户端"],
                            qconfig=self.config,
                            configItem=self.config.Game_Style,
                            parent=self,
                        )
                        self.card_Path = PathSettingCard(
                            icon=FluentIcon.FOLDER,
                            title="游戏/模拟器路径",
                            mode="可执行文件 (*.exe *.bat)",
                            text="选择文件",
                            qconfig=self.config,
                            configItem=self.config.Game_Path,
                            parent=self,
                        )
                        self.card_Arguments = LineEditSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="游戏/模拟器启动参数",
                            content="游戏/模拟器启动时的附加参数",
                            text="请输入游戏/模拟器参数",
                            qconfig=self.config,
                            configItem=self.config.Game_Arguments,
                            parent=self,
                        )
                        self.card_WaitTime = SpinBoxSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="等待游戏/模拟器启动时间",
                            content="启动游戏/模拟器与启动对应脚本的间隔时间，单位为秒",
                            range=(0, 1024),
                            qconfig=self.config,
                            configItem=self.config.Game_WaitTime,
                            parent=self,
                        )
                        self.card_IfForceClose = SwitchSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="游戏/模拟器强制关闭",
                            content="是否强制结束所有同路径进程",
                            qconfig=self.config,
                            configItem=self.config.Game_IfForceClose,
                            parent=self,
                        )

                        widget = QWidget()
                        Layout = QVBoxLayout(widget)
                        Layout.addWidget(self.card_Enabled)
                        Layout.addWidget(self.card_Style)
                        Layout.addWidget(self.card_Path)
                        Layout.addWidget(self.card_Arguments)
                        Layout.addWidget(self.card_WaitTime)
                        Layout.addWidget(self.card_IfForceClose)
                        self.viewLayout.setContentsMargins(0, 0, 0, 0)
                        self.viewLayout.setSpacing(0)
                        self.addGroupWidget(widget)

                class RunSettingCard(ExpandGroupSettingCard):

                    def __init__(self, config: GeneralConfig, parent=None):
                        super().__init__(
                            FluentIcon.SETTING, "运行设置", "运行调控配置选项", parent
                        )
                        self.config = config

                        self.card_ProxyTimesLimit = SpinBoxSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="子配置单日代理次数上限",
                            content="当子配置本日代理成功次数达到该阈值时跳过代理，阈值为「0」时视为无代理次数上限",
                            range=(0, 1024),
                            qconfig=self.config,
                            configItem=self.config.Run_ProxyTimesLimit,
                            parent=self,
                        )

                        self.card_RunTimesLimit = SpinBoxSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="代理重试次数限制",
                            content="若超过该次数限制仍未完成代理，视为代理失败",
                            range=(1, 1024),
                            qconfig=self.config,
                            configItem=self.config.Run_RunTimesLimit,
                            parent=self,
                        )
                        self.card_RunTimeLimit = SpinBoxSettingCard(
                            icon=FluentIcon.PAGE_RIGHT,
                            title="自动代理超时限制",
                            content="脚本日志无变化时间超过该阈值视为超时，单位为分钟",
                            range=(1, 1024),
                            qconfig=self.config,
                            configItem=self.config.Run_RunTimeLimit,
                            parent=self,
                        )

                        widget = QWidget()
                        Layout = QVBoxLayout(widget)
                        Layout.addWidget(self.card_ProxyTimesLimit)
                        Layout.addWidget(self.card_RunTimesLimit)
                        Layout.addWidget(self.card_RunTimeLimit)
                        self.viewLayout.setContentsMargins(0, 0, 0, 0)
                        self.viewLayout.setSpacing(0)
                        self.addGroupWidget(widget)

                class ConfigSettingCard(ExpandGroupSettingCard):

                    def __init__(self, name: str, config: GeneralConfig, parent=None):
                        super().__init__(
                            FluentIcon.SETTING,
                            "配置管理",
                            "使用配置模板文件快速设置脚本",
                            parent,
                        )
                        self.name = name
                        self.config = config

                        self.card_ImportFromFile = PushSettingCard(
                            text="从文件导入",
                            icon=FluentIcon.PAGE_RIGHT,
                            title="从文件导入通用配置",
                            content="选择一个配置文件，导入其中的配置信息",
                            parent=self,
                        )
                        self.card_ExportToFile = PushSettingCard(
                            text="导出到文件",
                            icon=FluentIcon.PAGE_RIGHT,
                            title="导出通用配置到文件",
                            content="选择一个保存路径，将当前配置信息导出到文件",
                            parent=self,
                        )
                        self.card_ImportFromWeb = PushSettingCard(
                            text="查看",
                            icon=FluentIcon.PAGE_RIGHT,
                            title="从「AUTO_MAA 配置分享中心」导入",
                            content="从「AUTO_MAA 配置分享中心」选择一个用户分享的通用配置模板，导入其中的配置信息",
                            parent=self,
                        )
                        self.card_UploadToWeb = PushSettingCard(
                            text="上传",
                            icon=FluentIcon.PAGE_RIGHT,
                            title="上传到「AUTO_MAA 配置分享中心」",
                            content="将当前通用配置分享到「AUTO_MAA 配置分享中心」，通过审核后可供其他用户下载使用",
                            parent=self,
                        )

                        self.card_ImportFromFile.clicked.connect(self.import_from_file)
                        self.card_ExportToFile.clicked.connect(self.export_to_file)
                        self.card_ImportFromWeb.clicked.connect(self.import_from_web)
                        self.card_UploadToWeb.clicked.connect(self.upload_to_web)

                        widget = QWidget()
                        Layout = QVBoxLayout(widget)
                        Layout.addWidget(self.card_ImportFromFile)
                        Layout.addWidget(self.card_ExportToFile)
                        Layout.addWidget(self.card_ImportFromWeb)
                        Layout.addWidget(self.card_UploadToWeb)
                        self.viewLayout.setContentsMargins(0, 0, 0, 0)
                        self.viewLayout.setSpacing(0)
                        self.addGroupWidget(widget)

                    def import_from_file(self):
                        """从文件导入配置"""

                        file_path, _ = QFileDialog.getOpenFileName(
                            self, "选择配置文件", "", "JSON Files (*.json)"
                        )
                        if file_path:

                            shutil.copy(
                                file_path,
                                Config.script_dict[self.name]["Path"] / "config.json",
                            )
                            self.config.load(
                                Config.script_dict[self.name]["Path"] / "config.json"
                            )

                            logger.success(
                                f"{self.name} 配置导入成功", module="脚本管理"
                            )
                            MainInfoBar.push_info_bar(
                                "success",
                                "操作成功",
                                f"{self.name} 配置导入成功",
                                3000,
                            )

                    def export_to_file(self):
                        """导出配置到文件"""

                        file_path, _ = QFileDialog.getSaveFileName(
                            self, "选择保存路径", "", "JSON Files (*.json)"
                        )
                        if file_path:

                            temp = self.config.toDict()

                            # 移除配置中可能存在的隐私信息
                            temp["Script"]["Name"] = Path(file_path).stem
                            for path in ["ScriptPath", "ConfigPath", "LogPath"]:

                                if Path(temp["Script"][path]).is_relative_to(
                                    Path(temp["Script"]["RootPath"])
                                ):

                                    temp["Script"][path] = str(
                                        Path(r"C:/脚本根目录")
                                        / Path(temp["Script"][path]).relative_to(
                                            Path(temp["Script"]["RootPath"])
                                        )
                                    )
                            temp["Script"]["RootPath"] = str(Path(r"C:/脚本根目录"))

                            with open(file_path, "w", encoding="utf-8") as file:
                                json.dump(temp, file, ensure_ascii=False, indent=4)

                            logger.success(
                                f"{self.name} 配置导出成功", module="脚本管理"
                            )
                            MainInfoBar.push_info_bar(
                                "success",
                                "操作成功",
                                f"{self.name} 配置导出成功",
                                3000,
                            )

                    def import_from_web(self):
                        """从「AUTO_MAA 配置分享中心」导入配置"""

                        # 从远程服务器获取配置列表
                        network = Network.add_task(
                            mode="get",
                            url="http://221.236.27.82:10023/api/list/config/general",
                        )
                        network.loop.exec()
                        network_result = Network.get_result(network)
                        if network_result["status_code"] == 200:
                            config_info: List[Dict[str, str]] = network_result[
                                "response_json"
                            ]
                        else:
                            logger.warning(
                                f"获取配置列表时出错：{network_result['error_message']}",
                                module="脚本管理",
                            )
                            MainInfoBar.push_info_bar(
                                "warning",
                                "获取配置列表时出错",
                                f"网络错误：{network_result['status_code']}",
                                5000,
                            )
                            return None

                        choice = NoticeMessageBox(
                            self.window(),
                            "配置分享中心",
                            {
                                _[
                                    "configName"
                                ]: f"""
# {_['configName']}

- **作者**: {_['author']}

- **发布时间**：{_['createTime']}

- **描述**：{_['description']}
"""
                                for _ in config_info
                            },
                        )
                        if choice.exec() and choice.currentIndex != 0:

                            # 从远程服务器获取具体配置
                            network = Network.add_task(
                                mode="get",
                                url=config_info[choice.currentIndex - 1]["downloadUrl"],
                            )
                            network.loop.exec()
                            network_result = Network.get_result(network)
                            if network_result["status_code"] == 200:
                                config_data = network_result["response_json"]
                            else:
                                logger.warning(
                                    f"获取配置列表时出错：{network_result['error_message']}",
                                    module="脚本管理",
                                )
                                MainInfoBar.push_info_bar(
                                    "warning",
                                    "获取配置列表时出错",
                                    f"网络错误：{network_result['status_code']}",
                                    5000,
                                )
                                return None

                            with (
                                Config.script_dict[self.name]["Path"] / "config.json"
                            ).open("w", encoding="utf-8") as file:
                                json.dump(
                                    config_data, file, ensure_ascii=False, indent=4
                                )
                            self.config.load(
                                Config.script_dict[self.name]["Path"] / "config.json"
                            )

                            logger.success(
                                f"{self.name} 配置导入成功", module="脚本管理"
                            )
                            MainInfoBar.push_info_bar(
                                "success",
                                "操作成功",
                                f"{self.name} 配置导入成功",
                                3000,
                            )

                    def upload_to_web(self):
                        """上传配置到「AUTO_MAA 配置分享中心」"""

                        choice = LineEditMessageBox(
                            self.window(), "请输入你的用户名", "用户名", "明文"
                        )
                        choice.input.setMinimumWidth(200)
                        if choice.exec() and choice.input.text() != "":

                            author = choice.input.text()

                            choice = LineEditMessageBox(
                                self.window(), "请输入配置名称", "配置名称", "明文"
                            )
                            choice.input.setMinimumWidth(200)
                            if choice.exec() and choice.input.text() != "":

                                config_name = choice.input.text()

                                choice = LineEditMessageBox(
                                    self.window(),
                                    "请描述一下您要分享的配置",
                                    "配置描述",
                                    "明文",
                                )
                                choice.input.setMinimumWidth(300)
                                if choice.exec() and choice.input.text() != "":

                                    description = choice.input.text()

                                    temp = self.config.toDict()

                                    # 移除配置中可能存在的隐私信息
                                    temp["Script"]["Name"] = config_name
                                    for path in ["ScriptPath", "ConfigPath", "LogPath"]:
                                        if Path(temp["Script"][path]).is_relative_to(
                                            Path(temp["Script"]["RootPath"])
                                        ):
                                            temp["Script"][path] = str(
                                                Path(r"C:/脚本根目录")
                                                / Path(
                                                    temp["Script"][path]
                                                ).relative_to(
                                                    Path(temp["Script"]["RootPath"])
                                                )
                                            )
                                    temp["Script"]["RootPath"] = str(
                                        Path(r"C:/脚本根目录")
                                    )

                                    files = {
                                        "file": (
                                            f"{config_name}&&{author}&&{description}&&{int(datetime.now().timestamp() * 1000)}.json",
                                            json.dumps(temp, ensure_ascii=False),
                                            "application/json",
                                        )
                                    }
                                    data = {
                                        "username": author,
                                        "description": description,
                                    }

                                    # 配置上传至远程服务器
                                    network = Network.add_task(
                                        "upload_file",
                                        "http://221.236.27.82:10023/api/upload/share",
                                        files=files,
                                        data=data,
                                    )
                                    network.loop.exec()
                                    network_result = Network.get_result(network)
                                    if network_result["status_code"] == 200:
                                        response = network_result["response_json"]
                                    else:
                                        logger.warning(
                                            f"上传配置时出错：{network_result['error_message']}",
                                            module="脚本管理",
                                        )
                                        MainInfoBar.push_info_bar(
                                            "warning",
                                            "上传配置时出错",
                                            f"网络错误：{network_result['status_code']}",
                                            5000,
                                        )
                                        return None

                                    logger.success(
                                        f"{self.name} 配置上传成功", module="脚本管理"
                                    )
                                    MainInfoBar.push_info_bar(
                                        "success",
                                        "上传配置成功",
                                        (
                                            response["message"]
                                            if "message" in response
                                            else response["text"]
                                        ),
                                        5000,
                                    )

            class BranchManager(HeaderCardWidget):
                """分支管理父页面"""

                def __init__(self, name: str, parent=None):
                    super().__init__(parent)

                    self.setObjectName(f"{name}_分支管理")
                    self.setTitle("下属配置")
                    self.name = name

                    self.tools = CommandBar()
                    self.sub_manager = self.SubConfigSettingBox(self.name, self)

                    # 逐个添加动作
                    self.tools.addActions(
                        [
                            Action(
                                FluentIcon.ADD_TO, "新建配置", triggered=self.add_sub
                            ),
                            Action(
                                FluentIcon.REMOVE_FROM,
                                "删除配置",
                                triggered=self.del_sub,
                            ),
                        ]
                    )
                    self.tools.addSeparator()
                    self.tools.addActions(
                        [
                            Action(
                                FluentIcon.LEFT_ARROW,
                                "向前移动",
                                triggered=self.left_sub,
                            ),
                            Action(
                                FluentIcon.RIGHT_ARROW,
                                "向后移动",
                                triggered=self.right_sub,
                            ),
                        ]
                    )

                    layout = QVBoxLayout()
                    layout.addWidget(self.tools)
                    layout.addWidget(self.sub_manager)
                    self.viewLayout.addLayout(layout)

                def add_sub(self):
                    """添加一个配置"""

                    index = len(Config.script_dict[self.name]["SubData"]) + 1

                    logger.info(
                        f"正在添加 {self.name} 的配置_{index}", module="脚本管理"
                    )

                    # 初始化通用配置
                    sub_config = GeneralSubConfig()
                    sub_config.load(
                        Config.script_dict[self.name]["Path"]
                        / f"SubData/配置_{index}/config.json",
                        sub_config,
                    )
                    sub_config.save()

                    Config.script_dict[self.name]["SubData"][f"配置_{index}"] = {
                        "Path": Config.script_dict[self.name]["Path"]
                        / f"SubData/配置_{index}",
                        "Config": sub_config,
                    }

                    # 添加通用配置页面
                    self.sub_manager.add_SettingBox(index)
                    self.sub_manager.switch_SettingBox(f"配置_{index}")

                    logger.success(
                        f"{self.name} 配置_{index} 添加成功", module="脚本管理"
                    )
                    MainInfoBar.push_info_bar(
                        "success", "操作成功", f"{self.name} 添加 配置_{index}", 3000
                    )
                    SoundPlayer.play("添加配置")

                def del_sub(self):
                    """删除一个配置"""

                    name = self.sub_manager.pivot.currentRouteKey()

                    if name is None:
                        logger.warning("未选择配置", module="脚本管理")
                        MainInfoBar.push_info_bar(
                            "warning", "未选择配置", "请先选择一个配置", 5000
                        )
                        return None
                    if name == "配置仪表盘":
                        logger.warning("试图删除配置仪表盘", module="脚本管理")
                        MainInfoBar.push_info_bar(
                            "warning", "未选择配置", "请勿尝试删除配置仪表盘", 5000
                        )
                        return None

                    if self.name in Config.running_list:
                        logger.warning("所属脚本正在运行", module="脚本管理")
                        MainInfoBar.push_info_bar(
                            "warning", "所属脚本正在运行", "请先停止任务", 5000
                        )
                        return None

                    choice = MessageBox(
                        "确认", f"确定要删除 {name} 吗？", self.window()
                    )
                    if choice.exec():

                        logger.info(
                            f"正在删除 {self.name} 的配置_{name}", module="脚本管理"
                        )

                        self.sub_manager.clear_SettingBox()

                        # 删除配置文件并同步到相关配置项
                        shutil.rmtree(
                            Config.script_dict[self.name]["SubData"][name]["Path"]
                        )
                        for i in range(
                            int(name[3:]) + 1,
                            len(Config.script_dict[self.name]["SubData"]) + 1,
                        ):
                            if Config.script_dict[self.name]["SubData"][f"配置_{i}"][
                                "Path"
                            ].exists():
                                Config.script_dict[self.name]["SubData"][f"配置_{i}"][
                                    "Path"
                                ].rename(
                                    Config.script_dict[self.name]["SubData"][
                                        f"配置_{i}"
                                    ]["Path"].with_name(f"配置_{i-1}")
                                )

                        self.sub_manager.show_SettingBox(
                            f"配置_{max(int(name[3:]) - 1, 1)}"
                        )

                        logger.success(
                            f"{self.name} {name} 删除成功", module="脚本管理"
                        )
                        MainInfoBar.push_info_bar(
                            "success", "操作成功", f"{self.name} 删除 {name}", 3000
                        )
                        SoundPlayer.play("删除配置")

                def left_sub(self):
                    """向前移动配置"""

                    name = self.sub_manager.pivot.currentRouteKey()

                    if name is None:
                        logger.warning("未选择配置", module="脚本管理")
                        MainInfoBar.push_info_bar(
                            "warning", "未选择配置", "请先选择一个配置", 5000
                        )
                        return None
                    if name == "配置仪表盘":
                        logger.warning("试图移动配置仪表盘", module="脚本管理")
                        MainInfoBar.push_info_bar(
                            "warning", "未选择配置", "请勿尝试移动配置仪表盘", 5000
                        )
                        return None

                    index = int(name[3:])

                    if index == 1:
                        logger.warning("向前移动配置时已到达最左端", module="脚本管理")
                        MainInfoBar.push_info_bar(
                            "warning", "已经是第一个配置", "无法向前移动", 5000
                        )
                        return None

                    if self.name in Config.running_list:
                        logger.warning("所属脚本正在运行", module="脚本管理")
                        MainInfoBar.push_info_bar(
                            "warning", "所属脚本正在运行", "请先停止任务", 5000
                        )
                        return None

                    logger.info(
                        f"正在将 {self.name} 的配置_{name} 前移", module="脚本管理"
                    )

                    self.sub_manager.clear_SettingBox()

                    # 移动配置文件并同步到相关配置项
                    Config.script_dict[self.name]["SubData"][name]["Path"].rename(
                        Config.script_dict[self.name]["SubData"][name][
                            "Path"
                        ].with_name("配置_0")
                    )
                    Config.script_dict[self.name]["SubData"][f"配置_{index-1}"][
                        "Path"
                    ].rename(Config.script_dict[self.name]["SubData"][name]["Path"])
                    Config.script_dict[self.name]["SubData"][name]["Path"].with_name(
                        "配置_0"
                    ).rename(
                        Config.script_dict[self.name]["SubData"][f"配置_{index-1}"][
                            "Path"
                        ]
                    )

                    self.sub_manager.show_SettingBox(f"配置_{index - 1}")

                    logger.success(f"{self.name} {name} 前移成功", module="脚本管理")
                    MainInfoBar.push_info_bar(
                        "success", "操作成功", f"{self.name} 前移 {name}", 3000
                    )

                def right_sub(self):
                    """向后移动配置"""

                    name = self.sub_manager.pivot.currentRouteKey()

                    if name is None:
                        logger.warning("未选择配置", module="脚本管理")
                        MainInfoBar.push_info_bar(
                            "warning", "未选择配置", "请先选择一个配置", 5000
                        )
                        return None
                    if name == "配置仪表盘":
                        logger.warning("试图删除配置仪表盘", module="脚本管理")
                        MainInfoBar.push_info_bar(
                            "warning", "未选择配置", "请勿尝试移动配置仪表盘", 5000
                        )
                        return None

                    index = int(name[3:])

                    if index == len(Config.script_dict[self.name]["SubData"]):
                        logger.warning("向后移动配置时已到达最右端", module="脚本管理")
                        MainInfoBar.push_info_bar(
                            "warning", "已经是最后一个配置", "无法向后移动", 5000
                        )
                        return None

                    if self.name in Config.running_list:
                        logger.warning("所属脚本正在运行", module="脚本管理")
                        MainInfoBar.push_info_bar(
                            "warning", "所属脚本正在运行", "请先停止任务", 5000
                        )
                        return None

                    logger.info(
                        f"正在将 {self.name} 的配置_{name} 后移", module="脚本管理"
                    )

                    self.sub_manager.clear_SettingBox()

                    # 移动配置文件并同步到相关配置项
                    Config.script_dict[self.name]["SubData"][name]["Path"].rename(
                        Config.script_dict[self.name]["SubData"][name][
                            "Path"
                        ].with_name("配置_0")
                    )
                    Config.script_dict[self.name]["SubData"][f"配置_{index+1}"][
                        "Path"
                    ].rename(Config.script_dict[self.name]["SubData"][name]["Path"])
                    Config.script_dict[self.name]["SubData"][name]["Path"].with_name(
                        "配置_0"
                    ).rename(
                        Config.script_dict[self.name]["SubData"][f"配置_{index+1}"][
                            "Path"
                        ]
                    )

                    self.sub_manager.show_SettingBox(f"配置_{index + 1}")

                    logger.success(f"{self.name} {name} 后移成功", module="脚本管理")
                    MainInfoBar.push_info_bar(
                        "success", "操作成功", f"{self.name} 后移 {name}", 3000
                    )

                class SubConfigSettingBox(QWidget):
                    """配置管理子页面组"""

                    def __init__(self, name: str, parent=None):
                        super().__init__(parent)

                        self.setObjectName("配置管理")
                        self.name = name

                        self.pivotArea = PivotArea(self)
                        self.pivot = self.pivotArea.pivot

                        self.stackedWidget = QStackedWidget(self)
                        self.stackedWidget.setContentsMargins(0, 0, 0, 0)
                        self.stackedWidget.setStyleSheet(
                            "background: transparent; border: none;"
                        )

                        self.script_list: List[
                            ScriptManager.ScriptSettingBox.GeneralSettingBox.BranchManager.SubConfigSettingBox.SubMemberSettingBox
                        ] = []

                        self.sub_dashboard = self.SubDashboard(self.name, self)
                        self.sub_dashboard.switch_to.connect(self.switch_SettingBox)
                        self.stackedWidget.addWidget(self.sub_dashboard)
                        self.pivot.addItem(routeKey="配置仪表盘", text="配置仪表盘")

                        self.Layout = QVBoxLayout(self)
                        self.Layout.addWidget(self.pivotArea)
                        self.Layout.addWidget(self.stackedWidget)
                        self.Layout.setContentsMargins(0, 0, 0, 0)

                        self.pivot.currentItemChanged.connect(
                            lambda index: self.switch_SettingBox(
                                index, if_change_pivot=False
                            )
                        )

                        self.show_SettingBox("配置仪表盘")

                    def show_SettingBox(self, index: str) -> None:
                        """
                        加载所有子界面

                        :param index: 要显示的子界面索引
                        """

                        Config.search_general_sub(self.name)

                        for name in Config.script_dict[self.name]["SubData"].keys():
                            self.add_SettingBox(name[3:])

                        self.switch_SettingBox(index)

                    def switch_SettingBox(
                        self, index: str, if_change_pivot: bool = True
                    ) -> None:
                        """
                        切换到指定的子界面

                        :param index: 要切换到的子界面索引
                        :param if_change_pivot: 是否更改 pivot 的当前项
                        """

                        if len(Config.script_dict[self.name]["SubData"]) == 0:
                            index = "配置仪表盘"

                        if index != "配置仪表盘" and int(index[3:]) > len(
                            Config.script_dict[self.name]["SubData"]
                        ):
                            return None

                        if index == "配置仪表盘":
                            self.sub_dashboard.load_info()

                        if if_change_pivot:
                            self.pivot.setCurrentItem(index)
                        self.stackedWidget.setCurrentWidget(
                            self.sub_dashboard
                            if index == "配置仪表盘"
                            else self.script_list[int(index[3:]) - 1]
                        )

                    def clear_SettingBox(self) -> None:
                        """清空所有子界面"""

                        for sub_interface in self.script_list:
                            self.stackedWidget.removeWidget(sub_interface)
                            sub_interface.deleteLater()
                        self.script_list.clear()
                        self.pivot.clear()
                        self.sub_dashboard.dashboard.setRowCount(0)
                        self.stackedWidget.addWidget(self.sub_dashboard)
                        self.pivot.addItem(routeKey="配置仪表盘", text="配置仪表盘")

                    def add_SettingBox(self, uid: int) -> None:
                        """
                        添加一个配置设置界面

                        :param uid: 配置的唯一标识符
                        """

                        setting_box = self.SubMemberSettingBox(self.name, uid, self)

                        self.script_list.append(setting_box)

                        self.stackedWidget.addWidget(self.script_list[-1])

                        self.pivot.addItem(routeKey=f"配置_{uid}", text=f"配置 {uid}")

                    class SubDashboard(HeaderCardWidget):
                        """配置仪表盘页面"""

                        switch_to = Signal(str)

                        def __init__(self, name: str, parent=None):
                            super().__init__(parent)
                            self.setObjectName("配置仪表盘")
                            self.setTitle("配置仪表盘")
                            self.name = name

                            self.dashboard = TableWidget(self)
                            self.dashboard.setColumnCount(5)
                            self.dashboard.setHorizontalHeaderLabels(
                                ["配置名", "状态", "代理情况", "备注", "详"]
                            )
                            self.dashboard.setEditTriggers(TableWidget.NoEditTriggers)
                            self.dashboard.verticalHeader().setVisible(False)
                            for col in range(2):
                                self.dashboard.horizontalHeader().setSectionResizeMode(
                                    col, QHeaderView.ResizeMode.ResizeToContents
                                )
                            for col in range(2, 4):
                                self.dashboard.horizontalHeader().setSectionResizeMode(
                                    col, QHeaderView.ResizeMode.Stretch
                                )
                            self.dashboard.horizontalHeader().setSectionResizeMode(
                                4, QHeaderView.ResizeMode.Fixed
                            )
                            self.dashboard.setColumnWidth(4, 32)

                            self.viewLayout.addWidget(self.dashboard)
                            self.viewLayout.setContentsMargins(3, 0, 3, 3)

                            Config.PASSWORD_refreshed.connect(self.load_info)

                        def load_info(self):
                            """加载配置仪表盘信息"""

                            logger.info(
                                f"正在加载 {self.name} 的配置仪表盘信息",
                                module="脚本管理",
                            )

                            self.sub_data = Config.script_dict[self.name]["SubData"]

                            self.dashboard.setRowCount(len(self.sub_data))

                            for name, info in self.sub_data.items():

                                config = info["Config"]

                                text_list = []
                                text_list.append(
                                    f"今日已代理{config.get(config.Data_ProxyTimes)}次"
                                    if Config.server_date().strftime("%Y-%m-%d")
                                    == config.get(config.Data_LastProxyDate)
                                    else "今日未进行代理"
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
                                self.dashboard.setCellWidget(
                                    int(name[3:]) - 1,
                                    1,
                                    StatusSwitchSetting(
                                        qconfig=config,
                                        configItem_check=config.Info_Status,
                                        configItem_enable=config.Info_RemainedDay,
                                        parent=self,
                                    ),
                                )
                                self.dashboard.setItem(
                                    int(name[3:]) - 1,
                                    2,
                                    QTableWidgetItem(" | ".join(text_list)),
                                )
                                self.dashboard.setItem(
                                    int(name[3:]) - 1,
                                    3,
                                    QTableWidgetItem(config.get(config.Info_Notes)),
                                )
                                self.dashboard.setCellWidget(
                                    int(name[3:]) - 1, 4, button
                                )

                            logger.success(
                                f"{self.name} 配置仪表盘信息加载成功", module="脚本管理"
                            )

                    class SubMemberSettingBox(HeaderCardWidget):
                        """配置管理子页面"""

                        def __init__(self, name: str, uid: int, parent=None):
                            super().__init__(parent)

                            self.setObjectName(f"配置_{uid}")
                            self.setTitle(f"配置 {uid}")
                            self.name = name
                            self.config = Config.script_dict[self.name]["SubData"][
                                f"配置_{uid}"
                            ]["Config"]
                            self.sub_path = Config.script_dict[self.name]["SubData"][
                                f"配置_{uid}"
                            ]["Path"]

                            self.card_Name = LineEditSettingCard(
                                icon=FluentIcon.PEOPLE,
                                title="配置名",
                                content="用于标识配置",
                                text="请输入配置名",
                                qconfig=self.config,
                                configItem=self.config.Info_Name,
                                parent=self,
                            )
                            self.card_SetConfig = PushSettingCard(
                                text="设置具体配置",
                                icon=FluentIcon.CAFE,
                                title="具体配置",
                                content="在脚本原始界面中查看具体配置内容",
                                parent=self,
                            )
                            self.card_Status = SwitchSettingCard(
                                icon=FluentIcon.CHECKBOX,
                                title="配置状态",
                                content="启用或禁用该配置",
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
                            self.item_IfScriptBeforeTask = StatusSwitchSetting(
                                qconfig=self.config,
                                configItem_check=self.config.Info_IfScriptBeforeTask,
                                configItem_enable=None,
                                parent=self,
                            )
                            self.card_ScriptBeforeTask = PathSettingCard(
                                icon=FluentIcon.FOLDER,
                                title="脚本前置任务",
                                mode="脚本文件 (*.py *.bat *.cmd *.exe)",
                                text="选择脚本文件",
                                qconfig=self.config,
                                configItem=self.config.Info_ScriptBeforeTask,
                                parent=self,
                            )
                            self.item_IfScriptAfterTask = StatusSwitchSetting(
                                qconfig=self.config,
                                configItem_check=self.config.Info_IfScriptAfterTask,
                                configItem_enable=None,
                                parent=self,
                            )
                            self.card_ScriptAfterTask = PathSettingCard(
                                icon=FluentIcon.FOLDER,
                                title="脚本后置任务",
                                mode="脚本文件 (*.py *.bat *.cmd *.exe)",
                                text="选择脚本文件",
                                qconfig=self.config,
                                configItem=self.config.Info_ScriptAfterTask,
                                parent=self,
                            )
                            self.card_Notes = LineEditSettingCard(
                                icon=FluentIcon.PENCIL_INK,
                                title="备注",
                                content="配置备注信息",
                                text="请输入备注",
                                qconfig=self.config,
                                configItem=self.config.Info_Notes,
                                parent=self,
                            )

                            self.card_UserLable = SubLableSettingCard(
                                icon=FluentIcon.INFO,
                                title="状态信息",
                                content="配置的代理情况汇总",
                                qconfig=self.config,
                                configItems={
                                    "LastProxyDate": self.config.Data_LastProxyDate,
                                    "ProxyTimes": self.config.Data_ProxyTimes,
                                },
                                parent=self,
                            )

                            self.card_ScriptBeforeTask.hBoxLayout.insertWidget(
                                5, self.item_IfScriptBeforeTask, 0, Qt.AlignRight
                            )
                            self.card_ScriptAfterTask.hBoxLayout.insertWidget(
                                5, self.item_IfScriptAfterTask, 0, Qt.AlignRight
                            )

                            # 单独通知卡片
                            self.card_NotifySet = UserNoticeSettingCard(
                                icon=FluentIcon.MAIL,
                                title="用户单独通知设置",
                                content="未启用任何通知项",
                                text="设置",
                                qconfig=self.config,
                                configItem=self.config.Notify_Enabled,
                                configItems={
                                    "IfSendStatistic": self.config.Notify_IfSendStatistic,
                                    "IfSendMail": self.config.Notify_IfSendMail,
                                    "ToAddress": self.config.Notify_ToAddress,
                                    "IfServerChan": self.config.Notify_IfServerChan,
                                    "ServerChanKey": self.config.Notify_ServerChanKey,
                                    "IfCompanyWebHookBot": self.config.Notify_IfCompanyWebHookBot,
                                    "CompanyWebHookBotUrl": self.config.Notify_CompanyWebHookBotUrl,
                                },
                                parent=self,
                            )
                            self.card_NotifyContent = self.NotifyContentSettingCard(
                                self.config, self
                            )
                            self.card_EMail = self.EMailSettingCard(self.config, self)
                            self.card_ServerChan = self.ServerChanSettingCard(
                                self.config, self
                            )
                            self.card_CompanyWebhookBot = (
                                self.CompanyWechatPushSettingCard(self.config, self)
                            )

                            self.NotifySetCard = SettingFlyoutView(
                                self,
                                "用户通知设置",
                                [
                                    self.card_NotifyContent,
                                    self.card_EMail,
                                    self.card_ServerChan,
                                    self.card_CompanyWebhookBot,
                                ],
                            )

                            h1_layout = QHBoxLayout()
                            h1_layout.addWidget(self.card_Name)
                            h1_layout.addWidget(self.card_SetConfig)
                            h2_layout = QHBoxLayout()
                            h2_layout.addWidget(self.card_Status)
                            h2_layout.addWidget(self.card_RemainedDay)

                            Layout = QVBoxLayout()
                            Layout.addLayout(h1_layout)
                            Layout.addLayout(h2_layout)
                            Layout.addWidget(self.card_UserLable)
                            Layout.addWidget(self.card_ScriptBeforeTask)
                            Layout.addWidget(self.card_ScriptAfterTask)
                            Layout.addWidget(self.card_Notes)
                            Layout.addWidget(self.card_NotifySet)

                            self.viewLayout.addLayout(Layout)
                            self.viewLayout.setContentsMargins(3, 0, 3, 3)

                            self.card_SetConfig.clicked.connect(self.set_sub)
                            self.card_NotifySet.clicked.connect(self.set_notify)

                        def set_sub(self) -> None:
                            """配置子配置"""

                            if self.name in Config.running_list:
                                logger.warning("所属脚本正在运行", module="脚本管理")
                                MainInfoBar.push_info_bar(
                                    "warning", "所属脚本正在运行", "请先停止任务", 5000
                                )
                                return None

                            TaskManager.add_task(
                                "设置通用脚本",
                                self.name,
                                {"SetSubInfo": {"Path": self.sub_path / "ConfigFiles"}},
                            )

                        def set_notify(self) -> None:
                            """设置用户通知相关配置"""

                            self.NotifySetCard.setVisible(True)
                            Flyout.make(
                                self.NotifySetCard,
                                self.card_NotifySet,
                                self,
                                aniType=FlyoutAnimationType.PULL_UP,
                                isDeleteOnClose=False,
                            )

                        class NotifyContentSettingCard(HeaderCardWidget):

                            def __init__(self, config: MaaUserConfig, parent=None):
                                super().__init__(parent)
                                self.setTitle("用户通知内容选项")

                                self.config = config

                                self.card_IfSendStatistic = SwitchSettingCard(
                                    icon=FluentIcon.PAGE_RIGHT,
                                    title="推送统计信息",
                                    content="推送自动代理统计信息的通知",
                                    qconfig=self.config,
                                    configItem=self.config.Notify_IfSendStatistic,
                                    parent=self,
                                )

                                Layout = QVBoxLayout()
                                Layout.addWidget(self.card_IfSendStatistic)
                                self.viewLayout.addLayout(Layout)
                                self.viewLayout.setSpacing(3)
                                self.viewLayout.setContentsMargins(3, 0, 3, 3)

                        class EMailSettingCard(HeaderCardWidget):

                            def __init__(self, config: MaaUserConfig, parent=None):
                                super().__init__(parent)
                                self.setTitle("用户邮箱通知")

                                self.config = config

                                self.card_IfSendMail = SwitchSettingCard(
                                    icon=FluentIcon.PAGE_RIGHT,
                                    title="推送用户邮件通知",
                                    content="是否启用用户邮件通知功能",
                                    qconfig=self.config,
                                    configItem=self.config.Notify_IfSendMail,
                                    parent=self,
                                )
                                self.card_ToAddress = LineEditSettingCard(
                                    icon=FluentIcon.PAGE_RIGHT,
                                    title="用户收信邮箱地址",
                                    content="接收用户通知的邮箱地址",
                                    text="请输入用户收信邮箱地址",
                                    qconfig=self.config,
                                    configItem=self.config.Notify_ToAddress,
                                    parent=self,
                                )

                                Layout = QVBoxLayout()
                                Layout.addWidget(self.card_IfSendMail)
                                Layout.addWidget(self.card_ToAddress)
                                self.viewLayout.addLayout(Layout)
                                self.viewLayout.setSpacing(3)
                                self.viewLayout.setContentsMargins(3, 0, 3, 3)

                        class ServerChanSettingCard(HeaderCardWidget):

                            def __init__(self, config: MaaUserConfig, parent=None):
                                super().__init__(parent)
                                self.setTitle("用户ServerChan通知")

                                self.config = config

                                self.card_IfServerChan = SwitchSettingCard(
                                    icon=FluentIcon.PAGE_RIGHT,
                                    title="推送用户Server酱通知",
                                    content="是否启用用户Server酱通知功能",
                                    qconfig=self.config,
                                    configItem=self.config.Notify_IfServerChan,
                                    parent=self,
                                )
                                self.card_ServerChanKey = LineEditSettingCard(
                                    icon=FluentIcon.PAGE_RIGHT,
                                    title="用户SendKey",
                                    content="SC3与SCT均须填写",
                                    text="请输入用户SendKey",
                                    qconfig=self.config,
                                    configItem=self.config.Notify_ServerChanKey,
                                    parent=self,
                                )
                                self.card_ServerChanChannel = LineEditSettingCard(
                                    icon=FluentIcon.PAGE_RIGHT,
                                    title="用户ServerChanChannel代码",
                                    content="留空则默认，多个请使用「|」隔开",
                                    text="请输入Channel代码，仅SCT生效",
                                    qconfig=self.config,
                                    configItem=self.config.Notify_ServerChanChannel,
                                    parent=self,
                                )
                                self.card_ServerChanTag = LineEditSettingCard(
                                    icon=FluentIcon.PAGE_RIGHT,
                                    title="用户Tag内容",
                                    content="留空则默认，多个请使用「|」隔开",
                                    text="请输入加入推送的Tag，仅SC3生效",
                                    qconfig=self.config,
                                    configItem=self.config.Notify_ServerChanTag,
                                    parent=self,
                                )

                                Layout = QVBoxLayout()
                                Layout.addWidget(self.card_IfServerChan)
                                Layout.addWidget(self.card_ServerChanKey)
                                Layout.addWidget(self.card_ServerChanChannel)
                                Layout.addWidget(self.card_ServerChanTag)
                                self.viewLayout.addLayout(Layout)
                                self.viewLayout.setSpacing(3)
                                self.viewLayout.setContentsMargins(3, 0, 3, 3)

                        class CompanyWechatPushSettingCard(HeaderCardWidget):

                            def __init__(self, config: MaaUserConfig, parent=None):
                                super().__init__(parent)
                                self.setTitle("用户企业微信推送")

                                self.config = config

                                self.card_IfCompanyWebHookBot = SwitchSettingCard(
                                    icon=FluentIcon.PAGE_RIGHT,
                                    title="推送用户企业微信机器人通知",
                                    content="是否启用用户企微机器人通知功能",
                                    qconfig=self.config,
                                    configItem=self.config.Notify_IfCompanyWebHookBot,
                                    parent=self,
                                )
                                self.card_CompanyWebHookBotUrl = LineEditSettingCard(
                                    icon=FluentIcon.PAGE_RIGHT,
                                    title="WebhookUrl",
                                    content="用户企微群机器人Webhook地址",
                                    text="请输入用户Webhook的Url",
                                    qconfig=self.config,
                                    configItem=self.config.Notify_CompanyWebHookBotUrl,
                                    parent=self,
                                )

                                Layout = QVBoxLayout()
                                Layout.addWidget(self.card_IfCompanyWebHookBot)
                                Layout.addWidget(self.card_CompanyWebHookBotUrl)
                                self.viewLayout.addLayout(Layout)
                                self.viewLayout.setSpacing(3)
                                self.viewLayout.setContentsMargins(3, 0, 3, 3)
