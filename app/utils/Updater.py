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

import sys
import json
import zipfile
import requests
import subprocess
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QHBoxLayout
from qfluentwidgets import (
    ProgressBar,
    IndeterminateProgressBar,
    BodyLabel,
    PushButton,
    EditableComboBox,
)
from PySide6.QtGui import QIcon, QCloseEvent
from PySide6.QtCore import QThread, Signal, QEventLoop


def version_text(version_numb: list) -> str:
    """将版本号列表转为可读的文本信息"""

    if version_numb[3] == 0:
        version = f"v{'.'.join(str(_) for _ in version_numb[0:3])}"
    else:
        version = (
            f"v{'.'.join(str(_) for _ in version_numb[0:3])}-beta.{version_numb[3]}"
        )
    return version


class UpdateProcess(QThread):

    info = Signal(str)
    progress = Signal(int, int, int)
    question = Signal(dict)
    question_response = Signal(str)
    accomplish = Signal()

    def __init__(
        self, app_path: Path, name: str, main_version: list, updater_version: list
    ) -> None:
        super(UpdateProcess, self).__init__()

        self.app_path = app_path
        self.name = name
        self.main_version = main_version
        self.updater_version = updater_version
        self.download_path = app_path / "DOWNLOAD_TEMP.zip"  #  临时下载文件的路径
        self.version_path = app_path / "resources/version.json"
        self.response = None

        self.question_response.connect(self._capture_response)

    def run(self) -> None:

        # 清理可能存在的临时文件
        if self.download_path.exists():
            self.download_path.unlink()

        self.info.emit("正在获取下载链接")
        url_list = self.get_download_url()
        url_dict = {}

        # 验证下载地址
        for i, url in enumerate(url_list):

            if self.isInterruptionRequested():
                return None

            self.progress.emit(0, len(url_list), i)

            try:
                self.info.emit(f"正在验证下载地址：{url}")
                response = requests.get(url, stream=True)
                if response.status_code != 200:
                    self.info.emit(f"连接失败，错误代码 {response.status_code}")
                    time.sleep(1)
                    continue
                url_dict[url] = response.elapsed.total_seconds()
            except requests.RequestException:
                self.info.emit(f"请求超时")
                time.sleep(1)

        download_url = self.push_question(url_dict)

        # 获取文件大小
        try:
            self.info.emit(f"正在连接下载地址：{download_url}")
            self.progress.emit(0, 0, 0)
            response = requests.get(download_url, stream=True)
            if response.status_code != 200:
                self.info.emit(f"连接失败，错误代码 {response.status_code}")
                return None
            file_size = response.headers.get("Content-Length")
        except requests.RequestException:
            self.info.emit(f"请求超时")
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

                    if self.isInterruptionRequested():
                        break

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

                if self.isInterruptionRequested() and self.download_path.exists():
                    self.download_path.unlink()
                    return None

        except Exception as e:
            e = str(e)
            e = "\n".join([e[_ : _ + 75] for _ in range(0, len(e), 75)])
            self.info.emit(f"下载{self.name}时出错：\n{e}")
            return None

        # 解压
        try:

            while True:
                if self.isInterruptionRequested():
                    self.download_path.unlink()
                    return None
                try:
                    self.info.emit("正在解压更新文件")
                    self.progress.emit(0, 0, 0)
                    with zipfile.ZipFile(self.download_path, "r") as zip_ref:
                        zip_ref.extractall(self.app_path)
                    break
                except PermissionError:
                    self.info.emit(f"解压出错：{self.name}正在运行，正在等待其关闭")
                    time.sleep(1)

            self.info.emit("正在删除临时文件")
            self.progress.emit(0, 0, 0)
            self.download_path.unlink()

            self.info.emit(f"{self.name}更新成功！")
            self.progress.emit(0, 100, 100)

        except Exception as e:

            e = str(e)
            e = "\n".join([e[_ : _ + 75] for _ in range(0, len(e), 75)])
            self.info.emit(f"解压更新时出错：\n{e}")
            return None

        # 更新version文件
        if not self.isInterruptionRequested and self.name in [
            "AUTO_MAA主程序",
            "AUTO_MAA更新器",
        ]:
            with open(self.version_path, "r", encoding="utf-8") as f:
                version_info = json.load(f)
            if self.name == "AUTO_MAA主程序":
                version_info["main_version"] = ".".join(map(str, self.main_version))
            elif self.name == "AUTO_MAA更新器":
                version_info["updater_version"] = ".".join(
                    map(str, self.updater_version)
                )
            with open(self.version_path, "w", encoding="utf-8") as f:
                json.dump(version_info, f, ensure_ascii=False, indent=4)

        # 主程序更新完成后打开AUTO_MAA
        if not self.isInterruptionRequested and self.name == "AUTO_MAA主程序":
            subprocess.Popen(
                str(self.app_path / "AUTO_MAA.exe"),
                shell=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        elif not self.isInterruptionRequested and self.name == "MAA":
            subprocess.Popen(
                str(self.app_path / "MAA.exe"),
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
                "https://ghfast.top/",
            ]
            time.sleep(1)

        url_list = []
        if self.name == "AUTO_MAA主程序":
            url_list.append(
                f"https://gitee.com/DLmaster_361/AUTO_MAA/releases/download/{version_text(self.main_version)}/AUTO_MAA_{version_text(self.main_version)}.zip"
            )
            url_list.append(
                f"https://jp-download.fearr.xyz/AUTO_MAA/AUTO_MAA_{version_text(self.main_version)}.zip"
            )
            for i in range(len(PROXY_list)):
                url_list.append(
                    f"{PROXY_list[i]}https://github.com/DLmaster361/AUTO_MAA/releases/download/{version_text(self.main_version)}/AUTO_MAA_{version_text(self.main_version)}.zip"
                )
        elif self.name == "AUTO_MAA更新器":
            url_list.append(
                f"https://gitee.com/DLmaster_361/AUTO_MAA/releases/download/{version_text(self.main_version)}/Updater_{version_text(self.updater_version)}.zip"
            )
            url_list.append(
                f"https://jp-download.fearr.xyz/AUTO_MAA/Updater_{version_text(self.updater_version)}.zip"
            )
            for i in range(len(PROXY_list)):
                url_list.append(
                    f"{PROXY_list[i]}https://github.com/DLmaster361/AUTO_MAA/releases/download/{version_text(self.main_version)}/Updater_{version_text(self.updater_version)}.zip"
                )
        elif self.name == "MAA":
            url_list.append(
                f"https://jp-download.fearr.xyz/MAA/MAA-{version_text(self.main_version)}-win-x64.zip"
            )
            for i in range(len(PROXY_list)):
                url_list.append(
                    f"{PROXY_list[i]}https://github.com/MaaAssistantArknights/MaaAssistantArknights/releases/download/{version_text(self.main_version)}/MAA-{version_text(self.main_version)}-win-x64.zip"
                )
        return url_list

    def push_question(self, url_dict: dict) -> str:
        self.question.emit(url_dict)
        loop = QEventLoop()
        self.question_response.connect(loop.quit)
        loop.exec()
        return self.response

    def _capture_response(self, response: str) -> None:
        self.response = response


class Updater(QDialog):

    def __init__(
        self, app_path: Path, name: str, main_version: list, updater_version: list
    ) -> None:
        super().__init__()

        self.setWindowTitle("AUTO_MAA更新器")
        self.setWindowIcon(
            QIcon(
                str(
                    Path(sys.argv[0]).resolve().parent
                    / "resources/icons/AUTO_MAA_Updater.ico"
                )
            )
        )

        # 创建垂直布局
        self.Layout = QVBoxLayout(self)

        self.info = BodyLabel("正在初始化", self)
        self.progress_1 = IndeterminateProgressBar(self)
        self.progress_2 = ProgressBar(self)
        self.combo_box = EditableComboBox(self)

        self.button = PushButton("继续", self)
        self.h_layout = QHBoxLayout()
        self.h_layout.addStretch(1)
        self.h_layout.addWidget(self.button)

        self.update_progress(0, 0, 0)

        self.Layout.addWidget(self.info)
        self.Layout.addStretch(1)
        self.Layout.addWidget(self.progress_1)
        self.Layout.addWidget(self.progress_2)
        self.Layout.addWidget(self.combo_box)
        self.Layout.addLayout(self.h_layout)
        self.Layout.addStretch(1)

        self.update_process = UpdateProcess(
            app_path, name, main_version, updater_version
        )

        self.update_process.info.connect(self.update_info)
        self.update_process.progress.connect(self.update_progress)
        self.update_process.question.connect(self.question)

        self.update_process.start()

    def update_info(self, text: str) -> None:
        self.info.setText(text)

    def update_progress(
        self, begin: int, end: int, current: int, if_show_combo_box: bool = False
    ) -> None:

        self.combo_box.setVisible(if_show_combo_box)
        self.button.setVisible(if_show_combo_box)

        if if_show_combo_box:
            self.progress_1.setVisible(False)
            self.progress_2.setVisible(False)
            self.resize(1000, 90)
        elif begin == 0 and end == 0:
            self.progress_2.setVisible(False)
            self.progress_1.setVisible(True)
            self.resize(700, 70)
        else:
            self.progress_1.setVisible(False)
            self.progress_2.setVisible(True)
            self.progress_2.setRange(begin, end)
            self.progress_2.setValue(current)
            self.resize(700, 70)

    def question(self, url_dict: dict) -> None:

        self.update_info("测速完成，请选择或自行输入一个合适下载地址：")
        self.update_progress(0, 0, 0, True)

        url_dict = dict(sorted(url_dict.items(), key=lambda item: item[1]))

        for url, time in url_dict.items():
            self.combo_box.addItem(f"{url} | 响应时间：{time:.3f}秒")

        self.button.clicked.connect(
            lambda: self.update_process.question_response.emit(
                self.combo_box.currentText().split(" | ")[0]
            )
        )

    def closeEvent(self, event: QCloseEvent):
        """清理残余进程"""

        self.update_process.requestInterruption()
        self.update_process.quit()
        self.update_process.wait()

        event.accept()


class AUTO_MAA_Updater(QApplication):
    def __init__(
        self, app_path: Path, name: str, main_version: list, updater_version: list
    ) -> None:
        super().__init__()

        self.main = Updater(app_path, name, main_version, updater_version)
        self.main.show()


if __name__ == "__main__":

    # 获取软件自身的路径
    app_path = Path(sys.argv[0]).resolve().parent

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

    # 从本地配置文件获取更新类型
    if (app_path / "config/config.json").exists():
        with (app_path / "config/config.json").open(mode="r", encoding="utf-8") as f:
            config = json.load(f)
        if "Update" in config and "UpdateType" in config["Update"]:
            update_type = config["Update"]["UpdateType"]
        else:
            update_type = "main"
    else:
        update_type = "main"

    # 从远程服务器获取最新版本信息
    for _ in range(3):
        try:
            response = requests.get(
                f"https://gitee.com/DLmaster_361/AUTO_MAA/raw/{update_type}/resources/version.json"
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
