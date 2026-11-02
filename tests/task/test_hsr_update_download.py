"""HSR 下载复用公共分发与代理，并保留内置 HTTP 续传。"""

import hashlib
from unittest.mock import AsyncMock

import httpx
import pytest

from app.task.HSR.tools.update import download
from app.task.HSR.tools.update.discover import HSRUpdateError, UpdateCandidate
from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "engine,source", [("M7A", "GitHub"), ("SRA", "AutoSite"), ("SRA", "MirrorChyan")]
)
async def test_package_uses_shared_downloader_and_verifies_before_publish(
    tmp_path, monkeypatch, engine, source
):
    data = b"script release bytes"
    candidate = UpdateCandidate(
        engine,
        "1.0",
        "2.0",
        source,
        "zip",
        "https://example.invalid/update",
        hashlib.sha256(data).hexdigest(),
    )
    proxy = httpx.Proxy("http://127.0.0.1:7890")
    progress = []

    async def fetch(url, path, **kwargs):
        assert kwargs["proxy"] is proxy
        assert kwargs["source"] == source
        assert kwargs["http_download"] is download._httpx_fetch
        path.write_bytes(data)
        await kwargs["progress"](len(data), len(data), 0)
        return len(data)

    monkeypatch.setattr(download, "download_script_package", fetch)
    target = tmp_path / "release.zip"
    assert (
        await download.download_package(
            candidate,
            target,
            proxy=proxy,
            progress=lambda done, total: progress.append((done, total)),
        )
        == target
    )
    assert target.read_bytes() == data
    assert progress[-1] == (len(data), len(data))


@pytest.mark.asyncio
async def test_unconfirmed_background_write_is_not_retried_or_deleted(
    tmp_path, monkeypatch
):
    target = tmp_path / "release.zip"
    partial = target.with_suffix(".zip.part")
    partial.write_bytes(b"in progress")
    error = FluxdownCancelUnconfirmed("writer still active")
    fetch = AsyncMock(side_effect=error)
    monkeypatch.setattr(download, "download_script_package", fetch)
    candidate = UpdateCandidate(
        "M7A", "1.0", "2.0", "GitHub", "zip", "https://example.invalid/update"
    )
    with pytest.raises(FluxdownCancelUnconfirmed):
        await download.download_package(candidate, target)
    assert fetch.await_count == 1
    assert partial.read_bytes() == b"in progress"
    assert not target.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 206])
async def test_builtin_http_preserves_safe_resume(tmp_path, monkeypatch, status):
    target = tmp_path / "download.part"
    target.write_bytes(b"abc")
    proxy = httpx.Proxy("http://127.0.0.1:7890")

    def respond(request):
        assert request.headers["Range"] == "bytes=3-"
        headers = {"Content-Range": "bytes 3-5/6"} if status == 206 else {}
        return httpx.Response(
            status, headers=headers, content=b"def" if status == 206 else b"abcdef"
        )

    original_client = httpx.AsyncClient

    def client(**kwargs):
        assert kwargs["proxy"] is proxy
        return original_client(transport=httpx.MockTransport(respond))

    monkeypatch.setattr(download.httpx, "AsyncClient", client)
    assert (
        await download._httpx_fetch(
            "https://example.invalid/update", target, timeout=30, proxy=proxy
        )
        == 6
    )
    assert target.read_bytes() == b"abcdef"


@pytest.mark.asyncio
async def test_wrong_resume_range_never_changes_existing_bytes(tmp_path, monkeypatch):
    target = tmp_path / "download.part"
    target.write_bytes(b"abc")
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        download.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    206, headers={"Content-Range": "bytes 0-2/6"}, content=b"bad"
                )
            )
        ),
    )
    with pytest.raises(HSRUpdateError):
        await download._httpx_fetch(
            "https://example.invalid/update", target, timeout=30
        )
    assert target.read_bytes() == b"abc"


def test_cache_identity_isolates_sources_and_downloaders(tmp_path, monkeypatch):
    from app.task.HSR.tools import update as updater
    from app.task.HSR.tools.update.engines import M7A

    def candidate(source, url, version="v2.0"):
        return UpdateCandidate("M7A", "v1.0", version, source, "zip", url)

    first = candidate("GitHub", "https://github.example/v2.0/a.zip")
    alternate_url = candidate("GitHub", "https://github.example/v2.0/b.zip")
    other_source = candidate("MirrorChyan", first.download_url)
    monkeypatch.setattr(updater, "script_downloader", lambda source: "fluxdown")
    flux = updater._cache_package_path(tmp_path, M7A, first, None)
    assert flux != updater._cache_package_path(tmp_path, M7A, alternate_url, None)
    assert flux != updater._cache_package_path(tmp_path, M7A, other_source, None)
    monkeypatch.setattr(updater, "script_downloader", lambda source: "builtin")
    builtin = updater._cache_package_path(tmp_path, M7A, first, None)
    assert builtin != flux
    assert builtin == updater._cache_package_path(tmp_path, M7A, first, None)
    assert builtin.parent == tmp_path

    dangerous = candidate("GitHub", "https://github.example/a.zip", "../../escape")
    assert (
        updater._cache_package_path(tmp_path, M7A, dangerous, None).parent == tmp_path
    )


@pytest.mark.asyncio
async def test_fluxdown_resumable_errors_keep_partial_and_exception(
    tmp_path, monkeypatch
):
    from app.services.common.update.fluxdown import FluxdownResumableError

    target = tmp_path / "release.zip"
    partial = target.with_suffix(".zip.part")
    partial.write_bytes(b"resumable fragment")
    fetch = AsyncMock(side_effect=FluxdownResumableError("daemon status unknown"))
    monkeypatch.setattr(download, "download_script_package", fetch)
    monkeypatch.setattr(download.asyncio, "sleep", AsyncMock())
    candidate = UpdateCandidate(
        "M7A", "1.0", "2.0", "GitHub", "zip", "https://example.invalid/update"
    )
    with pytest.raises(FluxdownResumableError):
        await download.download_package(candidate, target)
    assert fetch.await_count == download._RETRIES
    assert partial.read_bytes() == b"resumable fragment"
    assert not target.exists()


def test_unknown_local_version_still_rejects_invalid_remote_version():
    from app.task.HSR.tools.update.discover import is_newer

    assert not is_newer("../../outside", None)
    assert not is_newer("not-a-version", None)
    assert is_newer("v2.0", None)
