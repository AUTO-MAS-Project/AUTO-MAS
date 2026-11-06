"""接管开关、下载器和网络代理是独立的公共契约。"""

import asyncio
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import script_update as update
from app.core import update as host
from app.core.task_manager.manager import TaskInfo
from app.models.config import MaaConfig
from app.models.config.setting import GlobalConfig
from app.models.task import ScriptItem
from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [asyncio.CancelledError(), FluxdownCancelUnconfirmed("unconfirmed")]
)
async def test_cancellation_is_never_hidden_or_retried(tmp_path, monkeypatch, error):
    monkeypatch.setattr(
        update,
        "Config",
        SimpleNamespace(
            proxy=None,
            setting=SimpleNamespace(Update=SimpleNamespace(FluxdownTakeoverAll=True)),
        ),
    )
    download = AsyncMock(side_effect=error)
    monkeypatch.setattr(update, "download_file", download)
    with pytest.raises(type(error)):
        await update.download_script_package(
            "https://example.invalid/package",
            tmp_path / "package",
            source="GitHub",
            timeout=20,
        )
    download.assert_awaited_once()


@pytest.fixture
def prefetch_setup(monkeypatch):
    uid = uuid.uuid4()
    info = TaskInfo(
        mode="AutoProxy", task_id="task", queue_id=None, script_id=None, user_id=None
    )
    monkeypatch.setattr(TaskInfo, "schedule_on_change", lambda _: None)
    info.script_list = [ScriptItem(str(uid), "next", "等待")]
    manager = SimpleNamespace(
        prefetch_script_update=AsyncMock(), discard_prefetched_update=AsyncMock()
    )
    setting = GlobalConfig.build()
    monkeypatch.setattr(
        host,
        "Config",
        SimpleNamespace(
            setting=setting,
            proxy=None,
            install_path=Path("."),
            resource_path=Path("."),
        ),
    )
    session = update.ScriptUpdateSession(
        info,
        make_manager=lambda *_args, **_kwargs: manager,
        resources=lambda _: ((), None),
        scheduled=lambda _: True,
        config=SimpleNamespace(ScriptConfig={uid: MaaConfig()}, setting=setting),
    )
    return session, info, manager


@pytest.mark.asyncio
async def test_common_download_reports_progress_without_adapter_changes(
    prefetch_setup, monkeypatch, tmp_path
):
    session, info, manager = prefetch_setup
    clock = SimpleNamespace(now=10.0)
    monkeypatch.setattr(update, "time", SimpleNamespace(monotonic=lambda: clock.now))
    original = AsyncMock()
    retained_observer = None

    async def transport(url, destination, *, progress, **kwargs):
        await progress(1024**2, 2 * 1024**2, 1024**2)
        await asyncio.sleep(0)
        destination.write_bytes(b"package")
        return 7

    monkeypatch.setattr(host._service_update_fluxdown, "download_file", transport)

    async def prepare():
        nonlocal retained_observer
        retained_observer = host.download_observer.get()
        assert "next" in info._prefetch_log
        assert (
            await host.download_file(
                "https://example.invalid/one.zip",
                tmp_path / "one.zip",
                timeout=20,
                progress=original,
            )
            == 7
        )
        # 高频回调不刷新展示，但调用方原有回调仍照常执行。
        first = info._prefetch_log
        assert "one.zip" in first
        clock.now += 1
        await retained_observer(tmp_path / "one.zip", 1024**2, 2 * 1024**2, 1024**2)
        assert "50.0%" in info._prefetch_log
        assert "1.0/2.0 MiB" in info._prefetch_log
        assert "1.0 MiB/s" in info._prefetch_log
        latest = info._prefetch_log
        await retained_observer(tmp_path / "one.zip", 2 * 1024**2, 2 * 1024**2, 0)
        assert info._prefetch_log == latest
        clock.now += 1
        await retained_observer(tmp_path / "two.zip", 1024**2, 0, 0)
        assert "two.zip" in info._prefetch_log
        assert "1.0 MiB" in info._prefetch_log
        assert "%" not in info._prefetch_log

    manager.prefetch_script_update.side_effect = prepare
    await session._prefetch(0)
    original.assert_awaited_once_with(1024**2, 2 * 1024**2, 1024**2)
    assert "准备完成" in info._prefetch_log
    assert host.download_observer.get() is None
    # 子任务保留的旧观察者不能在预下载结束后重新写回下载状态。
    clock.now += 1
    await retained_observer(tmp_path / "one.zip", 0, 1, 0)
    assert "准备完成" in info._prefetch_log
    assert await session.take(0) is manager
    assert info._prefetch_log == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [RuntimeError("download failed"), asyncio.CancelledError()]
)
async def test_prefetch_failure_and_cancel_release_observer(prefetch_setup, error):
    session, info, manager = prefetch_setup
    manager.prefetch_script_update.side_effect = error

    async def cleanup():
        terminal = info._prefetch_log
        observer = host.download_observer.get()
        await observer(Path("late.zip"), 1, 2, 3)
        assert info._prefetch_log == terminal

    manager.discard_prefetched_update.side_effect = cleanup
    with pytest.raises(type(error)):
        await session._prefetch(0)
    assert host.download_observer.get() is None
    assert "准备中" not in info._prefetch_log
    manager.discard_prefetched_update.assert_awaited_once()
    await session.close()
    assert info._prefetch_log == ""


@pytest.mark.asyncio
async def test_download_observers_are_isolated_between_concurrent_tasks(
    monkeypatch, tmp_path
):
    observers = [AsyncMock(), AsyncMock()]

    async def transport(url, destination, *, progress, **kwargs):
        await asyncio.sleep(0)
        if progress:
            await progress(1, 2, 3)
        return 1

    monkeypatch.setattr(host._service_update_fluxdown, "download_file", transport)
    monkeypatch.setattr(
        host,
        "Config",
        SimpleNamespace(
            setting=GlobalConfig.build(),
            install_path=tmp_path,
            resource_path=tmp_path,
        ),
    )

    async def download(index):
        token = host.download_observer.set(observers[index])
        try:
            await host.download_file(
                "https://example.invalid/package", tmp_path / str(index), timeout=20
            )
        finally:
            host.download_observer.reset(token)

    await asyncio.gather(download(0), download(1))
    for index, observer in enumerate(observers):
        assert all(
            call.args[0] == tmp_path / str(index) for call in observer.await_args_list
        )
        observer.assert_any_await(tmp_path / str(index), 1, 2, 3)
    await host.download_file(
        "https://example.invalid/manual", tmp_path / "manual", timeout=20
    )
    assert all(len(observer.await_args_list) == 2 for observer in observers)
