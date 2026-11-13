"""MAA 启动前更新的隔离验证，不启动 MAA 或访问生产网络。"""

import asyncio
import hashlib
import json
import threading
import zipfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from maa_adapter.native.runtime_config import _without_maa_update_changes
from maa_adapter.tasks import auto_proxy, manager
from maa_adapter.tasks.auto_proxy import AutoProxyTask
from maa_adapter.updates import fluxdown as update
from maa_adapter.updates.resources import service as resource
from maa_adapter.updates.software import package as software_package
from maa_adapter.updates.software import service as mirror

from app.services.common.update import transport as update_transport
from tests.runtime_support import RuntimeStub as SimpleNamespace


def script_config(*, enabled=True, channel="stable", cdk=""):
    return SimpleNamespace(
        Update=SimpleNamespace(
            TakeoverEnabled=enabled, Channel=channel, MirrorChyanCDK=cdk
        )
    )


@pytest.fixture
def installation(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/gui.new.json").write_text('{"Update": {}}')
    monkeypatch.setattr(
        update.Config,
        "setting",
        SimpleNamespace(
            Update=SimpleNamespace(
                FluxdownTakeoverAll=True, ProxyAddress="", MirrorChyanCDK=""
            )
        ),
    )
    monkeypatch.setattr(
        update, "read_installed_release", lambda root: ("v6.0.0", "x64")
    )
    release = AsyncMock(return_value={"version": "v6.1.0", "details": {"assets": []}})
    monkeypatch.setattr(update, "request_maa_release", release)
    mirror_query = AsyncMock(return_value={"data": {"version_name": "v6.1.0"}})
    monkeypatch.setattr(update_transport, "request_mirror_resource", mirror_query)
    update._latest_versions.clear()

    async def download(url, path, **kwargs):
        path.write_bytes(b"opaque official package")
        if kwargs.get("progress"):
            await kwargs["progress"](23, 23, 23)
        return 23

    downloader = AsyncMock(side_effect=download)
    monkeypatch.setattr(update, "download_file", downloader)
    return tmp_path, release, downloader


@pytest.mark.asyncio
@pytest.mark.parametrize("fluxdown", [True, False])
@pytest.mark.parametrize("channel", ["stable", "beta"])
@pytest.mark.parametrize("ota", [True, False])
async def test_script_channel_and_global_downloader_are_independent(
    installation, fluxdown, channel, ota
):
    root, release, downloader = installation
    update.Config.setting.Update.FluxdownTakeoverAll = fluxdown
    name = (
        "MAAComponent-OTA-v6.0.0_v6.1.0-win-x64.zip"
        if ota
        else "MAA-v6.1.0-win-x64.zip"
    )
    release.return_value["details"]["assets"] = [{"name": name}]
    progress = AsyncMock()
    assert (
        await update.prepare_maa_fluxdown_update(
            root,
            config=script_config(channel=channel),
            config_dir=root / "config",
            progress=progress,
        )
        == "v6.1.0"
    )
    assert all(c.args == (channel,) for c in release.call_args_list)
    assert downloader.call_args.args[0].endswith("/v6.1.0/" + name)
    assert downloader.call_args.kwargs["source"] == "GitHub"
    assert downloader.call_args.kwargs["proxy"] is update.Config.proxy
    assert update.read_pending_update(root) == ("v6.1.0", str((root / name).resolve()))
    progress.assert_awaited_once()


@pytest.mark.asyncio
async def test_prefetch_is_outside_install_and_registers_only_when_consumed(
    installation, monkeypatch
):
    root, _, downloader = installation
    monkeypatch.chdir(root.parent)
    config = script_config(channel="stable")
    candidate = await update.prepare_maa_fluxdown_update(
        root, config=config, config_dir=root / "config", download_only=True
    )
    assert isinstance(candidate, update.PreparedUpdate)
    assert not candidate.package.is_relative_to(root)
    assert update.read_pending_update(root) == ("", "")
    assert (
        await update.prepare_maa_fluxdown_update(
            root, config=config, config_dir=root / "config", prepared=candidate
        )
        == "v6.1.0"
    )
    downloader.assert_awaited_once()
    version, package = update.read_pending_update(root)
    assert version == "v6.1.0"
    assert update.Path(package).is_relative_to(root)
    update.discard_prepared_update(candidate)
    assert update.Path(package).is_file()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["changed-source", "interrupted-copy"])
async def test_prefetched_package_handoff_preserves_verified_destination(
    installation, monkeypatch, failure
):
    root, _, _ = installation
    monkeypatch.chdir(root.parent)
    config = script_config()
    candidate = await update.prepare_maa_fluxdown_update(
        root, config=config, config_dir=root / "config", download_only=True
    )
    destination = root / candidate.package.name
    destination.write_bytes(b"previous archive")
    copy = update.shutil.copyfile

    def changed_copy(source, target):
        if source == candidate.package:
            if failure == "interrupted-copy":
                update.Path(target).write_bytes(b"partial copy")
                raise OSError("copy interrupted")
            candidate.package.write_bytes(b"changed after verification")
        return copy(source, target)

    monkeypatch.setattr(update.shutil, "copyfile", changed_copy)
    try:
        with pytest.raises(RuntimeError):
            await update.prepare_maa_fluxdown_update(
                root, config=config, config_dir=root / "config", prepared=candidate
            )
        assert update.read_pending_update(root) == ("", "")
        assert destination.read_bytes() == b"previous archive"
        assert not list(root.glob("*.tmp"))
    finally:
        update.discard_prepared_update(candidate)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["pending", "failure"])
async def test_prefetched_maa_package_preserves_new_native_update_state(
    installation, monkeypatch, change
):
    root, _, _ = installation
    monkeypatch.chdir(root.parent)
    config = script_config()
    candidate = await update.prepare_maa_fluxdown_update(
        root, config=config, config_dir=root / "config", download_only=True
    )
    native = root / "native-update.zip"
    if change == "pending":
        native.write_bytes(b"native update")
        update.write_pending_update(root, version="v6.2.0", package=str(native))
    else:
        (root / "pending-update-failure.txt").write_text("native install failed")
    before = update.read_pending_update(root)
    try:
        with pytest.raises(RuntimeError):
            await update.prepare_maa_fluxdown_update(
                root, config=config, config_dir=root / "config", prepared=candidate
            )
        assert update.read_pending_update(root) == before
        assert not (root / candidate.package.name).exists()
        if change == "pending":
            assert native.read_bytes() == b"native update"
    finally:
        update.discard_prepared_update(candidate)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change,same_name", [("pending", False), ("pending", True), ("failure", False)]
)
@pytest.mark.parametrize("prefetched", [False, True])
async def test_maa_package_handoff_preserves_native_state_created_during_io(
    installation, monkeypatch, change, same_name, prefetched
):
    root, _, downloader = installation
    monkeypatch.chdir(root.parent)
    config = script_config()
    candidate = (
        await update.prepare_maa_fluxdown_update(
            root, config=config, config_dir=root / "config", download_only=True
        )
        if prefetched
        else None
    )
    native = root / ("MAA-v6.1.0-win-x64.zip" if same_name else "native-update.zip")
    native_version = "v6.1.0" if same_name else "v6.2.0"

    def native_update_finished():
        if change == "pending":
            native.write_bytes(b"native update")
            update.write_pending_update(
                root, version=native_version, package=str(native)
            )
        else:
            (root / "pending-update-failure.txt").write_text("native install failed")

    if prefetched:
        copy = update.shutil.copyfile

        def changed_copy(source, target):
            result = copy(source, target)
            native_update_finished()
            return result

        monkeypatch.setattr(update.shutil, "copyfile", changed_copy)
    else:
        download = downloader.side_effect

        async def changed_download(*args, **kwargs):
            result = await download(*args, **kwargs)
            native_update_finished()
            return result

        downloader.side_effect = changed_download
    try:
        with pytest.raises(RuntimeError):
            await update.prepare_maa_fluxdown_update(
                root, config=config, config_dir=root / "config", prepared=candidate
            )
        if change == "pending":
            assert update.read_pending_update(root) == (native_version, str(native))
            assert native.read_bytes() == b"native update"
        else:
            assert update.read_pending_update(root) == ("", "")
            assert update.has_delegated_update_failure(root)
    finally:
        if candidate is not None:
            update.discard_prepared_update(candidate)


@pytest.mark.asyncio
async def test_prefetched_maa_package_rechecks_source_after_copy(
    installation, monkeypatch
):
    root, _, _ = installation
    monkeypatch.chdir(root.parent)
    config = script_config()
    candidate = await update.prepare_maa_fluxdown_update(
        root, config=config, config_dir=root / "config", download_only=True
    )
    destination = root / candidate.package.name
    destination.write_bytes(b"native archive")
    copy = update.shutil.copyfile

    def changed_copy(source, target):
        copied = copy(source, target)
        update.Config.setting.Update.MirrorChyanCDK = "new-global-cdk"
        return copied

    monkeypatch.setattr(update.shutil, "copyfile", changed_copy)
    try:
        assert (
            await update.prepare_maa_fluxdown_update(
                root, config=config, config_dir=root / "config", prepared=candidate
            )
            is None
        )
        assert update.read_pending_update(root) == ("", "")
        assert destination.read_bytes() == b"native archive"
        assert not list(root.glob(".mas-update-*"))
    finally:
        update.discard_prepared_update(candidate)


@pytest.mark.asyncio
async def test_prefetched_maa_package_is_consumed_once_when_release_advances(
    installation, monkeypatch
):
    root, release, downloader = installation
    monkeypatch.chdir(root.parent)
    config = script_config()
    installed = "v6.0.0"
    monkeypatch.setattr(update, "read_installed_release", lambda _: (installed, "x64"))
    monkeypatch.setattr(manager, "read_installed_release", lambda _: (installed, "x64"))
    candidate = await update.prepare_maa_fluxdown_update(
        root, config=config, config_dir=root / "config", download_only=True
    )
    scheduler = object.__new__(manager.MaaManager)
    scheduler.script_config = config
    scheduler.script_info = SimpleNamespace(
        log="", info=SimpleNamespace(script_id="test-script")
    )
    scheduler.maa_set_path = root / "config"
    scheduler.temp_path = root / "Temp"
    scheduler._updater_running = False
    scheduler._github_update_candidate = candidate
    clock = datetime(2026, 10, 28, tzinfo=timezone.utc)
    monkeypatch.setattr(manager, "read_resource_clock", lambda _: clock)
    monkeypatch.setattr(manager, "latest_resource_clock", AsyncMock(return_value=clock))
    monkeypatch.setattr(manager, "prepare_install_resources", AsyncMock())

    async def install_pending(install, **_kwargs):
        nonlocal installed
        installed, archive = update.read_pending_update(install)
        update.Path(archive).unlink()
        update.write_pending_update(install, version="", package="")
        # 下载完成与安装后核对之间，上游又发布了一版。
        release.return_value["version"] = "v6.2.0"

    monkeypatch.setattr(manager, "update_maa", AsyncMock(side_effect=install_pending))
    try:
        assert await scheduler._prepare_software_update_strict(
            SimpleNamespace(update_config_dir=root / "config")
        )
        assert installed == "v6.2.0"
        assert downloader.await_count == 2
        assert not candidate.package.exists()
    finally:
        update.discard_prepared_update(candidate)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "asset",
    [
        "MAAComponent-OTA-v5.9.0_v6.1.0-win-x64.zip",
        "MAAComponent-OTA-v6.0.0_v6.1.0-win-arm64.zip",
        "MAAComponent-OTA-v6.0.0_v6.1.1-win-x64.zip",
        "../../injected.zip",
    ],
)
async def test_only_matching_ota_is_selected(installation, asset):
    root, release, downloader = installation
    release.return_value["details"]["assets"] = [{"name": asset}]
    await update.prepare_maa_fluxdown_update(
        root, config=script_config(), config_dir=root / "config"
    )
    assert downloader.call_args.args[0].endswith("/MAA-v6.1.0-win-x64.zip")


@pytest.mark.asyncio
async def test_script_switch_off_never_queries_or_downloads(installation):
    root, release, downloader = installation
    assert (
        await update.prepare_maa_fluxdown_update(
            root, config=script_config(enabled=False), config_dir=root / "config"
        )
        is None
    )
    release.assert_not_called()
    downloader.assert_not_called()


@pytest.mark.asyncio
async def test_already_latest_is_prepared_and_does_not_download(installation):
    root, release, downloader = installation
    release.return_value["version"] = "v6.0.0"
    assert (
        await update.prepare_maa_fluxdown_update(
            root, config=script_config(), config_dir=root / "config"
        )
        == "v6.0.0"
    )
    downloader.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("version", ["v5.9.0", "v6.1.0/../../escape", "nonsense"])
async def test_invalid_or_lower_channel_version_blocks_startup(installation, version):
    root, release, downloader = installation
    release.return_value["version"] = version
    with pytest.raises(RuntimeError):
        await update.prepare_maa_fluxdown_update(
            root, config=script_config(), config_dir=root / "config"
        )
    downloader.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("offline"),
        asyncio.CancelledError(),
        update._utils_fluxdown_cli.FluxdownCancelUnconfirmed("unknown"),
    ],
)
async def test_download_failure_never_registers_package(installation, error):
    root, _, downloader = installation

    async def fail(url, path, **kwargs):
        path.write_bytes(b"partial")
        raise error

    downloader.side_effect = fail
    with pytest.raises(type(error)):
        await update.prepare_maa_fluxdown_update(
            root, config=script_config(), config_dir=root / "config"
        )
    assert update.read_pending_update(root) == ("", "")
    assert list(root.glob("*.part"))


@pytest.mark.asyncio
async def test_changed_installation_cannot_receive_old_ota(installation, monkeypatch):
    root, release, downloader = installation
    release.return_value["details"]["assets"] = [
        {"name": "MAAComponent-OTA-v6.0.0_v6.1.0-win-x64.zip"}
    ]
    destination = root / "MAAComponent-OTA-v6.0.0_v6.1.0-win-x64.zip"
    destination.write_bytes(b"native archive")
    original = downloader.side_effect

    async def changed(url, path, **kwargs):
        result = await original(url, path, **kwargs)
        monkeypatch.setattr(
            update, "read_installed_release", lambda root: ("v6.0.1", "x64")
        )
        return result

    downloader.side_effect = changed
    with pytest.raises(RuntimeError, match="安装版本发生变化"):
        await update.prepare_maa_fluxdown_update(
            root, config=script_config(), config_dir=root / "config"
        )
    assert update.read_pending_update(root) == ("", "")
    assert destination.read_bytes() == b"native archive"


@pytest.fixture
def resource_install(installation, monkeypatch):
    root, _, _ = installation
    install = root / "maa"
    (install / "resource").mkdir(parents=True)
    (install / "resource/version.json").write_text(
        json.dumps({"last_updated": "2026-10-01 00:00:00.000"})
    )
    work = root / "cache"
    for name, value in {
        "_WORK_DIR": work,
        "_STAGE_DIR": work / "stage",
        "_STAGE_ZIP": work / "package.zip",
        "_MANIFEST_FILE": work / "manifest.json",
        "_STATE_FILE": work / "state.json",
        "_LOCK_FILE": root / "cache.lock",
    }.items():
        monkeypatch.setattr(resource, name, value)
    target = datetime(2026, 10, 28, tzinfo=timezone.utc)
    monkeypatch.setattr(
        resource, "latest_resource_clock", AsyncMock(return_value=target)
    )

    async def download(url, path, **kwargs):
        assert (
            url
            == "https://github.com/MaaAssistantArknights/MaaResource/archive/refs/heads/main.zip"
        )
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "MaaResource-main/resource/version.json",
                json.dumps({"last_updated": "2026-10-28 00:00:00.000"}),
            )
            archive.writestr(
                "MaaResource-main/resource/tasks/test.json", '{"opaque":"upstream"}'
            )
        return path.stat().st_size

    downloader = AsyncMock(side_effect=download)
    monkeypatch.setattr(resource, "download_script_package", downloader)
    return install, target, downloader


@pytest.mark.asyncio
@pytest.mark.parametrize("fluxdown", [True, False])
async def test_github_resources_are_installed_before_return(resource_install, fluxdown):
    install, target, downloader = resource_install
    update.Config.setting.Update.FluxdownTakeoverAll = fluxdown
    await resource.prepare_install_resources(install, cdk=None, github=True)
    assert not resource._STAGE_ZIP.exists()
    assert resource.read_resource_clock(install) == target
    assert (install / "resource/tasks/test.json").read_text() == '{"opaque":"upstream"}'
    assert downloader.call_args.kwargs["source"] == "GitHub"
    # A software reinstall can reset resources: the verified shared cache repairs them without another download.
    (install / "resource/version.json").write_text(
        '{"last_updated":"2026-10-01 00:00:00.000"}'
    )
    await resource.prepare_install_resources(install, cdk=None, github=True)
    assert resource.read_resource_clock(install) == target
    downloader.assert_awaited_once()


@pytest.mark.asyncio
async def test_corrupt_resource_download_blocks_launch(resource_install):
    install, _, downloader = resource_install

    async def corrupt(url, path, **kwargs):
        path.write_bytes(b"incomplete zip")

    downloader.side_effect = corrupt
    with pytest.raises(resource._DownloadError):
        await resource.prepare_install_resources(install, cdk=None, github=True)
    assert not resource._STAGE_ZIP.exists()
    assert resource.read_resource_clock(install).day == 1


@pytest.mark.asyncio
async def test_mirror_resource_budget_failure_blocks_launch(
    resource_install, monkeypatch
):
    install, _, downloader = resource_install
    refresh = AsyncMock(return_value=None)
    monkeypatch.setattr(resource, "_refresh_resource_stage", refresh)
    with pytest.raises(RuntimeError, match="资源包未准备完成"):
        await resource.prepare_install_resources(install, cdk="cdk", github=False)
    downloader.assert_not_called()
    refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_unconfirmed_installation_never_updates_resources(
    installation, monkeypatch
):
    root, _, _ = installation
    instance = object.__new__(manager.MaaManager)
    instance.script_config = script_config()
    instance.script_info = SimpleNamespace(
        log="", info=SimpleNamespace(script_id="test-script")
    )
    instance.maa_set_path = root / "config"
    instance.temp_path = root / "Temp"
    instance._updater_running = False
    monkeypatch.setattr(manager, "read_pending_update", lambda root: ("", ""))
    monkeypatch.setattr(
        manager, "read_installed_release", lambda root: ("v6.0.0", "x64")
    )
    monkeypatch.setattr(manager, "has_delegated_update_failure", lambda root: False)
    monkeypatch.setattr(
        manager, "prepare_maa_fluxdown_update", AsyncMock(return_value="v6.1.0")
    )
    monkeypatch.setattr(manager, "update_maa", AsyncMock())
    resources = AsyncMock()
    monkeypatch.setattr(manager, "prepare_install_resources", resources)
    with pytest.raises(RuntimeError, match="未确认 MAA 已完成更新"):
        await instance._prepare_updates_once(
            SimpleNamespace(update_config_dir=root / "config")
        )
    resources.assert_not_called()


@pytest.mark.asyncio
async def test_no_update_never_requests_paid_mirror_url(installation, monkeypatch):
    root, _, _ = installation
    query = AsyncMock(return_value="v6.0.0")
    monkeypatch.setattr(update, "query_latest_maa_version", query)
    monkeypatch.setattr(
        mirror, "read_installed_release", lambda root: ("v6.0.0", "x64")
    )
    paid = AsyncMock()
    monkeypatch.setattr(mirror, "_precheck_inner", paid)
    assert (
        await mirror.prepare_maa_software_before_run(
            root,
            config_dir=root / "config",
            config=script_config(cdk="cdk", channel="beta"),
        )
        == "v6.0.0"
    )
    query.assert_awaited_once_with("x64", "beta")
    paid.assert_not_called()


def test_runtime_disables_update_download_and_restores_source(
    installation, monkeypatch
):
    root, _, _ = installation
    instance = object.__new__(AutoProxyTask)
    instance.script_config = SimpleNamespace(
        Update=SimpleNamespace(TakeoverEnabled=True),
        Run=SimpleNamespace(TaskTransitionMethod="ExitEmulator"),
        Emulator=SimpleNamespace(Index=""),
    )
    instance.cur_user_config = SimpleNamespace(
        Info=SimpleNamespace(Server="Official", Id="")
    )
    adb = root / "adb.exe"
    adb.touch()
    instance.emulator_manager = SimpleNamespace(get_adb_path=lambda: adb)
    monkeypatch.setattr(instance, "_resolve_avd_device", lambda: None)
    monkeypatch.setattr(auto_proxy, "resolve_device_ref", lambda *args: None)
    update.Config.setting.Function = SimpleNamespace(IfSilence=False)
    instance.mode = "Routine"
    instance.maa_set_path = root / "config"
    # No emulator is bound; the runtime configuration still must suppress both update paths.
    gui = {
        "Current": "Default",
        "Configurations": {
            "Default": {
                "Gui": {
                    "RuntimeSettings": {},
                    "StartUpSettings": {},
                    "ConnectSettings": {},
                }
            }
        },
        "Update": {
            "UpdateSource": "MirrorChyan",
            "CheckOnStartup": True,
            "AutoDownloadUpdatePackage": True,
        },
    }
    baseline = json.loads(json.dumps(gui))
    instance._configure_maa_runtime(
        gui_new_set=gui,
        emulator_info=SimpleNamespace(adb_address="127.0.0.1:5555"),
    )
    assert gui["Update"]["CheckOnStartup"] is False
    assert gui["Update"]["CheckOnSchedule"] is False
    assert gui["Update"]["AutoDownloadUpdatePackage"] is False
    assert gui["Update"]["AutoInstallUpdatePackage"] is False
    assert gui["Update"]["UpdateSource"] == "GitHub"
    restored = _without_maa_update_changes(gui, baseline, "gui.new.json")
    assert restored["Update"] == baseline["Update"]


@pytest.mark.parametrize("prefix", ["resource/", "MaaResource-main/resource/"])
def test_mirror_resource_stage_accepts_official_and_legacy_layout(
    resource_install, prefix
):
    install, target, _ = resource_install
    resource._WORK_DIR.mkdir(parents=True)
    with zipfile.ZipFile(resource._STAGE_ZIP, "w") as archive:
        archive.writestr(
            prefix + "version.json", '{"last_updated":"2026-10-28 00:00:00.000"}'
        )
        archive.writestr(prefix + "tasks/test.json", '{"opaque":"upstream"}')
    resource._build_stage(resource._STAGE_ZIP, target)
    assert resource._apply_stage(install, target, "cdk") is True
    assert resource.read_resource_clock(install) == target


@pytest.mark.asyncio
async def test_native_only_cdk_cannot_fall_back_to_runtime_updates(
    installation, monkeypatch
):
    root, _, _ = installation
    (root / "config/gui.new.json").write_text(
        '{"Update":{"MirrorChyanCdk":"opaque-native-value"}}'
    )
    instance = object.__new__(manager.MaaManager)
    instance.script_config = script_config()
    instance.maa_set_path = root / "config"
    install = AsyncMock()
    monkeypatch.setattr(manager, "update_maa", install)
    with pytest.raises(RuntimeError, match="脚本的更新配置中填写 CDK"):
        await instance._prepare_updates_once(
            SimpleNamespace(update_config_dir=root / "config")
        )
    install.assert_not_awaited()


@pytest.mark.asyncio
async def test_resource_lock_contention_has_deadline(resource_install, monkeypatch):
    class BusyLock:
        contended = True

        def __enter__(self):
            return None

    install, _, downloader = resource_install
    monkeypatch.setattr(resource, "_MachineLock", BusyLock)
    monkeypatch.setattr(resource, "_RESOURCE_LOCK_TIMEOUT", 0)
    progress = AsyncMock()
    with pytest.raises(RuntimeError, match="资源锁超时"):
        await resource.prepare_install_resources(
            install, cdk=None, github=True, progress=progress
        )
    progress.assert_awaited()
    downloader.assert_not_awaited()
    assert not resource._prepare_install_lock.locked()


@pytest.mark.asyncio
async def test_local_resource_lock_contention_has_deadline(
    resource_install, monkeypatch
):
    install, _, downloader = resource_install
    lock = asyncio.Lock()
    await lock.acquire()
    monkeypatch.setattr(resource, "_prepare_install_lock", lock)
    monkeypatch.setattr(resource, "_RESOURCE_LOCK_TIMEOUT", 0.001)
    try:
        with pytest.raises(RuntimeError, match="资源更新超时"):
            await asyncio.wait_for(
                resource.prepare_install_resources(install, cdk=None, github=True),
                timeout=1,
            )
        assert lock.locked()  # The waiting caller cannot release another caller's lock.
        downloader.assert_not_awaited()
    finally:
        lock.release()


@pytest.mark.parametrize("limit", ["entries", "bytes"])
def test_resource_archive_limits_reject_before_extracting(tmp_path, monkeypatch, limit):
    from maa_adapter.updates.resources import package as resource_package

    archive = tmp_path / "oversized.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("resource/version.json", "x" * 512)
        package.writestr("resource/tasks/test.json", "y" * 512)
    if limit == "entries":
        monkeypatch.setattr(resource_package, "_MAX_ARCHIVE_ENTRIES", 1)
    else:
        monkeypatch.setattr(resource_package, "_MAX_EXTRACTED_BYTES", 256)
    destination = tmp_path / "extracted"
    with pytest.raises(ValueError):
        resource_package.extract_zip(archive, destination)
    assert not list(destination.rglob("*.json"))


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["partial", "after_version"])
async def test_interrupted_resource_merge_blocks_next_run_until_repaired(
    resource_install, monkeypatch, failure
):
    from maa_adapter.updates.errors import MaaUpdateUnsafeError
    from maa_adapter.updates.resources import package as resource_package

    install, target, downloader = resource_install
    (install / "MAA.exe").touch()
    tasks = install / "resource/tasks"
    tasks.mkdir()
    (tasks / "a.json").write_text("old-a")
    (tasks / "b.json").write_text("old-b")
    download = downloader.side_effect

    async def package(url, path, **kwargs):
        await download(url, path, **kwargs)
        with zipfile.ZipFile(path, "a") as archive:
            archive.writestr("MaaResource-main/resource/tasks/a.json", "new-a")
            archive.writestr("MaaResource-main/resource/tasks/b.json", "new-b")

    downloader.side_effect = package
    copy = resource_package._copy_if_changed

    def interrupted(src, dst, **kwargs):
        if failure == "partial" and str(dst).endswith("b.json"):
            raise OSError("injected resource write failure")
        result = copy(src, dst, **kwargs)
        if failure == "after_version" and str(dst).endswith("version.json"):
            raise OSError("interrupted after version commit")
        return result

    monkeypatch.setattr(resource_package, "_copy_if_changed", interrupted)
    with pytest.raises(MaaUpdateUnsafeError):
        await resource.prepare_install_resources(install, cdk=None, github=True)
    assert resource.has_incomplete_resource_update(install)
    assert (tasks / "a.json").read_text() == "new-a"
    assert (tasks / "b.json").read_text() == (
        "old-b" if failure == "partial" else "new-b"
    )
    assert (resource.read_resource_clock(install) == target) is (
        failure == "after_version"
    )

    scheduler = object.__new__(manager.MaaManager)
    scheduler.script_config = script_config()
    scheduler.script_info = SimpleNamespace(log="")
    scheduler.task_info = SimpleNamespace(task_id="test-task")
    scheduler.maa_set_path = install / "config"
    scheduler._updater_running = False
    monkeypatch.setattr(
        scheduler, "_prepare_updates_once", AsyncMock(side_effect=TimeoutError())
    )
    monkeypatch.setattr(scheduler, "_remember_pending_update", Mock())
    monkeypatch.setattr(
        manager, "read_installed_release", lambda root: ("v6.0.0", "x64")
    )
    monkeypatch.setattr(manager, "has_delegated_update_failure", lambda root: False)
    monkeypatch.setattr(
        manager.process, "is_process_running", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(manager.Publisher, "send", AsyncMock())
    task = SimpleNamespace(update_config_dir=install / "config")
    # 上一轮旧时钟仍可读，或版本文件已写完，都不能在本轮断网后放行。
    with pytest.raises(MaaUpdateUnsafeError):
        await scheduler._prepare_software_update(task)
    scheduler._remember_pending_update.assert_not_called()
    scheduler.script_config.Update.TakeoverEnabled = False
    with pytest.raises(MaaUpdateUnsafeError):
        await scheduler._prepare_software_update(task)
    scheduler.script_config.Update.TakeoverEnabled = True

    monkeypatch.setattr(resource_package, "_copy_if_changed", copy)
    await resource.prepare_install_resources(install, cdk=None, github=True)
    assert not resource.has_incomplete_resource_update(install)
    assert (tasks / "a.json").read_text() == "new-a"
    assert (tasks / "b.json").read_text() == "new-b"
    assert resource.read_resource_clock(install) == target
    downloader.assert_awaited_once()
    # 已完整修复后，后续单纯断网可重新沿用当前安装。
    assert await scheduler._prepare_software_update(task) is False
    scheduler._remember_pending_update.assert_called_once()


@pytest.mark.asyncio
async def test_cancelled_mirror_prefetch_does_not_use_daily_attempt(
    tmp_path, monkeypatch
):
    """Explicit queue cancellation permits the same version later that day."""
    state = {}
    writes = []

    def load(_path):
        return dict(state)

    def save(_path, data):
        state.clear()
        state.update(data)
        writes.append(dict(data))

    monkeypatch.setattr(mirror, "_STATE_FILE", tmp_path / "mirror-state.json")
    monkeypatch.setattr(mirror, "_state_lock", asyncio.Lock())
    monkeypatch.setattr(mirror, "load_state", load)
    monkeypatch.setattr(mirror._utils_io, "write_file", save)
    monkeypatch.setattr(mirror, "read_installed_release", lambda _: ("v6.0.0", "x64"))
    monkeypatch.setattr(mirror, "software_cache_dir", lambda **_: tmp_path)
    monkeypatch.setattr(mirror, "load_cache_manifest", lambda _: None)
    monkeypatch.setattr(mirror, "backoff_active", lambda *_: False)
    monkeypatch.setattr(mirror, "attempted_today", lambda *_: False)
    monkeypatch.setattr(
        mirror,
        "_fetch_latest",
        AsyncMock(return_value=mirror._Latest("v6.1.0", "https://example.invalid/pkg")),
    )
    cancelled = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(mirror, "_ensure_cache", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await mirror._precheck_inner(
            tmp_path,
            "stable",
            "x64",
            "test-cdk",
            target_version="v6.1.0",
            refund_cancelled=True,
        )
    assert not any(k.startswith("last_download_attempt_") for k in state)
    assert writes


@pytest.mark.asyncio
async def test_cancelled_mirror_prefetch_keeps_cache_lock_until_hash_closes(
    installation, monkeypatch
):
    root, _, _ = installation
    cache = root / "cache"
    cache.mkdir()
    package = cache / "package.zip"
    package.write_bytes(b"verified cached archive")
    (cache / "manifest.json").write_text(
        json.dumps(
            {
                "version": "v6.1.0",
                "channel": "stable",
                "os": "win",
                "arch": "x64",
                "package_type": "full",
                "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
            }
        )
    )
    monkeypatch.setattr(mirror, "software_cache_dir", lambda **_: cache)
    monkeypatch.setattr(mirror, "read_installed_release", lambda _: ("v6.0.0", "x64"))
    monkeypatch.setattr(mirror, "_cache_locks", {})
    hashing, resume = threading.Event(), threading.Event()
    checksum = software_package._file_sha256

    def slow_checksum(path):
        with path.open("rb"):
            hashing.set()
            assert resume.wait(5)
            return checksum(path)

    monkeypatch.setattr(software_package, "_file_sha256", slow_checksum)
    pending = asyncio.create_task(
        mirror.prefetch_maa_software_update(root, script_config(cdk="test-cdk"))
    )
    try:
        assert await asyncio.to_thread(hashing.wait, 3)
        pending.cancel()
        done, _ = await asyncio.wait({pending}, timeout=0.05)
        assert not done, "共享缓存仍有读句柄时不得释放锁"
        assert mirror._cache_locks["win/x64/stable"].locked()
        pending.cancel()
        done, _ = await asyncio.wait({pending}, timeout=0.05)
        assert not done
    finally:
        resume.set()
        await asyncio.gather(pending, return_exceptions=True)
    assert pending.cancelled()
    assert not mirror._cache_locks["win/x64/stable"].locked()


@pytest.mark.asyncio
async def test_cancelled_resource_prefetch_can_retry_mirror_on_same_day(
    resource_install, monkeypatch
):
    install, target, github_download = resource_install
    request = AsyncMock(return_value=("https://example.invalid/resource", target))
    monkeypatch.setattr(resource, "_request_resource_package", request)
    started = asyncio.Event()

    async def download(_url, path, **kwargs):
        if not started.is_set():
            started.set()
            path.write_bytes(b"partial archive")
            await asyncio.Event().wait()
        return await github_download(
            "https://github.com/MaaAssistantArknights/MaaResource/archive/refs/heads/main.zip",
            path,
            **kwargs,
        )

    monkeypatch.setattr(resource, "download_file", AsyncMock(side_effect=download))
    pending = asyncio.create_task(
        resource.prefetch_resources(install, github=False, cdk="test-cdk")
    )
    await asyncio.wait_for(started.wait(), timeout=3)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending

    await resource.prefetch_resources(install, github=False, cdk="test-cdk")
    assert request.await_count == 2
    assert resource.read_resource_clock(resource._STAGE_DIR) == target
    assert resource.read_resource_clock(install) < target


@pytest.mark.asyncio
async def test_resource_prefetch_cancel_waits_for_cache_invalidation(
    resource_install, monkeypatch
):
    install, target, downloader = resource_install
    await resource.prefetch_resources(install, github=True, cdk=None)
    (resource._STAGE_DIR / "resource/tasks/test.json").write_text("changed")
    hashing, resume = threading.Event(), threading.Event()
    tree_hashes = resource.resource_tree_hashes
    paused = False

    def slow_hash(path):
        nonlocal paused
        hashes = tree_hashes(path)
        if not paused:
            paused = True
            hashing.set()
            assert resume.wait(5)
        return hashes

    monkeypatch.setattr(resource, "resource_tree_hashes", slow_hash)
    pending = asyncio.create_task(
        resource.prefetch_resources(install, github=True, cdk=None)
    )
    try:
        assert await asyncio.to_thread(hashing.wait, 3)
        pending.cancel()
        done, _ = await asyncio.wait({pending}, timeout=0.05)
        assert not done, "清单作废线程结束前不得释放资源缓存锁"
        assert resource._prepare_install_lock.locked()
        pending.cancel()
        done, _ = await asyncio.wait({pending}, timeout=0.05)
        assert not done
    finally:
        resume.set()
        await asyncio.gather(pending, return_exceptions=True)
    assert pending.cancelled()
    await resource.prefetch_resources(install, github=True, cdk=None)
    assert resource._MANIFEST_FILE.is_file()
    assert resource.read_resource_clock(resource._STAGE_DIR) == target
    assert downloader.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["offline", "cancelled", "writer-unknown", "resumable"]
)
@pytest.mark.parametrize("download_path", ["destination", "request"])
async def test_resource_prefetch_failed_download_cleanup(
    resource_install, monkeypatch, failure, download_path
):
    install, _, downloader = resource_install
    resource._WORK_DIR.mkdir(parents=True, exist_ok=True)
    unrelated = resource._WORK_DIR / "another-download.zip"
    unrelated.write_bytes(b"other task")
    outputs = []

    async def fail(_url, path, **_kwargs):
        output = (
            path.parent / ".mas-fluxdown-test.zip"
            if download_path == "request"
            else path
        )
        output.write_bytes(b"partial resource zip")
        outputs.append(output)
        if failure == "cancelled":
            raise asyncio.CancelledError
        if failure == "writer-unknown":
            raise update._utils_fluxdown_cli.FluxdownCancelUnconfirmed("busy")
        if failure == "resumable":
            raise update._service_update_fluxdown.FluxdownResumableError("resume")
        raise RuntimeError("offline")

    downloader.side_effect = fail
    with pytest.raises(
        asyncio.CancelledError
        if failure == "cancelled"
        else (
            update._utils_fluxdown_cli.FluxdownCancelUnconfirmed
            if failure == "writer-unknown"
            else (
                update._service_update_fluxdown.FluxdownResumableError
                if failure == "resumable"
                else RuntimeError
            )
        )
    ):
        await resource.prefetch_resources(install, github=True, cdk=None)
    assert outputs[0].exists() is (failure == "writer-unknown")
    assert unrelated.read_bytes() == b"other task"
    if failure != "writer-unknown":
        assert not list(resource._WORK_DIR.glob("prefetch-*"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["offline", "cancelled", "resumable", "writer-unknown"]
)
async def test_maa_software_prefetch_failed_directory_cleanup(
    installation, monkeypatch, failure
):
    root, _, downloader = installation
    monkeypatch.chdir(root)

    async def fail(_url, path, **_kwargs):
        path.write_bytes(b"partial software zip")
        if failure == "cancelled":
            raise asyncio.CancelledError
        if failure == "resumable":
            raise update._service_update_fluxdown.FluxdownResumableError("resume")
        if failure == "writer-unknown":
            raise update._utils_fluxdown_cli.FluxdownCancelUnconfirmed("busy")
        raise RuntimeError("offline")

    downloader.side_effect = fail
    expected = (
        asyncio.CancelledError
        if failure == "cancelled"
        else (
            update._service_update_fluxdown.FluxdownResumableError
            if failure == "resumable"
            else (
                update._utils_fluxdown_cli.FluxdownCancelUnconfirmed
                if failure == "writer-unknown"
                else RuntimeError
            )
        )
    )
    with pytest.raises(expected):
        await update.prepare_maa_fluxdown_update(
            root,
            config=script_config(),
            config_dir=root / "config",
            download_only=True,
        )
    directories = list((root / "data/maa_github_update").glob("download-*"))
    assert len(directories) == (1 if failure == "writer-unknown" else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["digest", "cleanup"])
async def test_prefetch_cancel_waits_for_file_worker_before_directory_release(
    installation, monkeypatch, operation
):
    root, _, downloader = installation
    monkeypatch.chdir(root)
    started, release, finished = (threading.Event() for _ in range(3))

    if operation == "digest":
        original = update._digest

        def digest(path):
            try:
                with path.open("rb"):
                    started.set()
                    assert release.wait(5)
                    return original(path)
            finally:
                finished.set()

        monkeypatch.setattr(update, "_digest", digest)
    else:
        original = update.shutil.rmtree

        def cleanup(path, *args, **kwargs):
            started.set()
            try:
                assert release.wait(5)
                return original(path, *args, **kwargs)
            finally:
                finished.set()

        async def cancelled_download(_url, path, **_kwargs):
            path.write_bytes(b"partial package")
            raise asyncio.CancelledError

        monkeypatch.setattr(update.shutil, "rmtree", cleanup)
        downloader.side_effect = cancelled_download

    task = asyncio.create_task(
        update.prepare_maa_fluxdown_update(
            root, config=script_config(), config_dir=root / "config", download_only=True
        )
    )
    try:
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=0.05)
        assert not done
        assert list((root / "data/maa_github_update").glob("download-*"))
        task.cancel()  # A repeated stop must also wait for the real file worker.
        done, _ = await asyncio.wait({task}, timeout=0.05)
        assert not done
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        assert await asyncio.to_thread(finished.wait, 3)
    assert task.cancelled()
    assert not list((root / "data/maa_github_update").glob("download-*"))


@pytest.mark.asyncio
async def test_resource_prefetch_cleans_archive_and_reuses_stage_on_consumption(
    resource_install,
):
    install, target, downloader = resource_install
    current = resource.read_resource_clock(install)
    await resource.prefetch_resources(install, github=True, cdk=None)
    assert resource.read_resource_clock(install) == current
    assert not list(resource._WORK_DIR.glob("prefetch-*"))
    assert resource.read_resource_clock(resource._STAGE_DIR) == target
    await resource.prepare_install_resources(install, github=True, cdk=None)
    assert resource.read_resource_clock(install) == target
    downloader.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("probe_result", [True, False, "error"])
async def test_cancelled_stop_probe_preserves_shared_resource_archive(
    resource_install, monkeypatch, probe_result
):
    from app.core.script_update import download_script_package
    from app.models.config.setting import GlobalConfig
    from app.services.common.update import fluxdown as transport
    from app.utils.common import fluxdown_cli as cli

    install, _, _ = resource_install
    resource._WORK_DIR.mkdir(parents=True)
    resource._STAGE_ZIP.write_bytes(b"previous daemon still owns this archive")
    update.Config.setting.Update = GlobalConfig.UpdateFields(FluxdownTakeoverAll=False)
    monkeypatch.setattr(resource, "download_script_package", download_script_package)
    exe = install.parent / "fluxdown.exe"
    monkeypatch.setattr(cli, "fluxdown_find_cli", lambda *_a, **_kw: exe)
    monkeypatch.setattr(cli, "_server_data_dir", lambda _: install.parent / "server")
    backend = AsyncMock(side_effect=AssertionError("must not start another writer"))
    monkeypatch.setattr(transport, "_httpx_download", backend)
    entered, release = threading.Event(), threading.Event()

    def probe(*_args, **_kwargs):
        entered.set()
        assert release.wait(5)
        if probe_result == "error":
            raise OSError("stop probe unavailable")
        return probe_result

    monkeypatch.setattr(cli, "fluxdown_server_task_safe_to_overwrite", probe)
    task = asyncio.create_task(
        resource.prepare_install_resources(install, github=True, cdk=None)
    )
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=0.05)
        assert not done
        assert resource._STAGE_ZIP.is_file()
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=0.05)
        assert not done
    finally:
        release.set()
    with pytest.raises(
        asyncio.CancelledError
        if probe_result is True
        else transport.FluxdownWriterUnconfirmed
    ):
        await asyncio.wait_for(task, 3)
    backend.assert_not_awaited()
    if probe_result is True:
        assert not resource._STAGE_ZIP.exists()
    else:
        assert (
            resource._STAGE_ZIP.read_bytes()
            == b"previous daemon still owns this archive"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stop_state", ["completed", "not-found", "paused", "unavailable"]
)
async def test_cancelled_fluxdown_resume_checks_current_writer_before_archive_cleanup(
    resource_install, monkeypatch, stop_state
):
    from app.core.script_update import download_script_package
    from app.models.config.setting import GlobalConfig
    from app.services.common.update import fluxdown as transport
    from app.utils.common import fluxdown_cli as cli

    install, _, _ = resource_install
    resource._WORK_DIR.mkdir(parents=True)
    archive = resource._STAGE_ZIP
    payload = b"same-source daemon still owns this archive"
    archive.write_bytes(payload)
    update.Config.setting.Update = GlobalConfig.UpdateFields(FluxdownTakeoverAll=True)
    monkeypatch.setattr(resource, "download_script_package", download_script_package)
    exe = install.parent / "fluxdown.exe"
    monkeypatch.setattr(cli, "fluxdown_find_cli", lambda *_a, **_kw: exe)
    monkeypatch.setattr(cli, "_server_data_dir", lambda _: install.parent / "server")
    monkeypatch.setattr(
        cli,
        "fluxdown_server_ensure",
        lambda _: SimpleNamespace(gateway_port=17800, token="test"),
    )
    url = "https://github.com/MaaAssistantArknights/MaaResource/archive/refs/heads/main.zip"
    key = cli._map_key(url, archive)
    cli._map_put(exe, key, "current-task", url, archive, None)
    original_load = cli._load_task_map
    first_probe, release_first = threading.Event(), threading.Event()
    current_probe, release_current = threading.Event(), threading.Event()

    def load_mapping(path):
        if not first_probe.is_set():
            first_probe.set()
            assert release_first.wait(5)
        return original_load(path)

    commands = []

    def command(_exe, _env, args, **_kwargs):
        commands.append(args)
        assert args in (["pause", "current-task"], ["status", "current-task", "--json"])
        current_probe.set()
        assert release_current.wait(5)
        if args[0] == "pause":
            if stop_state == "not-found":
                return 3, "task not found"
            return (
                (124, "pause unavailable")
                if stop_state == "unavailable"
                else (0, "cancel requested")
            )
        status = (
            cli._TASK_STATUS_DONE
            if stop_state == "completed"
            else cli._TASK_STATUS_PAUSED
        )
        return 0, json.dumps({"status": status})

    monkeypatch.setattr(cli, "_load_task_map", load_mapping)
    monkeypatch.setattr(cli, "_run_cli", command)
    backend = AsyncMock(side_effect=AssertionError("must not start a second writer"))
    monkeypatch.setattr(transport, "_httpx_download", backend)
    server_download, local_download = AsyncMock(), AsyncMock()
    monkeypatch.setattr(cli, "fluxdown_server_download", server_download)
    monkeypatch.setattr(cli, "fluxdown_download", local_download)
    task = asyncio.create_task(
        resource.prepare_install_resources(install, github=True, cdk=None)
    )
    try:
        assert await asyncio.to_thread(first_probe.wait, 3)
        task.cancel()
        release_first.set()
        assert await asyncio.to_thread(current_probe.wait, 3), (
            "cancellation must also probe the skipped current task"
        )
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=0.05)
        assert not done
        assert archive.read_bytes() == payload
    finally:
        release_first.set()
        release_current.set()
        await asyncio.gather(task, return_exceptions=True)
    if stop_state in {"completed", "not-found"}:
        assert task.cancelled()
        assert not archive.exists()
    else:
        assert isinstance(task.exception(), transport.FluxdownWriterUnconfirmed)
        assert archive.read_bytes() == payload
        assert archive.parent.is_dir()
    if stop_state == "paused":
        assert ["status", "current-task", "--json"] in commands
    assert original_load(exe)[key]["task_id"] == "current-task"
    assert ["pause", "current-task"] in commands
    backend.assert_not_awaited()
    server_download.assert_not_awaited()
    local_download.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stop_state", ["completed", "not-found", "paused", "unconfirmed", "unavailable"]
)
async def test_server_initialization_cancel_preserves_archive_until_writer_stops(
    resource_install, monkeypatch, stop_state
):
    from app.core.script_update import download_script_package
    from app.models.config.setting import GlobalConfig
    from app.services.common.update import fluxdown as transport
    from app.utils.common import fluxdown_cli as cli

    install, _, _ = resource_install
    resource._WORK_DIR.mkdir(parents=True)
    archive = resource._STAGE_ZIP
    payload = b"old daemon still owns this resource archive"
    archive.write_bytes(payload)
    update.Config.setting.Update = GlobalConfig.UpdateFields(FluxdownTakeoverAll=True)
    monkeypatch.setattr(resource, "download_script_package", download_script_package)
    exe = install.parent / "fluxdown.exe"
    monkeypatch.setattr(cli, "fluxdown_find_cli", lambda *_a, **_kw: exe)
    monkeypatch.setattr(cli, "_server_data_dir", lambda _: install.parent / "server")
    monkeypatch.setattr(cli, "fluxdown_server_available", lambda *_a, **_kw: True)
    monkeypatch.setattr(
        cli, "fluxdown_server_emergency_stop_if_exclusive", lambda *_: False
    )
    url = "https://github.com/MaaAssistantArknights/MaaResource/archive/refs/heads/main.zip"
    key = cli._map_key(url, archive)
    cli._map_put(exe, key, "old-task", url, archive, None)
    initializing, release_init = threading.Event(), threading.Event()
    checking, release_check = threading.Event(), threading.Event()

    def ensure(_exe):
        initializing.set()
        assert release_init.wait(5)
        return (
            None
            if stop_state == "unavailable"
            else SimpleNamespace(gateway_port=17800, token="test")
        )

    commands = []

    def command(_exe, _env, args, *_, **_kwargs):
        commands.append(args)
        assert args[0] in ("status", "pause")
        checking.set()
        assert release_check.wait(5)
        if args[0] == "pause":
            if stop_state == "not-found":
                return 3, "task not found"
            return (
                (0, "cancel requested")
                if stop_state in {"completed", "paused"}
                else (124, "pause unconfirmed")
            )
        status = (
            cli._TASK_STATUS_DONE
            if stop_state == "completed"
            else cli._TASK_STATUS_PAUSED
            if stop_state == "paused"
            else cli._TASK_STATUS_DOWNLOADING
        )
        return 0, json.dumps({"status": status})

    monkeypatch.setattr(cli, "fluxdown_server_ensure", ensure)
    monkeypatch.setattr(cli, "_run_cli", command)
    backend = AsyncMock(side_effect=AssertionError("must not start another writer"))
    local = AsyncMock(side_effect=AssertionError("must not start local fallback"))
    monkeypatch.setattr(transport, "_httpx_download", backend)
    monkeypatch.setattr(cli, "fluxdown_download", local)
    task = asyncio.create_task(
        resource.prepare_install_resources(install, github=True, cdk=None)
    )
    try:
        assert await asyncio.to_thread(initializing.wait, 3)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=0.05)
        assert not done, "initialization must finish before ownership cleanup"
        assert archive.read_bytes() == payload
        task.cancel()
        release_init.set()
        if stop_state != "unavailable":
            assert await asyncio.to_thread(checking.wait, 3)
            task.cancel()
            done, _ = await asyncio.wait({task}, timeout=0.05)
            assert not done, "repeated cancellation must await writer confirmation"
            assert archive.read_bytes() == payload
    finally:
        release_init.set()
        release_check.set()
        await asyncio.gather(task, return_exceptions=True)
    if stop_state in {"completed", "not-found"}:
        assert task.cancelled()
        assert not archive.exists()
        assert ["pause", "old-task"] in commands
    else:
        assert isinstance(task.exception(), cli.FluxdownCancelUnconfirmed)
        assert archive.read_bytes() == payload
        assert archive.parent.is_dir()
    if stop_state == "paused":
        assert ["pause", "old-task"] in commands
        assert ["status", "old-task", "--json"] in commands
    assert cli._load_task_map(exe)[key]["task_id"] == "old-task"
    backend.assert_not_awaited()
    local.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity",
    [
        "recovered-completed",
        "recovered-missing",
        "recovered-paused",
        "unavailable",
        "ambiguous",
        "empty",
    ],
)
async def test_cancelled_add_without_response_recovers_or_preserves_writer(
    resource_install, monkeypatch, identity
):
    from app.core.script_update import download_script_package
    from app.models.config.setting import GlobalConfig
    from app.services.common.update import fluxdown as transport
    from app.utils.common import fluxdown_cli as cli

    install, _, _ = resource_install
    update.Config.setting.Update = GlobalConfig.UpdateFields(FluxdownTakeoverAll=True)
    monkeypatch.setattr(resource, "download_script_package", download_script_package)
    exe = install.parent / "fluxdown.exe"
    monkeypatch.setattr(cli, "fluxdown_find_cli", lambda *_a, **_kw: exe)
    monkeypatch.setattr(cli, "_server_data_dir", lambda _: install.parent / "server")
    monkeypatch.setattr(cli, "fluxdown_server_available", lambda *_a, **_kw: True)
    monkeypatch.setattr(
        cli,
        "fluxdown_server_ensure",
        lambda _: SimpleNamespace(gateway_port=17800, token="test"),
    )
    monkeypatch.setattr(
        cli, "fluxdown_server_emergency_stop_if_exclusive", lambda *_: False
    )
    archive = resource._STAGE_ZIP
    payload = b"created by daemon before response was lost"
    url = "https://github.com/MaaAssistantArknights/MaaResource/archive/refs/heads/main.zip"
    accepted, release_add = threading.Event(), threading.Event()
    querying, release_query = threading.Event(), threading.Event()
    commands, paused = [], False
    request_path = None

    def command(_exe, _env, args, *_, **_kwargs):
        nonlocal paused, request_path
        commands.append(args)
        if args[0] == "add":
            request_path = (
                update.Path(args[args.index("-d") + 1]) / args[args.index("-o") + 1]
            )
            request_path.write_bytes(payload)
            accepted.set()
            assert release_add.wait(5)
            return 124, "request timed out without task ID"
        if args[0] == "list":
            if not accepted.is_set():
                return 0, "[]"
            querying.set()
            assert release_query.wait(5)
            if identity == "unavailable":
                return 124, "management unavailable"
            task = {
                "taskId": "accepted-task",
                "url": url,
                "saveDir": str(request_path.parent),
                "fileName": request_path.name,
            }
            tasks = (
                [task]
                if identity.startswith("recovered-")
                else [task, {**task, "taskId": "other-task"}]
            )
            if identity == "empty":
                tasks = []
            return 0, json.dumps(tasks)
        if args[0] == "pause":
            assert args[1] == "accepted-task"
            paused = True
            if identity == "recovered-missing":
                return 3, "task not found"
            return 0, "paused"
        if args[0] == "status":
            assert args[1] == "accepted-task"
            status = (
                cli._TASK_STATUS_DONE
                if identity == "recovered-completed"
                else cli._TASK_STATUS_PAUSED
                if paused
                else cli._TASK_STATUS_DOWNLOADING
            )
            return 0, json.dumps({"status": status})
        raise AssertionError(f"unexpected command {args}")

    monkeypatch.setattr(cli, "_run_cli", command)
    backend = AsyncMock(side_effect=AssertionError("must not start another writer"))
    local = AsyncMock(side_effect=AssertionError("must not start local fallback"))
    monkeypatch.setattr(transport, "_httpx_download", backend)
    monkeypatch.setattr(cli, "fluxdown_download", local)
    task = asyncio.create_task(
        resource.prepare_install_resources(install, github=True, cdk=None)
    )
    try:
        assert await asyncio.to_thread(accepted.wait, 3)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=0.05)
        assert not done
        assert request_path.read_bytes() == payload
        task.cancel()
        release_add.set()
        assert await asyncio.to_thread(querying.wait, 3), (
            "missing add response must trigger task identity recovery"
        )
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=0.05)
        assert not done
        assert request_path.read_bytes() == payload
    finally:
        release_add.set()
        release_query.set()
        await asyncio.gather(task, return_exceptions=True)
    key = cli._map_key(url, archive)
    entry = cli._load_task_map(exe)[key]
    assert not archive.exists()
    assert request_path.read_bytes() == payload
    assert entry["request_path"] == str(request_path)
    if identity.startswith("recovered-"):
        assert paused
        assert entry["task_id"] == "accepted-task"
        if identity == "recovered-paused":
            assert isinstance(task.exception(), cli.FluxdownCancelUnconfirmed)
            assert request_path.parent.is_dir()
            assert ["status", "accepted-task", "--json"] in commands
            assert not cli.fluxdown_server_task_safe_to_overwrite(exe, url, archive)
        else:
            assert task.cancelled()
    else:
        assert isinstance(task.exception(), cli.FluxdownCancelUnconfirmed)
        assert entry["pending_add"] is True
        with pytest.raises(cli.FluxdownCancelUnconfirmed):
            await cli.fluxdown_server_download(url, archive, cli_exe=exe)
        assert not cli.fluxdown_server_task_safe_to_overwrite(
            exe, url + "?other", archive
        )
        assert not cli.fluxdown_server_task_safe_to_overwrite(
            exe, url, archive, other_only=True
        )
    assert sum(args[0] == "add" for args in commands) == 1
    backend.assert_not_awaited()
    local.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancellation_before_resource_download_does_not_delete_previous_archive(
    resource_install,
):
    install, _, downloader = resource_install
    resource._WORK_DIR.mkdir(parents=True)
    resource._STAGE_ZIP.write_bytes(b"previous unconfirmed writer")
    reports = 0

    async def progress(_line):
        nonlocal reports
        reports += 1
        if reports == 2:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await resource.prepare_install_resources(
            install, github=True, cdk=None, progress=progress
        )
    assert resource._STAGE_ZIP.read_bytes() == b"previous unconfirmed writer"
    downloader.assert_not_awaited()
