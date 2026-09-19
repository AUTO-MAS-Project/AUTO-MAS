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

#   Contact: DLmaster_361@163.com

"""模拟器层面接管崩坏·星穹铁道客户端更新。

SRC 拉起游戏前由 MAS 负责登录，客户端 APK 版本落后时游戏会弹出强制更新门，
登录流程会一直卡住。本模块在启动模拟器后、登录前比对版本。

版本与安装包**同源**：逐跳跟随服务器对应下载入口的重定向，从最终地址
同时取到真实下载地址与版本号。这样不会出现"版本接口与安装包版本不一致"
的问题

只有配置了更新入口的服务器才做检查（当前为国服官服，入口跳转至安卓 APK，
可直接下载并通过 adb 安装），其余服务器跳过检查、交回原有登录流程判定。
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import httpx

from app.utils import get_logger
from app.utils.constants import STARRAIL_UPDATE_LINK_SERVER
from app.utils.game_apk import (
    GameUpdateResult,
    download_apk,
    get_installed_client_version,
    install_apk,
    is_client_outdated,
)

logger = get_logger("SRC 游戏更新")

_APK_SUFFIX = ".apk"

_VERSION_IN_NAME_RE = re.compile(r"(\d+(?:\.\d+)+)")
"""从下载地址的文件名中匹配版本号，形如 ``StarRail_4.5.0.apk``；
文件名以版本号开头时同样可匹配"""

_MAX_REDIRECT_HOPS = 5
"""下载入口重定向最大跟随跳数，防御入口被配置成多跳 302 链"""

__all__ = ["UpdateSource", "ensure_game_updated", "fetch_update_source"]


@dataclass
class UpdateSource:
    """从下载入口解析出的更新信息"""

    version: str
    """服务端当前客户端版本号，形如 ``4.5.0``"""
    download_url: str
    """302 跳转后的真实下载地址"""
    can_auto_install: bool
    """该地址是否为可直接安装的安卓安装包"""


async def _resolve_download_link(url: str) -> tuple[str, str] | None:
    """跟随重定向取真实下载地址，并从文件名解析出客户端版本号。

    崩坏·星穹铁道的下载入口为 302 跳转，最终地址的文件名里就带着客户端
    版本号。由此取到的版本与将下载的安装包必然同源同版本。

    跳转链逐跳手动跟随（实测国服官服入口为单跳，上限内兼容多跳）；每一跳
    只读响应头、不读响应体。

    Args:
        url: 下载入口（302 跳转至 CDN 真实地址）。

    Returns:
        tuple[str, str] | None: ``(最终地址, 版本号)``；跳数超限、请求失败或
        解析不出版本号时返回 ``None``。
    """

    final_url = ""
    try:
        async with httpx.AsyncClient(follow_redirects=False) as client:
            current_url = url
            for _ in range(_MAX_REDIRECT_HOPS):
                async with client.stream("GET", current_url, timeout=15.0) as response:
                    if not response.is_redirect:
                        final_url = str(response.url)
                        break
                    location = response.headers.get("location")
                if not location:
                    logger.warning(f"重定向响应缺少 Location 头: {current_url}")
                    return None
                # 跳转地址可能是相对路径，按当前地址补全
                current_url = urljoin(str(response.url), location)
            else:
                logger.warning(
                    f"下载入口重定向跳数超过上限 {_MAX_REDIRECT_HOPS}: {url}"
                )
                return None
    except Exception as e:
        logger.warning(f"解析下载地址失败: {e}")
        return None

    match = _VERSION_IN_NAME_RE.search(final_url.rsplit("/", 1)[-1])
    if match is None:
        logger.warning(f"未能从下载地址解析出版本号: {final_url}")
        return None

    logger.info(f"解析到下载地址 {final_url}，客户端版本 {match.group(1)}")
    return final_url, match.group(1)


async def fetch_update_source(server: str) -> UpdateSource | None:
    """拉取指定服务器的更新信息。

    Args:
        server: 用户配置的游戏服务器标识。

    Returns:
        UpdateSource | None: 更新信息；服务器无公开入口或请求失败时返回 ``None``。
    """

    link_url = STARRAIL_UPDATE_LINK_SERVER.get(server)
    if link_url is None:
        logger.info(f"服务器 {server} 无公开的更新入口，跳过客户端版本检查")
        return None

    resolved = await _resolve_download_link(link_url)
    if resolved is None:
        logger.warning(f"服务器 {server} 的更新入口未能解析出下载地址与版本号")
        return None

    download_url, version = resolved
    can_auto_install = download_url.lower().split("?", 1)[0].endswith(_APK_SUFFIX)

    logger.info(
        f"崩坏·星穹铁道服务器 {server} 当前版本: {version}"
        f"（{'可自动安装' if can_auto_install else '无可安装的安卓安装包'}）"
    )
    return UpdateSource(
        version=version,
        download_url=download_url,
        can_auto_install=can_auto_install,
    )


async def ensure_game_updated(
    *,
    adb_path: Path | None,
    adb_address: str,
    server: str,
    package_name: str,
    apk_dir: Path,
    if_auto_install: bool,
    time_limit: int,
    progress: Callable[[str], Awaitable[None]] | None = None,
) -> GameUpdateResult:
    """在登录游戏前确认客户端版本，必要时接管更新。

    Args:
        adb_path: 模拟器自带的 adb 路径；``None`` 时回退到系统 adb。
        adb_address: 模拟器的 adb 连接地址。
        server: 用户配置的游戏服务器标识。
        package_name: 游戏包名。
        apk_dir: 安装包下载目录。
        if_auto_install: 是否允许 MAS 自动下载并安装安装包。
        time_limit: 下载与安装的超时限制（分钟）。
        progress: 进度回调，用于向前端播报当前阶段。

    Returns:
        GameUpdateResult: 检查结果；``NeedManualUpdate`` 表示本次不应继续登录与代理。
    """

    if adb_address in ("", "Unknown"):
        logger.warning("未取到模拟器 adb 地址，跳过游戏版本检查")
        return GameUpdateResult("Skipped", "未取到模拟器 adb 地址，跳过游戏版本检查")

    source = await fetch_update_source(server)
    if source is None:
        return GameUpdateResult("Skipped", "更新入口不可用，跳过游戏版本检查")

    remote = source.version
    installed = await get_installed_client_version(adb_path, adb_address, package_name)
    if installed is None:
        # 读不到已安装版本可能是游戏未安装，也可能是 adb 临时异常，
        # 一律不阻断本次代理，交回原有登录流程判定
        return GameUpdateResult("Skipped", "未能读取模拟器内的游戏版本，跳过更新检查")

    if not is_client_outdated(installed, remote):
        return GameUpdateResult("UpToDate", f"游戏客户端已是最新版本 {installed}")

    outdated_text = f"游戏客户端版本落后（已安装 {installed}，最新 {remote}）"
    logger.info(outdated_text)

    if not source.can_auto_install:
        return GameUpdateResult(
            "NeedManualUpdate",
            f"{outdated_text}，更新入口未提供安卓安装包直链，请手动更新游戏后重试",
        )

    if not if_auto_install:
        return GameUpdateResult(
            "NeedManualUpdate",
            f"{outdated_text}，未开启自动安装，请手动更新游戏后重试",
        )

    apk_path = apk_dir / f"hkrpg-{remote}.apk"
    try:
        if progress is not None:
            await progress(f"{outdated_text}\n正在下载游戏安装包")
        await download_apk(
            source.download_url, apk_path, progress, timeout=time_limit * 60
        )

        if progress is not None:
            await progress(f"{outdated_text}\n正在安装游戏安装包")
        await install_apk(adb_path, adb_address, apk_path, timeout=time_limit * 60)
    except Exception as e:
        logger.opt(exception=True).warning(f"接管游戏更新失败: {e}")
        return GameUpdateResult(
            "NeedManualUpdate",
            f"{outdated_text}，MAS 自动更新失败（{e}），请手动更新游戏后重试",
        )
    finally:
        # 安装包体积很大，无论成败都不长期占用磁盘
        apk_path.unlink(missing_ok=True)

    current = await get_installed_client_version(adb_path, adb_address, package_name)
    if current is None or is_client_outdated(current, remote):
        return GameUpdateResult(
            "NeedManualUpdate",
            f"安装后版本仍未达到 {remote}（当前 {current or '未知'}），"
            "请手动更新游戏后重试",
        )

    return GameUpdateResult("Updated", f"MAS 已将游戏客户端更新至 {current}")
