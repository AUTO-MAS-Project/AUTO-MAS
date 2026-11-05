import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.config import ConfigCollection
from app.core.config.universal_plan import plan_directory, save_plan_config
from app.models.config import GeneralUserConfig, MaaPlanConfig, UniversalPlanConfig
from app.task.general.AutoProxy import AutoProxyTask
from app.task.general.ScriptConfig import ScriptConfigTask


def make_plan(script_id, user_id, **info):
    return UniversalPlanConfig.model_validate(
        {"Info": {"ScriptId": str(script_id), **info}}
    )


def test_reset_time_and_existing_plan_remain_independent():
    tz = timezone(timedelta(hours=8))
    plan = make_plan(uuid4(), uuid4())
    assert plan.current_group(datetime(2026, 11, 3, 3, 59, tzinfo=tz)) == "Monday"
    assert plan.current_group(datetime(2026, 11, 3, 4, 0, tzinfo=tz)) == "Tuesday"
    custom = make_plan(uuid4(), uuid4(), ResetHour=6, ResetMinute=30)
    assert custom.current_group(datetime(2026, 11, 3, 6, 29, tzinfo=tz)) == "Monday"
    assert custom.current_group(datetime(2026, 11, 3, 6, 30, tzinfo=tz)) == "Tuesday"
    fixed = make_plan(uuid4(), uuid4(), Mode="ALL")
    assert fixed.current_group(datetime(2026, 11, 3, 0, 0, tzinfo=tz)) == "ALL"
    rotate = make_plan(uuid4(), uuid4(), Mode="Rotate", RotateDays=3)
    before = rotate.current_group(datetime(2026, 11, 3, 3, 59, tzinfo=tz))
    after = rotate.current_group(datetime(2026, 11, 3, 4, 0, tzinfo=tz))
    assert int(after[3:]) == int(before[3:]) % 3 + 1
    old = MaaPlanConfig.model_validate({"Info": {"Mode": "Weekly"}})
    assert old.current_group(datetime(2026, 11, 3, 3, 59, tzinfo=tz)) == "Tuesday"


@pytest.mark.parametrize(
    "info", [{"ResetHour": 24}, {"ResetMinute": 60}, {"RotateDays": 0}]
)
def test_invalid_plan_settings_rejected(info):
    with pytest.raises(ValidationError):
        make_plan(uuid4(), uuid4(), **info)


def test_directory_rejects_wrong_owner_and_unsafe_day(tmp_path):
    script_id, user_id = uuid4(), uuid4()
    plan = make_plan(script_id, user_id)
    kwargs = dict(
        data_path=tmp_path, plan=plan, script_id=str(script_id), user_id=str(user_id)
    )
    for day in ("../outside", "Day0", "Day32", "Day01", "Monday/../Tuesday"):
        with pytest.raises(ValueError):
            plan_directory(**kwargs, day=day)
    with pytest.raises(ValueError):
        plan_directory(**{**kwargs, "script_id": str(uuid4())}, day="Monday")
    assert plan_directory(**kwargs, day="Day31").is_relative_to(tmp_path)


@pytest.mark.parametrize("mode", ["File", "Folder"])
def test_saved_days_and_user_base_are_isolated(tmp_path, mode):
    native = tmp_path / "native"
    native.mkdir()
    source = native / "settings.json"
    source.write_text("base")
    monday, tuesday = tmp_path / "Monday", tmp_path / "Tuesday"
    actual_source = source if mode == "File" else native
    save_plan_config(source=actual_source, destination=monday, mode=mode)
    save_plan_config(source=actual_source, destination=tuesday, mode=mode)
    source.write_text("monday")
    save_plan_config(source=actual_source, destination=monday, mode=mode)
    assert (monday / source.name).read_text() == "monday"
    assert (tuesday / source.name).read_text() == "base"


def test_failed_save_preserves_previous_configuration(tmp_path, monkeypatch):
    import app.core.config.universal_plan as module

    source = tmp_path / "settings.json"
    source.write_text("old")
    target = tmp_path / "Monday"
    save_plan_config(source=source, destination=target, mode="File")
    source.write_text("new")

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(module.shutil, "copy", fail)
    with pytest.raises(OSError):
        save_plan_config(source=source, destination=target, mode="File")
    assert (target / source.name).read_text() == "old"


def test_universal_plan_general_only():
    """通用脚本计划表只绑通用脚本；专项用户配置不带 PlanMode。"""

    from app.models.config import (
        PLAN_BOOK,
        GeneralConfig,
        OkNteUserConfig,
        OkwwUserConfig,
    )

    assert PLAN_BOOK["UniversalPlanConfig"]["script_class"] is GeneralConfig
    assert GeneralUserConfig().Info.PlanMode == "Fixed"
    for user_cls in (OkwwUserConfig, OkNteUserConfig):
        assert "PlanMode" not in type(user_cls().Info).model_fields


@pytest.mark.asyncio
async def test_runtime_and_edit_session_use_selected_day(
    isolated_app_paths, monkeypatch
):
    config = isolated_app_paths
    script_id, user_id = uuid4(), uuid4()
    plan = make_plan(script_id, user_id)
    plans = ConfigCollection.build([UniversalPlanConfig])
    await plans.activate()
    plan_id = plans.add(UniversalPlanConfig, payload=plan.model_dump())
    await plans.commit()
    plan = plans[plan_id]
    monkeypatch.setattr(config, "PlanConfig", plans)
    monkeypatch.setattr(
        UniversalPlanConfig, "current_group", lambda self, now: "Monday"
    )
    user = GeneralUserConfig.model_validate({"Info": {"PlanMode": plan.uid}})
    native = config.data_path / "native.json"
    native.write_text("base")
    script = SimpleNamespace(
        Script=SimpleNamespace(ConfigPath=native, ConfigPathMode="File"),
        Run=SimpleNamespace(ProxyTimesLimit=0),
    )
    task_info = SimpleNamespace(
        is_queue_task=False, plan_id=str(plan.uid), plan_day="Tuesday"
    )
    item = SimpleNamespace(user_id=str(user_id), name="User", status="waiting")
    info = SimpleNamespace(
        task_info=task_info, script_id=str(script_id), user_list=[item], current_index=0
    )
    run = AutoProxyTask(info, script, {user_id: user}, None)
    assert await run.check() != "Pass"
    # 当天未配置按「跳过」处理：否则报告会停留在「等待」
    assert item.status == "跳过"
    run.script_config_path = native
    save_plan_config(source=native, destination=run.plan_template_dir, mode="File")
    await run.update_config()
    assert await run.check() == "Pass"
    monday = run.mas_config_dir
    second_id = uuid4()
    second_info = SimpleNamespace(
        task_info=task_info,
        script_id=str(script_id),
        user_list=[
            SimpleNamespace(user_id=str(second_id), name="Second", status="waiting")
        ],
        current_index=0,
    )
    second_user = GeneralUserConfig.model_validate({"Info": {"PlanMode": plan.uid}})
    second = AutoProxyTask(second_info, script, {second_id: second_user}, None)
    second.script_config_path = native
    assert second.plan_template_dir == run.plan_template_dir
    assert second.mas_config_dir != run.mas_config_dir
    session = ScriptConfigTask(info, script, {user_id: user}, None)
    assert session.mas_config_dir != monday
    assert session.mas_config_dir.parent.name == "Tuesday"
    monkeypatch.setattr(
        UniversalPlanConfig, "current_group", lambda self, now: "Tuesday"
    )
    # 计划模式只从当天模板下发，运行结果不回写模板，也不改写运行副本
    native.write_text("after reset")
    await run.update_config()
    await second.update_config()
    assert (run.plan_template_dir / native.name).read_text() == "base"
    assert not run.mas_config_dir.exists()
    assert not second.mas_config_dir.exists()
    assert not session.mas_config_dir.exists()
    assert user.Data.ProxyTimes == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["File", "Folder"])
async def test_native_edit_session_saves_only_its_day(
    isolated_app_paths, monkeypatch, mode
):
    import app.task.general.ScriptConfig as module

    config = isolated_app_paths
    script_id, user_id = uuid4(), uuid4()
    plans = ConfigCollection.build([UniversalPlanConfig])
    await plans.activate()
    plan_id = plans.add(
        UniversalPlanConfig,
        payload={"Info": {"ScriptId": str(script_id)}},
    )
    await plans.commit()
    monkeypatch.setattr(config, "PlanConfig", plans)
    base = config.data_path / str(script_id) / str(user_id) / "ConfigFile"
    base.mkdir(parents=True)
    (base / "settings.json").write_text("base")
    native = config.data_path / "native"
    native.mkdir()
    native_file = native / "settings.json"
    native_file.write_text("base")
    executable = config.data_path / "script.exe"
    executable.touch()
    script = SimpleNamespace(
        Script=SimpleNamespace(
            ScriptPath=executable,
            Arguments="",
            ConfigPathMode=mode,
            ConfigPath=native if mode == "Folder" else native_file,
        )
    )
    task_info = SimpleNamespace(
        plan_id=str(plan_id), plan_day="Tuesday", view_only=False
    )
    item = SimpleNamespace(user_id="Default", name="Script", status="waiting")
    info = SimpleNamespace(
        task_info=task_info, script_id=str(script_id), user_list=[item], current_index=0
    )
    user = GeneralUserConfig()
    session = ScriptConfigTask(info, script, {user_id: user}, None)

    class FakeProcess:
        async def open_process(self, *args):
            assert native_file.read_text() == "base"
            native_file.write_text("Tuesday edited")
            asyncio.get_running_loop().call_soon(session.wait_event.set)

        async def kill(self):
            pass

    async def kill(*args):
        pass

    monkeypatch.setattr(module, "ProcessManager", FakeProcess)
    monkeypatch.setattr(module.System, "kill_process", kill)
    await session.main_task()
    await session.final_task()
    assert (session.mas_config_dir / "settings.json").read_text() == "Tuesday edited"
    assert (base / "settings.json").read_text() == "base"
    assert not (session.mas_config_dir.parent.parent / "Monday" / "ConfigFile").exists()


@pytest.mark.parametrize(
    "mode,plan_context,expected",
    [
        ("ScriptConfig", None, False),
        ("ScriptConfig", "plan", True),
        ("AutoProxy", None, True),
    ],
)
def test_native_user_editor_keeps_original_source(mode, plan_context, expected):
    from app.task.general.manager import GeneralManager

    user_id = uuid4()
    user = GeneralUserConfig.model_validate(
        {"Info": {"Base": "native", "PlanMode": str(uuid4())}}
    )
    manager = SimpleNamespace(
        script_info=SimpleNamespace(
            user_list=[SimpleNamespace(user_id=str(user_id))], current_index=0
        ),
        task_info=SimpleNamespace(mode=mode, plan_id=plan_context),
        user_config={user_id: user},
    )
    assert GeneralManager._user_uses_mas_config(manager) is expected
