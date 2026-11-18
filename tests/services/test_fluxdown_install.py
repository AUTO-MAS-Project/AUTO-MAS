"""FluxDown 安装安全边界与失败恢复回归；不联网、不执行下载的程序。"""

import hashlib
import os
import stat
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.api import update as api
from app.services.common.update import fluxdown_install as install
from app.utils import fluxdown_cli as cli


@pytest.fixture(autouse=True)
def windows_fluxdown_layout(monkeypatch):
    """用固定组件名隔离宿主平台，测试安装、解包与恢复边界。"""
    monkeypatch.setattr(
        install.update_native,
        "FLUXDOWN_EXE_NAMES",
        ("fluxdown.exe", "fluxdown-cli.exe"),
    )
    monkeypatch.setattr(
        install.update_native, "FLUXDOWN_AGENT_NAME", "fluxdown-agent.exe"
    )
    monkeypatch.setattr(install.update_native, "FLUXDOWN_DAEMON_NAME", "fluxdownd.exe")
    monkeypatch.setattr(
        cli, "_FLUXDOWN_EXE_NAMES", ("fluxdown.exe", "fluxdown-cli.exe")
    )


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


def test_zip_roundtrip_and_escape(tmp_path):
    archive = tmp_path / "package.zip"
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside user data")
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("package/bin/fluxdown.exe", b"ok")
    target = tmp_path / "out"
    install._extract_zip(archive, target)
    assert (target / "bin/fluxdown.exe").read_bytes() == b"ok"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("normal.exe", b"normal")
        bundle.writestr("../outside", b"bad")
    with pytest.raises(RuntimeError):
        install._extract_zip(archive, target)
    assert not (target / "normal.exe").exists()
    assert outside.read_bytes() == b"outside user data"


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
    backup = target.with_name("bin.old")
    assert not target.exists()
    assert (backup / "fluxdown.exe").read_bytes() == b"old binary"
    with pytest.raises(OSError):
        install._install_from(extracted)
    assert not target.exists()
    assert (backup / "fluxdown.exe").read_bytes() == b"old binary"
    assert (backup / "portable_data/db").read_bytes() == b"user data"
    monkeypatch.setattr(install.os, "replace", original)
    assert install._install_from(extracted) == target
    for name in install._REQUIRED_BINARIES:
        assert (target / name).read_bytes() == b"new binary"
    assert (target / "portable_data/db").read_bytes() == b"user data"
    assert (target / "portable").is_file()
    assert not backup.exists()
    assert not target.with_name("bin.new").exists()


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
@pytest.mark.parametrize(
    "client,host,origin,allowed",
    [
        ("192.168.1.2", "localhost", None, False),
        ("127.0.0.1", "attacker.test", None, False),
        ("127.0.0.1", "localhost", "https://attacker.test", False),
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
    "server_token,provided",
    [
        ("test-install-session-token", None),
        ("test-install-session-token", "Bearer stale-session"),
        (None, "Bearer "),
    ],
)
async def test_install_requires_session_authorization(
    server_token, provided, monkeypatch
):
    app = FastAPI()
    app.include_router(api.router)
    if server_token is None:
        monkeypatch.delenv("AUTO_MAS_INSTALL_TOKEN", raising=False)
    else:
        monkeypatch.setenv("AUTO_MAS_INSTALL_TOKEN", server_token)
    installer = AsyncMock()
    monkeypatch.setattr(api._fluxdown_install, "install_fluxdown", installer)
    headers = {"host": "localhost"}
    if provided is not None:
        headers["authorization"] = provided
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 123)),
        base_url="http://localhost",
    ) as session:
        response = await session.post(
            "/api/update/fluxdown/install", json={"mirror": "auto"}, headers=headers
        )
    assert response.status_code == 403
    installer.assert_not_awaited()


def test_tar_install_rejects_traversal_without_changing_external_files(tmp_path):
    import io
    import tarfile

    package = tmp_path / "FluxDown-CLI.tar.gz"
    with tarfile.open(package, "w:gz") as archive:
        folder = tarfile.TarInfo("release")
        folder.type = tarfile.DIRTYPE
        archive.addfile(folder)
        member = tarfile.TarInfo("release/fluxdown")
        member.size = len(b"binary")
        member.mode = 0o755
        archive.addfile(member, io.BytesIO(b"binary"))

    install._check_package(package, {"fluxdown"}, {"fluxdown-agent"})
    out = tmp_path / "out"
    install._extract_package(package, out)
    assert (out / "fluxdown").read_bytes() == b"binary"
    if os.name != "nt":
        assert (out / "fluxdown").stat().st_mode & 0o111

    invalid = tmp_path / "wrong.tar.gz"
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside user data")
    with tarfile.open(invalid, "w:gz") as archive:
        member = tarfile.TarInfo("../outside")
        member.size = 1
        archive.addfile(member, io.BytesIO(b"X"))
    with pytest.raises(RuntimeError):
        install._extract_package(invalid, tmp_path / "bad")
    assert outside.read_bytes() == b"outside user data"
