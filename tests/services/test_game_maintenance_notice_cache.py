"""维护信息按公告口径复用持久缓存和 ETag 的本地验证。"""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.models.config import GlobalConfig
from app.services import game_maintenance as service


@pytest.fixture
def environment(monkeypatch):
    config = GlobalConfig()
    clock = [0.0]

    class ClockDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = datetime(2026, 10, 10, 12) + timedelta(seconds=clock[0])
            if tz is None:
                return value
            return (
                (value - timedelta(hours=8)).replace(tzinfo=timezone.utc).astimezone(tz)
            )

    monkeypatch.setattr(service, "Config", config)
    monkeypatch.setattr(service, "datetime", ClockDatetime)
    monkeypatch.setattr(service.time, "monotonic", lambda: clock[0])
    return config, clock


def maintenance_data(
    start="2026-10-10T11:00:00+08:00", end="2026-10-10T16:00:00+08:00"
):
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


def transport(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        service.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler)),
    )


@pytest.mark.asyncio
async def test_200_persists_content_etag_and_time_then_304_reuses_cache(
    monkeypatch, environment
):
    config, clock = environment
    data = maintenance_data()
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=data, headers={"etag": '"version-1"'})
        # 非 JSON 正文：304 分支不应尝试解析响应正文。
        return httpx.Response(304, text="not json")

    transport(monkeypatch, handler)
    client = service.GameMaintenanceClient()
    first, concurrent = await asyncio.gather(
        client.get_active("arknights"), client.get_active("arknights")
    )
    assert first is not None and concurrent == first and len(requests) == 1
    assert not requests[0].headers.get("If-None-Match")
    assert json.loads(config.get("Data", "Maintenance")) == data
    assert config.get("Data", "MaintenanceETag") == '"version-1"'
    assert config.get("Data", "LastMaintenanceUpdated") == "2026-10-10 12:00:00"
    clock[0] = 3599
    assert await client.get_active("arknights") == first
    assert len(requests) == 1
    clock[0] = 3600
    assert await client.get_active("arknights") == first
    assert requests[1].headers["If-None-Match"] == '"version-1"'
    assert config.get("Data", "LastMaintenanceUpdated") == "2026-10-10 13:00:00"
    clock[0] = 7199
    assert await client.get_active("arknights") == first
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_cache_and_etag_survive_restart(monkeypatch, environment, tmp_path):
    config, clock = environment
    await config.connect(tmp_path / "GlobalConfig.json")
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                200, json=maintenance_data(), headers={"ETag": '"saved"'}
            )
        return httpx.Response(304)

    transport(monkeypatch, handler)
    assert await service.GameMaintenanceClient().get_active("arknights") is not None
    restored = GlobalConfig()
    await restored.connect(tmp_path / "GlobalConfig.json")
    monkeypatch.setattr(service, "Config", restored)
    clock[0] = 1200
    restarted = service.GameMaintenanceClient()
    assert await restarted.get_active("arknights") is not None
    assert len(calls) == 1
    clock[0] = 3600
    assert await restarted.get_active("arknights") is not None
    assert len(calls) == 2 and calls[1].headers["If-None-Match"] == '"saved"'


@pytest.mark.asyncio
async def test_changed_data_replaces_etag_and_empty_maintenance(
    monkeypatch, environment
):
    config, clock = environment
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                200, json=maintenance_data(), headers={"ETag": '"old"'}
            )
        return httpx.Response(
            200,
            json={"schema_version": 1, "games": {"arknights": {"maintenance": None}}},
            headers={"ETag": '"new"'},
        )

    transport(monkeypatch, handler)
    client = service.GameMaintenanceClient()
    assert await client.get_active("arknights") is not None
    clock[0] = 3600
    assert await client.get_active("arknights") is None
    assert calls[1].headers["If-None-Match"] == '"old"'
    assert config.get("Data", "MaintenanceETag") == '"new"'
    assert (
        json.loads(config.get("Data", "Maintenance"))["games"]["arknights"][
            "maintenance"
        ]
        is None
    )


@pytest.mark.asyncio
async def test_failure_fails_open_until_successful_304_revalidation(
    monkeypatch, environment
):
    config, clock = environment
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                200, json=maintenance_data(), headers={"ETag": '"valid"'}
            )
        if len(calls) == 2:
            return httpx.Response(503)
        return httpx.Response(304)

    transport(monkeypatch, handler)
    client = service.GameMaintenanceClient()
    first = await client.get_active("arknights")
    clock[0] = 3600
    assert await client.get_active("arknights") is None
    assert config.get("Data", "LastMaintenanceUpdated") == "2026-10-10 12:00:00"
    clock[0] += 59
    assert await client.get_active("arknights") is None and len(calls) == 2
    clock[0] += 1
    assert await client.get_active("arknights") == first
    assert calls[2].headers["If-None-Match"] == '"valid"'


@pytest.mark.asyncio
async def test_invalid_200_does_not_replace_persisted_content_or_etag(
    monkeypatch, environment
):
    config, clock = environment
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                200, json=maintenance_data(), headers={"ETag": '"valid"'}
            )
        return httpx.Response(
            200, json={"schema_version": 9}, headers={"ETag": '"broken"'}
        )

    transport(monkeypatch, handler)
    client = service.GameMaintenanceClient()
    assert await client.get_active("arknights") is not None
    old_data = config.get("Data", "Maintenance")
    clock[0] = 3600
    assert await client.get_active("arknights") is None
    assert config.get("Data", "Maintenance") == old_data
    assert config.get("Data", "MaintenanceETag") == '"valid"'
    assert config.get("Data", "LastMaintenanceUpdated") == "2026-10-10 12:00:00"


@pytest.mark.asyncio
async def test_corrupt_cached_data_fetches_without_etag(monkeypatch, environment):
    config, clock = environment
    await config.update(
        {
            "Data": {
                "Maintenance": '{"schema_version": 9}',
                "MaintenanceETag": '"corrupt"',
                "LastMaintenanceUpdated": "2026-10-10 12:00:00",
            }
        }
    )
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=maintenance_data(), headers={"ETag": '"fixed"'})

    transport(monkeypatch, handler)
    assert await service.GameMaintenanceClient().get_active("arknights") is not None
    assert not calls[0].headers.get("If-None-Match")
    assert config.get("Data", "MaintenanceETag") == '"fixed"'


@pytest.mark.asyncio
async def test_304_does_not_extend_maintenance_window(monkeypatch, environment):
    config, clock = environment
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                200,
                json=maintenance_data(end="2026-10-10T12:30:00+08:00"),
                headers={"ETag": '"end"'},
            )
        return httpx.Response(304)

    transport(monkeypatch, handler)
    client = service.GameMaintenanceClient()
    assert await client.get_active("arknights") is not None
    clock[0] = 1800
    assert await client.get_active("arknights") is None and len(calls) == 1
    clock[0] = 3600
    assert await client.get_active("arknights") is None and len(calls) == 2


@pytest.mark.asyncio
async def test_200_without_etag_clears_previous_etag(monkeypatch, environment):
    config, clock = environment
    await config.update(
        {
            "Data": {
                "Maintenance": json.dumps(maintenance_data()),
                "MaintenanceETag": '"old"',
            }
        }
    )
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=maintenance_data())

    transport(monkeypatch, handler)
    client = service.GameMaintenanceClient()
    assert await client.get_active("arknights") is not None
    assert config.get("Data", "MaintenanceETag") == ""
    clock[0] = 3600
    assert await client.get_active("arknights") is not None
    assert not calls[1].headers.get("If-None-Match")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [304, 204, 206])
async def test_unusable_response_does_not_mark_cache_fresh(
    monkeypatch, environment, status
):
    config, clock = environment
    await config.set("Data", "Maintenance", '{"schema_version": 9}')
    transport(
        monkeypatch, lambda request: httpx.Response(status, json=maintenance_data())
    )
    assert await service.GameMaintenanceClient().get_active("arknights") is None
    assert config.get("Data", "LastMaintenanceUpdated") == "2000-01-01 00:00:00"


@pytest.mark.asyncio
async def test_cancelled_refresh_does_not_replace_cache(monkeypatch, environment):
    config, clock = environment
    await config.update(
        {
            "Data": {
                "Maintenance": json.dumps(maintenance_data()),
                "MaintenanceETag": '"valid"',
            }
        }
    )

    def handler(request):
        raise asyncio.CancelledError

    transport(monkeypatch, handler)
    with pytest.raises(asyncio.CancelledError):
        await service.GameMaintenanceClient().get_active("arknights")
    assert config.get("Data", "MaintenanceETag") == '"valid"'
    assert config.get("Data", "LastMaintenanceUpdated") == "2000-01-01 00:00:00"
