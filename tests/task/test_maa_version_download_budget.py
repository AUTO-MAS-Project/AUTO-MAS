"""MAA 同日新版本取包、额度去重与共享缓存的离线回归。"""

import asyncio
import json
import zipfile
from datetime import datetime, timedelta, timezone
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
@pytest.mark.parametrize("blocked", ["daily", "download_backoff", "query_backoff"])
async def test_software_prefetch_respects_persisted_download_limits(
    software_install, blocked
):
    """进程内无下载缓存时，持久化额度或退避记录仍须阻止 L2 申请真实传输。"""
    install = software_install
    key = software._cache_key("x64", "beta")
    if blocked == "daily":
        state = {
            f"last_download_attempt_at/{key}": NOW.isoformat(),
            f"last_download_attempt_version/{key}": "v6.1.0",
        }
    else:
        field = (
            f"query_fail_until/{software._query_key('x64', 'beta', 'test-cdk')}"
            if blocked == "query_backoff"
            else f"download_fail_until/{key}"
        )
        state = {field: (NOW + timedelta(hours=1)).isoformat()}
    software._utils_io.write_file(install.state, state)
    assert await software.check_software_download(install.root, install.config) == []
    with pytest.raises(RuntimeError):
        await prepare_software(install)
    install.downloader.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", ["daily", "download_backoff"])
async def test_resource_prefetch_respects_persisted_download_limits(
    software_install, monkeypatch, blocked
):
    """资源检查在没有可复用共享缓存时也遵守实际准备流程的取包限制。"""
    import hashlib

    from maa_adapter.updates.resources import service as resources

    install = software_install
    monkeypatch.setattr(resources, "datetime", FixedDatetime)
    work = install.root / "resource-cache"
    for field, relative in {
        "_WORK_DIR": ".",
        "_STAGE_DIR": "stage",
        "_MANIFEST_FILE": "manifest.json",
        "_STATE_FILE": "state.json",
    }.items():
        monkeypatch.setattr(resources, field, work / relative)
    directory = install.root / "resource"
    directory.mkdir()
    (directory / "version.json").write_text(
        json.dumps({"last_updated": "2026-10-31 00:00:00.000"})
    )
    target = NOW.replace(hour=0)
    key = hashlib.sha256(b"test-cdk").hexdigest()[:16]
    state = (
        {
            f"last_download_attempt_at/{key}": NOW.isoformat(),
            f"last_download_attempt_version/{key}": target.isoformat(),
        }
        if blocked == "daily"
        else {f"download_fail_until/{key}": (NOW + timedelta(hours=1)).isoformat()}
    )
    resources._utils_io.write_file(resources._STATE_FILE, state)
    install.request.return_value = {
        "data": {
            "version_name": "2026-11-01 00:00:00.000",
            "url": "https://example.invalid/resources.zip",
            "update_type": "full",
        }
    }
    assert (
        await resources.check_resource_download(
            install.root, github=False, cdk="test-cdk"
        )
        == []
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("package_mode", ["full", "incremental"])
async def test_mirror_prefetch_selects_the_package_used_by_update(
    software_install, package_mode, monkeypatch, tmp_path
):
    from app.core import Config
    from app.core import downloads as host_downloads
    from app.core.background_tasks import BackgroundTaskRegistry
    from app.models.config import GlobalConfig
    from app.services.common.update.prefetch import prefetch_paths
    from tests.config_support import activate_config

    install = software_install
    install.config.Update.PackageMode = package_mode
    addresses = []
    transfers = []

    async def request(rid, *, params, **kwargs):
        """每次元数据查询返回新的临时地址，模拟同一文件在 Mirror 酱上的真实取址行为。"""
        incremental = params.get("current_version") == "v6.0.0"
        url = (
            "https://example.invalid/"
            + ("delta" if incremental else "full")
            + f"?ticket={len(addresses)}"
        )
        addresses.append(url)
        return {
            "data": {
                "version_name": "v6.1.0",
                "url": url,
                "update_type": "incremental" if incremental else "full",
            }
        }

    async def download(url, path, **kwargs):
        """仅替代 HTTP 传输，写入可通过插件真实包校验和登记流程的文件。"""
        transfers.append(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as package:
            if url.split("?")[0].endswith("delta"):
                package.writestr("changes.json", '{"deleted": []}')
                package.writestr("resource/change.json", "new")
            else:
                package.writestr("MAA.exe", "exe")
                package.writestr("MAA.dll", "dll")

    install.request.side_effect = request
    monkeypatch.setattr(software, "download_file", host_downloads.download_file)
    monkeypatch.setattr(
        host_downloads._service_update_fluxdown, "_httpx_download", download
    )
    monkeypatch.setattr(
        host_downloads._utils_fluxdown_cli,
        "_server_data_dir",
        lambda _: tmp_path / "fluxdown",
    )
    monkeypatch.setattr(Config, "setting", await activate_config(GlobalConfig.build()))
    background = BackgroundTaskRegistry()
    manager = host_downloads.DownloadManager()
    monkeypatch.setattr(host_downloads, "Downloads", manager)
    manager.initialize(
        directory=tmp_path / "downloads",
        max_running=1,
        attempts=1,
        retry_delay=0,
        background=background,
    )
    try:
        first = (await software.check_software_download(install.root, install.config))[
            0
        ]
        assert manager.request(first, owner="L2")
        ready = await manager.wait(first)
        second = (await software.check_software_download(install.root, install.config))[
            0
        ]
        assert second.url != first.url and second.cache_key == first.cache_key
        assert second.rid == first.rid == "v6.1.0"
        assert manager.request(second, owner="L2")
        assert (await manager.wait(second)).path == ready.path
        token = prefetch_paths.set({second.cache_key: ready.path})
        try:
            assert await prepare_software(install) == "v6.1.0"
        finally:
            prefetch_paths.reset(token)
        # 查询三次仍只发生一次文件传输，安装登记使用同一份全量或增量预下载包。
        assert len(addresses) == 3
        assert transfers == [first.url]
        assert software.read_pending_update(install.root)[0] == "v6.1.0"
        assert (
            await software.check_software_download(install.root, install.config) == []
        )
        assert transfers == [first.url]
        assert await manager.release(first.cache_key, owner="L2")
    finally:
        await manager.shutdown_all()
        await background.shutdown(timeout=2)


@pytest.mark.asyncio
async def test_resource_prefetch_reuses_verified_baseline_and_changed_address(
    tmp_path, monkeypatch, isolated_app_paths
):
    """安装比共享基线旧时仍选同一增量包，多次取址只传输一次，安装后保留未变更资源。"""
    from maa_adapter.updates.resources import service as resources

    from app.core import Config
    from app.core import downloads as host_downloads
    from app.core.background_tasks import BackgroundTaskRegistry
    from app.models.config import GlobalConfig
    from app.services.common.update.prefetch import prefetch_paths
    from tests.config_support import activate_config

    work = tmp_path / "resource-cache"
    for field, relative in {
        "_WORK_DIR": ".",
        "_STAGE_DIR": "stage",
        "_MANIFEST_FILE": "manifest.json",
        "_STAGE_ZIP": "package.zip",
        "_STATE_FILE": "state.json",
        "_LOCK_FILE": "resource.lock",
    }.items():
        monkeypatch.setattr(resources, field, work / relative)
    monkeypatch.setattr(resources, "_prepare_install_lock", asyncio.Lock())
    install = tmp_path / "maa"
    for root, version in (
        (install, "2026-11-01 00:00:00.000"),
        (work / "stage", "2026-11-02 00:00:00.000"),
    ):
        directory = root / "resource"
        directory.mkdir(parents=True)
        (directory / "version.json").write_text(json.dumps({"last_updated": version}))
        (directory / "unchanged.txt").write_text("keep")
    baseline = datetime(2026, 11, 2, tzinfo=timezone.utc)
    target = datetime(2026, 11, 3, tzinfo=timezone.utc)
    resources._utils_io.write_file(
        resources._MANIFEST_FILE,
        {
            "full": True,
            "target": baseline.isoformat(),
            "files": resources.resource_tree_hashes(work / "stage/resource"),
        },
    )
    addresses, transfers = [], []

    async def request(resource_id, *, params, **kwargs):
        """免费查询只返回版本，取址返回变化的 URL；增量基线必须是已校验共享缓存的版本。"""
        data = {"version_name": "2026-11-03 00:00:00.000"}
        if "cdk" in params:
            assert params.get("current_version") == "2026-11-02 00:00:00.000"
            data.update(
                url=f"https://example.invalid/resources?ticket={len(addresses)}",
                update_type="incremental",
            )
            addresses.append(data["url"])
        return {"data": data}

    async def download(url, destination, **kwargs):
        """仅隔离 HTTP，保留真实资源包解压、共享基线合并及安装结果核验。"""
        transfers.append(url)
        with zipfile.ZipFile(destination, "w") as package:
            package.writestr(
                "resource/version.json",
                json.dumps({"last_updated": "2026-11-03 00:00:00.000"}),
            )
            package.writestr("resource/new.txt", "new")
            package.writestr("changes.json", '{"deleted": []}')

    monkeypatch.setattr(
        resources._service_update_transport, "request_mirror_resource", request
    )
    monkeypatch.setattr(
        host_downloads._service_update_fluxdown, "_httpx_download", download
    )
    monkeypatch.setattr(
        host_downloads._utils_fluxdown_cli,
        "_server_data_dir",
        lambda _: tmp_path / "fluxdown",
    )
    monkeypatch.setattr(Config, "setting", await activate_config(GlobalConfig.build()))
    background = BackgroundTaskRegistry()
    manager = host_downloads.DownloadManager()
    monkeypatch.setattr(host_downloads, "Downloads", manager)
    manager.initialize(
        directory=tmp_path / "downloads",
        max_running=1,
        attempts=1,
        retry_delay=0,
        background=background,
    )
    try:
        first = (
            await resources.check_resource_download(
                install, github=False, cdk="test", incremental=True
            )
        )[0]
        assert manager.request(first, owner="L2")
        ready = await manager.wait(first)
        second = (
            await resources.check_resource_download(
                install, github=False, cdk="test", incremental=True
            )
        )[0]
        assert second.url != first.url and second.cache_key == first.cache_key
        assert second.rid == first.rid == target.isoformat()
        assert manager.request(second, owner="L2")
        assert (await manager.wait(second)).path == ready.path
        token = prefetch_paths.set({second.cache_key: ready.path})
        access = await resources.acquire_resource_access_lock(install)
        assert access is not None
        try:
            await resources.prepare_install_resources(
                install, github=False, cdk="test", incremental=True
            )
        finally:
            access.__exit__(None, None, None)
            prefetch_paths.reset(token)
        assert resources.read_resource_clock(install) == target
        assert (install / "resource/unchanged.txt").read_text() == "keep"
        assert (install / "resource/new.txt").read_text() == "new"
        assert len(addresses) == 3 and transfers == [first.url]
        assert await manager.release(first.cache_key, owner="L2")
    finally:
        await manager.shutdown_all()
        await background.shutdown(timeout=2)
