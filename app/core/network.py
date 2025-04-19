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
AUTO_MAA网络请求线程
v4.3
作者：DLmaster_361
"""

from loguru import logger
from PySide6.QtCore import QThread, QEventLoop, QTimer
import time
import requests
from pathlib import Path


class _Network(QThread):

    max_retries = 3
    timeout = 10
    backoff_factor = 0.1

    def __init__(self) -> None:
        super().__init__()

        self.if_running = False
        self.mode = None
        self.url = None
        self.loop = QEventLoop()
        self.wait_loop = QEventLoop()

    @logger.catch
    def run(self) -> None:
        """运行网络请求线程"""

        self.if_running = True

        print(self.url)

        if self.mode == "get":
            self.get_json(self.url)
        elif self.mode == "get_file":
            self.get_file(self.url, self.path)

        self.if_running = False

    def set_info(self, mode: str, url: str, path: Path = None) -> None:
        """设置网络请求信息"""

        while self.if_running:
            QTimer.singleShot(self.backoff_factor * 1000, self.wait_loop.quit)
            self.wait_loop.exec()

        self.mode = mode
        self.url = url
        self.path = path

        self.stutus_code = None
        self.response_json = None
        self.error_message = None

    def get_json(self, url: str) -> None:
        """通过get方法获取json数据"""

        for _ in range(self.max_retries):
            try:
                response = requests.get(url, timeout=self.timeout)
                self.stutus_code = response.status_code
                self.response_json = response.json()
                self.error_message = None
                break
            except Exception as e:
                self.stutus_code = response.status_code if response else None
                self.response_json = None
                self.error_message = str(e)
                time.sleep(self.backoff_factor)

        self.loop.quit()
        print("quited")

    def get_file(self, url: str, path: Path) -> None:
        """通过get方法获取json数据"""

        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                with open(path, "wb") as file:
                    file.write(response.content)
                self.stutus_code = response.status_code
            else:
                self.stutus_code = response.status_code
                self.error_message = "下载失败"

        except Exception as e:
            self.stutus_code = response.status_code if response else None
            self.error_message = str(e)

        self.loop.quit()
        print("quited-----")


Network = _Network()
