"""真实日志判态、队列下发与主循环共同守护体力/非体力任务的重试边界。"""

import importlib
import json
import uuid
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import ConfigCollection
from app.core.script_update_queue import script_task_retrying
from app.models.config import MaaConfig, MaaUserConfig
from app.models.emulator import DeviceInfo, DeviceStatus
from app.models.task import TaskItem, TaskMode
from app.task.MAA.AutoProxy import AutoProxyTask
from app.task.MAA.base_preset import get_maa_base_preset
from app.task.MAA.constants import MAA_TASKS
from app.task.MAA.tools.cultivate.types import (
    CultivatePlan,
    FarmEntry,
    Goal,
    OperatorTarget,
    Progression,
    ProgressionSnapshot,
    Requirement,
)
from tests.config_support import activate_config
from tests.task_stop_support import add_script


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "failures",
        "source",
        "recover",
        "pause_on_retry",
        "expected_modes",
        "routine_success",
    ),
    [
        (("基建换班",), "cultivate", True, False, ["Routine"] * 2, True),
        (("基建换班",), "managed", False, False, ["Routine"] * 3, False),
        (("理智任务",), "managed", True, False, ["Routine"], False),
        (("理智任务", "基建换班"), "managed", True, False, ["Routine"] * 2, False),
        (
            ("库存保持与干员养成", "基建换班"),
            "managed",
            True,
            False,
            ["Routine"] * 2,
            False,
        ),
        (
            ("活动关均衡理智", "基建换班"),
            "managed",
            True,
            False,
            ["Routine"] * 2,
            False,
        ),
        (("剿灭作战",), "managed", True, False, ["Annihilation", "Routine"], True),
        (("基建换班",), "source", True, False, ["Routine"], False),
        (("基建换班",), "native", True, False, ["Routine"], False),
        (("干员培养",), "cultivate", True, False, ["Routine"] * 2, True),
        (("更新数据",), "cultivate", True, False, ["Routine"] * 2, True),
        (("ADB",), "cultivate", True, True, ["Routine"] * 2, True),
        (("干员培养",), "cultivate", True, True, ["Routine"] * 3, False),
    ],
    ids=[
        "completed-cultivation-budget",
        "daily-limit",
        "sanity-only",
        "mixed-fight",
        "mixed-depot",
        "mixed-event-depot",
        "annihilation-stops",
        "source-queue",
        "native-queue",
        "cultivation-recovery",
        "data-update-recovery",
        "runtime-paused-cultivation",
        "failed-paused-cultivation",
    ],
)
async def test_task_failure_retry_scope(
    monkeypatch,
    isolated_app_paths,
    failures,
    source,
    recover,
    pause_on_retry,
    expected_modes,
    routine_success,
):
    module = importlib.import_module("app.task.MAA.AutoProxy")
    root = isolated_app_paths.work_path / "maa"
    root.mkdir()
    config = await activate_config(MaaConfig(Info={"Path": root}))
    annihilation = "剿灭作战" in failures
    cultivate = source == "cultivate"
    users = ConfigCollection.build([MaaUserConfig])
    await users.activate()
    uid = users.add(
        MaaUserConfig,
        payload={
            "Info": {
                "IfQuickConfig": source != "source",
                "Base": "native" if source == "native" else "shared",
            },
            "Task": {
                **{f"If{task}": False for task in MAA_TASKS},
                "IfStartUp": True,
                "IfFight": True,
                "IfInfrast": True,
                "IfRecruit": True,
                "IfCultivate": cultivate,
                "CultivateAllOwned": False,
                "CultivateAutoRaise": cultivate,
                "CultivateSklandAccount": "bound" if pause_on_retry else "",
                "CultivateSklandUid": "bound" if pause_on_retry else "",
                "CultivateSkipDuringActivity": False,
                "CultivateSkipDuringResourceCollection": False,
                "CultivateTargets": json.dumps(
                    [
                        {
                            "operator_id": "one",
                            "goals": [{"kind": "skill", "to_level": 7}],
                        }
                    ]
                )
                if cultivate
                else "[]",
                "CultivateMedicineNumb": 2 if cultivate else None,
                "CultivateStoneNumb": 1 if cultivate else None,
                "IfDepotMaintain": "库存保持与干员养成" in failures,
                "IfEventDepotMaintain": "活动关均衡理智" in failures,
                "EventDepotMaintainPlans": '[{"StageType":"material","StageIndex":1,"DropCount":1}]',
                "Annihilation": "Annihilation" if annihilation else "Close",
                "AnnihilationStartWeekday": "Monday",
            },
        },
    )
    await users.commit()
    task_info = TaskItem(info={"mode": TaskMode.AUTO_PROXY})
    script = await add_script(task_info, str(uuid.uuid4()), str(uid))
    user = script.user_list[0]
    emulator = SimpleNamespace(
        open=AsyncMock(return_value=DeviceInfo("test", DeviceStatus.ONLINE, "")),
        close=AsyncMock(return_value=True),
    )
    proxy = AutoProxyTask(script, config, users, emulator, capture_adb=AsyncMock())
    from app.task.history_core import TaskHistorySession

    proxy.history = TaskHistorySession(task_info)
    attempts = []
    queue = []

    async def set_maa(device):
        nonlocal queue
        gui = get_maa_base_preset()
        if source in ("managed", "cultivate"):
            await proxy._apply_maa_quick_config(gui)
        queue = gui["Configurations"]["Default"]["TaskQueue"]

    async def open_process(*args, **kwargs):
        attempts.append((proxy.mode, deepcopy(queue)))

    process = SimpleNamespace(
        open_process=open_process,
        kill=AsyncMock(),
        is_running=AsyncMock(return_value=True),
        main_pid=1,
    )

    class LogMonitor:
        def __init__(self, time_stamp_range, time_stamp_format, callback, **kwargs):
            self.callback = callback

        async def start_monitor_file(self, *args, **kwargs):
            succeeded = recover and (
                proxy.mode == "Routine" and (annihilation or len(attempts) > 1)
            )
            errors, lines = [], []
            for task in queue:
                if not task.get("IsEnable"):
                    continue
                name = task["Name"]
                failed = not succeeded and name in failures
                lines.append(f"{'任务出错' if failed else '完成任务'}: {name}\n")
                if failed:
                    errors.append(name)
            lines.append(
                "任务已结束，以下任务出现错误: " + ", ".join(errors)
                if errors
                else "任务已全部完成！"
            )
            if "ADB" in failures and len(attempts) == 1:
                lines = ["请 ｢检查连接设置｣ → ｢尝试重启模拟器与 ADB｣ → ｢重启电脑｣"]
            await self.callback(lines, datetime.now().astimezone())

        async def stop(self):
            pass

    monkeypatch.setattr(module, "ProcessManager", lambda: process)
    monkeypatch.setattr(module, "LogMonitor", LogMonitor)
    # 隔离文件落盘、进程/截图、通知和外部关卡查询，保留真实队列构造与重试决策。
    monkeypatch.setattr(proxy, "set_maa", set_maa)
    monkeypatch.setattr(proxy, "_take_failure_shot", AsyncMock(return_value=None))
    monkeypatch.setattr(
        module.maa_stage_service,
        "get_stage_info",
        AsyncMock(return_value={"Activity": [{"Value": "ACT-1", "Drop": "30013"}]}),
    )
    monkeypatch.setattr(module.process, "kill_process", AsyncMock())
    monkeypatch.setattr(module.Notify, "send_notice", AsyncMock())
    monkeypatch.setattr(module.Publisher, "send", AsyncMock())
    if cultivate:
        # 练度与材料缺口在两次尝试间保持不变，模拟药石额度用尽后仍未达目标。
        target = OperatorTarget("one", (Goal("skill", "", 7),))
        snapshot = ProgressionSnapshot(
            source="manual",
            timestamp=datetime.now().timestamp(),
            data=Progression(
                elite=1, level=50, masteries={}, modules={}, skill_level=6
            ),
        )
        monkeypatch.setattr(module, "resolve_progression", lambda **kwargs: snapshot)
        monkeypatch.setattr(
            module, "read_installed_release", lambda _: ("v6.21.0", "x64")
        )
        monkeypatch.setattr(
            module.depot_cultivate_service,
            "operator_catalog",
            AsyncMock(
                return_value=[
                    {
                        "value": "one",
                        "label": "干员",
                        "profession": "warrior",
                        "skills": [],
                    }
                ]
            ),
        )

        async def skland_progression(*args, **kwargs):
            # 首次同步成功，重试时外部查询失败，真实门控暂停培养。
            return (
                ({"one": snapshot.data}, snapshot.timestamp)
                if pause_on_retry and not attempts
                else None
            )

        monkeypatch.setattr(
            module.maa_api,
            "get_cultivate_skland_progression",
            skland_progression,
        )
        monkeypatch.setattr(
            module.depot_cultivate_service,
            "prepare_cultivate",
            AsyncMock(
                return_value=(
                    [target],
                    CultivatePlan(
                        entries=(
                            FarmEntry(item_id="30012", amount=100, stage_code="1-7"),
                        ),
                        reservations=(Requirement(item_id="30012", amount=100),),
                    ),
                    True,
                    (target,),
                )
            ),
        )

    retried_modes = []

    async def on_retry():
        retried_modes.append(proxy.mode)

    retry_token = script_task_retrying.set(on_retry)
    try:
        await proxy.main_task()
    finally:
        script_task_retrying.reset(retry_token)
        await proxy.callbacks.close()

    assert [mode for mode, _ in attempts] == expected_modes
    # 只有同一模式重新启动 MAA 才通知 L2；切到下一个模式不应重置成功信号。
    assert retried_modes == [
        mode
        for index, (mode, _) in enumerate(attempts)
        if index > 0 and attempts[index - 1][0] == mode
    ]
    assert proxy.run_book["Annihilation"] is (not annihilation)
    assert proxy.run_book["Routine"] is routine_success
    records = [record for _, record in user.iter_history_logs()]
    assert len(records) == len(expected_modes)
    assert records[0].status == (
        "MAA 的 ADB 连接异常" if "ADB" in failures else "MAA 部分任务执行失败"
    )
    if len(attempts) > 1 and recover:
        assert records[-1].status == (
            "MAA 部分任务执行失败"
            if pause_on_retry and not routine_success
            else "Success!"
        )
        enabled = {task["Name"] for task in attempts[-1][1] if task.get("IsEnable")}
        if "基建换班" in failures or annihilation or "ADB" in failures:
            assert "基建换班" in enabled
        if not annihilation:
            if "ADB" not in failures:
                assert "自动公招" not in enabled
            assert not set(failures).intersection(
                enabled - {"基建换班", "干员培养", "更新数据"}
            )
    if cultivate:
        first_enabled = {
            task["Name"] for task in attempts[0][1] if task.get("IsEnable")
        }
        assert {"干员培养", "更新数据"} <= first_enabled
        assert ("干员培养" in enabled) is (
            "干员培养" in failures and not pause_on_retry
        )
        assert ("更新数据" in enabled) is bool(
            {"ADB", "更新数据"}.intersection(failures)
        )
        first_farm = next(
            task
            for task in attempts[0][1]
            if task["TaskType"] == "DepotMaintain"
            and task["Name"] == "库存保持与干员养成"
        )
        assert first_farm["PlanList"][0].get("MedicineCount") == 2, first_farm
        assert first_farm["PlanList"][0]["StoneCount"] == 1
        if "ADB" not in failures:
            assert not any(
                task["TaskType"] in ("Fight", "DepotMaintain") and task.get("IsEnable")
                for task in attempts[1][1]
            )
        assert json.loads(proxy.cur_user_config.Task.CultivateTargets)
