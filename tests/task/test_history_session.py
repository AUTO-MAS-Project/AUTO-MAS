"""历史会话按运行身份归属附件，OBS 服务只清理受管副本。"""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.background_tasks import BackgroundTaskRegistry
from app.models.task import LogRecord, TaskItem, TaskScriptItem, TaskUserItem
from app.services.common import obs_replay
from app.task import history_core


@pytest.mark.asyncio
async def test_capture_session_owns_each_run_until_archive_or_cancelled_cleanup(
    tmp_path, monkeypatch
):
    root = TaskItem()
    await root.activate()
    script_id = root.scripts.add(
        TaskScriptItem, payload={"info": {"script_id": "script", "name": "Script"}}
    )
    await root.scripts.commit()
    script = root.scripts[script_id]
    user_id = script.users.add(
        TaskUserItem, payload={"info": {"user_id": "user", "name": "User"}}
    )
    await script.users.commit()
    user = script.users[user_id]
    await root.set_current_index(0)
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
    files = [
        service.directory / name for name in ("one.mkv", "two.mkv", "unclaimed.mkv")
    ]
    for path in files:
        path.write_bytes(b"isolated replay")
    entered, closed = asyncio.Event(), asyncio.Event()
    remaining = iter(files)

    async def capture(*args):
        path = next(remaining, None)
        if path is not None:
            return path
        try:
            entered.set()
            await asyncio.Event().wait()
        finally:
            closed.set()

    service.capture = AsyncMock(side_effect=capture)
    monkeypatch.setattr(obs_replay, "ObsReplay", service)

    async def duplicate_run():
        sid = root.scripts.add(
            TaskScriptItem, payload={"info": {"script_id": script.script_id}}
        )
        await root.scripts.commit()
        duplicate = root.scripts[sid]
        uid = duplicate.users.add(
            TaskUserItem, payload={"info": {"user_id": user.info.user_id}}
        )
        await duplicate.users.commit()
        return duplicate, duplicate.users[uid]

    duplicate, second = await duplicate_run()
    unclaimed_script, unclaimed = await duplicate_run()
    pending_script, pending = await duplicate_run()
    try:
        for current in (user, second, unclaimed, pending):
            await current.add_log_record(datetime.now().astimezone(), LogRecord())
            await current.set_state(status="异常")
        history.begin_user_history_capture(script, user, failed=True)
        history.begin_user_history_capture(script, user, failed=True)
        history.begin_user_history_capture(duplicate, second, failed=True)
        first = await history.collect_user_history_attachments(script, user)
        other = await history.collect_user_history_attachments(duplicate, second)
        assert [entry.path for entry in first + other] == files[:2]
        assert service.capture.await_count == 2
        assert await history.collect_user_history_attachments(script, user) == []
        await history.discard_user_history_capture(script, user)
        assert not files[0].exists() and files[1].exists()
        history._capture_group.result_ttl = 0.01
        history.begin_user_history_capture(unclaimed_script, unclaimed, failed=True)
        assert await history._capture_group.drain(2)
        await asyncio.sleep(0.03)
        assert files[2].exists()
        assert (
            await history.collect_user_history_attachments(unclaimed_script, unclaimed)
            == []
        )
        assert service.capture.await_count == 3
        history.begin_user_history_capture(pending_script, pending, failed=True)
        await asyncio.wait_for(entered.wait(), 2)
        await history.close()
        assert closed.is_set()
        original = tmp_path / "obs-original.mkv"
        original.write_bytes(b"original")
        assert not await service.discard_temporary(original)
        assert original.read_bytes() == b"original"
        assert all(not path.exists() for path in files)
        assert service.capture.await_count == 4
    finally:
        await history.close()
        await registry.shutdown()


@pytest.mark.asyncio
async def test_capture_session_uses_registered_failure_video_services(
    tmp_path, monkeypatch
):
    """插件已登记时，失败回放由插件配置控制，旧 Replay 开关不再阻挡采集。"""

    root = TaskItem()
    await root.activate()
    script_id = root.scripts.add(
        TaskScriptItem, payload={"info": {"script_id": "script", "name": "Script"}}
    )
    await root.scripts.commit()
    script = root.scripts[script_id]
    user_id = script.users.add(
        TaskUserItem, payload={"info": {"user_id": "user", "name": "User"}}
    )
    await script.users.commit()
    user = script.users[user_id]
    await user.add_log_record(datetime.now().astimezone(), LogRecord())
    await user.set_state(status="异常")

    capture_path = tmp_path / "plugin-replay.mkv"
    capture_path.write_bytes(b"plugin replay")
    calls: list[object] = []

    async def capture(*, temporary_copy=True):
        calls.append(temporary_copy)
        return capture_path

    async def discard(path):
        calls.append(path)
        path.unlink(missing_ok=True)
        return True

    providers = {
        history_core.FAILURE_VIDEO_ENABLED: lambda: True,
        history_core.FAILURE_VIDEO_CAPTURE: capture,
        history_core.FAILURE_VIDEO_DISCARD: discard,
    }
    monkeypatch.setattr(
        history_core,
        "_plugin_services",
        lambda: SimpleNamespace(get=providers.get),
    )
    monkeypatch.setattr(
        history_core,
        "Config",
        SimpleNamespace(setting=SimpleNamespace(Replay=SimpleNamespace(Enabled=False))),
    )
    registry = BackgroundTaskRegistry()
    monkeypatch.setattr(history_core, "BackgroundTaskManager", registry)
    history = history_core.TaskHistorySession(root)
    try:
        history.begin_user_history_capture(script, user, failed=True)
        attachments = await history.collect_user_history_attachments(script, user)
        assert [item.path for item in attachments] == [capture_path]
        await history.discard_user_history_capture(script, user)
        assert calls == [True, capture_path]
        assert not capture_path.exists()
    finally:
        await history.close()
        await registry.shutdown()
