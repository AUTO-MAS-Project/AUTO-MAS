"""Regression tests for bounded cross-script download diagnostics."""

import asyncio
import json
import zipfile

import httpx
import pytest
from fastapi import FastAPI

from app.api import setting
from app.config import config_manager
from app.core import Config, download_diagnostics, downloads
from app.core.download_diagnostics import describe_package, safe_origin
from app.models.config import GlobalConfig
from tests.config_support import activate_config


def test_signed_urls_are_reduced_to_origin():
    assert (
        safe_origin(
            "https://person:secret@example.com/updates/file.zip?cdk=secret&token=123"
        )
        == "https://example.com"
    )
    assert safe_origin("invalid") == "(hidden)"
    assert (
        safe_origin("https://[2001:db8::1]:8443/update.zip?token=private")
        == "https://[2001:db8::1]"
    )


def test_m7a_nested_root_and_version_marker(tmp_path):
    package = tmp_path / "m7a.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("March7thAssistant/assets/config/version.txt", "v2026.11.17")
        archive.writestr("release-notes.txt", "not secret")
    data = describe_package(package)
    assert data["format"] == "zip"
    assert data["root_count"] == 2
    assert data["known_roots"] == ["March7thAssistant"]
    assert data["version_markers"] == [
        {"name": "version.txt", "version": "v2026.11.17"}
    ]
    assert "release-notes.txt" not in str(data)


def test_opaque_executable_does_not_claim_invalid_zip(tmp_path):
    package = tmp_path / "setup.exe"
    package.write_bytes(b"MZ" + b"0" * 20)
    assert describe_package(package)["format"] == "opaque"


def test_invalid_zip_signature_is_reported_without_extraction(tmp_path):
    package = tmp_path / "broken.zip"
    package.write_bytes(b"PK" + b"broken")
    assert describe_package(package)["format"] == "zip-invalid"


def test_large_zip_directory_is_skipped_before_parsing(tmp_path, monkeypatch):
    package = tmp_path / "large-directory.zip"
    with zipfile.ZipFile(package, "w") as archive:
        entry = zipfile.ZipInfo("version.txt")
        entry.comment = b"x" * 2000
        archive.writestr(entry, "v1.2.3")

    def forbid_parsing(*args, **kwargs):
        pytest.fail("ZIP diagnostics parsed a directory over its byte budget")

    # Use a small budget so the test exercises the same limit without a large fixture.
    monkeypatch.setattr(
        download_diagnostics, "_MAX_ZIP_INSPECTION_BYTES", 1024, raising=False
    )
    monkeypatch.setattr(zipfile.ZipInfo, "__init__", forbid_parsing)
    assert describe_package(package) == {
        "schema": 1,
        "format": "zip",
        "bytes": package.stat().st_size,
    }


def test_unrecognized_version_markers_count_towards_read_limit(tmp_path, monkeypatch):
    package = tmp_path / "many-markers.zip"
    with zipfile.ZipFile(package, "w") as archive:
        for index in range(7):
            archive.writestr(f"{index}/version.txt", "unknown")
        archive.writestr("last/version.txt", "v1.2.3")

    opened = []
    open_entry = zipfile.ZipFile.open

    def record_open(archive, entry, *args, **kwargs):
        opened.append(entry.filename)
        return open_entry(archive, entry, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "open", record_open)
    assert describe_package(package) == {
        "schema": 1,
        "format": "zip",
        "bytes": package.stat().st_size,
    }
    assert opened == [f"{index}/version.txt" for index in range(6)]


@pytest.mark.asyncio
async def test_same_destination_retry_preserves_both_export_records(
    tmp_path, monkeypatch, isolated_app_paths
):
    monkeypatch.setattr(Config, "setting", await activate_config(GlobalConfig.build()))
    monkeypatch.setattr(
        downloads._utils_fluxdown_cli,
        "_server_data_dir",
        lambda _: tmp_path / "fluxdown",
    )
    url = "https://example.test/private/package.zip?token=secret"
    destination = tmp_path / "package.part"

    async def fail(*args, **kwargs):
        request = httpx.Request("GET", url)
        raise httpx.HTTPStatusError(
            f"download failed: {url}",
            request=request,
            response=httpx.Response(403, request=request),
        )

    async def succeed(url, destination, **kwargs):
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("March7thAssistant/version.txt", "v1.2.3")
        return destination.stat().st_size

    with pytest.raises(httpx.HTTPStatusError):
        await downloads.download_file(
            url, destination, timeout=3, downloader="builtin", http_download=fail
        )
    size = await downloads.download_file(
        url, destination, timeout=3, downloader="builtin", http_download=succeed
    )

    app = FastAPI()
    app.include_router(setting.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/setting/get")
    assert response.status_code == 200
    history = response.json()["data"]["Update"]["LastUpdateHistory"]
    failed, succeeded = history
    assert (failed["status"], failed["error"], failed["size"]) == (
        "failed",
        "HTTPStatusError",
        0,
    )
    assert failed["diagnostic"]["availability"] == "download_failed"
    assert failed["diagnostic"]["http_status"] == 403
    assert (succeeded["status"], succeeded["error"], succeeded["size"]) == (
        "success",
        None,
        size,
    )
    assert succeeded["diagnostic"]["version_markers"] == [
        {"name": "version.txt", "version": "v1.2.3"}
    ]
    for item in history:
        assert item["diagnostic"]["downloader"] == "httpx"
        assert item["url"] == "https://example.test"
        assert item["destination"] == str(destination)
        assert "token=secret" not in json.dumps(item)


@pytest.mark.asyncio
async def test_fluxdown_package_summary_is_on_its_terminal_record(
    tmp_path, monkeypatch, isolated_app_paths
):
    config = await activate_config(GlobalConfig.build())
    monkeypatch.setattr(Config, "setting", config)
    monkeypatch.setattr(
        downloads._utils_fluxdown_cli,
        "_server_data_dir",
        lambda _: tmp_path / "fluxdown",
    )
    await config.update(
        GlobalConfig.model_validate({"Update": {"FluxdownServerMode": False}}),
        check_visibility=False,
    )
    monkeypatch.setattr(
        downloads._utils_fluxdown_cli,
        "fluxdown_find_cli",
        lambda *_, **__: tmp_path / "fluxdown-cli",
    )

    async def fluxdown(url, destination, **kwargs):
        destination.write_bytes(b"MZ package")
        size = destination.stat().st_size
        return size, downloads._utils_fluxdown_cli.FluxdownDownloadRecord(
            url=url,
            destination=str(destination),
            size=size,
            duration_ms=31,
            segments=4,
            status="success",
        )

    monkeypatch.setattr(downloads._utils_fluxdown_cli, "fluxdown_download", fluxdown)
    size = await downloads.download_file(
        "https://example.test/package?token=secret",
        tmp_path / "package",
        timeout=3,
        downloader="fluxdown",
    )
    (record,) = config.Update.LastUpdateHistory
    assert (record.status, record.size, record.duration_ms, record.segments) == (
        "success",
        size,
        31,
        4,
    )
    assert record.url == "https://example.test"
    assert record.diagnostic["downloader"] == "FluxDown"
    assert record.diagnostic["format"] == "opaque"


@pytest.mark.asyncio
async def test_cancel_waiting_for_history_preserves_unconfirmed_writer(
    tmp_path, monkeypatch, isolated_app_paths
):
    config = await activate_config(GlobalConfig.build())
    monkeypatch.setattr(Config, "setting", config)
    cli = downloads._utils_fluxdown_cli
    monkeypatch.setattr(cli, "_server_data_dir", lambda _: tmp_path / "fluxdown")
    monkeypatch.setattr(
        cli, "fluxdown_server_task_safe_to_overwrite", lambda *_, **__: False
    )
    monkeypatch.setattr(cli, "fluxdown_server_mark_failure", lambda *_: 1)
    history_started = asyncio.Event()
    write_history = downloads._write_history

    async def observe_history(record):
        history_started.set()
        await write_history(record)

    monkeypatch.setattr(downloads, "_write_history", observe_history)
    async with config_manager.execution_gate():
        task = asyncio.create_task(
            downloads.download_file(
                "https://example.test/package",
                tmp_path / "package",
                timeout=3,
                downloader="builtin",
            )
        )
        try:
            await asyncio.wait_for(history_started.wait(), timeout=2)
        finally:
            task.cancel()
            with pytest.raises(cli.FluxdownCancelUnconfirmed):
                await asyncio.wait_for(task, timeout=2)
    assert not config.Update.LastUpdateHistory
