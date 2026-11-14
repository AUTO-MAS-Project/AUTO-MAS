"""HSR 更新发现保留下载源约束、CDK 原因及安装包校验信息。"""

import importlib

import httpx
import pytest

from app.task.HSR.tools.update import update_engine_if_needed
from app.task.HSR.tools.update.engines import M7A, SRA

discovery = importlib.import_module("app.task.HSR.tools.update.discover")
STATION = "https://data2.auto-mas.top/api/v1/files/starrailassistant/Release/beta"


@pytest.fixture
def mock_http(monkeypatch):
    client = httpx.AsyncClient

    def install(respond):
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda **kwargs: client(**kwargs, transport=httpx.MockTransport(respond)),
        )

    return install


@pytest.fixture
def mirror(mock_http):
    reply = {"code": 7002, "msg": "KEY_INVALID"}

    def respond(request):
        assert request.url.host == "mirrorchyan.com"
        assert "os" not in request.url.params and "arch" not in request.url.params
        return httpx.Response(403, json=reply)

    mock_http(respond)
    return reply


@pytest.fixture
def station(mock_http):
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

    mock_http(respond)
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code,reason",
    [
        (7001, "填入的 CDK 已过期"),
        (7002, "填入的 CDK 错误"),
        (7003, "填入的 CDK 今日下载次数已达上限"),
        (7004, "填入的 CDK 类型和待下载的资源不匹配"),
        (7005, "填入的 CDK 已被封禁"),
    ],
)
async def test_cdk_failure_without_version_explains_reason(mirror, code, reason):
    mirror["code"] = code
    with pytest.raises(discovery.HSRUpdateError, match=reason):
        await discovery.discover(
            M7A, current_version="v1.0.0", source="MirrorChyan", cdk="test-cdk"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", [M7A, SRA], ids=["M7A", "SRA"])
@pytest.mark.parametrize("version,available", [("v2.0.0", True), ("v1.0.0", False)])
async def test_cdk_failure_preserves_version_and_reason(
    mirror, spec, version, available
):
    mirror["data"] = {
        "version_name": version,
        "url": "https://example.invalid/must-not-install.zip",
    }
    result = await discovery.discover(
        spec, current_version="v1.0.0", source="MirrorChyan", cdk="test-cdk"
    )
    assert result.latest_version == version
    assert result.update_available is available
    assert not result.installable
    assert result.blocked_reason == "填入的 CDK 错误"


@pytest.mark.asyncio
@pytest.mark.parametrize("spec", [M7A, SRA], ids=["M7A", "SRA"])
async def test_valid_mirror_candidate_preserves_download_metadata(mock_http, spec):
    data = {
        "version_name": "v2.0.0",
        "url": "https://example.invalid/update.zip",
        "sha256": "a" * 64,
        "release_note": "release notes",
    }
    mock_http(lambda request: httpx.Response(200, json={"code": 0, "data": data}))
    result = await discovery.discover(
        spec, current_version="v1.0.0", source="MirrorChyan", cdk="test-cdk"
    )
    assert result.installable
    assert result.candidate.download_url == data["url"]
    assert result.candidate.sha256 == data["sha256"]
    assert result.candidate.release_note == data["release_note"]
    assert result.blocked_reason is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, text="<html>unavailable</html>"),
        httpx.Response(200, text="not JSON"),
        httpx.Response(403, json={"code": 0, "data": {"version_name": "v1.0.0"}}),
    ],
    ids=["http-error", "invalid-json", "http-error-with-success-code"],
)
async def test_mirror_transport_failure_is_not_up_to_date(mock_http, response):
    def respond(request):
        assert request.url.host == "mirrorchyan.com"
        return response

    mock_http(respond)
    with pytest.raises(discovery.HSRUpdateError) as caught:
        await discovery.discover(
            M7A, current_version="v1.0.0", source="MirrorChyan", cdk="test-cdk"
        )
    assert "test-cdk" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [404, 503])
async def test_selected_github_retains_fallback_without_sending_cdk(mock_http, status):
    def respond(request):
        assert "cdk" not in request.url.params
        if request.url.host == "mirrorchyan.com":
            return httpx.Response(
                status, json={"code": 8001, "msg": "RESOURCE_NOT_FOUND"}
            )
        assert request.url.host == "api.github.com"
        if request.url.path.endswith("/releases/latest"):
            return httpx.Response(200, json={"tag_name": "v2.0.0"})
        return httpx.Response(
            200,
            json={
                "assets": [
                    {
                        "name": "March7thAssistant_full.zip",
                        "browser_download_url": "https://example.invalid/full.zip",
                    }
                ]
            },
        )

    mock_http(respond)
    result = await discovery.discover(
        M7A, current_version="v1.0.0", source="GitHub", cdk="test-cdk"
    )
    assert result.latest_version == "v2.0.0"
    assert result.candidate.source == "GitHub"


@pytest.mark.asyncio
@pytest.mark.parametrize("version", [None, "v1.0.0", "v2.0.0"])
async def test_cdk_failure_reaches_automatic_update_result(mirror, tmp_path, version):
    if version is not None:
        mirror["data"] = {"version_name": version}
    root = tmp_path / "m7a"
    marker = root / "assets" / "config" / "version.txt"
    marker.parent.mkdir(parents=True)
    marker.write_text("v1.0.0", encoding="utf-8")
    messages = []
    result = await update_engine_if_needed(
        "M7A",
        root,
        source="MirrorChyan",
        cdk="test-cdk",
        download_dir=tmp_path / "downloads",
        send_log=messages.append,
    )
    assert result.message == "填入的 CDK 错误"
    assert any("填入的 CDK 错误" in message for message in messages)
    assert not result.updated and not result.blocking
    assert marker.read_text(encoding="utf-8") == "v1.0.0"
    assert not (tmp_path / "downloads").exists()
