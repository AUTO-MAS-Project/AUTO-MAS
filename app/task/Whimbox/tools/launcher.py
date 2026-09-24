#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""IProcessLauncher 默认实现 + 上游进程探测。

上游拉起事实：``spawn(<root>/python-embedded/python.exe, ['-s', '-m',
'whimbox.main'], {cwd: <root>})``，环境 PATH 前插 python-embedded 且
``PYTHONHOME=<root>/python-embedded``。**事实来源分级**：CLI 入口（含
``startOneDragon`` 分支）可在上游 Python 仓内核对（v3.0.5→v3.0.7 未改）；
env 与 spawn 布局来自发行版安装目录，Electron 壳源码不在该仓内、无法从上游
git 复核，按安装布局实证。MAS 无头拉起复刻同一入口（CLI 入口属「允许依赖」
白名单）。

提权与 env 的边界：``ProcessManager.open_process`` 的 elevated 分支走
ShellExecute（触发 UAC），不支持自定义 env；MAS 自身已提权时子进程继承
管理员令牌，走普通 spawn 分支、可带 env。两条路径下嵌入式 Python 的
home 解析以 ``python312._pth`` 布局为主，env 仅防御性复刻 app 行为。
"""

from __future__ import annotations

import os
from pathlib import Path

import psutil

from app.services import System
from app.task.Whimbox.tools.upstream import APP_EXE_NAME, REL_PYTHON_EXE
from app.utils import ProcessInfo, ProcessManager, get_logger
from app.utils.platform import IS_ELEVATED

logger = get_logger("奇想盒 进程启动")

# 无头一条龙 CLI 入口（上游 main.py:83-90，自 tag 1.3.6 起存在）
WHIMBOX_CLI_ARGS: tuple[str, ...] = ("-s", "-m", "whimbox.main", "startOneDragon")


def find_upstream_pids(root_path: Path) -> list[int]:
    """按安装根探测正在运行的上游进程（app 壳 + 后端 python），同步全扫。

    后端 python 以 exe 路径精确匹配（Path 比较对齐 ProcessManager 的
    match_process 惯例，嵌入式 python 与 MAS 自身解释器不同路径，不误伤）；
    app 壳按进程名匹配。属操作系统面的进程管理（MAS 领域），不读取上游
    内部状态。
    """

    pids: list[int] = []
    python_exe = Path(root_path) / REL_PYTHON_EXE
    for process in psutil.process_iter(["name", "exe"]):
        try:
            if process.info["name"] == APP_EXE_NAME:
                pids.append(process.pid)
                continue
            exe = process.info["exe"]
            if exe and Path(exe) == python_exe:
                pids.append(process.pid)
        except psutil.Error:
            continue
    return pids


class EmbeddedPythonLauncher:
    """IProcessLauncher 默认实现：复刻 app 的后端拉起方式。"""

    def __init__(self, root_path: Path, use_admin: bool) -> None:
        self.root_path = Path(root_path)
        self.use_admin = use_admin
        self.python_exe = self.root_path / REL_PYTHON_EXE
        self.process_manager = ProcessManager()
        # 按 exe 路径精确跟踪（python.exe 同名进程多，不能只按名字匹配）
        self.target_process = ProcessInfo(
            name="python.exe", exe=str(self.python_exe), cmdline=None
        )
        self.started = False

    def _build_env(self) -> dict[str, str]:
        """复刻 app 的 buildEnv：PATH 前插 python-embedded + PYTHONHOME。"""

        env = dict(os.environ)
        python_dir = str(self.python_exe.parent)
        parts = env.get("PATH", "").split(os.pathsep)
        if python_dir not in parts:
            env["PATH"] = python_dir + os.pathsep + env.get("PATH", "")
        env["PYTHONHOME"] = python_dir
        return env

    async def spawn(self) -> None:
        """拉起无头一条龙（cwd=安装根，configs/logs 相对 cwd 解析）。"""

        # 仅当 MAS 自身未提权时才走 runas 触发 UAC；已提权时子进程自动继承，
        # 并可带 env（ShellExecute 分支不支持 env，见模块注释）
        need_uac = self.use_admin and not IS_ELEVATED
        await self.process_manager.open_process(
            self.python_exe,
            *WHIMBOX_CLI_ARGS,
            cwd=self.root_path,
            target_process=self.target_process,
            elevated=need_uac,
            env=None if need_uac else self._build_env(),
        )
        self.started = True
        logger.info(
            f"已启动奇想盒无头一条龙: {self.python_exe} "
            f"{' '.join(WHIMBOX_CLI_ARGS)} (cwd={self.root_path}, elevated={need_uac})"
        )

    async def is_running(self) -> bool:
        """无头进程是否仍在运行。"""

        if not self.started:
            return False
        return await self.process_manager.is_running()

    async def terminate(self) -> None:
        """终止无头进程（进程管理器 + 兜底按路径强杀，两步独立容错）。"""

        try:
            await self.process_manager.kill()
        except Exception as e:
            logger.opt(exception=True).warning(f"通过进程管理器中止奇想盒失败: {e}")
        try:
            await System.kill_process(self.python_exe)
        except Exception as e:
            logger.opt(exception=True).warning(f"中止奇想盒后端进程失败: {e}")
