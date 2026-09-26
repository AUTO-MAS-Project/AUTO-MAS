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


import platform
import re
import sys
from dataclasses import dataclass
from urllib.parse import quote

import httpx


MIRRORCHYAN_API_BASE = "https://mirrorchyan.com/api/resources"
_CDK_ERROR_CODES = {7001, 7002, 7003, 7004, 7005}
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


class MirrorChyanError(RuntimeError):
    """Mirror酱查询失败或返回的版本号无法比较。"""


@dataclass(frozen=True)
class MirrorChyanVersionCheck:
    """Mirror酱返回的版本检查结果。"""

    resource_id: str
    current_version: str
    latest_version: str
    channel: str
    has_update: bool


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
            "版本号无法比较: "
            f"本地 {current_version!r}，远端 {remote_version!r}"
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


def _platform_parameters() -> tuple[str, str]:
    """返回 MXU 使用的 Mirror酱 操作系统和架构名称。"""

    if sys.platform == "win32":
        os_name = "windows"
    elif sys.platform == "darwin":
        os_name = "darwin"
    elif sys.platform.startswith("linux"):
        os_name = "linux"
    else:
        os_name = sys.platform

    machine = platform.machine().lower()
    if machine in {"x86_64", "x64", "amd64"}:
        arch = "amd64"
    elif machine in {"aarch64", "arm64"}:
        arch = "arm64"
    else:
        arch = machine
    return os_name, arch


async def check_mirrorchyan_update(
    resource_id: str,
    current_version: str,
    *,
    channel: str = "stable",
    user_agent: str = "AutoMasGui",
    os_name: str | None = None,
    arch: str | None = None,
    timeout: float = 30.0,
) -> MirrorChyanVersionCheck:
    """查询 Mirror酱 latest 接口并严格比较当前版本。

    不附带 CDK：Mirror酱允许无授权查询版本，下载链接仍由其
    授权策略控制。API 请求、响应结构和版本比较的失败都会抛出
    ``MirrorChyanError``，不会被转换成「没有更新」。
    """

    resource_id = resource_id.strip()
    current_version = current_version.strip()
    channel = channel.strip().lower()
    if not resource_id:
        raise MirrorChyanError("interface.json 未声明 mirrorchyan_rid")
    if not current_version:
        raise MirrorChyanError("interface.json 未声明 version")
    if channel not in {"stable", "beta"}:
        raise MirrorChyanError(f"不支持的 Mirror酱 更新频道: {channel!r}")

    default_os, default_arch = _platform_parameters()
    params = {
        "current_version": current_version,
        "channel": channel,
        "user_agent": user_agent,
        "os": os_name or default_os,
        "arch": arch or default_arch,
    }
    url = f"{MIRRORCHYAN_API_BASE}/{quote(resource_id, safe='')}/latest"

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            response = await client.get(
                url,
                params=params,
                headers={"User-Agent": user_agent},
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as error:
        raise MirrorChyanError(f"Mirror酱 请求失败: {error}") from error
    except ValueError as error:
        raise MirrorChyanError("Mirror酱 返回了无效 JSON") from error

    if not isinstance(payload, dict):
        raise MirrorChyanError("Mirror酱 返回了无效响应")

    if "code" not in payload:
        raise MirrorChyanError("Mirror酱 响应缺少状态码")
    try:
        error_code = int(payload.get("code", 0))
    except (TypeError, ValueError) as error:
        raise MirrorChyanError("Mirror酱 返回了无效状态码") from error

    data = payload.get("data")
    data = data if isinstance(data, dict) else {}
    latest_version = str(data.get("version_name") or "").strip()
    message = str(payload.get("msg") or payload.get("message") or "").strip()

    # MXU 与 MaaFW 均允许已知 CDK 状态错误携带的 version_name
    # 用于版本检查；其它业务错误不能被当作「无更新」。
    if error_code != 0 and not (error_code in _CDK_ERROR_CODES and latest_version):
        detail = f": {message}" if message else ""
        raise MirrorChyanError(f"Mirror酱 返回错误 [{error_code}]{detail}")
    if not latest_version:
        raise MirrorChyanError("Mirror酱 响应缺少 version_name")

    comparison = compare_mirrorchyan_versions(latest_version, current_version)
    return MirrorChyanVersionCheck(
        resource_id=resource_id,
        current_version=current_version,
        latest_version=latest_version,
        channel=channel,
        has_update=comparison > 0,
    )
