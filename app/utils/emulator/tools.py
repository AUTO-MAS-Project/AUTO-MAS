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


import shutil
import re
import winreg
from maa.toolkit import Toolkit
from contextlib import suppress
from pathlib import Path
from typing import List, Dict, Set

from app.utils.constants import EMULATOR_PATH_BOOK
from app.utils import get_logger

logger = get_logger("模拟器管理工具")

EXECUTABLE_EXTENSIONS = {".exe", ".bat", ".cmd"}
REGISTRY_INSTALL_VALUE_NAMES = (
    "InstallPath",
    "InstallLocation",
    "InstallDir",
    "instDir",
    "install_dir",
    "Path",
    "DataDir",
    "DisplayIcon",
    "UninstallString",
    "QuietUninstallString",
    "ImagePath",
)
MUMU_EXECUTABLES = ("MuMuManager.exe",)
MUMU_RELATIVE_EXECUTABLE_PATTERNS = (
    ("MuMuManager.exe",),
    ("nx_main", "MuMuManager.exe"),
    ("shell", "MuMuManager.exe"),
    ("MuMu Player 12", "nx_main", "MuMuManager.exe"),
    ("MuMu", "nx_main", "MuMuManager.exe"),
)
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


async def search_all_emulators(include_full_scan: bool = False) -> List[Dict[str, str]]:
    """搜索所有支持的模拟器"""

    # 历史版本存在全盘扫描/进度轮询，这里已完全移除，仅保留快速搜索。
    # include_full_scan 参数仅为接口兼容保留，不再触发任何扫描模式。
    if include_full_scan:
        logger.info("include_full_scan 参数已忽略（全盘扫描流程已移除）")
    logger.info("开始搜索所有模拟器, mode=quick_search")
    found_emulators = []
    found_emulator_paths = set()

    # 兼容主流模拟器：注册表（厂商键 + 卸载表关键词）→ 默认路径 → 系统 PATH → ADB 兜底。
    for emulator_type, config in EMULATOR_PATH_BOOK.items():
        try:
            emulator_paths = _search_emulator(config)
            for emulator_path in emulator_paths:
                # 自动修正路径
                corrected_path = find_emulator_manager_path(emulator_path, emulator_type)
                if corrected_path not in found_emulator_paths:
                    found_emulator_paths.add(corrected_path)
                    found_emulators.append(
                        {
                            "type": emulator_type,
                            "path": corrected_path,
                            "name": f"{config['name']} ({corrected_path})",
                        }
                    )
                    logger.info(f"找到{config['name']}: {corrected_path}")
        except Exception as e:
            logger.warning(f"搜索{config['name']}时出错: {e}")

    # ADB 兜底：尽量在“可验证主程序存在”的前提下归类；否则标记为 general。
    for emulator in Toolkit.find_adb_devices():
        adb_path = emulator.adb_path
        adb_dir = adb_path.parent
        assigned = False
        for emulator_type, config in EMULATOR_PATH_BOOK.items():
            primary_exe = config["executables"][0] if config.get("executables") else ""
            if not primary_exe:
                continue
            corrected_path = find_emulator_manager_path(adb_dir.as_posix(), emulator_type)
            corrected_obj = Path(corrected_path)
            if corrected_obj.exists() and corrected_obj.is_file() and corrected_obj.name == primary_exe:
                corrected_key = corrected_obj.as_posix()
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


def _search_emulator(config: Dict) -> List[str]:
    """搜索单类模拟器"""
    emulator_type = "general"
    for et, cfg in EMULATOR_PATH_BOOK.items():
        if cfg is config:
            emulator_type = et
            break

    # 1. 从注册表搜索
    found_paths: List[str] = []

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

    # 卸载表根键关键词匹配：兼容安装器写入路径不固定的场景，依赖后续“可执行文件存在”校验过滤噪声。
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

    # 默认路径：覆盖无法从注册表获取安装位置的情况（例如绿色版 / 权限受限）。
    for default_path in config.get("default_paths") or []:
        resolved_default_paths = _resolve_emulator_install_paths(
            default_path,
            config,
            emulator_type,
            source="default_paths",
        )
        found_paths.extend(resolved_default_paths)

    # 系统 PATH：命中率较低但成本很小，作为最后的轻量兜底。
    path_result = _search_from_path(config.get("executables") or [])
    if path_result:
        resolved_path_results = _resolve_emulator_install_paths(
            str(Path(path_result).parent),
            config,
            emulator_type,
            source="system_path",
        )
        found_paths.extend(resolved_path_results)

    return _dedupe_path_strings(found_paths)


def _resolve_emulator_install_paths(
    candidate_path: str,
    config: Dict,
    emulator_type: str,
    source: str,
) -> List[str]:
    """将来源路径统一解析为可用的模拟器安装目录。"""
    if not candidate_path:
        return []

    path_obj = Path(candidate_path)
    if not path_obj.exists():
        return []

    results: List[str] = []

    executable_names = config["executables"]

    # 若输入本身就是目标可执行文件，直接使用其父目录。
    if path_obj.is_file():
        if path_obj.name in executable_names:
            logger.info(f"{config['name']} 通过{source}命中可执行文件: {path_obj}")
            results.append(path_obj.parent.as_posix())
        return _dedupe_path_strings(results)

    # 目录本身可直接校验的场景先走通用逻辑。
    if _validate_emulator_path(str(path_obj), executable_names):
        logger.info(f"{config['name']} 通过{source}命中安装目录: {path_obj}")
        results.append(path_obj.as_posix())

    # MuMu 的安装器路径（如 GameViewer）与主程序目录分离，需要额外结构化推断。
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
    with suppress(OSError):
        return left.samefile(right)
    return left.resolve().as_posix().lower() == right.resolve().as_posix().lower()


def _iter_existing_drive_roots() -> List[Path]:
    """
    枚举当前系统存在的盘符根目录（仅检查 A:/ ~ Z:/ 是否存在，不做任何目录递归扫描）。
    这不是“全盘扫描”，只是为 MuMu GameViewer 的跨盘安装场景提供候选根路径。
    """
    roots: List[Path] = []
    for c in range(65, 91):  # A-Z
        root = Path(f"{chr(c)}:/")
        if root.exists():
            roots.append(root)
    return roots


def _iter_mumu_manager_paths(base_path: Path) -> List[Path]:
    """按 MuMu 常见目录结构生成主程序候选路径。"""
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

    # 若命中 GameViewer 安装器路径，进一步做结构化推断。
    if "gameviewer" in base_path.as_posix().lower():
        candidate_drive_roots: List[Path] = []
        current_drive_root = Path(base_path.anchor) if base_path.anchor else None
        if current_drive_root and current_drive_root.exists():
            candidate_drive_roots.append(current_drive_root)
        # 补齐跨盘安装的推断：仅枚举盘符根目录，不做递归扫描。
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


def _extract_path_from_command(value: str) -> str:
    """
    从注册表里常见的命令行字段中抽取一个路径（exe 或目录）。
    例如:
      - "\"D:\\MuMu\\uninstall.exe\" /S" -> D:\\MuMu\\uninstall.exe
      - "D:\\MuMu\\uninstall.exe /S"     -> D:\\MuMu\\uninstall.exe
    """
    if not value:
        return ""
    s = str(value).strip()
    if not s:
        return ""

    # 优先取第一个引号内片段
    m = re.match(r'^\s*"([^"]+)"', s)
    if m:
        extracted = m.group(1).strip()
        extracted = re.sub(r",\d+\s*$", "", extracted)
        return extracted.strip()

    # 否则取第一个 token（到空格为止）
    token = s.split(" ")[0].strip()
    token = re.sub(r",\d+\s*$", "", token)
    return token.strip()


def _search_from_registry(registry_paths: List[str], display_keywords: List[str] | None = None) -> List[str]:
    """从注册表搜索模拟器路径"""

    def iter_registry_paths(path: str):
        """在不改配置结构的前提下，兼容 WOW6432Node 视图路径。"""
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
        for value_name in REGISTRY_INSTALL_VALUE_NAMES:
            with suppress(FileNotFoundError, OSError):
                value, _ = winreg.QueryValueEx(key, value_name)
                if isinstance(value, str) and value.strip():
                    extracted = _extract_path_from_command(value.strip())
                    return extracted or value.strip()
        return ""

    def is_uninstall_root(path: str) -> bool:
        u = path.upper().rstrip("\\")
        return u.endswith(r"MICROSOFT\WINDOWS\CURRENTVERSION\UNINSTALL")

    def match_display_name(key) -> bool:
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

    for reg_path in registry_paths:
        for candidate_path in iter_registry_paths(reg_path):
            with suppress(FileNotFoundError, OSError):
                # 尝试HKEY_LOCAL_MACHINE
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, candidate_path) as key:
                    # 卸载表根: 枚举子键，根据 DisplayName 关键词匹配
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
                        continue

                    install_path = read_install_path(key)
                    if install_path:
                        add_path(install_path)

            with suppress(FileNotFoundError, OSError):
                # 尝试HKEY_CURRENT_USER
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, candidate_path) as key:
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
                        continue

                    install_path = read_install_path(key)
                    if install_path:
                        add_path(install_path)

    return found


def _search_from_path(executables: List[str]) -> str:
    """从系统PATH搜索模拟器"""

    for executable in executables:
        resolved_path = shutil.which(executable)
        if resolved_path:
            return str(Path(resolved_path))

    return ""


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
    """
    从给定路径向上或向下搜索模拟器主管理器程序的完整路径

    Args:
        input_path (str): 用户输入的路径，可能是主管理器程序的路径
        emulator_type (str): 模拟器类型，用于确定主程序名称
        max_levels (int): 向上搜索的最大层数，默认3层
    Returns:
        str: 找到的主管理器程序的完整路径，如果未找到则返回原输入路径
    """

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
    # 第一个可执行文件是主管理器程序（优先级最高）
    primary_exe = executables[0]

    path_obj = input_path_obj

    # 如果输入的是文件,先获取其父目录
    if path_obj.is_file():
        path_obj = path_obj.parent

    logger.info(
        f"开始搜索{config['name']}主管理器程序路径, 起始路径: {path_obj}, 主程序: {primary_exe}"
    )

    # 1. 首先检查当前目录是否直接包含主管理器程序
    # 如果用户给的就是正确的主程序路径，直接返回
    primary_exe_path = path_obj / primary_exe
    if primary_exe_path.exists():
        result = str(primary_exe_path)
        logger.info(f"当前目录直接包含主程序: {result}")
        return result

    # 2. 向上搜索父目录，找到直接包含主管理器程序的目录（最多3层）
    candidates = []
    current = path_obj
    for level in range(max_levels):
        parent = current.parent
        if parent == current:  # 已到达根目录
            break

        # 只接受直接包含主管理器程序的目录
        parent_exe_path = parent / primary_exe
        if parent_exe_path.exists():
            candidates.append(
                {
                    "path": parent,
                    "exe_path": parent_exe_path,
                    "depth": len(parent.parts),
                    "level": level + 1,
                }
            )
            logger.debug(f"父目录(第{level+1}层)直接包含主程序: {parent_exe_path}")

        current = parent

    # 如果找到了候选目录，选择最优的（层级最小的，即最接近输入路径的）
    if candidates:
        # 排序策略：level 越小越好（越接近输入路径）
        candidates.sort(key=lambda x: x["level"])

        best_candidate = candidates[0]
        result = str(best_candidate["exe_path"])
        logger.info(f"找到模拟器主程序(向上第{best_candidate['level']}层): {result}")
        return result

    # 3. 如果向上没找到，尝试向下搜索子目录（仅1层，且必须直接包含主管理器程序）
    with suppress(PermissionError):
        for subdir in path_obj.iterdir():
            if subdir.is_dir():
                subdir_exe_path = subdir / primary_exe
                # 只接受直接包含主管理器程序的子目录
                if subdir_exe_path.exists():
                    result = str(subdir_exe_path)
                    logger.info(f"在子目录找到主程序: {result}")
                    return result

    # 4. 检查兄弟目录（必须直接包含主管理器程序）
    if path_obj.parent != path_obj:
        with suppress(PermissionError):
            for sibling in path_obj.parent.iterdir():
                if sibling.is_dir() and sibling != path_obj:
                    sibling_exe_path = sibling / primary_exe
                    # 只接受直接包含主管理器程序的兄弟目录
                    if sibling_exe_path.exists():
                        result = str(sibling_exe_path)
                        logger.info(f"在兄弟目录找到主程序: {result}")
                        return result

    logger.warning(f"未能找到{config['name']}主程序，返回原路径: {input_path}")
    return input_path
