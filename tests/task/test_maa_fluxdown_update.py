"""MAA 启动前更新的隔离验证，不启动 MAA 或访问生产网络。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from maa_adapter.updates import fluxdown as update

from app.services.common.update import transport as update_transport


def script_config(
    *, enabled=True, channel="stable", cdk="", package_mode="incremental"
):
    return SimpleNamespace(
        Update=SimpleNamespace(
            TakeoverEnabled=enabled,
            Channel=channel,
            MirrorChyanCDK=cdk,
            PackageMode=package_mode,
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
async def test_full_mode_ignores_available_official_ota(installation):
    root, release, downloader = installation
    release.return_value["details"]["assets"] = [
        {"name": "MAAComponent-OTA-v6.0.0_v6.1.0-win-x64.zip"}
    ]
    await update.prepare_maa_fluxdown_update(
        root, config=script_config(package_mode="full"), config_dir=root / "config"
    )
    assert downloader.call_args.args[0].endswith("/MAA-v6.1.0-win-x64.zip")


@pytest.mark.asyncio
async def test_prefetched_ota_is_rejected_after_switching_to_full(
    installation, monkeypatch
):
    root, release, _ = installation
    monkeypatch.chdir(root.parent)
    release.return_value["details"]["assets"] = [
        {"name": "MAAComponent-OTA-v6.0.0_v6.1.0-win-x64.zip"}
    ]
    config = script_config()
    candidate = await update.prepare_maa_fluxdown_update(
        root, config=config, config_dir=root / "config", download_only=True
    )
    try:
        config.Update.PackageMode = "full"
        with pytest.raises(RuntimeError):
            await update.prepare_maa_fluxdown_update(
                root, config=config, config_dir=root / "config", prepared=candidate
            )
        assert update.read_pending_update(root) == ("", "")
    finally:
        update.discard_prepared_update(candidate)
