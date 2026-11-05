"""MaaEnd 官方完整包、准备回退、原生更新隔离和配置恢复。"""

import asyncio
import base64
import hashlib
import json
import shutil
import threading
import zipfile
from pathlib import Path
from tests.runtime_support import RuntimeStub as SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from packaging.version import Version

from app.services import script_install
from app.services.common.update.fluxdown import FluxdownResumableError
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
async def test_official_package_installs_and_preserves_native_interface(installation):
    root, config = installation
    await update.update_before_run(root, config)
    assert update.read_install(root) == (Version("2.2.0"), "x86_64")
    assert not list((root.parent / "data/maaend_update").glob("download-*"))
    assert (root / "data/AutoDelivery/catalog.json").is_file()
    assert (root / "config/mxu-MaaEnd.json").read_bytes() == b'{"user-data": true}'
    assert update.download_file.await_args.kwargs["downloader"] == "fluxdown"
    assert (
        json.loads((root / "interface.json").read_bytes())["mirrorchyan_rid"]
        == "MaaEnd"
    )


@pytest.mark.asyncio
async def test_checksum_failure_leaves_installation_unchanged(installation):
    root, config = installation
    update.request_release.return_value["assets"][0]["digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError):
        await update.update_before_run(root, config)
    assert update.read_install(root)[0] == Version("2.1.0")
    assert not list((root.parent / "data/maaend_update").glob("download-*"))


@pytest.mark.asyncio
async def test_wrong_package_version_is_not_installed(installation):
    root, config = installation
    release = update.request_release.return_value
    release["tag_name"] = "v2.3.0"
    release["assets"][0]["name"] = "MaaEnd-win-x86_64-v2.3.0.zip"
    with pytest.raises(ValueError):
        await update.update_before_run(root, config)
    assert update.read_install(root)[0] == Version("2.1.0")


def _create_old_interface_journal(root: Path) -> bytes:
    original = (root / "interface.json").read_bytes()
    injected = b'{"name":"MaaEnd","version":"v2.1.0"}'
    journal = script_install.workspace(root) / "runtime-interface.json"
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(
        json.dumps(
            {
                "original": base64.b64encode(original).decode(),
                "injected": base64.b64encode(injected).decode(),
            }
        )
    )
    (root / "interface.json").write_bytes(injected)
    return original


def test_legacy_interface_journal_is_restored(installation):
    root, _ = installation
    original = _create_old_interface_journal(root)
    update.recover_runtime_interface(root)
    assert (root / "interface.json").read_bytes() == original
    assert not (script_install.workspace(root) / "runtime-interface.json").exists()


def test_interface_recovery_preserves_external_changes(installation):
    root, _ = installation
    _create_old_interface_journal(root)
    changed = b'{"name":"MaaEnd","version":"v9.0.0"}'
    (root / "interface.json").write_bytes(changed)
    with pytest.raises(script_install.InstallUnsafeError):
        update.recover_runtime_interface(root)
    assert (root / "interface.json").read_bytes() == changed


def _cached_mxu_zip(
    root: Path, filename: str, version: str, project: str = "MaaEnd"
) -> Path:
    cache = root / "cache"
    cache.mkdir(exist_ok=True)
    path = cache / filename
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("MaaEnd.exe", pe())
        package.writestr(
            "interface.json", json.dumps({"name": project, "version": version})
        )
    return path


def test_discard_old_mxu_package_preserves_cache_and_newer_archives(installation):
    root, _ = installation
    webview = root / "cache" / "webview_data"
    webview.mkdir(parents=True)
    (webview / "Preferences").write_text("persistent")
    old = _cached_mxu_zip(root, "MaaEnd-win-x86_64-v2.0.0.zip", "v2.0.0")
    same = _cached_mxu_zip(root, "MaaEnd-win-x86_64-v2.1.0.zip", "v2.1.0")
    future = _cached_mxu_zip(root, "MaaEnd-win-x86_64-v2.2.0.zip", "v2.2.0")
    different = _cached_mxu_zip(root, "MaaEnd-win-x86_64-test.zip", "v2.0.0", "Other")
    unknown = _cached_mxu_zip(root, "user-backup.zip", "v2.0.0")
    removed = update.discard_obsolete_mxu_packages(root, threading.Event())
    assert set(removed) == {old.name, same.name}
    assert not old.exists() and not same.exists()
    assert future.is_file() and different.is_file() and unknown.is_file()
    assert (webview / "Preferences").read_text() == "persistent"
    assert (
        json.loads((root / "interface.json").read_text())["mirrorchyan_rid"] == "MaaEnd"
    )


def test_reparse_cache_is_rejected(installation, monkeypatch):
    root, _ = installation
    target = _cached_mxu_zip(root, "MaaEnd-win-x86_64-v2.0.0.zip", "v2.0.0")
    cache = root / "cache"
    original_lstat = Path.lstat

    def fake_junction(path, *args, **kwargs):
        info = original_lstat(path, *args, **kwargs)
        if path == cache:
            return SimpleNamespace(st_mode=info.st_mode, st_reparse_tag=1)
        return info

    monkeypatch.setattr(Path, "lstat", fake_junction)
    with pytest.raises(script_install.InstallUnsafeError, match="重解析点"):
        update.discard_obsolete_mxu_packages(root, threading.Event())
    assert target.is_file()


@pytest.mark.asyncio
async def test_cancelled_cleanup_waits_for_worker(installation, monkeypatch):
    root, _ = installation
    target = _cached_mxu_zip(root, "MaaEnd-win-x86_64-v2.0.0.zip", "v2.0.0")
    started, resume = threading.Event(), threading.Event()
    original_is_file = Path.is_file

    def blocked_is_file(path):
        if path == target:
            started.set()
            resume.wait(3)
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", blocked_is_file)
    task = asyncio.create_task(
        script_install.run_worker(update.discard_obsolete_mxu_packages, root)
    )
    try:
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        assert not task.done()
    finally:
        resume.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 5)
    assert target.is_file()


@pytest.fixture
def scheduler(installation, monkeypatch):
    root, config = installation
    instance = object.__new__(manager.MaaEndManager)
    instance.maintenance = False
    instance.script_config = config
    instance.script_info = SimpleNamespace(log="")
    instance.task_info = SimpleNamespace(mode="AutoProxy", task_id="test")
    instance._program_update_prepared = False
    monkeypatch.setattr(manager.MaaEndResourceLoader, "get_cached", Mock())
    monkeypatch.setattr(
        manager, "load_maaend_controller_protocol", lambda *args: "Win32"
    )
    monkeypatch.setattr(manager, "push_dispatch_log", AsyncMock())
    monkeypatch.setattr(manager.Publisher, "send", AsyncMock())
    return instance


@pytest.mark.asyncio
async def test_preparation_failure_preserves_native_update_configuration(
    scheduler, installation, monkeypatch
):
    root, _ = installation
    monkeypatch.setattr(
        update, "update_before_run", AsyncMock(side_effect=TimeoutError())
    )
    await scheduler._prepare_program_update(root)
    manager.Publisher.send.assert_awaited_once()
    assert scheduler._program_update_prepared
    assert (
        json.loads((root / "interface.json").read_bytes())["mirrorchyan_rid"]
        == "MaaEnd"
    )
    assert not (script_install.workspace(root) / "runtime-interface.json").exists()


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
    assert not scheduler._program_update_prepared
    manager.Publisher.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_pending_install_cannot_be_accepted_as_safe_fallback(installation):
    root, _ = installation
    directory = script_install.workspace(root)
    directory.mkdir()
    (directory / "transaction.json").write_text("invalid")
    with pytest.raises(script_install.InstallUnsafeError):
        await update.confirm_current_install(root)


@pytest.mark.asyncio
async def test_native_update_does_not_block_non_takeover_configuration(installation):
    root, config = installation
    await update.update_before_run(root, config)
    (root / "interface.json").write_text(
        json.dumps({"name": "MaaEnd", "version": "v2.3.0", "mirrorchyan_rid": "MaaEnd"})
    )
    with pytest.raises(script_install.InstallUnsafeError, match="校验记录"):
        await update.confirm_current_install(root)
    await update.confirm_current_install(root, verify_receipt=False)


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
    await config.activate()
    script_id = config.uid
    task = SimpleNamespace(mode="AutoProxy", task_id="test")
    info = SimpleNamespace(
        task_info=task, script_id=str(script_id), user_list=[], status="等待", log=""
    )
    instance = manager.MaaEndManager(info)
    instance.check = AsyncMock(return_value="unsupported controller")
    lock, unlock = AsyncMock(return_value="ticket"), AsyncMock()
    monkeypatch.setattr(MaaEndConfig, "try_lock_x", lock)
    monkeypatch.setattr(MaaEndConfig, "unlock", unlock)
    monkeypatch.setattr(manager.Config, "ScriptConfig", {script_id: config})
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
    assert not (script_install.workspace(root) / "runtime-interface.json").exists()
    assert (
        json.loads((root / "interface.json").read_bytes())["mirrorchyan_rid"]
        == "MaaEnd"
    )
    await instance.final_task()
    assert (root / "interface.json").read_bytes() == original
    unlock.assert_awaited_once_with("ticket")
    with script_install.installation_access(root):
        pass


@pytest.mark.asyncio
async def test_install_failure_retries_do_not_accumulate_packages(
    installation, monkeypatch
):
    root, config = installation
    monkeypatch.setattr(
        script_install, "verify_archive", Mock(side_effect=OSError("磁盘空间不足"))
    )
    cache = root.parent / "data/maaend_update"
    for _ in range(2):
        with pytest.raises(OSError, match="磁盘空间不足"):
            await update.update_before_run(root, config)
        assert not list(cache.glob("download-*"))
        assert update.read_install(root)[0] == Version("2.1.0")


@pytest.mark.asyncio
async def test_identity_write_failure_cleans_download_but_keeps_installed_receipt(
    installation, monkeypatch
):
    root, config = installation
    original_write = update._utils_io.write_file

    def fail_identity(path, value):
        if path.name == "program-identity.json":
            raise OSError("身份记录写入失败")
        return original_write(path, value)

    monkeypatch.setattr(update._utils_io, "write_file", fail_identity)
    with pytest.raises(OSError, match="身份记录写入失败"):
        await update.update_before_run(root, config)
    assert update.read_install(root)[0] == Version("2.2.0")
    assert (script_install.workspace(root) / "installed.json").exists()
    assert not list((root.parent / "data/maaend_update").glob("download-*"))


@pytest.mark.asyncio
async def test_cancel_install_waits_for_worker_before_deleting_archive(
    installation, monkeypatch
):
    root, config = installation
    started = threading.Event()
    finished = threading.Event()

    def blocking_install(
        _root,
        archive,
        _size,
        _digest,
        _protected,
        _validate,
        _idle,
        cancelled,
        *,
        prepare_ready=None,
    ):
        assert prepare_ready is update.refresh_merged_pipelines
        started.set()
        assert cancelled.wait(3)
        assert archive.is_file()
        finished.set()

    monkeypatch.setattr(script_install, "install_package", blocking_install)
    task = asyncio.create_task(update.update_before_run(root, config))
    assert await asyncio.to_thread(started.wait, 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)
    assert finished.is_set()
    assert not list((root.parent / "data/maaend_update").glob("download-*"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_type", [FluxdownCancelUnconfirmed, FluxdownResumableError]
)
async def test_unconfirmed_downloader_keeps_its_private_destination(
    installation, monkeypatch, error_type
):
    root, config = installation

    async def interrupted_download(_url, destination, **_kwargs):
        destination.write_bytes(b"partial download")
        raise error_type("下载器未确认停止")

    monkeypatch.setattr(
        update, "download_file", AsyncMock(side_effect=interrupted_download)
    )
    with pytest.raises(error_type):
        await update.update_before_run(root, config)
    downloads = list((root.parent / "data/maaend_update").glob("download-*"))
    assert len(downloads) == 1
    assert next(downloads[0].iterdir()).read_bytes() == b"partial download"
    assert update.read_install(root)[0] == Version("2.1.0")


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["GitHub", "MirrorChyan"])
async def test_cancel_builtin_download_cleans_partial_zip(
    installation, monkeypatch, source
):
    root, config = installation
    if source == "MirrorChyan":
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
    else:
        update.Config.setting.Update.FluxdownTakeoverAll = False

    started, stopped = asyncio.Event(), asyncio.Event()

    async def partial_download(_url, destination, **_kwargs):
        destination.write_bytes(b"partial ZIP")
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr(
        update, "download_file", AsyncMock(side_effect=partial_download)
    )
    cache = root.parent / "data/maaend_update"
    for _ in range(2):
        started, stopped = asyncio.Event(), asyncio.Event()
        pending = asyncio.create_task(update.update_before_run(root, config))
        await asyncio.wait_for(started.wait(), timeout=5)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(pending, timeout=5)
        assert stopped.is_set()
        assert not list(cache.glob("download-*"))
        assert update.read_install(root)[0] == Version("2.1.0")


@pytest.mark.asyncio
async def test_cancel_fluxdown_download_preserves_unconfirmed_partial_zip(
    installation, monkeypatch
):
    root, config = installation
    started = asyncio.Event()

    async def partial_fluxdown_download(_url, destination, **_kwargs):
        destination.write_bytes(b"unconfirmed FluxDown part")
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(
        update, "download_file", AsyncMock(side_effect=partial_fluxdown_download)
    )
    pending = asyncio.create_task(update.update_before_run(root, config))
    await asyncio.wait_for(started.wait(), timeout=5)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(pending, timeout=5)
    downloads = list((root.parent / "data/maaend_update").glob("download-*"))
    assert len(downloads) == 1
    assert next(downloads[0].iterdir()).read_bytes() == b"unconfirmed FluxDown part"
    assert update.read_install(root)[0] == Version("2.1.0")


def _official_release_for_test(tmp_path: Path, tag: str) -> tuple[Path, dict]:
    archive = tmp_path / "official-native.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("MaaEnd.exe", pe())
        package.writestr(
            "interface.json",
            json.dumps({"name": "MaaEnd", "version": tag, "mirrorchyan_rid": "MaaEnd"}),
        )
        package.writestr("resource/data.json", '{"native": true}')
        package.writestr("agent/service.exe", b"native agent")
    release = {
        "tag_name": tag,
        "assets": [
            {
                "name": f"MaaEnd-win-x86_64-{tag}.zip",
                "size": archive.stat().st_size,
                "digest": "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest(),
            }
        ],
    }
    return archive, release


@pytest.mark.asyncio
async def test_native_beta_newer_than_stable_uses_exact_official_package(
    installation, tmp_path, monkeypatch
):
    root, config = installation
    await update.update_before_run(root, config)
    assert script_install.verify_installed_files(root, threading.Event())

    # MXU 在 MAS 两次运行之间独立升级，版本高于 MAS 当前选用的 stable。
    native_tag = "v2.3.0-beta.1"
    (root / "interface.json").write_text(
        json.dumps(
            {"name": "MaaEnd", "version": native_tag, "mirrorchyan_rid": "MaaEnd"}
        )
    )
    assert not script_install.verify_installed_files(root, threading.Event())
    archive, official = _official_release_for_test(tmp_path, native_tag)
    exact = AsyncMock(return_value=official)
    monkeypatch.setattr(update, "request_release_for_version", exact)

    async def download_native(_url, destination, **_kwargs):
        shutil.copyfile(archive, destination)

    downloader = AsyncMock(side_effect=download_native)
    monkeypatch.setattr(update, "download_file", downloader)
    mirror = AsyncMock()
    monkeypatch.setattr(update, "request_mirror_resource", mirror)
    config.Update.MirrorChyanCDK = "test-cdk"
    update.Config.setting.Update.MirrorChyanCDK = "global-cdk"

    result = await update.update_before_run(root, config)
    assert "已更新" in result
    assert update.read_install(root) == (Version(native_tag), "x86_64")
    assert script_install.verify_installed_files(root, threading.Event())
    exact.assert_awaited_once_with(Version(native_tag), native_tag)
    assert downloader.await_args.kwargs["source"] == "GitHub"
    assert downloader.await_args.args[0].endswith(
        f"/releases/download/{native_tag}/MaaEnd-win-x86_64-{native_tag}.zip"
    )
    mirror.assert_not_awaited()
    identity = json.loads(
        (script_install.workspace(root) / "program-identity.json").read_text()
    )
    assert identity == {"arch": "x86_64", "version": str(Version(native_tag))}
    assert (root / "config/mxu-MaaEnd.json").read_bytes() == b'{"user-data": true}'

    # 回执已经重新建立；再运行时不得重复下载安装，也不得回退 stable。
    assert "高于所选通道" in await update.update_before_run(root, config)
    assert downloader.await_count == 1
    exact.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "lookup_error",
    [ValueError("unknown official tag"), httpx.ConnectError("offline")],
)
async def test_native_upgrade_cannot_be_blindly_trusted_or_downgraded(
    scheduler, installation, monkeypatch, lookup_error
):
    root, config = installation
    await update.update_before_run(root, config)
    receipt = script_install.workspace(root) / "installed.json"
    original_receipt = receipt.read_bytes()
    (root / "interface.json").write_text(
        json.dumps({"name": "MaaEnd", "version": "v2.3.0"})
    )
    monkeypatch.setattr(
        update,
        "request_release_for_version",
        AsyncMock(side_effect=lookup_error),
    )
    update.download_file.reset_mock()

    # 下载/校验不可用时，不把旧版本收据当成新安装可信，也不回退旧版。
    with pytest.raises(script_install.InstallUnsafeError, match="不会自动降级"):
        await scheduler._prepare_program_update(root)
    assert not scheduler._program_update_prepared
    assert receipt.read_bytes() == original_receipt
    assert update.read_install(root)[0] == Version("2.3.0")
    update.download_file.assert_not_awaited()
    manager.Publisher.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_release_mismatch_cannot_repair_stale_native_receipt(
    installation, monkeypatch, tmp_path
):
    root, config = installation
    await update.update_before_run(root, config)
    (root / "interface.json").write_text(
        json.dumps({"name": "MaaEnd", "version": "v2.3.0"})
    )
    _, wrong = _official_release_for_test(tmp_path, "v2.4.0")
    monkeypatch.setattr(
        update, "request_release_for_version", AsyncMock(return_value=wrong)
    )
    update.download_file.reset_mock()
    with pytest.raises(script_install.InstallUnsafeError, match="官方完整包"):
        await update.update_before_run(root, config)
    assert update.read_install(root)[0] == Version("2.3.0")
    update.download_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_exact_release_lookup_checks_official_tag_and_draft(
    installation, monkeypatch
):
    original_client = httpx.AsyncClient
    observed = []
    release = {"tag_name": "v2.3.0-beta.1", "draft": False, "assets": []}

    def serve(request):
        observed.append(request.url.path)
        return httpx.Response(200, json=release)

    transport = httpx.MockTransport(serve)
    monkeypatch.setattr(
        update.httpx,
        "AsyncClient",
        lambda **_kwargs: original_client(transport=transport),
    )
    got = await update.request_release_for_version(Version("2.3.0b1"), "v2.3.0-beta.1")
    assert got == release
    assert observed == ["/repos/MaaEnd/MaaEnd/releases/tags/v2.3.0-beta.1"]

    release["tag_name"] = "v2.4.0"
    with pytest.raises(ValueError, match="不一致"):
        await update.request_release_for_version(Version("2.3.0b1"), "v2.3.0-beta.1")
    release["tag_name"] = "v2.3.0-beta.1"
    release["draft"] = True
    with pytest.raises(ValueError, match="公开发行"):
        await update.request_release_for_version(Version("2.3.0b1"), "v2.3.0-beta.1")
