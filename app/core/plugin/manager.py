"""主程序插件系统入口：全局 Manager 单例。

五操作范式：锁 → 预检 → 标记 ×× 中 → 上下游 DFS → 本项（先用户后系统）
→（仅重载再依赖）→ 返回依赖字典；失败上抛，``finally`` 走失败分支。
其它模块只依赖 ``from app.core import Plugin``。

名单权威 = ``Config.plugin_registry``（由 ``discover.refresh`` 按本地发现增改删）；
已加载 = ``_plugin_cls is not None``；状态只写 ``record.info.state``。
公开方法只收配置实例（``PluginRecord`` / ``PluginMeta``），不传插件 id / 包名。
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
import weakref
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID, uuid4

from blinker import Namespace

from app.core.ws import Publisher
from app.core.ws.protocol import ID_PLUGIN, PLUGIN_CAPABILITIES_UPDATED
from app.plugin import uv as uv_tool
from app.plugin.base.game import GameAdapterPlugin, GameTypeDecl
from app.plugin.base.plugin import BasePlugin
from app.plugin.base.script import ScriptAdapterPlugin, ScriptTypeDecl
from app.plugin.calls import CallGate
from app.plugin.errors import (
    PluginBusyError,
    PluginError,
    PluginNotFoundError,
    PluginOperationError,
    PluginPrecheckError,
    PluginStateError,
)
from app.plugin.http import HttpRegistry, collect_route_decls
from app.plugin.runtime import discover, loader
from app.plugin.runtime import market as plugin_market
from app.plugin.runtime.watch import SourceWatcher
from app.plugin.services import ServiceRegistry
from app.plugin.signals import (
    capabilities_changed,
    plugin_signals,
    sources_changed,
)
from app.plugin.types import (
    CORE_DISTRIBUTION_NAME,
    CORE_PLUGIN_NAME,
    MARKET_GATE_TAG,
    PLUGIN_ID_TAG_PREFIX,
    LifecycleContext,
    PluginCodeDrift,
    PluginState,
    SourceChange,
    SourcesChangedPayload,
)
from app.plugin.uv.precheck import host_dependencies
from app.utils import get_logger
from app.utils.common.tools import to_pep440

if TYPE_CHECKING:
    from app.models.config import PluginMeta, PluginRecord

logger = get_logger("插件管理")


class _ServiceResolver:
    """提供注册表的实时查询面，不向插件暴露登记和注销。"""

    def __init__(self, registry: ServiceRegistry) -> None:
        # 注册表持有提供者的绑定方法；弱引用避免查询面反向保活服务提供者。
        """以弱引用绑定服务注册表，提供插件查询入口而不反向保留服务提供者。"""
        self._registry: ServiceRegistry = weakref.proxy(registry)

    def get(self, name: str, default: Any = None) -> Any:
        """按名称查询已发布的插件服务，未发布时返回调用方指定的默认值。"""
        return self._registry.get(name, default)

    def require(self, name: str) -> Any:
        """按名称取得必须存在的插件服务，缺失时由注册表报告服务未就绪。"""
        return self._registry.require(name)


class _PluginManager:
    """主程序插件管理器：DFS 级联、依赖字典、失败分支。"""

    def __init__(self) -> None:
        """建立服务与 HTTP 注册表、专项声明索引、生命周期互斥锁及源码变更观察状态。"""
        self.services = ServiceRegistry()
        self._service_resolver = _ServiceResolver(self.services)
        self.http = HttpRegistry()
        # 已启用适配：注册项 uid → 类型声明（脚本 decl 含 expander_class）
        self.script_types: dict[UUID, ScriptTypeDecl] = {}
        self.game_types: dict[UUID, GameTypeDecl] = {}
        self._busy = asyncio.Lock()
        self._initialized = False
        self._core_pep440: str | None = None
        self._watcher: SourceWatcher | None = None
        self._source_queue: asyncio.Queue[SourcesChangedPayload] | None = None
        self._source_worker_task: asyncio.Task[None] | None = None
        self._calls: dict[UUID, CallGate] = {}

    @asynccontextmanager
    async def _pause_owners(self, owners):
        """暂停指定插件的调用准入，等待在途调用和配置操作收尾，退出时按当前启用状态恢复准入。"""
        from app.core.plugin.operations import Operations

        owners = tuple(owners)
        gates = {
            uid: (self._calls[uid], self._calls[uid].accepting)
            for uid in owners
            if uid in self._calls
        }
        for gate, _ in gates.values():
            gate.accepting = False
        try:
            async with Operations.pause_owners(owners):
                await asyncio.gather(*(gate.drain() for gate, _ in gates.values()))
                yield
        finally:
            from app.core import Config

            for uid, (gate, accepting) in gates.items():
                record = Config.plugin_registry.get(uid)
                # 只有仍然启用的原实例才恢复准入；旧实例在卸载或换类后保持封闭。
                gate.accepting = bool(
                    accepting
                    and self.services.accepting
                    and self._calls.get(uid) is gate
                    and record is not None
                    and record._plugin is not None
                    and record.info.state == PluginState.ENABLED
                )

    async def _close_instance_work(self, plugin: BasePlugin) -> None:
        """注销插件实例拥有的背景任务组并关闭调用入口，避免实例卸载后继续执行工作。"""
        from app.core.background_tasks import BackgroundTaskManager

        if plugin._background_tasks is not None:
            await BackgroundTaskManager.unregister_group(plugin._background_tasks)
        gate = self._calls.pop(plugin.record.uid, None)
        if gate is not None:
            gate.accepting = False

    # ==================== 初始化 ====================

    async def initialize(self) -> None:
        """登记 core → discover.refresh → load → 按 ``enabled`` DFS 启用。"""
        async with self._hold():
            uv_tool.ensure()
            site = uv_tool.site_dir()
            from app.core.config import Config

            src = Config.source_path / "plugins" / "auto_mas_core" / "src"
            # SDK 源码属于进程初始化环境，供本地与已安装插件共享同一类型协议。
            core_src = str(src.resolve())
            if core_src not in sys.path:
                sys.path.insert(0, core_src)

            from app.core.config import Config

            # ── 登记合成 auto-mas-core ──
            pep = to_pep440(Config.VERSION)
            self._core_pep440 = pep
            safe_name = CORE_DISTRIBUTION_NAME.replace("-", "_")
            for child in site.glob(f"{safe_name}-*.dist-info"):
                if child.is_dir() and (child / "AUTO_MAS_SYNTHETIC").is_file():
                    for f in child.iterdir():
                        f.unlink(missing_ok=True)
                    child.rmdir()
            dist_dir = site / f"{safe_name}-{pep}.dist-info"
            dist_dir.mkdir(parents=True, exist_ok=True)
            # 合成 METADATA：keywords 门禁供已装视角发现；不再写 entry_points
            (dist_dir / "METADATA").write_text(
                "\n".join(
                    [
                        "Metadata-Version: 2.1",
                        f"Name: {CORE_DISTRIBUTION_NAME}",
                        f"Version: {pep}",
                        *(f"Requires-Dist: {dep}" for dep in host_dependencies()),
                        "Summary: AUTO-MAS core protocol (synthetic)",
                        f"Keywords: {MARKET_GATE_TAG},{PLUGIN_ID_TAG_PREFIX}{CORE_PLUGIN_NAME}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (dist_dir / "INSTALLER").write_text("auto-mas\n", encoding="utf-8")
            (dist_dir / "AUTO_MAS_SYNTHETIC").write_text("1\n", encoding="utf-8")
            if not src.is_dir():
                raise PluginError(
                    "核心包源码缺失，无法登记 auto-mas-core",
                    payload={"path": str(src)},
                )
            # ── 发现写注册表 → load 全部 → 按 enabled 启用 ──
            await discover.refresh()
            core_record = self._record_by_plugin_id(CORE_PLUGIN_NAME)
            if core_record is None:
                raise PluginError(
                    "核心包登记后未被发现（检查合成 dist-info / plugins/auto_mas_core）",
                    payload={"pep": pep, "site": str(site)},
                )

            for record in sorted(
                Config.plugin_registry.values(),
                key=lambda r: r.info.plugin_name or "",
            ):
                # 禁用且来源已移除的登记项只保留在插件中心展示；没有可加载来源时不进入
                # loader，避免启动日志把“已移除插件”误报成新的运行故障。
                if (
                    not record.info.enabled
                    and record._project_dir is None
                    and record.info.code_drift == PluginCodeDrift.PACKAGE_REMOVED
                ):
                    continue
                try:
                    await self.load(record, held=True)
                except Exception:
                    logger.exception(f"启动时加载插件失败: {record.info.plugin_name}")
                    continue

            await self.enable(core_record, held=True)

            for record in list(Config.plugin_registry.values()):
                name = record.info.plugin_name
                if (
                    not record.info.enabled
                    or not name
                    or name == CORE_PLUGIN_NAME
                    or record._plugin_cls is None
                ):
                    continue
                try:
                    await self.enable(record, held=True)
                except Exception:
                    logger.exception(f"启动时启用插件失败: {name}")
                    continue

            self._initialized = True

            # ── 源码监视：plugins/*/ 代码变更 → sources_changed → 增量 refresh ──
            sources_changed.connect(self._on_sources_changed)
            self._source_queue = asyncio.Queue()
            self._source_worker_task = asyncio.create_task(self._source_worker())
            self._watcher = SourceWatcher(plugins_dir=Config.plugins_path)
            self._watcher.start()

    def seal(self) -> None:
        """退出开始即拒绝新的公开调用；已有调用由 shutdown 等待实际结束。"""
        self.http.seal()
        self.services.seal()
        for gate in self._calls.values():
            gate.accepting = False

    async def stop_watching(self) -> None:
        """停止监视及元数据刷新，在主业务退出前收敛新派发。"""
        watcher = self._watcher
        self._watcher = None
        if watcher is not None:
            await watcher.stop()
        sources_changed.disconnect(self._on_sources_changed)
        source_task = self._source_worker_task
        self._source_worker_task = None
        self._source_queue = None
        if source_task is not None:
            source_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await source_task

    async def shutdown(self) -> None:
        """进程退出收尾（≠ 产品禁用；假定随后进程退出）。

        1. 密封 HTTP / 服务，挡住新输入；
        2. 依赖方优先调用 ``on_teardown``（**不**落盘、不释实例、不写七态、
           不卸挂载/索引；**不** ``system_disable`` / ``remove_type``）；
        3. 不改 ``plugin_registry.enabled``；配置落盘由主程序 teardown 末尾
           ``config_manager.flush()`` 统一完成。

        主程序应先停 WS / 任务，再调本方法（见 ``main`` teardown）。
        """
        if not self._initialized:
            return
        await self.stop_watching()
        async with self._busy:
            # ── 1. 密封对外入口（网关 503；服务 get/require 拒绝）──
            self.seal()
            await asyncio.gather(*(gate.drain() for gate in self._calls.values()))

            # ── 2. 已启用插件：依赖方优先；仅业务收尾（落盘交给主程序 flush）──
            done: set[str] = set()

            async def visit(record: PluginRecord) -> None:
                """按依赖关系先关闭下游插件，再关闭当前插件，去重访问并记录生命周期清理异常。"""
                uid_s = str(record.uid)
                if uid_s in done:
                    return
                done.add(uid_s)
                if record._plugin_cls is None:
                    return
                if record.info.state != PluginState.ENABLED:
                    return
                for dep_record in self._downstream(record):
                    await visit(dep_record)

                plugin = record._plugin
                if plugin is not None:
                    try:
                        await self._close_instance_work(plugin)
                        await plugin.on_teardown()
                    except Exception:
                        logger.exception(
                            f"插件 teardown 失败: {record.info.plugin_name}"
                        )

            for record in self.list_plugins():
                if record.info.state == PluginState.ENABLED:
                    await visit(record)

            self._initialized = False

    # ==================== 忙锁 ====================

    @asynccontextmanager
    async def _hold(self) -> AsyncGenerator[None]:
        """互斥保护插件生命周期变更，已有管理操作执行时立即报告插件系统忙。"""
        if self._busy.locked():
            raise PluginBusyError("插件系统忙，请稍后重试")
        async with self._busy:
            yield

    # ==================== 对外生命周期 ====================

    async def load(
        self,
        record: PluginRecord,
        *,
        held: bool = False,
    ) -> dict[str, Any]:
        """加载 → 禁用；返回依赖字典（恒空）。"""
        if not held:
            async with self._hold():
                return await self.load(record, held=True)

        name = record.info.plugin_name
        # 幂等：已加载且处于干净稳态（故障态允许再 load）
        if record._plugin_cls is not None and record.info.state in {
            PluginState.DISABLED,
            PluginState.ENABLED,
        }:
            return {}

        # ── 预检：import_name + PLUGIN 可导入 + 操作权限（未进 ×× 中）──
        self._assert_allowed(record, "load")
        if not record.info.import_name:
            await discover.refresh()
        if not record.info.import_name:
            raise PluginPrecheckError(f"未发现插件: {name}", payload={"name": name})
        try:
            cls = loader.load(record)
        except Exception as exc:
            record.info.state = PluginState.FAULT_LOAD
            record.info.last_error = str(exc)
            await record.commit()
            raise

        record.info.lifecycle_context = LifecycleContext.NORMAL
        record.info.state = PluginState.LOADING
        await record.commit()
        # 类已解析即可视为「在列表」；失败分支保留 _plugin_cls 落 fault_load
        record._plugin_cls = cls
        try:
            # load 只解析类；实例延后到 enable 构造
            record._plugin = None
            record.info.state = PluginState.DISABLED
            record.info.lifecycle_context = LifecycleContext.IDLE
            record.info.last_error = ""
            record.info.code_drift = PluginCodeDrift.NORMAL
            await record.commit()
            return {}
        except Exception as exc:
            # load 失败仍在列表：保留 _plugin_cls，落 fault_load
            await self._fail_branch(
                record,
                fault=PluginState.FAULT_LOAD,
                during=PluginState.LOADING,
                exc=exc,
                plugin=None,
                user_cleanup=False,
            )
            raise PluginOperationError(str(exc), payload={"name": name}) from exc

    async def enable(
        self,
        record: PluginRecord,
        *,
        held: bool = False,
        dep_path: list[str] | None = None,
        ctx: LifecycleContext = LifecycleContext.NORMAL,
    ) -> dict[str, Any]:
        """DFS 启用；返回嵌套依赖字典。"""
        if not held:
            async with self._hold():
                return await self.enable(record, held=True, dep_path=dep_path, ctx=ctx)

        path_list = list(dep_path or [])
        name = record.info.plugin_name
        uid_s = str(record.uid)
        if uid_s in path_list:
            raise PluginPrecheckError(
                f"服务依赖回环: {' → '.join([*path_list, uid_s])}",
                payload={"path": [*path_list, uid_s]},
            )
        if record._plugin_cls is None:
            raise PluginNotFoundError(f"插件不在列表中: {name}", payload={"name": name})
        self._assert_allowed(record, "enable")
        if self._is_enabled(record, ctx=ctx):
            return {}
        # 按语境允许进入态：根/级联 → disabled|fault_runtime；本项 reload 另允 reloading
        allowed_in = {PluginState.DISABLED, PluginState.FAULT_RUNTIME}
        if ctx == LifecycleContext.RELOAD:
            allowed_in.add(PluginState.RELOADING)
        if record.info.state not in allowed_in:
            raise PluginStateError(
                f"插件 `{name}` 状态为 {record.info.state}，无法启用"
            )

        # 系统预检：上游可解析为配置条目
        ups = self._upstream(record)
        assert record._plugin_cls is not None
        plugin_cls = record._plugin_cls

        # ── 先建配置，再构造实例（config 经构造注入）──
        config_cls = getattr(plugin_cls, "config_class", None)
        config = None
        if config_cls is not None:
            for attr_name in dir(config_cls):
                if attr_name.startswith("_"):
                    continue
                try:
                    attr = getattr(config_cls, attr_name)
                except Exception:
                    continue
                name_attr = getattr(attr, "name", None)
                if attr.__class__.__name__ == "ConfigCollection" and name_attr:
                    raise PluginPrecheckError(
                        f"插件 `{name}` 配置类禁止设置 Collection name=（字段 {attr_name}）",
                        payload={
                            "plugin": name,
                            "field": attr_name,
                            "name": name_attr,
                        },
                    )
            for base in getattr(config_cls, "__mro__", (config_cls,)):
                model_fields = getattr(base, "model_fields", None)
                if not isinstance(model_fields, dict):
                    continue
                for field in model_fields.values():
                    default = getattr(field, "default", None)
                    if (
                        default is not None
                        and default.__class__.__name__ == "ConfigCollection"
                        and getattr(default, "name", None)
                    ):
                        raise PluginPrecheckError(
                            f"插件 `{name}` 配置字段禁止 Collection name=",
                            payload={
                                "plugin": name,
                                "name": getattr(default, "name", None),
                            },
                        )
            from app.core.config import Config

            config_path = Config.config_path / "plugins" / f"{name}.yaml"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            if not hasattr(config_cls, "build"):
                raise PluginPrecheckError(
                    f"插件 `{name}` 的 config_class 未实现 build()",
                    payload={"plugin": name, "config_class": config_cls.__name__},
                )
            config = config_cls.build(file=config_path)
            record._config = config
            # activate 在进入 ×× 中之后、登记前完成（与事务同段）

        try:
            plugin = plugin_cls(config=config, record=record)
        except BaseException:
            await self._release_config(record)
            raise
        from app.core.background_tasks import BackgroundTaskManager
        from app.core.config import Config

        gate = CallGate()
        self._calls[record.uid] = gate
        record._plugin = plugin
        try:
            plugin.bind_background_tasks(
                BackgroundTaskManager.register_group(
                    f"plugin:{record.uid}:{uuid4()}",
                    max_running=Config.setting.plugin.max_operations,
                    max_retained=Config.setting.plugin.max_operations,
                )
            )
            if isinstance(plugin, GameAdapterPlugin):
                from app.core.plugin.adapters import GameAdapterRuntime

                plugin.bind_runtime(GameAdapterRuntime(plugin))
            elif isinstance(plugin, ScriptAdapterPlugin):
                from app.core.plugin.adapters import ScriptAdapterRuntime

                plugin.bind_runtime(ScriptAdapterRuntime(plugin))
            plugin.bind_services(self._service_resolver)

            await plugin.pre_enable()
        except BaseException:
            await self._close_instance_work(plugin)
            await self._release_config(record)
            record._plugin = None
            raise

        deps: dict[str, Any] = {}
        try:
            record.info.lifecycle_context = ctx
            # 首次状态提交也可能等待配置锁，必须覆盖失败与取消清理。
            if ctx in {LifecycleContext.NORMAL, LifecycleContext.RELOAD_CASCADE}:
                record.info.state = PluginState.ENABLING
                await record.commit()
            # ── 上游 DFS ──
            path = [*path_list, uid_s]
            for dep_record in ups:
                dep_id = dep_record.info.plugin_name
                deps[dep_id] = await self.enable(
                    dep_record, held=True, dep_path=path, ctx=ctx
                )

            # ── 激活配置根（若有）──
            if config is not None:
                await config.activate()
                record._config = config
            else:
                record._config = None

            # ── 用户段 ──
            await plugin.on_enable()

            # ── 系统段：服务/HTTP/类型表 + system_enable ──
            record._degraded_wants = [
                w
                for w in list(record.info.wants)
                if (
                    (prov := self._provider(w)) is None
                    or not self._is_enabled(prov, ctx=ctx)
                )
            ]

            for svc_name, method_name in plugin.provides_services.items():
                method = getattr(plugin, method_name, None)
                if callable(method):
                    self.services.register(svc_name, gate.wrap(method), owner=name)

            routes = [
                replace(route, handler=gate.wrap(route.handler))
                for route in collect_route_decls(plugin)
            ]
            if routes or plugin.api_router is not None:
                self.http.mount(name, routes, router=plugin.api_router, gate=gate)

            if isinstance(plugin, (ScriptAdapterPlugin, GameAdapterPlugin)):
                await plugin.system_enable()
            self.http.invalidate_schema()

            # 根语义落启用稳态；内嵌 reload 只记意图，由父操作收尾
            record.info.enabled = True
            record.info.last_error = ""
            if ctx in {LifecycleContext.NORMAL, LifecycleContext.RELOAD_CASCADE}:
                record.info.state = PluginState.ENABLED
                record.info.lifecycle_context = LifecycleContext.IDLE
            await record.commit()
            capabilities_changed.send(self, name=name, enabled=True)
            await Publisher.send(
                id=ID_PLUGIN, type=PLUGIN_CAPABILITIES_UPDATED, data={}
            )
            return deps
        except asyncio.CancelledError as exc:
            await self._fail_branch(
                record,
                fault=PluginState.FAULT_RUNTIME,
                during=PluginState.ENABLING,
                exc=exc,
                plugin=plugin,
            )
            raise
        except Exception as exc:
            await self._fail_branch(
                record,
                fault=PluginState.FAULT_RUNTIME,
                during=PluginState.ENABLING,
                exc=exc,
                plugin=plugin,
            )
            raise PluginOperationError(str(exc), payload={"name": name}) from exc

    @asynccontextmanager
    async def _pause_operations(self, record: PluginRecord):
        """收集当前插件及其下游依赖者，在上下文内统一暂停调用与配置操作。"""
        owners: set[UUID] = set()
        pending = [record]
        while pending:
            current = pending.pop()
            if current.uid in owners:
                continue
            owners.add(current.uid)
            pending.extend(self._downstream(current))
        async with self._pause_owners(owners):
            yield

    async def disable(
        self,
        record: PluginRecord,
        *,
        held: bool = False,
        dep_path: list[str] | None = None,
        ctx: LifecycleContext = LifecycleContext.NORMAL,
    ) -> dict[str, Any]:
        """DFS 禁用。"""
        if not held:
            async with self._pause_operations(record), self._hold():
                return await self.disable(record, held=True, dep_path=dep_path, ctx=ctx)

        path_list = list(dep_path or [])
        name = record.info.plugin_name
        uid_s = str(record.uid)
        if uid_s in path_list:
            raise PluginPrecheckError(
                f"服务依赖回环: {' → '.join([*path_list, uid_s])}",
                payload={"path": [*path_list, uid_s]},
            )
        if record._plugin_cls is None:
            raise PluginNotFoundError(f"插件不在列表中: {name}", payload={"name": name})
        if record.info.is_core:
            raise PluginPrecheckError("核心插件不可禁用", payload={"name": name})
        self._assert_allowed(record, "disable")
        if record.info.state in {
            PluginState.DISABLED,
            PluginState.FAULT_LOAD,
            PluginState.FAULT_RUNTIME,
            PluginState.UNLOADED,
        }:
            return {}
        # 按语境允许进入态：根/级联仅 enabled；reload 另允 reloading；unload 另允 unloading
        allowed_in = {PluginState.ENABLED}
        if ctx == LifecycleContext.RELOAD:
            allowed_in.add(PluginState.RELOADING)
        elif ctx == LifecycleContext.UNLOAD:
            allowed_in.add(PluginState.UNLOADING)
        if record.info.state not in allowed_in:
            raise PluginStateError(
                f"插件 `{name}` 状态为 {record.info.state}，无法禁用"
            )

        plugin = record._plugin
        # 撤类型路径须先过锁预检（reload/cascade 不撤表，见设计 §7.2/§7.5）
        if (
            ctx in {LifecycleContext.NORMAL, LifecycleContext.UNLOAD}
            and plugin is not None
            and isinstance(plugin, (ScriptAdapterPlugin, GameAdapterPlugin))
        ):
            plugin.precheck_locks()

        downs = self._downstream(record)
        if plugin is not None:
            await plugin.pre_disable()

        record.info.lifecycle_context = ctx
        # 根语义写禁用中；本项内嵌 reload/unload 保持父 ××中
        if ctx in {LifecycleContext.NORMAL, LifecycleContext.RELOAD_CASCADE}:
            record.info.state = PluginState.DISABLING
            await record.commit()
        deps: dict[str, Any] = {}
        try:
            # ── 下游 DFS ──
            path = [*path_list, uid_s]
            for dep_record in downs:
                dep_id = dep_record.info.plugin_name
                deps[dep_id] = await self.disable(
                    dep_record, held=True, dep_path=path, ctx=ctx
                )

            # ── 用户段 + 系统段 ──
            if plugin is not None:
                await self._close_instance_work(plugin)
                await plugin.on_disable()

            await self._release_config(record)
            self.services.unregister_owner(name)
            self.http.unmount(name)
            if isinstance(plugin, (ScriptAdapterPlugin, GameAdapterPlugin)):
                await plugin.system_disable()

            record._plugin = None
            record.info.last_error = ""
            # 根语义落禁用；内嵌路径不假写 enabled/state（父操作收尾）
            if ctx in {LifecycleContext.NORMAL, LifecycleContext.RELOAD_CASCADE}:
                record.info.state = PluginState.DISABLED
                record.info.lifecycle_context = LifecycleContext.IDLE
                record.info.enabled = False
            await record.commit()
            capabilities_changed.send(self, name=name, enabled=False)
            await Publisher.send(
                id=ID_PLUGIN, type=PLUGIN_CAPABILITIES_UPDATED, data={}
            )
            return deps
        except Exception as exc:
            await self._fail_branch(
                record,
                fault=PluginState.FAULT_RUNTIME,
                during=PluginState.DISABLING,
                exc=exc,
                plugin=plugin,
            )
            raise PluginOperationError(str(exc), payload={"name": name}) from exc

    async def unload(
        self,
        record: PluginRecord,
        *,
        held: bool = False,
        dep_path: list[str] | None = None,
        ctx: LifecycleContext = LifecycleContext.NORMAL,
        remove_record: bool = True,
    ) -> dict[str, Any]:
        """DFS 释放插件运行时；卸包入口可保留注册项，待发行包与配置删除成功后再移除。"""
        if not held:
            async with self._pause_operations(record), self._hold():
                return await self.unload(
                    record,
                    held=True,
                    dep_path=dep_path,
                    ctx=ctx,
                    remove_record=remove_record,
                )

        path_list = list(dep_path or [])
        name = record.info.plugin_name
        uid_s = str(record.uid)
        if uid_s in path_list:
            raise PluginPrecheckError(
                f"服务依赖回环: {' → '.join([*path_list, uid_s])}",
                payload={"path": [*path_list, uid_s]},
            )
        if self._record_by_plugin_id(name) is not record:
            raise PluginNotFoundError(f"插件不在列表中: {name}", payload={"name": name})
        if record.info.is_core:
            raise PluginPrecheckError("核心插件不可卸载", payload={"name": name})
        if record.info.is_local:
            raise PluginPrecheckError("本地目录插件不可卸载", payload={"name": name})
        self._assert_allowed(record, "unload")

        was_enabled = record.info.state == PluginState.ENABLED
        downs = self._downstream(record)
        plugin = record._plugin
        # 钩子只打挂载单例；未挂载则跳过，禁止为钩子静默 new
        if plugin is not None:
            await plugin.pre_unload()

        record.info.lifecycle_context = ctx
        record.info.state = PluginState.UNLOADING
        await record.commit()
        deps: dict[str, Any] = {}
        try:
            # ── 下游 DFS ──
            path = [*path_list, uid_s]
            for dep_record in downs:
                dep_id = dep_record.info.plugin_name
                deps[dep_id] = await self.unload(
                    dep_record, held=True, dep_path=path, ctx=ctx
                )

            # ── 若仍启用则先禁用，再卸本项（临时回到 enabled 须 commit，供 disable 预检）──
            if was_enabled:
                record.info.state = PluginState.ENABLED
                await record.commit()
                # 本项禁用不属于下游 DFS，路径不能再次包含本项 uid。
                await self.disable(record, held=True, dep_path=path_list, ctx=ctx)
                record.info.state = PluginState.UNLOADING
                record.info.lifecycle_context = ctx
                await record.commit()

            if plugin is not None:
                await plugin.on_unload()
            # 发现失败或来源已移除时没有导入路径，仍须允许卸包，不能要求先成功加载。
            if record._project_dir is not None:
                loader.clear(record)
            # 卸出列表：清运行时 → unloaded → 删注册表行
            record._plugin = None
            record._plugin_cls = None
            record._config = None
            record._degraded_wants = []
            record._project_dir = None
            record.info.state = PluginState.UNLOADED
            record.info.lifecycle_context = LifecycleContext.IDLE
            record.info.enabled = False
            record.info.last_error = ""
            await record.commit()
            from app.core.config import Config

            if remove_record:
                Config.plugin_registry.remove(record.uid)
                await Config.plugin_registry.commit()
            return deps
        except Exception as exc:
            await self._fail_branch(
                record,
                fault=PluginState.FAULT_LOAD,
                during=PluginState.UNLOADING,
                exc=exc,
                plugin=plugin,
            )
            raise PluginOperationError(str(exc), payload={"name": name}) from exc

    async def reload(
        self,
        record: PluginRecord,
        *,
        held: bool = False,
        dep_path: list[str] | None = None,
    ) -> dict[str, Any]:
        """拆下依赖方 → 重载本项 → 按依赖字典恢复。"""
        if not held:
            async with self._pause_operations(record), self._hold():
                return await self.reload(record, held=True, dep_path=dep_path)

        path_list = list(dep_path or [])
        name = record.info.plugin_name
        uid_s = str(record.uid)
        if record._plugin_cls is None:
            raise PluginNotFoundError(f"插件不在列表中: {name}", payload={"name": name})
        if record.info.is_core:
            raise PluginPrecheckError(
                "核心插件不对用户暴露重载", payload={"name": name}
            )
        self._assert_allowed(record, "reload")

        # 钩子只打挂载单例；未挂载则跳过，禁止为钩子静默 new
        hung = record._plugin
        # 重载会换类：任一实例锁定则系统预检拒绝（设计 §7.2/§7.5）
        if hung is not None and isinstance(
            hung, (ScriptAdapterPlugin, GameAdapterPlugin)
        ):
            hung.precheck_locks()
        if hung is not None:
            await hung.pre_reload()

        was_enabled = record.info.state == PluginState.ENABLED
        downs = self._downstream(record)

        # 先写语境；拆下游时本项仍保持原稳态以便随后 disable
        record.info.lifecycle_context = LifecycleContext.RELOAD
        await record.commit()
        deps: dict[str, Any] = {}
        try:
            # ── 拆下游 ──
            path = [*path_list, uid_s]
            tear: dict[str, Any] = {}
            for dep_record in downs:
                if dep_record.info.state != PluginState.ENABLED:
                    continue
                dep_id = dep_record.info.plugin_name
                tear[dep_id] = await self.disable(
                    dep_record,
                    held=True,
                    dep_path=path,
                    ctx=LifecycleContext.RELOAD_CASCADE,
                )
            deps["tear"] = tear

            # ── 本项用户重载钩子（仅挂载实例）──
            record.info.state = PluginState.RELOADING
            await record.commit()
            if hung is not None:
                await hung.on_reload()

            if was_enabled:
                # 本项 disable/enable：dep_path 不含自身 uid；ctx=RELOAD 可进 RELOADING
                await self.disable(
                    record, held=True, dep_path=path_list, ctx=LifecycleContext.RELOAD
                )

            # ── 刷新类 / i18n；仅原启用态才重新 enable ──
            if not record.info.import_name:
                await discover.refresh()
            if not record.info.import_name:
                raise PluginPrecheckError(f"未发现插件: {name}", payload={"name": name})
            loader.clear(record)
            cls = loader.load(record)
            record._plugin_cls = cls
            if was_enabled:
                await self.enable(
                    record,
                    held=True,
                    dep_path=path_list,
                    ctx=LifecycleContext.RELOAD,
                )

            # ── 按 tear 字典恢复下游 ──
            restore: dict[str, Any] = {}
            for dep_id in tear:
                restored_record = self._record_by_plugin_id(dep_id)
                if restored_record is None or restored_record._plugin_cls is None:
                    continue
                assert restored_record is not None
                try:
                    restore[dep_id] = await self.enable(
                        restored_record,
                        held=True,
                        dep_path=path_list,
                        ctx=LifecycleContext.RELOAD_CASCADE,
                    )
                except Exception as exc:
                    logger.exception(f"重载后恢复下游失败: {dep_id}")
                    restored_record.info.state = PluginState.FAULT_RUNTIME
                    restored_record.info.enabled = False
                    restored_record.info.last_error = str(exc)
                    await restored_record.commit()
                    restore[dep_id] = {"error": str(exc)}
            deps["restore"] = restore

            if was_enabled:
                record.info.state = PluginState.ENABLED
                record.info.enabled = True
            else:
                record.info.state = PluginState.DISABLED
                record.info.enabled = False
                record._plugin = None
            record.info.lifecycle_context = LifecycleContext.IDLE
            record.info.last_error = ""
            record.info.code_drift = PluginCodeDrift.NORMAL
            await record.commit()
            return deps
        except Exception as exc:
            await self._fail_branch(
                record,
                fault=PluginState.FAULT_RUNTIME,
                during=PluginState.RELOADING,
                exc=exc,
                plugin=record._plugin,
            )
            raise PluginOperationError(str(exc), payload={"name": name}) from exc

    async def install(self, meta: PluginMeta) -> dict[str, Any]:
        """uv 装包 → load；成功返回 load 依赖字典。

        包名取自 ``meta.info.package_name``（空则预检失败）；
        插件 id 优先 ``meta.info.plugin_name``，否则按包名在扫描结果中定位。
        """
        async with self._hold():
            package = (meta.info.package_name or "").strip()
            if not package:
                raise PluginPrecheckError(
                    "市场条目缺少 package_name，无法安装",
                    payload={"plugin_name": meta.info.plugin_name},
                )
            await uv_tool.install(package)
            await discover.refresh()

            from app.core.config import Config

            # 定位：市场插件名 → 按包名匹配注册表
            plugin_id = (meta.info.plugin_name or "").strip()
            record = self._record_by_plugin_id(plugin_id) if plugin_id else None
            if record is None:
                pkg_key = package.replace("_", "-").lower()
                for r in Config.plugin_registry.values():
                    if (r.info.package_name or "").replace("_", "-").lower() == pkg_key:
                        record = r
                        break
            if record is None:
                raise PluginError(f"安装成功但未发现 auto-mas.plugins 入口: {package}")
            return await self.load(record, held=True)

    async def uninstall(self, record: PluginRecord) -> dict[str, Any]:
        """unload + uv 卸包。"""
        async with self._pause_owners(
            [record.uid, *(item.uid for item in self._downstream(record))]
        ):
            return await self._uninstall(record)

    async def _uninstall(self, record: PluginRecord) -> dict[str, Any]:
        """释放插件运行时后删除发行包及专属配置；外部删除失败时保留登记和故障状态供重试。"""
        async with self._hold():
            name = record.info.plugin_name
            package = record.info.package_name or name
            deps = await self.unload(record, held=True, remove_record=False)
            from app.core.config import Config

            try:
                await uv_tool.uninstall(package)
                (Config.config_path / "plugins" / f"{name}.yaml").unlink(
                    missing_ok=True
                )
            except Exception as exc:
                record.info.state = PluginState.FAULT_LOAD
                record.info.last_error = str(exc)
                await record.commit()
                raise
            Config.plugin_registry.remove(record.uid)
            await Config.plugin_registry.commit()
            return deps

    async def refresh_market(self) -> None:
        """全量刷新市场目录（写 ``Config.plugin_catalog``）。"""
        await plugin_market.refresh()

    def list_plugins(self) -> list[PluginRecord]:
        """返回已加载的 PluginRecord 列表（``_plugin_cls is not None``），按 plugin_name 排序。"""
        from app.core.config import Config

        return sorted(
            (s for s in Config.plugin_registry.values() if s._plugin_cls is not None),
            key=lambda s: s.info.plugin_name,
        )

    def script_decl(self, config):
        """从当前插件类型目录查找配置的专项声明，不向宿主暴露具体插件模块。"""
        return next(
            (
                decl
                for decl in self.script_types.values()
                if isinstance(config, decl.script_type)
            ),
            None,
        )

    def script_classes(self):
        """返回已登记专项的创建标识和配置类，供通用配置管理使用。"""
        return {
            record._plugin_cls.script_type_key: self.script_types[
                record.uid
            ].script_type
            for record in self.list_plugins()
            if record.uid in self.script_types
            and record.info.state == PluginState.ENABLED
            and record._plugin_cls is not None
            and issubclass(record._plugin_cls, ScriptAdapterPlugin)
        }

    async def check_prefetch(self, config):
        """只读取当前声明，公开调用门防止与插件卸载并发。"""
        for record in self.list_plugins():
            decl = self.script_types.get(record.uid)
            if (
                record.info.state == PluginState.ENABLED
                and decl is not None
                and isinstance(config, decl.script_type)
            ):
                if decl.prefetch_check is None:
                    return []
                return await self._calls[record.uid].wrap(decl.prefetch_check)(config)
        raise PluginPrecheckError("托管所属插件当前不可用")

    def resolve_script_expander(self, script, config):
        """托管锁内按实际启用声明分派；旧类型由调用方继续走旧工厂。"""
        from app.models.config import ScriptEntry

        if not isinstance(config, ScriptEntry):
            return None
        for record in self.list_plugins():
            decl = self.script_types.get(record.uid)
            if record.info.state != PluginState.ENABLED or decl is None:
                continue
            if isinstance(config, decl.script_type):
                if script.task_info.info.mode not in decl.supported_modes:
                    raise PluginPrecheckError("该插件不支持当前执行模式")
                return decl.expander_class(script, config)
        raise PluginPrecheckError("托管所属插件当前不可用")

    # ==================== 失败分支 ====================

    async def _fail_branch(
        self,
        record: PluginRecord,
        *,
        fault: PluginState,
        during: PluginState,
        exc: BaseException,
        plugin: BasePlugin | None,
        user_cleanup: bool = True,
    ) -> None:
        """系统清 →（可选）用户清 → 落 fault_* 稳态；不吞原异常。"""
        name = record.info.plugin_name
        # 系统回退
        try:
            self.services.unregister_owner(name)
            self.http.unmount(name)
            await self._release_config(record)
        except Exception:
            logger.exception(f"失败分支系统回退异常: {name}")
        # 失败钩子：叶子 during + record 上 lifecycle_context 快照
        life_ctx = LifecycleContext(record.info.lifecycle_context)
        inst = plugin or record._plugin
        if inst is not None:
            await self._close_instance_work(inst)
        if user_cleanup and inst is not None:
            if isinstance(inst, (ScriptAdapterPlugin, GameAdapterPlugin)):
                try:
                    await inst.system_rollback(during, life_ctx, exc)
                except Exception:
                    logger.exception(f"失败分支 system_rollback 异常: {name}")
            try:
                await inst.on_fail_cleanup(during, life_ctx, exc)
            except Exception:
                logger.exception(f"失败分支 on_fail_cleanup 异常: {name}")

        record._plugin = None
        try:
            loader.clear(record)
        except Exception:
            logger.exception(f"失败分支模块清理异常: {name}")
        # 仍在列表则落故障稳态（load/unload 失败保留 _plugin_cls）
        if record._plugin_cls is not None:
            record.info.state = fault
        record.info.lifecycle_context = LifecycleContext.IDLE
        record.info.last_error = str(exc)
        try:
            await record.commit()
        except Exception:
            logger.exception(f"失败分支落盘异常: {name}")
        await Publisher.send(id=ID_PLUGIN, type=PLUGIN_CAPABILITIES_UPDATED, data={})

    # ==================== 配置宿主（挂 PluginRecord._config）====================

    async def _release_config(self, record: PluginRecord) -> None:
        """禁用/失败：commit → 该根落盘 → unregister_root → 清 ``_config``。

        进程退出不走此路径（由主程序 ``config_manager.flush()`` 统一落盘）。
        """
        from app.config import NodeState, config_manager
        from app.utils.common.io import write_file

        instance = record._config
        if instance is None:
            return
        if instance.activation_state != NodeState.ACTIVE:
            config_manager.unregister_root(instance)
            record._config = None
            return
        await instance.commit()
        # 须在 unregister 前写盘，否则防抖/flush 可能已扫不到该根
        path = config_manager.get_file(instance)
        if path is not None:
            write_file(path, await instance.to_dict())
        config_manager.unregister_root(instance)
        record._config = None

    # ==================== record / 状态回写 ====================

    def _record_by_plugin_id(self, plugin_id: str) -> PluginRecord | None:
        """按插件 id（plugin_name）查 record；供 requires 边解析。"""
        from app.core.config import Config

        return Config.plugin_registry.by_name(plugin_id)

    # ==================== 级联（requires 服务名 → 提供者 PluginRecord）====================

    @staticmethod
    def _is_enabled(record: PluginRecord, *, ctx: LifecycleContext) -> bool:
        """级联恢复复用已完成启用的提供者，根重载语义保留到恢复结束。"""
        return record.info.state == PluginState.ENABLED or (
            ctx == LifecycleContext.RELOAD_CASCADE
            and record.info.state == PluginState.RELOADING
            and record.info.enabled
        )

    def _provider(self, service: str) -> PluginRecord | None:
        """已加载插件中 ``provides_services`` 声明该服务的提供者。"""
        for record in self.list_plugins():
            cls = record._plugin_cls
            if cls is None:
                continue
            if service in (getattr(cls, "provides_services", None) or {}):
                return record
        return None

    def _upstream(self, record: PluginRecord) -> list[PluginRecord]:
        """本项 ``requires``（服务名）对应的上游提供者（去重，顺序随 requires）。"""
        name = record.info.plugin_name
        out: list[PluginRecord] = []
        seen: set[str] = set()
        for svc in list(record.info.requires):
            dep = self._provider(svc)
            if dep is None:
                raise PluginPrecheckError(
                    f"插件 `{name}` 所需服务无提供者: {svc}",
                    payload={"name": name, "service": svc},
                )
            if dep.uid == record.uid:
                continue
            key = str(dep.uid)
            if key in seen:
                continue
            seen.add(key)
            out.append(dep)
        return out

    def disable_impact(self, record: PluginRecord) -> list[Literal["scripts", "games"]]:
        """汇总停用本插件及级联下游时会删除的配置领域，供前端确认。"""
        impact: set[Literal["scripts", "games"]] = set()
        visited: set[UUID] = set()
        pending = [record]
        while pending:
            current = pending.pop()
            if current.uid in visited or current.info.state != PluginState.ENABLED:
                continue
            visited.add(current.uid)
            cls = current._plugin_cls
            if cls is not None:
                if issubclass(cls, ScriptAdapterPlugin):
                    impact.add("scripts")
                if issubclass(cls, GameAdapterPlugin):
                    impact.add("games")
            pending.extend(self._downstream(current))
        return sorted(impact)

    def _downstream(self, record: PluginRecord) -> list[PluginRecord]:
        """已加载且 ``requires`` 了本项所提供服务的下游（按 plugin_name 排序）。"""
        cls = record._plugin_cls
        provided = (
            set((getattr(cls, "provides_services", None) or {}).keys())
            if cls
            else set()
        )
        if not provided:
            return []
        out: list[PluginRecord] = []
        for other in self.list_plugins():
            if other.uid == record.uid:
                continue
            if any(s in provided for s in other.info.requires):
                out.append(other)
        return sorted(out, key=lambda r: r.info.plugin_name)

    # ==================== 小工具 ====================

    def _assert_allowed(self, record: PluginRecord, op: str) -> None:
        """按插件故障状态限制可执行的生命周期操作，拒绝不适用于当前状态的请求。"""
        state = record.info.state
        allowed: tuple[str, ...]
        if state == PluginState.FAULT_LOAD:
            allowed = ("load", "unload")
        elif state == PluginState.FAULT_RUNTIME:
            allowed = ("load", "unload", "enable", "reload")
        else:
            return
        if op not in allowed:
            raise PluginStateError(
                f"插件 `{record.info.plugin_name}` 处于 `{state}`，不允许 `{op}`",
                payload={
                    "name": record.info.plugin_name,
                    "state": state,
                    "allowed": sorted(allowed),
                },
            )

    @property
    def signals(self) -> Namespace:
        """返回插件框架共享的信号命名空间，供宿主订阅生命周期事件。"""
        return plugin_signals

    # ==================== 源码监视订阅 ====================

    def _on_sources_changed(
        self, sender: object, payload: SourcesChangedPayload
    ) -> None:
        """监视信号（blinker 同步）：调度增量 refresh；忙时跳过，下轮事件再触发。"""
        queue = self._source_queue
        if not self._initialized or queue is None:
            return
        queue.put_nowait(payload)

    async def _source_worker(self) -> None:
        """把监视载荷转成增量 refresh；不自动 reload。"""
        queue = self._source_queue
        if queue is None:
            return
        while True:
            payload = await queue.get()
            pending: dict[str, bool] = {}
            for change in payload.changes:
                pending[change.local_dir] = (
                    pending.get(change.local_dir, False) or change.code_touched
                )
            while not queue.empty():
                next_payload = queue.get_nowait()
                for change in next_payload.changes:
                    pending[change.local_dir] = (
                        pending.get(change.local_dir, False) or change.code_touched
                    )
            if not self._initialized:
                continue
            changes = tuple(
                SourceChange(
                    local_dir=local_dir,
                    code_touched=code_touched,
                )
                for local_dir, code_touched in sorted(pending.items())
            )
            try:
                # 锁顺序硬约束：Manager._busy → discover.refresh_lock。
                async with self._busy:
                    await discover.refresh(scope=discover.RefreshScope(changes=changes))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("源码变更 refresh 失败")

    @property
    def initialized(self) -> bool:
        """返回插件管理器是否已经完成宿主初始化。"""
        return self._initialized
