import pytest_asyncio
from types import SimpleNamespace
from tests.config_support import activate_config, group_view

"""Sourcery 意见的本地验证：保存异常、空 ETag、时钟回拨。"""
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock
import httpx
import pytest
from app.models.config import GlobalConfig
from app.services import game_maintenance as service
from app.utils.constants import UTC8


@pytest_asyncio.fixture
async def environment(monkeypatch):
    config = GlobalConfig.build()
    await activate_config(config)
    clock = [0.0]
    fixed_now = datetime(2026, 10, 10, 12, tzinfo=UTC8)

    class ClockDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            current = fixed_now + timedelta(seconds=clock[0])
            return (
                current.replace(tzinfo=None) if tz is None else current.astimezone(tz)
            )

    monkeypatch.setattr(service, "Config", SimpleNamespace(setting=config))
    monkeypatch.setattr(service, "datetime", ClockDatetime)
    monkeypatch.setattr(service.time, "monotonic", lambda: clock[0])
    return (config, clock)


def maintenance_data():
    return {
        "schema_version": 1,
        "games": {
            "arknights": {
                "maintenance": {
                    "planned_start_at": "2026-10-10T11:00:00+08:00",
                    "planned_end_at": "2026-10-10T15:00:00+08:00",
                }
            }
        },
    }


def transport(monkeypatch, handler):
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        service.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler)),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 304])
async def test_save_error_fails_open(monkeypatch, environment, tmp_path, status):
    config, clock = environment
    await config.update(
        type(config).model_validate(
            {
                "Data": {
                    "Maintenance": json.dumps(maintenance_data()),
                    "MaintenanceETag": '"valid"',
                }
            }
        ),
        check_visibility=False,
    )
    await activate_config(config, tmp_path / "GlobalConfig.yaml")
    save = AsyncMock(side_effect=OSError("simulated save failure"))
    monkeypatch.setattr(GlobalConfig, "update", save)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            status, json=maintenance_data(), headers={"ETag": '"new"'}
        )

    transport(monkeypatch, handler)
    client = service.GameMaintenanceClient()
    assert await client.get_active("arknights") is None
    save.assert_awaited_once()
    clock[0] = service.RETRY_SECONDS - 1
    assert await client.get_active("arknights") is None
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_empty_etag_is_omitted_on_first_fetch_and_refresh(
    monkeypatch, environment
):
    config, clock = environment
    requests = []

    def handler(request):
        requests.append(request)
        if "If-None-Match" in request.headers:
            return httpx.Response(400)
        return httpx.Response(200, json=maintenance_data())

    transport(monkeypatch, handler)
    client = service.GameMaintenanceClient()
    assert await client.get_active("arknights") is not None
    clock[0] = service.CACHE_SECONDS
    assert await client.get_active("arknights") is not None
    assert len(requests) == 2
    assert all(("If-None-Match" not in request.headers for request in requests))


@pytest.mark.asyncio
@pytest.mark.parametrize("future_seconds", [60, 3600, 86400])
async def test_future_check_time_triggers_revalidation(
    monkeypatch, environment, future_seconds
):
    config, clock = environment
    future = datetime(2026, 10, 10, 12) + timedelta(seconds=future_seconds)
    await config.update(
        type(config).model_validate(
            {
                "Data": {
                    "Maintenance": json.dumps(maintenance_data()),
                    "MaintenanceETag": '"old"',
                    "LastMaintenanceUpdated": future.replace(tzinfo=UTC8),
                }
            }
        ),
        check_visibility=False,
    )
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={"schema_version": 1, "games": {"arknights": {"maintenance": None}}},
            headers={"ETag": '"current"'},
        )

    transport(monkeypatch, handler)
    client = service.GameMaintenanceClient()
    assert await client.get_active("arknights") is None
    assert len(requests) == 1
    assert requests[0].headers["If-None-Match"] == '"old"'
    assert config.Data.LastMaintenanceUpdated == datetime(2026, 10, 10, 12, tzinfo=UTC8)
    clock[0] = service.CACHE_SECONDS - 1
    assert await client.get_active("arknights") is None
    assert len(requests) == 1
