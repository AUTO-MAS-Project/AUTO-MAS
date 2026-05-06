#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from __future__ import annotations

import asyncio
import inspect
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING


from pydantic import BaseModel

from app.models.task import ScriptItem, TaskExecuteBase, TaskItem, UserItem, LogRecord
from app.utils import get_logger
from app.utils.LogMonitor import LogMonitor
from app.utils.ProcessManager import ProcessManager

from .context import PluginContext
from .lifecycle_hooks import LifecycleHookRegistry, get_lifecycle_hooks
from .log_pipeline import (
    LogMonitorAdapter,
    LogPipeline,
    _LogPipelineHolder,
    get_log_handlers,
)
if TYPE_CHECKING:
    from loguru import Logger

_logger = get_logger("插件脚本基类")


# ── TaskContext ─────────────────────────────────────────────────────────


@dataclass
class TaskContext:
    """传递给所有生命周期钩子的可变上下文。"""

    script_info: ScriptItem
    task_info: TaskItem

    type_key: str = ""
    mode: str = ""

    script_config: dict[str, Any] = field(default_factory=dict)
    user_configs: list[dict[str, Any]] = field(default_factory=list)

    process_manager: ProcessManager | None = None
    log_monitor: LogMonitor | None = None
    log_pipeline: LogPipeline | None = None
    emulator_manager: Any = None

    script_root: Path | None = None
    exe_path: Path | None = None
    log_path: Path | None = None
    config_backup_path: Path | None = None

    wait_event: asyncio.Event = field(default_factory=asyncio.Event)

    extra: dict[str, Any] = field(default_factory=dict)
    logger: Logger = field(default_factory=lambda: get_logger("插件脚本"))

    # 执行参数
    exe_path_key: str = "Info.Path"
    log_time_range: tuple[int, int] = (0, 19)
    log_time_format: str = "%Y-%m-%d %H:%M:%S"
    log_path_key: str | None = None
    run_times_limit: int = 3
    run_time_limit: int = 30

    def get_config_value(self, config: dict[str, Any], key: str) -> Any:
        """按点分路径从配置 dict 读取值。"""
        parts = key.split(".")
        current: Any = config
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current


# ── 钩子执行辅助 ────────────────────────────────────────────────────────


async def _run_hooks(hooks: list[Callable[..., Any]], task_ctx: TaskContext) -> None:
    """按顺序执行钩子列表。"""
    for hook in hooks:
        result = hook(task_ctx)
        if inspect.isawaitable(result):
            await result


async def _run_phase(
    phase: str,
    registry: LifecycleHookRegistry,
    default_fn: Callable[..., Any],
    task_ctx: TaskContext,
) -> None:
    """执行一个生命周期阶段（支持 inject / replace）。"""
    replacement = registry.get_replacement(phase)
    if replacement is not None:
        result = replacement(task_ctx)
        if inspect.isawaitable(result):
            await result
        return

    before_hooks = registry.get_injections(phase, "inject_before")
    await _run_hooks(before_hooks, task_ctx)

    result = default_fn(task_ctx)
    if inspect.isawaitable(result):
        await result

    after_hooks = registry.get_injections(phase, "inject_after")
    await _run_hooks(after_hooks, task_ctx)


# ── PluginScriptManager ────────────────────────────────────────────────


class PluginScriptManager(TaskExecuteBase):
    """插件脚本类型的通用编排器。

    对应内置脚本类型的 manager.py，提供完整的生命周期：
    ``check → prepare → main_task（遍历用户 spawn 子任务）→ final_task / on_crash``
    """

    def __init__(
        self,
        script_info: ScriptItem,
        *,
        type_key: str,
        script_config: dict[str, Any],
        user_configs: list[dict[str, Any]],
        supported_modes: tuple[str, ...],
        hook_registry: LifecycleHookRegistry,
        log_pipeline: LogPipeline,
        plugin_context: PluginContext | None = None,
        exe_path_key: str = "Info.Path",
        log_time_range: tuple[int, int] = (0, 19),
        log_time_format: str = "%Y-%m-%d %H:%M:%S",
        log_path_key: str | None = None,
        run_times_limit_key: str = "Run.RunTimesLimit",
        run_time_limit_key: str = "Run.RunTimeLimit",
    ) -> None:
        super().__init__()
        self.script_info = script_info
        self.task_info = script_info.task_info
        self.type_key = type_key
        self.supported_modes = supported_modes
        self.hook_registry = hook_registry
        self.log_pipeline = log_pipeline
        self.plugin_context = plugin_context

        run_times_limit_val = 3
        run_time_limit_val = 30
        dummy_ctx = TaskContext(script_info=script_info, task_info=script_info.task_info or TaskItem.__new__(TaskItem))
        rtl = dummy_ctx.get_config_value(script_config, run_times_limit_key)
        if isinstance(rtl, int):
            run_times_limit_val = rtl
        rtlm = dummy_ctx.get_config_value(script_config, run_time_limit_key)
        if isinstance(rtlm, int):
            run_time_limit_val = rtlm

        self.task_ctx = TaskContext(
            script_info=script_info,
            task_info=script_info.task_info or TaskItem.__new__(TaskItem),
            type_key=type_key,
            mode=getattr(script_info.task_info, "mode", "AutoProxy") if script_info.task_info else "AutoProxy",
            script_config=script_config,
            user_configs=user_configs,
            exe_path_key=exe_path_key,
            log_time_range=log_time_range,
            log_time_format=log_time_format,
            log_path_key=log_path_key,
            run_times_limit=run_times_limit_val,
            run_time_limit=run_time_limit_val,
            log_pipeline=log_pipeline,
        )

        exe_path_val = self.task_ctx.get_config_value(script_config, exe_path_key)
        if isinstance(exe_path_val, str) and exe_path_val:
            candidate = Path(exe_path_val)
            if candidate.is_file():
                self.task_ctx.exe_path = candidate
                self.task_ctx.script_root = candidate.parent
            elif candidate.is_dir():
                self.task_ctx.script_root = candidate
                exe_candidates = list(candidate.glob("*.exe"))
                if exe_candidates:
                    self.task_ctx.exe_path = exe_candidates[0]
            else:
                self.task_ctx.script_root = candidate

    async def _default_check(self, task_ctx: TaskContext) -> None:
        """默认校验：检查模式合法性和脚本路径。"""
        if task_ctx.mode not in self.supported_modes:
            task_ctx.script_info.status = f"不支持的模式: {task_ctx.mode}"
            return
        if task_ctx.script_root and not task_ctx.script_root.exists():
            task_ctx.script_info.status = f"脚本路径不存在: {task_ctx.script_root}"

    async def _default_prepare(self, task_ctx: TaskContext) -> None:
        """默认准备：构建用户列表，备份配置。"""
        user_list: list[UserItem] = []
        for i, user_cfg in enumerate(task_ctx.user_configs):
            info = user_cfg.get("Info", {})
            if isinstance(info, dict):
                name = str(info.get("Name", f"用户{i + 1}"))
                user_id = str(info.get("Id", str(i)))
                status_val = info.get("Status", True)
            else:
                name = f"用户{i + 1}"
                user_id = str(i)
                status_val = True
            if not status_val:
                continue
            user_list.append(UserItem(user_id=user_id, name=name, status="等待中"))

        task_ctx.script_info.user_list = user_list

        if task_ctx.script_root:
            task_ctx.config_backup_path = Path.cwd() / "data" / task_ctx.type_key / "Temp"
            task_ctx.config_backup_path.mkdir(parents=True, exist_ok=True)

    async def _default_final_task(self, task_ctx: TaskContext) -> None:
        """默认清理：恢复配置，根据用户结果设置状态。"""
        if task_ctx.config_backup_path and task_ctx.config_backup_path.exists():
            shutil.rmtree(task_ctx.config_backup_path, ignore_errors=True)

        user_list = task_ctx.script_info.user_list
        if not user_list:
            task_ctx.script_info.status = "完成"
            return
        all_done = all(u.status == "完成" for u in user_list)
        any_done = any(u.status == "完成" for u in user_list)
        if all_done:
            task_ctx.script_info.status = "完成"
        elif any_done:
            task_ctx.script_info.status = "部分完成"
        else:
            task_ctx.script_info.status = "异常"

    async def _default_on_crash(self, task_ctx: TaskContext, e: Exception) -> None:
        """默认异常处理。"""
        task_ctx.script_info.status = "异常"
        task_ctx.logger.opt(exception=True).error(
            f"插件脚本 {task_ctx.type_key} 执行异常: {e}"
        )

    async def main_task(self) -> None:
        task_ctx = self.task_ctx

        await _run_phase("check", self.hook_registry, self._default_check, task_ctx)

        if task_ctx.script_info.status not in ("", "等待", "等待中", "运行", "运行中"):
            return

        task_ctx.script_info.status = "运行中"
        await _run_phase("prepare", self.hook_registry, self._default_prepare, task_ctx)

        mode = task_ctx.mode
        if mode == "AutoProxy":
            for idx in range(len(task_ctx.script_info.user_list)):
                task_ctx.script_info.current_index = idx
                proxy_task = PluginAutoProxyTask(task_ctx, idx, self.hook_registry)
                await self.spawn(proxy_task)

            subtask_hooks = self.hook_registry.get_subtasks()
            for hook in subtask_hooks:
                result = hook(task_ctx)
                if inspect.isawaitable(result):
                    await result

        elif mode == "ManualReview":
            for idx in range(len(task_ctx.script_info.user_list)):
                task_ctx.script_info.current_index = idx
                review_task = PluginManualReviewTask(task_ctx, idx, self.hook_registry)
                await self.spawn(review_task)

        elif mode == "ScriptConfig":
            for idx in range(len(task_ctx.script_info.user_list)):
                task_ctx.script_info.current_index = idx
                config_task = PluginScriptConfigTask(task_ctx, idx, self.hook_registry)
                await self.spawn(config_task)

    async def final_task(self) -> None:
        await _run_phase("final_task", self.hook_registry, self._default_final_task, self.task_ctx)

    async def on_crash(self, e: Exception) -> None:
        replacement = self.hook_registry.get_replacement("on_crash")
        if replacement is not None:
            result = replacement(self.task_ctx, e)
            if inspect.isawaitable(result):
                await result
            return

        await self._default_on_crash(self.task_ctx, e)

        after_hooks = self.hook_registry.get_injections("on_crash", "inject_after")
        for hook in after_hooks:
            result = hook(self.task_ctx, e)
            if inspect.isawaitable(result):
                await result


# ── PluginAutoProxyTask ────────────────────────────────────────────────


class PluginAutoProxyTask(TaskExecuteBase):
    """插件脚本的通用 per-user 自动代理任务。

    提供标准重试循环：初始化 → 启动进程 → 日志监控 → 等待结果 → 状态评估 → 重试决策。
    每个子阶段均可通过 ``hook.inject.main_task.*`` / ``hook.replace.main_task.*`` 钩子介入。
    """

    def __init__(
        self,
        task_ctx: TaskContext,
        user_index: int,
        hook_registry: LifecycleHookRegistry,
    ) -> None:
        super().__init__()
        self.task_ctx = task_ctx
        self.user_index = user_index
        self.hook_registry = hook_registry
        self.cur_user = task_ctx.script_info.user_list[user_index]

    # ── 子阶段默认实现 ──────────────────────────────────────────────────

    async def _default_init(self, task_ctx: TaskContext) -> None:
        """默认初始化：创建 ProcessManager、LogPipeline、LogMonitor。"""
        process_manager = ProcessManager()
        task_ctx.process_manager = process_manager

        pipeline = task_ctx.log_pipeline or LogPipeline()
        wait_event = asyncio.Event()
        adapter = LogMonitorAdapter(pipeline, wait_event)

        log_monitor = LogMonitor(
            task_ctx.log_time_range,
            task_ctx.log_time_format,
            adapter.callback,
        )
        task_ctx.log_monitor = log_monitor
        task_ctx.wait_event = wait_event

        task_ctx.extra["_proxy_adapter"] = adapter
        task_ctx.extra["_proxy_begin_time"] = datetime.now()

    async def _default_process_start(self, task_ctx: TaskContext) -> None:
        """默认进程启动：根据 exe_path 创建子进程。"""
        process_manager = task_ctx.process_manager
        if process_manager is None:
            return
        if task_ctx.exe_path and task_ctx.exe_path.exists():
            needs_stdout = not (task_ctx.log_path_key and task_ctx.get_config_value(
                task_ctx.script_config, task_ctx.log_path_key
            ))
            await process_manager.open_process(
                str(task_ctx.exe_path),
                cwd=task_ctx.script_root,
                stdout=asyncio.subprocess.PIPE if needs_stdout else asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE if needs_stdout else asyncio.subprocess.DEVNULL,
            )
        elif task_ctx.script_root:
            task_ctx.logger.warning(
                f"未找到可执行文件: {task_ctx.exe_path or task_ctx.script_root}"
            )

    async def _default_log_start(self, task_ctx: TaskContext) -> None:
        """默认日志监控启动：文件优先，否则 stdout。"""
        log_monitor = task_ctx.log_monitor
        process_manager = task_ctx.process_manager
        if log_monitor is None:
            return

        if task_ctx.log_path_key:
            log_path_val = task_ctx.get_config_value(task_ctx.script_config, task_ctx.log_path_key)
            if isinstance(log_path_val, str) and log_path_val:
                task_ctx.log_path = Path(log_path_val)

        begin_time: datetime = task_ctx.extra.get("_proxy_begin_time", datetime.now())
        if task_ctx.log_path and task_ctx.log_path.exists():
            await log_monitor.start_monitor_file(task_ctx.log_path, begin_time)
        elif process_manager is not None and process_manager.process is not None:
            await log_monitor.start_monitor_process(process_manager.process, "stdout")

    async def _default_wait(self, task_ctx: TaskContext) -> None:
        """默认等待：asyncio.wait_for 等待 wait_event。"""
        log_record: LogRecord | None = task_ctx.extra.get("_proxy_log_record")
        try:
            await asyncio.wait_for(task_ctx.wait_event.wait(), timeout=task_ctx.run_time_limit * 60)
        except asyncio.TimeoutError:
            if log_record is not None:
                log_record.status = "脚本进程超时"

    async def _default_evaluate(self, task_ctx: TaskContext) -> None:
        """默认状态评估：从 adapter 和 process 状态推断结果。"""
        log_monitor = task_ctx.log_monitor
        process_manager = task_ctx.process_manager
        adapter: LogMonitorAdapter | None = task_ctx.extra.get("_proxy_adapter")
        log_record: LogRecord | None = task_ctx.extra.get("_proxy_log_record")

        if log_monitor is not None and log_monitor.task is not None:
            await log_monitor.stop()

        if log_record is None:
            return

        if adapter is not None and adapter.last_status:
            log_record.status = adapter.last_status
        elif log_record.status == "未开始监看日志":
            if process_manager is not None and not await process_manager.is_running():
                log_record.status = "脚本在完成任务前退出"
            else:
                log_record.status = "运行中"

        if log_monitor is not None:
            task_ctx.script_info.log = "\n".join(log_monitor.log_contents)
            log_record.content = list(log_monitor.log_contents)

    async def _default_retry(self, task_ctx: TaskContext) -> None:
        """默认重试决策：成功则标记完成，否则杀进程等待重试。"""
        log_record: LogRecord | None = task_ctx.extra.get("_proxy_log_record")
        if log_record is not None and ("Success" in log_record.status or log_record.status == "完成"):
            self.cur_user.status = "完成"
            task_ctx.extra["_proxy_break"] = True
            return

        if task_ctx.process_manager is not None:
            await task_ctx.process_manager.kill()
        await asyncio.sleep(3)

    # ── 主循环 ────────────────────────────────────────────────────────────

    async def main_task(self) -> None:
        task_ctx = self.task_ctx
        cur_user = self.cur_user
        cur_user.status = "运行中"

        await _run_phase("proxy_init", self.hook_registry, self._default_init, task_ctx)

        for _ in range(task_ctx.run_times_limit):
            log_record = LogRecord()
            cur_user.log_record[datetime.now()] = log_record
            task_ctx.wait_event.clear()
            task_ctx.extra["_proxy_log_record"] = log_record
            task_ctx.extra["_proxy_break"] = False

            await _run_phase("proxy_process_start", self.hook_registry, self._default_process_start, task_ctx)
            await _run_phase("proxy_log_start", self.hook_registry, self._default_log_start, task_ctx)
            await _run_phase("proxy_wait", self.hook_registry, self._default_wait, task_ctx)
            await _run_phase("proxy_evaluate", self.hook_registry, self._default_evaluate, task_ctx)
            await _run_phase("proxy_retry", self.hook_registry, self._default_retry, task_ctx)

            if task_ctx.extra.get("_proxy_break"):
                break
        else:
            cur_user.status = "异常"

    async def final_task(self) -> None:
        task_ctx = self.task_ctx
        if task_ctx.log_monitor and task_ctx.log_monitor.task:
            await task_ctx.log_monitor.stop()
        if task_ctx.process_manager:
            await task_ctx.process_manager.kill()

    async def on_crash(self, e: Exception) -> None:
        self.cur_user.status = "异常"
        self.task_ctx.logger.opt(exception=True).error(
            f"插件脚本用户任务异常: {e}"
        )


# ── PluginManualReviewTask ─────────────────────────────────────────────


class PluginManualReviewTask(TaskExecuteBase):
    """插件脚本的通用人工审核任务。

    启动脚本后等待用户确认。
    """

    def __init__(
        self,
        task_ctx: TaskContext,
        user_index: int,
        hook_registry: LifecycleHookRegistry,
    ) -> None:
        super().__init__()
        self.task_ctx = task_ctx
        self.user_index = user_index
        self.hook_registry = hook_registry
        self.cur_user = task_ctx.script_info.user_list[user_index]

    async def main_task(self) -> None:
        self.cur_user.status = "等待审核"

        task_ctx = self.task_ctx
        process_manager = ProcessManager()
        task_ctx.process_manager = process_manager

        if task_ctx.exe_path and task_ctx.exe_path.exists():
            await process_manager.open_process(
                str(task_ctx.exe_path),
                cwd=task_ctx.script_root,
            )

        self.cur_user.status = "等待用户确认"

    async def final_task(self) -> None:
        if self.task_ctx.process_manager:
            await self.task_ctx.process_manager.kill()
        if self.cur_user.status == "等待用户确认":
            self.cur_user.status = "完成"

    async def on_crash(self, e: Exception) -> None:
        self.cur_user.status = "异常"
        self.task_ctx.logger.opt(exception=True).error(
            f"人工审核任务异常: {e}"
        )


# ── PluginScriptConfigTask ─────────────────────────────────────────────


class PluginScriptConfigTask(TaskExecuteBase):
    """插件脚本的通用配置任务。

    启动脚本的配置界面，等待用户完成配置。
    """

    def __init__(
        self,
        task_ctx: TaskContext,
        user_index: int,
        hook_registry: LifecycleHookRegistry,
    ) -> None:
        super().__init__()
        self.task_ctx = task_ctx
        self.user_index = user_index
        self.hook_registry = hook_registry
        self.cur_user = task_ctx.script_info.user_list[user_index]

    async def main_task(self) -> None:
        self.cur_user.status = "配置中"

        task_ctx = self.task_ctx
        process_manager = ProcessManager()
        task_ctx.process_manager = process_manager

        if task_ctx.exe_path and task_ctx.exe_path.exists():
            await process_manager.open_process(
                str(task_ctx.exe_path),
                cwd=task_ctx.script_root,
            )

        wait_event = asyncio.Event()
        task_ctx.wait_event = wait_event

    async def final_task(self) -> None:
        if self.task_ctx.process_manager:
            await self.task_ctx.process_manager.kill()
        self.cur_user.status = "完成"

    async def on_crash(self, e: Exception) -> None:
        self.cur_user.status = "异常"
        self.task_ctx.logger.opt(exception=True).error(
            f"配置任务异常: {e}"
        )


# ── register_script_type ───────────────────────────────────────────────


def register_script_type(
    *,
    ctx: PluginContext,
    type_key: str,
    display_name: str,
    script_config_class: type[BaseModel],
    user_config_class: type[BaseModel],
    supported_modes: tuple[str, ...] = ("AutoProxy", "ScriptConfig"),
    icon: str | None = None,
    docs_url: str | None = None,
    exe_path_key: str = "Info.Path",
    log_time_range: tuple[int, int] = (0, 19),
    log_time_format: str = "%Y-%m-%d %H:%M:%S",
    log_path_key: str | None = None,
    run_times_limit_key: str = "Run.RunTimesLimit",
    run_time_limit_key: str = "Run.RunTimeLimit",
) -> None:
    """高级助手：注册一个插件脚本类型。

    1. 发现调用者 Plugin 实例上的 ``@inject_*`` / ``@replace_*`` / ``@on_log`` 装饰器
    2. 创建 ``LifecycleHookRegistry`` + ``LogPipeline``，填充发现的钩子和处理器
    3. 创建 ``ScriptTypeProvider``（使用 ``PluginSchemaManager`` 生成 schema）
    4. 调用 ``script_type_registry.register(provider, owner=instance_id)``
    """
    from app.core.script_types import ScriptTypeProvider, script_type_registry, build_config_schema
    from app.task.plugin_adapter import create_plugin_manager_factory

    hook_registry = LifecycleHookRegistry()
    log_pipeline_holder = ctx.log._holder if hasattr(ctx.log, "_holder") else _LogPipelineHolder()

    plugin_instance = _find_plugin_instance(ctx)
    if plugin_instance is not None:
        _discover_and_register_hooks(plugin_instance, hook_registry, ctx.instance_id)
        _discover_and_register_log_handlers(plugin_instance, log_pipeline_holder, ctx.instance_id)

    def log_pipeline_factory() -> LogPipeline:
        pipeline = LogPipeline()
        for handler, priority, pattern, source_filter, owner in log_pipeline_holder._pending_handlers:
            pipeline.add_handler(
                handler, priority=priority, pattern=pattern,
                source_filter=source_filter, owner=owner,
            )
        return pipeline

    manager_factory = create_plugin_manager_factory(
        type_key=type_key,
        script_config_class=script_config_class,
        user_config_class=user_config_class,
        supported_modes=supported_modes,
        hook_registry=hook_registry,
        log_pipeline_factory=log_pipeline_factory,
        plugin_context=ctx,
        exe_path_key=exe_path_key,
        log_time_range=log_time_range,
        log_time_format=log_time_format,
        log_path_key=log_path_key,
        run_times_limit_key=run_times_limit_key,
        run_time_limit_key=run_time_limit_key,
    )

    script_schema = build_config_schema(script_config_class)
    user_schema = build_config_schema(user_config_class)

    provider = ScriptTypeProvider(
        type_key=type_key,
        display_name=display_name,
        script_config_class=script_config_class,
        user_config_class=user_config_class,
        supported_modes=supported_modes,
        manager_factory=manager_factory,
        script_schema=script_schema,
        user_schema=user_schema,
        icon=icon,
        docs_url=docs_url,
        editor_kind=f"plugin:{type_key}",
        is_builtin=False,
    )

    script_type_registry.register(provider, owner=ctx.instance_id)
    _logger.info(f"已注册插件脚本类型: {type_key} (owner={ctx.instance_id})")


# ── 内部辅助 ────────────────────────────────────────────────────────────


def _find_plugin_instance(ctx: PluginContext) -> Any:
    """从 PluginManager 中找到当前插件实例对象。"""
    try:
        from app.plugins.manager import PluginManager
        loader = PluginManager.loader
        record = loader.records.get(ctx.instance_id)
        if record is not None:
            return record.plugin_instance
    except Exception:
        pass
    return None


def _discover_and_register_hooks(
    plugin_instance: Any,
    registry: LifecycleHookRegistry,
    owner: str,
) -> None:
    """发现插件实例上的 ``@inject_*`` / ``@replace_*`` 钩子并注册。"""
    for _, member in inspect.getmembers(plugin_instance):
        if not (inspect.isfunction(member) or inspect.ismethod(member)):
            continue
        specs = get_lifecycle_hooks(member)
        for spec in specs:
            registry.register(
                phase=spec.phase,
                action=spec.action,
                handler=member,
                priority=spec.priority,
                owner=owner,
            )


def _discover_and_register_log_handlers(
    plugin_instance: Any,
    holder: _LogPipelineHolder,
    owner: str,
) -> None:
    """发现插件实例上的 ``@on_log`` 处理器并注册。"""
    for attr_name in dir(plugin_instance):
        try:
            member = getattr(plugin_instance, attr_name)
        except Exception:
            continue
        if not callable(member):
            continue
        specs = get_log_handlers(member)
        for spec in specs:
            if inspect.isfunction(member) and not inspect.ismethod(member):
                member = member.__get__(plugin_instance, type(plugin_instance))
            holder.add_pending_handler(
                member,
                priority=spec.priority,
                pattern=spec.pattern,
                source_filter=spec.source_filter,
                owner=owner,
            )
