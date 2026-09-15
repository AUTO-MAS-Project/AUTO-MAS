"""来源导入、快速覆盖与必要启动设置分别验证，不启动游戏或外部脚本。"""

import asyncio
import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest

from app.models.config import (
    BetterGIUserConfig,
    M9AConfig,
    M9AUserConfig,
    MaaConfig,
    MaaUserConfig,
    OkNteConfig,
    OkNteUserConfig,
    SrcUserConfig,
)
from app.task.M9A.AutoProxy import AutoProxyTask as M9ATask
from app.task.MAA.AutoProxy import AutoProxyTask as MaaTask
from app.task.OkNte.AutoProxy import AutoProxyTask as OkNteTask
from app.task.OkNte.manager import OkNteManager
from app.task.OkNte.ScriptConfig import ScriptConfigTask as OkNteGuiTask
from app.task.OkNte.tools.backup_archive import (
    archive_mas_backup,
    ensure_quick_config_dir,
    get_mas_backup_dir,
    list_mas_backups,
    mas_config_dir,
    quick_config_dir,
    restore_mas_backup,
)
from app.task.SRC.AutoProxy import AutoProxyTask as SrcTask
from app.task.SRC.tools.config import read_src_installation_id, save_src_user_config
from app.utils import ProcessManager
from app.utils.constants import MAA_TASKS


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def user_config(cls, mode: str, quick: bool):
    config = cls()
    asyncio.run(config.set("Info", "Mode", mode))
    asyncio.run(config.set("Info", "IfQuickConfig", quick))
    return config


@pytest.mark.parametrize("mode", ["脚本", "用户", "直控"])
@pytest.mark.parametrize("quick", [False, True])
def test_maa_source_and_overlay_preserve_runtime(tmp_path, monkeypatch, mode, quick):
    monkeypatch.chdir(tmp_path)
    task = MaaTask.__new__(MaaTask)
    uid = uuid.uuid4()
    task.script_info = SimpleNamespace(script_id="maa")
    task.script_config = MaaConfig()
    task.cur_user_uid = uid
    task.cur_user_config = user_config(MaaUserConfig, mode, quick)
    task.config_mode = mode
    task.direct_control = mode == "直控"
    task.mode = "Routine"
    task.maa_set_path = tmp_path / "maa" / "config"
    task.maa_exe_path = tmp_path / "maa" / "MAA.exe"
    task.maa_tasks_path = tmp_path / "maa" / "tasks.json"
    task.maa_process_manager = MagicMock(kill=AsyncMock())
    task._maa_config_baseline = None
    task._depot_maintain_suppressed = False
    task.task_dict = {name: name == "Fight" for name in MAA_TASKS}
    asyncio.run(task.cur_user_config.set("Info", "Stage", "1-7"))
    source_queue = [{"TaskType": "Native", "IsEnable": True}]
    paths = {
        "脚本": tmp_path / "data/maa/Default/ConfigFile",
        "用户": tmp_path / f"data/maa/{uid}/ConfigFile",
        "直控": tmp_path / "data/maa/Temp",
    }
    for name, directory in paths.items():
        write_json(
            directory / "gui.json",
            {"Current": "Default", "Global": {}, "Configurations": {"Default": {}}},
        )
        write_json(
            directory / "gui.new.json",
            {
                "source": name,
                "Configurations": {"Default": {"TaskQueue": source_queue}},
            },
        )
    write_json(task.maa_set_path / "gui.new.json", {"previous_user": True})

    with (
        patch("app.task.MAA.AutoProxy.System.kill_process", new_callable=AsyncMock),
        patch("app.task.MAA.AutoProxy.agree_bilibili", new_callable=AsyncMock),
        patch("app.task.MAA.AutoProxy.Config.get", return_value=False),
        patch("app.task.MAA.AutoProxy.mark_native_config_injected") as mark,
    ):
        asyncio.run(task.set_maa(SimpleNamespace(adb_address="127.0.0.1:5555")))
    actual = json.loads(
        (task.maa_set_path / "gui.new.json").read_text(encoding="utf-8")
    )
    assert actual["source"] == mode
    queue = actual["Configurations"]["Default"]["TaskQueue"]
    if quick:
        fight = next(item for item in queue if item["TaskType"] == "Fight")
        assert fight["StagePlan"] == ["1-7"]
        assert fight["IsEnable"] is True
        assert all(item["TaskType"] != "Native" for item in queue)
    else:
        assert queue == source_queue
    assert actual["Configurations"]["Default"]["Gui"]["StartUpSettings"]["RunDirectly"]
    assert task._maa_config_baseline is not None
    mark.assert_called_once()


@pytest.mark.parametrize("mode", ["脚本", "用户", "直控"])
@pytest.mark.parametrize("quick", [False, True])
@pytest.mark.parametrize("has_source", [False, True])
def test_m9a_source_queue_is_not_replaced_when_closed(
    tmp_path, monkeypatch, mode, quick, has_source
):
    monkeypatch.chdir(tmp_path)
    task = M9ATask.__new__(M9ATask)
    task.cur_user_uid = uuid.uuid4()
    task.script_info = SimpleNamespace(script_id="m9a")
    task.script_config = MagicMock()
    task.script_config.get.return_value = ""
    task.cur_user_config = user_config(M9AUserConfig, mode, quick)
    task.config_mode = mode
    task.direct_control = mode == "直控"
    task.is_virtual_update_user = False
    task.m9a_config_path = tmp_path / "m9a/config"
    task.m9a_tasks_path = task.m9a_config_path / "instances/default.json"
    task.m9a_exe_path = tmp_path / "m9a/M9A.exe"
    task.m9a_process_manager = MagicMock(kill=AsyncMock())
    task.m9a_task_loader = MagicMock()
    definition = {"name": "Panel", "entry": "Panel"}
    task.m9a_task_loader.get_all_tasks_with_entry.return_value = [definition]
    task.m9a_task_loader.get_full_definition.side_effect = lambda name: (
        definition if name == "Panel" else None
    )
    task.emulator_manager = MagicMock()
    for name, path in {
        "脚本": tmp_path / "data/m9a/Default/ConfigFile/default.json",
        "用户": tmp_path / f"data/m9a/{task.cur_user_uid}/ConfigFile/default.json",
        "直控": tmp_path / "data/m9a/Temp/instances/default.json",
    }.items():
        if has_source:
            write_json(path, {"source": name, "TaskItems": [{"entry": "Native"}]})
    write_json(task.m9a_tasks_path, {"source": "previous-user"})

    with patch("app.task.M9A.AutoProxy.System.kill_process", new_callable=AsyncMock):
        if not has_source and not quick:
            with pytest.raises(FileNotFoundError, match="默认实例"):
                asyncio.run(
                    task.write_m9a_config([], SimpleNamespace(adb_address="Unknown"))
                )
            return
        asyncio.run(
            task.write_m9a_config(
                [{"name": "Panel"}], SimpleNamespace(adb_address="127.0.0.1:5555")
            )
        )
    actual = json.loads(task.m9a_tasks_path.read_text(encoding="utf-8"))
    assert actual.get("source") == (mode if has_source else None)
    assert [item["entry"] for item in actual["TaskItems"]] == [
        "Panel" if quick else "Native"
    ]
    if not quick:
        assert actual["BeforeTask"] == "StartupSoftwareAndScript"


@pytest.mark.parametrize("mode", ["脚本", "用户", "直控"])
def test_bettergi_closed_does_not_parse_panel(tmp_path, mode):
    from app.task.BetterGI.AutoProxy import AutoProxyTask

    task = AutoProxyTask.__new__(AutoProxyTask)
    task.cur_user_config = user_config(BetterGIUserConfig, mode, False)
    task.use_mas_config = False
    task.script_config = MagicMock()
    task.script_config.get.return_value = str(tmp_path)
    with (
        patch(
            "app.task.BetterGI.AutoProxy.one_dragon.parse_custom_groups",
            side_effect=AssertionError("hidden panel"),
        ),
        patch(
            "app.task.BetterGI.AutoProxy.one_dragon.parse_one_dragon_queue",
            side_effect=AssertionError("hidden panel"),
        ),
        patch(
            "app.task.BetterGI.AutoProxy.team_resolver.parse_teams",
            side_effect=AssertionError("hidden panel"),
        ),
        patch(
            "app.task.BetterGI.AutoProxy.parse_one_dragon_plan",
            side_effect=AssertionError("hidden panel"),
        ),
    ):
        asyncio.run(task.prepare())
    assert not task.use_execution_layer
    assert not task.plan_mode
    assert not task.use_teams
    assert not task.one_dragon_queue


@pytest.mark.parametrize("mode", ["脚本", "用户", "直控"])
@pytest.mark.parametrize("quick", [False, True])
def test_bettergi_tag_matches_actual_config(mode, quick):
    cfg = user_config(BetterGIUserConfig, mode, quick)
    asyncio.run(cfg.set("Task", "OneDragonConfigName", "Native"))
    tags = json.loads(cfg.getTags())
    assert tags[1]["text"] == f"一条龙：{'MAS独立配置' if quick else 'Native'}"


@pytest.mark.parametrize("virtual", [False, True])
def test_m9a_launch_uses_process_signature(tmp_path, virtual):
    task = M9ATask.__new__(M9ATask)
    task.is_virtual_update_user = virtual
    task.cur_user_uid = uuid.uuid4()
    task.cur_user_config = user_config(M9AUserConfig, "用户", False)
    task.script_config = M9AConfig()
    task.cur_user_item = SimpleNamespace(name="test", status="等待", log_record={})
    task.script_info = SimpleNamespace(log="")
    task.emulator_manager = AsyncMock()
    task.m9a_exe_path = tmp_path / "M9A.exe"
    task.m9a_process_manager = create_autospec(ProcessManager, instance=True)
    task.m9a_process_manager.open_process.side_effect = RuntimeError(
        "stop after launch"
    )
    task._m9a_failed_task_names = set()
    task.wait_event = asyncio.Event()
    task.check = AsyncMock(return_value="Pass")
    task.prepare = AsyncMock()
    task._stop_failure_quiet_waiter = AsyncMock()
    task._load_user_queue = MagicMock(side_effect=AssertionError("hidden panel"))
    task.write_m9a_config = AsyncMock()
    with (
        patch("app.task.M9A.AutoProxy.Config.get", return_value=False),
        pytest.raises(RuntimeError, match="stop after launch"),
    ):
        asyncio.run(task.main_task())
    task.m9a_process_manager.open_process.assert_awaited_once_with(
        task.m9a_exe_path, *([] if virtual else ["--autostart", "-i", "default"])
    )


def test_oknte_panel_initialization_and_restore_keep_source(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = mas_config_dir("oknte", "user")
    write_json(source / "CoffeeTask.json", {"cups": 1})
    cfg = MagicMock()
    cfg.get.return_value = "Folder"
    panel = ensure_quick_config_dir("oknte", "user", cfg)
    write_json(panel / "CoffeeTask.json", {"cups": 3})
    assert ensure_quick_config_dir("oknte", "user", cfg) == panel
    assert json.loads((source / "CoffeeTask.json").read_text()) == {"cups": 1}
    backup = archive_mas_backup("oknte", "user", source)
    write_json(panel / "CoffeeTask.json", {"cups": 8})
    write_json(source / "CoffeeTask.json", {"cups": 2})
    restore_mas_backup("oknte", "user", backup.name, source)
    assert json.loads((source / "CoffeeTask.json").read_text()) == {"cups": 1}
    assert json.loads((panel / "CoffeeTask.json").read_text())["cups"] == 3


def test_oknte_single_file_initialization_retries_after_failed_write(
    tmp_path, monkeypatch
):
    workspace = tmp_path / "mas"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    native = tmp_path / "AutoCombatTask.json"
    write_json(native, {"enabled": True})
    cfg = OkNteConfig()
    asyncio.run(cfg.set("Script", "ConfigPathMode", "File"))
    asyncio.run(cfg.set("Script", "ConfigPath", str(native)))
    panel = quick_config_dir("oknte", "user")
    replace = Path.replace

    def fail_panel_write(self, target):
        if Path(target).parent == panel:
            raise OSError("write failed")
        return replace(self, target)

    with monkeypatch.context() as ctx:
        ctx.setattr(Path, "replace", fail_panel_write)
        with pytest.raises(OSError, match="write failed"):
            ensure_quick_config_dir("oknte", "user", cfg)
    assert not (panel / native.name).exists()
    assert ensure_quick_config_dir("oknte", "user", cfg) == panel
    assert (panel / native.name).read_bytes() == native.read_bytes()


def test_oknte_failed_panel_restore_keeps_recovery_backup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = mas_config_dir("oknte", "user")
    panel = quick_config_dir("oknte", "user")
    write_json(source / "AutoCombatTask.json", {"source": 1})
    write_json(panel / "AutoCombatTask.json", {"panel": 1})
    selected = archive_mas_backup("oknte", "user", source)
    write_json(source / "AutoCombatTask.json", {"source": 2})
    write_json(panel / "AutoCombatTask.json", {"panel": 2})
    with (
        patch(
            "app.task.OkNte.tools.backup_archive.swap_in_dir",
            side_effect=OSError("restore failed"),
        ),
        pytest.raises(OSError, match="restore failed"),
    ):
        restore_mas_backup("oknte", "user", selected.name, source)
    saved = get_mas_backup_dir("oknte", "user", list_mas_backups("oknte", "user")[0])
    assert json.loads((saved / "AutoCombatTask.json").read_text()) == {"source": 2}
    assert json.loads((saved / "QuickConfig/AutoCombatTask.json").read_text()) == {
        "panel": 2
    }
    assert json.loads((panel / "AutoCombatTask.json").read_text()) == {"panel": 2}
    restore_mas_backup("oknte", "user", selected.name, source)
    assert json.loads((source / "AutoCombatTask.json").read_text()) == {"source": 1}
    assert json.loads((panel / "AutoCombatTask.json").read_text()) == {"panel": 1}


@pytest.mark.parametrize("mode", ["脚本", "用户", "直控"])
@pytest.mark.parametrize("quick", [False, True])
def test_src_staging_uses_source_and_gates_only_stage_panel(
    tmp_path, monkeypatch, mode, quick
):
    monkeypatch.chdir(tmp_path)
    task = SrcTask.__new__(SrcTask)
    task.script_info = SimpleNamespace(script_id="src")
    task.cur_user_uid = uuid.uuid4()
    task.cur_user_config = user_config(SrcUserConfig, mode, quick)
    task.config_mode, task.direct_control = mode, mode == "直控"
    task.src_root_path = tmp_path / "src"
    task.src_root_path.mkdir()
    task.src_exe_path = task.src_root_path / "src.exe"
    task.src_exe_path.write_bytes(b"test")
    task.src_installation_id = read_src_installation_id(task.src_root_path)
    task.src_set_path = task.src_root_path / "config"
    task.src_process_manager = MagicMock()
    task.src_webui_port = 23333
    baseline = {
        "Alas": {"Emulator": {}, "Error": {}, "Optimization": {}},
        "Dungeon": {"PlannerTarget": {"Enable": True}, "Scheduler": {}, "Dungeon": {}},
        "Ornament": {"Scheduler": {}, "Ornament": {}},
        "Weekly": {"Scheduler": {}, "Weekly": {}},
        "Rogue": {"Scheduler": {}, "RogueWorld": {}},
    }
    for name, directory in {
        "previous-user": task.src_set_path,
        "脚本": tmp_path / "data/src/Default/ConfigFile",
        "用户": tmp_path / f"data/src/{task.cur_user_uid}/ConfigFile",
        "直控": tmp_path / "data/src/Temp",
    }.items():
        write_json(directory / "src.json", {**baseline, "source": name})
        (directory / "deploy.yaml").write_text("Run: null\n", encoding="utf-8")
    with patch(
        "app.task.SRC.AutoProxy.kill_src_processes",
        new_callable=AsyncMock,
        return_value=True,
    ):
        asyncio.run(task.set_src(SimpleNamespace(adb_address="127.0.0.1:5555")))
    actual = json.loads((task.src_set_path / "src.json").read_text(encoding="utf-8"))
    assert actual["source"] == mode
    assert actual["Dungeon"]["PlannerTarget"]["Enable"] is not quick
    assert actual["Alas"]["Emulator"]["Serial"] == "127.0.0.1:5555"
    assert not task.src_set_path.with_suffix(".tmp").exists()
    if mode == "用户":
        actual["Dungeon"]["Scheduler"]["NextRun"] = "runtime"
        write_json(task.src_set_path / "src.json", actual)
        source = tmp_path / f"data/src/{task.cur_user_uid}/ConfigFile"
        save_src_user_config(
            task.src_set_path,
            source,
            expected_installation_id=task.src_installation_id,
            runtime_baseline=task._src_injected_config,
        )
        saved = json.loads((source / "src.json").read_text())
        assert saved["Dungeon"]["PlannerTarget"]["Enable"] is True
        assert saved["Dungeon"]["Scheduler"]["NextRun"] == "runtime"
        asyncio.run(task.cur_user_config.set("Info", "IfQuickConfig", False))
        with patch(
            "app.task.SRC.AutoProxy.kill_src_processes",
            new_callable=AsyncMock,
            return_value=True,
        ):
            asyncio.run(task.set_src(SimpleNamespace(adb_address="127.0.0.1:5555")))
        assert (
            json.loads((task.src_set_path / "src.json").read_text())["Dungeon"][
                "PlannerTarget"
            ]["Enable"]
            is True
        )


@pytest.mark.parametrize("mode", ["脚本", "用户", "直控"])
@pytest.mark.parametrize("quick", [False, True])
def test_oknte_single_file_overlay_writeback_and_restore(
    tmp_path, monkeypatch, mode, quick
):
    workspace = tmp_path / "mas"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    cfg = OkNteConfig()
    native = tmp_path / "native/AutoCombatTask.json"
    asyncio.run(cfg.set("Script", "ConfigPathMode", "File"))
    asyncio.run(cfg.set("Script", "ConfigPath", str(native)))
    task = OkNteTask.__new__(OkNteTask)
    task.script_info = SimpleNamespace(script_id="oknte")
    task.cur_user_uid = uuid.uuid4()
    task.cur_user_config = user_config(OkNteUserConfig, mode, quick)
    task.config_mode, task.direct_control = mode, mode == "直控"
    task.script_config = cfg
    task.script_config_path = native
    task.script_exe_path = tmp_path / "oknte.exe"
    temp = workspace / "data/oknte/Temp"
    write_json(temp / "config.temp", {"source": "直控"})
    write_json(native, {"source": "previous-user"})
    write_json(native.with_name("DailyRoutineTask.json"), {"untouched": True})
    source = mas_config_dir(
        "oknte", "Default" if mode == "脚本" else str(task.cur_user_uid)
    )
    write_json(source / native.name, {"source": mode})
    panel = quick_config_dir("oknte", str(task.cur_user_uid))
    write_json(panel / native.name, {"source": "panel"})
    with patch("app.task.OkNte.AutoProxy.System.kill_process", new_callable=AsyncMock):
        asyncio.run(task.set_oknte())
    assert json.loads(native.read_text()) == {"source": "panel" if quick else mode}
    write_json(native, {"source": "runtime"})
    asyncio.run(task.update_config())
    assert json.loads((panel / native.name).read_text()) == {
        "source": "runtime" if quick else "panel"
    }
    assert json.loads((source / native.name).read_text()) == {
        "source": "runtime" if not quick and mode != "直控" else mode
    }
    manager = OkNteManager.__new__(OkNteManager)
    manager.task_info = SimpleNamespace(mode="AutoProxy")
    manager.temp_path = temp
    manager.script_config_path = native
    manager.script_config = cfg
    manager.had_original_script_config = True
    asyncio.run(manager._restore_script_config_from_temp())
    assert json.loads(native.read_text()) == {"source": "直控"}
    assert json.loads(native.with_name("DailyRoutineTask.json").read_text()) == {
        "untouched": True
    }


@pytest.mark.parametrize("mode", ["脚本", "用户", "直控"])
@pytest.mark.parametrize(
    "quick,view_only", [(False, False), (True, False), (False, True)]
)
def test_oknte_gui_uses_panel_or_source_without_overwriting_other_owner(
    tmp_path, monkeypatch, mode, quick, view_only
):
    workspace = tmp_path / "mas"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    cfg = OkNteConfig()
    native = tmp_path / "native"
    asyncio.run(cfg.set("Script", "ConfigPath", str(native)))
    uid = uuid.uuid4()
    source = mas_config_dir("oknte", "Default" if mode == "脚本" else str(uid))
    panel = quick_config_dir("oknte", str(uid))
    for path, name in [(source, mode), (panel, "panel"), (native, "native")]:
        write_json(path / "AutoCombatTask.json", {"source": name})
    info = SimpleNamespace(
        task_info=SimpleNamespace(),
        script_id="oknte",
        current_index=0,
        user_list=[SimpleNamespace(user_id=str(uid), status="等待")],
    )
    task = OkNteGuiTask(
        info,
        cfg,
        {uid: user_config(OkNteUserConfig, mode, quick)},
        None,
        view_only=view_only,
    )
    with patch.object(task, "_kill_oknte_process", new_callable=AsyncMock):
        asyncio.run(task.set_oknte())
        assert json.loads((native / "AutoCombatTask.json").read_text())["source"] == (
            "panel" if quick or view_only else "native" if mode == "直控" else mode
        )
        write_json(native / "AutoCombatTask.json", {"source": "GUI"})
        asyncio.run(task.final_task())
    assert json.loads((panel / "AutoCombatTask.json").read_text())["source"] == (
        "GUI" if quick and not view_only else "panel"
    )
    assert json.loads((source / "AutoCombatTask.json").read_text())["source"] == (
        "GUI" if not quick and not view_only and mode != "直控" else mode
    )
