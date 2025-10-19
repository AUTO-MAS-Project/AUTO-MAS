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


def resolve_lnk_path(lnk_path: str) -> str:
    """
    解析Windows快捷方式(.lnk)文件,获取目标路径

    Parameters
    ----------
    lnk_path : str
        快捷方式文件路径

    Returns
    -------
    str
        快捷方式指向的目标路径,如果解析失败则返回原路径
    """

    if not lnk_path.lower().endswith(".lnk"):
        return lnk_path

    if not os.path.exists(lnk_path):
        logger.warning(f"快捷方式文件不存在: {lnk_path}")
        return lnk_path

    try:
        import win32com.client

        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(lnk_path)
        target_path = shortcut.Targetpath

        if target_path and os.path.exists(target_path):
            logger.info(f"解析快捷方式: {lnk_path} -> {target_path}")
            return target_path
        else:
            logger.warning(f"快捷方式目标路径无效: {target_path}")
            return lnk_path

    except ImportError:
        logger.warning("未安装 pywin32,尝试使用备用方法解析快捷方式")

        # 备用方法:使用 PowerShell 解析快捷方式
        try:
            ps_command = f"""
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut("{lnk_path}")
$shortcut.TargetPath
"""
            result = subprocess.run(
                ["powershell", "-Command", ps_command],
                capture_output=True,
                text=True,
                timeout=5,
                encoding="utf-8",
                errors="replace",
            )

            if result.returncode == 0 and result.stdout.strip():
                target_path = result.stdout.strip()
                if os.path.exists(target_path):
                    logger.info(
                        f"解析快捷方式(PowerShell): {lnk_path} -> {target_path}"
                    )
                    return target_path

        except Exception as e:
            logger.warning(f"使用PowerShell解析快捷方式失败: {e}")

        return lnk_path

    except Exception as e:
        logger.warning(f"解析快捷方式失败: {e}")
        return lnk_path


async def search_all_emulators() -> List[Dict[str, str]]:
    """搜索所有支持的模拟器"""

    logger.info("开始搜索所有模拟器")
    found_emulators = []

    for emulator_type, config in EMULATOR_PATH_BOOK.items():
        try:
            emulator_path = await _search_emulator(emulator_type, config)
            if emulator_path:
                # 自动修正路径到根目录
                corrected_path = await find_emulator_root_path(
                    emulator_path, emulator_type
                )
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

    # 检查当前目录是否直接包含任何可执行文件
    for executable in executables:
        if (path_obj / executable).exists():
            return True

    # 仅检查一级子目录(不递归)
    try:
        for item in path_obj.iterdir():
            if item.is_dir():
                for executable in executables:
                    if (item / executable).exists():
                        return True
    except PermissionError:
        pass

    return False


async def find_emulator_root_path(
    input_path: str, emulator_type: str, max_levels: int = 5
) -> str:
    """
    从给定路径向上或向下搜索模拟器根目录

    Parameters
    ----------
    input_path : str
        用户输入的路径(可能是exe文件、快捷方式或某个子目录)
    emulator_type : str
        模拟器类型(mumu, ldplayer, nox等)
    max_levels : int, optional
        向上搜索的最大层级数, by default 5

    Returns
    -------
    str
        找到的模拟器根目录路径,如果未找到则返回原路径
    """

    if not input_path or not os.path.exists(input_path):
        logger.warning(f"输入路径无效: {input_path}")
        return input_path

    # 如果是快捷方式,先解析获取真实路径
    if input_path.lower().endswith(".lnk"):
        logger.info(f"检测到快捷方式文件: {input_path}")
        input_path = resolve_lnk_path(input_path)
        if not os.path.exists(input_path):
            logger.warning(f"快捷方式解析后的路径无效: {input_path}")
            return input_path

    # 获取模拟器配置信息
    if emulator_type not in EMULATOR_PATH_BOOK:
        logger.warning(f"不支持的模拟器类型: {emulator_type}")
        return input_path

    config = EMULATOR_PATH_BOOK[emulator_type]
    executables = config["executables"]

    path_obj = Path(input_path)

    # 如果输入的是文件,先获取其父目录
    if path_obj.is_file():
        path_obj = path_obj.parent

    logger.info(f"开始搜索{config['name']}根目录,起始路径: {path_obj}")

    # 1. 首先向上搜索,找到最顶层包含所需文件的目录
    candidates = []

    # 检查当前目录
    if await _validate_emulator_path(str(path_obj), executables):
        candidates.append(path_obj)
        logger.debug(f"当前目录有效: {path_obj}")

    # 向上搜索父目录
    current = path_obj
    for _ in range(max_levels):
        parent = current.parent
        if parent == current:  # 已到达根目录
            break

        if await _validate_emulator_path(str(parent), executables):
            candidates.append(parent)
            logger.debug(f"父目录有效: {parent}")

        current = parent

    # 如果找到了候选目录,优先返回直接包含更多可执行文件的目录
    if candidates:
        # 为每个候选目录计算直接包含的可执行文件数量
        candidate_scores = []
        for candidate in candidates:
            direct_exe_count = sum(
                1 for exe in executables if (candidate / exe).exists()
            )
            subfolder_exe_count = 0
            try:
                for item in candidate.iterdir():
                    if item.is_dir():
                        subfolder_exe_count += sum(
                            1 for exe in executables if (item / exe).exists()
                        )
            except PermissionError:
                pass

            candidate_scores.append(
                {
                    "path": candidate,
                    "direct_count": direct_exe_count,
                    "subfolder_count": subfolder_exe_count,
                    "depth": len(candidate.parts),
                }
            )

        # 排序:优先选择直接包含更多可执行文件的,其次选择子目录包含更多的,最后按深度
        candidate_scores.sort(
            key=lambda x: (x["direct_count"], x["subfolder_count"], -x["depth"]),
            reverse=True,
        )

        result = str(candidate_scores[0]["path"])
        logger.info(
            f"找到模拟器根目录 (直接包含{candidate_scores[0]['direct_count']}个exe,子目录{candidate_scores[0]['subfolder_count']}个): {result}"
        )
        return result

    # 2. 如果向上没找到,尝试向下搜索子目录(深度1层)
    try:
        for subdir in path_obj.iterdir():
            if subdir.is_dir():
                if await _validate_emulator_path(str(subdir), executables):
                    logger.info(f"在子目录找到根目录: {subdir}")
                    return str(subdir)
    except PermissionError:
        pass

    # 3. 检查兄弟目录
    if path_obj.parent != path_obj:
        try:
            for sibling in path_obj.parent.iterdir():
                if sibling.is_dir() and sibling != path_obj:
                    if await _validate_emulator_path(str(sibling), executables):
                        logger.info(f"在兄弟目录找到根目录: {sibling}")
                        return str(sibling)
        except PermissionError:
            pass

    logger.warning(f"未能找到{config['name']}根目录,返回原路径: {input_path}")
    return input_path
