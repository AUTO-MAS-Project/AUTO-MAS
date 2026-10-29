"""公开活动源的解析、回退、缓存与取消契约。"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest

from app.tools import arknights_activity as ak
from app.tools import bluearchive_activity_source as ba
from app.tools import stella_official as stella

REAL_CLIENT = httpx.AsyncClient


@pytest.fixture
def source_http(monkeypatch):
    def install(handler):
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda **kwargs: REAL_CLIENT(
                transport=httpx.MockTransport(handler), **kwargs
            ),
        )

    return install


@pytest.fixture(autouse=True)
def clean_caches(monkeypatch):
    monkeypatch.setattr(ak, "_arknights_cache", None)
    monkeypatch.setattr(ba, "_bluearchive_cache", {})


def prts_row(start, end, name="event", kind="story"):
    return (
        f"<tr><td>{start}</td><td><a><b>{name}</b></a><i>badge</i>"
        f'<span data-time="1790812800,{end}"></span>'
        '<img src="https://media.prts.wiki/thumb/a/650px-cover.png"></td>'
        f"<td>{kind}</td></tr>"
    )


def test_prts_dates_names_filters_and_cover():
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    end = int((now + timedelta(days=5)).timestamp())
    page = prts_row("2026-10-02 16:00", end, "later")
    page += prts_row("2026-09-29 16:00", end, "first", "<b>story</b>")
    page += prts_row("2026-09-01 16:00", int((now - timedelta(days=15)).timestamp()))
    page += prts_row("2026-09-01 16:00", 1790812800)  # PRTS 用渲染时刻表示已结束
    page += prts_row("invalid", end) + prts_row("2026-10-09 16:00", end)
    page += "<tr><td>incomplete</td></tr>"
    rows = ak._parse_prts_activities(page, now)
    assert [r["name"] for r in rows] == ["first", "later"]
    assert rows[0] == {
        "name": "first",
        "kind": "story",
        "startTime": "2026-09-29T16:00:00+08:00",
        "endTime": "2026-10-06T08:00:00+08:00",
        "cover": "https://media.prts.wiki/thumb/a/1300px-cover.png",
    }


@pytest.mark.asyncio
async def test_prts_empty_success_cached_until_exact_ttl(monkeypatch, source_http):
    clock = [1000.0]
    monkeypatch.setattr(ak.time, "time", lambda: clock[0])
    fallback = AsyncMock()
    monkeypatch.setattr(ak, "fetch_sra_activities", fallback)
    calls = []

    def respond(request):
        calls.append(request)
        assert str(request.url) == ak.PRTS_ACTIVITY_URL
        assert request.headers["user-agent"] == "AUTO-MAS"
        return httpx.Response(200, text="<table></table>")

    source_http(respond)
    assert await ak.fetch_arknights_activities() == {"activities": []}
    clock[0] += 599
    assert await ak.fetch_arknights_activities() == {"activities": []}
    assert len(calls) == 1
    clock[0] += 1
    await ak.fetch_arknights_activities()
    assert len(calls) == 2
    fallback.assert_not_awaited()


@pytest.mark.asyncio
async def test_prts_fallback_cache_and_original_failure(monkeypatch, source_http):
    source_http(lambda request: httpx.Response(503))
    fallback = AsyncMock(return_value={"activities": [{"name": "fallback"}]})
    monkeypatch.setattr(ak, "fetch_sra_activities", fallback)
    assert (await ak.fetch_arknights_activities())["activities"][0][
        "name"
    ] == "fallback"
    await ak.fetch_arknights_activities()
    fallback.assert_awaited_once_with("ak")
    monkeypatch.setattr(ak, "_arknights_cache", None)
    fallback.return_value = None
    with pytest.raises(httpx.HTTPStatusError):
        await ak.fetch_arknights_activities()
    assert ak._arknights_cache is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "module,call",
    [
        (ak, lambda: ak.fetch_arknights_activities()),
        (
            ba,
            lambda: ba.fetch_bluearchive_activities(
                line_type="CN", page=1, page_size=20
            ),
        ),
        (stella, lambda: stella.fetch_stella_activities()),
    ],
)
async def test_activity_cancellation_does_not_start_fallback(
    monkeypatch, source_http, module, call
):
    async def cancelled(request):
        raise asyncio.CancelledError

    source_http(cancelled)
    if module is stella:
        monkeypatch.setattr(
            stella,
            "fetch_official_activities",
            AsyncMock(side_effect=asyncio.CancelledError),
        )
    fallback = AsyncMock()
    monkeypatch.setattr(module, "fetch_sra_activities", fallback)
    with pytest.raises(asyncio.CancelledError):
        await call()
    fallback.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "line,server,source",
    [("CN", 16, "ba-cn"), ("JP", 15, "ba-jp"), ("Globle", 17, "ba-global")],
)
async def test_bluearchive_server_request_and_fallback(
    monkeypatch, source_http, line, server, source
):
    calls = []

    def respond(request):
        calls.append(request)
        assert request.url.params["serverId"] == str(server)
        assert request.url.params["page_no"] == "1"
        assert request.url.params["limit"] == "20"
        assert request.headers["referer"] == ba.GAMEKEE_HEADERS["Referer"]
        return httpx.Response(200, json={"code": 403, "msg": "unavailable"})

    source_http(respond)
    fallback = AsyncMock(
        return_value={
            "activities": [
                {
                    "name": "event",
                    "startTime": "2026-10-01T00:00:00+08:00",
                    "endTime": "2026-10-09T00:00:00+08:00",
                    "cover": "cover",
                },
                {"name": "invalid"},
            ]
        }
    )
    monkeypatch.setattr(ba, "fetch_sra_activities", fallback)
    data = await ba.fetch_bluearchive_activities(line_type=line, page=1, page_size=20)
    assert data == {
        "code": 0,
        "data": [
            {
                "title": "event",
                "picture": "cover",
                "description": "",
                "activity_kind_name": "活动",
                "begin_at": 1790784000,
                "end_at": 1791475200,
            }
        ],
    }
    assert (
        await ba.fetch_bluearchive_activities(line_type=line, page=1, page_size=20)
        == data
    )
    assert len(calls) == 1
    fallback.assert_awaited_once_with(source)


@pytest.mark.asyncio
async def test_bluearchive_pagination_and_cache_expiry(monkeypatch, source_http):
    clock = [1000.0]
    monkeypatch.setattr(ba.time, "time", lambda: clock[0])
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"code": 0, "data": []})

    source_http(respond)
    for page in (1, 2, 1):
        await ba.fetch_bluearchive_activities(line_type="CN", page=page, page_size=20)
    assert len(calls) == 2
    clock[0] += 600
    await ba.fetch_bluearchive_activities(line_type="CN", page=1, page_size=20)
    assert len(calls) == 3
    assert len(ba._bluearchive_cache) == 1
    source_http(lambda request: httpx.Response(503))
    fallback = AsyncMock(return_value=None)
    monkeypatch.setattr(ba, "fetch_sra_activities", fallback)
    assert await ba.fetch_bluearchive_activities(
        line_type="CN", page=2, page_size=20
    ) == {"code": 0, "data": []}
    fallback.assert_not_awaited()
    with pytest.raises(httpx.HTTPStatusError):
        await ba.fetch_bluearchive_activities(line_type="JP", page=1, page_size=20)


@pytest.mark.asyncio
async def test_stella_display_fallback_keeps_official_runtime_independent(monkeypatch):
    monkeypatch.setattr(
        stella, "fetch_official_activities", AsyncMock(return_value=None)
    )
    fallback = AsyncMock(
        return_value={"activities": [{"name": "猎影合围", "kind": ""}]}
    )
    monkeypatch.setattr(stella, "fetch_sra_activities", fallback)
    result = await stella.fetch_stella_activities()
    assert result["activities"][0]["kind"] == stella.classify_activity_name("猎影合围")
    fallback.assert_awaited_once_with("xtlr")
    assert await stella.has_running_official_activity() is None
    assert fallback.await_count == 1
    fallback.return_value = None
    assert await stella.fetch_stella_activities() is None
    official = {"activities": []}
    stella.fetch_official_activities.return_value = official
    assert await stella.fetch_stella_activities() is official


@pytest.mark.asyncio
async def test_bluearchive_cache_is_bounded_and_evicts_oldest(monkeypatch, source_http):
    clock = [1000.0]
    monkeypatch.setattr(ba.time, "time", lambda: clock[0])
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"code": 0, "data": []})

    source_http(respond)
    for page in range(1, 34):
        await ba.fetch_bluearchive_activities(line_type="CN", page=page, page_size=20)
        clock[0] += 1
    assert len(ba._bluearchive_cache) == 32
    await ba.fetch_bluearchive_activities(line_type="CN", page=33, page_size=20)
    assert len(calls) == 33
    await ba.fetch_bluearchive_activities(line_type="CN", page=1, page_size=20)
    assert len(calls) == 34
