"""需求复查、L2 引用和只向托管节点发布成功路径。"""

import asyncio
from pathlib import Path

import pytest
from maa_adapter.config.script import MaaConfig

from app.core import Config
from app.core.background_tasks import BackgroundTaskRegistry
from app.core.downloads import DownloadManager
from app.models.schema import DownloadRequest
from app.task.prefetch import PREFETCH_PATHS_KEY, PrefetchSession
from tests.config_support import activate_config
from tests.runtime_support import create_runtime_tree


@pytest.mark.asyncio
async def test_l2_progress_does_not_replace_logs_or_advance_log_sequence(monkeypatch):
    """新 L2 进度仍使用独立字段，大段日志及后续日志增量不受进度更新和清空影响。"""
    from unittest.mock import AsyncMock

    from app.core import Publisher
    from app.core.task_manager import _TaskManager
    from app.core.ws import protocol
    from app.models.task import WSTaskPrefetchData
    from app.task.script_expander import ScriptExpander

    root, script, _ = await create_runtime_tree()
    registry = _TaskManager()
    registry._running[root.uid] = ScriptExpander(root, registry)
    monkeypatch.setattr("app.core.task_manager.TaskManager", registry)
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(Publisher, "send", sent)
    session = PrefetchSession(root, {})
    await script.set_log("x" * 200_010 + "\n")
    baseline = root.get_log_snapshot()["logSeq"]
    sent.reset_mock()
    progress = WSTaskPrefetchData(target="本轮托管", progress="50%")
    await session._set_progress(progress)
    snapshot = registry.get_runtime_snapshot().tasks[0]
    assert snapshot.task.current.prefetch == progress
    assert snapshot.logSeq == baseline
    assert snapshot.log == script.current.log
    await script.append_log("next\n")
    await session._set_progress(None)
    logs = [
        call.kwargs["data"]
        for call in sent.await_args_list
        if call.kwargs["type"] == protocol.TASK_LOG_UPDATED
    ]
    assert len(logs) == 1 and logs[0].append and logs[0].log == "next\n"
    assert root.current.prefetch is None
    assert root.get_log_snapshot()["logSeq"] == baseline + 1


@pytest.mark.asyncio
async def test_recheck_retains_old_urls_and_updates_identity_under_lock(
    monkeypatch, tmp_path
):
    """验证配置锁内复查可增加新需求和文件身份，旧 URL 保留到统一收尾，成功路径按最新需求传递。"""
    entry = await activate_config(MaaConfig.build())
    root, script, user = await create_runtime_tree(script_id=str(entry.uid))
    monkeypatch.setattr(Config, "ScriptConfig", {entry.uid: entry})
    registry = BackgroundTaskRegistry()
    downloads = DownloadManager()
    calls = []
    writing = asyncio.Event()
    continue_download = asyncio.Event()

    async def transfer(request, path, progress):
        """记录下载请求并控制旧身份传输进度，生成带身份内容的本地测试产物。"""
        calls.append(request)
        if request.rid == "v1":
            await progress(1024**2, 2 * 1024**2, 1024**2)
            writing.set()
            await continue_download.wait()
        path.write_text(request.rid or "none")

    downloads.initialize(
        directory=tmp_path / "cache",
        max_running=3,
        attempts=1,
        retry_delay=0,
        background=registry,
        transfer=transfer,
    )
    old = DownloadRequest(url="https://example.test/old", rid="v1")
    changed = old.model_copy(update={"rid": "v2"})
    added = DownloadRequest(url="https://example.test/new")
    requirements = [old]

    async def check(config):
        """确认预下载检查收到实际配置对象，并返回当前可变需求列表。"""
        assert config is entry
        return list(requirements)

    session = PrefetchSession(root, {}, downloads=downloads, check=check)
    try:
        await session.start()
        await writing.wait()

        async def progress_visible():
            """等待任务快照显示预期的下载百分比，供验证进度汇总已发布。"""
            while (
                root.current.prefetch is None
                or root.current.prefetch.progress != "50.0%"
            ):
                await asyncio.sleep(0.01)

        await asyncio.wait_for(progress_visible(), timeout=3)
        assert root.current.prefetch.status == "下载中"
        assert root.current.prefetch.package == "0/1 个文件"
        continue_download.set()
        original = await downloads.wait(old)
        requirements[:] = [changed, added]
        ticket = await entry.try_lock_x()
        assert ticket is not None
        try:
            paths = await session.prepare(script, entry)
            assert entry.is_locked
        finally:
            await entry.unlock(ticket)
        assert Path(paths[old.url]).read_text() == "v2"
        assert Path(original.path).read_text() == "v1"
        assert set(paths) == {old.url, added.url}
        assert script.info.params[PREFETCH_PATHS_KEY] == paths
        assert PREFETCH_PATHS_KEY not in user.info.params
        requirements.clear()
        assert await session.prepare(script, entry) == {}
        assert set(session.requests) == {old.url, added.url}
        await session.close()
        assert root.current.prefetch is None
        assert not downloads.list(owner=session.owner)
    finally:
        continue_download.set()
        await session.close()
        await downloads.shutdown_all()
        await registry.shutdown(timeout=2)


@pytest.mark.asyncio
async def test_failed_download_publishes_no_path(monkeypatch, tmp_path):
    """验证永久失败的预下载不会向后续专项传入文件路径。"""
    entry = await activate_config(MaaConfig.build())
    root, script, _ = await create_runtime_tree(script_id=str(entry.uid))
    monkeypatch.setattr(Config, "ScriptConfig", {entry.uid: entry})
    registry = BackgroundTaskRegistry()
    downloads = DownloadManager()

    async def transfer(*args):
        """模拟不可恢复的下载产物错误，驱动预下载失败分支。"""
        raise ValueError("invalid artifact")

    downloads.initialize(
        directory=tmp_path / "cache",
        max_running=1,
        attempts=1,
        retry_delay=0,
        background=registry,
        transfer=transfer,
    )

    async def check(_):
        """返回一个固定失败文件需求，供验证路径映射的失败隔离。"""
        return [DownloadRequest(url="https://example.test/fails")]

    session = PrefetchSession(root, {}, downloads=downloads, check=check)
    try:
        await session.start()
        assert await session.prepare(script, entry) == {}
        assert script.info.params[PREFETCH_PATHS_KEY] == {}
        await session.close()
    finally:
        await downloads.shutdown_all()
        await registry.shutdown(timeout=2)
