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
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import aiofiles
import httpx

from app.utils import get_logger, ProcessRunner
from app.utils.constants import (
    ARKNIGHTS_OFFICIAL_APK_URL,
    ARKNIGHTS_VERSION_API_SERVER,
)

logger = get_logger("MAA 游戏更新")

_VERSION_API = "https://ak-conf.hypergryph.com/config/prod/{server}/Android/version"
_VERSION_NAME_RE = re.compile(r"versionName=([\w.\-]+)")
_APK_MIN_BYTES = 64 * 1024 * 1024
"""安装包体积下限，低于此值判定为下载到错误内容（如跳转页 HTML）"""


@dataclass
class GameVersion:
    """服务端下发的游戏版本信息"""

    client: str
    """客户端版本号，形如 ``2.7.61``"""
    resource: str
    """资源版本号，形如 ``26-08-17-11-25-42_dbc172``"""


@dataclass
class GameUpdateResult:
    """游戏更新检查与接管的结果"""

    status: Literal["Skipped", "UpToDate", "Updated", "NeedManualUpdate"]
    """``Skipped`` 未执行检查；``UpToDate`` 无需更新；``Updated`` 已由 MAS 完成更新；
    ``NeedManualUpdate`` 需要用户手动更新，本次不应继续代理"""
    message: str
    """面向用户的说明文本"""
    resource_version: str = ""
    """服务端当前资源版本；为空表示未取到"""


async def _run_adb(
    adb_path: Path | None,
    adb_address: str,
    *args: str,
    timeout: float = 60,
) -> tuple[int, str]:
    """执行一条 adb 命令，返回 (返回码, 合并后的输出)。"""

    program: Path | str = adb_path if adb_path is not None else "adb"
    result = await ProcessRunner.run_process(
        program,
        "-s",
        adb_address,
        *args,
        timeout=timeout,
        if_merge_std=True,
    )
    return result.returncode, result.stdout.strip()


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


async def get_installed_client_version(
    adb_path: Path | None, adb_address: str, package_name: str
) -> str | None:
    """读取模拟器内已安装的客户端版本号。

    Returns:
        str | None: 版本号；游戏未安装或读取失败时返回 ``None``。
    """

    if ":" in adb_address:
        # host:port 形式的设备需要先建立连接，否则 -s 会找不到设备
        await _run_adb(adb_path, adb_address, "connect", adb_address, timeout=20)

    returncode, output = await _run_adb(
        adb_path,
        adb_address,
        "shell",
        "dumpsys",
        "package",
        package_name,
        timeout=30,
    )
    if returncode != 0:
        logger.warning(f"读取已安装版本失败: returncode={returncode}, output={output}")
        return None

    match = _VERSION_NAME_RE.search(output)
    if match is None:
        logger.info(f"未在模拟器中找到已安装的 {package_name}")
        return None

    version = match.group(1)
    logger.info(f"模拟器内 {package_name} 已安装版本: {version}")
    return version


def _parse_version(version: str) -> tuple[int, ...]:
    """把形如 ``2.7.61`` 的版本号解析为可比较的整数元组，无法解析的段落按 0 处理。"""

    parts: list[int] = []
    for segment in version.split("."):
        digits = re.match(r"\d+", segment.strip())
        parts.append(int(digits.group()) if digits else 0)
    return tuple(parts)


def is_client_outdated(installed: str, remote: str) -> bool:
    """判断已安装客户端是否落后于服务端版本。"""

    installed_parts = _parse_version(installed)
    remote_parts = _parse_version(remote)
    if not any(installed_parts) or not any(remote_parts):
        # 任一侧完全解析不出数字时不敢下判断，按未落后处理，交给 MAA 原有流程
        logger.warning(f"版本号无法比较: 已安装 {installed}, 服务端 {remote}")
        return False
    length = max(len(installed_parts), len(remote_parts))
    installed_parts += (0,) * (length - len(installed_parts))
    remote_parts += (0,) * (length - len(remote_parts))
    return installed_parts < remote_parts


async def download_official_apk(
    target_path: Path,
    progress: Callable[[str], Awaitable[None]] | None = None,
) -> Path:
    """下载官服安装包。

    Args:
        target_path: 安装包落盘路径。
        progress: 进度回调，用于向前端播报下载进度。

    Returns:
        Path: 下载完成的安装包路径。

    Raises:
        RuntimeError: 下载失败，或下载内容体积明显小于安装包（通常是拿到了跳转页）。
    """

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(f"{target_path.name}.downloading")
    temp_path.unlink(missing_ok=True)

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            async with client.stream(
                "GET", ARKNIGHTS_OFFICIAL_APK_URL, timeout=60.0
            ) as response:
                response.raise_for_status()
                total = int(response.headers.get("content-length", 0) or 0)

                if total and shutil.disk_usage(target_path.parent).free < total * 1.2:
                    raise RuntimeError(
                        f"磁盘剩余空间不足以下载安装包（需要约 {total / 1024**3:.1f} GB）"
                    )

                downloaded = 0
                next_report = 0
                async with aiofiles.open(temp_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        await f.write(chunk)
                        downloaded += len(chunk)

                        if progress is not None and downloaded >= next_report:
                            next_report = downloaded + 50 * 1024 * 1024
                            if total:
                                await progress(
                                    f"正在下载游戏安装包 "
                                    f"{downloaded / 1024**3:.2f}/{total / 1024**3:.2f} GB"
                                )
                            else:
                                await progress(
                                    f"正在下载游戏安装包 {downloaded / 1024**3:.2f} GB"
                                )

        if temp_path.stat().st_size < _APK_MIN_BYTES:
            raise RuntimeError(
                f"下载内容体积异常（{temp_path.stat().st_size} 字节），可能未取到真实安装包"
            )

        target_path.unlink(missing_ok=True)
        temp_path.replace(target_path)
        logger.success(f"游戏安装包下载完成: {target_path}")
        return target_path

    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


async def install_apk(
    adb_path: Path | None,
    adb_address: str,
    apk_path: Path,
    timeout: float,
) -> None:
    """通过 adb 安装安装包，保留应用数据。

    Raises:
        RuntimeError: 安装未成功。
    """

    logger.info(f"开始安装游戏安装包: {apk_path}")
    returncode, output = await _run_adb(
        adb_path,
        adb_address,
        "install",
        "-r",
        str(apk_path),
        timeout=timeout,
    )
    if returncode != 0 or "Success" not in output:
        raise RuntimeError(f"安装失败: returncode={returncode}, output={output}")

    logger.success("游戏安装包安装成功")


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
        await download_official_apk(apk_path, progress)

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
