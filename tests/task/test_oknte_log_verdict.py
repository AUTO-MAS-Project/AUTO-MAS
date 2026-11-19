import uuid
from datetime import datetime

import pytest

from app.models.config.script import OkNteConfig, OkNteUserConfig
from app.models.task import LogRecord
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
    await proxy.prepare()
    now = datetime.now().astimezone()
    proxy.cur_user_log = await user.add_log_record(now, LogRecord())
    await proxy.check_log(["END:42\n", detail], now)
    assert proxy.cur_user_log.status == status
