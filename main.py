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
import ctypes
import logging
from pathlib import Path

current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))
if __name__ == "__main__":
    os.chdir(current_dir)

from app.utils.platform import IS_WINDOWS
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
    if IS_WINDOWS:
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:  # noqa: E722
            return False
    return True

def restart_as_admin():
    """以管理员权限重启当前进程"""
    if IS_WINDOWS:
        executable = sys.executable.removesuffix('.exe')
        executable += '.exe'
        result = ctypes.windll.shell32.ShellExecuteW(
            None, 'runas', 'wt.exe', f'"{executable}" "{os.path.realpath(sys.argv[0])}"', None, 1)
        if result > 32:
            sys.exit(0)
        else:
            result = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", executable, os.path.realpath(sys.argv[0]), None, 1)
            sys.exit(result)


def is_development_environment() -> bool:
    """识别开发环境：前端传入的环境变量，或仓库根目录的 .env 标记文件。

    .env 不纳入版本库，模板见 .env.example；更新器也不会把它复制到
    用户安装目录，因此用户直接启动后端时仍按生产环境上报。
    """

    raw = str(os.getenv("AUTO_MAS_ENV", "")).strip().lower()
    if raw in {"dev", "development"}:
        return True

    return (current_dir / ".env").is_file()


def is_hosted_launch() -> bool:
    """识别由前端拉起的后端进程，此时提权由前端负责，无需自行提权。"""

    raw = str(os.getenv("AUTO_MAS_DEV", "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


@logger.catch
def main():
    development_environment = is_development_environment()
    if development_environment:
        os.environ["AUTO_MAS_ENV"] = "development"
    
    if not (is_admin() or is_hosted_launch() or development_environment):
        restart_as_admin()

    from app.core import Config
    from app.services.telemetry import (
        init_sentry,
        is_telemetry_enabled,
        resolve_sentry_dist,
    )
    # 开发环境不上报遥测数据
    init_sentry(
        release=Config.VERSION,
        development=development_environment,
        enabled=is_telemetry_enabled(current_dir / "config" / "Config.json"),
        dist=resolve_sentry_dist(current_dir),
    )

    import asyncio
    import uvicorn
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles
    from contextlib import asynccontextmanager, suppress

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from app.core import Config, MainTimer, TaskManager

        await Config.init_config()

        background_task: asyncio.Task | None = None

        async def initialize_background_services() -> None:
            """后台完成重活初始化：MCP 挂载、活动关卡、历史清理、ArknightWin32、主定时器。

            lifespan 提前 yield 后 uvicorn 立即打印 "Uvicorn running"，
            让前端等待就绪的耗时只包含核心配置初始化。
            """

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

                if IS_WINDOWS:
                    for adapter in (
                        "app.MaaFW.ArknightWin32",
                        "app.MaaFW.EndFieldPCWin32",
                    ):
                        await asyncio.to_thread(importlib.import_module, adapter)

                    from app.MaaFW.ArknightWin32 import ArknightWin32Toolkit

                    await ArknightWin32Toolkit.init()
                await MainTimer.start()

                # 初始化 Koishi 系统客户端（如果已启用）
                if Config.get("Notify", "IfKoishiSupport"):
                    from app.utils.websocket import ws_client_manager

                    await ws_client_manager.init_system_client_koishi()

                if (Path.cwd() / "AUTO-MAS-Setup.exe").exists():
                    try:
                        (Path.cwd() / "AUTO-MAS-Setup.exe").unlink()
                    except Exception as e:
                        logger.error(f"删除AUTO-MAS-Setup.exe失败: {e}")
                if (Path.cwd() / "AUTO_MAA.exe").exists():
                    try:
                        (Path.cwd() / "AUTO_MAA.exe").unlink()
                    except Exception as e:
                        logger.error(f"删除AUTO_MAA.exe失败: {e}")

                app.state.background_status = "ready"
                logger.info("后端后台初始化完成")
            except asyncio.CancelledError:
                app.state.background_status = "cancelled"
                raise
            except Exception as error:
                app.state.background_status = "failed"
                app.state.background_error = f"{type(error).__name__}: {error}"
                logger.exception(f"后台初始化失败: {app.state.background_error}")

        app.state.background_status = "starting"
        app.state.background_error = None
        background_task = asyncio.create_task(initialize_background_services())

        try:
            yield
        finally:
            # 停止仍在执行的后台初始化，避免它在 teardown 期间继续启动服务
            if background_task is not None and not background_task.done():
                background_task.cancel()
                with suppress(asyncio.CancelledError):
                    await background_task

            await TaskManager.stop_task("ALL")

            await MainTimer.stop()

            from app.services import Matomo

            await Matomo.close()

            logger.info("AUTO-MAS 后端程序关闭")

    from fastapi.middleware.cors import CORSMiddleware
    from app.api import (
        core_router,
        info_router,
        scripts_router,
        plan_router,
        emulator_router,
        queue_router,
        dispatch_router,
        history_router,
        tools_router,
        setting_router,
        update_router,
        ocr_router,
        ws_debug_router,
        qr_login_router,
    )

    app = FastAPI(
        title="AUTO-MAS",
        description="API for managing automation scripts, plans, and tasks",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 允许所有域名跨域访问
        allow_credentials=True,
        allow_methods=["*"],  # 允许所有请求方法, 如 GET、POST、PUT、DELETE
        allow_headers=["*"],  # 允许所有请求头
    )

    app.include_router(core_router)
    app.include_router(info_router)
    app.include_router(scripts_router)
    app.include_router(plan_router)
    app.include_router(emulator_router)
    app.include_router(queue_router)
    app.include_router(dispatch_router)
    app.include_router(history_router)
    app.include_router(tools_router)
    app.include_router(setting_router)
    app.include_router(update_router)
    app.include_router(ocr_router)
    app.include_router(ws_debug_router)

    # 可选补丁：米游社扫码登录
    if qr_login_router is not None:
        app.include_router(qr_login_router)

    app.mount(
        "/api/res/materials",
        StaticFiles(directory=str(Path.cwd() / "res/images/materials")),
        name="materials",
    )
    app.mount(
        "/api/res/sounds",
        StaticFiles(directory=str(Path.cwd() / "res/sounds")),
        name="sounds",
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
