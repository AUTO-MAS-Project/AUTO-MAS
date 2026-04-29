#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

import inspect
import json
import sys
import asyncio
from copy import deepcopy
from functools import wraps
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, Iterable, Optional, Literal

from app.utils import get_logger
from app.utils.constants import UTC8

from .context import PluginContext
from .decorators import EventSubscription, get_event_subscriptions
from .lifecycle import REQUIRED_LIFECYCLE_METHODS
from .realtime import publish_runtime_record
from .service_registry import ServiceRegistry
from .service_spec import ServiceSpec
from .server import plugin_server
from .pypi_site import (
    ensure_pypi_site_packages_on_syspath,
    iter_plugin_entry_points,
    resolve_entry_point_editable_project_path,
)


logger = get_logger("插件加载器")


def _utc8_now_iso() -> str:
    """返回当前 UTC+8 时间的 ISO8601 字符串。"""
    return datetime.now(tz=UTC8).isoformat()


class PluginDefinitionError(Exception):
    """预期的插件编写错误，不应打印追溯信息。"""


@dataclass
class PluginRecord:
    instance_id: str
    plugin_name: str
    path: Optional[Path]
    display_name: str = ""
    status: str = "discovered"
    module: Optional[ModuleType] = None
    context: Optional[PluginContext] = None
    error: Optional[str] = None
    generation: int = 1
    lifecycle_phase: str = "idle"
    lifecycle_updated_at: str = field(default_factory=_utc8_now_iso)
    reload_count: int = 0
    last_reload_reason: Optional[str] = None
    last_reload_at: Optional[str] = None
    created_at: str = field(default_factory=_utc8_now_iso)
    discovered_at: str = field(default_factory=_utc8_now_iso)
    loaded_at: Optional[str] = None
    activated_at: Optional[str] = None
    disposed_at: Optional[str] = None
    unloaded_at: Optional[str] = None
    last_error: Optional[str] = None
    last_error_at: Optional[str] = None
    listener_ids: list[str] = field(default_factory=list)
    plugin_instance: Any = None
    config: Dict[str, Any] = field(default_factory=dict)
    provides: set[str] = field(default_factory=set)
    needs: set[str] = field(default_factory=set)
    wants: set[str] = field(default_factory=set)
    missing: set[str] = field(default_factory=set)


class PluginLoader:
    """从plugins/目录中发现、加载和卸载插件。"""

    @dataclass
    class PluginSource:
        """插件来源描述。"""

        source: Literal["pypi"]
        path: Optional[Path] = None
        entry_point: Any = None
        module_name: Optional[str] = None
        distribution: Optional[str] = None
        version: Optional[str] = None

    def __init__(
        self,
        events,
        runtime: Any = None,
        plugins_dir: Optional[Path] = None,
        service: Optional[ServiceRegistry] = None,
    ):
        self.events = events
        self.runtime = {} if runtime is None else runtime
        self.plugins_dir = plugins_dir or (Path.cwd() / "plugins")
        self.service = service or ServiceRegistry()
        self.pypi_site_packages_dir = ensure_pypi_site_packages_on_syspath(self.plugins_dir)
        self.records: Dict[str, PluginRecord] = {}
        self.discovered_plugins: Dict[str, PluginLoader.PluginSource] = {}
        self.startup_failed_instances: Dict[str, str] = {}
        self.startup_missing_instances: set[str] = set()
        self._pulse: set[str] = set()
        self._task: Optional[asyncio.Task[Any]] = None
        self._busy = False

        self.service.watch("before", self._before)
        self.service.watch("after", self._after)

    def _iter_entry_points(self) -> list[Any]:
        """读取 plugins/pypi/site-packages 中的插件 Entry Points。"""
        try:
            return list(iter_plugin_entry_points(self.plugins_dir))
        except Exception as e:
            logger.warning(f"读取本地 PyPI Entry Points 失败: {e}")
            return []

    def discover(self) -> Dict[str, PluginSource]:
        """
        扫描并发现可用插件来源（统一为 Entry Point）。

        规则：
        - 仅从 plugins/pypi/site-packages 的 Entry Point 发现插件。
        - 本地插件需先通过 `pip install -e` 安装后才可被发现。

        Returns:
            Dict[str, PluginSource]: 键为插件名、值为插件来源描述的映射。
        """
        ensure_pypi_site_packages_on_syspath(self.plugins_dir)
        discovered: Dict[str, PluginLoader.PluginSource] = {}

        for ep in self._iter_entry_points():
            plugin_name = str(getattr(ep, "name", "") or "").strip()
            if not plugin_name:
                continue

            dist = getattr(ep, "dist", None)
            distribution = getattr(dist, "name", None)
            version = getattr(dist, "version", None)
            editable_path = resolve_entry_point_editable_project_path(ep)

            discovered[plugin_name] = self.PluginSource(
                source="pypi",
                path=editable_path,
                entry_point=ep,
                module_name=getattr(ep, "module", None),
                distribution=distribution,
                version=version,
            )

        self.discovered_plugins = discovered
        logger.info(f"插件扫描完成，共发现 {len(discovered)} 个插件")
        return discovered

    def _meta(self, plugin_class: type[Any]) -> tuple[set[str], set[str], set[str]]:
        spec = ServiceSpec.load(plugin_class)
        return spec.sets()

    def _plan(self, instances: Iterable[Any]) -> tuple[list[str], dict[str, set[str]], dict[str, tuple[set[str], set[str], set[str]]]]:
        enabled: dict[str, Any] = {}
        order: list[str] = []
        meta: dict[str, tuple[set[str], set[str], set[str]]] = {}

        for item in instances:
            if not bool(getattr(item, "enabled", False)):
                continue
            instance_id = str(getattr(item, "id"))
            plugin_name = str(getattr(item, "plugin"))
            if not instance_id or not plugin_name:
                continue
            enabled[instance_id] = item
            order.append(instance_id)

            plugin_source = self.discovered_plugins.get(plugin_name)
            if plugin_source is None:
                meta[instance_id] = (set(), set(), set())
                continue

            try:
                _, plugin_class = self._resolve_plugin_module_and_class(plugin_name, plugin_source)
                meta[instance_id] = self._meta(plugin_class)
            except Exception as e:
                logger.warning(
                    f"解析插件依赖声明失败，已按空声明处理: instance_id={instance_id}, plugin={plugin_name}, error={type(e).__name__}: {e}"
                )
                meta[instance_id] = (set(), set(), set())

        providers: dict[str, list[str]] = {}
        for instance_id, payload in meta.items():
            provides, _, _ = payload
            for name in provides:
                providers.setdefault(name, []).append(instance_id)

        missing: dict[str, set[str]] = {}
        edges: dict[str, set[str]] = {instance_id: set() for instance_id in order}
        indegree: dict[str, int] = {instance_id: 0 for instance_id in order}

        for instance_id in order:
            _, needs, _ = meta.get(instance_id, (set(), set(), set()))
            lost = {
                name
                for name in needs
                if not self.service.ready(name) and not providers.get(name)
            }
            if lost:
                missing[instance_id] = lost

            for name in needs:
                if self.service.ready(name):
                    continue
                candidates = sorted(providers.get(name, []))
                if not candidates:
                    continue
                owner = candidates[0]
                if owner == instance_id:
                    continue
                if instance_id not in edges[owner]:
                    edges[owner].add(instance_id)
                    indegree[instance_id] += 1

        queue: list[str] = [instance_id for instance_id in order if indegree[instance_id] == 0]
        queue.sort(key=lambda item: order.index(item))
        planned: list[str] = []

        while queue:
            current = queue.pop(0)
            planned.append(current)
            for target in sorted(edges.get(current, set())):
                indegree[target] -= 1
                if indegree[target] == 0:
                    queue.append(target)
                    queue.sort(key=lambda item: order.index(item))

        if len(planned) < len(order):
            left = [instance_id for instance_id in order if instance_id not in planned]
            logger.warning(f"检测到插件依赖环，剩余实例将按原顺序加载: {left}")
            planned.extend(left)

        return planned, missing, meta

    def _before(self, _name: str, users: set[str]) -> None:
        if self._busy:
            return
        for instance_id in users:
            record = self.records.get(instance_id)
            if record is None:
                continue
            if record.status != "active":
                continue
            self._pulse.add(instance_id)

    def _after(self, _name: str, _users: set[str]) -> None:
        if self._busy:
            return
        if not self._pulse:
            return
        if self._task is not None and not self._task.done():
            return
        self._spawn(self._sync())

    def _spawn(self, coro: Any) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._task = loop.create_task(coro)

    async def _sync(self) -> None:
        targets = sorted(self._pulse)
        self._pulse.clear()
        if not targets:
            return

        self._busy = True
        try:
            for instance_id in targets:
                record = self.records.get(instance_id)
                if record is None:
                    continue
                if record.status == "active":
                    await self.unload_instance(instance_id)

            for instance_id in targets:
                record = self.records.get(instance_id)
                if record is None:
                    continue
                if record.config is None:
                    continue
                await self.load_instance(
                    instance_id=record.instance_id,
                    plugin_name=record.plugin_name,
                    instance_name=record.display_name,
                    config=deepcopy(record.config),
                    provides=set(record.provides),
                    needs=set(record.needs),
                    wants=set(record.wants),
                )
        finally:
            self._busy = False

    def _load_plugin_config(self, plugin_name: str, plugin_source: PluginSource) -> Dict[str, Any]:
        if plugin_source.path is None:
            return {}

        plugin_path = plugin_source.path
        config_path = plugin_path / "config.json"
        if not config_path.exists():
            return {}

        try:
            with config_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
            logger.warning(f"插件配置格式错误（非对象），已忽略: {plugin_name}")
            return {}
        except Exception as e:
            logger.error(f"读取插件配置失败: {plugin_name}, error={e}")
            return {}

    def _load_plugin_class_from_entry_point(self, plugin_name: str, entry_point: Any) -> tuple[Optional[ModuleType], type[Any]]:
        """从 PyPI Entry Point 加载插件类入口。

        Args:
            plugin_name (str): 插件名。
            entry_point (Any): 插件 Entry Point。

        Returns:
            tuple[Optional[ModuleType], type[Any]]: 模块对象与插件类对象。

        Raises:
            PluginDefinitionError: 当入口返回值既不是模块也不是类，或模块缺少 Plugin 类时抛出。
        """
        loaded = entry_point.load()
        if inspect.ismodule(loaded):
            plugin_class = getattr(loaded, "Plugin", None)
            if inspect.isclass(plugin_class):
                return loaded, plugin_class
            raise PluginDefinitionError(f"插件缺少类入口 Plugin: {plugin_name}")

        if inspect.isclass(loaded):
            module = inspect.getmodule(loaded)
            return module, loaded

        raise PluginDefinitionError(f"插件 Entry Point 返回了不支持的对象（需要模块或类）: {plugin_name}")

    def _clear_cached_pypi_module(self, plugin_name: str, plugin_source: PluginSource) -> None:
        """清理 PyPI 插件模块缓存，确保重载使用最新代码。"""
        if plugin_source.source != "pypi":
            return

        module_name = str(plugin_source.module_name or "").strip()
        if not module_name:
            entry_point = plugin_source.entry_point
            module_name = str(getattr(entry_point, "module", "") or "").strip()
        if not module_name:
            return

        target_keys = [
            key
            for key in list(sys.modules.keys())
            if key == module_name or key.startswith(f"{module_name}.")
        ]
        for key in target_keys:
            sys.modules.pop(key, None)

        if target_keys:
            logger.info(
                f"已清理 PyPI 插件模块缓存: plugin={plugin_name}, modules={len(target_keys)}"
            )

    def _resolve_plugin_module_and_class(
        self,
        plugin_name: str,
        plugin_source: PluginSource,
        *,
        clear_cache: bool = True,
    ) -> tuple[Optional[ModuleType], type[Any]]:
        """解析插件模块与类入口。

        Args:
            plugin_name (str): 插件名。
            plugin_source (PluginSource): 插件来源描述。

        Returns:
            tuple[Optional[ModuleType], type[Any]]: 模块对象与插件类。

        Raises:
            PluginDefinitionError: 当缺少 Entry Point、或未导出 Plugin 类时抛出。
        """
        if plugin_source.entry_point is None:
            raise PluginDefinitionError(f"PyPI 插件缺少 Entry Point: {plugin_name}")
        if clear_cache:
            self._clear_cached_pypi_module(plugin_name, plugin_source)
        return self._load_plugin_class_from_entry_point(plugin_name, plugin_source.entry_point)

    @staticmethod
    def _ensure_required_lifecycle_methods(plugin_name: str, instance: Any) -> None:
        """校验插件实例是否完整实现生命周期方法。

        Args:
            plugin_name (str): 插件名。
            instance (Any): 插件实例。

        Returns:
            None: 无返回值。

        Raises:
            PluginDefinitionError: 当缺失生命周期方法或方法不可调用时抛出。
        """
        missing: list[str] = []
        invalid: list[str] = []
        for method_name in REQUIRED_LIFECYCLE_METHODS:
            method = getattr(instance, method_name, None)
            if method is None:
                missing.append(method_name)
                continue
            if not callable(method):
                invalid.append(method_name)

        if missing:
            raise PluginDefinitionError(
                f"插件生命周期方法缺失: plugin={plugin_name}, missing={','.join(missing)}"
            )
        if invalid:
            raise PluginDefinitionError(
                f"插件生命周期方法不可调用: plugin={plugin_name}, invalid={','.join(invalid)}"
            )

    async def _call_lifecycle_method(self, instance: Any, method_name: str, *args: Any) -> None:
        """调用插件生命周期方法，并兼容同步/异步实现。

        Args:
            instance (Any): 插件实例对象。
            method_name (str): 生命周期方法名。
            *args (Any): 生命周期方法参数。

        Returns:
            None: 无返回值。

        Raises:
            AttributeError: 目标方法不存在时抛出。
            TypeError: 目标属性存在但不可调用时抛出。
            Exception: 生命周期方法执行失败时透传原始异常。
        """
        method = getattr(instance, method_name, None)
        if method is None:
            raise AttributeError(f"生命周期方法不存在: {method_name}")
        if not callable(method):
            raise TypeError(f"生命周期方法不可调用: {method_name}")

        result = method(*args)
        if inspect.isawaitable(result):
            await result

    async def _call_optional_lifecycle_method(self, instance: Any, method_name: str, *args: Any) -> bool:
        """尝试调用可选生命周期方法。

        Args:
            instance (Any): 插件实例对象。
            method_name (str): 生命周期方法名。
            *args (Any): 生命周期方法参数。

        Returns:
            bool: 方法存在并执行时返回 True；方法不存在时返回 False。

        Raises:
            TypeError: 当生命周期属性存在但不可调用时抛出。
            Exception: 生命周期方法执行失败时透传原始异常。
        """
        method = getattr(instance, method_name, None)
        if method is None:
            return False
        if not callable(method):
            raise TypeError(f"生命周期方法不可调用: {method_name}")

        result = method(*args)
        if inspect.isawaitable(result):
            await result
        return True

    def _create_plugin_instance(self, plugin_name: str, plugin_class: type[Any], context: PluginContext) -> Any:
        """构建插件实例并校验生命周期契约。

        Args:
            plugin_name (str): 插件名。
            plugin_class (type[Any]): 插件类。
            context (PluginContext): 插件上下文。

        Returns:
            Any: 插件实例对象。

        Raises:
            PluginDefinitionError: 插件构造失败、缺失生命周期方法、或生命周期方法不可调用时抛出。
        """
        try:
            instance = plugin_class(context)
        except Exception as e:
            raise PluginDefinitionError(
                f"插件实例构造失败: plugin={plugin_name}, error={type(e).__name__}: {e}"
            ) from e

        self._ensure_required_lifecycle_methods(plugin_name, instance)
        return instance

    def _mark_status(self, record: PluginRecord, status: str) -> None:
        """更新插件实例状态并记录对应时间戳。"""
        record.status = status

        status_time_map = {
            "discovered": "discovered_at",
            "loaded": "loaded_at",
            "active": "activated_at",
            "disposed": "disposed_at",
            "unloaded": "unloaded_at",
        }
        time_field = status_time_map.get(status)
        if time_field is not None:
            setattr(record, time_field, _utc8_now_iso())

        if status in {"active", "unloaded"}:
            record.error = None

        publish_runtime_record(record, event="status")

    def _mark_lifecycle_phase(self, record: PluginRecord, phase: str) -> None:
        """更新插件生命周期阶段并刷新时间戳。

        Args:
            record (PluginRecord): 插件运行记录。
            phase (str): 生命周期阶段名称。

        Returns:
            None: 无返回值。

        Raises:
            TypeError: 当 phase 不是字符串时抛出。
            ValueError: 当 phase 为空字符串时抛出。
        """
        if not isinstance(phase, str):
            raise TypeError("phase 必须是字符串")

        normalized = phase.strip()
        if not normalized:
            raise ValueError("phase 不能为空字符串")

        record.lifecycle_phase = normalized
        record.lifecycle_updated_at = _utc8_now_iso()
        publish_runtime_record(record, event="lifecycle")

    def _mark_error(self, record: PluginRecord, message: str) -> None:
        """记录插件错误并切换为 error 状态。"""
        record.error = message
        record.last_error = message
        record.last_error_at = _utc8_now_iso()
        record.status = "error"
        publish_runtime_record(record, event="error")

    @staticmethod
    def _invoke_with_context(handler: Callable[..., Any], payload: Any, context: PluginContext) -> Any:
        """
        按监听器签名将事件 payload 与上下文注入到处理函数。

        Args:
            handler (Callable[..., Any]): 原始监听器函数或方法。
            payload (Any): 事件载荷。
            context (PluginContext): 插件上下文。

        Returns:
            Any: 监听器返回值。

        Raises:
            TypeError: 监听器参数签名不满足允许形式时抛出。
        """
        signature = inspect.signature(handler)
        params = list(signature.parameters.values())

        if not params:
            raise TypeError("事件监听器至少需要一个参数用于接收 payload")

        has_var_keyword = any(item.kind == inspect.Parameter.VAR_KEYWORD for item in params)
        has_ctx_keyword = has_var_keyword or "ctx" in signature.parameters
        positional_params = [
            item
            for item in params
            if item.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]

        if len(positional_params) >= 2:
            return handler(payload, context)

        if has_ctx_keyword:
            return handler(payload, ctx=context)

        if len(positional_params) == 1:
            return handler(payload)

        raise TypeError("事件监听器参数签名不支持，请使用 (payload) 或 (payload, ctx)")

    def _build_context_bound_handler(
        self,
        *,
        handler: Callable[..., Any],
        context: PluginContext,
    ) -> Callable[[Any], Any]:
        """
        构建自动注入 `ctx` 的监听器包装函数。

        Args:
            handler (Callable[..., Any]): 原始监听器。
            context (PluginContext): 插件上下文。

        Returns:
            Callable[[Any], Any]: 仅接收 payload 的包装监听器。
        """
        if inspect.iscoroutinefunction(handler):
            @wraps(handler)
            async def async_wrapper(payload: Any) -> Any:
                result = self._invoke_with_context(handler, payload, context)
                if inspect.isawaitable(result):
                    return await result
                return result

            return async_wrapper

        @wraps(handler)
        def sync_wrapper(payload: Any) -> Any:
            return self._invoke_with_context(handler, payload, context)

        return sync_wrapper

    @staticmethod
    def _iter_decorated_members(target: Any) -> list[tuple[Callable[..., Any], EventSubscription]]:
        """遍历对象成员并提取 `@on_event` 声明。"""
        result: list[tuple[Callable[..., Any], EventSubscription]] = []
        for _, member in inspect.getmembers(target):
            if not (inspect.isfunction(member) or inspect.ismethod(member)):
                continue

            subscriptions = get_event_subscriptions(member)
            for subscription in subscriptions:
                result.append((member, subscription))
        return result

    def _register_decorated_handlers(
        self,
        *,
        record: PluginRecord,
        target: Any,
    ) -> list[str]:
        """
        将对象上的装饰器监听器注册到事件总线。

        Args:
            record (PluginRecord): 插件记录对象。
            target (Any): 模块对象或插件实例对象。

        Returns:
            list[str]: 新增监听器 ID 列表。

        Raises:
            TypeError: 监听器参数签名非法时抛出。
            ValueError: 监听器作用域为 instance 但实例 ID 缺失时抛出。
        """
        if record.context is None:
            return []

        created_ids: list[str] = []
        members = self._iter_decorated_members(target)
        for member, subscription in members:
            if subscription.scope == "instance" and not record.instance_id:
                raise ValueError("instance 作用域监听器需要实例 ID")

            wrapped = self._build_context_bound_handler(
                handler=member,
                context=record.context,
            )
            listener_id = self.events.on(
                subscription.event,
                wrapped,
                priority=subscription.priority,
                scope=subscription.scope,
                once=subscription.once,
                error_policy=subscription.error_policy,
                owner_plugin_name=record.plugin_name,
                owner_instance_id=record.instance_id,
            )
            created_ids.append(listener_id)

        return created_ids

    def _unregister_record_listeners(self, record: PluginRecord) -> None:
        """移除插件记录关联的全部监听器。"""
        if record.instance_id:
            self.events.off_by_instance(record.instance_id)
        record.listener_ids.clear()

    async def load_plugin(self, plugin_name: str) -> PluginRecord:
        """
        按插件名加载单个插件并激活默认实例。

        Args:
            plugin_name (str): 插件名。

        Returns:
            PluginRecord: 插件加载记录，包含状态、上下文和错误信息。

        Raises:
            KeyError: 重试扫描后仍未发现目标插件时抛出。
        """
        if not self.discovered_plugins:
            self.discover()

        if plugin_name not in self.discovered_plugins:
            self.discover()
        if plugin_name not in self.discovered_plugins:
            raise KeyError(f"未发现插件: {plugin_name}")

        plugin_source = self.discovered_plugins[plugin_name]
        record = PluginRecord(
            instance_id=plugin_name,
            plugin_name=plugin_name,
            path=plugin_source.path,
            display_name=plugin_name,
        )
        self._mark_status(record, "discovered")
        self._mark_lifecycle_phase(record, "discovered")
        self.records[record.instance_id] = record

        try:
            record.module, plugin_class = self._resolve_plugin_module_and_class(
                plugin_name,
                plugin_source,
            )
            provides, needs, wants = self._meta(plugin_class)
            missing = {
                name
                for name in needs
                if name not in provides and not self.service.ready(name)
            }
            if missing:
                record.provides = set(provides)
                record.needs = set(needs)
                record.wants = set(wants)
                record.missing = set(missing)
                self._mark_error(record, f"缺失 required 服务: {', '.join(sorted(missing))}")
                return record

            self._mark_status(record, "loaded")
            self._mark_lifecycle_phase(record, "loaded")

            plugin_logger = get_logger(f"插件:{plugin_name}")
            plugin_config = self._load_plugin_config(plugin_name, plugin_source)

            record.context = PluginContext(
                plugin_name=plugin_name,
                instance_id=plugin_name,
                config=plugin_config,
                logger=plugin_logger,
                events=self.events,
                runtime_capabilities=self.runtime,
                service_registry=self.service,
                server_registry=plugin_server,
                provides=provides,
                needs=needs,
                wants=wants,
            )
            record.config = deepcopy(plugin_config)
            record.provides = set(provides)
            record.needs = set(needs)
            record.wants = set(wants)
            record.missing = set()

            if record.module is not None:
                record.listener_ids.extend(
                    self._register_decorated_handlers(record=record, target=record.module)
                )

            record.plugin_instance = self._create_plugin_instance(
                plugin_name=plugin_name,
                plugin_class=plugin_class,
                context=record.context,
            )
            record.listener_ids.extend(
                self._register_decorated_handlers(record=record, target=record.plugin_instance)
            )
            self._mark_lifecycle_phase(record, "on_load")
            await self._call_optional_lifecycle_method(record.plugin_instance, "on_load", record.context)
            self._mark_lifecycle_phase(record, "on_start")
            await self._call_lifecycle_method(record.plugin_instance, "on_start")

            self._mark_status(record, "active")
            self._mark_lifecycle_phase(record, "active")
            logger.info(f"插件已激活: {plugin_name}")
        except PluginDefinitionError as e:
            self._unregister_record_listeners(record)
            await plugin_server.unregister_owner(record.instance_id)
            self._mark_error(record, str(e))
            logger.error(f"插件加载失败: {plugin_name}, error={e}")
        except Exception as e:
            self._unregister_record_listeners(record)
            await plugin_server.unregister_owner(record.instance_id)
            self._mark_error(record, f"{type(e).__name__}: {e}")
            logger.exception(f"插件加载失败: {plugin_name}, error={e}")

        return record

    async def load_instance(
        self,
        *,
        instance_id: str,
        plugin_name: str,
        instance_name: str,
        config: Dict[str, Any],
        provides: Optional[set[str]] = None,
        needs: Optional[set[str]] = None,
        wants: Optional[set[str]] = None,
    ) -> PluginRecord:
        """
        加载单个插件实例并返回实例记录。

        Args:
            instance_id (str): 插件实例 ID。
            plugin_name (str): 插件名。
            instance_name (str): 实例显示名。
            config (Dict[str, Any]): 实例配置。

        Returns:
            PluginRecord: 实例加载记录；失败信息会写入记录而非向上抛出。
        """
        if not self.discovered_plugins:
            self.discover()

        if plugin_name not in self.discovered_plugins:
            self.discover()
        if plugin_name not in self.discovered_plugins:
            record = PluginRecord(
                instance_id=instance_id,
                plugin_name=plugin_name,
                path=None,
                display_name=instance_name or instance_id,
            )
            self._mark_status(record, "discovered")
            self._mark_error(record, f"未发现插件: {plugin_name}")
            self.records[instance_id] = record
            return record

        plugin_source = self.discovered_plugins[plugin_name]
        record = PluginRecord(
            instance_id=instance_id,
            plugin_name=plugin_name,
            path=plugin_source.path,
            display_name=instance_name or instance_id,
        )
        self._mark_status(record, "discovered")
        self._mark_lifecycle_phase(record, "discovered")
        self.records[instance_id] = record

        try:
            record.module, plugin_class = self._resolve_plugin_module_and_class(
                plugin_name,
                plugin_source,
            )
            static_provides, static_needs, static_wants = self._meta(plugin_class)
            merged_provides = set(provides or static_provides)
            merged_needs = set(needs or static_needs)
            merged_wants = set(wants or static_wants)
            missing = {
                name
                for name in merged_needs
                if name not in merged_provides and not self.service.ready(name)
            }
            if missing:
                record.provides = merged_provides
                record.needs = merged_needs
                record.wants = merged_wants
                record.missing = set(missing)
                self._mark_error(record, f"缺失 required 服务: {', '.join(sorted(missing))}")
                return record

            self._mark_status(record, "loaded")
            self._mark_lifecycle_phase(record, "loaded")

            plugin_logger = get_logger(f"插件:{instance_id}")
            record.context = PluginContext(
                plugin_name=plugin_name,
                instance_id=instance_id,
                config=config,
                logger=plugin_logger,
                events=self.events,
                runtime_capabilities=self.runtime,
                service_registry=self.service,
                server_registry=plugin_server,
                provides=merged_provides,
                needs=merged_needs,
                wants=merged_wants,
            )
            record.config = deepcopy(config)
            record.provides = merged_provides
            record.needs = merged_needs
            record.wants = merged_wants
            record.missing = set()

            if record.module is not None:
                record.listener_ids.extend(
                    self._register_decorated_handlers(record=record, target=record.module)
                )

            record.plugin_instance = self._create_plugin_instance(
                plugin_name=plugin_name,
                plugin_class=plugin_class,
                context=record.context,
            )
            record.listener_ids.extend(
                self._register_decorated_handlers(record=record, target=record.plugin_instance)
            )
            self._mark_lifecycle_phase(record, "on_load")
            await self._call_optional_lifecycle_method(record.plugin_instance, "on_load", record.context)
            self._mark_lifecycle_phase(record, "on_start")
            await self._call_lifecycle_method(record.plugin_instance, "on_start")

            self._mark_status(record, "active")
            self._mark_lifecycle_phase(record, "active")
            logger.info(f"插件实例已激活: {instance_id} ({plugin_name})")
        except PluginDefinitionError as e:
            self._unregister_record_listeners(record)
            await plugin_server.unregister_owner(record.instance_id)
            self._mark_error(record, str(e))
            logger.error(f"插件实例加载失败: {instance_id}, error={e}")
        except Exception as e:
            self._unregister_record_listeners(record)
            await plugin_server.unregister_owner(record.instance_id)
            self._mark_error(record, f"{type(e).__name__}: {e}")
            logger.error(f"插件实例加载失败: {instance_id}, error={type(e).__name__}: {e}")

        return record

    async def load_all(self) -> Dict[str, PluginRecord]:
        """
        加载当前发现到的全部插件。

        Returns:
            Dict[str, PluginRecord]: 全部实例记录映射。
        """
        self.discover()
        for plugin_name in list(self.discovered_plugins.keys()):
            await self.load_plugin(plugin_name)
        return self.records

    async def load_instances(self, instances: Iterable[Any]) -> Dict[str, PluginRecord]:
        """
        批量加载插件实例，并记录启动失败信息。

        Args:
            instances (Iterable[Any]): 待加载的实例对象集合。

        Returns:
            Dict[str, PluginRecord]: 当前全部实例记录映射。
        """
        if not self.discovered_plugins:
            self.discover()
        self.startup_failed_instances = {}
        self.startup_missing_instances = set()
        self.service.clear()

        planned, missing_map, meta_map = self._plan(instances)
        enabled_map: dict[str, Any] = {
            str(getattr(item, "id")): item
            for item in instances
            if bool(getattr(item, "enabled", False))
        }

        for instance_id in planned:
            instance = enabled_map.get(instance_id)
            if instance is None:
                continue

            plugin_name = str(getattr(instance, "plugin"))
            instance_name = str(getattr(instance, "name", "") or "")
            config = dict(getattr(instance, "config", {}) or {})
            provides, needs, wants = meta_map.get(instance_id, (set(), set(), set()))

            if instance_id in missing_map:
                lost = sorted(missing_map[instance_id])
                record = PluginRecord(
                    instance_id=instance_id,
                    plugin_name=plugin_name,
                    path=None,
                    display_name=instance_name or instance_id,
                )
                record.config = deepcopy(config)
                record.provides = set(provides)
                record.needs = set(needs)
                record.wants = set(wants)
                record.missing = set(lost)
                self._mark_status(record, "discovered")
                self._mark_error(record, f"缺失 required 服务: {', '.join(lost)}")
                self.records[instance_id] = record
                self.startup_failed_instances[instance_id] = str(record.error or "未知错误")
                logger.warning(
                    f"插件实例缺失 required 服务，已跳过启动: instance_id={instance_id}, missing={lost}"
                )
                continue

            record = await self.load_instance(
                instance_id=instance_id,
                plugin_name=plugin_name,
                instance_name=instance_name,
                config=config,
                provides=provides,
                needs=needs,
                wants=wants,
            )
            if record.status == "error":
                error_text = str(record.error or "未知错误")
                self.startup_failed_instances[instance_id] = error_text
                if error_text.startswith("未发现插件:"):
                    self.startup_missing_instances.add(instance_id)
                logger.error(
                    f"插件实例加载失败但已忽略（继续启动）: instance_id={instance_id}, plugin={plugin_name}, error='{error_text}'"
                )

        return self.records

    async def unload_plugin(self, plugin_name: str) -> None:
        """
        卸载单个插件实例并执行其释放逻辑。

        Args:
            plugin_name (str): 目标实例 ID（兼容插件名作为默认实例 ID）。

        Returns:
            None: 无返回值。
        """
        record = self.records.get(plugin_name)
        if record is None:
            self.service.drop(plugin_name)
            return

        try:
            if record.plugin_instance is not None:
                self._mark_lifecycle_phase(record, "on_stop")
                await self._call_lifecycle_method(record.plugin_instance, "on_stop", "stop")
                self._mark_lifecycle_phase(record, "on_unload")
                await self._call_optional_lifecycle_method(record.plugin_instance, "on_unload")
            self._mark_status(record, "disposed")
            self._mark_lifecycle_phase(record, "disposed")
        except Exception as e:
            self._mark_error(record, f"{type(e).__name__}: {e}")
            logger.exception(f"插件卸载失败: {plugin_name}, error={e}")
            return
        finally:
            self._unregister_record_listeners(record)
            self.service.drop(record.instance_id)
            await plugin_server.unregister_owner(record.instance_id)

        self._mark_status(record, "unloaded")
        self._mark_lifecycle_phase(record, "unloaded")
        logger.info(f"插件已卸载: {plugin_name}")

    async def unload_instance(self, instance_id: str) -> None:
        """
        卸载指定插件实例。

        Args:
            instance_id (str): 目标实例 ID。

        Returns:
            None: 无返回值。
        """
        await self.unload_plugin(instance_id)

    async def reload_instance(
        self,
        *,
        instance_id: str,
        plugin_name: str,
        instance_name: str,
        config: Dict[str, Any],
        reason: str = "manual",
    ) -> PluginRecord:
        """重载指定插件实例。

        当前实现为基础事务雏形：
        1. 若存在旧实例，先调用 `on_reload_prepare`；
        2. 卸载旧实例；
        3. 加载新实例；
        4. 新实例激活后调用 `on_reload_commit`；
        5. 若加载失败，直接关闭实例并保留错误状态。

        Args:
            instance_id (str): 插件实例 ID。
            plugin_name (str): 插件名。
            instance_name (str): 实例展示名。
            config (Dict[str, Any]): 实例配置。
            reason (str): 重载触发原因。

        Returns:
            PluginRecord: 重载后的实例记录。

        Raises:
            Exception: 生命周期方法或加载流程异常时透传。
        """
        old_record = self.records.get(instance_id)
        if old_record is not None and old_record.plugin_instance is not None:
            old_record.last_reload_reason = reason
            old_record.last_reload_at = _utc8_now_iso()
            self._mark_lifecycle_phase(old_record, "on_reload_prepare")
            await self._call_optional_lifecycle_method(old_record.plugin_instance, "on_reload_prepare")
            self._mark_lifecycle_phase(old_record, "on_stop")
            await self._call_lifecycle_method(old_record.plugin_instance, "on_stop", f"reload:{reason}")

        await self.unload_instance(instance_id)
        new_record = await self.load_instance(
            instance_id=instance_id,
            plugin_name=plugin_name,
            instance_name=instance_name,
            config=config,
        )

        if new_record.status == "error":
            new_record.last_reload_reason = reason
            new_record.last_reload_at = _utc8_now_iso()
            self._mark_lifecycle_phase(new_record, "reload_failed")
            await self.unload_instance(instance_id)
            self._mark_lifecycle_phase(new_record, "closed")
            return new_record

        previous_generation = 0
        if old_record is not None:
            previous_generation = int(getattr(old_record, "generation", 1) or 1)
        new_record.generation = previous_generation + 1
        new_record.reload_count = (old_record.reload_count + 1) if old_record is not None else 1
        new_record.last_reload_reason = reason
        new_record.last_reload_at = _utc8_now_iso()

        if new_record.plugin_instance is not None:
            self._mark_lifecycle_phase(new_record, "on_reload_commit")
            await self._call_optional_lifecycle_method(new_record.plugin_instance, "on_reload_commit")
        self._mark_lifecycle_phase(new_record, "active")
        return new_record

    async def unload_all(self) -> None:
        """
        卸载当前已加载的全部插件实例。

        Returns:
            None: 无返回值。
        """
        for plugin_name in list(self.records.keys()):
            await self.unload_plugin(plugin_name)
