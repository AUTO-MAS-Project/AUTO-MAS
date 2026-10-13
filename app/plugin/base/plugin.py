"""插件开发者通用基类。"""

from __future__ import annotations

import weakref
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar, Mapping

from app.plugin.types import LifecycleContext, PluginState

if TYPE_CHECKING:
    from app.models.config import PluginConfig, PluginRecord


class BasePlugin:
    """所有插件共享的业务生命周期契约。"""

    requires: ClassVar[tuple[str, ...]] = ()
    wants: ClassVar[tuple[str, ...]] = ()
    provides_services: ClassVar[Mapping[str, str]] = MappingProxyType({})
    config_class: ClassVar[type[PluginConfig] | None] = None

    def __init__(
        self, config: PluginConfig | None = None, record: PluginRecord | None = None
    ) -> None:
        # 仅 enable 时由 Manager 构造注入；load 阶段不建实例。
        # record 只存弱引用，避免与 PluginRecord._plugin 形成不可回收环。
        self.config = config
        self._record_ref: weakref.ReferenceType[PluginRecord] | None = (
            weakref.ref(record) if record is not None else None
        )

    @property
    def record(self) -> PluginRecord:
        """注册表项；未注入或已回收则上抛（实例只在注册项存活期内有用）。"""
        ref = self._record_ref
        record = ref() if ref is not None else None
        if record is None:
            raise RuntimeError("插件注册表项已回收")
        return record

    @property
    def lifecycle_context(self) -> LifecycleContext:
        """读 record 上的语境。"""
        return self.record.info.lifecycle_context

    @property
    def plugin_name(self) -> str:
        """注册名；服务 owner 仍由 Manager 用 record 填写。"""
        return self.record.info.plugin_name or type(self).__name__

    async def pre_enable(self) -> None:
        """启用前的业务预检。"""

    async def pre_reload(self) -> None:
        """重载前的业务预检。"""

    async def pre_disable(self) -> None:
        """禁用前的业务预检。"""

    async def pre_unload(self) -> None:
        """卸载前的业务预检。"""

    async def on_enable(self) -> None:
        """启用业务资源。"""

    async def on_reload(self) -> None:
        """重载业务资源（换类前打旧实例；不能替代 on_disable/on_enable）。"""

    async def on_disable(self) -> None:
        """释放启用期间创建的业务资源。"""

    async def on_unload(self) -> None:
        """释放卸载期间的业务资源。"""

    async def on_teardown(self) -> None:
        """进程退出时的业务收尾，不替代 ``on_disable``。"""

    async def on_fail_cleanup(
        self,
        during: PluginState,
        lifecycle_context: LifecycleContext,
        exc: BaseException,
    ) -> None:
        """生命周期失败后的业务资源清理。

        Args:
            during: 真正出错的叶子操作过渡语义（如 ``ENABLING``/``DISABLING``），
                与展示用 ``info.state``（内嵌时可仍为父 ××中）解耦。
            lifecycle_context: Manager 从 ``PluginRecord.info.lifecycle_context``
                读出的快照（唯一真相源）。
            exc: 触发失败分支的原异常。
        """
