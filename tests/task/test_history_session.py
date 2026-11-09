"""历史会话按运行身份归属附件，OBS 服务只清理受管副本。"""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.background_tasks import BackgroundTaskRegistry
from app.models.task import LogRecord, TaskScriptItem, TaskUserItem
from app.services.common import obs_replay
from app.task import history_core
from tests.runtime_support import create_runtime_tree


@pytest.mark.asyncio
async def test_duplicate_config_runs_keep_independent_captures_and_cleanup(
    tmp_path, monkeypatch
):
    root, script, user = await create_runtime_tree()
    history = history_core.TaskHistorySession(root)
    registry = BackgroundTaskRegistry()
    monkeypatch.setattr(history_core, "BackgroundTaskManager", registry)
    monkeypatch.setattr(
        history_core,
        "Config",
        SimpleNamespace(
            setting=SimpleNamespace(Replay=SimpleNamespace(Enabled=True)),
            obs_replay_options=lambda: None,
        ),
    )
    service = obs_replay.ObsReplayService(tmp_path)
    service.directory.mkdir(parents=True)
    files = [service.directory / "one.mkv", service.directory / "two.mkv"]
    for path in files:
        path.write_bytes(b"isolated replay")
    service.capture = AsyncMock(side_effect=files)
    monkeypatch.setattr(obs_replay, "ObsReplay", service)
    sid = root.scripts.add(
        TaskScriptItem, payload={"info": {"script_id": script.script_id}}
    )
    await root.scripts.commit()
    duplicate = root.scripts[sid]
    uid = duplicate.users.add(
        TaskUserItem, payload={"info": {"user_id": user.info.user_id}}
    )
    await duplicate.users.commit()
    second = duplicate.users[uid]
    try:
        for current in (user, second):
            await current.add_log_record(datetime.now().astimezone(), LogRecord())
            await current.set_state(status="异常")
        history.begin_user_history_capture(script, user, failed=True)
        history.begin_user_history_capture(script, user, failed=True)
        history.begin_user_history_capture(duplicate, second, failed=True)
        first = await history.collect_user_history_attachments(script, user)
        other = await history.collect_user_history_attachments(duplicate, second)
        assert [entry.path for entry in first + other] == files
        assert service.capture.await_count == 2
        assert await history.collect_user_history_attachments(script, user) == []
        await history.discard_user_history_capture(script, user)
        assert not files[0].exists() and files[1].exists()
        await history.close()
        assert not files[1].exists()
    finally:
        await registry.shutdown()


@pytest.mark.asyncio
async def test_close_waits_for_pending_capture_and_keeps_obs_original(
    tmp_path, monkeypatch
):
    root, script, user = await create_runtime_tree()
    history = history_core.TaskHistorySession(root)
    registry = BackgroundTaskRegistry()
    monkeypatch.setattr(history_core, "BackgroundTaskManager", registry)
    monkeypatch.setattr(
        history_core,
        "Config",
        SimpleNamespace(
            setting=SimpleNamespace(Replay=SimpleNamespace(Enabled=True)),
            obs_replay_options=lambda: None,
        ),
    )
    service = obs_replay.ObsReplayService(tmp_path)
    entered, closed = asyncio.Event(), asyncio.Event()

    async def capture(*args):
        try:
            entered.set()
            await asyncio.Event().wait()
        finally:
            closed.set()

    service.capture = capture
    monkeypatch.setattr(obs_replay, "ObsReplay", service)
    await user.add_log_record(datetime.now().astimezone(), LogRecord())
    history.begin_user_history_capture(script, user, failed=True)
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await history.close()
        assert closed.is_set()
        original = tmp_path / "obs-original.mkv"
        original.write_bytes(b"original")
        assert not await service.discard_temporary(original)
        assert original.read_bytes() == b"original"
    finally:
        await registry.shutdown()


@pytest.mark.asyncio
async def test_expired_capture_result_keeps_file_owned_until_session_cleanup(
    tmp_path, monkeypatch
):
    root, script, user = await create_runtime_tree()
    registry = BackgroundTaskRegistry()
    monkeypatch.setattr(history_core, "BackgroundTaskManager", registry)
    monkeypatch.setattr(
        history_core,
        "Config",
        SimpleNamespace(
            setting=SimpleNamespace(Replay=SimpleNamespace(Enabled=True)),
            obs_replay_options=lambda: None,
        ),
    )
    history = history_core.TaskHistorySession(root)
    service = obs_replay.ObsReplayService(tmp_path)
    service.directory.mkdir(parents=True)
    path = service.directory / "unclaimed.mkv"
    path.write_bytes(b"temporary replay")
    service.capture = AsyncMock(return_value=path)
    monkeypatch.setattr(obs_replay, "ObsReplay", service)
    await user.add_log_record(datetime.now().astimezone(), LogRecord())
    await user.set_state(status="异常")
    history._capture_group.result_ttl = 0.01
    try:
        history.begin_user_history_capture(script, user, failed=True)
        assert await history._capture_group.drain(2)
        await asyncio.sleep(0.03)
        assert path.exists()
        # 缓存消失后也不重复采集、不将附件挂到别的执行轮次。
        assert await history.collect_user_history_attachments(script, user) == []
        assert service.capture.await_count == 1
        await history.close()
        assert not path.exists()
    finally:
        await history.close()
        await registry.shutdown()
