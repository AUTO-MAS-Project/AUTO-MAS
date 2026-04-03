from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.plugins import on_event
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from app.core.plugins.context import PluginContext


class Plugin:
    """用于演示新生命周期协议与 on_event 装饰器的示例插件。"""

    def __init__(self, ctx: "PluginContext") -> None:
        """初始化插件上下文与缓存能力。

        Args:
            ctx (PluginContext): 插件上下文对象。

        Returns:
            None: 无返回值。
        """
        self.ctx = ctx
        self.cache = self.ctx.cache.register(
            cache_name="test_cache",
            backend="json",
            limit=10,
            limit_mode="count",
        )

    async def on_load(self, ctx: "PluginContext") -> None:
        """生命周期：加载完成后调用。

        Args:
            ctx (PluginContext): 当前插件上下文。

        Returns:
            None: 无返回值。
        """
        _ = ctx
        self.ctx.logger.info("[new_plugin] on_load 完成")

    async def on_start(self) -> None:
        """生命周期：实例进入运行态。

        Returns:
            None: 无返回值。

        Raises:
            ValueError: 当事件名或作用域参数不合法时由事件系统抛出。
            Exception: 当监听器在严格错误策略下失败时由事件系统透传。
        """
        await self.ctx.event.emit_async(
            "runtime.test",
            {"message": "Hello from instance runtime event!"},
            scope="instance",
        )
        await self.ctx.event.emit_async(
            "cache.test",
            {"key": "test_cache", "value": {"1": "2"}},
            scope="instance",
        )
        await self.ctx.event.emit_async(
            "demo.ping",
            {"message": "Hello from plugin event!"},
            scope="global",
        )
        await self.ctx.event.emit_async(
            "config.test", 
            {"from": "on_start"}, 
            scope="instance"
        )
        self.ctx.logger.info("[new_plugin] on_start 完成")

    async def on_stop(self, reason: str) -> None:
        """生命周期：实例停止前调用。

        Args:
            reason (str): 停止原因。

        Returns:
            None: 无返回值。
        """
        self.ctx.logger.info(f"[new_plugin] on_stop, reason={reason}")

    async def on_unload(self) -> None:
        """生命周期：实例卸载前调用。"""
        self.ctx.logger.info("[new_plugin] on_unload 完成")

    async def on_reload_prepare(self) -> None:
        """生命周期：重载准备阶段。"""
        self.ctx.logger.info("[new_plugin] on_reload_prepare")

    async def on_reload_commit(self) -> None:
        """生命周期：重载提交阶段。"""
        self.ctx.logger.info("[new_plugin] on_reload_commit")

    @on_event("demo.ping", scope="global", priority=10)
    async def on_ping(self, payload: dict, ctx: "PluginContext") -> None:
        """
        处理全局 `demo.ping` 事件。

        Args:
            payload (dict): 事件载荷。
            ctx (PluginContext): 插件上下文。

        Returns:
            None: 无返回值。
        """
        ctx.logger.info(f"收到 demo.ping: {payload}")

    @on_event("runtime.test", scope="instance")
    async def on_runtime_test(self, payload: dict, ctx: "PluginContext") -> None:
        """
        处理实例内 `runtime.test` 事件并执行 runtime 代码。

        Args:
            payload (dict): 事件载荷。
            ctx (PluginContext): 插件上下文。

        Returns:
            None: 无返回值。
        """
        ctx.logger.info(f"runtime.test 载荷: {payload}")
        code = "a=1; b=2; c=a+b; print(c)"
        result = await ctx.runtime.run(code=code, timeout_seconds=5)
        if result.get("ok"):
            ctx.logger.info(f"运行结果: {result.get('stdout', '').strip()}")
        else:
            ctx.logger.error(f"运行失败: {result.get('stderr', '').strip()}")

    @on_event("cache.test", scope="instance")
    def on_cache_test(self, payload: dict, ctx: "PluginContext") -> None:
        """
        处理实例内 `cache.test` 事件并写入缓存。

        Args:
            payload (dict): 事件载荷。
            ctx (PluginContext): 插件上下文。

        Returns:
            None: 无返回值。
        """
        value = payload.get("value", {"1": "2"})
        self.cache.set("test_cache", value)
        ctx.logger.info(f"缓存写入成功: {self.cache.get('test_cache')}")

    @on_event("config.test", scope="instance")
    def on_config_test(self, payload: dict, ctx: "PluginContext") -> None:
        """
        处理实例内 `config.test` 事件并打印配置。

        Args:
            payload (dict): 事件载荷。
            ctx (PluginContext): 插件上下文。

        Returns:
            None: 无返回值。
        """
        _ = payload
        ctx.logger.info(f"hello={ctx.config.get('hello')}")
        ctx.logger.info(f"hi={ctx.config.get('hi')}")


class Config(BaseModel):
    """示例插件配置模型。"""

    model_config = ConfigDict(extra="allow")

    hello: str = Field(default="world", description="示例配置项")
    hi: str = Field(default="worldworld", description="示例配置项示例配置项")
    hi2: int = Field(default=42, description="示例配置项示例配置项")