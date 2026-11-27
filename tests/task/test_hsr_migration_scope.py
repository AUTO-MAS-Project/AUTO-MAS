import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import Config
from app.models.config import HSRConfig, HSRUserConfig
from app.models.task import TaskItem, TaskScriptItem, TaskUserItem
from app.task.history_core import TaskHistorySession
from app.task.HSR import AutoProxy as hsr_autoproxy
from app.task.HSR import manager as hsr_manager
from app.task.HSR.tools import account_switch, m7a_paths
from app.task.HSR.tools.m7a_runtime import M7ARunner
from app.task.HSR.tools.native_control import (
    M7ANativeControlProvider,
    SRANativeControlProvider,
)
from tests.config_support import activate_config


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("accounts", "migration_completes", "expected_status"),
    [
        (("native_sra",), False, ("完成",)),
        (("managed_sra",), False, ("完成",)),
        (("native_m7a", "native_sra"), False, ("异常", "完成")),
        (("managed_m7a", "managed_sra"), False, ("异常", "完成")),
        (("native_m7a",), True, ("完成",)),
        (("managed_m7a",), True, ("完成",)),
    ],
)
async def test_hsr_only_prepares_m7a_for_accounts_that_use_it(
    isolated_app_paths, monkeypatch, accounts, migration_completes, expected_status
):
    root = isolated_app_paths.work_path
    mas_root = root / "mas"
    mas_root.mkdir()
    monkeypatch.chdir(mas_root)
    monkeypatch.setattr(m7a_paths, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.delenv("M7A_DATA_DIR", raising=False)
    appdata = root / "appdata"
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setattr(hsr_manager, "disable_sra_windows_notifications", lambda: None)

    m7a = root / "m7a"
    marker = m7a / "assets" / "config" / "version.txt"
    marker.parent.mkdir(parents=True)
    marker.write_text("v2026.11.25-beta", encoding="utf-8")
    (m7a / "March7th Assistant.exe").touch()
    (m7a / "m7a.exe").touch()
    legacy = m7a / "config.yaml"
    original = b"daily_enable: true\n"
    legacy.write_bytes(original)
    migrated = m7a / "userdata" / "config.yaml"

    sra = root / "sra"
    sra.mkdir()
    (sra / "SRA-cli.exe").touch()
    profile = appdata / "SRA" / "configs" / "Default.json"
    profile.parent.mkdir(parents=True)
    profile.write_text("{}", encoding="utf-8")

    config = await activate_config(
        HSRConfig(
            Info={"SRAPath": sra, "M7APath": m7a},
            Game={"Enabled": False},
            Update={"AutoUpdateMode": "Off"},
        )
    )
    task_info = TaskItem()
    await task_info.activate()
    script_key = task_info.scripts.add(
        TaskScriptItem, payload={"info": {"script_id": str(config.uid), "name": "HSR"}}
    )
    await task_info.scripts.commit()
    script = task_info.scripts[script_key]
    for account in accounts:
        mode, engine = account.split("_")
        engine = engine.upper()
        user_id = config.UserData.add(
            HSRUserConfig,
            payload={
                "Info": {
                    "Name": account,
                    "Base": "native" if mode == "native" else "independent",
                    "Status": True,
                    "RemainedDay": -1,
                },
                "Control": {engine: True},
                "TaskSwitch": {"Daily": False, "ReceiveRewards": True},
                "Managed": {"TaskMapping": json.dumps({"ReceiveRewards": engine})},
            },
        )
        script.users.add(
            TaskUserItem, payload={"info": {"user_id": str(user_id), "name": account}}
        )
    await config.UserData.commit()
    await script.users.commit()
    await task_info.set_current_index(0)
    monkeypatch.setattr(Config, "ScriptConfig", {config.uid: config})

    migration_attempts = []

    async def upstream_status(program, command, **kwargs):
        assert (program, command) == (m7a / "m7a.exe", "--status")
        migration_attempts.append(kwargs["cwd"])
        if migration_completes:
            migrated.parent.mkdir()
            legacy.rename(migrated)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(
        m7a_paths, "ProcessRunner", SimpleNamespace(run_process=upstream_status)
    )

    async def run_managed_m7a(_runner, _command, *, timeout):
        assert not legacy.exists()
        assert migrated.is_file()
        migrated.write_bytes(b"daily_enable: false\n")
        return SimpleNamespace(success=True)

    monkeypatch.setattr(M7ARunner, "run_task", run_managed_m7a)
    monkeypatch.setattr(
        account_switch,
        "run_sra_single_task",
        AsyncMock(return_value=SimpleNamespace(success=True)),
    )

    async def run_native_m7a(_timeout):
        assert not legacy.exists()
        assert migrated.is_file()
        return SimpleNamespace(success=True, summary="", error="")

    for provider_cls, run_fn in (
        (
            SRANativeControlProvider,
            AsyncMock(return_value=SimpleNamespace(success=True, summary="", error="")),
        ),
        (M7ANativeControlProvider, run_native_m7a),
    ):
        session = SimpleNamespace(run=run_fn, close=AsyncMock())
        monkeypatch.setattr(
            provider_cls,
            "open_direct_session",
            AsyncMock(return_value=session),
        )
    manager = hsr_manager.HSRManager(script)
    manager.history = TaskHistorySession(task_info)
    try:
        await manager.main_task()
        assert manager.check_result == "Pass"
        assert tuple(user.status for user in script.user_list) == expected_status
    finally:
        await manager.callbacks.drain()
        restore_error = await manager._restore_external_configs()
        manager._release_external_path_lock()
        await manager._unlock_script_config()

    assert not restore_error
    assert migration_attempts == [m7a for name in accounts if name.endswith("_m7a")]
    if migration_completes:
        assert not legacy.exists()
        assert migrated.read_bytes() == original
    else:
        assert legacy.read_bytes() == original
        assert not migrated.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("already_migrated", "mode"),
    [
        (True, "managed"),
        (False, "managed"),
        (False, "native"),
    ],
)
async def test_sra_before_script_edit_does_not_become_m7a_backup_baseline(
    isolated_app_paths, monkeypatch, already_migrated, mode
):
    root = isolated_app_paths.work_path
    mas_root = root / "mas"
    mas_root.mkdir()
    monkeypatch.chdir(mas_root)
    monkeypatch.setattr(m7a_paths, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.delenv("M7A_DATA_DIR", raising=False)
    appdata = root / "appdata"
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setattr(hsr_manager, "disable_sra_windows_notifications", lambda: None)

    m7a = root / "m7a"
    marker = m7a / "assets" / "config" / "version.txt"
    marker.parent.mkdir(parents=True)
    marker.write_text("v2026.11.25-beta", encoding="utf-8")
    (m7a / "March7th Assistant.exe").touch()
    (m7a / "m7a.exe").touch()
    legacy = m7a / "config.yaml"
    migrated = m7a / "userdata" / "config.yaml"
    original = b"daily_enable: true\n"
    temp_from_sra = b"daily_enable: false\n# temp from sra before-script\n"
    if already_migrated:
        migrated.parent.mkdir()
        migrated.write_bytes(original)
    else:
        legacy.write_bytes(original)

    sra = root / "sra"
    sra.mkdir()
    (sra / "SRA-cli.exe").touch()
    profile = appdata / "SRA" / "configs" / "Default.json"
    profile.parent.mkdir(parents=True)
    profile.write_text("{}", encoding="utf-8")

    config = await activate_config(
        HSRConfig(
            Info={"SRAPath": sra, "M7APath": m7a},
            Game={"Enabled": False},
            Update={"AutoUpdateMode": "Off"},
        )
    )
    task_info = TaskItem()
    await task_info.activate()
    script_key = task_info.scripts.add(
        TaskScriptItem, payload={"info": {"script_id": str(config.uid), "name": "HSR"}}
    )
    await task_info.scripts.commit()
    script = task_info.scripts[script_key]
    for engine in ("SRA", "M7A"):
        name = f"{mode}_{engine.lower()}"
        user_id = config.UserData.add(
            HSRUserConfig,
            payload={
                "Info": {
                    "Name": name,
                    "Base": "native" if mode == "native" else "independent",
                    "Status": True,
                    "RemainedDay": -1,
                },
                "Control": {engine: True},
                "TaskSwitch": {"Daily": False, "ReceiveRewards": True},
                "Managed": {"TaskMapping": json.dumps({"ReceiveRewards": engine})},
            },
        )
        script.users.add(
            TaskUserItem, payload={"info": {"user_id": str(user_id), "name": name}}
        )
    await config.UserData.commit()
    await script.users.commit()
    await task_info.set_current_index(0)
    monkeypatch.setattr(Config, "ScriptConfig", {config.uid: config})

    async def before_script(user_cfg):
        if str(user_cfg.Info.Name).endswith("_sra"):
            target = migrated if already_migrated else legacy
            target.write_bytes(temp_from_sra)

    monkeypatch.setattr(hsr_manager, "run_script_before_task", before_script)
    monkeypatch.setattr(hsr_autoproxy, "run_script_before_task", before_script)

    migrated_bytes = []

    async def upstream_status(program, command, **kwargs):
        assert (program, command) == (m7a / "m7a.exe", "--status")
        migrated_bytes.append(legacy.read_bytes())
        migrated.parent.mkdir()
        legacy.rename(migrated)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(
        m7a_paths, "ProcessRunner", SimpleNamespace(run_process=upstream_status)
    )

    async def run_managed_m7a(_runner, _command, *, timeout):
        assert migrated.is_file()
        migrated.write_bytes(b"daily_enable: false\n# patched during run\n")
        return SimpleNamespace(success=True)

    monkeypatch.setattr(M7ARunner, "run_task", run_managed_m7a)
    monkeypatch.setattr(
        account_switch,
        "run_sra_single_task",
        AsyncMock(return_value=SimpleNamespace(success=True)),
    )

    async def run_native_m7a(_timeout):
        assert migrated.read_bytes() == original
        return SimpleNamespace(success=True, summary="", error="")

    for provider_cls, run_fn in (
        (
            SRANativeControlProvider,
            AsyncMock(return_value=SimpleNamespace(success=True, summary="", error="")),
        ),
        (M7ANativeControlProvider, run_native_m7a),
    ):
        session = SimpleNamespace(run=run_fn, close=AsyncMock())
        monkeypatch.setattr(
            provider_cls,
            "open_direct_session",
            AsyncMock(return_value=session),
        )

    manager = hsr_manager.HSRManager(script)
    manager.history = TaskHistorySession(task_info)
    try:
        await manager.main_task()
        assert manager.check_result == "Pass"
        assert tuple(user.status for user in script.user_list) == ("完成", "完成")
    finally:
        await manager.callbacks.drain()
        restore_error = await manager._restore_external_configs()
        manager._release_external_path_lock()
        await manager._unlock_script_config()

    assert not restore_error
    if not already_migrated:
        assert migrated_bytes == [original]
    assert not legacy.exists()
    assert migrated.read_bytes() == original
