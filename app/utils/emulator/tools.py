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
    input_path: str, emulator_type: str, max_levels: int = 3
) -> str:
    """
    从给定路径向上或向下搜索模拟器主管理器程序的完整路径

    Parameters
    ----------
    input_path : str
        用户输入的路径(可能是exe文件、快捷方式或某个子目录)
    emulator_type : str
        模拟器类型(mumu, ldplayer, nox等)
    max_levels : int, optional
        向上搜索的最大层级数, by default 3

    Returns
    -------
    str
        找到的模拟器主管理器程序的完整路径（如 C:/MuMu/MuMuManager.exe），如果未找到则返回原路径

    Notes
    -----
    - 向上搜索：最多3层父目录
    - 向下搜索：仅1层子目录
    - 返回主管理器程序的完整文件路径（不是文件夹路径）
    - 优先级：包含主管理器程序的目录 > exe数量多的 > 深度小的

    Examples
    --------
    >>> # MuMu模拟器，主程序是 MuMuManager.exe
    >>> find_emulator_root_path("C:/MuMu/shell/MuMuPlayer.exe", "mumu")
    "C:/MuMu/MuMuManager.exe"  # 返回主程序的完整路径
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
    # 第一个可执行文件是主管理器程序（优先级最高）
    primary_exe = executables[0]

    path_obj = Path(input_path)

    # 如果输入的是文件,先获取其父目录
    if path_obj.is_file():
        path_obj = path_obj.parent

    logger.info(
        f"开始搜索{config['name']}根目录,起始路径: {path_obj}, 主程序: {primary_exe}"
    )

    # 1. 首先向上搜索,找到直接包含主管理器程序的目录（最多3层）
    candidates = []

    # 检查当前目录是否直接包含主管理器程序
    if (path_obj / primary_exe).exists():
        candidates.append(
            {
                "path": path_obj,
                "depth": len(path_obj.parts),
            }
        )
        logger.debug(
            f"当前目录直接包含主程序: {path_obj}"
        )

    # 向上搜索父目录（最多3层）
    current = path_obj
    for level in range(max_levels):
        parent = current.parent
        if parent == current:  # 已到达根目录
            break

        # 只接受直接包含主管理器程序的目录
        if (parent / primary_exe).exists():
            candidates.append(
                {
                    "path": parent,
                    "depth": len(parent.parts),
                }
            )
            logger.debug(
                f"父目录(第{level+1}层)直接包含主程序: {parent}"
            )

        current = parent

    # 如果找到了候选目录，选择最优的（深度最小的，即最接近根目录的）
    if candidates:
        # 排序策略：深度越小越好（越靠近根目录）
        candidates.sort(
            key=lambda x: x["depth"],  # 深度越小越好
        )

        best_dir = candidates[0]["path"]
        # 返回主管理器程序的完整路径
        primary_exe_path = best_dir / primary_exe

        # 验证主程序文件是否真实存在
        if not primary_exe_path.exists():
            logger.error(f"候选目录不包含主程序文件: {primary_exe_path}")
            return input_path

        result = str(primary_exe_path)
        logger.info(
            f"找到模拟器主程序: {result}"
        )
        return result

    # 2. 如果向上没找到,尝试向下搜索子目录(仅1层，且必须直接包含主管理器程序)
    best_subdir = None
    try:
        for subdir in path_obj.iterdir():
            if subdir.is_dir():
                # 只接受直接包含主管理器程序的子目录
                if (subdir / primary_exe).exists():
                    best_subdir = subdir
                    break  # 找到第一个就停止
    except PermissionError:
        pass

    if best_subdir:
        # 返回主管理器程序的完整路径
        primary_exe_path = best_subdir / primary_exe

        # 验证主程序文件是否真实存在
        if not primary_exe_path.exists():
            logger.warning(
                f"子目录不包含主程序文件: {primary_exe_path}"
            )
        else:
            result = str(primary_exe_path)
            logger.info(
                f"在子目录找到主程序: {result}"
            )
            return result

    # 3. 检查兄弟目录（必须直接包含主管理器程序）
    if path_obj.parent != path_obj:
        try:
            for sibling in path_obj.parent.iterdir():
                if sibling.is_dir() and sibling != path_obj:
                    # 只接受直接包含主管理器程序的兄弟目录
                    if (sibling / primary_exe).exists():
                        primary_exe_path = sibling / primary_exe
                        
                        # 验证主程序文件是否真实存在
                        if primary_exe_path.exists():
                            result = str(primary_exe_path)
                            logger.info(
                                f"在兄弟目录找到主程序: {result}"
                            )
                            return result
        except PermissionError:
            pass

    logger.warning(
        f"未能找到{config['name']}主程序，返回原路径: {input_path}"
    )
    return input_path
