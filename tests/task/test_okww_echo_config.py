"""4C 面板读取实际来源并保留账号已保存配置。"""

import uuid
from types import SimpleNamespace

import pytest

from app.models.config.script import OkwwConfig, OkwwUserConfig
from app.task.Okww import api_service
from app.task.Okww.tools import backup_archive


@pytest.mark.asyncio
@pytest.mark.parametrize("base", ["native", "shared", "independent"])
async def test_echo_panel_uses_source_until_account_saved(tmp_path, monkeypatch, base):
    install = tmp_path / "script-install"
    install.mkdir()
    app_root = tmp_path / "mas"
    app_root.mkdir()
    monkeypatch.chdir(app_root)
    config = OkwwConfig()
    await config.activate()
    user_id = config.UserData.add(OkwwUserConfig, payload={"Info": {"Base": base}})
    await config.UserData.commit()
    script_id = uuid.uuid4()
    config.Info.RootPath = install
    await config.commit()
    monkeypatch.setattr(
        api_service, "Config", SimpleNamespace(ScriptConfig={script_id: config})
    )
    monkeypatch.setattr(backup_archive, "mas_config_dir", lambda *_: install)
    root = install / "data/apps/ok-ww/working/configs" if base == "native" else install
    root.mkdir(parents=True, exist_ok=True)
    path = root / "FarmEchoTask.json"
    path.write_text('{"Repeat Farm Count": 23, "Boss": "Lorelei"}', encoding="utf-8")
    values = api_service.read_task_config(str(script_id), str(user_id), "echo")
    assert values["Repeat Farm Count"] == 23
    assert values["Boss"] == "Lorelei"
    assert config.UserData[user_id].Task.FarmEchoConfig == {}
    config.UserData[user_id].Task.FarmEchoConfig = {"Repeat Farm Count": 7}
    await config.UserData[user_id].commit()
    assert (
        api_service.read_task_config(str(script_id), str(user_id), "echo")[
            "Repeat Farm Count"
        ]
        == 7
    )
    assert (
        path.read_text(encoding="utf-8")
        == '{"Repeat Farm Count": 23, "Boss": "Lorelei"}'
    )
    path.write_text(
        '{"Repeat Farm Count":23,"New source field":false}', encoding="utf-8"
    )
    updated = api_service.read_task_config(str(script_id), str(user_id), "echo")
    assert updated["New source field"] is False
    assert updated["Repeat Farm Count"] == 7


@pytest.mark.asyncio
@pytest.mark.parametrize("view_only", [False, True])
async def test_gui_echo_changes_return_to_panel_without_polluting_base(
    tmp_path, view_only
):
    import asyncio
    from unittest.mock import AsyncMock

    from app.task.Okww.ScriptConfig import ScriptConfigTask

    user = OkwwUserConfig()
    await user.activate()
    original = b'{"Repeat Farm Count":100}'
    path = tmp_path / "FarmEchoTask.json"
    path.write_text('{"Repeat Farm Count":7}', encoding="utf-8")
    task = ScriptConfigTask.__new__(ScriptConfigTask)
    task.wait_event = asyncio.Event()
    task._kill_processes = AsyncMock()
    task.view_only = view_only
    task.crashed = False
    task.panel_user = user
    task.panel_originals = {"FarmEchoTask.json": original}
    task.script_config_path = tmp_path
    task.use_mas_config = False
    task.cur_user_item = SimpleNamespace(set_state=AsyncMock())
    await task.final_task()
    if view_only:
        assert user.Task.FarmEchoConfig == {}
    else:
        assert user.Task.FarmEchoConfig == {"Repeat Farm Count": 7}
        assert path.read_bytes() == original


@pytest.mark.parametrize(
    "value,kind",
    [
        (True, "bool"),
        (2.5, "number"),
        ("text", "string"),
        ([1, 2], "json"),
        ({"nested": True}, "json"),
    ],
)
def test_new_native_fields_are_described_without_a_registered_field(value, kind):
    from app.task.Okww.tools.config_fields import describe_fields

    fields = describe_fields({"New native field": value, "_internal": False})
    assert len(fields) == 1
    assert fields[0]["name"] == "New native field"
    assert fields[0]["type"] == kind


@pytest.mark.asyncio
async def test_daily_new_field_reaches_runtime_without_losing_plan_fields(tmp_path):
    import json

    from app.task.Okww.AutoProxy import AutoProxyTask

    user = OkwwUserConfig()
    user.Task.DailyConfig = {
        "New native field": {"nested": [1, 2]},
        "Which to Farm": "Simulation Challenge",
    }
    user.Task.WhichToFarm = "Forgery Challenge"
    task = AutoProxyTask.__new__(AutoProxyTask)
    task.cur_user_config = user
    task.script_config_path = tmp_path
    task._apply_mas_overrides()
    actual = json.loads((tmp_path / "DailyTask.json").read_text(encoding="utf-8"))
    assert actual["New native field"] == {"nested": [1, 2]}
    assert actual["Which to Farm"] == "Forgery Challenge"


@pytest.mark.asyncio
async def test_dynamic_save_keeps_unknown_data_and_updates_legacy_daily_fields(
    monkeypatch,
):
    config = OkwwConfig()
    await config.activate()
    uid = config.UserData.add(OkwwUserConfig)
    await config.UserData.commit()
    sid = uuid.uuid4()
    user = config.UserData[uid]

    async def store_update(script_id, user_id, data, *, precondition):
        assert precondition()
        await user.update(OkwwUserConfig.model_validate(data))
        return True

    monkeypatch.setattr(
        api_service,
        "Config",
        SimpleNamespace(ScriptConfig={sid: config}, update_user=store_update),
    )
    values = {
        "Which to Farm": "Simulation Challenge",
        "New task option": ["one", "two"],
    }
    await api_service.save_task_config(str(sid), str(uid), "daily", values)
    assert user.Task.WhichToFarm == "Simulation Challenge"
    assert user.Task.DailyConfig == values
    assert user.Task.CustomArguments == "-t DailyTask"


def test_native_translation_files_follow_installation_updates(tmp_path):
    from app.task.Okww.tools.config_fields import load_labels

    directory = tmp_path / "data/apps/ok-ww/working/i18n/zh_CN/LC_MESSAGES"
    directory.mkdir(parents=True)
    path = directory / "ok.po"
    path.write_text('msgid "Walk"\nmsgstr "后退再前进"\n', encoding="utf-8")
    qt = tmp_path / "data/apps/ok-ww/working/ok/ui/qt/i18n/zh_CN.ts"
    qt.parent.mkdir(parents=True)
    qt.write_text(
        "<TS><context><message><source>Exit After Task</source><translation>完成后退出</translation></message></context></TS>",
        encoding="utf-8",
    )
    assert load_labels(tmp_path, "zh_CN")["Walk"] == "后退再前进"
    assert load_labels(tmp_path, "zh_CN")["Exit After Task"] == "完成后退出"
    path.write_text('msgid "Walk"\nmsgstr "更新后的名称"\n', encoding="utf-8")
    assert load_labels(tmp_path, "zh_CN")["Walk"] == "更新后的名称"
    assert load_labels(tmp_path, "en_US") == {}


@pytest.mark.parametrize("quick", [True, False])
def test_advanced_panels_reach_runtime_under_the_global_switch(tmp_path, quick):
    import json

    from app.task.Okww.AutoProxy import AutoProxyTask

    user = OkwwUserConfig()
    user.Info.IfQuickConfig = quick
    user.Task.NativeConfigs = {
        "NightmareNestTask.json": {"Which to Farm": ["Tacet Discord Nest"]},
        "AutoCombatTask.json": {"Switch to Healer before and after Combat": False},
        "Character Config.json": {"Iuno C6": True},
        "Monthly Card Config.json": {"Monthly Card Time": 8},
    }
    task = AutoProxyTask.__new__(AutoProxyTask)
    task.cur_user_config = user
    task.script_config_path = tmp_path
    task._apply_mas_overrides()
    for filename, expected in user.Task.NativeConfigs.items():
        path = tmp_path / filename
        if quick:
            assert json.loads(path.read_text(encoding="utf-8")) == expected
        else:
            assert not path.exists()


def test_nightmare_has_distinct_choices_and_daily_has_exit_default():
    from app.task.Okww.tools.config_fields import PANEL_DEFAULTS, describe_fields

    fields = describe_fields(PANEL_DEFAULTS["nightmare"], "nightmare")
    assert fields[0]["options"] == ["Nightmare Purification", "Tacet Discord Nest"]
    assert fields[0]["type"] == "multi_selection"
    assert PANEL_DEFAULTS["daily"]["Exit After Task"] is False


@pytest.mark.asyncio
async def test_plan_fields_are_readonly_and_not_saved_as_account_defaults(monkeypatch):
    from app.models.config import OkwwPlanConfig
    from app.task.Okww.tools import plan as plan_module
    from app.task.Okww.tools.plan import daily_panel_patch

    config = OkwwConfig()
    await config.activate()
    uid = config.UserData.add(OkwwUserConfig)
    await config.UserData.commit()
    user = config.UserData[uid]
    sid, pid = uuid.uuid4(), uuid.uuid4()
    from app.config import ConfigCollection, config_manager

    plans = ConfigCollection.build([OkwwPlanConfig])
    await plans.activate()
    plans.add(
        OkwwPlanConfig,
        uid=pid,
        payload={
            "Info": {"Mode": "ALL"},
            "ALL": {"Key": {"WhichToFarm": "Forgery Challenge"}},
        },
    )
    await plans.commit()
    monkeypatch.setattr(
        config_manager,
        "_collections",
        {
            key: value
            for key, value in config_manager._collections.items()
            if key != "PlanConfig"
        },
    )
    config_manager.register_collection("PlanConfig", plans)
    user.Info.PlanMode = pid
    await user.commit()
    context = SimpleNamespace(ScriptConfig={sid: config}, PlanConfig=plans)
    monkeypatch.setattr(api_service, "Config", context)
    monkeypatch.setattr(plan_module, "Config", context)
    values, fields = api_service.describe_task_config(str(sid), str(uid), "daily")
    assert values["Which to Farm"] == "Forgery Challenge"
    assert values["Exit After Task"] is False
    assert next(field for field in fields if field["name"] == "Which to Farm")[
        "disabled"
    ]
    assert not next(
        field for field in fields if field["name"] == "Exit After Task"
    ).get("disabled", False)
    patch = daily_panel_patch(
        user, {"Which to Farm": "Simulation Challenge", "Exit After Task": True}
    )
    assert "WhichToFarm" not in patch
    assert "Which to Farm" not in patch["DailyConfig"]
    assert patch["DailyConfig"]["Exit After Task"] is True
    assert user.Task.WhichToFarm == "Tacet Suppression"


@pytest.mark.asyncio
async def test_gui_advanced_panels_return_to_account_and_restore_base(tmp_path):
    import asyncio
    from unittest.mock import AsyncMock

    from app.task.Okww.ScriptConfig import ScriptConfigTask

    user = OkwwUserConfig()
    await user.activate()
    original = b'{"Which to Farm":["Tacet Discord Nest"]}'
    (tmp_path / "NightmareNestTask.json").write_text(
        '{"Which to Farm":["Nightmare Purification"]}', encoding="utf-8"
    )
    task = ScriptConfigTask.__new__(ScriptConfigTask)
    task.wait_event = asyncio.Event()
    task._kill_processes = AsyncMock()
    task.view_only = False
    task.crashed = False
    task.panel_user = user
    task.panel_originals = {"NightmareNestTask.json": original}
    task.script_config_path = tmp_path
    task.use_mas_config = False
    task.cur_user_item = SimpleNamespace(set_state=AsyncMock())
    await task.final_task()
    assert user.Task.NativeConfigs["NightmareNestTask.json"] == {
        "Which to Farm": ["Nightmare Purification"]
    }
    assert (tmp_path / "NightmareNestTask.json").read_bytes() == original


@pytest.mark.asyncio
@pytest.mark.parametrize("hour", [-1, 24, 2.5, True])
async def test_monthly_card_hour_rejects_values_outside_native_contract(
    monkeypatch, hour
):
    config = OkwwConfig()
    await config.activate()
    uid = config.UserData.add(OkwwUserConfig)
    await config.UserData.commit()
    sid = uuid.uuid4()
    monkeypatch.setattr(
        api_service, "Config", SimpleNamespace(ScriptConfig={sid: config})
    )
    with pytest.raises(ValueError, match="0.*23"):
        await api_service.save_task_config(
            str(sid), str(uid), "monthly", {"Monthly Card Time": hour}
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("hour", [0, 23])
async def test_monthly_card_time_accepts_midnight_and_last_hour(monkeypatch, hour):
    from app.task.Okww.tools.config_fields import describe_fields

    config = OkwwConfig()
    await config.activate()
    uid = config.UserData.add(OkwwUserConfig)
    await config.UserData.commit()
    sid = uuid.uuid4()
    user = config.UserData[uid]

    async def save(script_id, user_id, data, *, precondition):
        assert precondition()
        await user.update(OkwwUserConfig.model_validate(data))
        return True

    monkeypatch.setattr(
        api_service,
        "Config",
        SimpleNamespace(ScriptConfig={sid: config}, update_user=save),
    )
    await api_service.save_task_config(
        str(sid), str(uid), "monthly", {"Monthly Card Time": hour}
    )
    assert (
        user.Task.NativeConfigs["Monthly Card Config.json"]["Monthly Card Time"] == hour
    )
    field = describe_fields({"Monthly Card Time": hour}, "monthly")[0]
    assert field["minimum"] == 0
    assert field["maximum"] == 23


@pytest.mark.asyncio
async def test_concurrent_advanced_saves_preserve_both_panels(monkeypatch):
    import asyncio

    from app.config import config_manager
    from app.core.config.manager import AppConfig

    config = OkwwConfig()
    await config.activate()
    uid = config.UserData.add(OkwwUserConfig)
    await config.UserData.commit()
    sid = uuid.uuid4()
    owner = SimpleNamespace(
        ScriptConfig={sid: config}, _get_script_config_handler=lambda _: None
    )

    async def save(*args, **kwargs):
        return await AppConfig.update_user(owner, *args, **kwargs)

    monkeypatch.setattr(
        api_service,
        "Config",
        SimpleNamespace(ScriptConfig={sid: config}, update_user=save),
    )
    async with config_manager.execution_gate():
        combat = asyncio.create_task(
            api_service.save_task_config(
                str(sid), str(uid), "combat", {"Auto Target": False}
            )
        )
        monthly = asyncio.create_task(
            api_service.save_task_config(
                str(sid), str(uid), "monthly", {"Check Monthly Card": False}
            )
        )
        await asyncio.sleep(0)
    await asyncio.gather(combat, monthly)
    assert config.UserData[uid].Task.NativeConfigs == {
        "AutoCombatTask.json": {"Auto Target": False},
        "Monthly Card Config.json": {"Check Monthly Card": False},
    }


@pytest.mark.parametrize("quick", [True, False])
def test_echo_override_preserves_source_and_respects_quick_config(tmp_path, quick):
    import json

    from app.task.Okww.AutoProxy import AutoProxyTask

    user = OkwwUserConfig()
    user.Info.IfQuickConfig = quick
    user.Task.FarmEchoConfig = {
        "Teleport to Boss": "Boss Challenge",
        "Repeat Farm Count": 5,
    }
    target = tmp_path / "FarmEchoTask.json"
    target.write_text(json.dumps({"Repeat Farm Count": 100, "unknown": "preserved"}))
    proxy = AutoProxyTask.__new__(AutoProxyTask)
    proxy.cur_user_config = user
    proxy.script_config_path = tmp_path
    proxy._apply_mas_overrides()
    values = json.loads(target.read_text(encoding="utf-8"))
    assert values["Repeat Farm Count"] == (5 if quick else 100)
    assert values["unknown"] == "preserved"
    assert user.Task.FarmEchoConfig["Repeat Farm Count"] == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["echo", "advanced"])
async def test_batch_arguments_grouping_preserves_user_order(tmp_path, scenario):
    from unittest.mock import AsyncMock

    from app.models.task import UserItem
    from app.task.Okww.manager import OkwwManager

    (tmp_path / "ok-ww.exe").touch()
    app_json = tmp_path / "data/apps/ok-ww/app.json"
    app_json.parent.mkdir(parents=True)
    app_json.write_text('{"current_version":"unknown"}')
    native = app_json.parent / "working/configs"
    native.mkdir(parents=True)
    (native / "DailyTask.json").write_text("{}")
    ids = [uuid.uuid4() for _ in range(5)]
    users = [
        UserItem(user_id=str(uid), name=str(i), status="等待")
        for i, uid in enumerate(ids)
    ]
    info = SimpleNamespace(
        task_info=SimpleNamespace(mode="AutoProxy", is_queue_task=False),
        script_id=str(uuid.uuid4()),
        user_list=users,
        current_index=0,
    )

    async def select_user(index):
        info.current_index = index

    info.set_current_index = select_user
    manager = OkwwManager(info)
    # 下发给任务的是已校验的配置；安装路径在此测试中直接使用临时安装目录。
    manager.script_config = SimpleNamespace(
        Info=SimpleNamespace(RootPath=tmp_path),
        Game=SimpleNamespace(AccountSwitchMethod="OKWW", Enabled=False),
        Run=SimpleNamespace(ProxyTimesLimit=0),
    )
    drafts = [None, "-t OtherTask", "-t OtherTask", None, None]
    manager.user_config = {
        uid: OkwwUserConfig.model_validate(
            {
                "Info": {"Id": f"1301234000{i}", "Base": "native"},
                "Task": {
                    "IfCustomArguments": draft is not None,
                    "CustomArguments": draft or '"ignored',
                },
            }
        )
        for i, (uid, draft) in enumerate(zip(ids, drafts))
    }
    if scenario == "advanced":
        manager.user_config[ids[2]].Task.NativeConfigs = {
            "NightmareNestTask.json": {"Which to Farm": ["Nightmare Purification"]}
        }
    if scenario == "echo":
        manager.user_config[ids[2]].Task.FarmEchoConfig = {"Repeat Farm Count": 5}
    manager.game_manager = None
    manager.check = AsyncMock(return_value="Pass")
    manager.prepare = AsyncMock()
    manager.check_user_before_run = AsyncMock(return_value=True)
    manager.notify_user_check_failure = AsyncMock()
    manager._restore_script_config_from_temp = AsyncMock()
    manager.record_user_run_start = lambda user: None
    dispatched = []

    async def run(task):
        dispatched.append(
            ([user.user_id for user in task.participants], task._build_run_arguments())
        )

    manager.spawn = AsyncMock(side_effect=run)
    await manager.main_task()
    default = ["-t", "MultiAccountConfigTask", "-e"]
    expected = [
        ([str(ids[0])], default),
        (
            [str(ids[1])],
            ["-t", "OtherTask"],
        ),
    ]
    if scenario in ("echo", "advanced"):
        expected.append(([str(ids[2])], ["-t", "OtherTask"]))
    expected.append(([str(ids[3]), str(ids[4])], default))
    assert dispatched == expected
    assert manager._restore_script_config_from_temp.await_count == len(expected)


@pytest.mark.asyncio
@pytest.mark.parametrize("view_only", [True, False])
async def test_gui_preview_keeps_historical_panels_instead_of_live_overrides(
    tmp_path, monkeypatch, view_only
):
    import asyncio
    from unittest.mock import AsyncMock

    from app.task.Okww.ScriptConfig import ScriptConfigTask
    from app.utils import io

    monkeypatch.chdir(tmp_path)
    sid, uid = uuid.uuid4(), uuid.uuid4()
    root = tmp_path / "install"
    configs = root / "data/apps/ok-ww/working/configs"
    configs.mkdir(parents=True)
    historical = b'{"Repeat Farm Count":100}'
    path = configs / "FarmEchoTask.json"
    path.write_bytes(historical)
    io.commit_native_config_snapshot(
        tmp_path / "data" / str(sid) / "Temp", configs, script_id=str(sid)
    )
    user = OkwwUserConfig()
    user.Task.FarmEchoConfig = {"Repeat Farm Count": 7}
    task = ScriptConfigTask.__new__(ScriptConfigTask)
    task._kill_processes = AsyncMock()
    task.root_path = root
    task.use_mas_config = False
    task.view_only = view_only
    task.cur_user_item = SimpleNamespace(user_id=str(uid), set_state=AsyncMock())
    task.script_info = SimpleNamespace(script_id=str(sid))
    task.user_config = {uid: user}
    task.panel_originals = {}
    task.panel_user = None
    task.script_config_path = configs
    task.exe_path = root / "ok-ww.exe"
    task.process_manager = SimpleNamespace(open_process=AsyncMock())
    task.wait_event = asyncio.Event()
    task.wait_event.set()
    await task.main_task()
    if view_only:
        assert path.read_bytes() == historical
        assert task.panel_user is None
    else:
        import json

        assert json.loads(path.read_text())["Repeat Farm Count"] == 7
