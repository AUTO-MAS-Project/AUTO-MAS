"""MAA 专项完整插件声明；模拟器复用宿主，游戏管理仍由宿主负责。"""

from datetime import datetime, timezone

from auto_mas_core import Config, ScriptAdapterPlugin, ScriptTypeDecl, TaskMode
from fastapi import APIRouter

from maa_adapter.api import router as maa_router
from maa_adapter.api.backup import router as backup_router
from maa_adapter.api.stages import router as stage_router
from maa_adapter.config.plan import MaaPlanConfig
from maa_adapter.config.plugin import MaaPluginConfig
from maa_adapter.config.script import MaaConfig
from maa_adapter.config.user import MaaUserConfig
from maa_adapter.stages import fetch_stage
from maa_adapter.stages.service import MaaStageService
from maa_adapter.tasks.manager import MaaManager
from maa_adapter.updates.prefetch import check_prefetch

router = APIRouter()
router.include_router(maa_router, prefix="/api/scripts", tags=["脚本管理"])
router.include_router(stage_router)
router.include_router(backup_router)


class Plugin(ScriptAdapterPlugin):
    config_class = MaaPluginConfig
    script_type_key = "MAA"
    api_router = router
    provides_services = {
        "arknights.stage_info": "stage_info",
        "arknights.stage_data": "stage_data",
        "arknights.stage_overview": "stage_overview",
    }
    decl = ScriptTypeDecl(
        script_type=MaaConfig,
        user_type=MaaUserConfig,
        expander_class=MaaManager,
        plan_type=MaaPlanConfig,
        supported_modes=(
            TaskMode.AUTO_PROXY,
            TaskMode.SCRIPT_CONFIG,
            TaskMode.SCRIPT_VIEW,
        ),
        prefetch_check=check_prefetch,
        activity_game="arknights",
    )

    async def pre_enable(self):
        """领域配置激活前绑定 MAA 使用的关联集合，使历史配置引用原样恢复。"""
        refs = {
            "PlanConfig": Config.PlanConfig,
            "EmulatorConfig": Config.EmulatorConfig,
        }
        MaaConfig.related_config = refs
        MaaUserConfig.related_config = refs

    async def on_enable(self):
        """启用时绑定本插件配置缓存，并在发布 HTTP 和业务服务前首次获取关卡资源。"""
        assert isinstance(self.config, MaaPluginConfig)
        self.stage_service = MaaStageService(
            read_cache=self.config.stage_cache.snapshot,
            write_cache=self.config.store_stage_cache,
            fetch=fetch_stage,
            now=lambda: datetime.now(timezone.utc),
            background_tasks=self.background_tasks,
        )
        await self.stage_service.get_stage(refresh=True)

    async def stage_data(self, *, refresh=False):
        """检查并提供本插件缓存的官方资源，不再读取宿主全局设置。"""
        await self.stage_service.get_stage(refresh=refresh)
        assert isinstance(self.config, MaaPluginConfig)
        return self.config.stage_cache.content

    async def stage_info(self, kind, *, server="Official"):
        """向宿主下拉框提供官方关卡资源，所有调用共享插件内的缓存与刷新任务。"""
        return await self.stage_service.get_stage_info(kind, server=server)

    async def stage_overview(self, *, refresh=False):
        """向宿主首页提供各服务器活动概览，主动刷新仅由调用方请求时执行。"""
        if refresh:
            await self.stage_service.get_stage(refresh=True)
        return {
            server: await self.stage_service.get_stage_info("Info", server=server)
            for server in (
                "Official",
                "Bilibili",
                "YoStarEN",
                "YoStarJP",
                "YoStarKR",
                "txwy",
            )
        }
