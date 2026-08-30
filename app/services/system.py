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

from app.core.ws import MainConnection, Publisher, protocol
from app.models.schema import PowerCountdownSnapshot, WSPowerCountdownData
from app.utils import LazyProxy, get_logger
from app.utils.platform.process import platform_process

from .platform.power import power
from .platform.startup import startup

logger = get_logger("系统服务")

# 延迟加载 Config，避免 app.services 初始化期间触发 app.core 循环导入
Config = LazyProxy("app.core", "Config")


@dataclass(frozen=True, slots=True)
class _ProcessPathScan:
    """按可执行文件路径扫描进程的结果。"""

    pids: list[int]
    uncertain_pids: list[int]
    complete: bool


class _SystemHandler:
    countdown = 60
    frontend_close_timeout = 10.0

    def __init__(self) -> None:
        self.power_task: Optional[asyncio.Task] = None
        self._power_cancelled_event_task: Optional[asyncio.Task] = None
        self.current_power_operation: Optional[str] = None
        self.current_power_remaining = 0

    def get_power_countdown_snapshot(self) -> PowerCountdownSnapshot:
        """返回当前电源倒计时的 HTTP 初始快照。"""

        active = bool(self.power_task is not None and not self.power_task.done())
        return PowerCountdownSnapshot(
            active=active,
            operation=self.current_power_operation if active else None,
            remaining=self.current_power_remaining if active else 0,
        )

    async def set_Sleep(self, if_allow_sleep: bool) -> None:
        """
        设置系统休眠

        Parameters
        ----------
        if_allow_sleep: bool
            是否允许系统休眠
        """

        if not power.supported:
            # 该方法绑定在配置项上, 启动流程会无条件调用, 因此记录后跳过而非抛出
            logger.info(f"当前平台不支持阻止休眠, 跳过设置(目标值: {if_allow_sleep})")
            return
        await power.set_sleep_prevention(if_allow_sleep)

    async def set_SelfStart(self, if_self_start: bool) -> None:
        """设置程序开机自启。"""

        # 开发环境不管理需要提权的开机自启任务计划
        if os.getenv("AUTO_MAS_ENV") == "development":
            return
        if not startup.supported:
            # 同上, 启动流程会无条件调用, 记录后跳过
            logger.info(f"当前平台不支持开机自启, 跳过设置(目标值: {if_self_start})")
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

        if mode == "NoAction":
            logger.info("不执行系统电源操作")
            return

        if mode == "KillSelf" and Config.server is not None:
            logger.info("执行退出主程序操作")
            if not from_frontend:
                await self._request_frontend_close()
            Config.server.should_exit = True
            return

        if mode not in power.supported_actions:
            raise RuntimeError(f"当前平台不支持电源操作: {mode}")
        if mode in {"Shutdown", "Reboot", "Logoff"}:
            await self.kill_emulator_processes()
        logger.info(f"执行电源操作: {mode}")
        await self._request_frontend_close()
        await power.execute(mode)

    async def _request_frontend_close(self) -> None:
        """请求前端退出，并等待主会话断开后才允许执行系统动作。"""

        sent = await Publisher.send(
            id=protocol.ID_MAIN, type=protocol.FRONTEND_CLOSE_REQUESTED
        )
        if not sent:
            # 当前没有前端会话，本身已满足“前端关闭”前置条件。
            logger.info("当前无前端主连接，继续执行系统电源操作")
            return

        disconnected = await MainConnection.wait_until_disconnected(
            timeout=self.frontend_close_timeout
        )
        if not disconnected:
            raise TimeoutError(
                "前端未在规定时间内完成关闭，已取消系统电源操作"
            )

        # 主连接断开是 renderer 退出的可观测边界；给 Electron 窗口销毁留出短暂调度时间。
        await asyncio.sleep(0.2)

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
        """电源任务：逐秒推送倒计时状态，归零后执行电源操作"""

        self.current_power_operation = power_sign
        try:
            for remaining in range(self.countdown, 0, -1):
                self.current_power_remaining = remaining
                await Publisher.send(
                    id=protocol.ID_MAIN,
                    type=protocol.POWER_COUNTDOWN_UPDATED,
                    data=WSPowerCountdownData(
                        operation=power_sign, remaining=remaining
                    ),
                )
                await asyncio.sleep(1)
            await self.set_power(power_sign)
        except asyncio.CancelledError:
            await self._publish_power_cancelled(asyncio.current_task())
            raise
        except Exception:
            await self._publish_power_cancelled(asyncio.current_task())
            raise
        finally:
            self.current_power_operation = None
            self.current_power_remaining = 0

    async def start_power_task(self):
        """开始电源任务"""

        if self.power_task is None or self.power_task.done():
            power_sign = Config.power_sign
            self._power_cancelled_event_task = None
            power_task = asyncio.create_task(self._power_task(power_sign))
            self.power_task = power_task
            logger.info(
                f"电源任务已启动, {self.countdown}秒后执行: {power_sign}"
            )
            Config.power_sign = "NoAction"
        else:
            logger.warning("已有电源任务在运行, 请勿重复启动")

    async def _publish_power_cancelled(
        self, power_task: Optional[asyncio.Task]
    ) -> None:
        """按电源任务身份幂等发布取消事件。"""

        if power_task is not None and self._power_cancelled_event_task is power_task:
            return
        self._power_cancelled_event_task = power_task
        await Publisher.send(
            id=protocol.ID_MAIN, type=protocol.POWER_COUNTDOWN_CANCELLED
        )

    async def cancel_power_task(self):
        """取消电源任务"""

        power_task = self.power_task
        if power_task is not None and not power_task.done():
            power_task.cancel()
            try:
                await power_task
            except asyncio.CancelledError:
                logger.info("电源任务已取消")
            self.current_power_operation = None
            self.current_power_remaining = 0
            await self._publish_power_cancelled(power_task)
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
        """判断程序是否已经开机自启。

        平台不支持开机自启时抛出 UnsupportedPlatformError, 不与「未开启」
        共用 False; 调用方需在 API 边界转换为用户可见的错误。
        """

        return await startup.is_enabled()

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
