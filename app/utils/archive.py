#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

"""安全校验 ZIP 内容，并将完整结果发布到一个新目录。"""

from __future__ import annotations

import os
import shutil
import stat
import unicodedata
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from .atomic_file import create_staging_directory


_WINDOWS_INVALID_CHARACTERS = frozenset('<>:"|?*')
_WINDOWS_RESERVED_NAMES = frozenset(
    {
        "aux",
        "clock$",
        "con",
        "conin$",
        "conout$",
        "nul",
        "prn",
        *(f"com{index}" for index in range(1, 10)),
        *(f"lpt{index}" for index in range(1, 10)),
    }
)


class ArchiveValidationError(RuntimeError):
    """归档文件不满足安全解压约束。"""


@dataclass(frozen=True, slots=True)
class ArchiveSafetyLimits:
    """ZIP 下载与展开过程使用的资源上限。"""

    max_archive_bytes: int = 1024 * 1024 * 1024
    max_entries: int = 4096
    max_expanded_bytes: int = 2 * 1024 * 1024 * 1024
    max_file_bytes: int = 512 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class _ValidatedMember:
    info: zipfile.ZipInfo
    parts: tuple[str, ...]
    is_directory: bool


def read_archive_safety_limits(
    environment: Mapping[str, str] | None = None,
) -> ArchiveSafetyLimits:
    """读取与前端发布验证器一致的归档安全上限。"""

    values = os.environ if environment is None else environment
    defaults = ArchiveSafetyLimits()
    return ArchiveSafetyLimits(
        max_archive_bytes=_read_positive_limit(
            values,
            "AUTO_MAS_ARCHIVE_MAX_BYTES",
            defaults.max_archive_bytes,
        ),
        max_entries=_read_positive_limit(
            values,
            "AUTO_MAS_ARCHIVE_MAX_ENTRIES",
            defaults.max_entries,
        ),
        max_expanded_bytes=_read_positive_limit(
            values,
            "AUTO_MAS_ARCHIVE_MAX_EXPANDED_BYTES",
            defaults.max_expanded_bytes,
        ),
        max_file_bytes=_read_positive_limit(
            values,
            "AUTO_MAS_ARCHIVE_MAX_FILE_BYTES",
            defaults.max_file_bytes,
        ),
    )


def safe_extract_zip(
    archive_path: Path,
    destination: Path,
    *,
    limits: ArchiveSafetyLimits | None = None,
) -> list[Path]:
    """完整预检 ZIP，再原子发布解压结果到一个不存在的目录。

    Args:
        archive_path: 待解压的 ZIP 文件。
        destination: 最终目录；调用前必须不存在。
        limits: 可选资源上限，默认读取 ``AUTO_MAS_ARCHIVE_*``。

    Returns:
        最终目录内已解压的普通文件路径。

    Raises:
        ArchiveValidationError: ZIP 无效、路径不安全或资源预算超限。
        FileExistsError: 最终目录已存在。
    """

    archive_path = Path(archive_path)
    destination = Path(destination)
    effective_limits = limits or read_archive_safety_limits()

    if os.path.lexists(destination):
        raise FileExistsError(f"归档解压目标已存在: {destination}")
    if archive_path.stat().st_size > effective_limits.max_archive_bytes:
        raise ArchiveValidationError(
            "归档大小超过 AUTO_MAS_ARCHIVE_MAX_BYTES "
            f"({effective_limits.max_archive_bytes})"
        )

    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            members = _validate_members(archive, effective_limits)
            return _extract_validated_members(
                archive,
                destination,
                members,
                effective_limits,
            )
    except ArchiveValidationError:
        raise
    except (NotImplementedError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
        raise ArchiveValidationError(f"归档无法安全读取: {error}") from error


def _read_positive_limit(
    environment: Mapping[str, str],
    name: str,
    default: int,
) -> int:
    raw_value = environment.get(name, "").strip()
    if not raw_value:
        return default
    if (
        not raw_value.isascii()
        or not raw_value.isdecimal()
        or raw_value.startswith("0")
    ):
        raise ArchiveValidationError(f"{name} 必须是正十进制整数")
    maximum_safe_integer = "9007199254740991"
    if len(raw_value) > len(maximum_safe_integer) or (
        len(raw_value) == len(maximum_safe_integer)
        and raw_value > maximum_safe_integer
    ):
        raise ArchiveValidationError(f"{name} 超过 JavaScript 安全整数范围")
    return int(raw_value)


def _validate_members(
    archive: zipfile.ZipFile,
    limits: ArchiveSafetyLimits,
) -> list[_ValidatedMember]:
    infos = archive.infolist()
    if len(infos) > limits.max_entries:
        raise ArchiveValidationError(
            "归档条目数超过 AUTO_MAS_ARCHIVE_MAX_ENTRIES "
            f"({limits.max_entries})"
        )

    validated: list[_ValidatedMember] = []
    declared_paths: set[tuple[str, ...]] = set()
    path_kinds: dict[tuple[str, ...], str] = {}
    expanded_bytes = 0

    for info in infos:
        member = _validate_member_path(info)
        path_key = tuple(
            unicodedata.normalize("NFC", part).casefold() for part in member.parts
        )

        if path_key in declared_paths:
            raise ArchiveValidationError(
                f"归档包含重复或大小写冲突路径: {info.filename}"
            )

        for index in range(1, len(path_key)):
            parent_key = path_key[:index]
            if path_kinds.get(parent_key) == "file":
                raise ArchiveValidationError(
                    f"归档文件与子路径冲突: {info.filename}"
                )
            path_kinds.setdefault(parent_key, "directory")

        existing_kind = path_kinds.get(path_key)
        current_kind = "directory" if member.is_directory else "file"
        if existing_kind is not None and existing_kind != current_kind:
            raise ArchiveValidationError(
                f"归档文件与目录路径冲突: {info.filename}"
            )

        if not member.is_directory:
            if info.file_size > limits.max_file_bytes:
                raise ArchiveValidationError(
                    "归档成员超过 AUTO_MAS_ARCHIVE_MAX_FILE_BYTES "
                    f"({limits.max_file_bytes}): {info.filename}"
                )
            expanded_bytes += info.file_size
            if expanded_bytes > limits.max_expanded_bytes:
                raise ArchiveValidationError(
                    "归档展开大小超过 AUTO_MAS_ARCHIVE_MAX_EXPANDED_BYTES "
                    f"({limits.max_expanded_bytes})"
                )

        declared_paths.add(path_key)
        path_kinds[path_key] = current_kind
        validated.append(member)

    return validated


def _validate_member_path(info: zipfile.ZipInfo) -> _ValidatedMember:
    raw_name = info.filename
    if not raw_name or "\x00" in raw_name:
        raise ArchiveValidationError("归档包含空路径或 NUL 字符")
    if info.flag_bits & 0x1:
        raise ArchiveValidationError(f"归档包含加密条目: {raw_name}")

    normalized_name = raw_name.replace("\\", "/")
    windows_path = PureWindowsPath(normalized_name)
    if (
        PurePosixPath(normalized_name).is_absolute()
        or windows_path.drive
        or windows_path.root
    ):
        raise ArchiveValidationError(f"归档包含绝对路径: {raw_name}")

    is_directory = normalized_name.endswith("/")
    path_text = normalized_name[:-1] if is_directory else normalized_name
    parts = tuple(path_text.split("/"))
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ArchiveValidationError(f"归档包含不安全路径: {raw_name}")

    for part in parts:
        _validate_windows_component(part, raw_name)

    unix_mode = info.external_attr >> 16
    unix_type = stat.S_IFMT(unix_mode)
    if unix_type == stat.S_IFLNK:
        raise ArchiveValidationError(f"归档包含符号链接: {raw_name}")
    if unix_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
        raise ArchiveValidationError(f"归档包含特殊文件: {raw_name}")
    if unix_type == stat.S_IFDIR and not is_directory:
        raise ArchiveValidationError(f"归档目录标记与路径不一致: {raw_name}")
    if unix_type == stat.S_IFREG and is_directory:
        raise ArchiveValidationError(f"归档文件标记与路径不一致: {raw_name}")
    if bool(info.external_attr & 0x10) and not is_directory:
        raise ArchiveValidationError(f"归档目录属性与路径不一致: {raw_name}")
    if is_directory and info.file_size != 0:
        raise ArchiveValidationError(f"归档目录包含非零数据: {raw_name}")

    return _ValidatedMember(
        info=info,
        parts=parts,
        is_directory=is_directory,
    )


def _validate_windows_component(component: str, raw_name: str) -> None:
    if component.endswith((" ", ".")):
        raise ArchiveValidationError(f"归档路径以空格或点结尾: {raw_name}")
    if any(character in _WINDOWS_INVALID_CHARACTERS for character in component):
        raise ArchiveValidationError(f"归档路径含 Windows 非法字符: {raw_name}")
    if any(ord(character) < 32 for character in component):
        raise ArchiveValidationError(f"归档路径含控制字符: {raw_name}")

    device_name = component.split(".", maxsplit=1)[0].rstrip(" .").casefold()
    if device_name in _WINDOWS_RESERVED_NAMES:
        raise ArchiveValidationError(f"归档路径使用 Windows 保留名称: {raw_name}")


def _extract_validated_members(
    archive: zipfile.ZipFile,
    destination: Path,
    members: list[_ValidatedMember],
    limits: ArchiveSafetyLimits,
) -> list[Path]:
    destination_parent = destination.parent
    destination_parent.mkdir(parents=True, exist_ok=True)
    # 解压结果经 os.replace 发布为持久目录;mkdtemp 的仅限当前令牌 DACL
    # 会随发布保留,导致另一提升级别的进程无法访问,改用继承 ACL 暂存目录。
    temporary_root = create_staging_directory(
        destination_parent,
        prefix=f".{destination.name}.extract-",
    )
    extracted_parts: list[tuple[str, ...]] = []
    expanded_bytes = 0

    try:
        for member in members:
            target = temporary_root.joinpath(*member.parts)
            if member.is_directory:
                target.mkdir(parents=True, exist_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with archive.open(member.info, "r") as source, target.open("xb") as output:
                while chunk := source.read(1024 * 1024):
                    written += len(chunk)
                    expanded_bytes += len(chunk)
                    if written > limits.max_file_bytes:
                        raise ArchiveValidationError(
                            "归档成员实际展开大小超过 "
                            "AUTO_MAS_ARCHIVE_MAX_FILE_BYTES "
                            f"({limits.max_file_bytes}): {member.info.filename}"
                        )
                    if expanded_bytes > limits.max_expanded_bytes:
                        raise ArchiveValidationError(
                            "归档实际展开大小超过 "
                            "AUTO_MAS_ARCHIVE_MAX_EXPANDED_BYTES "
                            f"({limits.max_expanded_bytes})"
                        )
                    output.write(chunk)

            if written != member.info.file_size:
                raise ArchiveValidationError(
                    f"归档成员声明大小与实际不符: {member.info.filename}"
                )
            extracted_parts.append(member.parts)

        os.replace(temporary_root, destination)
    except BaseException:
        if os.path.lexists(temporary_root):
            shutil.rmtree(temporary_root)
        raise

    return [destination.joinpath(*parts) for parts in extracted_parts]
