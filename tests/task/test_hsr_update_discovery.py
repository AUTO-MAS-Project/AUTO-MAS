"""SRA 自建下载站使用已发布文件记录，拒绝错版本或缺少校验的包。"""

import importlib

import httpx
import pytest

from app.task.HSR.tools.update.engines import SRA

discovery = importlib.import_module("app.task.HSR.tools.update.discover")
STATION = "https://data2.auto-mas.top/api/v1/files/starrailassistant/Release/beta"


@pytest.fixture
def station(monkeypatch):
    published = {
        "version_no": 15,
        "source_filename": "StarRailAssistant_v2.25.1.zip",
        "sha256": "a" * 64,
    }

    def respond(request):
        if request.url.host == "mirrorchyan.com":
            return httpx.Response(
                200, json={"code": 0, "data": {"version_name": "v2.25.1"}}
            )
        if str(request.url) == STATION:
            return httpx.Response(
                200, json={"code": 0, "data": {"published_version": published}}
            )
        raise AssertionError(f"Unexpected download discovery request: {request.url}")

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(**kwargs, transport=httpx.MockTransport(respond)),
    )
    return published


@pytest.mark.asyncio
async def test_station_pins_verified_full_package(station):
    result = await discovery.discover(SRA, current_version="v2.25.0", source="AutoSite")
    assert result.installable
    assert result.candidate.latest_version == "v2.25.1"
    assert result.candidate.download_url == STATION + "/download/content?version_no=15"
    assert result.candidate.sha256 == "a" * 64


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("source_filename", "StarRailAssistant_v2.26.0-beta.1.zip"),
        ("source_filename", "StarRailAssistant_Core_v2.25.1.zip"),
        ("sha256", ""),
        ("sha256", "invalid"),
        ("version_no", None),
        ("version_no", True),
    ],
)
async def test_station_rejects_unverifiable_or_different_package(station, field, value):
    station[field] = value
    with pytest.raises(discovery.HSRUpdateError):
        await discovery.discover(SRA, current_version="v2.25.0", source="AutoSite")
