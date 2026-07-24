"""应用 API 路由注册。

保持主程序运行时与离线 OpenAPI 导出的路由集合一致，避免前端生成客户端
依赖启动完整后端、插件生命周期或真实设备环境。
"""

from __future__ import annotations

from fastapi import FastAPI


def register_application_routers(app: FastAPI) -> None:
    """注册 AUTO-MAS 的内建及核心插件 API 路由。"""
    from app.api import (
        core_router,
        dispatch_router,
        history_router,
        info_router,
        ocr_router,
        plugin_gateway_router,
        plugins_router,
        qr_login_router,
        setting_router,
        tools_router,
        update_router,
        ws_router,
    )
    from app.plugins.system import get_core_plugin_routers

    app.include_router(core_router)
    app.include_router(info_router)
    for core_plugin_router in get_core_plugin_routers():
        app.include_router(core_plugin_router)
    app.include_router(dispatch_router)
    app.include_router(history_router)
    app.include_router(tools_router)
    app.include_router(setting_router)
    app.include_router(update_router)
    app.include_router(ocr_router)
    app.include_router(ws_router)
    app.include_router(plugins_router)
    app.include_router(plugin_gateway_router)
    if qr_login_router is not None:
        app.include_router(qr_login_router)
