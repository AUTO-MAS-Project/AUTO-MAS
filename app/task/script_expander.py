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
from app.models.config import ScriptEntry
from app.models.schema import WSTaskCompletedData, WSTaskNoticeData
from app.models.task import TaskItem, TaskMode, TaskScriptItem, TaskTriggerReason
from app.services import execute_script_task
from app.task.context import TaskContext
from app.task.history_core import TaskHistorySession
from app.task.lifecycle import TaskBase
from app.task.script_update import ScriptRecoverySession
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
        """绑定 L2 任务与调度器，建立历史、恢复和预下载会话，并初始化新旧专项执行与锁状态。"""
        super().__init__()
        self.task_info = info
        self.dispatcher = dispatcher
        self.context = TaskContext()
        self._manager: TaskExecuteBase | None = None
        self._plugin: UserExpander | None = None
        self._plugin_process_scope = None
        self._plugin_stop_checks: asyncio.Task | None = None
        self._script_ticket: LockTicket | None = None
        self._script_config: ScriptConfigType | None = None
        self._started_at = time.perf_counter()
        # [兼容旧专项] 隐藏的手动更新标记；新代码按标准 TaskMode 分派。
        self.maintenance = False
        self.history = TaskHistorySession(info)
        # L2 持有恢复事件与汇总；TODO(脚本更新迁移)：旧 manager 的检查、安装和恢复也统一上移至此层。
        self._recovery = ScriptRecoverySession(info)
        self.report_coordinator: TaskReportCoordinator | None = None
        self._callback_failed = False
        from app.task.prefetch import PrefetchSession

        self._prefetch = PrefetchSession(info, dispatcher.manager_factories)

    async def stop(self) -> None:
        """先确认插件更新停写及原生配置保存，再取消任务并等待级联收尾。"""
        self.history.cancelled = True
        await self.task_info.set_state(status="cancelled")
        if self._plugin_process_scope is not None:
            if self._plugin_stop_checks is None:
                self._plugin_stop_checks = asyncio.create_task(
                    self._plugin_process_scope.run_checks()
                )
            await asyncio.shield(self._plugin_stop_checks)
        if self._manager is not None:
            self._manager.stopped_manually = True
            self._manager._on_finalize_cancel_requested()
        await super().stop()

    async def main_task(self) -> None:
        """建立整次任务的遥测与安装恢复作用域，在其中执行 L2 调度主流程。"""
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
            with self._recovery.bind():
                await self._run_task()

    async def _run_task(self) -> None:
        """启动任务公共准备与预下载，依次调度脚本节点，并根据执行结果设置本次任务状态。"""
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
        if not self.maintenance:
            await self._prefetch.start()
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
            with Notify.task_notification_batch(
                task_id=info.task_id, coordinator=self.report_coordinator
            ):
                await self._run_script(script)
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
        """确认专项配置身份并取得所需锁，复查预下载后选择插件 L3 或旧管理器执行，结束时释放资源并记录历史。"""
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
                        name = (
                            candidate.info.name
                            if isinstance(candidate, ScriptEntry)
                            else candidate.Info.Name
                        )
                        message = (
                            f"等待托管配置「{name}」的 X 锁，当前占用：{holders}。"
                        )
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
                    await self._prefetch.prepare(script, entry)
                    plugin.context = self.context.with_params(script.info.params)
                    plugin.history = self.history
                    self._plugin = plugin
                    await self._run_plugin(plugin)
                else:
                    if Config.ScriptConfig.get(script.script_id) is not entry:
                        raise ValueError("托管配置已删除或替换")
                    factory = self.dispatcher.manager_factories.get(type(entry))
                    manager = factory(script) if factory is not None else None
                    if manager is None:
                        raise ValueError("该托管没有内建执行能力")
                    self._manager = manager
                    # [兼容旧专项] 仅向旧 manager 传递隐藏更新语义。
                    manager.maintenance = self.maintenance
                    manager.history = self.history
                    if not self.maintenance:

                        async def after_lock(locked_config):
                            """在旧专项取得配置锁后复查并等待预下载，将任务参数和 URL 路径映射绑定到专项运行上下文。"""
                            paths = await self._prefetch.prepare(script, locked_config)
                            manager.context = self.context.with_params(
                                script.info.params
                            )
                            from app.services.common.update.prefetch import (
                                prefetch_paths,
                            )

                            prefetch_paths.set(paths)

                        manager.after_config_lock = after_lock
                    manager.context = self.context.with_params(script.info.params)
                    script._manager_controls_users = True
                    # 旧 manager 自行持锁、展开用户、执行和收尾；L2 不再重复这些操作。
                    try:
                        from app.services.common.update.prefetch import prefetch_paths

                        # 锁后回调在 manager 的同一执行 Task 中设置，L4 参数保持原有隔离。
                        token = prefetch_paths.set({})
                        try:
                            await manager._execute_task()
                            if isinstance(
                                manager.execution.error, FluxdownCancelUnconfirmed
                            ):
                                raise manager.execution.error
                        finally:
                            prefetch_paths.reset(token)
                    finally:
                        await manager.callbacks.close()
                        self._callback_failed |= bool(manager.callbacks.errors)
                if any("异常" in u.status for u in script.users.values()):
                    await script.set_state(status="异常")
        except FluxdownCancelUnconfirmed:
            await script.set_state(status="异常")
            raise
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

    async def _run_plugin(self, plugin: UserExpander) -> None:
        """为插件运行登记独立进程归属与停止确认，沿当前持锁协程执行完整 L3 生命周期。"""
        from app.utils.common.process.scope import (
            TaskProcessScope,
            current_process_scope,
        )

        scope = TaskProcessScope()
        scope.add_check("update", scope.stop_updates, timeout=30)
        self._plugin_process_scope = scope
        self._plugin_stop_checks = None
        token = current_process_scope.set(scope)
        try:
            await self.spawn(plugin)
        finally:
            try:
                await scope.force_close()
            finally:
                current_process_scope.reset(token)
                self._plugin_process_scope = None

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
        """释放本次预下载和配置锁，结算取消或异常状态，完成恢复汇总、历史、通知及任务耗时记录。"""
        try:
            try:
                await self._prefetch.close()
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
        await self._recovery.publish_recovery_summary()
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
