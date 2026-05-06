#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2026 AUTO-MAS Team

from __future__ import annotations


from .context import PluginContext


class PluginLifecycle:
    """插件生命周期协议基类。

    新协议要求插件模块导出 `Plugin` 类，默认采用“最小必选 + 高级可选”：
    - 必选：on_start()、on_stop(reason)
    - 可选：on_load(ctx)、on_unload()、on_reload_prepare()、on_reload_commit()

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
        """生命周期（可选）：代码加载后、启动前。"""
        _ = ctx

    async def on_start(self) -> None:
        """生命周期（必选）：实例进入运行态。"""
        raise NotImplementedError

    async def on_stop(self, reason: str) -> None:
        """生命周期（必选）：实例准备停止。"""
        _ = reason
        raise NotImplementedError

    async def on_unload(self) -> None:
        """生命周期（可选）：实例已停止并即将卸载。"""

    async def on_reload_prepare(self) -> None:
        """生命周期（可选）：热重载开始前的准备阶段。"""

    async def on_reload_commit(self) -> None:
        """生命周期（可选）：热重载提交完成。"""


REQUIRED_LIFECYCLE_METHODS: tuple[str, ...] = (
    "on_start",
    "on_stop",
)
"""插件类必须实现的生命周期方法名集合。"""


OPTIONAL_LIFECYCLE_METHODS: tuple[str, ...] = (
    "on_load",
    "on_unload",
    "on_reload_prepare",
    "on_reload_commit",
)
"""插件类可选实现的生命周期方法名集合。"""
