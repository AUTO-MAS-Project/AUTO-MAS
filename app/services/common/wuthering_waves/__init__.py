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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.utils import UnsupportedPlatformError, get_logger, registry

logger = get_logger("鸣潮启动器")


_CLIENT_RELATIVE_PATH = Path("Client/Binaries/Win64/Client-Win64-Shipping.exe")
_LAUNCHER_PREFERENCE_RELATIVE_PATH = Path("kr_game_cache/kr_game_temp.bin")
_LAUNCHER_SELECTION_RELATIVE_PATH = Path("kr_game_cache/platform_ui_state.bin")
_LAUNCHER_EXECUTABLE = "launcher.exe"
# 启动器记录不可用时，在启动器目录树下试的最大嵌套层数（安装目录是它的子目录）
_CLIENT_SEARCH_MAX_DEPTH = 2

# 官方启动器在注册表里登记的安装信息。只有一个值：启动器安装根，**没有**游戏
# 安装目录；键名形如 `KRLauncher\Aki_G152_default_10003`，含资源标识（G152=官服、
# G153=国际服），同机装了多个服时据此选，别认错用户实际用的那份。
_KURO_LAUNCHER_REGISTRY = r"Software\kurogame\KRLauncher"
_LAUNCHER_INSTALL_VALUE = "SingleLauncherInstallPath"
_LAUNCHER_RESOURCE_MARKS = {"官服": "g152", "国际服": "g153"}


class _LauncherSelectionError(ValueError):
    """启动器已明确选择游戏或档位，不能靠目录搜索回退。"""


@dataclass(frozen=True)
class WutheringWavesFallback:
    """配置路径失效时的兜底定位结果，两者至多其一非空。"""

    launcher_path: Path | None = None
    process_path: Path | None = None


def read_wuthering_waves_launcher_selection(launcher_path: Path) -> str | None:
    """读取官方启动器当前选中的鸣潮画质；旧启动器没有平台记录时返回 None。"""
    state_path = launcher_path.parent / _LAUNCHER_SELECTION_RELATIVE_PATH
    message = "请在官方启动器中选择鸣潮及 SD、HD 或 UHD 资源档位后重试"
    try:
        encoded = state_path.read_bytes().strip()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise _LauncherSelectionError(message) from exc
    try:
        encrypted = base64.b64decode(encoded, validate=True)
        payload = json.loads(
            bytes(value ^ 0x63 for value in encrypted).decode("utf-8-sig")
        )
    except (ValueError, UnicodeError) as exc:
        raise _LauncherSelectionError(message) from exc
    active = payload.get("activeGameScope") if isinstance(payload, dict) else None
    if not isinstance(active, dict) or active.get("gameIdentity") != "Aki":
        raise _LauncherSelectionError(message)
    bundle = active.get("bundleName")
    if not isinstance(bundle, str) or bundle.lower() not in ("sd", "hd", "uhd"):
        raise _LauncherSelectionError(message)
    return bundle.lower()


def _resources_install_dir(payload: Any, bundle: str | None = None) -> str:
    """从启动器记录的 `resources` 里取游戏安装目录（改版后的新位置）。

    旧记录的安装目录是顶层 `installDirPath`；新记录顶层只剩启动器偏好项，
    安装目录按 HD/UHD/SD 各记一条，且 `resources` 是「装着 JSON 的字符串」，
    要解两层。有当前档位及档位绑定时只选对应记录；旧记录多条目录优先取
    仍有客户端的目录，避免旧画质绑定已移走。
    明确选择的档位没有目录时抛错，其余取不到返回空串，避免把当前工作
    目录 `Path("")` 当成有效游戏安装。
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
    if bundle is not None:
        bound = [
            item
            for item in value
            if isinstance(item, dict)
            and isinstance(item.get("bundleName"), str)
            and item["bundleName"]
        ]
        if not bound:
            return ""
        value = [item for item in bound if item["bundleName"].lower() == bundle]
    first_install_dir = ""
    for item in value:
        install_dir = item.get("installDirPath") if isinstance(item, dict) else None
        if isinstance(install_dir, str) and install_dir.strip():
            if not first_install_dir:
                first_install_dir = install_dir
            if (Path(install_dir) / _CLIENT_RELATIVE_PATH).is_file():
                return install_dir
    if bundle is not None and not first_install_dir:
        raise _LauncherSelectionError(
            f"官方启动器未记录当前 {bundle.upper()} 档位的游戏安装目录，"
            "请在启动器中确认该档位已安装"
        )
    return first_install_dir


def _decode_official_launcher_install_dir(
    launcher_path: Path, *, require_client: bool = False
) -> Path:
    """Decode the official launcher's read-only game install metadata."""

    if launcher_path.name.lower() != _LAUNCHER_EXECUTABLE:
        raise ValueError("请选择鸣潮官方启动器 launcher.exe")

    bundle = read_wuthering_waves_launcher_selection(launcher_path)
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

    if bundle is not None:
        bound_install_dir = _resources_install_dir(payload, bundle)
        if bound_install_dir:
            selected_dir = Path(bound_install_dir)
            if require_client and not (selected_dir / _CLIENT_RELATIVE_PATH).is_file():
                raise _LauncherSelectionError(
                    f"官方启动器当前 {bundle.upper()} 档位的鸣潮客户端不存在，"
                    "请在启动器中确认该档位已安装"
                )
            return selected_dir

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

    mark = _LAUNCHER_RESOURCE_MARKS.get(resource, "")
    matched: list[Path] = []
    others: list[Path] = []
    try:
        entries = registry.user_subkey_values(
            _KURO_LAUNCHER_REGISTRY, _LAUNCHER_INSTALL_VALUE
        )
        for key_name, value in entries:
            install_root = value.strip()
            if not install_root:
                continue
            target = matched if mark and mark in key_name.lower() else others
            target.append(Path(install_root))
    except (OSError, UnsupportedPlatformError):
        return []
    return matched + others


def discover_wuthering_waves_fallback(resource: str) -> WutheringWavesFallback:
    """配置的启动器路径失效时，从注册表找回官方启动器或客户端。

    注册表里只有启动器安装根，**没有**游戏安装目录：命中后仍要靠启动器自己的
    记录或目录搜索定位游戏，所以它只解决「配置的启动器路径不可用」。候选根先认
    ``launcher.exe``——有它就能复用启动器记录解出安装目录，更新链也一并可用；
    没有才在根下按约定路径搜客户端（启动器被删、游戏还在的情形）。拿不到即返回
    空结果，由调用方决定报错文案。

    只回答「在哪」：不改配置，也不代表用户已确认，调用方必须把命中结果告知用户。

    Args:
        resource: ``官服`` 或 ``国际服``（用于同机多服时排序）。

    Returns:
        命中的启动器路径或客户端路径，两者至多其一非空。
    """

    seen: set[str] = set()
    client_candidate: Path | None = None
    for root in _registry_launcher_roots(resource):
        key = str(root).casefold()
        if key in seen:
            continue
        seen.add(key)
        launcher_path = root / _LAUNCHER_EXECUTABLE
        if launcher_path.is_file():
            logger.info(f"按注册表找回鸣潮启动器: {launcher_path}")
            return WutheringWavesFallback(launcher_path=launcher_path)
        process_path = _find_client_process_below(root)
        if process_path is not None and client_candidate is None:
            # 继续找启动器：启动器模式不能因前一个根只找到客户端而提前失败。
            client_candidate = process_path
    if client_candidate is not None:
        logger.info(f"按注册表找回鸣潮客户端: {client_candidate}")
    return WutheringWavesFallback(process_path=client_candidate)


def _decode_official_launcher_process_path(launcher_path: Path) -> Path:
    install_dir = _decode_official_launcher_install_dir(
        launcher_path, require_client=True
    )
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
    except _LauncherSelectionError:
        raise
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
