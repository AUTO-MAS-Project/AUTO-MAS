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


import asyncio
import os
import psutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from .platform.power import power
from .platform.startup import startup
from app.utils import get_logger
from app.utils.platform.process import platform_process
from app.utils.platform import IS_WINDOWS


logger = get_logger("系统服务")


@dataclass(frozen=True, slots=True)
class _ProcessPathScan:
    """按可执行文件路径扫描进程的结果。"""

    pids: list[int]
    uncertain_pids: list[int]
    complete: bool


class _SystemHandler:
    countdown = 60

    def __init__(self) -> None:
        self.power_task: Optional[asyncio.Task] = None

    async def set_Sleep(self, if_allow_sleep: bool) -> None:
        """
        设置系统休眠

        Parameters
        ----------
        if_allow_sleep: bool
            是否允许系统休眠
        """

        if IS_WINDOWS:
            await power.set_sleep_prevention(if_allow_sleep)

    async def set_SelfStart(self, if_self_start: bool) -> None:
        """设置程序开机自启。"""

        if (
            os.getenv("AUTO_MAS_ENV") == "development"
            or not IS_WINDOWS
        ):
            return
        await startup.set_enabled(if_self_start)

    async def set_power(
        self,
        mode: Literal[
            "NoAction",
            "Shutdown",
            "ShutdownForce",
            "Reboot",
            "Hibernate",
            "Sleep",
            "KillSelf",
            "Logoff",
        ],
        from_frontend: bool = False,
    ) -> None:
        """
        执行系统电源操作

        :param mode: 电源操作
        """

        from app.core import Config

        if mode == "NoAction":
            logger.info("不执行系统电源操作")
            return

        if mode == "KillSelf" and Config.server is not None:
            logger.info("执行退出主程序操作")
            if not from_frontend:
                await Config.send_websocket_message(
                    id="Main", type="Signal", data={"RequestClose": "请求前端关闭"}
                )
            Config.server.should_exit = True
            return

        if mode not in power.supported_actions:
            raise RuntimeError(f"当前平台不支持电源操作: {mode}")
        if mode in {"Shutdown", "Reboot", "Logoff"}:
            await self.kill_emulator_processes()
        logger.info(f"执行电源操作: {mode}")
        await power.execute(mode)

    async def _power_task(
        self,
        power_sign: Literal[
            "NoAction",
            "Shutdown",
            "ShutdownForce",
            "Reboot",
            "Hibernate",
            "Sleep",
            "KillSelf",
            "Logoff",
        ],
    ) -> None:
        """电源任务"""

        await asyncio.sleep(self.countdown)
        await self.set_power(power_sign)

    async def start_power_task(self):
        """开始电源任务"""

        from app.core import Config

        if self.power_task is None or self.power_task.done():
            self.power_task = asyncio.create_task(self._power_task(Config.power_sign))
            logger.info(
                f"电源任务已启动, {self.countdown}秒后执行: {Config.power_sign}"
            )
            Config.power_sign = "NoAction"
        else:
            logger.warning("已有电源任务在运行, 请勿重复启动")

    async def cancel_power_task(self):
        """取消电源任务"""

        if self.power_task is not None and not self.power_task.done():
            self.power_task.cancel()
            try:
                await self.power_task
            except asyncio.CancelledError:
                logger.info("电源任务已取消")
        else:
            logger.warning("当前无电源任务在运行")
            raise RuntimeError("当前无电源任务在运行")

    async def kill_emulator_processes(self):
        """这里暂时仅支持 MuMu 模拟器"""

        logger.info("正在清除模拟器进程")

        keywords = ["Nemu", "nemu", "emulator", "MuMu"]
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                pname = proc.info["name"].lower()
                if any(keyword.lower() in pname for keyword in keywords):
                    proc.kill()
                    logger.info(f"已关闭 MuMu 模拟器进程: {proc.info['name']}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        logger.success("模拟器进程清除完成")

    async def is_startup(self) -> bool:
        """判断程序是否已经开机自启"""

        if not IS_WINDOWS:
            return False
        return await startup.is_enabled()

    # async def get_window_info(self) -> list:
    #     """获取当前前台窗口信息"""

    #     def callback(hwnd, window_info):
    #         if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
    #             _, pid = win32process.GetWindowThreadProcessId(hwnd)
    #             process = psutil.Process(pid)
    #             window_info.append((win32gui.GetWindowText(hwnd), process.exe()))
    #         return True

    #     window_info = []
    #     win32gui.EnumWindows(callback, window_info)
    #     return window_info

    async def kill_process(
        self, path: Path | str, *, kill_tree: bool = True
    ) -> bool:
        """根据路径中止进程。

        Args:
            path (Path | str): 目标进程路径。
            kill_tree (bool): 是否同时中止子进程树。

        Returns:
            bool: 所有匹配进程均成功中止时返回 True。
        """

        path = Path(path)
        logger.info(f"开始中止进程: {path}")

        scan = await self._scan_processes_by_path(path)
        success = scan.complete
        first_error: Exception | None = None
        if scan.uncertain_pids:
            logger.warning(
                f"存在无法确认路径的同名进程: {path.name}, PID: {scan.uncertain_pids}"
            )

        for pid in scan.pids:
            try:
                pid_success = await self.kill_process_by_pid(pid, kill_tree=kill_tree)
            except Exception as e:
                pid_success = False
                if first_error is None:
                    first_error = e
                logger.opt(exception=True).warning(
                    f"进程中止异常 PID: {pid}, 原因: {e}"
                )
            if not pid_success:
                success = False

        if first_error is not None:
            raise first_error
        if success:
            logger.success(f"进程已中止: {path}")
        return success

    async def kill_process_by_pid(self, pid: int, *, kill_tree: bool = True) -> bool:
        """根据 PID 中止进程。

        Args:
            pid (int): 目标进程 PID。
            kill_tree (bool): 是否同时中止子进程树。

        Returns:
            bool: 进程成功终止时返回 True。
        """

        logger.info(f"开始中止进程 PID: {pid}")
        succeeded, reason = await platform_process.kill_process(pid, kill_tree)
        if not succeeded:
            if not psutil.pid_exists(pid):
                logger.info(f"进程已自行退出 PID: {pid}")
                return True

            logger.warning(f"进程中止失败 PID: {pid}, {reason}")
            return False

        logger.success(f"进程已中止 PID: {pid}")
        return True

    async def _scan_processes_by_path(self, path: Path | str) -> _ProcessPathScan:
        """扫描精确路径进程，并记录无法确认路径的同名候选。"""

        path = Path(path)
        pids: list[int] = []
        uncertain_pids: list[int] = []
        complete = True
        target_path = str(path).casefold()
        target_name = path.name.casefold()

        try:
            processes = psutil.process_iter(["pid", "name", "exe"])
            for proc in processes:
                try:
                    info = proc.info
                except (psutil.NoSuchProcess, psutil.ZombieProcess):
                    continue

                process_path = info.get("exe")
                if process_path:
                    if str(process_path).casefold() == target_path:
                        pids.append(info["pid"])
                    continue

                process_name = info.get("name")
                if process_name and str(process_name).casefold() == target_name:
                    uncertain_pids.append(info["pid"])
        except (psutil.AccessDenied, OSError) as e:
            complete = False
            logger.warning(f"扫描进程路径失败: {e}")

        return _ProcessPathScan(
            pids=pids,
            uncertain_pids=uncertain_pids,
            complete=complete,
        )

    async def search_pids(self, path: Path | str) -> list[int]:
        """
        根据路径查找进程PID

        :param path: 进程路径
        :return: 匹配的进程PID列表
        """

        logger.info(f"开始查找进程 PID: {path}")

        return (await self._scan_processes_by_path(path)).pids


System = _SystemHandler()
