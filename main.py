#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import os
import sys
import time
import ctypes
import logging
from pathlib import Path
from typing import Any

current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from app.utils import get_logger, sanitize_log_message

logger = get_logger("主程序")


class InterceptHandler(logging.Handler):
    def emit(self, record):
        # 获取对应 loguru 的 level
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        # 过滤敏感信息并转发日志
        sanitized_message = sanitize_log_message(record.getMessage())
        logger.opt(depth=6, exception=record.exc_info).log(level, sanitized_message)


# 拦截标准 logging
logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
    logging.getLogger(name).handlers = [InterceptHandler()]
    logging.getLogger(name).propagate = False


def is_admin() -> bool:
    """检查当前程序是否以管理员身份运行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:  # noqa: E722
        return False


@logger.catch
def main():
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, os.path.realpath(sys.argv[0]), None, 1
        )
        sys.exit(0)

    from app.plugins.uv_backend import ensure_uv

    if not ensure_uv():
        logger.error(
            "uv 包管理器安装失败，请手动安装: https://docs.astral.sh/uv/getting-started/installation/"
        )
        sys.exit(1)

    import asyncio
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """在 lifespan 内完成路由注册与核心初始化，确保 server.startup()
        能在极短时间内打印 "Uvicorn running"。
        """
        from fastapi.staticfiles import StaticFiles
        from pathlib import Path as _Path

        from app.core import Config
        from app.plugins import PluginManager
        from app.core.page_registry import register_builtin_pages
        from app.core.script_types import validate_script_type_registry
        from app.api import (
            core_router,
            info_router,
            dispatch_router,
            history_router,
            tools_router,
            setting_router,
            update_router,
            ocr_router,
            ws_router,
            plugins_router,
            plugin_gateway_router,
            qr_login_router,
            script_types_router,
        )
        from app.plugins.system import get_core_plugin_routers

        hmr_service: Any = None
        background_task = None
        _start_t = time.perf_counter()

        # ---- 路由注册 ----
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
        app.include_router(script_types_router)
        if qr_login_router is not None:
            app.include_router(qr_login_router)

        app.mount(
            "/api/res/materials",
            StaticFiles(directory=str(_Path.cwd() / "res/images/materials")),
            name="materials",
        )
        app.mount(
            "/api/res/sounds",
            StaticFiles(directory=str(_Path.cwd() / "res/sounds")),
            name="sounds",
        )

        # ---- 核心初始化 ----
        await Config.init_config()
        register_builtin_pages()

        if os.getenv("AUTO_MAS_DEV") == "1":
            import shutil
            plugins_dir = _Path.cwd() / "plugins"
            for pycache in plugins_dir.rglob("__pycache__"):
                if pycache.is_dir():
                    shutil.rmtree(pycache, ignore_errors=True)
            logger.debug("DEV 模式：已清理 plugins 目录下的 __pycache__")

        await PluginManager.start(fast_startup=False)

        missing_script_types = validate_script_type_registry(Config)
        if missing_script_types:
            raise RuntimeError(
                "脚本类型注册不完整，以下脚本未找到可用 provider: "
                + "; ".join(missing_script_types)
            )

        async def initialize_background_services() -> None:
            nonlocal hmr_service

            app.state.background_status = "running"
            try:
                import importlib

                # MCP 构建需要遍历完整 OpenAPI schema (约 1s)，后移到后台
                # 导入与构建均为重 CPU 操作，放入线程避免阻塞事件循环推迟 API 响应
                # Starlette 支持运行期追加路由，首个 /mcp 请求前挂载完成即可
                if os.getenv("AUTO_MAS_ENABLE_MCP", "1") == "1":
                    fastapi_mcp = await asyncio.to_thread(
                        importlib.import_module, "fastapi_mcp"
                    )

                    mcp = await asyncio.to_thread(
                        fastapi_mcp.FastApiMCP,
                        app,
                        name="AUTO-MAS MCP",
                        description="MCP server for AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software",
                        describe_full_response_schema=True,
                        describe_all_responses=True,
                        exclude_tags=["Delete"],
                    )
                    mcp.mount_http()
                    logger.info("MCP 服务已挂载")
                else:
                    logger.info("MCP 服务未启用，跳过路由挂载")

                await Config.get_stage()
                await Config.clean_old_history()

                # ArknightWin32 导入链含 pyautogui/cv2/numpy (约 700ms 重 CPU)，
                # 放入线程导入，避免阻塞事件循环影响 API 响应
                await asyncio.to_thread(
                    importlib.import_module, "app.MaaFW.ArknightWin32"
                )
                from app.MaaFW import ArknightWin32Toolkit
                from app.core.timer import MainTimer

                await ArknightWin32Toolkit.init()
                await MainTimer.start()
                await PluginManager._finish_background_install()

                if os.getenv("AUTO_MAS_DEV") == "1":
                    from app.plugins.dev_hmr import DevPluginHMR

                    hmr_service = DevPluginHMR(PluginManager)
                    hmr_service.start()

                if Config.get("Notify", "IfKoishiSupport"):
                    from app.utils.websocket import ws_client_manager

                    await ws_client_manager.init_system_client_koishi()

                app.state.background_status = "ready"
                logger.info(
                    f"后端完全就绪, 总耗时 {time.perf_counter() - _start_t:.2f}s"
                )
            except asyncio.CancelledError:
                app.state.background_status = "cancelled"
                raise
            except Exception as error:
                app.state.background_status = "failed"
                app.state.background_error = f"{type(error).__name__}: {error}"
                logger.exception(f"后台初始化失败: {app.state.background_error}")

        app.state.background_status = "starting"
        app.state.background_error = None
        logger.info(
            f"核心初始化完成, 耗时 {time.perf_counter() - _start_t:.2f}s"
        )
        background_task = asyncio.create_task(initialize_background_services())
        try:
            yield
        finally:
            if not background_task.done():
                background_task.cancel()
                try:
                    await background_task
                except asyncio.CancelledError:
                    pass

            from app.core.task_manager import TaskManager
            from app.core.timer import MainTimer

            if hmr_service is not None:
                await hmr_service.stop()

            await TaskManager.stop_task("ALL")
            await PluginManager.stop()
            await MainTimer.stop()

            from app.services import Matomo

            await Matomo.close()

            logger.info("AUTO-MAS 后端程序关闭")

    # ---- 极简 app 创建：无路由、无 MCP、无静态挂载 ----
    app = FastAPI(
        title="AUTO-MAS",
        description="API for managing automation scripts, plans, and tasks",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    async def run_server():
        config = uvicorn.Config(
            app, host="0.0.0.0", port=36163, log_level="info", log_config=None
        )
        server = uvicorn.Server(config)

        from app.core import Config

        Config.server = server
        await server.serve()

    asyncio.run(run_server())


if __name__ == "__main__":
    main()
