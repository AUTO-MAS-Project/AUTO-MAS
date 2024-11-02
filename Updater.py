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
AUTO_MAA更新器
v1.0
作者：DLmaster_361
"""

import os
import sys
import json
import zipfile
import requests

from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QProgressBar,
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtUiTools import QUiLoader

uiLoader = QUiLoader()


class UpdateProcess(QThread):

    info = Signal(str)
    progress = Signal(int, int, int)
    accomplish = Signal()

    def __init__(self, app_path, name, download_url):
        super(UpdateProcess, self).__init__()

        self.app_path = app_path
        self.name = name
        self.download_url = download_url
        self.download_path = app_path + "/AUTO_MAA_Update.zip"  #  临时下载文件的路径
        self.version_path = app_path + "/res/version.json"

    def run(self):

        # 下载
        try:
            response = requests.get(self.download_url, stream=True)
            file_size = response.headers.get("Content-Length")
            if file_size is None:
                file_size = 1
            else:
                file_size = int(file_size)
            with open(self.download_path, "wb") as f:
                downloaded_size = 0
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    self.info.emit(
                        f"正在下载：{self.name} 已下载: {downloaded_size / 1048576:.2f}/{file_size / 1048576:.2f} MB ({downloaded_size / file_size * 100:.2f}%)"
                    )
                    self.progress.emit(0, 100, int(downloaded_size / file_size * 100))
        except Exception as e:
            self.info.emit(f"下载{self.name}时出错: {e}")
            return None
        # 解压
        try:
            self.info.emit("正在解压更新文件")
            self.progress.emit(0, 0, 0)
            with zipfile.ZipFile(self.download_path, "r") as zip_ref:
                zip_ref.extractall(self.app_path)

            self.info.emit("正在删除临时文件")
            self.progress.emit(0, 0, 0)
            os.remove(self.download_path)

            self.info.emit(f"{self.name}更新成功！")
            self.progress.emit(0, 100, 100)

        except Exception as e:
            self.info.emit(f"解压更新时出错: {e}")
        self.accomplish.emit()


class Updater(QObject):

    def __init__(self, app_path, name, download_url):
        super().__init__()

        self.ui = uiLoader.load(app_path + "/gui/ui/updater.ui")
        self.ui.setWindowTitle("AUTO_MAA更新器")
        self.ui.setWindowIcon(QIcon(app_path + "/res/AUTO_MAA.ico"))

        self.info = self.ui.findChild(QLabel, "label")
        self.info.setText("正在初始化")

        self.progress = self.ui.findChild(QProgressBar, "progressBar")
        self.progress.setRange(0, 0)

        self.update_process = UpdateProcess(app_path, name, download_url)

        self.update_process.info.connect(self.update_info)
        self.update_process.progress.connect(self.update_progress)

        self.update_process.start()

    def update_info(self, text):
        self.info.setText(text)

    def update_progress(self, begin, end, current):
        self.progress.setRange(begin, end)
        self.progress.setValue(current)


class AUTO_MAA_Updater(QApplication):
    def __init__(self, app_path, name, download_url):
        super().__init__()

        self.main = Updater(app_path, name, download_url)
        self.main.ui.show()


if __name__ == "__main__":
    # 获取软件自身的路径
    app_path = os.path.dirname(os.path.realpath(sys.argv[0])).replace("\\", "/")
    # 从本地版本信息文件获取当前版本信息
    with open(app_path + "/res/version.json", "r", encoding="utf-8") as f:
        version_current = json.load(f)
    main_version_current = list(map(int, version_current["main_version"].split(".")))
    # 从远程服务器获取最新版本信息
    response = requests.get(
        "https://ghp.ci/https://github.com/DLmaster361/AUTO_MAA/blob/Updater/res/version.json"
    )
    version_remote = response.json()
    main_version_remote = list(map(int, version_remote["main_version"].split(".")))

    if main_version_remote > main_version_current:
        app = AUTO_MAA_Updater(
            app_path, "AUTO_MAA主程序", version_remote["main_download_url"]
        )
        sys.exit(app.exec())
