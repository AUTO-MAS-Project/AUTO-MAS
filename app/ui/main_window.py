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
AUTO_MAA主界面
v4.4
作者：DLmaster_361
"""

from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from qfluentwidgets import (
    Action,
    SystemTrayMenu,
    SplashScreen,
    FluentIcon,
    setTheme,
    isDarkTheme,
    SystemThemeListener,
    Theme,
    MSFluentWindow,
    NavigationItemPosition,
)
from PySide6.QtGui import QIcon, QCloseEvent
from PySide6.QtCore import QTimer
import darkdetect

from app.core import Config, logger, TaskManager, MainTimer, MainInfoBar, SoundPlayer
from app.services import Notify, Crypto, System
from .home import Home
from .script_manager import ScriptManager
from .plan_manager import PlanManager
from .queue_manager import QueueManager
from .dispatch_center import DispatchCenter
from .history import History
from .setting import Setting


class AUTO_MAA(MSFluentWindow):
    """AUTO_MAA主界面"""

    def __init__(self):
        super().__init__()

        self.setWindowIcon(QIcon(str(Config.app_path / "resources/icons/AUTO_MAA.ico")))

        version_numb = list(map(int, Config.VERSION.split(".")))
        version_text = (
            f"v{'.'.join(str(_) for _ in version_numb[0:3])}"
            if version_numb[3] == 0
            else f"v{'.'.join(str(_) for _ in version_numb[0:3])}-beta.{version_numb[3]}"
        )

        self.setWindowTitle(f"AUTO_MAA - {version_text}")

        self.switch_theme()

        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.show_ui("显示主窗口", if_quick=True)

        # 设置主窗口的引用，便于各组件访问
        Config.main_window = self.window()

        # 创建各子窗口
        logger.info("正在创建各子窗口", module="主窗口")
        self.home = Home(self)
        self.plan_manager = PlanManager(self)
        self.script_manager = ScriptManager(self)
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
            self.script_manager,
            FluentIcon.ROBOT,
            "脚本管理",
            FluentIcon.ROBOT,
            NavigationItemPosition.TOP,
        )
        self.addSubInterface(
            self.plan_manager,
            FluentIcon.CALENDAR,
            "计划管理",
            FluentIcon.CALENDAR,
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
        self.stackedWidget.currentChanged.connect(self.__currentChanged)
        logger.success("各子窗口创建完成", module="主窗口")

        # 创建系统托盘及其菜单
        logger.info("正在创建系统托盘", module="主窗口")
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
            Action(
                FluentIcon.POWER_BUTTON,
                "退出主程序",
                triggered=lambda: System.set_power("KillSelf"),
            )
        )

        # 设置托盘菜单
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self.on_tray_activated)
        logger.success("系统托盘创建完成", module="主窗口")

        self.set_min_method()

        # 绑定各组件信号
        Config.sub_info_changed.connect(self.script_manager.refresh_dashboard)
        Config.power_sign_changed.connect(self.dispatch_center.update_power_sign)
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

        logger.success("AUTO_MAA主程序初始化完成", module="主窗口")

    def switch_theme(self) -> None:
        """切换主题"""

        setTheme(
            Theme(darkdetect.theme()) if darkdetect.theme() else Theme.LIGHT, lazy=True
        )
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

    def set_min_method(self) -> None:
        """设置最小化方法"""

        if Config.get(Config.ui_IfToTray):

            self.titleBar.minBtn.clicked.disconnect()
            self.titleBar.minBtn.clicked.connect(lambda: self.show_ui("隐藏到托盘"))

        else:

            self.titleBar.minBtn.clicked.disconnect()
            self.titleBar.minBtn.clicked.connect(self.window().showMinimized)

    def on_tray_activated(self, reason):
        """双击返回主界面"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_ui("显示主窗口")

    def show_ui(
        self, mode: str, if_quick: bool = False, if_start: bool = False
    ) -> None:
        """配置窗口状态"""

        if Config.args.mode != "gui":
            return None

        self.switch_theme()

        if mode == "显示主窗口":

            # 配置主窗口
            if not self.window().isVisible():
                size = list(
                    map(
                        int,
                        Config.get(Config.ui_size).split("x"),
                    )
                )
                location = list(
                    map(
                        int,
                        Config.get(Config.ui_location).split("x"),
                    )
                )
                if self.window().isMaximized():
                    self.window().showNormal()
                self.window().setGeometry(location[0], location[1], size[0], size[1])
                self.window().show()
                if not if_quick:
                    if (
                        Config.get(Config.ui_maximized)
                        and not self.window().isMaximized()
                    ):
                        self.titleBar.maxBtn.click()
                    SoundPlayer.play("欢迎回来")
                    self.show_ui("配置托盘")
            elif if_start:
                if Config.get(Config.ui_maximized) and not self.window().isMaximized():
                    self.titleBar.maxBtn.click()
                self.show_ui("配置托盘")

            # 如果窗口不在屏幕内，则重置窗口位置
            if not any(
                self.window().geometry().intersects(screen.availableGeometry())
                for screen in QApplication.screens()
            ):
                self.window().showNormal()
                self.window().setGeometry(100, 100, 1200, 700)

            self.window().raise_()
            self.window().activateWindow()

            while Config.info_bar_list:
                info_bar_item = Config.info_bar_list.pop(0)
                MainInfoBar.push_info_bar(
                    info_bar_item["mode"],
                    info_bar_item["title"],
                    info_bar_item["content"],
                    info_bar_item["time"],
                )

        elif mode == "配置托盘":

            if Config.get(Config.ui_IfShowTray):
                self.tray.show()
            else:
                self.tray.hide()

        elif mode == "隐藏到托盘":

            # 保存窗口相关属性
            if not self.window().isMaximized():

                Config.set(
                    Config.ui_size,
                    f"{self.geometry().width()}x{self.geometry().height()}",
                )
                Config.set(
                    Config.ui_location,
                    f"{self.geometry().x()}x{self.geometry().y()}",
                )

            Config.set(Config.ui_maximized, self.window().isMaximized())
            Config.save()

            # 隐藏主窗口
            if not if_quick:

                self.window().hide()
                self.tray.show()

    def start_up_task(self) -> None:
        """启动时任务"""

        logger.info("开始执行启动时任务", module="主窗口")

        # 清理旧历史记录
        Config.clean_old_history()

        # 清理安装包
        if (Config.app_path / "AUTO_MAA-Setup.exe").exists():
            try:
                (Config.app_path / "AUTO_MAA-Setup.exe").unlink()
            except Exception:
                pass

        # 检查密码
        self.setting.check_PASSWORD()

        # 获取关卡号信息
        Config.get_stage()

        # 获取主题图像
        if Config.get(Config.function_HomeImageMode) == "主题图像":
            self.home.get_home_image()

        # 直接运行主任务
        if Config.get(Config.start_IfRunDirectly):

            self.start_main_task()

        # 启动定时器
        MainTimer.start()

        # 获取公告
        self.setting.show_notice(if_first=True)

        # 检查更新
        if Config.get(Config.update_IfAutoUpdate):
            self.setting.check_update(if_first=True)

        # 直接最小化
        if Config.get(Config.start_IfMinimizeDirectly):

            self.titleBar.minBtn.click()

        if Config.args.config:

            for config in [_ for _ in Config.args.config if _ in Config.queue_dict]:

                TaskManager.add_task(
                    "自动代理_新调度台",
                    config,
                    Config.queue_dict["调度队列_1"]["Config"].toDict(),
                )

            for config in [_ for _ in Config.args.config if _ in Config.script_dict]:

                TaskManager.add_task(
                    "自动代理_新调度台",
                    "自定义队列",
                    {"Queue": {"Script_0": config}},
                )

            if not any(
                _ in (list(Config.script_dict.keys()) + list(Config.queue_dict.keys()))
                for _ in Config.args.config
            ):

                logger.warning(
                    "当前运行模式为命令行模式，由于您使用了错误的 --config 参数进行配置，程序自动退出"
                )
                System.set_power("KillSelf")

        elif Config.args.mode == "cli":

            logger.warning(
                "当前运行模式为命令行模式，由于您未使用 --config 参数进行配置，程序自动退出"
            )
            System.set_power("KillSelf")

        logger.success("启动时任务执行完成", module="主窗口")

    def start_main_task(self) -> None:
        """启动主任务"""

        logger.info("正在启动主任务", module="主窗口")

        if "调度队列_1" in Config.queue_dict:

            logger.info("自动添加任务：调度队列_1", module="主窗口")
            TaskManager.add_task(
                "自动代理_主调度台",
                "调度队列_1",
                Config.queue_dict["调度队列_1"]["Config"].toDict(),
            )

        elif "脚本_1" in Config.script_dict:

            logger.info("自动添加任务：脚本_1", module="主窗口")
            TaskManager.add_task(
                "自动代理_主调度台", "自定义队列", {"Queue": {"Script_0": "脚本_1"}}
            )

        else:

            logger.warning(
                "启动主任务失败：未找到有效的主任务配置文件", module="主窗口"
            )
            MainInfoBar.push_info_bar(
                "warning", "启动主任务失败", "「调度队列_1」与「脚本_1」均不存在", -1
            )

        logger.success("主任务启动完成", module="主窗口")

    def __currentChanged(self, index: int) -> None:
        """切换界面时任务"""

        if index == 1:
            self.script_manager.reload_plan_name()
        elif index == 3:
            self.queue_manager.reload_script_name()
        elif index == 4:
            self.dispatch_center.pivot.setCurrentItem("主调度台")
            self.dispatch_center.update_top_bar()

    def closeEvent(self, event: QCloseEvent):
        """清理残余进程"""

        logger.info("保存窗口位置与大小信息", module="主窗口")
        self.show_ui("隐藏到托盘", if_quick=True)

        # 清理各功能线程
        MainTimer.stop()
        TaskManager.stop_task("ALL")

        # 关闭主题监听
        self.themeListener.terminate()
        self.themeListener.deleteLater()

        logger.info("AUTO_MAA主程序关闭", module="主窗口")
        logger.info("----------------END----------------", module="主窗口")

        event.accept()
