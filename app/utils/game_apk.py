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

"""模拟器层面的游戏客户端 APK 更新公共原语。

模块只提供与具体游戏无关的能力：通过 adb 读取/安装客户端、版本比较、
流式下载安装包。各专项（MAA / SRC 等）自行对接各自游戏的版本接口与
下载入口后调用本模块完成"检查版本 → 下载 → 安装"的编排。
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin

import aiofiles
import httpx

from app.utils import ProcessRunner, get_logger

logger = get_logger("游戏 APK 更新")

APK_MIN_BYTES = 64 * 1024 * 1024
"""安装包体积下限，低于此值判定为下载到错误内容（如跳转页 HTML）"""

_VERSION_NAME_RE = re.compile(r"versionName=([\w.\-]+)")


@dataclass
class GameUpdateResult:
    """游戏更新检查与接管的结果"""

    status: Literal["Skipped", "UpToDate", "Updated", "NeedManualUpdate"]
    """``Skipped`` 未执行检查；``UpToDate`` 无需更新；``Updated`` 已由 MAS 完成更新；
    ``NeedManualUpdate`` 需要用户手动更新，本次不应继续代理"""
    message: str
    """面向用户的说明文本"""
    resource_version: str = ""
    """可选的服务端资源版本号；仅部分游戏提供（如明日方舟用于识别待下载的资源热更新），
    未提供时为空字符串"""


async def run_adb(
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


async def get_installed_client_version(
    adb_path: Path | None, adb_address: str, package_name: str
) -> str | None:
    """读取模拟器内已安装的客户端版本号。

    Returns:
        str | None: 版本号；游戏未安装或读取失败时返回 ``None``。
    """

    if ":" in adb_address:
        # host:port 形式的设备需要先建立连接，否则 -s 会找不到设备
        await run_adb(adb_path, adb_address, "connect", adb_address, timeout=20)

    returncode, output = await run_adb(
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


def parse_version(version: str) -> tuple[int, ...]:
    """把形如 ``2.7.61`` 的版本号解析为可比较的整数元组，无法解析的段落按 0 处理。"""

    parts: list[int] = []
    for segment in version.split("."):
        digits = re.match(r"\d+", segment.strip())
        parts.append(int(digits.group()) if digits else 0)
    return tuple(parts)


def is_client_outdated(installed: str, remote: str) -> bool:
    """判断已安装客户端是否落后于服务端版本。"""

    installed_parts = parse_version(installed)
    remote_parts = parse_version(remote)
    if not any(installed_parts) or not any(remote_parts):
        # 任一侧完全解析不出数字时不敢下判断，按未落后处理，交给上游原有流程
        logger.warning(f"版本号无法比较: 已安装 {installed}, 服务端 {remote}")
        return False
    length = max(len(installed_parts), len(remote_parts))
    installed_parts += (0,) * (length - len(installed_parts))
    remote_parts += (0,) * (length - len(remote_parts))
    return installed_parts < remote_parts


_VERSION_IN_NAME_RE = re.compile(r"(\d+(?:\.\d+)+)")
"""从下载地址的文件名中匹配版本号，形如 ``StarRail_4.5.0.apk``；
文件名以版本号开头时同样可匹配"""


async def resolve_download_link(url: str) -> tuple[str, str] | None:
    """跟随重定向取真实下载地址，并从文件名解析出客户端版本号。

    各游戏的下载入口多为 302 跳转，最终地址的文件名里通常就带着客户端版本号。
    由此取到的版本与将下载的安装包必然同源同版本，不会出现"版本接口与安装包
    版本不一致"的情况（例如 PC 启动器包与安卓 APK 本就不同步）。

    Args:
        url: 下载入口（302 跳转至 CDN 真实地址）。

    Returns:
        tuple[str, str] | None: ``(最终地址, 版本号)``；未发生跳转、请求失败或
        解析不出版本号时返回 ``None``。
    """

    try:
        async with httpx.AsyncClient(follow_redirects=False) as client:
            response = await client.get(url, timeout=15.0)
            location = response.headers.get("location")
    except Exception as e:
        logger.warning(f"解析下载地址失败: {e}")
        return None

    if not location:
        logger.warning(f"下载入口未返回重定向地址: {url}")
        return None

    # 入口可能给出相对地址，按入口本身补全
    final_url = urljoin(str(response.request.url), location)

    match = _VERSION_IN_NAME_RE.search(final_url.rsplit("/", 1)[-1])
    if match is None:
        logger.warning(f"未能从下载地址解析出版本号: {final_url}")
        return None

    logger.info(f"解析到下载地址 {final_url}，客户端版本 {match.group(1)}")
    return final_url, match.group(1)


async def download_apk(
    url: str,
    target_path: Path,
    progress: Callable[[str], Awaitable[None]] | None = None,
) -> Path:
    """下载安装包。

    Args:
        url: 安装包下载入口（允许重定向到真实下载地址）。
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
                "GET", url, timeout=60.0
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

        if temp_path.stat().st_size < APK_MIN_BYTES:
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
    returncode, output = await run_adb(
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
