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
AUTO_MAA网络请求线程
v4.4
作者：DLmaster_361
"""

from PySide6.QtCore import QObject, QThread, QEventLoop
import re
import time
import requests
import truststore
from pathlib import Path

from .logger import logger


class NetworkThread(QThread):
    """网络请求线程类"""

    max_retries = 3
    timeout = 10
    backoff_factor = 0.1

    def __init__(self, mode: str, url: str, path: Path = None) -> None:
        super().__init__()

        self.setObjectName(
            f"NetworkThread-{mode}-{re.sub(r'(&cdk=)[^&]+(&)', r'\1******\2', url)}"
        )

        logger.info(f"创建网络请求线程: {self.objectName()}", module="网络请求子线程")

        self.mode = mode
        self.url = url
        self.path = path

        from .config import Config

        self.proxies = {
            "http": Config.get(Config.update_ProxyAddress),
            "https": Config.get(Config.update_ProxyAddress),
        }

        self.status_code = None
        self.response_json = None
        self.error_message = None

        self.loop = QEventLoop()

        truststore.inject_into_ssl()  # 信任系统证书

    @logger.catch
    def run(self) -> None:
        """运行网络请求线程"""

        if self.mode == "get":
            self.get_json(self.url)
        elif self.mode == "get_file":
            self.get_file(self.url, self.path)

    def get_json(self, url: str) -> None:
        """
        通过get方法获取json数据

        :param url: 请求的URL
        """

        logger.info(f"子线程 {self.objectName()} 开始网络请求", module="网络请求子线程")

        response = None

        for _ in range(self.max_retries):
            try:
                response = requests.get(url, timeout=self.timeout, proxies=self.proxies)
                self.status_code = response.status_code
                self.response_json = response.json()
                self.error_message = None
                break
            except Exception as e:
                self.status_code = response.status_code if response else None
                self.response_json = None
                self.error_message = str(e)
                logger.exception(
                    f"子线程 {self.objectName()} 网络请求失败：{e}",
                    module="网络请求子线程",
                )
                time.sleep(self.backoff_factor)

        self.loop.quit()

    def get_file(self, url: str, path: Path) -> None:
        """
        通过get方法下载文件到指定路径

        :param url: 请求的URL
        :param path: 下载文件的保存路径
        """

        logger.info(f"子线程 {self.objectName()} 开始下载文件", module="网络请求子线程")

        response = None

        try:
            response = requests.get(url, timeout=10, proxies=self.proxies)
            if response.status_code == 200:
                with open(path, "wb") as file:
                    file.write(response.content)
                self.status_code = response.status_code
            else:
                self.status_code = response.status_code
                self.error_message = "下载失败"

        except Exception as e:
            self.status_code = response.status_code if response else None
            self.error_message = str(e)
            logger.exception(
                f"子线程 {self.objectName()} 网络请求失败：{e}", module="网络请求子线程"
            )

        self.loop.quit()


class _Network(QObject):
    """网络请求线程管理类"""

    def __init__(self) -> None:
        super().__init__()

        self.task_queue = []

    def add_task(self, mode: str, url: str, path: Path = None) -> NetworkThread:
        """
        添加网络请求任务

        :param mode: 请求模式，支持 "get", "get_file"
        :param url: 请求的URL
        :param path: 下载文件的保存路径，仅在 mode 为 "get_file" 时有效
        :return: 返回创建的 NetworkThread 实例
        """

        logger.info(f"添加网络请求任务: {mode} {url} {path}", module="网络请求")

        network_thread = NetworkThread(mode, url, path)

        self.task_queue.append(network_thread)

        network_thread.start()

        return network_thread

    def get_result(self, network_thread: NetworkThread) -> dict:
        """
        获取网络请求结果

        :param network_thread: 网络请求线程实例
        :return: 包含状态码、响应JSON和错误信息的字典
        """

        result = {
            "status_code": network_thread.status_code,
            "response_json": network_thread.response_json,
            "error_message": (
                re.sub(r"(&cdk=)[^&]+(&)", r"\1******\2", network_thread.error_message)
                if network_thread.error_message
                else None
            ),
        }

        network_thread.quit()
        network_thread.wait()
        self.task_queue.remove(network_thread)
        network_thread.deleteLater()

        logger.info(
            f"网络请求结果: {result['status_code']}，请求子线程已结束",
            module="网络请求",
        )

        return result


Network = _Network()
