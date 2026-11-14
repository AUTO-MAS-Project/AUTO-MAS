from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config.universal_plan import plan_directory, save_plan_config
from app.models.config import MaaPlanConfig, UniversalPlanConfig


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


def test_first_save_from_empty_template_succeeds(tmp_path):
    """空模板目录（原生配置目录为空的首次会话换入结果）保存不再报错。"""

    native = tmp_path / "native"
    native.mkdir()
    (native / "config.json").write_text("first", encoding="utf-8")
    template = tmp_path / "Monday" / "ConfigFile"
    template.mkdir(parents=True)
    save_plan_config(source=native, destination=template, mode="Folder")
    assert (template / "config.json").read_text(encoding="utf-8") == "first"
