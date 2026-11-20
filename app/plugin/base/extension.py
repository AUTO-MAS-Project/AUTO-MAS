"""拓展插件基类。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from app.config import ConfigNode
from app.plugin.types import LifecycleContext, PluginState

from .plugin import BasePlugin


class AdapterRuntime(Protocol):
    """宿主注入的适配登记能力，不暴露全局配置或插件管理器。"""

    def instances(self) -> Iterable[ConfigNode]:
        """提供当前适配声明对应的配置实例，供插件生命周期遍历和清理。"""
        ...

    def precheck_locks(self) -> None:
        """检查适配实例的配置锁是否允许当前生命周期操作，存在占用时阻止继续。"""
        ...

    async def system_enable(self) -> None:
        """将适配器声明和配置实例接入宿主系统，完成插件业务启用前的公共接线。"""
        ...

    async def system_disable(self) -> None:
        """撤销适配器在宿主中的配置与类型接线，按生命周期上下文处理实例身份。"""
        ...

    async def system_rollback(
        self,
        during: PluginState,
        lifecycle_context: LifecycleContext,
        exc: BaseException,
    ) -> None:
        """按失败阶段、生命周期上下文和异常信息恢复宿主注册状态。"""
        ...


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
        """绑定宿主提供的适配运行时，让插件基类通过统一协议调用宿主接线能力。"""
        self._adapter_runtime = runtime

    def instances(self) -> Iterable[ConfigNode]:
        """返回本适配器拥有的配置实例。"""
        return self._adapter_runtime.instances()

    def precheck_locks(self) -> None:
        """委托适配运行时检查配置占用，防止生命周期操作破坏执行中的任务。"""
        self._adapter_runtime.precheck_locks()

    async def system_enable(self) -> None:
        """委托适配运行时将当前专项声明注册到宿主系统。"""
        await self._adapter_runtime.system_enable()

    async def system_disable(self) -> None:
        """委托适配运行时撤销当前专项的宿主注册与配置接线。"""
        await self._adapter_runtime.system_disable()

    async def system_rollback(
        self,
        during: PluginState,
        lifecycle_context: LifecycleContext,
        exc: BaseException,
    ) -> None:
        """将生命周期失败的阶段和原因交给适配运行时，恢复此前的宿主接线。"""
        await self._adapter_runtime.system_rollback(
            during=during, lifecycle_context=lifecycle_context, exc=exc
        )
