"""协议空间与基质独立控制，以及送货失败对后续任务的阻断。"""

import importlib
import json
import uuid
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app.config import ConfigCollection, config_manager
from app.models.config import MaaEndConfig, MaaEndPlanConfig, MaaEndUserConfig
from app.models.task import TaskItem, TaskMode, TaskScriptItem, TaskUserItem
from app.task.MaaEnd.AutoProxy import AutoProxyTask
from app.task.MaaEnd.tools.backup_archive import group_overlay
from app.utils import MAAEND_TASKS
from tests.config_support import activate_config


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "strategy,kind,enabled,expected",
    [
        ("Inventory", "Essence", True, (True, False)),
        ("MAS", "Essence", True, (False, True)),
        ("MAS", "OperatorProgression", True, (True, False)),
        ("Native", "Essence", True, (True, True)),
        ("Inventory", "Essence", False, (False, False)),
    ],
)
async def test_old_switch_migrates_without_enabling_extra_tasks(
    strategy, kind, enabled, expected
):
    users = ConfigCollection.build([MaaEndUserConfig])
    await users.activate()
    uid = users.add(
        MaaEndUserConfig,
        payload={
            "Info": {"SanityStrategy": strategy},
            "Task": {
                "IfSanity": enabled,
                "SanityTaskType": kind,
                "DailyOnceTasks": '["Sanity"]',
            },
            "Data": {"PeriodTaskRecords": '{"daily":{"Sanity":"2026-11-16"}}'},
        },
    )
    await users.commit()
    user = users[uid]
    assert (user.Task.IfProtocolSpace, user.Task.IfAutoEssence) == expected
    assert json.loads(user.Task.DailyOnceTasks) == ["ProtocolSpace", "AutoEssence"]
    assert json.loads(user.Data.PeriodTaskRecords)["daily"] == {
        "ProtocolSpace": "2026-11-16",
        "AutoEssence": "2026-11-16",
    }
    restored = group_overlay(
        {"SanityStrategy": strategy, "IfSanity": enabled, "SanityTaskType": kind}
    )
    assert (
        restored["Task"]["IfProtocolSpace"],
        restored["Task"]["IfAutoEssence"],
    ) == expected


@pytest_asyncio.fixture
async def proxy_fixture(monkeypatch, isolated_app_paths):
    module = importlib.import_module("app.task.MaaEnd.AutoProxy")
    app_root = isolated_app_paths.work_path / "app"
    app_root.mkdir()
    monkeypatch.chdir(app_root)
    root = isolated_app_paths.work_path / "maaend"
    root.mkdir()
    (root / "resource").mkdir()
    names = [
        "SeizeDeliveryJobs",
        "AutoEssence",
        "ProtocolSpace",
        "CloseGamePC",
        "AccountSwitch",
    ]
    (root / "interface.json").write_text(
        json.dumps(
            {
                "interface_version": 2,
                "name": "MaaEnd",
                "languages": {"zh_cn": "zh.json"},
                "controller": [{"name": "Win32-Front", "type": "Win32", "win32": {}}],
                "resource": [{"name": "Default", "path": ["resource"]}],
                "import": ["ProtocolSpace.json"],
            }
        )
    )
    (root / "zh.json").write_text(
        json.dumps(
            {"task.SceneManager.focus.color_match_failed_prefix": "颜色识别失败"}
        )
    )
    options = {
        "ProtocolSpaceMode": {
            "type": "select",
            "cases": [{"name": "TargetInventory"}, {"name": "ByCount"}],
        },
        "SupplyPlanLimits": {
            "type": "input",
            "inputs": [
                {"name": "test_material", "label": "测试材料", "verify": "[0-9]+"}
            ],
        },
        "ProtocolSpaceObtainModeClaim": {
            "type": "select",
            "cases": [{"name": "ObtainScaling2"}],
        },
        "ProtocolSpaceUseSpMedication": {
            "type": "select",
            "cases": [{"name": "UseMedication"}, {"name": "EndTask"}],
        },
    }
    (root / "ProtocolSpace.json").write_text(
        json.dumps(
            {
                "task": [
                    {
                        "name": name,
                        "label": name,
                        "entry": name,
                        "option": list(options) if name == "ProtocolSpace" else [],
                    }
                    for name in names
                ],
                "option": options,
            }
        )
    )
    config = await activate_config(
        MaaEndConfig(
            Info={"Path": root},
            Game={"LaunchMode": "MaaEnd", "CloseOnFinish": False},
            Run={"RunTimesLimit": 2, "IfSaveLogBundle": False},
        )
    )
    users = ConfigCollection.build([MaaEndUserConfig])
    await users.activate()
    uid = users.add(
        MaaEndUserConfig,
        payload={
            "Info": {"SanityStrategy": "Inventory"},
            "Task": {
                **{f"If{name}": False for name in MAAEND_TASKS},
                "IfSanity": True,
                "IfSeizeDeliveryJobs": True,
                "IfProtocolSpace": True,
                "IfAutoEssence": True,
                "IfAutoCollect": False,
                "AutoEssenceSpecifiedLocation": "test_location",
                "SupplyPlanLimits": '{"test_material":"10"}',
                "DailyOnceTasks": '["ProtocolSpace", "AutoEssence"]',
            },
        },
    )
    await users.commit()
    info = TaskItem(info={"mode": TaskMode.AUTO_PROXY})
    await info.activate()
    script_uid = info.scripts.add(
        TaskScriptItem,
        payload={
            "info": {"script_id": str(uuid.uuid4()), "name": "test", "status": "运行"}
        },
    )
    await info.scripts.commit()
    script = info.scripts[script_uid]
    script.users.add(
        TaskUserItem,
        payload={"info": {"user_id": str(uid), "name": "test", "status": "等待"}},
    )
    await script.users.commit()
    await script.set_current_index(0)
    await info.set_current_index(0)
    proxy = AutoProxyTask(
        script, config, users, None, capture_adb=AsyncMock(), capture_win32=AsyncMock()
    )
    from app.task.history_core import TaskHistorySession

    proxy.history = TaskHistorySession(info)
    source = app_root / "data" / script.script_id / "Default" / "ConfigFile"
    source.mkdir(parents=True)
    (source / "mxu-MaaEnd.json").write_text(
        json.dumps(
            {
                "instances": [
                    {
                        "id": "automas",
                        "name": "AUTO-MAS",
                        "tasks": [
                            {
                                "id": name,
                                "taskName": name,
                                "enabled": True,
                                "optionValues": {},
                            }
                            for name in names
                        ],
                    }
                ],
                "settings": {"language": "zh-CN"},
            }
        )
    )
    proxy.maaend_config_file = source / "mxu-MaaEnd.json"
    attempts = []

    async def launch(*args, **kwargs):
        running = json.loads((root / "config/mxu-MaaEnd.json").read_text())
        attempts.append(
            (
                proxy.mode,
                deepcopy(
                    [
                        task
                        for task in running["instances"][0]["tasks"]
                        if task["enabled"]
                    ]
                ),
            )
        )

    process = SimpleNamespace(open_process=launch, kill=AsyncMock())
    monkeypatch.setattr(module, "ProcessManager", lambda: process)
    monkeypatch.setattr(module.process, "kill_process", AsyncMock())
    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(module.Notify, "send_notice", AsyncMock())
    monkeypatch.setattr(proxy, "check", AsyncMock(return_value="Pass"))
    for name in [
        "_start_game",
        "_take_failure_shot",
        "_archive_failure_logs",
        "_update_after_first_stage",
        "kill_managed_process",
    ]:
        monkeypatch.setattr(proxy, name, AsyncMock())
    return proxy, attempts


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    [
        "delivery_failure",
        "both",
        "stock_completed",
        "essence_off",
        "native",
        "essence_retry",
    ],
)
async def test_native_tasks_run_independently_in_one_queue(
    proxy_fixture, monkeypatch, scenario
):
    proxy, attempts = proxy_fixture
    user = proxy.cur_user_config
    if scenario == "stock_completed":
        user.Data.PeriodTaskRecords = json.dumps(
            {"daily": {"ProtocolSpace": proxy.curdate}}
        )
        await user.commit()
    if scenario == "essence_off":
        user.Task.IfAutoEssence = False
        await user.commit()

    if scenario == "native":
        user.Info.SanityStrategy = "Native"
        user.Info.AutoEssenceMode = "Native"
        await user.commit()
        path = proxy.maaend_config_file
        original = json.loads(path.read_text())
        for task in original["instances"][0]["tasks"]:
            task["optionValues"] = {"preserved": {"type": "switch", "value": True}}
        path.write_text(json.dumps(original))

    async def upstream_result(offsets):
        lines = []
        for task in attempts[-1][1]:
            name = task["taskName"]
            failure = (scenario == "delivery_failure" and proxy.mode == "Delivery") or (
                scenario == "essence_retry"
                and proxy.mode == "Routine"
                and len(attempts) == 2
                and name == "AutoEssence"
            )
            result = "失败" if failure else "完成"
            lines.extend([f"任务开始: {name}\n", f"任务{result}: {name}\n"])
        await proxy.check_log(lines, datetime.now().astimezone(), if_stream_end=True)

    monkeypatch.setattr(proxy, "_wait_maaend_stage", upstream_result)
    await proxy.main_task()
    if scenario == "delivery_failure":
        assert [mode for mode, _ in attempts] == ["Delivery", "Delivery"]
        assert proxy.run_book["Routine"] is False
    else:
        assert [mode for mode, _ in attempts] == (
            ["Delivery", "Routine", "Routine"]
            if scenario == "essence_retry"
            else ["Delivery", "Routine"]
        )
        expected = {
            "both": ["ProtocolSpace", "AutoEssence"],
            "stock_completed": ["AutoEssence"],
            "essence_off": ["ProtocolSpace"],
            "native": ["ProtocolSpace", "AutoEssence"],
            "essence_retry": ["ProtocolSpace", "AutoEssence"],
        }[scenario]
        tasks = attempts[1][1]
        assert [task["taskName"] for task in tasks] == expected
        if scenario == "native":
            assert all(
                task["optionValues"] == {"preserved": {"type": "switch", "value": True}}
                for task in tasks
            )
        elif tasks[0]["taskName"] == "ProtocolSpace":
            assert (
                tasks[0]["optionValues"]["ProtocolSpaceMode"]["caseName"]
                == "TargetInventory"
            )
        if scenario == "essence_retry":
            assert [task["taskName"] for task in attempts[2][1]] == ["AutoEssence"]
        assert all(proxy.run_book.values())


@pytest.mark.asyncio
async def test_old_plan_routes_each_native_task_and_unbinds_on_delete(monkeypatch):
    plans = ConfigCollection.build([MaaEndPlanConfig])
    monkeypatch.setitem(config_manager._collections, "PlanConfig", plans)
    await plans.activate()
    plan_id = plans.add(
        MaaEndPlanConfig,
        payload={
            "ALL": {
                "Key": {
                    "SanityTaskType": "Essence",
                    "AutoEssenceSpecifiedLocation": "test_location",
                }
            }
        },
    )
    await plans.commit()
    monkeypatch.setattr(MaaEndUserConfig, "related_config", {"PlanConfig": plans})
    users = ConfigCollection.build([MaaEndUserConfig])
    await users.activate()
    uid = users.add(
        MaaEndUserConfig,
        payload={
            "Info": {"SanityStrategy": "MAS", "SanityMode": str(plan_id)},
            "Task": {"IfSanity": True},
        },
    )
    await users.commit()
    user = users[uid]
    assert str(user.Info.AutoEssenceMode) == str(plan_id)
    assert (
        user.get_effective_essence_task_key()["AutoEssenceSpecifiedLocation"]
        == "test_location"
    )
    assert user.get_effective_sanity_task_key()[0]["SanityTaskType"] == "Essence"
    from app.models.schema import MaaEndProtocolSpacePlanKey

    plans[plan_id].ALL.Key = MaaEndProtocolSpacePlanKey()
    await plans[plan_id].commit()
    assert user.get_effective_essence_task_key() is None
    assert (
        user.get_effective_sanity_task_key()[0]["SanityTaskType"]
        == "OperatorProgression"
    )
    plans.remove(plan_id)
    await plans.commit()
    assert user.Info.SanityMode == "Fixed"
    assert user.Info.AutoEssenceMode == "Fixed"
