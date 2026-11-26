"""脚本适配：插件以 decl 声明脚本类、用户类、计划类与用户展开类；系统段管理类型表。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Literal, get_args

from app.models.config.plan import PlanEntry
from app.models.config.plugin_script import ScriptEntry, UserEntry
from app.models.schema import DownloadRequest
from app.models.task import TaskMode
from app.task.user_expander import UserExpander

from .extension import _AdapterPlugin

if TYPE_CHECKING:
    from pathlib import Path

    from app.utils.common.config.restore import ConfigRestorePool

    from .emulator import EmulatorExpect


DesktopSessionCheckReason = Literal["admin_required", "unsupported_config"]
DesktopSessionReason = Literal[DesktopSessionCheckReason, "plugin_unavailable"]
FirstAccountMode = Literal["direct", "wizard"]


@dataclass(frozen=True)
class ScriptTypeDecl:
    """脚本适配统一声明：子类以 ClassVar ``decl`` 一次交出。

    与游戏适配的 ``GameTypeDecl`` 同形。``plan_type`` 为 ``None`` 表示
    该脚本不用计划表；其余三项必填且须是收窄后的子类。
    ``expect_builder`` 从脚本配置解析模拟器期望；``None`` 表示只备份还原。
    """

    script_type: type[ScriptEntry]
    user_type: type[UserEntry]
    expander_class: type[UserExpander]
    plan_type: type[PlanEntry] | None = None
    supported_modes: tuple[TaskMode, ...] = (
        TaskMode.AUTO_PROXY,
        TaskMode.SCRIPT_VIEW,
        TaskMode.SCRIPT_CONFIG,
    )
    expect_builder: Callable[[ScriptEntry], EmulatorExpect | None] | None = None
    prefetch_check: Callable[[ScriptEntry], Awaitable[list[DownloadRequest]]] | None = (
        None
    )
    # 以下为对接现有 MAS 业务新增的声明，不属于来源框架的原始类型声明。
    # 首页活动展示和活动提醒使用的游戏标识，不声明游戏适配能力。
    activity_game: str | None = None
    game_kinds: tuple[str, ...] = ()
    supports_mod_avd: bool = False
    # 按托管当前配置和保存补丁判定这次用的游戏类型：返回 "emulator" / "client"；
    # 返回 None、插件不可用或抛异常时按 game_kinds。所选目标类型不一致只提示、
    # 不拦截绑定和运行。同步调用，经插件调用门。
    game_kind: Callable[[ScriptEntry, dict[str, Any]], str | None] | None = None
    # [兼容旧调用方] MFW 系已发布适配器使用布尔能力检查。
    desktop_session: Callable[[ScriptEntry], bool] | None = None
    # None 沿用旧插件的绑定能力，game_kinds 为空时不限制目标类型。
    supports_game_binding: bool | None = None
    supports_account_game_override: bool = True
    # 维护入口复用调度任务的锁、进程归属和停止确认。
    maintenance_expander: type[UserExpander] | None = None
    restore_pools: tuple[ConfigRestorePool, ...] = ()
    # 同步读取当前托管配置与宿主提权状态；None 表示可用。
    desktop_session_check: (
        Callable[[ScriptEntry, bool], DesktopSessionCheckReason | None] | None
    ) = None
    first_account_mode: FirstAccountMode = "direct"

    def desktop_session_reason(
        self, config: ScriptEntry, elevated: bool
    ) -> DesktopSessionReason | None:
        """核验自动代理模式，并在调用门返回前拦截无效结果。"""
        if TaskMode.AUTO_PROXY not in self.supported_modes:
            return "unsupported_config"
        if self.desktop_session_check is not None:
            result = self.desktop_session_check(config, elevated)
            if result is None or result in get_args(DesktopSessionCheckReason):
                return result
        elif self.desktop_session is not None:
            result = self.desktop_session(config)
            if isinstance(result, bool):
                return None if result else "unsupported_config"
        else:
            return "unsupported_config"
        if isinstance(result, Coroutine):
            result.close()
        raise ValueError("桌面分身能力检查须同步返回有效值")


class ScriptAdapterPlugin(_AdapterPlugin):
    """启用时把脚本配置类登记进 ScriptConfig；reload 时 reload_type 换类保 uid。"""

    script_type_key: ClassVar[str] = ""
    # 子类重写 decl；script_type 等是外部读取面。
    decl: ClassVar[ScriptTypeDecl | None] = None

    def __init__(self, config: Any = None, record: Any = None) -> None:
        """初始化专项插件并校验脚本、用户、任务展开器与执行模式声明，拒绝缺失或无效实现。"""
        super().__init__(config=config, record=record)

        if (
            self.decl is None
            or self.decl.script_type is ScriptEntry
            or self.decl.user_type is UserEntry
            or self.decl.expander_class is UserExpander
            or not self.decl.supported_modes
        ):
            raise ValueError(
                "脚本适配须以 decl 声明收窄的 script_type、user_type、"
                "expander_class 与非空 supported_modes"
            )
        self.script_type = self.decl.script_type
        self.user_type = self.decl.user_type
        self.expander_class = self.decl.expander_class
        self.plan_type = self.decl.plan_type
        self.supported_modes = self.decl.supported_modes
        if self.decl.expect_builder is not None and not callable(
            self.decl.expect_builder
        ):
            raise ValueError("expect_builder 须为可调用或 None")
        if self.decl.desktop_session_check is not None and not callable(
            self.decl.desktop_session_check
        ):
            raise ValueError("desktop_session_check 须为可调用或 None")
        self._validate_decl()

    # ── 托管生命周期钩子 ──
    # 默认什么都不做；宿主只在子类覆盖了某一项时才接上它（见 SCRIPT_LIFECYCLE_HOOKS）。
    # 全部经本插件的调用门执行，插件停用中调用得到 PluginBusyError；
    # 抛出的其他异常原样传给发起操作的接口。

    async def on_script_cloned(self, source: ScriptEntry, target: ScriptEntry) -> None:
        """复制托管：新托管的配置已提交，宿主复制 ``data/<来源 uid>`` 之前调用。"""

    async def on_script_removed(self, script_id: str) -> None:
        """删除托管：配置删除已提交、宿主已删 ``data/<uid>`` 之后调用。"""

    async def prepare_user_read(
        self, script: ScriptEntry, user_ids: list[str] | None
    ) -> None:
        """读取账号配置前调用；``user_ids`` 为 ``None`` 表示读取整个托管的账号。"""

    async def on_user_added(self, script: ScriptEntry, user: UserEntry) -> None:
        """新账号已提交后调用；失败时账号保留，不撤回。"""

    async def prepare_user_update(
        self, script: ScriptEntry, user: UserEntry, data: dict[str, Any]
    ) -> Callable[[], None] | None:
        """保存账号前原地修改 ``data``（例如加密、补字段）。

        在配置执行门之外调用，可以等待；返回的同步守卫在执行门内、写入前执行，
        守卫抛出异常时本次不写入。
        """
        return None

    def validate_update(self, data: dict[str, Any]) -> None:
        """保存托管配置前校验补丁；抛异常即拒绝保存。同步调用，不要在这里等待。"""

    async def import_config(
        self,
        script: ScriptEntry,
        target_directory: "Path",
        *,
        user_id: str | None = None,
    ) -> None:
        """把安装目录里的上游配置导入到 ``target_directory``；由导入接口调用。"""

    async def initialize(self, script: ScriptEntry) -> None:
        """托管配置激活后的一次性整理，由宿主在启动装配时按提交边界调用。"""

    def _validate_decl(self) -> None:
        """校验脚本/用户预声明字段；有计划类型时要求 user.info 含 plan_id。"""
        fields = getattr(self.script_type, "model_fields", {})
        if "info" not in fields or "users" not in fields:
            raise ValueError("script_type 须含 info 与 users")
        # user_type 不是 Config 可直达的类型，而是 script_type.users 这个嵌套集合的
        # 类型域，故不走全局类型表，改为要求子类在类体上 collection(user_type) 收窄。
        # 校验在此一次性完成：实例出生即带正确类型域，无需运行时补挂 add_type。
        users_field = fields["users"]
        factory = getattr(users_field, "default_factory", None)
        declared = factory().entry_types if factory else {}
        if list(declared.values()) != [self.user_type]:
            raise ValueError(
                f"script_type.users 须以 collection({self.user_type.__name__}) "
                f"收窄为仅含该用户类型，当前为 {list(declared)}"
            )
        ufields = getattr(self.user_type, "model_fields", {})
        if "info" not in ufields:
            raise ValueError("user_type 须含 info")
        # 计划表选择字段：宿主骨架 UserEntry.info.plan_id；子类须保留
        if self.plan_type is not None:
            info_ann = ufields["info"]
            info_cls = getattr(info_ann, "annotation", None)
            info_fields = getattr(info_cls, "model_fields", {}) or {}
            if not info_fields:
                info_fields = getattr(
                    getattr(self.user_type, "Info", None), "model_fields", {}
                )
            if "plan_id" not in info_fields:
                raise ValueError("声明了 plan_type 时，user_type.info 须含 plan_id")


# 宿主按名字检查子类是否覆盖，只接覆盖了的钩子。
SCRIPT_LIFECYCLE_HOOKS: tuple[str, ...] = (
    "on_script_cloned",
    "on_script_removed",
    "prepare_user_read",
    "on_user_added",
    "prepare_user_update",
    "validate_update",
    "import_config",
    "initialize",
)
