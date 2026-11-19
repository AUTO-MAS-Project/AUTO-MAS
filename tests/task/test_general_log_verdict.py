import uuid
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.models.config.script import GeneralConfig, GeneralUserConfig
from app.models.task import LogRecord
from app.task.general.AutoProxy import AutoProxyTask
from tests.config_support import activate_config
from tests.support.scheduler import create_runtime_tree


@pytest.mark.asyncio
@pytest.mark.parametrize("success,completed", [("", True), ("[", False)])
async def test_process_exit_only_completes_without_a_configured_success_sign(
    tmp_path, monkeypatch, success, completed
):
    uid = uuid.uuid4()
    _root, script, user = await create_runtime_tree(user_id=str(uid))
    path = tmp_path / "test.log"
    path.touch()
    config = await activate_config(
        GeneralConfig(
            Script={
                "ScriptPath": path,
                "LogPath": path,
                "ConfigPath": path,
                "SuccessLogMode": "Regex",
                "SuccessLog": success,
            }
        )
    )
    account = await activate_config(GeneralUserConfig())
    proxy = AutoProxyTask(script, config, {uid: account}, None)
    await proxy.prepare()
    now = datetime.now().astimezone()
    proxy.cur_user_log = await user.add_log_record(now, LogRecord())
    monkeypatch.setattr(
        proxy.general_process_manager,
        "is_running",
        AsyncMock(side_effect=[True, False]),
    )
    await proxy.check_log(["working"], now)
    assert not proxy.wait_event.is_set()
    await proxy.check_log(["working"], now)
    assert proxy.wait_event.is_set()
    assert (proxy.cur_user_log.status == "Success!") == completed
