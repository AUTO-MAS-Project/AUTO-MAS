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


import re
import time
import json
import zipfile
import requests
import subprocess
from packaging import version
from typing import List, Dict, Optional
from pathlib import Path

from app.core import Config
from app.models.schema import WebSocketMessage
from app.utils.constants import MIRROR_ERROR_INFO
from app.utils.logger import get_logger

logger = get_logger("更新服务")


class _UpdateHandler:

    def __init__(self) -> None:
        self.is_locked: bool = False
        self.remote_version: Optional[str] = None
        self.mirror_chyan_download_url: Optional[str] = None

    async def check_update(
        self, current_version: str
    ) -> tuple[bool, str, Dict[str, List[str]]]:

        logger.info("开始检查更新")

        response = requests.get(
            f"https://mirrorchyan.com/api/resources/AUTO_MAA/latest?user_agent=AutoMaaGui&current_version={current_version}&cdk={Config.get('Update', 'MirrorChyanCDK')}&channel={Config.get('Update', 'UpdateType')}",
            timeout=10,
            proxies=Config.get_proxies(),
        )
        if response.status_code == 200:
            version_info = response.json()
        else:
            result = response.json()

            if result["code"] != 0:
                if result["code"] in MIRROR_ERROR_INFO:
                    raise Exception(
                        f"获取版本信息时出错: {MIRROR_ERROR_INFO[result['code']]}"
                    )
                else:
                    raise Exception(
                        "获取版本信息时出错: 意料之外的错误, 请及时联系项目组以获取来自 Mirror 酱的技术支持"
                    )

        logger.success("获取版本信息成功")

        remote_version = version_info["data"]["version_name"]
        self.remote_version = remote_version
        if "url" in version_info["data"]:
            self.mirror_chyan_download_url = version_info["data"]["url"]

        if version.parse(remote_version) > version.parse(current_version):

            # 版本更新信息
            version_info_json: Dict[str, Dict[str, List[str]]] = json.loads(
                re.sub(
                    r"^<!--\s*(.*?)\s*-->$",
                    r"\1",
                    version_info["data"]["release_note"].splitlines()[0],
                )
            )

            update_version_info = {}
            for v_i in [
                info
                for ver, info in version_info_json.items()
                if version.parse(ver) > version.parse(current_version)
            ]:

                for key, value in v_i.items():
                    if key not in update_version_info:
                        update_version_info[key] = []
                    update_version_info[key] += value

            return True, remote_version, update_version_info

        else:
            return False, current_version, {}

    async def download_update(self) -> None:

        if self.is_locked:
            await Config.send_json(
                WebSocketMessage(
                    id="Update",
                    type="Signal",
                    data={"Failed": "已有更新任务在进行中, 请勿重复操作"},
                ).model_dump()
            )
            return None

        self.is_locked = True

        if self.remote_version is None:
            await Config.send_json(
                WebSocketMessage(
                    id="Update",
                    type="Signal",
                    data={"Failed": "未检测到可用的远程版本, 请先检查更新"},
                ).model_dump()
            )
            self.is_locked = False
            return None

        if (Path.cwd() / f"UpdatePack_{self.remote_version}.zip").exists():
            logger.info(
                f"更新包已存在: {Path.cwd() / f'UpdatePack_{self.remote_version}.zip'}"
            )
            await Config.send_json(
                WebSocketMessage(
                    id="Update",
                    type="Signal",
                    data={
                        "Accomplish": str(
                            Path.cwd() / f"UpdatePack_{self.remote_version}.zip"
                        )
                    },
                ).model_dump()
            )
            self.is_locked = False
            return None

        if Config.get("Update", "Source") == "GitHub":

            download_url = f"https://github.com/DLmaster361/AUTO_MAA/releases/download/{self.remote_version}/AUTO_MAA_{self.remote_version}.zip"

        elif Config.get("Update", "Source") == "MirrorChyan":

            if self.mirror_chyan_download_url is None:
                logger.warning("MirrorChyan 未返回下载链接, 使用自建下载站")
                download_url = f"https://download.auto-mas.top/d/AUTO_MAA/AUTO_MAA_{self.remote_version}.zip"

            else:
                with requests.get(
                    self.mirror_chyan_download_url,
                    allow_redirects=True,
                    timeout=10,
                    stream=True,
                    proxies=Config.get_proxies(),
                ) as response:
                    if response.status_code == 200:
                        download_url = response.url
        elif Config.get("Update", "Source") == "AutoSite":
            download_url = f"https://download.auto-mas.top/d/AUTO_MAA/AUTO_MAA_{self.remote_version}.zip"

        else:
            await Config.send_json(
                WebSocketMessage(
                    id="Update",
                    type="Signal",
                    data={
                        "Failed": f"未知的下载源: {Config.get('Update', 'Source')}, 请检查配置文件"
                    },
                ).model_dump()
            )
            self.is_locked = False
            return None

        logger.info(f"开始下载: {download_url}")

        check_times = 3
        while check_times != 0:

            try:
                # 清理可能存在的临时文件
                if (Path.cwd() / "download.temp").exists():
                    (Path.cwd() / "download.temp").unlink()

                start_time = time.time()

                response = requests.get(
                    download_url, timeout=10, stream=True, proxies=Config.get_proxies()
                )

                if response.status_code not in [200, 206]:

                    if check_times != -1:
                        check_times -= 1

                    logger.warning(
                        f"连接失败: {download_url}, 状态码: {response.status_code}, 剩余重试次数: {check_times}"
                    )

                    time.sleep(1)
                    continue

                logger.info(f"连接成功: {download_url}, 状态码: {response.status_code}")

                file_size = int(response.headers.get("content-length", 0))
                downloaded_size = 0
                last_download_size = 0
                speed = 0
                last_time = time.time()
                with (Path.cwd() / "download.temp").open(mode="wb") as f:

                    for chunk in response.iter_content(chunk_size=8192):

                        f.write(chunk)
                        downloaded_size += len(chunk)
                        await Config.send_json(
                            WebSocketMessage(
                                id="Update",
                                type="Update",
                                data={
                                    "downloaded_size": downloaded_size,
                                    "file_size": file_size,
                                    "speed": speed,
                                },
                            ).model_dump()
                        )

                        # 更新指定线程的下载进度, 每秒更新一次
                        if time.time() - last_time >= 1.0:
                            speed = (
                                (downloaded_size - last_download_size)
                                / (time.time() - last_time)
                                / 1024
                            )
                            last_download_size = downloaded_size
                            last_time = time.time()

                (Path.cwd() / "download.temp").rename(
                    Path.cwd() / f"UpdatePack_{self.remote_version}.zip"
                )

                logger.success(
                    f"下载完成: {download_url}, 实际下载大小: {downloaded_size} 字节, 耗时: {time.time() - start_time:.2f} 秒, 保存位置: {Path.cwd() / f'UpdatePack_{self.remote_version}.zip'}"
                )
                await Config.send_json(
                    WebSocketMessage(
                        id="Update",
                        type="Signal",
                        data={
                            "Accomplish": str(
                                Path.cwd() / f"UpdatePack_{self.remote_version}.zip"
                            )
                        },
                    ).model_dump()
                )
                self.is_locked = False
                break

            except Exception as e:

                if check_times != -1:
                    check_times -= 1

                logger.info(
                    f"下载出错: {download_url}, 错误信息: {e}, 剩余重试次数: {check_times}"
                )
                time.sleep(1)

        else:

            if (Path.cwd() / "download.temp").exists():
                (Path.cwd() / "download.temp").unlink()
            await Config.send_json(
                WebSocketMessage(
                    id="Update",
                    type="Signal",
                    data={"Failed": f"下载失败: {download_url}"},
                ).model_dump()
            )
            self.is_locked = False

    async def install_update(self):

        if self.is_locked:
            await Config.send_json(
                WebSocketMessage(
                    id="Update",
                    type="Signal",
                    data={"Failed": "已有更新任务在进行中, 请勿重复操作"},
                ).model_dump()
            )
            return None

        logger.info("开始应用更新")
        self.is_locked = True

        versions = {
            version.parse(match.group(1)): f.name
            for f in Path.cwd().glob("UpdatePack_*.zip")
            if (match := re.match(r"UpdatePack_(.+)\.zip$", f.name))
        }
        logger.info(f"检测到的更新包: {versions.values()}")

        if not versions:
            await Config.send_json(
                WebSocketMessage(
                    id="Update",
                    type="Signal",
                    data={"Failed": "未检测到更新包, 请先下载更新"},
                ).model_dump()
            )
            self.is_locked = False
            return None

        update_package = Path.cwd() / versions[max(versions)]

        logger.info(f"开始解压: {update_package} 到 {Path.cwd()}")

        try:
            with zipfile.ZipFile(update_package, "r") as zip_ref:
                zip_ref.extractall(Path.cwd())
        except Exception as e:
            logger.error(f"解压失败, {type(e).__name__}: {e}")
            await Config.send_json(
                WebSocketMessage(
                    id="Update",
                    type="Message",
                    data={"Error": f"解压失败, {type(e).__name__}: {e}"},
                ).model_dump()
            )
            self.is_locked = False
            return None

        logger.success(f"解压完成: {update_package} 到 {Path.cwd()}")

        logger.info("正在删除临时文件与旧更新包文件")
        if (Path.cwd() / "changes.json").exists():
            (Path.cwd() / "changes.json").unlink()
        for f in versions.values():
            if (Path.cwd() / f).exists():
                (Path.cwd() / f).unlink()

        logger.info("启动更新程序")
        self.is_locked = False
        subprocess.Popen(
            [Path.cwd() / "AUTO_MAA-Setup.exe"],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NO_WINDOW,
        )


Updater = _UpdateHandler()
