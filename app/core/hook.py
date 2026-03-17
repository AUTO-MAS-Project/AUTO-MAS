#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


"""
作用域感知的 Hook 系统（用于动态拦截/增强异步函数调用）。

这个模块提供一个轻量、可组合、对并发友好的 Hook 机制，用于在**不侵入业务代码**的
前提下，为异步函数添加日志、埋点、性能统计、参数校验、错误上报等横切能力。

核心概念
--------
1) ``@hookable``
     用于标记一个 **async 函数** 为“可被拦截”。被装饰后的函数在被调用时，会检查当前
     是否存在激活的 :class:`HookScope`：

     - **无作用域**：直接调用原函数（额外开销仅一次 ``ContextVar.get``）。
     - **有作用域**：由作用域统一调度 before/after/error/around hooks。

2) :class:`HookScope`
     一个异步上下文管理器（``async with``），用于**注册并承载 hooks**。
     作用域通过 :mod:`contextvars` 传播：

     - ``asyncio.create_task`` / ``TaskGroup.create_task``：创建子任务时 Python 会复制上下文，
         因此子协程/子任务会自动继承当前作用域。
     - 嵌套 ``async with HookScope()``：子作用域会对父作用域的 hook 列表做浅拷贝继承；
         **子作用域的注册不会回写父作用域**（避免污染外层）。

     退出作用域时，会恢复进入前的作用域（或恢复为 ``None``）。

Hook 类型与语义
---------------
- ``before``：在目标函数执行前触发，回调签名与目标函数一致（包含 ``self``）。
- ``after``：在目标函数成功返回后触发，回调第 1 个参数为返回值 ``result``，后续参数为原始入参。
    该 hook 仅用于观察/副作用；若需要修改返回值请使用 ``around``。
- ``error``：当目标函数抛出异常时触发，回调第 1 个参数为异常对象 ``exc``，后续参数为原始入参。
    注意：异常在所有 ``error`` hooks 执行完后会**原样重新抛出**。
- ``around``：完整包裹（中间件 / 洋葱模型）。回调第 1 个参数为 ``call_next`` 可调用对象，
    后续参数为原始入参。回调必须 ``await call_next(...)`` 才会继续执行下一层或原函数。
    **注册顺序决定包裹顺序**：最后注册的 around hook 是最外层（最先执行）。

实用提示
--------
- Hook 的注册是按“函数身份”而不是按函数名匹配：只有被 ``@hookable`` 装饰过的函数才能被注册。
- Hook 回调本身也是 async：如果回调抛异常，会像普通异常一样向外传播（请谨慎处理）。
- 该实现依赖 ``contextvars``，适用于 asyncio 并发；不同任务间互不干扰（只要不手动共享 scope）。

快速上手
--------
::

        from app.core.hook import hookable, HookScope

        class MyTask:
                @hookable
                async def prepare(self) -> None:
                        ...

        async with HookScope() as scope:
                async def log_before(self: MyTask) -> None:
                        print(f"准备执行 prepare: {self}")

                scope.before(MyTask.prepare, log_before)
                await task.prepare()        # 在作用域内：hooks 生效

        await task.prepare()            # 作用域外：不触发 hooks
"""

from __future__ import annotations

import contextvars
import importlib.util
import inspect
import sys
from collections.abc import Awaitable, Callable, Iterable
from functools import wraps
from hashlib import sha1
from pathlib import Path
from types import ModuleType
from typing import Any, Concatenate, Literal, ParamSpec, TypeVar

from app.utils import get_logger

__all__ = [
    "hookable",
    "HookScope",
    "HookPoint",
    "HookError",
    "load_hook_module",
]

P = ParamSpec("P")
R = TypeVar("R")

HookKind = Literal["before", "after", "error", "around"]
_ALL_HOOK_KINDS: frozenset[HookKind] = frozenset({"before", "after", "error", "around"})

# 保存当前作用域的 ContextVar；``None`` 表示“当前没有激活的作用域”。
_current_scope: contextvars.ContextVar[HookScope | None] = contextvars.ContextVar(
    "hook_scope", default=None
)

logger = get_logger("Hook管理器")


class HookError(Exception):
    """Hook 显式异常。

    约定：
    - Hook 回调中抛出 HookError：视作真实异常，继续向上抛出。
    - Hook 回调中抛出其他异常：降级为 warning，不中断主流程。
    """

    pass


def _build_hook_logger(module: ModuleType, raw_path: str):
    """为 Hook 模块构建专属 logger（优先使用 HOOK_META.name）。"""
    hook_name: str | None = None
    meta = getattr(module, "HOOK_META", None)
    if isinstance(meta, dict):
        name = meta.get("name")
        if isinstance(name, str) and name.strip():
            hook_name = name.strip()

    if not hook_name:
        stem = Path(raw_path).stem.strip()
        hook_name = stem or getattr(module, "__name__", "unknown_hook")

    return get_logger(f"hook-{hook_name}")


def _inject_hook_logger(module: ModuleType, raw_path: str):
    """为 Hook 模块创建并注入 logger。

    - 注入 module.HOOK_LOGGER
    - 若模块提供 set_logger(logger)，则一并调用
    """
    hook_logger = _build_hook_logger(module, raw_path)
    setattr(module, "HOOK_LOGGER", hook_logger)

    set_logger = getattr(module, "set_logger", None)
    if callable(set_logger):
        set_logger(hook_logger)

    return hook_logger


def _load_hook_module_from_path(file_path: str) -> tuple[ModuleType | None, str | None]:
    """从 .py 文件路径动态加载模块。

    返回 (module, warning)。失败时 module 为 None，warning 为说明文本。
    """
    p = Path(file_path)
    if not p.exists() or not p.is_file():
        return None, "文件不存在或不是文件"
    if p.suffix.lower() != ".py":
        return None, "仅支持 .py 文件"

    try:
        resolved = p.resolve()
    except Exception:
        resolved = p

    # 生成稳定且尽量不冲突的模块名（避免重复 import 相互覆盖）
    digest = sha1(str(resolved).encode("utf-8", errors="ignore")).hexdigest()[:12]
    module_name = f"auto_mas_hook_{p.stem}_{digest}"

    # 每次任务运行都重新加载一份，避免被上次运行的模块状态污染。
    if module_name in sys.modules:
        sys.modules.pop(module_name, None)

    spec = importlib.util.spec_from_file_location(module_name, str(resolved))
    if spec is None or spec.loader is None:
        return None, "无法创建模块加载器"

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        return None, f"导入失败: {type(e).__name__}: {e}"

    return module, None


def load_hook_module(
    hook_paths: list[str], scope: HookScope, target_cls: type[Any]
) -> list[str]:
    """按顺序加载并注册 Hook 列表。

    - 每个 Hook 模块会注入 ``HOOK_LOGGER``（命名为 ``hook-xxx``）
    - 兼容 register(scope, target_cls) / register(scope, target_cls, hook_logger)
    - 发生错误时继续处理后续 Hook，并返回 warning 列表
    """
    warnings: list[str] = []

    for raw_path in hook_paths:
        module, warn = _load_hook_module_from_path(raw_path)
        if warn:
            msg = f"Hook 加载警告 [{raw_path}]: {warn}"
            warnings.append(msg)
            logger.warning(msg)
            continue

        assert module is not None
        try:
            hook_logger = _inject_hook_logger(module, raw_path)
        except Exception as e:
            msg = f"Hook 日志注入警告 [{raw_path}]: {type(e).__name__}: {e}"
            warnings.append(msg)
            logger.warning(msg)
            continue

        register = getattr(module, "register", None)
        if not callable(register):
            msg = f"Hook 加载警告 [{raw_path}]: 未找到可调用的 register(scope, target_cls)"
            warnings.append(msg)
            logger.warning(msg)
            continue

        try:
            # 兼容两种签名：
            # - register(scope, target_cls)
            # - register(scope, target_cls, hook_logger)
            sig = inspect.signature(register)
            params = list(sig.parameters.values())
            positional_count = len(
                [
                    p
                    for p in params
                    if p.kind
                    in (
                        inspect.Parameter.POSITIONAL_ONLY,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    )
                ]
            )
            has_varargs = any(
                p.kind == inspect.Parameter.VAR_POSITIONAL for p in params
            )

            if has_varargs or positional_count >= 3:
                register(scope, target_cls, hook_logger)
            else:
                register(scope, target_cls)
        except HookError:
            raise
        except Exception as e:
            msg = f"Hook 注册警告 [{raw_path}]: {type(e).__name__}: {e}"
            warnings.append(msg)
            logger.warning(msg)
            continue

    return warnings


# ---------------------------------------------------------------------------
# HookPoint —— 附加在每个 @hookable 包装器上的“身份标记”
# ---------------------------------------------------------------------------


class HookPoint:
    """可钩函数的唯一身份标识。

    由 :func:`hookable` 装饰器将实例保存在 ``wrapper._hook_point`` 中，
    并在 :class:`HookScope` 内部作为字典键使用。
    """

    __slots__ = ("qualname", "name", "allowed")

    def __init__(
        self,
        func: Callable[..., Any],
        *,
        name: str,
        allowed: frozenset[HookKind],
    ) -> None:
        """_summary_

        Args:
            name (str | None): 钩子名称
            allowed (frozenset[HookKind]): 允许的钩子类型
        """
        self.qualname: str = getattr(func, "__qualname__", repr(func))
        # 仅用于日志/调试展示，不参与匹配。
        self.name: str = name
        self.allowed: frozenset[HookKind] = allowed

    def __repr__(self) -> str:
        if self.name:
            return f"<HookPoint {self.name} ({self.qualname})>"
        return f"<HookPoint {self.qualname}>"


# ---------------------------------------------------------------------------
# @hookable 装饰器
# ---------------------------------------------------------------------------


def _normalize_allow(allow: Iterable[str] | Iterable[HookKind]) -> frozenset[HookKind]:
    if isinstance(allow, dict):
        raise TypeError(
            "hookable(allow=...) does not accept a dict; "
            "use a set, e.g. allow=set() or allow={'before','after'}"
        )
    allow_set = frozenset(allow)  # type: ignore[arg-type]
    unknown = set(allow_set) - set(_ALL_HOOK_KINDS)
    if unknown:
        raise TypeError(
            "hookable(allow=...) contains unknown hook kinds: "
            f"{sorted(unknown)!r}. Valid kinds: {sorted(_ALL_HOOK_KINDS)!r}"
        )
    # 这里 cast 的目的是把 Literal 收窄到 HookKind
    return frozenset(allow_set)  # type: ignore[return-value]


def hookable(
    *args: Any,
    allow: Iterable[HookKind] | None = None,
    name: str,
):
    """标记一个 async 函数为可被钩取（hookable）。
    用法:``@hookable(name='MyTask.prepare', allow={'before','after'})``

    ``allow`` 控制允许注册的 hook 类型；不在 allow 内的注册会在
    :class:`HookScope` 注册阶段直接报错（fail-fast）。
    """
    if args:
        raise TypeError(
            "hookable must be used as @hookable(allow={...}) "
            "(allow is required and must be explicit). "
            "If you need a label, use @hookable(name='...', allow={...})."
        )
    if allow is None:
        raise TypeError(
            "hookable requires explicit 'allow', e.g. "
            "@hookable(allow={'before','after','error','around'})"
        )

    allowed = _normalize_allow(allow)

    def _decorator(real_func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        point = HookPoint(real_func, name=name, allowed=allowed)

        @wraps(real_func)
        async def _wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            scope = _current_scope.get(None)
            if scope is None:
                # 快速路径：没有激活的作用域时，直接调用原函数。
                return await real_func(*args, **kwargs)
            return await scope._dispatch(point, real_func, args, kwargs)

        # 绑定身份标记，便于 HookScope.before/after/… 在注册时定位到该函数。
        _wrapper._hook_point = point  # type: ignore[attr-defined]
        return _wrapper  # type: ignore[return-value]

    return _decorator


# ---------------------------------------------------------------------------
# HookScope
# ---------------------------------------------------------------------------


class HookScope:
    """用于保存钩子注册的异步上下文管理器。

    Scope 通过 :mod:`contextvars` 传播：

    * ``asyncio.create_task``/``TaskGroup.create_task`` — 子任务在创建时
      自动继承当前 scope（Python 会复制上下文）。
    * 嵌套 ``async with HookScope()`` — 子作用域对父作用域的钩子列表
      进行浅拷贝继承；子作用域的注册不会影响父作用域。

    退出时会恢复之前的作用域（或 ``None``）。
    """

    __slots__ = ("_before", "_after", "_error", "_around", "_token")

    def __init__(self) -> None:
        self._before: dict[HookPoint, list[Callable[..., Awaitable[None]]]] = {}
        self._after: dict[HookPoint, list[Callable[..., Awaitable[None]]]] = {}
        self._error: dict[HookPoint, list[Callable[..., Awaitable[None]]]] = {}
        self._around: dict[HookPoint, list[Callable[..., Awaitable[Any]]]] = {}
        self._token: contextvars.Token[HookScope | None] | None = None

    # ------------------------------------------------------------------
    # 上下文管理器
    # ------------------------------------------------------------------

    async def __aenter__(self) -> HookScope:
        parent = _current_scope.get(None)
        if parent is not None:
            # 继承：对每个 hook 列表做浅拷贝，确保修改只作用于当前 scope。
            self._before = {k: list(v) for k, v in parent._before.items()}
            self._after = {k: list(v) for k, v in parent._after.items()}
            self._error = {k: list(v) for k, v in parent._error.items()}
            self._around = {k: list(v) for k, v in parent._around.items()}
        self._token = _current_scope.set(self)
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._token is not None:
            try:
                _current_scope.reset(self._token)
            except ValueError:
                # 可能发生在“进入 scope 与退出 scope 发生在不同 Context”
                # （例如取消/屏蔽取消等复杂调度路径）。
                # 此时 reset 会报错：Token was created in a different Context。
                # 退化处理：仅跳过 reset，避免二次异常影响任务收尾。
                pass
            self._token = None

    # ------------------------------------------------------------------
    # 注册 API
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_point(target: Callable[..., Any]) -> HookPoint:
        """从 ``@hookable`` 包装器中提取 :class:`HookPoint` 实例。"""
        point: HookPoint | None = getattr(target, "_hook_point", None)
        if point is None:
            raise TypeError(
                f"{target!r} is not decorated with @hookable — "
                "only @hookable(allow={...}) functions can be hooked"
            )
        return point

    @staticmethod
    def _ensure_allowed(
        point: HookPoint, kind: HookKind, target: Callable[..., Any]
    ) -> None:
        if kind not in point.allowed:
            label = point.name or point.qualname
            raise TypeError(
                f"Hook kind '{kind}' is not allowed for {label!r}; "
                f"allowed kinds: {sorted(point.allowed)!r}. "
                f"Target: {target!r}"
            )

    # --- before（前置 hook）-------------------------------------------

    def before(
        self,
        target: Callable[P, Awaitable[R]],
        callback: Callable[P, Awaitable[None]],
    ) -> None:
        """注册一个 *before* 钩子。

        ``callback`` 将在目标函数执行前被调用，参数与目标函数一致
        （对于绑定方法包含 ``self``）。
        """
        point = self._resolve_point(target)
        self._ensure_allowed(point, "before", target)
        self._before.setdefault(point, []).append(callback)

    # --- after（后置 hook）--------------------------------------------

    def after(
        self,
        target: Callable[P, Awaitable[R]],
        callback: Callable[Concatenate[R, P], Awaitable[None]],
    ) -> None:
        """注册一个 *after* 钩子。

        ``callback`` 的第一个参数为函数返回值，后续参数为原始入参。
        此钩子仅用于观察或副作用，若需修改返回值请使用 :meth:`around`。
        """
        point = self._resolve_point(target)
        self._ensure_allowed(point, "after", target)
        self._after.setdefault(point, []).append(callback)

    # --- error（异常 hook）--------------------------------------------

    def error(
        self,
        target: Callable[P, Awaitable[R]],
        callback: Callable[Concatenate[Exception, P], Awaitable[None]],
    ) -> None:
        """注册一个 *error* 钩子。

        ``callback`` 的第一个参数为异常对象，后续参数为原始入参。
        所有 error 钩子执行完毕后异常将**再次抛出**。
        """
        point = self._resolve_point(target)
        self._ensure_allowed(point, "error", target)
        self._error.setdefault(point, []).append(callback)

    # --- around（环绕 hook）-------------------------------------------

    def around(
        self,
        target: Callable[P, Awaitable[R]],
        callback: Callable[Concatenate[Callable[P, Awaitable[R]], P], Awaitable[R]],
    ) -> None:
        """注册一个 *around* 钩子（洋葱/中间件模型）。

        ``callback`` 的第一个参数是 ``call_next`` 可调用对象，后续参数
        为原始入参。必须 ``await call_next(...)`` 才能继续执行下一层
        或原函数。最后注册的 around 钩子会成为最外层。
        """
        point = self._resolve_point(target)
        self._ensure_allowed(point, "around", target)
        self._around.setdefault(point, []).append(callback)

    # ------------------------------------------------------------------
    # 内部调度：由 @hookable 的包装器调用
    # ------------------------------------------------------------------

    async def _dispatch(
        self,
        point: HookPoint,
        func: Callable[..., Awaitable[Any]],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        """为指定 HookPoint 调度并执行围绕 *func* 的所有钩子。"""

        point_name = point.name or point.qualname

        def _warn_hook_exception(phase: str, cb: Callable[..., Any], exc: Exception) -> None:
            logger.warning(
                f"Hook 执行警告 [{point_name}] ({phase}) {cb!r}: "
                f"{type(exc).__name__}: {exc}"
            )

        # ---- before hooks（按注册顺序执行）-------------------------------
        for cb in self._before.get(point, ()):
            try:
                await cb(*args, **kwargs)
            except HookError:
                raise
            except Exception as e:
                _warn_hook_exception("before", cb, e)

        # ---- 构建 around 链（最后注册 = 最外层）---------------------------
        around_hooks = self._around.get(point, ())

        async def _original(*a: Any, **kw: Any) -> Any:
            return await func(*a, **kw)

        call_next: Callable[..., Awaitable[Any]] = _original
        for around_cb in around_hooks:
            # 通过默认参数捕获循环变量，避免闭包引用被后续循环覆盖。
            _next = call_next
            _cb = around_cb

            async def _chained(
                *a: Any, _cb: Any = _cb, _next: Any = _next, **kw: Any
            ) -> Any:
                try:
                    return await _cb(_next, *a, **kw)
                except HookError:
                    raise
                except Exception as e:
                    _warn_hook_exception("around", _cb, e)
                    return await _next(*a, **kw)

            call_next = _chained

        # ---- 执行（around 链 → 原函数）-----------------------------------
        try:
            result = await call_next(*args, **kwargs)
        except Exception as exc:
            # ---- error hooks（按注册顺序执行）--------------------------------
            for cb in self._error.get(point, ()):
                try:
                    await cb(exc, *args, **kwargs)
                except HookError:
                    raise
                except Exception as e:
                    _warn_hook_exception("error", cb, e)
            raise

        # ---- after hooks（按注册顺序执行）--------------------------------
        for cb in self._after.get(point, ()):
            try:
                await cb(result, *args, **kwargs)
            except HookError:
                raise
            except Exception as e:
                _warn_hook_exception("after", cb, e)

        return result
