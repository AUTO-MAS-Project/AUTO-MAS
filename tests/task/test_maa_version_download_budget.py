"""MAA 同日新版本取包、额度去重与共享缓存的离线回归。"""

import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from maa_adapter.updates import fluxdown as github
from maa_adapter.updates.software import service as software

NOW = datetime(2026, 11, 1, 4, tzinfo=timezone.utc)


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


@pytest.fixture
def software_install(tmp_path, monkeypatch, isolated_app_paths):
    monkeypatch.setattr(software, "datetime", FixedDatetime)
    state = tmp_path / "software-state.json"
    cache = tmp_path / "software-cache"
    monkeypatch.setattr(software, "_STATE_FILE", state)
    monkeypatch.setattr(
        software, "software_cache_dir", lambda os_name, arch, channel, **kwargs: cache
    )
    monkeypatch.setattr(software, "_running_updater_paths", lambda: set())
    monkeypatch.setattr(
        software, "read_installed_release", lambda root: ("v6.0.0", "x64")
    )
    monkeypatch.setattr(software, "_cache_locks", {})
    monkeypatch.setattr(software, "_precheck_tasks", {})
    query = AsyncMock(return_value="v6.1.0")
    monkeypatch.setattr(github, "query_latest_maa_version", query)
    request = AsyncMock(
        return_value={
            "data": {
                "version_name": "v6.1.0",
                "url": "https://example.invalid/maa.zip",
                "update_type": "full",
            }
        }
    )
    monkeypatch.setattr(
        software._service_update_transport, "request_mirror_resource", request
    )

    async def download(url, path, **kwargs):
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("MAA.exe", b"opaque executable")
            archive.writestr("MAA.dll", b"opaque assembly")

    downloader = AsyncMock(side_effect=download)
    monkeypatch.setattr(software, "download_file", downloader)

    def installation(name):
        root = tmp_path / name
        (root / "config").mkdir(parents=True)
        (root / "config/gui.new.json").write_text('{"Update": {}}')
        return root

    return SimpleNamespace(
        root=installation("maa"),
        installation=installation,
        state=state,
        cache=cache,
        query=query,
        request=request,
        downloader=downloader,
        config=SimpleNamespace(
            Update=SimpleNamespace(
                TakeoverEnabled=True,
                Channel="beta",
                MirrorChyanCDK="test-cdk",
                PackageMode="full",
            )
        ),
    )


async def prepare_software(install, root=None):
    root = root or install.root
    return await software.prepare_maa_software_before_run(
        root, config_dir=root / "config", config=install.config
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("package_mode", ["full", "incremental"])
async def test_mirror_prefetch_selects_the_package_used_by_update(
    software_install, package_mode
):
    install = software_install
    install.config.Update.PackageMode = package_mode

    async def request(rid, *, params, **kwargs):
        incremental = params.get("current_version") == "v6.0.0"
        return {
            "data": {
                "version_name": "v6.1.0",
                "url": "https://example.invalid/"
                + ("delta" if incremental else "full"),
                "update_type": "incremental" if incremental else "full",
            }
        }

    async def download(url, path, **kwargs):
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as package:
            if url.endswith("delta"):
                package.writestr("changes.json", '{"deleted": []}')
                package.writestr("resource/change.json", "new")
            else:
                package.writestr("MAA.exe", "exe")
                package.writestr("MAA.dll", "dll")

    install.request.side_effect = request
    install.downloader.side_effect = download
    downloads = await software.check_software_download(install.root, install.config)
    expected_url = "https://example.invalid/" + (
        "delta" if package_mode == "incremental" else "full"
    )
    assert downloads[0].url == expected_url
    assert await prepare_software(install) == "v6.1.0"
    assert install.downloader.await_args.args[0] == expected_url
