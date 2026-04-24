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
import asyncio
import concurrent.futures
import threading
import time
import winreg
import subprocess
from maa.toolkit import Toolkit
from contextlib import suppress
from pathlib import Path
from typing import List, Dict, Set, Callable

from app.utils.constants import EMULATOR_PATH_BOOK
from app.utils import get_logger

logger = get_logger("模拟器管理工具")

EXECUTABLE_EXTENSIONS = {".exe", ".bat", ".cmd"}

_SCAN_PROGRESS_LOCK = threading.Lock()
_SCAN_PROGRESS = {
    "active": False,
    "phase": "idle",
    "total_drives": 0,
    "completed_drives": 0,
    "current_drive": "",
    "current_path": "",
    "found_count": 0,
    "elapsed_seconds": 0,
    "progress_percent": 0,
}


def get_available_drives() -> List[str]:
    """获取当前系统可用盘符"""
    drives = []
    for c in range(65, 91):  # A-Z
        drive = f"{chr(c)}:\\"
        if os.path.exists(drive):
            drives.append(drive)
    return drives


def _set_scan_progress(**kwargs) -> None:
    with _SCAN_PROGRESS_LOCK:
        _SCAN_PROGRESS.update(kwargs)


def get_emulator_search_progress() -> Dict[str, int | str | bool]:
    """读取当前全盘扫描进度（用于前端轮询）"""
    with _SCAN_PROGRESS_LOCK:
        return dict(_SCAN_PROGRESS)


def _search_in_directory_sync(
    directory: str,
    executable_names: Set[str],
    max_depth: int = 5,
    progress_callback: Callable[[str], None] | None = None,
) -> Set[str]:
    """同步目录搜索，用于线程池并发全盘扫描"""
    found_paths: Set[str] = set()
    stack: List[tuple[str, int]] = [(directory, 0)]

    while stack:
        current_dir, depth = stack.pop()
        if progress_callback is not None:
            with suppress(Exception):
                progress_callback(current_dir)
        if depth > max_depth:
            continue

        try:
            with os.scandir(current_dir) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            entry_name = entry.name.lower()
                            if entry_name.startswith(".") or entry_name.startswith("$"):
                                continue
                            stack.append((entry.path, depth + 1))
                        elif entry.is_file(follow_symlinks=False):
                            if (
                                Path(entry.path).suffix.lower() in EXECUTABLE_EXTENSIONS
                                and entry.name in executable_names
                            ):
                                found_paths.add(entry.path)
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError):
            continue

    return found_paths


def _full_disk_scan_sync(executable_names: Set[str]) -> Set[str]:
    """全盘扫描模拟器可执行文件（可选慢速模式）"""
    found_paths: Set[str] = set()
    drives = get_available_drives()
    if not drives:
        _set_scan_progress(
            active=False,
            phase="done",
            total_drives=0,
            completed_drives=0,
            current_drive="",
            current_path="",
            found_count=0,
            elapsed_seconds=0,
            progress_percent=100,
        )
        return found_paths

    scan_start = time.monotonic()
    _set_scan_progress(
        active=True,
        phase="full_scan",
        total_drives=len(drives),
        completed_drives=0,
        current_drive="",
        current_path="",
        found_count=0,
        elapsed_seconds=0,
        progress_percent=0,
    )

    worker_count = min(max(2, (os.cpu_count() or 4) // 2), len(drives), 6)
    progress_update_lock = threading.Lock()
    last_path_update_ts = 0.0

    def report_current_path(path: str) -> None:
        nonlocal last_path_update_ts
        # 限流更新，降低锁竞争和状态刷新开销
        now = time.monotonic()
        if now - last_path_update_ts < 0.4:
            return
        with progress_update_lock:
            if now - last_path_update_ts < 0.4:
                return
            last_path_update_ts = now
        current_drive = f"{Path(path).drive}\\" if Path(path).drive else ""
        _set_scan_progress(current_drive=current_drive, current_path=path)

    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_drive = {
            executor.submit(
                _search_in_directory_sync,
                drive,
                executable_names,
                8,
                report_current_path,
            ): drive
            for drive in drives
        }
        completed = 0
        for future in concurrent.futures.as_completed(future_to_drive):
            drive = future_to_drive[future]
            _set_scan_progress(current_drive=drive)
            with suppress(Exception):
                found_paths.update(future.result())
            completed += 1
            elapsed = int(time.monotonic() - scan_start)
            percent = int((completed / len(drives)) * 100)
            _set_scan_progress(
                completed_drives=completed,
                found_count=len(found_paths),
                elapsed_seconds=elapsed,
                progress_percent=percent,
            )

    _set_scan_progress(
        active=False,
        phase="done",
        current_drive="",
        current_path="",
        elapsed_seconds=int(time.monotonic() - scan_start),
        progress_percent=100,
    )

    return found_paths


async def _full_disk_scan(executable_names: Set[str]) -> Set[str]:
    """在线程中执行全盘扫描，避免阻塞事件循环导致进度接口卡住"""
    return await asyncio.to_thread(_full_disk_scan_sync, executable_names)


async def search_all_emulators(include_full_scan: bool = False) -> List[Dict[str, str]]:
    """搜索所有支持的模拟器"""

    logger.info(f"开始搜索所有模拟器, include_full_scan={include_full_scan}")
    if include_full_scan:
        # 每次开始全盘扫描请求前先重置进度，避免前端读到上次扫描残留耗时
        _set_scan_progress(
            active=True,
            phase="preparing",
            total_drives=0,
            completed_drives=0,
            current_drive="",
            current_path="",
            found_count=0,
            elapsed_seconds=0,
            progress_percent=0,
        )
    else:
        _set_scan_progress(
            active=False,
            phase="quick_search",
            total_drives=0,
            completed_drives=0,
            current_drive="",
            current_path="",
            found_count=0,
            elapsed_seconds=0,
            progress_percent=0,
        )
    found_emulators = []
    found_emulator_paths = set()

    # 根据可能的模拟器路径搜索
    for emulator_type, config in EMULATOR_PATH_BOOK.items():
        try:
            emulator_path = _search_emulator(config)
            if emulator_path:
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

    # 可选全盘扫描（慢）
    if include_full_scan:
        custom_executables = set()
        for config in EMULATOR_PATH_BOOK.values():
            custom_executables.update(config["executables"])
        full_disk_paths = await _full_disk_scan(custom_executables)

        for path in full_disk_paths:
            emulator_type = "general"
            for et, cfg in EMULATOR_PATH_BOOK.items():
                if any(exe in path for exe in cfg["executables"]):
                    emulator_type = et
                    break

            corrected_path = find_emulator_manager_path(path, emulator_type)
            if corrected_path not in found_emulator_paths:
                found_emulator_paths.add(corrected_path)
                cfg = EMULATOR_PATH_BOOK.get(emulator_type, {"name": "未知模拟器"})
                found_emulators.append(
                    {
                        "type": emulator_type,
                        "path": corrected_path,
                        "name": f"{cfg['name']} ({corrected_path})",
                    }
                )

    for emulator in Toolkit.find_adb_devices():
        for emulator_type in EMULATOR_PATH_BOOK.keys():
            corrected_path = find_emulator_manager_path(
                emulator.adb_path.as_posix(), emulator_type
            )
            if corrected_path != emulator.adb_path.as_posix():
                if corrected_path not in found_emulator_paths:
                    found_emulator_paths.add(corrected_path)
                    found_emulators.append(
                        {
                            "type": emulator_type,
                            "path": corrected_path,
                            "name": f"{EMULATOR_PATH_BOOK[emulator_type]['name']} ({corrected_path})",
                        }
                    )
                    logger.info(
                        f"通过ADB找到{EMULATOR_PATH_BOOK[emulator_type]['name']}: {corrected_path}"
                    )
                break
        else:
            if emulator.adb_path.as_posix() not in found_emulator_paths:
                found_emulator_paths.add(emulator.adb_path.as_posix())
                found_emulators.append(
                    {
                        "type": "general",
                        "path": emulator.adb_path.parent.as_posix(),
                        "name": f"未知模拟器 ({emulator.adb_path.parent.as_posix()})",
                    }
                )
                logger.info(f"通过ADB找到未知模拟器: {emulator.adb_path.as_posix()}")

    logger.info(f"搜索完成，共找到 {len(found_emulators)} 个模拟器")
    return found_emulators


def _search_emulator(config: Dict) -> str:
    """搜索单类模拟器"""

    # 1. 从注册表搜索
    registry_path = _search_from_registry(config["registry_paths"])
    if registry_path and _validate_emulator_path(registry_path, config["executables"]):
        return registry_path

    # 2. 从默认路径搜索
    for default_path in config["default_paths"]:
        if _validate_emulator_path(default_path, config["executables"]):
            return default_path

    # 3. 从系统PATH搜索
    path_result = _search_from_path(config["executables"])
    if path_result:
        return Path(path_result).parent.as_posix()

    return ""


def _search_from_registry(registry_paths: List[str]) -> str:
    """从注册表搜索模拟器路径"""

    for reg_path in registry_paths:
        with suppress(FileNotFoundError, OSError):
            # 尝试HKEY_LOCAL_MACHINE
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
                install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                return install_path

        with suppress(FileNotFoundError, OSError):
            # 尝试HKEY_CURRENT_USER
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path) as key:
                install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                return install_path

    return ""


def _search_from_path(executables: List[str]) -> str:
    """从系统PATH搜索模拟器"""

    for executable in executables:
        with suppress(subprocess.TimeoutExpired, subprocess.SubprocessError):
            # 使用where命令搜索可执行文件
            result = subprocess.run(
                ["where", executable], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split("\n")[0]

    return ""


def _validate_emulator_path(path: str, executables: List[str]) -> bool:
    """验证模拟器路径是否有效"""

    if not path or not os.path.exists(path):
        return False

    path_obj = Path(path)

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

    if not input_path or not os.path.exists(input_path):
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

    path_obj = Path(input_path)

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

    # 如果找到了候选目录，选择最优的（深度最小的，即最接近根目录的）
    if candidates:
        # 排序策略：深度越小越好（越靠近根目录）
        candidates.sort(key=lambda x: x["depth"])

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
