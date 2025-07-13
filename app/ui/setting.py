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
AUTO_MAA设置界面
v4.4
作者：DLmaster_361
"""

from loguru import logger
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt
from qfluentwidgets import (
    ScrollArea,
    FluentIcon,
    MessageBox,
    HyperlinkCard,
    HeaderCardWidget,
    ExpandGroupSettingCard,
    PushSettingCard,
    HyperlinkButton,
)
import os
import re
import json
import shutil
import subprocess
from datetime import datetime
from packaging import version
from pathlib import Path
from typing import Dict, Union

from app.core import Config, MainInfoBar, Network, SoundPlayer
from app.services import Crypto, System, Notify
from .downloader import DownloadManager
from .Widget import (
    SwitchSettingCard,
    RangeSettingCard,
    ComboBoxSettingCard,
    LineEditMessageBox,
    LineEditSettingCard,
    PasswordLineEditSettingCard,
    UrlListSettingCard,
    NoticeMessageBox,
)


class Setting(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("设置")

        self.function = FunctionSettingCard(self)
        self.voice = VoiceSettingCard(self)
        self.start = StartSettingCard(self)
        self.ui = UiSettingCard(self)
        self.notification = NotifySettingCard(self)
        self.security = SecuritySettingCard(self)
        self.updater = UpdaterSettingCard(self)
        self.other = OtherSettingCard(self)

        self.function.card_IfAllowSleep.checkedChanged.connect(System.set_Sleep)
        self.function.card_IfAgreeBilibili.checkedChanged.connect(self.agree_bilibili)
        self.function.card_IfSkipMumuSplashAds.checkedChanged.connect(
            self.skip_MuMu_splash_ads
        )
        self.start.card_IfSelfStart.checkedChanged.connect(System.set_SelfStart)
        self.security.card_changePASSWORD.clicked.connect(self.change_PASSWORD)
        self.security.card_resetPASSWORD.clicked.connect(self.reset_PASSWORD)
        self.updater.card_CheckUpdate.clicked.connect(
            lambda: self.check_update(if_show=True)
        )
        self.other.card_Notice.clicked.connect(lambda: self.show_notice(if_show=True))

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 11, 0)
        content_layout.addWidget(self.function)
        content_layout.addWidget(self.voice)
        content_layout.addWidget(self.start)
        content_layout.addWidget(self.ui)
        content_layout.addWidget(self.notification)
        content_layout.addWidget(self.security)
        content_layout.addWidget(self.updater)
        content_layout.addWidget(self.other)

        scrollArea = ScrollArea()
        scrollArea.setWidgetResizable(True)
        scrollArea.setContentsMargins(0, 0, 0, 0)
        scrollArea.setStyleSheet("background: transparent; border: none;")
        scrollArea.setWidget(content_widget)

        layout = QVBoxLayout(self)
        layout.addWidget(scrollArea)

    def agree_bilibili(self) -> None:
        """授权bilibili游戏隐私政策"""

        if Config.get(Config.function_IfAgreeBilibili):

            choice = MessageBox(
                "授权声明",
                "开启「托管bilibili游戏隐私政策」功能，即代表您已完整阅读并同意《哔哩哔哩弹幕网用户使用协议》、《哔哩哔哩隐私政策》和《哔哩哔哩游戏中心用户协议》，并授权AUTO_MAA在其认定需要时以其认定合适的方法替您处理相关弹窗\n\n是否同意授权？",
                self.window(),
            )
            if choice.exec():
                logger.success("确认授权bilibili游戏隐私政策")
                MainInfoBar.push_info_bar(
                    "success", "操作成功", "已确认授权bilibili游戏隐私政策", 3000
                )
            else:
                Config.set(Config.function_IfAgreeBilibili, False)
        else:

            logger.info("取消授权bilibili游戏隐私政策")
            MainInfoBar.push_info_bar(
                "info", "操作成功", "已取消授权bilibili游戏隐私政策", 3000
            )

    def skip_MuMu_splash_ads(self) -> None:
        """跳过MuMu启动广告"""

        MuMu_splash_ads_path = (
            Path(os.getenv("APPDATA")) / "Netease/MuMuPlayer-12.0/data/startupImage"
        )

        if Config.get(Config.function_IfSkipMumuSplashAds):

            choice = MessageBox(
                "风险声明",
                "开启「跳过MuMu启动广告」功能，即代表您已安装MuMu模拟器-12且允许AUTO_MAA以其认定合适的方法屏蔽MuMu启动广告，并接受此操作带来的风险\n\n此功能即时生效，是否仍要开启此功能？",
                self.window(),
            )
            if choice.exec():

                if MuMu_splash_ads_path.exists() and MuMu_splash_ads_path.is_dir():
                    shutil.rmtree(MuMu_splash_ads_path)

                MuMu_splash_ads_path.touch()

                logger.success("开启跳过MuMu启动广告功能")
                MainInfoBar.push_info_bar(
                    "success", "操作成功", "已开启跳过MuMu启动广告功能", 3000
                )
            else:
                Config.set(Config.function_IfSkipMumuSplashAds, False)

        else:

            if MuMu_splash_ads_path.exists() and MuMu_splash_ads_path.is_file():
                MuMu_splash_ads_path.unlink()

            logger.info("关闭跳过MuMu启动广告功能")
            MainInfoBar.push_info_bar(
                "info", "操作成功", "已关闭跳过MuMu启动广告功能", 3000
            )

    def check_PASSWORD(self) -> None:
        """检查并配置管理密钥"""

        if Config.key_path.exists():
            return None

        while True:

            choice = LineEditMessageBox(
                self.window(), "请设置您的管理密钥", "管理密钥", "密码"
            )
            if choice.exec() and choice.input.text() != "":
                Crypto.get_PASSWORD(choice.input.text())
                break
            else:
                choice = MessageBox(
                    "警告",
                    "您没有设置管理密钥，无法使用本软件，请先设置管理密钥",
                    self.window(),
                )
                choice.cancelButton.hide()
                choice.buttonLayout.insertStretch(1)
                choice.exec()

    def change_PASSWORD(self) -> None:
        """修改管理密钥"""

        if_change = True

        while if_change:

            choice = LineEditMessageBox(
                self.window(),
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

                        choice = LineEditMessageBox(
                            self.window(),
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
                                self.window(),
                            )
                            if choice.exec():
                                if_change = False
                                break

                else:
                    choice = MessageBox("错误", "管理密钥错误", self.window())
                    choice.cancelButton.hide()
                    choice.buttonLayout.insertStretch(1)
                    choice.exec()
            else:
                choice = MessageBox(
                    "确认", "您没有输入管理密钥，是否取消修改管理密钥？", self.window()
                )
                if choice.exec():
                    break

    def reset_PASSWORD(self) -> None:
        """重置管理密钥"""

        choice = MessageBox(
            "确认",
            "重置管理密钥将清空所有使用管理密钥加密的数据，您确认要重置管理密钥吗？",
            self.window(),
        )
        if choice.exec():
            choice = LineEditMessageBox(
                self.window(),
                "请输入文本提示框内的验证信息",
                "AUTO_MAA绝赞DeBug中！",
                "明文",
            )

            if choice.exec() and choice.input.text() in [
                "AUTO_MAA绝赞DeBug中！",
                "AUTO_MAA绝赞DeBug中!",
            ]:

                # 获取新的管理密钥
                while True:

                    choice = LineEditMessageBox(
                        self.window(), "请输入新的管理密钥", "新管理密钥", "密码"
                    )
                    if choice.exec() and choice.input.text() != "":

                        # 重置管理密钥
                        Crypto.reset_PASSWORD(choice.input.text())
                        MainInfoBar.push_info_bar(
                            "success", "操作成功", "管理密钥重置成功", 3000
                        )
                        break

                    else:

                        choice = MessageBox(
                            "确认",
                            "您没有输入新的管理密钥，是否取消修改管理密钥？",
                            self.window(),
                        )
                        if choice.exec():
                            break

            else:

                MainInfoBar.push_info_bar(
                    "info",
                    "验证未通过",
                    "请输入「AUTO_MAA绝赞DeBug中！」后单击确认键",
                    3000,
                )

    def check_update(self, if_show: bool = False, if_first: bool = False) -> None:
        """检查版本更新，调起文件下载进程"""

        current_version = list(map(int, Config.VERSION.split(".")))

        # 从远程服务器获取最新版本信息
        network = Network.add_task(
            mode="get",
            url=f"https://mirrorchyan.com/api/resources/AUTO_MAA/latest?user_agent=AutoMaaGui&current_version={version_text(current_version)}&cdk={Crypto.win_decryptor(Config.get(Config.update_MirrorChyanCDK))}&channel={Config.get(Config.update_UpdateType)}",
        )
        network.loop.exec()
        network_result = Network.get_result(network)
        if network_result["status_code"] == 200:
            version_info: Dict[str, Union[int, str, Dict[str, str]]] = network_result[
                "response_json"
            ]
        else:

            if network_result["response_json"]:

                version_info = network_result["response_json"]

                if version_info["code"] != 0:

                    logger.error(f"获取版本信息时出错：{version_info['msg']}")

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
                        1: version_info["msg"],
                    }

                    if version_info["code"] in error_remark_dict:
                        MainInfoBar.push_info_bar(
                            "error",
                            "获取版本信息时出错",
                            error_remark_dict[version_info["code"]],
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

            logger.warning(f"获取版本信息时出错：{network_result['error_message']}")
            MainInfoBar.push_info_bar(
                "warning",
                "获取版本信息时出错",
                f"网络错误：{network_result['status_code']}",
                5000,
            )
            return None

        remote_version = list(
            map(
                int,
                version_info["data"]["version_name"][1:]
                .replace("-beta", "")
                .split("."),
            )
        )

        if (
            if_show
            or (
                not if_show
                and if_first
                and not Config.get(Config.function_UnattendedMode)
            )
        ) and version.parse(version_text(remote_version)) > version.parse(
            version_text(current_version)
        ):

            version_info_json: Dict[str, Dict[str, str]] = json.loads(
                re.sub(
                    r"^<!--\s*(.*?)\s*-->$",
                    r"\1",
                    version_info["data"]["release_note"].splitlines()[0],
                )
            )

            # 生成版本更新信息
            main_version_info = f"## 主程序：{version_text(current_version)} --> {version_text(remote_version)}"

            update_version_info = {}
            all_version_info = {}
            for v_i in [
                info
                for ver, info in version_info_json.items()
                if version.parse(version_text(list(map(int, ver.split(".")))))
                > version.parse(version_text(current_version))
            ]:

                for key, value in v_i.items():
                    if key in update_version_info:
                        update_version_info[key] += value.copy()
                    else:
                        update_version_info[key] = value.copy()
            for v_i in version_info_json.values():
                for key, value in v_i.items():
                    if key in all_version_info:
                        all_version_info[key] += value.copy()
                    else:
                        all_version_info[key] = value.copy()

            # 询问是否开始版本更新
            SoundPlayer.play("有新版本")
            choice = NoticeMessageBox(
                self.window(),
                "版本更新",
                {
                    "更新总览": f"{main_version_info}\n\n{version_info_markdown(update_version_info)}",
                    "ALL~版本信息": version_info_markdown(all_version_info),
                    **{
                        version_text(
                            list(map(int, k.split(".")))
                        ): version_info_markdown(v)
                        for k, v in version_info_json.items()
                    },
                },
            )
            if choice.exec():

                if "url" in version_info["data"]:
                    download_config = {
                        "mode": "MirrorChyan",
                        "thread_numb": 1,
                        "url": version_info["data"]["url"],
                    }
                else:

                    # 从远程服务器获取代理信息
                    network = Network.add_task(
                        mode="get",
                        url="https://gitee.com/DLmaster_361/AUTO_MAA/raw/server/download_info.json",
                    )
                    network.loop.exec()
                    network_result = Network.get_result(network)
                    if network_result["status_code"] == 200:
                        download_info = network_result["response_json"]
                    else:
                        logger.warning(
                            f"获取应用列表时出错：{network_result['error_message']}"
                        )
                        MainInfoBar.push_info_bar(
                            "warning",
                            "获取应用列表时出错",
                            f"网络错误：{network_result['status_code']}",
                            5000,
                        )
                        return None

                    download_config = {
                        "mode": "Proxy",
                        "thread_numb": Config.get(Config.update_ThreadNumb),
                        "proxy_list": list(
                            set(
                                Config.get(Config.update_ProxyUrlList)
                                + download_info["proxy_list"]
                            )
                        ),
                        "download_dict": download_info["download_dict"],
                    }

                self.downloader = DownloadManager(
                    Config.app_path, "AUTO_MAA", remote_version, download_config
                )
                self.downloader.setWindowTitle("AUTO_MAA更新器")
                self.downloader.setWindowIcon(
                    QIcon(str(Config.app_path / "resources/icons/AUTO_MAA_Updater.ico"))
                )
                self.downloader.download_accomplish.connect(self.start_setup)
                self.downloader.show()
                self.downloader.run()

        elif (
            if_show
            or if_first
            or version.parse(version_text(remote_version))
            > version.parse(version_text(current_version))
        ):

            if version.parse(version_text(remote_version)) > version.parse(
                version_text(current_version)
            ):
                MainInfoBar.push_info_bar(
                    "info",
                    "发现新版本",
                    f"{version_text(current_version)} --> {version_text(remote_version)}",
                    3600000,
                    if_force=True,
                )
                SoundPlayer.play("有新版本")
            else:
                MainInfoBar.push_info_bar("success", "更新检查", "已是最新版本~", 3000)
                SoundPlayer.play("无新版本")

    def start_setup(self) -> None:
        subprocess.Popen(
            [
                Config.app_path / "AUTO_MAA-Setup.exe",
                "/SP-",
                "/SILENT",
                "/NOCANCEL",
                "/FORCECLOSEAPPLICATIONS",
                "/LANG=Chinese",
                f"/DIR={Config.app_path}",
            ],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NO_WINDOW,
        )
        System.set_power("KillSelf")

    def show_notice(self, if_show: bool = False, if_first: bool = False) -> None:
        """显示公告"""

        # 从远程服务器获取最新公告
        network = Network.add_task(
            mode="get",
            url="https://gitee.com/DLmaster_361/AUTO_MAA/raw/server/notice.json",
        )
        network.loop.exec()
        network_result = Network.get_result(network)
        if network_result["status_code"] == 200:
            notice = network_result["response_json"]
        else:
            logger.warning(f"获取最新公告时出错：{network_result['error_message']}")
            MainInfoBar.push_info_bar(
                "warning",
                "获取最新公告时出错",
                f"网络错误：{network_result['status_code']}",
                5000,
            )
            return None

        if (Config.app_path / "resources/notice.json").exists():
            with (Config.app_path / "resources/notice.json").open(
                mode="r", encoding="utf-8"
            ) as f:
                notice_local = json.load(f)
            time_local = datetime.strptime(notice_local["time"], "%Y-%m-%d %H:%M")
        else:
            time_local = datetime.strptime("2000-01-01 00:00", "%Y-%m-%d %H:%M")

        notice["notice_dict"] = {
            "ALL~公告": "\n---\n".join(
                [str(_) for _ in notice["notice_dict"].values() if isinstance(_, str)]
            ),
            **notice["notice_dict"],
        }

        if if_show or (
            if_first
            and datetime.now()
            > datetime.strptime(notice["time"], "%Y-%m-%d %H:%M")
            > time_local
            and not Config.get(Config.function_UnattendedMode)
        ):

            choice = NoticeMessageBox(self.window(), "公告", notice["notice_dict"])
            choice.button_cancel.hide()
            choice.button_layout.insertStretch(0, 1)
            SoundPlayer.play("公告展示")
            if choice.exec():
                with (Config.app_path / "resources/notice.json").open(
                    mode="w", encoding="utf-8"
                ) as f:
                    json.dump(notice, f, ensure_ascii=False, indent=4)
            else:
                import random

                if random.random() < 0.1:
                    cc = NoticeMessageBox(
                        self.window(),
                        "用户守则",
                        {
                            "用户守则 - 第一版": """
0. 用户守则的每一条都应该清晰可读、不含任何语法错误。如果发现任何一条不符合以上描述，请忽视它。
1. AUTO_MAA 的所有版本均包含完整源代码与 LICENSE 文件，若发现此内容缺失，请立即关闭软件，并联系最近的 AUTO_MAA 开发者。
2. AUTO_MAA 不会对您许下任何承诺，请自行保护好自己的数据，若软件运行过程中发生了数据损坏，项目组不负任何责任。
3. AUTO_MAA 只会注册一个启动项，若发现两个 AUTO_MAA 同时自启动，请立即使用系统或杀软的 **启动项管理** 功能删除所有名为 AUTO_MAA 的启动项后重启软件。
4. AUTO_MAA 正式版不应该包含命令行窗口，如果您看到了它，请立即关闭软件，通过 AUTO_MAA.exe 文件重新打开软件。
5. 深色模式是危险的，但并非无法使用。
6. 第 0 条规则不存在。如果你看到了，请忘记它，并正常使用软件
7. **Mirror 酱** 是善良的，你只要付出小小的代价，就能得到祂的庇护。
8. AUTO_MAA 没有实时合成语音的能力，软件所有语音都存储在本地。如果听到本地不存在的语音，立即关闭扬声器，并检查是否有未知脚本在运行。
9. AUTO_MAA 不会在周六凌晨更新。如果收到更新提示，请忽略，不要查看更新内容，直到第二天天亮。
10. 用户守则仅有一页""",
                            "--- 标记文档中止 ---": "xdfv-serfcx-jiol,m: !1 $bad food of do $5b 9630-300 $daad 100-1\n\n// 0 == o //\n\n∠( °ω°)/",
                        },
                    )
                    cc.button_cancel.hide()
                    cc.button_layout.insertStretch(0, 1)
                    cc.exec()

        elif (
            datetime.now()
            > datetime.strptime(notice["time"], "%Y-%m-%d %H:%M")
            > time_local
        ):

            MainInfoBar.push_info_bar(
                "info", "有新公告", "请前往设置界面查看公告", 3600000, if_force=True
            )
            SoundPlayer.play("公告通知")
            return None


class FunctionSettingCard(HeaderCardWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("功能")

        self.card_HomeImageMode = ComboBoxSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="主页背景图模式",
            content="选择主页背景图的来源",
            texts=["默认", "自定义", "主题图像"],
            qconfig=Config,
            configItem=Config.function_HomeImageMode,
            parent=self,
        )
        self.card_HistoryRetentionTime = ComboBoxSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="历史记录保留时间",
            content="选择历史记录的保留时间，超期自动清理",
            texts=["7 天", "15 天", "30 天", "60 天", "90 天", "半年", "一年", "永久"],
            qconfig=Config,
            configItem=Config.function_HistoryRetentionTime,
            parent=self,
        )
        self.card_IfAllowSleep = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="启动时阻止系统休眠",
            content="仅阻止电脑自动休眠，不会影响屏幕是否熄灭",
            qconfig=Config,
            configItem=Config.function_IfAllowSleep,
            parent=self,
        )
        self.card_IfSilence = self.SilenceSettingCard(self)
        self.card_UnattendedMode = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="无人值守模式",
            content="开启后AUTO_MAA不再主动弹出对话框，以免影响代理任务运行",
            qconfig=Config,
            configItem=Config.function_UnattendedMode,
            parent=self,
        )
        self.card_IfAgreeBilibili = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="托管bilibili游戏隐私政策",
            content="授权AUTO_MAA同意bilibili游戏隐私政策",
            qconfig=Config,
            configItem=Config.function_IfAgreeBilibili,
            parent=self,
        )
        self.card_IfSkipMumuSplashAds = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="跳过MuMu启动广告",
            content="启动MuMu模拟器时屏蔽启动广告",
            qconfig=Config,
            configItem=Config.function_IfSkipMumuSplashAds,
            parent=self,
        )

        Layout = QVBoxLayout()
        Layout.addWidget(self.card_HomeImageMode)
        Layout.addWidget(self.card_HistoryRetentionTime)
        Layout.addWidget(self.card_IfAllowSleep)
        Layout.addWidget(self.card_IfSilence)
        Layout.addWidget(self.card_UnattendedMode)
        Layout.addWidget(self.card_IfAgreeBilibili)
        Layout.addWidget(self.card_IfSkipMumuSplashAds)
        self.viewLayout.addLayout(Layout)

    class SilenceSettingCard(ExpandGroupSettingCard):

        def __init__(self, parent=None):
            super().__init__(
                FluentIcon.SETTING,
                "静默模式",
                "将各代理窗口置于后台运行，减少对前台的干扰",
                parent,
            )

            self.card_IfSilence = SwitchSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="静默模式",
                content="是否启用静默模式",
                qconfig=Config,
                configItem=Config.function_IfSilence,
                parent=self,
            )
            self.card_BossKey = LineEditSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="模拟器老板键",
                content="请输入对应的模拟器老板键，请直接输入文字，多个键位之间请用「+」隔开。如：「Alt+Q」",
                text="请以文字形式输入模拟器老板快捷键",
                qconfig=Config,
                configItem=Config.function_BossKey,
                parent=self,
            )

            widget = QWidget()
            Layout = QVBoxLayout(widget)
            Layout.addWidget(self.card_IfSilence)
            Layout.addWidget(self.card_BossKey)
            self.viewLayout.setContentsMargins(0, 0, 0, 0)
            self.viewLayout.setSpacing(0)
            self.addGroupWidget(widget)


class VoiceSettingCard(HeaderCardWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("音效")

        self.card_Enabled = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="音效开关",
            content="是否启用音效",
            qconfig=Config,
            configItem=Config.voice_Enabled,
            parent=self,
        )
        self.card_Type = ComboBoxSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="音效模式",
            content="选择音效的播放模式",
            texts=["简洁", "聒噪"],
            qconfig=Config,
            configItem=Config.voice_Type,
            parent=self,
        )

        Layout = QVBoxLayout()
        Layout.addWidget(self.card_Enabled)
        Layout.addWidget(self.card_Type)
        self.viewLayout.addLayout(Layout)


class StartSettingCard(HeaderCardWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("启动")

        self.card_IfSelfStart = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="开机时自动启动",
            content="将AUTO_MAA添加到开机启动项",
            qconfig=Config,
            configItem=Config.start_IfSelfStart,
            parent=self,
        )
        self.card_IfRunDirectly = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="启动后直接运行主任务",
            content="启动AUTO_MAA后自动运行自动代理任务，优先级：调度队列 1 > 脚本 1",
            qconfig=Config,
            configItem=Config.start_IfRunDirectly,
            parent=self,
        )
        self.card_IfMinimizeDirectly = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="启动后直接最小化",
            content="启动AUTO_MAA后直接最小化",
            qconfig=Config,
            configItem=Config.start_IfMinimizeDirectly,
            parent=self,
        )

        Layout = QVBoxLayout()
        Layout.addWidget(self.card_IfSelfStart)
        Layout.addWidget(self.card_IfRunDirectly)
        Layout.addWidget(self.card_IfMinimizeDirectly)
        self.viewLayout.addLayout(Layout)


class UiSettingCard(HeaderCardWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("界面")

        self.card_IfShowTray = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="显示托盘图标",
            content="常态显示托盘图标",
            qconfig=Config,
            configItem=Config.ui_IfShowTray,
            parent=self,
        )
        self.card_IfToTray = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="最小化到托盘",
            content="最小化时隐藏到托盘",
            qconfig=Config,
            configItem=Config.ui_IfToTray,
            parent=self,
        )

        Layout = QVBoxLayout()
        Layout.addWidget(self.card_IfShowTray)
        Layout.addWidget(self.card_IfToTray)
        self.viewLayout.addLayout(Layout)


class NotifySettingCard(HeaderCardWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setTitle("通知")

        self.card_NotifyContent = self.NotifyContentSettingCard(self)
        self.card_Plyer = self.PlyerSettingCard(self)
        self.card_EMail = self.EMailSettingCard(self)
        self.card_ServerChan = self.ServerChanSettingCard(self)
        self.card_CompanyWebhookBot = self.CompanyWechatPushSettingCard(self)
        self.card_TestNotification = PushSettingCard(
            text="发送测试通知",
            icon=FluentIcon.SEND,
            title="测试通知",
            content="发送测试通知到所有已启用的通知渠道",
            parent=self,
        )
        self.card_TestNotification.clicked.connect(self.send_test_notification)

        Layout = QVBoxLayout()
        Layout.addWidget(self.card_NotifyContent)
        Layout.addWidget(self.card_Plyer)
        Layout.addWidget(self.card_EMail)
        Layout.addWidget(self.card_ServerChan)
        Layout.addWidget(self.card_CompanyWebhookBot)
        Layout.addWidget(self.card_TestNotification)
        self.viewLayout.addLayout(Layout)

    def send_test_notification(self):
        """发送测试通知到所有已启用的通知渠道"""
        if Notify.send_test_notification():
            MainInfoBar.push_info_bar(
                "success",
                "测试通知已发送",
                "请检查已配置的通知渠道是否正常收到消息",
                3000,
            )

    class NotifyContentSettingCard(ExpandGroupSettingCard):

        def __init__(self, parent=None):
            super().__init__(
                FluentIcon.SETTING, "通知内容选项", "选择需要推送的通知内容", parent
            )

            self.card_SendTaskResultTime = ComboBoxSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="推送任务结果选项",
                content="选择推送自动代理与人工排查任务结果的时机",
                texts=["不推送", "任何时刻", "仅失败时"],
                qconfig=Config,
                configItem=Config.notify_SendTaskResultTime,
                parent=self,
            )
            self.card_IfSendStatistic = SwitchSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="推送统计信息",
                content="推送自动代理统计信息的通知",
                qconfig=Config,
                configItem=Config.notify_IfSendStatistic,
                parent=self,
            )
            self.card_IfSendSixStar = SwitchSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="推送公招高资喜报",
                content="公招出现六星词条时推送喜报",
                qconfig=Config,
                configItem=Config.notify_IfSendSixStar,
                parent=self,
            )

            widget = QWidget()
            Layout = QVBoxLayout(widget)
            Layout.addWidget(self.card_SendTaskResultTime)
            Layout.addWidget(self.card_IfSendStatistic)
            Layout.addWidget(self.card_IfSendSixStar)
            self.viewLayout.setContentsMargins(0, 0, 0, 0)
            self.viewLayout.setSpacing(0)
            self.addGroupWidget(widget)

    class PlyerSettingCard(ExpandGroupSettingCard):

        def __init__(self, parent=None):
            super().__init__(
                FluentIcon.SETTING, "推送系统通知", "Plyer系统通知推送渠道", parent
            )

            self.card_IfPushPlyer = SwitchSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="推送系统通知",
                content="使用Plyer推送系统级通知，不会在通知中心停留",
                qconfig=Config,
                configItem=Config.notify_IfPushPlyer,
                parent=self,
            )

            widget = QWidget()
            Layout = QVBoxLayout(widget)
            Layout.addWidget(self.card_IfPushPlyer)
            self.viewLayout.setContentsMargins(0, 0, 0, 0)
            self.viewLayout.setSpacing(0)
            self.addGroupWidget(widget)

    class EMailSettingCard(ExpandGroupSettingCard):

        def __init__(self, parent=None):
            super().__init__(
                FluentIcon.SETTING, "推送邮件通知", "电子邮箱通知推送渠道", parent
            )

            self.card_IfSendMail = SwitchSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="推送邮件通知",
                content="是否启用邮件通知功能",
                qconfig=Config,
                configItem=Config.notify_IfSendMail,
                parent=self,
            )
            self.card_SMTPServerAddress = LineEditSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="SMTP服务器地址",
                content="发信邮箱的SMTP服务器地址",
                text="请输入SMTP服务器地址",
                qconfig=Config,
                configItem=Config.notify_SMTPServerAddress,
                parent=self,
            )
            self.card_FromAddress = LineEditSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="发信邮箱地址",
                content="发送通知的邮箱地址",
                text="请输入发信邮箱地址",
                qconfig=Config,
                configItem=Config.notify_FromAddress,
                parent=self,
            )
            self.card_AuthorizationCode = PasswordLineEditSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="发信邮箱授权码",
                content="发送通知的邮箱授权码",
                text="请输入发信邮箱授权码",
                algorithm="DPAPI",
                qconfig=Config,
                configItem=Config.notify_AuthorizationCode,
                parent=self,
            )
            self.card_ToAddress = LineEditSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="收信邮箱地址",
                content="接收通知的邮箱地址",
                text="请输入收信邮箱地址",
                qconfig=Config,
                configItem=Config.notify_ToAddress,
                parent=self,
            )

            widget = QWidget()
            Layout = QVBoxLayout(widget)
            Layout.addWidget(self.card_IfSendMail)
            Layout.addWidget(self.card_SMTPServerAddress)
            Layout.addWidget(self.card_FromAddress)
            Layout.addWidget(self.card_AuthorizationCode)
            Layout.addWidget(self.card_ToAddress)
            self.viewLayout.setContentsMargins(0, 0, 0, 0)
            self.viewLayout.setSpacing(0)
            self.addGroupWidget(widget)

    class ServerChanSettingCard(ExpandGroupSettingCard):
        def __init__(self, parent=None):
            super().__init__(
                FluentIcon.SETTING,
                "推送ServerChan通知",
                "ServerChan通知推送渠道",
                parent,
            )

            self.card_IfServerChan = SwitchSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="推送SeverChan通知",
                content="是否启用SeverChan通知功能",
                qconfig=Config,
                configItem=Config.notify_IfServerChan,
                parent=self,
            )
            self.card_ServerChanKey = LineEditSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="SendKey",
                content="Server酱的SendKey（SC3与SCT都可以）",
                text="请输入SendKey",
                qconfig=Config,
                configItem=Config.notify_ServerChanKey,
                parent=self,
            )
            self.card_ServerChanChannel = LineEditSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="ServerChanChannel代码",
                content="可以留空，留空则默认。可以多个，请使用「|」隔开",
                text="请输入需要推送的Channel代码（SCT生效）",
                qconfig=Config,
                configItem=Config.notify_ServerChanChannel,
                parent=self,
            )
            self.card_ServerChanTag = LineEditSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="Tag内容",
                content="可以留空，留空则默认。可以多个，请使用「|」隔开",
                text="请输入加入推送的Tag（SC3生效）",
                qconfig=Config,
                configItem=Config.notify_ServerChanTag,
                parent=self,
            )

            widget = QWidget()
            Layout = QVBoxLayout(widget)
            Layout.addWidget(self.card_IfServerChan)
            Layout.addWidget(self.card_ServerChanKey)
            Layout.addWidget(self.card_ServerChanChannel)
            Layout.addWidget(self.card_ServerChanTag)
            self.viewLayout.setContentsMargins(0, 0, 0, 0)
            self.viewLayout.setSpacing(0)
            self.addGroupWidget(widget)

    class CompanyWechatPushSettingCard(ExpandGroupSettingCard):
        def __init__(self, parent=None):
            super().__init__(
                FluentIcon.SETTING,
                "推送企业微信机器人通知",
                "企业微信机器人Webhook通知推送渠道",
                parent,
            )

            self.card_IfCompanyWechat = SwitchSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="推送企业微信机器人通知",
                content="是否启用企业微信机器人通知功能",
                qconfig=Config,
                configItem=Config.notify_IfCompanyWebHookBot,
                parent=self,
            )
            self.card_CompanyWebHookBotUrl = LineEditSettingCard(
                icon=FluentIcon.PAGE_RIGHT,
                title="WebhookUrl",
                content="企业微信群机器人的Webhook地址",
                text="请输入Webhook的Url",
                qconfig=Config,
                configItem=Config.notify_CompanyWebHookBotUrl,
                parent=self,
            )

            widget = QWidget()
            Layout = QVBoxLayout(widget)
            Layout.addWidget(self.card_IfCompanyWechat)
            Layout.addWidget(self.card_CompanyWebHookBotUrl)
            self.viewLayout.setContentsMargins(0, 0, 0, 0)
            self.viewLayout.setSpacing(0)
            self.addGroupWidget(widget)


class SecuritySettingCard(HeaderCardWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("安全")

        self.card_changePASSWORD = PushSettingCard(
            text="修改",
            icon=FluentIcon.VPN,
            title="修改管理密钥",
            content="修改用于解密用户密码的管理密钥",
            parent=self,
        )
        self.card_resetPASSWORD = PushSettingCard(
            text="重置",
            icon=FluentIcon.VPN,
            title="重置管理密钥",
            content="重置用于解密用户密码的管理密钥",
            parent=self,
        )

        Layout = QVBoxLayout()
        Layout.addWidget(self.card_changePASSWORD)
        Layout.addWidget(self.card_resetPASSWORD)
        self.viewLayout.addLayout(Layout)


class UpdaterSettingCard(HeaderCardWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("更新")

        self.card_CheckUpdate = PushSettingCard(
            text="检查更新",
            icon=FluentIcon.UPDATE,
            title="获取最新版本",
            content="检查AUTO_MAA是否有新版本",
            parent=self,
        )
        self.card_IfAutoUpdate = SwitchSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="自动检查更新",
            content="将在启动时自动检查AUTO_MAA是否有新版本",
            qconfig=Config,
            configItem=Config.update_IfAutoUpdate,
            parent=self,
        )
        self.card_UpdateType = ComboBoxSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="版本更新类别",
            content="选择AUTO_MAA的更新类别",
            texts=["稳定版", "公测版"],
            qconfig=Config,
            configItem=Config.update_UpdateType,
            parent=self,
        )
        self.card_ThreadNumb = RangeSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="下载器线程数",
            content="更新器的下载线程数，建议仅在下载速度较慢时适量拉高",
            qconfig=Config,
            configItem=Config.update_ThreadNumb,
            parent=self,
        )
        self.card_ProxyAddress = LineEditSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="网络代理地址",
            content="使用网络代理软件时，若出现网络连接问题，请尝试设置代理地址，此设置全局生效",
            text="请输入代理地址",
            qconfig=Config,
            configItem=Config.update_ProxyAddress,
            parent=self,
        )
        self.card_ProxyUrlList = UrlListSettingCard(
            icon=FluentIcon.SETTING,
            title="代理地址列表",
            content="更新器代理地址列表",
            qconfig=Config,
            configItem=Config.update_ProxyUrlList,
            parent=self,
        )
        self.card_MirrorChyanCDK = PasswordLineEditSettingCard(
            icon=FluentIcon.PAGE_RIGHT,
            title="Mirror酱CDK",
            content="填写后改为使用由Mirror酱提供的下载服务",
            text="请输入Mirror酱CDK",
            algorithm="DPAPI",
            qconfig=Config,
            configItem=Config.update_MirrorChyanCDK,
            parent=self,
        )
        mirrorchyan_url = HyperlinkButton(
            "https://mirrorchyan.com/zh/get-start?source=auto_maa-setting_card",
            "获取Mirror酱CDK",
            self,
        )
        self.card_MirrorChyanCDK.hBoxLayout.insertWidget(
            5, mirrorchyan_url, 0, Qt.AlignRight
        )

        Layout = QVBoxLayout()
        Layout.addWidget(self.card_CheckUpdate)
        Layout.addWidget(self.card_IfAutoUpdate)
        Layout.addWidget(self.card_UpdateType)
        Layout.addWidget(self.card_ThreadNumb)
        Layout.addWidget(self.card_ProxyAddress)
        Layout.addWidget(self.card_ProxyUrlList)
        Layout.addWidget(self.card_MirrorChyanCDK)
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
            parent=self,
        )
        self.card_UserDocs = HyperlinkCard(
            url="https://clozya.github.io/AUTOMAA_docs",
            text="查看指南",
            icon=FluentIcon.PAGE_RIGHT,
            title="用户指南",
            content="访问AUTO_MAA的官方文档站，获取使用指南和项目相关信息",
            parent=self,
        )
        self.card_Association = self.AssociationSettingCard(self)

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
                parent=self,
            )
            self.card_QQGroup = HyperlinkCard(
                url="https://qm.qq.com/q/bd9fISNoME",
                text="加入官方QQ交流群",
                icon=FluentIcon.CHAT,
                title="QQ群",
                content="与AUTO_MAA开发者和用户交流",
                parent=self,
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

    while len(version_numb) < 4:
        version_numb.append(0)

    if version_numb[3] == 0:
        version = f"v{'.'.join(str(_) for _ in version_numb[0:3])}"
    else:
        version = (
            f"v{'.'.join(str(_) for _ in version_numb[0:3])}-beta.{version_numb[3]}"
        )
    return version


def version_info_markdown(info: dict) -> str:
    """将版本信息字典转为markdown信息"""

    version_info = ""
    for key, value in info.items():
        version_info += f"### {key}\n\n"
        for v in value:
            version_info += f"- {v}\n\n"
    return version_info
