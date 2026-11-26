"""验证 FluxDown 下载中心的产物归位和取消收尾。"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.utils.common import fluxdown_cli


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["new", "legacy", "unrelated"])
async def test_fluxdown_places_the_requested_download_in_extensionless_cache(
    monkeypatch, tmp_path, scenario
):
    url = "https://example.test/MAA-v6.23.2-win-x64.zip?ticket=1"
    destination = tmp_path / "cache" / "null-cache-identity"
    destination.parent.mkdir()
    cli = tmp_path / "fluxdown"
    task_id = "test-download"
    payload = b"completed ZIP"
    actual = destination.with_name("unrelated.zip")
    added = []

    monkeypatch.setattr(fluxdown_cli, "_server_data_dir", lambda _: tmp_path / "server")
    monkeypatch.setattr(
        fluxdown_cli,
        "fluxdown_server_ensure",
        lambda _: SimpleNamespace(gateway_port=12345, token="test"),
    )
    if scenario == "legacy":
        old_request = destination.with_name("mas-fluxdown-" + "a" * 32)
        actual = old_request.with_suffix(".zip")
        actual.write_bytes(payload)
        fluxdown_cli._map_put(
            cli,
            fluxdown_cli._map_key(url, destination),
            task_id,
            url,
            destination,
            request_path=old_request,
        )

    def run_cli(_cli, _env, args, timeout):
        nonlocal actual
        match args[0]:
            case "add":
                requested = (
                    Path(args[args.index("-d") + 1]) / args[args.index("-o") + 1]
                )
                added.append(requested)
                if scenario != "unrelated":
                    # 服务端会给无扩展名的显式文件名补上源文件的扩展名。
                    actual = (
                        requested if requested.suffix else requested.with_suffix(".zip")
                    )
                actual.write_bytes(payload)
                return 0, json.dumps([task_id])
            case "status":
                return 0, json.dumps(
                    {
                        "status": 3,
                        "saveDir": str(actual.parent),
                        "fileName": actual.name,
                    }
                )
            case "resume":
                return 0, ""
            case "pause" | "rm":
                return 0, ""
            case _:
                pytest.fail(f"Unexpected FluxDown command: {args[0]}")

    monkeypatch.setattr(fluxdown_cli, "_run_cli", run_cli)

    if scenario == "unrelated":
        with pytest.raises(RuntimeError, match="输出路径与本次请求不符"):
            await fluxdown_cli.fluxdown_server_download(url, destination, cli_exe=cli)
        assert actual.read_bytes() == payload
        assert not destination.exists()
        return

    size, _ = await fluxdown_cli.fluxdown_server_download(url, destination, cli_exe=cli)
    assert size == len(payload)
    assert destination.read_bytes() == payload
    assert not actual.exists()
    assert len(added) == (0 if scenario == "legacy" else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("before_pause", "version", "outcome"),
    [
        (1, "0.6.6", asyncio.CancelledError),
        (2, "0.6.6", fluxdown_cli.FluxdownCancelUnconfirmed),
        (1, "0.5.8", fluxdown_cli.FluxdownCancelUnconfirmed),
    ],
)
async def test_cancel_waits_for_fresh_fluxdown_pause(
    monkeypatch, tmp_path, before_pause, version, outcome
):
    cli = tmp_path / "fluxdown"
    destination = tmp_path / "cache"
    started = asyncio.Event()
    paused = False
    status_checks_after_pause = 0

    monkeypatch.setattr(fluxdown_cli, "_server_data_dir", lambda _: tmp_path / "server")
    monkeypatch.setattr(
        fluxdown_cli,
        "fluxdown_server_ensure",
        lambda _: SimpleNamespace(gateway_port=12345, token="test"),
    )

    def run_cli(_cli, _env, args, timeout):
        nonlocal paused, status_checks_after_pause
        match args[0]:
            case "add":
                return 0, '["test-download"]'
            case "pause":
                paused = True
                return 0, ""
            case "info":
                return 0, json.dumps({"version": version})
            case "status":
                if paused:
                    status_checks_after_pause += 1
                # The supported daemon may keep publishing an active frame while flushing.
                finished = paused and (
                    status_checks_after_pause > 1 or version == "0.5.8"
                )
                status = 2 if finished else before_pause
                return 0, json.dumps(
                    {"status": status, "downloadedBytes": 10, "totalBytes": 100}
                )
            case _:
                pytest.fail(f"Unexpected FluxDown command: {args[0]}")

    async def progress(*_):
        started.set()

    monkeypatch.setattr(fluxdown_cli, "_run_cli", run_cli)
    download = asyncio.create_task(
        fluxdown_cli.fluxdown_server_download(
            "https://example.test/asset.zip",
            destination,
            cli_exe=cli,
            progress=progress,
        )
    )
    try:
        await asyncio.wait_for(started.wait(), 2)
        download.cancel()
        with pytest.raises(outcome):
            await asyncio.wait_for(download, 3)
        assert paused
        assert not destination.exists()
        assert any(
            entry["task_id"] == "test-download"
            for entry in fluxdown_cli._load_task_map(cli).values()
        )
    finally:
        if not download.done():
            download.cancel()
            await asyncio.gather(download, return_exceptions=True)
