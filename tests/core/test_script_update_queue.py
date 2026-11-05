"""预取遵守任务成功信号、登录保护窗口和下载取消的所有权。"""

import asyncio
import uuid
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import script_update_queue as queue
from app.models.task import ScriptItem, UserItem
from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed


@pytest.fixture
def running(monkeypatch):
    monkeypatch.setattr(queue, "PREFETCH_POLL_SECONDS", 0.001)
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(queue, "time", SimpleNamespace(monotonic=lambda: clock.now))
    user = UserItem("user", "", "运行")
    script = ScriptItem("script", "", "运行", user_list=[user], current_index=0)
    return script, user, clock


async def settle():
    await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_only_prefetches_after_success_and_sixty_seconds(running):
    script, user, clock = running
    started = asyncio.Event()
    operation = AsyncMock(side_effect=started.set)
    pipeline = queue.ScriptUpdateQueue()
    pipeline.watch(script, operation)
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
@pytest.mark.parametrize("status", ["异常", "跳过", "等待"])
async def test_unhealthy_user_does_not_start_download(running, status):
    script, user, clock = running
    user.first_task_completed_at, clock.now = 100, 200
    user.status = status
    operation = AsyncMock()
    pipeline = queue.ScriptUpdateQueue()
    pipeline.watch(script, operation)
    await settle()
    await pipeline.finish()
    operation.assert_not_called()


@pytest.mark.asyncio
async def test_short_script_does_not_leave_a_timer_for_next_login(running):
    script, user, _ = running
    user.first_task_completed_at = 100
    operation = AsyncMock()
    pipeline = queue.ScriptUpdateQueue()
    pipeline.watch(script, operation)
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
    pipeline.watch(script, download)
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
    pipeline.watch(script, download)
    await asyncio.wait_for(started.wait(), 1)
    if stop == "retry":
        user.first_task_completed_at = None
    elif stop == "failure":
        user.status = "异常"
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
    pipeline.watch(script, operation)
    await settle()
    await pipeline.finish()
    assert script.status == "运行"
    operation.assert_awaited_once()


@pytest.mark.asyncio
async def test_stop_during_timer_cleanup_is_not_swallowed():
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
    finishing = asyncio.create_task(pipeline.finish())
    await cleaning.wait()
    finishing.cancel()
    await asyncio.sleep(0)
    assert not finishing.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await finishing


@pytest.mark.asyncio
@pytest.mark.parametrize("change_config", [False, True])
async def test_three_scripts_download_then_install_in_queue_order(
    monkeypatch, change_config
):
    from app.core.task_manager import manager as scheduler
    from app.models.task import TaskExecuteBase

    monkeypatch.setattr(queue, "PREFETCH_GRACE_SECONDS", 0)
    monkeypatch.setattr(queue, "PREFETCH_POLL_SECONDS", 0.001)
    ids = [uuid.uuid4() for _ in range(3)]
    configs = {}
    for uid in ids:
        config = SimpleNamespace(revision=0, is_locked=False)
        config.model_dump = lambda *, mode, config=config: {
            "Update": {"revision": config.revision}
        }
        configs[uid] = config
    monkeypatch.setattr(
        scheduler,
        "Config",
        SimpleNamespace(
            ScriptConfig=configs,
            proxy=None,
            setting=SimpleNamespace(
                Update=SimpleNamespace(model_dump=lambda **_: {}),
                Replay=SimpleNamespace(Enabled=False),
            ),
        ),
    )
    monkeypatch.setattr(scheduler, "_exclusive_resources", lambda _: ((), None))
    info = scheduler.TaskInfo("AutoProxy", "test", "queue", None, None)
    monkeypatch.setattr(info, "schedule_on_change", lambda: None)
    info.script_list = [ScriptItem(str(uid), "", "等待") for uid in ids]
    events = []
    prepared = [asyncio.Event() for _ in ids]

    class Manager(TaskExecuteBase):
        def __init__(self, item):
            super().__init__()
            self.item = item
            self.index = ids.index(uuid.UUID(item.script_id))
            self.ready = False

        async def prefetch_script_update(self):
            events.append(("download", self.index))
            self.ready = True
            if change_config and self.index == 1 and not prepared[1].is_set():
                configs[ids[1]].revision += 1
            prepared[self.index].set()

        async def main_task(self):
            if not self.ready:
                await self.prefetch_script_update()
            events.append(("install", self.index))
            user = UserItem(str(self.index), "", "运行")
            self.item.user_list = [user]
            self.item.current_index = 0
            user.mark_task_completed()
            events.append(("run", self.index))
            if self.index < 2:
                await asyncio.wait_for(prepared[self.index + 1].wait(), 1)
            events.append(("finish", self.index))
            self.item.status = "完成"

        async def final_task(self):
            pass

        async def on_crash(self, error):
            raise error

        async def discard_prefetched_update(self):
            self.ready = False

    task = scheduler.Task(
        info, [], manager_factories={SimpleNamespace: lambda item, _: Manager(item)}
    )
    monkeypatch.setattr(task, "spawn", lambda child: child.main_task())
    monkeypatch.setattr(task, "_observe_script_run", lambda *args: nullcontext())
    await task._run_script_list(0)
    for index in (1, 2):
        assert events.index(("run", index - 1)) < events.index(("download", index))
        assert events.index(("finish", index - 1)) < events.index(("install", index))
        assert events.index(("download", index)) < events.index(("install", index))
    assert events.count(("download", 1)) == (2 if change_config else 1)
    assert task._script_updates._pending is None


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
    pipeline.watch(script, download)
    await asyncio.wait_for(started.wait(), 1)
    user.status = "完成"
    script.user_list.append(UserItem("second", "", "运行"))
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
async def test_first_success_clock_survives_account_switch_before_sixty(running):
    script, user, clock = running
    script.first_task_completed_at = user.first_task_completed_at = 100
    clock.now = 130
    started = asyncio.Event()
    pipeline = queue.ScriptUpdateQueue()
    pipeline.watch(script, AsyncMock(side_effect=started.set))
    await settle()
    user.status = "完成"
    script.user_list.append(UserItem("second", "", "运行"))
    script.current_index = 1
    clock.now = 160
    await asyncio.wait_for(started.wait(), 1)
    await pipeline.finish()


@pytest.mark.parametrize("run_status", ["运行", "运行 - 日常", "运行 - 剿灭"])
def test_script_success_signal_survives_new_stage_and_resets_on_retry(
    monkeypatch, run_status
):
    from datetime import datetime

    from app.models import task as task_models
    from app.models.task import LogRecord

    user = UserItem("user", "", run_status)
    script = ScriptItem("script", "", "运行", user_list=[user])
    task_info = SimpleNamespace(
        script_list=[script],
        on_status_changed=lambda *_: None,
        schedule_on_change=lambda: None,
    )
    user._task_item_ref = lambda: task_info
    monkeypatch.setattr(task_models, "time", SimpleNamespace(monotonic=lambda: 123.0))
    user.mark_task_completed()
    assert user.first_task_completed_at == 123.0
    assert script.first_task_completed_at == 123.0

    # MaaEnd / MAA 正常切换到下一阶段并添加日志，不应取消下一脚本下载。
    user.add_log_record(datetime.now(), LogRecord(phase="NextStage"))
    assert user.first_task_completed_at == 123.0
    assert script.first_task_completed_at == 123.0

    # 只有同一阶段真正重试时，旧成功信号才会失效。
    user.add_log_record(datetime.now(), LogRecord(), retry=True)
    assert user.first_task_completed_at is None
    assert script.first_task_completed_at == 123.0

    user.status = "异常"
    user.mark_task_completed()
    assert user.first_task_completed_at is None


@pytest.mark.asyncio
async def test_new_stage_log_does_not_cancel_inflight_prefetch(running):
    from datetime import datetime

    from app.models.task import LogRecord

    script, user, clock = running
    user.first_task_completed_at = script.first_task_completed_at = 100
    clock.now = 200
    started, release = asyncio.Event(), asyncio.Event()

    async def download():
        started.set()
        await release.wait()

    pipeline = queue.ScriptUpdateQueue()
    pipeline.watch(script, download)
    await asyncio.wait_for(started.wait(), 1)
    user.add_log_record(datetime.now(), LogRecord(phase="SecondStage"))
    await settle()
    assert pipeline._download is not None
    assert not pipeline._download.done()
    assert script.first_task_completed_at == 100
    release.set()
    await pipeline.finish()


@pytest.mark.asyncio
async def test_public_update_entry_skips_next_non_runnable_item(monkeypatch):
    from app.core import script_update
    from app.models.task import TaskExecuteBase

    monkeypatch.setattr(queue, "PREFETCH_GRACE_SECONDS", 0)
    monkeypatch.setattr(queue, "PREFETCH_POLL_SECONDS", 0.001)
    script_ids = [uuid.uuid4() for _ in range(3)]
    scripts = [ScriptItem(str(uid), "", "等待") for uid in script_ids]
    user = UserItem("first", "", "运行")
    scripts[0].user_list = [user]
    scripts[0].status = "运行"
    user.first_task_completed_at = scripts[0].first_task_completed_at = 1
    configs = {
        uid: SimpleNamespace(is_locked=False, model_dump=lambda **_: {})
        for uid in script_ids
    }
    info = SimpleNamespace(
        mode="AutoProxy",
        is_cycle=False,
        script_list=scripts,
        task_id="task",
        script_user_scope=lambda script_id: (
            frozenset() if script_id == str(script_ids[1]) else None
        ),
    )
    settings = SimpleNamespace(Update=SimpleNamespace(model_dump=lambda **_: {}))
    calls = []

    class Manager(TaskExecuteBase):
        async def prefetch_script_update(self):
            calls.append("download")

        async def main_task(self): ...
        async def final_task(self): ...
        async def on_crash(self, e): ...

    session = script_update.ScriptUpdateSession(
        info,
        make_manager=lambda item, *_args, **_kwargs: (
            calls.append(item.script_id) or Manager()
        ),
        resources=lambda config: ((), None),
        scheduled=lambda _: True,
        config=SimpleNamespace(ScriptConfig=configs, setting=settings),
    )
    session.watch(scripts[0], 1)
    await settle()
    await session.finish()
    assert calls == [str(script_ids[2]), "download"]
    await session.close()


@pytest.mark.asyncio
async def test_unconfirmed_fluxdown_stop_blocks_handoff(running):
    script, user, clock = running
    user.first_task_completed_at = 100
    clock.now = 200
    started = asyncio.Event()

    async def download():
        started.set()
        raise FluxdownCancelUnconfirmed("daemon might still write")

    pipeline = queue.ScriptUpdateQueue()
    pipeline.watch(script, download)
    await asyncio.wait_for(started.wait(), 1)
    with pytest.raises(FluxdownCancelUnconfirmed):
        await pipeline.finish()


@pytest.mark.asyncio
async def test_unconfirmed_fluxdown_cancel_remains_visible():
    started = asyncio.Event()

    async def download():
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            raise FluxdownCancelUnconfirmed("daemon cannot confirm stop")

    task = asyncio.create_task(download())
    await started.wait()
    with pytest.raises(FluxdownCancelUnconfirmed):
        await queue._cancel_and_wait(task)


@pytest.mark.asyncio
async def test_second_account_retry_keeps_running_prefetch(running):
    """Account B retry does not cancel A's script-level success clock."""
    from datetime import datetime

    from app.models.task import LogRecord

    script, first, clock = running
    second = UserItem("second", "", "运行")
    script.user_list.append(second)
    parent = SimpleNamespace(
        script_list=[script],
        on_status_changed=lambda *_: None,
        schedule_on_change=lambda: None,
    )
    script._task_item_ref = lambda: parent
    first._task_item_ref = second._task_item_ref = lambda: parent
    first.first_task_completed_at = script.first_task_completed_at = 100
    clock.now = 200
    started, release = asyncio.Event(), asyncio.Event()

    async def download():
        started.set()
        await release.wait()

    pipeline = queue.ScriptUpdateQueue()
    pipeline.watch(script, download)
    await asyncio.wait_for(started.wait(), 1)
    first.status = "完成"
    script.current_index = 1
    second.add_log_record(datetime.now(), LogRecord(), retry=True)
    assert script.first_task_completed_at == 100
    await settle()
    assert pipeline._download is not None and not pipeline._download.done()
    release.set()
    await pipeline.finish()


@pytest.mark.asyncio
async def test_cycle_unconfirmed_stop_never_starts_next_entry(monkeypatch):
    """Exercise the cycle dispatcher: unsafe cancellation aborts the round."""
    from datetime import datetime

    from app.core.task_manager import manager as scheduler
    from app.core.task_manager.cycle import CycleEntry
    from app.models.config import MaaConfig

    queue_id, item_a, item_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    script_a, script_b = uuid.uuid4(), uuid.uuid4()

    class QueueItemStub:
        Data = SimpleNamespace(LastCycleStartedAt=None)
        Schedule = SimpleNamespace(IntervalAnchor="finish")

        @classmethod
        def model_validate(cls, value):
            return value

        async def update(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr(
        scheduler,
        "Config",
        SimpleNamespace(
            QueueConfig={
                queue_id: SimpleNamespace(
                    QueueItem={item_a: QueueItemStub(), item_b: QueueItemStub()}
                )
            },
            ScriptConfig={script_a: MaaConfig(), script_b: MaaConfig()},
            setting=SimpleNamespace(
                Update=SimpleNamespace(model_dump=lambda **_: {}),
                Replay=SimpleNamespace(Enabled=False),
            ),
        ),
    )
    monkeypatch.setattr(scheduler, "_exclusive_resources", lambda _: ((), None))
    info = scheduler.TaskInfo(
        "AutoProxy", "test", str(queue_id), None, None, is_cycle=True
    )
    monkeypatch.setattr(info, "schedule_on_change", lambda: None)
    info.script_list = [
        ScriptItem(str(script_a), "first", "等待"),
        ScriptItem(str(script_b), "next", "等待"),
    ]
    task = scheduler.Task(info, [], manager_factories={})
    task.stopped_manually = True
    task._exit_result = "cancelled"
    task._exit_error = "任务执行被取消"
    monkeypatch.setattr(task, "_build_task_item", lambda *_a, **_k: object())
    monkeypatch.setattr(task, "_observe_script_run", lambda *_a: nullcontext())
    monkeypatch.setattr(task, "_publish_cycle_preview", AsyncMock())
    monkeypatch.setattr(task._script_updates, "take", AsyncMock(return_value=None))
    entries = [
        CycleEntry(str(item_a), str(script_a), "first", 0, datetime.now(), True),
        CycleEntry(str(item_b), str(script_b), "next", 1, datetime.now(), True),
    ]
    monkeypatch.setattr(task, "_collect_entries", lambda *_: entries)
    started = []

    async def simulate_spawn(*_args):
        started.append(info.current_index)
        raise FluxdownCancelUnconfirmed("daemon still writing")

    monkeypatch.setattr(task, "_spawn_with_preview", simulate_spawn)
    with pytest.raises(FluxdownCancelUnconfirmed):
        await task._run_due_entries(queue_id, entries)
    assert started == [0]
    assert task._exit_result == "cancelled"
    assert "无法确认" in task._exit_error
    assert task.script_reservations.try_acquire(
        script_a, "another", root_paths=(), emulator_key=None
    )


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
    pipeline.watch(script, download_next)
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


@pytest.mark.asyncio
async def test_download_history_does_not_invalidate_prefetched_candidate(
    monkeypatch, tmp_path
):
    """A FluxDown history write during a successful prefetch is not a config edit."""
    from app.core import script_update
    from app.core import update as host
    from app.models.config import MaaConfig
    from app.models.config.setting import GlobalConfig
    from app.models.task import TaskExecuteBase
    from app.utils.common.fluxdown_cli import FluxdownDownloadRecord
    from tests.config_support import activate_config

    uid = uuid.uuid4()
    script = ScriptItem(str(uid), "test", "等待")
    config = MaaConfig.model_validate({"Info": {"Path": tmp_path}})
    setting = GlobalConfig.build()
    await activate_config(setting)
    monkeypatch.setattr(host.Config, "setting", setting)
    update_settings = setting.Update
    info = SimpleNamespace(
        mode="AutoProxy",
        is_cycle=False,
        script_list=[script],
        task_id="test",
        script_user_scope=lambda _: None,
    )
    instances = []

    class Manager(TaskExecuteBase):
        def __init__(self):
            super().__init__()
            self.discarded = False

        async def prefetch_script_update(self):
            await host._write_history(FluxdownDownloadRecord(status="success"))

        async def main_task(self): ...
        async def final_task(self): ...
        async def on_crash(self, error): ...

        async def discard_prefetched_update(self):
            self.discarded = True

    def make_manager(*_args, **_kwargs):
        instance = Manager()
        instances.append(instance)
        return instance

    session = script_update.ScriptUpdateSession(
        info,
        make_manager=make_manager,
        resources=lambda _: ((), None),
        scheduled=lambda _: True,
        config=SimpleNamespace(
            ScriptConfig={uid: config},
            setting=SimpleNamespace(Update=update_settings),
        ),
    )
    await session._prefetch(0)
    assert await session.take(0) is instances[0]
    assert not instances[0].discarded
    assert len(update_settings.LastUpdateHistory) == 1

    await session._prefetch(0)
    await setting.update(
        GlobalConfig.model_validate({"Update": {"Source": "MirrorChyan"}})
    )
    assert await session.take(0) is None
    assert instances[1].discarded


@pytest.mark.asyncio
async def test_runtime_records_do_not_invalidate_but_install_path_does(
    monkeypatch, tmp_path
):
    from app.core import script_update
    from app.models.config import MaaConfig, MaaUserConfig
    from app.models.config.setting import GlobalConfig
    from tests.config_support import activate_config

    uid = uuid.uuid4()
    config = MaaConfig.build()
    await activate_config(config)
    user_id = config.UserData.add(MaaUserConfig, payload={})
    await config.UserData.commit()
    user = config.UserData[user_id]
    manager = SimpleNamespace(
        prefetch_script_update=AsyncMock(), discard_prefetched_update=AsyncMock()
    )
    info = SimpleNamespace(
        mode="AutoProxy",
        is_cycle=False,
        script_list=[ScriptItem(str(uid), "test", "等待")],
        task_id="test",
        script_user_scope=lambda _: None,
    )
    session = script_update.ScriptUpdateSession(
        info,
        make_manager=lambda *_a, **_kw: manager,
        resources=lambda _: ((), None),
        scheduled=lambda _: True,
        config=SimpleNamespace(ScriptConfig={uid: config}, setting=GlobalConfig()),
    )
    await session._prefetch(0)
    await user.update(MaaUserConfig.model_validate({"Data": {"ProxyTimes": 1}}))
    await config.update(MaaConfig.model_validate({"Info": {"Name": "renamed"}}))
    assert await session.take(0) is manager
    manager.discard_prefetched_update.assert_not_awaited()
    await session._prefetch(0)
    await config.update(MaaConfig.model_validate({"Info": {"Path": tmp_path}}))
    assert await session.take(0) is None
    manager.discard_prefetched_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_install_setting_still_invalidates_prefetch():
    """Downloader/source policy changes must not reuse an old package."""
    from app.core import script_update
    from app.models.config.setting import GlobalConfig
    from app.models.task import TaskExecuteBase

    uid = uuid.uuid4()
    script = ScriptItem(str(uid), "test", "等待")
    script_config = SimpleNamespace(is_locked=False, model_dump=lambda **_: {})
    update_settings = GlobalConfig.UpdateFields()
    info = SimpleNamespace(
        mode="AutoProxy",
        is_cycle=False,
        script_list=[script],
        task_id="test",
        script_user_scope=lambda _: None,
    )
    discarded = []

    class Manager(TaskExecuteBase):
        async def prefetch_script_update(self): ...
        async def main_task(self): ...
        async def final_task(self): ...
        async def on_crash(self, error): ...

        async def discard_prefetched_update(self):
            discarded.append(True)

    session = script_update.ScriptUpdateSession(
        info,
        make_manager=lambda *_args, **_kwargs: Manager(),
        resources=lambda _: ((), None),
        scheduled=lambda _: True,
        config=SimpleNamespace(
            ScriptConfig={uid: script_config},
            setting=SimpleNamespace(Update=update_settings),
        ),
    )
    await session._prefetch(0)
    update_settings.FluxdownTakeoverAll = True
    assert await session.take(0) is None
    assert discarded == [True]
