"""应用电源编排：管理待执行信号，订阅调度结束并持有唯一倒计时。"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from app.core import Config, Publisher
from app.core.ws import protocol
from app.models.schema import (
    PowerCountdownSnapshot,
    WSPowerCountdownData,
    WSPowerSignData,
)
from app.utils import get_logger, power

if TYPE_CHECKING:
    from app.core.task_manager import _TaskManager
    from app.models.task import TaskItem

logger = get_logger("电源管理")
type PowerSignal = Literal[
    "NoAction",
    "Shutdown",
    "ShutdownForce",
    "Reboot",
    "Hibernate",
    "Sleep",
    "KillSelf",
    "RestartSelf",
    "Logoff",
]


class _PowerManager:
    countdown = 60

    def __init__(self) -> None:
        from app.core.task_manager import _TaskManager

        self.signal: PowerSignal = "NoAction"
        self.delay = 0
        self.power_task: asyncio.Task[None] | None = None
        self.current_power_operation: PowerSignal | None = None
        self.current_power_remaining = 0
        self._power_task_lock = asyncio.Lock()
        self._power_cancelled_event_task: asyncio.Task | None = None
        self._executing = False
        self._exit_requested = False
        _TaskManager.task_ended.connect(self._on_task_ended)

    @property
    def active(self) -> bool:
        return self._executing or bool(self.power_task and not self.power_task.done())

    async def set_signal(
        self, signal: PowerSignal, *, overwrite: bool, delay: int = 0
    ) -> bool:
        """设置待执行意图；已有电源任务不覆盖，非强制设置仅填补空意图。"""
        if self.active or (not overwrite and self.signal != "NoAction"):
            return False
        if not overwrite and signal == "NoAction":
            return False
        self.signal, self.delay = signal, delay
        await Publisher.send(
            id=protocol.ID_MAIN,
            type=protocol.POWER_SIGN_UPDATED,
            data=WSPowerSignData(signal=signal),
        )
        return True

    async def _on_task_ended(self, sender: _TaskManager, *, task: TaskItem) -> None:
        """只在调度已注销任务后判定；不在信号接收链等待倒计时或后台工作。"""
        if not sender.idle or task.info.status == "cancelled":
            return
        await self.start_power_task()

    async def start_power_task(self) -> bool:
        """消费待执行意图并启动唯一倒计时；重复触发直接跳过。"""
        if self.active or self.signal == "NoAction":
            return False
        signal, delay = self.signal, self.delay
        self.signal, self.delay = "NoAction", 0
        self._power_cancelled_event_task = None
        task = asyncio.create_task(self._power_task(signal, delay))
        self.power_task = task

        def finished(done: asyncio.Task) -> None:
            if not done.cancelled() and (error := done.exception()) is not None:
                logger.opt(exception=error).error(f"电源操作 {signal} 失败")

        task.add_done_callback(finished)
        return True

    async def _power_task(self, signal: PowerSignal, delay: int) -> None:
        self.current_power_operation = signal
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            for remaining in range(self.countdown, 0, -1):
                self.current_power_remaining = remaining
                await Publisher.send(
                    id=protocol.ID_MAIN,
                    type=protocol.POWER_COUNTDOWN_UPDATED,
                    data=WSPowerCountdownData(operation=signal, remaining=remaining),
                )
                await asyncio.sleep(1)
            await self.set_power(signal, automatic=True)
        except asyncio.CancelledError:
            await self._publish_power_cancelled(asyncio.current_task())
            raise
        except Exception:
            await self._publish_power_cancelled(asyncio.current_task())
            raise
        finally:
            self.current_power_operation = None
            self.current_power_remaining = 0
            if not self._exit_requested:
                self._executing = False

    async def _cancel_automatic_power_for_schedule(
        self, mode: str, *, automatic: bool, at: datetime
    ) -> bool:
        from app.core import MainTimer, TaskManager

        if not automatic or not Config.setting.Start.IfScheduledWakeUp:
            return False
        if not TaskManager.idle or MainTimer.has_pending_wakeup_schedule(at):
            logger.info(f"定时队列即将或正在运行，取消本次自动完成后操作: {mode}")
            await self._publish_power_cancelled(asyncio.current_task())
            return True
        return False

    async def set_power(
        self, mode: PowerSignal, from_frontend: bool = False, *, automatic: bool = False
    ) -> None:
        """执行原生操作后请求宿主退出；退出收尾由生命周期协调器独立持有。"""
        from app.core import MainTimer, ShutdownCoordinator

        if mode == "NoAction":
            return
        at = datetime.now().astimezone()
        if await self._cancel_automatic_power_for_schedule(
            mode, automatic=automatic, at=at
        ):
            return
        if mode not in {"KillSelf", "RestartSelf"}:
            from app.core import EmulatorManager

            if mode not in power.supported_actions:
                raise RuntimeError(f"当前平台不支持电源操作: {mode}")
            if mode in {"Shutdown", "ShutdownForce", "Reboot", "Logoff"}:
                try:
                    await asyncio.wait_for(
                        EmulatorManager.close_running_avd_instances(), 30
                    )
                except Exception as error:
                    logger.warning(f"关闭魔改 AVD 实例失败，继续电源操作: {error}")
            if mode in {"Shutdown", "Reboot", "Logoff"}:
                await EmulatorManager.kill_emulator_processes()
            if await self._cancel_automatic_power_for_schedule(
                mode, automatic=automatic, at=datetime.now().astimezone()
            ):
                return
        self._executing = True
        try:
            if mode not in {"KillSelf", "RestartSelf"}:
                # TODO(退出时序优化)：本轮保留先发系统动作再请求应用退出的顺序。
                # /t 0、/f 或睡眠可能先终止/暂停本进程，不能保证后台收尾及时完成。
                await power.execute(mode)
            self._exit_requested = True
            ShutdownCoordinator.request_exit(
                restart=mode == "RestartSelf",
                automatic=automatic,
                next_wake_at=MainTimer.next_scheduled_wakeup(at) if automatic else None,
                notify_frontend=not from_frontend,
            )
        except BaseException:
            self._executing = False
            self._exit_requested = False
            raise

    def get_power_countdown_snapshot(self) -> PowerCountdownSnapshot:
        active = bool(
            self.power_task
            and not self.power_task.done()
            and self.current_power_remaining > 0
        )
        return PowerCountdownSnapshot(
            active=active,
            operation=self.current_power_operation if active else None,
            remaining=self.current_power_remaining if active else 0,
        )

    async def _publish_power_cancelled(self, task: asyncio.Task | None) -> None:
        if task is not None and self._power_cancelled_event_task is task:
            return
        self._power_cancelled_event_task = task
        await Publisher.send(
            id=protocol.ID_MAIN, type=protocol.POWER_COUNTDOWN_CANCELLED
        )

    async def cancel_power_task(self) -> bool:
        """撤销待执行意图及倒计时；已交给系统或退出协调器的操作不能再撤销。"""
        if self._executing:
            return False
        self.signal, self.delay = "NoAction", 0
        async with self._power_task_lock:
            if self._executing:
                return False
            task = self.power_task
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                await self._publish_power_cancelled(task)
        return True


Power = _PowerManager()

__all__ = ["Power"]
