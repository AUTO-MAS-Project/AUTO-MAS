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
v1.1
作者：DLmaster_361
"""

import os
import sys
import json
import zipfile
import requests
import subprocess
import time
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QVBoxLayout,
)
from qfluentwidgets import ProgressBar, BodyLabel
from PySide6.QtGui import QIcon
from PySide6.QtCore import QObject, QThread, Signal

from .version import version_text


class UpdateProcess(QThread):

    info = Signal(str)
    progress = Signal(int, int, int)
    accomplish = Signal()

    def __init__(
        self, app_path: Path, name: str, main_version: list, updater_version: list
    ) -> None:
        super(UpdateProcess, self).__init__()

        self.app_path = app_path
        self.name = name
        self.main_version = main_version
        self.updater_version = updater_version
        self.download_path = app_path / "AUTO_MAA_Update.zip"  #  临时下载文件的路径
        self.version_path = app_path / "resources/version.json"

    def run(self) -> None:

        # 清理可能存在的临时文件
        try:
            os.remove(self.download_path)
        except FileNotFoundError:
            pass

        self.info.emit("正在获取下载链接")
        url_list = self.get_download_url()

        # 验证下载地址并获取文件大小
        for i in range(len(url_list)):
            try:
                self.info.emit(f"正在验证下载地址：{url_list[i]}")
                response = requests.get(url_list[i], stream=True)
                if response.status_code != 200:
                    self.info.emit(
                        f"连接失败，错误代码 {response.status_code} ，正在切换代理（{i+1}/{len(url_list)}）"
                    )
                    time.sleep(1)
                    continue
                file_size = response.headers.get("Content-Length")
                break
            except requests.RequestException:
                self.info.emit(f"请求超时，正在切换代理（{i+1}/{len(url_list)}）")
                time.sleep(1)
        else:
            self.info.emit(f"连接失败，已尝试所有{len(url_list)}个代理")
            return None

        if file_size is None:
            file_size = 1
        else:
            file_size = int(file_size)

        try:
            # 下载文件
            with open(self.download_path, "wb") as f:

                downloaded_size = 0
                last_download_size = 0
                speed = 0
                last_time = time.time()

                for chunk in response.iter_content(chunk_size=8192):

                    # 写入已下载数据
                    f.write(chunk)
                    downloaded_size += len(chunk)

                    # 计算下载速度
                    if time.time() - last_time >= 1.0:
                        speed = (
                            (downloaded_size - last_download_size)
                            / (time.time() - last_time)
                            / 1024
                        )
                        last_download_size = downloaded_size
                        last_time = time.time()

                    # 更新下载进度
                    if speed >= 1024:
                        self.info.emit(
                            f"正在下载：{self.name} 已下载：{downloaded_size / 1048576:.2f}/{file_size / 1048576:.2f} MB （{downloaded_size / file_size * 100:.2f}%） 下载速度：{speed / 1024:.2f} MB/s",
                        )
                    else:
                        self.info.emit(
                            f"正在下载：{self.name} 已下载：{downloaded_size / 1048576:.2f}/{file_size / 1048576:.2f} MB （{downloaded_size / file_size * 100:.2f}%） 下载速度：{speed:.2f} KB/s",
                        )
                    self.progress.emit(0, 100, int(downloaded_size / file_size * 100))

        except Exception as e:
            e = str(e)
            e = "\n".join([e[_ : _ + 75] for _ in range(0, len(e), 75)])
            self.info.emit(f"下载{self.name}时出错：\n{e}")
            return None

        # 解压
        try:

            while True:
                try:
                    self.info.emit("正在解压更新文件")
                    self.progress.emit(0, 0, 0)
                    with zipfile.ZipFile(self.download_path, "r") as zip_ref:
                        zip_ref.extractall(self.app_path)
                    break
                except PermissionError:
                    self.info.emit("解压出错：AUTO_MAA正在运行，正在等待其关闭")
                    time.sleep(1)

            self.info.emit("正在删除临时文件")
            self.progress.emit(0, 0, 0)
            os.remove(self.download_path)

            self.info.emit(f"{self.name}更新成功！")
            self.progress.emit(0, 100, 100)

        except Exception as e:

            e = str(e)
            e = "\n".join([e[_ : _ + 75] for _ in range(0, len(e), 75)])
            self.info.emit(f"解压更新时出错：\n{e}")
            return None

        # 更新version文件
        with open(self.version_path, "r", encoding="utf-8") as f:
            version_info = json.load(f)
        if self.name == "AUTO_MAA更新器":
            version_info["updater_version"] = ".".join(map(str, self.updater_version))
        elif self.name == "AUTO_MAA主程序":
            version_info["main_version"] = ".".join(map(str, self.main_version))
        with open(self.version_path, "w", encoding="utf-8") as f:
            json.dump(version_info, f, indent=4)

        # 主程序更新完成后打开AUTO_MAA
        if self.name == "AUTO_MAA主程序":
            subprocess.Popen(
                str(self.app_path / "AUTO_MAA.exe"),
                shell=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

        self.accomplish.emit()

    def get_download_url(self) -> list:
        """获取下载链接"""

        try_num = 3
        for i in range(try_num):
            try:
                response = requests.get(
                    "https://gitee.com/DLmaster_361/AUTO_MAA/raw/main/resources/version.json"
                )
                if response.status_code != 200:
                    self.info.emit(
                        f"连接失败，错误代码 {response.status_code} ，正在重试（{i+1}/{try_num}）"
                    )
                    time.sleep(0.1)
                    continue
                version_remote = response.json()
                PROXY_list = version_remote["proxy_list"]
                break
            except requests.RequestException:
                self.info.emit(f"请求超时，正在重试（{i+1}/{try_num}）")
                time.sleep(0.1)
            except KeyError:
                self.info.emit(f"未找到远端代理网址项，正在重试（{i+1}/{try_num}）")
                time.sleep(0.1)
        else:
            self.info.emit("获取远端代理信息失败，将使用默认代理地址")
            PROXY_list = [
                "",
                "https://gitproxy.click/",
                "https://cdn.moran233.xyz/",
                "https://gh.llkk.cc/",
                "https://github.akams.cn/",
                "https://www.ghproxy.cn/",
                "https://ghp.ci/",
            ]
            time.sleep(1)

        url_list = []
        if self.name == "AUTO_MAA主程序":
            url_list.append(
                f"https://gitee.com/DLmaster_361/AUTO_MAA/releases/download/{version_text(self.main_version)}/AUTO_MAA_{version_text(self.main_version)}.zip"
            )
            for i in range(len(PROXY_list)):
                url_list.append(
                    f"{PROXY_list[i]}https://github.com/DLmaster361/AUTO_MAA/releases/download/{version_text(self.main_version)}/AUTO_MAA_{version_text(self.main_version)}.zip"
                )
        elif self.name == "AUTO_MAA更新器":
            url_list.append(
                f"https://gitee.com/DLmaster_361/AUTO_MAA/releases/download/{version_text(self.main_version)}/Updater_{version_text(self.updater_version)}.zip"
            )
            for i in range(len(PROXY_list)):
                url_list.append(
                    f"{PROXY_list[i]}https://github.com/DLmaster361/AUTO_MAA/releases/download/{version_text(self.main_version)}/Updater_{version_text(self.updater_version)}.zip"
                )
        return url_list


class Updater(QObject):

    def __init__(
        self, app_path: Path, name: str, main_version: list, updater_version: list
    ) -> None:
        super().__init__()

        self.ui = QDialog()
        self.ui.setWindowTitle("AUTO_MAA更新器")
        self.ui.resize(700, 70)
        self.ui.setWindowIcon(
            QIcon(str(app_path / "resources/icons/AUTO_MAA_Updater.ico"))
        )

        # 创建垂直布局
        self.Layout_v = QVBoxLayout(self.ui)

        self.info = BodyLabel("正在初始化", self.ui)
        self.Layout_v.addWidget(self.info)

        self.progress = ProgressBar(self.ui)
        self.progress.setRange(0, 0)
        self.Layout_v.addWidget(self.progress)

        self.update_process = UpdateProcess(
            app_path, name, main_version, updater_version
        )

        self.update_process.info.connect(self.update_info)
        self.update_process.progress.connect(self.update_progress)

        self.update_process.start()

    def update_info(self, text: str) -> None:
        self.info.setText(text)

    def update_progress(self, begin: int, end: int, current: int) -> None:
        self.progress.setRange(begin, end)
        self.progress.setValue(current)


class AUTO_MAA_Updater(QApplication):
    def __init__(
        self, app_path: Path, name: str, main_version: list, updater_version: list
    ) -> None:
        super().__init__()

        self.main = Updater(app_path, name, main_version, updater_version)
        self.main.ui.show()


if __name__ == "__main__":

    # 获取软件自身的路径
    app_path = Path.cwd()

    # 从本地版本信息文件获取当前版本信息
    if (app_path / "resources/version.json").exists():
        with (app_path / "resources/version.json").open(
            mode="r", encoding="utf-8"
        ) as f:
            version_current = json.load(f)
        main_version_current = list(
            map(int, version_current["main_version"].split("."))
        )
    else:
        main_version_current = [0, 0, 0, 0]

    # 从远程服务器获取最新版本信息
    for _ in range(3):
        try:
            response = requests.get(
                "https://gitee.com/DLmaster_361/AUTO_MAA/raw/main/resources/version.json"
            )
            version_remote = response.json()
            main_version_remote = list(
                map(int, version_remote["main_version"].split("."))
            )
            break
        except Exception as e:
            err = e
            time.sleep(0.1)
    else:
        sys.exit(f"获取版本信息时出错：\n{err}")

    # 启动更新线程
    if main_version_remote > main_version_current:
        app = AUTO_MAA_Updater(
            app_path,
            "AUTO_MAA主程序",
            main_version_remote,
            [],
        )
        sys.exit(app.exec())
