#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2026 AUTO-MAS Team

from __future__ import annotations

from typing import Any

from .context import PluginContext


class PluginLifecycle:
    """插件生命周期协议基类。

    新协议要求插件模块导出 `Plugin` 类，并实现以下异步生命周期方法：
    - on_load(ctx)
    - on_start()
    - on_stop(reason)
    - on_unload()
    - on_reload_prepare()
    - on_reload_commit()
    - on_reload_rollback(error)

    说明：
    - 本基类仅用于协议声明与开发提示，不强制继承。
    - 加载器会以反射方式校验方法是否存在且可调用。
    """

    def __init__(self, ctx: PluginContext) -> None:
        """初始化插件实例。

        Args:
            ctx (PluginContext): 插件上下文对象。

        Returns:
            None: 无返回值。
        """
        self.ctx = ctx

    async def on_load(self, ctx: PluginContext) -> None:
        """生命周期：代码加载后、启动前。"""
        raise NotImplementedError

    async def on_start(self) -> None:
        """生命周期：实例进入运行态。"""
        raise NotImplementedError

    async def on_stop(self, reason: str) -> None:
        """生命周期：实例准备停止。"""
        raise NotImplementedError

    async def on_unload(self) -> None:
        """生命周期：实例已停止并即将卸载。"""
        raise NotImplementedError

    async def on_reload_prepare(self) -> None:
        """生命周期：热重载开始前的准备阶段。"""
        raise NotImplementedError

    async def on_reload_commit(self) -> None:
        """生命周期：热重载提交完成。"""
        raise NotImplementedError

    async def on_reload_rollback(self, error: Exception) -> None:
        """生命周期：热重载失败后的回滚阶段。"""
        raise NotImplementedError


REQUIRED_LIFECYCLE_METHODS: tuple[str, ...] = (
    "on_load",
    "on_start",
    "on_stop",
    "on_unload",
    "on_reload_prepare",
    "on_reload_commit",
    "on_reload_rollback",
)
"""插件类必须实现的生命周期方法名集合。"""
