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
AUTO_MAA设置界面
v4.2
作者：DLmaster_361
"""

from loguru import logger
from PySide6.QtWidgets import (
    QWidget,
    QApplication,
    QVBoxLayout,
    QVBoxLayout,
)
from qfluentwidgets import (
    ScrollArea,
    FluentIcon,
    MessageBox,
    Dialog,
    HyperlinkCard,
    HeaderCardWidget,
    SwitchSettingCard,
    ExpandGroupSettingCard,
    PushSettingCard,
)
from datetime import datetime
import json
import subprocess
import time
import requests

from app.core import Config, MainInfoBar
from app.services import Crypto, System
from app.utils import Updater
from .Widget import InputMessageBox, LineEditSettingCard


class Setting(QWidget):

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent)

        self.setObjectName("设置")

        layout = QVBoxLayout()

        scrollArea = ScrollArea()
        scrollArea.setWidgetResizable(True)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)

        self.function = FunctionSettingCard(self)
        self.start = StartSettingCard(self)
        self.ui = UiSettingCard(self)
        self.notification = NotifySettingCard(self)
        self.security = SecuritySettingCard(self)
        self.updater = UpdaterSettingCard(self)
        self.other = OtherSettingCard(self)

        self.function.card_IfAllowSleep.checkedChanged.connect(System.set_Sleep)
        self.start.card_IfSelfStart.checkedChanged.connect(System.set_SelfStart)
        self.security.card_changePASSWORD.clicked.connect(self.change_PASSWORD)
        self.updater.card_CheckUpdate.clicked.connect(self.get_update)
        self.other.card_Notice.clicked.connect(self.show_notice)

        content_layout.addWidget(self.function)
        content_layout.addWidget(self.start)
        content_layout.addWidget(self.ui)
        content_layout.addWidget(self.notification)
        content_layout.addWidget(self.security)
        content_layout.addWidget(self.updater)
        content_layout.addWidget(self.other)

        scrollArea.setWidget(content_widget)

        layout.addWidget(scrollArea)

        self.setLayout(layout)

    def check_PASSWORD(self) -> None:
        """检查并配置管理密钥"""

        if Config.key_path.exists():
            return None

        while True:

            choice = InputMessageBox(
                self.parent().parent().parent(),
                "未检测到管理密钥，请设置您的管理密钥",
                "管理密钥",
                "密码",
            )
            if choice.exec() and choice.input.text() != "":
                Crypto.get_PASSWORD(choice.input.text())
                break
            else:
                choice = MessageBox(
                    "警告",
                    "您没有设置管理密钥，无法使用本软件，请先设置管理密钥",
                    self.parent().parent().parent(),
                )
                choice.cancelButton.hide()
                choice.buttonLayout.insertStretch(1)
                if choice.exec():
                    pass

    def change_PASSWORD(self) -> None:
        """修改管理密钥"""

        if_change = True

        while if_change:

            choice = InputMessageBox(
                self,
                "请输入旧的管理密钥",
                "旧管理密钥",
                "密码",
            )
            if choice.exec() and choice.input.text() != "":

                # 验证旧管理密钥
                if Crypto.check_PASSWORD(choice.input.text()):

                    PASSWORD_old = choice.input.text()
                    # 获取新的管理密钥
                    while True:

                        choice = InputMessageBox(
                            self,
                            "请输入新的管理密钥",
                            "新管理密钥",
                            "密码",
                        )
                        if choice.exec() and choice.input.text() != "":

                            # 修改管理密钥
                            Crypto.change_PASSWORD(PASSWORD_old, choice.input.text())
                            MainInfoBar.push_info_bar(
                                "success", "操作成功", "管理密钥修改成功", 3000
                            )
                            if_change = False
                            break

                        else:

                            choice = MessageBox(
                                "确认",
                                "您没有输入新的管理密钥，是否取消修改管理密钥？",
                                self,
                            )
                            if choice.exec():
                                if_change = False
                                break

                else:
                    choice = MessageBox("错误", "管理密钥错误", self)
                    choice.cancelButton.hide()
                    choice.buttonLayout.insertStretch(1)
                    if choice.exec():
                        pass
            else:
                choice = MessageBox(
                    "确认",
                    "您没有输入管理密钥，是否取消修改管理密钥？",
                    self,
                )
                if choice.exec():
                    break

    def get_update_info(self) -> str:
        """检查主程序版本更新，返回更新信息"""

        # 从本地版本信息文件获取当前版本信息
        with Config.version_path.open(mode="r", encoding="utf-8") as f:
            version_current = json.load(f)
        main_version_current = list(
            map(int, version_current["main_version"].split("."))
        )

        # 从远程服务器获取最新版本信息
        for _ in range(3):
            try:
                response = requests.get(
                    "https://gitee.com/DLmaster_361/AUTO_MAA/raw/main/resources/version.json"
                )
                version_remote = response.json()
                break
            except Exception as e:
                err = e
                time.sleep(0.1)
        else:
            return f"获取版本信息时出错：\n{err}"

        main_version_remote = list(map(int, version_remote["main_version"].split(".")))

        # 有版本更新
        if main_version_remote > main_version_current:

            main_version_info = f"    主程序：{version_text(main_version_current)} --> {version_text(main_version_remote)}\n"

            return f"发现新版本：\n{main_version_info}    更新说明：\n{version_remote['announcement'].replace("\n# ","\n   ！").replace("\n## ","\n        - ").replace("\n- ","\n            · ")}\n\n是否开始更新？\n\n    注意：主程序更新时AUTO_MAA将自动关闭"

        else:
            return "已是最新版本~"

    def get_update(self, if_question: bool = True) -> None:
        """检查版本更新，调起文件下载进程"""

        # 从本地版本信息文件获取当前版本信息
        with Config.version_path.open(mode="r", encoding="utf-8") as f:
            version_current = json.load(f)
        main_version_current = list(
            map(int, version_current["main_version"].split("."))
        )
        updater_version_current = list(
            map(int, version_current["updater_version"].split("."))
        )
        # 检查更新器是否存在
        if not (Config.app_path / "Updater.exe").exists():
            updater_version_current = [0, 0, 0, 0]

        # 从远程服务器获取最新版本信息
        for _ in range(3):
            try:
                response = requests.get(
                    "https://gitee.com/DLmaster_361/AUTO_MAA/raw/main/resources/version.json"
                )
                version_remote = response.json()
                break
            except Exception as e:
                err = e
                time.sleep(0.1)
        else:
            choice = MessageBox(
                "错误",
                f"获取版本信息时出错：\n{err}",
                self,
            )
            choice.cancelButton.hide()
            choice.buttonLayout.insertStretch(1)
            if choice.exec():
                return None

        main_version_remote = list(map(int, version_remote["main_version"].split(".")))
        updater_version_remote = list(
            map(int, version_remote["updater_version"].split("."))
        )

        # 有版本更新
        if (main_version_remote > main_version_current) or (
            updater_version_remote > updater_version_current
        ):

            # 生成版本更新信息
            if main_version_remote > main_version_current:
                main_version_info = f"    主程序：{version_text(main_version_current)} --> {version_text(main_version_remote)}\n"
            else:
                main_version_info = (
                    f"    主程序：{version_text(main_version_current)}\n"
                )
            if updater_version_remote > updater_version_current:
                updater_version_info = f"    更新器：{version_text(updater_version_current)} --> {version_text(updater_version_remote)}\n"
            else:
                updater_version_info = (
                    f"    更新器：{version_text(updater_version_current)}\n"
                )

            # 询问是否开始版本更新
            if if_question:
                choice = MessageBox(
                    "版本更新",
                    f"发现新版本：\n{main_version_info}{updater_version_info}    更新说明：\n{version_remote['announcement'].replace("\n# ","\n   ！").replace("\n## ","\n        - ").replace("\n- ","\n            · ")}\n\n是否开始更新？\n\n    注意：主程序更新时AUTO_MAA将自动关闭",
                    self,
                )
                if not choice.exec():
                    return None

            # 更新更新器
            if updater_version_remote > updater_version_current:
                # 创建更新进程
                self.updater = Updater(
                    Config.app_path,
                    "AUTO_MAA更新器",
                    main_version_remote,
                    updater_version_remote,
                )
                # 完成更新器的更新后更新主程序
                if main_version_remote > main_version_current:
                    self.updater.update_process.accomplish.connect(self.update_main)
                # 显示更新页面
                self.updater.ui.show()

            # 更新主程序
            elif main_version_remote > main_version_current:
                self.update_main()

        # 无版本更新
        else:
            MainInfoBar.push_info_bar("success", "更新检查", "已是最新版本~", 3000)

    def update_main(self) -> None:
        """更新主程序"""

        subprocess.Popen(
            str(Config.app_path / "Updater.exe"),
            shell=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.close()
        QApplication.quit()

    def show_notice(self, if_show: bool = True):
        """显示公告"""

        # 从远程服务器获取最新版本信息
        for _ in range(3):
            try:
                response = requests.get(
                    "https://gitee.com/DLmaster_361/AUTO_MAA/raw/server/notice.json"
                )
                notice = response.json()
                break
            except Exception as e:
                err = e
                time.sleep(0.1)
        else:
            logger.warning(f"获取最新公告时出错：\n{err}")
            if if_show:
                choice = Dialog(
                    "网络错误",
                    f"获取最新公告时出错：\n{err}",
                    self,
                )
                choice.cancelButton.hide()
                choice.buttonLayout.insertStretch(1)
                choice.exec()
            return None

        if (Config.app_path / "resources/notice.json").exists():
            with (Config.app_path / "resources/notice.json").open(
                mode="r", encoding="utf-8"
            ) as f:
                notice_local = json.load(f)
            time_local = datetime.strptime(notice_local["time"], "%Y-%m-%d %H:%M")
        else:
            time_local = datetime.strptime("2000-01-01 00:00", "%Y-%m-%d %H:%M")

        if if_show or (
            datetime.now() > datetime.strptime(notice["time"], "%Y-%m-%d %H:%M")
            and datetime.strptime(notice["time"], "%Y-%m-%d %H:%M") > time_local
        ):

            choice = Dialog("公告", notice["content"], self)
            choice.cancelButton.hide()
            choice.buttonLayout.insertStretch(1)
            if choice.exec():
                with (Config.app_path / "resources/notice.json").open(
                    mode="w", encoding="utf-8"
                ) as f:
                    json.dump(notice, f, ensure_ascii=False, indent=4)


class FunctionSettingCard(HeaderCardWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setTitle("功能")

        Layout = QVBoxLayout()

        self.card_IfAllowSleep = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="启动时阻止系统休眠",
            content="仅阻止电脑自动休眠，不会影响屏幕是否熄灭",
            configItem=Config.global_config.function_IfAllowSleep,
        )

        self.card_IfSilence = self.SilenceSettingCard(self)

        # 添加各组到设置卡中
        Layout.addWidget(self.card_IfAllowSleep)
        Layout.addWidget(self.card_IfSilence)

        self.viewLayout.addLayout(Layout)

    class SilenceSettingCard(ExpandGroupSettingCard):

        def __init__(self, parent=None):
            super().__init__(
                FluentIcon.SETTING,
                "静默模式",
                "将各代理窗口置于后台运行，减少对前台的干扰",
                parent,
            )

            widget = QWidget()
            Layout = QVBoxLayout(widget)

            self.card_IfSilence = SwitchSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="静默模式",
                content="是否启用静默模式",
                configItem=Config.global_config.function_IfSilence,
            )

            self.card_BossKey = LineEditSettingCard(
                text="请输入安卓模拟器老版键",
                icon=FluentIcon.PAGE_RIGHT,
                title="模拟器老版键",
                content="输入模拟器老版快捷键，以“+”分隔",
                configItem=Config.global_config.function_BossKey,
            )

            Layout.addWidget(self.card_IfSilence)
            Layout.addWidget(self.card_BossKey)

            # 调整内部布局
            self.viewLayout.setContentsMargins(0, 0, 0, 0)
            self.viewLayout.setSpacing(0)

            self.addGroupWidget(widget)


class StartSettingCard(HeaderCardWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setTitle("启动")

        Layout = QVBoxLayout()

        self.card_IfSelfStart = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="开机时自动启动",
            content="将AUTO_MAA添加到开机启动项",
            configItem=Config.global_config.start_IfSelfStart,
        )

        self.card_IfRunDirectly = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="启动后直接运行",
            content="启动AUTO_MAA后自动运行任务(暂不可用)",
            configItem=Config.global_config.start_IfRunDirectly,
        )

        # 添加各组到设置卡中
        Layout.addWidget(
            self.card_IfSelfStart,
        )
        Layout.addWidget(self.card_IfRunDirectly)

        self.viewLayout.addLayout(Layout)


class UiSettingCard(HeaderCardWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setTitle("界面")

        Layout = QVBoxLayout()

        self.card_IfShowTray = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="显示托盘图标",
            content="常态显示托盘图标",
            configItem=Config.global_config.ui_IfShowTray,
        )

        self.card_IfToTray = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="最小化到托盘",
            content="最小化时隐藏到托盘",
            configItem=Config.global_config.ui_IfToTray,
        )

        # 添加各组到设置卡中
        Layout.addWidget(self.card_IfShowTray)
        Layout.addWidget(self.card_IfToTray)

        self.viewLayout.addLayout(Layout)


class NotifySettingCard(HeaderCardWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setTitle("通知")

        Layout = QVBoxLayout()

        self.card_IfSendErrorOnly = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="仅推送异常信息",
            content="仅在任务出现异常时推送通知",
            configItem=Config.global_config.notify_IfSendErrorOnly,
        )

        self.card_IfPushPlyer = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="推送系统通知",
            content="推送系统级通知，不会在通知中心停留",
            configItem=Config.global_config.notify_IfPushPlyer,
        )

        self.card_SendMail = self.SendMailSettingCard(self)
        self.card_ServerChan = self.ServerChanSettingCard(self)
        self.card_CompanyWebhookBot = self.CompanyWechatPushSettingCard(self)
        Layout.addWidget(self.card_IfSendErrorOnly)
        Layout.addWidget(self.card_IfPushPlyer)
        Layout.addWidget(self.card_SendMail)
        Layout.addWidget(self.card_ServerChan)
        Layout.addWidget(self.card_CompanyWebhookBot)

        self.viewLayout.addLayout(Layout)

    class SendMailSettingCard(ExpandGroupSettingCard):

        def __init__(self, parent=None):
            super().__init__(
                FluentIcon.SETTING,
                "推送邮件通知",
                "通过AUTO_MAA官方通知服务邮箱推送任务结果",
                parent,
            )

            widget = QWidget()
            Layout = QVBoxLayout(widget)

            self.card_IfSendMail = SwitchSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="推送邮件通知",
                content="是否启用邮件通知功能",
                configItem=Config.global_config.notify_IfSendMail,
            )

            self.MailAddress = LineEditSettingCard(
                text="请输入邮箱地址",
                icon=FluentIcon.PAGE_RIGHT,
                title="邮箱地址",
                content="接收通知的邮箱地址",
                configItem=Config.global_config.notify_MailAddress,
            )

            Layout.addWidget(self.card_IfSendMail)
            Layout.addWidget(self.MailAddress)

            # 调整内部布局
            self.viewLayout.setContentsMargins(0, 0, 0, 0)
            self.viewLayout.setSpacing(0)

            self.addGroupWidget(widget)

    class ServerChanSettingCard(ExpandGroupSettingCard):
        def __init__(self, parent=None):
            super().__init__(
                FluentIcon.SETTING,
                "ServerChan推送",
                "通过ServerChan推送推送任务结果",
                parent,
            )

            widget = QWidget()
            Layout = QVBoxLayout(widget)

            self.card_IfServerChan = SwitchSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="SeverChan推送",
                content="是否SeverChan推送",
                configItem=Config.global_config.notify_IfServerChan,
            )

            self.ServerChanKey = LineEditSettingCard(
                text="请输入SendKey",
                icon=FluentIcon.PAGE_RIGHT,
                title="SendKey",
                content="Server酱的SendKey（SC3与SCT都可以）",
                configItem=Config.global_config.notify_ServerChanKey,
            )

            self.ServerChanChannel = LineEditSettingCard(
                text="请输入需要推送的Channel代码(SCT生效）",
                icon=FluentIcon.PAGE_RIGHT,
                title="ServerChanChannel代码",
                content="可以留空，留空则默认。可以多个，请使用|隔开",
                configItem=Config.global_config.notify_ServerChanChannel,
            )

            self.ServerChanTag = LineEditSettingCard(
                text="请输入加入推送的Tag（SC3生效）",
                icon=FluentIcon.PAGE_RIGHT,
                title="Tag内容",
                content="可以留空，留空则默认。可以多个，请使用|隔开",
                configItem=Config.global_config.notify_ServerChanTag,
            )
            Layout.addWidget(self.card_IfServerChan)
            Layout.addWidget(self.ServerChanKey)
            Layout.addWidget(self.ServerChanChannel)
            Layout.addWidget(self.ServerChanTag)
            self.viewLayout.setContentsMargins(0, 0, 0, 0)
            self.viewLayout.setSpacing(0)
            self.addGroupWidget(widget)

        widget = QWidget()
        Layout = QVBoxLayout(widget)

    class CompanyWechatPushSettingCard(ExpandGroupSettingCard):
        def __init__(self, parent=None):
            super().__init__(
                FluentIcon.SETTING,
                "企业微信机器人推送",
                "通过企业微信机器人Webhook推送推送任务结果",
                parent,
            )

            widget = QWidget()
            Layout = QVBoxLayout(widget)

            self.card_IfCompanyWechat = SwitchSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="企业微信机器人推送",
                content="是否启用企业微信机器人推送",
                configItem=Config.global_config.notify_IfCompanyWebHookBot,
            )

            self.CompanyWebHookBotUrl = LineEditSettingCard(
                text="请输入Webhook的Url",
                icon=FluentIcon.PAGE_RIGHT,
                title="WebhookUrl",
                content="企业微信群机器人的Webhook地址",
                configItem=Config.global_config.notify_CompanyWebHookBotUrl,
            )

            Layout.addWidget(self.card_IfCompanyWechat)
            Layout.addWidget(self.CompanyWebHookBotUrl)
            self.viewLayout.setContentsMargins(0, 0, 0, 0)
            self.viewLayout.setSpacing(0)
            self.addGroupWidget(widget)
        widget = QWidget()
        Layout = QVBoxLayout(widget)


class SecuritySettingCard(HeaderCardWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setTitle("安全")

        Layout = QVBoxLayout()

        self.card_changePASSWORD = PushSettingCard(
            text="修改",
            icon=FluentIcon.VPN,
            title="修改管理密钥",
            content="修改用于解密用户密码的管理密钥",
        )

        Layout.addWidget(self.card_changePASSWORD)

        self.viewLayout.addLayout(Layout)


class UpdaterSettingCard(HeaderCardWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setTitle("更新")

        Layout = QVBoxLayout()

        self.card_IfAutoUpdate = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="自动检查更新",
            content="将在启动时自动检查AUTO_MAA是否有新版本",
            configItem=Config.global_config.update_IfAutoUpdate,
        )

        self.card_CheckUpdate = PushSettingCard(
            text="检查更新",
            icon=FluentIcon.UPDATE,
            title="获取最新版本",
            content="检查AUTO_MAA是否有新版本",
        )

        Layout.addWidget(self.card_IfAutoUpdate)
        Layout.addWidget(self.card_CheckUpdate)

        self.viewLayout.addLayout(Layout)


class OtherSettingCard(HeaderCardWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setTitle("其他")

        self.card_Notice = PushSettingCard(
            text="查看",
            icon=FluentIcon.PAGE_RIGHT,
            title="公告",
            content="查看AUTO_MAA的最新公告",
        )

        self.card_UserDocs = HyperlinkCard(
            url="https://docs.qq.com/aio/DQ2NwUHRiWGtMWHBy",
            text="访问用户文档",
            icon=FluentIcon.PAGE_RIGHT,
            title="用户文档",
            content="查看AUTO_MAA的使用教程和文档",
        )

        self.card_Association = self.AssociationSettingCard()

        Layout = QVBoxLayout()
        Layout.addWidget(self.card_Notice)
        Layout.addWidget(self.card_UserDocs)
        Layout.addWidget(self.card_Association)
        self.viewLayout.addLayout(Layout)

    class AssociationSettingCard(ExpandGroupSettingCard):

        def __init__(self, parent=None):
            super().__init__(
                FluentIcon.SETTING,
                "AUTO_MAA官方社群",
                "加入AUTO_MAA官方社群，获取更多帮助",
                parent,
            )

            self.card_GitHubRepository = HyperlinkCard(
                url="https://github.com/DLmaster361/AUTO_MAA",
                text="访问GitHub仓库",
                icon=FluentIcon.GITHUB,
                title="GitHub",
                content="查看AUTO_MAA的源代码，提交问题和建议，欢迎参与开发",
            )
            self.card_QQGroup = HyperlinkCard(
                url="https://qm.qq.com/q/bd9fISNoME",
                text="加入官方QQ交流群",
                icon=FluentIcon.CHAT,
                title="QQ群",
                content="与AUTO_MAA开发者和用户交流",
            )

            widget = QWidget()
            Layout = QVBoxLayout(widget)
            Layout.addWidget(self.card_GitHubRepository)
            Layout.addWidget(self.card_QQGroup)
            self.viewLayout.setContentsMargins(0, 0, 0, 0)
            self.viewLayout.setSpacing(0)
            self.addGroupWidget(widget)


def version_text(version_numb: list) -> str:
    """将版本号列表转为可读的文本信息"""

    if version_numb[3] == 0:
        version = f"v{'.'.join(str(_) for _ in version_numb[0:3])}"
    else:
        version = (
            f"v{'.'.join(str(_) for _ in version_numb[0:3])}-beta.{version_numb[3]}"
        )
    return version
