"""批次账号准入、跨日计数与异常收尾回归。"""

import json
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.config.script import OkwwConfig, OkwwUserConfig
from app.models.task import LogRecord, UserItem
from app.task.Okww.AutoProxy import AutoProxyTask
from app.task.Okww.BatchProxy import BatchProxyTask
from app.task.Okww.manager import OkwwManager
from app.utils import constants
from tests.config_support import activate_config
from tests.runtime_support import RuntimeStub


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
async def test_batch_filters_each_accounts_real_daily_limit(tmp_path, limited_index):
    sentinel = tmp_path / "data/apps/ok-ww/app.json"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("{}", encoding="utf-8")
    (tmp_path / "ok-ww.exe").touch()
    native = tmp_path / "data/apps/ok-ww/working/configs"
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
            "Info": {"RootPath": str(tmp_path)},
            "Game": {"AccountSwitchMethod": "OKWW"},
            "Run": {"ProxyTimesLimit": 1},
        }
    )
    now = datetime.now(tz=constants.UTC4)
    manager.user_config = {
        uid: OkwwUserConfig.model_validate(
            {
                "Info": {"Id": phone, "Base": "native"},
                "Data": {"LastProxyDate": now, "ProxyTimes": int(i == limited_index)},
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
