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
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSpacerItem,
    QSizePolicy,
    QFileDialog,
)
from PySide6.QtCore import Qt, QSize, QUrl
from PySide6.QtGui import QDesktopServices, QColor
from qfluentwidgets import FluentIcon, ScrollArea, SimpleCardWidget, PrimaryToolButton
import shutil
import requests
import json
import time
from datetime import datetime
from pathlib import Path

from app.core import Config, MainInfoBar
from .Widget import Banner, IconButton


class Home(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("主页")

        self.banner = Banner()
        self.banner.set_percentage_size(
            0.8, 0.5
        )  # 设置 Banner 大小为窗口的 80% 宽度和 50% 高度

        v_layout = QVBoxLayout(self.banner)
        v_layout.setContentsMargins(0, 0, 0, 15)
        v_layout.setSpacing(5)
        v_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 空白占位符
        v_layout.addItem(
            QSpacerItem(10, 20, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        )

        # 顶部部分 (按钮组)
        h1_layout = QHBoxLayout()
        h1_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 左边留白区域
        h1_layout.addStretch()

        # 按钮组
        buttonGroup = ButtonGroup()
        buttonGroup.setMaximumHeight(320)
        h1_layout.addWidget(buttonGroup)

        # 空白占位符
        h1_layout.addItem(
            QSpacerItem(20, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        )

        # 将顶部水平布局添加到垂直布局
        v_layout.addLayout(h1_layout)

        # 中间留白区域
        v_layout.addItem(
            QSpacerItem(10, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        )
        v_layout.addStretch()

        # 中间留白区域
        v_layout.addItem(
            QSpacerItem(10, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        )
        v_layout.addStretch()

        # 底部部分 (图片切换按钮)
        h2_layout = QHBoxLayout()
        h2_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 左边留白区域
        h2_layout.addItem(
            QSpacerItem(20, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        )

        # # 公告卡片
        # noticeCard = NoticeCard()
        # h2_layout.addWidget(noticeCard)

        h2_layout.addStretch()

        # 自定义图像按钮布局
        self.imageButton = PrimaryToolButton(FluentIcon.IMAGE_EXPORT)
        self.imageButton.setFixedSize(56, 56)
        self.imageButton.setIconSize(QSize(32, 32))
        self.imageButton.clicked.connect(self.get_home_image)

        v1_layout = QVBoxLayout()
        v1_layout.addWidget(self.imageButton, alignment=Qt.AlignmentFlag.AlignBottom)

        h2_layout.addLayout(v1_layout)

        # 空白占位符
        h2_layout.addItem(
            QSpacerItem(25, 10, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        )

        # 将底部水平布局添加到垂直布局
        v_layout.addLayout(h2_layout)

        layout = QVBoxLayout()
        scrollArea = ScrollArea()
        scrollArea.setWidgetResizable(True)
        scrollArea.setWidget(self.banner)
        layout.addWidget(scrollArea)
        self.setLayout(layout)

        self.set_banner()

    def get_home_image(self) -> None:
        """获取主页图片"""

        if (
            Config.global_config.get(Config.global_config.function_HomeImageMode)
            == "默认"
        ):
            pass
        elif (
            Config.global_config.get(Config.global_config.function_HomeImageMode)
            == "自定义"
        ):

            file_path, _ = QFileDialog.getOpenFileName(
                self, "打开自定义主页图片", "", "图片文件 (*.png *.jpg *.bmp)"
            )
            if file_path:

                for file in Config.app_path.glob(
                    "resources/images/Home/BannerCustomize.*"
                ):
                    file.unlink()

                shutil.copy(
                    file_path,
                    Config.app_path
                    / f"resources/images/Home/BannerCustomize{Path(file_path).suffix}",
                )

                logger.info(f"自定义主页图片更换成功：{file_path}")
                MainInfoBar.push_info_bar(
                    "success",
                    "主页图片更换成功",
                    "自定义主页图片更换成功！",
                    3000,
                )

            else:
                logger.warning("自定义主页图片更换失败：未选择图片文件")
                MainInfoBar.push_info_bar(
                    "warning",
                    "主页图片更换失败",
                    "未选择图片文件！",
                    5000,
                )
        elif (
            Config.global_config.get(Config.global_config.function_HomeImageMode)
            == "主题图像"
        ):

            # 从远程服务器获取最新主题图像
            for _ in range(3):
                try:
                    response = requests.get(
                        "https://gitee.com/DLmaster_361/AUTO_MAA/raw/server/theme_image.json"
                    )
                    theme_image = response.json()
                    break
                except Exception as e:
                    err = e
                    time.sleep(0.1)
            else:
                logger.error(f"获取最新主题图像时出错：\n{err}")
                MainInfoBar.push_info_bar(
                    "error",
                    "主题图像获取失败",
                    f"获取最新主题图像信息时出错：\n{err}",
                    -1,
                )
                return None

            if (Config.app_path / "resources/theme_image.json").exists():
                with (Config.app_path / "resources/theme_image.json").open(
                    mode="r", encoding="utf-8"
                ) as f:
                    theme_image_local = json.load(f)
                time_local = datetime.strptime(
                    theme_image_local["time"], "%Y-%m-%d %H:%M"
                )
            else:
                time_local = datetime.strptime("2000-01-01 00:00", "%Y-%m-%d %H:%M")

            if not (
                Config.app_path / "resources/images/Home/BannerTheme.jpg"
            ).exists() or (
                datetime.now()
                > datetime.strptime(theme_image["time"], "%Y-%m-%d %H:%M")
                and datetime.strptime(theme_image["time"], "%Y-%m-%d %H:%M")
                > time_local
            ):

                response = requests.get(theme_image["url"])
                if response.status_code == 200:

                    with open(
                        Config.app_path / "resources/images/Home/BannerTheme.jpg", "wb"
                    ) as file:
                        file.write(response.content)

                    logger.info("主题图像下载成功")
                    MainInfoBar.push_info_bar(
                        "success",
                        "主题图像下载成功",
                        "主题图像下载成功！",
                        3000,
                    )

                else:

                    logger.error("主题图像下载失败")
                    MainInfoBar.push_info_bar(
                        "error",
                        "主题图像下载失败",
                        f"主题图像下载失败：{response.status_code}",
                        -1,
                    )

                with (Config.app_path / "resources/theme_image.json").open(
                    mode="w", encoding="utf-8"
                ) as f:
                    json.dump(theme_image, f, ensure_ascii=False, indent=4)

            else:

                logger.info("主题图像已是最新")
                MainInfoBar.push_info_bar(
                    "info",
                    "主题图像已是最新",
                    "主题图像已是最新！",
                    3000,
                )

        self.set_banner()

    def set_banner(self):
        """设置主页图像"""
        if (
            Config.global_config.get(Config.global_config.function_HomeImageMode)
            == "默认"
        ):
            self.banner.set_banner_image(
                str(Config.app_path / "resources/images/Home/BannerDefault.png")
            )
            self.imageButton.hide()
        elif (
            Config.global_config.get(Config.global_config.function_HomeImageMode)
            == "自定义"
        ):
            for file in Config.app_path.glob("resources/images/Home/BannerCustomize.*"):
                self.banner.set_banner_image(str(file))
                break
            self.imageButton.show()
        elif (
            Config.global_config.get(Config.global_config.function_HomeImageMode)
            == "主题图像"
        ):
            self.banner.set_banner_image(
                str(Config.app_path / "resources/images/Home/BannerTheme.jpg")
            )
            self.imageButton.show()


class ButtonGroup(SimpleCardWidget):
    """显示主页和 GitHub 按钮的竖直按钮组"""

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setFixedSize(56, 180)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 创建主页按钮
        home_button = IconButton(
            FluentIcon.HOME.icon(color=QColor("#fff")),
            tip_title="AUTO_MAA官网",
            tip_content="AUTO_MAA官方文档站",
            isTooltip=True,
        )
        home_button.setIconSize(QSize(32, 32))
        home_button.clicked.connect(self.open_home)
        layout.addWidget(home_button)

        # 创建 GitHub 按钮
        github_button = IconButton(
            FluentIcon.GITHUB.icon(color=QColor("#fff")),
            tip_title="Github仓库",
            tip_content="如果本项目有帮助到您~\n不妨给项目点一个Star⭐",
            isTooltip=True,
        )
        github_button.setIconSize(QSize(32, 32))
        github_button.clicked.connect(self.open_github)
        layout.addWidget(github_button)

        # # 创建 文档 按钮
        # doc_button = IconButton(
        #     FluentIcon.DICTIONARY.icon(color=QColor("#fff")),
        #     tip_title="自助排障文档",
        #     tip_content="点击打开自助排障文档,好孩子都能看懂",
        #     isTooltip=True,
        # )
        # doc_button.setIconSize(QSize(32, 32))
        # doc_button.clicked.connect(self.open_doc)
        # layout.addWidget(doc_button)

        # 创建 Q群 按钮
        doc_button = IconButton(
            FluentIcon.CHAT.icon(color=QColor("#fff")),
            tip_title="官方社群",
            tip_content="加入官方群聊【AUTO_MAA绝赞DeBug中！】",
            isTooltip=True,
        )
        doc_button.setIconSize(QSize(32, 32))
        doc_button.clicked.connect(self.open_chat)
        layout.addWidget(doc_button)

        # 创建 官方店铺 按钮 (当然没有)
        doc_button = IconButton(
            FluentIcon.SHOPPING_CART.icon(color=QColor("#fff")),
            tip_title="官方店铺",
            tip_content="暂时没有官方店铺，但是可以加入官方群聊哦~",
            isTooltip=True,
        )
        doc_button.setIconSize(QSize(32, 32))
        doc_button.clicked.connect(self.open_sales)
        layout.addWidget(doc_button)

    def _normalBackgroundColor(self):
        return QColor(0, 0, 0, 96)

    def open_home(self):
        """打开主页链接"""
        QDesktopServices.openUrl(QUrl("https://clozya.github.io/AUTOMAA_docs"))

    def open_github(self):
        """打开 GitHub 链接"""
        QDesktopServices.openUrl(QUrl("https://github.com/DLmaster361/AUTO_MAA"))

    def open_chat(self):
        """打开 Q群 链接"""
        QDesktopServices.openUrl(QUrl("https://qm.qq.com/q/bd9fISNoME"))

    def open_doc(self):
        """打开 文档 链接"""
        QDesktopServices.openUrl(QUrl("https://clozya.github.io/AUTOMAA_docs"))

    def open_sales(self):
        """其实还是打开 Q群 链接"""
        QDesktopServices.openUrl(QUrl("https://qm.qq.com/q/bd9fISNoME"))
