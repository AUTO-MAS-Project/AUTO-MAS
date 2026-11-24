import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.core import Notify
from app.models.config.script import OkNteConfig, OkNteUserConfig
from app.models.task import LogRecord
from app.task.history_core import TaskHistorySession
from app.task.OkNte import AutoProxy as proxy_module
from app.task.OkNte.AutoProxy import AutoProxyTask
from tests.config_support import activate_config
from tests.support.scheduler import create_runtime_tree


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("detail", "status"),
    [
        ("Resolution Error; ERROR:42", "OK-NTE 游戏分辨率不符合要求"),
        ("ERROR:42", "OK-NTE：ERROR:42"),
        ("DailyRoutineTask:info_set success []", "OK-NTE 日常任务未完成日常领取"),
        ("DailyRoutineTask:info_set success ['Daily Claim']", "Success!"),
    ],
)
async def test_daily_result_checks_fatal_and_claim_after_configured_sign(
    tmp_path, detail, status
):
    uid = uuid.uuid4()
    _root, script, user = await create_runtime_tree(user_id=str(uid))
    path = tmp_path / "test.log"
    path.touch()
    config = await activate_config(
        OkNteConfig(
            Info={"RootPath": tmp_path},
            Game={"Enabled": False},
            Script={
                "ScriptPath": path,
                "LogPath": path,
                "ConfigPath": tmp_path,
                "SuccessLog": "END:42",
                "ErrorLogMode": "Regex",
                "ErrorLog": r"ERROR:\d+",
            },
        )
    )
    account = await activate_config(
        OkNteUserConfig(Task={"TaskIndex": "2"}, Notify={"PushLogMode": "关闭"})
    )
    proxy = AutoProxyTask(script, config, {uid: account}, None)
    assert await proxy.check() == "Pass"
    await proxy.prepare()
    now = datetime.now().astimezone()
    proxy.cur_user_log = await user.add_log_record(now, LogRecord())
    await proxy.check_log(["END:42\n", detail], now)
    assert proxy.cur_user_log.status == status


@pytest.mark.asyncio
@pytest.mark.parametrize("attempts", [1, 3], ids=["crash", "startup-retry"])
async def test_startup_error_is_kept_in_history_without_runtime_logs(
    tmp_path, monkeypatch, attempts
):
    uid = uuid.uuid4()
    _root, script, user = await create_runtime_tree(user_id=str(uid))
    log_path = tmp_path / "app.log"
    log_path.touch()
    program = tmp_path / "ok-nte.exe"
    program.touch()
    config = await activate_config(
        OkNteConfig(
            Info={"RootPath": tmp_path},
            Run={"RunTimesLimit": attempts},
            Script={
                "ScriptPath": program,
                "LogPath": log_path,
                "ConfigPath": tmp_path,
            },
        )
    )
    account = await activate_config(
        OkNteUserConfig(Task={"TaskIndex": "2"}, Notify={"PushLogMode": "关闭"})
    )
    proxy = AutoProxyTask(script, config, {uid: account}, None)
    assert await proxy.check() == "Pass"
    reason = "OK-NTE 启动器更新至 v1.5.10 失败：下载依赖时读取超时"
    startup = AsyncMock(side_effect=RuntimeError(reason))
    if attempts == 1:
        await proxy.prepare()
        now = datetime.now().astimezone()
        proxy.cur_user_log = await user.add_log_record(now, LogRecord())
        monkeypatch.setattr(proxy, "main_task", startup)
    else:
        monkeypatch.setattr(proxy_module.OkNteProcessManager, "open_oknte", startup)
        monkeypatch.setattr(proxy, "set_oknte", AsyncMock())
        monkeypatch.setattr(proxy, "run_user_scripts_before", AsyncMock())
        real_sleep = asyncio.sleep

        async def skip_retry_wait(delay, *args, **kwargs):
            if delay != 10:
                return await real_sleep(delay, *args, **kwargs)

        monkeypatch.setattr(asyncio, "sleep", skip_retry_wait)

    monkeypatch.setattr(proxy, "kill_managed_process", AsyncMock())
    monkeypatch.setattr(proxy, "run_user_scripts_after", AsyncMock())
    monkeypatch.setattr(Notify, "send_notice", AsyncMock())
    monkeypatch.setattr(Notify, "push_statistics_report", AsyncMock())
    proxy.history = TaskHistorySession(proxy.task_info)
    save_history = AsyncMock()
    monkeypatch.setattr(proxy.history, "save_user_history", save_history)

    await proxy.execution.run()

    records = save_history.await_args.args[0]
    assert len(records) == attempts
    assert startup.await_count == attempts
    for record in records:
        assert record.status == "error"
        assert reason in record.message
        assert reason in record.logs
    assert reason in user.result
