"""MAA 同日新版本取包、额度去重与共享缓存的离线回归。"""

import asyncio
import hashlib
import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.task.MAA.tools import fluxdown_update as github
from app.task.MAA.tools import resource_update as resource
from app.task.MAA.tools import software_update as software

NOW = datetime(2026, 11, 1, 4, tzinfo=timezone.utc)


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


def save_state(path, *, key, version, yesterday=False, backoff=False):
    state = {
        f"last_download_attempt_at/{key}": (
            NOW - timedelta(days=1) if yesterday else NOW
        ).isoformat(),
    }
    if version is not None:
        state[f"last_download_attempt_version/{key}"] = version
    if backoff:
        state[f"download_fail_until/{key}"] = (NOW + timedelta(hours=1)).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


@pytest.fixture
def software_install(tmp_path, monkeypatch, isolated_app_paths):
    monkeypatch.setattr(software, "datetime", FixedDatetime)
    state = tmp_path / "software-state.json"
    cache = tmp_path / "software-cache"
    monkeypatch.setattr(software, "_STATE_FILE", state)
    monkeypatch.setattr(
        software, "software_cache_dir", lambda os_name, arch, channel: cache
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
                TakeoverEnabled=True, Channel="beta", MirrorChyanCDK="test-cdk"
            )
        ),
    )


async def prepare_software(install, root=None):
    root = root or install.root
    return await software.prepare_maa_software_before_run(
        root, config_dir=root / "config", config=install.config
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("previous", ["v6.1.0", "v6.2.0", "6.1.0+build"])
async def test_software_same_or_older_version_never_requests_another_url(
    software_install, previous
):
    install = software_install
    save_state(install.state, key="win/x64/beta", version=previous)
    with pytest.raises(RuntimeError):
        await prepare_software(install)
    install.request.assert_not_awaited()
    install.downloader.assert_not_awaited()


@pytest.mark.asyncio
async def test_software_cache_is_registered_for_other_install_and_cdk_after_restart(
    software_install,
):
    install = software_install
    assert await prepare_software(install) == "v6.1.0"
    install.config.Update.MirrorChyanCDK = "other-cdk"
    for name in ("maa-second", "maa-third"):
        root = install.installation(name)
        assert await prepare_software(install, root) == "v6.1.0"
        version, package = software.read_pending_update(root)
        assert version == "v6.1.0" and Path(package).is_file()
    install.request.assert_awaited_once()
    install.downloader.assert_awaited_once()


@pytest.mark.asyncio
async def test_software_new_release_is_downloaded_once_for_other_installs(
    software_install,
):
    install = software_install
    assert await prepare_software(install) == "v6.1.0"
    install.query.return_value = "v6.2.0"
    install.request.return_value["data"]["version_name"] = "v6.2.0"
    roots = [install.installation("maa-second"), install.installation("maa-third")]
    assert await asyncio.gather(
        *(prepare_software(install, root) for root in roots)
    ) == ["v6.2.0", "v6.2.0"]
    assert install.request.await_count == install.downloader.await_count == 2


@pytest.mark.asyncio
async def test_software_corrupt_cache_cannot_bypass_version_budget(software_install):
    install = software_install
    assert await prepare_software(install) == "v6.1.0"
    (install.cache / "package.zip").write_bytes(b"corrupt package")
    root = install.installation("maa-second")
    with pytest.raises(RuntimeError):
        await prepare_software(install, root)
    assert software.read_pending_update(root) == ("", "")
    install.request.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["error", "cancel"])
async def test_software_records_actual_newer_response_before_failed_download(
    software_install, failure
):
    install = software_install
    install.request.return_value["data"]["version_name"] = "v6.2.0"
    install.downloader.side_effect = (
        OSError("offline") if failure == "error" else asyncio.CancelledError()
    )
    with pytest.raises(RuntimeError if failure == "error" else asyncio.CancelledError):
        await prepare_software(install)
    saved = json.loads(install.state.read_text())
    assert saved["last_download_attempt_version/win/x64/beta"] == "v6.2.0"
    # 日限额本身必须生效，不能只靠失败退避挡住重复取包。
    saved.pop("download_fail_until/win/x64/beta", None)
    install.state.write_text(json.dumps(saved))
    install.query.return_value = "v6.2.0"
    with pytest.raises(RuntimeError):
        await prepare_software(install)
    install.request.assert_awaited_once()


@pytest.mark.asyncio
async def test_software_previous_day_allows_retry_but_backoff_still_applies(
    software_install,
):
    install = software_install
    save_state(
        install.state,
        key="win/x64/beta",
        version="v6.1.0",
        yesterday=True,
        backoff=True,
    )
    with pytest.raises(RuntimeError):
        await prepare_software(install)
    install.request.assert_not_awaited()
    save_state(install.state, key="win/x64/beta", version="v6.1.0", yesterday=True)
    assert await prepare_software(install) == "v6.1.0"


@pytest.fixture
def resource_install(tmp_path, monkeypatch, isolated_app_paths):
    monkeypatch.setattr(resource, "datetime", FixedDatetime)
    monkeypatch.setattr(resource, "_prepare_install_lock", asyncio.Lock())
    work = tmp_path / "resource-cache"
    for name, value in {
        "_WORK_DIR": work,
        "_STAGE_DIR": work / "stage",
        "_STAGE_ZIP": work / "package.zip",
        "_MANIFEST_FILE": work / "manifest.json",
        "_STATE_FILE": work / "state.json",
        "_LOCK_FILE": tmp_path / "resource.lock",
    }.items():
        monkeypatch.setattr(resource, name, value)
    target = NOW - timedelta(hours=1)
    query = AsyncMock(return_value=target)
    monkeypatch.setattr(resource, "latest_resource_clock", query)
    request = AsyncMock(
        return_value={
            "data": {
                "url": "https://example.invalid/resource.zip",
                "version_name": resource._format_clock(target),
                "update_type": "full",
            }
        }
    )
    monkeypatch.setattr(
        resource._service_update_transport, "request_mirror_resource", request
    )

    async def download(url, path, **kwargs):
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "resource/version.json",
                json.dumps(
                    {"last_updated": request.return_value["data"]["version_name"]}
                ),
            )
            archive.writestr("resource/tasks.json", "opaque resource")

    downloader = AsyncMock(side_effect=download)
    monkeypatch.setattr(resource, "download_file", downloader)

    def installation(name):
        root = tmp_path / name
        (root / "resource").mkdir(parents=True)
        (root / "resource/version.json").write_text(
            '{"last_updated":"2026-10-01 00:00:00.000"}'
        )
        return root

    return SimpleNamespace(
        root=installation("maa"),
        installation=installation,
        target=target,
        query=query,
        request=request,
        downloader=downloader,
        state=resource._STATE_FILE,
        key=hashlib.sha256(b"test-cdk").hexdigest()[:16],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("previous", ["older", "legacy", "yesterday"])
async def test_resource_new_version_legacy_and_previous_day_allow_download(
    resource_install, previous
):
    install = resource_install
    version = (
        None
        if previous == "legacy"
        else (
            install.target - timedelta(hours=1)
            if previous == "older"
            else install.target
        ).isoformat()
    )
    save_state(
        install.state,
        key=install.key,
        version=version,
        yesterday=previous == "yesterday",
    )
    await resource.prepare_install_resources(install.root, cdk="test-cdk", github=False)
    assert resource.read_resource_clock(install.root) == install.target
    install.request.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("backoff", [False, True])
async def test_resource_same_version_or_backoff_never_requests_url(
    resource_install, backoff
):
    install = resource_install
    version = install.target - timedelta(hours=1) if backoff else install.target
    save_state(
        install.state, key=install.key, version=version.isoformat(), backoff=backoff
    )
    with pytest.raises(RuntimeError):
        await resource.prepare_install_resources(
            install.root, cdk="test-cdk", github=False
        )
    install.request.assert_not_awaited()


@pytest.mark.asyncio
async def test_resource_new_release_updates_shared_cache_once_for_all_installs(
    resource_install,
):
    install = resource_install
    await resource.prepare_install_resources(install.root, cdk="test-cdk", github=False)
    install.query.return_value += timedelta(minutes=9)
    install.request.return_value["data"]["version_name"] = resource._format_clock(
        install.query.return_value
    )
    roots = [
        install.root,
        install.installation("maa-second"),
        install.installation("maa-third"),
    ]
    await asyncio.gather(
        *(
            resource.prepare_install_resources(root, cdk="test-cdk", github=False)
            for root in roots
        )
    )
    assert all(
        resource.read_resource_clock(root) == install.query.return_value
        for root in roots
    )
    assert install.request.await_count == install.downloader.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["error", "cancel"])
async def test_resource_failed_download_keeps_version_budget(resource_install, failure):
    install = resource_install
    install.downloader.side_effect = (
        OSError("offline") if failure == "error" else asyncio.CancelledError()
    )
    with pytest.raises(RuntimeError if failure == "error" else asyncio.CancelledError):
        await resource.prepare_install_resources(
            install.root, cdk="test-cdk", github=False
        )
    saved = json.loads(install.state.read_text())
    assert (
        saved[f"last_download_attempt_version/{install.key}"]
        == install.target.isoformat()
    )
    saved.pop(f"download_fail_until/{install.key}", None)
    install.state.write_text(json.dumps(saved))
    with pytest.raises(RuntimeError):
        await resource.prepare_install_resources(
            install.root, cdk="test-cdk", github=False
        )
    install.request.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("response_version", [None, "2026-10-31 00:00:00.000"])
async def test_resource_invalid_or_older_response_is_accounted_before_rejection(
    resource_install, response_version
):
    install = resource_install
    install.request.return_value["data"]["version_name"] = response_version
    with pytest.raises(RuntimeError):
        await resource.prepare_install_resources(
            install.root, cdk="test-cdk", github=False
        )
    saved = json.loads(install.state.read_text())
    assert (
        saved[f"last_download_attempt_version/{install.key}"]
        == install.target.isoformat()
    )
    saved.pop(f"download_fail_until/{install.key}", None)
    install.state.write_text(json.dumps(saved))
    with pytest.raises(RuntimeError):
        await resource.prepare_install_resources(
            install.root, cdk="test-cdk", github=False
        )
    install.request.assert_awaited_once()
    install.downloader.assert_not_awaited()
