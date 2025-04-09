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
AUTO_MAA主界面
v4.2
作者：DLmaster_361
"""

from loguru import logger
from PySide6.QtWidgets import QSystemTrayIcon
from qfluentwidgets import (
    Action,
    PushButton,
    SystemTrayMenu,
    SplashScreen,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    setTheme,
    isDarkTheme,
    SystemThemeListener,
    Theme,
    MSFluentWindow,
    NavigationItemPosition,
    qconfig,
    FluentBackgroundTheme,
)
from PySide6.QtGui import QIcon, QCloseEvent
from PySide6.QtCore import Qt, QTimer
import json
from datetime import datetime, timedelta
import shutil
import sys

from app.core import Config, TaskManager, MainTimer, MainInfoBar
from app.services import Notify, Crypto, System
from .home import Home
from .member_manager import MemberManager
from .queue_manager import QueueManager
from .dispatch_center import DispatchCenter
from .history import History
from .setting import Setting


class AUTO_MAA(MSFluentWindow):

    def __init__(self):
        super().__init__()

        self.setWindowIcon(QIcon(str(Config.app_path / "resources/icons/AUTO_MAA.ico")))
        self.setWindowTitle("AUTO_MAA")

        setTheme(Theme.AUTO, lazy=True)
        self.switch_theme()

        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.show_ui("显示主窗口", if_quick=True)

        TaskManager.main_window = self.window()
        MainInfoBar.main_window = self.window()
        System.main_window = self.window()

        # 创建主窗口
        self.home = Home(self)
        self.member_manager = MemberManager(self)
        self.queue_manager = QueueManager(self)
        self.dispatch_center = DispatchCenter(self)
        self.history = History(self)
        self.setting = Setting(self)

        self.addSubInterface(
            self.home,
            FluentIcon.HOME,
            "主页",
            FluentIcon.HOME,
            NavigationItemPosition.TOP,
        )
        self.addSubInterface(
            self.member_manager,
            FluentIcon.ROBOT,
            "脚本管理",
            FluentIcon.ROBOT,
            NavigationItemPosition.TOP,
        )
        self.addSubInterface(
            self.queue_manager,
            FluentIcon.BOOK_SHELF,
            "调度队列",
            FluentIcon.BOOK_SHELF,
            NavigationItemPosition.TOP,
        )
        self.addSubInterface(
            self.dispatch_center,
            FluentIcon.IOT,
            "调度中心",
            FluentIcon.IOT,
            NavigationItemPosition.TOP,
        )
        self.addSubInterface(
            self.history,
            FluentIcon.HISTORY,
            "历史记录",
            FluentIcon.HISTORY,
            NavigationItemPosition.BOTTOM,
        )
        self.addSubInterface(
            self.setting,
            FluentIcon.SETTING,
            "设置",
            FluentIcon.SETTING,
            NavigationItemPosition.BOTTOM,
        )
        self.stackedWidget.currentChanged.connect(
            lambda index: (self.member_manager.refresh() if index == 1 else None)
        )
        self.stackedWidget.currentChanged.connect(
            lambda index: self.queue_manager.refresh() if index == 2 else None
        )
        self.stackedWidget.currentChanged.connect(
            lambda index: (
                self.dispatch_center.pivot.setCurrentItem("主调度台")
                if index == 3
                else None
            )
        )
        self.stackedWidget.currentChanged.connect(
            lambda index: (
                self.dispatch_center.update_top_bar() if index == 3 else None
            )
        )
        self.stackedWidget.currentChanged.connect(
            lambda index: (self.history.refresh() if index == 4 else None)
        )

        # 创建系统托盘及其菜单
        self.tray = QSystemTrayIcon(
            QIcon(str(Config.app_path / "resources/icons/AUTO_MAA.ico")), self
        )
        self.tray.setToolTip("AUTO_MAA")
        self.tray_menu = SystemTrayMenu("AUTO_MAA", self)

        # 显示主界面菜单项
        self.tray_menu.addAction(
            Action(
                FluentIcon.CAFE,
                "显示主界面",
                triggered=lambda: self.show_ui("显示主窗口"),
            )
        )
        self.tray_menu.addSeparator()

        # 开始任务菜单项
        self.tray_menu.addActions(
            [
                Action(FluentIcon.PLAY, "运行自动代理", triggered=self.start_main_task),
                Action(
                    FluentIcon.PAUSE,
                    "中止所有任务",
                    triggered=lambda: TaskManager.stop_task("ALL"),
                ),
            ]
        )
        self.tray_menu.addSeparator()

        # 退出主程序菜单项
        self.tray_menu.addAction(
            Action(FluentIcon.POWER_BUTTON, "退出主程序", triggered=self.window().close)
        )

        # 设置托盘菜单
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self.on_tray_activated)

        TaskManager.create_gui.connect(self.dispatch_center.add_board)
        TaskManager.connect_gui.connect(self.dispatch_center.connect_main_board)
        Notify.push_info_bar.connect(MainInfoBar.push_info_bar)
        self.setting.ui.card_IfShowTray.checkedChanged.connect(
            lambda: self.show_ui("配置托盘")
        )
        self.setting.ui.card_IfToTray.checkedChanged.connect(self.set_min_method)
        self.setting.function.card_HomeImageMode.comboBox.currentIndexChanged.connect(
            lambda index: (
                self.home.get_home_image() if index == 2 else self.home.set_banner()
            )
        )

        self.splashScreen.finish()

        self.themeListener = SystemThemeListener(self)
        self.themeListener.systemThemeChanged.connect(self.switch_theme)
        self.themeListener.start()

    def switch_theme(self) -> None:
        """切换主题"""
        setTheme(Theme.AUTO, lazy=True)
        QTimer.singleShot(300, lambda: setTheme(Theme.AUTO, lazy=True))

        # 云母特效启用时需要增加重试机制
        # 云母特效不兼容Win10,如果True则通过云母进行主题转换,False则根据当前主题设置背景颜色
        if self.isMicaEffectEnabled():
            QTimer.singleShot(
                300,
                lambda: self.windowEffect.setMicaEffect(self.winId(), isDarkTheme()),
            )

        else:
            # 根据当前主题设置背景颜色
            if isDarkTheme():
                self.setStyleSheet(
                    """
                    CardWidget {background-color: #313131;}
                    HeaderCardWidget {background-color: #313131;}
                    background-color: #313131;
                """
                )
            else:
                self.setStyleSheet("background-color: #ffffff;")

    def start_up_task(self) -> None:
        """启动时任务"""

        # 加载配置
        qconfig.load(Config.config_path, Config.global_config)
        Config.global_config.save()

        # 清理旧日志
        self.clean_old_logs()

        # 检查密码
        self.setting.check_PASSWORD()

        # 获取主题图像
        if (
            Config.global_config.get(Config.global_config.function_HomeImageMode)
            == "主题图像"
        ):
            self.home.get_home_image()

        # 直接运行主任务
        if Config.global_config.get(Config.global_config.start_IfRunDirectly):

            self.start_main_task()

        # 获取公告
        self.setting.show_notice(if_show=False)

        # 检查更新
        if Config.global_config.get(Config.global_config.update_IfAutoUpdate):
            self.setting.check_update()

        # 直接最小化
        if Config.global_config.get(Config.global_config.start_IfMinimizeDirectly):

            self.titleBar.minBtn.click()

    def set_min_method(self) -> None:
        """设置最小化方法"""

        if Config.global_config.get(Config.global_config.ui_IfToTray):

            self.titleBar.minBtn.clicked.disconnect()
            self.titleBar.minBtn.clicked.connect(lambda: self.show_ui("隐藏到托盘"))

        else:

            self.titleBar.minBtn.clicked.disconnect()
            self.titleBar.minBtn.clicked.connect(self.window().showMinimized)

    def on_tray_activated(self, reason):
        """双击返回主界面"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_ui("显示主窗口")

    def clean_old_logs(self):
        """
        删除超过用户设定天数的日志文件（基于目录日期）
        """

        if (
            Config.global_config.get(Config.global_config.function_HistoryRetentionTime)
            == 0
        ):
            logger.info("由于用户设置日志永久保留，跳过日志清理")
            return

        deleted_count = 0

        for date_folder in (Config.app_path / "history").iterdir():
            if not date_folder.is_dir():
                continue  # 只处理日期文件夹

            try:
                # 只检查 `YYYY-MM-DD` 格式的文件夹
                folder_date = datetime.strptime(date_folder.name, "%Y-%m-%d")
                if datetime.now() - folder_date > timedelta(
                    days=Config.global_config.get(
                        Config.global_config.function_HistoryRetentionTime
                    )
                ):
                    shutil.rmtree(date_folder, ignore_errors=True)
                    deleted_count += 1
                    logger.info(f"已删除超期日志目录: {date_folder}")
            except ValueError:
                logger.warning(f"非日期格式的目录: {date_folder}")

        logger.info(f"清理完成: {deleted_count} 个日期目录")

    def start_main_task(self) -> None:
        """启动主任务"""

        if (Config.app_path / "config/QueueConfig/调度队列_1.json").exists():

            with (Config.app_path / "config/QueueConfig/调度队列_1.json").open(
                mode="r", encoding="utf-8"
            ) as f:
                info = json.load(f)

            logger.info("自动添加任务：调度队列_1")
            TaskManager.add_task("自动代理_主调度台", "主任务队列", info)

        elif (Config.app_path / "config/MaaConfig/脚本_1").exists():

            info = {"Queue": {"Member_1": "脚本_1"}}

            logger.info("自动添加任务：脚本_1")
            TaskManager.add_task("自动代理_主调度台", "主任务队列", info)

        else:

            logger.worning("启动主任务失败：未找到有效的主任务配置文件")
            MainInfoBar.push_info_bar(
                "warning", "启动主任务失败", "“调度队列_1”与“脚本_1”均不存在", -1
            )

    def show_ui(self, mode: str, if_quick: bool = False) -> None:
        """配置窗口状态"""

        if mode == "显示主窗口":

            # 配置主窗口
            size = list(
                map(
                    int,
                    Config.global_config.get(Config.global_config.ui_size).split("x"),
                )
            )
            location = list(
                map(
                    int,
                    Config.global_config.get(Config.global_config.ui_location).split(
                        "x"
                    ),
                )
            )
            self.window().setGeometry(location[0], location[1], size[0], size[1])
            self.window().show()
            self.window().raise_()
            self.window().activateWindow()
            if not if_quick:
                if Config.global_config.get(Config.global_config.ui_maximized):
                    self.window().showMaximized()
                self.set_min_method()
                self.show_ui("配置托盘")

        elif mode == "配置托盘":

            if Config.global_config.get(Config.global_config.ui_IfShowTray):
                self.tray.show()
            else:
                self.tray.hide()

        elif mode == "隐藏到托盘":

            # 保存窗口相关属性
            if not self.window().isMaximized():

                Config.global_config.set(
                    Config.global_config.ui_size,
                    f"{self.geometry().width()}x{self.geometry().height()}",
                )
                Config.global_config.set(
                    Config.global_config.ui_location,
                    f"{self.geometry().x()}x{self.geometry().y()}",
                )
            Config.global_config.set(
                Config.global_config.ui_maximized, self.window().isMaximized()
            )
            Config.global_config.save()

            # 隐藏主窗口
            if not if_quick:

                self.window().hide()
                self.tray.show()

    def closeEvent(self, event: QCloseEvent):
        """清理残余进程"""

        self.show_ui("隐藏到托盘", if_quick=True)

        # 清理各功能线程
        MainTimer.Timer.stop()
        MainTimer.Timer.deleteLater()
        TaskManager.stop_task("ALL")

        # 关闭数据库连接
        Config.close_database()

        # 关闭主题监听
        self.themeListener.terminate()
        self.themeListener.deleteLater()

        logger.info("AUTO_MAA主程序关闭")
        logger.info("----------------END----------------")

        event.accept()
