"""本地隔离验证：不启动 MAA、游戏或生产网络。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.task.MAA import manager
from app.task.MAA.tools import fluxdown_update as update
from app.task.MAA.tools import software_update as mirror_update
from app.task.MAA.tools import update_credentials as credentials


@pytest.fixture
def installation(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "gui.new.json").write_text('{"Update": {}}', encoding="utf-8")
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
    monkeypatch.setattr(update, "resolve_update_channel", lambda version, dirs: "beta")
    update._latest_versions.clear()
    query = AsyncMock(return_value={"data": {"version_name": "v6.1.0-beta.2"}})

    async def download(url, path, **kwargs):
        path.write_bytes(b"opaque upstream package")
        if kwargs.get("progress"):
            await kwargs["progress"](23, 23, 23)
        return 23

    downloader = AsyncMock(side_effect=download)
    monkeypatch.setattr(update, "request_mirror_resource", query)
    monkeypatch.setattr(update, "download_file", downloader)
    return tmp_path, query, downloader


@pytest.mark.asyncio
async def test_download_handoff_and_progress(installation):
    root, query, downloader = installation
    progress = AsyncMock()
    target = await update.prepare_maa_fluxdown_update(
        root,
        config=SimpleNamespace(Update=SimpleNamespace(MirrorChyanCDK="")),
        config_dir=root / "config",
        progress=progress,
    )
    assert target == "v6.1.0-beta.2"
    assert query.call_args.kwargs["params"] == {
        "os": "win",
        "arch": "x64",
        "channel": "beta",
    }
    url, part = downloader.call_args.args
    assert url.endswith("/v6.1.0-beta.2/MAA-v6.1.0-beta.2-win-x64.zip")
    assert downloader.call_args.kwargs["downloader"] == "fluxdown"
    assert downloader.call_args.kwargs["source"] == "GitHub"
    assert not part.exists()
    version, package = update.read_pending_update(root)
    assert version == target
    assert (root / package).read_bytes() == b"opaque upstream package"
    progress.assert_awaited_once()


@pytest.mark.asyncio
async def test_disabled_does_not_query(installation):
    root, query, downloader = installation
    update.Config.setting.Update.FluxdownTakeoverAll = False
    assert (
        await update.prepare_maa_fluxdown_update(
            root,
            config=SimpleNamespace(Update=SimpleNamespace(MirrorChyanCDK="")),
            config_dir=root / "config",
        )
        is None
    )
    query.assert_not_called()
    downloader.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("remote", ["v6.0.0", "v5.9.0", "v6.0.0-beta.1"])
async def test_current_or_older_does_not_download(installation, remote):
    root, query, downloader = installation
    query.return_value = {"data": {"version_name": remote}}
    assert (
        await update.prepare_maa_fluxdown_update(
            root,
            config=SimpleNamespace(Update=SimpleNamespace(MirrorChyanCDK="")),
            config_dir=root / "config",
        )
        is None
    )
    downloader.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_or_path_version_rejected(installation):
    root, query, downloader = installation
    query.return_value = {"data": {"version_name": "v6.1.0/../../escape"}}
    assert (
        await update.prepare_maa_fluxdown_update(
            root,
            config=SimpleNamespace(Update=SimpleNamespace(MirrorChyanCDK="")),
            config_dir=root / "config",
        )
        is None
    )
    downloader.assert_not_called()


@pytest.mark.asyncio
async def test_pending_native_package_protected(installation):
    root, query, downloader = installation
    (root / "native.zip").write_bytes(b"native")
    update.write_pending_update(root, version="v6.0.1", package="native.zip")
    assert (
        await update.prepare_maa_fluxdown_update(
            root,
            config=SimpleNamespace(Update=SimpleNamespace(MirrorChyanCDK="")),
            config_dir=root / "config",
        )
        is None
    )
    assert update.read_pending_update(root) == ("v6.0.1", "native.zip")
    query.assert_not_called()
    downloader.assert_not_called()


@pytest.mark.asyncio
async def test_failure_preserves_part_without_registration(installation):
    root, _, downloader = installation

    async def fail(url, path, **kwargs):
        path.write_bytes(b"partial")
        raise RuntimeError("offline")

    downloader.side_effect = fail
    assert (
        await update.prepare_maa_fluxdown_update(
            root,
            config=SimpleNamespace(Update=SimpleNamespace(MirrorChyanCDK="")),
            config_dir=root / "config",
        )
        is None
    )
    assert list(root.glob("*.part"))[0].read_bytes() == b"partial"
    assert update.read_pending_update(root) == ("", "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        asyncio.CancelledError(),
        update._utils_fluxdown_cli.FluxdownCancelUnconfirmed("unknown"),
    ],
)
async def test_cancellation_never_launches_or_registers(installation, error):
    root, _, downloader = installation
    downloader.side_effect = error
    with pytest.raises(type(error)):
        await update.prepare_maa_fluxdown_update(
            root,
            config=SimpleNamespace(Update=SimpleNamespace(MirrorChyanCDK="")),
            config_dir=root / "config",
        )
    assert update.read_pending_update(root) == ("", "")


@pytest.mark.asyncio
async def test_resumable_retries_reuse_same_destination(installation, monkeypatch):
    root, _, downloader = installation
    original = downloader.side_effect
    count = 0

    async def retry(url, path, **kwargs):
        nonlocal count
        count += 1
        if count < 3:
            path.write_bytes(b"partial")
            raise update.FluxdownResumableError("offline")
        assert path.read_bytes() == b"partial"
        return await original(url, path, **kwargs)

    downloader.side_effect = retry
    monkeypatch.setattr(update.asyncio, "sleep", AsyncMock())
    assert (
        await update.prepare_maa_fluxdown_update(
            root,
            config=SimpleNamespace(Update=SimpleNamespace(MirrorChyanCDK="")),
            config_dir=root / "config",
        )
        == "v6.1.0-beta.2"
    )
    assert downloader.await_count == 3
    assert len({call.args[1] for call in downloader.call_args_list}) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("actual, ready", [("v6.1.0", True), ("v6.0.0", False)])
async def test_manager_waits_for_official_installer(
    tmp_path, monkeypatch, actual, ready
):
    monkeypatch.setattr(
        manager.Config,
        "setting",
        SimpleNamespace(
            Update=SimpleNamespace(FluxdownTakeoverAll=True, MirrorChyanCDK="")
        ),
    )
    monkeypatch.setattr(manager, "read_pending_update", lambda root: ("", ""))
    instance = object.__new__(manager.MaaManager)
    instance.maa_set_path = tmp_path / "config"
    instance.script_config = SimpleNamespace(Update=SimpleNamespace(MirrorChyanCDK=""))
    instance.script_info = SimpleNamespace(log="")
    instance._updater_running = False
    task = SimpleNamespace(update_config_dir=tmp_path / "config")
    prepared = AsyncMock(return_value="v6.1.0")
    installed = False

    async def install(root):
        nonlocal installed
        assert prepared.await_count == 1
        installed = True

    def read(root):
        assert installed
        return actual, "x64"

    monkeypatch.setattr(manager, "prepare_maa_fluxdown_update", prepared)
    monkeypatch.setattr(manager, "update_maa", install)
    monkeypatch.setattr(manager, "read_installed_release", read)
    monkeypatch.setattr(manager, "has_delegated_update_failure", lambda root: False)
    if ready:
        assert await instance._prepare_software_update(task) is True
    else:
        with pytest.raises(RuntimeError, match="未确认 MAA 已完成更新"):
            await instance._prepare_software_update(task)


@pytest.mark.asyncio
async def test_manager_consumes_interrupted_pending_before_query(tmp_path, monkeypatch):
    monkeypatch.setattr(
        manager.Config,
        "setting",
        SimpleNamespace(
            Update=SimpleNamespace(FluxdownTakeoverAll=True, MirrorChyanCDK="")
        ),
    )
    (tmp_path / "pending.zip").write_bytes(b"pending")
    monkeypatch.setattr(
        manager, "read_pending_update", lambda root: ("v6.1.0", "pending.zip")
    )
    instance = object.__new__(manager.MaaManager)
    instance.maa_set_path = tmp_path / "config"
    instance.script_config = SimpleNamespace(Update=SimpleNamespace(MirrorChyanCDK=""))
    instance.script_info = SimpleNamespace(log="")
    instance._updater_running = False
    steps = []

    async def install(root):
        steps.append("install")

    async def query(*args, **kwargs):
        steps.append("query")
        return None

    monkeypatch.setattr(manager, "update_maa", install)
    monkeypatch.setattr(
        manager, "read_installed_release", lambda root: ("v6.1.0", "x64")
    )
    monkeypatch.setattr(manager, "has_delegated_update_failure", lambda root: False)
    monkeypatch.setattr(manager, "prepare_maa_fluxdown_update", query)
    assert (
        await instance._prepare_software_update(
            SimpleNamespace(update_config_dir=tmp_path)
        )
        is False
    )
    assert steps == ["install", "query"]


@pytest.mark.asyncio
async def test_upstream_install_failure_blocks_account_task(tmp_path, monkeypatch):
    instance = object.__new__(manager.MaaManager)
    instance.maa_set_path = tmp_path / "config"
    instance.script_config = SimpleNamespace(Update=SimpleNamespace(MirrorChyanCDK=""))
    instance.script_info = SimpleNamespace(log="")
    monkeypatch.setattr(manager, "update_maa", AsyncMock())
    monkeypatch.setattr(manager, "has_delegated_update_failure", lambda root: True)
    with pytest.raises(RuntimeError, match="官方更新器报告安装失败"):
        await instance._install_pending_software_update()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "location", ["script", "global", "native", "legacy", "corrupt"]
)
async def test_configured_cdk_always_bypasses_fluxdown(installation, location):
    root, query, downloader = installation
    config = SimpleNamespace(
        Update=SimpleNamespace(MirrorChyanCDK="", TakeoverEnabled=False)
    )
    if location == "script":
        config.Update.MirrorChyanCDK = "script-cdk"
    elif location == "global":
        update.Config.setting.Update.MirrorChyanCDK = "global-cdk"
    elif location == "native":
        (root / "config/gui.new.json").write_text(
            '{"Update":{"MirrorChyanCdk":"opaque-encrypted-value"}}', encoding="utf-8"
        )
    elif location == "legacy":
        (root / "config/gui.json").write_text(
            '{"Global":{"VersionUpdate.ResourceUpdateSource.MirrorChyanCdk":"opaque-encrypted-value"}}',
            encoding="utf-8",
        )
    else:
        (root / "config/gui.new.json").write_text("{broken", encoding="utf-8")
    assert (
        await update.prepare_maa_fluxdown_update(
            root, config=config, config_dir=root / "config"
        )
        is None
    )
    query.assert_not_called()
    downloader.assert_not_called()


@pytest.mark.asyncio
async def test_cdk_added_during_query_prevents_download(installation):
    root, query, downloader = installation
    config = SimpleNamespace(Update=SimpleNamespace(MirrorChyanCDK=""))

    async def metadata(*args, **kwargs):
        config.Update.MirrorChyanCDK = "new-cdk"
        return {"data": {"version_name": "v6.1.0"}}

    query.side_effect = metadata
    assert (
        await update.prepare_maa_fluxdown_update(
            root, config=config, config_dir=root / "config"
        )
        is None
    )
    downloader.assert_not_called()


@pytest.mark.asyncio
async def test_mirror_precheck_still_runs_with_global_takeover(
    installation, monkeypatch
):
    root, _, _ = installation
    config = SimpleNamespace(
        Update=SimpleNamespace(MirrorChyanCDK="script-cdk", TakeoverEnabled=True)
    )
    monkeypatch.setattr(
        mirror_update, "read_installed_release", lambda root: ("v6.0.0", "x64")
    )
    monkeypatch.setattr(
        mirror_update, "resolve_update_channel", lambda version, dirs: "stable"
    )
    check = AsyncMock()
    monkeypatch.setattr(mirror_update, "_precheck_flow", check)
    monkeypatch.setattr(mirror_update, "_precheck_tasks", {})
    mirror_update.start_maa_software_update_precheck(
        root, config=config, config_dir=root / "config"
    )
    await asyncio.gather(*mirror_update._precheck_tasks.values())
    check.assert_awaited_once_with(root, "stable", "x64", "script-cdk")


def test_blank_native_cdk_allows_fluxdown(installation):
    root, _, _ = installation
    (root / "config/gui.new.json").write_text(
        '{"Update":{"MirrorChyanCdk":"  "}}', encoding="utf-8"
    )
    config = SimpleNamespace(Update=SimpleNamespace(MirrorChyanCDK="  "))
    assert credentials.use_maa_fluxdown_update(config, config_dirs=[root / "config"])


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["script", "global", "native", "disabled"])
async def test_policy_change_during_download_prevents_handoff(installation, change):
    root, _, downloader = installation
    config = SimpleNamespace(Update=SimpleNamespace(MirrorChyanCDK=""))
    original = downloader.side_effect

    async def download(*args, **kwargs):
        size = await original(*args, **kwargs)
        if change == "script":
            config.Update.MirrorChyanCDK = "new-cdk"
        elif change == "global":
            update.Config.setting.Update.MirrorChyanCDK = "new-cdk"
        elif change == "native":
            (root / "config/gui.new.json").write_text(
                '{"Update":{"MirrorChyanCdk":"opaque"}}', encoding="utf-8"
            )
        else:
            update.Config.setting.Update.FluxdownTakeoverAll = False
        return size

    downloader.side_effect = download
    assert (
        await update.prepare_maa_fluxdown_update(
            root, config=config, config_dir=root / "config"
        )
        is None
    )
    assert update.read_pending_update(root) == ("", "")
    assert not list(root.glob("*.zip"))
    assert list(root.glob("*.part"))


@pytest.mark.asyncio
async def test_slow_metadata_response_cannot_regress_version_cache(installation):
    root, query, _ = installation
    started, release = asyncio.Event(), asyncio.Event()
    config = SimpleNamespace(Update=SimpleNamespace(MirrorChyanCDK=""))
    count = 0

    async def metadata(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 1:
            started.set()
            await release.wait()
            return {"data": {"version_name": "v6.0.1"}}
        return {"data": {"version_name": "v6.0.2"}}

    query.side_effect = metadata
    first = asyncio.create_task(
        update.prepare_maa_fluxdown_update(
            root, config=config, config_dir=root / "config"
        )
    )
    await started.wait()
    await update.prepare_maa_fluxdown_update(
        root, config=config, config_dir=root / "config"
    )
    release.set()
    await first
    assert update._latest_versions[("x64", "beta")][1] == "v6.0.2"


@pytest.mark.parametrize(
    "channels, eligible, fails",
    [
        (["beta", "stable"], True, True),
        (["stable", "beta"], True, True),
        (["beta", "beta"], True, False),
        (["beta", "stable"], False, False),
    ],
)
def test_batch_checks_channels_before_any_installation(
    tmp_path, monkeypatch, channels, eligible, fails
):
    import uuid

    monkeypatch.setattr(
        manager.Config,
        "setting",
        SimpleNamespace(Update=SimpleNamespace(FluxdownTakeoverAll=True)),
    )
    monkeypatch.setattr(manager, "use_maa_fluxdown_update", lambda *a, **kw: eligible)
    monkeypatch.setattr(
        manager, "read_installed_release", lambda root: ("v6.0.0", "x64")
    )
    calls = iter(channels)
    monkeypatch.setattr(manager, "resolve_update_channel", lambda *args: next(calls))
    instance = object.__new__(manager.MaaManager)
    instance.maa_set_path = tmp_path / "config"
    instance.script_config = SimpleNamespace()
    users = [str(uuid.uuid4()), str(uuid.uuid4())]
    instance.script_info = SimpleNamespace(
        script_id="script", user_list=[SimpleNamespace(user_id=u) for u in users]
    )
    instance.user_config = {uuid.UUID(u): SimpleNamespace() for u in users}
    if fails:
        with pytest.raises(RuntimeError, match="更新通道不一致"):
            instance._validate_update_channels()
    else:
        instance._validate_update_channels()
