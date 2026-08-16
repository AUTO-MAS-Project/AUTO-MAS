import json
from pathlib import Path

from app.models.config import OkwwUserConfig
from app.task.Okww.AutoProxy import (
    _OKWW_REL_APP_JSON,
    AutoProxyTask,
    _configure_okww_launcher,
    _okww_mas_config_dir,
)


def test_configure_okww_launcher_selects_resource_profile(tmp_path: Path) -> None:
    app_json_path = tmp_path / _OKWW_REL_APP_JSON
    app_json_path.parent.mkdir(parents=True)
    app_json_path.write_text(
        json.dumps(
            {
                "name": "ok-ww",
                "auto_start": False,
                "current_profile": "China",
                "profiles": [{"name": "China"}, {"name": "Global"}],
            }
        ),
        encoding="utf-8",
    )

    _configure_okww_launcher(tmp_path, "国际服")

    assert json.loads(app_json_path.read_text(encoding="utf-8")) == {
        "name": "ok-ww",
        "auto_start": True,
        "current_profile": "Global",
        "update_method": "AUTO_UPDATE",
        "profiles": [{"name": "China"}, {"name": "Global"}],
    }


def test_configure_okww_launcher_preserves_profile_for_gui(tmp_path: Path) -> None:
    app_json_path = tmp_path / _OKWW_REL_APP_JSON
    app_json_path.parent.mkdir(parents=True)
    app_json_path.write_text(
        json.dumps(
            {
                "auto_start": False,
                "current_profile": "Global",
                "update_method": "MANUAL",
            }
        ),
        encoding="utf-8",
    )

    _configure_okww_launcher(tmp_path)

    assert json.loads(app_json_path.read_text(encoding="utf-8")) == {
        "auto_start": True,
        "current_profile": "Global",
        "update_method": "AUTO_UPDATE",
    }


def test_okww_config_owner_matches_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert _okww_mas_config_dir("script", "user", "简洁") == (
        tmp_path / "data/script/Default/ConfigFile"
    )
    assert _okww_mas_config_dir("script", "user", "详细") == (
        tmp_path / "data/script/user/ConfigFile"
    )


def test_okww_runtime_overrides_daily_and_required_settings(tmp_path: Path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "DailyTask.json").write_text(
        json.dumps({"Unmanaged": "keep", "Which to Farm": "Forgery Challenge"}),
        encoding="utf-8",
    )
    (config_dir / "Basic Options.json").write_text(
        json.dumps({"Unmanaged": "keep", "Exit App when Game Exits": False}),
        encoding="utf-8",
    )

    user_config = OkwwUserConfig()
    user_config.Task_WhichToFarm.setValue("Simulation Challenge")
    user_config.Task_MaterialSelection.setValue("Weapon EXP")
    user_config.Task_AdditionalTasks.setValue(
        ["Check Weekly Garden", "Teleport and Farm 4C Echo"]
    )

    task = AutoProxyTask.__new__(AutoProxyTask)
    task.script_config_path = config_dir
    task.cur_user_config = user_config
    task._apply_mas_overrides()

    daily = json.loads((config_dir / "DailyTask.json").read_text(encoding="utf-8"))
    basic = json.loads(
        (config_dir / "Basic Options.json").read_text(encoding="utf-8")
    )
    assert daily["Unmanaged"] == "keep"
    assert daily["Which to Farm"] == "Simulation Challenge"
    assert daily["Material Selection"] == "Weapon EXP"
    assert daily["Additional Tasks to Run After Daily Task"] == [
        "Check Weekly Garden",
        "Teleport and Farm 4C Echo",
    ]
    assert basic == {"Unmanaged": "keep", "Exit App when Game Exits": True}


def test_okww_task_index_only_accepts_daily_tasks() -> None:
    user_config = OkwwUserConfig()

    user_config.Task_TaskIndex.setValue(7)
    assert user_config.get("Task", "TaskIndex") == 7

    user_config.Task_TaskIndex.setValue(2)
    assert user_config.get("Task", "TaskIndex") == 7
