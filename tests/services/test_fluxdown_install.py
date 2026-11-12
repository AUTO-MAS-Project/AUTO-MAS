"""FluxDown 安装安全边界与失败恢复回归；不联网、不执行下载的程序。"""

import asyncio
import hashlib
import os
import stat
import threading
import zipfile
from pathlib import Path
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


@pytest.fixture(autouse=True)
def windows_fluxdown_layout(monkeypatch):
    """平台无关 CI 模拟 Windows 组件名，跨平台分发另有专门用例。"""
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


@pytest.mark.asyncio
async def test_save_external_install_while_managed_install_is_complete(
    tmp_path, monkeypatch
):
    """自动推荐 MAS 托管目录时，已补齐的外部目标仍能成功保存。"""
    monkeypatch.chdir(tmp_path)
    managed = tmp_path / "data" / "fluxdown" / "bin"
    external = tmp_path / "user-fluxdown"
    for directory in (managed, external):
        directory.mkdir(parents=True)
        for name in install._REQUIRED_BINARIES:
            (directory / name).write_bytes(b"binary")
    (managed / "portable").touch()
    monkeypatch.setattr(cli, "_candidate_drives", lambda: [])
    monkeypatch.setattr(cli, "_scan_drives", lambda *args, **kwargs: [])
    assert cli.fluxdown_detect(str(external), managed_dir=managed)["path"] == str(
        managed
    )

    config = GlobalConfig.build()
    await activate_config(config)
    await config.update(
        type(config).model_validate({"Update": {"FluxdownPath": str(external)}}),
        check_visibility=False,
    )
    flush = AsyncMock()
    monkeypatch.setattr(
        install,
        "Config",
        SimpleNamespace(setting=config, flush=flush, data_path=tmp_path / "data"),
    )
    progress = AsyncMock()
    monkeypatch.setattr(install, "_report_install_progress", progress)
    result = await install._save_path(
        str(external), external, version="existing", cli_size=0, server_size=0
    )
    assert result["path"] == str(external)
    assert config.Update.FluxdownPath == str(external)
    flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_external_install_rejects_missing_components(tmp_path, monkeypatch):
    """定向安装校验仍须拒绝缺失组件的目录。"""
    external = tmp_path / "external"
    external.mkdir()
    (external / "fluxdown.exe").write_bytes(b"binary")
    with pytest.raises(RuntimeError, match="Server"):
        await install._save_path(
            str(external), external, version="existing", cli_size=0, server_size=0
        )


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
    assert not target.with_name("bin.old").exists()


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
    backup = target.with_name("bin.old")
    assert (backup / "fluxdown.exe").read_bytes() == b"old binary"
    with pytest.raises(OSError):
        install._install_from(extracted)
    assert (backup / "portable_data/db").read_bytes() == b"user data"
    monkeypatch.setattr(install.os, "replace", original)
    install._install_from(extracted)
    assert (target / "portable_data/db").read_bytes() == b"user data"


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
    # 本用例验证全新托管安装；桌面版复用另有覆盖，不扫描开发机已有安装。
    if change_path or fail_save:
        with pytest.raises(RuntimeError, match="文件已安装"):
            await install._install_locked("auto", None, force_managed=True)
    else:
        result = await install._install_locked("auto", None, force_managed=True)
        assert Path(result["path"]) == install._install_dir()
        assert Path(config.Update.FluxdownPath) == install._install_dir()
        flush.assert_awaited_once()
    assert (install._install_dir() / "portable").is_file()
    assert not (tmp_path / "data/fluxdown/install_tmp").exists()
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


@pytest.mark.parametrize(
    "system,machine,expected",
    [
        ("Windows", "AMD64", ("windows", "x64", "zip")),
        ("Windows", "ARM64", ("windows", "arm64", "zip")),
        ("Linux", "x86_64", ("linux", "x64", "tar.gz")),
        ("Linux", "aarch64", ("linux", "arm64", "tar.gz")),
        ("Darwin", "x86_64", ("macos", "x64", "tar.gz")),
        ("Darwin", "arm64", ("macos", "arm64", "tar.gz")),
    ],
)
def test_platform_asset_names(system, machine, expected, monkeypatch):
    monkeypatch.setattr(install.platform, "system", lambda: system)
    monkeypatch.setattr(install.platform, "machine", lambda: machine)
    assert install._platform_asset() == expected
    platform_name, arch, extension = expected
    payload = {
        "tag_name": "v0.6.6",
        "assets": [
            {
                "name": f"FluxDown-{part}-0.6.6-{platform_name}-{arch}.{extension}",
                "browser_download_url": f"https://github.com/zerx-lab/FluxDown/releases/download/v0.6.6/FluxDown-{part}-0.6.6-{platform_name}-{arch}.{extension}",
                "digest": "sha256:" + "a" * 64,
            }
            for part in ("CLI", "Server")
        ],
    }
    result = install._parse_release(payload)
    assert result.cli_name in {a["name"] for a in payload["assets"]}
    assert result.server_name in {a["name"] for a in payload["assets"]}


@pytest.mark.parametrize("system,machine", [("Windows", "x86"), ("FreeBSD", "amd64")])
def test_unknown_platform_never_downloads_other_arch(system, machine, monkeypatch):
    monkeypatch.setattr(install.platform, "system", lambda: system)
    monkeypatch.setattr(install.platform, "machine", lambda: machine)
    with pytest.raises(RuntimeError, match="不支持"):
        install._platform_asset()


def test_wrong_zip_asset_fails_before_extraction(tmp_path):
    archive = tmp_path / "FluxDown-CLI.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("fluxdown/fluxdown-desktop.exe", b"desktop")
        bundle.writestr("fluxdown/fluxdown-agent.exe", b"agent")
    with pytest.raises(RuntimeError, match="错误的发布包"):
        install._check_package(
            archive,
            {"fluxdown.exe"},
            {"fluxdown-agent.exe", "fluxdownd.exe", "fluxdown-desktop.exe"},
        )


def test_valid_zip_asset_and_co_located_extraction(tmp_path):
    first = tmp_path / "FluxDown-CLI.zip"
    second = tmp_path / "FluxDown-Server.zip"
    for archive, names in (
        (first, ("fluxdown.exe",)),
        (second, ("fluxdown-agent.exe", "fluxdownd.exe")),
    ):
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("release/", b"")
            for name in names:
                bundle.writestr("release/" + name, name.encode())
    install._check_package(
        first, {"fluxdown.exe"}, {"fluxdown-agent.exe", "fluxdownd.exe"}
    )
    install._check_package(
        second, {"fluxdown-agent.exe", "fluxdownd.exe"}, {"fluxdown.exe"}
    )
    directory = tmp_path / "combined"
    install._extract_package(first, directory)
    install._extract_package(second, directory)
    install._assert_complete_install(directory)


def test_tar_packages_and_reject_links(tmp_path):
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
    with tarfile.open(invalid, "w:gz") as archive:
        member = tarfile.TarInfo("../outside")
        member.size = 1
        archive.addfile(member, io.BytesIO(b"X"))
    with pytest.raises(RuntimeError):
        install._extract_package(invalid, tmp_path / "bad")


def test_components_requires_cli_and_both_server_programs(tmp_path):
    desktop = tmp_path / "desktop"
    desktop.mkdir()
    (desktop / "fluxdown-desktop.exe").write_bytes(b"gui")
    (desktop / "fluxdown-agent.exe").write_bytes(b"agent")
    (desktop / "fluxdownd.exe").write_bytes(b"daemon")
    state = cli.fluxdown_components(desktop)
    assert not state["cli"]
    assert state["server"]
    (desktop / "fluxdown.exe").write_bytes(b"cli")
    assert cli.fluxdown_components(desktop)["cli"]
    (desktop / "fluxdownd.exe").unlink()
    assert not cli.fluxdown_components(desktop)["server"]


def test_add_missing_cli_to_existing_desktop_never_overwrites_server(tmp_path):
    target = tmp_path / "desktop"
    target.mkdir()
    (target / "fluxdown-desktop.exe").write_bytes(b"gui")
    (target / "fluxdown-agent.exe").write_bytes(b"original")
    (target / "fluxdownd.exe").write_bytes(b"original")
    archive = tmp_path / "extract"
    archive.mkdir()
    (archive / "fluxdown.exe").write_bytes(b"downloaded cli")
    install._install_missing_to_existing(archive, target)
    assert (target / "fluxdown.exe").read_bytes() == b"downloaded cli"
    assert (target / "fluxdown-agent.exe").read_bytes() == b"original"
    assert (target / "fluxdownd.exe").read_bytes() == b"original"


def test_existing_desktop_copy_failure_does_not_poison_retry(tmp_path, monkeypatch):
    target = tmp_path / "desktop"
    target.mkdir()
    (target / "fluxdown-desktop.exe").write_bytes(b"gui")
    (target / "fluxdown-agent.exe").write_bytes(b"original agent")
    (target / "fluxdownd.exe").write_bytes(b"original daemon")
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    (extracted / "fluxdown.exe").write_bytes(b"new CLI")
    original = install.shutil.copy2
    failed = False

    def partial_copy(source, destination, *args, **kwargs):
        nonlocal failed
        if not failed and str(destination).endswith(".mas-install"):
            failed = True
            Path(destination).write_bytes(b"partial")
            raise OSError("disk full")
        return original(source, destination, *args, **kwargs)

    monkeypatch.setattr(install.shutil, "copy2", partial_copy)
    with pytest.raises(OSError, match="disk full"):
        install._install_missing_to_existing(extracted, target)
    assert not list(target.glob(".*.mas-install"))
    assert not (target / "fluxdown.exe").exists()
    assert (target / "fluxdown-agent.exe").read_bytes() == b"original agent"
    assert (target / "fluxdownd.exe").read_bytes() == b"original daemon"

    install._install_missing_to_existing(extracted, target)
    assert (target / "fluxdown.exe").read_bytes() == b"new CLI"
    assert not list(target.glob(".*.mas-install"))


def test_empty_server_binary_routes_to_managed_install(tmp_path, monkeypatch):
    external = tmp_path / "desktop"
    external.mkdir()
    (external / "fluxdown-desktop.exe").write_bytes(b"desktop")
    (external / "fluxdown.exe").write_bytes(b"cli")
    (external / "fluxdown-agent.exe").write_bytes(b"agent")
    (external / "fluxdownd.exe").touch()
    managed = tmp_path / "data" / "fluxdown" / "bin"

    monkeypatch.setattr(
        install,
        "Config",
        SimpleNamespace(data_path=tmp_path / "data"),
    )
    selected, is_external = install._choose_install_target(str(external))
    assert selected == managed
    assert not is_external
    assert (external / "fluxdownd.exe").stat().st_size == 0


def test_external_install_refuses_to_overwrite_empty_component(tmp_path):
    external = tmp_path / "desktop"
    external.mkdir()
    (external / "fluxdown-desktop.exe").write_bytes(b"desktop")
    (external / "fluxdown-agent.exe").write_bytes(b"agent")
    (external / "fluxdownd.exe").touch()
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    (extracted / "fluxdown.exe").write_bytes(b"cli")
    (extracted / "fluxdownd.exe").write_bytes(b"good daemon")

    with pytest.raises(RuntimeError, match="空文件"):
        install._install_missing_to_existing(extracted, external)
    assert not (external / "fluxdown.exe").exists()
    assert (external / "fluxdownd.exe").stat().st_size == 0


def test_protected_desktop_directory_uses_managed_install(tmp_path, monkeypatch):
    external = tmp_path / "protected"
    external.mkdir()
    (external / "fluxdown-desktop.exe").write_bytes(b"desktop")
    (external / "fluxdown-agent.exe").write_bytes(b"agent")
    (external / "fluxdownd.exe").write_bytes(b"daemon")
    monkeypatch.setattr(install, "Config", SimpleNamespace(data_path=tmp_path / "data"))
    monkeypatch.setattr(install, "_can_write_directory", lambda _: False)
    managed, external_install = install._choose_install_target(str(external))
    assert managed == tmp_path / "data" / "fluxdown" / "bin"
    assert not external_install

    monkeypatch.setattr(
        install._fluxdown_cli,
        "fluxdown_detect",
        lambda *args, **kwargs: {"candidates": [{"path": str(external)}]},
    )
    managed, external_install = install._choose_install_target("")
    assert managed == tmp_path / "data" / "fluxdown" / "bin"
    assert not external_install
    assert (external / "fluxdown-agent.exe").read_bytes() == b"agent"


@pytest.mark.asyncio
async def test_permission_changed_after_probe_retries_in_managed_directory(
    release, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    external = tmp_path / "protected"
    external.mkdir()
    (external / "fluxdown-desktop.exe").write_bytes(b"desktop")
    (external / "fluxdown-agent.exe").write_bytes(b"original agent")
    (external / "fluxdownd.exe").write_bytes(b"original daemon")

    config = GlobalConfig.build()
    await activate_config(config)
    await config.update(
        type(config).model_validate({"Update": {"FluxdownPath": str(external)}}),
        check_visibility=False,
    )
    flush = AsyncMock()
    monkeypatch.setattr(
        install,
        "Config",
        SimpleNamespace(setting=config, flush=flush, data_path=tmp_path / "data"),
    )
    monkeypatch.setattr(install, "_can_write_directory", lambda _: True)
    monkeypatch.setattr(
        install, "fetch_latest_release", AsyncMock(return_value=release)
    )
    downloaded = []

    async def download(release, name, *args):
        downloaded.append(name)
        folder = args[2]
        with zipfile.ZipFile(folder / name, "w") as bundle:
            names = (
                ("fluxdown.exe",)
                if name == release.cli_name
                else ("fluxdown-agent.exe", "fluxdownd.exe")
            )
            for binary in names:
                bundle.writestr("package/" + binary, b"new binary")
        return 100

    monkeypatch.setattr(install, "_download_asset", download)
    monkeypatch.setattr(cli, "fluxdown_server_shutdown", lambda: None)
    original_copy = install._install_missing_to_existing

    def access_denied(extracted, target):
        if target == external:
            raise PermissionError("protected folder")
        return original_copy(extracted, target)

    monkeypatch.setattr(install, "_install_missing_to_existing", access_denied)
    result = await install._install_locked("auto", None)
    managed = tmp_path / "data" / "fluxdown" / "bin"
    assert result["path"] == str(managed)
    assert Path(config.Update.FluxdownPath) == managed
    assert (managed / "fluxdown.exe").is_file()
    assert (managed / "fluxdown-agent.exe").is_file()
    assert (managed / "fluxdownd.exe").is_file()
    assert (external / "fluxdown-agent.exe").read_bytes() == b"original agent"
    assert (external / "fluxdownd.exe").read_bytes() == b"original daemon"
    assert not (external / "fluxdown.exe").exists()
    assert downloaded == [release.cli_name, release.cli_name, release.server_name]
    flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_permission_fallback_preserves_user_selected_path(
    release, tmp_path, monkeypatch
):
    """A -> (download starts) user chooses B -> A denied -> managed fallback must not overwrite B."""
    monkeypatch.chdir(tmp_path)
    external = tmp_path / "desktop-a"
    external.mkdir()
    (external / "fluxdown-desktop.exe").write_bytes(b"desktop")
    (external / "fluxdown-agent.exe").write_bytes(b"original agent")
    (external / "fluxdownd.exe").write_bytes(b"original daemon")
    user_choice = str(tmp_path / "desktop-b")

    config = GlobalConfig.build()
    await activate_config(config)
    await config.update(
        type(config).model_validate({"Update": {"FluxdownPath": str(external)}}),
        check_visibility=False,
    )
    flush = AsyncMock()
    monkeypatch.setattr(
        install,
        "Config",
        SimpleNamespace(setting=config, flush=flush, data_path=tmp_path / "data"),
    )
    monkeypatch.setattr(install, "_can_write_directory", lambda _: True)
    monkeypatch.setattr(
        install, "fetch_latest_release", AsyncMock(return_value=release)
    )
    downloaded = []

    async def download(release, name, *args):
        downloaded.append(name)
        folder = args[2]
        with zipfile.ZipFile(folder / name, "w") as bundle:
            names = (
                ("fluxdown.exe",)
                if name == release.cli_name
                else ("fluxdown-agent.exe", "fluxdownd.exe")
            )
            for binary in names:
                bundle.writestr("package/" + binary, b"new binary")
        if len(downloaded) == 1:
            await config.update(
                type(config).model_validate({"Update": {"FluxdownPath": user_choice}}),
                check_visibility=False,
            )
        return 100

    monkeypatch.setattr(install, "_download_asset", download)
    monkeypatch.setattr(cli, "fluxdown_server_shutdown", lambda: None)

    def access_denied(extracted, target):
        if target == external:
            raise PermissionError("directory became protected")
        raise AssertionError("unexpected external target")

    monkeypatch.setattr(install, "_install_missing_to_existing", access_denied)
    with pytest.raises(RuntimeError, match="路径未保存"):
        await install._install_locked("auto", None)

    managed = tmp_path / "data" / "fluxdown" / "bin"
    assert Path(config.Update.FluxdownPath) == Path(user_choice)
    assert (managed / "fluxdown.exe").is_file()
    assert (managed / "fluxdown-agent.exe").is_file()
    assert (managed / "fluxdownd.exe").is_file()
    assert (external / "fluxdown-agent.exe").read_bytes() == b"original agent"
    assert (external / "fluxdownd.exe").read_bytes() == b"original daemon"
    assert not (external / "fluxdown.exe").exists()
    assert downloaded == [release.cli_name, release.cli_name, release.server_name]
    flush.assert_not_awaited()
