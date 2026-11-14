"""MaaEnd 官方完整包、准备回退、原生更新隔离和配置恢复。"""

import asyncio
import base64
import hashlib
import json
import shutil
import threading
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from packaging.version import Version

from app.services import script_install
from app.services.common.update.fluxdown import FluxdownResumableError
from app.task.MaaEnd import manager
from app.task.MaaEnd.tools import package_download
from app.task.MaaEnd.tools import script_update as update
from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed
from tests.runtime_support import RuntimeStub as SimpleNamespace


def pe(machine=0x8664):
    data = bytearray(134)
    data[:2] = b"MZ"
    data[60:64] = (128).to_bytes(4, "little")
    data[128:132] = b"PE\0\0"
    data[132:134] = machine.to_bytes(2, "little")
    return bytes(data)


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["valid", "corrupt", "wrong-base", "cancel"])
async def test_site_delta_installs_exact_official_package_or_falls_back(
    installation, tmp_path, monkeypatch, variant
):
    root, config = installation
    old = tmp_path / "official.zip"
    config.Update.PackageMode = "incremental"
    unchanged = b"unchanged distribution data" * 40000
    with zipfile.ZipFile(old, "a") as archive:
        archive.writestr("resource/large.bin", unchanged)
    asset = update.request_release.return_value["assets"][0]
    asset.update(
        size=old.stat().st_size,
        digest="sha256:" + hashlib.sha256(old.read_bytes()).hexdigest(),
    )
    await update.update_before_run(root, config)
    target, release = _official_release_for_test(tmp_path, "v2.3.0")
    with zipfile.ZipFile(target, "a") as archive:
        archive.writestr("resource/large.bin", unchanged)
    asset = release["assets"][0]
    size = target.stat().st_size
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    asset.update(size=size, digest="sha256:" + digest)
    with zipfile.ZipFile(old) as archive:
        item = archive.getinfo("resource/large.bin")
        old_start = item.header_offset + 30 + len(item.filename.encode())
    with zipfile.ZipFile(target) as archive:
        item = archive.getinfo("resource/large.bin")
        new_start = item.header_offset + 30 + len(item.filename.encode())
    data = target.read_bytes()
    tail = new_start + len(unchanged)
    metadata = {
        "version": 2,
        "mode": "range-zip",
        "arch": "x86_64",
        "channel": "stable",
        "target_version": "2.3.0",
        "bases": ["2.2.0"],
        "beta_base": None,
        "base_sha256": hashlib.sha256(old.read_bytes()).hexdigest(),
        "target_size": size,
        "target_sha256": digest,
        "operations": [
            ["new", 0, new_start],
            ["old", old_start, len(unchanged)],
            ["new", new_start, size - tail],
        ],
    }
    patch = tmp_path / "site.delta.zip"
    if variant == "wrong-base":
        metadata["base_sha256"] = "0" * 64
    metadata["plans"] = {metadata["base_sha256"]: metadata["operations"]}
    with zipfile.ZipFile(patch, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(metadata))
        payload = data[:new_start] + data[tail:]
        archive.writestr("payload", b"corrupt" if variant == "corrupt" else payload)

    async def site_download(url, destination, **kwargs):
        assert url.endswith("/maaend-x64-stable-delta/download")
        if variant == "cancel":
            raise asyncio.CancelledError
        shutil.copyfile(patch, destination)

    monkeypatch.setattr(
        package_download, "download_file", AsyncMock(side_effect=site_download)
    )
    async_client, sync_client = httpx.AsyncClient, httpx.Client

    def response(request):
        if request.url.host == "api.github.com":
            return httpx.Response(200, json=[{"tag_name": "v2.2.0"}])
        return httpx.Response(503)

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: async_client(**kw, transport=httpx.MockTransport(response)),
    )
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: sync_client(**kw, transport=httpx.MockTransport(response)),
    )
    monkeypatch.setattr(update, "request_release", AsyncMock(return_value=release))

    async def full_download(url, destination, **kwargs):
        shutil.copyfile(target, destination)

    monkeypatch.setattr(update, "download_file", AsyncMock(side_effect=full_download))
    config.Update.PackageMode = "incremental"
    if variant == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await update.prepare_update(root, config)
        assert update.read_install(root)[0] == Version("2.2.0")
        update.download_file.assert_not_awaited()
        return
    candidate = await update.prepare_update(root, config)
    assert candidate.destination.read_bytes() == target.read_bytes()
    assert update.read_install(root)[0] == Version("2.2.0")
    assert update.download_file.await_count == int(variant != "valid")
    await update.apply_update(root, candidate)
    assert update.read_install(root)[0] == Version("2.3.0")
    assert script_install.verify_installed_files(root, threading.Event())
    assert (root / "resource/large.bin").read_bytes() == unchanged
    assert (root / "config/mxu-MaaEnd.json").read_bytes() == b'{"user-data": true}'


@pytest.mark.asyncio
@pytest.mark.parametrize("base_tag", ["v3.1.0-beta.4", "v2.2.0"])
async def test_beta_range_skips_versions_reuses_data_and_removes_obsolete_files(
    installation, tmp_path, monkeypatch, base_tag
):
    import random

    root, config = installation
    shared = random.Random(7).randbytes(1024 * 1024)
    old, release = _official_release_for_test(tmp_path, base_tag)
    with zipfile.ZipFile(old, "a") as archive:
        archive.writestr("resource/shared.bin", shared)
        archive.writestr("resource/obsolete.json", "removed in b8")
        archive.writestr("resource/reverted.json", "changed in b4")
    release["assets"][0].update(
        size=old.stat().st_size,
        digest="sha256:" + hashlib.sha256(old.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(update, "request_release", AsyncMock(return_value=release))

    async def initial_download(_url, destination, **_):
        shutil.copyfile(old, destination)

    monkeypatch.setattr(
        update, "download_file", AsyncMock(side_effect=initial_download)
    )
    config.Update.PackageMode = "incremental"
    config.Update.Channel = "beta"
    await update.update_before_run(root, config)
    target, release = _official_release_for_test(tmp_path, "v3.1.0-beta.8")
    with zipfile.ZipFile(target, "a") as archive:
        archive.writestr("resource/shared.bin", shared)
        archive.writestr("resource/reverted.json", "original stable content")
    content = target.read_bytes()
    release["assets"][0].update(
        size=len(content), digest="sha256:" + hashlib.sha256(content).hexdigest()
    )
    monkeypatch.setattr(update, "request_release", AsyncMock(return_value=release))
    received = []

    def respond(request):
        assert request.url.host != "api.github.com", "GitHub Range 不依赖版本范围索引"
        start, end = map(
            int, request.headers["Range"].removeprefix("bytes=").split("-")
        )
        data = content[start : end + 1]
        received.append(len(data))
        return httpx.Response(
            206,
            content=data,
            headers={"Content-Range": f"bytes {start}-{end}/{len(content)}"},
        )

    async_client, sync_client = httpx.AsyncClient, httpx.Client
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: async_client(**kw, transport=httpx.MockTransport(respond)),
    )
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: sync_client(**kw, transport=httpx.MockTransport(respond)),
    )
    site = AsyncMock(side_effect=AssertionError("GitHub 成功时不应取自建站包"))
    full = AsyncMock(side_effect=AssertionError("合法区间更新不应下载全量"))
    monkeypatch.setattr(package_download, "download_file", site)
    monkeypatch.setattr(update, "download_file", full)
    candidate = await update.prepare_update(root, config)
    assert candidate.destination.read_bytes() == content
    assert sum(received) < len(content) * 0.4
    await update.apply_update(root, candidate)
    assert update.read_install(root)[0] == Version("3.1.0b8")
    assert not (root / "resource/obsolete.json").exists()
    assert (root / "resource/reverted.json").read_text() == "original stable content"
    assert (root / "resource/shared.bin").read_bytes() == shared
    assert script_install.verify_installed_files(root, threading.Event())
    site.assert_not_awaited()
    full.assert_not_awaited()


@pytest.mark.parametrize(
    "current,channel,target,bases,anchor,allowed",
    [
        ("3.0.0", "stable", "3.1.0", ["3.0.0", "2.9.0", "2.8.0"], None, True),
        ("2.7.0", "stable", "3.1.0", ["3.0.0", "2.9.0", "2.8.0"], None, False),
        ("3.1.0", "beta", "3.1.0b8", ["3.1.0"], "3.1.0", True),
        ("3.1.0b1", "beta", "3.1.0b8", ["3.1.0"], "3.1.0", True),
        ("3.0.0", "beta", "3.1.0b8", ["3.1.0"], "3.1.0", False),
        ("3.2.0b1", "beta", "3.2.0b8", [], None, False),
    ],
)
def test_incremental_policy_requires_supported_stable_or_same_cycle_beta(
    current, channel, target, bases, anchor, allowed
):
    policy = {
        "version": 2,
        "mode": "range-zip",
        "target_version": target,
        "target_size": 100,
        "target_sha256": "a" * 64,
        "arch": "x86_64",
        "channel": channel,
        "bases": bases,
        "beta_base": anchor,
    }
    assert (
        package_download.policy_allows(
            policy, current, target, 100, "a" * 64, "x86_64", channel
        )
        is allowed
    )


@pytest.mark.asyncio
async def test_beta_site_fallback_retains_formal_anchor_across_beta_updates(
    installation, tmp_path, monkeypatch
):
    root, config = installation
    shared = b"shared formal distribution" * 40000
    formal, release = _official_release_for_test(tmp_path, "v3.1.0")
    saved_formal = tmp_path / "saved-formal.zip"
    shutil.copyfile(formal, saved_formal)
    formal = saved_formal
    with zipfile.ZipFile(formal, "a") as archive:
        archive.writestr("resource/shared.bin", shared)
    size, digest = (
        formal.stat().st_size,
        hashlib.sha256(formal.read_bytes()).hexdigest(),
    )
    release["assets"][0].update(size=size, digest="sha256:" + digest)
    monkeypatch.setattr(update, "request_release", AsyncMock(return_value=release))

    async def first_download(_url, destination, **_):
        shutil.copyfile(formal, destination)

    monkeypatch.setattr(update, "download_file", AsyncMock(side_effect=first_download))
    config.Update.PackageMode = "incremental"
    await update.update_before_run(root, config)
    beta, beta_release = _official_release_for_test(tmp_path, "v3.1.0-beta.4")
    with zipfile.ZipFile(beta, "a") as archive:
        archive.writestr("resource/shared.bin", shared)
    beta_release["assets"][0].update(
        size=beta.stat().st_size,
        digest="sha256:" + hashlib.sha256(beta.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(update, "request_release", AsyncMock(return_value=beta_release))

    async def beta_download(_url, destination, **_):
        shutil.copyfile(beta, destination)

    monkeypatch.setattr(update, "download_file", AsyncMock(side_effect=beta_download))
    config.Update.Channel = "beta"
    config.Update.PackageMode = "full"
    await update.update_before_run(root, config)
    await script_install.run_worker(
        package_download.remember_package,
        root,
        beta,
        beta.stat().st_size,
        hashlib.sha256(beta.read_bytes()).hexdigest(),
        version="3.1.0b4",
    )
    target, release = _official_release_for_test(tmp_path, "v3.1.0-beta.8")
    with zipfile.ZipFile(target, "a") as archive:
        archive.writestr("resource/shared.bin", shared)
    content = target.read_bytes()
    target_digest = hashlib.sha256(content).hexdigest()
    release["assets"][0].update(size=len(content), digest="sha256:" + target_digest)
    with zipfile.ZipFile(formal) as archive:
        info = archive.getinfo("resource/shared.bin")
        old_start = info.header_offset + 30 + len(info.filename.encode())
    with zipfile.ZipFile(target) as archive:
        info = archive.getinfo("resource/shared.bin")
        start = info.header_offset + 30 + len(info.filename.encode())
    tail = start + len(shared)
    patch = tmp_path / "beta-fallback.zip"
    policy = {
        "version": 2,
        "mode": "range-zip",
        "arch": "x86_64",
        "channel": "beta",
        "target_version": "3.1.0b8",
        "target_size": len(content),
        "target_sha256": target_digest,
        "bases": ["3.1.0"],
        "beta_base": "3.1.0",
        "plans": {
            digest: [
                ["new", 0, start],
                ["old", old_start, len(shared)],
                ["new", start, len(content) - tail],
            ]
        },
    }
    with zipfile.ZipFile(patch, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(policy))
        archive.writestr("payload", content[:start] + content[tail:])
    client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: client(
            **kw, transport=httpx.MockTransport(lambda _: httpx.Response(200))
        ),
    )

    async def site_download(_url, destination, **_):
        shutil.copyfile(patch, destination)

    site = AsyncMock(side_effect=site_download)
    monkeypatch.setattr(package_download, "download_file", site)
    monkeypatch.setattr(update, "request_release", AsyncMock(return_value=release))
    full = AsyncMock(side_effect=AssertionError("备用增量成功时不能全量"))
    monkeypatch.setattr(update, "download_file", full)
    config.Update.PackageMode = "incremental"
    candidate = await update.prepare_update(root, config)
    assert candidate.destination.read_bytes() == content
    await update.apply_update(root, candidate)
    directory = (
        package_download.Config.data_path
        / "maaend_package_cache"
        / script_install.record_directory(root).name
    )
    assert (directory / "stable.zip").read_bytes() == formal.read_bytes()
    assert json.loads((directory / "baseline.json").read_text())["version"] == "3.1.0b8"
    assert script_install.verify_installed_files(root, threading.Event())
    site.assert_awaited_once()
    full.assert_not_awaited()


@pytest.fixture
def installation(tmp_path, monkeypatch, isolated_app_paths):
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
            TakeoverEnabled=True,
            Channel="stable",
            MirrorChyanCDK="",
            PackageMode="full",
        ),
        Game=SimpleNamespace(ControllerType="Win32-Front"),
    )
    return root, config


@pytest.mark.asyncio
async def test_official_package_installs_and_preserves_native_interface(installation):
    root, config = installation
    old_pipeline = root / "resource/pipeline/old.json"
    old_pipeline.parent.mkdir(parents=True)
    old_pipeline.write_bytes(b'{"OldNode": {}}')
    archive = root.parent / "official.zip"
    with zipfile.ZipFile(archive, "a") as package:
        package.writestr("resource/pipeline/nodes.json", '{"NewNode": {}}')
    asset = update.request_release.return_value["assets"][0]
    asset["size"] = archive.stat().st_size
    asset["digest"] = "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
    await update.update_before_run(root, config)
    assert update.read_install(root) == (Version("2.2.0"), "x86_64")
    assert not list((root.parent / "data/maaend_update").glob("download-*"))
    assert (root / "data/AutoDelivery/catalog.json").is_file()
    assert not old_pipeline.exists()
    assert (root / "resource/pipeline/nodes.json").read_bytes() == b'{"NewNode": {}}'
    backups = list(
        (script_install.workspace(root) / "retired-pipelines").rglob("old.json")
    )
    assert len(backups) == 1
    assert backups[0].read_bytes() == b'{"OldNode": {}}'
    assert (root / "config/mxu-MaaEnd.json").read_bytes() == b'{"user-data": true}'
    assert update.download_file.await_args.kwargs["downloader"] == "fluxdown"
    assert (
        json.loads((root / "interface.json").read_bytes())["mirrorchyan_rid"]
        == "MaaEnd"
    )


@pytest.mark.asyncio
async def test_same_version_without_receipt_does_not_download(
    installation, tmp_path, monkeypatch
):
    root, config = installation
    archive, release = _official_release_for_test(tmp_path, "v2.1.0")
    monkeypatch.setattr(update, "request_release", AsyncMock(return_value=release))

    async def download(_url, destination, **_kwargs):
        shutil.copyfile(archive, destination)

    downloader = AsyncMock(side_effect=download)
    monkeypatch.setattr(update, "download_file", downloader)
    original_interface = (root / "interface.json").read_bytes()
    assert not script_install.record_path(root, "installed.json").exists()

    for _ in range(2):
        assert "无需更新" in await update.update_before_run(root, config)
    downloader.assert_not_awaited()
    assert not script_install.record_directory(root).exists()
    assert not script_install.workspace(root).exists()
    assert (root / "interface.json").read_bytes() == original_interface
    assert (root / "config/mxu-MaaEnd.json").read_bytes() == b'{"user-data": true}'


@pytest.mark.asyncio
async def test_same_version_with_receipt_repairs_damaged_resources(installation):
    root, config = installation
    await update.update_before_run(root, config)
    (root / "resource/data.json").write_bytes(b"damaged resource")
    update.download_file.reset_mock()

    assert "已更新" in await update.update_before_run(root, config)
    update.download_file.assert_awaited_once()
    assert (root / "resource/data.json").read_bytes() == b"{}"
    assert script_install.verify_installed_files(root, threading.Event())


@pytest.mark.asyncio
async def test_legacy_records_are_ignored_during_prefetch_and_deleted_on_recovery(
    installation,
):
    root, config = installation
    await update.update_before_run(root, config)
    directory = script_install.record_directory(root)
    legacy = script_install.workspace(root)
    legacy.mkdir()
    original = {}
    for name in ("installed.json", "program-identity.json"):
        original[name] = (directory / name).read_bytes()
        (directory / name).replace(legacy / name)
    update.download_file.reset_mock()

    candidate = await update.prepare_update(root, config)
    assert isinstance(candidate, str)
    update.download_file.assert_not_awaited()
    assert all(
        (legacy / name).read_bytes() == value for name, value in original.items()
    )
    assert not list(directory.iterdir())

    with script_install.installation_access(root):
        script_install.recover_install(root, lambda: None, threading.Event())
    assert not legacy.exists()
    assert not list(directory.iterdir())
    assert not script_install.verify_installed_files(root, threading.Event())
    assert isinstance(await update.prepare_update(root, config), str)
    update.download_file.assert_not_awaited()
    assert update.read_install(root) == (Version("2.2.0"), "x86_64")


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
    instance.script_info = SimpleNamespace(script_id="test-script", log="")
    instance.task_info = SimpleNamespace(mode="AutoProxy", task_id="test")
    instance._program_update_prepared = False
    instance._update_candidate = None
    monkeypatch.setattr(manager.MaaEndResourceLoader, "get_cached", Mock())
    monkeypatch.setattr(
        manager, "load_maaend_controller_protocol", lambda *args: "Win32"
    )
    monkeypatch.setattr(manager, "push_dispatch_log", AsyncMock())
    monkeypatch.setattr(manager.Publisher, "send", AsyncMock())
    return instance


@pytest.mark.asyncio
async def test_prefetch_does_not_require_idle_or_change_install(
    installation, monkeypatch
):
    root, config = installation
    original = (root / "interface.json").read_bytes()
    monkeypatch.setattr(
        update, "assert_idle", Mock(side_effect=RuntimeError("running"))
    )
    candidate = await update.prepare_update(root, config)
    assert isinstance(candidate, update.PreparedUpdate)
    assert (root / "interface.json").read_bytes() == original
    assert candidate.destination.is_file()
    assert not (script_install.workspace(root) / "transaction.json").exists()
    with pytest.raises(RuntimeError, match="running"):
        await update.apply_update(root, candidate)
    monkeypatch.setattr(update, "assert_idle", Mock())
    await update.apply_update(root, candidate)
    assert json.loads((root / "interface.json").read_text())["version"] == "v2.2.0"
    assert not candidate.destination.exists()


@pytest.mark.asyncio
async def test_prefetched_candidate_rejects_native_upgrade(installation):
    root, config = installation
    candidate = await update.prepare_update(root, config)
    (root / "interface.json").write_text(
        json.dumps({"name": "MaaEnd", "version": "v2.3.0"})
    )
    try:
        with pytest.raises(ValueError):
            await update.apply_update(root, candidate)
        assert json.loads((root / "interface.json").read_text())["version"] == "v2.3.0"
    finally:
        update.discard_update(candidate)


@pytest.mark.asyncio
async def test_prefetched_candidate_preserves_native_upgrade_during_archive_verify(
    installation, monkeypatch
):
    root, config = installation
    candidate = await update.prepare_update(root, config)
    native = root.parent / "native.zip"
    with zipfile.ZipFile(root.parent / "official.zip") as original:
        with zipfile.ZipFile(native, "w") as archive:
            for name in original.namelist():
                content = original.read(name)
                if name == "interface.json":
                    payload = json.loads(content)
                    payload["version"] = "v2.3.0"
                    content = json.dumps(payload).encode()
                archive.writestr(name, content)
    size = native.stat().st_size
    digest = hashlib.sha256(native.read_bytes()).hexdigest()
    verify = script_install.verify_archive

    def native_upgrade_after_verify(path, *args):
        verify(path, *args)
        if path == candidate.destination:
            # 另一个完整发行包经真实目录切换安装，不伪造私有回执或版本标记。
            script_install.install_package(
                root,
                native,
                size,
                digest,
                update.PROTECTED,
                lambda path: update.read_install(path),
                lambda: update.assert_idle(root),
                threading.Event(),
            )
            assert update.read_install(root)[0] == Version("2.3.0")

    monkeypatch.setattr(script_install, "verify_archive", native_upgrade_after_verify)
    try:
        with pytest.raises(ValueError):
            await update.apply_update(root, candidate)
        assert update.read_install(root)[0] == Version("2.3.0")
        assert script_install.verify_installed_files(root, threading.Event())
        assert (root / "config/mxu-MaaEnd.json").read_bytes() == b'{"user-data": true}'
        assert not (script_install.workspace(root) / "transaction.json").exists()
    finally:
        update.discard_update(candidate)


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
    assert (script_install.record_directory(root) / "installed.json").exists()
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
@pytest.mark.parametrize("download_path", ["destination", "request"])
async def test_unconfirmed_downloader_keeps_its_private_destination(
    installation, monkeypatch, error_type, download_path
):
    root, config = installation

    async def interrupted_download(_url, destination, **_kwargs):
        output = (
            destination.parent / ".mas-fluxdown-test.zip"
            if download_path == "request"
            else destination
        )
        output.write_bytes(b"partial download")
        raise error_type("下载器未确认停止")

    monkeypatch.setattr(
        update, "download_file", AsyncMock(side_effect=interrupted_download)
    )
    with pytest.raises(error_type):
        await update.update_before_run(root, config)
    downloads = list((root.parent / "data/maaend_update").glob("download-*"))
    if error_type is FluxdownCancelUnconfirmed:
        assert len(downloads) == 1
        assert next(downloads[0].iterdir()).read_bytes() == b"partial download"
    else:
        assert not downloads
    assert update.read_install(root)[0] == Version("2.1.0")


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["GitHub", "MirrorChyan", "FluxDown-confirmed"])
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
        update.Config.setting.Update.FluxdownTakeoverAll = (
            source == "FluxDown-confirmed"
        )

    started, stopped = asyncio.Event(), asyncio.Event()

    async def partial_download(_url, destination, **_kwargs):
        output = (
            destination.parent / ".mas-fluxdown-test.zip"
            if source == "FluxDown-confirmed"
            else destination
        )
        output.write_bytes(b"partial ZIP")
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
        (destination.parent / ".mas-fluxdown-test.zip").write_bytes(
            b"unconfirmed FluxDown part"
        )
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise FluxdownCancelUnconfirmed("daemon still writing") from None

    monkeypatch.setattr(
        update, "download_file", AsyncMock(side_effect=partial_fluxdown_download)
    )
    pending = asyncio.create_task(update.update_before_run(root, config))
    await asyncio.wait_for(started.wait(), timeout=5)
    pending.cancel()
    with pytest.raises(FluxdownCancelUnconfirmed):
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
        (script_install.record_directory(root) / "program-identity.json").read_text()
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
    receipt = script_install.record_directory(root) / "installed.json"
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


@pytest.mark.asyncio
async def test_no_update_prefetch_is_rechecked_at_script_start(
    scheduler, installation, monkeypatch
):
    root, _ = installation
    scheduler._update_candidate = "MaaEnd 当前版本无需更新"
    check = AsyncMock(return_value="MaaEnd 当前版本无需更新")
    apply = AsyncMock()
    monkeypatch.setattr(update, "update_before_run", check)
    monkeypatch.setattr(update, "apply_update", apply)
    await scheduler._prepare_program_update(root)
    check.assert_awaited_once()
    apply.assert_not_awaited()


@pytest.mark.asyncio
async def test_maaend_stale_journal_verified_by_public_native_adapter(installation):
    from app.task.MaaEnd.tools.managed_recovery import MaaEndInstallAdapter

    root, config = installation
    work = script_install.workspace(root)
    work.mkdir(parents=True, exist_ok=True)
    marker = work / "transaction.json"
    marker.write_bytes(b"stale-journal")
    adapter = MaaEndInstallAdapter(root, config, takeover_enabled=False)
    state = await adapter.inspect()
    assert state.pending and state.healthy and state.updated_confirmed
    await adapter.acknowledge()
    assert not marker.exists()
    assert list(work.glob("maaend-transaction-ack-*.json"))


@pytest.mark.asyncio
async def test_maaend_old_backup_prevents_journal_bypass(installation):
    from app.task.MaaEnd.tools.managed_recovery import MaaEndInstallAdapter

    root, config = installation
    work = script_install.workspace(root)
    work.mkdir(parents=True, exist_ok=True)
    marker = work / "transaction.json"
    marker.write_bytes(b"stale-journal")
    (work / "previous").mkdir()
    adapter = MaaEndInstallAdapter(root, config, takeover_enabled=True)
    state = await adapter.inspect()
    assert state.pending and not state.healthy
    with pytest.raises(script_install.InstallUnsafeError):
        await adapter.acknowledge()
    assert marker.exists()


@pytest.mark.asyncio
async def test_maaend_bad_exe_stays_blocked_without_frontend(installation):
    from app.task.MaaEnd.tools.managed_recovery import MaaEndInstallAdapter

    root, config = installation
    marker = script_install.workspace(root) / "transaction.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_bytes(b"stale-journal")
    (root / "MaaEnd.exe").write_bytes(b"damaged")
    adapter = MaaEndInstallAdapter(root, config, takeover_enabled=False)
    state = await adapter.inspect()
    assert state.pending and not state.healthy
    assert marker.exists()


@pytest.mark.asyncio
async def test_maaend_repaired_native_build_can_ignore_stale_receipt_without_takeover(
    installation,
):
    from app.task.MaaEnd.tools.managed_recovery import MaaEndInstallAdapter

    root, config = installation
    await update.update_before_run(root, config)
    (root / "interface.json").write_text(
        json.dumps({"name": "MaaEnd", "version": "v2.3.0", "mirrorchyan_rid": "MaaEnd"})
    )
    marker = script_install.workspace(root) / "transaction.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_bytes(b"stale-journal")
    adapter = MaaEndInstallAdapter(root, config, takeover_enabled=False)
    state = await adapter.inspect()
    assert state.pending and state.healthy
    await adapter.acknowledge()
    assert not marker.exists()


async def _interrupt_native_install_after_ready(root: Path, monkeypatch):
    """调用真实原生安装器，在写入 transaction.json 前故障注入。"""
    archive = root.parent / "official.zip"
    original_copytree = script_install.shutil.copytree

    def copy_then_interrupt(source, destination, *args, **kwargs):
        result = original_copytree(source, destination, *args, **kwargs)
        if Path(destination).name == "ready":
            raise OSError("injected failure after ready copy")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(script_install.shutil, "copytree", copy_then_interrupt)
        with pytest.raises(OSError, match="after ready copy"):
            await script_install.run_worker(
                script_install.install_package,
                root,
                archive,
                archive.stat().st_size,
                hashlib.sha256(archive.read_bytes()).hexdigest(),
                update.PROTECTED,
                lambda path: None,
                lambda: None,
            )
    workspace = script_install.workspace(root)
    assert (workspace / "ready").is_dir()
    assert (workspace / "package").is_dir()
    assert not (workspace / "transaction.json").exists()
    assert not (workspace / "previous").exists()


async def _start_real_maaend_manager_for_repair(root: Path, monkeypatch):
    """保留真实 main_task / adapter / #1916 公共恢复层，只截断游戏任务。"""
    from app.models.config import MaaEndConfig

    home = root.parent / "mas-home"
    home.mkdir(exist_ok=True)
    monkeypatch.chdir(home)
    config = MaaEndConfig.model_validate(
        {"Info": {"Path": str(root)}, "Update": {"TakeoverEnabled": True}}
    )
    await config.activate()
    script_id = config.uid
    info = SimpleNamespace(
        task_info=SimpleNamespace(mode="AutoProxy", task_id="test"),
        script_id=str(script_id),
        user_list=[],
        status="等待",
        log="",
        set_log=AsyncMock(),
    )
    instance = manager.MaaEndManager(info)
    instance.check = AsyncMock(return_value="test stop before game startup")
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
    return instance, lock, unlock


@pytest.mark.asyncio
async def test_manager_repairs_damaged_exe_with_no_native_journal_via_common_entry(
    installation, monkeypatch
):
    root, existing_config = installation
    await update.update_before_run(root, existing_config)
    (root / "MaaEnd.exe").write_bytes(b"damaged executable")
    await _interrupt_native_install_after_ready(root, monkeypatch)
    instance, lock, unlock = await _start_real_maaend_manager_for_repair(
        root, monkeypatch
    )
    await instance.main_task()
    assert update.read_install(root) == (Version("2.2.0"), "x86_64")
    assert script_install.verify_installed_files(root, threading.Event())
    assert (root / "config/mxu-MaaEnd.json").read_bytes() == b'{"user-data": true}'
    assert not (script_install.workspace(root) / "ready").exists()
    assert any(
        "reinstalled" in str(call)
        for call in instance.script_info.set_log.await_args_list
    )
    lock.assert_awaited_once()
    await instance.final_task()
    unlock.assert_awaited_once_with("ticket")


@pytest.mark.asyncio
async def test_manager_repairs_native_upgrade_receipt_at_exact_newer_version(
    installation, tmp_path, monkeypatch
):
    root, existing_config = installation
    await update.update_before_run(root, existing_config)
    native_tag = "v2.3.0-beta.1"
    (root / "interface.json").write_text(
        json.dumps(
            {"name": "MaaEnd", "version": native_tag, "mirrorchyan_rid": "MaaEnd"}
        )
    )
    archive, release = _official_release_for_test(tmp_path, native_tag)
    exact = AsyncMock(return_value=release)
    monkeypatch.setattr(update, "request_release_for_version", exact)

    async def download_exact(_url, destination, **_kwargs):
        shutil.copyfile(archive, destination)

    monkeypatch.setattr(update, "download_file", AsyncMock(side_effect=download_exact))
    await _interrupt_native_install_after_ready(root, monkeypatch)
    instance, _, _ = await _start_real_maaend_manager_for_repair(root, monkeypatch)
    await instance.main_task()
    assert not (script_install.workspace(root) / "ready").exists()
    assert update.read_install(root) == (Version(native_tag), "x86_64")
    assert script_install.verify_installed_files(root, threading.Event())
    exact.assert_awaited_once_with(Version(native_tag), native_tag)
    await instance.final_task()


@pytest.mark.asyncio
async def test_manager_recovers_ready_left_before_native_journal(
    installation, monkeypatch
):
    """真实安装器完成 ready 复制后异常，下一轮真实 manager 可安全清理重跑。"""
    root, config = installation
    await update.update_before_run(root, config)
    original_version = update.read_install(root)
    archive = root.parent / "official.zip"
    candidate = update.PreparedUpdate(
        root.resolve(),
        original_version,
        original_version[0],
        original_version[1],
        archive,
        archive.stat().st_size,
        hashlib.sha256(archive.read_bytes()).hexdigest(),
    )
    original_copytree = script_install.shutil.copytree

    def fail_after_ready(*args, **kwargs):
        result = original_copytree(*args, **kwargs)
        if Path(args[1]).name == "ready":
            raise OSError("interrupted after ready copy, before transaction")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(script_install.shutil, "copytree", fail_after_ready)
        with pytest.raises(OSError, match="before transaction"):
            await update.apply_update(root, candidate)

    work = script_install.workspace(root)
    assert (work / "ready").is_dir()
    assert (work / "package").is_dir()
    assert not (work / "transaction.json").exists()
    assert not (work / "previous").exists()
    assert update.read_install(root) == original_version
    assert script_install.verify_installed_files(root, threading.Event())
    instance, _, unlock = await _start_real_maaend_manager_for_repair(root, monkeypatch)
    await instance.main_task()
    assert not (work / "ready").exists()
    assert not (work / "package").exists()
    assert update.read_install(root) == original_version
    assert script_install.verify_installed_files(root, threading.Event())
    await instance.final_task()
    unlock.assert_awaited_once_with("ticket")


@pytest.mark.asyncio
async def test_maaend_precommit_cleanup_preserves_previous_and_invalid_original(
    installation,
):
    from app.task.MaaEnd.tools.managed_recovery import MaaEndInstallAdapter

    root, config = installation
    await update.update_before_run(root, config)
    work = script_install.workspace(root)
    work.mkdir(parents=True, exist_ok=True)
    (work / "ready").mkdir()
    (work / "previous").mkdir()
    adapter = MaaEndInstallAdapter(root, config, takeover_enabled=True)
    with pytest.raises(script_install.InstallUnsafeError, match="备份存在"):
        await adapter.recover_native()
    assert (work / "ready").exists() and (work / "previous").exists()

    (work / "previous").rmdir()
    (root / "MaaEnd.exe").write_bytes(b"damaged")
    with pytest.raises((OSError, ValueError, script_install.InstallUnsafeError)):
        await adapter.recover_native()
    assert (work / "ready").exists()
    assert not (work / "transaction.json").exists()


@pytest.mark.asyncio
async def test_precommit_staging_repair_requires_trusted_identity(
    installation, monkeypatch
):
    from app.task.MaaEnd.tools.managed_recovery import MaaEndInstallAdapter

    root, config = installation
    await update.update_before_run(root, config)
    (root / "MaaEnd.exe").write_bytes(b"damaged")
    await _interrupt_native_install_after_ready(root, monkeypatch)
    script_install.record_path(root, "program-identity.json").unlink()
    adapter = MaaEndInstallAdapter(
        root,
        config,
        takeover_enabled=True,
        allow_damaged_repair=True,
    )
    with pytest.raises(script_install.InstallUnsafeError, match="可信 MAS 身份"):
        await adapter.recover_native()
    assert (script_install.workspace(root) / "ready").exists()
    assert (root / "MaaEnd.exe").read_bytes() == b"damaged"
