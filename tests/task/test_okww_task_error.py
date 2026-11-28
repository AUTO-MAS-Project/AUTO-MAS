"""OK-WW 任务报错保留原文，已知配置冲突只运行一次。"""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.config.script import OkwwConfig, OkwwUserConfig
from app.models.task import TaskItem, TaskScriptItem, TaskUserItem
from app.utils import IS_WINDOWS
from app.utils import IS_WINDOWS
from app.task.Okww import AutoProxy as proxy_module
from app.task.Okww.BatchProxy import BatchProxyTask
from tests.config_support import activate_config

_4C_ERROR = "选择“传送并刷取4C声骸”时，必须在刷取声骸任务中启用“传送至首领”。"


@pytest.mark.asyncio
@pytest.mark.skipif(not IS_WINDOWS, reason="账号按 Windows DPAPI 加密落盘")
@pytest.mark.parametrize(
    ("task", "upstream_error", "expected_detail", "attempts"),
    [
        ("DailyTask", _4C_ERROR, _4C_ERROR, 1),
        ("DailyTask", "请在大世界并在队伍中开始!", "请在大世界并在队伍中开始!", 3),
        ("MultiAccountConfigTask", _4C_ERROR, _4C_ERROR, 1),
        (
            "MultiAccountConfigTask",
            "账号列表中未找到 13012340000",
            "登录列表中未找到目标账号",
            3,
        ),
        (
            "MultiAccountConfigTask",
            "无法确认目标账号 13012340000，停止登录。",
            "原生多账号任务失败，请查看本地脚本日志",
            3,
        ),
    ],
)
async def test_okww_run_reports_error_and_only_retries_recoverable_failure(
    tmp_path, monkeypatch, task, upstream_error, expected_detail, attempts
):
    app_json = tmp_path / "data/apps/ok-ww/app.json"
    app_json.parent.mkdir(parents=True)
    app_json.write_text('{"current_version": "v3.8.4"}', encoding="utf-8")
    script_log = app_json.parent / "working/logs/ok-script.log"
    script_log.parent.mkdir(parents=True)
    script_log.touch()

    root = TaskItem()
    await root.activate()
    script_key = root.scripts.add(
        TaskScriptItem,
        payload={"info": {"script_id": str(uuid.uuid4()), "name": "OK-WW"}},
    )
    await root.scripts.commit()
    script = root.scripts[script_key]
    uid = uuid.uuid4()
    user_key = script.users.add(
        TaskUserItem, payload={"info": {"user_id": str(uid), "name": "User"}}
    )
    await script.users.commit()
    await root.set_current_index(0)
    user = script.users[user_key]
    config = OkwwConfig.model_validate(
        {
            "Info": {"RootPath": str(tmp_path)},
            "Game": {"Enabled": False},
            "Run": {"RunTimesLimit": 3},
        }
    )
    account = OkwwUserConfig.model_validate(
        {"Info": {"Id": "13012340000"}, "Notify": {"PushLogMode": "关闭"}}
    )
    await activate_config(config)
    await activate_config(account)
    batch = task == "MultiAccountConfigTask"
    proxy = (
        BatchProxyTask(script, config, {uid: account}, None, participants=[user])
        if batch
        else proxy_module.AutoProxyTask(script, config, {uid: account}, None)
    )
    woke_before_error = []

    async def report_log(callback):
        task_name = "Multi Account Config Task" if batch else "📅 Daily Task"
        lines = [
            f"2026-11-18 16:55:35,026 INFO TaskExecutor TaskExecutor:get queued onetime_task {task_name}\n"
        ]
        if batch:
            lines.extend(
                [
                    f"2026-11-18 16:55:35,027 INFO TaskExecutor {task}:info_set 当前账号 1300000\n",
                    f"2026-11-18 16:55:35,029 INFO TaskExecutor {task}:info_set 状态 执行失败\n",
                ]
            )
            await callback(lines, proxy.log_start_time)
            woke_before_error.append(proxy.wait_event.is_set())
        lines.append(
            f"2026-11-18 16:55:35,030 INFO TaskExecutor {task}:info_set 错误 {upstream_error}\n"
        )
        await callback(lines, proxy.log_start_time)
        woke_before_error.append(proxy.wait_event.is_set())
        lines.append(
            f"2026-11-18 16:55:35,031 ERROR TaskExecutor TaskExecutor:{task_name} exception stopped Traceback\n"
        )
        with script_log.open("a", encoding="utf-8") as log:
            log.writelines(lines)
        await callback(lines, proxy.log_start_time)

    monkeypatch.setattr(
        proxy_module,
        "asyncio",
        SimpleNamespace(
            Event=asyncio.Event,
            CancelledError=asyncio.CancelledError,
            create_task=asyncio.create_task,
            shield=asyncio.shield,
            sleep=AsyncMock(),
        ),
    )

    def log_monitor(_time_range, _time_format, callback):
        async def start_monitor_file(*_args):
            asyncio.create_task(report_log(callback))

        return SimpleNamespace(start_monitor_file=start_monitor_file, stop=AsyncMock())

    monkeypatch.setattr(proxy_module, "LogMonitor", log_monitor)
    monkeypatch.setattr(
        proxy_module,
        "ProcessManager",
        lambda: SimpleNamespace(is_running=AsyncMock(return_value=True)),
    )
    notify = AsyncMock()
    monkeypatch.setattr(proxy_module.Notify, "send_notice", notify)
    monkeypatch.setattr(proxy, "run_user_scripts_before", AsyncMock())
    monkeypatch.setattr(
        proxy, "skip_on_game_maintenance", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(proxy, "watch_game_maintenance", AsyncMock())
    monkeypatch.setattr(proxy_module.AutoProxyTask, "set_okww", AsyncMock())
    start = AsyncMock()
    monkeypatch.setattr(proxy, "_start_okww_with_current_arguments", start)
    monkeypatch.setattr(proxy, "kill_managed_process", AsyncMock())

    await asyncio.wait_for(proxy.main_task(), timeout=3)
    if batch:
        # Keep the real batch result and log collection, with history delivery isolated.
        monkeypatch.setattr(proxy_module.AutoProxyTask, "final_task", AsyncMock())
        await proxy.final_task()

    assert not any(woke_before_error)
    assert user.status == "异常"
    assert start.await_count == attempts
    result = f"OK-WW：{expected_detail}"
    assert proxy.cur_user_log.status == result
    assert result in notify.await_args.args[0].message
