"""客户端热更新中断本轮，只在真实失败路径上保底再跑一次。"""

import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.models.config.script import OkwwConfig, OkwwUserConfig
from app.task.Okww import AutoProxy
from app.task.run_flow import observe_run
from tests.config_support import activate_config
from tests.support.scheduler import create_runtime_tree


@pytest.mark.asyncio
@pytest.mark.parametrize("updated_again", [False, True])
async def test_client_update_retries_once_without_claiming_task_success(
    tmp_path, monkeypatch, updated_again
):
    uid = uuid.uuid4()
    _root, script, user = await create_runtime_tree(user_id=str(uid))
    config = await activate_config(
        OkwwConfig(Info={"RootPath": tmp_path}, Run={"RunTimesLimit": 1})
    )
    account = await activate_config(
        OkwwUserConfig(Info={"Base": "native"}, Notify={"PushLogMode": "关闭"})
    )
    proxy = AutoProxy.AutoProxyTask(script, config, {uid: account}, None)
    log = tmp_path / "data/apps/ok-ww/working/logs/ok-script.log"
    log.parent.mkdir(parents=True)
    app_json = tmp_path / "data/apps/ok-ww/app.json"
    app_json.write_text('{"current_version":"v3.8.0"}', encoding="utf-8")
    updated = "游戏更新成功, 游戏即将重启"
    done = "Successfully Executed Task, Exiting Game and App!"
    attempts = iter([[updated, done], [updated if updated_again else done]])

    async def launch(*args, **kwargs):
        stamp = (datetime.now() + timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S,%f")
        log.write_text(
            "".join(f"{stamp[:23]} INFO {line}\n" for line in next(attempts)),
            encoding="utf-8",
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(proxy, "_maintenance_detect", lambda: None)
    monkeypatch.setattr(AutoProxy, "start_okww", launch)
    monkeypatch.setattr(AutoProxy.process, "kill_process", AsyncMock(return_value=True))
    monkeypatch.setattr(
        AutoProxy.process, "is_process_stopped", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(AutoProxy.Notify, "send_notice", AsyncMock())
    sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda seconds: sleep(0.001))
    points = []
    with observe_run(lambda owner, event: points.append(event)):
        await asyncio.wait_for(proxy.main_task(), timeout=5)

    assert len(user.logs) == 2
    assert user.status == ("异常" if updated_again else "完成")
    assert [
        (p.state, p.key) for p in points if p.stage == "run" and p.state != "entered"
    ] == [
        ("failed", "game_updated"),
        ("failed", "game_updated") if updated_again else ("succeeded", "success"),
    ]
    assert [p.attempt for p in points if p.stage == "retry"] == [2]
    assert not any(p.stage == "game_update" for p in points)
