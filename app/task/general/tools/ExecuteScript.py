#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

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
import sys
import asyncio
from pathlib import Path

from app.utils import ProcessRunner, get_logger
from app.utils.constants import CREATION_FLAGS

logger = get_logger("自定义脚本执行工具")


async def execute_script_task(script_path: Path, task_name: str) -> bool:
    """执行脚本任务并等待结束"""

    if not script_path.exists():
        logger.error(f"{task_name}脚本不存在")
        return False

    try:
        logger.info(f"开始执行{task_name}: {script_path}")

        # 根据文件类型选择执行方式
        if script_path.suffix.lower() == ".py":
            cmd = [sys.executable, str(script_path)]
        elif script_path.suffix.lower() in [".bat", ".cmd"]:
            # bat/cmd 脚本使用 cmd.exe 执行，并传递 admin 参数跳过权限检查
            cmd = ["cmd.exe", "/c", str(script_path), "admin"]
        elif script_path.suffix.lower() == ".exe":
            cmd = [str(script_path)]
        elif script_path.suffix.lower() == "":
            logger.warning(f"{task_name}脚本没有指定后缀名, 无法执行")
            return False
        else:
            # 使用系统默认程序打开
            os.startfile(str(script_path))
            return True

        # 创建异步子进程
        result = await ProcessRunner.run_process(
            *cmd, cwd=script_path.parent, timeout=600
        )

        if result.returncode == 0:
            logger.success(f"{task_name}执行成功, 输出:\n{result.stdout}")
            return True
        else:
            logger.error(f"{task_name}执行失败({result.returncode}):")
            logger.error(f"  - 标准输出:{result.stdout}")
            logger.error(f"  - 错误输出:{result.stderr}")
            return False

    except Exception as e:
        logger.exception(f"执行{task_name}时出现异常: {e}")
        return False
