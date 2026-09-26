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

"""模拟器层面接管《重返未来：1999》官服客户端更新。

游戏大版本是强制更新：客户端落后时一启动就弹「请下载并安装新客户端」，M9A 的全部
任务都会失败。本模块在模拟器启动之后、第一个任务下发之前比对版本，由 MaaFW 引擎经
特调钩子调用（见 ``app/task/M9A/flavor.py``）。

只有官服有公开的安卓直链：取官网的版本配置接口拿直链，再按 HTTP Range 只读直链里安装包
的清单拿版本号（直链文件名里没有版本号）。版本与安装包同源，不会出现"接口说的版本和
下到的包不一致"。B 服、国际服等其他资源一律跳过，交回 M9A 原有流程。
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path

import httpx

from app.utils import get_logger
from app.utils.game_apk import (
    GameUpdateResult,
    download_apk,
    fetch_remote_apk_version,
    get_installed_client_info,
    install_apk,
    is_client_outdated,
)

logger = get_logger("M9A 游戏更新")

OFFICIAL_PACKAGE_NAME = "com.shenlan.m.reverse1999"
"""官服包名（B 服是 ``.bilibili`` 后缀的另一个包）"""

GAME_UPDATE_TIME_LIMIT_MINUTES = 60
"""下载与安装各自的超时（分钟）。官服安装包约 2 GB，与 MAA / SRC 的默认值一致；
不做成配置项：只在网络停滞时才会撞上，httpx 的单次读写超时另有兜底。"""

_SITE_API_JS_URL = "https://re.bluepoch.com/assets/js/api.js"
"""官网前端脚本：版本配置接口的 ``pageVersion`` 写死在这里，随游戏大版本改"""
_VERSION_PAGE_URL = "https://re.bluepoch.com/activity/official/websites/version-page"
_GAME_ID = 50001
_FALLBACK_PAGE_VERSION = "4.0"
"""从官网脚本里读不出 ``pageVersion`` 时用的值（2026-09-24 官网的取值；实测旧页面版本
仍返回同一条直链）"""
_PAGE_VERSION_RE = re.compile(r"pageVersion\s*:\s*[\"']([^\"']+)[\"']")

__all__ = [
    "GAME_UPDATE_TIME_LIMIT_MINUTES",
    "OFFICIAL_PACKAGE_NAME",
    "ensure_game_updated",
    "fetch_download_url",
]


async def _fetch_page_version(client: httpx.AsyncClient) -> str:
    """官网当前的页面版本；读不出来就用写死的兜底值。"""

    try:
        response = await client.get(_SITE_API_JS_URL)
        response.raise_for_status()
        match = _PAGE_VERSION_RE.search(response.text)
        if match is not None:
            return match.group(1)
        logger.warning("官网脚本里没有找到 pageVersion，使用兜底值")
    except Exception as e:
        logger.warning(f"读取官网页面版本失败，使用兜底值: {e}")
    return _FALLBACK_PAGE_VERSION


async def fetch_download_url() -> str | None:
    """从官网版本配置接口取官服安卓安装包直链。

    Returns:
        str | None: 直链；接口不可用或没给直链时返回 ``None``。
    """

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            page_version = await _fetch_page_version(client)
            response = await client.post(
                _VERSION_PAGE_URL,
                json={"gameId": _GAME_ID, "pageVersion": page_version},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as e:
        logger.warning(f"请求官网版本配置失败: {e}")
        return None

    data = payload.get("data") if isinstance(payload, dict) else None
    url = data.get("androidDownloadUrl") if isinstance(data, dict) else None
    if not isinstance(url, str) or not url.startswith("http"):
        logger.warning(
            f"官网版本配置没有给出安卓直链（pageVersion={page_version}）: "
            f"code={payload.get('code') if isinstance(payload, dict) else None}"
        )
        return None
    logger.info(f"官服安卓直链: {url}（pageVersion={page_version}）")
    return url


async def ensure_game_updated(
    *,
    adb_path: Path | None,
    adb_address: str,
    resource_name: str | None,
    package_name: str,
    official_resource_name: str,
    apk_dir: Path,
    if_auto_install: bool,
    progress: Callable[[str], Awaitable[None]] | None = None,
) -> GameUpdateResult:
    """在下发第一个任务前确认官服客户端版本，必要时接管更新。

    Args:
        adb_path: adb 路径；``None`` 时回退到系统 adb。
        adb_address: 模拟器的 adb 连接地址。
        resource_name: 本次运行的 MaaFW 资源名。
        package_name: 本次随模拟器拉起的游戏包名；空串表示没有拉起游戏。
        official_resource_name: 官服资源名，只有它才检查。
        apk_dir: 安装包下载目录。
        if_auto_install: 落后时是否由 MAS 自动下载并安装。
        progress: 进度回调，写进用户可见的运行日志。

    Returns:
        GameUpdateResult: 检查结果；``NeedManualUpdate`` 表示本次不应继续代理。
    """

    async def report(text: str) -> None:
        if progress is not None:
            await progress(text)

    if str(resource_name or "").strip() != official_resource_name:
        return GameUpdateResult(
            "Skipped", f"资源不是{official_resource_name}，跳过游戏版本检查"
        )
    if package_name != OFFICIAL_PACKAGE_NAME:
        return GameUpdateResult(
            "Skipped",
            f"本次启动的游戏包名不是官服（{package_name or '未启动游戏'}），跳过游戏版本检查",
        )
    if adb_address in ("", "Unknown"):
        return GameUpdateResult("Skipped", "未取到模拟器 adb 地址，跳过游戏版本检查")

    download_url = await fetch_download_url()
    if download_url is None:
        return GameUpdateResult("Skipped", "未能从官网取到安装包直链，跳过游戏版本检查")

    remote = await fetch_remote_apk_version(download_url)
    if remote is None:
        return GameUpdateResult(
            "Skipped", "未能读取官网安装包的版本号，跳过游戏版本检查"
        )
    if remote.package != OFFICIAL_PACKAGE_NAME:
        return GameUpdateResult(
            "Skipped",
            f"官网安装包的包名是 {remote.package}，与官服不符，跳过游戏版本检查",
        )

    installed_info = await get_installed_client_info(
        adb_path, adb_address, package_name
    )
    if installed_info is None:
        # 读不到已安装版本可能是游戏未安装，也可能是 adb 临时异常，
        # 一律不阻断本次代理，交回 M9A 原有流程判定
        return GameUpdateResult("Skipped", "未能读取模拟器内的游戏版本，跳过更新检查")
    installed, installed_code = installed_info

    if not is_client_outdated(installed, remote.version_name):
        return GameUpdateResult("UpToDate", f"游戏客户端已是最新版本 {installed}")

    outdated_text = (
        f"游戏客户端版本落后（已安装 {installed}，最新 {remote.version_name}）"
    )
    logger.info(
        f"{outdated_text}；versionCode 本机 {installed_code}，官网 {remote.version_code}"
    )

    if (
        installed_code is not None
        and remote.version_code is not None
        and installed_code > remote.version_code
    ):
        # Android 不允许 versionCode 降级：其他渠道（如模拟器自带的应用中心）装的客户端
        # versionCode 比官网包高时，官网包永远装不上，下了也白下
        return GameUpdateResult(
            "NeedManualUpdate",
            f"{outdated_text}。本机客户端来自其他渠道（如模拟器自带的应用中心），"
            "官网安装包无法覆盖安装，请在原渠道更新游戏后重试",
        )

    if not if_auto_install:
        return GameUpdateResult(
            "NeedManualUpdate",
            f"{outdated_text}，未开启自动安装，请手动更新游戏后重试",
        )

    time_limit = GAME_UPDATE_TIME_LIMIT_MINUTES * 60
    apk_path = apk_dir / f"reverse1999-{remote.version_name}.apk"
    try:
        await report(f"{outdated_text}，正在下载游戏安装包")
        await download_apk(download_url, apk_path, progress, timeout=time_limit)
        await report("正在安装游戏安装包（保留游戏数据）")
        await install_apk(adb_path, adb_address, apk_path, timeout=time_limit)
    except Exception as e:
        logger.opt(exception=True).warning(f"接管游戏更新失败: {e}")
        return GameUpdateResult(
            "NeedManualUpdate",
            f"{outdated_text}，MAS 自动更新失败（{e}），请手动更新游戏后重试",
        )
    finally:
        # 安装包体积很大，无论成败都不长期占用磁盘。取消时 adb 可能还开着这个文件，
        # 删不掉就留给下次覆盖，不能让删除失败盖掉取消本身。
        with suppress(OSError):
            apk_path.unlink(missing_ok=True)

    current_info = await get_installed_client_info(adb_path, adb_address, package_name)
    current = current_info[0] if current_info is not None else None
    if current is None or is_client_outdated(current, remote.version_name):
        return GameUpdateResult(
            "NeedManualUpdate",
            f"安装后版本仍未达到 {remote.version_name}（当前 {current or '未知'}），"
            "请手动更新游戏后重试",
        )

    return GameUpdateResult("Updated", f"MAS 已将游戏客户端更新至 {current}")
