"""#1297 本地验证：维护数据、缓存与失败放行。"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import httpx
import pytest

from app.services import game_maintenance as service


def payload(start, end):
    return {
        "schema_version": 1,
        "games": {
            "arknights": {
                "maintenance": {
                    "planned_start_at": start,
                    "planned_end_at": end,
                }
            }
        },
    }


def test_offset_comparison_and_exclusive_end():
    window = service.parse_maintenance(
        payload("2026-10-10T08:00:00+08:00", "2026-10-10T10:00:00+08:00")
    )["arknights"]
    assert window.contains(datetime(2026, 10, 10, 0, tzinfo=timezone.utc))
    assert not window.contains(datetime(2026, 10, 9, 23, 59, tzinfo=timezone.utc))
    assert not window.contains(datetime(2026, 10, 10, 2, tzinfo=timezone.utc))
    assert window.start.utcoffset() == timedelta(hours=8)


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {"schema_version": True, "games": {}},
        {"schema_version": 2, "games": {}},
        {"schema_version": 1, "games": []},
        {"schema_version": 1, "games": {"arknights": {}}},
        payload("2026-10-10T08:00:00", "2026-10-10T10:00:00"),
        payload("bad", "2026-10-10T10:00:00+08:00"),
        payload("2026-10-10T10:00:00Z", "2026-10-10T08:00:00Z"),
        payload(None, "2026-10-10T10:00:00Z"),
    ],
)
def test_invalid_data_is_rejected(data):
    with pytest.raises(ValueError):
        service.parse_maintenance(data)


def test_unknown_game_does_not_break_supported_records():
    assert (
        service.parse_maintenance(
            {
                "schema_version": 1,
                "games": {
                    "arknights": {"maintenance": None},
                    "unknown": "unsupported",
                },
            }
        )
        == {}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["network", "http", "schema", "timeout"])
async def test_cache_failure_clears_stale_window_and_throttles_retry(
    monkeypatch, failure
):
    clock = [0.0]
    monkeypatch.setattr(service.time, "monotonic", lambda: clock[0])
    now = datetime.now(timezone.utc)
    good = payload(
        (now - timedelta(hours=1)).isoformat(), (now + timedelta(hours=1)).isoformat()
    )
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) != 2:
            return httpx.Response(200, json=good)
        if failure == "network":
            raise httpx.ConnectError("offline", request=request)
        if failure == "timeout":
            raise TimeoutError("deadline")
        if failure == "http":
            return httpx.Response(503)
        return httpx.Response(200, json={"schema_version": 9})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        service.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler)),
    )
    warning = Mock()
    monkeypatch.setattr(service, "logger", Mock(warning=warning))
    client = service.GameMaintenanceClient()
    first, concurrent = await asyncio.gather(
        client.get_active("arknights"), client.get_active("arknights")
    )
    assert first is not None and concurrent == first and len(requests) == 1
    clock[0] = service.CACHE_SECONDS - 1
    assert await client.get_active("arknights") == first
    clock[0] = service.CACHE_SECONDS
    assert await client.get_active("arknights") is None
    warning.assert_called_once()
    assert client._windows == {}
    clock[0] += service.RETRY_SECONDS - 1
    assert await client.get_active("arknights") is None
    assert len(requests) == 2
    clock[0] += 1
    assert await client.get_active("arknights") is not None
    assert len(requests) == 3
