"""MaaEnd 官方完整包、准备回退、原生更新隔离和配置恢复。"""

import asyncio
import hashlib
import json
import shutil
import threading
import uuid
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from packaging.version import Version

from app.services import script_install
from app.task.MaaEnd import manager
from app.task.MaaEnd.tools import script_update as update
from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed


def pe(machine=0x8664):
    data = bytearray(134)
    data[:2] = b"MZ"
    data[60:64] = (128).to_bytes(4, "little")
    data[128:132] = b"PE\0\0"
    data[132:134] = machine.to_bytes(2, "little")
    return bytes(data)


@pytest.fixture
def installation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "MaaEnd"
    root.mkdir()
    (root / "MaaEnd.exe").write_bytes(pe())
    (root / "interface.json").write_text(
        json.dumps({"name": "MaaEnd", "version": "v2.1.0", "mirrorchyan_rid": "MaaEnd"})
    )
    (root / "resource").mkdir()
    (root / "agent").mkdir()
    (root / "config").mkdir()
    (root / "config/mxu-MaaEnd.json").write_bytes(b'{"user-data": true}')
    archive = tmp_path / "official.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("MaaEnd.exe", pe())
        package.writestr(
            "interface.json",
            json.dumps(
                {"name": "MaaEnd", "version": "v2.2.0", "mirrorchyan_rid": "MaaEnd"}
            ),
        )
        package.writestr("resource/data.json", "{}")
        package.writestr("data/AutoDelivery/catalog.json", '{"release": true}')
        package.writestr("agent/service.exe", b"agent")
    release = {
        "tag_name": "v2.2.0",
        "assets": [
            {
                "name": "MaaEnd-win-x86_64-v2.2.0.zip",
                "size": archive.stat().st_size,
                "digest": "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest(),
            }
        ],
    }
    monkeypatch.setattr(
        update,
        "Config",
        SimpleNamespace(
            proxy=None,
            setting=SimpleNamespace(
                Update=SimpleNamespace(MirrorChyanCDK="", FluxdownTakeoverAll=True)
            ),
        ),
    )
    monkeypatch.setattr(update, "assert_idle", Mock())
    monkeypatch.setattr(update, "request_release", AsyncMock(return_value=release))

    async def download(url, destination, **kwargs):
        shutil.copyfile(archive, destination)

    monkeypatch.setattr(update, "download_file", AsyncMock(side_effect=download))
    config = SimpleNamespace(
        Update=SimpleNamespace(
            TakeoverEnabled=True, Channel="stable", MirrorChyanCDK=""
        ),
        Game=SimpleNamespace(ControllerType="Win32-Front"),
    )
    return root, config


@pytest.mark.asyncio
async def test_official_package_installs_before_runtime_overlay(installation):
    root, config = installation
    await update.update_before_run(root, config)
    assert update.read_install(root) == (Version("2.2.0"), "x86_64")
    assert (root / "data/AutoDelivery/catalog.json").is_file()
    assert (root / "config/mxu-MaaEnd.json").read_bytes() == b'{"user-data": true}'
    assert update.download_file.await_args.kwargs["downloader"] == "fluxdown"
    original = (root / "interface.json").read_bytes()
    update.suspend_native_updates(root)
    assert "mirrorchyan_rid" not in json.loads((root / "interface.json").read_bytes())
    update.recover_runtime_interface(root)
    assert (root / "interface.json").read_bytes() == original


@pytest.mark.asyncio
async def test_checksum_failure_leaves_installation_unchanged(installation):
    root, config = installation
    update.request_release.return_value["assets"][0]["digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError):
        await update.update_before_run(root, config)
    assert update.read_install(root)[0] == Version("2.1.0")


@pytest.mark.asyncio
async def test_wrong_package_version_is_not_installed(installation):
    root, config = installation
    release = update.request_release.return_value
    release["tag_name"] = "v2.3.0"
    release["assets"][0]["name"] = "MaaEnd-win-x86_64-v2.3.0.zip"
    with pytest.raises(ValueError):
        await update.update_before_run(root, config)
    assert update.read_install(root)[0] == Version("2.1.0")


@pytest.mark.asyncio
async def test_mirror_download_still_requires_official_sha256(
    installation, monkeypatch
):
    root, config = installation
    config.Update.MirrorChyanCDK = "test-cdk"
    monkeypatch.setattr(
        update,
        "request_mirror_resource",
        AsyncMock(
            return_value={
                "data": {
                    "update_type": "full",
                    "version_name": "v2.2.0",
                    "url": "https://mirror.example/official.zip",
                }
            }
        ),
    )
    await update.update_before_run(root, config)
    assert update.read_install(root)[0] == Version("2.2.0")
    assert (
        update.download_file.await_args.args[0] == "https://mirror.example/official.zip"
    )


def test_interface_recovery_preserves_external_changes(installation):
    root, _ = installation
    update.suspend_native_updates(root)
    changed = b'{"name":"MaaEnd","version":"v9.0.0"}'
    (root / "interface.json").write_bytes(changed)
    with pytest.raises(script_install.InstallUnsafeError):
        update.recover_runtime_interface(root)
    assert (root / "interface.json").read_bytes() == changed


def test_launch_environment_is_new_and_does_not_mutate_global_environment(
    installation, monkeypatch
):
    monkeypatch.setenv("WEBVIEW2_USER_DATA_FOLDER", "original-profile")
    first, second = (
        update.managed_launch_environment(),
        update.managed_launch_environment(),
    )
    assert first["WEBVIEW2_USER_DATA_FOLDER"] != second["WEBVIEW2_USER_DATA_FOLDER"]
    import os

    assert os.environ["WEBVIEW2_USER_DATA_FOLDER"] == "original-profile"


@pytest.fixture
def scheduler(installation, monkeypatch):
    root, config = installation
    instance = object.__new__(manager.MaaEndManager)
    instance.script_config = config
    instance.script_info = SimpleNamespace(log="")
    instance.task_info = SimpleNamespace(mode="AutoProxy", task_id="test")
    instance._runtime_interface = False
    instance._program_update_prepared = False
    instance._launch_env = None
    monkeypatch.setattr(manager.MaaEndResourceLoader, "get_cached", Mock())
    monkeypatch.setattr(
        manager, "load_maaend_controller_protocol", lambda *args: "Win32"
    )
    monkeypatch.setattr(manager, "push_dispatch_log", AsyncMock())
    monkeypatch.setattr(manager.Publisher, "send", AsyncMock())
    return instance


@pytest.mark.asyncio
async def test_preparation_failure_warns_and_still_suspends_native_updates(
    scheduler, installation, monkeypatch
):
    root, _ = installation
    monkeypatch.setattr(
        update, "update_before_run", AsyncMock(side_effect=TimeoutError())
    )
    await scheduler._prepare_program_update(root)
    manager.Publisher.send.assert_awaited_once()
    assert scheduler._runtime_interface
    assert "mirrorchyan_rid" not in json.loads((root / "interface.json").read_bytes())
    update.recover_runtime_interface(root)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        asyncio.CancelledError(),
        script_install.InstallUnsafeError("unknown"),
        FluxdownCancelUnconfirmed("active"),
    ],
)
async def test_unsafe_and_cancel_never_fall_back(
    scheduler, installation, monkeypatch, error
):
    root, _ = installation
    monkeypatch.setattr(update, "update_before_run", AsyncMock(side_effect=error))
    with pytest.raises(type(error)):
        await scheduler._prepare_program_update(root)
    assert not scheduler._runtime_interface
    manager.Publisher.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_pending_install_cannot_be_accepted_as_safe_fallback(installation):
    root, _ = installation
    directory = script_install.workspace(root)
    directory.mkdir()
    (directory / "transaction.json").write_text("invalid")
    with pytest.raises(script_install.InstallUnsafeError):
        await update.confirm_current_install(root)


def test_config_defaults_and_partial_update_contract():
    from app.config.wire import config_contract
    from app.models.config import MaaEndConfig

    assert MaaEndConfig.model_validate({}).Update.TakeoverEnabled is False
    patch = config_contract(MaaEndConfig, mode="input").model_validate(
        {"Update": {"TakeoverEnabled": True}}
    )
    assert patch.model_dump(exclude_unset=True) == {"Update": {"TakeoverEnabled": True}}


def test_missing_installation_path_survives_reload_for_crash_recovery(
    tmp_path, monkeypatch
):
    from app.models.config import MaaEndConfig

    missing_root = tmp_path / "interrupted-installation"
    home = tmp_path / "mas-home"
    home.mkdir()
    monkeypatch.chdir(home)
    config = MaaEndConfig.model_validate({"Info": {"Path": str(missing_root)}})
    assert config.Info.Path == missing_root


@pytest.mark.asyncio
async def test_same_version_repairs_corrupted_executable_using_recorded_architecture(
    installation,
):
    root, config = installation
    await update.update_before_run(root, config)
    (root / "MaaEnd.exe").write_bytes(b"damaged executable")
    with pytest.raises(script_install.InstallUnsafeError):
        await update.confirm_current_install(root)
    await update.update_before_run(root, config)
    assert update.read_install(root) == (Version("2.2.0"), "x86_64")
    assert script_install.verify_installed_files(root, threading.Event())


@pytest.mark.asyncio
async def test_scheduler_prepares_only_once_for_all_users(
    scheduler, installation, monkeypatch
):
    root, _ = installation
    updater = AsyncMock(return_value="ready")
    monkeypatch.setattr(update, "update_before_run", updater)
    await scheduler._prepare_program_update(root)
    await scheduler._prepare_program_update(root)
    updater.assert_awaited_once()
    update.recover_runtime_interface(root)


@pytest.mark.asyncio
async def test_early_resource_rejection_restores_interface_and_releases_both_locks(
    installation, monkeypatch
):
    from app.models.config import MaaEndConfig

    root, _ = installation
    home = root.parent / "mas-home"
    home.mkdir()
    monkeypatch.chdir(home)
    config = MaaEndConfig.model_validate(
        {"Info": {"Path": str(root)}, "Update": {"TakeoverEnabled": True}}
    )
    script_id = uuid.uuid4()
    task = SimpleNamespace(mode="AutoProxy", task_id="test")
    info = SimpleNamespace(
        task_info=task, script_id=str(script_id), user_list=[], status="等待", log=""
    )
    instance = manager.MaaEndManager(info)
    instance.check = AsyncMock(return_value="unsupported controller")
    lock, unlock = AsyncMock(return_value="ticket"), AsyncMock()
    monkeypatch.setattr(MaaEndConfig, "lock_x", lock)
    monkeypatch.setattr(MaaEndConfig, "unlock", unlock)
    monkeypatch.setattr(
        manager, "Config", SimpleNamespace(ScriptConfig={script_id: config})
    )
    monkeypatch.setattr(manager.MaaEndResourceLoader, "get_cached", Mock())
    monkeypatch.setattr(
        manager, "load_maaend_controller_protocol", lambda *args: "Win32"
    )
    monkeypatch.setattr(manager, "push_dispatch_log", AsyncMock())
    monkeypatch.setattr(manager.Publisher, "send", AsyncMock())

    async def prepared(*args, **kwargs):
        instance.check.assert_not_awaited()
        return "ready"

    monkeypatch.setattr(update, "update_before_run", AsyncMock(side_effect=prepared))
    original = (root / "interface.json").read_bytes()
    await instance.main_task()
    lock.assert_awaited_once()
    assert instance._runtime_interface
    await instance.final_task()
    assert (root / "interface.json").read_bytes() == original
    unlock.assert_awaited_once_with("ticket")
    with script_install.installation_access(root):
        pass
