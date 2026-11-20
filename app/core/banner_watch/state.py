# SPDX-License-Identifier: AGPL-3.0-or-later
"""Durable subscriptions, observations, and notification outbox for banner watch."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterable, Mapping, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Literal

UTC = timezone.utc
OutboxStatus = Literal["delivered", "rejected", "unknown"]

GAME_SERVERS = {
    "endfield": ("明日方舟：终末地", ("cn", "global")),
    "wutheringwaves": ("鸣潮", ("cn", "global")),
    "arknights": ("明日方舟", ("cn", "jp", "global")),
    "bluearchive": ("蔚蓝档案", ("cn", "jp", "global")),
    "princessconnect": ("公主连结", ("cn", "jp")),
    "azurlane": ("碧蓝航线", ("cn", "jp", "global")),
    "girlsfrontline2": ("少女前线2：追放", ("cn", "global")),
    "resonance": ("雷索纳斯", ("cn", "jp")),
}
SERVER_NAMES = {"cn": "国服", "jp": "日服", "global": "国际服"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS subscriptions (
    game TEXT NOT NULL,
    server TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    first_follow_done INTEGER NOT NULL DEFAULT 0,
    first_follow_ready INTEGER NOT NULL DEFAULT 0,
    followed_at TEXT NOT NULL,
    PRIMARY KEY (game, server)
);
CREATE TABLE IF NOT EXISTS sources (
    game TEXT NOT NULL,
    server TEXT NOT NULL,
    last_success_at TEXT,
    error TEXT,
    last_attempt_at TEXT NOT NULL,
    PRIMARY KEY (game, server)
);
CREATE TABLE IF NOT EXISTS banners (
    id TEXT PRIMARY KEY,
    game TEXT NOT NULL,
    server TEXT NOT NULL,
    source_anchor TEXT NOT NULL,
    title TEXT NOT NULL,
    kind TEXT NOT NULL,
    start_mode TEXT NOT NULL,
    starts_at TEXT,
    ends_at TEXT,
    confirmed_open_at TEXT,
    official_url TEXT NOT NULL,
    verified_at TEXT NOT NULL,
    end_kind TEXT,
    published_at TEXT,
    official_id TEXT,
    cancelled INTEGER NOT NULL DEFAULT 0,
    source_revision TEXT NOT NULL,
    publication_order INTEGER NOT NULL DEFAULT 0,
    stale INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (game, server, source_anchor)
);
CREATE TABLE IF NOT EXISTS series (
    event_kind TEXT NOT NULL,
    game TEXT NOT NULL,
    server TEXT NOT NULL,
    group_key TEXT NOT NULL,
    version INTEGER NOT NULL,
    fingerprint TEXT NOT NULL,
    current_intent_id TEXT,
    PRIMARY KEY (event_kind, game, server, group_key)
);
CREATE TABLE IF NOT EXISTS intents (
    id TEXT PRIMARY KEY,
    event_kind TEXT NOT NULL,
    notice_kind TEXT NOT NULL,
    game TEXT NOT NULL,
    server TEXT NOT NULL,
    group_key TEXT NOT NULL,
    version INTEGER NOT NULL,
    subscription_revision INTEGER NOT NULL,
    due_at TEXT NOT NULL,
    expires_at TEXT,
    payload TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notice_state (
    banner_id TEXT NOT NULL,
    event_kind TEXT NOT NULL,
    group_key TEXT NOT NULL,
    intent_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    PRIMARY KEY (banner_id, event_kind)
);
CREATE TABLE IF NOT EXISTS banner_aliases (
    game TEXT NOT NULL,
    server TEXT NOT NULL,
    alias TEXT NOT NULL,
    banner_id TEXT NOT NULL,
    PRIMARY KEY (game, server, alias)
);
CREATE TABLE IF NOT EXISTS outbox (
    intent_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    status TEXT NOT NULL,
    claim_token TEXT UNIQUE,
    version INTEGER NOT NULL,
    subscription_revision INTEGER NOT NULL,
    claimed_at TEXT,
    finished_at TEXT,
    reason TEXT,
    receipt_json TEXT,
    PRIMARY KEY (intent_id, channel_id)
);
CREATE INDEX IF NOT EXISTS intents_due ON intents(active, due_at, expires_at);
CREATE INDEX IF NOT EXISTS outbox_claim ON outbox(channel_id, status, intent_id);
"""


class SubscriptionConflict(RuntimeError):
    """The caller's optimistic subscription revision is stale."""

    def __init__(self, expected: int, actual: int) -> None:
        self.expected_revision = expected
        self.current_revision = actual
        super().__init__(
            f"subscription revision {expected} is stale; current is {actual}"
        )


@dataclass(frozen=True)
class BannerClaim:
    """An atomic per-channel claim; banners are immutable snapshots of the intent."""

    intent_id: str
    channel_id: str
    version: int
    subscription_revision: int
    token: str
    kind: str
    banners: tuple[dict[str, Any], ...]

    @property
    def claim_token(self) -> str:
        return self.token


def _dt(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise TypeError("expected a datetime or ISO datetime string")
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime | str) -> str:
    return _dt(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _optional_iso(value: object) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, (datetime, str)):
        raise TypeError("expected an ISO datetime string or None")
    return _iso(value)


def _region(value: object) -> tuple[str, str]:
    if isinstance(value, Mapping):
        value = (value.get("game"), value.get("server"))
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 2
    ):
        raise ValueError("region must contain game and server")
    game, server = str(value[0]), str(value[1])
    if game not in GAME_SERVERS or server not in GAME_SERVERS[game][1]:
        raise ValueError(f"unsupported banner region: {game}/{server}")
    return game, server


def _banner_id(game: str, server: str, anchor: str) -> str:
    digest = hashlib.sha256(f"{game}\0{server}\0{anchor}".encode()).hexdigest()
    return f"bw_{digest[:24]}"


def _status(row: Mapping[str, Any], now: datetime) -> str:
    if row["cancelled"]:
        return "cancelled"
    if row["ends_at"] is not None and now >= _dt(row["ends_at"]):
        return "ended"
    confirmed = row["confirmed_open_at"]
    if confirmed is not None and now >= _dt(confirmed):
        return "open"
    if (
        row["start_mode"] == "scheduled"
        and row["starts_at"] is not None
        and now >= _dt(row["starts_at"])
    ):
        return "open"
    return "pending" if row["start_mode"] == "tbd" else "announced"


def _public_banner(row: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    return {
        "id": row["id"],
        "game": row["game"],
        "server": row["server"],
        "title": row["title"],
        "kind": row["kind"],
        "start_mode": row["start_mode"],
        "starts_at": row["starts_at"],
        "ends_at": row["ends_at"],
        "confirmed_open_at": row["confirmed_open_at"],
        "official_url": row["official_url"],
        "verified_at": row["verified_at"],
        "end_kind": row["end_kind"],
        "published_at": row["published_at"],
        "status": _status(row, now),
        "stale": bool(row["stale"])
        or now - _dt(row["verified_at"]) > timedelta(minutes=30),
    }


def _digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _minute(value: str) -> str:
    return _iso(_dt(value).replace(second=0, microsecond=0))


def _banner_fingerprint(row: Mapping[str, Any], event_kind: str) -> str:
    # Actual-open evidence has its own opening event. It is not a schedule
    # correction; only a real schedule/content change rewrites an announcement.
    confirmed = (
        row["confirmed_open_at"]
        if event_kind == "opening" and row["start_mode"] != "scheduled"
        else None
    )
    return _digest(
        [
            row["title"],
            row["kind"],
            row["start_mode"],
            row["starts_at"],
            row["ends_at"],
            confirmed,
            row["official_url"],
            row["end_kind"],
            bool(row["cancelled"]),
            event_kind,
        ]
    )


def _future_banner(row: Mapping[str, Any], now: datetime) -> bool:
    if row["cancelled"]:
        return False
    if row["ends_at"] is not None and now >= _dt(row["ends_at"]):
        return False
    if row["start_mode"] == "scheduled":
        return row["starts_at"] is not None and now < _dt(row["starts_at"])
    if row["start_mode"] == "after_maintenance":
        return row["confirmed_open_at"] is None
    return False


class BannerWatchState:
    """SQLite-backed state with short single-writer transactions."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            db.execute("PRAGMA journal_mode = WAL")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 2:
                raise RuntimeError(
                    f"banner watch schema {version} is newer than supported"
                )
            db.executescript(_SCHEMA)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(banners)")}
            for column in ("end_kind", "published_at", "official_id"):
                if column not in columns:
                    db.execute(f"ALTER TABLE banners ADD COLUMN {column} TEXT")
            if version < 2:
                self._normalize_legacy_times(db)
            for row in db.execute(
                "SELECT id, game, server, source_anchor FROM banners"
            ):
                db.execute(
                    "INSERT OR IGNORE INTO banner_aliases(game, server, alias, banner_id) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        row["game"],
                        row["server"],
                        f"anchor:{row['source_anchor']}",
                        row["id"],
                    ),
                )
            db.execute(
                "INSERT OR IGNORE INTO metadata(key, value) VALUES "
                "('subscription_revision', '0')"
            )
            db.execute("PRAGMA user_version = 2")
            # A claim has no channel-side lookup or idempotency guarantee. After
            # restart its outcome is therefore unknown and must not be retried.
            db.execute(
                "UPDATE outbox SET status = 'unknown', "
                "reason = COALESCE(reason, 'interrupted'), "
                "finished_at = ? WHERE status = 'claimed'",
                (_iso(datetime.now(UTC)),),
            )
            db.commit()

    @staticmethod
    def _normalize_legacy_times(db: sqlite3.Connection) -> None:
        columns = {
            "subscriptions": ("followed_at",),
            "sources": ("last_success_at", "last_attempt_at"),
            "banners": (
                "starts_at",
                "ends_at",
                "confirmed_open_at",
                "verified_at",
                "published_at",
                "first_seen_at",
                "updated_at",
            ),
            "intents": ("due_at", "expires_at", "created_at"),
            "outbox": ("claimed_at", "finished_at"),
        }
        for table, names in columns.items():
            for row in db.execute(f"SELECT rowid, * FROM {table}").fetchall():
                changes = {
                    name: _iso(row[name])
                    for name in names
                    if row[name] is not None and row[name] != _iso(row[name])
                }
                if changes:
                    assignments = ", ".join(f"{name} = ?" for name in changes)
                    db.execute(
                        f"UPDATE {table} SET {assignments} WHERE rowid = ?",
                        (*changes.values(), row["rowid"]),
                    )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA busy_timeout = 5000")
        return db

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with closing(self._connect()) as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    @staticmethod
    def _revision(db: sqlite3.Connection) -> int:
        row = db.execute(
            "SELECT value FROM metadata WHERE key = 'subscription_revision'"
        ).fetchone()
        return int(row[0])

    def snapshot(self, now: datetime | str | None = None) -> dict[str, Any]:
        current = _dt(now or datetime.now(UTC))
        with closing(self._connect()) as db:
            db.execute("BEGIN")
            revision = self._revision(db)
            subscriptions = [
                {"game": row["game"], "server": row["server"]}
                for row in db.execute(
                    "SELECT game, server FROM subscriptions WHERE active = 1 "
                    "ORDER BY game, server"
                )
            ]
            banners = [
                _public_banner(row, current)
                for row in db.execute(
                    "SELECT * FROM banners ORDER BY game, server, "
                    "COALESCE(starts_at, confirmed_open_at, '9999'), id"
                )
            ]
            sources = [
                {
                    "game": row["game"],
                    "server": row["server"],
                    "last_success_at": row["last_success_at"],
                    "error": row["error"],
                }
                for row in db.execute("SELECT * FROM sources ORDER BY game, server")
            ]
            db.commit()
        covered = {(row["game"], row["server"]) for row in sources}
        games = [
            {
                "id": game,
                "name": label,
                "servers": [
                    {
                        "id": server,
                        "name": SERVER_NAMES[server],
                        "covered": (game, server) in covered,
                        "managed": False,
                    }
                    for server in servers
                ],
            }
            for game, (label, servers) in GAME_SERVERS.items()
        ]
        return {
            "games": games,
            "subscriptions": subscriptions,
            "subscriptionRevision": revision,
            "banners": banners,
            "sources": sources,
        }

    read = snapshot
    get = snapshot

    def update_subscriptions(
        self,
        regions: Iterable[tuple[str, str] | Mapping[str, str]],
        revision: int,
        now: datetime | str | None = None,
    ) -> dict[str, Any]:
        current = _dt(now or datetime.now(UTC))
        selected = {_region(region) for region in regions}
        with self._transaction() as db:
            actual = self._revision(db)
            if revision != actual:
                raise SubscriptionConflict(revision, actual)
            previous = {
                (row["game"], row["server"])
                for row in db.execute(
                    "SELECT game, server FROM subscriptions WHERE active = 1"
                )
            }
            # The first explicit empty save is a durable opt-out from any
            # managed-account defaults owned by the integration layer.
            if selected == previous and (selected or actual != 0):
                return self.snapshot(current)
            next_revision = actual + 1
            db.execute(
                "UPDATE metadata SET value = ? WHERE key = 'subscription_revision'",
                (str(next_revision),),
            )
            for game, server in previous - selected:
                db.execute(
                    "UPDATE subscriptions SET active = 0 WHERE game = ? AND server = ?",
                    (game, server),
                )
            for game, server in selected:
                ready = db.execute(
                    "SELECT EXISTS(SELECT 1 FROM sources WHERE game = ? AND server = ? "
                    "AND last_success_at IS NOT NULL) OR "
                    "EXISTS(SELECT 1 FROM banners WHERE game = ? AND server = ?)",
                    (game, server, game, server),
                ).fetchone()[0]
                db.execute(
                    "INSERT INTO subscriptions(game, server, active, first_follow_ready, followed_at) "
                    "VALUES (?, ?, 1, ?, ?) "
                    "ON CONFLICT(game, server) DO UPDATE SET active = 1, "
                    "first_follow_ready = MAX(subscriptions.first_follow_ready, excluded.first_follow_ready), "
                    "followed_at = CASE WHEN subscriptions.active = 1 "
                    "THEN subscriptions.followed_at ELSE excluded.followed_at END",
                    (game, server, ready, _iso(current)),
                )
            inactive = [region for region in previous - selected]
            for game, server in inactive:
                rows = db.execute(
                    "SELECT id FROM intents WHERE game = ? AND server = ? AND active = 1",
                    (game, server),
                ).fetchall()
                for row in rows:
                    self._deactivate(db, row["id"], current, "unsubscribed")
            db.execute(
                "UPDATE intents SET subscription_revision = ? WHERE active = 1",
                (next_revision,),
            )
        return self.snapshot(current)

    def apply_observations(
        self,
        region: tuple[str, str],
        observations: Sequence[Mapping[str, Any]],
        now: datetime | str | None = None,
    ) -> dict[str, Any]:
        game, server = _region(region)
        current = _dt(now or datetime.now(UTC))
        with self._transaction() as db:
            db.execute(
                "UPDATE banners SET stale = 1, updated_at = ? WHERE game = ? AND server = ?",
                (_iso(current), game, server),
            )
            for observation in observations:
                if _region((observation["game"], observation["server"])) != (
                    game,
                    server,
                ):
                    raise ValueError("observation region does not match its source")
                self._merge_observation(db, game, server, observation, current)
            self._source_success(db, game, server, current)
        return self.snapshot(current)

    def _merge_observation(
        self,
        db: sqlite3.Connection,
        game: str,
        server: str,
        observation: Mapping[str, Any],
        now: datetime,
    ) -> None:
        title = str(observation["title"]).strip()
        url = str(observation["official_url"]).strip()
        if not title or not url:
            raise ValueError("banner title and official_url are required")
        mode = observation["start_mode"]
        if mode not in {"scheduled", "after_maintenance", "tbd"}:
            raise ValueError(f"unsupported start_mode: {mode}")
        starts_at = _optional_iso(observation.get("starts_at"))
        ends_at = _optional_iso(observation.get("ends_at"))
        confirmed = _optional_iso(observation.get("confirmed_open_at"))
        if mode == "scheduled" and starts_at is None:
            raise ValueError("a scheduled banner requires a definite starts_at")
        if starts_at and ends_at and _dt(ends_at) < _dt(starts_at):
            raise ValueError("banner ends_at precedes starts_at")
        verified_at = _iso(observation["verified_at"])
        anchor = str(
            observation.get("source_anchor")
            or observation.get("official_id")
            or f"{title}\0{url}"
        ).strip()
        official_id = observation.get("official_id")
        official_id = str(official_id).strip() if official_id is not None else None
        replaces_value = observation.get("replaces", ())
        if isinstance(replaces_value, str) or replaces_value is None:
            replaces_value = (replaces_value,) if replaces_value else ()
        aliases = {f"anchor:{anchor}"}
        if official_id:
            aliases.add(f"official:{official_id}")
        for replaced in replaces_value:
            replaced = str(replaced).strip()
            if replaced:
                aliases.update(
                    {
                        f"anchor:{replaced}",
                        f"official:{replaced}",
                        f"replaces:{replaced}",
                    }
                )
        banner_id = None
        for alias in sorted(aliases):
            row = db.execute(
                "SELECT banner_id FROM banner_aliases WHERE game = ? AND server = ? AND alias = ?",
                (game, server, alias),
            ).fetchone()
            if row is not None:
                banner_id = row["banner_id"]
                break
        if banner_id is None:
            for replaced in replaces_value:
                row = db.execute(
                    "SELECT id FROM banners WHERE game = ? AND server = ? "
                    "AND (id = ? OR source_anchor = ?)",
                    (game, server, str(replaced), str(replaced)),
                ).fetchone()
                if row is not None:
                    banner_id = row["id"]
                    break
        banner_id = banner_id or _banner_id(game, server, anchor)
        existing = db.execute(
            "SELECT verified_at, first_seen_at FROM banners WHERE id = ?", (banner_id,)
        ).fetchone()
        for alias in aliases:
            db.execute(
                "INSERT OR REPLACE INTO banner_aliases(game, server, alias, banner_id) "
                "VALUES (?, ?, ?, ?)",
                (game, server, alias, banner_id),
            )
        if existing is not None and _dt(verified_at) < _dt(existing["verified_at"]):
            db.execute("UPDATE banners SET stale = 0 WHERE id = ?", (banner_id,))
            return
        db.execute(
            "INSERT INTO banners(id, game, server, source_anchor, title, kind, start_mode, "
            "starts_at, ends_at, confirmed_open_at, official_url, verified_at, "
            "end_kind, published_at, official_id, cancelled, "
            "source_revision, publication_order, stale, first_seen_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET title = excluded.title, kind = excluded.kind, "
            "start_mode = excluded.start_mode, starts_at = excluded.starts_at, "
            "ends_at = excluded.ends_at, confirmed_open_at = excluded.confirmed_open_at, "
            "official_url = excluded.official_url, verified_at = excluded.verified_at, "
            "end_kind = excluded.end_kind, published_at = excluded.published_at, "
            "official_id = excluded.official_id, "
            "cancelled = excluded.cancelled, source_revision = excluded.source_revision, "
            "publication_order = excluded.publication_order, stale = 0, updated_at = excluded.updated_at",
            (
                banner_id,
                game,
                server,
                anchor,
                title,
                str(observation["kind"]),
                mode,
                starts_at,
                ends_at,
                confirmed,
                url,
                verified_at,
                (
                    str(observation["end_kind"])
                    if observation.get("end_kind") is not None
                    else None
                ),
                _optional_iso(observation.get("published_at")),
                official_id,
                int(bool(observation.get("cancelled", False))),
                str(observation.get("revision", "")),
                int(observation.get("publication_order", 0)),
                _iso(existing["first_seen_at"] if existing else now),
                _iso(now),
            ),
        )

    @staticmethod
    def _source_success(
        db: sqlite3.Connection, game: str, server: str, now: datetime
    ) -> None:
        db.execute(
            "INSERT INTO sources(game, server, last_success_at, error, last_attempt_at) "
            "VALUES (?, ?, ?, NULL, ?) "
            "ON CONFLICT(game, server) DO UPDATE SET "
            "last_success_at = CASE WHEN sources.last_success_at IS NULL "
            "OR sources.last_success_at < excluded.last_success_at "
            "THEN excluded.last_success_at ELSE sources.last_success_at END, error = NULL, "
            "last_attempt_at = excluded.last_attempt_at",
            (game, server, _iso(now), _iso(now)),
        )
        db.execute(
            "UPDATE subscriptions SET first_follow_ready = 1 WHERE game = ? AND server = ?",
            (game, server),
        )

    def source_failure(
        self,
        region: tuple[str, str],
        error: str,
        now: datetime | str | None = None,
    ) -> dict[str, Any]:
        game, server = _region(region)
        current = _dt(now or datetime.now(UTC))
        reason = str(error) or "unknown"
        with self._transaction() as db:
            db.execute(
                "INSERT INTO sources(game, server, last_success_at, error, last_attempt_at) "
                "VALUES (?, ?, NULL, ?, ?) "
                "ON CONFLICT(game, server) DO UPDATE SET "
                "error = excluded.error, last_attempt_at = excluded.last_attempt_at",
                (game, server, reason, _iso(current)),
            )
            db.execute(
                "UPDATE banners SET stale = 1, updated_at = ? WHERE game = ? AND server = ?",
                (_iso(current), game, server),
            )
        return self.snapshot(current)

    def refresh(self, batch: Mapping[str, Any]) -> dict[str, Any]:
        """Adapt a multi-region batch to the collector-facing methods."""

        now = batch.get("now") or datetime.now(UTC)
        observations = list(batch.get("observations", ()))
        sweeps = list(batch.get("sweeps", ()))
        swept_regions = set()
        for sweep in sweeps:
            region = _region(sweep)
            swept_regions.add(region)
            if sweep.get("success"):
                selected = [item for item in observations if _region(item) == region]
                self.apply_observations(
                    region, selected, sweep.get("observed_at") or now
                )
            else:
                self.source_failure(region, str(sweep.get("error") or "unknown"), now)
        grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
        for item in observations:
            region = _region(item)
            if region not in swept_regions:
                grouped.setdefault(region, []).append(item)
        for region, items in grouped.items():
            self.apply_observations(region, items, now)
        return self.snapshot(now)

    @staticmethod
    def _deactivate(
        db: sqlite3.Connection, intent_id: str, now: datetime, reason: str
    ) -> None:
        db.execute("UPDATE intents SET active = 0 WHERE id = ?", (intent_id,))
        db.execute(
            "UPDATE outbox SET status = 'cancelled', finished_at = ?, reason = ? "
            "WHERE intent_id = ? AND status = 'pending'",
            (_iso(now), reason, intent_id),
        )

    def plan(self, now: datetime | str | None = None) -> list[dict[str, Any]]:
        """Reconcile due announcement/opening groups without performing network IO."""

        current = _dt(now or datetime.now(UTC))
        with self._transaction() as db:
            revision = self._revision(db)
            db.execute(
                "UPDATE intents SET subscription_revision = ? WHERE active = 1 AND "
                "EXISTS (SELECT 1 FROM subscriptions s WHERE s.game = intents.game "
                "AND s.server = intents.server AND s.active = 1)",
                (revision,),
            )
            for row in db.execute(
                "SELECT i.*, s.active AS subscribed FROM intents i "
                "LEFT JOIN subscriptions s ON s.game = i.game AND s.server = i.server "
                "WHERE i.active = 1"
            ).fetchall():
                expired = row["expires_at"] is not None and current >= _dt(
                    row["expires_at"]
                )
                if not row["subscribed"] or expired:
                    self._deactivate(
                        db,
                        row["id"],
                        current,
                        "expired" if expired else "unsubscribed",
                    )

            self._plan_first_follow(db, current, revision)
            for event_kind in ("announcement", "opening"):
                groups: dict[tuple[str, str, str], dict[str, Any]] = {}
                for row in db.execute(
                    "SELECT s.game, s.server, s.followed_at FROM subscriptions s WHERE s.active = 1 "
                    "AND EXISTS (SELECT 1 FROM banners b WHERE b.game = s.game "
                    "AND b.server = s.server) ORDER BY s.game, s.server"
                ):
                    selected = self._build_groups(
                        db,
                        row["game"],
                        row["server"],
                        event_kind,
                        current,
                        _dt(row["followed_at"]),
                    )
                    groups.update(selected)
                self._process_groups(db, event_kind, groups, current, revision)

            return [
                self._intent_view(row)
                for row in db.execute(
                    "SELECT * FROM intents WHERE active = 1 ORDER BY due_at, created_at, id"
                )
                if _dt(row["due_at"]) <= current
                and (row["expires_at"] is None or current < _dt(row["expires_at"]))
            ]

    @staticmethod
    def _notice(
        db: sqlite3.Connection, banner_id: str, event_kind: str
    ) -> sqlite3.Row | None:
        return db.execute(
            "SELECT n.*, i.event_kind AS source_event_kind FROM notice_state n "
            "JOIN intents i ON i.id = n.intent_id "
            "WHERE n.banner_id = ? AND n.event_kind = ?",
            (banner_id, event_kind),
        ).fetchone()

    @staticmethod
    def _add_group(
        groups: dict[tuple[str, str, str], dict[str, Any]],
        row: sqlite3.Row,
        group_key: str,
        due_at: datetime,
        expires_at: datetime | None,
        base_kind: str,
    ) -> None:
        key = (row["game"], row["server"], group_key)
        group = groups.get(key)
        if group is None:
            groups[key] = {
                "game": row["game"],
                "server": row["server"],
                "group_key": group_key,
                "due_at": due_at,
                "expires_at": expires_at,
                "base_kind": base_kind,
                "rows": [row],
            }
            return
        group["rows"].append(row)
        group["due_at"] = max(group["due_at"], due_at)
        if expires_at is not None:
            group["expires_at"] = (
                expires_at
                if group["expires_at"] is None
                else min(group["expires_at"], expires_at)
            )
        if base_kind == "catchup":
            group["base_kind"] = "catchup"

    def _build_groups(
        self,
        db: sqlite3.Connection,
        game: str,
        server: str,
        event_kind: str,
        now: datetime,
        followed_at: datetime,
    ) -> dict[tuple[str, str, str], dict[str, Any]]:
        groups: dict[tuple[str, str, str], dict[str, Any]] = {}
        rows = db.execute(
            "SELECT * FROM banners WHERE game = ? AND server = ? "
            "ORDER BY publication_order, id",
            (game, server),
        )
        for row in rows:
            notice = self._notice(db, row["id"], event_kind)
            ended = row["ends_at"] is not None and now >= _dt(row["ends_at"])
            if event_kind == "announcement":
                opened_notice = self._notice(db, row["id"], "opening")
                changed_notices = [
                    recorded
                    for kind, recorded in (
                        ("announcement", notice),
                        ("opening", opened_notice),
                    )
                    if recorded is not None
                    and recorded["fingerprint"] != _banner_fingerprint(row, kind)
                ]
                needs_correction = self._has_history(
                    db, {recorded["intent_id"] for recorded in changed_notices}
                )
                if row["start_mode"] == "tbd" or (ended and not row["cancelled"]):
                    if needs_correction:
                        self._add_group(
                            groups,
                            row,
                            f"revised:{row['id']}",
                            now,
                            now + timedelta(hours=24),
                            "correction",
                        )
                    continue
                if row["cancelled"] and notice is None and not needs_correction:
                    continue
                confirmed = row["confirmed_open_at"]
                if confirmed is not None and now >= _dt(confirmed):
                    continue
                if (
                    row["start_mode"] == "scheduled"
                    and now >= _dt(row["starts_at"])
                    and notice is None
                ):
                    continue
                if row["start_mode"] == "scheduled":
                    group_key = f"scheduled:{_minute(row['starts_at'])}"
                else:
                    start = row["starts_at"]
                    group_key = (
                        f"maintenance:{_minute(start)}"
                        if start is not None
                        else "maintenance:unscheduled"
                    )
                expires = (
                    now + timedelta(hours=24)
                    if row["cancelled"] or ended
                    else min(
                        now + timedelta(hours=24),
                        _dt(row["ends_at"])
                        if row["ends_at"]
                        else now + timedelta(hours=24),
                    )
                )
                self._add_group(groups, row, group_key, now, expires, "announcement")
                continue

            if row["cancelled"] and notice is None:
                continue
            if ended and not row["cancelled"]:
                continue
            event_value = (
                row["starts_at"]
                if row["start_mode"] == "scheduled"
                else row["confirmed_open_at"]
            )
            if event_value is None:
                continue
            event_at = _dt(event_value)
            if event_at > now and not row["cancelled"]:
                continue
            if notice is None and event_at <= followed_at:
                # Following a region summarizes future banners only. An already
                # open pool is not an offline catch-up for the new subscription.
                continue
            on_time = now < event_at.replace(second=0, microsecond=0) + timedelta(
                minutes=1
            )
            within_catchup = now - event_at <= timedelta(hours=24)
            strictly_open = not ended and (
                row["ends_at"] is not None or row["end_kind"] == "permanent"
            )
            if not row["cancelled"] and notice is None:
                if not within_catchup or (not on_time and not strictly_open):
                    continue
            elif not row["cancelled"] and not strictly_open and not on_time:
                # A previously notified group may be corrected, while a new
                # catch-up still requires positive evidence that it remains open.
                if not within_catchup:
                    continue
            group_key = (
                f"scheduled:{_minute(event_value)}"
                if row["start_mode"] == "scheduled"
                else f"maintenance:{_minute(event_value)}"
            )
            correction_due = row["cancelled"] or not within_catchup
            due = now if correction_due else event_at
            catchup_expiry = event_at + timedelta(hours=24, microseconds=1)
            expires = (
                now + timedelta(hours=24)
                if correction_due
                else min(
                    catchup_expiry,
                    _dt(row["ends_at"]) if row["ends_at"] else catchup_expiry,
                )
            )
            base_kind = "opening" if on_time else "catchup"
            self._add_group(groups, row, group_key, due, expires, base_kind)
        return groups

    def _plan_first_follow(
        self, db: sqlite3.Connection, now: datetime, revision: int
    ) -> None:
        for subscription in db.execute(
            "SELECT * FROM subscriptions WHERE active = 1 "
            "AND first_follow_done = 0 AND first_follow_ready = 1"
        ).fetchall():
            game, server = subscription["game"], subscription["server"]
            rows = [
                row
                for row in db.execute(
                    "SELECT * FROM banners WHERE game = ? AND server = ? "
                    "ORDER BY publication_order, id",
                    (game, server),
                )
                if _future_banner(row, now)
            ]
            if rows:
                fingerprint = self._group_fingerprint(rows, "announcement")
                series = db.execute(
                    "SELECT version FROM series WHERE event_kind = 'first_follow' "
                    "AND game = ? AND server = ? AND group_key = 'root'",
                    (game, server),
                ).fetchone()
                version = (series["version"] if series else 0) + 1
                expirations = [
                    _dt(value)
                    for row in rows
                    for value in (row["starts_at"], row["ends_at"])
                    if value is not None and now < _dt(value)
                ]
                expires = min(expirations) if expirations else now + timedelta(hours=24)
                self._create_intent(
                    db,
                    event_kind="first_follow",
                    notice_kind="first_follow",
                    game=game,
                    server=server,
                    group_key="root",
                    version=version,
                    revision=revision,
                    due_at=now,
                    expires_at=expires,
                    rows=rows,
                    fingerprint=fingerprint,
                    now=now,
                    state_event_kind="announcement",
                )
            db.execute(
                "UPDATE subscriptions SET first_follow_done = 1 WHERE game = ? AND server = ?",
                (game, server),
            )

    @staticmethod
    def _group_fingerprint(rows: Sequence[Mapping[str, Any]], event_kind: str) -> str:
        return _digest(
            [
                [row["id"], _banner_fingerprint(row, event_kind)]
                for row in sorted(rows, key=lambda item: item["id"])
            ]
        )

    @staticmethod
    def _has_history(db: sqlite3.Connection, intent_ids: set[str]) -> bool:
        if not intent_ids:
            return False
        placeholders = ",".join("?" for _ in intent_ids)
        return bool(
            db.execute(
                f"SELECT EXISTS(SELECT 1 FROM outbox WHERE intent_id IN ({placeholders}) "
                "AND status IN ('delivered', 'unknown', 'claimed'))",
                tuple(intent_ids),
            ).fetchone()[0]
        )

    def _process_groups(
        self,
        db: sqlite3.Connection,
        event_kind: str,
        groups: dict[tuple[str, str, str], dict[str, Any]],
        now: datetime,
        revision: int,
    ) -> None:
        keep: set[str] = set()
        for (_, _, group_key), group in groups.items():
            rows = group["rows"]
            fingerprint = self._group_fingerprint(rows, event_kind)
            series = db.execute(
                "SELECT * FROM series WHERE event_kind = ? AND game = ? "
                "AND server = ? AND group_key = ?",
                (event_kind, group["game"], group["server"], group_key),
            ).fetchone()
            states = {
                row["id"]: self._notice(db, row["id"], event_kind) for row in rows
            }
            if series is not None:
                changed = series["fingerprint"] != fingerprint
            else:
                changed = any(
                    state is None
                    or state["fingerprint"] != _banner_fingerprint(row, event_kind)
                    or (
                        state["group_key"] != group_key
                        and state["source_event_kind"] != "first_follow"
                    )
                    for row in rows
                    for state in (states[row["id"]],)
                )
            if not changed:
                if series is not None and series["current_intent_id"]:
                    active = db.execute(
                        "SELECT active FROM intents WHERE id = ?",
                        (series["current_intent_id"],),
                    ).fetchone()
                    if active and active["active"]:
                        keep.add(series["current_intent_id"])
                continue

            previous_ids = {
                state["intent_id"] for state in states.values() if state is not None
            }
            if series is not None and series["current_intent_id"]:
                previous_ids.add(series["current_intent_id"])
            if event_kind == "announcement":
                for row in rows:
                    opened = self._notice(db, row["id"], "opening")
                    if opened is not None and opened[
                        "fingerprint"
                    ] != _banner_fingerprint(row, "opening"):
                        previous_ids.add(opened["intent_id"])
            has_history = self._has_history(db, previous_ids)
            if all(row["cancelled"] for row in rows) and not has_history:
                continue
            previous_versions = [series["version"]] if series is not None else []
            if previous_ids:
                placeholders = ",".join("?" for _ in previous_ids)
                previous_versions.extend(
                    row["version"]
                    for row in db.execute(
                        f"SELECT version FROM intents WHERE id IN ({placeholders})",
                        tuple(previous_ids),
                    )
                )
            version = max(previous_versions, default=0) + 1
            intent_id = self._create_intent(
                db,
                event_kind=event_kind,
                notice_kind="correction" if has_history else group["base_kind"],
                game=group["game"],
                server=group["server"],
                group_key=group_key,
                version=version,
                revision=revision,
                due_at=group["due_at"],
                expires_at=group["expires_at"],
                rows=rows,
                fingerprint=fingerprint,
                now=now,
                state_event_kind=event_kind,
            )
            keep.add(intent_id)

        for row in db.execute(
            "SELECT id FROM intents WHERE event_kind = ? AND active = 1",
            (event_kind,),
        ).fetchall():
            if row["id"] not in keep:
                self._deactivate(db, row["id"], now, "superseded")

    def _create_intent(
        self,
        db: sqlite3.Connection,
        *,
        event_kind: str,
        notice_kind: str,
        game: str,
        server: str,
        group_key: str,
        version: int,
        revision: int,
        due_at: datetime,
        expires_at: datetime | None,
        rows: Sequence[sqlite3.Row],
        fingerprint: str,
        now: datetime,
        state_event_kind: str,
    ) -> str:
        intent_id = (
            f"bwi_{_digest([event_kind, game, server, group_key, version])[:24]}"
        )
        banners = [_public_banner(row, now) for row in rows]
        db.execute(
            "INSERT INTO intents(id, event_kind, notice_kind, game, server, group_key, "
            "version, subscription_revision, due_at, expires_at, payload, fingerprint, "
            "active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
            (
                intent_id,
                event_kind,
                notice_kind,
                game,
                server,
                group_key,
                version,
                revision,
                _iso(due_at),
                _iso(expires_at) if expires_at else None,
                json.dumps(banners, ensure_ascii=False),
                fingerprint,
                _iso(now),
            ),
        )
        db.execute(
            "INSERT INTO series(event_kind, game, server, group_key, version, "
            "fingerprint, current_intent_id) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(event_kind, game, server, group_key) DO UPDATE SET "
            "version = excluded.version, fingerprint = excluded.fingerprint, "
            "current_intent_id = excluded.current_intent_id",
            (event_kind, game, server, group_key, version, fingerprint, intent_id),
        )
        for row in rows:
            db.execute(
                "INSERT INTO notice_state(banner_id, event_kind, group_key, intent_id, "
                "fingerprint) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(banner_id, event_kind) DO UPDATE SET "
                "group_key = excluded.group_key, intent_id = excluded.intent_id, "
                "fingerprint = excluded.fingerprint",
                (
                    row["id"],
                    state_event_kind,
                    group_key,
                    intent_id,
                    _banner_fingerprint(row, state_event_kind),
                ),
            )
        return intent_id

    @staticmethod
    def _intent_view(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "kind": row["notice_kind"],
            "game": row["game"],
            "server": row["server"],
            "version": row["version"],
            "subscriptionRevision": row["subscription_revision"],
            "due_at": row["due_at"],
            "expires_at": row["expires_at"],
            "banners": json.loads(row["payload"]),
        }

    def _claim_payload(
        self, db: sqlite3.Connection, row: sqlite3.Row, now: datetime
    ) -> list[dict[str, Any]] | None:
        series = db.execute(
            "SELECT current_intent_id FROM series WHERE event_kind = ? AND game = ? "
            "AND server = ? AND group_key = ?",
            (row["event_kind"], row["game"], row["server"], row["group_key"]),
        ).fetchone()
        if series is not None and series["current_intent_id"] != row["id"]:
            return None
        state_kind = (
            "announcement" if row["event_kind"] == "first_follow" else row["event_kind"]
        )
        current_rows = []
        for banner in json.loads(row["payload"]):
            current = db.execute(
                "SELECT * FROM banners WHERE id = ?", (banner["id"],)
            ).fetchone()
            notice = self._notice(db, banner["id"], state_kind)
            if current is None or notice is None or notice["intent_id"] != row["id"]:
                return None
            if notice["fingerprint"] != _banner_fingerprint(current, state_kind):
                return None
            if row["event_kind"] == "first_follow" and not _future_banner(current, now):
                return None
            if (
                row["event_kind"] == "announcement"
                and current["confirmed_open_at"] is not None
                and now >= _dt(current["confirmed_open_at"])
            ):
                return None
            current_rows.append(current)
        return [_public_banner(current, now) for current in current_rows]

    def claim(
        self,
        channel: str,
        now: datetime | str | None = None,
        *,
        notice_kind: str | None = None,
        region: tuple[str, str] | None = None,
    ) -> BannerClaim | None:
        current = _dt(now or datetime.now(UTC))
        channel_id = str(channel).strip()
        if not channel_id:
            raise ValueError("channel is required")
        selected_region = _region(region) if region is not None else None
        with self._transaction() as db:
            revision = self._revision(db)
            candidates = db.execute(
                "SELECT i.* FROM intents i JOIN subscriptions s "
                "ON s.game = i.game AND s.server = i.server "
                "WHERE i.active = 1 AND s.active = 1 "
                "ORDER BY i.due_at, i.created_at, i.id"
            ).fetchall()
            for row in candidates:
                if notice_kind is not None and row["notice_kind"] != notice_kind:
                    continue
                if (
                    selected_region is not None
                    and (
                        row["game"],
                        row["server"],
                    )
                    != selected_region
                ):
                    continue
                if row["subscription_revision"] != revision:
                    continue
                if _dt(row["due_at"]) > current or (
                    row["expires_at"] is not None and current >= _dt(row["expires_at"])
                ):
                    continue
                payload = self._claim_payload(db, row, current)
                if payload is None:
                    self._deactivate(db, row["id"], current, "stale")
                    continue
                existing = db.execute(
                    "SELECT * FROM outbox WHERE intent_id = ? AND channel_id = ?",
                    (row["id"], channel_id),
                ).fetchone()
                if existing is not None and existing["status"] != "pending":
                    continue
                token = uuid.uuid4().hex
                if existing is None:
                    db.execute(
                        "INSERT INTO outbox(intent_id, channel_id, status, claim_token, "
                        "version, subscription_revision, claimed_at) "
                        "VALUES (?, ?, 'claimed', ?, ?, ?, ?)",
                        (
                            row["id"],
                            channel_id,
                            token,
                            row["version"],
                            revision,
                            _iso(current),
                        ),
                    )
                else:
                    changed = db.execute(
                        "UPDATE outbox SET status = 'claimed', claim_token = ?, "
                        "version = ?, subscription_revision = ?, claimed_at = ?, "
                        "finished_at = NULL, reason = NULL "
                        "WHERE intent_id = ? AND channel_id = ? AND status = 'pending'",
                        (
                            token,
                            row["version"],
                            revision,
                            _iso(current),
                            row["id"],
                            channel_id,
                        ),
                    )
                    if changed.rowcount != 1:
                        continue
                return BannerClaim(
                    intent_id=row["id"],
                    channel_id=channel_id,
                    version=row["version"],
                    subscription_revision=revision,
                    token=token,
                    kind=row["notice_kind"],
                    banners=tuple(payload),
                )
        return None

    def finish(
        self,
        claim: BannerClaim,
        status: OutboxStatus,
        reason: str | None,
        now: datetime | str | None = None,
        *,
        receipt: Any = None,
    ) -> dict[str, Any]:
        if status not in {"delivered", "rejected", "unknown"}:
            raise ValueError(f"unsupported delivery status: {status}")
        current = _dt(now or datetime.now(UTC))
        receipt_json = (
            json.dumps(receipt, ensure_ascii=False, sort_keys=True)
            if receipt is not None
            else None
        )
        with self._transaction() as db:
            row = db.execute(
                "SELECT * FROM outbox WHERE claim_token = ?", (claim.token,)
            ).fetchone()
            if row is None or (
                row["intent_id"],
                row["channel_id"],
                row["version"],
                row["subscription_revision"],
            ) != (
                claim.intent_id,
                claim.channel_id,
                claim.version,
                claim.subscription_revision,
            ):
                raise ValueError("claim is no longer valid")
            # The first durable terminal result owns the receipt. A repeated or
            # late finish cannot rewrite an unknown outcome into a success.
            if row["status"] == "claimed":
                db.execute(
                    "UPDATE outbox SET status = ?, reason = ?, receipt_json = ?, "
                    "finished_at = ? WHERE claim_token = ? AND status = 'claimed'",
                    (status, reason, receipt_json, _iso(current), claim.token),
                )
            return self._outbox_view(
                db.execute(
                    "SELECT * FROM outbox WHERE claim_token = ?", (claim.token,)
                ).fetchone()
            )

    record_result = finish

    @staticmethod
    def _outbox_view(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "intent_id": row["intent_id"],
            "channel_id": row["channel_id"],
            "status": row["status"],
            "reason": row["reason"],
            "version": row["version"],
            "subscriptionRevision": row["subscription_revision"],
            "claimed_at": row["claimed_at"],
            "finished_at": row["finished_at"],
            "receipt": json.loads(row["receipt_json"]) if row["receipt_json"] else None,
        }


__all__ = [
    "BannerClaim",
    "BannerWatchState",
    "GAME_SERVERS",
    "OutboxStatus",
    "SubscriptionConflict",
]
