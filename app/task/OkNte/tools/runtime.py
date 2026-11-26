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
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""OK-NTE 源码 / 冻结包的目录与本体进程识别。"""

import asyncio
import shlex
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

import psutil

from app.models.config import OkNteConfig
from app.task.pyappify_startup import open_launcher_logs, wait_for_launcher_process
from app.utils import ProcessInfo, ProcessManager, get_logger, process
from app.utils.common.process.operations import iter_scoped_process_info

logger = get_logger("OK-NTE 运行入口")


def runtime_dir(root: Path) -> Path:
    """独立 body 包在根目录运行，带启动器的安装在 working 运行。"""
    if (root / "ok-nte.exe").is_file() and (root / "_internal").is_dir():
        return root
    return root / "data/apps/ok-nte/working"


def runtime_executables(root: Path) -> list[Path]:
    """同时保留两种本体候选，允许启动器在更新后更换运行方式。"""
    return [
        runtime_dir(root) / "ok-nte.exe",
        root / "data/apps/ok-nte/python/pythonw.exe",
    ]


class OkNteProcessManager(ProcessManager):
    """只在当前安装内识别本体；兼容旧自动路径，保留自定义追踪条件。"""

    def __init__(self, config: OkNteConfig):
        super().__init__(reseek_target=True)
        self.config = config
        self.root = config.Info.RootPath
        if self.root is None:
            raise ValueError("RootPath未配置，请检查路径设置")
        self._automatic_target_info: ProcessInfo | None = None

    def _custom_target(self) -> ProcessInfo | None:
        name = str(self.config.Script.TrackProcessName or "").strip()
        exe = str(self.config.Script.TrackProcessExe or "").strip()
        cmdline = str(self.config.Script.TrackProcessCmdline or "").strip()
        defaults = runtime_executables(self.root)
        if (
            (not name or name in {"pythonw.exe", "ok-nte.exe"})
            and (not exe or Path(exe) in defaults)
            and not cmdline
        ):
            return None
        return ProcessInfo(
            name=name or None,
            exe=exe or None,
            cmdline=shlex.split(cmdline, posix=False) if cmdline else None,
        )

    async def open_oknte(
        self,
        program: Path | str,
        *args: str,
        use_custom_target: bool = True,
        require_runtime: bool = False,
        on_log: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        """启动上游入口，按自定义条件或实际本体接管生命周期。"""
        track = require_runtime or self.config.Script.IfTrackProcess
        custom = self._custom_target() if track and use_custom_target else None
        launcher = (
            Path(program) == self.root / "ok-nte.exe"
            and runtime_dir(self.root) != self.root
        )
        if not track or not launcher:
            started = time.time()
            await self.open_process(
                program, *args, target_process=custom, retain_desktop_descendants=track
            )
            if track and custom is None:
                await self.search_runtime_process(min_create_time=started)
            return

        log_dir = self.root / "logs"
        sources = await asyncio.to_thread(open_launcher_logs, log_dir)
        started = time.monotonic()
        started_at = time.time()
        await self.open_process(program, *args, retain_desktop_descendants=True)

        async def search(timeout_seconds: float) -> None:
            if custom is not None:
                await self.search_process(
                    custom, timeout_seconds=timeout_seconds, min_create_time=started_at
                )
            else:
                await self.search_runtime_process(
                    timeout_seconds=timeout_seconds, min_create_time=started_at
                )

        async def report(message: str) -> None:
            if on_log is None:
                logger.info(message)
            else:
                await on_log(message)

        # 启动时检查版本本身不延长无更新时的等待。
        try:
            await wait_for_launcher_process(
                log_dir,
                sources,
                app_id="ok-nte",
                started=started,
                search_process=search,
                on_log=report,
                include_update_check=False,
            )
        except BaseException:
            # 对齐父类显式目标启动失败时的分身进程收尾。
            if custom is not None and self._desktop_process is not None:
                await self.clear()
            raise

    async def search_runtime_process(
        self,
        timeout_seconds: float = 60.0,
        min_create_time: float | None = None,
    ) -> None:
        """自动搜索本次安装的主进程；不改变父类显式目标搜索的契约。"""

        def scan() -> tuple[psutil.Process, float, str] | None:
            executables = runtime_executables(self.root)
            candidates: list[tuple[int, float, int, psutil.Process, str]] = []
            for proc, info in iter_scoped_process_info(
                ["exe", "cmdline", "create_time"]
            ):
                executable = info["exe"]
                if not executable or not info["cmdline"]:
                    continue
                # 冻结包的 multiprocessing worker 与 GUI 共用 EXE，不能当作本体。
                if "--multiprocessing-fork" in info["cmdline"]:
                    continue
                exe = Path(executable)
                created = info["create_time"]
                if exe not in executables or created is None:
                    continue
                if min_create_time is not None and created < min_create_time - 2:
                    continue
                candidates.append(
                    (executables.index(exe), created, proc.pid, proc, executable)
                )
            if not candidates:
                return None
            _, created, _, proc, executable = min(candidates)
            return proc, created, executable

        # 不依据磁盘残留文件决定模式：源码与冻结包文件可能同时存在。
        # 每轮重算候选，覆盖启动器更新期间才解压出来的新本体。
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            found = await asyncio.to_thread(scan)
            if found is not None:
                proc, created, executable = found
                target = ProcessInfo(exe=executable)
                self.target_process = proc
                self._target_info = target
                self._target_create_time = created
                self._automatic_target_info = target
                logger.info(f"已识别 OK-NTE 本体: {target.exe}, PID: {self.main_pid}")
                return
            await asyncio.sleep(0.1)
        raise RuntimeError(
            "未找到 OK-NTE 本体进程，请确认脚本已启动或检查自定义追踪设置"
        )

    async def _reseek_target(self) -> bool:
        # 显式目标仍走父类；只有自动识别的本体允许在源码 / 冻结入口间交接。
        if self._target_info is not self._automatic_target_info:
            return await super()._reseek_target()
        if self._target_create_time is None:
            return False
        try:
            await self.search_runtime_process(
                timeout_seconds=5,
                min_create_time=max(self._target_create_time, time.time() - 180),
            )
        except RuntimeError:
            return False
        logger.info(f"OK-NTE 已交接到后继本体进程: {self.main_pid}")
        return True

    def cleanup_executables(self) -> list[Path]:
        script_path = self.config.Script.ScriptPath
        if script_path is None:
            raise ValueError("ScriptPath未配置，请检查路径设置")
        paths = [script_path]
        paths.extend(runtime_executables(self.root))
        track_exe = str(self.config.Script.TrackProcessExe or "").strip()
        if track_exe:
            paths.append(Path(track_exe))
        return list(dict.fromkeys(paths))

    async def confirm_stopped(self, *, all_sessions: bool = False) -> bool:
        """按路径确认启动器、本体和配置的追踪目标已退出。"""
        stopped = True
        for exe in self.cleanup_executables():
            try:
                if not await process.is_process_stopped(exe, all_sessions=all_sessions):
                    stopped = False
                    logger.warning(f"无法确认 OK-NTE 进程已退出: {exe}")
            except Exception as e:
                stopped = False
                logger.opt(exception=True).warning(
                    f"复核 OK-NTE 进程退出状态失败: {exe}: {e}"
                )
        return stopped
