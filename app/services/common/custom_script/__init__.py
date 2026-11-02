#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
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


from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from app.services import custom_script_native
from app.utils import ProcessRunner, get_logger, process_platform
from app.utils.common.process.runner import ProcessResult

logger = get_logger("自定义脚本执行工具")


class ScriptProcessRunner(Protocol):
    """运行并等待命令；超时或取消时清理进程树，取消须继续上抛。"""

    def __call__(
        self,
        program: str,
        *args: str,
        cwd: Path,
        timeout: float,
        kill_tree_on_cancel: bool,
    ) -> Awaitable[ProcessResult]: ...


class CustomScriptExecutor:
    """MAS 自定义脚本执行能力；进程等待与系统默认打开由宿主装配。"""

    def __init__(
        self,
        *,
        run_process: ScriptProcessRunner,
        open_file: Callable[[str], Awaitable[None]],
    ) -> None:
        self._run_process = run_process
        self._open_file = open_file

    async def execute(self, script_path: Path | None, task_name: str) -> bool:
        """执行脚本并等待结束；普通失败返回 False，取消继续上抛。"""

        if script_path is None or not script_path.is_file():
            logger.warning(f"{task_name}脚本不存在")
            return False

        try:
            logger.info(
                f"开始执行{task_name}: {script_path}, 工作目录: {script_path.parent}"
            )

            if not script_path.suffix:
                logger.warning(f"{task_name}脚本没有指定后缀名, 无法执行")
                return False
            cmd = custom_script_native.build(script_path)
            if cmd is None:
                # 使用系统默认程序打开
                await self._open_file(str(script_path))
                return True

            # 创建异步子进程
            result = await self._run_process(
                *cmd,
                cwd=script_path.parent,
                timeout=600,
                kill_tree_on_cancel=True,
            )

            if result.returncode == 0:
                logger.success(
                    f"{task_name}进程正常退出(返回码: {result.returncode}), "
                    f"输出:\n{result.stdout}"
                )
                if result.stderr:
                    logger.warning(f"{task_name}错误输出:\n{result.stderr}")
                return True
            else:
                logger.warning(f"{task_name}执行失败({result.returncode}):")
                logger.warning(f"  - 标准输出:{result.stdout}")
                logger.warning(f"  - 错误输出:{result.stderr}")
                return False

        except Exception as e:
            logger.opt(exception=True).warning(f"执行{task_name}时出现异常: {e}")
            return False


execute_script_task = CustomScriptExecutor(
    run_process=ProcessRunner.run_process,
    open_file=process_platform.platform_process.open_protocol,
).execute
