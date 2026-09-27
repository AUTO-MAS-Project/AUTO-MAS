#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

import os
import socket
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.utils.io import file_collection_fingerprint

LEASE_TTL_SECONDS = 30


class ConfigEditError(RuntimeError):
    """配置编辑会话错误，API 层按 code/message 透传。"""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ConfigEditResource:
    key: str
    paths: tuple[Path, ...]

    @property
    def fingerprint(self) -> str:
        return file_collection_fingerprint(self.paths)


@dataclass(frozen=True, slots=True)
class ConfigEditLease:
    resource_key: str
    token: str
    version: str
    expires_at: float


@dataclass(slots=True)
class ConfigEditWriteGuard:
    """把编辑租约适配为通用配置文件写入保护。"""

    service: "ConfigEditLeaseService"
    resource: ConfigEditResource
    token: str | None
    expected_version: str | None

    @property
    def paths(self) -> tuple[Path, ...]:
        return self.resource.paths

    def before_write(self, _path: Path) -> None:
        self.service.assert_save_allowed(
            self.resource,
            token=self.token,
            base_version=self.expected_version,
        )

    def after_write(self, _path: Path) -> None:
        self.expected_version = self.resource.fingerprint


class ConfigEditLeaseService:
    """使用 data/data.db 保存跨进程配置编辑租约。"""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def init_schema(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS config_edit_lease(
                    resource_key TEXT PRIMARY KEY,
                    token TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )

    def acquire(self, resource: ConfigEditResource) -> ConfigEditLease:
        token = str(uuid.uuid4())
        owner = _current_owner()
        now = time.time()
        expires_at = now + LEASE_TTL_SECONDS

        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._delete_expired(db, now)
            row = db.execute(
                "SELECT token FROM config_edit_lease WHERE resource_key = ?",
                (resource.key,),
            ).fetchone()
            if row is not None:
                raise ConfigEditError(409, "有其他用户正在编辑该配置")
            db.execute(
                """
                INSERT INTO config_edit_lease(
                    resource_key, token, owner, expires_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (resource.key, token, owner, expires_at, now, now),
            )
            db.commit()

        return ConfigEditLease(
            resource_key=resource.key,
            token=token,
            version=resource.fingerprint,
            expires_at=expires_at,
        )

    def renew(self, resource: ConfigEditResource, token: str) -> ConfigEditLease:
        now = time.time()
        expires_at = now + LEASE_TTL_SECONDS

        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._delete_expired(db, now)
            row = db.execute(
                """
                SELECT token FROM config_edit_lease
                WHERE resource_key = ? AND token = ?
                """,
                (resource.key, token),
            ).fetchone()
            if row is None:
                raise ConfigEditError(409, "配置编辑锁已失效，请重新进入编辑页")
            db.execute(
                """
                UPDATE config_edit_lease
                SET expires_at = ?, updated_at = ?
                WHERE resource_key = ? AND token = ?
                """,
                (expires_at, now, resource.key, token),
            )
            db.commit()

        return ConfigEditLease(
            resource_key=resource.key,
            token=token,
            version=resource.fingerprint,
            expires_at=expires_at,
        )

    def release(self, resource_key: str, token: str) -> bool:
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._delete_expired(db, now)
            cur = db.execute(
                """
                DELETE FROM config_edit_lease
                WHERE resource_key = ? AND token = ?
                """,
                (resource_key, token),
            )
            db.commit()
            return cur.rowcount > 0

    def status(self, resource: ConfigEditResource) -> ConfigEditLease | None:
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._delete_expired(db, now)
            row = db.execute(
                """
                SELECT token, expires_at FROM config_edit_lease
                WHERE resource_key = ?
                """,
                (resource.key,),
            ).fetchone()
            db.commit()
        if row is None:
            return None
        return ConfigEditLease(
            resource_key=resource.key,
            token=row[0],
            version=resource.fingerprint,
            expires_at=float(row[1]),
        )

    def assert_save_allowed(
        self,
        resource: ConfigEditResource,
        *,
        token: str | None,
        base_version: str | None,
    ) -> None:
        if not token:
            raise ConfigEditError(409, "配置编辑锁已失效，请重新进入编辑页")
        if not base_version:
            raise ConfigEditError(409, "配置版本缺失，请重新进入编辑页")

        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._delete_expired(db, now)
            row = db.execute(
                """
                SELECT token FROM config_edit_lease
                WHERE resource_key = ? AND token = ?
                """,
                (resource.key, token),
            ).fetchone()
            db.commit()
        if row is None:
            raise ConfigEditError(409, "配置编辑锁已失效，请重新进入编辑页")
        if resource.fingerprint != base_version:
            raise ConfigEditError(409, "配置已被外部修改，请刷新后再保存")

    def create_write_guard(
        self,
        resource: ConfigEditResource,
        *,
        token: str | None,
        base_version: str | None,
    ) -> ConfigEditWriteGuard:
        """创建一个供统一 ``write_file`` 链路使用的保存保护。"""

        return ConfigEditWriteGuard(self, resource, token, base_version)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path, timeout=30.0, isolation_level=None)

    @staticmethod
    def _delete_expired(db: sqlite3.Connection, now: float) -> None:
        db.execute("DELETE FROM config_edit_lease WHERE expires_at <= ?", (now,))


def _current_owner() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"
