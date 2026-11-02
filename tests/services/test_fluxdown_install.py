"""FluxDown 安装安全边界与失败恢复回归；不联网、不执行下载的程序。"""

import asyncio
import hashlib
import os
import stat
import threading
import zipfile
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.api import update as api
from app.models.config import GlobalConfig
from app.services.common.update import fluxdown_install as install
from app.services.common.update import transport as transport
from app.utils import fluxdown_cli as cli
from tests.config_support import activate_config


@pytest.fixture
def release():
    return install.FluxdownRelease(
        version="0.6.3",
        tag="v0.6.3",
        arch="x64",
        cli_name="cli.zip",
        server_name="server.zip",
        cli_url="",
        server_url="",
        cli_sha256="a" * 64,
        server_sha256="b" * 64,
    )


@pytest.fixture
def packages(tmp_path, monkeypatch, isolated_app_paths):
    monkeypatch.chdir(tmp_path)
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    for name in install._REQUIRED_BINARIES:
        (extracted / name).write_bytes(b"new binary")
    target = install._install_dir()
    target.mkdir(parents=True)
    (target / "fluxdown.exe").write_bytes(b"old binary")
    (target / "portable_data").mkdir()
    (target / "portable_data" / "db").write_bytes(b"user data")
    return extracted, target


@pytest.mark.parametrize(
    "name",
    [
        "C:/outside.exe",
        "C:outside.exe",
        "root/C:/outside.exe",
        "root/C:outside.exe",
        r"\\server\share\file",
        r"\rooted",
        "/absolute",
        "../up",
        r"a\..\up",
        "root/file:stream",
        "root/CON",
        "root/dir. /file",
        "root/dir./file",
    ],
)
def test_reject_windows_paths(name):
    with pytest.raises(RuntimeError):
        install._safe_parts(name)


def test_windows_drive_resets_join():
    # PureWindowsPath 在非 Windows CI 也能重现原校验与落点的语义差异。
    escaped = PureWindowsPath("C:/staging").joinpath("D:", "payload.exe")
    assert not escaped.is_relative_to(PureWindowsPath("C:/staging"))


def test_zip_roundtrip_and_escape(tmp_path):
    archive = tmp_path / "package.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("package/bin/fluxdown.exe", b"ok")
    target = tmp_path / "out"
    install._extract_zip(archive, target)
    assert (target / "bin/fluxdown.exe").read_bytes() == b"ok"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("normal.exe", b"normal")
        bundle.writestr("D:/escaped.exe", b"bad")
    with pytest.raises(RuntimeError):
        install._extract_zip(archive, target)
    assert not (target / "normal.exe").exists()


def test_zip_symlink_and_limits(tmp_path, monkeypatch):
    archive = tmp_path / "package.zip"
    info = zipfile.ZipInfo("link")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(info, "../outside")
    with pytest.raises(RuntimeError):
        install._extract_zip(archive, tmp_path / "out")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("file", b"0" * 100)
    monkeypatch.setattr(install, "_MAX_EXTRACTED_BYTES", 50)
    with pytest.raises(RuntimeError):
        install._extract_zip(archive, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_install_preserves_data(packages):
    extracted, target = packages
    assert install._install_from(extracted) == target
    assert (target / "fluxdown.exe").read_bytes() == b"new binary"
    assert (target / "portable_data/db").read_bytes() == b"user data"
    assert (target / "portable").is_file()
    assert not target.with_name("fluxdown-cli.old").exists()


def test_replace_failure_rolls_back(packages, monkeypatch):
    extracted, target = packages
    original = os.replace

    def fail_publish(source, destination):
        if Path(source).name.endswith(".new"):
            raise OSError("publish failed")
        return original(source, destination)

    monkeypatch.setattr(install.os, "replace", fail_publish)
    with pytest.raises(RuntimeError):
        install._install_from(extracted)
    assert (target / "fluxdown.exe").read_bytes() == b"old binary"
    assert (target / "portable_data/db").read_bytes() == b"user data"


def test_rollback_failure_survives_retry(packages, monkeypatch):
    extracted, target = packages
    original = os.replace

    def fail(source, destination):
        if Path(source).name.endswith((".new", ".old")):
            raise OSError("unavailable")
        return original(source, destination)

    monkeypatch.setattr(install.os, "replace", fail)
    with pytest.raises(RuntimeError):
        install._install_from(extracted)
    backup = target.with_name("fluxdown-cli.old")
    assert (backup / "fluxdown.exe").read_bytes() == b"old binary"
    with pytest.raises(OSError):
        install._install_from(extracted)
    assert (backup / "portable_data/db").read_bytes() == b"user data"
    monkeypatch.setattr(install.os, "replace", original)
    install._install_from(extracted)
    assert (target / "portable_data/db").read_bytes() == b"user data"


@pytest.mark.parametrize(
    "digest", [None, "", "sha256:xyz", "sha256:" + "a" * 63, "md5:" + "a" * 64]
)
def test_invalid_digest(digest):
    assert install._asset_sha256({"digest": digest}) is None


@pytest.mark.asyncio
async def test_trusted_metadata_only(monkeypatch):
    original = httpx.AsyncClient
    urls = []

    def handle(request):
        urls.append(str(request.url))
        return httpx.Response(503)

    monkeypatch.setattr(
        install.httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handle), **kw),
    )
    with pytest.raises(RuntimeError):
        await install._fetch_release_payload(None)
    assert urls == [install._GITHUB_API_LATEST]


@pytest.mark.asyncio
async def test_hash_required_and_mirror_fallback(release, tmp_path, monkeypatch):
    contents = b"valid package"
    downloader = AsyncMock()
    monkeypatch.setattr(install, "download_file", downloader)
    with pytest.raises(RuntimeError):
        await install._download_asset(release, "cli.zip", None, "auto", tmp_path, None)
    downloader.assert_not_called()
    attempts = []

    async def download(url, destination, **kwargs):
        attempts.append(url)
        destination.write_bytes(b"tampered" if len(attempts) == 1 else contents)

    monkeypatch.setattr(install, "download_file", download)
    size = await install._download_asset(
        release, "cli.zip", hashlib.sha256(contents).hexdigest(), "auto", tmp_path, None
    )
    assert size == len(contents)
    assert len(attempts) == 2
    assert (tmp_path / "cli.zip").read_bytes() == contents


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [{"Content-Length": "999"}, {}])
async def test_bounded_download(tmp_path, monkeypatch, headers):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        transport.httpx,
        "AsyncClient",
        lambda **kw: original(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, headers=headers, content=b"x" * 50)
            ),
            **kw,
        ),
    )
    destination = tmp_path / "asset"
    with pytest.raises(ValueError):
        await transport.download_file(
            "https://example.test/a", destination, timeout=1, max_bytes=10
        )
    assert not destination.exists() or destination.stat().st_size <= 10


@pytest.mark.asyncio
async def test_download_install_exclusion(monkeypatch):
    started, finish = asyncio.Event(), asyncio.Event()

    @cli._using_fluxdown
    async def download():
        started.set()
        await finish.wait()

    task = asyncio.create_task(download())
    await started.wait()
    shutdown = AsyncMock()
    monkeypatch.setattr(cli, "fluxdown_server_shutdown", shutdown)
    with pytest.raises(RuntimeError):
        with cli.fluxdown_install_guard():
            pytest.fail("must not install during download")
    shutdown.assert_not_called()
    finish.set()
    await task
    monkeypatch.setattr(cli, "fluxdown_server_shutdown", lambda: None)
    with cli.fluxdown_install_guard():
        with pytest.raises(RuntimeError):
            await download()
    assert cli._active_downloads == 0


def test_foreign_agent_not_killed(monkeypatch):
    monkeypatch.setattr(cli._server, "handle", object())
    monkeypatch.setattr(cli._server, "spawned_by_us", False)
    with pytest.raises(RuntimeError):
        with cli.fluxdown_install_guard():
            pytest.fail("foreign agent must block replacement")
    assert cli._server.handle is not None
    assert not cli._installing


@pytest.mark.asyncio
async def test_cancel_keeps_lock_until_worker_finishes(monkeypatch):
    started, finish = threading.Event(), threading.Event()

    def worker():
        started.set()
        finish.wait(5)

    async def installation(*args):
        await asyncio.to_thread(worker)
        return {}

    monkeypatch.setattr(install, "_install_locked", installation)
    monkeypatch.setattr(install.update_native, "supports_fluxdown_install", True)
    task = asyncio.create_task(install.install_fluxdown())
    await asyncio.to_thread(started.wait, 5)
    task.cancel()
    await asyncio.sleep(0)
    assert install._install_lock.locked()
    with pytest.raises(RuntimeError):
        await install.install_fluxdown()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not install._install_lock.locked()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client,host,origin,allowed",
    [
        ("192.168.1.2", "localhost", None, False),
        ("127.0.0.1", "attacker.test", None, False),
        ("127.0.0.1", "localhost", "http://[invalid", False),
        ("127.0.0.1", "localhost", "ftp://localhost", False),
        ("127.0.0.1", "localhost", "https://attacker.test", False),
        ("127.0.0.1", "127.0.0.1:36164", None, True),
        ("127.0.0.1", "127.0.0.1:36164", "http://localhost:5173", True),
        ("::1", "[::1]:36164", "null", True),
    ],
)
async def test_local_install_route(client, host, origin, allowed, monkeypatch):
    app = FastAPI()
    app.include_router(api.router)
    monkeypatch.setenv("AUTO_MAS_INSTALL_TOKEN", "test-install-session-token")
    installer = AsyncMock(return_value={"version": "0.6.3", "path": "installed"})
    monkeypatch.setattr(api._fluxdown_install, "install_fluxdown", installer)
    headers = {"host": host, "authorization": "Bearer test-install-session-token"}
    if origin is not None:
        headers["origin"] = origin
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=(client, 123)),
        base_url="http://localhost",
    ) as session:
        response = await session.post(
            "/api/update/fluxdown/install", json={"mirror": "auto"}, headers=headers
        )
    assert response.status_code == (200 if allowed else 403)
    assert installer.await_count == int(allowed)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change_path,fail_save", [(False, False), (True, False), (False, True)]
)
async def test_full_install_and_config(
    release, tmp_path, monkeypatch, change_path, fail_save
):
    monkeypatch.chdir(tmp_path)
    config = GlobalConfig.build()
    await activate_config(config)
    flush = AsyncMock(side_effect=OSError("disk full") if fail_save else None)
    monkeypatch.setattr(
        install,
        "Config",
        SimpleNamespace(setting=config, flush=flush, data_path=tmp_path / "data"),
    )
    monkeypatch.setattr(
        install, "fetch_latest_release", AsyncMock(return_value=release)
    )

    async def download(release, name, *args):
        work = args[2]
        with zipfile.ZipFile(work / name, "w") as bundle:
            names = (
                ["fluxdown.exe"]
                if name == release.cli_name
                else ["fluxdown-agent.exe", "fluxdownd.exe"]
            )
            for binary in names:
                bundle.writestr("package/" + binary, b"new binary")
        if change_path:
            await config.update(
                type(config).model_validate(
                    {"Update": {"FluxdownPath": "user-choice"}}
                ),
                check_visibility=False,
            )
        return 100

    monkeypatch.setattr(install, "_download_asset", download)
    monkeypatch.setattr(cli, "fluxdown_server_shutdown", lambda: None)
    if change_path or fail_save:
        with pytest.raises(RuntimeError, match="文件已安装"):
            await install._install_locked("auto", None)
    else:
        result = await install._install_locked("auto", None)
        assert Path(result["path"]) == install._install_dir()
        assert Path(config.Update.FluxdownPath) == install._install_dir()
        flush.assert_awaited_once()
    assert (install._install_dir() / "portable").is_file()
    assert not (tmp_path / "data/fluxdown_install_tmp").exists()
    if change_path:
        assert str(config.Update.FluxdownPath) == "user-choice"


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", [None, "null", "http://localhost:5173"])
@pytest.mark.parametrize(
    "provided", [None, "Bearer stale-session", "Bearer ", "Bearer 非法"]
)
async def test_install_requires_session_authorization(origin, provided, monkeypatch):
    app = FastAPI()
    app.include_router(api.router)
    monkeypatch.setenv("AUTO_MAS_INSTALL_TOKEN", "test-install-session-token")
    installer = AsyncMock()
    monkeypatch.setattr(api._fluxdown_install, "install_fluxdown", installer)
    headers = {"host": "localhost"}
    if origin is not None:
        headers["origin"] = origin
    if provided is not None:
        headers["authorization"] = provided
    # httpx 编码头部不接受非 ASCII；原始字节覆盖恶意编码不会导致服务端异常。
    raw_headers = [(k.encode(), v.encode()) for k, v in headers.items()]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 123)),
        base_url="http://localhost",
    ) as session:
        response = await session.post(
            "/api/update/fluxdown/install", json={"mirror": "auto"}, headers=raw_headers
        )
    assert response.status_code == 403
    installer.assert_not_awaited()


@pytest.mark.asyncio
async def test_install_fails_closed_when_not_started_by_desktop(monkeypatch):
    app = FastAPI()
    app.include_router(api.router)
    monkeypatch.delenv("AUTO_MAS_INSTALL_TOKEN", raising=False)
    installer = AsyncMock()
    monkeypatch.setattr(api._fluxdown_install, "install_fluxdown", installer)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 123)),
        base_url="http://localhost",
    ) as session:
        response = await session.post(
            "/api/update/fluxdown/install",
            json={"mirror": "auto"},
            headers={"authorization": "Bearer guessed"},
        )
    assert response.status_code == 403
    installer.assert_not_awaited()
