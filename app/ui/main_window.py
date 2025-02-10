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
from PySide6.QtWidgets import (
    QApplication,
    QSystemTrayIcon,
)
from qfluentwidgets import (
    Action,
    PushButton,
    SystemTrayMenu,
    SplashScreen,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    setTheme,
    Theme,
    MSFluentWindow,
    NavigationItemPosition,
    qconfig,
)
from PySide6.QtGui import QIcon, QCloseEvent
from PySide6.QtCore import Qt

from app.core import Config, Task_manager, Main_timer, MainInfoBar
from app.services import Notify, Crypto, System
from .setting import Setting
from .member_manager import MemberManager
from .queue_manager import QueueManager
from .dispatch_center import DispatchCenter


class AUTO_MAA(MSFluentWindow):

    def __init__(self):
        super().__init__()

        self.setWindowIcon(QIcon(str(Config.app_path / "resources/icons/AUTO_MAA.ico")))
        self.setWindowTitle("AUTO_MAA")

        setTheme(Theme.AUTO)

        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.show_ui("显示主窗口", if_quick=True)

        MainInfoBar.main_window = self.window()
        System.main_window = self.window()

        # 创建主窗口
        self.setting = Setting(self)
        self.member_manager = MemberManager(self)
        self.queue_manager = QueueManager(self)
        self.dispatch_center = DispatchCenter(self)

        self.addSubInterface(
            self.setting,
            FluentIcon.SETTING,
            "设置",
            FluentIcon.SETTING,
            NavigationItemPosition.BOTTOM,
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

        # 创建系统托盘及其菜单
        self.tray = QSystemTrayIcon(
            QIcon(str(Config.app_path / "resources/icons/AUTO_MAA.ico")),
            self,
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
        # self.tray_menu.addActions(
        #     [
        #         Action(
        #             FluentIcon.PLAY,
        #             "运行自动代理",
        #             triggered=lambda: self.start_task("自动代理"),
        #         ),
        #         Action(
        #             FluentIcon.PLAY,
        #             "运行人工排查",
        #             triggered=lambda: self.start_task("人工排查"),
        #         ),
        #         Action(FluentIcon.PAUSE, "中止当前任务", triggered=self.stop_task),
        #     ]
        # )
        # self.tray_menu.addSeparator()

        # 退出主程序菜单项
        self.tray_menu.addAction(
            Action(FluentIcon.POWER_BUTTON, "退出主程序", triggered=self.window().close)
        )

        # 设置托盘菜单
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self.on_tray_activated)

        Task_manager.create_gui.connect(self.dispatch_center.add_board)
        Task_manager.connect_gui.connect(self.dispatch_center.connect_main_board)
        self.setting.ui.card_IfShowTray.checkedChanged.connect(
            lambda: self.show_ui("配置托盘")
        )
        self.setting.ui.card_IfToTray.checkedChanged.connect(self.set_min_method)

        self.splashScreen.finish()

    def start_up_task(self) -> None:
        """启动时任务"""

        # 加载配置
        qconfig.load(Config.config_path, Config.global_config)
        Config.global_config.save()

        # 检查密码
        self.setting.check_PASSWORD()

        # 获取公告
        self.setting.show_notice(if_show=False)

        # 检查更新
        if Config.global_config.get(Config.global_config.update_IfAutoUpdate):
            result = self.setting.get_update_info()
            if result == "已是最新版本~":
                MainInfoBar.push_info_bar("success", "更新检查", result, 3000)
            else:
                info = InfoBar.info(
                    title="更新检查",
                    content=result,
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.BOTTOM_LEFT,
                    duration=-1,
                    parent=self,
                )
                Up = PushButton("更新")
                Up.clicked.connect(lambda: self.setting.get_update(if_question=False))
                Up.clicked.connect(info.close)
                info.addWidget(Up)
                info.show()

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

    # def start_task(self, mode):
    #     """调起对应任务"""
    #     if self.main.MaaManager.isRunning():
    #         Notify.push_notification(
    #             f"无法运行{mode}！",
    #             "当前已有任务正在运行，请在该任务结束后重试",
    #             "当前已有任务正在运行，请在该任务结束后重试",
    #             3,
    #         )
    #     else:
    #         self.main.maa_starter(mode)

    # def stop_task(self):
    #     """中止当前任务"""
    #     if self.main.MaaManager.isRunning():
    #         if (
    #             self.main.MaaManager.mode == "自动代理"
    #             or self.main.MaaManager.mode == "人工排查"
    #         ):
    #             self.main.maa_ender(f"{self.main.MaaManager.mode}_结束")
    #         elif "设置MAA" in self.main.MaaManager.mode:
    #             Notify.push_notification(
    #                 "正在设置MAA！",
    #                 "正在运行设置MAA任务，无法中止",
    #                 "正在运行设置MAA任务，无法中止",
    #                 3,
    #             )
    #     else:
    #         Notify.push_notification(
    #             "无任务运行！",
    #             "当前无任务正在运行，无需中止",
    #             "当前无任务正在运行，无需中止",
    #             3,
    #         )

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
        Main_timer.Timer.stop()
        Main_timer.Timer.deleteLater()
        Task_manager.stop_task("ALL")

        # 关闭数据库连接
        Config.close_database()

        logger.info("AUTO_MAA主程序关闭")
        logger.info("----------------END----------------")

        event.accept()
