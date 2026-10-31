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


import asyncio
import json
import re
import subprocess
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

import httpx
from packaging import version

from app.core import Publisher
from app.core.ws import protocol
from app.models.schema import (
    UpdateDownloadSnapshot,
    WSUpdateCompletedData,
    WSUpdateFailedData,
    WSUpdateProgressData,
)
from app.services.common.system import System
from app.services.common.update.fluxdown import FluxdownResumableError
from app.services.common.update.transport import (
    DownloadProgress,
    request_mirror_resource,
)
from app.utils import LazyProxy, ProcessRunner, get_logger, process_platform
from app.utils import fluxdown_cli as _utils_fluxdown_cli

logger = get_logger("更新服务")

# 延迟加载 Config，避免 app.services 初始化期间触发 app.core 循环导入
Config = LazyProxy("app.core", "Config")


class UpdateDownloader(Protocol):
    """更新器只依赖下载能力，默认选项与历史由宿主装配。"""

    async def __call__(
        self,
        url: str,
        destination: Path,
        *,
        timeout: float,
        proxy: httpx.Proxy | None = None,
        progress: DownloadProgress | None = None,
        downloader: str | None = None,
        source: str | None = None,
    ) -> int: ...


@dataclass(frozen=True)
class _DownloadJob:
    """下载任务启动时冻结的版本、来源与 URL。"""

    version: Optional[str]
    source: str
    mirror_chyan_download_url: Optional[str]
    download_url: Optional[str]
    # 显式下载器覆盖（"builtin"/"fluxdown"）；None = 按 Update.Downloader 配置
    downloader: Optional[str] = None


def _describe_version_section_error(section: object) -> Optional[str]:
    """返回版本段不合法的原因，合法时返回 None。

    版本段必须是「分类名 -> 字符串列表」的映射。更新日志会原样交给
    `/update/check` 的响应模型，形状不对的版本段会让响应校验抛异常，
    用户连「检测到更新」都看不到，因此形状不对的版本段进不了响应。
    """

    if not isinstance(section, dict):
        return "版本段不是字典"

    for category, notes in section.items():
        if not isinstance(notes, list):
            return f"分类 {category!r} 的内容不是列表"
        if not all(isinstance(note, str) for note in notes):
            return f"分类 {category!r} 的列表里混有非字符串内容"

    return None


def select_newer_version_info(
    version_info: Dict[str, Any], current_version: str
) -> Dict[str, Dict[str, List[str]]]:
    """挑出比当前版本新的版本段，按版本号降序排列，保留每段的分类归属。

    版本号用 packaging 比较而不是字符串比较，否则 beta.10 会排到 beta.2 前面。
    认不出是版本号的键、或内部形状不是「分类名 -> 字符串列表」的版本段直接跳过：
    更新日志来自 Mirror 酱，内容坏掉时只该丢日志，不该让整条更新检查失败。
    """

    current = version.parse(current_version)
    newer = []
    for raw_version, info in version_info.items():
        try:
            parsed = version.parse(raw_version)
        except version.InvalidVersion:
            logger.warning(f"更新日志里的版本号无法识别, 已跳过: {raw_version!r}")
            continue
        section_error = _describe_version_section_error(info)
        if section_error is not None:
            logger.warning(
                f"更新日志的版本段结构异常, 已跳过 {raw_version!r}: {section_error}"
            )
            continue
        if parsed > current:
            newer.append((parsed, raw_version, info))

    newer.sort(key=lambda item: item[0], reverse=True)
    return {ver: info for _, ver, info in newer}


def parse_release_note(release_note: object) -> Dict[str, Any]:
    """解析 Mirror 酱返回的更新日志。

    只保证解析出 JSON 对象，不保证版本段的内部形状，形状校验留给
    `select_newer_version_info`，避免同一处坏数据被记两次警告。

    日志正文是 release_note 首行里一条被 HTML 注释包裹的 JSON。Mirror 酱对
    release_note 有长度上限，日志过长时它返回的首行是截断过的、不完整的 JSON，
    此时只丢掉更新日志本身：「检测到更新」这个结论必须留住，否则用户连新版本
    提示都看不到。
    """

    if not isinstance(release_note, str) or not release_note.strip():
        logger.warning("Mirror 酱未返回更新日志")
        return {}

    first_line = release_note.splitlines()[0].strip()
    try:
        parsed = json.loads(re.sub(r"^<!--\s*(.*?)\s*-->$", r"\1", first_line))
    except json.JSONDecodeError as error:
        logger.warning(
            f"更新日志无法解析, 本次只提示更新: {type(error).__name__}: {error}"
        )
        return {}

    if not isinstance(parsed, dict):
        logger.warning("更新日志不是预期的版本字典格式, 本次只提示更新")
        return {}

    return parsed


class UpdateHandler:
    def __init__(self, *, download: UpdateDownloader) -> None:
        self._download = download
        self.is_locked: bool = False
        self.download_task: Optional[asyncio.Task[None]] = None
        self.is_switching_source: bool = False
        self.remote_version: Optional[str] = None
        self.current_version: Optional[str] = None
        self.last_check_time: Optional[datetime] = None
        self.update_version_info: Optional[Dict[str, Dict[str, List[str]]]] = None
        # 非强制检查的结果缓存: (当前版本, 检查结果, 检查时间)
        self._check_cache: Optional[
            tuple[str, tuple[bool, str, Dict[str, Dict[str, List[str]]]], datetime]
        ] = None
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
        logger.error(message)
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
        self, *, target_version: Optional[str] = None, downloader: Optional[str] = None
    ) -> bool:
        if self.is_switching_source or self.is_locked:
            return False

        # Mirror 酱的下载地址是一次性的, 不能沿用版本检查缓存里的旧地址
        if self._get_download_source() == "MirrorChyan":
            await self._refresh_mirror_download_url()

        return self._start_download_task(
            job=self._create_download_job(
                download_version=target_version, downloader=downloader
            )
        )

    def _start_download_task(self, *, job: Optional[_DownloadJob] = None) -> bool:
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
        except _utils_fluxdown_cli.FluxdownCancelUnconfirmed as error:
            # 暂停未确认：daemon 可能仍在写目标文件。按失败上报并抛出，
            # 让调用方走失败路径（API 500 / 切源中止），绝不能继续覆写
            # 同一目标或报告取消成功
            logger.error(f"取消下载时无法确认 FluxDown 任务已停止: {error}")
            await self._publish_failed(
                "取消时无法确认 FluxDown 任务已停止，将在下次重试时续传"
            )
            self._cleanup_download()
            raise
        self._cleanup_download()

        if notify:
            self._update_download_snapshot(status="cancelled", speed=0)
            await Publisher.send(id=protocol.ID_UPDATE, type=protocol.UPDATE_CANCELLED)
        return True

    async def switch_to_cnb(self) -> bool:
        frozen_job = self._download_task_job
        download_version = (
            frozen_job.version if frozen_job is not None else self.remote_version
        )
        # 切源要重建 job：显式下载器与来源一样随任务冻结，不能因重建丢回配置默认
        frozen_downloader = frozen_job.downloader if frozen_job is not None else None
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
                await Config.setting.update(
                    type(Config.setting).model_validate({"Update": {"Source": "CNB"}}),
                    check_visibility=False,
                )
            except Exception as error:
                await self._publish_failed(
                    f"切换至 CNB 源失败: {type(error).__name__}: {str(error)}"
                )
                raise

            self.is_locked = False
            restart_job = self._create_download_job(
                download_version=download_version, downloader=frozen_downloader
            )
            if not self._start_download_task(job=restart_job):
                error = RuntimeError("切换至 CNB 源失败: 无法重新启动更新下载任务")
                await self._publish_failed(str(error))
                raise error
            return True
        finally:
            self.is_switching_source = False
            if self.is_locked and (
                self.download_task is None or self.download_task.done()
            ):
                self.is_locked = False

    def _cleanup_download(self) -> None:
        # 不删 download.temp：取消/中断时保留它作为断点续传状态（httpx 追加、
        # FluxDown server resume 都依赖它），仅在彻底放弃（重试耗尽）与成功
        # 改名两条路径处理该文件
        if not self.is_switching_source:
            self.is_locked = False

    def _create_download_job(
        self,
        *,
        download_version: Optional[str] = None,
        downloader: Optional[str] = None,
    ) -> _DownloadJob:
        frozen_version = (
            download_version if download_version is not None else self.remote_version
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
            downloader=downloader,
        )

    def _get_download_source(self) -> str:
        return Config.setting.Update.Source

    def _get_download_url(
        self,
        source: str,
        *,
        download_version: Optional[str] = None,
        mirror_chyan_download_url: Optional[str] = None,
    ) -> str:
        remote_version = (
            download_version if download_version is not None else self.remote_version
        )
        if remote_version is None:
            raise ValueError("未检测到可用的远程版本, 请先检查更新")

        if source == "GitHub":
            return f"https://github.com/AUTO-MAS-Project/AUTO-MAS/releases/download/{remote_version}/AUTO-MAS-Setup-{remote_version}-x64.zip"

        if source == "MirrorChyan":
            mirror_url = (
                mirror_chyan_download_url
                if mirror_chyan_download_url is not None
                else self.mirror_chyan_download_url
            )
            if mirror_url is None:
                logger.warning("MirrorChyan 未返回下载链接, 使用自建下载站")
                return f"https://data.auto-mas.top/api/v1/files/auto-mas/Release/{'beta' if 'beta' in remote_version else 'stable'}/download"
            return mirror_url

        if source == "AutoSite":
            return f"https://data.auto-mas.top/api/v1/files/auto-mas/Release/{'beta' if 'beta' in remote_version else 'stable'}/download"

        if source == "CNB":
            return f"https://cnb.cool/AUTO-MAS-Project/AUTO-MAS/-/releases/download/{remote_version}/AUTO-MAS-Setup-{remote_version}-x64.zip"

        raise ValueError(f"未知的下载源: {source}, 请检查配置文件")

    async def _refresh_mirror_download_url(self) -> None:
        """重新获取 Mirror 酱的一次性下载地址。

        Mirror 酱的下载地址用过或过期即作废, 而版本检查的四小时缓存不会刷新它,
        因此每次下载开始前都要重新获取。获取失败时清空缓存地址,
        由 `_get_download_url` 回落到自建下载站。
        """

        if self.current_version is None:
            logger.warning("尚未检查过更新, 无法刷新 Mirror 酱下载地址")
            return None

        try:
            version_info = await self._request_version_info(self.current_version)
            data = version_info.get("data")
            download_url = data.get("url") if isinstance(data, dict) else None
        except Exception as error:
            logger.warning(
                f"刷新 Mirror 酱下载地址失败: {type(error).__name__}: {error}"
            )
            self.mirror_chyan_download_url = None
            return None

        self.mirror_chyan_download_url = download_url
        if download_url is not None:
            logger.info("已刷新 Mirror 酱下载地址")

    async def _request_version_info(self, current_version: str) -> Dict[str, Any]:
        """向 Mirror 酱查询最新版本信息。

        Args:
            current_version: 本地当前版本号, 用于 Mirror 酱判定增量包。

        Returns:
            Mirror 酱返回的完整响应体。

        Raises:
            Exception: Mirror 酱返回业务错误码或无法识别的响应时抛出。
        """

        return await request_mirror_resource(
            "AUTO_MAS",
            params={
                "os": "win",
                "arch": "x64",
                "current_version": current_version,
                "cdk": Config.setting.Update.MirrorChyanCDK
                if Config.setting.Update.Source == "MirrorChyan"
                else "",
                "channel": Config.setting.Update.Channel,
            },
            proxy=Config.proxy,
            timeout=5,
        )

    async def check_update(
        self, current_version: str, if_force: bool = False
    ) -> tuple[bool, str, Dict[str, Dict[str, List[str]]]]:

        self.current_version = current_version

        # 标题栏每 10 分钟轮询一次, 非强制检查一小时内直接复用上次结果
        if not if_force and self._check_cache is not None:
            cached_version, cached_result, checked_at = self._check_cache
            if (
                cached_version == current_version
                and checked_at > datetime.now() - timedelta(hours=1)
            ):
                logger.info("一小时内已进行过一次检查, 直接使用缓存的版本更新信息")
                return cached_result

        logger.info("开始检查更新")

        version_info = await self._request_version_info(current_version)

        logger.success("获取版本信息成功")
        self.last_check_time = datetime.now()

        data = version_info.get("data")
        if not isinstance(data, dict):
            raise Exception("Mirror 酱返回的数据不完整, 请稍后重试")

        self.remote_version = data.get("version_name")
        if self.remote_version is None:
            raise Exception("Mirror 酱未返回版本号, 请稍后重试")
        self.mirror_chyan_download_url = data.get("url")

        if version.parse(self.remote_version) > version.parse(current_version):
            # 版本更新信息: 更新日志读取失败只丢日志, 不影响「需要更新」这个结论
            self.update_version_info = select_newer_version_info(
                parse_release_note(data.get("release_note")), current_version
            )

            result = (True, self.remote_version, self.update_version_info)

        else:
            result = (False, current_version, {})

        self._check_cache = (current_version, result, self.last_check_time)
        return result

    async def download_update(self, *, job: Optional[_DownloadJob] = None) -> None:

        download_job = job or self._create_download_job()

        logger.info("收到前端下载请求")

        if self.is_locked:
            await Publisher.send(
                id=protocol.ID_UPDATE,
                type=protocol.UPDATE_FAILED,
                data=WSUpdateFailedData(message="已有更新任务在进行中, 请勿重复操作"),
            )
            return None

        self.is_locked = True
        try:
            await self._download_update_locked(job=download_job)
        except asyncio.CancelledError:
            logger.info("更新下载已取消")
            raise
        except _utils_fluxdown_cli.FluxdownCancelUnconfirmed:
            # 透传给 cancel_download 的 await task：由那里按失败上报，
            # 不走通用"下载失败"路径，更不能在后台状态未知时报告取消成功
            raise
        except Exception as error:
            logger.exception(f"更新下载任务异常: {type(error).__name__}: {error}")
            await self._publish_failed(f"下载失败: {type(error).__name__}: {error}")
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

        if (Config.work_path / f"UpdatePack_{download_version}.zip").exists():
            existing_package = Config.work_path / f"UpdatePack_{download_version}.zip"
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

        async def report_progress(downloaded: int, total: int, speed: float) -> None:
            self._update_download_snapshot(
                status="downloading",
                downloaded_size=downloaded,
                file_size=total,
                speed=speed,
                source=source,
            )
            await Publisher.send(
                id=protocol.ID_UPDATE,
                type=protocol.UPDATE_PROGRESS,
                data=WSUpdateProgressData(
                    downloaded_size=downloaded,
                    file_size=total,
                    speed=speed,
                    source=source,
                ),
            )

        check_times = 3
        while check_times != 0:
            try:
                # 注意：这里不能删 download.temp —— httpx（ab+Range 追加）与
                # FluxDown server 的断点续传都以它为续传状态，删掉会让重试从头下载

                start_time = time.time()

                downloaded_size = await self._download(
                    download_url,
                    Config.work_path / "download.temp",
                    timeout=30,
                    proxy=Config.proxy,
                    progress=report_progress,
                    downloader=download_job.downloader,
                    source=download_job.source,
                )

                # 重命名临时文件为最终包
                final_path = Config.work_path / f"UpdatePack_{download_version}.zip"
                (Config.work_path / "download.temp").rename(final_path)

                logger.success(
                    f"下载完成: {download_url}, 实际下载大小: {downloaded_size} 字节, 耗时: {time.time() - start_time:.2f} 秒, 保存位置: {final_path}"
                )
                await self._publish_completed(final_path)
                self.is_locked = False
                break

            except _utils_fluxdown_cli.FluxdownCancelUnconfirmed:
                # 取消但无法确认 FluxDown 任务已停止：不是可重试的下载错误，
                # 必须退出取消流程，不能睡眠后自动 resume 状态未知的任务
                raise

            except FluxdownResumableError as e:
                # 中断类失败不自动重试：立即弹出失败，由用户点击重试发起下一次尝试
                # （同一 url+destination 走 resume 断点续传，不消耗 check_times）。
                # 用户多次重试仍失败时，错误信息内已附带改用内置 httpx 的提示
                # （由 update_fluxdown 按任务累计中断次数追加）。
                logger.warning(f"下载中断: {download_url}, 错误信息: {e}")
                await self._publish_failed(f"下载中断: {e}")
                self.is_locked = False
                return

            except Exception as e:
                if check_times != -1:
                    check_times -= 1

                logger.exception(
                    f"下载出错: {download_url}, 错误信息: {e}, 剩余重试次数: {check_times}"
                )
                await asyncio.sleep(1)

        else:
            if (Config.work_path / "download.temp").exists():
                (Config.work_path / "download.temp").unlink()
            await self._publish_failed(f"下载失败: {download_url}")
            self.is_locked = False

    async def install_update(self):

        if self.is_locked or self.is_switching_source:
            await Publisher.send(
                id=protocol.ID_UPDATE,
                type=protocol.UPDATE_FAILED,
                data=WSUpdateFailedData(message="已有更新任务在进行中, 请勿重复操作"),
            )
            return None

        logger.info("开始应用更新")
        self.is_locked = True

        versions = {
            version.parse(match.group(1)): f.name
            for f in Config.work_path.glob("UpdatePack_*.zip")
            if (match := re.match(r"UpdatePack_(.+)\.zip$", f.name))
        }
        logger.info(f"检测到的更新包: {versions.values()}")

        if not versions:
            await Publisher.send(
                id=protocol.ID_UPDATE,
                type=protocol.UPDATE_FAILED,
                data=WSUpdateFailedData(message="未检测到更新包, 请先下载更新"),
            )
            self.is_locked = False
            return None

        update_package = Config.work_path / versions[max(versions)]

        logger.info(f"开始解压: {update_package} 到 {Config.work_path}")

        try:
            with zipfile.ZipFile(update_package, "r") as zip_ref:
                await asyncio.to_thread(zip_ref.extractall, Config.work_path)
        except Exception as e:
            logger.error(f"解压失败, {type(e).__name__}: {e}")
            await Publisher.send(
                id=protocol.ID_UPDATE,
                type=protocol.UPDATE_FAILED,
                data=WSUpdateFailedData(message=f"解压失败, {type(e).__name__}: {e}"),
            )
            self.is_locked = False
            return None

        logger.success(f"解压完成: {update_package} 到 {Config.work_path}")

        logger.info("正在删除临时文件与旧更新包文件")
        if (Config.work_path / "changes.json").exists():
            (Config.work_path / "changes.json").unlink()
        for f in versions.values():
            if (Config.work_path / f).exists():
                (Config.work_path / f).unlink()

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
                Config.work_path / "AUTO-MAS-Setup.exe",
                "/SP-",
                "/SILENT",
                "/NOCANCEL",
                "/FORCECLOSEAPPLICATIONS",
                "/LANG=Chinese",
                f"/DIR={Config.work_path}",
            ],
            creationflags=process_platform.platform_process.detached_flags,
        )
        await System.set_power("KillSelf")
