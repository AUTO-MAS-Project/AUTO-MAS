#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


import re

_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


class MirrorChyanError(RuntimeError):
    """Mirror酱版本号无法比较。"""


def compare_mirrorchyan_versions(remote_version: str, current_version: str) -> int:
    """按语义化版本顺序比较 Mirror酱 版本，无法解析时显式失败。

    ``v`` 前缀不参与比较，预发布版本仍按版本规则排序。
    返回值为正数时远端较新，负数时本地较新，零表示同一版本。
    """

    remote = remote_version.strip()
    current = current_version.strip()
    if not remote or not current:
        raise MirrorChyanError("远端版本或本地版本为空，无法比较版本")

    remote_parsed = _parse_semver(remote)
    current_parsed = _parse_semver(current)
    if remote_parsed is None or current_parsed is None:
        raise MirrorChyanError(
            f"版本号无法比较: 本地 {current_version!r}，远端 {remote_version!r}"
        )

    remote_core, remote_prerelease = remote_parsed
    current_core, current_prerelease = current_parsed
    if remote_core != current_core:
        return (remote_core > current_core) - (remote_core < current_core)
    if remote_prerelease is None:
        return 0 if current_prerelease is None else 1
    if current_prerelease is None:
        return -1
    return _compare_prerelease(remote_prerelease, current_prerelease)


def _parse_semver(
    raw_version: str,
) -> tuple[tuple[int, int, int], tuple[str, ...] | None] | None:
    version = raw_version.strip().removeprefix("v").removeprefix("V")
    match = _SEMVER_RE.fullmatch(version)
    if match is None:
        return None
    major, minor, patch, prerelease = match.groups()
    identifiers = tuple(prerelease.split(".")) if prerelease is not None else None
    if identifiers and any(
        item.isdigit() and len(item) > 1 and item.startswith("0")
        for item in identifiers
    ):
        return None
    return (int(major), int(minor), int(patch)), identifiers


def _compare_prerelease(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    for left_item, right_item in zip(left, right):
        if left_item == right_item:
            continue
        left_numeric = left_item.isdigit()
        right_numeric = right_item.isdigit()
        if left_numeric and right_numeric:
            return (int(left_item) > int(right_item)) - (
                int(left_item) < int(right_item)
            )
        if left_numeric != right_numeric:
            return -1 if left_numeric else 1
        return (left_item > right_item) - (left_item < right_item)
    return (len(left) > len(right)) - (len(left) < len(right))
