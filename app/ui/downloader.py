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
AUTO_MAA更新器
v4.4
作者：DLmaster_361
"""

from loguru import logger
import zipfile
import requests
import subprocess
import time
import psutil
from functools import partial
from pathlib import Path

from PySide6.QtWidgets import QDialog, QVBoxLayout
from qfluentwidgets import (
    ProgressBar,
    IndeterminateProgressBar,
    BodyLabel,
    setTheme,
    Theme,
)
from PySide6.QtGui import QCloseEvent
from PySide6.QtCore import QThread, Signal, QTimer, QEventLoop

from typing import List, Dict, Union

from app.services import System


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


class DownloadProcess(QThread):
    """分段下载子线程"""

    progress = Signal(int)
    accomplish = Signal(float)

    def __init__(
        self,
        url: str,
        start_byte: int,
        end_byte: int,
        download_path: Path,
        check_times: int = -1,
    ) -> None:
        super(DownloadProcess, self).__init__()

        self.setObjectName(f"DownloadProcess-{url}-{start_byte}-{end_byte}")

        self.url = url
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.download_path = download_path
        self.check_times = check_times

    @logger.catch
    def run(self) -> None:

        # 清理可能存在的临时文件
        if self.download_path.exists():
            self.download_path.unlink()

        logger.info(
            f"开始下载：{self.url}，范围：{self.start_byte}-{self.end_byte}，存储地址：{self.download_path}"
        )

        headers = (
            {"Range": f"bytes={self.start_byte}-{self.end_byte}"}
            if not (self.start_byte == -1 or self.end_byte == -1)
            else None
        )

        while not self.isInterruptionRequested() and self.check_times != 0:

            try:

                start_time = time.time()

                response = requests.get(
                    self.url, headers=headers, timeout=10, stream=True
                )

                if response.status_code not in [200, 206]:

                    if self.check_times != -1:
                        self.check_times -= 1

                    logger.error(
                        f"连接失败：{self.url}，状态码：{response.status_code}，剩余重试次数：{self.check_times}"
                    )

                    time.sleep(1)
                    continue

                logger.info(f"连接成功：{self.url}，状态码：{response.status_code}")

                downloaded_size = 0
                with self.download_path.open(mode="wb") as f:

                    for chunk in response.iter_content(chunk_size=8192):

                        if self.isInterruptionRequested():
                            break

                        f.write(chunk)
                        downloaded_size += len(chunk)

                        self.progress.emit(downloaded_size)

                if self.isInterruptionRequested():

                    if self.download_path.exists():
                        self.download_path.unlink()
                    self.accomplish.emit(0)
                    logger.info(f"下载中止：{self.url}")

                else:

                    self.accomplish.emit(time.time() - start_time)
                    logger.success(
                        f"下载完成：{self.url}，实际下载大小：{downloaded_size} 字节，耗时：{time.time() - start_time:.2f} 秒"
                    )

                break

            except Exception as e:

                if self.check_times != -1:
                    self.check_times -= 1

                logger.exception(
                    f"下载出错：{self.url}，错误信息：{e}，剩余重试次数：{self.check_times}"
                )
                time.sleep(1)

        else:

            if self.download_path.exists():
                self.download_path.unlink()
            self.accomplish.emit(0)
            logger.error(f"下载失败：{self.url}")


class ZipExtractProcess(QThread):
    """解压子线程"""

    info = Signal(str)
    accomplish = Signal()

    def __init__(self, name: str, app_path: Path, download_path: Path) -> None:
        super(ZipExtractProcess, self).__init__()

        self.setObjectName(f"ZipExtractProcess-{name}")

        self.name = name
        self.app_path = app_path
        self.download_path = download_path

    @logger.catch
    def run(self) -> None:

        try:

            logger.info(f"开始解压：{self.download_path} 到 {self.app_path}")

            while True:

                if self.isInterruptionRequested():
                    self.download_path.unlink()
                    return None
                try:
                    with zipfile.ZipFile(self.download_path, "r") as zip_ref:
                        zip_ref.extractall(self.app_path)
                    self.accomplish.emit()
                    logger.success(f"解压完成：{self.download_path} 到 {self.app_path}")
                    break
                except PermissionError:
                    if self.name == "AUTO_MAA":
                        self.info.emit(f"解压出错：AUTO_MAA正在运行，正在尝试将其关闭")
                        System.kill_process(self.app_path / "AUTO_MAA.exe")
                    else:
                        self.info.emit(f"解压出错：{self.name}正在运行，正在等待其关闭")
                    logger.warning(f"解压出错：{self.name}正在运行，正在等待其关闭")
                    time.sleep(1)

        except Exception as e:

            e = str(e)
            e = "\n".join([e[_ : _ + 75] for _ in range(0, len(e), 75)])
            self.info.emit(f"解压更新时出错：\n{e}")
            logger.exception(f"解压更新时出错：{e}")
            return None


class DownloadManager(QDialog):
    """下载管理器"""

    speed_test_accomplish = Signal()
    download_accomplish = Signal()
    download_process_clear = Signal()

    isInterruptionRequested = False

    def __init__(self, app_path: Path, name: str, version: list, config: dict) -> None:
        super().__init__()

        self.app_path = app_path
        self.name = name
        self.version = version
        self.config = config
        self.download_path = app_path / "DOWNLOAD_TEMP.zip"  #  临时下载文件的路径
        self.download_process_dict: Dict[str, DownloadProcess] = {}
        self.timer_dict: Dict[str, QTimer] = {}
        self.if_speed_test_accomplish = False

        self.resize(700, 70)

        setTheme(Theme.AUTO, lazy=True)

        # 创建垂直布局
        self.Layout = QVBoxLayout(self)

        self.info = BodyLabel("正在初始化", self)
        self.progress_1 = IndeterminateProgressBar(self)
        self.progress_2 = ProgressBar(self)

        self.update_progress(0, 0, 0)

        self.Layout.addWidget(self.info)
        self.Layout.addStretch(1)
        self.Layout.addWidget(self.progress_1)
        self.Layout.addWidget(self.progress_2)
        self.Layout.addStretch(1)

    def run(self) -> None:

        if self.name == "AUTO_MAA":
            if self.config["mode"] == "Proxy":
                self.test_speed_task1()
                self.speed_test_accomplish.connect(self.download_task1)
            elif self.config["mode"] == "MirrorChyan":
                self.download_task1()
        elif self.config["mode"] == "MirrorChyan":
            self.download_task1()

    def get_download_url(self, mode: str) -> Union[str, Dict[str, str]]:
        """获取下载链接"""

        url_dict = {}

        if mode == "测速":

            url_dict["GitHub站"] = (
                f"https://github.com/DLmaster361/AUTO_MAA/releases/download/{version_text(self.version)}/AUTO_MAA_{version_text(self.version)}.zip"
            )
            url_dict["官方镜像站"] = (
                f"https://gitee.com/DLmaster_361/AUTO_MAA/releases/download/{version_text(self.version)}/AUTO_MAA_{version_text(self.version)}.zip"
            )
            for name, download_url_head in self.config["download_dict"].items():
                url_dict[name] = (
                    f"{download_url_head}AUTO_MAA_{version_text(self.version)}.zip"
                )
            for proxy_url in self.config["proxy_list"]:
                url_dict[proxy_url] = (
                    f"{proxy_url}https://github.com/DLmaster361/AUTO_MAA/releases/download/{version_text(self.version)}/AUTO_MAA_{version_text(self.version)}.zip"
                )
            return url_dict

        elif mode == "下载":

            if self.name == "AUTO_MAA":

                if self.config["mode"] == "Proxy":

                    if "selected" in self.config:
                        selected_url = self.config["selected"]
                    elif "speed_result" in self.config:
                        selected_url = max(
                            self.config["speed_result"],
                            key=self.config["speed_result"].get,
                        )

                    if selected_url == "GitHub站":
                        return f"https://github.com/DLmaster361/AUTO_MAA/releases/download/{version_text(self.version)}/AUTO_MAA_{version_text(self.version)}.zip"
                    elif selected_url == "官方镜像站":
                        return f"https://gitee.com/DLmaster_361/AUTO_MAA/releases/download/{version_text(self.version)}/AUTO_MAA_{version_text(self.version)}.zip"
                    elif selected_url in self.config["download_dict"].keys():
                        return f"{self.config["download_dict"][selected_url]}AUTO_MAA_{version_text(self.version)}.zip"
                    else:
                        return f"{selected_url}https://github.com/DLmaster361/AUTO_MAA/releases/download/{version_text(self.version)}/AUTO_MAA_{version_text(self.version)}.zip"

                elif self.config["mode"] == "MirrorChyan":

                    with requests.get(
                        self.config["url"],
                        allow_redirects=True,
                        timeout=10,
                        stream=True,
                    ) as response:
                        if response.status_code == 200:
                            return response.url

            elif self.config["mode"] == "MirrorChyan":

                with requests.get(
                    self.config["url"], allow_redirects=True, timeout=10, stream=True
                ) as response:
                    if response.status_code == 200:
                        return response.url

    def test_speed_task1(self) -> None:

        if self.isInterruptionRequested:
            return None

        url_dict = self.get_download_url("测速")
        self.test_speed_result: Dict[str, float] = {}

        logger.info(f"测速链接：{url_dict}")

        for name, url in url_dict.items():

            if self.isInterruptionRequested:
                break

            # 创建测速线程，下载4MB文件以测试下载速度
            self.download_process_dict[name] = DownloadProcess(
                url,
                0,
                4194304,
                self.app_path / f"{name.replace('/','').replace(':','')}.zip",
                10,
            )
            self.test_speed_result[name] = -1
            self.download_process_dict[name].accomplish.connect(
                partial(self.test_speed_task2, name)
            )

            self.download_process_dict[name].start()
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(partial(self.kill_speed_test, name))
            timer.start(30000)
            self.timer_dict[name] = timer

        self.update_info("正在测速，预计用时30秒")
        self.update_progress(0, 1, 0)

    def kill_speed_test(self, name: str) -> None:

        if name in self.download_process_dict:
            self.download_process_dict[name].requestInterruption()

    def test_speed_task2(self, name: str, t: float) -> None:

        # 计算下载速度
        if self.isInterruptionRequested:
            self.update_info(f"已中止测速进程：{name}")
            self.test_speed_result[name] = 0
        elif t != 0:
            self.update_info(f"{name}：{ 4 / t:.2f} MB/s")
            self.test_speed_result[name] = 4 / t
        else:
            self.update_info(f"{name}：{ 0:.2f} MB/s")
            self.test_speed_result[name] = 0
        self.update_progress(
            0,
            len(self.test_speed_result),
            sum(1 for speed in self.test_speed_result.values() if speed != -1),
        )

        # 删除临时文件
        if (self.app_path / f"{name.replace('/','').replace(':','')}.zip").exists():
            (self.app_path / f"{name.replace('/','').replace(':','')}.zip").unlink()

        # 清理下载线程
        self.timer_dict[name].stop()
        self.timer_dict[name].deleteLater()
        self.timer_dict.pop(name)
        self.download_process_dict[name].requestInterruption()
        self.download_process_dict[name].quit()
        self.download_process_dict[name].wait()
        self.download_process_dict[name].deleteLater()
        self.download_process_dict.pop(name)
        if not self.download_process_dict:
            self.download_process_clear.emit()

        # 当有速度大于1 MB/s的链接或存在3个即以上链接测速完成时，停止其他测速
        if not self.if_speed_test_accomplish and (
            sum(1 for speed in self.test_speed_result.values() if speed > 0) >= 3
            or any(speed > 1 for speed in self.test_speed_result.values())
        ):
            self.if_speed_test_accomplish = True
            for timer in self.timer_dict.values():
                timer.timeout.emit()

        if any(speed == -1 for _, speed in self.test_speed_result.items()):
            return None

        # 保存测速结果
        self.config["speed_result"] = self.test_speed_result
        logger.info(f"测速结果：{self.test_speed_result}")

        self.update_info("测速完成！")
        self.speed_test_accomplish.emit()

    def download_task1(self) -> None:

        if self.isInterruptionRequested:
            return None

        url = self.get_download_url("下载")
        self.downloaded_size_list: List[List[int, bool]] = []

        response = requests.head(url, timeout=10)

        self.file_size = int(response.headers.get("content-length", 0))
        part_size = self.file_size // self.config["thread_numb"]
        self.downloaded_size = 0
        self.last_download_size = 0
        self.last_time = time.time()
        self.speed = 0

        # 拆分下载任务，启用多线程下载
        for i in range(self.config["thread_numb"]):

            if self.isInterruptionRequested:
                break

            # 计算单任务下载范围
            start_byte = i * part_size
            end_byte = (
                (i + 1) * part_size - 1
                if (i != self.config["thread_numb"] - 1)
                else self.file_size - 1
            )

            # 创建下载子线程
            self.download_process_dict[f"part{i}"] = DownloadProcess(
                url,
                -1 if self.config["mode"] == "MirrorChyan" else start_byte,
                -1 if self.config["mode"] == "MirrorChyan" else end_byte,
                self.download_path.with_suffix(f".part{i}"),
                1 if self.config["mode"] == "MirrorChyan" else -1,
            )
            self.downloaded_size_list.append([0, False])
            self.download_process_dict[f"part{i}"].progress.connect(
                partial(self.download_task2, i)
            )
            self.download_process_dict[f"part{i}"].accomplish.connect(
                partial(self.download_task3, i)
            )
            self.download_process_dict[f"part{i}"].start()

    def download_task2(self, index: str, current: int) -> None:
        """更新下载进度"""

        self.downloaded_size_list[index][0] = current
        self.downloaded_size = sum([_[0] for _ in self.downloaded_size_list])
        self.update_progress(0, self.file_size, self.downloaded_size)

        if time.time() - self.last_time >= 1.0:
            self.speed = (
                (self.downloaded_size - self.last_download_size)
                / (time.time() - self.last_time)
                / 1024
            )
            self.last_download_size = self.downloaded_size
            self.last_time = time.time()

        if self.speed >= 1024:
            self.update_info(
                f"正在下载：{self.name} 已下载：{self.downloaded_size / 1048576:.2f}/{self.file_size / 1048576:.2f} MB （{self.downloaded_size / self.file_size * 100:.2f}%） 下载速度：{self.speed / 1024:.2f} MB/s",
            )
        else:
            self.update_info(
                f"正在下载：{self.name} 已下载：{self.downloaded_size / 1048576:.2f}/{self.file_size / 1048576:.2f} MB （{self.downloaded_size / self.file_size * 100:.2f}%） 下载速度：{self.speed:.2f} KB/s",
            )

    def download_task3(self, index: str, t: float) -> None:

        # 标记下载线程完成
        self.downloaded_size_list[index][1] = True

        # 清理下载线程
        self.download_process_dict[f"part{index}"].requestInterruption()
        self.download_process_dict[f"part{index}"].quit()
        self.download_process_dict[f"part{index}"].wait()
        self.download_process_dict[f"part{index}"].deleteLater()
        self.download_process_dict.pop(f"part{index}")
        if not self.download_process_dict:
            self.download_process_clear.emit()

        if (
            any([not _[1] for _ in self.downloaded_size_list])
            or self.isInterruptionRequested
        ):
            return None

        # 合并下载的分段文件
        logger.info(
            f"所有分段下载完成：{self.name}，开始合并分段文件到 {self.download_path}"
        )
        with self.download_path.open(mode="wb") as outfile:
            for i in range(self.config["thread_numb"]):
                with self.download_path.with_suffix(f".part{i}").open(
                    mode="rb"
                ) as infile:
                    outfile.write(infile.read())
                self.download_path.with_suffix(f".part{i}").unlink()

        logger.success(
            f"合并完成：{self.name}，下载文件大小：{self.download_path.stat().st_size} 字节"
        )

        self.update_info("正在解压更新文件")
        self.update_progress(0, 0, 0)

        # 创建解压线程
        self.zip_extract = ZipExtractProcess(
            self.name, self.app_path, self.download_path
        )
        self.zip_loop = QEventLoop()
        self.zip_extract.info.connect(self.update_info)
        self.zip_extract.accomplish.connect(self.zip_loop.quit)
        self.zip_extract.start()
        self.zip_loop.exec()

        self.update_info("正在删除临时文件")
        self.update_progress(0, 0, 0)
        if (self.app_path / "changes.json").exists():
            (self.app_path / "changes.json").unlink()
        if self.download_path.exists():
            self.download_path.unlink()

        # 下载完成后打开对应程序
        if not self.isInterruptionRequested and self.name == "MAA":
            subprocess.Popen(
                [self.app_path / "MAA.exe"],
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NO_WINDOW,
            )
        if self.name == "AUTO_MAA":
            self.update_info(f"即将安装{self.name}")
        else:
            self.update_info(f"{self.name}下载成功！")
        self.update_progress(0, 100, 100)
        self.download_accomplish.emit()

    def update_info(self, text: str) -> None:
        self.info.setText(text)

    def update_progress(self, begin: int, end: int, current: int) -> None:

        if begin == 0 and end == 0:
            self.progress_2.setVisible(False)
            self.progress_1.setVisible(True)
        else:
            self.progress_1.setVisible(False)
            self.progress_2.setVisible(True)
            self.progress_2.setRange(begin, end)
            self.progress_2.setValue(current)

    def requestInterruption(self) -> None:
        """请求中断下载任务"""

        logger.info("收到下载任务中止请求")

        self.isInterruptionRequested = True

        if hasattr(self, "zip_extract") and self.zip_extract:
            self.zip_extract.requestInterruption()

        if hasattr(self, "zip_loop") and self.zip_loop:
            self.zip_loop.quit()

        for process in self.download_process_dict.values():
            process.requestInterruption()

        if self.download_process_dict:
            loop = QEventLoop()
            self.download_process_clear.connect(loop.quit)
            loop.exec()

    def closeEvent(self, event: QCloseEvent):
        """清理残余进程"""

        self.requestInterruption()

        event.accept()
