"""统一下载业务：宿主传输、历史与进度，以及 URL 引用、内容身份、可查询结果和缓存管理。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from uuid import uuid4

import httpx

from app.config import config_manager
from app.core import Config
from app.core.background_tasks import (
    BackgroundTaskGroup,
    BackgroundTaskHandle,
    BackgroundTaskManager,
    BackgroundTaskRegistry,
    BackgroundTaskState,
    TaskOutcome,
)
from app.models.config.setting import FluxdownRecord
from app.models.schema import DownloadRequest, DownloadSnapshot
from app.services.common.update import fluxdown as _service_update_fluxdown
from app.services.common.update import transport as _service_update_transport
from app.utils import fluxdown_cli as _utils_fluxdown_cli
from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed
from app.utils.common.update_files import native_path

type Progress = Callable[[int, int, float], Awaitable[None]]
type Transfer = Callable[[DownloadRequest, Path, Progress], Awaitable[None]]


DownloadObserver = Callable[[Path, int, int, float], None]
# 只由预下载作用域设置；各下载任务继承自己的观察者，不影响其他队列或手动更新。
download_observer: ContextVar[DownloadObserver | None] = ContextVar(
    "download_observer", default=None
)


download_method: ContextVar[str] = ContextVar("download_method", default="httpx")


async def _write_history(record: _utils_fluxdown_cli.FluxdownDownloadRecord) -> None:
    """串行追加历史并保留最近 50 条，复制列表后整体提交。"""
    # 读、改、提交共用配置事务，避免并发下载覆盖历史，也不持线程锁等待异步提交。
    async with config_manager.transaction():
        # 旧版本记录也去除 userinfo，避免下次保存继续保留历史代理凭据。
        history = [
            FluxdownRecord(
                **_utils_fluxdown_cli.FluxdownDownloadRecord(
                    **item.model_dump()
                ).to_dict()
            )
            for item in (Config.setting.Update.LastUpdateHistory or [])
        ]
        history.append(FluxdownRecord(**record.to_dict()))
        await Config.setting.update(
            type(Config.setting).model_validate(
                {"Update": {"LastUpdateHistory": history[-50:]}}
            ),
            check_visibility=False,
        )


async def download_file(
    url: str,
    destination: Path,
    *,
    timeout: float,
    proxy: httpx.Proxy | None = None,
    progress: _service_update_transport.DownloadProgress | None = None,
    downloader: str | None = None,
    source: str | None = None,
    http_download: _service_update_transport.BuiltinDownload | None = None,
) -> int:
    """复用当前任务的预下载产物，或按宿主配置传输文件；保留来源与下载器覆盖并记录历史和进度。"""
    from app.services.common.update.prefetch import copy_prefetched

    if await copy_prefetched(url, destination):
        size = destination.stat().st_size
        if progress is not None:
            await progress(size, size, 0.0)
        return size
    observer = download_observer.get()
    actual_method = "FluxDown"
    if observer is not None:
        original_progress = progress

        async def report(downloaded: int, total: int, speed: float) -> None:
            """向原调用方与当前任务的观察者报告进度，并隔离实际下载器上下文。"""
            if original_progress is not None:
                await original_progress(downloaded, total, speed)
            token = download_method.set(actual_method)
            try:
                observer(destination, downloaded, total, speed)
            finally:
                download_method.reset(token)

        progress = report
        original_http_download = (
            http_download or _service_update_transport.download_file
        )

        async def observed_http_download(
            url, destination, *, timeout, proxy=None, progress=None
        ):
            """HTTP 回退时切换实际下载器标识，报告开始状态并执行内置传输。"""
            nonlocal actual_method
            actual_method = "httpx"
            token = download_method.set(actual_method)
            try:
                observer(destination, 0, 0, 0.0)
            finally:
                download_method.reset(token)
            return await original_http_download(
                url, destination, timeout=timeout, proxy=proxy, progress=progress
            )

        http_download = observed_http_download
    update = Config.setting.Update
    return await _service_update_fluxdown.download_file(
        url,
        destination,
        timeout=timeout,
        proxy=proxy,
        progress=progress,
        downloader=downloader,
        source=source,
        http_download=http_download,
        options=_service_update_fluxdown.FluxdownOptions(
            downloader=update.Downloader,
            source=str(update.Source or ""),
            cli_path=str(update.FluxdownPath or ""),
            segments=int(update.FluxdownSegments),
            server_mode=bool(update.FluxdownServerMode),
            cli_search_dirs=(
                Config.install_path / "res" / "fluxdown-cli",
                Config.resource_path / "fluxdown-cli",
            ),
        ),
        write_history=_write_history,
    )


@dataclass
class _Artifact:
    request: DownloadRequest
    path: Path
    snapshot: DownloadSnapshot
    handle: BackgroundTaskHandle[None] | None = None
    error: BaseException | None = None


@dataclass
class _Entry:
    owners: set[str] = field(default_factory=set)
    artifacts: dict[tuple[str, str | None], _Artifact] = field(default_factory=dict)
    retired: list[_Artifact] = field(default_factory=list)
    touched: float = field(default_factory=monotonic)


async def _transfer(request: DownloadRequest, path: Path, progress: Progress) -> None:
    """按请求指定的下载渠道和宿主代理下载到目标文件，通过回调上报传输进度。"""
    await download_file(
        request.url,
        path,
        timeout=60,
        proxy=Config.proxy,
        progress=progress,
        downloader=request.downloader or "fluxdown",
        source="",
    )


class DownloadManager:
    """受理不排队；调用方等待容量，完成消费者在结果过期前同步接管状态。"""

    def __init__(self) -> None:
        """建立下载条目、后台任务组和缓存策略的初始状态，等待宿主显式初始化。"""
        self._entries: dict[str, _Entry] = {}
        self._group: BackgroundTaskGroup | None = None
        self._background: BackgroundTaskRegistry | None = None
        self._root: Path | None = None
        self._transfer: Transfer = _transfer
        self._attempts = 1
        self._retry_delay = 0.0
        self._closing = False

    def initialize(
        self,
        *,
        directory: Path,
        max_running: int,
        attempts: int,
        retry_delay: float,
        background: BackgroundTaskRegistry = BackgroundTaskManager,
        transfer: Transfer = _transfer,
    ) -> None:
        """配置缓存目录与重试策略，向背景任务管理器申请受并发限制的下载任务组。"""
        if self._group is not None:
            raise RuntimeError("下载中心已初始化")
        if attempts < 1 or retry_delay < 0:
            raise ValueError("下载重试配置无效")
        self._root = Path(native_path(directory.resolve(), force=True))
        self._root.mkdir(parents=True, exist_ok=True)
        self._attempts = attempts
        self._retry_delay = retry_delay
        self._background = background
        self._transfer = transfer
        self._group = background.register_group(
            "downloads", max_running=max_running, max_retained=max_running
        )

    @property
    def closing(self) -> bool:
        """返回下载中心是否已停止受理新请求，供调用方结束重试等待。"""
        return self._closing

    def request(self, request: DownloadRequest, *, owner: str) -> bool:
        """按 URL 和文件身份复用或新建下载，成功受理后登记使用者；产物丢失时重新下载，容量忙时返回 False。"""
        if self._closing:
            raise RuntimeError("download_manager_closed")
        if self._group is None or self._root is None:
            raise RuntimeError("下载中心未初始化")
        entry = self._entries.get(request.url)
        if entry is not None and any(
            item.snapshot.writer_unconfirmed
            for item in [*entry.artifacts.values(), *entry.retired]
        ):
            raise FluxdownCancelUnconfirmed("download_writer_unconfirmed")
        artifact = entry.artifacts.get(request.identity) if entry else None
        if artifact is not None:
            if artifact.snapshot.writer_unconfirmed:
                raise FluxdownCancelUnconfirmed("download_writer_unconfirmed")
            if artifact.snapshot.state == "cancelling":
                return False
            if artifact.snapshot.state == "succeeded" and not artifact.path.is_file():
                artifact.snapshot.state = "pending"
                artifact.snapshot.path = None
            if artifact.handle is not None or artifact.snapshot.state == "succeeded":
                assert entry is not None
                entry.owners.add(owner)
                entry.touched = monotonic()
                return True
        entry = entry or _Entry()
        artifact = self._start(request, entry)
        if artifact is None:
            return False
        entry.owners.add(owner)
        entry.touched = monotonic()
        self._entries[request.url] = entry
        return True

    def _start(self, request: DownloadRequest, entry: _Entry) -> _Artifact | None:
        """为指定文件身份建立独立下载轮次和路径，提交背景任务；未被受理时不修改现有产物记录。"""
        assert self._root is not None and self._group is not None
        generation = uuid4().hex
        url_key = hashlib.sha256(request.url.encode()).hexdigest()
        kind, identity = request.identity
        identity_key = hashlib.sha256(json.dumps(request.identity).encode()).hexdigest()
        path = Path(
            native_path(self._root / url_key / f"{kind}-{identity_key}-{generation}")
        )
        artifact = _Artifact(
            request,
            path,
            DownloadSnapshot(
                url=request.url,
                identity_type=kind,
                identity=identity,
                generation=generation,
                state="pending",
            ),
        )
        handle = self._group.spawn(lambda: self._run(artifact))
        if handle is None:
            return None
        old = entry.artifacts.get(request.identity)
        if old is not None:
            entry.retired.append(old)
        entry.artifacts[request.identity] = artifact
        artifact.handle = handle
        handle.add_done_callback(lambda done: self._complete(artifact, done))
        return artifact

    async def _run(self, artifact: _Artifact) -> None:
        """执行文件传输并更新进度，对可恢复的网络错误按退避策略重试，永久失败交由完成回调记录。"""
        from app.services.common.update.fluxdown import FluxdownResumableError

        async def progress(downloaded: int, total: int, speed: float) -> None:
            """将传输回调中的已下载字节、总量和速度写入本轮下载快照。"""
            artifact.snapshot.downloaded = downloaded
            artifact.snapshot.total = total
            artifact.snapshot.speed = speed

        artifact.path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(self._attempts):
            artifact.snapshot.state = "running"
            try:
                await self._transfer(artifact.request, artifact.path, progress)
                if not artifact.path.is_file():
                    raise FileNotFoundError("下载完成但文件不存在")
                return
            except (
                httpx.TransportError,
                httpx.HTTPStatusError,
                FluxdownResumableError,
            ) as error:
                if (
                    isinstance(error, httpx.HTTPStatusError)
                    and error.response.status_code < 500
                    and error.response.status_code not in {408, 425, 429}
                ):
                    raise
                if attempt + 1 == self._attempts:
                    raise
                artifact.error = error
                artifact.snapshot.state = "retrying"
                await asyncio.sleep(self._retry_delay * (2**attempt))

    def _complete(
        self, artifact: _Artifact, handle: BackgroundTaskHandle[None]
    ) -> None:
        """消费背景任务结果，记录成功、取消或失败状态及可用路径，然后按缓存容量执行回收。"""
        outcome = handle.group.try_take(handle)
        assert isinstance(outcome, TaskOutcome)
        artifact.error = outcome.error
        artifact.handle = None
        artifact.snapshot.error_code = (
            type(outcome.error).__name__ if outcome.error else None
        )
        artifact.snapshot.writer_unconfirmed = isinstance(
            outcome.error, FluxdownCancelUnconfirmed
        )
        artifact.snapshot.state = (
            "succeeded"
            if outcome.state == BackgroundTaskState.SUCCEEDED
            else "cancelled"
            if outcome.state == BackgroundTaskState.CANCELLED
            else "failed"
        )
        artifact.snapshot.path = (
            str(artifact.path) if artifact.snapshot.state == "succeeded" else None
        )

        self._evict()

    def query(self, request: DownloadRequest) -> DownloadSnapshot:
        """返回指定文件身份的状态副本；成功文件已丢失且仍有使用者时，尝试补交下载。"""
        entry = self._entries.get(request.url)
        artifact = entry.artifacts.get(request.identity) if entry else None
        if artifact is None:
            kind, identity = request.identity
            return DownloadSnapshot(
                url=request.url,
                identity_type=kind,
                identity=identity,
                state="not_found",
            )
        assert entry is not None
        if artifact.snapshot.state == "succeeded" and not artifact.path.is_file():
            artifact.snapshot.path = None
            artifact.snapshot.state = "pending"
        if (
            artifact.snapshot.state == "pending"
            and artifact.handle is None
            and entry.owners
            and not self._closing
        ):
            replacement = self._start(request, entry)
            if replacement is not None:
                artifact = replacement
        return artifact.snapshot.model_copy(deep=True)

    async def wait(self, request: DownloadRequest) -> DownloadSnapshot:
        """等待本轮下载得到终态快照；完成文件丢失时继续等待补下载，中心关闭或引用释放后结束等待。"""
        while True:
            snapshot = self.query(request)
            if snapshot.state not in {"pending", "running", "retrying", "cancelling"}:
                return snapshot
            entry = self._entries[request.url]
            artifact = entry.artifacts[request.identity]
            if artifact.handle is not None:
                await artifact.handle.wait_done()
                # 绑定本次执行，其他需求的新轮次不会替换这个结果。
                if (
                    artifact.snapshot.state == "succeeded"
                    and not artifact.path.is_file()
                ):
                    continue
                return artifact.snapshot.model_copy(deep=True)
            if not entry.owners or self._closing:
                return snapshot.model_copy(update={"state": "cancelled"})
            await asyncio.sleep(1)

    def list(self, *, owner: str | None = None) -> list[DownloadSnapshot]:
        """按可选使用者筛选当前下载，逐条检查文件可用性后返回状态快照。"""
        requests = [
            artifact.request
            for entry in tuple(self._entries.values())
            if owner is None or owner in entry.owners
            for artifact in tuple(entry.artifacts.values())
        ]
        return [self.query(request) for request in requests]

    async def release(self, url: str, *, owner: str) -> bool:
        """释放使用者的 URL 引用，最后一次释放时取消全部未完成轮次；停写确认后再按容量回收缓存。"""
        entry = self._entries.get(url)
        if entry is None:
            return True
        entry.owners.discard(owner)
        if entry.owners:
            return True
        artifacts = [*entry.artifacts.values(), *entry.retired]
        for artifact in artifacts:
            if artifact.handle is not None:
                artifact.snapshot.state = "cancelling"
                artifact.handle.cancel()
        for artifact in artifacts:
            if artifact.handle is not None:
                await artifact.handle.wait_done()
        if any(item.snapshot.writer_unconfirmed for item in artifacts):
            return False
        entry.touched = monotonic()
        self._evict()
        return True

    def _evict(self) -> None:
        """直接读取当前配置的 MB 容量上限，超限时按最近使用时间回收零引用且已停写的文件及条目。"""

        def size(entry: _Entry) -> int:
            """统计同一 URL 当前与历史轮次仍存在的缓存文件总字节数。"""
            return sum(
                artifact.path.stat().st_size
                for artifact in [*entry.artifacts.values(), *entry.retired]
                if artifact.path.is_file()
            )

        total = sum(size(entry) for entry in self._entries.values())
        for url, entry in sorted(
            tuple(self._entries.items()), key=lambda item: item[1].touched
        ):
            if total <= Config.setting.download.cache_mb * 1024**2:
                break
            if entry.owners or any(
                artifact.handle is not None or artifact.snapshot.writer_unconfirmed
                for artifact in [*entry.artifacts.values(), *entry.retired]
            ):
                continue
            removed = size(entry)
            for artifact in [*entry.artifacts.values(), *entry.retired]:
                artifact.path.unlink(missing_ok=True)
            del self._entries[url]
            total -= removed

    def seal(self) -> None:
        """关闭新下载受理入口，让申请重试与补下载流程停止继续提交任务。"""
        self._closing = True

    async def shutdown_all(self) -> bool:
        """退出时关闭受理、取消并等待全部下载；确认停写后删除所有缓存并注销背景任务组。"""
        self.seal()
        artifacts = [
            artifact
            for entry in self._entries.values()
            for artifact in [*entry.artifacts.values(), *entry.retired]
        ]
        for artifact in artifacts:
            if artifact.handle is not None:
                artifact.snapshot.state = "cancelling"
                artifact.handle.cancel()
        for artifact in artifacts:
            if artifact.handle is not None:
                await artifact.handle.wait_done()
        if any(artifact.snapshot.writer_unconfirmed for artifact in artifacts):
            return False
        if self._root is not None:
            try:
                shutil.rmtree(self._root)
            except FileNotFoundError:
                pass
        self._entries.clear()
        if self._group is not None and self._background is not None:
            await self._background.unregister_group(self._group)
        return True


Downloads = DownloadManager()
