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
from app.core.task_manager.manager import TaskInfo
from app.models.config import MaaConfig, MaaUserConfig
from app.models.emulator import DeviceInfo, DeviceStatus
from app.models.task import LogRecord, ScriptItem, UserItem
from app.task.MAA.AutoProxy import AutoProxyTask, _should_retry_maa
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failures", "source", "recover", "expected_modes", "routine_success"),
    [
        (("基建换班",), "managed", True, ["Routine"] * 2, True),
        (("基建换班",), "cultivate", True, ["Routine"] * 2, True),
        (("基建换班",), "managed", False, ["Routine"] * 3, False),
        (("理智任务",), "managed", True, ["Routine"], False),
        (("理智任务", "基建换班"), "managed", True, ["Routine"] * 2, False),
        (("库存保持与干员养成", "基建换班"), "managed", True, ["Routine"] * 2, False),
        (("活动关均衡理智", "基建换班"), "managed", True, ["Routine"] * 2, False),
        (("剿灭作战",), "managed", True, ["Annihilation", "Routine"], True),
        (("基建换班",), "source", True, ["Routine"], False),
        (("基建换班",), "native", True, ["Routine"], False),
    ],
    ids=[
        "daily-recovery",
        "completed-cultivation-budget",
        "daily-limit",
        "sanity-only",
        "mixed-fight",
        "mixed-depot",
        "mixed-event-depot",
        "annihilation-stops",
        "source-queue",
        "native-queue",
    ],
)
async def test_task_failure_retry_scope(
    monkeypatch,
    isolated_app_paths,
    failures,
    source,
    recover,
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
                "CultivateAutoRaise": False,
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
    user = UserItem(str(uid), "test", "等待")
    script = ScriptItem(
        str(uuid.uuid4()), "MAA", "运行", user_list=[user], current_index=0
    )
    task_info = TaskInfo("AutoProxy", "test", "queue", None, None)
    monkeypatch.setattr(task_info, "schedule_on_change", lambda: None)
    task_info.script_list = [script]
    emulator = SimpleNamespace(
        open=AsyncMock(return_value=DeviceInfo("test", DeviceStatus.ONLINE, "")),
        close=AsyncMock(return_value=True),
    )
    proxy = AutoProxyTask(script, config, users, emulator, capture_adb=AsyncMock())
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
    monkeypatch.setattr(module.System, "kill_process", AsyncMock())
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
            module.maa_api,
            "get_cultivate_skland_progression",
            AsyncMock(return_value=None),
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

    await proxy.main_task()

    assert [mode for mode, _ in attempts] == expected_modes
    assert proxy.run_book["Annihilation"] is (not annihilation)
    assert proxy.run_book["Routine"] is routine_success
    records = [record for _, record in user.iter_history_logs()]
    assert len(records) == len(expected_modes)
    assert records[0].status == "MAA 部分任务执行失败"
    if len(attempts) > 1 and recover:
        assert records[-1].status == "Success!"
        enabled = {task["Name"] for task in attempts[-1][1] if task.get("IsEnable")}
        assert "基建换班" in enabled
        if not annihilation:
            assert "自动公招" not in enabled
            assert not set(failures).intersection(enabled - {"基建换班"})
    if cultivate:
        assert proxy.cur_user_config.Task.IfCultivate
        assert json.loads(proxy.cur_user_config.Task.CultivateTargets)
        assert any(task["Name"] == "库存保持与干员养成" for task in attempts[0][1]), (
            attempts[0][1]
        )
        first_farm = next(
            task
            for task in attempts[0][1]
            if task["TaskType"] == "DepotMaintain"
            and task["Name"] == "库存保持与干员养成"
        )
        assert first_farm["PlanList"][0].get("MedicineCount") == 2, first_farm
        assert first_farm["PlanList"][0]["StoneCount"] == 1
        assert not any(
            task["TaskType"] in ("Fight", "DepotMaintain") and task.get("IsEnable")
            for task in attempts[1][1]
        )
        assert json.loads(proxy.cur_user_config.Task.CultivateTargets)


@pytest.fixture
def extra_proxy(monkeypatch, isolated_app_paths):
    async def make(name):
        root = isolated_app_paths.work_path / "maa"
        root.mkdir()
        config = await activate_config(MaaConfig(Info={"Path": root}))
        users = ConfigCollection.build([MaaUserConfig])
        await users.activate()
        uid = users.add(
            MaaUserConfig,
            payload={
                "Task": {
                    "IfDepotMaintain": False,
                    "IfEventDepotMaintain": False,
                    "IfCultivate": True,
                    "CultivateAutoRaise": True,
                    "CultivateTargets": "[]",
                }
            },
        )
        await users.commit()
        user = UserItem(str(uid), "test", "运行")
        script = ScriptItem(
            str(uuid.uuid4()), "MAA", "运行", user_list=[user], current_index=0
        )
        task_info = TaskInfo("AutoProxy", "test", "queue", None, None)
        monkeypatch.setattr(task_info, "schedule_on_change", lambda: None)
        task_info.script_list = [script]
        proxy = AutoProxyTask(
            script, config, users, SimpleNamespace(), capture_adb=AsyncMock()
        )
        await proxy.prepare()
        proxy.mode = "Routine"
        # 与真实队列下发一致：常规任务已结束，只有附加任务等待 MAA 结果。
        proxy.task_dict = {task: False for task in MAA_TASKS}
        proxy.task_dict[name] = True
        proxy.cur_user_log = LogRecord()
        return proxy, task_info

    return make


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["干员培养", "更新数据"])
async def test_extra_non_sanity_task_can_retry_then_complete(extra_proxy, name):
    proxy, task_info = await extra_proxy(name)
    failure_name = f"{name} #2" if name == "干员培养" else name
    failed_log = (
        f"完成任务: {name} #1\n任务出错: {failure_name}\n"
        f"任务已结束，以下任务出现错误: {failure_name}"
    )

    await proxy.check_log([failed_log], datetime.now().astimezone())

    assert proxy.cur_user_log.status == "MAA 部分任务执行失败"
    assert _should_retry_maa(
        proxy.cur_user_log.status,
        failed_log,
        managed=True,
        pending_tasks=proxy.task_dict,
    )

    proxy.cur_user_log = LogRecord()
    await proxy.check_log(
        [f"完成任务: {name}\n任务已全部完成！"], datetime.now().astimezone()
    )

    assert proxy.cur_user_log.status == "Success!"
    assert proxy.task_dict[name] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["干员培养", "更新数据"])
@pytest.mark.parametrize("explicit_failure", [False, True])
async def test_extra_task_rebuild_distinguishes_runtime_and_task_failure(
    extra_proxy, monkeypatch, name, explicit_failure
):
    proxy, task_info = await extra_proxy(name)
    log = (
        f"任务出错: {name}\n任务已结束，以下任务出现错误: {name}"
        if explicit_failure
        else "请 ｢检查连接设置｣ → ｢尝试重启模拟器与 ADB｣ → ｢重启电脑｣"
    )
    await proxy.check_log([log], datetime.now().astimezone())
    module = importlib.import_module("app.task.MAA.AutoProxy")
    monkeypatch.setattr(
        module.maa_stage_service,
        "get_stage_info",
        AsyncMock(return_value={"Activity": []}),
    )
    monkeypatch.setattr(module.Publisher, "send", AsyncMock())
    monkeypatch.setattr(
        module.maa_api, "get_cultivate_skland_progression", AsyncMock(return_value=None)
    )

    # 当前目标为空，真实规划不会再次下发附加任务。
    await proxy._apply_maa_quick_config(get_maa_base_preset())

    assert proxy.task_dict.get(name, False) is explicit_failure
    proxy.cur_user_log = LogRecord()
    await proxy.check_log(
        ["完成任务: 开始唤醒\n任务已全部完成！"], datetime.now().astimezone()
    )
    assert proxy.cur_user_log.status == (
        "MAA 部分任务执行失败" if explicit_failure else "Success!"
    )
