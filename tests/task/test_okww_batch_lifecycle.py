"""批次账号准入、跨日计数与异常收尾回归。"""

import asyncio
import importlib
import json
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app.core.background_tasks import BackgroundTaskRegistry
from app.models.config.script import OkwwConfig, OkwwUserConfig
from app.models.task import LogRecord, UserItem
from app.task import history_core
from app.task.Okww.AutoProxy import AutoProxyTask
from app.task.Okww.BatchProxy import BatchProxyTask
from app.task.Okww.manager import OkwwManager
from app.utils import constants
from tests.config_support import activate_config
from tests.runtime_support import RuntimeStub
from tests.support.history import store as store


@pytest.fixture
def okww_installation(tmp_path, monkeypatch):
    module = importlib.import_module("app.task.Okww.AutoProxy")
    work = tmp_path / "mas"
    work.mkdir()
    monkeypatch.chdir(work)
    root = tmp_path / "okww"
    native = root / "data/apps/ok-ww/working/configs"
    native.mkdir(parents=True)
    (native / "DailyTask.json").write_text('{"original":true}', encoding="utf-8")
    log = native.parent / "logs/ok-script.log"
    log.parent.mkdir()
    log.touch()
    (root / "ok-ww.exe").touch()
    (root / "data/apps/ok-ww/app.json").write_text(
        '{"current_version":"unknown"}', encoding="utf-8"
    )
    monkeypatch.setattr(
        module,
        "ProcessManager",
        lambda: SimpleNamespace(
            is_running=AsyncMock(return_value=False), kill=AsyncMock(return_value=True)
        ),
    )
    monkeypatch.setattr(module.process, "kill_process", AsyncMock(return_value=True))
    monkeypatch.setattr(
        module.process, "is_process_stopped", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(module, "is_process_alive", lambda *args: False)
    monkeypatch.setattr(module, "find_client_pids", lambda *args: [])
    monkeypatch.setattr(module, "detect_game_maintenance_text", lambda *args: None)
    monkeypatch.setattr(module.Notify, "push_statistics_report", AsyncMock())
    monkeypatch.setattr(module.Notify, "send_notice", AsyncMock())
    monkeypatch.setattr(module.Publisher, "send", AsyncMock())
    sleep = asyncio.sleep

    async def settle(delay, result=None):
        # 启动和退出已由边界替身立即完成，保留让出调度而不空等进程稳定。
        return await sleep(min(delay, 0.01), result)

    monkeypatch.setattr(module.asyncio, "sleep", settle)
    return SimpleNamespace(root=root, native=native, log=log)


@pytest_asyncio.fixture
async def okww_history(store, monkeypatch):
    registry = BackgroundTaskRegistry()
    session = history_core.TaskHistorySession(
        RuntimeStub(uid=uuid.uuid4(), mode="AutoProxy")
    )
    monkeypatch.setattr(history_core, "History", store)
    monkeypatch.setattr(history_core, "BackgroundTaskManager", registry)
    monkeypatch.setattr(
        history_core,
        "Config",
        SimpleNamespace(
            setting=SimpleNamespace(Replay=SimpleNamespace(Enabled=False)),
            obs_replay_options=lambda: None,
        ),
    )
    try:
        yield session
    finally:
        await session.close()
        await registry.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("interruption", ["first_file", "before_mark", "after_mark"])
async def test_interrupted_batch_injection_keeps_original_recoverable(
    tmp_path, monkeypatch, interruption
):
    from pathlib import Path

    from app.utils import io

    monkeypatch.chdir(tmp_path)
    uid, sid = uuid.uuid4(), str(uuid.uuid4())
    live, snapshot = tmp_path / "configs", tmp_path / "data" / sid / "Temp"
    live.mkdir()
    original = '{"original":true}'
    (live / "DailyTask.json").write_text(original)
    io.commit_native_config_snapshot(snapshot, live, script_id=sid)
    io.mark_native_config_injected(snapshot, live, script_id=sid)
    user = UserItem(user_id=str(uid), name="user", status="等待")
    info = RuntimeStub(
        task_info=RuntimeStub(mode="AutoProxy"),
        script_id=sid,
        user_list=[user],
        current_index=0,
    )
    task = BatchProxyTask(
        info, OkwwConfig(), {uid: OkwwUserConfig()}, None, participants=[user]
    )
    task.script_config_path = live
    task.accounts = [
        {"account_key": "1306220", "enabled": True, "task": None, "config": {}}
    ]
    monkeypatch.setattr(AutoProxyTask, "set_okww", AsyncMock())
    write = Path.write_text

    def interrupted_write(path, *args, **kwargs):
        if path.name == "MultiAccountConfig.json":
            raise OSError("interrupted injection")
        return write(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        if interruption == "first_file":
            patch.setattr(Path, "write_text", interrupted_write)
        elif interruption == "before_mark":
            patch.setattr(
                io,
                "mark_native_config_injected",
                lambda *a, **kw: (_ for _ in ()).throw(
                    OSError("interrupted fingerprint")
                ),
            )
        if interruption == "after_mark":
            await task.set_okww()
        else:
            with pytest.raises(OSError):
                await task.set_okww()
    manager = OkwwManager(info)
    manager.temp_path, manager.script_config_path = snapshot, live
    manager._recover_previous_run()
    if interruption == "after_mark":
        assert list(live.iterdir()) == [live / "DailyTask.json"]
        assert (live / "DailyTask.json").read_text() == original
    else:
        saved = list(snapshot.parent.glob("Temp.unresolved*"))
        saved = [path for path in saved if path.is_dir()]
        assert len(saved) == 1
        assert (saved[0] / "DailyTask.json").read_text() == original
        assert (live / "MultiAccountResults.json").exists()


@pytest.mark.asyncio
async def test_batch_result_is_final_before_monitor_can_be_cancelled(
    tmp_path, monkeypatch
):
    from app.utils import LogMonitor

    ids = [uuid.uuid4(), uuid.uuid4()]
    users = [UserItem(user_id=str(uid), name="user", status="运行") for uid in ids]
    info = RuntimeStub(
        task_info=RuntimeStub(mode="AutoProxy"),
        user_list=users,
        current_index=0,
        log="",
    )
    task = BatchProxyTask(
        info,
        OkwwConfig(),
        {uid: OkwwUserConfig() for uid in ids},
        None,
        participants=users,
    )
    # 与 prepare 一致，父类先更新批次临时节点，再提交真实账号的最终状态。
    task.cur_user_item = UserItem(
        user_id=users[0].user_id, name="OK-WW 批次", status="运行"
    )
    task.task_name = "MultiAccountConfigTask"
    task.script_config_path = tmp_path
    task.pending = {"A", "B"}
    task.account_users = dict(zip(["A", "B"], users))
    task.cur_user_log = LogRecord()
    task.wait_event = asyncio.Event()
    task.okww_process_manager = SimpleNamespace(is_running=AsyncMock(return_value=True))
    task.is_log_stalled = lambda *args, **kwargs: False
    (tmp_path / "MultiAccountResults.json").write_text(
        json.dumps({"A": {"status": "success"}, "B": {"status": "failed"}})
    )
    committing, release = asyncio.Event(), asyncio.Event()
    original = type(users[0]).set_state

    async def delayed_state(user, **fields):
        if user is users[0] and fields.get("status") == "完成":
            committing.set()
            await release.wait()
        await original(user, **fields)

    monkeypatch.setattr(type(users[0]), "set_state", delayed_state)
    monitor = LogMonitor((0, 23), "%Y-%m-%d %H:%M:%S,%f", task.check_log)
    monitor.log_contents = ["Successfully Executed Task, Exiting Game and App!\n"]
    monitor.latest_time = datetime.now()

    async def consume():
        await task.wait_event.wait()
        await monitor.stop()

    consumer = asyncio.create_task(consume())
    monitor.task = asyncio.create_task(monitor.do_callback())
    try:
        await asyncio.wait_for(committing.wait(), 2)
        assert not task.wait_event.is_set()
        release.set()
        await asyncio.wait_for(consumer, 2)
        assert task.cur_user_log.status != "Success!"
        assert task.succeeded == {"A"}
        assert users[0].status == "完成"
        assert users[1].status != "完成"
    finally:
        release.set()
        consumer.cancel()
        await asyncio.gather(consumer, return_exceptions=True)
        await monitor.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("started", [False, True])
async def test_report_after_check_failure_and_later_manual_stop(monkeypatch, started):
    from app.task.Okww.manager import Notify, config_manager

    users = [
        UserItem(user_id=str(uuid.uuid4()), name=name, status="异常")
        for name in ["invalid-account", "stopped-account"]
    ]
    for user, reason in zip(users, ["check failed", "stopped manually"]):
        await user.add_log_record(
            datetime.now().astimezone(), LogRecord(status=reason, content=[reason])
        )
    info = RuntimeStub(
        task_info=RuntimeStub(mode="AutoProxy"),
        script_id=str(uuid.uuid4()),
        name="script",
        log="",
        user_list=users,
        current_index=1,
    )
    manager = OkwwManager(info)
    manager.check_result = "check failed"
    if started:
        manager.record_user_run_start(users[1])
    push = AsyncMock()
    monkeypatch.setattr(Notify, "push_proxy_result", push)
    monkeypatch.setattr(config_manager, "flush", AsyncMock())

    await manager.final_task()

    assert info.status == "异常"
    if started:
        push.assert_awaited_once()
        report = push.call_args.kwargs["report"]
        assert report.completed_count == 0
        assert report.uncompleted_count == 2
        assert all(user.name in report.result for user in users)
        assert "check failed" in report.result
        assert "stopped manually" in report.result
    else:
        push.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("limited_index", [0, 1])
@pytest.mark.parametrize("skip_reason", ["daily_limit", "expired"])
@pytest.mark.parametrize("method", ["OKWW", "OKWW_SINGLE"])
async def test_batch_filters_each_accounts_real_daily_limit(
    tmp_path, monkeypatch, limited_index, skip_reason, method
):
    work = tmp_path / "mas"
    work.mkdir()
    monkeypatch.chdir(work)
    root = tmp_path / "okww"
    root.mkdir()
    sentinel = root / "data/apps/ok-ww/app.json"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("{}", encoding="utf-8")
    (root / "ok-ww.exe").touch()
    native = root / "data/apps/ok-ww/working/configs"
    native.mkdir(parents=True)
    (native / "DailyTask.json").write_text("{}", encoding="utf-8")
    ids = [uuid.uuid4(), uuid.uuid4()]
    users = [UserItem(user_id=str(uid), name="user", status="等待") for uid in ids]
    info = RuntimeStub(
        task_info=RuntimeStub(mode="AutoProxy", is_queue_task=True),
        script_id=str(uuid.uuid4()),
        user_list=users,
        current_index=0,
    )
    manager = OkwwManager(info)
    manager.script_config = OkwwConfig.model_validate(
        {
            "Info": {"RootPath": str(root)},
            "Game": {"AccountSwitchMethod": method},
            "Run": {"ProxyTimesLimit": 1},
        }
    )
    now = datetime.now(tz=constants.UTC4)
    manager.user_config = {
        uid: OkwwUserConfig.model_validate(
            {
                "Info": {
                    "Id": phone,
                    "Base": "native",
                    "RemainedDay": 0
                    if i == limited_index and skip_reason == "expired"
                    else -1,
                },
                "Data": {
                    "LastProxyDate": now,
                    "ProxyTimes": int(
                        i == limited_index and skip_reason == "daily_limit"
                    ),
                },
            }
        )
        for i, (uid, phone) in enumerate(zip(ids, ["13012346220", "13912347052"]))
    }
    manager.game_manager = None
    manager.check = AsyncMock(return_value="Pass")
    manager.prepare = AsyncMock()
    manager.check_user_before_run = AsyncMock(return_value=True)
    manager.notify_user_check_failure = AsyncMock()
    manager._restore_script_config_from_temp = AsyncMock()
    manager.record_user_run_start = lambda user: None
    dispatched = []

    async def run(task):
        dispatched.extend(user.user_id for user in task.participants)

    manager.spawn = AsyncMock(side_effect=run)
    await manager.main_task()
    assert dispatched == [str(ids[1 - limited_index])], (
        manager.notify_user_check_failure.call_args_list
    )
    assert users[limited_index].status == "跳过"


@pytest.mark.asyncio
async def test_all_batch_accounts_reset_and_count_today_once(tmp_path, monkeypatch):
    ids = [uuid.uuid4(), uuid.uuid4()]
    users = [UserItem(user_id=str(uid), name="user", status="等待") for uid in ids]
    info = RuntimeStub(
        task_info=RuntimeStub(mode="AutoProxy"),
        script_id=str(uuid.uuid4()),
        user_list=users,
        current_index=0,
    )
    yesterday = datetime.now(tz=constants.UTC4) - timedelta(days=1)
    configs = {
        uid: await activate_config(
            OkwwUserConfig.model_validate(
                {
                    "Info": {"Id": phone, "Base": "native", "RemainedDay": 3},
                    "Data": {"LastProxyDate": yesterday, "ProxyTimes": 4},
                }
            )
        )
        for uid, phone in zip(ids, ["13012346220", "13912347052"])
    }
    task = BatchProxyTask(info, OkwwConfig(), configs, None, participants=users)

    async def prepare(self):
        self.script_config_path = tmp_path
        self._log_source = object()
        self.log_start_time = datetime.now().astimezone()

    monkeypatch.setattr(AutoProxyTask, "prepare", prepare)
    await task.prepare()
    for uid, user in zip(ids, users):
        assert configs[uid].Data.ProxyTimes == 0
        assert (
            configs[uid].Data.LastProxyDate.date()
            == datetime.now(tz=constants.UTC4).date()
        )
        task.cur_user_uid = uid
        task.cur_user_config = configs[uid]
        task.cur_user_item = user
        task.run_book = True
        await task._persist_user_run_result()
        assert configs[uid].Data.ProxyTimes == 1
        assert configs[uid].Info.RemainedDay == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stop,maintenance,expected",
    [(True, False, "任务被用户手动中止"), (False, True, "鸣潮正在维护")],
)
async def test_batch_preserves_stop_reason_when_node_read_fails(
    monkeypatch, stop, maintenance, expected
):
    ids = [uuid.uuid4(), uuid.uuid4()]
    users = [UserItem(user_id=str(uid), name="user", status="等待") for uid in ids]
    info = RuntimeStub(
        task_info=RuntimeStub(mode="AutoProxy"),
        script_id=str(uuid.uuid4()),
        user_list=users,
        current_index=0,
    )
    configs = {
        uid: OkwwUserConfig.model_validate({"Info": {"Id": phone}})
        for uid, phone in zip(ids, ["13012346220", "13912347052"])
    }
    task = BatchProxyTask(info, OkwwConfig(), configs, None, participants=users)
    task.stopped_manually = stop
    task.user_state(task.cur_user_item).maintenance_skipped = maintenance
    task._maintenance_reason = "鸣潮正在维护" if maintenance else None
    task._log_user = task.cur_user_item
    task._log_source = SimpleNamespace(
        read_new=lambda: (_ for _ in ()).throw(OSError("read failed"))
    )
    task.kill_managed_process = AsyncMock(return_value=True)
    conclusions = []

    async def finalize(self):
        conclusions.append(
            (
                self.cur_user_item.user_id,
                self.cur_user_log.status,
                self.user_state(self.cur_user_item).maintenance_skipped,
            )
        )

    monkeypatch.setattr(AutoProxyTask, "final_task", finalize)
    await task.final_task()
    assert [row[0] for row in conclusions] == [str(uid) for uid in ids]
    assert all(row[1] == expected and row[2] == maintenance for row in conclusions)
    task.kill_managed_process.assert_awaited()


@pytest.mark.asyncio
async def test_batch_keeps_raw_history_when_nodes_are_disabled(tmp_path, monkeypatch):
    uid = uuid.uuid4()
    user = UserItem(user_id=str(uid), name="user", status="等待")
    info = RuntimeStub(
        task_info=RuntimeStub(mode="AutoProxy"),
        script_id=str(uuid.uuid4()),
        user_list=[user],
        current_index=0,
    )
    config = await activate_config(
        OkwwUserConfig.model_validate(
            {
                "Info": {"Id": "13012346220", "Base": "native"},
                "Notify": {"PushLogMode": "关闭"},
            }
        )
    )
    task = BatchProxyTask(info, OkwwConfig(), {uid: config}, None, participants=[user])

    async def prepare(self):
        self.script_config_path = tmp_path
        self.script_log_path = tmp_path / "ok-script.log"
        self.script_log_path.touch()
        self.log_start_time = datetime.now().astimezone()

    monkeypatch.setattr(AutoProxyTask, "prepare", prepare)
    await task.prepare()
    lines = [
        "MultiAccountConfigTask:info_set 当前账号 1306220\n",
        "account task details\n",
    ]
    task.script_log_path.write_text("".join(lines), encoding="utf-8")
    await task._collect_log_details()

    assert [line.rstrip() for line in task.batch_records[user.user_id].content] == [
        line.rstrip() for line in lines
    ]
    assert task.user_state(user).push_log == []


@pytest.mark.asyncio
async def test_missing_native_switch_task_is_reported_for_each_account(
    tmp_path, monkeypatch
):
    ids = [uuid.uuid4(), uuid.uuid4()]
    users = [UserItem(user_id=str(uid), name="user", status="运行") for uid in ids]
    info = RuntimeStub(
        task_info=RuntimeStub(mode="AutoProxy"),
        script_id=str(uuid.uuid4()),
        user_list=users,
        current_index=0,
        log="",
    )
    configs = {
        uid: OkwwUserConfig.model_validate({"Info": {"Id": phone}})
        for uid, phone in zip(ids, ["13012346220", "13912347052"])
    }
    task = BatchProxyTask(info, OkwwConfig(), configs, None, participants=users)
    task.script_config_path = tmp_path
    task.wait_event = asyncio.Event()
    task.cur_user_log = LogRecord()
    task.okww_process_manager = SimpleNamespace(is_running=AsyncMock(return_value=True))
    task.is_log_stalled = lambda *args, **kwargs: False
    await task.check_log(
        ["ValueError: Task not found: MultiAccountConfigTask\n"], datetime.now()
    )
    assert task.wait_event.is_set()
    expected = "当前ok-ww版本不支持或已移除原生账号切换，请检查ok-ww版本，或改用 MAS 切换账号。"
    assert task.cur_user_log.status == expected
    assert task.native_switch_unsupported
    task.kill_managed_process = AsyncMock(return_value=True)
    monkeypatch.setattr(AutoProxyTask, "final_task", AsyncMock())

    await task.final_task()

    assert all(user.status == "异常" for user in users)
    assert all(
        next(iter(user.log_record.values())).status == expected for user in users
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("write_fails", [False, True])
async def test_stop_preserves_success_written_since_last_log_poll(
    tmp_path, monkeypatch, write_fails
):
    ids = [uuid.uuid4(), uuid.uuid4()]
    users = [UserItem(user_id=str(uid), name="user", status="运行") for uid in ids]
    info = RuntimeStub(
        task_info=RuntimeStub(mode="AutoProxy"),
        script_id=str(uuid.uuid4()),
        user_list=users,
        current_index=0,
    )
    configs = {
        uid: OkwwUserConfig.model_validate({"Info": {"Id": phone}})
        for uid, phone in zip(ids, ["13012346220", "13912347052"])
    }
    task = BatchProxyTask(info, OkwwConfig(), configs, None, participants=users)
    task.stopped_manually = True
    task.script_config_path = tmp_path
    task.pending = {"1306220", "1397052"}
    (tmp_path / "MultiAccountResults.json").write_text(
        json.dumps({"1306220": {"status": "success"}}), encoding="utf-8"
    )
    if write_fails:
        # base 中的历史结果可读，但本轮清空结果失败；不能将旧成功计入本轮。
        from pathlib import Path

        original_write = Path.write_text

        def write(path, *args, **kwargs):
            if path.name == "MultiAccountResults.json":
                raise PermissionError("results are read-only")
            return original_write(path, *args, **kwargs)

        task.accounts = [{"account_key": key} for key in task.pending]
        monkeypatch.setattr(Path, "write_text", write)
        monkeypatch.setattr(AutoProxyTask, "set_okww", AsyncMock())
        with pytest.raises(PermissionError):
            await task.set_okww()
    task.kill_managed_process = AsyncMock(return_value=True)
    results = []

    async def finalize(self):
        results.append(
            (self.cur_user_item.status, self.run_book, self.cur_user_log.status)
        )

    monkeypatch.setattr(AutoProxyTask, "final_task", finalize)
    await task.final_task()

    assert results[0] == (
        ("异常", False, "任务被用户手动中止")
        if write_fails
        else ("完成", True, "Success!")
    )
    assert results[1] == ("异常", False, "任务被用户手动中止")


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["normal", "invalid", "duplicate", "cancel"])
async def test_batch_arguments_grouping_preserves_user_order(
    okww_installation, okww_history, monkeypatch, scenario
):
    from app.utils import io

    module = importlib.import_module("app.task.Okww.AutoProxy")
    root, native = okww_installation.root, okww_installation.native
    ids = [uuid.uuid4() for _ in range(5)]
    users = [
        UserItem(user_id=str(uid), name=str(i), status="等待")
        for i, uid in enumerate(ids)
    ]
    info = RuntimeStub(
        task_info=RuntimeStub(
            mode="AutoProxy", is_queue_task=False, task_id=str(uuid.uuid4())
        ),
        uid=uuid.uuid4(),
        script_id=str(uuid.uuid4()),
        user_list=users,
        current_index=0,
        status="等待",
        name="okww",
        log="",
    )
    manager = OkwwManager(info)
    manager.script_config = OkwwConfig.model_validate(
        {
            "Info": {"RootPath": str(root)},
            "Game": {"AccountSwitchMethod": "OKWW", "Enabled": False},
            "Run": {"RunTimesLimit": 1},
        }
    )
    drafts = [None, '-t "Other Task" --', " -t 'Other Task' -- ", None, None]
    if scenario == "invalid":
        drafts[2] = '"unfinished'
    manager.user_config = {
        uid: await activate_config(
            OkwwUserConfig.model_validate(
                {
                    "Info": {"Id": f"1301234000{i}", "Base": "native"},
                    "Task": {
                        "IfCustomArguments": draft is not None,
                        "CustomArguments": draft or '"ignored',
                    },
                    "Notify": {"PushLogMode": "关闭"},
                },
            )
        )
        for i, (uid, draft) in enumerate(zip(ids, drafts))
    }
    if scenario == "duplicate":
        manager.user_config[ids[1]].Info.Id = manager.user_config[ids[0]].Info.Id
        await manager.user_config[ids[1]].commit()
    manager.game_manager = None
    manager.history = okww_history
    manager.script_config_path = native
    manager.temp_path = (
        okww_installation.root.parent / "mas/data" / info.script_id / "Temp"
    )
    manager.had_original_script_config = io.commit_native_config_snapshot(
        manager.temp_path, native, script_id=info.script_id
    )
    # 仅省略全局配置提取与取锁；批次准入、执行、归档和目录恢复均走真实逻辑。
    manager.check = AsyncMock(return_value="Pass")
    manager.prepare = AsyncMock()
    dispatched = []

    async def launch(process_manager, executable, *, args, **kwargs):
        accounts = json.loads(
            (native / "MultiAccountConfig.json").read_text(encoding="utf-8")
        )["accounts"]
        keys = [account["account_key"] for account in accounts]
        dispatched.append((keys, list(args)))
        assert (
            json.loads(
                (native / "MultiAccountResults.json").read_text(encoding="utf-8")
            )
            == {}
        )
        if scenario == "cancel":
            okww_history.cancelled = True
            raise asyncio.CancelledError
        (native / "MultiAccountResults.json").write_text(
            json.dumps({key: {"status": "success"} for key in keys}),
            encoding="utf-8",
        )
        timestamp = (datetime.now() + timedelta(seconds=1)).strftime(
            "%Y-%m-%d %H:%M:%S,%f"
        )[:-3]
        with okww_installation.log.open("a", encoding="utf-8") as log:
            log.write(
                f"{timestamp} INFO TaskExecutor:"
                "Successfully Executed Task, Exiting Game and App!\n"
            )

    monkeypatch.setattr(module, "start_okww", launch)
    if scenario == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(manager.main_task(), timeout=30)
        assert dispatched == [(["1300000"], ["-t", "MultiAccountConfigTask", "-e"])]
        assert [user.status for user in users] == ["异常", *["等待"] * 4]
    else:
        await asyncio.wait_for(manager.main_task(), timeout=30)
    assert [path.name for path in native.iterdir()] == ["DailyTask.json"]
    assert (native / "DailyTask.json").read_text(encoding="utf-8") == (
        '{"original":true}'
    )
    if scenario == "duplicate":
        assert not dispatched
        assert all(user.status == "异常" for user in users)
    if scenario in {"duplicate", "cancel"}:
        assert all(
            config.Data.ProxyTimes == 0 for config in manager.user_config.values()
        )
        return
    default = ["-t", "MultiAccountConfigTask", "-e"]
    assert dispatched == [
        (["1300000"], default),
        (
            ["1300001"] if scenario == "invalid" else ["1300001", "1300002"],
            ["-t", "Other Task", "--"],
        ),
        (["1300003", "1300004"], default),
    ]
    assert [user.status for user in users] == [
        "异常" if scenario == "invalid" and index == 2 else "完成" for index in range(5)
    ]
    assert [config.Data.ProxyTimes for config in manager.user_config.values()] == [
        int(scenario != "invalid" or index != 2) for index in range(5)
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome,expected",
    [
        ("success", "success"),
        ("maintenance", "skipped"),
        ("cancel", "cancelled"),
        ("failure", "error"),
    ],
)
async def test_single_batch_archives_only_account_summary(
    tmp_path, monkeypatch, okww_installation, okww_history, store, outcome, expected
):
    from app.services.common import obs_replay

    module = importlib.import_module("app.task.Okww.AutoProxy")
    root, native = okww_installation.root, okww_installation.native
    uid = uuid.uuid4()
    user = UserItem(user_id=str(uid), name="user", status="等待")
    info = RuntimeStub(
        task_info=RuntimeStub(
            mode="AutoProxy", is_queue_task=False, task_id=str(uuid.uuid4())
        ),
        uid=uuid.uuid4(),
        script_id=str(uuid.uuid4()),
        user_list=[user],
        current_index=0,
        name="okww",
    )
    config = await activate_config(
        OkwwUserConfig.model_validate(
            {
                "Info": {"Id": "13012346220", "Base": "native"},
                "Notify": {"PushLogMode": "关闭"},
            }
        )
    )
    script = OkwwConfig.model_validate(
        {
            "Info": {"RootPath": str(root)},
            "Game": {"Enabled": False, "AccountSwitchMethod": "OKWW_SINGLE"},
            "Run": {"RunTimesLimit": 1},
        }
    )
    task = BatchProxyTask(info, script, {uid: config}, None, participants=[user])
    task.history = okww_history
    replay = obs_replay.ObsReplayService(tmp_path)
    replay.directory.mkdir(parents=True)
    other_capture = replay.directory / "other.mkv"
    own_capture = replay.directory / f"{user.uid}.mkv"
    other_capture.write_bytes(b"other account replay")
    own_capture.write_bytes(b"this account replay")
    replay.capture = AsyncMock(side_effect=[other_capture, own_capture])
    monkeypatch.setattr(obs_replay, "ObsReplay", replay)
    monkeypatch.setattr(history_core.Config.setting.Replay, "Enabled", True)
    other = UserItem(user_id=str(uuid.uuid4()), name="other", status="异常")
    await other.add_log_record(
        datetime.now().astimezone(), LogRecord(status="other failure")
    )
    okww_history.begin_user_history_capture(info, other, failed=True)
    assert await okww_history._capture_group.drain(2)

    async def start(*args, **kwargs):
        if outcome == "cancel":
            # ScriptExpander.stop 先标记历史取消，再将中止传播给账号任务。
            okww_history.cancelled = True
            task.stopped_manually = True
            raise asyncio.CancelledError

    monkeypatch.setattr(module, "start_okww", start)

    async def deliver():
        with okww_installation.log.open("a", encoding="utf-8") as log:
            log.write(
                "MultiAccountConfigTask:info_set 当前账号 1306220\n"
                "account task details\n"
            )
        if outcome in {"success", "failure"}:
            (native / "MultiAccountResults.json").write_text(
                json.dumps(
                    {
                        "1306220": {
                            "status": "success" if outcome == "success" else "failed"
                        }
                    }
                ),
                encoding="utf-8",
            )
            await task.check_log(
                ["TaskExecutor:Successfully Executed Task, Exiting Game and App!\n"],
                datetime.now(),
            )
        else:
            await task.mark_game_maintenance_skip("测试维护")
            task._maintenance_reason = "测试维护"
            task.wait_event.set()

    async def monitor(*args):
        asyncio.create_task(deliver())

    monkeypatch.setattr(
        module,
        "LogMonitor",
        lambda *args: SimpleNamespace(start_monitor_file=monitor, stop=AsyncMock()),
    )
    if outcome == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await task.main_task()
    else:
        await asyncio.wait_for(task.main_task(), timeout=10)
    await task.final_task()
    today = datetime.now(tz=constants.UTC4).date()
    archived = await store.search(start_date=today, end_date=today, mode="DAILY")
    assert set(archived[today.isoformat()]) == {"user"}
    records = archived[today.isoformat()]["user"].index
    assert len(records) == 1
    detail = await store.get_detail(record_id=records[0].id)
    assert detail.status == expected
    assert detail.script_name == "okww"
    assert detail.log_available
    assert not detail.storage_errors
    assert len(detail.attachments) == int(outcome == "failure")
    if outcome == "failure":
        attachment = await store.get_attachment(attachment_id=detail.attachments[0].id)
        assert attachment.display_name == own_capture.name
        assert attachment.path.read_bytes() == b"this account replay"
    assert other_capture.read_bytes() == b"other account replay"
    assert len(user.iter_history_logs()) == 1
    assert config.Data.ProxyTimes == int(outcome == "success")
