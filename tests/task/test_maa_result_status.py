import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.models.config import MaaUserConfig
from app.task.MAA.AutoProxy import AutoProxyTask
from app.utils.constants import MAA_TASKS


@pytest.mark.parametrize("quick", [False, True])
def test_completed_fight_recovers_an_earlier_optional_fight_failure(quick) -> None:
    task = object.__new__(AutoProxyTask)
    task.cur_user_config = MaaUserConfig()
    asyncio.run(task.cur_user_config.set("Info", "IfQuickConfig", quick))
    task.cur_user_log = SimpleNamespace(content=[], status="")
    task.script_info = SimpleNamespace(log="")
    task.task_dict = dict.fromkeys(MAA_TASKS, False)
    task.mode = "Routine"
    task.wait_event = SimpleNamespace(set=lambda: None)

    asyncio.run(
        task.check_log(
            [
                "任务出错: 理智作战\n",
                "完成任务: 理智作战\n",
                "任务已全部完成！\n",
            ],
            datetime.now(),
        )
    )

    assert task.task_dict["Fight"] is False
    assert task.cur_user_log.status == "Success!"


@pytest.mark.parametrize("quick", [False, True])
def test_fight_stays_pending_when_no_fight_task_completes(quick) -> None:
    task = object.__new__(AutoProxyTask)
    task.cur_user_config = MaaUserConfig()
    asyncio.run(task.cur_user_config.set("Info", "IfQuickConfig", quick))
    task.cur_user_log = SimpleNamespace(content=[], status="")
    task.script_info = SimpleNamespace(log="")
    task.task_dict = dict.fromkeys(MAA_TASKS, False)
    task.task_dict["Fight"] = quick
    task.mode = "Routine"
    task.wait_event = SimpleNamespace(set=lambda: None)

    asyncio.run(
        task.check_log(
            ["任务出错: 理智作战\n", "任务已全部完成！\n"],
            datetime.now(),
        )
    )

    assert task.task_dict["Fight"] is quick
    assert task.cur_user_log.status == "MAA 部分任务执行失败"
