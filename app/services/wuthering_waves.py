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

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
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
_LAUNCHER_STATE_RELATIVE_PATH = Path("launcherDownloadConfig.json")

# 官方启动器的版本元数据入口。除这两个 URL 外不要硬编码任何 CDN 路径，
# 其余路径一律从接口返回的清单里取。
_OFFICIAL_UPDATE_API = {
    "官服": "https://prod-cn-alicdn-gamestarter.kurogame.com/launcher/game/G152/10003_Y8xXrXk65DqFHEDgApn3cpK5lfczpFx5/index.json",
    "国际服": "https://prod-alicdn-gamestarter.kurogame.com/launcher/game/G153/50004_obOHXFrFanqsaIEOmuKroCcbZkQRBC7c/index.json",
}


@dataclass(frozen=True)
class WutheringWavesLocalState:
    """`launcherDownloadConfig.json` 记录的本地安装状态。"""

    version: str
    state: str
    is_predownload: bool

    @property
    def is_idle(self) -> bool:
        """启动器是否已静止（无正在进行的下载或解压）。

        version 可能在下载途中就被写入，只有 state 为空且不处于预下载时，
        才代表该版本真正落盘可用。
        """

        return not self.state and not self.is_predownload


@dataclass(frozen=True)
class WutheringWavesUpdateInfo:
    """鸣潮官方启动器更新检查结果。"""

    install_dir: Path
    current_version: str
    release_version: str
    predownload_version: str | None
    update_available: bool
    predownload_available: bool
    api_url: str


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
        payload = json.loads(bytes(value ^ 0x63 for value in encrypted).decode("utf-8"))
    except (OSError, UnicodeError, ValueError) as e:
        raise ValueError("鸣潮启动器游戏路径记录无法解码，请重新导入启动器") from e

    install_dir = payload.get("installDirPath") if isinstance(payload, dict) else None
    if not isinstance(install_dir, str) or not install_dir.strip():
        raise ValueError("鸣潮启动器游戏路径记录缺少 installDirPath，请重新导入启动器")

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


def read_wuthering_waves_local_state(install_dir: Path) -> WutheringWavesLocalState:
    """读取本地安装状态。

    读不到时一律抛错，绝不退化成「已是最新」——否则会静默启动旧版客户端。

    Raises:
        FileNotFoundError: 版本记录不存在。
        ValueError: 版本记录无法解析或缺少 version 字段。
    """

    state_path = install_dir / _LAUNCHER_STATE_RELATIVE_PATH
    try:
        payload: Any = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"未找到鸣潮本地版本记录 {_LAUNCHER_STATE_RELATIVE_PATH}，"
            "请先用官方启动器完整安装一次游戏"
        ) from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("鸣潮本地版本记录无法读取，请重新导入启动器") from exc

    version = payload.get("version") if isinstance(payload, dict) else None
    version = str(version).strip() if version else ""
    if not version:
        raise ValueError("鸣潮本地版本记录缺少 version，请重新导入启动器")

    return WutheringWavesLocalState(
        version=version,
        state=str(payload.get("state") or "").strip(),
        is_predownload=bool(payload.get("isPreDownload")),
    )


def get_official_index_url(resource: str) -> str:
    """取指定服的版本元数据入口 URL。"""

    try:
        return _OFFICIAL_UPDATE_API[resource]
    except KeyError as exc:
        raise ValueError(f"不支持的鸣潮游戏资源: {resource}") from exc


def write_wuthering_waves_local_version(install_dir: Path, version: str) -> None:
    """把已装版本写回本地记录，保留启动器自己的其余字段。

    只应在所有文件都落盘成功后调用：这份记录就是"装到哪一版"的唯一凭据，
    提前写入会让中断后的下一轮误判为已完成。
    """

    state_path = install_dir / _LAUNCHER_STATE_RELATIVE_PATH
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload["version"] = version
    payload["state"] = ""
    payload["isPreDownload"] = False
    state_path.write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _version_key(version: str) -> tuple[int, ...]:
    """把版本号转成可比较元组，并抹掉尾部 0（使 3.6 与 3.6.0 等价）。"""

    values = [int(item) for item in re.findall(r"\d+", version)]
    while values and values[-1] == 0:
        values.pop()
    return tuple(values)


def _is_newer_version(candidate: str, current: str) -> bool:
    if not candidate or not current:
        return False
    return _version_key(candidate) > _version_key(current)


def _parse_update_payload(
    payload: Any,
    *,
    install_dir: Path,
    local_version: str,
    api_url: str,
) -> WutheringWavesUpdateInfo:
    """比对接口返回的版本元数据与本地版本。"""

    if not isinstance(payload, dict):
        raise ValueError("鸣潮官方更新接口返回格式错误")

    default_info = payload.get("default")
    if not isinstance(default_info, dict):
        raise ValueError("鸣潮官方更新接口缺少 default 版本信息")

    release_version = str(default_info.get("version") or "").strip()
    if not release_version:
        raise ValueError("鸣潮官方更新接口缺少 default.version")

    # 预下载段仅在预下载窗口期存在，平时整个键都不下发。
    predownload_info = payload.get("predownload")
    predownload_version = (
        str(predownload_info.get("version") or "").strip() or None
        if isinstance(predownload_info, dict)
        else None
    )
    predownload_enabled = payload.get("predownloadSwitch") in (True, 1, "1", "true")

    # 与官方启动器一致：只要版本号不等就需要更新，不假设官方只会升版本。
    update_available = release_version != local_version
    return WutheringWavesUpdateInfo(
        install_dir=install_dir,
        current_version=local_version,
        release_version=release_version,
        predownload_version=predownload_version,
        update_available=update_available,
        predownload_available=(
            predownload_enabled
            and not update_available
            and predownload_version is not None
            and _is_newer_version(predownload_version, local_version)
        ),
        api_url=api_url,
    )


async def check_wuthering_waves_update(
    launcher_path: Path,
    resource: str,
    *,
    timeout: float = 15.0,
) -> WutheringWavesUpdateInfo:
    """读取官方版本元数据，判断正式更新或预下载是否可用。

    MAS 只读版本元数据；包体下载、覆盖、校验全部仍由官方启动器负责。

    Args:
        launcher_path: 官方鸣潮启动器 `launcher.exe` 路径。
        resource: `官服` 或 `国际服`。
        timeout: HTTP 请求超时时间（秒）。

    Raises:
        ValueError: 资源名不支持、接口响应格式错误，或本地版本记录不可用。
        FileNotFoundError: 启动器或本地版本记录不存在。
        httpx.HTTPError: 官方接口请求失败。
    """

    try:
        api_url = _OFFICIAL_UPDATE_API[resource]
    except KeyError as exc:
        raise ValueError(f"不支持的鸣潮游戏资源: {resource}") from exc

    install_dir = resolve_wuthering_waves_install_dir(launcher_path)
    local_state = read_wuthering_waves_local_state(install_dir)

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

    result = _parse_update_payload(
        payload,
        install_dir=install_dir,
        local_version=local_state.version,
        api_url=api_url,
    )
    logger.info(
        "鸣潮更新检查: 本地={} (state={}), 正式={}, 预下载={}, 需更新={}, 可预下载={}",
        result.current_version,
        local_state.state or "-",
        result.release_version,
        result.predownload_version or "无",
        result.update_available,
        result.predownload_available,
    )
    return result
