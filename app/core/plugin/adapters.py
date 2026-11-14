"""宿主拥有的适配器类型登记、锁检查与回滚。"""

from __future__ import annotations

import weakref
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from app.config import ConfigCollection, ConfigEntry, ConfigNode
from app.models.config import GameDeviceEntry, GameEntry
from app.plugin.types import LifecycleContext, PluginState

if TYPE_CHECKING:
    from app.models.config import PluginRecord
    from app.plugin.base.game import GameAdapterPlugin
    from app.plugin.base.script import ScriptAdapterPlugin


class _AdapterRuntime:
    def __init__(self, plugin: GameAdapterPlugin | ScriptAdapterPlugin) -> None:
        """保存插件名称及注册记录的弱引用，让宿主适配接线不延长插件实例的存活时间。"""
        self._record_ref = weakref.ref(plugin.record)
        self.plugin_name = plugin.plugin_name

    @property
    def record(self) -> PluginRecord:
        """取得仍存活的插件注册记录，记录已回收时明确报告接线失效。"""
        record = self._record_ref()
        if record is None:
            raise RuntimeError("插件注册表项已回收")
        return record

    @property
    def lifecycle_context(self) -> LifecycleContext:
        """将记录中的生命周期上下文转换为枚举，供注册与恢复流程选择对应语义。"""
        return LifecycleContext(self.record.info.lifecycle_context)


@dataclass
class GameRegistrationSnapshot:
    """游戏适配回滚记录：新增类型标志与重载前的类。"""

    lifecycle: LifecycleContext
    game_type_added: bool = False
    prev_game_class: type[GameEntry] | None = None
    prev_device_class: type[GameDeviceEntry] | None = None
    prev_control_class: type | None = None


@dataclass
class ScriptRegistrationSnapshot:
    """脚本适配回滚记录：新增类型标志与重载前的类。"""

    lifecycle: LifecycleContext
    script_type_added: bool = False
    plan_type_added: bool = False
    prev_script_type: type[ConfigEntry] | None = None
    prev_plan_type: type[ConfigEntry] | None = None


class GameAdapterRuntime(_AdapterRuntime):
    def __init__(self, plugin: GameAdapterPlugin) -> None:
        """绑定游戏、设备和控制器声明，并初始化宿主注册失败时使用的回滚快照。"""
        super().__init__(plugin)
        self.decl = plugin.decl
        self.game_class = plugin.game_class
        self.device_class = plugin.device_class
        self.control_class = plugin.control_class
        self._system_rollback: GameRegistrationSnapshot | None = None

    def instances(self) -> Iterable[ConfigNode]:
        """从宿主游戏配置集合中筛选属于当前游戏插件的实例，供生命周期处理。"""
        from app.core import Config

        return tuple(
            entry
            for entry in Config.GameConfig.values()
            if isinstance(entry, self.game_class)
        )

    def precheck_locks(self) -> None:
        """用本类创建的游戏配置若已锁定，则无法 remove_type / reload_type。"""
        from app.core import Config
        from app.plugin.errors import PluginPrecheckError

        game_class = self.game_class
        for entry in Config.GameConfig.values():
            if not isinstance(entry, game_class) or not entry.is_locked:
                continue
            raise PluginPrecheckError(
                f"用 {game_class.__name__} 创建的游戏配置 {entry.uid} 已锁定，"
                f"无法 remove_type",
                payload={
                    "plugin": self.plugin_name,
                    "game_uid": str(entry.uid),
                    "script_type": game_class.__name__,
                },
            )

    async def _record_system_rollback(self) -> GameRegistrationSnapshot:
        """类型表写入前统一记录回退信息。"""
        from app.core import Config

        rb = GameRegistrationSnapshot(lifecycle=self.lifecycle_context)
        if self.lifecycle_context != LifecycleContext.RELOAD:
            self._system_rollback = rb
            return rb

        games = Config.GameConfig
        game_class = self.game_class
        # 重载换皮前表内仍是旧类对象；实例按表内类匹配，不能只用新 ClassVar
        live_cls = games.entry_types.get(game_class.__name__)
        rb.prev_game_class = live_cls if isinstance(live_cls, type) else None
        match_cls = rb.prev_game_class or game_class
        for entry in list(games.values()):
            if not isinstance(entry, match_cls):
                continue
            rb.prev_control_class = (
                type(entry._game_control) if entry._game_control is not None else None
            )
            # 设备类插件侧只有一个；从任一同类实例类型表取非上界项
            for cls in entry.devices.entry_types.values():
                if cls is GameDeviceEntry:
                    continue
                if isinstance(cls, type) and issubclass(cls, GameDeviceEntry):
                    rb.prev_device_class = cls
                    break
            if rb.prev_device_class is not None:
                break
        self._system_rollback = rb
        return rb

    async def system_enable(self) -> None:
        """按语境登记或重载游戏配置类；reload 时保留游戏及嵌套设备身份。

        顺序：快照 → 类型表 → ``Plugin.game_types``。
        成功后保留 ``_system_rollback``，供同一次 enable 在 system_enable 之后失败时回滚。
        """
        from app.config import NodeState
        from app.core import Config
        from app.core.game_manager import GameManager
        from app.core.plugin import Plugin

        if self.lifecycle_context == LifecycleContext.RELOAD_CASCADE:
            return
        game_class = self.game_class
        device_class = self.device_class
        control_class = self.control_class

        # ── 领域集合尚未 activate：只注入类型表，供稍后热化按类名还原 ──
        if Config.GameConfig.activation_state != NodeState.ACTIVE:
            rb = await self._record_system_rollback()
            # 类型表键仍是框架约定的类名
            Config.GameConfig.register_initial_type(game_class)
            rb.game_type_added = True
        elif self.lifecycle_context == LifecycleContext.RELOAD:
            # ── reload：先快照，再以 reload_type 重建并保留身份 ──
            await self._record_system_rollback()
            Config.GameConfig.reload_type(game_class)
            await Config.GameConfig.commit()
            for entry in list(Config.GameConfig.values()):
                if not isinstance(entry, game_class):
                    continue
                # 父配置重建时已按新声明还原嵌套设备及 UID；单独动态登记的类型才另行换类。
                existing = entry.devices.entry_types.get(device_class.__name__)
                if existing is not None and existing is not device_class:
                    entry.devices.reload_type(device_class)
                    await entry.devices.commit()
                entry.bind_runtime_signals()
                ctrl = GameManager.create_control(
                    config=entry, control_class=control_class
                )
                await ctrl.refresh()
        else:
            # ── normal / unload：add_type 游戏类，给已有实例补设备类 ──
            rb = await self._record_system_rollback()
            Config.GameConfig.add_type(game_class)
            await Config.GameConfig.commit()
            rb.game_type_added = True
            for entry in list(Config.GameConfig.values()):
                if not isinstance(entry, game_class):
                    continue
                if device_class.__name__ not in entry.devices.entry_types:
                    entry.devices.add_type(device_class)
                    await entry.devices.commit()
                ctrl = entry._game_control
                if ctrl is None:
                    ctrl = GameManager.create_control(
                        config=entry, control_class=control_class
                    )

        assert self.decl is not None
        Plugin.game_types[self.record.uid] = self.decl

    async def system_disable(self) -> None:
        """普通禁用：类型表 → 目录 → 清快照。重载语境三步都不做。"""
        from app.config import NodeState
        from app.core import Config
        from app.core.plugin import Plugin

        if self.lifecycle_context in {
            LifecycleContext.RELOAD,
            LifecycleContext.RELOAD_CASCADE,
        }:
            return

        # ── 1. 类型表 ──
        game_class = self.game_class
        if Config.GameConfig.activation_state != NodeState.ACTIVE:
            Config.GameConfig.remove_initial_type(game_class.__name__)
        else:
            Config.GameConfig.remove_type(game_class)
            await Config.GameConfig.commit()
        # ── 2. 搜索/展示目录（仅本适配写入，也仅此处与 rollback 摘掉）──
        Plugin.game_types.pop(self.record.uid, None)
        # ── 3. 清快照 ──
        self._system_rollback = None

    async def system_rollback(
        self,
        during: PluginState,
        lifecycle_context: LifecycleContext,
        exc: BaseException,
    ) -> None:
        """按 ``_system_rollback`` 对称回退；终态顺序与 disable 一致：类型表 → 目录 → 清快照。"""
        _ = exc
        from app.config import NodeState
        from app.core import Config
        from app.core.plugin import Plugin

        rb = self._system_rollback
        game_class = self.game_class

        if during == PluginState.ENABLING:
            if lifecycle_context == LifecycleContext.RELOAD_CASCADE:
                return
            if lifecycle_context == LifecycleContext.RELOAD:
                # ── reload：reload_type 回旧类（框架内事务）；设备类公开 API 换回 ──
                if (
                    rb is not None
                    and Config.GameConfig.activation_state == NodeState.ACTIVE
                ):
                    prev = rb.prev_game_class
                    try:
                        if prev is not None:
                            Config.GameConfig.reload_type(prev)
                            await Config.GameConfig.commit()
                            from app.core.game_manager import GameManager

                            for entry in Config.GameConfig.values():
                                if isinstance(entry, prev):
                                    entry.bind_runtime_signals()
                                    if rb.prev_control_class is not None:
                                        GameManager.create_control(
                                            config=entry,
                                            control_class=rb.prev_control_class,
                                        )
                    except Exception:
                        pass
                # 启用失败后插件非 enabled：目录必须摘掉（可能已写成新 decl）
                Plugin.game_types.pop(self.record.uid, None)
                self._system_rollback = None
                return

            # ── normal / unload：若曾加类型则卸类型表，再摘目录、清快照 ──
            if rb is not None and rb.game_type_added:
                try:
                    if Config.GameConfig.activation_state != NodeState.ACTIVE:
                        Config.GameConfig.remove_initial_type(game_class.__name__)
                    else:
                        Config.GameConfig.remove_type(game_class)
                        await Config.GameConfig.commit()
                except Exception:
                    pass
            Plugin.game_types.pop(self.record.uid, None)
            self._system_rollback = None
            return

        if during == PluginState.DISABLING:
            if lifecycle_context in {
                LifecycleContext.RELOAD,
                LifecycleContext.RELOAD_CASCADE,
            }:
                return
            # 禁用失败：不补做 remove_type（可能尚未执行）；只确保目录与快照不脏
            Plugin.game_types.pop(self.record.uid, None)
            self._system_rollback = None


class ScriptAdapterRuntime(_AdapterRuntime):
    def __init__(self, plugin: ScriptAdapterPlugin) -> None:
        """绑定脚本、用户和计划声明，初始化脚本配置注册的回滚快照。"""
        super().__init__(plugin)
        self.decl = plugin.decl
        self.script_type = plugin.script_type
        self.plan_type = plugin.plan_type
        self._system_rollback: ScriptRegistrationSnapshot | None = None

    def instances(self) -> Iterable[ConfigNode]:
        """从宿主脚本配置集合中筛选属于当前专项插件的实例，供卸载、重载等流程处理。"""
        from app.core import Config

        return tuple(
            entry
            for entry in Config.ScriptConfig.values()
            if isinstance(entry, self.script_type)
        )

    def precheck_locks(self) -> None:
        """系统预检：该类型脚本实例任一锁定则拒绝（设计 §7.2）。"""
        from app.core import Config
        from app.plugin.errors import PluginPrecheckError

        script_type = self.script_type
        for entry in Config.ScriptConfig.values():
            if isinstance(entry, script_type) and entry.is_locked:
                raise PluginPrecheckError(
                    f"脚本配置 {entry.uid} 已锁定，无法禁用/重载/卸载",
                    payload={
                        "plugin": self.plugin_name,
                        "script_uid": str(entry.uid),
                    },
                )

    async def _record_system_rollback(self) -> ScriptRegistrationSnapshot:
        """类型表写入前统一记录回退信息。"""
        from app.core import Config

        rb = ScriptRegistrationSnapshot(lifecycle=self.lifecycle_context)
        if self.lifecycle_context != LifecycleContext.RELOAD:
            self._system_rollback = rb
            return rb

        # 重载换皮前表内仍是旧类对象；回滚要 reload 回它，不能只用新 ClassVar
        live_cls = Config.ScriptConfig.entry_types.get(self.script_type.__name__)
        if isinstance(live_cls, type):
            rb.prev_script_type = live_cls
        if self.plan_type is not None:
            live_plan = Config.PlanConfig.entry_types.get(self.plan_type.__name__)
            if isinstance(live_plan, type):
                rb.prev_plan_type = live_plan
        self._system_rollback = rb
        return rb

    async def system_enable(self) -> None:
        """登记脚本类型、计划类型与类型目录。

        顺序：快照 → 类型表 → ``Plugin.script_types``。用户类型域由 script_type 类体
        声明（见 ``_validate_decl``），``UserExpander`` 经 ``Plugin.script_types`` 的 decl 取，
        故此处既不补挂 add_type 也不另立索引。
        成功后保留 ``_system_rollback``，供同一次 enable 在本方法之后失败时回滚。
        """
        from app.config import NodeState
        from app.core import Config
        from app.core.plugin import Plugin

        ctx = self.lifecycle_context
        if ctx == LifecycleContext.RELOAD_CASCADE:
            return
        script_type = self.script_type
        script_type.bind_runtime_signals()
        # [兼容旧专项] 根集合仍以旧专项联合类型公开；这里仅操作动态类型表。
        scripts = cast(ConfigCollection[ConfigEntry], Config.ScriptConfig)
        plans = cast(ConfigCollection[ConfigEntry], Config.PlanConfig)

        # ── 1. 快照 + 类型表 ──
        if scripts.activation_state != NodeState.ACTIVE:
            # 领域集合尚未 activate：只注入类型表，供稍后热化按类名还原
            rb = await self._record_system_rollback()
            scripts.register_initial_type(script_type)
            rb.script_type_added = True
            if self.plan_type is not None:
                plans.register_initial_type(self.plan_type)
                rb.plan_type_added = True
        elif ctx == LifecycleContext.RELOAD:
            # 保留实例 uid，仅换类
            await self._record_system_rollback()
            scripts.reload_type(script_type)
            await scripts.commit()
            if self.plan_type is not None:
                plans.reload_type(self.plan_type)
                await plans.commit()
        else:
            # normal / unload：user_type 已在 script_type 类体上收窄，直接 add_type
            rb = await self._record_system_rollback()
            scripts.add_type(script_type)
            await scripts.commit()
            rb.script_type_added = True
            if self.plan_type is not None:
                plans.add_type(self.plan_type)
                await plans.commit()
                rb.plan_type_added = True
                # plan_id 已在 UserEntry 宿主骨架上；选项由 /api/info/combox/plan 提供

        # ── 2. 类型目录（仅本适配写入，也仅 disable / rollback 摘掉）──
        assert self.decl is not None
        Plugin.script_types[self.record.uid] = self.decl

    async def system_disable(self) -> None:
        """普通禁用：类型表 → 目录 → 清快照。重载语境三步都不做。"""
        from app.config import NodeState
        from app.core import Config
        from app.core.plugin import Plugin

        if self.lifecycle_context in {
            LifecycleContext.RELOAD,
            LifecycleContext.RELOAD_CASCADE,
        }:
            return

        script_type = self.script_type
        script_type.bind_runtime_signals()
        # [兼容旧专项] 根集合仍以旧专项联合类型公开；这里仅操作动态类型表。
        scripts = cast(ConfigCollection[ConfigEntry], Config.ScriptConfig)
        plans = cast(ConfigCollection[ConfigEntry], Config.PlanConfig)
        # ── 1. 类型表（remove_type 级联删该类实例，用户配置随嵌套集合一并清掉）──
        if scripts.activation_state != NodeState.ACTIVE:
            scripts.remove_initial_type(script_type.__name__)
        else:
            scripts.remove_type(script_type)
            await scripts.commit()
        if self.plan_type is not None:
            if plans.activation_state != NodeState.ACTIVE:
                plans.remove_initial_type(self.plan_type.__name__)
            else:
                plans.remove_type(self.plan_type)
                await plans.commit()
        # ── 2. 类型目录 ──
        Plugin.script_types.pop(self.record.uid, None)
        # ── 3. 清快照 ──
        self._system_rollback = None

    async def system_rollback(
        self,
        during: PluginState,
        lifecycle_context: LifecycleContext,
        exc: BaseException,
    ) -> None:
        """按 ``_system_rollback`` 对称回退（设计 §7.4）；终态顺序与 disable 一致。"""
        _ = exc
        from app.config import NodeState
        from app.core import Config
        from app.core.plugin import Plugin

        rb = self._system_rollback
        script_type = self.script_type
        script_type.bind_runtime_signals()
        # [兼容旧专项] 根集合仍以旧专项联合类型公开；这里仅操作动态类型表。
        scripts = cast(ConfigCollection[ConfigEntry], Config.ScriptConfig)
        plans = cast(ConfigCollection[ConfigEntry], Config.PlanConfig)

        if during == PluginState.ENABLING:
            if lifecycle_context == LifecycleContext.RELOAD_CASCADE:
                return
            if lifecycle_context == LifecycleContext.RELOAD:
                # 优先 reload_type 回旧类；禁止误 remove_type
                if rb is not None and scripts.activation_state == NodeState.ACTIVE:
                    try:
                        if rb.prev_script_type is not None:
                            scripts.reload_type(rb.prev_script_type)
                            await scripts.commit()
                        if rb.prev_plan_type is not None:
                            plans.reload_type(rb.prev_plan_type)
                            await plans.commit()
                    except Exception:
                        pass
                # 启用失败后插件非 enabled：目录必须撤净
                Plugin.script_types.pop(self.record.uid, None)
                self._system_rollback = None
                return

            # ── normal / unload：幂等撤净；类型表只回退本次真加过的 ──
            if rb is not None and rb.script_type_added:
                try:
                    if scripts.activation_state != NodeState.ACTIVE:
                        scripts.remove_initial_type(script_type.__name__)
                    else:
                        scripts.remove_type(script_type)
                        await scripts.commit()
                except Exception:
                    pass
            if rb is not None and rb.plan_type_added:
                assert self.plan_type is not None
                try:
                    if plans.activation_state != NodeState.ACTIVE:
                        plans.remove_initial_type(self.plan_type.__name__)
                    else:
                        plans.remove_type(self.plan_type)
                        await plans.commit()
                except Exception:
                    pass
            Plugin.script_types.pop(self.record.uid, None)
            self._system_rollback = None
            return

        if during == PluginState.DISABLING:
            if lifecycle_context in {
                LifecycleContext.RELOAD,
                LifecycleContext.RELOAD_CASCADE,
            }:
                return
            # 禁用失败：不补做 remove_type（可能尚未执行）；只确保目录不脏
            Plugin.script_types.pop(self.record.uid, None)
            self._system_rollback = None
