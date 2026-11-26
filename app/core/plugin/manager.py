"""主程序插件系统入口：全局 Manager 单例。

五操作范式：锁 → 预检 → 标记 ×× 中 → 上下游 DFS → 本项（先用户后系统）
→（重载按本次拆卸树逐层恢复）→ 返回依赖字典；失败上抛，``finally`` 走失败分支。
其它模块只依赖 ``from app.core import Plugin``。

名单权威 = ``Config.plugin_registry``（由 ``discover.refresh`` 按本地发现增改删）；
已加载 = ``_plugin_cls is not None``；状态只写 ``record.info.state``。
公开方法只收配置实例（``PluginRecord`` / ``PluginMeta``），不传插件 id / 包名。
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.metadata as importlib_metadata
import inspect
import re
import sys
import weakref
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID, uuid4

import httpx
from blinker import Namespace
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from app.config import NodeState, config_manager
from app.core.ws import Publisher
from app.core.ws.protocol import ID_PLUGIN, PLUGIN_CAPABILITIES_UPDATED
from app.mystery.gate import is_unlocked
from app.plugin import uv as uv_tool
from app.plugin.base.game import GameAdapterPlugin, GameTypeDecl
from app.plugin.base.plugin import BasePlugin
from app.plugin.base.script import ScriptAdapterPlugin, ScriptTypeDecl
from app.plugin.calls import CallGate, call_context
from app.plugin.errors import (
    PluginBusyError,
    PluginError,
    PluginNotFoundError,
    PluginOperationError,
    PluginPrecheckError,
    PluginStateError,
)
from app.plugin.http import HttpRegistry, collect_route_decls
from app.plugin.runtime import discover, loader, market_index
from app.plugin.runtime import market as plugin_market
from app.plugin.runtime.metadata import validate_install_metadata
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
    PLUGIN_ID_PATTERN,
    PLUGIN_ID_TAG_PREFIX,
    RESTRICTED_PLUGIN_NAMES,
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
    from app.config import ConfigEntry, ConfigNode
    from app.models.config import PluginMeta, PluginRecord
    from app.models.config.game import GameEntry

logger = get_logger("插件管理")

# 停用、重载、卸载时等待在途调用收尾的上限（秒）。到时仍有调用没结束就拒绝本次操作、恢复准入，
# 不让一次生命周期操作无限期挡住正在运行的托管。
_PAUSE_DRAIN_TIMEOUT = 15.0
_BUSY_MESSAGE = "插件系统忙，请稍后重试"


def _requirement_closure(package: str) -> set[str]:
    """已装发行包按 Requires-Dist 展开的依赖闭包（规范化包名，含自身）；读不到的包跳过。"""
    from packaging.requirements import InvalidRequirement, Requirement

    seen: set[str] = set()
    pending = [canonicalize_name(package)]
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        try:
            requires = importlib_metadata.distribution(name).requires or []
        except importlib_metadata.PackageNotFoundError:
            continue
        for text in requires:
            try:
                requirement = Requirement(text)
            except InvalidRequirement:
                continue
            if requirement.marker is not None and not requirement.marker.evaluate(
                {"extra": ""}
            ):
                continue
            pending.append(canonicalize_name(requirement.name))
    return seen


def _mount_local_libraries() -> None:
    """本地源码库的 src 放到导入路径最前，优先于共享环境里的同名发行包；改库要重启后端。"""
    for library in discover.local_libraries():
        path = str(library / "src")
        if path not in sys.path:
            sys.path.insert(0, path)
            logger.info(f"本地库已加入导入路径: {library.name}")


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
        self._restart_installation: UUID | None = None
        self._core_pep440: str | None = None
        self._watcher: SourceWatcher | None = None
        self._source_queue: asyncio.Queue[SourcesChangedPayload] | None = None
        self._source_worker_task: asyncio.Task[None] | None = None
        self._calls: dict[UUID, CallGate] = {}
        # 退出开始后不再受理新的生命周期操作；插件之间的服务调用要留到停完任务之后才封。
        self._entries_sealed = False
        # 本次启动因版本低于存量配置要求而不启用的插件（插件 ID）。
        self._held_back: frozenset[str] = frozenset()

    def trigger_owner(self, entry: ConfigEntry) -> UUID | None:
        """从插件记录、专属配置及游戏或脚本声明中确定配置节点所属插件，未归属插件时返回 None。"""
        from app.models.config import PluginRecord

        if isinstance(entry, PluginRecord):
            return entry.uid
        for record in self.list_plugins():
            if record._config is entry.root:
                return record.uid
        node: ConfigNode | None = entry
        while node is not None:
            for uid, decl in self.game_types.items():
                if isinstance(node, (decl.game_class, decl.device_class)):
                    return uid
            for uid, decl in self.script_types.items():
                # 账号可复用同一类型，由其所属托管确定插件。
                if type(node) is decl.script_type or type(node) is decl.plan_type:
                    return uid
            node = node.parent
        return None

    @asynccontextmanager
    async def _pause_owners(self, owners):
        """暂停指定插件的调用准入，等待在途调用和配置操作收尾，退出时按当前启用状态恢复准入。

        等配置触发器和等在途调用共用一个截止时间，任一段到点都放弃本次操作。
        """
        owners = tuple(owners)
        gates = {
            uid: (self._calls[uid], self._calls[uid].accepting)
            for uid in owners
            if uid in self._calls
        }
        for gate, _ in gates.values():
            gate.accepting = False
        deadline = asyncio.get_running_loop().time() + _PAUSE_DRAIN_TIMEOUT
        try:
            async with contextlib.AsyncExitStack() as stack:
                # 保留发起调用的任务身份，让 drain 排除自身，避免等待自己返回。
                # 在当前任务里限时等待（不另起任务），否则 drain 认不出发起者自己的调用。
                pending: UUID | None = None
                try:
                    async with asyncio.timeout_at(deadline):
                        # 进入时等这些插件的配置触发器退出；超时取消在这里，
                        # 暂停计数由它自己的 finally 撤回。
                        await stack.enter_async_context(
                            config_manager.pause_trigger_owners(owners)
                        )
                        for uid, (gate, _) in gates.items():
                            pending = uid
                            await gate.drain()
                except TimeoutError:
                    from app.core import Config

                    if pending is None:
                        names = "、".join(
                            str(
                                record.info.plugin_name
                                if (record := Config.plugin_registry.get(uid))
                                is not None
                                else uid
                            )
                            for uid in owners
                        )
                        logger.warning(
                            f"插件 {names} 的配置触发器 {_PAUSE_DRAIN_TIMEOUT:g} 秒内"
                            "没有结束，拒绝本次停用 / 重载 / 卸载，恢复调用准入"
                        )
                    else:
                        record = Config.plugin_registry.get(pending)
                        name = (
                            record.info.plugin_name if record is not None else pending
                        )
                        logger.warning(
                            f"插件 {name} 的在途调用 {_PAUSE_DRAIN_TIMEOUT:g} 秒内没有结束，"
                            "拒绝本次停用 / 重载 / 卸载，恢复调用准入"
                        )
                    raise PluginBusyError(_BUSY_MESSAGE) from None
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
            site = uv_tool.site_dir(activate=False)
            from app.plugin.uv.environment import apply_pending, read_installation

            installation = read_installation()
            if installation is not None and installation.progress.state in {
                "applying",
                "failed",
            }:
                # 未完成发布可能留下部分元数据，先恢复文件再执行发现。
                await apply_pending()
            # 只发现元数据；旧插件及其依赖在联合升级完成前不能进入导入环境。
            await discover.refresh(installed_path=site)
            minimums = self._startup_minimums()
            libraries = self._host_libraries()
            requirements: dict[str, Any] = {}
            if minimums:
                # 存量配置要的专项低于下限时，在任何插件模块导入前连同同族一起升上来。
                requirements["minimums"] = minimums
            if libraries:
                # 宿主内置托管要的库（例如 MaaEnd 用的 MFW 解析库）一起装进插件环境。
                requirements["libraries"] = libraries
            await uv_tool.prepare_environment(**requirements)
            uv_tool.site_dir()
            from app.core.config import Config

            src = Config.source_path / "plugins" / "auto_mas_core" / "src"
            # SDK 源码属于进程初始化环境，供本地与已安装插件共享同一类型协议。
            core_src = str(src.resolve())
            if core_src not in sys.path:
                sys.path.insert(0, core_src)
            _mount_local_libraries()

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

            self._held_back = self._below_minimum_family(minimums)
            for record in list(Config.plugin_registry.values()):
                name = record.info.plugin_name
                if (
                    not record.info.enabled
                    or not name
                    or name == CORE_PLUGIN_NAME
                    or record._plugin_cls is None
                ):
                    continue
                if name in self._held_back:
                    logger.warning(
                        f"插件 {name} 本次启动不启用：它或只用它的专项低于存量配置"
                        "要求的版本，等升级完成后再接手"
                    )
                    continue
                try:
                    await self.enable(record, held=True)
                except Exception:
                    logger.exception(f"启动时启用插件失败: {name}")
                    continue

            from app.plugin.uv.environment import finish_installation

            finish_installation(held_back=self._held_back)
            self._initialized = True

            # ── 源码监视：plugins/*/ 代码变更 → sources_changed → 增量 refresh ──
            sources_changed.connect(self._on_sources_changed)
            self._source_queue = asyncio.Queue()
            self._source_worker_task = asyncio.create_task(self._source_worker())
            self._watcher = SourceWatcher(plugins_dir=Config.plugins_path)
            self._watcher.start()

    def seal_entries(self) -> None:
        """退出开始只封外部入口：插件 HTTP 网关和新的生命周期操作。

        服务注册表和调用门留到停完任务之后由 ``shutdown`` 封：任务收尾（停 worker、关游戏、
        恢复分辨率、放预约）要经插件之间的服务调用完成。
        """
        self._entries_sealed = True
        self.http.seal()

    def seal(self) -> None:
        """封住全部公开调用：HTTP、服务取用和各插件调用门；已有调用由 shutdown 等待实际结束。"""
        self.seal_entries()
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

        主程序应先 ``seal_entries``、停 WS / 任务，再调本方法（见 ``main`` teardown）：
        任务收尾要用的插件服务到这里才封。
        """
        if not self._initialized:
            # 初始化没走完（后台初始化被取消）也可能已经登记了部分服务，同样封住。
            self.seal()
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
        """先取得生命周期互斥资格，再暂停调用；忙时或退出已开始时拒绝，不能提前取消业务操作。"""
        if (
            self._busy.locked()
            or self._restart_installation is not None
            or self._entries_sealed
        ):
            raise PluginBusyError(_BUSY_MESSAGE)
        async with self._busy:
            # 线程回调进入生命周期时绑定本协程，独立子任务不继承它的自禁用资格。
            with call_context():
                yield

    # ==================== 对外生命周期 ====================

    async def prepare_installation_restart(self, installation_id: UUID) -> bool:
        """确认候选身份，等待业务空闲后封闭新任务和命令，交由前端立即重启。"""
        from app.core import TaskManager
        from app.plugin.uv.environment import read_installation

        record = read_installation()
        if (
            record is None
            or record.progress.installationId != installation_id
            or record.progress.state != "waiting_restart"
        ):
            raise PluginPrecheckError("等待重启的插件安装已变化，请重新查询")
        if self._restart_installation == installation_id:
            return True
        async with self._hold():
            if not TaskManager.prepare_restart():
                return False
            if not config_manager.prepare_trigger_restart():
                TaskManager.cancel_restart()
                return False
            self._restart_installation = installation_id
            return True

    def cancel_installation_restart(self, installation_id: UUID) -> None:
        """前端重启失败或放弃时恢复受理；候选环境继续保留，供下次启动应用。"""
        from app.core import TaskManager

        if self._restart_installation != installation_id:
            return
        self._restart_installation = None
        TaskManager.cancel_restart()
        config_manager.cancel_trigger_restart()

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
        # 受控插件：未通过神秘入口校验时不可启用。已安装并启用的存量不受影响——
        # 它的启用请求走上面的早退，重载时拆下游再恢复的那一段由内部语境放行，
        # 因此跨日失效或手动锁定都不会让在用的插件掉线。
        if (
            name in RESTRICTED_PLUGIN_NAMES
            and ctx != LifecycleContext.RELOAD_CASCADE
            and not record.info.enabled
            and not is_unlocked()
        ):
            raise PluginPrecheckError(
                "该插件需要先在神秘入口解锁后才能启用",
                payload={"name": name},
            )
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
            # 上次禁用可能写盘失败；先保存并释放旧根，成功后才从文件重建。
            await self._release_config(record)
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
            # 「重载本项」语境只属于本项：新版本新依赖了一个停着的上游时，上游是一次普通启用，
            # 否则它会停在「已停用」却挂着实例（RELOAD 语境下状态留给父操作收尾）。
            up_ctx = LifecycleContext.NORMAL if ctx == LifecycleContext.RELOAD else ctx
            for dep_record in ups:
                dep_id = dep_record.info.plugin_name
                deps[dep_id] = await self.enable(
                    dep_record, held=True, dep_path=path, ctx=up_ctx
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

    def _activity_owners(self, record: PluginRecord) -> set[UUID]:
        """当前插件及其全部传递下游依赖者，即生命周期操作要暂停的范围。"""
        owners: set[UUID] = set()
        pending = [record]
        while pending:
            current = pending.pop()
            if current.uid in owners:
                continue
            owners.add(current.uid)
            pending.extend(self._downstream(current))
        return owners

    @asynccontextmanager
    async def _pause_activity(self, record: PluginRecord):
        """收集当前插件及其下游依赖者，在上下文内统一暂停调用与配置操作。"""
        owners = self._activity_owners(record)
        async with self._pause_owners(owners):
            yield owners

    async def disable(
        self,
        record: PluginRecord,
        *,
        held: bool = False,
        dep_path: list[str] | None = None,
        ctx: LifecycleContext = LifecycleContext.NORMAL,
    ) -> dict[str, Any]:
        """递归禁用仍启用的下游，返回本次实际拆卸的完整级联树。"""
        if not held:
            async with self._hold():

                async def precheck() -> None:
                    """级联停用前对整棵要拆的树一起预检：下游的拒绝不能等到兄弟分支已经拆完、
                    托管已经删掉之后才冒出来，再落进上游的失败分支。"""
                    if (
                        record.info.state == PluginState.ENABLED
                        and record._plugin_cls is not None
                    ):
                        tree = self._teardown_tree(record, enabled_only=True)
                        self._precheck_cascade_data(tree)
                        await self._precheck_teardown(tree)

                # 先在不关调用门时问一次：有运行在途就直接拒，在跑的托管不受打扰；
                # 暂停之后再问一次，关上两次检查之间的窗口。
                await precheck()
                async with self._pause_activity(record):
                    await precheck()
                    return await self.disable(
                        record, held=True, dep_path=dep_path, ctx=ctx
                    )

        path_list = list(dep_path or [])
        name = record.info.plugin_name
        uid_s = str(record.uid)
        if uid_s in path_list:
            raise PluginPrecheckError(
                f"服务依赖回环: {' → '.join([*path_list, uid_s])}",
                payload={"path": [*path_list, uid_s]},
            )
        if record.info.is_core:
            raise PluginPrecheckError("核心插件不可禁用", payload={"name": name})
        self._assert_allowed(record, "disable")
        # 故障、禁停与已卸载记录没有可拆的实例：显式停用只取消下次启动的启用意图，
        # 不再跑一遍插件收尾。否则用户想让出错的插件安静待着也做不到，重启还会被拉起。
        if record.info.state in {
            PluginState.DISABLED,
            PluginState.FAULT_LOAD,
            PluginState.FAULT_RUNTIME,
            PluginState.UNLOADED,
        }:
            if record.info.enabled:
                record.info.enabled = False
                await record.commit()
                capabilities_changed.send(self, name=name, enabled=False)
                await Publisher.send(
                    id=ID_PLUGIN, type=PLUGIN_CAPABILITIES_UPDATED, data={}
                )
            return {}
        if record._plugin_cls is None:
            raise PluginNotFoundError(f"插件不在列表中: {name}", payload={"name": name})
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
            # ── 下游 DFS：只记录本次实际禁用的节点，供重载原样恢复 ──
            path = [*path_list, uid_s]
            for dep_record in downs:
                if dep_record.info.state != PluginState.ENABLED:
                    continue
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
            # 只有用户真的点停用才写掉「下次还要开」。重载只是暂时停一下：它拆到一半失败时，
            # 已经停稳的下层不在父层那份名单里，事后没处补，写掉就再也起不来。
            if ctx == LifecycleContext.NORMAL:
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
            async with self._hold():
                # 先在不关调用门时预检，暂停之后再预检一次（同停用）。
                tree = self._teardown_tree(record, enabled_only=False)
                self._precheck_cascade_data(tree)
                await self._precheck_teardown(tree)
                async with self._pause_activity(record):
                    tree = self._teardown_tree(record, enabled_only=False)
                    self._precheck_cascade_data(tree)
                    await self._precheck_teardown(tree)
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
            # 禁用写盘失败可能留下配置根，必须解除所有权后才可卸包并删除配置文件。
            await self._release_config(record)
            # 发现失败或来源已移除时没有导入路径，仍须允许卸包，不能要求先成功加载。
            if record._project_dir is not None:
                loader.clear(record)
            # 卸出列表：清运行时 → unloaded → 删注册表行
            record._plugin = None
            record._plugin_cls = None
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
        """拆下启用中的下游并保存完整树，重载本项后按树先父后子恢复。"""
        if not held:
            async with self._hold():
                from app.core import Config

                # 重载会替换整棵实际拆卸树的实例，先检查所有适配器，避免拆到一半才遇到锁。
                # 先在不关调用门时预检，暂停之后再预检一次（同停用）。
                await self._precheck_teardown(
                    [
                        Config.plugin_registry[uid]
                        for uid in self._activity_owners(record)
                    ]
                )
                async with self._pause_activity(record) as owners:
                    await self._precheck_teardown(
                        [Config.plugin_registry[uid] for uid in owners]
                    )
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
        if hung is not None:
            await hung.pre_reload()

        # 「在跑」决定要不要拆实例，「想开」决定重载后要不要重新拉起。故障记录上两者不同：
        # 用户原本开着、只是眼下没运行，重载不该把这份启用意图抹成「从没启用过」。
        was_running = record.info.state == PluginState.ENABLED
        want_enabled = was_running or record.info.enabled
        downs = self._downstream(record)

        # 先写语境；拆下游时本项仍保持原稳态以便随后 disable
        record.info.lifecycle_context = LifecycleContext.RELOAD
        await record.commit()
        deps: dict[str, Any] = {}
        tear: dict[str, Any] = {}

        try:
            # ── 拆下游 ──
            path = [*path_list, uid_s]
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

            if was_running:
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
            # 新类的 requires / wants 写在暂存区；先提交，启用时的上游求解才看得到新版本的依赖。
            await record.commit()
            if want_enabled:
                await self.enable(
                    record,
                    held=True,
                    dep_path=path_list,
                    ctx=LifecycleContext.RELOAD,
                )

            # ── 沿实际拆卸树恢复；enable 自身的上游求解不能代替下游树遍历 ──
            async def restore_cascade(tree: dict[str, Any]) -> dict[str, Any]:
                """先恢复树中节点再恢复其子树；单点失败保留故障并继续其他分支。"""
                restored: dict[str, Any] = {}
                for dep_id, children in tree.items():
                    restored_record = self._record_by_plugin_id(dep_id)
                    if restored_record is None or restored_record._plugin_cls is None:
                        continue
                    try:
                        await self.enable(
                            restored_record,
                            held=True,
                            dep_path=path_list,
                            ctx=LifecycleContext.RELOAD_CASCADE,
                        )
                    except Exception as exc:
                        logger.exception(f"重载后恢复下游失败: {dep_id}")
                        restored_record.info.state = PluginState.FAULT_RUNTIME
                        restored_record.info.last_error = str(exc)
                        await restored_record.commit()
                        # 子节点仍缺少此提供者，不能借恢复子树再次启用失败分支。
                        continue
                    restored[dep_id] = await restore_cascade(children)
                return restored

            deps["restore"] = await restore_cascade(tear)

            if want_enabled:
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

    async def install(
        self, meta: PluginMeta, *, minimum_version: Version | None = None
    ) -> dict[str, Any]:
        """确认只读目录的安装目标及发行元数据，联合装包后核对实际身份，再发现并加载插件。"""
        async with self._hold():
            from app.core.config import Config
            from app.plugin.uv.environment import finish_installation, read_installation

            pending = read_installation()
            if pending is not None and pending.progress.state == "waiting_restart":
                if (
                    pending.progress.metaId == meta.uid
                    and canonicalize_name(pending.progress.packageName)
                    == canonicalize_name(meta.info.package_name)
                    and pending.progress.pluginName == meta.info.plugin_name
                    and (
                        minimum_version is None
                        or Version(pending.progress.version) >= minimum_version
                    )
                    and (
                        not meta.info.version
                        or Version(pending.progress.version)
                        == Version(meta.info.version)
                    )
                ):
                    return {"restart_required": True}
                # 主程序升级补装同族插件：前一个补装已把它一起升到满足下限的版本，
                # 重启后生效；不能当成另一轮安装拒掉，否则它的托管会被旁挂。
                upgraded = pending.co_upgraded.get(
                    canonicalize_name(meta.info.package_name or "")
                )
                if (
                    upgraded is not None
                    and minimum_version is not None
                    and not meta.info.version
                    and Version(upgraded) >= minimum_version
                ):
                    return {"restart_required": True}
                raise PluginPrecheckError("已有插件安装等待重启，请先完成该操作")

            package = (meta.info.package_name or "").strip()
            plugin_id = (meta.info.plugin_name or "").strip()
            version = meta.info.version.strip()
            # 包名仅接受发行身份，不能夹带 URL、路径或任意依赖表达式。
            if (
                not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", package)
                or canonicalize_name(package)
                == canonicalize_name(CORE_DISTRIBUTION_NAME)
                or plugin_id.casefold() == CORE_PLUGIN_NAME.casefold()
                or not PLUGIN_ID_PATTERN.fullmatch(plugin_id)
            ):
                raise PluginPrecheckError("无效的插件安装目标")
            await discover.refresh()
            existing = self._record_by_plugin_id(plugin_id)
            if existing is not None and existing._project_dir is not None:
                if existing.info.source == "local":
                    raise PluginPrecheckError(
                        f"插件 `{plugin_id}` 正在使用本地源码，请先移除该工程后再安装发行包"
                    )
                if canonicalize_name(existing.info.package_name) != canonicalize_name(
                    package
                ):
                    raise PluginPrecheckError(
                        f"插件身份 `{plugin_id}` 已由其他发行包占用"
                    )
            if version:
                version = str(Version(version))
                # 市场安装固定条目版本；镜像未同步时只换源，不放宽版本或插件身份。
                last_error: Exception | None = None
                async with httpx.AsyncClient(
                    timeout=15, follow_redirects=True, proxy=Config.proxy
                ) as client:
                    for source in uv_tool.candidates():
                        try:
                            metadata = await market_index.fetch_metadata(
                                client,
                                source,
                                package,
                                proxy=Config.proxy,
                                version=version,
                            )
                        except (httpx.HTTPError, OSError, ValueError) as error:
                            last_error = error
                            continue
                        if metadata is not None:
                            validate_install_metadata(
                                metadata,
                                package_name=package,
                                plugin_name=plugin_id,
                                version=version,
                            )
                            break
                    else:
                        # 源码包也可安装；Simple 没有 wheel 时从官方精确版本 JSON 核验声明。
                        try:
                            response = await client.get(
                                f"https://pypi.org/pypi/{package}/{version}/json"
                            )
                            response.raise_for_status()
                            payload = response.json()
                            if not isinstance(payload, dict):
                                raise ValueError("发行元数据必须是对象")
                        except (httpx.HTTPError, ValueError) as error:
                            raise PluginPrecheckError(
                                f"无法取得插件目标版本的发行元数据：{package}=={version}"
                            ) from (last_error or error)
                        validate_install_metadata(
                            payload,
                            package_name=package,
                            plugin_name=plugin_id,
                            version=version,
                        )
            elif meta.activation_state != NodeState.INACTIVE:
                raise PluginPrecheckError("市场条目缺少版本，请刷新目录后重试")
            # 主程序升级可从内部声明自动求解版本；同样须通过装包后的实际元数据校验。
            requirement = package
            options: dict[str, Any] = {}
            if version:
                requirement += f"=={version}"
            elif minimum_version is not None:
                requirement += f">={minimum_version}"
                # 装不成时按下限说原因（要的下限、现装版本、索引里拿不拿得到）。
                options["minimum"] = minimum_version
            pause = (
                self._pause_activity(existing)
                if existing is not None and existing._plugin_cls is not None
                else contextlib.nullcontext(set())
            )
            if existing is not None and existing._plugin_cls is not None:
                # 升级已加载的插件同样先在不关调用门时预检，暂停之后再预检一次（同停用）。
                await self._precheck_teardown(
                    [
                        Config.plugin_registry[uid]
                        for uid in self._activity_owners(existing)
                    ]
                )
            async with pause as owners:
                await self._precheck_teardown(
                    [Config.plugin_registry[uid] for uid in owners]
                )
                # 装包可能按 Requires-Dist 连带装上别的插件，记下装包前已登记的名字。
                before = {r.info.plugin_name for r in Config.plugin_registry.values()}
                if libraries := self._host_libraries():
                    # 重建环境时留住宿主内置托管要的库（例如 MaaEnd 用的 MFW 解析库）。
                    options["libraries"] = libraries
                restart_required = await uv_tool.install(
                    requirement,
                    plugin_name=plugin_id,
                    meta_id=meta.uid,
                    **options,
                )
                if restart_required:
                    return {"restart_required": True}
                distribution = importlib_metadata.distribution(package)
                installed_version = validate_install_metadata(
                    distribution.metadata,
                    package_name=package,
                    plugin_name=plugin_id,
                    version=version,
                )
                await discover.refresh()
                record = self._record_by_plugin_id(plugin_id)
                if (
                    record is None
                    or record.info.source != "installed"
                    or canonicalize_name(record.info.package_name)
                    != canonicalize_name(package)
                    or Version(record.info.version) != Version(installed_version)
                    or record._project_dir is None
                    or record._project_dir.resolve()
                    != Path(str(distribution.locate_file(""))).resolve()
                ):
                    raise PluginPrecheckError("发现的插件与已验证的安装发行包不一致")
                try:
                    # 先加载本次新出现的依赖插件（只加载不启用），目标启用时才找得到上游提供者；
                    # 否则装完直接启用会报「所需服务无提供者」，要重启后端才行。
                    created = [
                        r
                        for r in Config.plugin_registry.values()
                        if r.info.plugin_name not in before
                        and r.uid != record.uid
                        and r._project_dir is not None
                        and r._plugin_cls is None
                    ]
                    for dep in sorted(created, key=lambda r: r.info.plugin_name):
                        await self.load(dep, held=True)
                    # 早已登记、这次随装包换了一份的依赖插件（来源丢失后重装、从本地源码换成
                    # 发行包）也停在未加载：只要它是本插件发行包依赖链上的包，同启动时一样
                    # 加载；单个失败只记日志，目标启用时缺哪个上游会按「所需服务无提供者」报出来。
                    required = _requirement_closure(package)
                    for other in sorted(
                        Config.plugin_registry.values(),
                        key=lambda r: r.info.plugin_name or "",
                    ):
                        if (
                            other.uid == record.uid
                            or other._plugin_cls is not None
                            or other.info.source != "installed"
                            or other._project_dir is None
                            or canonicalize_name(other.info.package_name or "")
                            not in required
                        ):
                            continue
                        try:
                            await self.load(other, held=True)
                        except Exception:
                            logger.exception(
                                f"加载随安装带入的插件失败: {other.info.plugin_name}"
                            )
                    if record._plugin_cls is not None:
                        result = await self.reload(record, held=True)
                    else:
                        result = await self.load(record, held=True)
                        # 登记里留着启用意图（重装、换来源）：同启动时一样按意图启用，
                        # 否则安装确认会把「意图启用、实际停用」判成失败，下次启动回滚。
                        if record.info.enabled:
                            await self.enable(record, held=True)
                except BaseException:
                    from app.plugin.uv.environment import write_installation

                    installation = read_installation()
                    assert installation is not None
                    installation.progress.state = "failed"
                    installation.progress.message = "插件加载失败，请检查插件兼容性"
                    write_installation(installation)
                    raise
                finish_installation(held_back=self._held_back)
                return result

    async def uninstall(self, record: PluginRecord) -> dict[str, Any]:
        """取得互斥并等待完整下游后卸包；外部删除失败时保留登记和故障状态供重试。"""
        from app.plugin.uv.environment import ensure_writable

        ensure_writable()
        async with self._hold():
            # 先在不关调用门时预检，暂停之后再预检一次（同停用）。
            tree = self._teardown_tree(record, enabled_only=False)
            self._precheck_cascade_data(tree)
            await self._precheck_teardown(tree)
            async with self._pause_activity(record):
                name = record.info.plugin_name
                package = record.info.package_name or name
                tree = self._teardown_tree(record, enabled_only=False)
                self._precheck_cascade_data(tree)
                await self._precheck_teardown(tree)
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
                if type(config) is decl.script_type
            ),
            None,
        )

    def desktop_session_reason(self, config, elevated: bool):
        """在当前启用实例的调用门内查询分身能力。"""
        for record in self.list_plugins():
            decl = self.script_types.get(record.uid)
            if decl is None or type(config) is not decl.script_type:
                continue
            gate = self._calls.get(record.uid)
            if (
                record.info.state != PluginState.ENABLED
                or gate is None
                or not gate.accepting
            ):
                break
            try:
                return gate.wrap(decl.desktop_session_reason)(config, elevated)
            except Exception as error:
                logger.opt(exception=True).warning(f"无法检查插件桌面分身能力: {error}")
                break
        return "plugin_unavailable"

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
                and type(config) is decl.script_type
            ):
                if decl.prefetch_check is None:
                    return []
                return await self._calls[record.uid].wrap(decl.prefetch_check)(config)
        raise PluginPrecheckError("托管所属插件当前不可用")

    def script_config_handler(self, config):
        """把插件托管覆盖了的生命周期钩子包装成宿主内部回调。

        插件一个钩子都没覆盖时返回 ``None``，宿主各入口照旧走插件的直写路径。
        覆盖了钩子却拿不到实例或调用门（停用、重载途中）时拒绝，免得保存绕开钩子。
        """
        from app.models.script_contracts import ScriptConfigHandler
        from app.plugin.base.script import SCRIPT_LIFECYCLE_HOOKS

        for record in self.list_plugins():
            decl = self.script_types.get(record.uid)
            if decl is None or type(config) is not decl.script_type:
                continue
            plugin_cls = record._plugin_cls
            overridden = {
                name
                for name in SCRIPT_LIFECYCLE_HOOKS
                if getattr(plugin_cls, name, None)
                is not getattr(ScriptAdapterPlugin, name)
            }
            if not overridden:
                return None
            plugin = record._plugin
            gate = self._calls.get(record.uid)
            if (
                record.info.state != PluginState.ENABLED
                or plugin is None
                or gate is None
            ):
                raise PluginBusyError("托管所属插件当前不可用")
            return self._wrap_script_hooks(
                ScriptConfigHandler, decl, plugin, gate, overridden
            )
        return None

    @staticmethod
    def _wrap_script_hooks(handler_cls, decl, plugin, gate, overridden):
        """按旧回调签名经调用门转接插件钩子；同步实现的钩子也照样受理。"""

        async def call(name, *args):
            result = gate.wrap(getattr(plugin, name))(*args)
            return await result if inspect.isawaitable(result) else result

        async def clone_script(source, target):
            await call("on_script_cloned", source, target)

        async def cleanup_script_files(script_id):
            await call("on_script_removed", script_id)

        async def prepare_user_read(script, *, user_ids):
            await call("prepare_user_read", script, user_ids)

        async def initialize_user(script, user, *, rollback):
            # 插件钩子不提供撤回：新账号失败时保留，由插件自行修正。
            _ = rollback
            await call("on_user_added", script, user)

        async def prepare_user_update(script, user, *, data):
            guard = await call("prepare_user_update", script, user, data)
            # 守卫在配置执行门内执行，此时插件调用门已经放开，所以再包一层。
            return None if guard is None else gate.wrap(guard)

        # 旧回调字段 → (插件钩子名, 转接函数)
        hooks = {
            "clone_script": ("on_script_cloned", clone_script),
            "cleanup_script_files": ("on_script_removed", cleanup_script_files),
            "prepare_user_read": ("prepare_user_read", prepare_user_read),
            "initialize_user": ("on_user_added", initialize_user),
            "prepare_user_update": ("prepare_user_update", prepare_user_update),
        }
        return handler_cls(
            **{
                field: hook
                for field, (name, hook) in hooks.items()
                if name in overridden
            },
            supports_mod_avd=decl.supports_mod_avd,
            game_kinds=decl.game_kinds,
        )

    def _script_decl_gate(self, config):
        """按托管配置找声明及其插件的调用门；声明在、门不在时门为 ``None``。"""
        for uid, decl in self.script_types.items():
            if type(config) is decl.script_type:
                return decl, self._calls.get(uid)
        return None, None

    def script_game_kinds(self, config, patch: dict) -> tuple[str, ...]:
        """插件托管可绑定的游戏类型：声明了 ``game_kind`` 时按配置收窄，失败时取静态声明。"""
        decl, gate = self._script_decl_gate(config)
        if decl is None:
            raise PluginPrecheckError("托管所属插件当前不可用")
        if decl.game_kind is None or gate is None:
            return decl.game_kinds
        try:
            kind = gate.wrap(decl.game_kind)(config, patch)
        except Exception:
            logger.opt(exception=True).warning(
                f"插件判定游戏类型失败，按静态声明处理: {type(config).__name__}"
            )
            return decl.game_kinds
        return decl.game_kinds if kind is None else (kind,)

    async def search_game_adapter(
        self, uid: UUID, decl: GameTypeDecl
    ) -> Sequence[GameEntry]:
        """通过当前插件实例的调用门执行自己的发现方法。"""
        from app.core import Config

        record = Config.plugin_registry.get(uid)
        gate = self._calls.get(uid)
        if (
            record is None
            or record.info.state != PluginState.ENABLED
            or self.game_types.get(uid) is not decl
            or gate is None
            or not gate.accepting
        ):
            return ()
        entries = await gate.wrap(decl.search)()
        return entries if gate.accepting and self.game_types.get(uid) is decl else ()

    def resolve_script_expander(self, script, config):
        """托管锁内按实际启用声明分派；旧类型由调用方继续走旧工厂。"""
        from app.models.config import ScriptEntry

        if not isinstance(config, ScriptEntry):
            return None
        for record in self.list_plugins():
            decl = self.script_types.get(record.uid)
            if record.info.state != PluginState.ENABLED or decl is None:
                continue
            if type(config) is decl.script_type:
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
        # 激活出过错的根只加载了一部分，整根写回会抹掉没加载上的内容。
        if path is not None and instance.persist_blocked is None:
            write_file(path, await instance.to_dict())
        config_manager.unregister_root(instance)
        record._config = None

    # ==================== record / 状态回写 ====================

    @staticmethod
    def _startup_minimums() -> dict[str, Version]:
        """存量配置要的专项插件里带版本下限的那些；读不了配置时按没有处理。"""
        from app.core.config import Config
        from app.core.config.plugin_upgrade import required_minimum_versions

        try:
            return required_minimum_versions(Config.config_path)
        except Exception:
            logger.exception("读取存量配置要求的插件版本下限失败，按无下限启动")
            return {}

    @staticmethod
    def _host_libraries() -> list[str]:
        """配置里的宿主内置托管要留在插件环境里的库；读不了配置时按没有处理。

        启动前准备环境和安装插件重建环境都从这里取，换入的候选环境是安装时建的。
        """
        from app.core.config import Config
        from app.core.config.plugin_upgrade import required_host_libraries

        try:
            return required_host_libraries(Config.config_path)
        except Exception:
            logger.exception("读取宿主内置托管要的库失败，这次准备插件环境不带上它们")
            return []

    def _below_minimum_family(self, minimums: dict[str, Version]) -> frozenset[str]:
        """已加载版本仍低于下限的插件，加上只为它们服务的上游，这一轮都不启用。

        上游只在启用意图里的下游全在名单里时才一起留下，别的插件照常用得到它。
        """
        from app.core.config import Config

        held: set[str] = set()
        for record in Config.plugin_registry.values():
            minimum = minimums.get(record.info.plugin_name)
            if (
                minimum is None
                or record.info.source != "installed"
                or record._plugin_cls is None
                or not record.info.version
            ):
                continue
            try:
                if Version(record.info.version) < minimum:
                    held.add(record.info.plugin_name)
            except InvalidVersion:
                continue
        grown = bool(held)
        while grown:
            grown = False
            for name in sorted(held):
                record = Config.plugin_registry.by_name(name)
                if record is None:
                    continue
                try:
                    upstream = self._upstream(record)
                except PluginError:
                    continue
                for provider in upstream:
                    provider_name = provider.info.plugin_name
                    if provider_name in held or provider_name == CORE_PLUGIN_NAME:
                        continue
                    if all(
                        other.info.plugin_name in held
                        for other in self._downstream(provider)
                        if other.info.enabled
                    ):
                        held.add(provider_name)
                        grown = True
        return frozenset(held)

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

    def _teardown_tree(
        self, root: PluginRecord, *, enabled_only: bool
    ) -> list[PluginRecord]:
        """根加全部传递下游，顺序同级联。``enabled_only`` 对应停用 / 重载只拆启用中的下游。"""
        out: list[PluginRecord] = []
        seen: set[UUID] = set()
        pending = [root]
        while pending:
            current = pending.pop(0)
            if current.uid in seen:
                continue
            seen.add(current.uid)
            out.append(current)
            pending.extend(
                dep
                for dep in self._downstream(current)
                if not enabled_only or dep.info.state == PluginState.ENABLED
            )
        return out

    async def _precheck_teardown(self, records: Sequence[PluginRecord]) -> None:
        """拆卸前对整棵树问一遍「能不能拆」，收集全部原因后一次拒绝；任何实例都还没动。"""
        blockers: list[dict[str, str]] = []
        for record in records:
            plugin = record._plugin
            if plugin is None:
                continue
            name = record.info.plugin_name
            if isinstance(plugin, (ScriptAdapterPlugin, GameAdapterPlugin)):
                try:
                    plugin.precheck_locks()
                except PluginPrecheckError as exc:
                    blockers.append({"plugin": name, "reason": exc.message})
            # 插件自己的在途工作（运行、更新作业、准备环境）不对应托管锁，由它说明能否拆。
            try:
                reasons = await plugin.teardown_blockers()
            except Exception as exc:
                logger.exception(f"插件拆卸预检出错: {name}")
                reasons = [f"预检出错：{exc}"]
            blockers.extend(
                {"plugin": name, "reason": str(reason)} for reason in reasons or ()
            )
        if blockers:
            raise PluginPrecheckError(
                "；".join(f"插件 `{b['plugin']}`：{b['reason']}" for b in blockers),
                payload={"blockers": blockers},
            )

    def _precheck_cascade_data(self, records: Sequence[PluginRecord]) -> None:
        """连带停用 / 卸载的专项名下还有托管或计划表时拒绝，与直接停用专项时界面拦住同一口径。

        ``records`` 是 ``_teardown_tree`` 的结果，第一项是用户操作的插件本身，不在此列。
        停用专项会按类型删掉名下全部托管和计划表，只经确认框不够：经接口直接写触发器也要拦住。
        只有用户发起的停用与卸载走这里；重载、安装与升级不删数据，不经过此检查。
        """
        from app.core import Config

        in_use: list[dict[str, Any]] = []
        for record in records[1:]:
            plugin = record._plugin
            # 未启用的专项没有登记类型，名下托管与计划表已在它停用时删除。
            if not isinstance(plugin, ScriptAdapterPlugin):
                continue
            scripts = sum(
                1
                for entry in Config.ScriptConfig.values()
                if isinstance(entry, plugin.script_type)
            )
            plans = (
                sum(
                    1
                    for entry in Config.PlanConfig.values()
                    if isinstance(entry, plugin.plan_type)
                )
                if plugin.plan_type is not None
                else 0
            )
            if scripts or plans:
                in_use.append(
                    {
                        "plugin": record.info.plugin_name,
                        "scripts": scripts,
                        "plans": plans,
                    }
                )
        if in_use:
            listing = "、".join(
                f"`{item['plugin']}`（{item['scripts']} 个托管、{item['plans']} 张计划表）"
                for item in in_use
            )
            raise PluginPrecheckError(
                f"会一并停用的专项名下还有托管或计划表：{listing}。"
                "删掉这些托管和计划表后才能停用或卸载",
                payload={"inUse": in_use},
            )

    def dependency_view(self, record: PluginRecord) -> dict[str, list[str]]:
        """只读的依赖关系：直接上游、缺提供者的服务，以及停用 / 卸载会一并拆掉的插件。"""
        depends_on: list[str] = []
        missing: list[str] = []
        for service in record.info.requires:
            provider = self._provider(service)
            if provider is None:
                if service not in missing:
                    missing.append(service)
            elif provider.uid != record.uid:
                name = provider.info.plugin_name
                if name not in depends_on:
                    depends_on.append(name)
        disable_cascade = (
            [
                r.info.plugin_name
                for r in self._teardown_tree(record, enabled_only=True)[1:]
            ]
            if record.info.state == PluginState.ENABLED
            else []
        )
        return {
            "dependsOn": depends_on,
            "missingServices": missing,
            "disableCascade": disable_cascade,
            "uninstallCascade": [
                r.info.plugin_name
                for r in self._teardown_tree(record, enabled_only=False)[1:]
            ],
        }

    def disable_impact(
        self, record: PluginRecord
    ) -> list[Literal["scripts", "games", "plans"]]:
        """汇总停用本插件及级联下游时会删除的配置领域，供前端确认。"""
        impact: set[Literal["scripts", "games", "plans"]] = set()
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
                    # 声明了计划类型的专项停用时，计划类型连同全部计划表一起删除。
                    decl = getattr(cls, "decl", None)
                    if getattr(decl, "plan_type", None) is not None:
                        impact.add("plans")
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
        if not PLUGIN_ID_PATTERN.fullmatch(record.info.plugin_name):
            raise PluginPrecheckError("无效的插件身份，不能用作配置文件名")
        state = record.info.state
        allowed: tuple[str, ...]
        if state == PluginState.FAULT_LOAD:
            allowed = ("load", "unload", "disable")
        elif state == PluginState.FAULT_RUNTIME:
            allowed = ("load", "unload", "enable", "reload", "disable")
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
        """将监视信号加入合并队列，由统一发现流程检查来源及冲突。"""
        queue = self._source_queue
        if not self._initialized or queue is None:
            return
        queue.put_nowait(payload)

    async def _source_worker(self) -> None:
        """合并源码变化并校验完整候选，仅标记需重载，不自动切换运行实现。"""
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
