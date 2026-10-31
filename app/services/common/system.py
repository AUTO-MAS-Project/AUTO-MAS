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
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import psutil

from app.core import MainConnection, Publisher
from app.core.ws import protocol
from app.models.schema import PowerCountdownSnapshot, WSPowerCountdownData
from app.services import power, startup
from app.utils import LazyProxy, get_logger, process_platform
from app.utils import environment as _utils_environment

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
        # 应用生命周期注入，仅提供 AVD 关闭能力，不把宿主配置带进系统服务。
        self.avd_instance_closer: Callable[[], Awaitable[object]] | None = None
        self.power_task: Optional[asyncio.Task] = None
        self._power_cancelled_event_task: Optional[asyncio.Task] = None
        self.current_power_operation: Optional[str] = None
        self.current_power_remaining = 0

    def get_power_countdown_snapshot(self) -> PowerCountdownSnapshot:
        """返回当前电源倒计时的 HTTP 初始快照。"""

        # 延时阶段 remaining 为 0, 此时只是在等待, 不该被当作倒计时推给前端
        active = bool(
            self.power_task is not None
            and not self.power_task.done()
            and self.current_power_remaining > 0
        )
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
        if _utils_environment.is_development_environment():
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
            "RestartSelf",
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

        # 回放在后台复制；真正执行电源动作前给它有限的收尾窗口。
        from app.services.common.obs_replay import ObsReplay

        if not await ObsReplay.drain():
            logger.warning("失败回放尚未保存完成，继续执行电源操作")

        if mode in {"KillSelf", "RestartSelf"} and Config.server is not None:
            restart = mode == "RestartSelf"
            action = "重启" if restart else "退出"
            logger.info(f"执行{action}主程序操作")
            if not from_frontend:
                try:
                    await self._request_frontend_close(restart=restart)
                except TimeoutError as e:
                    # 退出 / 重启是用户设定的完成后操作或安装更新的要求，前端卡死不能让
                    # 后端就此留下不退；此前这里只抛异常，退出被静默放弃。
                    logger.error(f"{e}，仍继续{action}主程序")
            Config.server.should_exit = True
            return

        if mode not in power.supported_actions:
            raise RuntimeError(f"当前平台不支持电源操作: {mode}")
        # 强制关机（shutdown /f）不等程序退出，魔改 AVD 实例同样要先让安卓正常关机（不成再 sync 后关）；
        # 其余模拟器的进程清理仍只在原来三种操作上做
        if mode in {"Shutdown", "ShutdownForce", "Reboot", "Logoff"}:
            await self.close_avd_instances()
        if mode in {"Shutdown", "Reboot", "Logoff"}:
            await self.kill_emulator_processes()
        logger.info(f"执行电源操作: {mode}")
        # 系统电源动作必须先于前端关闭执行：请求前端退出会让 Electron 退出并连带结束后端进程，
        # 若先等前端断开，关机/重启等命令将永远没有机会执行（issue #611）。
        await power.execute(mode)

    async def _request_frontend_close(self, restart: bool = False) -> None:
        """请求前端退出或重启，并等待主会话断开（后端自行的 KillSelf / RestartSelf 场景）。"""

        action = "重启" if restart else "退出"
        sent = await Publisher.send(
            id=protocol.ID_MAIN,
            type=(
                protocol.FRONTEND_RESTART_REQUESTED
                if restart
                else protocol.FRONTEND_CLOSE_REQUESTED
            ),
        )
        if not sent:
            # 当前没有前端会话。退出时这本身已满足“前端关闭”前置条件；重启则没人接收信号，
            # 只能退到后端退出这一步（Runtime 监督下会被重新拉起），记一条日志免得看着像成功了。
            logger.info(f"当前无前端主连接，继续{action}主程序")
            if restart:
                logger.warning("重启请求没有前端接收，本次只重启后端进程")
            return

        disconnected = await MainConnection.wait_until_disconnected(
            timeout=self.frontend_close_timeout
        )
        if not disconnected:
            raise TimeoutError(
                f"前端未在 {self.frontend_close_timeout:g} 秒内断开主连接"
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
            "RestartSelf",
            "Logoff",
        ],
        delay: int = 0,
        *,
        before_power: Callable[[], Awaitable[bool]] | None = None,
    ) -> None:
        """电源任务：先静默等待队列设定的延时，再逐秒推送倒计时状态，归零后执行电源操作"""

        self.current_power_operation = power_sign
        try:
            if delay > 0:
                # 延时阶段保持静默：不推送倒计时，调度中心的电源标志仍显示待执行操作
                await asyncio.sleep(delay)
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
            if before_power is not None and not await before_power():
                logger.warning("后台任务收尾超时，继续执行电源操作")
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

    async def start_power_task(
        self, *, before_power: Callable[[], Awaitable[bool]] | None = None
    ):
        """开始电源任务"""

        if self.power_task is None or self.power_task.done():
            power_sign = Config.power_sign
            delay = Config.power_delay
            self._power_cancelled_event_task = None
            power_task = asyncio.create_task(
                self._power_task(
                    power_sign=power_sign, delay=delay, before_power=before_power
                )
            )

            def _on_done(done_task: asyncio.Task) -> None:
                # 电源任务无人 await，异常只能在这里取出记录，否则失败不留痕迹
                if done_task.cancelled():
                    return
                exc = done_task.exception()
                if exc is not None:
                    logger.opt(exception=exc).error(
                        f"电源操作 {power_sign} 执行失败: {type(exc).__name__}: {exc}"
                    )

            power_task.add_done_callback(_on_done)
            self.power_task = power_task
            logger.info(
                f"电源任务已启动, {delay + self.countdown}秒后执行: {power_sign}"
            )
            Config.power_sign = "NoAction"
            Config.power_delay = 0
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

    async def cancel_pending_power_task(self) -> None:
        """存在待执行的电源任务时取消它，没有则跳过。"""

        if self.power_task is not None and not self.power_task.done():
            await self.cancel_power_task()

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

    async def close_avd_instances(self) -> None:
        """按进程名强杀之前，先把在跑的魔改 AVD 实例正常关掉（安卓正常关机，不成再 sync + 关）。

        强杀不走客体关机流程，客体页缓存里没写回的数据会丢。整体限时（30 秒），出错只记日志，
        不拦住电源操作。
        """
        try:
            if self.avd_instance_closer is None:
                raise RuntimeError("未注入魔改 AVD 关闭能力")
            await self.avd_instance_closer()
        except Exception as e:  # noqa: BLE001 - 关不掉也要继续关机
            logger.warning(f"关闭魔改 AVD 实例失败，继续电源操作: {e}")

    async def kill_emulator_processes(self):
        """这里暂时仅支持 MuMu 模拟器"""

        logger.info("正在清除模拟器进程")

        keywords = ["Nemu", "nemu", "emulator", "MuMu"]

        def _kill_all() -> None:
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    pname = proc.info["name"].lower()
                    if any(keyword.lower() in pname for keyword in keywords):
                        proc.kill()
                        logger.info(f"已关闭 MuMu 模拟器进程: {proc.info['name']}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        await asyncio.to_thread(_kill_all)
        logger.success("模拟器进程清除完成")

    async def is_process_running(self, path: Path | str) -> bool:
        """按镜像路径判断该进程是否还在跑。

        Args:
            path (Path | str): 目标进程路径。

        Returns:
            bool: 有该路径的进程在跑时返回 True。读不出镜像路径的同名候选不算——
                那些进程无法归到这个路径上，与 `kill_process` 用同一套判据。
        """

        return bool((await self._scan_processes_by_path(path)).pids)

    async def is_process_stopped(self, path: Path | str) -> bool:
        """确认目标路径没有存活进程；扫描不完整或同名进程路径不可读时返回 False。"""

        scan = await self._scan_processes_by_path(path)
        return scan.complete and not scan.pids and not scan.uncertain_pids

    async def kill_process(self, path: Path | str, *, kill_tree: bool = True) -> bool:
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
        succeeded, reason = await process_platform.platform_process.kill_process(
            pid, kill_tree
        )
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
        target_path = str(path).casefold()
        target_name = path.name.casefold()

        def _scan() -> bool:
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
                logger.warning(f"扫描进程路径失败: {e}")
                return False
            return True

        complete = await asyncio.to_thread(_scan)

        return _ProcessPathScan(
            pids=pids,
            uncertain_pids=uncertain_pids,
            complete=complete,
        )


System = _SystemHandler()
