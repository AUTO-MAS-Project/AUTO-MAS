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
from collections import defaultdict
from contextlib import suppress
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

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


def _executable_name_set(config: Dict) -> Set[str]:
    return {x.lower() for x in (config.get("executables") or []) if x}


def _emulator_brand_keyword_rows() -> List[Tuple[str, List[str]]]:
    return [
        (emulator_type, cfg.get("registry_display_keywords") or [])
        for emulator_type, cfg in EMULATOR_PATH_BOOK.items()
    ]


def _find_manager_exe_in_dir(directory: Path, executable_names: List[str]) -> Optional[Path]:
    for name in executable_names:
        if not name:
            continue
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def _find_manager_exe_near_side_exe(
    path_obj: Path,
    executable_names: List[str],
    *,
    max_parent_levels: int = 2,
) -> Optional[Path]:
    """自旁路 exe 所在目录向上有限层查找主管理器（仅 is_file，不 iterdir）。"""
    if path_obj.suffix.lower() != ".exe":
        return None
    allowed = _executable_name_set({"executables": executable_names})
    if path_obj.name.lower() in allowed:
        return path_obj

    current = path_obj.parent
    for _ in range(max_parent_levels):
        hit = _find_manager_exe_in_dir(current, executable_names)
        if hit:
            return hit
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


# MuMu 卸载表旁路：自 uninstall.exe 所在目录向上最多 2 层，按序尝试相对路径
MUMU_RELATIVE_EXECUTABLE_PATTERNS = (
    ("MuMuManager.exe",),
    ("nx_main", "MuMuManager.exe"),
    ("shell", "MuMuManager.exe"),
)


def _iter_registry_path_variants(path: str):
    """SOFTWARE 路径同时尝试 WOW6432Node 镜像，与原先 _search_from_registry 行为一致。"""
    yielded = set()
    candidates = [path]
    software_prefix = "SOFTWARE\\"
    wow_prefix = "SOFTWARE\\WOW6432Node\\"
    p_upper = path.upper()
    if p_upper.startswith(software_prefix) and not p_upper.startswith(wow_prefix):
        candidates.append(path.replace(software_prefix, wow_prefix, 1))
    if p_upper.startswith(wow_prefix):
        candidates.append(path.replace(wow_prefix, software_prefix, 1))
    for candidate in candidates:
        key = candidate.upper()
        if key in yielded:
            continue
        yielded.add(key)
        yield candidate


def _is_uninstall_registry_root(path: str) -> bool:
    u = path.upper().rstrip("\\")
    return u.endswith(r"MICROSOFT\WINDOWS\CURRENTVERSION\UNINSTALL")


def _match_registry_display_keywords(display_name: str, keywords: List[str]) -> bool:
    if not keywords:
        return True
    n = display_name.lower()
    return any(k.lower() in n for k in keywords if k)


def _read_registry_uninstall_string(subkey) -> str:
    with suppress(FileNotFoundError, OSError):
        value, _ = winreg.QueryValueEx(subkey, "UninstallString")
        if isinstance(value, str) and value.strip():
            s = value.strip()
            return _extract_path_from_command(s) or s
    return ""


def _unique_uninstall_roots_from_book() -> List[str]:
    """从 EMULATOR_PATH_BOOK 去重收集卸载表根路径（保持首次出现顺序）。"""
    seen: Set[str] = set()
    out: List[str] = []
    for cfg in EMULATOR_PATH_BOOK.values():
        for p in cfg.get("registry_paths") or []:
            if "MICROSOFT\\WINDOWS\\CURRENTVERSION\\UNINSTALL" not in p.upper():
                continue
            u = p.upper()
            if u in seen:
                continue
            seen.add(u)
            out.append(p)
    return out


def _collect_uninstall_paths_by_emulator_type() -> Dict[str, List[str]]:
    """单遍枚举卸载表：每个子键只读一次 DisplayName / UninstallString，再按品牌关键词分发。"""

    acc: Dict[str, List[str]] = defaultdict(list)
    roots = _unique_uninstall_roots_from_book()
    if not roots:
        return {}

    for reg_path in roots:
        for candidate_path in _iter_registry_path_variants(reg_path):
            if not _is_uninstall_registry_root(candidate_path):
                continue
            # 已安装模拟器卸载项均在 HKLM；跳过 HKCU 以减少整树枚举
            for hive in (winreg.HKEY_LOCAL_MACHINE,):
                with suppress(FileNotFoundError, OSError):
                    with winreg.OpenKey(hive, candidate_path) as key:
                        i = 0
                        while True:
                            try:
                                sub = winreg.EnumKey(key, i)
                                i += 1
                            except OSError:
                                break
                            with suppress(FileNotFoundError, OSError):
                                with winreg.OpenKey(key, sub) as subkey:
                                    try:
                                        dn, _ = winreg.QueryValueEx(
                                            subkey, "DisplayName"
                                        )
                                    except OSError:
                                        continue
                                    if not isinstance(dn, str):
                                        continue
                                    matched: List[str] = []
                                    for emulator_type, kw in _emulator_brand_keyword_rows():
                                        if _match_registry_display_keywords(dn, kw):
                                            matched.append(emulator_type)
                                    if not matched:
                                        continue
                                    raw = _read_registry_uninstall_string(subkey)
                                    if not raw:
                                        continue
                                    for emulator_type in matched:
                                        acc[emulator_type].append(raw)

    return {et: _dedupe_path_strings(paths) for et, paths in acc.items()}


def search_all_emulators() -> List[Dict[str, str]]:
    """搜索所有支持的模拟器：仅卸载表 UninstallString 路径（全同步实现）。"""

    logger.info("开始搜索所有模拟器, mode=registry_uninstall")
    found_emulators = []
    found_emulator_paths = set()

    paths_by_type = _collect_uninstall_paths_by_emulator_type()

    for emulator_type, config in EMULATOR_PATH_BOOK.items():
        try:
            for raw_path in paths_by_type.get(emulator_type, []):
                manager_key = _resolve_uninstall_exe_to_manager(
                    raw_path,
                    config,
                    emulator_type,
                    source="registry_uninstall",
                )
                if not manager_key:
                    continue
                dedupe_key = manager_key.lower()
                if dedupe_key in found_emulator_paths:
                    continue
                found_emulator_paths.add(dedupe_key)
                found_emulators.append(
                    {
                        "type": emulator_type,
                        "path": manager_key,
                        "name": f"{config['name']} ({manager_key})",
                    }
                )
                logger.info(f"找到{config['name']}: {manager_key}")
        except Exception as e:
            logger.warning(f"搜索{config['name']}时出错: {e}")

    logger.info(f"搜索完成，共找到 {len(found_emulators)} 个模拟器")
    return found_emulators


def _resolve_uninstall_exe_to_manager(
    candidate_path: str,
    config: Dict,
    emulator_type: str,
    source: str,
) -> Optional[str]:
    """卸载表 UninstallString 一次解析到主管理器 exe（避免目录校验与二次全盘查找）。"""

    candidate_path = _normalize_fs_path_candidate(candidate_path)
    if not candidate_path:
        return None

    path_obj = Path(candidate_path)
    if not path_obj.is_file():
        return None

    executable_names = config.get("executables") or []
    allowed = _executable_name_set(config)
    if path_obj.name.lower() in allowed:
        logger.info(f"{config['name']} 通过{source}命中主管理器: {path_obj}")
        return path_obj.as_posix()

    manager: Optional[Path] = None
    if emulator_type == "mumu":
        manager = _find_mumu_manager_from_base(path_obj.parent)
    elif emulator_type in ("ldplayer", "nox", "bluestacks", "memu"):
        parent_levels = 3 if emulator_type == "memu" else 2
        manager = _find_manager_exe_near_side_exe(
            path_obj,
            executable_names,
            max_parent_levels=parent_levels,
        )

    if manager:
        logger.info(f"{config['name']} 通过{source}由旁路 exe 推断主管理器: {manager}")
        return manager.as_posix()

    logger.debug(f"{config['name']} 通过{source}未解析到主管理器: {candidate_path}")
    return None


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


def _find_mumu_manager_from_base(base_path: Path) -> Optional[Path]:
    """自基准目录及最多 2 层父目录，按 MUMU_RELATIVE_EXECUTABLE_PATTERNS 找首个存在的 MuMuManager。"""
    candidate_bases: List[Path] = [base_path]
    current = base_path
    for _ in range(2):
        parent = current.parent
        if parent == current:
            break
        candidate_bases.append(parent)
        current = parent

    seen: Set[str] = set()
    for candidate_base in candidate_bases:
        for pattern in MUMU_RELATIVE_EXECUTABLE_PATTERNS:
            candidate = candidate_base.joinpath(*pattern)
            key = candidate.as_posix().lower()
            if key in seen:
                continue
            seen.add(key)
            if candidate.exists():
                return candidate
    return None


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


def find_emulator_manager_path(
    input_path: str, emulator_type: str, max_levels: int = 3
) -> str:
    """从给定路径搜索主管理器 exe 完整路径，未找到则返回原路径（配置校正等场景）。"""

    if not input_path:
        logger.warning(f"输入路径无效: {input_path}")
        return input_path
    input_path_obj = Path(input_path)
    if not input_path_obj.exists():
        logger.warning(f"输入路径无效: {input_path}")
        return input_path

    if emulator_type not in EMULATOR_PATH_BOOK:
        logger.warning(f"不支持的模拟器类型: {emulator_type}")
        return input_path

    config = EMULATOR_PATH_BOOK[emulator_type]
    executables = config["executables"]

    if input_path_obj.is_file():
        if emulator_type == "mumu":
            manager = _find_mumu_manager_from_base(input_path_obj.parent)
            if manager:
                return str(manager)
        else:
            manager = _find_manager_exe_near_side_exe(
                input_path_obj,
                executables,
                max_parent_levels=max_levels,
            )
            if manager:
                return str(manager)

    path_obj = input_path_obj if input_path_obj.is_dir() else input_path_obj.parent

    hit = _find_manager_exe_in_dir(path_obj, executables)
    if hit:
        return str(hit)

    current = path_obj
    for level in range(max_levels):
        parent = current.parent
        if parent == current:
            break
        parent_hit = _find_manager_exe_in_dir(parent, executables)
        if parent_hit:
            logger.debug(f"父目录(第{level + 1}层)直接包含主程序: {parent_hit}")
            return str(parent_hit)
        current = parent

    with suppress(PermissionError):
        for subdir in path_obj.iterdir():
            if subdir.is_dir():
                sub_hit = _find_manager_exe_in_dir(subdir, executables)
                if sub_hit:
                    return str(sub_hit)

    logger.warning(f"未能找到{config['name']}主程序，返回原路径: {input_path}")
    return input_path
