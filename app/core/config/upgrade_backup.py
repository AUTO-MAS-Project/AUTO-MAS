"""整包升级启动时保留旧数据，并在新版就绪后轮换归档。"""

import json
import os
import re
import shutil
import sqlite3
import zipfile
import zlib
from collections.abc import Callable
from contextlib import closing, suppress
from datetime import UTC, datetime
from filecmp import cmp
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
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
from app.utils import get_logger
from app.utils.common.io import atomic_write, force_rmtree
from app.utils.common.zip_delta import file_digest

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
logger = get_logger("升级备份")


class _BackupAttempt(BaseModel):
    source: ReleaseVersion
    target: ReleaseVersion
    captured_at: datetime
    id: UUID = Field(default_factory=uuid4)
    owner: str | None = None
    directory: str | None = None
    snapshot_ready: bool = False
    published: bool = False
    settled: bool = False
    retired: bool = False

    @property
    def filename(self) -> str:
        stamp = self.captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        return (
            f"AUTO-MAS-backup-{self.source}-to-{self.target}-{stamp}-{self.id.hex}.zip"
        )


class _DirectoryCleanup(BaseModel):
    source: str
    attempt: _BackupAttempt
    digest: str


class _BackupState(BaseModel):
    data_version: ReleaseVersion | None = None
    ready_version: ReleaseVersion | None = None
    attempts: list[_BackupAttempt] = Field(default_factory=list)
    selected_directory: str | None = None
    use_default_directory: bool = False
    directory_cleanup: list[_DirectoryCleanup] = Field(default_factory=list)


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


def _installation_owner(root: Path) -> str:
    return sha256(os.fsencode(os.path.normcase(str(root)))).hexdigest()


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
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if (
                not {f"{name}/" for name in _DATA_DIRECTORIES}.issubset(names)
                or archive.testzip()
            ):
                raise zipfile.BadZipFile("升级备份 ZIP 校验失败")
    except (EOFError, RuntimeError, zlib.error) as error:
        raise zipfile.BadZipFile("升级备份 ZIP 校验失败") from error


def _pack_snapshot(snapshot: Path, archive: Path, *, new_only: bool = False) -> bool:
    with NamedTemporaryFile(
        prefix=".backup-pack-", suffix=".part", dir=archive.parent, delete=False
    ) as file:
        temporary = Path(file.name)
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED
        ) as output:
            for item in snapshot.rglob("*"):
                output.write(item, item.relative_to(snapshot).as_posix())
        _check_zip(temporary)
        with temporary.open("rb+") as file:
            os.fsync(file.fileno())
        if new_only:
            return _publish_move_file(temporary, archive)
        temporary.replace(archive)
        return True
    finally:
        temporary.unlink(missing_ok=True)


def _publish_move_file(temporary: Path, target: Path) -> bool:
    if target.exists() or _is_redirected(target):
        if _is_redirected(target) or not cmp(temporary, target, shallow=False):
            raise FileExistsError(f"目标备份同名且内容不同：{target.name}")
        return False
    if os.name == "nt":
        temporary.rename(target)
    else:
        os.link(temporary, target)
    return True


def _write_registration(
    attempt: _BackupAttempt, registration: Path, *, new_only: bool = False
) -> bool:
    with NamedTemporaryFile(
        prefix=".backup-register-", suffix=".tmp", dir=registration.parent, delete=False
    ) as file:
        temporary = Path(file.name)
    try:
        with temporary.open("wb") as file:
            file.write(attempt.model_dump_json().encode("utf-8"))
            file.flush()
            os.fsync(file.fileno())
        if new_only:
            return _publish_move_file(temporary, registration)
        temporary.replace(registration)
        return True
    finally:
        temporary.unlink(missing_ok=True)


def _copy_verified_archive(source: Path, target: Path) -> bool:
    """发布验证过的 ZIP，不覆盖目标目录里的同名文件。"""

    _check_zip(source)
    if target.exists() or _is_redirected(target):
        if _is_redirected(target) or not cmp(source, target, shallow=False):
            raise FileExistsError(f"目标备份同名且内容不同：{target.name}")
        return False
    with NamedTemporaryFile(
        prefix=".backup-move-", suffix=".part", dir=target.parent, delete=False
    ) as file:
        temporary = Path(file.name)
    try:
        shutil.copyfile(source, temporary)
        _check_zip(temporary)
        with temporary.open("rb+") as file:
            os.fsync(file.fileno())
        return _publish_move_file(temporary, target)
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
        self.owner = _installation_owner(self.root)
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
        self.lock = Lock()

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

    def _rebind_default_archives(self) -> None:
        """搬动安装目录后，只接续状态和默认目录归档登记能够互相印证的旧档。"""

        if self.directory != self.default_directory or _is_redirected(self.directory):
            return
        directory = os.path.normcase(str(self.directory))
        changed = False
        for item in self.state.attempts:
            if item.owner in {None, self.owner} or item.directory is None:
                continue
            origin = Path(item.directory)
            if (
                not origin.is_absolute()
                or origin != origin.parent / self.default_directory.name
                or item.owner != _installation_owner(origin.parent)
            ):
                continue
            registration = self._registration_path(item)
            if _is_redirected(registration):
                continue
            try:
                archived = _BackupAttempt.model_validate_json(registration.read_bytes())
            except FileNotFoundError:
                snapshot = self._snapshot_path(item)
                if item.published or _is_redirected(snapshot) or not snapshot.is_dir():
                    continue
                archived = None
            except (OSError, ValueError):
                continue
            if archived is not None:
                old_location = (item.owner, item.directory)
                new_location = (self.owner, directory)
                if (
                    not archived.published
                    or archived.id != item.id
                    or archived.filename != item.filename
                    or (archived.owner, archived.directory)
                    not in {old_location, new_location}
                ):
                    continue
                if (archived.owner, archived.directory) == old_location:
                    try:
                        _write_registration(
                            archived.model_copy(
                                update={"owner": self.owner, "directory": directory}
                            ),
                            registration,
                        )
                    except OSError as error:
                        logger.debug(
                            "暂无法更新搬迁前的归档登记：{} ({})",
                            type(error).__name__,
                            error.errno,
                        )
                        continue
            item.owner = self.owner
            item.directory = directory
            changed = True
        if changed:
            self._save()

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

    def _resolve_directory(self, configured: str | None) -> Path:
        if configured is None:
            return self.default_directory
        path = Path(configured)
        if not path.is_absolute() or _is_redirected(path):
            raise ValueError("自动备份目录必须是实际的绝对路径")
        resolved = path.resolve()
        if resolved == resolved.parent or any(
            resolved.is_relative_to((self.root / name).resolve())
            for name in _DATA_DIRECTORIES
        ):
            raise ValueError("自动备份目录不能位于备份源目录内或磁盘根目录")
        if any(
            re.fullmatch(r"\.[0-9a-f]{32}\.(?:snapshot|partial)", part, re.IGNORECASE)
            for part in resolved.parts
        ):
            raise ValueError("自动备份目录不能位于升级备份暂存目录内")
        return resolved

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
        try:
            configured = (
                None
                if self.state.use_default_directory
                else self.state.selected_directory or preferences.directory
            )
            self.directory = self._resolve_directory(configured)
            self._rebind_default_archives()
        except (OSError, ValueError) as error:
            self.prepared = True
            self.error = error
            return "backup_failed"
        if not self.enabled:
            self.prepared = True
            return None
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
                    attempt.snapshot_ready = True
                    self._save()
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
            _write_registration(attempt, self._registration_path(attempt))
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

        with self.lock:
            self._finish()

    def _finish(self) -> None:
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
        self._finish_directory_cleanup()
        if (
            not self.enabled
            or self.downgrade
            or self.error is not None
            or self.using_migration_mark
        ):
            return

        if self.attempt is not None:
            if not self.attempt.published:
                # 已确认完整的快照可能只是暂时离线，保留后续重试机会。
                if self.attempt.snapshot_ready:
                    return
                # 完整原件已不可用。保留尚存回退点，后续升级可建立新的备份。
                self.attempt.settled = True
                self._save()
                return
            if _is_redirected(self.directory):
                raise ValueError("升级备份目录被重定向")
            if not self._plan_cleanup(self.attempt):
                return

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
            # 归档已轮换，没有可验证的目标副本时保留旧盘上的文件。
            retired_ids = {item.id for item in retired}
            self.state.directory_cleanup = [
                entry
                for entry in self.state.directory_cleanup
                if entry.attempt.id not in retired_ids
            ]
            self._save()

    def _load_registered_archives(self) -> None:
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

    def _plan_cleanup(self, attempt: _BackupAttempt) -> bool:
        _check_zip(self.directory / attempt.filename)
        self._load_registered_archives()
        published = sorted(
            (
                item
                for item in self.state.attempts
                if item.published and not item.retired and self._owns_attempt(item)
            ),
            key=lambda item: item.captured_at,
            reverse=True,
        )
        valid = []
        for item in published:
            archive = self.directory / item.filename
            if item.id != attempt.id:
                try:
                    _check_zip(archive)
                except (FileNotFoundError, ValueError, zipfile.BadZipFile):
                    continue
                except OSError:
                    # 磁盘或文件暂不可读时保留所有回退点，等待下次启动重试。
                    return False
            valid.append((item, Version(item.source)))

        target = Version(self.version)
        current = (target.major, target.minor)
        previous = max(
            (
                (version.major, version.minor)
                for _, version in valid
                if (version.major, version.minor) < current
            ),
            default=current,
        )
        retained = {
            item.id
            for item, version in valid
            if (version.major, version.minor) in {current, previous}
        }
        # 版本段之外仍保留可用的渠道回退点，公测版同时保留最近公测。
        channels = {False, True} if target.is_prerelease else {False}
        valid_count = 0
        for item, version in valid:
            channel = version.is_prerelease
            if valid_count >= 2 and channel not in channels:
                continue
            retained.add(item.id)
            valid_count += 1
            channels.discard(channel)
            if valid_count >= 2 and not channels:
                break
        attempt.settled = True
        for item, _ in valid:
            item.retired = item.id not in retained
        # 先提交清理决定，重启能继续清理而不会重新备份已经迁移的数据。
        self._save()
        return True

    def _finish_directory_cleanup(self) -> bool:
        cleanup = self.state.directory_cleanup
        if not cleanup:
            return True
        if _is_redirected(self.directory):
            return False
        remaining = [
            entry for entry in cleanup if not self._remove_directory_copy(entry)
        ]
        if len(remaining) != len(cleanup):
            updated = self.state.model_copy(update={"directory_cleanup": remaining})
            try:
                atomic_write(self.state_path, updated.model_dump_json().encode("utf-8"))
            except OSError:
                return False
            self.state = updated
        return not remaining

    def _remove_directory_copy(self, entry: _DirectoryCleanup) -> bool:
        try:
            source = Path(entry.source)
            item = entry.attempt
            if _is_redirected(source) or not source.is_dir():
                return False
            origin = source / item.filename
            destination = self.directory / item.filename
            snapshot = source / f".{item.id.hex}.snapshot"
            if (
                _is_redirected(destination)
                or _is_redirected(origin)
                or _is_redirected(snapshot)
                or self.directory.resolve().is_relative_to(snapshot.resolve())
                or file_digest(destination) != entry.digest
            ):
                return False
            # 再次切回原目录时，保留当前正在使用的 ZIP 和归档登记。
            if source != self.directory:
                if origin.exists() and file_digest(origin) != entry.digest:
                    return False
                origin.unlink(missing_ok=True)
                (source / f".{item.id.hex}.archive.json").unlink(missing_ok=True)
            if snapshot.is_dir():
                force_rmtree(snapshot)
            return not snapshot.exists()
        except OSError:
            return False

    def move_directory(self, configured: str | None, *, expected: str) -> bool:
        """先验证并复制备份，再提交位置与归属，最后删除旧副本。"""

        with self.lock:
            if not self.prepared or str(self.directory) != expected:
                raise ValueError("备份设置已变化，请重新选择目录")
            destination = self._resolve_directory(configured)
            changing = destination != self.directory
            use_default = destination == self.default_directory
            if _is_redirected(self.directory) or _is_redirected(destination):
                raise ValueError("升级备份目录被重定向")
            self._rebind_default_archives()
            self._load_registered_archives()
            owned = [
                item
                for item in self.state.attempts
                if not item.retired
                and (
                    (changing and item.published and self._owns_attempt(item))
                    or (
                        not item.published
                        and not item.settled
                        and item.owner in {None, self.owner}
                    )
                )
            ]
            created: list[Path] = []
            moved: dict[UUID, _BackupAttempt] = {}
            cleanup = {
                (Path(entry.source), entry.attempt.id): entry
                for entry in self.state.directory_cleanup
            }
            try:
                destination.mkdir(exist_ok=True)
                for item in owned:
                    source = self._resolve_directory(item.directory)
                    source_zip = source / item.filename
                    snapshot = source / f".{item.id.hex}.snapshot"
                    destination_zip = destination / item.filename
                    if source_zip.exists() or _is_redirected(source_zip):
                        copied = _copy_verified_archive(source_zip, destination_zip)
                    elif not item.published and snapshot.is_dir():
                        if _is_redirected(snapshot):
                            raise ValueError("旧快照目录被重定向")
                        copied = _pack_snapshot(
                            snapshot, destination_zip, new_only=True
                        )
                    elif not source.is_dir() and (
                        item.published or item.snapshot_ready
                    ):
                        raise FileNotFoundError("旧备份目录不可用")
                    else:
                        continue
                    if copied:
                        created.append(destination_zip)
                    updated = item.model_copy(
                        update={
                            "directory": os.path.normcase(str(destination)),
                            "owner": self.owner,
                            "published": True,
                        }
                    )
                    registration = destination / f".{item.id.hex}.archive.json"
                    if _is_redirected(registration):
                        raise ValueError("目标归档登记被重定向")
                    if registration.exists():
                        old = _BackupAttempt.model_validate_json(
                            registration.read_bytes()
                        )
                        if (old.id, old.filename, old.owner, old.directory) != (
                            updated.id,
                            updated.filename,
                            updated.owner,
                            updated.directory,
                        ):
                            raise FileExistsError("目标目录包含不同的归档登记")
                    elif _write_registration(updated, registration, new_only=True):
                        created.append(registration)
                    moved[item.id] = updated
                    cleanup[source, item.id] = _DirectoryCleanup(
                        source=str(source),
                        attempt=item,
                        digest=file_digest(destination_zip),
                    )
                if (
                    not moved
                    and not changing
                    and not (use_default and not self.state.use_default_directory)
                ):
                    return self._finish_directory_cleanup()
                updated_state = self.state.model_copy(
                    update={
                        "selected_directory": None if use_default else str(destination),
                        "use_default_directory": use_default,
                        "attempts": [
                            moved.get(item.id, item) for item in self.state.attempts
                        ],
                        "directory_cleanup": list(cleanup.values()),
                    }
                )
                atomic_write(
                    self.state_path, updated_state.model_dump_json().encode("utf-8")
                )
            except (OSError, ValueError, zipfile.BadZipFile):
                for file in reversed(created):
                    with suppress(OSError):
                        file.unlink(missing_ok=True)
                raise

            self.state = updated_state
            self.directory = destination
            self.attempt = (
                moved.get(self.attempt.id) if self.attempt is not None else None
            )
            return self._finish_directory_cleanup()

    def directory_info(self) -> dict[str, str | None]:
        with self.lock:
            return {
                "directory": None
                if self.directory == self.default_directory
                else str(self.directory),
                "resolvedDirectory": str(self.directory),
                "defaultDirectory": str(self.default_directory),
            }
