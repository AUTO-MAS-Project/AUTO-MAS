#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

from __future__ import annotations

import inspect
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Final

from app.utils import get_logger


logger = get_logger("生命周期钩子")

LIFECYCLE_HOOK_ATTR: Final[str] = "__mas_lifecycle_hooks__"

VALID_PHASES: Final[frozenset[str]] = frozenset({
    "check", "prepare", "main_task", "final_task", "on_crash",
    "proxy_init", "proxy_process_start", "proxy_log_start",
    "proxy_wait", "proxy_evaluate", "proxy_retry",
})
VALID_ACTIONS: Final[frozenset[str]] = frozenset(
    {"inject_before", "inject_after", "inject_subtask", "replace"}
)


class PluginDefinitionError(Exception):
    """插件定义冲突错误。"""


@dataclass(frozen=True, slots=True)
class LifecycleHookSpec:
    """生命周期钩子元数据。"""

    phase: str
    action: str
    priority: int = 0


@dataclass(slots=True)
class _BoundHook:
    """已注册的钩子条目。"""

    hook_id: str
    phase: str
    action: str
    handler: Callable[..., Any]
    priority: int
    owner: str | None


def get_lifecycle_hooks(target: Any) -> list[LifecycleHookSpec]:
    """从函数或方法上提取 ``@inject_*`` / ``@replace_*`` 声明的元数据列表。"""
    specs: list[LifecycleHookSpec] = getattr(target, LIFECYCLE_HOOK_ATTR, [])
    return list(specs)


def _lifecycle_decorator(
    phase: str,
    action: str,
    priority: int,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    if phase not in VALID_PHASES:
        raise ValueError(f"非法生命周期阶段: {phase}")
    if action not in VALID_ACTIONS:
        raise ValueError(f"非法钩子动作: {action}")

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        hooks: list[LifecycleHookSpec] = list(getattr(func, LIFECYCLE_HOOK_ATTR, []))
        hooks.append(LifecycleHookSpec(phase=phase, action=action, priority=priority))
        setattr(func, LIFECYCLE_HOOK_ATTR, hooks)
        return func

    return decorator


# ── inject 装饰器 ──────────────────────────────────────────────────────


def inject_check(*, priority: int = 0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """在默认 ``check`` 之后注入额外校验逻辑。"""
    return _lifecycle_decorator("check", "inject_after", priority)


def inject_before_prepare(*, priority: int = 0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """在默认 ``prepare`` 之前注入前置逻辑。"""
    return _lifecycle_decorator("prepare", "inject_before", priority)


def inject_prepare(*, priority: int = 0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """在默认 ``prepare`` 之后注入后置逻辑。"""
    return _lifecycle_decorator("prepare", "inject_after", priority)


def inject_main_task(*, priority: int = 0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """在 ``main_task`` 中作为子任务注入。"""
    return _lifecycle_decorator("main_task", "inject_subtask", priority)


def inject_final_task(*, priority: int = 0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """在默认 ``final_task`` 之后注入清理逻辑。"""
    return _lifecycle_decorator("final_task", "inject_after", priority)


def inject_on_crash(*, priority: int = 0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """在默认 ``on_crash`` 之后注入额外错误处理。"""
    return _lifecycle_decorator("on_crash", "inject_after", priority)


# ── replace 装饰器 ─────────────────────────────────────────────────────


def replace_check() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """替换默认的 ``check`` 阶段。

    .. warning::

        不建议使用, 除非你知道你在做什么。
        替换后默认校验逻辑和所有 inject 钩子均不会执行。
    """
    return _lifecycle_decorator("check", "replace", 0)


def replace_prepare() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """替换默认的 ``prepare`` 阶段。

    .. warning::

        不建议使用, 除非你知道你在做什么。
        替换后默认准备逻辑和所有 inject 钩子均不会执行。
    """
    return _lifecycle_decorator("prepare", "replace", 0)


def replace_main_task() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """替换默认的 ``main_task`` 阶段。

    .. warning::

        不建议使用, 除非你知道你在做什么。
        替换后默认任务循环和所有 inject 钩子均不会执行。
    """
    return _lifecycle_decorator("main_task", "replace", 0)


def replace_final_task() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """替换默认的 ``final_task`` 阶段。

    .. warning::

        不建议使用, 除非你知道你在做什么。
        替换后默认清理逻辑和所有 inject 钩子均不会执行。
    """
    return _lifecycle_decorator("final_task", "replace", 0)


def replace_on_crash() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """替换默认的 ``on_crash`` 阶段。

    .. warning::

        不建议使用, 除非你知道你在做什么。
        替换后默认错误处理和所有 inject 钩子均不会执行。
    """
    return _lifecycle_decorator("on_crash", "replace", 0)


# ── hook 命名空间 ──────────────────────────────────────────────────────


class _InjectMainTaskNamespace:
    """``hook.inject.main_task`` —— 既可直接调用，也可通过子属性访问子阶段。

    用法::

        @hook.inject.main_task(priority=5)                   # 原有：子任务注入
        @hook.inject.main_task.before_process_start(priority=10)  # 新增：子阶段
    """

    def __call__(self, *, priority: int = 0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """在 ``main_task`` 中作为子任务注入。"""
        return _lifecycle_decorator("main_task", "inject_subtask", priority)

    @staticmethod
    def before_init(*, priority: int = 0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """在 AutoProxy 初始化（创建 ProcessManager/LogMonitor）之前注入。"""
        return _lifecycle_decorator("proxy_init", "inject_before", priority)

    @staticmethod
    def init(*, priority: int = 0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """在 AutoProxy 初始化之后注入。"""
        return _lifecycle_decorator("proxy_init", "inject_after", priority)

    @staticmethod
    def before_process_start(*, priority: int = 0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """在启动脚本进程之前注入。每次重试都会调用。"""
        return _lifecycle_decorator("proxy_process_start", "inject_before", priority)

    @staticmethod
    def process_start(*, priority: int = 0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """在启动脚本进程之后注入。每次重试都会调用。"""
        return _lifecycle_decorator("proxy_process_start", "inject_after", priority)

    @staticmethod
    def before_log_start(*, priority: int = 0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """在启动日志监控之前注入。可修改 ``task_ctx.log_path`` 改变日志来源。"""
        return _lifecycle_decorator("proxy_log_start", "inject_before", priority)

    @staticmethod
    def log_start(*, priority: int = 0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """在启动日志监控之后注入。"""
        return _lifecycle_decorator("proxy_log_start", "inject_after", priority)

    @staticmethod
    def before_wait(*, priority: int = 0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """在等待脚本结果之前注入。"""
        return _lifecycle_decorator("proxy_wait", "inject_before", priority)

    @staticmethod
    def wait(*, priority: int = 0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """在等待脚本结果之后注入。"""
        return _lifecycle_decorator("proxy_wait", "inject_after", priority)

    @staticmethod
    def before_evaluate(*, priority: int = 0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """在状态评估之前注入。"""
        return _lifecycle_decorator("proxy_evaluate", "inject_before", priority)

    @staticmethod
    def evaluate(*, priority: int = 0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """在状态评估之后注入。可修改 ``log_record.status`` 覆盖结果。"""
        return _lifecycle_decorator("proxy_evaluate", "inject_after", priority)

    @staticmethod
    def before_retry(*, priority: int = 0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """在重试决策之前注入。"""
        return _lifecycle_decorator("proxy_retry", "inject_before", priority)

    @staticmethod
    def retry(*, priority: int = 0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """在重试决策之后注入。"""
        return _lifecycle_decorator("proxy_retry", "inject_after", priority)


class _ReplaceMainTaskNamespace:
    """``hook.replace.main_task`` —— 既可直接调用，也可通过子属性替换子阶段。"""

    def __call__(self) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """替换默认的 ``main_task`` 阶段。

        .. warning::

            不建议使用, 除非你知道你在做什么。
            替换后默认任务循环和所有 inject 钩子均不会执行。
        """
        return _lifecycle_decorator("main_task", "replace", 0)

    @staticmethod
    def init() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """替换 AutoProxy 初始化阶段。"""
        return _lifecycle_decorator("proxy_init", "replace", 0)

    @staticmethod
    def process_start() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """替换脚本进程启动阶段。"""
        return _lifecycle_decorator("proxy_process_start", "replace", 0)

    @staticmethod
    def log_start() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """替换日志监控启动阶段。可完全自定义日志来源选择逻辑。"""
        return _lifecycle_decorator("proxy_log_start", "replace", 0)

    @staticmethod
    def wait() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """替换等待脚本结果阶段。"""
        return _lifecycle_decorator("proxy_wait", "replace", 0)

    @staticmethod
    def evaluate() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """替换状态评估阶段。"""
        return _lifecycle_decorator("proxy_evaluate", "replace", 0)

    @staticmethod
    def retry() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """替换重试决策阶段。"""
        return _lifecycle_decorator("proxy_retry", "replace", 0)


class _InjectNamespace:
    """``hook.inject.*`` 命名空间，提供注入式生命周期钩子装饰器。"""

    check = staticmethod(inject_check)
    before_prepare = staticmethod(inject_before_prepare)
    prepare = staticmethod(inject_prepare)
    main_task = _InjectMainTaskNamespace()
    final_task = staticmethod(inject_final_task)
    on_crash = staticmethod(inject_on_crash)


class _ReplaceNamespace:
    """``hook.replace.*`` 命名空间，提供替换式生命周期钩子装饰器。"""

    check = staticmethod(replace_check)
    prepare = staticmethod(replace_prepare)
    main_task = _ReplaceMainTaskNamespace()
    final_task = staticmethod(replace_final_task)
    on_crash = staticmethod(replace_on_crash)


class _HookNamespace:
    """``hook.inject.*`` / ``hook.replace.*`` 顶层命名空间。

    用法::

        from app.plugins.lifecycle_hooks import hook

        # 顶层阶段
        @hook.inject.main_task(priority=5)
        async def my_subtask(self, ctx: TaskContext) -> None: ...

        @hook.replace.prepare()
        async def my_prepare(self, ctx: TaskContext) -> None: ...

        # main_task 子阶段
        @hook.inject.main_task.before_process_start(priority=10)
        async def setup_env(self, ctx: TaskContext) -> None: ...

        @hook.replace.main_task.log_start()
        async def my_log_start(self, ctx: TaskContext) -> None: ...
    """

    inject = _InjectNamespace()
    replace = _ReplaceNamespace()


hook = _HookNamespace()


# ── LifecycleHookRegistry ─────────────────────────────────────────────


class LifecycleHookRegistry:
    """收集和管理来自插件的生命周期钩子。"""

    def __init__(self) -> None:
        self._hooks: dict[str, list[_BoundHook]] = defaultdict(list)
        self._by_id: dict[str, _BoundHook] = {}

    def register(
        self,
        phase: str,
        action: str,
        handler: Callable[..., Any],
        *,
        priority: int = 0,
        owner: str | None = None,
    ) -> str:
        """注册一个生命周期钩子。

        Args:
            phase: 目标阶段名。
            action: 钩子动作类型。
            handler: 钩子处理函数。
            priority: 优先级（值越大越先执行）。
            owner: 所属插件实例 ID。

        Returns:
            钩子 ID。

        Raises:
            PluginDefinitionError: 同一阶段已有 replace 钩子时再次注册 replace。
        """
        if action == "replace":
            existing = self.get_replacement(phase)
            if existing is not None:
                raise PluginDefinitionError(
                    f"阶段 {phase} 已被替换，不能注册多个 replace 钩子"
                )
            logger.warning(
                f"插件 {owner or '未知'} 使用 replace_{phase}, "
                "不建议使用, 除非你知道你在做什么"
            )

        hook_id = str(uuid.uuid4())
        hook = _BoundHook(
            hook_id=hook_id,
            phase=phase,
            action=action,
            handler=handler,
            priority=priority,
            owner=owner,
        )
        self._hooks[phase].append(hook)
        self._by_id[hook_id] = hook
        return hook_id

    def unregister(self, hook_id: str) -> None:
        """按 ID 注销钩子。"""
        hook = self._by_id.pop(hook_id, None)
        if hook is None:
            return
        phase_hooks = self._hooks.get(hook.phase)
        if phase_hooks is not None:
            self._hooks[hook.phase] = [h for h in phase_hooks if h.hook_id != hook_id]

    def unregister_by_owner(self, owner: str) -> None:
        """按 owner 批量注销钩子。"""
        ids_to_remove = [h.hook_id for h in self._by_id.values() if h.owner == owner]
        for hook_id in ids_to_remove:
            self.unregister(hook_id)

    def get_injections(self, phase: str, position: str) -> list[Callable[..., Any]]:
        """获取指定阶段和位置的 inject 钩子，按优先级降序排列。

        Args:
            phase: 阶段名。
            position: ``"inject_before"`` 或 ``"inject_after"``。

        Returns:
            钩子处理函数列表。
        """
        hooks = [h for h in self._hooks.get(phase, []) if h.action == position]
        hooks.sort(key=lambda h: h.priority, reverse=True)
        return [h.handler for h in hooks]

    def get_replacement(self, phase: str) -> Callable[..., Any] | None:
        """获取指定阶段的 replace 钩子（至多一个）。"""
        for hook in self._hooks.get(phase, []):
            if hook.action == "replace":
                return hook.handler
        return None

    def get_subtasks(self) -> list[Callable[..., Any]]:
        """获取 ``main_task`` 阶段的 inject_subtask 钩子，按优先级降序排列。"""
        hooks = [h for h in self._hooks.get("main_task", []) if h.action == "inject_subtask"]
        hooks.sort(key=lambda h: h.priority, reverse=True)
        return [h.handler for h in hooks]

    def iter_members_with_hooks(
        self, target: Any
    ) -> list[tuple[Callable[..., Any], LifecycleHookSpec]]:
        """遍历对象成员并提取生命周期钩子声明。"""
        result: list[tuple[Callable[..., Any], LifecycleHookSpec]] = []
        for _, member in inspect.getmembers(target):
            if not (inspect.isfunction(member) or inspect.ismethod(member)):
                continue
            specs = get_lifecycle_hooks(member)
            for spec in specs:
                result.append((member, spec))
        return result
