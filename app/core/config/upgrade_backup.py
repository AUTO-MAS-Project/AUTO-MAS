"""整包升级启动时保留旧数据，并在新版就绪后轮换归档。"""

import json
import os
import re
import shutil
import sqlite3
import zipfile
from collections.abc import Callable
from contextlib import closing, suppress
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from packaging.version import Version
from pydantic import BaseModel, Field, StringConstraints

from app.core.config.backup import (
    UPGRADE_BACKUP_STATE,
    UPGRADE_MIGRATION_MARK,
    backup_database,
    backup_includes,
)
from app.utils.common.io import atomic_write, force_rmtree

_VERSION_PATTERN = (
    r"v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-beta\.(?:0|[1-9]\d*))?"
)
ReleaseVersion = Annotated[str, StringConstraints(pattern=f"^{_VERSION_PATTERN}$")]
BackupWarning = Literal[
    "unknown_version", "backup_failed", "snapshot_missing", "source_not_ready"
]
BACKUP_WARNING_TITLE = "core.update.startupBackup.title"
BACKUP_WARNING_LINES: dict[BackupWarning, tuple[str, str]] = {
    "unknown_version": (
        "core.update.startupBackup.unknown_version",
        "无法确认升级前的版本，本次未生成备份，已有备份仍保留。",
    ),
    "backup_failed": (
        "core.update.startupBackup.backup_failed",
        "未能完成更新前备份，应用将继续启动。已有备份仍保留，下次启动仅从完整的旧数据快照重试。",
    ),
    "snapshot_missing": (
        "core.update.startupBackup.snapshot_missing",
        "本次升级缺少完整的迁移前快照，已有回退备份仍保留。",
    ),
    "source_not_ready": (
        "core.update.startupBackup.source_not_ready",
        "上一版本未完成启动，已保留原有回退备份。",
    ),
}
_DATA_DIRECTORIES = ("config", "data", "history")
_DATABASES = ("data/data.db", "data/history.db")


class _BackupAttempt(BaseModel):
    source: ReleaseVersion
    target: ReleaseVersion
    captured_at: datetime
    id: UUID = Field(default_factory=uuid4)
    owner: str | None = None
    directory: str | None = None
    published: bool = False
    settled: bool = False
    retired: bool = False

    @property
    def filename(self) -> str:
        stamp = self.captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        return (
            f"AUTO-MAS-backup-{self.source}-to-{self.target}-{stamp}-{self.id.hex}.zip"
        )


class _BackupState(BaseModel):
    data_version: ReleaseVersion | None = None
    ready_version: ReleaseVersion | None = None
    attempts: list[_BackupAttempt] = Field(default_factory=list)


class _BackupPreferences(BaseModel):
    enabled: bool = True
    directory: str | None = None


def _release_version(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    version = f"v{value.removeprefix('v')}"
    return version if re.fullmatch(_VERSION_PATTERN, version) else None


def _raise_walk_error(error: OSError) -> None:
    raise error


def _is_redirected(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _make_snapshot(root: Path, snapshot: Path) -> None:
    """抓取迁移前磁盘内容，完成后发布整个暂存目录。"""

    partial = snapshot.with_suffix(".partial")
    if _is_redirected(partial):
        raise ValueError("升级备份暂存目录被重定向")
    if partial.exists():
        force_rmtree(partial)
    partial.mkdir()
    try:
        for name in _DATA_DIRECTORIES:
            source = root / name
            if _is_redirected(source):
                raise ValueError(f"升级备份源目录被重定向：{name}")
            (partial / name).mkdir()
            if not source.exists():
                continue
            for directory, folders, files in source.walk(on_error=_raise_walk_error):
                folders[:] = [
                    folder
                    for folder in folders
                    if backup_includes(
                        (directory / folder).relative_to(root).as_posix()
                    )
                    and not _is_redirected(directory / folder)
                ]
                (partial / directory.relative_to(root)).mkdir(exist_ok=True)
                for file in files:
                    original = directory / file
                    relative = original.relative_to(root)
                    if backup_includes(relative.as_posix()) and not _is_redirected(
                        original
                    ):
                        shutil.copy2(original, partial / relative)

        for name in _DATABASES:
            original = root / name
            if _is_redirected(original):
                raise ValueError(f"升级备份数据库被重定向：{name}")
            if not original.is_file():
                continue
            target = partial / name
            backup_database(original, target, busy_timeout=5)
            if name == "data/history.db":
                # 未完成的历史归档可能持有原安装的绝对路径，只从副本中移除。
                with closing(sqlite3.connect(target)) as database:
                    pending_table = database.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='pending_files'"
                    ).fetchone()
                    if pending_table:
                        database.execute("DELETE FROM pending_files")
                        database.commit()
        partial.rename(snapshot)
    finally:
        with suppress(OSError):
            force_rmtree(partial)


def _check_zip(path: Path) -> None:
    if _is_redirected(path):
        raise ValueError("升级备份 ZIP 被重定向")
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if (
            not {f"{name}/" for name in _DATA_DIRECTORIES}.issubset(names)
            or archive.testzip()
        ):
            raise zipfile.BadZipFile("升级备份 ZIP 校验失败")


def _pack_snapshot(snapshot: Path, archive: Path) -> None:
    temporary = archive.with_suffix(".part")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(
            temporary, "x", compression=zipfile.ZIP_DEFLATED
        ) as output:
            for item in snapshot.rglob("*"):
                output.write(item, item.relative_to(snapshot).as_posix())
        _check_zip(temporary)
        with temporary.open("rb+") as file:
            os.fsync(file.fileno())
        temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)


class UpgradeBackup:
    """为同一安装目录记录数据版本、本次备份和可清理的自动归档。"""

    def __init__(self, *, root: Path, desktop_version: str) -> None:
        version = _release_version(desktop_version)
        if version is None:
            raise ValueError("桌面版本无效，无法识别整包升级")
        self.root = root.resolve()
        self.version = version
        self.default_directory = self.root / "backup"
        self.directory = self.default_directory
        self.owner = sha256(os.fsencode(os.path.normcase(str(self.root)))).hexdigest()
        self.enabled = True
        self.state_path = root / "config" / UPGRADE_BACKUP_STATE
        self.migration_mark = root / "data" / UPGRADE_MIGRATION_MARK
        self.state = _BackupState()
        self.attempt: _BackupAttempt | None = None
        self.error: Exception | None = None
        self.outcome: Literal["success", "failure"] | None = None
        self.downgrade = False
        self.prepared = False
        self.using_migration_mark = False

    def _save(self) -> None:
        atomic_write(self.state_path, self.state.model_dump_json().encode("utf-8"))

    def _snapshot_path(self, attempt: _BackupAttempt) -> Path:
        return self.directory / f".{attempt.id.hex}.snapshot"

    def _registration_path(self, attempt: _BackupAttempt) -> Path:
        return self.directory / f".{attempt.id.hex}.archive.json"

    def _owns_attempt(self, attempt: _BackupAttempt) -> bool:
        if attempt.owner is None:
            return (
                self.directory == self.default_directory and attempt.directory is None
            )
        return attempt.owner == self.owner and attempt.directory == os.path.normcase(
            str(self.directory)
        )

    def _frontend_config(self) -> dict[str, Any]:
        try:
            data = json.loads(
                (self.root / "config" / "frontend_config.json").read_text(
                    encoding="utf-8"
                )
            )
        except FileNotFoundError:
            return {}
        if not isinstance(data, dict):
            raise ValueError("无法确认自动备份设置")
        return data

    def _set_directory(self, configured: str | None) -> None:
        if configured is None:
            return
        path = Path(configured)
        if not path.is_absolute() or _is_redirected(path):
            raise ValueError("自动备份目录必须是实际的绝对路径")
        resolved = path.resolve()
        if resolved == resolved.parent or any(
            resolved.is_relative_to((self.root / name).resolve())
            for name in _DATA_DIRECTORIES
        ):
            raise ValueError("自动备份目录不能位于备份源目录内或磁盘根目录")
        self.directory = resolved

    def prepare(
        self, *, on_backup: Callable[[], None] | None = None
    ) -> BackupWarning | None:
        """在任何迁移之前准备备份，记录给后续启动使用的恢复依据。"""

        if _is_redirected(self.state_path.parent) or _is_redirected(self.state_path):
            raise ValueError("升级备份状态路径被重定向")
        config = self._frontend_config()
        preferences = _BackupPreferences.model_validate(config.get("upgradeBackup", {}))
        self.enabled = preferences.enabled
        try:
            self.state = _BackupState.model_validate_json(self.state_path.read_bytes())
        except FileNotFoundError:
            self.state.data_version = _release_version(config.get("initializedVersion"))
            self.state.ready_version = self.state.data_version
        try:
            marked_version = self.migration_mark.read_text(encoding="ascii")
        except FileNotFoundError:
            pass
        else:
            self.using_migration_mark = True
            self.state.data_version = _release_version(marked_version)
            if self.state.data_version is None:
                raise ValueError("升级备份迁移标记无效")
        if not self.enabled:
            self.prepared = True
            return None

        try:
            self._set_directory(preferences.directory)
        except (OSError, ValueError) as error:
            self.prepared = True
            self.error = error
            return "backup_failed"
        source = self.state.data_version
        if source is None:
            self.prepared = True
            if any(
                directory.is_dir()
                and any(
                    path.name != "frontend_config.json" or directory.name != "config"
                    for path in directory.iterdir()
                )
                for directory in (self.root / name for name in _DATA_DIRECTORIES)
            ):
                return "unknown_version"
            return None

        target_version, source_version = Version(self.version), Version(source)
        creates_snapshot = target_version > source_version
        self.downgrade = target_version < source_version
        if creates_snapshot:
            if self.state.ready_version != source:
                # 启动失败的版本可能只迁移了一部分，不能替换原有回退点。
                self.prepared = True
                return "source_not_ready"
            self.attempt = next(
                (
                    item
                    for item in reversed(self.state.attempts)
                    if item.source == source
                    and item.target == self.version
                    and not item.settled
                    and self._owns_attempt(item)
                ),
                None,
            )
            if self.attempt is None:
                self.attempt = _BackupAttempt(
                    source=source,
                    target=self.version,
                    captured_at=datetime.now(UTC),
                    owner=self.owner,
                    directory=os.path.normcase(str(self.directory)),
                )
                self.state.attempts.append(self.attempt)
                self._save()
        elif not self.downgrade:
            self.attempt = next(
                (
                    item
                    for item in reversed(self.state.attempts)
                    if item.target == self.version and self._owns_attempt(item)
                ),
                None,
            )

        self.prepared = True
        attempt = self.attempt
        if attempt is None or attempt.settled:
            self.attempt = None
            return None

        try:
            if _is_redirected(self.directory):
                raise ValueError("升级备份目录被重定向")
            self.directory.mkdir(exist_ok=True)
            snapshot = self._snapshot_path(attempt)
            archive = self.directory / attempt.filename
            if archive.exists():
                _check_zip(archive)
            else:
                if on_backup is not None and (creates_snapshot or snapshot.is_dir()):
                    on_backup()
                if creates_snapshot and not snapshot.is_dir():
                    _make_snapshot(self.root, snapshot)
                if _is_redirected(snapshot):
                    raise ValueError("升级备份快照目录被重定向")
                if not snapshot.is_dir():
                    partial = snapshot.with_suffix(".partial")
                    if partial.is_dir() and not _is_redirected(partial):
                        force_rmtree(partial)
                    return "snapshot_missing"
                _pack_snapshot(snapshot, archive)
                self.outcome = "success"
            attempt.published = True
            atomic_write(
                self._registration_path(attempt),
                attempt.model_dump_json().encode("utf-8"),
            )
            self._save()
        except (OSError, ValueError, sqlite3.Error, zipfile.BadZipFile) as error:
            self.error = error
            self.outcome = "failure"
            self.attempt = None
            return "backup_failed"

        if not _is_redirected(snapshot):
            with suppress(OSError):
                force_rmtree(snapshot)
        return None

    def begin_migration(self) -> bool:
        """持久化迁移边界。主状态写入失败时使用数据目录内的独立标记。"""

        if self.prepared and not self.using_migration_mark:
            if self.state.data_version == self.version:
                return True
            self.state.data_version = self.version
            try:
                self._save()
            except OSError as error:
                self.error = error
            else:
                return True
        # 若连此标记都无法保存，必须阻止迁移，否则无法证明下次读取的是旧数据。
        atomic_write(self.migration_mark, self.version.encode("ascii"))
        self.using_migration_mark = True
        return False

    def finish(self) -> None:
        """仅在当前版本业务就绪后确认升级，并轮换已登记的备份。"""

        if not self.prepared:
            return
        if (
            self.state.ready_version != self.version
            or self.using_migration_mark
            or not self.state_path.is_file()
        ):
            self.state.data_version = self.version
            self.state.ready_version = self.version
            self._save()
            if self.using_migration_mark:
                self.migration_mark.unlink(missing_ok=True)
        if (
            not self.enabled
            or self.downgrade
            or self.error is not None
            or self.using_migration_mark
        ):
            return

        if self.attempt is not None:
            if not self.attempt.published:
                # 完整原件已不可用。保留尚存回退点，后续升级可建立新的备份。
                self.attempt.settled = True
                self._save()
                return
            if _is_redirected(self.directory):
                raise ValueError("升级备份目录被重定向")
            self._plan_cleanup(self.attempt)

        retired = [
            item
            for item in self.state.attempts
            if item.retired and self._owns_attempt(item)
        ]
        if retired:
            if _is_redirected(self.directory):
                raise ValueError("升级备份目录被重定向")
            for item in retired:
                (self.directory / item.filename).unlink(missing_ok=True)
                self._registration_path(item).unlink(missing_ok=True)
            self.state.attempts = [
                item for item in self.state.attempts if item not in retired
            ]
            self._save()

    def _plan_cleanup(self, attempt: _BackupAttempt) -> None:
        _check_zip(self.directory / attempt.filename)
        # 用户恢复 config 时可能替换升级记录。归档登记随 ZIP 一起留在 backup。
        known = {item.id for item in self.state.attempts}
        for path in self.directory.glob(".*.archive.json"):
            if _is_redirected(path):
                continue
            try:
                archived = _BackupAttempt.model_validate_json(path.read_bytes())
            except (OSError, ValueError):
                continue
            if (
                archived.published
                and self._owns_attempt(archived)
                and path == self._registration_path(archived)
                and archived.id not in known
            ):
                archived.settled = True
                self.state.attempts.append(archived)

        published = sorted(
            (
                item
                for item in self.state.attempts
                if item.published and not item.retired and self._owns_attempt(item)
            ),
            key=lambda item: item.captured_at,
            reverse=True,
        )
        existing = []
        for item in published:
            archive = self.directory / item.filename
            if not archive.is_file() or _is_redirected(archive):
                continue
            existing.append((item, Version(item.source)))

        target = Version(self.version)
        current = (target.major, target.minor)
        previous = max(
            (
                (version.major, version.minor)
                for _, version in existing
                if (version.major, version.minor) < current
            ),
            default=current,
        )
        retained = {
            item.id
            for item, version in existing
            if (version.major, version.minor) in {current, previous}
        }
        # 版本段之外仍保留可用的渠道回退点，公测版同时保留最近公测。
        channels = {False, True} if target.is_prerelease else {False}
        valid_count = 0
        for item, version in existing:
            channel = version.is_prerelease
            if valid_count >= 2 and channel not in channels:
                continue
            if item.id != attempt.id:
                try:
                    _check_zip(self.directory / item.filename)
                except (OSError, ValueError, zipfile.BadZipFile):
                    continue
            retained.add(item.id)
            valid_count += 1
            channels.discard(channel)
            if valid_count >= 2 and not channels:
                break
        attempt.settled = True
        for item in published:
            item.retired = item.id not in retained
        # 先提交清理决定，重启能继续清理而不会重新备份已经迁移的数据。
        self._save()
