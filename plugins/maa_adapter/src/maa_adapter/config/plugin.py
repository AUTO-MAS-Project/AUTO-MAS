"""MAA 插件自己的关卡缓存，随插件配置持久化。"""

from datetime import datetime, timezone
from typing import Annotated

from auto_mas_core import ConfigGroup, JsonDictString, PluginConfig, UiVisibility, ui
from auto_mas_core.host.config import config_manager
from pydantic import Field

from maa_adapter.stages.service import MaaStageCache


class StageCacheFields(ConfigGroup):
    content: JsonDictString = Field(
        default="{}", description="MAA 官方多区服关卡资源原文"
    )
    etag: str = Field(default="", description="关卡资源条件请求标识")
    checked_at: datetime = Field(
        default_factory=lambda: datetime(2000, 1, 1, tzinfo=timezone.utc),
        description="上次成功检查关卡资源的 UTC 时间",
    )

    def snapshot(self) -> MaaStageCache:
        """读取已提交的关卡正文和条件请求元数据，供全部区服共享。"""
        return MaaStageCache(
            content=self.content, etag=self.etag, checked_at=self.checked_at
        )


class MaaPluginConfig(PluginConfig):
    stage_cache: Annotated[StageCacheFields, ui(visibility=UiVisibility.HIDE)] = Field(
        default_factory=StageCacheFields
    )

    async def store_stage_cache(
        self,
        *,
        checked_at: datetime,
        content: str | None = None,
        etag: str | None = None,
    ) -> None:
        """在同一事务保存成功检查的字段，304 响应保留正文及 ETag。"""
        async with config_manager.transaction():
            self.stage_cache.checked_at = checked_at
            if content is not None:
                self.stage_cache.content = content
            if etag is not None:
                self.stage_cache.etag = etag
            await self.commit()
