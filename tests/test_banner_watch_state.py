from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest

from app.core.banner_watch.state import (
    BannerWatchState,
    SubscriptionConflict,
)

UTC = timezone.utc
NOW = datetime(2026, 11, 20, tzinfo=UTC)
REGION = ("arknights", "cn")


def iso(value: datetime) -> str:
    return (
        value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def observation(anchor: str = "one", **changes):
    value = {
        "game": REGION[0],
        "server": REGION[1],
        "title": f"Banner {anchor}",
        "kind": "character",
        "start_mode": "scheduled",
        "starts_at": iso(NOW + timedelta(hours=2)),
        "ends_at": iso(NOW + timedelta(days=2)),
        "confirmed_open_at": None,
        "official_url": f"https://example.com/{anchor}",
        "verified_at": iso(NOW),
        "official_id": f"official-{anchor}",
        "source_anchor": f"test:{anchor}",
        "revision": "source:1",
        "cancelled": False,
        "publication_order": 0,
        "end_kind": "dated",
        "published_at": iso(NOW - timedelta(hours=1)),
    }
    value.update(changes)
    return value


def primed_state(path, *, followed_at=NOW):
    state = BannerWatchState(path)
    state.update_subscriptions({REGION}, 0, followed_at)
    state.apply_observations(REGION, [], followed_at)
    state.plan(followed_at)
    return state


def test_empty_opt_out_and_optimistic_revision(tmp_path):
    state = BannerWatchState(tmp_path / "watch.sqlite3")

    assert state.update_subscriptions([], 0, NOW)["subscriptionRevision"] == 1
    assert state.update_subscriptions({REGION}, 1, NOW)["subscriptionRevision"] == 2
    with pytest.raises(SubscriptionConflict) as caught:
        state.update_subscriptions([], 1, NOW)

    assert caught.value.current_revision == 2
    assert state.snapshot(NOW)["subscriptions"] == [
        {"game": REGION[0], "server": REGION[1]}
    ]
    assert (
        BannerWatchState(tmp_path / "watch.sqlite3").snapshot(NOW)[
            "subscriptionRevision"
        ]
        == 2
    )


def test_first_follow_waits_for_discovery_and_never_catches_up_open(tmp_path):
    path = tmp_path / "watch.sqlite3"
    state = BannerWatchState(path)
    state.update_subscriptions({REGION}, 0, NOW)

    assert state.plan(NOW) == []
    state.source_failure(REGION, "TimeoutError", NOW)
    assert state.claim("mail", NOW) is None

    future = observation("future")
    ongoing = observation(
        "ongoing",
        starts_at=iso(NOW - timedelta(hours=2)),
        ends_at=iso(NOW + timedelta(days=1)),
    )
    undated = observation("undated", start_mode="tbd", starts_at=None, ends_at=None)
    state.apply_observations(REGION, [future, ongoing, undated], NOW)
    state.plan(NOW)
    claim = state.claim("mail", NOW)

    assert claim is not None
    assert claim.kind == "first_follow"
    assert [banner["title"] for banner in claim.banners] == ["Banner future"]
    state.finish(claim, "delivered", None, NOW)
    assert state.claim("mail", NOW) is None

    resumed = BannerWatchState(path)
    resumed.plan(NOW)
    assert resumed.claim("mail", NOW) is None
    source = resumed.snapshot(NOW)["sources"][0]
    assert source["last_success_at"] == iso(NOW)
    assert source["error"] is None


def test_scheduled_groups_and_maintenance_open_are_distinct(tmp_path):
    state = primed_state(
        tmp_path / "watch.sqlite3", followed_at=NOW - timedelta(hours=1)
    )
    start = NOW + timedelta(hours=1)
    maintenance_start = NOW + timedelta(hours=2)
    first = observation("first", starts_at=iso(start))
    second = observation(
        "second", starts_at=iso(start + timedelta(seconds=20)), publication_order=1
    )
    maintenance = observation(
        "maintenance",
        start_mode="after_maintenance",
        starts_at=iso(maintenance_start),
        confirmed_open_at=None,
    )
    state.apply_observations(REGION, [first, second, maintenance], NOW)
    state.plan(NOW)

    scheduled = state.claim("mail", NOW)
    assert scheduled is not None and scheduled.kind == "announcement"
    assert len(scheduled.banners) == 2
    state.finish(scheduled, "delivered", None, NOW)
    announced_maintenance = state.claim("mail", NOW)
    assert announced_maintenance is not None
    assert announced_maintenance.kind == "announcement"
    state.finish(announced_maintenance, "delivered", None, NOW)

    state.plan(maintenance_start)
    opening = state.claim("mail", maintenance_start)
    assert opening is not None and opening.kind == "catchup"
    assert len(opening.banners) == 2
    state.finish(opening, "delivered", None, maintenance_start)
    assert state.claim("mail", maintenance_start) is None

    confirmed = dict(maintenance)
    confirmed.update(
        confirmed_open_at=iso(maintenance_start),
        verified_at=iso(maintenance_start),
        revision="source:2",
    )
    state.apply_observations(REGION, [confirmed], maintenance_start)
    state.plan(maintenance_start)
    maintenance_open = state.claim("mail", maintenance_start)

    assert maintenance_open is not None
    assert maintenance_open.kind == "opening"
    assert len(maintenance_open.banners) == 1
    assert maintenance_open.banners[0]["confirmed_open_at"] == iso(maintenance_start)
    state.finish(maintenance_open, "delivered", None, maintenance_start)
    assert state.claim("mail", maintenance_start) is None
    assert all(
        banner["status"] == "open"
        for banner in state.snapshot(maintenance_start)["banners"]
    )


def test_concurrent_claim_has_one_channel_winner(tmp_path):
    path = tmp_path / "watch.sqlite3"
    state = primed_state(path)
    state.apply_observations(REGION, [observation()], NOW)
    state.plan(NOW)
    other = BannerWatchState(path)
    barrier = Barrier(2)

    def claim(instance):
        barrier.wait()
        return instance.claim("mail", NOW)

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(claim, (state, other)))

    assert sum(claim is not None for claim in claims) == 1
    second_channel = state.claim("webhook", NOW)
    assert second_channel is not None
    state.finish(second_channel, "delivered", None, NOW)
    assert state.claim("webhook", NOW) is None


def test_pre_and_post_send_crash_replay(tmp_path):
    pre_path = tmp_path / "pre.sqlite3"
    pre = primed_state(pre_path)
    pre.apply_observations(REGION, [observation()], NOW)
    pre.plan(NOW)
    interrupted = pre.claim("mail", NOW)
    assert interrupted is not None

    recovered = BannerWatchState(pre_path)
    recovered.plan(NOW + timedelta(minutes=1))
    assert recovered.claim("mail", NOW + timedelta(minutes=1)) is None
    result = recovered.finish(
        interrupted, "delivered", "late_reply", NOW + timedelta(minutes=2)
    )
    assert result["status"] == "unknown"
    assert result["reason"] == "interrupted"

    post_path = tmp_path / "post.sqlite3"
    post = primed_state(post_path)
    post.apply_observations(REGION, [observation()], NOW)
    post.plan(NOW)
    sent = post.claim("mail", NOW)
    assert sent is not None
    post.finish(sent, "delivered", None, NOW, receipt={"code": 0})

    replayed = BannerWatchState(post_path)
    replayed.plan(NOW + timedelta(minutes=1))
    assert replayed.claim("mail", NOW + timedelta(minutes=1)) is None
    receipt = replayed.finish(sent, "delivered", None, NOW + timedelta(minutes=1))
    assert receipt["status"] == "delivered"
    assert receipt["receipt"] == {"code": 0}


def test_partial_channels_and_corrected_versions(tmp_path):
    state = primed_state(tmp_path / "watch.sqlite3")
    state.apply_observations(REGION, [observation()], NOW)
    state.plan(NOW)
    delivered = state.claim("mail", NOW)
    unknown = state.claim("webhook", NOW)
    assert delivered is not None and unknown is not None
    state.finish(delivered, "delivered", None, NOW)
    state.finish(unknown, "unknown", "timeout", NOW)
    assert state.claim("mail", NOW) is None
    assert state.claim("webhook", NOW) is None

    corrected = observation(
        starts_at=iso(NOW + timedelta(hours=3)),
        verified_at=iso(NOW + timedelta(minutes=1)),
        revision="source:2",
    )
    state.apply_observations(REGION, [corrected], NOW + timedelta(minutes=1))
    state.plan(NOW + timedelta(minutes=1))

    assert state.claim("mail", NOW, notice_kind="opening") is None
    correction = state.claim(
        "mail",
        NOW + timedelta(minutes=1),
        notice_kind="correction",
        region=REGION,
    )
    assert correction is not None
    assert correction.kind == "correction"
    assert correction.version == delivered.version + 1
    state.finish(correction, "delivered", None, NOW + timedelta(minutes=1))
    webhook_correction = state.claim("webhook", NOW + timedelta(minutes=1))
    assert webhook_correction is not None
    assert webhook_correction.intent_id == correction.intent_id
    state.finish(webhook_correction, "rejected", "configuration", NOW)


def test_old_calendar_catchup_preserves_follow_time_and_open_rules(tmp_path):
    path = tmp_path / "watch.sqlite3"
    followed_at = NOW - timedelta(hours=30)
    state = BannerWatchState(path)
    state.update_subscriptions({REGION}, 0, followed_at)
    state.apply_observations(REGION, [], followed_at)
    state.plan(followed_at)
    state.update_subscriptions(
        {REGION, ("azurlane", "cn")}, 1, NOW - timedelta(hours=1)
    )
    start = NOW - timedelta(hours=2)
    valid = observation(
        "valid", starts_at=iso(start), ends_at=iso(NOW + timedelta(hours=2))
    )
    permanent = observation(
        "permanent", starts_at=iso(start), ends_at=None, end_kind="permanent"
    )
    too_old = observation(
        "too-old",
        starts_at=iso(NOW - timedelta(hours=24, microseconds=1)),
        ends_at=iso(NOW + timedelta(days=1)),
    )
    ended = observation(
        "ended", starts_at=iso(start), ends_at=iso(NOW - timedelta(hours=1))
    )
    unknown_open = observation(
        "unknown-open", starts_at=iso(start), ends_at=None, end_kind="dated"
    )
    boundary = observation(
        "boundary",
        starts_at=iso(NOW - timedelta(hours=24)),
        ends_at=iso(NOW + timedelta(hours=1)),
    )
    state.apply_observations(
        REGION, [valid, permanent, too_old, ended, unknown_open, boundary], NOW
    )
    state.plan(NOW)

    first = state.claim("mail", NOW, notice_kind="catchup")
    second = state.claim("mail", NOW, notice_kind="catchup")
    assert first is not None and second is not None
    caught_up = {
        banner["title"] for claim in (first, second) for banner in claim.banners
    }
    assert caught_up == {"Banner valid", "Banner permanent", "Banner boundary"}
    assert state.claim("mail", NOW) is None

    replay = observation(
        "valid",
        title="Stale replay",
        starts_at=iso(start),
        ends_at=iso(NOW + timedelta(hours=2)),
        verified_at=iso(NOW - timedelta(minutes=1)),
        revision="source:old",
    )
    state.apply_observations(REGION, [replay], NOW + timedelta(minutes=1))
    current = next(
        banner
        for banner in state.snapshot(NOW + timedelta(minutes=31))["banners"]
        if banner["title"] != "Stale replay"
        and banner["official_url"].endswith("/valid")
    )
    assert current["title"] == "Banner valid"
    assert current["status"] == "open"
    assert current["stale"] is True
    state.source_failure(REGION, "TimeoutError", NOW + timedelta(minutes=32))
    refreshed = next(
        banner
        for banner in state.snapshot(NOW + timedelta(minutes=32))["banners"]
        if banner["official_url"].endswith("/valid")
    )
    assert refreshed["status"] == "open"
    assert refreshed["stale"] is True


def test_explicit_cancel_cancels_pending_and_corrects_unknown(tmp_path):
    pending = primed_state(tmp_path / "pending.sqlite3")
    pending.apply_observations(REGION, [observation()], NOW)
    pending.plan(NOW)
    cancelled = observation(
        cancelled=True,
        verified_at=iso(NOW + timedelta(minutes=1)),
        revision="source:cancelled",
    )
    pending.apply_observations(REGION, [cancelled], NOW + timedelta(minutes=1))
    pending.plan(NOW + timedelta(minutes=1))

    assert pending.claim("mail", NOW + timedelta(minutes=1)) is None
    assert pending.snapshot(NOW)["banners"][0]["status"] == "cancelled"

    unknown = primed_state(tmp_path / "unknown.sqlite3")
    unknown.apply_observations(REGION, [observation()], NOW)
    unknown.plan(NOW)
    interrupted = unknown.claim("mail", NOW)
    assert interrupted is not None
    unknown.finish(interrupted, "unknown", "timeout", NOW)
    unknown.apply_observations(REGION, [cancelled], NOW + timedelta(minutes=1))
    unknown.plan(NOW + timedelta(minutes=1))
    correction = unknown.claim("mail", NOW + timedelta(minutes=1))

    assert correction is not None
    assert correction.kind == "correction"
    assert correction.banners[0]["status"] == "cancelled"


def test_alias_merge_retains_metadata_and_versions(tmp_path):
    state = primed_state(tmp_path / "watch.sqlite3")
    original = observation(end_kind="dated")
    state.apply_observations(REGION, [original], NOW)
    state.plan(NOW)
    first = state.claim("mail", NOW)
    assert first is not None
    state.finish(first, "delivered", None, NOW)
    banner_id = state.snapshot(NOW)["banners"][0]["id"]

    corrected = observation(
        source_anchor="test:new-anchor",
        starts_at=iso(NOW + timedelta(hours=3)),
        verified_at=iso(NOW + timedelta(minutes=1)),
        revision="source:2",
        end_kind="permanent",
        published_at=iso(NOW + timedelta(minutes=1)),
    )
    state.apply_observations(REGION, [corrected], NOW + timedelta(minutes=1))
    assert len(state.snapshot(NOW)["banners"]) == 1
    assert state.snapshot(NOW)["banners"][0]["id"] == banner_id
    state.plan(NOW + timedelta(minutes=1))
    second = state.claim("mail", NOW + timedelta(minutes=1))
    assert second is not None and second.version == 2
    state.finish(second, "delivered", None, NOW + timedelta(minutes=1))

    replaced = observation(
        official_id="official-replacement",
        source_anchor="test:replacement",
        replaces=["test:new-anchor"],
        starts_at=iso(NOW + timedelta(hours=4)),
        verified_at=iso(NOW + timedelta(minutes=2)),
        revision="source:3",
        end_kind="permanent",
        published_at=iso(NOW + timedelta(minutes=2)),
    )
    state.apply_observations(REGION, [replaced], NOW + timedelta(minutes=2))
    state.plan(NOW + timedelta(minutes=2))
    third = state.claim("mail", NOW + timedelta(minutes=2))
    banners = state.snapshot(NOW + timedelta(minutes=33))["banners"]

    assert len(banners) == 1
    assert banners[0]["id"] == banner_id
    assert banners[0]["end_kind"] == "permanent"
    assert banners[0]["published_at"] == iso(NOW + timedelta(minutes=2))
    assert banners[0]["stale"] is True
    assert third is not None and third.version == 3


def test_claim_rebuilds_stale_payload_after_source_outage(tmp_path):
    state = primed_state(tmp_path / "watch.sqlite3")
    state.apply_observations(REGION, [observation()], NOW)
    state.plan(NOW)
    state.source_failure(REGION, "TimeoutError", NOW + timedelta(minutes=1))

    claim = state.claim("mail", NOW + timedelta(minutes=1))

    assert claim is not None
    assert claim.banners[0]["stale"] is True
    with sqlite3.connect(state.path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2


@pytest.mark.parametrize("new_mode", ["scheduled", "tbd"])
def test_only_opening_was_sent_before_official_reschedule(tmp_path, new_mode):
    state = primed_state(
        tmp_path / "watch.sqlite3", followed_at=NOW - timedelta(hours=3)
    )
    initial = observation(starts_at=iso(NOW), end_kind="known")
    state.apply_observations(REGION, [initial], NOW)
    state.plan(NOW)
    opening = state.claim("channel", NOW)
    assert opening is not None and opening.kind == "opening"
    state.finish(opening, "delivered", None, NOW)

    revised_at = NOW + timedelta(minutes=10)
    revised = {
        **initial,
        "start_mode": new_mode,
        "starts_at": iso(NOW + timedelta(hours=3)) if new_mode == "scheduled" else None,
        "published_at": iso(revised_at),
        "verified_at": iso(revised_at),
        "revision": "source:2",
    }
    state.apply_observations(REGION, [revised], revised_at)
    state.plan(revised_at)
    correction = state.claim("channel", revised_at)
    assert correction is not None and correction.kind == "correction"
    assert correction.banners[0]["id"] == opening.banners[0]["id"]
    assert correction.banners[0]["start_mode"] == new_mode
