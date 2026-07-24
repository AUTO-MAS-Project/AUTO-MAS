"""Fail-closed archive handling for the legacy manual release helper."""

from __future__ import annotations

import os
import re
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath


_WINDOWS_DEVICE_NAME = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ArchiveBudgets:
    max_archive_bytes: int = 1024 * 1024 * 1024
    max_entries: int = 4096
    max_expanded_bytes: int = 2 * 1024 * 1024 * 1024
    max_file_bytes: int = 512 * 1024 * 1024

    def __post_init__(self) -> None:
        for field_name, value in (
            ("max_archive_bytes", self.max_archive_bytes),
            ("max_entries", self.max_entries),
            ("max_expanded_bytes", self.max_expanded_bytes),
            ("max_file_bytes", self.max_file_bytes),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")


def _entry_parts(entry: zipfile.ZipInfo) -> tuple[str, ...]:
    raw_name = entry.filename
    if not raw_name or "\x00" in raw_name:
        raise ValueError("ZIP entry has an empty name or contains NUL")

    normalized = raw_name.replace("\\", "/")
    posix_path = PurePosixPath(normalized)
    windows_path = PureWindowsPath(normalized)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise ValueError(f"ZIP entry uses an absolute path: {raw_name!r}")

    parts = tuple(part for part in posix_path.parts if part not in ("", "."))
    if not parts or any(part == ".." for part in parts):
        raise ValueError(f"ZIP entry escapes the destination: {raw_name!r}")

    for part in parts:
        if ":" in part:
            raise ValueError(f"ZIP entry uses a drive or alternate data stream: {raw_name!r}")
        canonical_part = part.rstrip(" .")
        if not canonical_part or _WINDOWS_DEVICE_NAME.fullmatch(canonical_part):
            raise ValueError(f"ZIP entry uses an unsafe Windows name: {raw_name!r}")
    return parts


def _reject_special_entry(entry: zipfile.ZipInfo) -> None:
    if entry.create_system != 3:
        return
    file_type = stat.S_IFMT(entry.external_attr >> 16)
    if file_type and file_type not in (stat.S_IFREG, stat.S_IFDIR):
        raise ValueError(f"ZIP entry is a link or special file: {entry.filename!r}")


def _validate_entries(
    archive: zipfile.ZipFile,
    budgets: ArchiveBudgets,
) -> list[tuple[zipfile.ZipInfo, tuple[str, ...]]]:
    entries = archive.infolist()
    if len(entries) > budgets.max_entries:
        raise ValueError(
            f"ZIP entry count {len(entries)} exceeds limit {budgets.max_entries}"
        )

    validated: list[tuple[zipfile.ZipInfo, tuple[str, ...]]] = []
    seen_paths: set[str] = set()
    total_expanded = 0
    for entry in entries:
        parts = _entry_parts(entry)
        _reject_special_entry(entry)

        canonical_path = "/".join(
            part.rstrip(" .").casefold() for part in parts
        )
        if canonical_path in seen_paths:
            raise ValueError(f"ZIP contains a duplicate canonical path: {entry.filename!r}")
        seen_paths.add(canonical_path)

        if entry.file_size < 0 or entry.file_size > budgets.max_file_bytes:
            raise ValueError(
                f"ZIP entry {entry.filename!r} exceeds the per-file limit"
            )
        total_expanded += entry.file_size
        if total_expanded > budgets.max_expanded_bytes:
            raise ValueError("ZIP expanded size exceeds the total limit")
        validated.append((entry, parts))
    return validated


def _copy_entry(
    archive: zipfile.ZipFile,
    entry: zipfile.ZipInfo,
    destination: Path,
    budgets: ArchiveBudgets,
) -> None:
    actual_size = 0
    with archive.open(entry, "r") as source, destination.open("xb") as target:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            actual_size += len(chunk)
            if actual_size > entry.file_size or actual_size > budgets.max_file_bytes:
                raise ValueError(
                    f"ZIP entry {entry.filename!r} expanded beyond its declared size"
                )
            target.write(chunk)
        target.flush()
        os.fsync(target.fileno())

    if actual_size != entry.file_size:
        raise ValueError(
            f"ZIP entry {entry.filename!r} size mismatch: "
            f"expected {entry.file_size}, got {actual_size}"
        )


def extract_zip_safely(
    archive_path: str | os.PathLike[str],
    destination_path: str | os.PathLike[str],
    *,
    budgets: ArchiveBudgets | None = None,
) -> list[str]:
    """Validate and atomically extract a ZIP into a new destination directory."""

    limits = budgets or ArchiveBudgets()
    archive_file = Path(archive_path).resolve(strict=True)
    destination = Path(destination_path).resolve(strict=False)
    if not archive_file.is_file():
        raise ValueError(f"ZIP archive is not a regular file: {archive_file}")
    if archive_file.stat().st_size > limits.max_archive_bytes:
        raise ValueError("ZIP archive exceeds the compressed-size limit")
    if destination.exists():
        raise FileExistsError(f"Extraction destination already exists: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=".artifact-stage-", dir=destination.parent)
    ).resolve(strict=True)
    extracted_files: list[str] = []
    try:
        with zipfile.ZipFile(archive_file, "r") as archive:
            validated_entries = _validate_entries(archive, limits)
            for entry, parts in validated_entries:
                target = staging.joinpath(*parts)
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                _copy_entry(archive, entry, target, limits)
                extracted_files.append(str(destination.joinpath(*parts)))

        if destination.exists():
            raise FileExistsError(
                f"Extraction destination appeared during validation: {destination}"
            )
        staging.rename(destination)
        return extracted_files
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
