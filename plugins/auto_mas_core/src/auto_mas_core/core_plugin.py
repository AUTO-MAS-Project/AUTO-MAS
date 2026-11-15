"""核心系统插件入口类（不可禁用）。

与 ``auto_mas_core.plugin`` 子包分离：后者暴露 Manager 上的 services/http。
"""

from __future__ import annotations

from app.plugin.base import BasePlugin


class CorePlugin(BasePlugin):
    """auto_mas_core 核心插件入口。"""

    async def on_enable(self) -> None:
        """完成 core SDK 插件的启用回调；基础能力由宿主提供，此处无需额外启动工作。"""
        return None

    async def on_disable(self) -> None:
        # 运行时 pre_disable 会拦截；此处防御
        """拒绝停用 core SDK 插件，保护其他插件依赖的基础能力。"""
        raise RuntimeError("核心插件不可禁用")
