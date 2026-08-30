"""Persistent idempotency ledger for MaaFW notification channels.

The host notification transports do not expose an idempotency token.  The
ledger therefore claims a channel before invoking the transport and keeps an
unknown claim after an unclean process exit.  This provides at-most-once
delivery across MAS restarts; explicit sender failures remain retryable.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class MaaFWNotificationClaim:
    key: str
    owner: str


class MaaFWNotificationLedger:
    """Cross-process notification claim store backed by SQLite."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = (path or _default_ledger_path()).resolve()
        self._init_lock = threading.Lock()
        self._initialized = False

    def claim(self, key: str) -> MaaFWNotificationClaim | None:
        """Claim one channel delivery, or return ``None`` if already claimed."""

        owner = uuid.uuid4().hex
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status FROM notification_delivery WHERE delivery_key = ?",
                (key,),
            ).fetchone()
            if row is not None and str(row[0]) in {"claimed", "delivered"}:
                connection.commit()
                return None
            connection.execute(
                """
                INSERT INTO notification_delivery(
                    delivery_key, status, owner, updated_at, error_code
                ) VALUES(?, 'claimed', ?, ?, NULL)
                ON CONFLICT(delivery_key) DO UPDATE SET
                    status = 'claimed',
                    owner = excluded.owner,
                    updated_at = excluded.updated_at,
                    error_code = NULL
                """,
                (key, owner, _now()),
            )
            connection.commit()
        return MaaFWNotificationClaim(key=key, owner=owner)

    def delivered(self, claim: MaaFWNotificationClaim) -> bool:
        """Persist successful delivery for the claim owner."""

        return self._finish(claim, status="delivered", error_code=None)

    def failed(self, claim: MaaFWNotificationClaim, error_code: str) -> bool:
        """Release a known sender failure so a later dispatch may retry it."""

        return self._finish(claim, status="failed", error_code=error_code)

    def status(self, key: str) -> str | None:
        """Return the durable channel state for diagnostics."""

        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT status FROM notification_delivery WHERE delivery_key = ?",
                (key,),
            ).fetchone()
        return str(row[0]) if row is not None else None

    def _finish(
        self,
        claim: MaaFWNotificationClaim,
        *,
        status: str,
        error_code: str | None,
    ) -> bool:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE notification_delivery
                SET status = ?, updated_at = ?, error_code = ?
                WHERE delivery_key = ? AND owner = ? AND status = 'claimed'
                """,
                (status, _now(), error_code, claim.key, claim.owner),
            )
            connection.commit()
        return cursor.rowcount == 1

    def _connect(self) -> sqlite3.Connection:
        self._ensure_schema()
        connection = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _ensure_schema(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=30.0)
            try:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS notification_delivery(
                        delivery_key TEXT PRIMARY KEY,
                        status TEXT NOT NULL,
                        owner TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        error_code TEXT
                    )
                    """
                )
                connection.commit()
            finally:
                connection.close()
            self._initialized = True


def _default_ledger_path() -> Path:
    return Path.cwd() / "data" / "maafw_notifications" / "delivery.sqlite3"


__all__ = [
    "MaaFWNotificationClaim",
    "MaaFWNotificationLedger",
]
