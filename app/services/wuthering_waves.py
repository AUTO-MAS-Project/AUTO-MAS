#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

import asyncio
import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any

import httpx

from app.utils import get_logger


logger = get_logger("鸣潮更新检查")


_CLIENT_RELATIVE_PATH = Path(
    "Client/Binaries/Win64/Client-Win64-Shipping.exe"
)
_LAUNCHER_PREFERENCE_RELATIVE_PATH = Path(
    "kr_game_cache/kr_game_temp.bin"
)
_LAUNCHER_VERSION_RELATIVE_PATH = Path("launcherDownloadConfig.json")
_UPDATE_WAIT_INTERVAL = 5.0
_UPDATE_WAIT_TIMEOUT = 6 * 60 * 60

# 官方启动器使用的游戏渠道配置。接口返回的 default 是正式版本，
# predownload 是预下载版本；两者都由启动器负责实际下载和校验。
_OFFICIAL_UPDATE_API = {
    "官服": "https://prod-cn-alicdn-gamestarter.kurogame.com/launcher/game/G152/10003_Y8xXrXk65DqFHEDgApn3cpK5lfczpFx5/index.json",
    "国际服": "https://prod-alicdn-gamestarter.kurogame.com/launcher/game/G153/50004_obOHXFrFanqsaIEOmuKroCcbZkQRBC7c/index.json",
}


@dataclass(frozen=True)
class WutheringWavesUpdateInfo:
    """鸣潮官方启动器更新检查结果。"""

    current_version: str | None
    release_version: str | None
    predownload_version: str | None
    update_available: bool
    predownload_available: bool
    api_url: str

    @property
    def should_start_launcher(self) -> bool:
        """是否需要启动官方启动器处理更新或预下载。"""

        return self.update_available or self.predownload_available


def _decode_official_launcher_install_dir(launcher_path: Path) -> Path:
    """Decode the official launcher's read-only game install metadata."""

    if launcher_path.name.lower() != "launcher.exe":
        raise ValueError("请选择鸣潮官方启动器 launcher.exe")

    preference_path = launcher_path.parent / _LAUNCHER_PREFERENCE_RELATIVE_PATH
    if not preference_path.is_file():
        raise FileNotFoundError(
            "未找到鸣潮启动器的游戏路径记录，请重新导入正确的官方启动器"
        )
    try:
        encoded = preference_path.read_text(encoding="ascii").strip()
        encrypted = base64.b64decode(encoded, validate=True)
        payload = json.loads(
            bytes(value ^ 0x63 for value in encrypted).decode("utf-8")
        )
    except (OSError, UnicodeError, ValueError) as e:
        raise ValueError("鸣潮启动器游戏路径记录无法解码，请重新导入启动器") from e

    install_dir = payload.get("installDirPath") if isinstance(payload, dict) else None
    if not isinstance(install_dir, str) or not install_dir.strip():
        raise ValueError(
            "鸣潮启动器游戏路径记录缺少 installDirPath，请重新导入启动器"
        )

    return Path(install_dir)


def resolve_wuthering_waves_install_dir(launcher_path: Path) -> Path:
    """Resolve the game install directory recorded by the official launcher."""

    if not launcher_path.is_file():
        raise FileNotFoundError("鸣潮启动器不存在，请重新导入启动器")
    return _decode_official_launcher_install_dir(launcher_path)


def _decode_official_launcher_process_path(launcher_path: Path) -> Path:
    install_dir = _decode_official_launcher_install_dir(launcher_path)
    process_path = install_dir / _CLIENT_RELATIVE_PATH
    if not process_path.is_file():
        raise FileNotFoundError(
            "启动器记录的鸣潮客户端不存在，请确认游戏已安装后重新导入启动器"
        )
    return process_path


def resolve_wuthering_waves_process_path(launcher_path: Path) -> Path:
    """Resolve the game process exe without reading or modifying game resources."""

    if not launcher_path.is_file():
        raise FileNotFoundError("鸣潮启动器不存在，请重新导入启动器")
    return _decode_official_launcher_process_path(launcher_path)


def _read_local_wuthering_waves_version(launcher_path: Path) -> str | None:
    version_path = (
        resolve_wuthering_waves_install_dir(launcher_path)
        / _LAUNCHER_VERSION_RELATIVE_PATH
    )
    if not version_path.is_file():
        return None

    try:
        payload: Any = json.loads(version_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("鸣潮本地版本记录无法读取，请重新导入启动器") from exc
    version = payload.get("version") if isinstance(payload, dict) else None
    return str(version).strip() if version else None


def _version_key(version: str | None) -> tuple[int, ...]:
    values = [int(item) for item in re.findall(r"\d+", version or "")]
    while values and values[-1] == 0:
        values.pop()
    return tuple(values)


def _is_newer_version(candidate: str | None, current: str | None) -> bool:
    if not candidate or not current:
        return False
    return _version_key(candidate) > _version_key(current)


async def wait_wuthering_waves_update(
    launcher_path: Path,
    target_version: str,
    *,
    interval: float = _UPDATE_WAIT_INTERVAL,
    timeout: float = _UPDATE_WAIT_TIMEOUT,
) -> None:
    """等待官方启动器完成更新和解压。"""

    if not target_version:
        raise ValueError("鸣潮官方更新缺少目标版本")

    deadline = monotonic() + timeout
    while True:
        try:
            current_version = _read_local_wuthering_waves_version(launcher_path)
        except (OSError, ValueError) as exc:
            # 启动器写入版本文件时可能短暂占用文件，继续等待下一轮读取。
            logger.debug("读取鸣潮本地版本记录失败，继续等待: {}", exc)
            current_version = None
        if current_version and not _is_newer_version(target_version, current_version):
            logger.info("鸣潮官方启动器更新完成: {}", current_version)
            return
        if monotonic() >= deadline:
            raise TimeoutError(
                f"鸣潮官方启动器更新超过 {int(timeout // 3600)} 小时仍未完成"
            )
        await asyncio.sleep(interval)


async def check_wuthering_waves_update(
    launcher_path: Path,
    resource: str,
    *,
    timeout: float = 15.0,
) -> WutheringWavesUpdateInfo:
    """读取官方启动器接口，判断正式更新或预下载是否可用。

    MAS 只读取版本元数据；包体下载、覆盖、校验和最终结果全部交给官方启动器。

    Args:
        launcher_path: 官方鸣潮启动器 `launcher.exe` 路径。
        resource: `官服` 或 `国际服`。
        timeout: HTTP 请求超时时间（秒）。

    Returns:
        WutheringWavesUpdateInfo: 当前版本与官方版本比较结果。

    Raises:
        ValueError: 启动器资源或接口响应格式不受支持。
        httpx.HTTPError: 官方接口请求失败。
    """

    try:
        api_url = _OFFICIAL_UPDATE_API[resource]
    except KeyError as exc:
        raise ValueError(f"不支持的鸣潮游戏资源: {resource}") from exc

    current_version = _read_local_wuthering_waves_version(launcher_path)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(
            api_url,
            headers={
                "User-Agent": "AUTO-MAS/okww",
                "Accept": "application/json",
            },
        )
        response.raise_for_status()
        payload: Any = response.json()

    if not isinstance(payload, dict):
        raise ValueError("鸣潮官方更新接口返回格式错误")

    default_info = payload.get("default")
    predownload_info = payload.get("predownload")
    if not isinstance(default_info, dict):
        raise ValueError("鸣潮官方更新接口缺少 default 版本信息")

    release_version = str(default_info.get("version") or "").strip() or None
    predownload_version = (
        str(predownload_info.get("version") or "").strip()
        if isinstance(predownload_info, dict)
        else None
    ) or None
    predownload_switch = payload.get("predownloadSwitch")
    predownload_enabled = predownload_switch in (True, 1, "1", "true")

    result = WutheringWavesUpdateInfo(
        current_version=current_version,
        release_version=release_version,
        predownload_version=predownload_version,
        update_available=_is_newer_version(release_version, current_version),
        predownload_available=predownload_enabled
        and _is_newer_version(predownload_version, current_version)
        and not _is_newer_version(release_version, current_version),
        api_url=api_url,
    )
    logger.info(
        "鸣潮更新检查: 本地={}, 正式={}, 预下载={}, 更新={}, 预下载={}",
        result.current_version or "未知",
        result.release_version or "未知",
        result.predownload_version or "无",
        result.update_available,
        result.predownload_available,
    )
    return result
