"""接管开关、下载器和网络代理是独立的公共契约。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core import script_update as update
from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed


@pytest.mark.asyncio
@pytest.mark.parametrize("fluxdown", [False, True])
@pytest.mark.parametrize("source", ["GitHub", "MirrorChyan", "AutoSite"])
async def test_download_policy_and_proxy_are_independent(
    tmp_path, monkeypatch, fluxdown, source
):
    proxy = httpx.Proxy("http://127.0.0.1:7890")
    monkeypatch.setattr(
        update,
        "Config",
        SimpleNamespace(
            proxy=proxy,
            setting=SimpleNamespace(
                Update=SimpleNamespace(FluxdownTakeoverAll=fluxdown)
            ),
        ),
    )
    download = AsyncMock(return_value=42)
    progress = AsyncMock()
    monkeypatch.setattr(update, "download_file", download)
    assert (
        await update.download_script_package(
            "https://example.invalid/package",
            tmp_path / "package",
            source=source,
            timeout=20,
            progress=progress,
        )
        == 42
    )
    options = download.call_args.kwargs
    assert options["proxy"] is proxy
    assert options["source"] == source
    assert options["progress"] is progress
    assert options["downloader"] == (
        "fluxdown" if fluxdown and source == "GitHub" else "builtin"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [asyncio.CancelledError(), FluxdownCancelUnconfirmed("unconfirmed")]
)
async def test_cancellation_is_never_hidden_or_retried(tmp_path, monkeypatch, error):
    monkeypatch.setattr(
        update,
        "Config",
        SimpleNamespace(
            proxy=None,
            setting=SimpleNamespace(Update=SimpleNamespace(FluxdownTakeoverAll=True)),
        ),
    )
    download = AsyncMock(side_effect=error)
    monkeypatch.setattr(update, "download_file", download)
    with pytest.raises(type(error)):
        await update.download_script_package(
            "https://example.invalid/package",
            tmp_path / "package",
            source="GitHub",
            timeout=20,
        )
    download.assert_awaited_once()


@pytest.mark.asyncio
async def test_explicit_proxy_is_preserved_with_authentication(tmp_path, monkeypatch):
    proxy = httpx.Proxy("http://user:secret@127.0.0.1:7891")
    monkeypatch.setattr(
        update,
        "Config",
        SimpleNamespace(
            proxy=httpx.Proxy("http://127.0.0.1:7890"),
            setting=SimpleNamespace(Update=SimpleNamespace(FluxdownTakeoverAll=True)),
        ),
    )
    download = AsyncMock(return_value=1)
    monkeypatch.setattr(update, "download_file", download)
    await update.download_script_package(
        "https://example.invalid/package",
        tmp_path / "package",
        source="GitHub",
        timeout=20,
        proxy=proxy,
    )
    assert download.call_args.kwargs["proxy"] is proxy
    assert download.call_args.kwargs["proxy"].auth == ("user", "secret")
