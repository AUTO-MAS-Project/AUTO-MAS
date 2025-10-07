#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import os
import winreg
import subprocess
from pathlib import Path
from typing import List, Dict

from app.utils.constants import EMULATOR_PATH_BOOK
from app.utils import get_logger

logger = get_logger("模拟器管理工具")


async def search_all_emulators() -> List[Dict[str, str]]:
    """搜索所有支持的模拟器"""

    logger.info("开始搜索所有模拟器")
    found_emulators = []

    for emulator_type, config in EMULATOR_PATH_BOOK.items():
        try:
            emulator_path = await _search_emulator(emulator_type, config)
            if emulator_path:
                found_emulators.append(
                    {
                        "type": emulator_type,
                        "path": emulator_path,
                        "name": f"{config['name']} ({emulator_path})",
                    }
                )
                logger.info(f"找到{config['name']}: {emulator_path}")
        except Exception as e:
            logger.warning(f"搜索{config['name']}时出错: {e}")

    logger.info(f"搜索完成，共找到 {len(found_emulators)} 个模拟器")
    return found_emulators


async def _search_emulator(emulator_type: str, config: Dict) -> str:
    """搜索单个模拟器"""

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
        return str(Path(path_result).parent)

    return ""


async def _search_from_registry(registry_paths: List[str]) -> str:
    """从注册表搜索模拟器路径"""

    for reg_path in registry_paths:
        try:
            # 尝试HKEY_LOCAL_MACHINE
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
                install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                return install_path
        except (FileNotFoundError, OSError):
            pass

        try:
            # 尝试HKEY_CURRENT_USER
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path) as key:
                install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                return install_path
        except (FileNotFoundError, OSError):
            pass

    return ""


async def _search_from_path(executables: List[str]) -> str:
    """从系统PATH搜索模拟器"""

    for executable in executables:
        try:
            # 使用where命令搜索可执行文件
            result = subprocess.run(
                ["where", executable], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split("\n")[0]
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass

    return ""


async def _validate_emulator_path(path: str, executables: List[str]) -> bool:
    """验证模拟器路径是否有效"""

    if not path or not os.path.exists(path):
        return False

    path_obj = Path(path)

    # 检查是否存在任何一个可执行文件
    for executable in executables:
        if (path_obj / executable).exists():
            return True

        # 也检查子目录
        for subdir in path_obj.iterdir():
            if subdir.is_dir() and (subdir / executable).exists():
                return True

    return False
