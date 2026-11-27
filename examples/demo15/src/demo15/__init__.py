"""使用宿主 SDK 声明托管、账号和计划。"""

import json
from pathlib import Path
from typing import Annotated, Literal

from auto_mas_core import (
    ConfigCollection,
    ConfigGroup,
    ConfigRestorePool,
    ConfigTableColumn,
    FrontendManifest,
    FrontendPlanCreation,
    FrontendSurface,
    FrontendTarget,
    OptionHint,
    PlanEntry,
    RestoreContext,
    ScriptAdapterPlugin,
    ScriptEntry,
    ScriptRootPath,
    ScriptTypeDecl,
    ScriptViewWorker,
    TaskMode,
    Trigger,
    UiSection,
    UiStep,
    UiVisibility,
    UserEntry,
    UserExpander,
    collection,
    encrypted,
    plugin_route,
    select,
    trigger_field,
    ui,
    ui_visibility,
)
from auto_mas_core.host.utils_common_config import archive
from fastapi import Request
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
    ui_steps = (UiStep("env", "环境"), UiStep("run", "运行"))
    ui_sections = {
        "group:Info": UiSection(step="env"),
        "group:Setup": UiSection(step="env"),
        "group:Run": UiSection(step="run", collapsible=True, default_collapsed=True),
    }
    ui_native_session = "view"

    class Environment(ConfigGroup):
        Path: Annotated[ScriptRootPath, ui(action_ref="Info.DiscoverPath")] = Field(
            default=None, description="示例包目录"
        )
        DiscoverPath: Trigger = Field(default=None, description="定位示例包目录")

    class SetupOptions(ConfigGroup):
        Region: Literal["cn", "global"] = Field(default="cn", description="区域")
        Profile: Annotated[
            str, select(option_source="profiles", depends_on={"region": "Setup.Region"})
        ] = Field(default="", description="区域配置")

    class RunOptions(ConfigGroup):
        Retries: int = Field(default=0, ge=0, description="重试次数")
        Mode: Literal["once", "repeat"] = Field(default="once", description="执行方式")
        Token: Annotated[str, ui(visibility=UiVisibility.MASKED), encrypted()] = Field(
            default="", description="访问令牌"
        )

    Info: Environment = Field(default_factory=Environment, description="环境路径")
    Setup: SetupOptions = Field(default_factory=SetupOptions, description="区域设置")
    Run: RunOptions = Field(default_factory=RunOptions, description="运行设置")
    users: ConfigCollection[Demo15UserConfig] = collection(Demo15UserConfig)

    @trigger_field("Info.DiscoverPath")
    async def discover_path(self) -> None:
        self.Info.Path = Path(__file__).resolve().parent
        await self.commit()


async def run_files(ctx: RestoreContext) -> dict[str, str]:
    run = ctx.script_config.Run
    return {"run.json": json.dumps({"Mode": run.Mode, "Retries": run.Retries})}


async def run_backup_root(ctx: RestoreContext) -> Path:
    return ctx.config.data_path / ctx.script_id / "backups" / "run"


async def restore_run(ctx: RestoreContext, ts: str) -> None:
    root = await run_backup_root(ctx)
    directory = archive.get_backup_dir(root, ts)
    if directory is None:
        raise ValueError(f"备份不存在: {ts}")
    run = json.loads(archive.read_backup_text(directory, "run.json")["content"])
    if not isinstance(run, dict) or run.keys() != {"Mode", "Retries"}:
        raise ValueError("run.json 须且仅能包含 Mode 和 Retries")
    archive.archive_files(await run_files(ctx), root, force=True)
    await ctx.config.update_script(ctx.script_id, data={"Run": run})


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
    frontend = FrontendManifest(
        static_dir="ui",
        assets=("plan.html", "plan.css", "plan.js", "plan.svg"),
        targets=(
            FrontendTarget(
                script_key=script_type_key,
                script_config_type="Demo15Config",
                plan_config_type="Demo15PlanConfig",
                plan_creation=FrontendPlanCreation(key="Demo15PlanConfig"),
                surfaces={"plan": FrontendSurface(mode="wheel", entry="plan.html")},
            ),
        ),
    )
    decl = ScriptTypeDecl(
        script_type=Demo15Config,
        user_type=Demo15UserConfig,
        plan_type=Demo15PlanConfig,
        expander_class=Demo15Expander,
        supported_modes=(TaskMode.SCRIPT_VIEW,),
        supports_game_binding=False,
        restore_pools=(
            ConfigRestorePool(
                key="run",
                kind="script",
                editor_scope="script",
                files=run_files,
                backup_root=run_backup_root,
                restore=restore_run,
            ),
        ),
        first_account_mode="wizard",
    )

    @plugin_route("/options/profiles")
    def profiles(self, request: Request) -> dict:
        options: dict[str, list[OptionHint]] = {
            "cn": [
                {"value": "cn-main", "label": "国服主线"},
                {"value": "cn-daily", "label": "国服日常"},
            ],
            "global": [
                {"value": "global-main", "label": "国际服主线"},
                {"value": "global-daily", "label": "国际服日常"},
            ],
        }
        return {
            "code": 200,
            "status": "success",
            "message": "ok",
            "data": options.get(request.query_params.get("region", ""), []),
        }


PLUGIN = Demo15Plugin
