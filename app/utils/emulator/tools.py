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
import winreg
import subprocess
import asyncio
import concurrent.futures
from maa.toolkit import Toolkit
from contextlib import suppress
from pathlib import Path
from typing import List, Dict, Set, Optional

from app.utils.constants import EMULATOR_PATH_BOOK
from app.utils import get_logger
from app.core.config import Config

logger = get_logger("模拟器管理工具")

# 排除的目录列表，避免搜索系统目录和其他不必要的目录
EXCLUDED_DIRS = {
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "C:\\ProgramData",
    "C:\\Users",
    "C:\\System Volume Information",
    "C:\\$Recycle.Bin",
    "D:\\System Volume Information",
    "D:\\$Recycle.Bin",
}

# 可执行文件扩展名
EXECUTABLE_EXTENSIONS = {".exe", ".bat", ".cmd"}


def get_available_drives() -> List[str]:
    """获取所有可用的磁盘驱动器"""
    drives = []
    for c in range(65, 91):  # A-Z
        drive = f"{chr(c)}:/"
        if os.path.exists(drive):
            drives.append(drive)
    return drives


async def _search_in_directory(
    directory: str, 
    executable_names: Set[str], 
    found_paths: Set[str],
    max_depth: int = 5,  # 增加搜索深度
    current_depth: int = 0
) -> None:
    """在指定目录中搜索模拟器可执行文件"""
    if current_depth >= max_depth:
        return

    # 检查是否是排除目录，但允许搜索 E:\Program Files 目录
    if directory in EXCLUDED_DIRS and not directory.startswith("E:\\Program Files"):
        logger.debug(f"跳过排除目录: {directory}")
        return

    try:
        logger.debug(f"搜索目录: {directory}")
        with os.scandir(directory) as entries:
            for entry in entries:
                try:
                    if entry.is_dir():
                        # 跳过隐藏目录
                        if entry.name.startswith(".") or entry.name.startswith("$"):
                            logger.debug(f"跳过隐藏目录: {entry.path}")
                            continue
                        # 特别关注 YXReverse1999-12.0 目录
                        if "YXReverse1999" in entry.name:
                            logger.info(f"发现 YXReverse1999 目录: {entry.path}")
                        # 递归搜索子目录
                        await _search_in_directory(
                            entry.path, 
                            executable_names, 
                            found_paths, 
                            max_depth, 
                            current_depth + 1
                        )
                    elif entry.is_file():
                        # 检查是否是可执行文件且名称匹配
                        if (
                            Path(entry.path).suffix.lower() in EXECUTABLE_EXTENSIONS and
                            entry.name in executable_names
                        ):
                            logger.info(f"找到匹配的可执行文件: {entry.path}")
                            found_paths.add(entry.path)
                except (PermissionError, OSError) as e:
                    # 跳过无权限访问的文件或目录
                    logger.debug(f"无法访问 {entry.path}: {e}")
                    pass
    except (PermissionError, OSError) as e:
        # 跳过无权限访问的目录
        logger.debug(f"无法访问目录 {directory}: {e}")
        pass


async def _full_disk_scan(executable_names: Set[str]) -> Set[str]:
    """全盘扫描模拟器可执行文件"""
    logger.info("开始全盘扫描模拟器")
    found_paths = set()
    drives = get_available_drives()
    
    logger.info(f"发现 {len(drives)} 个可用磁盘驱动器: {drives}")
    
    # 针对 E 盘的特殊处理，添加详细日志
    for drive in drives:
        if drive == "E:/":
            logger.info(f"开始扫描 E 盘")
            # 直接扫描 E 盘的 Program Files 目录
            program_files_path = os.path.join(drive, "Program Files")
            if os.path.exists(program_files_path):
                logger.info(f"扫描 E:\\Program Files 目录")
                # 列出该目录下的所有子目录
                try:
                    with os.scandir(program_files_path) as entries:
                        for entry in entries:
                            if entry.is_dir():
                                logger.info(f"E:\\Program Files 下的目录: {entry.name}")
                                # 特别检查 YXReverse1999-12.0 目录
                                if "YXReverse1999" in entry.name:
                                    logger.info(f"发现 YXReverse1999 目录: {entry.path}")
                                    # 直接在该目录中搜索模拟器可执行文件
                                    await _search_in_directory(entry.path, executable_names, found_paths, max_depth=5)
                except Exception as e:
                    logger.warning(f"无法列出 E:\\Program Files 目录: {e}")
    
    # 使用线程池并行扫描
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(drives))) as executor:
        tasks = []
        for drive in drives:
            task = executor.submit(
                asyncio.run, 
                _search_in_directory(drive, executable_names, found_paths)
            )
            tasks.append(task)
        
        # 等待所有任务完成
        for task in concurrent.futures.as_completed(tasks):
            try:
                task.result()
            except Exception as e:
                logger.warning(f"扫描过程中出错: {e}")
    
    logger.info(f"全盘扫描完成，找到 {len(found_paths)} 个匹配的可执行文件")
    logger.info(f"找到的可执行文件: {found_paths}")
    return found_paths


async def search_all_emulators() -> List[Dict[str, str]]:
    """搜索所有支持的模拟器"""

    logger.info("开始搜索所有模拟器")
    found_emulators = []
    found_emulator_paths = set()

    # 收集所有模拟器可执行文件名称
    all_executables = set()
    for config in EMULATOR_PATH_BOOK.values():
        all_executables.update(config["executables"])

    # 1. 传统搜索（注册表、默认路径、PATH）
    for emulator_type, config in EMULATOR_PATH_BOOK.items():
        try:
            emulator_path = await _search_emulator(config)
            if emulator_path:
                # 自动修正路径
                corrected_path = await find_emulator_manager_path(
                    emulator_path, emulator_type
                )
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

    # 2. 自定义目录扫描
    try:
        # 读取用户自定义的搜索目录
        custom_dirs = Config.get("Emulator", "CustomSearchDirs")
        if custom_dirs:
            logger.info(f"开始扫描用户自定义目录: {custom_dirs}")
            for custom_dir in custom_dirs:
                if os.path.exists(custom_dir):
                    # 在自定义目录中搜索模拟器可执行文件
                    custom_paths = set()
                    await _search_in_directory(custom_dir, all_executables, custom_paths, max_depth=5)
                    for path in custom_paths:
                        # 尝试确定模拟器类型
                        emulator_type = "general"
                        for et, config in EMULATOR_PATH_BOOK.items():
                            if any(exe in path for exe in config["executables"]):
                                emulator_type = et
                                break
                        
                        # 自动修正路径
                        corrected_path = await find_emulator_manager_path(path, emulator_type)
                        if corrected_path not in found_emulator_paths:
                            found_emulator_paths.add(corrected_path)
                            config = EMULATOR_PATH_BOOK.get(emulator_type, {"name": "未知模拟器"})
                            found_emulators.append(
                                {
                                    "type": emulator_type,
                                    "path": corrected_path,
                                    "name": f"{config['name']} ({corrected_path})",
                                }
                            )
                            logger.info(f"通过自定义目录扫描找到{config['name']}: {corrected_path}")
    except Exception as e:
        logger.warning(f"自定义目录扫描时出错: {e}")

    # 3. 全盘扫描
    try:
        full_disk_paths = await _full_disk_scan(all_executables)
        for path in full_disk_paths:
            # 尝试确定模拟器类型
            emulator_type = "general"
            for et, config in EMULATOR_PATH_BOOK.items():
                if any(exe in path for exe in config["executables"]):
                    emulator_type = et
                    break
            
            # 自动修正路径
            corrected_path = await find_emulator_manager_path(path, emulator_type)
            if corrected_path not in found_emulator_paths:
                found_emulator_paths.add(corrected_path)
                config = EMULATOR_PATH_BOOK.get(emulator_type, {"name": "未知模拟器"})
                found_emulators.append(
                    {
                        "type": emulator_type,
                        "path": corrected_path,
                        "name": f"{config['name']} ({corrected_path})",
                    }
                )
                logger.info(f"通过全盘扫描找到{config['name']}: {corrected_path}")
    except Exception as e:
        logger.warning(f"全盘扫描时出错: {e}")

    # 4. ADB设备搜索
    for emulator in Toolkit.find_adb_devices():
        for emulator_type in EMULATOR_PATH_BOOK.keys():
            corrected_path = await find_emulator_manager_path(
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


async def _search_emulator(config: Dict) -> str:
    """搜索单类模拟器"""

    # 1. 从注册表搜索
    registry_path = await _search_from_registry(config["registry_paths"])
    if registry_path and await _validate_emulator_path(
        registry_path, config["executables"]
    ):
        return registry_path

    # 2. 从默认路径搜索
    for default_path in config["default_paths"]:
        if await _validate_emulator_path(default_path, config["executables"]):
            return default_path

    # 3. 从系统PATH搜索
    path_result = await _search_from_path(config["executables"])
    if path_result:
        return Path(path_result).parent.as_posix()

    return ""


async def _search_from_registry(registry_paths: List[str]) -> str:
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


async def _search_from_path(executables: List[str]) -> str:
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


async def _validate_emulator_path(path: str, executables: List[str]) -> bool:
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


async def find_emulator_manager_path(
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
