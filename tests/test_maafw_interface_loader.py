from pathlib import Path
import asyncio
import io
import json
import os
import subprocess
import sys
import threading
import uuid
import zipfile

import pytest

from app.models.ConfigBase import MultipleConfig
from app.models.config import EmulatorConfig, MaaFWConfig, MaaFWUserConfig
from app.models.emulator import DeviceStatus
from app.models.task import ScriptItem, TaskItem, UserItem
from app.task.MaaFW.AutoProxy import AutoProxyTask
from app.task.MaaFW.interface_loader import load_interface_model
from app.task.MaaFW.interface_models import MaaFWPreset
from app.task.MaaFW.interface_preview import build_maafw_interface_preview_data
from app.task.MaaFW.project_updater import (
    MaaFWProjectUpdateError,
    _apply_update_package,
    update_maafw_project_if_needed,
)
from app.task.MaaFW.runner import MaaFWDeviceConfig, MaaFWRunResult, MaaFWRunner
from app.task.MaaFW.run_plan import build_maafw_run_plan
from app.task.MaaFW.task_config import (
    build_interface_preset_snapshot,
    normalize_task_execution_payload,
)
from app.task.MaaFW.window_service import (
    MaaFWDesktopWindow,
    match_controller_windows,
    resolve_window_handle,
)
from app.utils.emulator.ldplayer import LDManager, LDPlayerDevice


maafw_autoproxy_module = sys.modules["app.task.MaaFW.AutoProxy"]
maafw_runner_module = sys.modules["app.task.MaaFW.runner"]

M9A_ROOT = Path(r"C:\Users\qiyin\Downloads\M9A-win-x86_64-v3.22.1")
MAABBB_ROOT = Path(r"C:\Users\qiyin\Downloads\Maa_bbb-win-x86_64-v1.12.5")


class DummyTaskItem(TaskItem):
    async def on_change(self):
        return None


def _write_interface(root: Path, name: str, version: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "interface.json").write_text(
        json.dumps(
            {
                "interface_version": 2,
                "name": name,
                "version": version,
                "controller": [{"name": "ADB", "type": "Adb"}],
                "resource": [{"name": "default", "path": ["resource"]}],
                "task": [{"name": "Start", "entry": "Start"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_zip(package_path: Path, source_root: Path) -> None:
    with zipfile.ZipFile(package_path, "w") as zip_ref:
        for file_path in source_root.rglob("*"):
            if file_path.is_file():
                zip_ref.write(file_path, file_path.relative_to(source_root))


def _skip_missing_root(root: Path) -> None:
    if not root.exists():
        pytest.skip(f"本地 MaaFW 项目目录不存在: {root}")


def test_load_m9a_interface_imports_tasks_and_presets():
    _skip_missing_root(M9A_ROOT)

    interface = load_interface_model(M9A_ROOT)

    assert interface.name == "M9A"
    assert {controller.name for controller in interface.controller} >= {"ADB", "PC"}
    assert len(interface.resource) >= 9
    assert len(interface.task) >= 20
    assert len(interface.option) >= 60
    assert len(interface.preset) >= 4
    assert any(task.name == "启动游戏" for task in interface.task)

    snapshot = build_interface_preset_snapshot(interface, interface.preset[0])
    assert len(snapshot.taskOrder) == len(interface.task)
    assert any(snapshot.taskChecked.values())

    plan = build_maafw_run_plan(
        M9A_ROOT,
        interface,
        controller_name="ADB",
        resource_name="官服",
        selected_preset=interface.preset[0].name,
    )
    assert plan.projectName == "M9A"
    assert plan.controllerName == "ADB"
    assert plan.resourceName == "官服"
    assert plan.agents
    assert plan.agents[0].executableExists is True
    assert plan.agents[0].command[-1] == "<socket_id>"
    assert all(item.exists and item.isDir for item in plan.resource.paths)
    assert plan.tasks
    assert "PI_CONTROLLER" in plan.piEnv
    assert "PI_RESOURCE" in plan.piEnv
    runner = MaaFWRunner(plan)
    assert runner.plan.projectName == "M9A"


def test_load_maabbb_interface_imports_tasks_and_presets():
    _skip_missing_root(MAABBB_ROOT)

    interface = load_interface_model(MAABBB_ROOT)

    assert interface.name == "MAA_bbb"
    assert {controller.name for controller in interface.controller} >= {"桌面端", "安卓端"}
    assert len(interface.resource) >= 10
    assert len(interface.task) >= 30
    assert len(interface.option) >= 100
    assert len(interface.preset) >= 3
    assert any(task.name == "崩坏三 启动！" for task in interface.task)

    snapshot = build_interface_preset_snapshot(interface, interface.preset[0])
    assert len(snapshot.taskOrder) == len(interface.task)
    assert any(snapshot.taskChecked.values())
    assert "日常奖励领取-第一次" in snapshot.taskOrder
    assert "日常奖励领取-第二次" in snapshot.taskOrder

    plan = build_maafw_run_plan(
        MAABBB_ROOT,
        interface,
        controller_name="桌面端",
        resource_name="键鼠操作",
        selected_preset=interface.preset[0].name,
    )
    assert plan.projectName == "MAA_bbb"
    assert plan.controllerName == "桌面端"
    assert plan.resourceName == "键鼠操作"
    assert plan.agents
    assert plan.agents[0].embedded is False
    assert plan.agents[0].runtimeKind == "isolated_venv"
    assert plan.agents[0].executableExists is False
    assert plan.agents[0].fallbackReason is not None
    assert plan.agents[0].executable != sys.executable
    assert plan.agents[0].command[-1] == "<socket_id>"
    assert all(item.exists and item.isDir for item in plan.resource.paths)
    assert plan.tasks
    assert any(item.pipelineOverride for item in plan.tasks)
    runner = MaaFWRunner(plan)
    assert runner.plan.projectName == "MAA_bbb"


def test_maafw_config_models_have_required_runtime_fields():
    async def _run():
        script_config = MaaFWConfig()
        user_config = MaaFWUserConfig()

        script_data = await script_config.toDict()
        user_data = await user_config.toDict()

        assert script_data["Info"]["Name"] == "新 MaaFW 脚本"
        assert script_data["Info"]["Path"] == ""
        assert script_data["Emulator"]["Id"] == "-"
        assert script_data["Device"]["AdbScreencapMethods"] == -57
        assert script_data["Device"]["Win32ScreencapMethod"] == 0
        assert script_data["Game"]["Path"] == ""
        assert script_data["Game"]["Arguments"] == ""
        assert script_data["Game"]["WaitTime"] == 60
        assert script_data["Game"]["CloseOnFinish"] is True
        assert script_data["Update"]["IfAutoUpdate"] is True
        assert script_data["Update"]["Source"] == ""
        assert script_data["Update"]["Channel"] == ""
        assert script_data["Update"]["MirrorChyanCDK"] == ""
        assert "UserData" in script_data["SubConfigsInfo"]

        assert user_data["Info"]["Controller"] == ""
        assert user_data["Info"]["Resource"] == ""
        assert user_data["Info"]["Account"] == ""
        assert user_data["Info"]["Password"] == ""
        assert user_data["Task"]["TaskSnapshot"] == "{ }"
        assert user_data["Device"]["HWnd"] == 0

    asyncio.run(_run())


def test_maafw_unknown_option_is_preserved_and_input_aliases_work(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "interface.json").write_text(
        json.dumps(
            {
                "interface_version": 2,
                "name": "demo",
                "version": "v1.0.0",
                "controller": [{"name": "ADB", "type": "Adb"}],
                "resource": [{"name": "default", "path": ["resource"]}],
                "option": {
                    "Mystery": {"type": "slider", "label": "未知选项"},
                    "Level": {
                        "type": "input",
                        "inputs": [
                            {
                                "name": "level",
                                "pipeline_type": "integer",
                                "verify": "^\\d+$",
                                "verify_error": "请输入整数",
                            }
                        ],
                        "pipeline_override": {"level": "{level}"},
                    },
                },
                "task": [
                    {
                        "name": "Start",
                        "entry": "Start",
                        "default_check": True,
                        "option": ["Mystery", "Level"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    interface = load_interface_model(project_root)
    input_item = interface.option["Level"].inputs[0]

    assert interface.option["Mystery"].type == "slider"
    assert input_item.verify_error == "请输入整数"
    assert input_item.pattern_msg == "请输入整数"

    task_names, task_options = normalize_task_execution_payload(
        ["Start"],
        {"Start": {"Mystery": "keep", "Level": {"level": "5"}}},
        interface,
    )
    plan = build_maafw_run_plan(
        project_root,
        interface,
        controller_name="ADB",
        resource_name="default",
        task_names=task_names,
        task_options=task_options,
    )

    assert task_options["Start"]["Mystery"] == "keep"
    assert plan.tasks[0].pipelineOverride["level"] == 5


def test_maafw_common_options_are_available_to_task_pipeline(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "interface.json").write_text(
        json.dumps(
            {
                "interface_version": 2,
                "name": "demo",
                "version": "v1.0.0",
                "controller": [
                    {
                        "name": "ADB",
                        "type": "Adb",
                        "option": ["ControllerMode"],
                    }
                ],
                "resource": [
                    {
                        "name": "default",
                        "path": ["resource"],
                        "option": ["ResourceMode"],
                    }
                ],
                "global_option": ["GlobalMode"],
                "option": {
                    "GlobalMode": {
                        "type": "select",
                        "cases": [
                            {
                                "name": "global",
                                "pipeline_override": {"global": True},
                            }
                        ],
                    },
                    "ControllerMode": {
                        "type": "select",
                        "cases": [
                            {
                                "name": "controller",
                                "pipeline_override": {"controller": True},
                            }
                        ],
                    },
                    "ResourceMode": {
                        "type": "select",
                        "cases": [
                            {
                                "name": "resource",
                                "pipeline_override": {"resource": True},
                            }
                        ],
                    },
                    "TaskMode": {
                        "type": "select",
                        "cases": [
                            {
                                "name": "task",
                                "pipeline_override": {"task": True},
                            }
                        ],
                    },
                },
                "task": [
                    {
                        "name": "Start",
                        "entry": "Start",
                        "default_check": True,
                        "option": ["TaskMode"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    interface = load_interface_model(project_root)
    snapshot = build_interface_preset_snapshot(
        interface,
        MaaFWPreset(name="empty"),
    )
    task_options = snapshot.taskOptions["Start"]

    assert task_options["GlobalMode"] == "global"
    assert task_options["ControllerMode"] == "controller"
    assert task_options["ResourceMode"] == "resource"
    assert task_options["TaskMode"] == "task"

    plan = build_maafw_run_plan(
        project_root,
        interface,
        controller_name="ADB",
        resource_name="default",
        task_names=["Start"],
        task_options={"Start": task_options},
    )

    assert plan.tasks[0].pipelineOverride == {
        "global": True,
        "resource": True,
        "controller": True,
        "task": True,
    }


def test_maafw_common_options_are_filtered_by_runtime_resource(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "interface.json").write_text(
        json.dumps(
            {
                "interface_version": 2,
                "name": "demo",
                "version": "v1.0.0",
                "controller": [{"name": "ADB", "type": "Adb"}],
                "resource": [
                    {"name": "first", "path": ["resource"], "option": ["FirstMode"]},
                    {"name": "second", "path": ["resource"], "option": ["SecondMode"]},
                ],
                "option": {
                    "FirstMode": {
                        "type": "select",
                        "cases": [
                            {
                                "name": "enabled",
                                "pipeline_override": {"first": True},
                            }
                        ],
                    },
                    "SecondMode": {
                        "type": "select",
                        "cases": [
                            {
                                "name": "enabled",
                                "pipeline_override": {"second": True},
                            }
                        ],
                    },
                },
                "task": [
                    {
                        "name": "Start",
                        "entry": "Start",
                        "default_check": True,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    interface = load_interface_model(project_root)
    plan = build_maafw_run_plan(
        project_root,
        interface,
        controller_name="ADB",
        resource_name="first",
        task_names=["Start"],
        task_options={
            "Start": {
                "FirstMode": "enabled",
                "SecondMode": "enabled",
            }
        },
    )

    assert plan.tasks[0].options == {"FirstMode": "enabled"}
    assert plan.tasks[0].pipelineOverride == {"first": True}


def test_maafw_project_updater_applies_full_package(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_interface(project_root, "demo", "v1.0.0")
    (project_root / "old.txt").write_text("old", encoding="utf-8")

    package_root = tmp_path / "package" / "demo"
    package_root.mkdir(parents=True)
    _write_interface(package_root, "demo", "v1.1.0")
    (package_root / "new.txt").write_text("new", encoding="utf-8")

    package_path = tmp_path / "full.zip"
    _write_zip(package_path, tmp_path / "package")

    logs: list[str] = []
    asyncio.run(_apply_update_package(project_root, package_path, logs.append))

    assert json.loads((project_root / "interface.json").read_text(encoding="utf-8"))["version"] == "v1.1.0"
    assert (project_root / "new.txt").read_text(encoding="utf-8") == "new"
    assert not (project_root / "old.txt").exists()


def test_maafw_project_updater_applies_incremental_package(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_interface(project_root, "demo", "v1.0.0")
    (project_root / "keep.txt").write_text("keep", encoding="utf-8")
    (project_root / "remove.txt").write_text("remove", encoding="utf-8")
    (project_root / "remove-dir").mkdir()
    (project_root / "remove-dir" / "stale.txt").write_text("stale", encoding="utf-8")

    package_root = tmp_path / "package"
    package_root.mkdir()
    _write_interface(package_root, "demo", "v1.1.0")
    (package_root / "changed.txt").write_text("changed", encoding="utf-8")
    (package_root / "changes.json").write_text(
        json.dumps(
            {"deleted": ["remove.txt"], "deleted_dir": ["remove-dir"]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    package_path = tmp_path / "incremental.zip"
    _write_zip(package_path, package_root)

    logs: list[str] = []
    asyncio.run(_apply_update_package(project_root, package_path, logs.append))

    assert json.loads((project_root / "interface.json").read_text(encoding="utf-8"))["version"] == "v1.1.0"
    assert (project_root / "changed.txt").read_text(encoding="utf-8") == "changed"
    assert (project_root / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert not (project_root / "remove.txt").exists()
    assert not (project_root / "remove-dir").exists()


def test_maafw_project_updater_rejects_payload_path_outside_extract(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_interface(project_root, "demo", "v1.0.0")

    package_root = tmp_path / "package"
    package_root.mkdir()
    _write_interface(package_root, "demo", "v1.1.0")
    (package_root / "changes.json").write_text(
        json.dumps({"payload": "../../.."}, ensure_ascii=False),
        encoding="utf-8",
    )

    package_path = tmp_path / "unsafe.zip"
    _write_zip(package_path, package_root)

    logs: list[str] = []
    with pytest.raises(MaaFWProjectUpdateError, match="路径越界"):
        asyncio.run(_apply_update_package(project_root, package_path, logs.append))

    assert json.loads((project_root / "interface.json").read_text(encoding="utf-8"))[
        "version"
    ] == "v1.0.0"


def test_maafw_project_updater_skips_when_version_empty(tmp_path):
    project_root = tmp_path / "project"
    _write_interface(project_root, "demo", "")
    interface = load_interface_model(project_root)
    logs: list[str] = []

    result = asyncio.run(
        update_maafw_project_if_needed(
            project_root,
            interface,
            source="GitHub",
            channel="beta",
            proxy=None,
            send_log=logs.append,
        )
    )

    assert result.checked is False
    assert result.updated is False
    assert "未声明版本" in result.message
    assert logs == ["interface 未声明版本，跳过 MaaFW 项目更新"]


def test_maafw_autoproxy_selects_adb_controller_from_emulator_config():
    _skip_missing_root(MAABBB_ROOT)

    async def _run():
        emulator_config = MultipleConfig([EmulatorConfig])
        emulator_uid, _ = await emulator_config.add(EmulatorConfig)
        original_related_config = dict(MaaFWConfig.related_config)
        MaaFWConfig.related_config["EmulatorConfig"] = emulator_config

        script_config = MaaFWConfig()
        try:
            await script_config.set("Info", "Path", str(MAABBB_ROOT))
            await script_config.set("Emulator", "Id", str(emulator_uid))
            await script_config.set("Emulator", "Index", "0")
        finally:
            MaaFWConfig.related_config = original_related_config

        user_config = MultipleConfig([MaaFWUserConfig])
        user_uid, user = await user_config.add(MaaFWUserConfig)
        await user.set("Task", "SelectedPreset", "日常-简化版")

        task_info = DummyTaskItem(
            mode="AutoProxy",
            task_id="test-task",
            queue_id=None,
            script_id=str(uuid.uuid4()),
            user_id=None,
        )
        script_item = ScriptItem(
            script_id=str(uuid.uuid4()),
            name="MAAbbb",
            status="运行",
            user_list=[
                UserItem(user_id=str(user_uid), name="测试用户", status="等待")
            ],
            current_index=0,
        )
        task_info._bind_task_item(script_item)

        task = AutoProxyTask(script_item, script_config, user_config, None)
        interface = load_interface_model(MAABBB_ROOT)
        plan = task._build_run_plan(interface)

        assert plan.controllerName == "安卓端"
        assert plan.controllerType == "Adb"
        assert plan.resourceName == "官服"
        assert plan.tasks

    asyncio.run(_run())


def test_ldplayer_device_info_uses_emulator_serial_even_when_port_exists(monkeypatch):
    manager = object.__new__(LDManager)

    async def fake_get_device_info(idx):
        assert idx == "0"
        return {
            "0": LDPlayerDevice(
                idx=0,
                title="雷电模拟器",
                top_hwnd=1,
                bind_hwnd=2,
                in_android=1,
                pid=100,
                vbox_pid=200,
                width=1280,
                height=720,
                density=320,
            )
        }

    async def fake_get_status(idx, data=None):
        assert idx == "0"
        return DeviceStatus.ONLINE

    async def fail_get_adb_ports(pid):
        raise AssertionError("雷电 ADB 地址不应再依赖 VBox 监听端口")

    monkeypatch.setattr(manager, "get_device_info", fake_get_device_info)
    monkeypatch.setattr(manager, "getStatus", fake_get_status)
    monkeypatch.setattr(manager, "get_adb_ports", fail_get_adb_ports)

    device_info = asyncio.run(manager.getInfo("0"))["0"]

    assert device_info.adb_address == "emulator-5554"


def test_maafw_autoproxy_prefers_script_level_resource_over_user_legacy_value(tmp_path):
    """MaaFW 用户级 Resource 是历史遗留；运行时应以脚本页配置为准。"""
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "interface.json").write_text(
        json.dumps(
            {
                "interface_version": 2,
                "name": "demo",
                "version": "v1.0.0",
                "controller": [{"name": "ADB", "type": "Adb"}],
                "resource": [
                    {
                        "name": "官服",
                        "path": ["resource/base"],
                        "controller": ["ADB"],
                    },
                    {
                        "name": "应用宝渠道服",
                        "path": ["resource/base", "resource/resource_yyb"],
                        "controller": ["ADB"],
                    },
                ],
                "task": [
                    {
                        "name": "Start",
                        "entry": "Start",
                        "default_check": True,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    async def _run():
        script_config = MaaFWConfig()
        await script_config.set("Info", "Path", str(project_root))
        await script_config.set("Info", "Controller", "ADB")
        await script_config.set("Info", "Resource", "应用宝渠道服")

        user_config = MultipleConfig([MaaFWUserConfig])
        user_uid, user = await user_config.add(MaaFWUserConfig)
        await user.set("Info", "Resource", "官服")

        task_info = DummyTaskItem(
            mode="AutoProxy",
            task_id="test-task",
            queue_id=None,
            script_id=str(uuid.uuid4()),
            user_id=None,
        )
        script_item = ScriptItem(
            script_id=str(uuid.uuid4()),
            name="demo",
            status="运行",
            user_list=[UserItem(user_id=str(user_uid), name="测试用户", status="等待")],
            current_index=0,
        )
        task_info._bind_task_item(script_item)

        task = AutoProxyTask(script_item, script_config, user_config, None)
        interface = load_interface_model(project_root)
        plan = task._build_run_plan(interface)

        assert plan.controllerName == "ADB"
        assert plan.resourceName == "应用宝渠道服"
        assert [Path(item.raw).as_posix() for item in plan.resource.paths] == [
            "resource/base",
            "resource/resource_yyb",
        ]

    asyncio.run(_run())


def test_maafw_autoproxy_skips_same_project_path(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "interface.json").write_text(
        json.dumps(
            {
                "interface_version": 2,
                "name": "demo",
                "version": "v1.0.0",
                "controller": [{"name": "ADB", "type": "Adb"}],
                "resource": [{"name": "default", "path": ["resource"]}],
                "task": [{"name": "Start", "entry": "Start", "default_check": True}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    async def _run():
        emulator_config = MultipleConfig([EmulatorConfig])
        emulator_uid, _ = await emulator_config.add(EmulatorConfig)
        original_related_config = dict(MaaFWConfig.related_config)
        MaaFWConfig.related_config["EmulatorConfig"] = emulator_config

        script_config = MaaFWConfig()
        try:
            await script_config.set("Info", "Path", str(project_root))
            await script_config.set("Emulator", "Id", str(emulator_uid))
            await script_config.set("Emulator", "Index", "0")
        finally:
            MaaFWConfig.related_config = original_related_config

        user_config = MultipleConfig([MaaFWUserConfig])
        user_uid, _ = await user_config.add(MaaFWUserConfig)

        def _build_script_item(name: str) -> tuple[ScriptItem, DummyTaskItem]:
            task_info = DummyTaskItem(
                mode="AutoProxy",
                task_id=f"test-task-{name}",
                queue_id=None,
                script_id=str(uuid.uuid4()),
                user_id=None,
            )
            script_item = ScriptItem(
                script_id=str(uuid.uuid4()),
                name=name,
                status="运行",
                user_list=[
                    UserItem(user_id=str(user_uid), name="测试用户", status="等待")
                ],
                current_index=0,
            )
            task_info._bind_task_item(script_item)
            return script_item, task_info

        first_script, first_task_info = _build_script_item("first")
        second_script, second_task_info = _build_script_item("second")
        first = AutoProxyTask(first_script, script_config, user_config, None)
        second = AutoProxyTask(second_script, script_config, user_config, None)
        try:
            assert first_task_info.mode == "AutoProxy"
            assert second_task_info.mode == "AutoProxy"
            assert await first.check() == "Pass"
            skip_message = await second.check()
            assert skip_message == "同一路径 MaaFW 脚本正在运行，已跳过本次启动"
            assert second.cur_user_item.status == "跳过"
        finally:
            await first._release_project_path()
            await second._release_project_path()

    asyncio.run(_run())


def test_maafw_autoproxy_ignores_stale_user_controller_when_emulator_selected(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "interface.json").write_text(
        json.dumps(
            {
                "interface_version": 2,
                "name": "demo",
                "version": "v1.0.0",
                "controller": [
                    {"name": "PC", "type": "Win32"},
                    {"name": "ADB", "type": "Adb"},
                ],
                "resource": [
                    {"name": "desktop", "path": ["resource"], "controller": ["PC"]},
                    {"name": "android", "path": ["resource"], "controller": ["ADB"]},
                ],
                "task": [
                    {
                        "name": "RunStandalone",
                        "entry": "RunStandalone",
                        "group": ["standalone"],
                        "controller": ["ADB"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    async def _run():
        emulator_config = MultipleConfig([EmulatorConfig])
        emulator_uid, _ = await emulator_config.add(EmulatorConfig)
        original_related_config = dict(MaaFWConfig.related_config)
        MaaFWConfig.related_config["EmulatorConfig"] = emulator_config

        script_config = MaaFWConfig()
        try:
            await script_config.set("Info", "Path", str(project_root))
            await script_config.set("Emulator", "Id", str(emulator_uid))
            await script_config.set("Emulator", "Index", "0")
        finally:
            MaaFWConfig.related_config = original_related_config

        user_config = MultipleConfig([MaaFWUserConfig])
        user_uid, user = await user_config.add(MaaFWUserConfig)
        await user.set("Info", "Controller", "PC")
        await user.set(
            "Task",
            "TaskSnapshot",
            json.dumps(
                {
                    "taskOrder": ["RunStandalone"],
                    "taskChecked": {"RunStandalone": True},
                    "taskOptions": {},
                },
                ensure_ascii=False,
            ),
        )

        task_info = DummyTaskItem(
            mode="AutoProxy",
            task_id="test-task",
            queue_id=None,
            script_id=str(uuid.uuid4()),
            user_id=None,
        )
        script_item = ScriptItem(
            script_id=str(uuid.uuid4()),
            name="demo",
            status="运行",
            user_list=[UserItem(user_id=str(user_uid), name="测试用户", status="等待")],
            current_index=0,
        )
        task_info._bind_task_item(script_item)

        task = AutoProxyTask(script_item, script_config, user_config, None)
        interface = load_interface_model(project_root)
        plan = task._build_run_plan(interface)

        assert plan.controllerName == "ADB"
        assert plan.resourceName == "android"
        assert [item.name for item in plan.tasks] == ["RunStandalone"]

    asyncio.run(_run())


def test_maafw_interface_preview_resolves_i18n_labels(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "zh_cn.json").write_text(
        json.dumps(
            {
                "project": {"label": "中文项目", "description": "项目说明"},
                "controller": {"adb": "安卓控制器"},
                "resource": {"main": "官服"},
                "task": {"mini": "小游戏任务"},
                "option": {
                    "mode": "模式",
                    "auto": "自动模式",
                    "desc": "模式说明",
                },
                "preset": {"daily": "日常队列"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (project_root / "interface.json").write_text(
        json.dumps(
            {
                "interface_version": 2,
                "name": "demo",
                "label": "$project.label",
                "description": "$project.description",
                "version": "v1.0.0",
                "languages": {"zh_cn": "zh_cn.json"},
                "controller": [{"name": "ADB", "type": "Adb", "label": "$controller.adb"}],
                "resource": [{"name": "main", "path": ["resource"], "label": "$resource.main"}],
                "task": [
                    {
                        "name": "MiniGame",
                        "entry": "MiniGame",
                        "label": "$task.mini",
                        "option": ["Mode"],
                    }
                ],
                "option": {
                    "Mode": {
                        "type": "select",
                        "label": "$option.mode",
                        "description": "$option.desc",
                        "cases": [{"name": "Auto", "label": "$option.auto"}],
                    }
                },
                "preset": [{"name": "daily", "label": "$preset.daily", "task": [{"name": "MiniGame"}]}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    interface = load_interface_model(project_root)
    preview = build_maafw_interface_preview_data(project_root, interface)

    assert preview.project.label == "中文项目"
    assert preview.project.description == "项目说明"
    assert preview.controllers[0].label == "安卓控制器"
    assert preview.resources[0].label == "官服"
    assert preview.tasks[0].label == "小游戏任务"
    assert preview.options[0].label == "模式"
    assert preview.options[0].description == "模式说明"
    assert preview.options[0].cases[0].label == "自动模式"
    assert preview.presets[0].label == "日常队列"


def test_maafw_autoproxy_filters_completed_period_tasks(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "interface.json").write_text(
        json.dumps(
            {
                "interface_version": 2,
                "name": "demo",
                "version": "v1.0.0",
                "controller": [{"name": "ADB", "type": "Adb"}],
                "resource": [{"name": "default", "path": ["resource"]}],
                "task": [
                    {"name": "Daily", "entry": "Daily", "default_check": True},
                    {"name": "Weekly", "entry": "Weekly", "default_check": True},
                    {"name": "Monthly", "entry": "Monthly", "default_check": True},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    async def _run():
        script_config = MaaFWConfig()
        await script_config.set("Info", "Path", str(project_root))
        await script_config.set("Run", "WeeklyOnceTasks", json.dumps(["Weekly"]))
        await script_config.set("Run", "MonthlyOnceTasks", json.dumps(["Monthly"]))

        user_config = MultipleConfig([MaaFWUserConfig])
        user_uid, user = await user_config.add(MaaFWUserConfig)

        task_info = DummyTaskItem(
            mode="AutoProxy",
            task_id="test-task",
            queue_id=None,
            script_id=str(uuid.uuid4()),
            user_id=None,
        )
        script_item = ScriptItem(
            script_id=str(uuid.uuid4()),
            name="demo",
            status="运行",
            user_list=[UserItem(user_id=str(user_uid), name="测试用户", status="等待")],
            current_index=0,
        )
        task_info._bind_task_item(script_item)

        task = AutoProxyTask(script_item, script_config, user_config, None)
        interface = load_interface_model(project_root)
        base_plan = task._build_run_plan(interface)
        assert [item.name for item in base_plan.tasks] == [
            "Daily",
            "Weekly",
            "Monthly",
        ]

        await task._mark_period_tasks_completed(["Weekly", "Monthly"])
        filtered_plan = task._filter_period_once_tasks(base_plan)

        assert [item.name for item in filtered_plan.tasks] == ["Daily"]
        assert {item.name for item in filtered_plan.skippedTasks} == {
            "Weekly",
            "Monthly",
        }

        records = json.loads(user.get("Data", "PeriodTaskRecords"))
        assert records["weekly"]["Weekly"]
        assert records["monthly"]["Monthly"]

    asyncio.run(_run())


def test_maafw_autoproxy_skips_when_all_period_tasks_are_done(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "interface.json").write_text(
        json.dumps(
            {
                "interface_version": 2,
                "name": "demo",
                "version": "v1.0.0",
                "controller": [{"name": "ADB", "type": "Adb"}],
                "resource": [{"name": "default", "path": ["resource"]}],
                "task": [{"name": "Weekly", "entry": "Weekly", "default_check": True}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    async def _run():
        script_config = MaaFWConfig()
        await script_config.set("Info", "Path", str(project_root))
        await script_config.set("Run", "WeeklyOnceTasks", json.dumps(["Weekly"]))

        user_config = MultipleConfig([MaaFWUserConfig])
        user_uid, _ = await user_config.add(MaaFWUserConfig)

        task_info = DummyTaskItem(
            mode="AutoProxy",
            task_id="test-task",
            queue_id=None,
            script_id=str(uuid.uuid4()),
            user_id=None,
        )
        script_item = ScriptItem(
            script_id=str(uuid.uuid4()),
            name="demo",
            status="运行",
            user_list=[UserItem(user_id=str(user_uid), name="测试用户", status="等待")],
            current_index=0,
        )
        task_info._bind_task_item(script_item)

        task = AutoProxyTask(script_item, script_config, user_config, None)
        await task._mark_period_tasks_completed(["Weekly"])

        assert await task.check() == "MaaFW 周期任务已在本周或本月完成，跳过本次运行"
        assert task.cur_user_item.status == "跳过"
        assert task.run_plan is not None
        assert task.run_plan.tasks == []

    asyncio.run(_run())


def test_maafw_autoproxy_uses_interface_win32_methods():
    _skip_missing_root(MAABBB_ROOT)

    async def _run():
        script_config = MaaFWConfig()
        await script_config.set("Info", "Path", str(MAABBB_ROOT))

        user_config = MultipleConfig([MaaFWUserConfig])
        user_uid, user = await user_config.add(MaaFWUserConfig)
        await user.set("Info", "Controller", "桌面端")
        await user.set("Info", "Resource", "键鼠操作")
        await user.set("Task", "SelectedPreset", "日常-简化版")
        await user.set("Device", "HWnd", 12345)

        task_info = DummyTaskItem(
            mode="AutoProxy",
            task_id="test-task",
            queue_id=None,
            script_id=str(uuid.uuid4()),
            user_id=None,
        )
        script_item = ScriptItem(
            script_id=str(uuid.uuid4()),
            name="MAAbbb",
            status="运行",
            user_list=[
                UserItem(user_id=str(user_uid), name="测试用户", status="等待")
            ],
            current_index=0,
        )
        task_info._bind_task_item(script_item)

        task = AutoProxyTask(script_item, script_config, user_config, None)
        interface = load_interface_model(MAABBB_ROOT)
        plan = task._build_run_plan(interface)
        device_config = await task._build_device_config(plan, interface)

        assert plan.controllerName == "桌面端"
        assert plan.controllerType == "Win32"
        assert plan.resourceName == "键鼠操作"
        assert device_config.hWnd == 12345
        assert device_config.screencapMethod == 16
        assert device_config.mouseMethod == 64
        assert device_config.keyboardMethod == 1

    asyncio.run(_run())


def test_maafw_window_service_matches_win32_regex():
    _skip_missing_root(MAABBB_ROOT)

    interface = load_interface_model(MAABBB_ROOT)
    controller = next(item for item in interface.controller if item.name == "桌面端")
    windows = [
        MaaFWDesktopWindow(hWnd=100, className="OtherClass", windowName="崩坏3"),
        MaaFWDesktopWindow(hWnd=200, className="UnityWndClass", windowName="Honkai Impact 3"),
        MaaFWDesktopWindow(hWnd=300, className="UnityWndClass", windowName="Not Target"),
    ]

    matches = match_controller_windows(controller, windows)

    assert [item.hWnd for item in matches] == [200]
    assert matches[0].controllerName == "桌面端"
    assert matches[0].controllerType == "Win32"


def test_maafw_window_service_uses_explicit_hwnd_before_scan():
    _skip_missing_root(MAABBB_ROOT)

    interface = load_interface_model(MAABBB_ROOT)
    controller = next(item for item in interface.controller if item.name == "桌面端")
    logs: list[str] = []

    hWnd = resolve_window_handle(controller, "24680", send_log=logs.append)

    assert hWnd == 24680
    assert "24680" in logs[0]


def test_maafw_runner_reads_agent_stdout_lines():
    runner = object.__new__(MaaFWRunner)
    logs: list[str] = []
    runner.send_log = logs.append

    runner._read_agent_output(io.StringIO("first line\n\nsecond line\n"), "agent.py")

    assert logs == [
        "[Agent:agent.py] first line",
        "[Agent:agent.py] second line",
    ]


def test_maafw_runner_decodes_agent_stdout_bytes_and_strips_ansi():
    runner = object.__new__(MaaFWRunner)
    logs: list[str] = []
    runner.send_log = logs.append

    payload = "\x1b[32m开始安装/更新依赖\x1b[0m\n".encode("gbk")

    runner._read_agent_output(io.BytesIO(payload), "python.exe")

    assert logs == ["[Agent:python.exe] 开始安装/更新依赖"]


def test_maafw_runner_retries_agent_connect(monkeypatch):
    class FakeAgentClient:
        def __init__(self):
            self.attempts = 0

        def set_timeout(self, milliseconds):
            self.timeout = milliseconds
            return True

        def connect(self):
            self.attempts += 1
            return self.attempts == 3

    class FakeProcess:
        def poll(self):
            return None

    monkeypatch.setattr(maafw_runner_module.time, "sleep", lambda _: None)

    runner = object.__new__(MaaFWRunner)
    logs: list[str] = []
    runner.send_log = logs.append
    agent_client = FakeAgentClient()

    runner._connect_agent_client(agent_client, FakeProcess(), "agent.py")

    assert agent_client.attempts == 3
    assert any("尝试次数 3" in log for log in logs)


def test_maafw_runner_reports_exited_agent_before_connect(monkeypatch):
    class FakeAgentClient:
        def set_timeout(self, milliseconds):
            self.timeout = milliseconds
            return True

        def connect(self):
            return False

    class FakeProcess:
        def poll(self):
            return 1

    monkeypatch.setattr(maafw_runner_module.time, "sleep", lambda _: None)

    runner = object.__new__(MaaFWRunner)
    runner.send_log = lambda _: None

    with pytest.raises(RuntimeError, match="Agent 进程已退出"):
        runner._connect_agent_client(FakeAgentClient(), FakeProcess(), "agent.py")


def test_maafw_runner_uses_ipc_agent_client_on_windows(monkeypatch):
    class FakeAgentClient:
        def __init__(self):
            self.identifier = "ipc-id"

        @classmethod
        def create_tcp(cls):
            raise AssertionError("Windows 分支不应优先创建 TCP AgentClient")

    monkeypatch.setattr(maafw_runner_module.os, "name", "nt")
    monkeypatch.setattr(maafw_runner_module, "AgentClient", FakeAgentClient)

    runner = object.__new__(MaaFWRunner)
    logs: list[str] = []
    runner.send_log = logs.append

    agent_client = runner._create_agent_client("agent.py")

    assert agent_client.identifier == "ipc-id"
    assert any("IPC 模式" in log for log in logs)


def test_maafw_runner_falls_back_to_tcp_agent_client_on_windows(monkeypatch):
    class FakeAgentClient:
        def __init__(self):
            raise RuntimeError("ipc unavailable")

        @classmethod
        def create_tcp(cls):
            client = object.__new__(cls)
            client.identifier = "59127"
            return client

    monkeypatch.setattr(maafw_runner_module.os, "name", "nt")
    monkeypatch.setattr(maafw_runner_module, "AgentClient", FakeAgentClient)

    runner = object.__new__(MaaFWRunner)
    logs: list[str] = []
    runner.send_log = logs.append

    agent_client = runner._create_agent_client("agent.py")

    assert agent_client.identifier == "59127"
    assert any("回退 TCP" in log for log in logs)


def test_maafw_runner_requires_hwnd_for_desktop_controllers():
    runner = object.__new__(MaaFWRunner)

    with pytest.raises(RuntimeError, match="Win32 controller 需要窗口句柄"):
        runner._create_controller(MaaFWDeviceConfig(type="Win32", hWnd=0))

    with pytest.raises(RuntimeError, match="Gamepad controller 需要窗口句柄"):
        runner._create_controller(MaaFWDeviceConfig(type="Gamepad", hWnd=None))


def test_maafw_runner_does_not_post_next_task_after_cleanup():
    from app.task.MaaFW.run_plan import (
        MaaFWResourceBundlePlan,
        MaaFWRunPlan,
        MaaFWTaskRunPlan,
    )

    plan = MaaFWRunPlan(
        path=".",
        projectName="demo",
        controllerName="ADB",
        controllerType="Adb",
        resourceName="default",
        resource=MaaFWResourceBundlePlan(name="default"),
        agents=[],
        piEnv={},
        tasks=[
            MaaFWTaskRunPlan(name="first", entry="First"),
            MaaFWTaskRunPlan(name="second", entry="Second"),
        ],
    )
    runner = MaaFWRunner(plan, send_log=lambda _: None)
    posted_entries: list[str] = []

    class FakeJob:
        failed = False

        def __init__(self, on_wait=None):
            self.on_wait = on_wait

        def wait(self):
            if self.on_wait is not None:
                self.on_wait()

    class FakeTasker:
        running = True

        def post_task(self, entry, *args):
            posted_entries.append(entry)
            return FakeJob(on_wait=runner.cleanup)

        def post_stop(self):
            self.running = False
            return FakeJob()

    runner.tasker = FakeTasker()

    with pytest.raises(RuntimeError, match="已停止"):
        runner._run_tasks()

    assert posted_entries == ["First"]


def test_maafw_runner_includes_raw_failure_summary_in_job_error():
    from maa.define import MaaStatusEnum, Status, TaskDetail
    from maa.job import JobWithResult

    runner = object.__new__(MaaFWRunner)
    runner._task_failure_summaries = []
    runner._record_task_failure_summary(
        "Node.PipelineNode.Failed",
        {
            "name": "DailyEventEnterMenu",
            "node_details": {
                "name": "DailyEventUnreadItemInit",
                "node_id": 300003360,
            },
            "reco_details": {
                "detail": {
                    "items": [
                        {
                            "box": [55, 118, 122, 20],
                            "text": "危机合约重燃测",
                        }
                    ]
                }
            },
        },
    )
    detail = TaskDetail(
        200000197,
        "DailyRewardStart",
        [300003120, 300003360],
        Status(MaaStatusEnum.failed),
    )
    job = JobWithResult(
        1,
        lambda _: MaaStatusEnum.failed,
        lambda _: MaaStatusEnum.failed,
        lambda _: detail,
    )

    with pytest.raises(RuntimeError) as exc_info:
        runner._wait_job(job)

    message = str(exc_info.value)
    assert "DailyRewardStart" in message
    assert "failed(4000)" in message
    assert "DailyEventUnreadItemInit(300003360)" in message
    assert "危机合约重燃测" in message


def test_maafw_autoproxy_cleans_runner_on_cancel(monkeypatch):
    cleanup_called = threading.Event()

    class FakeScriptConfig:
        def get(self, group: str, name: str):
            if (group, name) == ("Run", "RunTimeLimit"):
                return 1
            return None

    class FakeRunner:
        def __init__(self, plan, *, send_log=None):
            self.plan = plan
            self.send_log = send_log

        def run(self, device_config):
            cleanup_called.wait(timeout=1)
            return MaaFWRunResult(
                success=False,
                projectName="test",
                controllerName="test",
                resourceName="test",
            )

        def cleanup(self):
            cleanup_called.set()

    monkeypatch.setattr(maafw_autoproxy_module, "MaaFWRunner", FakeRunner)

    async def _run():
        task = object.__new__(AutoProxyTask)
        task.run_plan = object()
        task.script_config = FakeScriptConfig()
        task.loop = None
        task.cur_user_log = None
        task.script_info = None

        running = asyncio.create_task(
            task._run_maafw(
                MaaFWDeviceConfig(type="Adb", adbPath="adb.exe", address="127.0.0.1:5555")
            )
        )
        await asyncio.sleep(0.01)
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running

    asyncio.run(_run())

    assert cleanup_called.is_set()


# ==================== MaaFW Agent 环境隔离测试 ====================


def test_maafw_client_library_mode_recovers_after_agent_server_import():
    """Importing maa.agent must not leave AUTO-MAS in AgentServer mode."""

    code = "\n".join(
        [
            "from maa.library import Library",
            "from maa.resource import Resource",
            "from maa.tasker import Tasker",
            "from app.task.MaaFW.runner import _ensure_maafw_client_library_mode",
            "",
            "resource = Resource()",
            "tasker = Tasker()",
            "import maa.agent.agent_server",
            "assert Library.is_agent_server()",
            "_ensure_maafw_client_library_mode()",
            "assert not Library.is_agent_server()",
            "del tasker",
            "del resource",
            "print('ok')",
        ]
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        cwd=Path.cwd(),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "OverflowError" not in result.stderr


def test_maafw_resolve_executable_does_not_fallback_to_sys_executable(tmp_path):
    """项目声明 python/python.exe 不存在时，绝不回退到 AUTO-MAS 的 sys.executable。"""
    from app.task.MaaFW.run_plan import _resolve_executable

    # 创建项目目录，有 agent/main.py 但无 python/python.exe
    project_dir = tmp_path / "maafw_project"
    (project_dir / "agent").mkdir(parents=True)
    (project_dir / "agent" / "main.py").write_text(
        "# placeholder", encoding="utf-8"
    )

    child_exec = "{PROJECT_DIR}/python/python.exe"
    result = _resolve_executable(project_dir, child_exec)

    # 绝不回退到 AUTO-MAS 自身 Python
    assert result["command"] != sys.executable
    # 应标记为隔离 venv runtime
    assert result["runtime_kind"] == "isolated_venv"
    # 应提供隔离 venv 路径
    assert result["isolated_venv_path"] is not None


def test_maafw_resolve_executable_uses_project_python_when_exists(tmp_path):
    """项目自带 python/python.exe 存在时，使用项目自带 Python。"""
    from app.task.MaaFW.run_plan import _resolve_executable

    project_dir = tmp_path / "maafw_project"
    python_dir = project_dir / "python"
    python_dir.mkdir(parents=True)
    python_exe = python_dir / "python.exe"
    python_exe.write_text("# placeholder", encoding="utf-8")

    child_exec = "{PROJECT_DIR}/python/python.exe"
    result = _resolve_executable(project_dir, child_exec)

    assert result["exists"] is True
    assert result["runtime_kind"] == "project_python"
    assert result["isolated_venv_path"] is None


def test_maafw_resolve_executable_detects_project_binary_with_windows_suffix(tmp_path):
    from app.task.MaaFW.run_plan import _resolve_executable

    project_dir = tmp_path / "maafw_project"
    agent_dir = project_dir / "agent"
    agent_dir.mkdir(parents=True)
    agent_exe = agent_dir / "go-service.exe"
    agent_exe.write_text("# placeholder", encoding="utf-8")

    result = _resolve_executable(project_dir, "agent/go-service")

    assert result["exists"] is True
    assert result["runtime_kind"] == "project_binary"
    assert result["command"] == str(agent_exe.resolve())
    assert result["isolated_venv_path"] is None


def test_maafw_project_binary_embedded_flag_keeps_declared_args(tmp_path):
    """Project binary agents must not receive Python entry args."""
    from app.task.MaaFW.interface_models import MaaFWAgent
    from app.task.MaaFW.run_plan import build_maafw_agent_command_plans

    project_dir = tmp_path / "maafw_project"
    agent_dir = project_dir / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "go-service.exe").write_text("# placeholder", encoding="utf-8")

    plans = build_maafw_agent_command_plans(
        project_dir,
        MaaFWAgent(
            child_exec="agent/go-service",
            child_args=[],
            embedded=True,
        ),
    )

    assert plans[0].runtimeKind == "project_binary"
    assert plans[0].command[-1] == "<socket_id>"
    assert "-u" not in plans[0].command
    assert not any(str(arg).endswith("agent/main.py") for arg in plans[0].command)


def test_maafw_embedded_agent_runs_in_isolated_subprocess(tmp_path):
    """Explicit embedded agents should still run outside the MAS process."""
    from app.task.MaaFW.interface_models import MaaFWAgent
    from app.task.MaaFW.run_plan import build_maafw_agent_command_plans

    project_dir = tmp_path / "maafw_project"
    (project_dir / "agent").mkdir(parents=True)
    (project_dir / "agent" / "main.py").write_text(
        "# placeholder",
        encoding="utf-8",
    )

    plans = build_maafw_agent_command_plans(
        project_dir,
        MaaFWAgent(
            child_exec="./python/python.exe",
            child_args=["-u", "./agent/main.py"],
            embedded=True,
        ),
    )

    assert plans[0].embedded is False
    assert plans[0].runtimeKind == "isolated_venv"
    assert plans[0].isolatedVenvPath is not None
    assert plans[0].command[0] != sys.executable
    assert plans[0].command[-2:] == ["./agent/main.py", "<socket_id>"]
    assert plans[0].fallbackReason is not None


def test_maafw_embedded_agent_defaults_to_agent_main(tmp_path):
    """Embedded agents without child_args use agent/main.py as subprocess entry."""
    from app.task.MaaFW.interface_models import MaaFWAgent
    from app.task.MaaFW.run_plan import build_maafw_agent_command_plans

    project_dir = tmp_path / "maafw_project"
    (project_dir / "agent").mkdir(parents=True)
    agent_entry = project_dir / "agent" / "main.py"
    agent_entry.write_text(
        "# placeholder",
        encoding="utf-8",
    )

    plans = build_maafw_agent_command_plans(
        project_dir,
        MaaFWAgent(
            child_exec="./python/python.exe",
            embedded=True,
        ),
    )

    assert plans[0].embedded is False
    assert plans[0].runtimeKind == "isolated_venv"
    assert plans[0].command[-3:] == ["-u", str(agent_entry.resolve()), "<socket_id>"]


def test_maafw_missing_embedded_defaults_to_process_agent(tmp_path):
    """未声明 embedded 的旧项目继续按子进程 agent 处理。"""
    from app.task.MaaFW.interface_models import MaaFWAgent
    from app.task.MaaFW.run_plan import build_maafw_agent_command_plans

    project_dir = tmp_path / "maafw_project"
    (project_dir / "agent").mkdir(parents=True)
    (project_dir / "agent" / "main.py").write_text(
        "# placeholder",
        encoding="utf-8",
    )

    plans = build_maafw_agent_command_plans(
        project_dir,
        MaaFWAgent(
            child_exec="./python/python.exe",
            child_args=["-u", "./agent/main.py"],
        ),
    )

    assert plans[0].embedded is False
    assert plans[0].runtimeKind == "isolated_venv"
    assert plans[0].isolatedVenvPath is not None
    assert plans[0].command[0] != sys.executable


def test_maafw_runner_rejects_embedded_agent_runtime_plan(tmp_path):
    """Runner must not import embedded agents into the AUTO-MAS process."""
    from app.task.MaaFW.run_plan import (
        MaaFWAgentCommandPlan,
        MaaFWResourceBundlePlan,
        MaaFWRunPlan,
    )

    plan = MaaFWRunPlan(
        path=str(tmp_path),
        projectName="demo",
        projectLabel=None,
        controllerName="ADB",
        controllerType="Adb",
        resourceName="default",
        resource=MaaFWResourceBundlePlan(name="default"),
        agents=[
            MaaFWAgentCommandPlan(
                childExec="python",
                executable="python",
                cwd=str(tmp_path),
                embedded=True,
            )
        ],
        piEnv={},
        tasks=[],
        skippedTasks=[],
    )
    runner = MaaFWRunner(plan)

    with pytest.raises(RuntimeError, match="isolated subprocess"):
        runner._load_embedded_agents()


def test_maafw_embedded_agent_registers_implicit_tasker_sink(tmp_path):
    """继承 TaskerEventSink 的 embedded 类应按 MFW 语义自动挂到当前 tasker。"""
    from app.task.MaaFW.run_plan import MaaFWResourceBundlePlan, MaaFWRunPlan

    agent_root = tmp_path / "agent"
    agent_root.mkdir()
    (agent_root / "implicit_sink.py").write_text(
        "\n".join(
            [
                "from maa.tasker import TaskerEventSink",
                "",
                "class DemoSink(TaskerEventSink):",
                "    pass",
            ]
        ),
        encoding="utf-8",
    )

    class FakeResource:
        custom_action_list = []
        custom_recognition_list = []

        def custom_action(self, name):
            def wrapper(cls):
                self.custom_action_list.append(name)
                return cls

            return wrapper

        def custom_recognition(self, name):
            def wrapper(cls):
                self.custom_recognition_list.append(name)
                return cls

            return wrapper

        def add_sink(self, sink):
            return None

    class FakeTasker:
        def __init__(self):
            self.sinks = []

        def add_sink(self, sink):
            self.sinks.append(sink)

    plan = MaaFWRunPlan(
        path=str(tmp_path),
        projectName="demo",
        projectLabel=None,
        controllerName="",
        controllerType="Adb",
        resourceName="",
        resource=MaaFWResourceBundlePlan(name="", label=None),
        agents=[],
        piEnv={},
        tasks=[],
        skippedTasks=[],
    )
    runner = MaaFWRunner(plan, send_log=lambda _: None)
    runner.resource = FakeResource()
    runner.tasker = FakeTasker()
    runner.controller = object()

    assert runner._load_embedded_agent_custom(agent_root) is True
    assert len(runner.event_sinks) == 1
    assert len(runner.tasker.sinks) == 1


def test_maafw_isolated_venv_path_differs_per_project(tmp_path):
    """不同项目路径得到不同隔离 venv 路径。"""
    from app.task.MaaFW.run_plan import _compute_isolated_venv_path

    project_a = tmp_path / "project_a"
    project_b = tmp_path / "project_b"
    project_a.mkdir()
    project_b.mkdir()

    venv_a = _compute_isolated_venv_path(project_a)
    venv_b = _compute_isolated_venv_path(project_b)

    assert venv_a != venv_b
    # venv 路径应在 config/maafw_agent_venvs/ 下
    assert venv_a.parent.name == "maafw_agent_venvs"
    assert venv_b.parent.name == "maafw_agent_venvs"


def test_maafw_runner_env_excludes_mas_virtual_env(tmp_path):
    """agent env 不包含 AUTO-MAS 的 VIRTUAL_ENV，PYTHONPATH 是当前项目显式构造。"""
    from app.task.MaaFW.run_plan import (
        MaaFWResourceBundlePlan,
        MaaFWRunPlan,
    )

    project_path = tmp_path / "maafw_project"
    project_path.mkdir()

    plan = MaaFWRunPlan(
        path=str(project_path),
        projectName="test",
        controllerName="ADB",
        controllerType="Adb",
        resourceName="default",
        resource=MaaFWResourceBundlePlan(name="default"),
        agents=[],
        piEnv={},
        tasks=[],
    )
    runner = object.__new__(MaaFWRunner)
    runner.plan = plan
    runner.send_log = lambda _: None

    # 模拟 AUTO-MAS 自身环境变量
    old_venv = os.environ.get("VIRTUAL_ENV")
    old_pythonhome = os.environ.get("PYTHONHOME")
    old_pythonpath = os.environ.get("PYTHONPATH")
    old_pythonuserbase = os.environ.get("PYTHONUSERBASE")
    old_pip_target = os.environ.get("PIP_TARGET")
    old_pip_prefix = os.environ.get("PIP_PREFIX")
    old_pip_user = os.environ.get("PIP_USER")
    try:
        os.environ["VIRTUAL_ENV"] = "/fake/mas/venv"
        os.environ["PYTHONHOME"] = "/fake/mas/pythonhome"
        os.environ["PYTHONUSERBASE"] = "/fake/mas/userbase"
        os.environ["PYTHONPATH"] = "/fake/mas/pythonpath"
        os.environ["PIP_TARGET"] = "/fake/mas/pip-target"
        os.environ["PIP_PREFIX"] = "/fake/mas/pip-prefix"
        os.environ["PIP_USER"] = "1"

        agent_plan = type("AgentPlan", (), {
            "executable": str(project_path / "python" / "python.exe"),
        })()
        env = runner._build_agent_env(agent_plan)

        # VIRTUAL_ENV 和 PYTHONHOME 必须被清理
        assert "VIRTUAL_ENV" not in env
        assert "PYTHONHOME" not in env
        assert "PYTHONUSERBASE" not in env
        assert "PIP_TARGET" not in env
        assert "PIP_PREFIX" not in env
        assert "PIP_USER" not in env
        # PYTHONPATH 必须是当前项目根目录
        assert env["PYTHONPATH"] == str(project_path)
    finally:
        for key, old_val in [
            ("VIRTUAL_ENV", old_venv),
            ("PYTHONHOME", old_pythonhome),
            ("PYTHONPATH", old_pythonpath),
            ("PYTHONUSERBASE", old_pythonuserbase),
            ("PIP_TARGET", old_pip_target),
            ("PIP_PREFIX", old_pip_prefix),
            ("PIP_USER", old_pip_user),
        ]:
            if old_val is not None:
                os.environ[key] = old_val
            else:
                os.environ.pop(key, None)


def test_maafw_runner_reports_adb_offline_before_controller_start(monkeypatch):
    """ADB offline 时应在 MaaFW controller 创建前给出可操作错误。"""
    runner = object.__new__(MaaFWRunner)
    logs = []
    runner.send_log = logs.append

    class FakeResult:
        returncode = 1
        stdout = ""
        stderr = "error: device offline"

    captured_commands = []

    def fake_run(cmd, **kwargs):
        captured_commands.append(list(cmd))
        return FakeResult()

    monkeypatch.setattr(maafw_runner_module.subprocess, "run", fake_run)
    monkeypatch.setattr(maafw_runner_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(maafw_runner_module, "ADB_READY_RETRY_COUNT", 1)
    monkeypatch.setattr(maafw_runner_module, "ADB_READY_RETRY_INTERVAL", 0)

    with pytest.raises(RuntimeError, match="offline"):
        runner._wait_adb_device_ready(
            MaaFWDeviceConfig(
                type="Adb",
                adbPath="adb.exe",
                address="127.0.0.1:5555",
            )
        )

    assert captured_commands == [
        ["adb.exe", "-s", "127.0.0.1:5555", "get-state"]
    ]
    assert logs
    assert "ADB 设备未就绪" in logs[0]


def test_maafw_runner_pip_install_does_not_upgrade_maafw(monkeypatch):
    """pip 安装命令不包含 --upgrade maafw。"""
    runner = object.__new__(MaaFWRunner)
    runner.send_log = lambda _: None

    captured_commands = []

    class FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured_commands.append(list(cmd))
        return FakeResult()

    monkeypatch.setattr(maafw_runner_module.subprocess, "run", fake_run)

    # pip install helper 本身不加 --upgrade；项目自带 Python 分支不会自动调用它
    runner._pip_install(
        "/fake/python.exe",
        ["json-with-comments"],
        cwd="/fake",
        env={},
    )
    # 隔离 venv: 安装项目 requirements，不 --upgrade
    runner._pip_install(
        "/fake/python.exe",
        ["MaaFw", "json-with-comments"],
        cwd="/fake",
        env={},
    )

    assert len(captured_commands) == 2
    for cmd in captured_commands:
        assert "--upgrade" not in cmd, f"pip 命令不应包含 --upgrade: {cmd}"


def test_maafw_project_python_does_not_auto_install_packages(monkeypatch):
    """项目自带 Python 分支不自动 pip install，避免持久修改 release 目录。"""
    runner = object.__new__(MaaFWRunner)
    runner.send_log = lambda _: None

    def fail_pip_install(*args, **kwargs):
        raise AssertionError("project_python 不应自动安装依赖")

    monkeypatch.setattr(runner, "_pip_install", fail_pip_install)

    assert runner._ensure_agent_packages(
        "/fake/python.exe",
        runtime_kind="project_python",
        cwd="/fake",
        env={},
    ) is True


def test_maafw_runner_reads_agent_requirements_from_project(tmp_path):
    """隔离 venv 的依赖来自 MaaFW 项目 requirements.txt，不来自 AUTO-MAS。"""
    project_path = tmp_path / "maafw_project"
    project_path.mkdir()
    (project_path / "requirements.txt").write_text(
        "json-with-comments\nMaaFw\n",
        encoding="utf-8",
    )

    assert maafw_runner_module._load_project_agent_requirements(project_path) == [
        "json-with-comments",
        "MaaFw",
    ]


def test_maafw_runner_isolated_venv_installs_project_requirements(tmp_path, monkeypatch):
    """隔离 venv 不应串用 AUTO-MAS requirements.txt 中的 maafw pin。"""
    project_path = tmp_path / "maafw_project"
    project_path.mkdir()
    (project_path / "requirements.txt").write_text(
        "MaaFw\njson-with-comments\n",
        encoding="utf-8",
    )

    runner = object.__new__(MaaFWRunner)
    runner.send_log = lambda _: None
    captured_packages = []

    def fake_pip_install(python_exe, packages, **kwargs):
        captured_packages.extend(packages)
        return True

    monkeypatch.setattr(runner, "_pip_install", fake_pip_install)

    assert runner._ensure_agent_packages(
        "/fake/python.exe",
        runtime_kind="isolated_venv",
        project_path=project_path,
        cwd=str(project_path),
        env={},
    ) is True
    assert captured_packages == ["MaaFw", "json-with-comments"]
    assert "maafw==5.8.1" not in captured_packages


def test_maafw_runner_skips_pip_install_when_isolated_manifest_current(
    tmp_path,
    monkeypatch,
):
    """隔离 venv 清单未变化时，不重复执行 pip install。"""
    project_path = tmp_path / "maafw_project"
    project_path.mkdir()
    (project_path / "requirements.txt").write_text("MaaFw\n", encoding="utf-8")
    (project_path / "interface.json").write_text(
        '{"name":"demo","version":"v1"}',
        encoding="utf-8",
    )
    venv_path = tmp_path / "maafw_agent_venvs" / "maafw_venv_demo"
    venv_path.mkdir(parents=True)
    python_path = maafw_runner_module._venv_python_path(venv_path)
    python_path.parent.mkdir(parents=True)
    python_path.write_text("", encoding="utf-8")

    runner = object.__new__(MaaFWRunner)
    logs = []
    runner.send_log = logs.append
    runner._write_isolated_venv_manifest(venv_path, project_path)

    def fail_install(*args, **kwargs):
        raise AssertionError("manifest 未变化时不应执行 pip install")

    monkeypatch.setattr(runner, "_should_rebuild_isolated_venv", lambda *_: False)
    monkeypatch.setattr(runner, "_ensure_isolated_venv", lambda *_: None)
    monkeypatch.setattr(runner, "_check_pip_health", lambda *_, **__: True)
    monkeypatch.setattr(runner, "_ensure_agent_packages", fail_install)

    agent_plan = type(
        "AgentPlan",
        (),
        {
            "isolatedVenvPath": str(venv_path),
            "command": ["python.exe"],
        },
    )()
    runner._prepare_isolated_venv_env(agent_plan, project_path)

    assert "[Python环境] 隔离 venv 依赖清单未变化，跳过 pip install" in logs


def test_maafw_runner_installs_when_manifest_exists_but_venv_python_missing(
    tmp_path,
    monkeypatch,
):
    """manifest 残留但 venv Python 缺失时，不能跳过依赖安装。"""
    project_path = tmp_path / "maafw_project"
    project_path.mkdir()
    (project_path / "requirements.txt").write_text("MaaFw\n", encoding="utf-8")
    (project_path / "interface.json").write_text(
        '{"name":"demo","version":"v1"}',
        encoding="utf-8",
    )
    venv_path = tmp_path / "maafw_agent_venvs" / "maafw_venv_demo"
    venv_path.mkdir(parents=True)

    runner = object.__new__(MaaFWRunner)
    runner.send_log = lambda _: None
    runner._write_isolated_venv_manifest(venv_path, project_path)
    install_called = False

    def fake_install(*args, **kwargs):
        nonlocal install_called
        install_called = True
        return True

    monkeypatch.setattr(runner, "_should_rebuild_isolated_venv", lambda *_: False)
    monkeypatch.setattr(runner, "_ensure_isolated_venv", lambda *_: None)
    monkeypatch.setattr(runner, "_check_pip_health", lambda *_, **__: True)
    monkeypatch.setattr(runner, "_ensure_agent_packages", fake_install)

    agent_plan = type(
        "AgentPlan",
        (),
        {
            "isolatedVenvPath": str(venv_path),
            "command": ["python.exe"],
        },
    )()
    runner._prepare_isolated_venv_env(agent_plan, project_path)

    assert install_called is True


def test_maafw_runner_rebuilds_legacy_isolated_venv_without_manifest(tmp_path):
    """旧隔离 venv 没有 manifest，应重建避免沿用错误 maafw 版本。"""
    project_path = tmp_path / "maafw_project"
    project_path.mkdir()
    (project_path / "requirements.txt").write_text("MaaFw\n", encoding="utf-8")
    (project_path / "interface.json").write_text(
        '{"name":"demo","version":"v1"}',
        encoding="utf-8",
    )

    venv_path = tmp_path / "maafw_agent_venvs" / "maafw_venv_demo"
    python_path = venv_path / ("Scripts" if os.name == "nt" else "bin") / (
        "python.exe" if os.name == "nt" else "python"
    )
    python_path.parent.mkdir(parents=True)
    python_path.write_text("", encoding="utf-8")

    runner = object.__new__(MaaFWRunner)
    runner.send_log = lambda _: None

    assert runner._should_rebuild_isolated_venv(venv_path, project_path) is True


def test_maafw_runner_rebuilds_isolated_venv_when_requirements_change(tmp_path):
    """项目 requirements 变化后，应重建隔离 venv。"""
    project_path = tmp_path / "maafw_project"
    project_path.mkdir()
    (project_path / "requirements.txt").write_text("MaaFw\n", encoding="utf-8")
    (project_path / "interface.json").write_text(
        '{"name":"demo","version":"v1"}',
        encoding="utf-8",
    )

    venv_path = tmp_path / "maafw_agent_venvs" / "maafw_venv_demo"
    python_path = venv_path / ("Scripts" if os.name == "nt" else "bin") / (
        "python.exe" if os.name == "nt" else "python"
    )
    python_path.parent.mkdir(parents=True)
    python_path.write_text("", encoding="utf-8")

    runner = object.__new__(MaaFWRunner)
    runner.send_log = lambda _: None
    runner._write_isolated_venv_manifest(venv_path, project_path)

    assert runner._should_rebuild_isolated_venv(venv_path, project_path) is False
    (project_path / "requirements.txt").write_text(
        "MaaFw\nrequests\n",
        encoding="utf-8",
    )
    assert runner._should_rebuild_isolated_venv(venv_path, project_path) is True


def test_maafw_runner_rebuilds_isolated_venv_when_interface_changes(tmp_path):
    """项目 interface 变化后，应重建隔离 venv。"""
    project_path = tmp_path / "maafw_project"
    project_path.mkdir()
    (project_path / "requirements.txt").write_text("MaaFw\n", encoding="utf-8")
    (project_path / "interface.json").write_text(
        '{"name":"demo","version":"v1"}',
        encoding="utf-8",
    )

    venv_path = tmp_path / "maafw_agent_venvs" / "maafw_venv_demo"
    python_path = venv_path / ("Scripts" if os.name == "nt" else "bin") / (
        "python.exe" if os.name == "nt" else "python"
    )
    python_path.parent.mkdir(parents=True)
    python_path.write_text("", encoding="utf-8")

    runner = object.__new__(MaaFWRunner)
    runner.send_log = lambda _: None
    runner._write_isolated_venv_manifest(venv_path, project_path)

    assert runner._should_rebuild_isolated_venv(venv_path, project_path) is False
    (project_path / "interface.json").write_text(
        '{"name":"demo","version":"v2"}',
        encoding="utf-8",
    )
    assert runner._should_rebuild_isolated_venv(venv_path, project_path) is True


def test_maafw_runner_no_broken_rename_logic():
    """确认破坏性重命名方法已被删除，不会调用 .broken 重命名。"""
    assert not hasattr(MaaFWRunner, "_try_fix_backports_zstd"), (
        "_try_fix_backports_zstd 不应存在"
    )
    assert not hasattr(MaaFWRunner, "_try_upgrade_pip"), (
        "_try_upgrade_pip 不应存在"
    )
    assert not hasattr(MaaFWRunner, "_get_site_packages"), (
        "_get_site_packages 不应存在"
    )
