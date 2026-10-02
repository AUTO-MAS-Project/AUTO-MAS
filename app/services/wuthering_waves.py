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


_CLIENT_RELATIVE_PATH = Path("Client/Binaries/Win64/Client-Win64-Shipping.exe")
_LAUNCHER_PREFERENCE_RELATIVE_PATH = Path("kr_game_cache/kr_game_temp.bin")
_LAUNCHER_STATE_RELATIVE_PATH = Path("launcherDownloadConfig.json")
_LAUNCHER_EXECUTABLE = "launcher.exe"
# 启动器记录不可用时，在启动器目录树下试的最大嵌套层数（安装目录是它的子目录）
_CLIENT_SEARCH_MAX_DEPTH = 2

# 官方启动器在注册表里登记的安装信息。只有一个值：启动器安装根，**没有**游戏
# 安装目录；键名形如 `KRLauncher\Aki_G152_default_10003`，含资源标识（G152=官服、
# G153=国际服），同机装了多个服时据此选，别认错用户实际用的那份。
_KURO_LAUNCHER_REGISTRY = r"Software\kurogame\KRLauncher"
_LAUNCHER_INSTALL_VALUE = "SingleLauncherInstallPath"
_LAUNCHER_RESOURCE_MARKS = {"官服": "g152", "国际服": "g153"}

# 卸载信息兜底：官方启动器实测不写卸载项，这里只覆盖会写的那种安装方式。
# 「名字」命中才认，免得把其它游戏的安装位置当成鸣潮。
_UNINSTALL_KEY_PATHS = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
)
_UNINSTALL_VALUE_NAMES = ("InstallLocation", "DisplayIcon", "UninstallString")
_UNINSTALL_NAME_TOKENS = ("鸣潮", "wuthering")

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


@dataclass(frozen=True)
class WutheringWavesFallback:
    """配置路径失效时的兜底定位结果，两者至多其一非空。"""

    launcher_path: Path | None = None
    process_path: Path | None = None


def _resources_install_dir(payload: Any) -> str:
    """从启动器记录的 `resources` 里取游戏安装目录（改版后的新位置）。

    旧记录的安装目录是顶层 `installDirPath`；新记录顶层只剩启动器偏好项，
    安装目录按 HD/UHD/SD 各记一条，且 `resources` 是「装着 JSON 的字符串」，
    要解两层。取不到一律返回空串——**绝不能放行成空 Path**，
    `Path("")` 是当前工作目录，更新链会照着它往盘上写。
    """

    if not isinstance(payload, dict):
        return ""
    value: Any = payload.get("resources")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return ""
    if not isinstance(value, list):
        return ""
    for item in value:
        install_dir = item.get("installDirPath") if isinstance(item, dict) else None
        if isinstance(install_dir, str) and install_dir.strip():
            return install_dir
    return ""


def _decode_official_launcher_install_dir(launcher_path: Path) -> Path:
    """Decode the official launcher's read-only game install metadata."""

    if launcher_path.name.lower() != _LAUNCHER_EXECUTABLE:
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
        # 启动器改版后顶层不再有 installDirPath，安装目录迁进了 resources
        install_dir = _resources_install_dir(payload)
    if not isinstance(install_dir, str) or not install_dir.strip():
        raise ValueError(
            "鸣潮启动器未记录游戏安装目录，"
            "请在「直接启动」下手动选择游戏客户端文件，或重新导入官方启动器"
        )

    return Path(install_dir)


def resolve_wuthering_waves_install_dir(launcher_path: Path) -> Path:
    """Resolve the game install directory recorded by the official launcher."""

    if not launcher_path.is_file():
        raise FileNotFoundError("鸣潮启动器不存在，请重新导入启动器")
    return _decode_official_launcher_install_dir(launcher_path)


def _registry_launcher_roots(resource: str) -> list[Path]:
    """官方启动器在注册表登记的安装根，同服优先。

    注册表里只有启动器安装根，**没有**游戏安装目录。键名含资源标识
    （G152=官服、G153=国际服），据此把用户实际用的那份排前面，避免同机多服时
    认错。
    """

    try:
        import winreg
    except ImportError:
        return []

    mark = _LAUNCHER_RESOURCE_MARKS.get(resource, "")
    matched: list[Path] = []
    others: list[Path] = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KURO_LAUNCHER_REGISTRY) as root:
            for index in range(winreg.QueryInfoKey(root)[0]):
                key_name = winreg.EnumKey(root, index)
                try:
                    with winreg.OpenKey(root, key_name) as entry:
                        install_root = str(
                            winreg.QueryValueEx(entry, _LAUNCHER_INSTALL_VALUE)[0]
                        ).strip()
                except OSError:
                    continue
                if not install_root:
                    continue
                target = matched if mark and mark in key_name.lower() else others
                target.append(Path(install_root))
    except OSError:
        return []
    return matched + others


def _is_wuthering_uninstall_entry(display_name: str, entry_name: str) -> bool:
    """卸载项是不是鸣潮的：只认名字命中，避免认成其它游戏。"""

    blob = f"{display_name} {entry_name}".casefold()
    return any(token in blob for token in _UNINSTALL_NAME_TOKENS)


def _uninstall_value_path(value: str) -> Path | None:
    """把卸载项里的写法还原成目录：可执行文件取其所在目录，目录原样取。"""

    text = value.strip().strip('"')
    if not text:
        return None
    # "C:\x\uninst.exe" / C:\x\uninst.exe,0 / C:\x\uninst.exe --arg
    executable = re.match(r'^"?([^"]+?\.exe)"?(?:\s|,|$)', text, re.IGNORECASE)
    if executable:
        directory = Path(executable.group(1).strip()).parent
        return directory if str(directory) not in ("", ".") else None
    path = Path(text.rstrip("\\/"))
    return path if path.is_absolute() else None


def _uninstall_launcher_roots() -> list[Path]:
    """Windows 卸载信息里疑似鸣潮的安装根。

    官方启动器实测**不写**卸载项（本机 221 条枚举零命中），这里覆盖的是会写的
    那种安装方式，属兜底的兜底。只认「名字」命中鸣潮的条目，免得把其它游戏的
    安装位置认成鸣潮；InstallLocation / DisplayIcon / UninstallString 都可能是
    安装根或根下的可执行文件，统一取所在目录作候选。
    """

    try:
        import winreg
    except ImportError:
        return []

    roots: list[Path] = []
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for key_path in _UNINSTALL_KEY_PATHS:
            try:
                with winreg.OpenKey(hive, key_path) as parent:
                    count = winreg.QueryInfoKey(parent)[0]
                    for index in range(count):
                        try:
                            entry_name = winreg.EnumKey(parent, index)
                            with winreg.OpenKey(parent, entry_name) as entry:
                                display_name = str(
                                    winreg.QueryValueEx(entry, "DisplayName")[0]
                                )
                                values = [
                                    str(winreg.QueryValueEx(entry, name)[0])
                                    for name in _UNINSTALL_VALUE_NAMES
                                ]
                        except OSError:
                            continue
                        if not _is_wuthering_uninstall_entry(display_name, entry_name):
                            continue
                        for value in values:
                            root = _uninstall_value_path(value)
                            if root is not None:
                                roots.append(root)
            except OSError:
                continue
    return roots


def discover_wuthering_waves_fallback(resource: str) -> WutheringWavesFallback:
    """配置的启动器路径失效时，按兜底来源找回启动器或客户端。

    来源优先级：注册表登记（官方启动器自己写的，最权威）→ Windows 卸载信息。
    候选根先认 ``launcher.exe``——有它就能复用启动器记录解出安装目录，更新链
    也一并可用；没有才在根下按约定路径搜客户端。两条都拿不到即返回空结果，
    由调用方决定报错文案。

    只回答「在哪」：不改配置，也不代表用户已确认，调用方必须把命中结果告知用户。

    Args:
        resource: ``官服`` 或 ``国际服``（用于同机多服时排序）。

    Returns:
        命中的启动器路径或客户端路径，两者至多其一非空。
    """

    candidates = [
        *((root, "注册表") for root in _registry_launcher_roots(resource)),
        *((root, "卸载信息") for root in _uninstall_launcher_roots()),
    ]
    seen: set[str] = set()
    for root, source in candidates:
        key = str(root).casefold()
        if key in seen:
            continue
        seen.add(key)
        launcher_path = root / _LAUNCHER_EXECUTABLE
        if launcher_path.is_file():
            logger.info(f"按{source}找回鸣潮启动器: {launcher_path}")
            return WutheringWavesFallback(launcher_path=launcher_path)
        process_path = _find_client_process_below(root)
        if process_path is not None:
            logger.info(f"按{source}找回鸣潮客户端: {process_path}")
            return WutheringWavesFallback(process_path=process_path)
    return WutheringWavesFallback()


def is_wuthering_waves_record_usable(launcher_path: Path) -> bool:
    """本地记录能否支撑启动前自动更新。

    更新检查依赖两份本地记录：启动器记录解出的安装目录，与该目录下的
    ``launcherDownloadConfig.json``（缺一即无法判断版本）。客户端 exe 有
    目录搜索兜底，更新没有——记录读不出来时启动照跑、更新无从下手，
    调用方据此决定要不要提示用户，别让更新静默停掉。
    """

    try:
        install_dir = resolve_wuthering_waves_install_dir(launcher_path)
        read_wuthering_waves_local_state(install_dir)
    except (FileNotFoundError, ValueError):
        return False
    return True


def _decode_official_launcher_process_path(launcher_path: Path) -> Path:
    install_dir = _decode_official_launcher_install_dir(launcher_path)
    process_path = install_dir / _CLIENT_RELATIVE_PATH
    if not process_path.is_file():
        raise FileNotFoundError(
            "启动器记录的鸣潮客户端不存在，请确认游戏已安装，"
            "或在「直接启动」下手动选择游戏客户端文件"
        )
    return process_path


def _find_client_process_below(root: Path) -> Path | None:
    """在启动器目录树下按有限深度找鸣潮客户端 exe。

    安装目录是启动器目录的子目录（实测 `launcher.exe` 同级还套着一层
    `Wuthering Waves Game`），记录不可用时靠它自愈；只按约定相对路径
    逐层试，不做整树遍历。
    """

    for depth in range(_CLIENT_SEARCH_MAX_DEPTH + 1):
        pattern = "/".join(["*"] * depth + [_CLIENT_RELATIVE_PATH.as_posix()])
        for candidate in sorted(root.glob(pattern)):
            if candidate.is_file():
                return candidate
    return None


def resolve_wuthering_waves_process_path(launcher_path: Path) -> Path:
    """Resolve the game process exe without reading or modifying game resources.

    记录解不出安装目录时退回目录搜索：上游改过记录结构，改版期整批用户会同时
    失去启动能力，而「重新导入启动器」修不了记录内容。搜索只服务启动、已运行
    检测与收尾，**不进更新链**——更新要往安装目录写盘，不允许猜。
    """

    if not launcher_path.is_file():
        raise FileNotFoundError("鸣潮启动器不存在，请重新导入启动器")
    try:
        return _decode_official_launcher_process_path(launcher_path)
    except (FileNotFoundError, ValueError) as e:
        if launcher_path.name.lower() != _LAUNCHER_EXECUTABLE:
            # 选错文件是配置错误，要原样报出去，别靠目录搜索掩盖
            raise
        process_path = _find_client_process_below(launcher_path.parent)
        if process_path is None:
            # 记录的问题用户自己修不了，别把上游「重新导入启动器」的旧文案转出去；
            # 原始原因留在日志与异常链里
            logger.warning(f"鸣潮启动器记录不可用且未搜索到客户端: {e}")
            raise FileNotFoundError(
                "未找到鸣潮客户端程序：请确认游戏已安装，"
                "或在「直接启动」下手动选择游戏客户端文件"
            ) from e
        logger.warning(f"鸣潮启动器记录不可用，已按目录搜索定位客户端: {process_path}")
        return process_path


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
    state_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _version_key(version: str) -> tuple[int, ...]:
    """把版本号转成可比较元组，并抹掉尾部 0（使 3.6 与 3.6.0 等价）。"""

    values = [int(item) for item in re.findall(r"\d+", version)]
    while values and values[-1] == 0:
        values.pop()
    return tuple(values)


def _is_newer_version(candidate: str, current: str) -> bool:
    """candidate 是否比 current 新。

    不对空值做特判：`_version_key("")` 为空元组，于是本地版本未知时
    任何有效版本都判为更新，方向是安全的。若在此静默返回 False，
    未来新增调用点就会把"查不到版本"误当成"已是最新"。
    """

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
