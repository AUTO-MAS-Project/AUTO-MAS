"""脚本适配：插件以 decl 声明脚本类、用户类、计划类与用户展开类；系统段管理类型表。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from app.models.config.plan import PlanEntry
from app.models.config.plugin_script import ScriptEntry, UserEntry
from app.models.schema import DownloadRequest
from app.models.task import TaskMode
from app.task.user_expander import UserExpander

from .extension import _AdapterPlugin

if TYPE_CHECKING:
    from .emulator import EmulatorExpect


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
        self._validate_decl()

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
