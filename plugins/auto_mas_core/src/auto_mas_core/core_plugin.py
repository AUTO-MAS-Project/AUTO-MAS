"""核心系统插件入口类（不可禁用）。

与 ``auto_mas_core.plugin`` 子包分离：后者暴露 Manager 上的 services/http。
"""

from __future__ import annotations

from app.plugin.base import BasePlugin


class CorePlugin(BasePlugin):
    """auto_mas_core 核心插件入口。"""

    async def on_enable(self) -> None:
        return None

    async def on_disable(self) -> None:
        # 运行时 pre_disable 会拦截；此处防御
        raise RuntimeError("核心插件不可禁用")
