"""拓展插件基类。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from app.config import ConfigNode
from app.plugin.types import LifecycleContext, PluginState

from .plugin import BasePlugin


class AdapterRuntime(Protocol):
    """宿主注入的适配登记能力，不暴露全局配置或插件管理器。"""

    def instances(self) -> Iterable[ConfigNode]: ...

    def precheck_locks(self) -> None: ...

    async def system_enable(self) -> None: ...

    async def system_disable(self) -> None: ...

    async def system_rollback(
        self,
        during: PluginState,
        lifecycle_context: LifecycleContext,
        exc: BaseException,
    ) -> None: ...


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


class _AdapterPlugin(ExtensionPlugin):
    """保留适配器生命周期入口，系统操作交给宿主绑定实现。"""

    _adapter_runtime: AdapterRuntime

    def bind_runtime(self, runtime: AdapterRuntime) -> None:
        self._adapter_runtime = runtime

    def instances(self) -> Iterable[ConfigNode]:
        """返回本适配器拥有的配置实例。"""
        return self._adapter_runtime.instances()

    def precheck_locks(self) -> None:
        self._adapter_runtime.precheck_locks()

    async def system_enable(self) -> None:
        await self._adapter_runtime.system_enable()

    async def system_disable(self) -> None:
        await self._adapter_runtime.system_disable()

    async def system_rollback(
        self,
        during: PluginState,
        lifecycle_context: LifecycleContext,
        exc: BaseException,
    ) -> None:
        await self._adapter_runtime.system_rollback(
            during=during, lifecycle_context=lifecycle_context, exc=exc
        )
