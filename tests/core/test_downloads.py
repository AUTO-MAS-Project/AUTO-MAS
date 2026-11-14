"""统一下载的共享、内容身份、缓存及真实取消收尾契约。"""

import asyncio
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from app.core import Config
from app.core import downloads as host
from app.core.background_tasks import BackgroundTaskRegistry
from app.core.downloads import DownloadManager
from app.models.config import GlobalConfig
from app.models.schema import DownloadRequest
from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed
from tests.config_support import activate_config


@pytest_asyncio.fixture
async def manager(tmp_path, monkeypatch):
    """建立隔离缓存和背景任务组的真实下载管理器，测试结束后清理文件并关闭任务组。"""
    registry = BackgroundTaskRegistry()
    manager = DownloadManager()
    monkeypatch.setattr(Config, "setting", await activate_config(GlobalConfig.build()))

    async def transfer(request, path, progress):
        """把请求文件身份写入本地产物并报告完成进度，隔离真实网络而保留下载中心生命周期。"""
        path.write_text(request.rid or request.content_hash or "null")
        await progress(path.stat().st_size, path.stat().st_size, 1)

    manager.initialize(
        directory=tmp_path / "downloads",
        max_running=2,
        attempts=3,
        retry_delay=0,
        background=registry,
        transfer=transfer,
    )
    yield manager
    await manager.shutdown_all()
    assert await registry.shutdown(timeout=2)


@pytest.mark.asyncio
async def test_default_transfer_uses_host_download_and_prefetched_copy(
    monkeypatch, isolated_app_paths, tmp_path
):
    """通过下载中心默认传输取得文件，再由专项入口复制预下载产物；仅隔离 HTTP 传输和下载器工作目录。"""
    from app.services.common.update.prefetch import prefetch_paths

    monkeypatch.setattr(Config, "setting", await activate_config(GlobalConfig.build()))
    monkeypatch.setattr(
        host._utils_fluxdown_cli, "_server_data_dir", lambda _: tmp_path / "fluxdown"
    )

    async def builtin(url, destination, *, timeout, proxy=None, progress=None):
        """代替远端 HTTP 将已知文件写入真实缓存路径，报告完成进度供下载中心保存结果。"""
        destination.write_bytes(b"downloaded package")
        if progress is not None:
            await progress(18, 18, 0)
        return 18

    monkeypatch.setattr(host._service_update_fluxdown, "_httpx_download", builtin)
    registry = BackgroundTaskRegistry()
    manager = DownloadManager()
    manager.initialize(
        directory=tmp_path / "downloads",
        max_running=1,
        attempts=1,
        retry_delay=0,
        background=registry,
    )
    request = DownloadRequest(url="https://example.test/package", downloader="builtin")
    try:
        assert manager.request(request, owner="L2")
        result = await manager.wait(request)
        assert result.state == "succeeded", result
        assert result.downloaded == result.total == 18
        destination = tmp_path / "script/package"
        token = prefetch_paths.set({request.url: result.path})
        try:
            assert await host.download_file(request.url, destination, timeout=10) == 18
        finally:
            prefetch_paths.reset(token)
        assert (
            destination.read_bytes()
            == Path(result.path).read_bytes()
            == b"downloaded package"
        )
        assert await manager.release(request.url, owner="L2")
        assert Path(result.path).is_file()
    finally:
        assert await manager.shutdown_all()
        assert await registry.shutdown(timeout=2)


@pytest.mark.asyncio
async def test_shared_reference_missing_file_and_identity_change(manager):
    """验证同一使用者重复申请不增加引用，多个使用者共享结果，身份变化或文件丢失会产生新下载轮次。"""
    old = DownloadRequest(url="https://example.test/file", rid="one")
    assert manager.request(old, owner="A")
    assert manager.request(old, owner="A")
    assert manager.request(old, owner="B")
    first = await manager.wait(old)
    assert first.state == "succeeded", first
    assert await manager.release(old.url, owner="A")
    assert Path(first.path).is_file()
    changed = old.model_copy(update={"rid": "two"})
    assert manager.request(changed, owner="B")
    second = await manager.wait(changed)
    assert second.path != first.path
    assert Path(first.path).read_text() == "one"
    assert manager.query(old).path == first.path
    Path(second.path).unlink()
    assert manager.query(changed).state in {"pending", "running"}
    third = await manager.wait(changed)
    assert third.state == "succeeded"
    assert third.generation != second.generation
    assert await manager.release(old.url, owner="B")
    assert Path(third.path).is_file()


@pytest.mark.asyncio
async def test_null_identity_stable_and_cache_limit_only_removes_unused(manager):
    """验证空身份稳定复用，运行中调低配置容量后按新上限回收零引用文件，并保留使用中的产物。"""
    same = DownloadRequest(url="https://example.test/null")
    another = DownloadRequest(url="https://example.test/other")
    assert manager.request(same, owner="A")
    first = await manager.wait(same)
    assert manager.request(same, owner="A")
    assert (await manager.wait(same)).generation == first.generation
    assert manager.request(another, owner="B")
    second = await manager.wait(another)
    with Path(first.path).open("r+b") as file:
        file.truncate(256 * 1024**2)
    with Path(second.path).open("r+b") as file:
        file.truncate(1024**2)
    assert await manager.release(same.url, owner="A")
    assert Path(first.path).is_file()
    Config.setting.download.cache_mb = 256
    await Config.setting.commit()
    assert await manager.release(same.url, owner="A")
    assert not Path(first.path).exists()
    assert Path(second.path).is_file()
    assert manager.query(same).state == "not_found"


@pytest.mark.asyncio
async def test_last_release_waits_cleanup_and_waiter_cancel_does_not_cancel_download(
    manager,
):
    """验证取消等待者不会取消共享下载，最后一次释放会等待传输清理真正结束。"""
    started, stopped, finish_cleanup = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def transfer(request, path, progress):
        """模拟持续传输及受事件控制的取消清理，供检查最后一次释放是否等待停写。"""
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            await finish_cleanup.wait()
            stopped.set()

    manager._transfer = transfer
    request = DownloadRequest(url="https://example.test/pending")
    assert manager.request(request, owner="A")
    assert manager.request(request, owner="B")
    await started.wait()
    waiter = asyncio.create_task(manager.wait(request))
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert manager.query(request).state == "running"
    assert await manager.release(request.url, owner="A")
    assert not stopped.is_set()
    cleanup = asyncio.create_task(manager.release(request.url, owner="B"))
    await asyncio.sleep(0)
    assert not cleanup.done()
    assert manager.query(request).state == "cancelling"
    finish_cleanup.set()
    assert await cleanup
    assert stopped.is_set()
    assert manager.query(request).state == "cancelled"


@pytest.mark.asyncio
async def test_network_retry_permanent_failure_and_unconfirmed_writer(manager):
    """验证可恢复网络故障重试、永久错误终止，以及停写未确认时阻止释放和后续下载。"""
    calls = 0

    async def transfer(request, path, progress):
        """前两次调用模拟短暂连接故障，之后写入成功产物，供验证下载重试。"""
        nonlocal calls
        calls += 1
        if calls < 3:
            raise httpx.ConnectError("temporary")
        path.write_text("complete")

    manager._transfer = transfer
    request = DownloadRequest(url="https://example.test/retry", content_hash="abc")
    assert manager.request(request, owner="A")
    assert (await manager.wait(request)).state == "succeeded"
    assert calls == 3

    async def unsafe(request, path, progress):
        """模拟外部下载器无法确认停止写入的结果，验证中心保留阻断状态。"""
        raise FluxdownCancelUnconfirmed("still writing")

    manager._transfer = unsafe
    changed = request.model_copy(update={"content_hash": "def"})
    assert manager.request(changed, owner="A")
    result = await manager.wait(changed)
    assert result.state == "failed"
    assert result.path is None
    assert result.writer_unconfirmed
    assert not await manager.release(changed.url, owner="A")
    assert not await manager.shutdown_all()
