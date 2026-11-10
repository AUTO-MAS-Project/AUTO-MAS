"""BAAH 下载/安装分离及配置保护；网络与真实程序进程在边界隔离。"""

import hashlib
import json
import shutil
import threading
import uuid
import zipfile
from contextlib import ExitStack
from tests.runtime_support import RuntimeStub as SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from packaging.version import Version

from app.services import script_install
from app.task.BAAH import manager
from app.task.BAAH.tools import program_update as update

REAL_ASSERT_IDLE = update.assert_idle


def pe(extra=b""):
    data = bytearray(134)
    data[:2] = b"MZ"
    data[60:64] = (128).to_bytes(4, "little")
    data[128:132] = b"PE\0\0"
    data[132:134] = (0x8664).to_bytes(2, "little")
    return bytes(data) + extra


@pytest.fixture
def installation(tmp_path, monkeypatch, isolated_app_paths):
    root = tmp_path / "BAAH"
    (root / "DATA/CONFIGS").mkdir(parents=True)
    (root / "DATA/CONFIGS/software_config.json").write_text(
        '{"NOWVERSION":"2.5.6", "custom":true}'
    )
    (root / "BAAH_CONFIGS").mkdir()
    (root / "BAAH_CONFIGS/account.json").write_text('{"opaque": true}')
    (root / "BAAH.exe").write_bytes(pe())
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("BAAH.exe", pe(b"new"))
        package.writestr("DATA/icons/icon.png", b"resource")
    release = {
        "tag_name": "BAAH2.5.7",
        "assets": [
            {
                "name": "BAAH2.5.7_update.zip",
                "size": archive.stat().st_size,
                "digest": "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest(),
            }
        ],
    }
    config = SimpleNamespace(
        Update=SimpleNamespace(Channel="stable", MirrorChyanCDK="")
    )
    monkeypatch.setattr(
        update,
        "Config",
        SimpleNamespace(
            data_path=tmp_path / "cache",
            proxy=None,
            setting=SimpleNamespace(Update=SimpleNamespace(MirrorChyanCDK="")),
        ),
    )
    monkeypatch.setattr(update, "assert_idle", lambda root, **kwargs: None)
    monkeypatch.setattr(update, "request_release", AsyncMock(return_value=release))

    async def download(url, destination, **kwargs):
        shutil.copyfile(archive, destination)

    monkeypatch.setattr(
        update, "download_script_package", AsyncMock(side_effect=download)
    )
    return root, config, archive, release


@pytest.mark.asyncio
async def test_prepare_can_run_while_installation_is_reserved_then_apply_preserves_configs(
    installation,
):
    root, config, _, _ = installation
    with script_install.installation_access(root):
        prepared = await update.prepare_update(root, config)
    assert (root / "BAAH.exe").read_bytes() == pe()
    with script_install.installation_access(root):
        await update.apply_update(root, prepared)
    assert (root / "BAAH.exe").read_bytes() == pe(b"new")
    assert (
        json.loads((root / "DATA/CONFIGS/software_config.json").read_text())["custom"]
        is True
    )
    assert (root / "BAAH_CONFIGS/account.json").read_text() == '{"opaque": true}'
    assert update.read_version(root) == Version("2.5.7")
    assert (script_install.record_directory(root) / "installed.json").is_file()
    assert (script_install.record_directory(root) / "baah-version.json").is_file()
    assert not script_install.workspace(root).exists()
    await update.confirm_current_install(root)
    assert await update.prepare_update(root, config) is None


@pytest.mark.asyncio
async def test_legacy_records_are_deleted_before_next_update(installation):
    root, config, _, _ = installation
    prepared = await update.prepare_update(root, config)
    await update.apply_update(root, prepared)
    directory = script_install.record_directory(root)
    legacy = script_install.workspace(root)
    legacy.mkdir()
    for name in ("installed.json", "baah-version.json"):
        (directory / name).replace(legacy / name)

    with script_install.installation_access(root):
        script_install.recover_install(root, lambda: None, threading.Event())
        assert not legacy.exists()
        assert not list(directory.iterdir())
        await update.update_before_run(root, config)

    assert update.read_version(root) == Version("2.5.7")
    assert (directory / "installed.json").is_file()
    assert (directory / "baah-version.json").is_file()
    assert await update.prepare_update(root, config) is None


@pytest.mark.asyncio
async def test_archive_tampering_is_rejected_again_at_apply(installation):
    root, config, _, _ = installation
    prepared = await update.prepare_update(root, config)
    prepared.archive.write_bytes(b"changed after download")
    with pytest.raises(ValueError):
        await update.apply_update(root, prepared)
    assert (root / "BAAH.exe").read_bytes() == pe()


@pytest.mark.asyncio
async def test_changed_executable_invalidates_prefetch(installation):
    root, config, _, _ = installation
    prepared = await update.prepare_update(root, config)
    (root / "BAAH.exe").write_bytes(pe(b"native newer"))
    with pytest.raises(ValueError):
        await update.apply_update(root, prepared)
    assert (root / "BAAH.exe").read_bytes() == pe(b"native newer")


@pytest.mark.asyncio
async def test_package_cannot_replace_user_config(installation):
    root, config, archive, release = installation
    with zipfile.ZipFile(archive, "a") as package:
        package.writestr("DATA/CONFIGS/software_config.json", "{}")
    release["assets"][0]["size"] = archive.stat().st_size
    release["assets"][0]["digest"] = (
        "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
    )
    with pytest.raises(ValueError):
        await update.prepare_update(root, config)
    assert (
        json.loads((root / "DATA/CONFIGS/software_config.json").read_text())["custom"]
        is True
    )


@pytest.mark.asyncio
async def test_download_cancellation_cannot_modify_installation(installation):
    import asyncio

    root, config, _, _ = installation
    update.download_script_package.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await update.prepare_update(root, config)
    assert (root / "BAAH.exe").read_bytes() == pe()


@pytest.mark.asyncio
async def test_existing_install_allows_toolkit_adb_but_update_remains_strict(
    installation, monkeypatch
):
    root, config, _, _ = installation
    prepared = await update.prepare_update(root, config)
    assert prepared is not None
    adb = root / "tools" / "adb" / "adb.exe"
    adb.parent.mkdir(parents=True)
    adb.write_bytes(pe())
    monkeypatch.setattr(
        update.psutil,
        "process_iter",
        lambda fields: [SimpleNamespace(info={"exe": str(adb), "name": "adb.exe"})],
    )

    def check_idle(root, *, allow_background_adb=False):
        if not allow_background_adb:
            raise script_install.InstallUnsafeError("adb is still running")

    monkeypatch.setattr(update, "assert_idle", check_idle)
    # A non-mutating confirmation tolerates a server, but applying a package does not.
    await update.confirm_current_install(root)
    with pytest.raises(script_install.InstallUnsafeError, match="adb"):
        await update.apply_update(root, prepared)


@pytest.mark.asyncio
async def test_install_lock_conflict_never_marks_unrun_task_complete(
    installation, monkeypatch
):
    root, config, _, _ = installation
    instance = object.__new__(manager.BAAHManager)
    instance.maintenance = False
    instance._install_access = ExitStack()
    instance.check_result = "Pass"
    instance.script_config = SimpleNamespace(
        Script=SimpleNamespace(BAAHPath=root / "BAAH.exe"),
        Update=config.Update,
        uid=uuid.uuid4(),
    )
    instance.script_info = SimpleNamespace(status="等待", user_list=[])
    instance.config_locks = {}
    instance.task_info = SimpleNamespace(mode="AutoProxy", task_id=str(uuid.uuid4()))
    monkeypatch.setattr(manager.Publisher, "send", AsyncMock())
    with script_install.installation_access(root):
        with pytest.raises(script_install.InstallUnsafeError) as raised:
            await instance._prepare_program_update()
    await instance.on_crash(raised.value)
    await instance.final_task()
    assert instance.script_info.status == "异常"
    assert instance.check_result != "Pass"


@pytest.mark.asyncio
async def test_second_baah_config_waits_for_same_directory(installation, monkeypatch):
    import asyncio

    from app.utils import update_files

    root, config, _, _ = installation
    config.Update.TakeoverEnabled = False
    monkeypatch.setattr(manager.script_install, "run_worker", AsyncMock())
    one = object.__new__(manager.BAAHManager)
    two = object.__new__(manager.BAAHManager)
    for instance in (one, two):
        instance._install_access = ExitStack()
        instance._directory_lock = None
        instance.script_config = SimpleNamespace(
            Script=SimpleNamespace(BAAHPath=root / "BAAH.exe"),
            Update=config.Update,
        )
        instance.check_result = "Pass"
        instance.script_info = SimpleNamespace(
            script_id=str(uuid.uuid4()), set_log=AsyncMock()
        )

    # 第一个任务在整个用户运行期间独占目录；第二个任务要等待。
    await one._prepare_program_update()
    pending = asyncio.create_task(two._prepare_program_update())
    await asyncio.sleep(0)
    assert not pending.done()
    assert update_files.directory_lock(root).locked()
    one._install_access.close()
    one._directory_lock.release()
    one._directory_lock = None
    await asyncio.wait_for(pending, 2)
    assert two.check_result == "Pass"
    two._install_access.close()
    two._directory_lock.release()


def test_real_idle_whitelist_rejects_baah_but_allows_known_adb(
    installation, monkeypatch
):
    root, _, _, _ = installation
    adb = root / "tools" / "adb" / "adb.exe"
    adb.parent.mkdir(parents=True, exist_ok=True)
    adb.write_bytes(pe())
    processes = [SimpleNamespace(info={"exe": str(adb), "name": "adb.exe"})]
    monkeypatch.setattr(update.psutil, "process_iter", lambda fields: processes)
    REAL_ASSERT_IDLE(root, allow_background_adb=True)
    with pytest.raises(script_install.InstallUnsafeError):
        REAL_ASSERT_IDLE(root)
    processes.append(
        SimpleNamespace(info={"exe": str(root / "BAAH.exe"), "name": "BAAH.exe"})
    )
    with pytest.raises(script_install.InstallUnsafeError):
        REAL_ASSERT_IDLE(root, allow_background_adb=True)


@pytest.mark.asyncio
async def test_explicit_repair_can_reinstall_missing_baah_exe(installation):
    root, config, _, _ = installation
    original = await update.prepare_update(root, config)
    await update.apply_update(root, original)
    receipt = script_install.record_path(root, "installed.json")
    assert receipt.is_file()
    snapshot = receipt.read_bytes()
    (root / "BAAH.exe").unlink()
    with pytest.raises(script_install.InstallUnsafeError):
        await update.confirm_current_install(root)
    with pytest.raises(OSError):
        await update.prepare_update(root, config)
    result = await update.update_before_run(root, config, recovery_receipt=snapshot)
    assert "校验通过" in result
    assert (root / "BAAH.exe").read_bytes() == pe(b"new")
    assert not (script_install.workspace(root) / "transaction.json").exists()
    await update.confirm_current_install(root)


@pytest.mark.asyncio
async def test_repair_refuses_changed_receipt(installation):
    root, config, _, _ = installation
    candidate = await update.prepare_update(root, config)
    await update.apply_update(root, candidate)
    receipt = script_install.record_path(root, "installed.json")
    previous = receipt.read_bytes()
    receipt.write_text('{"files":{}}')
    with pytest.raises(script_install.InstallUnsafeError, match="已改变"):
        await update.update_before_run(root, config, recovery_receipt=previous)
    assert (root / "BAAH.exe").is_file()


@pytest.mark.asyncio
async def test_manager_without_takeover_repairs_corrupt_receipt_via_common_entry(
    installation, monkeypatch
):
    root, config, _, _ = installation
    prepared = await update.prepare_update(root, config)
    await update.apply_update(root, prepared)
    (root / "BAAH.exe").write_bytes(pe(b"corrupt"))
    config.Update.TakeoverEnabled = False

    instance = object.__new__(manager.BAAHManager)
    instance._install_access = ExitStack()
    instance._directory_lock = None
    instance.script_config = SimpleNamespace(
        Script=SimpleNamespace(BAAHPath=root / "BAAH.exe"),
        Update=config.Update,
    )
    instance.script_info = SimpleNamespace(
        script_id=str(uuid.uuid4()), name="BAAH A", set_log=AsyncMock()
    )
    instance.task_info = SimpleNamespace(task_id="task", mode="AutoProxy")
    common = AsyncMock(return_value="reinstalled")
    monkeypatch.setattr(manager, "auto_recover_script_install", common)
    await instance._prepare_program_update()
    common.assert_awaited_once()
    instance._install_access.close()
    if instance._directory_lock is not None:
        instance._directory_lock.release()


@pytest.mark.asyncio
async def test_baah_stale_journal_automatically_requires_verified_receipt(
    installation, monkeypatch
):
    from app.task.BAAH.tools.managed_recovery import inspect_stale_transaction

    root, config, _, _ = installation
    candidate = await update.prepare_update(root, config)
    await update.apply_update(root, candidate)
    marker = script_install.workspace(root) / "transaction.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_bytes(b'{"state":"completed"}')
    state = await inspect_stale_transaction(root)
    assert state.pending and state.healthy and state.updated_confirmed
    (root / "BAAH.exe").write_bytes(b"bad")
    unhealthy = await inspect_stale_transaction(root)
    assert unhealthy.pending and not unhealthy.healthy


@pytest.mark.asyncio
async def test_baah_corrupt_install_has_no_gui_dependency(installation, monkeypatch):
    root, config, _, _ = installation
    candidate = await update.prepare_update(root, config)
    await update.apply_update(root, candidate)
    (root / "BAAH.exe").unlink()
    config.Update.TakeoverEnabled = False
    manager_mock = object.__new__(manager.BAAHManager)
    manager_mock._install_access = ExitStack()
    manager_mock._directory_lock = None
    manager_mock.script_config = SimpleNamespace(
        Script=SimpleNamespace(BAAHPath=root / "BAAH.exe"),
        Update=config.Update,
    )
    manager_mock.script_info = SimpleNamespace(
        script_id=str(uuid.uuid4()), name="BAAH", set_log=AsyncMock()
    )
    manager_mock.task_info = SimpleNamespace(task_id="task", mode="AutoProxy")
    monkeypatch.setattr(
        manager, "auto_recover_script_install", AsyncMock(return_value="reinstalled")
    )
    await manager_mock._prepare_program_update()
    manager.auto_recover_script_install.assert_awaited_once()
    manager_mock._install_access.close()
    if manager_mock._directory_lock is not None:
        manager_mock._directory_lock.release()
