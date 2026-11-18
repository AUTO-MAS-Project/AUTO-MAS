"""OK-WW 任务报错保留原文，已知配置冲突只运行一次。"""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.config.script import OkwwConfig, OkwwUserConfig
from app.models.task import TaskItem, TaskScriptItem, TaskUserItem
from app.task.Okww import AutoProxy as proxy_module
from tests.config_support import activate_config


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("task", "upstream_error", "expected_detail", "attempts"),
    [
        (
            "DailyTask",
            "选择“传送并刷取4C声骸”时，必须在刷取声骸任务中启用“传送至首领”。",
            "选择“传送并刷取4C声骸”时，必须在刷取声骸任务中启用“传送至首领”。",
            1,
        ),
        ("DailyTask", "请在大世界并在队伍中开始!", "请在大世界并在队伍中开始!", 3),
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
    account = OkwwUserConfig.model_validate({"Notify": {"PushLogMode": "关闭"}})
    await activate_config(config)
    await activate_config(account)
    proxy = proxy_module.AutoProxyTask(script, config, {uid: account}, None)

    async def report_log(callback):
        await callback(
            [
                f"2026-11-18 16:55:35,030 INFO TaskExecutor {task}:info_set 错误 {upstream_error}\n",
                "2026-11-18 16:55:35,031 ERROR TaskExecutor Traceback\n",
            ],
            proxy.log_start_time,
        )

    monkeypatch.setattr(
        proxy_module,
        "asyncio",
        SimpleNamespace(
            Event=asyncio.Event,
            CancelledError=asyncio.CancelledError,
            create_task=asyncio.create_task,
            sleep=AsyncMock(),
        ),
    )

    def log_monitor(_time_range, _time_format, callback):
        async def start_monitor_file(*_args):
            asyncio.create_task(report_log(callback))

        return SimpleNamespace(start_monitor_file=start_monitor_file, stop=AsyncMock())

    monkeypatch.setattr(proxy_module, "LogMonitor", log_monitor)
    notify = AsyncMock()
    monkeypatch.setattr(proxy_module.Notify, "send_notice", notify)
    monkeypatch.setattr(proxy, "run_user_scripts_before", AsyncMock())
    monkeypatch.setattr(
        proxy, "skip_on_game_maintenance", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(proxy, "watch_game_maintenance", AsyncMock())
    monkeypatch.setattr(proxy, "set_okww", AsyncMock())
    monkeypatch.setattr(proxy, "_start_okww_with_current_arguments", AsyncMock())
    monkeypatch.setattr(proxy, "kill_managed_process", AsyncMock())

    await proxy.main_task()

    assert user.status == "异常"
    assert len(user.log_record) == attempts
    result = f"OK-WW：{expected_detail}"
    assert proxy.cur_user_log.status == result
    assert result in notify.await_args.args[0].message
