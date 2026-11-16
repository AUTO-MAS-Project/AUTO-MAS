#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""官方 GitHub 发行版查询；不持有宿主配置或执行脚本安装。"""

import re

import httpx
from packaging.version import InvalidVersion, Version


async def request_github_release(
    repository: str, *, channel: str = "stable", proxy: httpx.Proxy | None = None
) -> dict:
    """读取所选通道最高版本，拒绝草稿、开发版与不可识别的版本标签。"""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or any(
        part in {".", ".."} for part in repository.split("/")
    ):
        raise ValueError("无效的 GitHub 仓库")
    if channel not in {"stable", "beta"}:
        raise ValueError("不支持的更新通道")
    path = "releases/latest" if channel == "stable" else "releases?per_page=100"
    async with httpx.AsyncClient(
        proxy=proxy, timeout=15, follow_redirects=True
    ) as client:
        response = await client.get(f"https://api.github.com/repos/{repository}/{path}")
        response.raise_for_status()
        payload = response.json()
    candidates = payload if isinstance(payload, list) else [payload]
    releases = []
    for item in candidates:
        if not isinstance(item, dict) or item.get("draft"):
            continue
        if channel == "stable" and item.get("prerelease"):
            continue
        try:
            version = Version(item["tag_name"])
        except (InvalidVersion, KeyError, TypeError):
            continue
        if not version.is_devrelease and not (
            channel == "stable" and version.is_prerelease
        ):
            releases.append((version, item))
    if not releases:
        raise ValueError("没有可识别的官方发行版")
    return max(releases, key=lambda item: item[0])[1]
