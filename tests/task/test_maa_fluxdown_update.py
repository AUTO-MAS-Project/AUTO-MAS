"""MAA 启动前更新的隔离验证，不启动 MAA 或访问生产网络。"""

import asyncio
import json
import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from pydantic import ValidationError

from app.models.config import MaaConfig
from app.services.common.update import fluxdown as update_fluxdown
from app.services.common.update import transport as update_transport
from app.task.MAA import AutoProxy as auto_proxy
from app.task.MAA import manager
from app.task.MAA.AutoProxy import AutoProxyTask, _without_maa_update_changes
from app.task.MAA.tools import fluxdown_update as update
from app.task.MAA.tools import resource_update as resource
from app.task.MAA.tools import software_update as mirror

_request_release = update.request_maa_release


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
    assert downloader.call_args.kwargs["downloader"] == (
        "fluxdown" if fluxdown else "builtin"
    )
    assert update.read_pending_update(root) == ("v6.1.0", str((root / name).resolve()))
    progress.assert_awaited_once()


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


@pytest.mark.asyncio
async def test_resumable_retry_reuses_same_file(installation, monkeypatch):
    root, _, downloader = installation
    original = downloader.side_effect
    count = 0

    async def download(url, path, **kwargs):
        nonlocal count
        count += 1
        if count < 3:
            path.write_bytes(b"partial")
            raise update_fluxdown.FluxdownResumableError("offline")
        assert path.read_bytes() == b"partial"
        return await original(url, path, **kwargs)

    downloader.side_effect = download
    monkeypatch.setattr(update.asyncio, "sleep", AsyncMock())
    await update.prepare_maa_fluxdown_update(
        root, config=script_config(), config_dir=root / "config"
    )
    assert downloader.await_count == 3
    assert len({c.args[1] for c in downloader.call_args_list}) == 1


@pytest.mark.asyncio
async def test_release_metadata_uses_official_contract(installation, monkeypatch):
    _, _, _ = installation
    original_client = httpx.AsyncClient
    seen = []

    def response(request):
        seen.append(request.url)
        return httpx.Response(
            200, json={"version": "v6.1.0", "details": {"assets": []}}
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(response)),
    )
    assert (await _request_release("beta"))["version"] == "v6.1.0"
    assert str(seen[0]).endswith("/version/beta.json")


@pytest.mark.parametrize("channel", ["stable", "beta"])
def test_script_channel_schema_round_trip(channel):
    config = MaaConfig.model_validate({"Update": {"Channel": channel}})
    assert config.Update.Channel == channel
    assert MaaConfig.model_validate(config.model_dump()).Update.Channel == channel


def test_nightly_is_not_an_exposed_channel():
    with pytest.raises(ValidationError):
        MaaConfig.model_validate({"Update": {"Channel": "alpha"}})


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
    monkeypatch.setattr(resource, "download_file", downloader)
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
    assert downloader.call_args.kwargs["downloader"] == (
        "fluxdown" if fluxdown else "builtin"
    )
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
async def test_manager_installs_software_before_resources(installation, monkeypatch):
    root, _, _ = installation
    instance = object.__new__(manager.MaaManager)
    instance.script_config = script_config()
    instance.script_info = SimpleNamespace(log="", script_id="test-script")
    instance.maa_set_path = root / "config"
    instance.temp_path = root / "Temp"
    instance._updater_running = False
    steps = []
    monkeypatch.setattr(manager, "read_pending_update", lambda root: ("", ""))
    monkeypatch.setattr(
        manager, "read_installed_release", lambda root: ("v6.1.0", "x64")
    )
    monkeypatch.setattr(manager, "has_delegated_update_failure", lambda root: False)

    async def prepare(*args, **kwargs):
        steps.append("download")
        return "v6.1.0"

    async def install(*args, **kwargs):
        steps.append("install")

    async def resources(*args, **kwargs):
        steps.append("resources")

    monkeypatch.setattr(manager, "prepare_maa_fluxdown_update", prepare)
    monkeypatch.setattr(manager, "update_maa", install)
    monkeypatch.setattr(manager, "prepare_install_resources", resources)
    assert await instance._prepare_updates_once(
        SimpleNamespace(update_config_dir=root / "config")
    )
    assert steps == ["download", "install", "resources"]


@pytest.mark.asyncio
async def test_unconfirmed_installation_never_updates_resources(
    installation, monkeypatch
):
    root, _, _ = installation
    instance = object.__new__(manager.MaaManager)
    instance.script_config = script_config()
    instance.script_info = SimpleNamespace(log="", script_id="test-script")
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
@pytest.mark.parametrize(
    "changed, succeeds", [(False, True), (True, True), (True, False)]
)
async def test_final_gate_requeries_and_repeats_when_upstream_changes(
    installation, monkeypatch, changed, succeeds
):
    root, _, _ = installation
    instance = object.__new__(manager.MaaManager)
    instance.script_config = script_config(channel="beta")
    instance.script_info = SimpleNamespace(log="")
    instance.maa_set_path = root / "config"
    prepared = AsyncMock(return_value=True)
    monkeypatch.setattr(instance, "_prepare_updates_once", prepared)
    clock = datetime(2026, 10, 28, tzinfo=timezone.utc)
    monkeypatch.setattr(manager, "read_resource_clock", lambda root: clock)
    monkeypatch.setattr(manager, "latest_resource_clock", AsyncMock(return_value=clock))
    versions = iter([("v6.0.0", "x64"), ("v6.1.0", "x64"), ("v6.1.0", "x64")])
    monkeypatch.setattr(manager, "read_installed_release", lambda root: next(versions))
    query = AsyncMock(
        side_effect=[
            "v6.1.0" if changed else "v6.0.0",
            "v6.1.0" if succeeds else "v6.2.0",
            "v6.3.0",
        ]
    )
    monkeypatch.setattr(manager, "query_latest_maa_version", query)
    if succeeds:
        assert await instance._prepare_software_update_strict(
            SimpleNamespace(update_config_dir=root / "config")
        )
        assert prepared.await_count == (2 if changed else 1)
    else:
        with pytest.raises(RuntimeError, match="版本持续变化"):
            await instance._prepare_software_update_strict(
                SimpleNamespace(update_config_dir=root / "config")
            )
        assert prepared.await_count == 3
    assert all(call.kwargs["github"] is True for call in query.call_args_list)
    assert all(call.args[1] == "beta" for call in query.call_args_list)


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
@pytest.mark.parametrize("channel", ["stable", "beta"])
async def test_existing_channel_is_migrated_once(tmp_path, monkeypatch, channel):
    from tests.config_support import activate_config

    config_root = tmp_path / "maa" / "config"
    config_root.mkdir(parents=True)
    (config_root / "gui.new.json").write_text(
        json.dumps({"Update": {"VersionType": channel.title()}}), encoding="utf-8"
    )
    config = MaaConfig.build(
        payload={
            "Info": {"Path": str(config_root.parent)},
            "Update": {"TakeoverEnabled": True, "TakeoverMigrationVersion": 1},
        }
    )
    await activate_config(config)
    assert config.Update.ChannelMigrationVersion == 0
    await mirror.migrate_maa_update_channel(config)
    assert config.Update.Channel == channel
    assert config.Update.ChannelMigrationVersion == 1
    # A later user choice is authoritative even if the native GUI still says Beta.
    await config.update(type(config).model_validate({"Update": {"Channel": "stable"}}))
    await mirror.migrate_maa_update_channel(config)
    assert config.Update.Channel == "stable"


@pytest.mark.asyncio
async def test_explicit_channel_does_not_trigger_migration(tmp_path):
    from tests.config_support import activate_config

    config = MaaConfig.build(payload={"Update": {"Channel": "beta"}})
    await activate_config(config)
    assert config.Update.ChannelMigrationVersion == 1
    await mirror.migrate_maa_update_channel(config)
    assert config.Update.Channel == "beta"


def test_global_cdk_keeps_mirror_priority(installation):
    from app.task.MAA.tools import update_credentials

    root, _, _ = installation
    update.Config.setting.Update.MirrorChyanCDK = "global-review-cdk"
    config = script_config()
    assert update_credentials.resolve_takeover_credentials(config) == (
        True,
        "global-review-cdk",
    )
    assert not update_credentials.use_maa_github_update(
        config, config_dirs=[root / "config"]
    )


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
            await resource.prepare_install_resources(install, cdk=None, github=True)
        assert lock.locked()  # The waiting caller cannot release another caller's lock.
        downloader.assert_not_awaited()
    finally:
        lock.release()


@pytest.mark.parametrize("limit", ["entries", "bytes"])
def test_resource_archive_limits_reject_before_extracting(tmp_path, monkeypatch, limit):
    from app.task.MAA.tools import resource_package

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
@pytest.mark.parametrize("failure", ["write", "unconfirmed", "cancel"])
async def test_resource_write_failure_cannot_be_ignored(
    resource_install, monkeypatch, failure
):
    from app.task.MAA.tools.update_errors import MaaUpdateUnsafeError

    install, _, _ = resource_install

    def apply(*args):
        if failure == "cancel":
            raise asyncio.CancelledError()
        if failure == "write":
            raise OSError("resource write failed")
        return False

    monkeypatch.setattr(resource, "_apply_stage", apply)
    expected = asyncio.CancelledError if failure == "cancel" else MaaUpdateUnsafeError
    with pytest.raises(expected):
        await resource.prepare_install_resources(install, cdk=None, github=True)
    assert not resource._prepare_install_lock.locked()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["partial", "after_version"])
async def test_interrupted_resource_merge_blocks_next_run_until_repaired(
    resource_install, monkeypatch, failure
):
    from app.task.MAA.tools import resource_package
    from app.task.MAA.tools.update_errors import MaaUpdateUnsafeError

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
        manager.System, "is_process_running", AsyncMock(return_value=False)
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
