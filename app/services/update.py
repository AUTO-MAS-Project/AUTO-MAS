#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import re
import time
import json
import asyncio
import zipfile
import httpx
import aiofiles
import subprocess
from dataclasses import dataclass
from packaging import version
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path

from app.core.ws import Publisher, protocol
from app.models.schema import (
    UpdateDownloadSnapshot,
    WSUpdateCompletedData,
    WSUpdateFailedData,
    WSUpdateProgressData,
)
from app.utils.constants import MIRROR_ERROR_INFO
from app.utils import LazyProxy, ProcessRunner, get_logger
from .system import System

logger = get_logger("更新服务")

# 延迟加载 Config，避免 app.services 初始化期间触发 app.core 循环导入
Config = LazyProxy("app.core", "Config")


@dataclass(frozen=True)
class _DownloadJob:
    """下载任务启动时冻结的版本、来源与 URL。"""

    version: Optional[str]
    source: str
    mirror_chyan_download_url: Optional[str]
    download_url: Optional[str]


class _UpdateHandler:

    def __init__(self) -> None:
        self.is_locked: bool = False
        self.download_task: Optional[asyncio.Task[None]] = None
        self.is_switching_source: bool = False
        self.remote_version: Optional[str] = None
        self.last_check_time: Optional[datetime] = None
        self.update_version_info: Optional[Dict[str, List[str]]] = None
        self.mirror_chyan_download_url: Optional[str] = None
        self._download_task_job: Optional[_DownloadJob] = None
        self._download_snapshot = UpdateDownloadSnapshot()

    def get_download_snapshot(self) -> UpdateDownloadSnapshot:
        """返回当前下载权威状态的 HTTP 初始快照。"""

        return self._download_snapshot.model_copy(deep=True)

    def _update_download_snapshot(self, **updates: object) -> None:
        self._download_snapshot = UpdateDownloadSnapshot.model_validate(
            {**self._download_snapshot.model_dump(), **updates}
        )

    async def _publish_failed(self, message: str) -> None:
        self._update_download_snapshot(
            status="failed",
            speed=0,
            message=message,
        )
        await Publisher.send(
            id=protocol.ID_UPDATE,
            type=protocol.UPDATE_FAILED,
            data=WSUpdateFailedData(message=message),
        )

    async def _publish_completed(self, file: Path) -> None:
        file_path = str(file)
        self._update_download_snapshot(
            status="completed",
            speed=0,
            file=file_path,
            message=None,
        )
        await Publisher.send(
            id=protocol.ID_UPDATE,
            type=protocol.UPDATE_COMPLETED,
            data=WSUpdateCompletedData(file=file_path),
        )

    async def start_download(
        self, *, target_version: Optional[str] = None
    ) -> bool:
        if self.is_switching_source or self.is_locked:
            return False
        return self._start_download_task(
            job=self._create_download_job(download_version=target_version)
        )

    def _start_download_task(
        self, *, job: Optional[_DownloadJob] = None
    ) -> bool:
        if self.download_task is not None and not self.download_task.done():
            return False

        download_job = job or self._create_download_job()
        self._download_task_job = download_job
        self._download_snapshot = UpdateDownloadSnapshot(
            status="downloading",
            version=download_job.version,
            source=download_job.source,
        )
        self.download_task = asyncio.create_task(
            self.download_update(job=download_job),
            name=f"update-download:{download_job.version or 'unknown'}",
        )
        self.download_task.add_done_callback(self._clear_download_task)
        return True

    def _clear_download_task(self, task: asyncio.Task[None]) -> None:
        if not task.cancelled():
            exception = task.exception()
            if exception is not None:
                logger.error(f"后台更新下载任务异常: {exception}")
        if self.download_task is task:
            self.download_task = None
            self._download_task_job = None

    async def cancel_download(self, *, notify: bool = True) -> bool:
        task = self.download_task
        if task is None or task.done():
            return False

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        self._cleanup_download()

        if notify:
            self._update_download_snapshot(status="cancelled", speed=0)
            await Publisher.send(
                id=protocol.ID_UPDATE, type=protocol.UPDATE_CANCELLED
            )
        return True

    async def switch_to_cnb(self) -> bool:
        download_version = (
            self._download_task_job.version
            if self._download_task_job is not None
            else self.remote_version
        )
        if self.is_switching_source:
            return False

        if self._get_download_source() != "GitHub":
            return False

        task = self.download_task
        if task is None or task.done():
            return False

        self.is_switching_source = True
        self.is_locked = True
        self._update_download_snapshot(status="switchingSource", speed=0)
        try:
            if not await self.cancel_download(notify=False):
                return False

            try:
                await Config.set("Update", "Source", "CNB")
            except Exception as error:
                await self._publish_failed(
                    f"切换至 CNB 源失败: {type(error).__name__}: {str(error)}"
                )
                raise

            self.is_locked = False
            restart_job = self._create_download_job(
                download_version=download_version
            )
            if not self._start_download_task(job=restart_job):
                error = RuntimeError("切换至 CNB 源失败: 无法重新启动更新下载任务")
                await self._publish_failed(str(error))
                raise error
            return True
        finally:
            self.is_switching_source = False
            if self.is_locked and (self.download_task is None or self.download_task.done()):
                self.is_locked = False

    def _cleanup_download(self) -> None:
        temp_file = Path.cwd() / "download.temp"
        try:
            if temp_file.exists():
                temp_file.unlink()
        except OSError as error:
            logger.exception(f"清理更新下载临时文件失败: {error}")
        finally:
            if not self.is_switching_source:
                self.is_locked = False

    def _create_download_job(
        self, *, download_version: Optional[str] = None
    ) -> _DownloadJob:
        frozen_version = (
            download_version
            if download_version is not None
            else self.remote_version
        )
        frozen_source = self._get_download_source()
        frozen_mirror_url = self.mirror_chyan_download_url
        frozen_download_url = (
            self._get_download_url(
                frozen_source,
                download_version=frozen_version,
                mirror_chyan_download_url=frozen_mirror_url,
            )
            if frozen_version is not None
            else None
        )
        return _DownloadJob(
            version=frozen_version,
            source=frozen_source,
            mirror_chyan_download_url=frozen_mirror_url,
            download_url=frozen_download_url,
        )

    def _get_download_source(self) -> str:
        return Config.get("Update", "Source")

    def _get_download_url(
        self,
        source: str,
        *,
        download_version: Optional[str] = None,
        mirror_chyan_download_url: Optional[str] = None,
    ) -> str:
        remote_version = (
            download_version
            if download_version is not None
            else self.remote_version
        )
        if remote_version is None:
            raise ValueError("未检测到可用的远程版本, 请先检查更新")

        if source == "GitHub":
            return f"https://github.com/AUTO-MAS-Project/AUTO-MAS/releases/download/{remote_version}/AUTO-MAS-Lite-Setup-{remote_version}-x64.zip"

        if source == "MirrorChyan":
            mirror_url = (
                mirror_chyan_download_url
                if mirror_chyan_download_url is not None
                else self.mirror_chyan_download_url
            )
            if mirror_url is None:
                logger.warning("MirrorChyan 未返回下载链接, 使用自建下载站")
                return f"https://download.auto-mas.top/d/AUTO-MAS/AUTO-MAS-Lite-Setup-{remote_version}-x64.zip"
            return mirror_url

        if source == "AutoSite":
            return f"https://download.auto-mas.top/d/AUTO-MAS/AUTO-MAS-Lite-Setup-{remote_version}-x64.zip"

        if source == "CNB":
            return f"https://cnb.cool/AUTO-MAS-Project/AUTO-MAS/-/releases/download/{remote_version}/AUTO-MAS-Lite-Setup-{remote_version}-x64.zip"

        raise ValueError(f"未知的下载源: {source}, 请检查配置文件")

    async def check_update(
        self, current_version: str, if_force: bool = False
    ) -> tuple[bool, str, Dict[str, List[str]]]:

        if (
            not if_force
            and self.remote_version is not None
            and self.last_check_time is not None
            and self.update_version_info is not None
            and self.last_check_time > datetime.now() - timedelta(hours=4)
        ):
            logger.info("四小时内已进行过一次检查, 直接使用缓存的版本更新信息")
            return (
                bool(
                    version.parse(self.remote_version) > version.parse(current_version)
                ),
                self.remote_version,
                self.update_version_info,
            )

        logger.info("开始检查更新")

        # 使用 httpx 异步请求
        async with httpx.AsyncClient(
            proxy=Config.proxy, follow_redirects=True
        ) as client:
            response = await client.get(
                f"https://mirrorchyan.com/api/resources/AUTO_MAS/latest?user_agent=AutoMasGui&os=win&arch=x64&current_version={current_version}&cdk={Config.get('Update', 'MirrorChyanCDK') if Config.get('Update', 'Source') == 'MirrorChyan' else ''}&channel={Config.get('Update', 'Channel')}"
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
        self.last_check_time = datetime.now()

        self.remote_version = version_info["data"]["version_name"]
        if self.remote_version is None:
            raise Exception("Mirror 酱未返回版本号, 请稍后重试")
        if "url" in version_info["data"]:
            self.mirror_chyan_download_url = version_info["data"]["url"]

        if version.parse(self.remote_version) > version.parse(current_version):

            # 版本更新信息
            version_info_json: Dict[str, Dict[str, List[str]]] = json.loads(
                re.sub(
                    r"^<!--\s*(.*?)\s*-->$",
                    r"\1",
                    version_info["data"]["release_note"].splitlines()[0].strip(),
                )
            )

            self.update_version_info = {}
            for v_i in [
                info
                for ver, info in version_info_json.items()
                if version.parse(ver) > version.parse(current_version)
            ]:

                for key, value in v_i.items():
                    if key not in self.update_version_info:
                        self.update_version_info[key] = []
                    self.update_version_info[key] += value

            return True, self.remote_version, self.update_version_info

        else:
            return False, current_version, {}

    async def download_update(
        self, *, job: Optional[_DownloadJob] = None
    ) -> None:

        download_job = job or self._create_download_job()

        logger.info("收到前端下载请求")

        if self.is_locked:
            await Publisher.send(
                id=protocol.ID_UPDATE,
                type=protocol.UPDATE_FAILED,
                data=WSUpdateFailedData(
                    message="已有更新任务在进行中, 请勿重复操作"
                ),
            )
            return None

        self.is_locked = True
        try:
            await self._download_update_locked(job=download_job)
        except asyncio.CancelledError:
            logger.info("更新下载已取消")
            raise
        except Exception as error:
            logger.exception(
                f"更新下载任务异常: {type(error).__name__}: {error}"
            )
            await self._publish_failed(
                f"下载失败: {type(error).__name__}: {error}"
            )
        finally:
            self._cleanup_download()

    async def _download_update_locked(
        self, *, job: Optional[_DownloadJob] = None
    ) -> None:

        download_job = job or self._create_download_job()
        download_version = download_job.version

        if download_version is None:
            await self._publish_failed("未检测到可用的远程版本, 请先检查更新")
            self.is_locked = False
            return None

        if (Path.cwd() / f"UpdatePack_{download_version}.zip").exists():
            existing_package = (
                Path.cwd() / f"UpdatePack_{download_version}.zip"
            )
            logger.info(f"更新包已存在: {existing_package}")
            await self._publish_completed(existing_package)
            self.is_locked = False
            return None

        source = download_job.source
        download_url = download_job.download_url
        if download_url is None:
            error = ValueError("下载 job 未绑定 URL")
            await self._publish_failed(str(error))
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

                # 使用 httpx 异步流式下载
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    async with client.stream(
                        "GET", download_url, timeout=30.0
                    ) as response:
                        status_code = response.status_code

                        if status_code not in [200, 206]:
                            if check_times != -1:
                                check_times -= 1

                            logger.warning(
                                f"连接失败: {download_url}, 状态码: {status_code}, 剩余重试次数: {check_times}"
                            )
                            await asyncio.sleep(1)
                            continue

                        logger.info(f"连接成功: {download_url}, 状态码: {status_code}")

                        file_size = int(response.headers.get("content-length", 0) or 0)
                        downloaded_size = 0
                        last_download_size = 0
                        speed = 0
                        last_time = time.time()

                        # 使用 aiofiles 异步写入临时文件
                        async with aiofiles.open(
                            Path.cwd() / "download.temp", "wb"
                        ) as f:
                            async for chunk in response.aiter_bytes(chunk_size=8192):
                                if not chunk:
                                    continue
                                await f.write(chunk)
                                downloaded_size += len(chunk)

                                # 更新指定线程的下载进度, 每秒更新一次
                                if time.time() - last_time >= 1.0:
                                    elapsed = time.time() - last_time
                                    if elapsed <= 0:
                                        elapsed = 1.0
                                    speed = (
                                        downloaded_size - last_download_size
                                    ) / elapsed
                                    last_download_size = downloaded_size
                                    last_time = time.time()

                                    self._update_download_snapshot(
                                        status="downloading",
                                        downloaded_size=downloaded_size,
                                        file_size=file_size,
                                        speed=speed,
                                        source=source,
                                    )

                                    await Publisher.send(
                                        id=protocol.ID_UPDATE,
                                        type=protocol.UPDATE_PROGRESS,
                                        data=WSUpdateProgressData(
                                            downloaded_size=downloaded_size,
                                            file_size=file_size,
                                            speed=speed,
                                            source=source,
                                        ),
                                    )

                # 重命名临时文件为最终包
                final_path = Path.cwd() / f"UpdatePack_{download_version}.zip"
                (Path.cwd() / "download.temp").rename(final_path)

                logger.success(
                    f"下载完成: {download_url}, 实际下载大小: {downloaded_size} 字节, 耗时: {time.time() - start_time:.2f} 秒, 保存位置: {final_path}"
                )
                await self._publish_completed(final_path)
                self.is_locked = False
                break

            except Exception as e:

                if check_times != -1:
                    check_times -= 1

                logger.exception(
                    f"下载出错: {download_url}, 错误信息: {e}, 剩余重试次数: {check_times}"
                )
                await asyncio.sleep(1)

        else:

            if (Path.cwd() / "download.temp").exists():
                (Path.cwd() / "download.temp").unlink()
            await self._publish_failed(f"下载失败: {download_url}")
            self.is_locked = False

    async def install_update(self):

        if self.is_locked or self.is_switching_source:
            await Publisher.send(
                id=protocol.ID_UPDATE,
                type=protocol.UPDATE_FAILED,
                data={"message": "已有更新任务在进行中, 请勿重复操作"},
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
            await Publisher.send(
                id=protocol.ID_UPDATE,
                type=protocol.UPDATE_FAILED,
                data={"message": "未检测到更新包, 请先下载更新"},
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
            await Publisher.send(
                id=protocol.ID_UPDATE,
                type=protocol.UPDATE_FAILED,
                data={"message": f"解压失败, {type(e).__name__}: {e}"},
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

        logger.info("正在清理旧版本注册表项")
        await ProcessRunner.run_process(
            "reg",
            "delete",
            r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{D116A92A-E174-4699-B777-61C5FD837B19}_is1",
            "/f",
        )
        logger.success("清理完成")

        logger.info("启动更新程序")
        self.is_locked = False
        subprocess.Popen(
            [
                Path.cwd() / "AUTO-MAS-Setup.exe",
                "/SP-",
                "/SILENT",
                "/NOCANCEL",
                "/FORCECLOSEAPPLICATIONS",
                "/LANG=Chinese",
                f"/DIR={Path.cwd()}",
            ],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NO_WINDOW,
        )
        await System.set_power("KillSelf")


Updater = _UpdateHandler()
