"""脚本适配：插件以 decl 声明脚本类、用户类、计划类与用户展开类；系统段管理类型表。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from app.models.config.plan import PlanEntry
from app.models.config.script import ScriptEntry, UserEntry
from app.models.task import TaskMode
from app.plugin.types import LifecycleContext, PluginState
from app.task import UserExpander

from .extension import ExtensionPlugin

if TYPE_CHECKING:
    from .emulator import EmulatorExpect


@dataclass(frozen=True)
class ScriptTypeDecl:
    """脚本适配统一声明：子类以 ClassVar ``decl`` 一次交出。

    与游戏适配的 ``GameTypeDecl`` 同形。``plan_entry_type`` 为 ``None`` 表示
    该脚本不用计划表；其余三项必填且须是收窄后的子类。
    ``expect_builder`` 从脚本配置解析模拟器期望；``None`` 表示只备份还原。
    """

    entry_type: type[ScriptEntry]
    user_type: type[UserEntry]
    expander_class: type[UserExpander]
    plan_entry_type: type[PlanEntry] | None = None
    supported_modes: tuple[TaskMode, ...] = (
        TaskMode.AUTO_PROXY,
        TaskMode.MANUAL_REVIEW,
        TaskMode.SCRIPT_CONFIG,
    )
    expect_builder: Callable[[ScriptEntry], EmulatorExpect | None] | None = None


@dataclass
class _SystemRollback:
    """脚本适配 system_rollback 的唯一真相源。标志 did_*，快照 prev_*。"""

    lifecycle: LifecycleContext
    script_type_added: bool = False
    plan_type_added: bool = False
    prev_entry_type: type[ScriptEntry] | None = None
    prev_plan_entry_type: type[PlanEntry] | None = None


class ScriptAdapterPlugin(ExtensionPlugin):
    """启用时把脚本配置类登记进 ScriptConfig；reload 时 reload_type 换类保 uid。"""

    script_type_key: ClassVar[str] = ""
    # 子类重写 decl；entry_type 等是外部读取面。
    decl: ClassVar[ScriptTypeDecl | None] = None

    def __init__(self, config: Any = None, record: Any = None) -> None:
        super().__init__(config=config, record=record)
        self._system_rollback: _SystemRollback | None = None

        if (
            self.decl is None
            or self.decl.entry_type is ScriptEntry
            or self.decl.user_type is UserEntry
            or self.decl.expander_class is UserExpander
            or not self.decl.supported_modes
        ):
            raise ValueError(
                "脚本适配须以 decl 声明收窄的 entry_type、user_type、"
                "expander_class 与非空 supported_modes"
            )
        self.entry_type = self.decl.entry_type
        self.user_type = self.decl.user_type
        self.expander_class = self.decl.expander_class
        self.plan_entry_type = self.decl.plan_entry_type
        self.supported_modes = self.decl.supported_modes
        if self.decl.expect_builder is not None and not callable(
            self.decl.expect_builder
        ):
            raise ValueError("expect_builder 须为可调用或 None")
        self._validate_decl()

    def _validate_decl(self) -> None:
        """校验脚本/用户预声明字段；有计划类型时要求 user.info 含 plan_id。"""
        fields = getattr(self.entry_type, "model_fields", {})
        if "info" not in fields or "users" not in fields:
            raise ValueError("entry_type 须含 info 与 users")
        # user_type 不是 Config 可直达的类型，而是 entry_type.users 这个嵌套集合的
        # 类型域，故不走全局类型表，改为要求子类在类体上 collection(user_type) 收窄。
        # 校验在此一次性完成：实例出生即带正确类型域，无需运行时补挂 add_type。
        users_field = fields["users"]
        factory = getattr(users_field, "default_factory", None)
        declared = getattr(factory(), "_entry_types", {}) if factory else {}
        if list(declared.values()) != [self.user_type]:
            raise ValueError(
                f"entry_type.users 须以 collection({self.user_type.__name__}) "
                f"收窄为仅含该用户类型，当前为 {list(declared)}"
            )
        ufields = getattr(self.user_type, "model_fields", {})
        if "info" not in ufields:
            raise ValueError("user_type 须含 info")
        # 计划表选择字段：宿主骨架 UserEntry.info.plan_id；子类须保留
        if self.plan_entry_type is not None:
            info_ann = ufields["info"]
            info_cls = getattr(info_ann, "annotation", None)
            info_fields = getattr(info_cls, "model_fields", {}) or {}
            if not info_fields:
                info_fields = getattr(
                    getattr(self.user_type, "Info", None), "model_fields", {}
                )
            if "plan_id" not in info_fields:
                raise ValueError(
                    "声明了 plan_entry_type 时，user_type.info 须含 plan_id"
                )

    def precheck_locks(self) -> None:
        """系统预检：该类型脚本实例任一锁定则拒绝（设计 §7.2）。"""
        from app.core import Config
        from app.plugin.errors import PluginPrecheckError

        entry_type = self.entry_type
        for entry in Config.ScriptConfig.values():
            if isinstance(entry, entry_type) and entry.is_locked:
                raise PluginPrecheckError(
                    f"脚本配置 {entry.uid} 已锁定，无法禁用/重载/卸载",
                    payload={
                        "plugin": self.plugin_name,
                        "script_uid": str(entry.uid),
                    },
                )

    async def _record_system_rollback(self) -> _SystemRollback:
        """类型表写入前统一记录回退信息。"""
        from app.core import Config

        rb = _SystemRollback(lifecycle=self.lifecycle_context)
        if self.lifecycle_context != LifecycleContext.RELOAD:
            self._system_rollback = rb
            return rb

        # 重载换皮前表内仍是旧类对象；回滚要 reload 回它，不能只用新 ClassVar
        live_cls = Config.ScriptConfig.effective._entry_types.get(
            self.entry_type.__name__
        )
        if isinstance(live_cls, type):
            rb.prev_entry_type = live_cls
        if self.plan_entry_type is not None:
            live_plan = Config.PlanConfig.effective._entry_types.get(
                self.plan_entry_type.__name__
            )
            if isinstance(live_plan, type):
                rb.prev_plan_entry_type = live_plan
        self._system_rollback = rb
        return rb

    async def system_enable(self) -> None:
        """登记脚本类型、计划类型与类型目录。

        顺序：快照 → 类型表 → ``Plugin.script_types``。用户类型域由 entry_type 类体
        声明（见 ``_validate_decl``），``UserExpander`` 经 ``Plugin.script_types`` 的 decl 取，
        故此处既不补挂 add_type 也不另立索引。
        成功后保留 ``_system_rollback``，供同一次 enable 在本方法之后失败时回滚。
        """
        from app.config import NodeState
        from app.core import Config
        from app.core.plugin_manager import Plugin

        ctx = self.lifecycle_context
        if ctx == LifecycleContext.RELOAD_CASCADE:
            return
        entry_type = self.entry_type
        scripts = Config.ScriptConfig
        plans = Config.PlanConfig

        # ── 1. 快照 + 类型表 ──
        if scripts.activation_state != NodeState.ACTIVE:
            # 领域集合尚未 activate：只注入类型表，供稍后热化按类名还原
            rb = await self._record_system_rollback()
            scripts._entry_types[entry_type.__name__] = entry_type
            rb.script_type_added = True
            if self.plan_entry_type is not None:
                plans._entry_types[self.plan_entry_type.__name__] = self.plan_entry_type
                rb.plan_type_added = True
        elif ctx == LifecycleContext.RELOAD:
            # 保留实例 uid，仅换类
            await self._record_system_rollback()
            scripts.reload_type(entry_type)
            await scripts.commit()
            if self.plan_entry_type is not None:
                plans.reload_type(self.plan_entry_type)
                await plans.commit()
        else:
            # normal / unload：user_type 已在 entry_type 类体上收窄，直接 add_type
            rb = await self._record_system_rollback()
            scripts.add_type(entry_type)
            await scripts.commit()
            rb.script_type_added = True
            if self.plan_entry_type is not None:
                plans.add_type(self.plan_entry_type)
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
        from app.core.plugin_manager import Plugin

        if self.lifecycle_context in {
            LifecycleContext.RELOAD,
            LifecycleContext.RELOAD_CASCADE,
        }:
            return

        entry_type = self.entry_type
        scripts = Config.ScriptConfig
        plans = Config.PlanConfig
        # ── 1. 类型表（remove_type 级联删该类实例，用户配置随嵌套集合一并清掉）──
        if scripts.activation_state != NodeState.ACTIVE:
            scripts._entry_types.pop(entry_type.__name__, None)
        else:
            scripts.remove_type(entry_type)
            await scripts.commit()
        if self.plan_entry_type is not None:
            if plans.activation_state != NodeState.ACTIVE:
                plans._entry_types.pop(self.plan_entry_type.__name__, None)
            else:
                plans.remove_type(self.plan_entry_type)
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
        from app.core.plugin_manager import Plugin

        rb = self._system_rollback
        entry_type = self.entry_type
        scripts = Config.ScriptConfig
        plans = Config.PlanConfig

        if during == PluginState.ENABLING:
            if lifecycle_context == LifecycleContext.RELOAD_CASCADE:
                return
            if lifecycle_context == LifecycleContext.RELOAD:
                # 优先 reload_type 回旧类；禁止误 remove_type
                if rb is not None and scripts.activation_state == NodeState.ACTIVE:
                    try:
                        if rb.prev_entry_type is not None:
                            scripts.reload_type(rb.prev_entry_type)
                            await scripts.commit()
                        if rb.prev_plan_entry_type is not None:
                            plans.reload_type(rb.prev_plan_entry_type)
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
                        scripts._entry_types.pop(entry_type.__name__, None)
                    else:
                        scripts.remove_type(entry_type)
                        await scripts.commit()
                except Exception:
                    pass
            if rb is not None and rb.plan_type_added:
                assert self.plan_entry_type is not None
                try:
                    if plans.activation_state != NodeState.ACTIVE:
                        plans._entry_types.pop(self.plan_entry_type.__name__, None)
                    else:
                        plans.remove_type(self.plan_entry_type)
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
