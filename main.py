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

from app.utils import get_logger, sanitize_log_message
from app.core import Config
from app.services.telemetry import init_sentry, is_telemetry_enabled

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

    # 开发环境不上报遥测数据
    init_sentry(
        release=Config.VERSION,
        development=development_environment,
        enabled=is_telemetry_enabled(current_dir / "config" / "Config.json"),
    )

    if is_admin() or is_hosted_launch() or development_environment:
        import asyncio
        import uvicorn
        from fastapi import FastAPI
        from fastapi_mcp import FastApiMCP
        from fastapi.staticfiles import StaticFiles
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            from app.core import Config, MainTimer, TaskManager
            from app.MaaFW import ArknightWin32Toolkit

            await Config.init_config()
            await Config.get_stage()
            await Config.clean_old_history()
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

            yield

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

        mcp = FastApiMCP(
            app,
            name="AUTO-MAS MCP",
            description="MCP server for AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software",
            describe_full_response_schema=True,
            describe_all_responses=True,
            exclude_tags=["Delete"],
        )

        mcp.mount_http()

        async def run_server():
            config = uvicorn.Config(
                app, host="0.0.0.0", port=36163, log_level="info", log_config=None
            )
            server = uvicorn.Server(config)

            from app.core import Config

            Config.server = server
            await server.serve()

        asyncio.run(run_server())

    else:
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, os.path.realpath(sys.argv[0]), None, 1
        )
        sys.exit(0)


if __name__ == "__main__":
    main()
