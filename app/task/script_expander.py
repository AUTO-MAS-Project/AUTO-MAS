"""L2：按任务根的托管快照派发；内建专项交 manager，插件继续 L3/L4。"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from app.config import LockTicket
from app.core import Config, Notify, Publisher
from app.core.ws import protocol
from app.models.schema import WSTaskCompletedData, WSTaskNoticeData
from app.models.task import TaskItem, TaskMode, TaskScriptItem, TaskTriggerReason
from app.services import execute_script_task
from app.task.context import TaskContext
from app.task.history_core import TaskHistorySession
from app.task.lifecycle import TaskBase
from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed
from app.utils.contracts.power import PowerSignal

if TYPE_CHECKING:
    from app.core.community.scheduling import CommunityTriggerSource
    from app.core.notify.coordinator import TaskReportCoordinator
    from app.core.task_manager import _TaskManager
    from app.models.config import ScriptConfigType
    from app.models.task import TaskExecuteBase
    from app.task.user_expander import UserExpander


class ScriptExpander(TaskBase):
    def __init__(self, info: TaskItem, dispatcher: _TaskManager) -> None:
        super().__init__()
        self.task_info = info
        self.dispatcher = dispatcher
        self.context = TaskContext()
        self._manager: TaskExecuteBase | None = None
        self._plugin: UserExpander | None = None
        self._script_ticket: LockTicket | None = None
        self._script_config: ScriptConfigType | None = None
        self._started_at = time.perf_counter()
        # [兼容旧专项] 隐藏的手动更新标记；新代码按标准 TaskMode 分派。
        self.maintenance = False
        self.history = TaskHistorySession(info)
        self.report_coordinator: TaskReportCoordinator | None = None
        self._callback_failed = False
        from app.core.script_update import ScriptUpdateSession

        self._updates = ScriptUpdateSession(
            info,
            make_manager=self._make_prefetch_manager,
            # 预下载复用当前旧专项的更新确认点与限时强清理，不另建停止框架。
            process_scope=lambda: (
                self._manager.execution._process_scope
                if self._manager is not None
                else None
            ),
        )

    async def stop(self) -> None:
        self.history.cancelled = True
        await self.task_info.set_state(status="cancelled")
        if self._manager is not None:
            self._manager.stopped_manually = True
            self._manager._on_finalize_cancel_requested()
        await super().stop()

    async def main_task(self) -> None:
        from app.services import telemetry

        info = self.task_info
        with telemetry.observe_span(
            name="AUTO-MAS task",
            op="auto_mas.task.run",
            attributes={
                "mode": "Update" if self.maintenance else info.mode,
                "trigger": telemetry.task_trigger_category(info.info.trigger),
            },
            force_transaction=True,
        ):
            await self._run_task()

    async def _run_task(self) -> None:
        info = self.task_info
        await info.set_state(status="running")
        if info.mode == TaskMode.AUTO_PROXY:
            from app.core.desktop_guard import ensure_desktop_available

            await ensure_desktop_available()
            from app.core.notify.task_report import receive_task_community_results
            from app.core.timer import MainTimer

            coordinator = Notify.create_task_report_coordinator(info)
            self.report_coordinator = coordinator
            community_source: CommunityTriggerSource = (
                "task_scheduled"
                if info.info.trigger
                in (TaskTriggerReason.TIMED, TaskTriggerReason.CYCLE)
                else "task_startup"
                if info.info.trigger == TaskTriggerReason.STARTUP
                else "task_manual"
            )
            MainTimer.schedule_community_for_task(
                source=community_source,
                on_completed=lambda results: receive_task_community_results(
                    coordinator, results
                ),
            )
        await self._run_extra_script(info.execution.script_before, "队列运行前脚本")
        for index, script in enumerate(info.script_list):
            if self.cancelled:
                raise asyncio.CancelledError
            await info.set_current_index(index)
            if (
                script._run_days is not None
                and datetime.now().astimezone().strftime("%A") not in script._run_days
            ):
                await script.set_state(status="跳过")
                continue
            from app.core.script_update_queue import (
                script_task_completed,
                script_task_retrying,
            )

            self._updates.watch(script, index + 1)
            token = script_task_completed.set(self._updates.mark_completed)
            retry_token = script_task_retrying.set(
                lambda: self._updates.retry(script, index + 1)
            )
            try:
                with Notify.task_notification_batch(
                    task_id=info.task_id, coordinator=self.report_coordinator
                ):
                    await self._run_script(script)
            finally:
                script_task_retrying.reset(retry_token)
                script_task_completed.reset(token)
                await self._updates.finish(
                    cancelled=self.cancelled or script.info.status in ("异常", "已取消")
                )
        # 附加脚本属于可中止的业务流程，直接 await，停止时不启动后续动作。
        await self._run_extra_script(info.execution.script_after, "队列运行后脚本")
        if self.cancelled:
            raise asyncio.CancelledError
        await info.set_state(
            status="error"
            if self._callback_failed
            or any(s.status == "异常" for s in info.scripts.values())
            else "success"
        )

    def _make_prefetch_manager(self, script: TaskScriptItem) -> TaskExecuteBase | None:
        """只复用旧专项已提供的下载入口，不探测或构造插件执行器。"""
        if self.maintenance or self.dispatcher.plugin_expander is not None:
            return None
        entry = Config.ScriptConfig.get(script.info.script_id)
        if entry is None:
            return None
        factory = self.dispatcher.manager_factories.get(type(entry))
        if factory is None:
            return None
        manager = factory(script)
        return manager if hasattr(manager, "prefetch_script_update") else None

    async def _run_extra_script(self, path: Path | None, label: str) -> None:
        """按受理快照复用基础脚本执行器；普通失败提示后继续，取消向上传播。"""
        if self.cancelled:
            raise asyncio.CancelledError
        if path is None:
            return
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="info", message=f"开始执行{label}"),
        )
        if self.cancelled:
            raise asyncio.CancelledError
        succeeded = await execute_script_task(path, label)
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(
                level="info" if succeeded else "warning",
                message=f"{label}执行{'成功' if succeeded else '失败'}",
            ),
        )

    async def _run_script(self, script: TaskScriptItem) -> None:
        from app.services import telemetry

        entry: ScriptConfigType
        try:
            candidate: ScriptConfigType | None = Config.ScriptConfig.get(
                script.script_id
            )
            if candidate is None or (
                script._config_ref is not None and script._config_ref() is not candidate
            ):
                raise ValueError("托管配置已删除或替换")
            entry = candidate
            await script.set_current_index(-1)
            await script.set_state(status="等待")
            if Config.ScriptConfig.get(script.script_id) is not entry:
                raise ValueError("托管配置已删除或替换")
            with telemetry.observe_script_run(
                self.task_info,
                script,
                mode="Update" if self.maintenance else self.task_info.mode,
            ):
                # 插件接入位置：真实解析器在托管锁内接收当前配置，提供 L3 与模式能力。
                plugin = None
                if not self.maintenance and self.dispatcher.plugin_expander is not None:
                    last_wait_message = None
                    while True:
                        candidate = Config.ScriptConfig.get(script.script_id)
                        if candidate is None or (
                            script._config_ref is not None
                            and script._config_ref() is not candidate
                        ):
                            raise ValueError("托管配置已删除或替换")
                        ticket = await candidate.try_lock_x(cascade=False)
                        if ticket is not None:
                            self._script_ticket = ticket
                            self._script_config = candidate
                            entry = candidate
                            break
                        holders = self.dispatcher.describe_lock_holders(
                            candidate, cascade=False
                        )
                        message = f"等待托管配置「{candidate.Info.Name}」的 X 锁，当前占用：{holders}。"
                        if message != last_wait_message:
                            script.current.log = script.current.log + message + "\n"
                            await script.commit()
                            last_wait_message = message
                        await asyncio.sleep(1)
                    if Config.ScriptConfig.get(script.script_id) is not entry:
                        raise ValueError("托管配置已删除或替换")
                    plugin = self.dispatcher.plugin_expander(script, entry)
                    if plugin is None:
                        # 旧 manager 自持递归锁，必须先归还探测锁，不能叠加持锁等待。
                        await self._release_script_lock()
                if plugin is not None:
                    from app.task.user_expander import UserExpander

                    if (
                        not isinstance(plugin, UserExpander)
                        or plugin.script_info is not script
                        or plugin.script_config is not entry
                    ):
                        raise TypeError("插件必须绑定当前托管运行节点及已锁配置")
                    plugin.context = self.context.with_params(script.info.params)
                    self._plugin = plugin
                    await self.spawn(plugin)
                else:
                    if Config.ScriptConfig.get(script.script_id) is not entry:
                        raise ValueError("托管配置已删除或替换")
                    factory = self.dispatcher.manager_factories.get(type(entry))
                    manager = await self._updates.take(script.uid)
                    if manager is None:
                        manager = factory(script) if factory is not None else None
                    if manager is None:
                        raise ValueError("该托管没有内建执行能力")
                    self._manager = manager
                    # [兼容旧专项] 仅向旧 manager 传递隐藏更新语义。
                    manager.maintenance = self.maintenance
                    manager.history = self.history
                    manager.context = self.context.with_params(script.info.params)
                    script._manager_controls_users = True
                    # 旧 manager 自行持锁、展开用户、执行和收尾；L2 不再重复这些操作。
                    try:
                        await manager._execute_task()
                    finally:
                        await manager.callbacks.close()
                        self._callback_failed |= bool(manager.callbacks.errors)
                if any("异常" in u.status for u in script.users.values()):
                    await script.set_state(status="异常")
        except asyncio.CancelledError:
            await script.set_state(status="已取消")
            raise
        except Exception as error:
            await script.set_log(str(error))
            await script.set_state(status="异常")
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=str(error)),
            )
        finally:
            await self._release_script_lock()
            self._manager = None
            self._plugin = None
            self.history.observe(script)
            script._manager_controls_users = False

    async def _release_script_lock(self) -> None:
        if self._script_ticket is not None:
            assert self._script_config is not None
            await self._script_config.unlock(self._script_ticket)
            self._script_ticket = None
            self._script_config = None

    async def on_crash(self, exc: BaseException) -> None:
        try:
            await self.task_info.set_state(status="error")
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=str(exc)),
            )
        except Exception as failure:
            await super().on_crash(failure)
        await super().on_crash(exc)

    async def final_task(self) -> None:
        try:
            try:
                await self._updates.close()
            except FluxdownCancelUnconfirmed as error:
                # 未确认停写必须保持为错误，但重复看到同一个失败不应
                # 中断历史收尾和 TASK_COMPLETED 发布，也不重复发送通知。
                if not isinstance(self.error, FluxdownCancelUnconfirmed):
                    self.error = error
                    await self.on_crash(error)
        finally:
            await self._release_script_lock()
        info = self.task_info
        if isinstance(self.error, FluxdownCancelUnconfirmed):
            await info.set_state(status="error")
        elif self.cancelled:
            await info.set_state(status="cancelled")
        elif self.error:
            await info.set_state(status="error")
        self.history.cancelled |= self.cancelled
        await self.history.close()
        if self.report_coordinator is not None:
            self.report_coordinator.finish()
        if (
            not self.cancelled
            and self.error is None
            and info.mode == TaskMode.AUTO_PROXY
            and info.execution.after_accomplish != PowerSignal.NO_ACTION
        ):
            from app.core import Power

            await Power.set_signal(
                info.execution.after_accomplish,
                overwrite=False,
                delay=info.execution.after_accomplish_delay * 60,
            )

        await Publisher.send(
            id=info.task_id,
            type=protocol.TASK_COMPLETED,
            data=WSTaskCompletedData.model_validate(
                {
                    "result": info.info.result,
                    "outcome": info.status,
                    "error": str(self.error) if self.error else None,
                    "task": info.get_update(),
                }
            ),
        )
        from app.services import telemetry

        attrs = {
            "mode": "Update" if self.maintenance else info.mode,
            "trigger": telemetry.task_trigger_category(info.info.trigger),
            "outcome": info.status,
        }
        telemetry.record_count("auto_mas.task.runs", attributes=attrs)
        telemetry.record_distribution(
            "auto_mas.task.duration",
            (time.perf_counter() - self._started_at) * 1000,
            unit="millisecond",
            attributes=attrs,
        )
