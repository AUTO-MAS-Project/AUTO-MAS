#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025 MoeSnowyFox
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


import os
import re
import winreg
from maa.toolkit import Toolkit
from contextlib import suppress
from pathlib import Path
from typing import Dict, List, Optional, Set

from app.utils.constants import EMULATOR_PATH_BOOK
from app.utils import get_logger

logger = get_logger("模拟器管理工具")


def _normalize_fs_path_candidate(raw: str) -> str:
    """规整注册表/服务 ImagePath（如 \\??\\、\\?\\、\\SystemRoot）为本地路径。"""
    s = str(raw).strip().strip('"').strip("'")
    if not s:
        return ""
    # \??\C:\... ；\??\UNC\server\share\... 去掉前缀后 UNC 仍缺前导 \\，需补全
    if len(s) >= 4 and s.startswith("\\??\\"):
        rest = s[4:]
        ul = rest.upper()
        if ul.startswith("UNC\\"):
            rest = "\\\\" + rest[4:].lstrip("\\")
        s = rest
    # \\?\C:\... 扩展路径前缀（去掉 \\?\ 保留盘符路径）
    if s.startswith("\\\\?\\") and len(s) >= 7 and s[5] == ":":
        s = s[4:]
    # \SystemRoot\...（服务镜像偶见）
    sr = "\\SystemRoot"
    if s[: len(sr)].lower() == sr.lower() and (
        len(s) == len(sr) or s[len(sr) : len(sr) + 1] in ("\\", "/")
    ):
        root = os.environ.get("SystemRoot", r"C:\Windows").rstrip("\\/")
        s = root + s[len(sr) :]
    return s.strip()


def _resolved_primary_manager_key(corrected_path: str, config: Dict) -> Optional[str]:
    """若路径已解析为配置中的任一管理器 exe，返回 posix 路径键，否则 None。"""
    allowed = {x.lower() for x in (config.get("executables") or []) if x}
    if not allowed:
        return None
    corrected_obj = Path(corrected_path)
    if (
        corrected_obj.exists()
        and corrected_obj.is_file()
        and corrected_obj.name.lower() in allowed
    ):
        return corrected_obj.as_posix()
    return None


def _resolve_manager_dir_from_side_exe(
    path_obj: Path,
    emulator_type: str,
    executable_names: List[str],
    config_name: str,
    source: str,
) -> List[str]:
    """从旁路 exe（卸载/服务镜像等）反查配置中的管理器 exe 所在目录。"""
    if path_obj.suffix.lower() != ".exe":
        return []
    resolved = find_emulator_manager_path(str(path_obj), emulator_type)
    rp = Path(resolved)
    allowed = {x.lower() for x in executable_names}
    if rp.is_file() and rp.name.lower() in allowed:
        logger.info(f"{config_name} 通过{source}由旁路 exe 反查主管理器: {rp}")
        return [rp.parent.as_posix()]
    return []


# 注册表中常见的安装路径值名称（按优先级排列；已剪枝低覆盖项）
REGISTRY_INSTALL_VALUE_NAMES = (
    "InstallLocation",
    "InstallDir",
    "UninstallString",
    "ImagePath",
    "DisplayIcon",  # 兜底，模拟器卸载项多为 .ico，read_install_path 会跳过
)

# 值为安装目录/路径，可能含空格；勿走命令行 token 截断（如 C:\Program Files\...）
REGISTRY_DIRECTORY_VALUE_NAMES = frozenset(
    {
        "InstallLocation",
        "InstallDir",
    }
)

# MuMu 相对路径推断模式：从给定基准目录出发，按顺序拼接子路径直到 MuMuManager.exe
MUMU_RELATIVE_EXECUTABLE_PATTERNS = (
    ("MuMuManager.exe",),
    ("nx_main", "MuMuManager.exe"),
    ("shell", "MuMuManager.exe"),
    ("MuMu Player 12", "nx_main", "MuMuManager.exe"),
    ("MuMu", "nx_main", "MuMuManager.exe"),
)

# MuMu GameViewer 安装器跨盘符推断模式：安装器在 C 盘但主程序可能在 D/E 盘
MUMU_GAMEVIEWER_DRIVE_PATTERNS = (
    ("MuMuPlayer", "nx_main", "MuMuManager.exe"),
    ("Program Files", "Netease", "MuMu Player 12", "nx_main", "MuMuManager.exe"),
    (
        "Program Files (x86)",
        "Netease",
        "MuMu Player 12",
        "nx_main",
        "MuMuManager.exe",
    ),
    ("Program Files", "YXArkNights-12.0", "shell", "MuMuManager.exe"),
    ("Program Files", "YXReverse1999-12.0", "shell", "MuMuManager.exe"),
)


def search_all_emulators() -> List[Dict[str, str]]:
    """搜索所有支持的模拟器（全同步实现）。"""

    logger.info("开始搜索所有模拟器, mode=registry_plus_adb")
    found_emulators = []
    found_emulator_paths = set()

    # 根据可能的模拟器路径搜索
    for emulator_type, config in EMULATOR_PATH_BOOK.items():
        try:
            emulator_paths = _search_emulator(emulator_type, config)
            for emulator_path in emulator_paths:
                # 自动修正路径（与 ADB 分支一致：仅收录已定位到主管理器 exe 的项）
                corrected_path = find_emulator_manager_path(
                    emulator_path, emulator_type
                )
                corrected_key = _resolved_primary_manager_key(corrected_path, config)
                if not corrected_key:
                    continue
                if corrected_key not in found_emulator_paths:
                    found_emulator_paths.add(corrected_key)
                    found_emulators.append(
                        {
                            "type": emulator_type,
                            "path": corrected_key,
                            "name": f"{config['name']} ({corrected_key})",
                        }
                    )
                    logger.info(f"找到{config['name']}: {corrected_key}")
        except Exception as e:
            logger.warning(f"搜索{config['name']}时出错: {e}")

    for emulator in Toolkit.find_adb_devices():
        adb_path = emulator.adb_path
        adb_dir = adb_path.parent
        assigned = False
        for emulator_type, config in EMULATOR_PATH_BOOK.items():
            corrected_path = find_emulator_manager_path(
                adb_dir.as_posix(), emulator_type
            )
            corrected_key = _resolved_primary_manager_key(corrected_path, config)
            if corrected_key:
                if corrected_key not in found_emulator_paths:
                    found_emulator_paths.add(corrected_key)
                    found_emulators.append(
                        {
                            "type": emulator_type,
                            "path": corrected_key,
                            "name": f"{config['name']} ({corrected_key})",
                        }
                    )
                    logger.info(f"通过ADB找到{config['name']}: {corrected_key}")
                assigned = True
                break

        if assigned:
            continue

        general_path = adb_dir.as_posix()
        if general_path not in found_emulator_paths:
            found_emulator_paths.add(general_path)
            found_emulators.append(
                {
                    "type": "general",
                    "path": general_path,
                    "name": f"未知模拟器 ({general_path})",
                }
            )
            logger.info(f"通过ADB找到未知模拟器: {adb_path.as_posix()}")

    logger.info(f"搜索完成，共找到 {len(found_emulators)} 个模拟器")
    return found_emulators


def _search_emulator(emulator_type: str, config: Dict) -> List[str]:
    """搜索单类模拟器，返回找到的所有候选路径列表"""

    found_paths: List[str] = []

    # 将注册表路径分为厂商键和卸载表根键
    vendor_registry_paths = [
        path
        for path in config["registry_paths"]
        if "MICROSOFT\\WINDOWS\\CURRENTVERSION\\UNINSTALL" not in path.upper()
    ]
    uninstall_registry_paths = [
        path
        for path in config["registry_paths"]
        if "MICROSOFT\\WINDOWS\\CURRENTVERSION\\UNINSTALL" in path.upper()
    ]

    # 1. 厂商注册表键搜索
    registry_candidates = _search_from_registry(
        vendor_registry_paths,
        config.get("registry_display_keywords") or [],
    )
    for registry_path in registry_candidates:
        resolved_registry_paths = _resolve_emulator_install_paths(
            registry_path,
            config,
            emulator_type,
            source="registry",
        )
        found_paths.extend(resolved_registry_paths)

    # 2. 卸载表根键关键词匹配：兼容安装器写入路径不固定的场景，
    #    依赖后续"可执行文件存在"校验过滤噪声
    if uninstall_registry_paths:
        uninstall_candidates = _search_from_registry(
            uninstall_registry_paths,
            config.get("registry_display_keywords") or [],
        )
        for registry_path in uninstall_candidates:
            resolved_registry_paths = _resolve_emulator_install_paths(
                registry_path,
                config,
                emulator_type,
                source="registry_uninstall",
            )
            found_paths.extend(resolved_registry_paths)

    return _dedupe_path_strings(found_paths)


def _resolve_emulator_install_paths(
    candidate_path: str,
    config: Dict,
    emulator_type: str,
    source: str,
) -> List[str]:
    """将注册表/卸载表等来源路径解析为含主管理器 exe 的安装目录。"""

    if not candidate_path:
        return []

    candidate_path = _normalize_fs_path_candidate(candidate_path)
    if not candidate_path:
        return []

    path_obj = Path(candidate_path)
    if not path_obj.exists():
        return []

    results: List[str] = []
    executable_names = config["executables"]

    # 若输入本身就是目标可执行文件，直接使用其父目录
    if path_obj.is_file():
        if path_obj.name in executable_names:
            logger.info(f"{config['name']} 通过{source}命中可执行文件: {path_obj}")
            results.append(path_obj.parent.as_posix())
        elif emulator_type == "mumu" and path_obj.suffix.lower() == ".exe":
            # 旁路 exe：MuMuRemoteService.exe、游戏专版 uninstall.exe 等，从安装根推断 shell/nx_main
            for manager_path in _iter_mumu_manager_paths(path_obj.parent):
                if manager_path.exists():
                    logger.info(
                        f"{config['name']} 通过{source}由旁路 exe 推断主程序路径: {manager_path}"
                    )
                    results.append(manager_path.parent.as_posix())
        elif emulator_type in ("ldplayer", "nox", "bluestacks", "memu") and (
            path_obj.suffix.lower() == ".exe"
        ):
            results.extend(
                _resolve_manager_dir_from_side_exe(
                    path_obj,
                    emulator_type,
                    executable_names,
                    config["name"],
                    source,
                )
            )
        return _dedupe_path_strings(results)

    # 目录本身可直接校验的场景先走通用逻辑
    if _validate_emulator_path(str(path_obj), executable_names):
        logger.info(f"{config['name']} 通过{source}命中安装目录: {path_obj}")
        results.append(path_obj.as_posix())

    # MuMu 的安装器路径（如 GameViewer）与主程序目录分离，需要额外结构化推断
    if emulator_type == "mumu":
        for manager_path in _iter_mumu_manager_paths(path_obj):
            if manager_path.exists():
                logger.info(
                    f"{config['name']} 通过{source}推断主程序路径: {manager_path}"
                )
                results.append(manager_path.parent.as_posix())

    if not results:
        logger.debug(f"{config['name']} 通过{source}未解析到有效路径: {candidate_path}")
    return _dedupe_path_strings(results)


def _dedupe_path_strings(paths: List[str]) -> List[str]:
    """路径去重（大小写不敏感），保留首次出现的大小写"""
    dedup: List[str] = []
    seen: Set[str] = set()
    for path in paths:
        key = path.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(path)
    return dedup


def _safe_is_same_path(left: Path, right: Path) -> bool:
    """安全比较两个路径是否指向同一位置"""
    with suppress(OSError):
        return left.samefile(right)
    return left.resolve().as_posix().lower() == right.resolve().as_posix().lower()


def _iter_existing_drive_roots() -> List[Path]:
    """枚举存在的盘符根（A-Z），供 MuMu GameViewer 跨盘推断，非全盘扫描。"""
    roots: List[Path] = []
    for c in range(65, 91):  # A-Z
        root = Path(f"{chr(c)}:/")
        if root.exists():
            roots.append(root)
    return roots


def _iter_mumu_manager_paths(base_path: Path) -> List[Path]:
    """按 MuMu 常见目录结构生成主程序候选路径"""

    candidate_bases: List[Path] = [base_path]

    current = base_path
    for _ in range(2):
        parent = current.parent
        if parent == current:
            break
        candidate_bases.append(parent)
        current = parent

    candidates: List[Path] = []
    for candidate_base in candidate_bases:
        for pattern in MUMU_RELATIVE_EXECUTABLE_PATTERNS:
            candidates.append(candidate_base.joinpath(*pattern))

    # 若命中 GameViewer 安装器路径，进一步做跨盘符结构化推断
    if "gameviewer" in base_path.as_posix().lower():
        candidate_drive_roots: List[Path] = []
        current_drive_root = Path(base_path.anchor) if base_path.anchor else None
        if current_drive_root and current_drive_root.exists():
            candidate_drive_roots.append(current_drive_root)
        # 补齐跨盘安装的推断：仅枚举盘符根目录，不做递归扫描
        for drive_root in _iter_existing_drive_roots():
            if any(
                _safe_is_same_path(drive_root, existing)
                for existing in candidate_drive_roots
            ):
                continue
            candidate_drive_roots.append(drive_root)
        for drive_root in candidate_drive_roots:
            for pattern in MUMU_GAMEVIEWER_DRIVE_PATTERNS:
                candidates.append(drive_root.joinpath(*pattern))

    # 去重并保持顺序
    dedup: List[Path] = []
    seen: Set[str] = set()
    for candidate in candidates:
        key = candidate.as_posix().lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(candidate)
    return dedup


# 未加引号时，从命令行中提取「盘符:\...\文件名.扩展名」（贪婪，支持空格与 / 或 \）
_CMDLINE_PATH_WITH_EXT = re.compile(
    r"([A-Za-z]:[/\\](?:[^/\\:*?\"<>|\r\n]+[/\\])*[^/\\:*?\"<>|\r\n]+"
    r"\.(?:exe|cmd|bat|lnk|msi))(?:,\d+)?",
    re.IGNORECASE,
)


def _strip_icon_index_suffix(path: str) -> str:
    return re.sub(r",\d+\s*$", "", path).strip()


def _merge_unquoted_path_tokens(s: str) -> str:
    """无引号且路径含空格时，合并 token 直至拼成存在的文件路径。"""
    parts = s.split()
    if not parts:
        return ""
    if not re.match(r"^[A-Za-z]:[/\\]", parts[0]):
        return ""
    candidate = _strip_icon_index_suffix(parts[0])
    if Path(candidate).is_file():
        return candidate
    for extra in parts[1:]:
        if extra.startswith("/") or extra.startswith("-"):
            break
        trial = _strip_icon_index_suffix(f"{candidate} {extra}")
        if Path(trial).is_file():
            return trial
        candidate = f"{candidate} {extra}"
    final = _strip_icon_index_suffix(candidate)
    return final if Path(final).is_file() else ""


def _extract_path_from_command(value: str) -> str:
    """从注册表命令行字段抽取 exe/目录路径，并去掉图标索引尾缀（如 ,0）。"""

    if not value:
        return ""
    s = str(value).strip()
    if not s:
        return ""

    # 优先取第一个引号内片段
    m = re.match(r'^\s*"([^"]+)"', s)
    if m:
        extracted = _strip_icon_index_suffix(m.group(1).strip())
        return extracted

    # 未加引号：贪婪匹配带扩展名的 Windows 路径（含空格、正斜杠/反斜杠、.msi）
    m = _CMDLINE_PATH_WITH_EXT.search(s)
    if m:
        return _strip_icon_index_suffix(m.group(1).strip())

    merged = _merge_unquoted_path_tokens(s)
    if merged:
        return merged

    # 兜底：取第一个 token（到空格为止）
    token = _strip_icon_index_suffix(s.split(" ", 1)[0].strip())
    return token


def _search_from_registry(
    registry_paths: List[str],
    display_keywords: List[str] | None = None,
) -> List[str]:
    """从注册表搜索模拟器路径，返回所有找到的路径列表"""

    def iter_registry_paths(path: str):
        """在不改配置结构的前提下，兼容 WOW6432Node 视图路径"""
        yielded = set()
        candidates = [path]
        software_prefix = "SOFTWARE\\"
        wow_prefix = "SOFTWARE\\WOW6432Node\\"
        if path.upper().startswith(software_prefix) and not path.upper().startswith(
            wow_prefix
        ):
            candidates.append(path.replace(software_prefix, wow_prefix, 1))
        if path.upper().startswith(wow_prefix):
            candidates.append(path.replace(wow_prefix, software_prefix, 1))
        for candidate in candidates:
            key = candidate.upper()
            if key in yielded:
                continue
            yielded.add(key)
            yield candidate

    def read_install_path(key) -> str:
        """尝试多种常见的值名称读取安装路径"""
        for value_name in REGISTRY_INSTALL_VALUE_NAMES:
            with suppress(FileNotFoundError, OSError):
                value, _ = winreg.QueryValueEx(key, value_name)
                if isinstance(value, str) and value.strip():
                    raw = value.strip()
                    if value_name in REGISTRY_DIRECTORY_VALUE_NAMES:
                        path = raw.strip('"').strip("'")
                    else:
                        path = _extract_path_from_command(raw) or raw
                    if not path:
                        continue
                    # 卸载表常先命中 DisplayIcon（.ico），需继续尝试 UninstallString 等
                    if path.lower().endswith(".ico"):
                        continue
                    return path
        return ""

    def is_uninstall_root(path: str) -> bool:
        u = path.upper().rstrip("\\")
        return u.endswith(r"MICROSOFT\WINDOWS\CURRENTVERSION\UNINSTALL")

    def match_display_name(key) -> bool:
        """检查子键的 DisplayName 是否包含任一关键词"""
        if not display_keywords:
            return True
        with suppress(FileNotFoundError, OSError):
            name, _ = winreg.QueryValueEx(key, "DisplayName")
            if isinstance(name, str):
                n = name.lower()
                return any(k.lower() in n for k in display_keywords if k)
        return False

    found: List[str] = []
    seen: Set[str] = set()

    def add_path(p: str) -> None:
        if not p:
            return
        key = str(p).strip().lower()
        if not key or key in seen:
            return
        seen.add(key)
        found.append(str(p).strip())

    def collect_from_hive(hive: int, candidate_path: str) -> None:
        with suppress(FileNotFoundError, OSError):
            with winreg.OpenKey(hive, candidate_path) as key:
                if is_uninstall_root(candidate_path):
                    with suppress(OSError):
                        i = 0
                        while True:
                            sub = winreg.EnumKey(key, i)
                            i += 1
                            with suppress(FileNotFoundError, OSError):
                                with winreg.OpenKey(key, sub) as subkey:
                                    if not match_display_name(subkey):
                                        continue
                                    p = read_install_path(subkey)
                                    if p:
                                        add_path(p)
                    return

                install_path = read_install_path(key)
                if install_path:
                    add_path(install_path)

    for reg_path in registry_paths:
        for candidate_path in iter_registry_paths(reg_path):
            collect_from_hive(winreg.HKEY_LOCAL_MACHINE, candidate_path)
            collect_from_hive(winreg.HKEY_CURRENT_USER, candidate_path)

    return found


def _validate_emulator_path(path: str, executables: List[str]) -> bool:
    """验证模拟器路径是否有效"""

    if not path:
        return False

    path_obj = Path(path)
    if not path_obj.exists():
        return False

    # 检查当前目录是否直接包含任何可执行文件
    for executable in executables:
        if (path_obj / executable).exists():
            return True

    # 仅检查一级子目录(不递归)
    with suppress(PermissionError):
        for item in path_obj.iterdir():
            if item.is_dir():
                for executable in executables:
                    if (item / executable).exists():
                        return True

    return False


def find_emulator_manager_path(
    input_path: str, emulator_type: str, max_levels: int = 3
) -> str:
    """从给定路径搜索主管理器 exe 完整路径，未找到则返回原路径。"""

    if not input_path:
        logger.warning(f"输入路径无效: {input_path}")
        return input_path
    input_path_obj = Path(input_path)
    if not input_path_obj.exists():
        logger.warning(f"输入路径无效: {input_path}")
        return input_path

    # 获取模拟器配置信息
    if emulator_type not in EMULATOR_PATH_BOOK:
        logger.warning(f"不支持的模拟器类型: {emulator_type}")
        return input_path

    config = EMULATOR_PATH_BOOK[emulator_type]
    executables = config["executables"]

    path_obj = input_path_obj
    if path_obj.is_file():
        path_obj = path_obj.parent

    logger.info(
        f"开始搜索{config['name']}主管理器程序路径, 起始路径: {path_obj}, 候选: {executables}"
    )

    def first_existing_exe(base: Path) -> Optional[Path]:
        for exe in executables:
            candidate = base / exe
            if candidate.exists():
                return candidate
        return None

    hit = first_existing_exe(path_obj)
    if hit:
        result = str(hit)
        logger.info(f"当前目录直接包含主程序: {result}")
        return result

    candidates = []
    current = path_obj
    for level in range(max_levels):
        parent = current.parent
        if parent == current:
            break
        parent_hit = first_existing_exe(parent)
        if parent_hit:
            candidates.append(
                {"exe_path": parent_hit, "level": level + 1}
            )
            logger.debug(f"父目录(第{level+1}层)直接包含主程序: {parent_hit}")
        current = parent

    if candidates:
        candidates.sort(key=lambda x: x["level"])
        result = str(candidates[0]["exe_path"])
        logger.info(f"找到模拟器主程序(向上第{candidates[0]['level']}层): {result}")
        return result

    with suppress(PermissionError):
        for subdir in path_obj.iterdir():
            if subdir.is_dir():
                sub_hit = first_existing_exe(subdir)
                if sub_hit:
                    result = str(sub_hit)
                    logger.info(f"在子目录找到主程序: {result}")
                    return result

    if path_obj.parent != path_obj:
        with suppress(PermissionError):
            for sibling in path_obj.parent.iterdir():
                if sibling.is_dir() and sibling != path_obj:
                    sib_hit = first_existing_exe(sibling)
                    if sib_hit:
                        result = str(sib_hit)
                        logger.info(f"在兄弟目录找到主程序: {result}")
                        return result

    logger.warning(f"未能找到{config['name']}主程序，返回原路径: {input_path}")
    return input_path
