"""OK-WW 终止判定与节点告警分离。"""

import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.models.config.script import OkwwConfig, OkwwUserConfig
from app.models.task import LogRecord, TaskItem, TaskScriptItem, TaskUserItem
from app.task.Okww.AutoProxy import AutoProxyTask
from app.utils import ProcessManager
from tests.config_support import activate_config


@pytest.mark.asyncio
async def test_okww_waits_for_the_active_task_to_report_failure(monkeypatch):
    uid = uuid.uuid4()
    task = TaskItem()
    await task.activate()
    script_id = task.scripts.add(
        TaskScriptItem,
        payload={"info": {"script_id": str(uuid.uuid4()), "name": "OK-WW"}},
    )
    await task.scripts.commit()
    script = task.scripts[script_id]
    user_id = script.users.add(
        TaskUserItem, payload={"info": {"user_id": str(uid), "name": "User"}}
    )
    await script.users.commit()
    await task.set_current_index(0)
    config = OkwwConfig()
    account = OkwwUserConfig()
    await activate_config(config)
    await activate_config(account)

    proxy = AutoProxyTask(script, config, {uid: account}, None)
    proxy.okww_process_manager = ProcessManager()
    monkeypatch.setattr(
        proxy.okww_process_manager, "is_running", AsyncMock(return_value=True)
    )
    proxy.wait_event = asyncio.Event()
    now = datetime.now().astimezone()
    proxy.cur_user_log = await script.users[user_id].add_log_record(now, LogRecord())
    lines = [
        "2026-11-19 10:48:07,226 INFO TaskExecutor TaskExecutor:get queued onetime_task 📅 Daily Task\n",
        "2026-11-19 10:53:25,328 INFO TaskExecutor DailyTask:info_set 错误 \n",
        "2026-11-19 10:53:25,329 INFO update_window_size hwnd_window:hwnd changed,connected:0\n",
        "2026-11-19 10:53:25,330 ERROR TaskExecutor TaskExecutor:🔑 Auto Login exception stopped Traceback\n",
    ]
    await proxy.check_log(lines, now)
    assert not proxy.wait_event.is_set()

    lines.append(
        "2026-11-19 10:53:25,331 ERROR TaskExecutor TaskExecutor:📅 Daily Task exception stopped Traceback\n"
    )
    await proxy.check_log(lines, now)
    assert proxy.wait_event.is_set()
    assert script.users[user_id].status == "异常"
