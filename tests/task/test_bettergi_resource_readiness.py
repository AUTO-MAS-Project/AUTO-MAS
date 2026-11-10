"""BetterGI DFS2 发布资源检查的网络和版本边界。"""

from unittest.mock import AsyncMock

import httpx
import pytest
from packaging.version import Version

from app.task.BetterGI.tools import resource_readiness as probe


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload,ready",
    [
        ({"data": {"metadata": {"tag_name": "0.67.0"}, "index": {"abc": {}}}}, True),
        ({"data": {"metadata": {"tag_name": "0.66.0"}, "index": {"abc": {}}}}, False),
        ({"data": None}, False),
        ({"data": {"metadata": {"tag_name": "0.67.0"}, "index": {}}}, False),
        ({"data": {"metadata": {}, "index": {"abc": {}}}}, False),
        ({"data": {"metadata": {"tag_name": "invalid"}, "index": {"abc": {}}}}, False),
        ([], False),
    ],
)
async def test_stable_resource_metadata(monkeypatch, payload, ready):
    response = httpx.Response(
        200,
        json=payload,
        request=httpx.Request("GET", probe._STABLE_DFS2_URL),
    )
    client = AsyncMock()
    client.get.return_value = response
    context = AsyncMock()
    context.__aenter__.return_value = client
    monkeypatch.setattr(probe.httpx, "AsyncClient", lambda **kw: context)

    result, _ = await probe.stable_resources_ready(Version("0.67.0"), proxy=None)

    assert result is ready
    client.get.assert_awaited_once_with(
        probe._STABLE_DFS2_URL, params={"with_metadata": "1"}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [403, 404, 500])
async def test_stable_resource_http_error_skips(monkeypatch, status):
    response = httpx.Response(
        status, request=httpx.Request("GET", probe._STABLE_DFS2_URL)
    )
    client = AsyncMock()
    client.get.return_value = response
    context = AsyncMock()
    context.__aenter__.return_value = client
    monkeypatch.setattr(probe.httpx, "AsyncClient", lambda **kw: context)

    ready, reason = await probe.stable_resources_ready(Version("0.67.0"), proxy=None)

    assert not ready
    assert "不可用" in reason


@pytest.mark.asyncio
async def test_stable_resource_network_failure_skips(monkeypatch):
    client = AsyncMock()
    client.get.side_effect = httpx.ConnectError("unreachable")
    context = AsyncMock()
    context.__aenter__.return_value = client
    monkeypatch.setattr(probe.httpx, "AsyncClient", lambda **kw: context)

    ready, _ = await probe.stable_resources_ready(Version("0.67.0"), proxy=None)

    assert not ready
