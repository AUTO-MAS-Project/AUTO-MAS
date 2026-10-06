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
current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from app.utils import get_logger, sanitize_log_message

logger = get_logger("主程序")


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
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
        from app.core.plugin_manager import Plugin
        from app.api import (
            core_router,
            info_router,
            dispatch_router,
            history_router,
            tools_router,
            setting_router,
            update_router,
            ocr_router,
            plugin_router,
            i18n_router,
            queue_router,
            plan_router,
            scripts_router,
            games_router,
            qr_login_router,
        )
        from app.plugin import uv as uv_tool

        background_task = None
        _start_t = time.perf_counter()

        # ---- 路由注册（系统插件 API 须先于网关，避免 path 抢匹配）----
        app.include_router(core_router)
        app.include_router(info_router)
        app.include_router(dispatch_router)
        app.include_router(history_router)
        app.include_router(tools_router)
        app.include_router(setting_router)
        app.include_router(update_router)
        app.include_router(ocr_router)
        app.include_router(queue_router)
        app.include_router(plan_router)
        app.include_router(scripts_router)
        app.include_router(games_router)
        # 新插件系统：注册表/目录/自有配置/list/网关均在 plugin_router（网关最后挂）
        app.include_router(plugin_router)
        app.include_router(i18n_router)
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

        # ---- 核心初始化：引导配置 → 插件系统 → 领域配置 ----
        await Config.init_bootstrap_configs()

        if os.getenv("AUTO_MAS_DEV") == "1":
            import shutil
            plugins_dir = _Path.cwd() / "plugins"
            for pycache in plugins_dir.rglob("__pycache__"):
                if pycache.is_dir():
                    shutil.rmtree(pycache, ignore_errors=True)
            logger.debug("DEV 模式：已清理 plugins 目录下的 __pycache__")

        try:
            uv_tool.ensure()
        except Exception as exc:
            logger.error(
                f"uv 不可用: {exc}；请使用 AUTO-MAS-Runtime，或安装系统 uv: "
                "https://docs.astral.sh/uv/getting-started/installation/"
            )
            raise
        await Plugin.initialize()
        await Config.init_domain_configs()

        async def initialize_background_services() -> None:
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
                from app.core.history import history_store

                history_store.clean()

                # ArknightWin32 导入链含 pyautogui/cv2/numpy (约 700ms 重 CPU)，
                # 放入线程导入，避免阻塞事件循环影响 API 响应
                await asyncio.to_thread(
                    importlib.import_module, "app.MaaFW.ArknightWin32"
                )
                from app.MaaFW import ArknightWin32Toolkit
                from app.core.timer import MainTimer

                await ArknightWin32Toolkit.init()
                await MainTimer.start()

                if Config.setting.notify.if_koishi_support:
                    from app.api.ws_command import execute_ws_command
                    from app.utils.websocket import ws_client_manager

                    ws_client_manager.set_command_executor(execute_ws_command)
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

        async def shutdown_services() -> None:
            """完整的非 WS teardown，供 /close 与 lifespan 收尾共用（幂等）。"""

            from contextlib import suppress

            from app.core.plugin_manager import Plugin as PluginRuntime
            from app.core.task_dispatcher import TaskDispatcher
            from app.core.timer import MainTimer
            from app.core.ws import Dispatcher, MainConnection
            from app.runtime_tasks import RuntimeTasks
            from app.services import Matomo, System, Updater

            # 先停止仍在执行的后台初始化，避免它在 teardown 期间继续启动服务
            # （yield 前已必然创建 background_task，无需判空）
            if not background_task.done():
                background_task.cancel()
                with suppress(asyncio.CancelledError):
                    await background_task

            # 停止 WS 分发与连接后台任务，避免插件 teardown 期间仍处理入站消息
            await MainConnection.begin_shutdown()
            await Dispatcher.shutdown()
            await MainConnection.cancel_hook_tasks()

            # 取消待执行的电源操作（无任务在跑属正常）
            with suppress(RuntimeError):
                await System.cancel_power_task()

            await MainTimer.stop()
            await TaskDispatcher.stop("ALL")
            # 任务 final_task 可能在收尾时重新安排电源操作，停止后再次兜底取消。
            with suppress(RuntimeError):
                await System.cancel_power_task()
            await Updater.cancel_download(notify=False)
            await RuntimeTasks.shutdown()
            await PluginRuntime.shutdown()
            # 插件 on_teardown 可能已 commit；跳过防抖，全量落盘全部 file= 根
            from app.config import config_manager

            await config_manager.flush()
            await Matomo.close()
            logger.info("AUTO-MAS 后端服务清理完成")

        from app.core.lifecycle import ShutdownCoordinator

        ShutdownCoordinator.set_teardown(shutdown_services)
        try:
            yield
        finally:
            # 覆盖 taskkill 等未经 /close 的退出路径；已由 /close 执行过则跳过
            await ShutdownCoordinator.run_teardown()
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
        # 主 WebSocket 心跳依赖协议层 ping/pong，显式配置底层参数
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=36163,
            log_level="info",
            log_config=None,
            ws_ping_interval=20.0,
            ws_ping_timeout=20.0,
        )
        server = uvicorn.Server(config)

        from app.core import Config

        Config.server = server
        await server.serve()

    asyncio.run(run_server())


if __name__ == "__main__":
    main()
