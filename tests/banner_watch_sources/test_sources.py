from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.tools.common.game_calendar.banner_sources import SOURCES
from app.tools.common.game_calendar.banner_sources.base import (
    BannerObservation,
    BannerSourceError,
    BaseBannerSource,
    PoolSection,
    datetime_from_epoch,
    split_pool_sections,
    stable_digest,
)
from app.tools.common.game_calendar.banner_sources.bilibili import (
    BlueArchiveBilibiliSource,
    _bluearchive_identity,
)
from app.tools.common.game_calendar.banner_sources.hypergryph import EndfieldSource
from app.tools.common.game_calendar.banner_sources.kuro import WutheringWavesSource
from app.tools.common.game_calendar.banner_sources.sina import PrincessConnectSource
from app.tools.common.game_calendar.banner_sources.sunborn import GirlsFrontline2Source
from app.tools.common.game_calendar.banner_sources.taptap import (
    AzurLaneSource,
    ResonanceSource,
    TapTapRecord,
    _azurlane_sections,
    _record_from_detail,
    _resonance_sections,
)

FIXTURES = Path(__file__).with_name("fixtures")
FIXED_NOW = datetime(2026, 11, 20, 4, 0, tzinfo=timezone.utc)


def _fragment(name: str) -> dict:
    payload = json.loads(
        (FIXTURES / "source_fragments.json").read_text(encoding="utf-8")
    )
    return payload[name]


def _json_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _record(value: dict) -> TapTapRecord:
    return TapTapRecord(
        article_id=str(value["article_id"]),
        title=str(value["title"]),
        body_text="\n".join(value["lines"]),
        published_at=datetime_from_epoch(value["publish_epoch"]),
        edited_time=value.get("edited_epoch"),
        detail_url=f"https://www.taptap.cn/moment/{value['article_id']}",
        revision=stable_digest(value),
    )


def _observation_shape() -> set[str]:
    return set(BannerObservation.__annotations__)


def test_sources_cover_exact_catalog() -> None:
    assert set(SOURCES) == {
        ("endfield", "cn"),
        ("wutheringwaves", "cn"),
        ("arknights", "cn"),
        ("bluearchive", "cn"),
        ("princessconnect", "cn"),
        ("azurlane", "cn"),
        ("girlsfrontline2", "cn"),
        ("resonance", "cn"),
    }


def test_bluearchive_bilibili_fixture_replays_exactly_three_pools() -> None:
    item = _json_fixture("bluearchive_bilibili_opus_1168392597461270533.json")
    drafts = BlueArchiveBilibiliSource()._draft_items(
        item=item,
        verified_at="2026-11-20T04:00:00Z",
        public_url="https://www.bilibili.com/opus/1168392597461270533",
    )
    rows = [draft.data for draft in drafts]

    assert [row["title"] for row in rows] == [
        "限时复刻招募【守护，终将化作未来】",
        "限时复刻招募【全年无休 沉迷研啾！】",
        "限时复刻招募【蒸腾热气 搅动牛奶】",
    ]
    assert {row["starts_at"] for row in rows} == {"2026-02-14T06:00:00Z"}
    assert {row["ends_at"] for row in rows} == {"2026-02-28T05:59:00Z"}
    assert {row["published_at"] for row in rows} == {"2026-02-12T06:00:00Z"}
    assert len({row["source_anchor"] for row in rows}) == 3
    assert all(row["official_id"] is None for row in rows)
    assert all(row["article_id"] == "1168392597461270533" for row in rows)


def test_bluearchive_taptap_schedule_corrections_and_upcoming_pools() -> None:
    fixture = _fragment("bluearchive_taptap_2026_11")
    records = [_record(value) for value in fixture["records"]]
    drafts = BlueArchiveBilibiliSource()._draft_taptap_records(
        records=records,
        verified_at="2026-11-20T04:00:00Z",
    )
    rows = [draft.data for draft in drafts]
    titles = {row["title"] for row in rows}

    assert "限时限定复刻招募【花阴映白浪】" in titles
    assert "限时限定复刻招募【骤雨让白昼】" in titles
    assert "限时限定复刻招募【春阴映白浪】" not in titles
    assert "限时限定复刻招募【片雨让白昼】" not in titles
    assert "限时复刻招募活动即将开启" not in titles

    scheduled = {
        row["title"]: row for row in rows if row["start_mode"] == "after_maintenance"
    }
    assert set(scheduled) == {
        "限时复刻招募【夏空渺渺 遥寄心愿】",
        "限时限定复刻招募【骤雨让白昼】",
        "限时限定复刻招募【花阴映白浪】",
        "限时复刻招募【夏日炎炎 笑靥未改】",
    }
    for row in scheduled.values():
        assert row["starts_at"] is None
        assert row["ends_at"] == "2026-11-26T05:59:00Z"
        assert row["end_kind"] == "known"
        assert row["confirmed_open_at"] == "2026-11-12T08:45:00Z"
        assert any("maintenance:867409998819360981" in item for item in row["related"])

    upcoming = {
        row["title"]: row
        for row in rows
        if row["published_at"] == "2026-11-19T03:00:00Z"
    }
    assert set(upcoming) == {
        "限时招募【Amiable,Advisor, Analytica！】",
        "限时招募【Collect, Convey, Conclude★★★】",
        "限时复刻招募【银装素裹，一樽星月】",
        "限时复刻招募【这里是RABBIT 4，凭指尖完成证明】",
    }
    assert all(row["start_mode"] == "tbd" for row in upcoming.values())
    assert all(row["starts_at"] is None for row in upcoming.values())
    assert all(row["ends_at"] is None for row in upcoming.values())

    corrected_a = PoolSection(
        title="限时限定复刻招募【骤雨让白昼】",
        text="3★限定成员“日和（泳装）”",
    )
    corrected_b = PoolSection(
        title="限时限定复刻招募【片雨让白昼】",
        text='3★限定成员"日和（泳装）"',
    )
    assert _bluearchive_identity(corrected_a) == _bluearchive_identity(corrected_b)


@pytest.mark.asyncio
async def test_endfield_version_article_is_pool_evidence_and_sale_is_not() -> None:
    fragment = _fragment("endfield_6094")
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        if request.url.path.endswith("/api/bulletin"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "list": [
                            {
                                "cid": "6094",
                                "title": fragment["title"],
                                "displayTime": fragment["published_epoch"],
                            },
                            {
                                "cid": "5971",
                                "title": "「月映申领」限时特卖说明",
                                "displayTime": 1793788200,
                            },
                        ]
                    }
                },
                request=request,
            )
        if request.url.path.endswith("/api/bulletin/6094"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "title": fragment["title"],
                        "displayTime": fragment["published_epoch"],
                        "data": fragment["body_html"],
                    }
                },
                request=request,
            )
        raise AssertionError(f"unexpected Endfield request: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await EndfieldSource(client=client, clock=lambda: FIXED_NOW).fetch()

    month = next(row for row in rows if row["title"] == "「月映申领」开放")
    assert month["kind"] == "weapon"
    assert month["starts_at"] == "2026-11-05T04:00:00Z"
    assert month["ends_at"] is None
    assert month["end_kind"] == "unknown"
    assert month["article_id"] == "6094"
    assert month["official_id"] is None
    assert all("/api/bulletin/5971" not in path for path in requested)


@pytest.mark.asyncio
async def test_endfield_required_detail_failure_aborts_sweep() -> None:
    fragment = _fragment("endfield_6094")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/bulletin"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "list": [
                            {
                                "cid": "6094",
                                "title": fragment["title"],
                                "displayTime": fragment["published_epoch"],
                            }
                        ]
                    }
                },
                request=request,
            )
        return httpx.Response(503, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(BannerSourceError):
            await EndfieldSource(client=client, clock=lambda: FIXED_NOW).fetch()


@pytest.mark.asyncio
async def test_bluearchive_required_taptap_aborts_partial_bili() -> None:
    item = _json_fixture("bluearchive_bilibili_opus_1168392597461270533.json")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.bilibili.com":
            return httpx.Response(200, text="<html></html>", request=request)
        if request.url.path.endswith("/feed/space"):
            return httpx.Response(
                200,
                json={"code": 0, "data": {"items": [item]}},
                request=request,
            )
        if request.url.host == "www.taptap.cn":
            return httpx.Response(503, request=request)
        raise AssertionError(f"unexpected Blue Archive request: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = BlueArchiveBilibiliSource(client=client, clock=lambda: FIXED_NOW)
        with pytest.raises(BannerSourceError):
            await source.fetch()


@pytest.mark.asyncio
async def test_wuthering_waves_only_emits_named_pool_lines() -> None:
    fragment = _fragment("wutheringwaves_4609")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/ArticleMenu.json"):
            return httpx.Response(
                200,
                json=[
                    {
                        "articleId": fragment["articleId"],
                        "articleTitle": fragment["articleTitle"],
                        "startTime": fragment["startTime"],
                    }
                ],
                request=request,
            )
        if request.url.path.endswith("/article/4609.json"):
            return httpx.Response(200, json=fragment, request=request)
        raise AssertionError(f"unexpected Kuro request: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await WutheringWavesSource(
            client=client,
            clock=lambda: FIXED_NOW,
        ).fetch()

    assert {row["title"] for row in rows} == {
        "雪色所映千般未来｜角色活动唤取",
        "予明日以谎言｜角色活动唤取",
        "灼霜｜武器活动唤取",
        "赝作的矮星｜武器活动唤取",
    }
    assert all("动画演出" not in row["title"] for row in rows)
    assert all(row["start_mode"] == "after_maintenance" for row in rows)


def test_azurlane_permanent_additions_do_not_use_maintenance_clock() -> None:
    fragment = _fragment("azurlane_871814659823372045")
    body = "\n".join(fragment["lines"])
    sections = _azurlane_sections(fragment["title"], body)
    source = AzurLaneSource()
    published_at = datetime_from_epoch(fragment["publish_epoch"])
    drafts = [
        source._draft(
            title=section.title,
            body_text=section.text,
            published_at=published_at,
            official_url=f"https://www.taptap.cn/moment/{fragment['article_id']}",
            article_id=fragment["article_id"],
            verified_at="2026-11-20T04:00:00Z",
            revision=f"fixture:{section.title}",
            related=[f"azurlane:article:{fragment['article_id']}"],
        )
        for section in sections
    ]

    assert len(drafts) == 3
    for draft in drafts:
        row = draft.data
        assert row["start_mode"] == "after_maintenance"
        assert row["starts_at"] is None
        assert row["ends_at"] is None
        assert row["end_kind"] == "permanent"


def test_azurlane_limited_build_uses_maintenance_relation_not_start_clock() -> None:
    fragment = _fragment("azurlane_861667880171735573")
    sections = _azurlane_sections(
        fragment["title"],
        "\n".join(fragment["lines"]),
    )
    assert len(sections) == 1
    source = AzurLaneSource()
    draft = source._draft(
        title=sections[0].title,
        body_text=sections[0].text,
        published_at=datetime_from_epoch(fragment["publish_epoch"]),
        official_url=f"https://www.taptap.cn/moment/{fragment['article_id']}",
        article_id=fragment["article_id"],
        verified_at="2026-11-20T04:00:00Z",
        revision="fixture",
    )
    row = draft.data
    assert row["title"] == "限时建造｜水星号、塞利米耶号、铁角号、长蛇号"
    assert row["start_mode"] == "after_maintenance"
    assert row["starts_at"] is None
    assert row["ends_at"] is None
    assert row["end_kind"] == "unknown"


def test_girls_frontline2_current_articles_split_into_eight_named_pools() -> None:
    fixture = _json_fixture("girlsfrontline2_current_pools.json")
    source = GirlsFrontline2Source()

    from app.tools.common.game_calendar.banner_sources.base import html_to_text
    from app.tools.common.game_calendar.banner_sources.sunborn import _gf2_sections

    articles_with_sections: list[tuple[dict[str, Any], PoolSection]] = []
    for article in fixture["articles"]:
        sections = _gf2_sections(
            article["Title"],
            html_to_text(article["Content"]),
        )
        assert len(sections) == 2
        articles_with_sections.extend((article, section) for section in sections)

    drafts = []
    for article, section in articles_with_sections:
        drafts.append(
            source._draft(
                title=section.title,
                body_text=section.text,
                published_at=datetime(
                    2026,
                    11,
                    3,
                    3,
                    tzinfo=timezone.utc,
                ),
                official_url=(
                    f"https://gf2.sunborngame.com/NewsInfo?id={article['Id']}&typeId=4"
                ),
                article_id=article["Id"],
                verified_at="2026-11-20T04:00:00Z",
                revision=f"fixture:{section.title}",
                related=[f"girlsfrontline2:article:{article['Id']}"],
                confirmed_open_at_override=(
                    datetime(2026, 11, 3, 3, tzinfo=timezone.utc)
                    if "现已开启" in article["Title"]
                    else None
                ),
            )
        )

    titles = {section.title for _, section in articles_with_sections}
    assert len(titles) == 8
    assert {
        "定向采购｜索米",
        "军备提升｜未言使命",
        "定向采购｜索普",
        "军备提升｜碎穹嚎歌",
        "定向采购｜希丽雅",
        "军备提升｜斯诺特拉",
        "定向采购｜破坏者",
        "军备提升｜盖娅终结",
    } == titles
    assert all(draft.data["start_mode"] == "after_maintenance" for draft in drafts)
    assert all(draft.data["ends_at"] == "2026-11-24T00:59:00Z" for draft in drafts)
    assert all(
        draft.data["confirmed_open_at"] == "2026-11-03T03:00:00Z" for draft in drafts
    )


def test_resonance_multi_pool_update_has_three_stable_sections() -> None:
    fragment = _fragment("resonance_872109359222491961")
    sections = _resonance_sections(
        fragment["title"],
        "\n".join(fragment["lines"]),
    )
    source = ResonanceSource()
    published_at = datetime_from_epoch(fragment["publish_epoch"])
    drafts = [
        source._draft(
            title=section.title,
            body_text=section.text,
            published_at=published_at,
            official_url=f"https://www.taptap.cn/moment/{fragment['article_id']}",
            article_id=fragment["article_id"],
            verified_at="2026-11-20T04:00:00Z",
            revision=f"fixture:{section.title}",
            related=[f"resonance:article:{fragment['article_id']}"],
        )
        for section in sections
    ]
    rows = [draft.data for draft in drafts]

    assert [row["title"] for row in rows] == [
        "特设招募｜天鳞至理",
        "专列招募｜原罪抱拥",
        "常驻招募｜那由他",
    ]
    assert [row["kind"] for row in rows] == [
        "character",
        "character",
        "standard",
    ]
    assert all(row["start_mode"] == "after_maintenance" for row in rows)
    assert [row["ends_at"] for row in rows] == [
        "2026-12-16T04:00:00Z",
        "2026-12-02T04:00:00Z",
        "2026-12-02T04:00:00Z",
    ]
    assert all("关注我们" not in row["title"] for row in rows)


@pytest.mark.asyncio
async def test_princess_connect_uses_official_sina_profile() -> None:
    html = (FIXTURES / "princessconnect_sina_6603867494.html").read_text(
        encoding="utf-8"
    )
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, text=html, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await PrincessConnectSource(
            client=client,
            clock=lambda: FIXED_NOW,
        ).fetch()

    assert requested == ["https://www.sina.cn/media/6603867494"]
    assert {row["title"] for row in rows} == {
        "精选扭蛋｜纳娜",
        "自选复刻附奖扭蛋｜限定角色",
        "白金扭蛋｜★3必得",
    }
    assert all(row["start_mode"] == "after_maintenance" for row in rows)
    assert all(row["starts_at"] is None for row in rows)
    assert all(row["end_kind"] == "unknown" for row in rows)
    assert all("临时维护" not in row["title"] for row in rows)

    nana = next(row for row in rows if row["title"] == "精选扭蛋｜纳娜")
    assert nana["confirmed_open_at"] == "2026-11-13T06:05:00Z"
    assert nana["published_at"] == "2026-11-13T06:05:00Z"
    assert nana["official_url"].endswith("/5364793474548377.html")


def test_princess_connect_legacy_taptap_fixture_still_replays() -> None:
    fragment = _fragment("princessconnect_taptap_768909398603991311")
    sections = split_pool_sections(
        fragment["title"],
        "\n".join(fragment["lines"]),
    )

    assert sections
    assert all("镜华（春日）" in section.text for section in sections)
    assert all("咲恋（沙漠）" in section.text for section in sections)
    assert "2/13 维护后～2/20 10:59" in sections[0].text


def test_time_boundaries_distinguish_end_maintenance_and_permanent() -> None:
    from app.tools.common.game_calendar.banner_sources.base import extract_time_window

    end_mode, end_start, end_value, end_confirmation = extract_time_window(
        title="限时复刻招募",
        text="招募时间：11月12日 维护结束后 ~ 11月26日 13:59",
        published_at=datetime(2026, 11, 9, tzinfo=timezone.utc),
    )
    assert end_mode == "after_maintenance"
    assert end_start is None
    assert end_value is not None
    assert end_value.isoformat() == "2026-11-26T05:59:00+00:00"
    assert end_confirmation is None

    version_mode, version_start, version_end, version_confirmation = (
        extract_time_window(
            title="冬猎",
            text="开放时间：「雪凇幽梦」版本开启后 - 2026/09/30 11:59",
            published_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
    )
    assert version_mode == "after_maintenance"
    assert version_start is None
    assert version_end is not None
    assert version_end.isoformat() == "2026-09-30T03:59:00+00:00"
    assert version_confirmation is None

    permanent = extract_time_window(
        title="常驻建造新增",
        text=("维护后永久回归常规建造\n维护时间：11月19日 10:00~15:00"),
        published_at=datetime(2026, 11, 17, tzinfo=timezone.utc),
    )
    assert permanent[0] == "after_maintenance"
    assert permanent[1] is None
    assert permanent[2] is None


def test_anchor_is_stable_across_corrections_and_uses_absolute_publication() -> None:
    source = EndfieldSource()
    original = source._draft(
        title="「原题」特许寻访说明",
        body_text="开放时间：2026/11/05 12:00（服务器时间）",
        published_at=datetime(2026, 11, 4, 10, tzinfo=timezone.utc),
        official_url="https://endfield.hypergryph.com/news/7204",
        article_id="7204",
        verified_at="2026-11-20T04:00:00Z",
        revision="first",
        anchor_title="「稳定池名」特许寻访",
    )
    correction = source._draft(
        title="「更正题」特许寻访说明（延期）",
        body_text=(
            "开放时间：2026/11/06 12:00（服务器时间）\n"
            "结束时间：2026/11/20 11:59（服务器时间）"
        ),
        published_at=datetime(2026, 11, 5, 10, tzinfo=timezone.utc),
        official_url="https://endfield.hypergryph.com/news/7300",
        article_id="7300",
        verified_at="2026-11-20T04:00:00Z",
        revision="second",
        anchor_title="「稳定池名」特许寻访",
    )
    assert original.data["source_anchor"] == correction.data["source_anchor"]
    assert original.data["publication_order"] == 1793786400
    assert correction.data["publication_order"] == 1793872800

    ordered = BaseBannerSource._finish([correction, original])
    assert [row["article_id"] for row in ordered] == ["7300"]


def test_official_pool_id_is_not_news_article_id() -> None:
    draft = EndfieldSource()._draft(
        title="「测试」特许寻访 卡池ID: pool_42",
        body_text="开放时间：2026/11/05 12:00（服务器时间）",
        published_at=datetime(2026, 11, 4, 10, tzinfo=timezone.utc),
        official_url="https://endfield.hypergryph.com/news/7204",
        article_id="7204",
        official_id="pool_42",
        verified_at="2026-11-20T04:00:00Z",
        revision="fixture",
    )
    assert draft.data["official_id"] == "pool_42"
    assert draft.data["article_id"] == "7204"
    assert draft.data["source_anchor"] == "endfield:official:pool_42"
    assert set(draft.data) == _observation_shape()


def test_revision_ignores_reaction_counters() -> None:
    item = _json_fixture("bluearchive_bilibili_opus_1168392597461270533.json")
    changed_item = copy.deepcopy(item)
    changed_item["modules"].append(
        {
            "module_type": "MODULE_TYPE_STAT",
            "module_stat": {
                "like": {"count": 999},
                "comment": {"count": 1000},
            },
        }
    )
    source = BlueArchiveBilibiliSource()
    original = source._draft_items(
        item=item,
        verified_at="2026-11-20T04:00:00Z",
        public_url="https://www.bilibili.com/opus/1168392597461270533",
    )
    changed = source._draft_items(
        item=changed_item,
        verified_at="2026-11-20T04:05:00Z",
        public_url="https://www.bilibili.com/opus/1168392597461270533",
    )
    assert [row.data["revision"] for row in original] == [
        row.data["revision"] for row in changed
    ]

    moment = {
        "publish_time": "1794979874",
        "edited_time": "1794979874",
        "topic": {
            "title": "《雷索纳斯》11月18日更新公告",
            "summary": "summary is not used when full lines exist",
        },
        "reaction_count": "1",
    }
    changed_moment = copy.deepcopy(moment)
    changed_moment["reaction_count"] = "999"
    lines = ["正文"]
    first = _record_from_detail(
        moment=moment,
        lines=lines,
        article_id="872109359222491961",
    )
    second = _record_from_detail(
        moment=changed_moment,
        lines=lines,
        article_id="872109359222491961",
    )
    assert first.revision == second.revision
