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

"""模拟器层面接管明日方舟游戏更新。

MAA 自带的开始唤醒任务会原地轮询等待游戏内的资源热更新走完，因此本模块不重复实现热更新，
只负责 MAA 无法处理的两件事：

1. 客户端 APK 版本落后时游戏会弹出强制更新门，MAA 没有对应任务，只会一直卡到超时。
   本模块在 MAA 启动前比对版本，官服可直接下载安装包并通过 adb 安装。
2. 资源热更新耗时可能远超日常超时限制，本模块通过记录服务端 resVersion 让调用方
   在有热更新待下载的那一次运行放宽超时，避免把正常更新误判成卡死。

adb 读取/安装、版本比较与安装包下载等游戏无关原语见 ``app/utils/game_apk.py``。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.utils import get_logger
from app.utils.constants import (
    ARKNIGHTS_OFFICIAL_APK_URL,
    ARKNIGHTS_VERSION_API_SERVER,
)
from app.utils.game_apk import (
    GameUpdateResult,
    download_apk,
    get_installed_client_version,
    install_apk,
    is_client_outdated,
)

logger = get_logger("MAA 游戏更新")

_VERSION_API = "https://ak-conf.hypergryph.com/config/prod/{server}/Android/version"

__all__ = [
    "GameUpdateResult",
    "ensure_game_updated",
    "fetch_game_version",
]


@dataclass
class GameVersion:
    """服务端下发的游戏版本信息"""

    client: str
    """客户端版本号，形如 ``2.7.61``"""
    resource: str
    """资源版本号，形如 ``26-08-17-11-25-42_dbc172``"""


async def fetch_game_version(server: str) -> GameVersion | None:
    """拉取指定服务器的客户端与资源版本号。

    Args:
        server: MAA 服务器标识，如 ``Official``、``Bilibili``。

    Returns:
        GameVersion | None: 版本信息；服务器无公开接口或请求失败时返回 ``None``。
    """

    api_server = ARKNIGHTS_VERSION_API_SERVER.get(server)
    if api_server is None:
        logger.info(f"服务器 {server} 无可用的版本接口，跳过版本检查")
        return None

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                _VERSION_API.format(server=api_server), timeout=15.0
            )
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        logger.warning(f"获取服务器 {server} 的游戏版本失败: {e}")
        return None

    client_version = str(data.get("clientVersion", "")).strip()
    resource_version = str(data.get("resVersion", "")).strip()
    if not client_version:
        logger.warning(f"服务器 {server} 返回的版本信息缺少 clientVersion: {data}")
        return None

    logger.info(
        f"服务器 {server} 当前版本: 客户端 {client_version}, 资源 {resource_version}"
    )
    return GameVersion(client=client_version, resource=resource_version)


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
    """在 MAA 启动前确认游戏客户端版本，必要时接管更新。

    Args:
        adb_path: 模拟器自带的 adb 路径；``None`` 时回退到系统 adb。
        adb_address: 模拟器的 adb 连接地址。
        server: MAA 服务器标识。
        package_name: 游戏包名。
        apk_dir: 安装包下载目录。
        if_auto_install: 是否允许 MAS 自动下载并安装安装包。
        time_limit: 下载与安装的超时限制（分钟）。
        progress: 进度回调，用于向前端播报当前阶段。

    Returns:
        GameUpdateResult: 检查结果；``NeedManualUpdate`` 表示本次不应继续代理。
    """

    if adb_address in ("", "Unknown"):
        logger.warning("未取到模拟器 adb 地址，跳过游戏版本检查")
        return GameUpdateResult("Skipped", "未取到模拟器 adb 地址，跳过游戏版本检查")

    remote = await fetch_game_version(server)
    if remote is None:
        return GameUpdateResult("Skipped", f"服务器 {server} 无可用版本接口，跳过检查")

    installed = await get_installed_client_version(adb_path, adb_address, package_name)
    if installed is None:
        # 读不到已安装版本可能是游戏未安装，也可能是 adb 临时异常，
        # 一律不阻断本次代理，交回 MAA 原有流程判定
        return GameUpdateResult(
            "Skipped",
            "未能读取模拟器内的游戏版本，跳过更新检查",
            remote.resource,
        )

    if not is_client_outdated(installed, remote.client):
        return GameUpdateResult(
            "UpToDate", f"游戏客户端已是最新版本 {installed}", remote.resource
        )

    outdated_text = f"游戏客户端版本落后（已安装 {installed}，最新 {remote.client}）"
    logger.info(outdated_text)

    if server != "Official":
        return GameUpdateResult(
            "NeedManualUpdate",
            f"{outdated_text}，当前仅官服支持自动更新，请手动更新游戏后重试",
            remote.resource,
        )

    if not if_auto_install:
        return GameUpdateResult(
            "NeedManualUpdate",
            f"{outdated_text}，未开启自动安装，请手动更新游戏后重试",
            remote.resource,
        )

    apk_path = apk_dir / f"arknights-official-{remote.client}.apk"
    try:
        if progress is not None:
            await progress(f"{outdated_text}\n正在下载游戏安装包")
        await download_apk(
            ARKNIGHTS_OFFICIAL_APK_URL, apk_path, progress, timeout=time_limit * 60
        )

        if progress is not None:
            await progress(f"{outdated_text}\n正在安装游戏安装包")
        await install_apk(adb_path, adb_address, apk_path, timeout=time_limit * 60)
    except Exception as e:
        logger.opt(exception=True).warning(f"接管游戏更新失败: {e}")
        return GameUpdateResult(
            "NeedManualUpdate",
            f"{outdated_text}，MAS 自动更新失败（{e}），请手动更新游戏后重试",
            remote.resource,
        )
    finally:
        # 安装包体积很大，无论成败都不长期占用磁盘
        apk_path.unlink(missing_ok=True)

    current = await get_installed_client_version(adb_path, adb_address, package_name)
    if current is None or is_client_outdated(current, remote.client):
        return GameUpdateResult(
            "NeedManualUpdate",
            f"安装后版本仍未达到 {remote.client}（当前 {current or '未知'}），"
            "请手动更新游戏后重试",
            remote.resource,
        )

    return GameUpdateResult(
        "Updated", f"MAS 已将游戏客户端更新至 {current}", remote.resource
    )
