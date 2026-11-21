"""StellaBase 部分损坏时，主页和 MSS 仍能使用已确认的当前活动。"""

from datetime import datetime
from unittest.mock import patch

import httpx
import pytest

from app.tools.common.game_calendar import stella


@pytest.fixture
def calendar(monkeypatch):
    entry = {
        "title": "本期活动",
        "description": "挑战活动限时关卡，阅读活动故事剧情",
        "startTime": "2026-11-13T12:00:00+08:00",
        "endTime": "2026-11-27T04:00:00+08:00",
        "claimEndTime": "2026-12-04T10:59:59+08:00",
        "textures": {"banner": "/stella/assets/banner_activity.png"},
    }
    payload = {"current": [entry], "upcoming": [], "ended": []}
    client_class = httpx.AsyncClient
    monkeypatch.setattr(stella, "_cache", None)
    monkeypatch.setattr(
        stella.httpx,
        "AsyncClient",
        lambda **kwargs: client_class(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
            **kwargs,
        ),
    )
    with patch.object(stella, "datetime", wraps=datetime) as clock:
        clock.now.return_value = datetime(2026, 11, 20, tzinfo=stella.BEIJING)
        yield payload, clock


@pytest.mark.asyncio
@pytest.mark.parametrize("broken", [{}, None, {"startTime": "invalid"}])
async def test_current_activity_survives_broken_archive(calendar, broken):
    payload, _ = calendar
    payload["ended"].append(broken)
    assert await stella.has_running_official_activity() is True
    data = await stella.fetch_official_activities()
    assert [item["name"] for item in data["activities"]] == ["本期活动"]
    assert data["activities"][0]["cover"] == (
        "https://stella.ennead.cc/api/asset/stella/assets/banner_activity.png"
    )
    assert data["sourceName"] == "StellaBase"


@pytest.mark.asyncio
async def test_unknown_archive_does_not_confirm_no_activity(calendar):
    payload, clock = calendar
    payload["ended"].append({})
    clock.now.return_value = datetime(2026, 11, 28, tzinfo=stella.BEIJING)
    assert await stella.has_running_official_activity() is None


@pytest.mark.asyncio
async def test_cached_activity_ends_before_shop_claim_deadline(calendar):
    _, clock = calendar
    assert await stella.has_running_official_activity() is True
    clock.now.return_value = datetime(2026, 11, 27, 4, tzinfo=stella.BEIJING)
    assert await stella.has_running_official_activity() is False
