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


import ctypes
import logging
import os
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))
if __name__ == "__main__" and os.getenv("AUTO_MAS_SUPERVISED") != "1":
    # 受监督时由监督器决定工作目录（app-root），源码在 repo/ 子目录，不能 chdir 进去；
    # 判据与 app.utils.is_supervised() 相同，此处不能先导入 app.utils（见下方
    # app.utils.logger 会在导入时以 Path.cwd() 建 debug/ 目录，导入必须留在 chdir 之后）
    os.chdir(current_dir)

from app.utils import (  # noqa: E402
    get_logger,
    is_supervised,
    resource_path,
    sanitize_log_message,
)
from app.utils.platform import IS_WINDOWS, is_admin  # noqa: E402

logger = get_logger("主程序")

# 清理启动链路（Runtime → uv run → 后端）注入的 Python/uv 环境变量。MAS 自身
# 不消费它们，但进程环境会原样传给所有被 MAS 拉起的子进程（专项脚本启动器、
# 提权 ShellExecute 等）：外部脚本自己的 uv/pip 会把环境解析到 MAS 的 runtime
# venv 上、甚至尝试删除该目录（曾导致 ZzzOd 启动器报「运行环境同步失败」并
# 损坏 venv）。uv run 实际注入 VIRTUAL_ENV、UV_PROJECT_ENVIRONMENT、UV、
# UV_RUN_RECURSION_DEPTH 与 PATH 前置 <venv>/Scripts 五样，逐一摘除
_leaked_venv = os.environ.pop("VIRTUAL_ENV", None)
for _leaked_env in ("UV", "UV_PROJECT_ENVIRONMENT", "UV_RUN_RECURSION_DEPTH"):
    os.environ.pop(_leaked_env, None)
if _leaked_venv is not None:
    logger.info(f"已清理启动链路注入的环境变量: VIRTUAL_ENV={_leaked_venv}")
    # <venv>/Scripts（内含 python.exe/pip.exe）插在 PATH 里不摘的话，任何经
    # PATH 裸调 python/pip 的子进程都会命中 MAS 的 runtime venv；按该值精确
    # 摘除对应段，PATH 其余内容不动
    _venv_scripts = os.path.normcase(
        os.path.join(_leaked_venv, "Scripts" if os.name == "nt" else "bin").rstrip(
            "\\/"
        )
    )
    _path_entries = os.environ.get("PATH", "").split(os.pathsep)
    _kept_entries = [
        _entry
        for _entry in _path_entries
        if os.path.normcase(_entry.rstrip("\\/")) != _venv_scripts
    ]
    if _kept_entries != _path_entries:
        os.environ["PATH"] = os.pathsep.join(_kept_entries)
        logger.info(f"已从 PATH 摘除启动链路注入的段: {_venv_scripts}")

# 正式版固定端口；开发环境错开一位，避免与用户已装正式版抢占同一端口
DEFAULT_HTTP_PORT = 36163
DEV_HTTP_PORT = 36164
# 受 AUTO-MAS-Runtime 监督时由监督器注入的监听端口；受监督时只认它
SUPERVISED_PORT_ENV = "AUTO_MAS_SUPERVISED_PORT"
SUPERVISED_PORT_MIN = 1024
# /api/core/health 里后台初始化失败项的长度上限：Runtime 拒收超过 64 KiB 的健康响应正文，
# 单条异常信息与失败项条数都要封顶
BACKGROUND_ERROR_MESSAGE_MAX = 300
BACKGROUND_WARNINGS_MAX = 20


class InterceptHandler(logging.Handler):
    def emit(self, record):
        # 获取对应 loguru 的 level
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        # 访问日志降到 DEBUG: 不进 app.log (INFO), 开发时 stderr (DEBUG) 仍可见
        if record.name == "uvicorn.access":
            level = "DEBUG"
        # 过滤敏感信息并转发日志
        sanitized_message = sanitize_log_message(record.getMessage())
        logger.opt(depth=6, exception=record.exc_info).log(level, sanitized_message)


# 拦截标准 logging
logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
    logging.getLogger(name).handlers = [InterceptHandler()]
    logging.getLogger(name).propagate = False


def restart_as_admin():
    """以管理员权限重启当前进程"""
    if IS_WINDOWS:
        executable = sys.executable.removesuffix(".exe")
        executable += ".exe"
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            "wt.exe",
            f'"{executable}" "{os.path.realpath(sys.argv[0])}"',
            None,
            1,
        )
        if result > 32:
            sys.exit(0)
        else:
            result = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", executable, os.path.realpath(sys.argv[0]), None, 1
            )
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


def should_restart_as_admin(
    *,
    supervised: bool,
    admin: bool,
    hosted_launch: bool,
    development_environment: bool,
) -> bool:
    """判断是否需要以管理员身份重启当前进程。

    抽成纯函数便于单独测试：restart_as_admin() 会 ShellExecuteW("runas", ...)
    拉起新进程再退出当前进程，若在受 AUTO-MAS-Runtime 监督（Windows Job Object
    托管进程树）下这么做，新进程会脱离 Job Object，监督器看到旧进程退出即判定
    后端已结束，因此受监督时优先级最高、永远不重启；其余情况维持既有判据。
    """

    if supervised:
        return False
    return not (admin or hosted_launch or development_environment)


def resolve_http_port(development_environment: bool) -> int:
    """解析 HTTP/WS 监听端口，让开发环境与用户安装的正式版可以同时运行。

    正式版保持 36163 不变；开发环境默认改用 36164，因此源码调试不会再抢占
    用户已装正式版的端口。前端拉起后端时会注入 AUTO_MAS_HTTP_PORT，保证两侧
    始终对齐同一个端口。

    受 AUTO-MAS-Runtime 监督时只认监督器注入的 AUTO_MAS_SUPERVISED_PORT：
    监督器按实例类型自行选定端口（managed 缺省 36163、development 缺省 36164）
    并据此做健康检查与关闭请求。后端若钉死 36163，受监督的开发版就会撞上同机
    正在运行的正式版。该变量缺失或非法时回退 36163 并记 warning；.env、
    AUTO_MAS_HTTP_PORT 与开发环境判据在受监督时一律忽略，优先级低于注入值。

    Args:
        development_environment: 当前是否为开发环境。

    Returns:
        实际用于监听的端口号。
    """

    raw = str(os.getenv("AUTO_MAS_HTTP_PORT", "")).strip()

    if is_supervised():
        if raw:
            logger.info(
                f"受监督模式下端口由运行时注入，已忽略 AUTO_MAS_HTTP_PORT={raw}"
            )
        return _resolve_supervised_port()

    if raw:
        try:
            port = int(raw)
        except ValueError:
            port = 0
        if 1 <= port <= 65535:
            return port
        logger.warning(f"AUTO_MAS_HTTP_PORT 取值无效，已忽略: {raw}")

    return DEV_HTTP_PORT if development_environment else DEFAULT_HTTP_PORT


def _resolve_supervised_port() -> int:
    """读取 Runtime 注入的 AUTO_MAS_SUPERVISED_PORT；缺失或非法时回退 36163。"""

    raw = os.getenv(SUPERVISED_PORT_ENV)
    if raw is None:
        logger.warning(
            f"受监督模式下未注入 {SUPERVISED_PORT_ENV}，回退 {DEFAULT_HTTP_PORT}"
        )
        return DEFAULT_HTTP_PORT

    try:
        port = int(str(raw).strip())
    except ValueError:
        port = 0
    if SUPERVISED_PORT_MIN <= port <= 65535:
        return port

    logger.warning(f"{SUPERVISED_PORT_ENV} 取值无效，回退 {DEFAULT_HTTP_PORT}: {raw!r}")
    return DEFAULT_HTTP_PORT


# ? init_config / ConfigBase ??????????????? .git/codex-backups?
@logger.catch
def main():
    development_environment = is_development_environment()
    if development_environment:
        os.environ["AUTO_MAS_ENV"] = "development"

    supervised = is_supervised()
    admin = is_admin()
    if should_restart_as_admin(
        supervised=supervised,
        admin=admin,
        hosted_launch=is_hosted_launch(),
        development_environment=development_environment,
    ):
        restart_as_admin()
    elif supervised and not admin:
        logger.warning(
            "受监督模式下不自行提权，当前非管理员，依赖模拟器/窗口操作的功能可能受限"
        )

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
            openclaw_qq_router,
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
        app.include_router(openclaw_qq_router)
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

                from app.core.timer import MainTimer
                from app.core.desktop_guard import DesktopGuard

                # ArknightWin32 暂不接入新配置系统；保留源码供后续迁移参考。
                await MainTimer.start()
                await DesktopGuard.start()

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
            from app.core.desktop_guard import DesktopGuard
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
            await DesktopGuard.stop()
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
            port=resolve_http_port(development_environment),
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
