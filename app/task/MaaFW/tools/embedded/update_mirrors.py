#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""GitHub Release 下载地址 → 加速镜像候选地址。

国内直连 ``github.com`` 的资产下载常年 100 多 KB/s，MFW 项目的 359MB 全量包
要四十分钟；初始化 clone 主仓早就在用 gh-proxy 那组镜像，项目包一直没用上。

镜像清单与开关都只在接缝层读，核心包
（``tools/core/project_update``）只收一串 ``(名字, URL)`` 备选，
自己不认识 ``Config``，也不知道 GitHub 长什么样。

**镜像只在能校验完整性时才用**：经第三方转发的字节必须对得上发布方的
sha256，这个判断在核心包的 ``download_resumable`` 里（没有摘要就忽略备选），
不在这里——这里只回答「这个地址有哪些镜像写法」。
"""

from __future__ import annotations

import re
from typing import Sequence
from urllib.parse import urlsplit

# 与 ``frontend/electron/services/mirrorService.ts`` 的 gh-proxy 组同源，
# **改一处要同步另一处**。用法是前缀直接拼原地址：
# ``https://gh-proxy.com/https://github.com/<owner>/<repo>/releases/download/...``
# 顺序即尝试顺序。
GITHUB_RELEASE_MIRRORS: tuple[tuple[str, str], ...] = (
    ("gh-proxy (Cloudflare)", "https://gh-proxy.com/"),
    ("gh-proxy (Fastly)", "https://cdn.gh-proxy.com/"),
    ("gh-proxy (EdgeOne)", "https://edgeone.gh-proxy.com/"),
    ("ghfast", "https://ghfast.top/"),
)

MIRROR_MODE_AUTO = "Auto"
MIRROR_MODE_OFF = "Off"

# ``/<owner>/<repo>/releases/download/<tag>/<资产名>``——只有 Release 资产走
# 镜像。API 地址（api.github.com）与仓库页面都不在内：前者返回 JSON 元数据，
# 几 KB 而已，套镜像只是多一层不确定性。
_RELEASE_ASSET_PATH = re.compile(r"^/[^/]+/[^/]+/releases/download/.+")


def _mirror_mode() -> str:
    """全局 ``Update.GitHubMirror``；读不到或值非法一律当 ``Auto``。

    ``app.core.config`` 会拉起整份全局配置，按接缝层的惯例在函数里导入。
    """

    try:
        from app.core.config import Config

        value = str(Config.get("Update", "GitHubMirror") or "").strip()
    except Exception:  # noqa: BLE001 - 旧配置文件缺这一项不该挡住更新
        return MIRROR_MODE_AUTO
    return value if value in {MIRROR_MODE_AUTO, MIRROR_MODE_OFF} else MIRROR_MODE_AUTO


def github_release_mirror_urls(download_url: str) -> list[tuple[str, str]]:
    """``(镜像名, 镜像地址)`` 列表，按尝试顺序；不适用时回空列表。

    空列表有三种来源，调用方不需要区分：不是 GitHub Release 资产地址
    （Mirror 酱的一次性地址就走这条）、用户把 ``Update.GitHubMirror`` 关成了
    ``Off``、或者地址根本解析不了。
    """

    if _mirror_mode() == MIRROR_MODE_OFF:
        return []
    value = str(download_url or "").strip()
    if not value:
        return []
    try:
        parsed = urlsplit(value)
    except ValueError:
        return []
    if parsed.scheme.casefold() != "https":
        return []
    if (parsed.hostname or "").casefold() != "github.com":
        return []
    if not _RELEASE_ASSET_PATH.match(parsed.path):
        return []
    return [(name, f"{prefix}{value}") for name, prefix in GITHUB_RELEASE_MIRRORS]


def describe_github_mirror() -> str:
    """给日志用的一句话：镜像是开着还是被关了。"""

    return "自动" if _mirror_mode() == MIRROR_MODE_AUTO else "已关闭"


__all__: Sequence[str] = [
    "GITHUB_RELEASE_MIRRORS",
    "MIRROR_MODE_AUTO",
    "MIRROR_MODE_OFF",
    "describe_github_mirror",
    "github_release_mirror_urls",
]
