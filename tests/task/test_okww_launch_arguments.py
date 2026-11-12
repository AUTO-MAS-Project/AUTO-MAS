"""OK-WW 普通日常启动参数回归。"""

import json
import uuid
from types import SimpleNamespace

import pytest

from app.models.config.script import OkwwUserConfig
from app.models.task import UserItem
from app.task.Okww.AutoProxy import AutoProxyTask
from tests.runtime_support import RuntimeStub


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("version", "argument"),
    [
        ("v3.6.6", "1"),
        ("v3.6.7-beta.2", "DailyTask"),
        ("v3.6.7", "DailyTask"),
        ("v3.8.0-beta.1", "DailyTask"),
        ("unknown", None),
    ],
)
async def test_daily_task_uses_version_supported_argument(tmp_path, version, argument):
    app_json = tmp_path / "data/apps/ok-ww/app.json"
    app_json.parent.mkdir(parents=True)
    app_json.write_text(json.dumps({"current_version": version}), encoding="utf-8")
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

    if argument is None:
        with pytest.raises(ValueError, match="无法识别 OK-WW 当前版本"):
            await task.prepare()
        return
    await task.prepare()

    assert task.okww_args == ["-t", argument, "-e"]
