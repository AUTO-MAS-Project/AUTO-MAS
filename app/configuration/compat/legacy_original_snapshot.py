"""Freeze the original r6 JSON roots before any legacy configuration load.

The snapshot stores opaque bytes plus integrity metadata only.  It never parses
or logs configuration content, so encrypted values and any unexpected legacy
fields remain exactly as they were on disk.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator

LEGACY_ROOT_FILE_NAMES = (
    "Config.json",
    "EmulatorConfig.json",
    "PlanConfig.json",
    "ScriptConfig.json",
    "QueueConfig.json",
    "ToolsConfig.json",
    "PluginConfig.json",
    "GameSignAccounts.json",
)

SNAPSHOT_DIRECTORY_NAME = ".config-v2-original"
SNAPSHOT_SCHEMA_VERSION = 1
_GENERATION_PATTERN = re.compile(r"original-[0-9a-f]{24}")


class LegacyOriginalSnapshotError(RuntimeError):
    """The immutable pre-migration snapshot is absent, damaged, or unsafe."""


@dataclass(frozen=True)
class LegacyOriginalSnapshot:
    """A validated immutable generation selected by ``CURRENT``."""

    generation: str
    generation_path: Path
    manifest_path: Path
    created: bool


@dataclass(frozen=True)
class _CapturedRoot:
    name: str
    exists: bool
    content: bytes | None
    sha256: str | None
    size_bytes: int | None
    mtime_ns: int | None

    def manifest_record(self) -> dict[str, object]:
        return {
            "name": self.name,
            "exists": self.exists,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "mtime_ns": self.mtime_ns,
            "snapshot": f"files/{self.name}" if self.exists else None,
        }


def ensure_legacy_original_snapshot(config_dir: Path) -> LegacyOriginalSnapshot:
    """Create or validate the one immutable original legacy generation.

    The first fully published generation is the only generation that may be
    selected as the r6 original.  Later calls validate that generation without
    consulting current legacy files, because legacy loading may already have
    normalized them.

    Args:
        config_dir: Directory containing the eight legacy JSON roots.

    Returns:
        The validated original generation and whether this call created it.

    Raises:
        LegacyOriginalSnapshotError: Snapshot state or source files are unsafe.
        OSError: A durable snapshot or ``CURRENT`` write fails.
    """

    config_dir = Path(config_dir)
    _ensure_plain_directory(config_dir, create=True)

    snapshot_dir = config_dir / SNAPSHOT_DIRECTORY_NAME
    generations_dir = snapshot_dir / "generations"
    _ensure_plain_directory(snapshot_dir, create=True)
    _ensure_plain_directory(generations_dir, create=True)

    with _exclusive_snapshot_lock(snapshot_dir / "LOCK"):
        current_path = snapshot_dir / "CURRENT"
        if _lexical_stat(current_path) is not None:
            generation, expected_manifest_hash = _read_current(current_path)
            generation_path = generations_dir / generation
            manifest_path = _validate_generation(
                generation_path,
                expected_generation=generation,
                expected_manifest_hash=expected_manifest_hash,
            )
            return LegacyOriginalSnapshot(
                generation=generation,
                generation_path=generation_path,
                manifest_path=manifest_path,
                created=False,
            )

        published = _published_generation_directories(generations_dir)
        pending = sorted(
            path.name
            for path in generations_dir.iterdir()
            if path.name.startswith(".pending-")
        )
        if pending:
            raise LegacyOriginalSnapshotError(
                "unfinished original snapshot staging directory exists"
            )
        if len(published) > 1:
            raise LegacyOriginalSnapshotError(
                "multiple original snapshot generations exist without CURRENT"
            )
        if published:
            generation_path = published[0]
            manifest_path = _validate_generation(
                generation_path,
                expected_generation=generation_path.name,
            )
            manifest_hash = _sha256_file(manifest_path)
            _write_current(
                current_path,
                generation=generation_path.name,
                manifest_hash=manifest_hash,
            )
            _fsync_directory(snapshot_dir)
            return LegacyOriginalSnapshot(
                generation=generation_path.name,
                generation_path=generation_path,
                manifest_path=manifest_path,
                created=False,
            )

        captured_roots = _capture_legacy_roots(config_dir)
        root_records = [root.manifest_record() for root in captured_roots]
        generation = _generation_id(root_records)
        generation_path = generations_dir / generation
        manifest = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "kind": "legacy-original",
            "generation": generation,
            "roots": root_records,
        }

        staging_path = Path(
            tempfile.mkdtemp(prefix=".pending-", dir=str(generations_dir))
        )
        try:
            files_dir = staging_path / "files"
            files_dir.mkdir()
            for root in captured_roots:
                if root.content is not None:
                    _write_new_bytes(files_dir / root.name, root.content)

            manifest_path = staging_path / "manifest.json"
            _write_new_bytes(manifest_path, _serialize_json(manifest))
            _fsync_directory(files_dir)
            _fsync_directory(staging_path)

            _validate_generation(
                staging_path,
                expected_generation=generation,
            )
            os.replace(staging_path, generation_path)
            _fsync_directory(generations_dir)
        except BaseException:
            # A failed staging directory is deliberately retained.  Silently
            # deleting uncertain evidence could allow a later run to choose a
            # different "original" generation.
            raise

        manifest_path = generation_path / "manifest.json"
        manifest_hash = _sha256_file(manifest_path)
        _write_current(
            current_path,
            generation=generation,
            manifest_hash=manifest_hash,
        )
        _fsync_directory(snapshot_dir)

        return LegacyOriginalSnapshot(
            generation=generation,
            generation_path=generation_path,
            manifest_path=manifest_path,
            created=True,
        )


def _capture_legacy_roots(config_dir: Path) -> tuple[_CapturedRoot, ...]:
    initial = {
        name: _source_signature(config_dir / name)
        for name in LEGACY_ROOT_FILE_NAMES
    }
    captured: list[_CapturedRoot] = []

    for name in LEGACY_ROOT_FILE_NAMES:
        path = config_dir / name
        signature = initial[name]
        if signature is None:
            captured.append(
                _CapturedRoot(
                    name=name,
                    exists=False,
                    content=None,
                    sha256=None,
                    size_bytes=None,
                    mtime_ns=None,
                )
            )
            continue

        content = path.read_bytes()
        if len(content) != signature[0]:
            raise LegacyOriginalSnapshotError(
                "legacy configuration root size changed during capture"
            )
        captured.append(
            _CapturedRoot(
                name=name,
                exists=True,
                content=content,
                sha256=hashlib.sha256(content).hexdigest(),
                size_bytes=signature[0],
                mtime_ns=signature[1],
            )
        )

    final = {
        name: _source_signature(config_dir / name)
        for name in LEGACY_ROOT_FILE_NAMES
    }
    if initial != final:
        raise LegacyOriginalSnapshotError(
            "legacy configuration roots changed while the original snapshot "
            "was being captured"
        )
    return tuple(captured)


def _source_signature(path: Path) -> tuple[int, int, int, int] | None:
    path_stat = _lexical_stat(path)
    if path_stat is None:
        return None
    if not _is_plain_file_stat(path_stat):
        raise LegacyOriginalSnapshotError(
            f"legacy configuration root is not a plain file: {path.name}"
        )
    return (
        path_stat.st_size,
        path_stat.st_mtime_ns,
        path_stat.st_ctime_ns,
        path_stat.st_ino,
    )


def _generation_id(root_records: list[dict[str, object]]) -> str:
    digest = hashlib.sha256(_serialize_json(root_records)).hexdigest()
    return f"original-{digest[:24]}"


def _published_generation_directories(generations_dir: Path) -> list[Path]:
    published: list[Path] = []
    for path in generations_dir.iterdir():
        if path.name.startswith("."):
            continue
        path_stat = _lexical_stat(path)
        if path_stat is None or not _is_plain_directory_stat(path_stat):
            raise LegacyOriginalSnapshotError(
                "unexpected entry in original snapshot generations"
            )
        if _GENERATION_PATTERN.fullmatch(path.name) is None:
            raise LegacyOriginalSnapshotError(
                "invalid original snapshot generation name"
            )
        published.append(path)
    return sorted(published, key=lambda path: path.name)


def _validate_generation(
    generation_path: Path,
    *,
    expected_generation: str,
    expected_manifest_hash: str | None = None,
) -> Path:
    if _GENERATION_PATTERN.fullmatch(expected_generation) is None:
        raise LegacyOriginalSnapshotError("CURRENT has an invalid generation")
    generation_stat = _lexical_stat(generation_path)
    if generation_stat is None or not _is_plain_directory_stat(generation_stat):
        raise LegacyOriginalSnapshotError(
            "CURRENT references a missing or unsafe generation"
        )

    manifest_path = generation_path / "manifest.json"
    manifest_stat = _lexical_stat(manifest_path)
    if manifest_stat is None or not _is_plain_file_stat(manifest_stat):
        raise LegacyOriginalSnapshotError("original snapshot manifest is missing")
    actual_manifest_hash = _sha256_file(manifest_path)
    if (
        expected_manifest_hash is not None
        and actual_manifest_hash != expected_manifest_hash
    ):
        raise LegacyOriginalSnapshotError("original snapshot manifest hash mismatch")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LegacyOriginalSnapshotError(
            "original snapshot manifest is unreadable"
        ) from exc
    if not isinstance(manifest, dict):
        raise LegacyOriginalSnapshotError("original snapshot manifest is not an object")
    if set(manifest) != {"schema_version", "kind", "generation", "roots"}:
        raise LegacyOriginalSnapshotError("original snapshot manifest fields differ")
    if manifest["schema_version"] != SNAPSHOT_SCHEMA_VERSION:
        raise LegacyOriginalSnapshotError(
            "unsupported original snapshot schema version"
        )
    if manifest["kind"] != "legacy-original":
        raise LegacyOriginalSnapshotError("invalid original snapshot kind")
    if manifest["generation"] != expected_generation:
        raise LegacyOriginalSnapshotError("original snapshot generation mismatch")

    roots = manifest["roots"]
    if not isinstance(roots, list) or len(roots) != len(LEGACY_ROOT_FILE_NAMES):
        raise LegacyOriginalSnapshotError("original snapshot root count mismatch")
    if _generation_id(roots) != expected_generation:
        raise LegacyOriginalSnapshotError("original snapshot metadata hash mismatch")

    files_dir = generation_path / "files"
    files_stat = _lexical_stat(files_dir)
    if files_stat is None or not _is_plain_directory_stat(files_stat):
        raise LegacyOriginalSnapshotError(
            "original snapshot files directory is missing"
        )

    expected_snapshot_names: set[str] = set()
    for expected_name, record in zip(
        LEGACY_ROOT_FILE_NAMES,
        roots,
        strict=True,
    ):
        if _validate_root_record(files_dir, expected_name, record):
            expected_snapshot_names.add(expected_name)
    actual_snapshot_names = {path.name for path in files_dir.iterdir()}
    if actual_snapshot_names != expected_snapshot_names:
        raise LegacyOriginalSnapshotError(
            "original snapshot files directory contains unexpected entries"
        )
    if {path.name for path in generation_path.iterdir()} != {
        "files",
        "manifest.json",
    }:
        raise LegacyOriginalSnapshotError(
            "original snapshot generation contains unexpected entries"
        )
    return manifest_path


def _validate_root_record(
    files_dir: Path,
    expected_name: str,
    record: object,
) -> bool:
    required_fields = {
        "name",
        "exists",
        "sha256",
        "size_bytes",
        "mtime_ns",
        "snapshot",
    }
    if not isinstance(record, dict) or set(record) != required_fields:
        raise LegacyOriginalSnapshotError("original snapshot root metadata differs")
    if record["name"] != expected_name or not isinstance(record["exists"], bool):
        raise LegacyOriginalSnapshotError("original snapshot root order differs")

    snapshot_path = files_dir / expected_name
    if not record["exists"]:
        if any(
            record[field] is not None
            for field in ("sha256", "size_bytes", "mtime_ns", "snapshot")
        ):
            raise LegacyOriginalSnapshotError(
                "missing legacy root has unexpected snapshot metadata"
            )
        if _lexical_stat(snapshot_path) is not None:
            raise LegacyOriginalSnapshotError(
                "missing legacy root unexpectedly has snapshot bytes"
            )
        return False

    expected_snapshot = f"files/{expected_name}"
    if record["snapshot"] != expected_snapshot:
        raise LegacyOriginalSnapshotError("legacy root snapshot path differs")
    if (
        not isinstance(record["sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is None
        or not isinstance(record["size_bytes"], int)
        or isinstance(record["size_bytes"], bool)
        or record["size_bytes"] < 0
        or not isinstance(record["mtime_ns"], int)
        or isinstance(record["mtime_ns"], bool)
        or record["mtime_ns"] < 0
    ):
        raise LegacyOriginalSnapshotError("legacy root integrity metadata is invalid")
    snapshot_stat = _lexical_stat(snapshot_path)
    if snapshot_stat is None or not _is_plain_file_stat(snapshot_stat):
        raise LegacyOriginalSnapshotError("legacy root snapshot bytes are missing")
    if snapshot_stat.st_size != record["size_bytes"]:
        raise LegacyOriginalSnapshotError("legacy root snapshot size mismatch")
    if _sha256_file(snapshot_path) != record["sha256"]:
        raise LegacyOriginalSnapshotError("legacy root snapshot hash mismatch")
    return True


def _read_current(current_path: Path) -> tuple[str, str]:
    current_stat = _lexical_stat(current_path)
    if current_stat is None or not _is_plain_file_stat(current_stat):
        raise LegacyOriginalSnapshotError("CURRENT is not a plain file")
    try:
        current = json.loads(current_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LegacyOriginalSnapshotError("CURRENT is unreadable") from exc
    if not isinstance(current, dict) or set(current) != {
        "schema_version",
        "generation",
        "manifest_sha256",
    }:
        raise LegacyOriginalSnapshotError("CURRENT fields differ")
    generation = current["generation"]
    manifest_hash = current["manifest_sha256"]
    if (
        current["schema_version"] != SNAPSHOT_SCHEMA_VERSION
        or not isinstance(generation, str)
        or _GENERATION_PATTERN.fullmatch(generation) is None
        or not isinstance(manifest_hash, str)
        or re.fullmatch(r"[0-9a-f]{64}", manifest_hash) is None
    ):
        raise LegacyOriginalSnapshotError("CURRENT integrity metadata is invalid")
    return generation, manifest_hash


def _write_current(
    current_path: Path,
    *,
    generation: str,
    manifest_hash: str,
) -> None:
    if _lexical_stat(current_path) is not None:
        raise LegacyOriginalSnapshotError("CURRENT already exists")
    payload = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "generation": generation,
        "manifest_sha256": manifest_hash,
    }
    fd, temp_name = tempfile.mkstemp(
        prefix=".CURRENT.",
        suffix=".tmp",
        dir=str(current_path.parent),
    )
    temp_path: Path | None = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(_serialize_json(payload))
            stream.flush()
            os.fsync(stream.fileno())
        if _lexical_stat(current_path) is not None:
            raise LegacyOriginalSnapshotError("CURRENT appeared during publication")
        if os.name == "nt":
            # Windows rename is same-volume atomic and refuses an existing
            # destination, including reparse points.
            os.rename(temp_path, current_path)
        else:
            # POSIX rename replaces an existing file, so publish through an
            # atomic no-overwrite hard link instead.
            os.link(temp_path, current_path)
            temp_path.unlink()
        temp_path = None
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _serialize_json(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _write_new_bytes(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_plain_directory(path: Path, *, create: bool) -> None:
    path_stat = _lexical_stat(path)
    if path_stat is not None:
        if not _is_plain_directory_stat(path_stat):
            raise LegacyOriginalSnapshotError(f"unsafe snapshot directory: {path.name}")
        return
    if not create:
        raise LegacyOriginalSnapshotError(f"snapshot directory is missing: {path.name}")
    path.mkdir(parents=True)


def _lexical_stat(path: Path) -> os.stat_result | None:
    """Return lstat data, preserving dangling links and Windows reparse points."""
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _is_reparse_point(path_stat: os.stat_result) -> bool:
    attributes = getattr(path_stat, "st_file_attributes", 0)
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & reparse_attribute)


def _is_plain_file_stat(path_stat: os.stat_result) -> bool:
    return stat.S_ISREG(path_stat.st_mode) and not _is_reparse_point(path_stat)


def _is_plain_directory_stat(path_stat: os.stat_result) -> bool:
    return stat.S_ISDIR(path_stat.st_mode) and not _is_reparse_point(path_stat)


def _fsync_directory(path: Path) -> None:
    """Best-effort directory flush; Windows may reject directory handles."""
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


@contextmanager
def _exclusive_snapshot_lock(lock_path: Path) -> Iterator[None]:
    lock_stat = _lexical_stat(lock_path)
    if lock_stat is None:
        descriptor = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        os.close(descriptor)
        lock_stat = _lexical_stat(lock_path)
    if lock_stat is None or not _is_plain_file_stat(lock_stat):
        raise LegacyOriginalSnapshotError("snapshot LOCK is not a plain file")

    with lock_path.open("r+b") as lock_file:
        opened_stat = os.fstat(lock_file.fileno())
        current_stat = _lexical_stat(lock_path)
        if (
            current_stat is None
            or not _is_plain_file_stat(current_stat)
            or (current_stat.st_dev, current_stat.st_ino)
            != (opened_stat.st_dev, opened_stat.st_ino)
        ):
            raise LegacyOriginalSnapshotError(
                "snapshot LOCK changed while it was being opened"
            )
        if lock_file.seek(0, os.SEEK_END) == 0:
            lock_file.write(b"\0")
            lock_file.flush()
            os.fsync(lock_file.fileno())
        lock_file.seek(0)
        _lock_one_byte(lock_file)
        try:
            yield
        finally:
            lock_file.seek(0)
            _unlock_one_byte(lock_file)


def _lock_one_byte(lock_file: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        return

    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)


def _unlock_one_byte(lock_file: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


__all__ = [
    "LEGACY_ROOT_FILE_NAMES",
    "LegacyOriginalSnapshot",
    "LegacyOriginalSnapshotError",
    "ensure_legacy_original_snapshot",
]
