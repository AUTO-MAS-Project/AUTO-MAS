"""使用宿主 SDK 声明托管、账号和计划。"""

from typing import Annotated, Literal

from auto_mas_core import (
    ConfigCollection,
    ConfigGroup,
    ConfigTableColumn,
    PlanEntry,
    ScriptAdapterPlugin,
    ScriptEntry,
    ScriptTypeDecl,
    ScriptViewWorker,
    TaskMode,
    UiVisibility,
    UserEntry,
    UserExpander,
    collection,
    encrypted,
    ui,
    ui_visibility,
)
from pydantic import Field


class Demo15UserConfig(UserEntry):
    class Credentials(ConfigGroup):
        Id: str = Field(default="", description="账号")
        UsePassword: bool = Field(default=True, description="使用密码")
        Password: Annotated[str, encrypted()] = Field(default="", description="密码")

    Info: Credentials = Field(default_factory=Credentials, description="登录设置")

    @ui_visibility("Info.Password")
    def password_visibility(self) -> UiVisibility:
        return UiVisibility.MASKED if self.Info.UsePassword else UiVisibility.HIDE


class Demo15Config(ScriptEntry):
    class RunOptions(ConfigGroup):
        Retries: int = Field(default=0, ge=0, description="重试次数")
        Mode: Literal["once", "repeat"] = Field(default="once", description="执行方式")
        Token: Annotated[str, ui(visibility=UiVisibility.MASKED), encrypted()] = Field(
            default="", description="访问令牌"
        )

    Run: RunOptions = Field(default_factory=RunOptions, description="运行设置")
    users: ConfigCollection[Demo15UserConfig] = collection(Demo15UserConfig)


class TaskColumn(ConfigTableColumn):
    _table_key = "tasks"
    _table_transpose = True

    Enabled: bool = Field(default=True, description="启用任务")
    Count: int = Field(default=1, ge=0, description="执行次数")


class Demo15PlanConfig(PlanEntry):
    First: TaskColumn = Field(default_factory=TaskColumn, description="任务一")
    Second: TaskColumn = Field(default_factory=TaskColumn, description="任务二")


class Demo15View(ScriptViewWorker):
    async def main_logic(self) -> None:
        await self.expander.record_user_state(
            self.user_info, status="跳过", reason="示例仅用于配置编辑"
        )


class Demo15Expander(UserExpander):
    def build_worker(self, user, config) -> Demo15View:
        return Demo15View(expander=self, user=user, config=config)


class Demo15Plugin(ScriptAdapterPlugin):
    script_type_key = "Demo15"
    decl = ScriptTypeDecl(
        script_type=Demo15Config,
        user_type=Demo15UserConfig,
        plan_type=Demo15PlanConfig,
        expander_class=Demo15Expander,
        supported_modes=(TaskMode.SCRIPT_VIEW,),
        supports_game_binding=False,
    )


PLUGIN = Demo15Plugin
