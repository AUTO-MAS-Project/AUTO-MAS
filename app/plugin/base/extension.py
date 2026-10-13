"""拓展插件基类。"""

from __future__ import annotations

from app.plugin.types import LifecycleContext, PluginState

from .plugin import BasePlugin


class ExtensionPlugin(BasePlugin):
    """由 Manager 统一调度系统适配阶段的扩展插件。"""

    async def system_enable(self) -> None:
        """预留扩展能力的系统登记。"""

    async def system_disable(self) -> None:
        """预留扩展能力的系统注销。"""

    async def system_rollback(
        self,
        during: PluginState,
        lifecycle_context: LifecycleContext,
        exc: BaseException,
    ) -> None:
        """预留扩展能力的系统回滚。

        Args:
            during: 真正出错的叶子操作过渡语义（如 ``ENABLING``/``DISABLING``）。
            lifecycle_context: Manager 从 ``PluginRecord.info.lifecycle_context``
                读出的快照（查对称回滚表）。
            exc: 触发失败分支的原异常。
        """
