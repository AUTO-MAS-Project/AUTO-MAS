"""OK-WW 普通日常启动参数回归。"""

import uuid
from types import SimpleNamespace

import pytest

from app.models.config.script import OkwwUserConfig
from app.models.task import UserItem
from app.task.Okww.AutoProxy import AutoProxyTask
from tests.runtime_support import RuntimeStub


@pytest.mark.asyncio
async def test_daily_task_uses_stable_task_name(tmp_path):
    uid = uuid.uuid4()
    user = UserItem(user_id=str(uid), name="用户", status="等待")
    script_info = RuntimeStub(
        task_info=RuntimeStub(),
        script_id=str(uuid.uuid4()),
        user_list=[user],
        current_index=0,
    )
    task = AutoProxyTask(
        script_info,
        SimpleNamespace(Info=SimpleNamespace(RootPath=tmp_path)),
        {uid: OkwwUserConfig.model_validate({"Notify": {"PushLogMode": "关闭"}})},
        None,
    )

    await task.prepare()

    assert task.okww_args == ["-t", "DailyTask", "-e"]
