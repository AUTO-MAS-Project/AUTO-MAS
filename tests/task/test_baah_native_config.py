"""托管运行只覆盖设备和生命周期配置，不改写原生任务与关卡轮换。"""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.task.BAAH.AutoProxy import AutoProxyTask
from app.task.BAAH.tools.config_manager import read_json, write_json


@pytest.mark.asyncio
@pytest.mark.parametrize("managed", [True, False])
@pytest.mark.parametrize("outcome", ["success", "failure", "cancel"])
async def test_native_tasks_and_rotation_survive_managed_run(
    tmp_path, isolated_app_paths, managed, outcome
):
    task = object.__new__(AutoProxyTask)
    task.wait_event = asyncio.Event()
    task.config_dir = tmp_path / "baah" / "BAAH_CONFIGS"
    task.user_config_path = task.config_dir / "native.json"
    task.software_config_path = (
        tmp_path / "baah" / "DATA" / "CONFIGS" / "software_config.json"
    )
    task.cur_user_uid = uuid4()
    task.if_manage_config = managed
    task.managed_backup = None
    task.emulator_adb_address = "127.0.0.1:5555"
    task._ensure_emulator_online = AsyncMock(return_value=True)
    task._close_log_collect = AsyncMock()
    native = {
        "HARD": [[[1, 1, -1]], [[2, 1, -1]]],
        "EVENT_QUEST_LEVEL": [[[9, -1]]],
        "CLOSE_BAAH_FINISH": False,
        "TASK_ORDER_GROUP": {
            "ACTIVATE_IND": 0,
            "ALL_PIPELINES": [
                {
                    "TASK_PIPELINE": [
                        "活动关卡",
                        "每日任务",
                        "邮件",
                        "活动关卡",
                        "普通关卡",
                    ],
                    "TASK_ONOFF": [True, True, True, True, True],
                }
            ],
        },
    }
    software = {"SAVE_LOG_TO_FILE": False, "unrelated": "keep"}
    write_json(task.user_config_path, native)
    write_json(task.software_config_path, software)

    async def launch():
        running = read_json(task.user_config_path)
        for key in ("HARD", "EVENT_QUEST_LEVEL", "TASK_ORDER_GROUP"):
            assert running[key] == native[key]
        assert running["CLOSE_BAAH_FINISH"] is managed
        assert read_json(task.software_config_path)["SAVE_LOG_TO_FILE"] is managed
        if outcome == "failure":
            raise RuntimeError("script failed")
        if outcome == "cancel":
            raise asyncio.CancelledError

    task._run_launched = launch
    if outcome == "success":
        await task._run_once_locked()
    else:
        error = RuntimeError if outcome == "failure" else asyncio.CancelledError
        with pytest.raises(error):
            await task._run_once_locked()

    assert read_json(task.user_config_path) == native
    assert read_json(task.software_config_path) == software
