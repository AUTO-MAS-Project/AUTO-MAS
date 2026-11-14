"""预取遵守任务成功信号、登录保护窗口和下载取消的所有权。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import script_update_queue as queue


def _user_state(user_id, name, status):
    return SimpleNamespace(
        user_id=user_id, name=name, status=status, first_task_completed_at=None
    )


def _script_state(script_id, name, status, user_list=None, current_index=-1):
    return SimpleNamespace(
        script_id=script_id,
        name=name,
        status=status,
        user_list=user_list or [],
        current_index=current_index,
        first_task_completed_at=None,
    )


@pytest.fixture
def running(monkeypatch):
    monkeypatch.setattr(queue, "PREFETCH_POLL_SECONDS", 0.001)
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(queue, "time", SimpleNamespace(monotonic=lambda: clock.now))
    user = _user_state("user", "", "运行")
    script = _script_state("script", "", "运行", user_list=[user], current_index=0)
    return script, user, clock


async def settle():
    await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_only_prefetches_after_success_and_sixty_seconds(running):
    script, user, clock = running
    started = asyncio.Event()
    operation = AsyncMock(side_effect=started.set)
    pipeline = queue.ScriptUpdateQueue()
    pipeline.watch(
        script,
        operation,
        completed_at=lambda: (
            script.first_task_completed_at
            or (user.first_task_completed_at if user.status == "运行" else None)
        ),
    )
    await settle()
    operation.assert_not_called()
    user.first_task_completed_at = 100
    clock.now = 159.9
    await settle()
    operation.assert_not_called()
    clock.now = 160
    await asyncio.wait_for(started.wait(), 1)
    await pipeline.finish()
    operation.assert_awaited_once()


@pytest.mark.asyncio
async def test_short_script_does_not_leave_a_timer_for_next_login(running):
    script, user, _ = running
    user.first_task_completed_at = 100
    operation = AsyncMock()
    pipeline = queue.ScriptUpdateQueue()
    pipeline.watch(
        script,
        operation,
        completed_at=lambda: (
            script.first_task_completed_at
            or (user.first_task_completed_at if user.status == "运行" else None)
        ),
    )
    await settle()
    await pipeline.finish()
    operation.assert_not_called()


@pytest.mark.asyncio
async def test_normal_finish_waits_for_inflight_download(running):
    script, user, clock = running
    user.first_task_completed_at, clock.now = 100, 200
    started, release = asyncio.Event(), asyncio.Event()

    async def download():
        started.set()
        await release.wait()

    pipeline = queue.ScriptUpdateQueue()
    pipeline.watch(
        script,
        download,
        completed_at=lambda: (
            script.first_task_completed_at or user.first_task_completed_at
        ),
    )
    await asyncio.wait_for(started.wait(), 1)
    script.status = "完成"
    finishing = asyncio.create_task(pipeline.finish())
    await settle()
    assert not finishing.done()
    release.set()
    await asyncio.wait_for(finishing, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("stop", ["cancel", "retry", "failure"])
async def test_cancellation_waits_for_download_cleanup(running, stop):
    script, user, clock = running
    user.first_task_completed_at, clock.now = 100, 200
    started, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def download():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()

    pipeline = queue.ScriptUpdateQueue()
    pipeline.watch(
        script,
        download,
        completed_at=lambda: (
            script.first_task_completed_at or user.first_task_completed_at
        ),
    )
    await asyncio.wait_for(started.wait(), 1)
    if stop == "retry":
        user.first_task_completed_at = None
    elif stop == "failure":
        script.status = "异常"
    finishing = asyncio.create_task(pipeline.finish(cancelled=stop == "cancel"))
    await asyncio.wait_for(cleaning.wait(), 1)
    assert not finishing.done()
    release.set()
    await asyncio.wait_for(finishing, 1)


@pytest.mark.asyncio
async def test_failed_prefetch_does_not_fail_current_script(running):
    script, user, clock = running
    user.first_task_completed_at, clock.now = 100, 200
    operation = AsyncMock(side_effect=RuntimeError("offline"))
    pipeline = queue.ScriptUpdateQueue()
    pipeline.watch(
        script,
        operation,
        completed_at=lambda: (
            script.first_task_completed_at
            or (user.first_task_completed_at if user.status == "运行" else None)
        ),
    )
    await settle()
    await pipeline.finish()
    assert script.status == "运行"
    operation.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_stop_during_timer_cleanup_is_not_swallowed(cancelled):
    cleaning, release = asyncio.Event(), asyncio.Event()

    async def timer():
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()

    pipeline = queue.ScriptUpdateQueue()
    pipeline._watcher = asyncio.create_task(timer())
    await asyncio.sleep(0)
    finishing = asyncio.create_task(pipeline.finish(cancelled=cancelled))
    await cleaning.wait()
    finishing.cancel()
    await asyncio.sleep(0)
    assert not finishing.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await finishing


@pytest.mark.asyncio
async def test_account_switch_keeps_prefetch_and_avoids_second_download(running):
    script, user, clock = running
    script.first_task_completed_at = user.first_task_completed_at = 100
    clock.now = 200
    started, release = asyncio.Event(), asyncio.Event()
    count = 0

    async def download():
        nonlocal count
        count += 1
        started.set()
        await release.wait()

    pipeline = queue.ScriptUpdateQueue()
    pipeline.watch(
        script,
        download,
        completed_at=lambda: (
            script.first_task_completed_at or user.first_task_completed_at
        ),
    )
    await asyncio.wait_for(started.wait(), 1)
    user.status = "完成"
    script.user_list.append(_user_state("second", "", "运行"))
    script.current_index = 1
    await settle()
    assert count == 1
    assert pipeline._download is not None and not pipeline._download.done()
    script.status = "完成"
    finishing = asyncio.create_task(pipeline.finish())
    await settle()
    assert not finishing.done()
    release.set()
    await asyncio.wait_for(finishing, 1)
    assert count == 1


@pytest.mark.asyncio
async def test_unconfirmed_daemon_from_real_service_blocks_next_script(
    running, tmp_path, monkeypatch
):
    """Status/pause failure must reach the queue and abort the script handoff."""
    from app.services.common.update import fluxdown as transport
    from app.utils.common import fluxdown_cli as cli

    script, user, clock = running
    user.first_task_completed_at = 100
    clock.now = 200
    exe, target = tmp_path / "fluxdown.exe", tmp_path / "next.zip"
    url = "https://example.invalid/next.zip"
    monkeypatch.setattr(cli, "_server_data_dir", lambda _exe: tmp_path)
    monkeypatch.setattr(
        cli,
        "fluxdown_server_ensure",
        lambda _exe: SimpleNamespace(gateway_port=12345, token="test"),
    )
    monkeypatch.setattr(cli, "fluxdown_find_cli", lambda *_a, **_kw: exe)
    monkeypatch.setattr(cli, "fluxdown_server_available", lambda *_a, **_kw: True)
    monkeypatch.setattr(cli, "_run_cli", lambda *_a, **_kw: (124, "timeout"))
    cli._map_put(exe, cli._map_key(url, target), "active", url, target)
    options = transport.FluxdownOptions("fluxdown", "GitHub", str(exe), 8, True)
    operation_started = asyncio.Event()

    async def download_next():
        operation_started.set()
        await transport.download_file(
            url, target, timeout=30, options=options, source="GitHub"
        )

    pipeline = queue.ScriptUpdateQueue()
    pipeline.watch(
        script, download_next, completed_at=lambda: user.first_task_completed_at
    )
    await asyncio.wait_for(operation_started.wait(), 1)
    next_script_started = False

    async def handoff():
        nonlocal next_script_started
        await pipeline.finish()
        next_script_started = True

    with pytest.raises(transport.FluxdownWriterUnconfirmed):
        await handoff()
    assert not next_script_started
    assert cli._load_task_map(exe)[cli._map_key(url, target)]["task_id"] == "active"
