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
import json
import logging
import socket
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from app.utils import get_logger, sanitize_log_message
from app.utils.ws_limits import (
    DEFAULT_WS_MAX_MESSAGE_BYTES,
    DEFAULT_WS_QUEUE_MESSAGES,
)

logger = get_logger("主程序")

UVICORN_WS_PING_INTERVAL_SECONDS = 20.0
UVICORN_WS_PING_TIMEOUT_SECONDS = 20.0
UVICORN_WS_MAX_MESSAGE_BYTES = DEFAULT_WS_MAX_MESSAGE_BYTES
UVICORN_WS_MAX_QUEUE_MESSAGES = DEFAULT_WS_QUEUE_MESSAGES


def prepare_configuration_startup(config_dir: Path) -> None:
    """Upgrade legacy data, freeze legacy bytes, reject unsupported modes.

    Ordering contract: the standalone v1.7->v1.11 upgrade must complete
    before ``ensure_legacy_original_snapshot`` freezes the roots (the
    snapshot stays fail-closed on pre-v1.11 data), and both run before any
    Config import so no legacy ``AppConfig`` graph is ever constructed.
    """
    from app.configuration import assert_config_v2_startup_mode_ready
    from app.configuration.compat import (
        ensure_legacy_original_snapshot,
        upgrade_legacy_data,
    )

    upgrade_result = upgrade_legacy_data(config_dir.parent)
    if upgrade_result.performed:
        logger.info(
            "旧版用户数据已升级: "
            f"{upgrade_result.from_version} -> {upgrade_result.to_version} "
            f"({', '.join(upgrade_result.steps)})"
        )
    ensure_legacy_original_snapshot(config_dir)
    assert_config_v2_startup_mode_ready()


def build_uvicorn_config(uvicorn_module: Any, app: Any) -> Any:
    """Build the local server configuration with protocol-level WS liveness."""
    return uvicorn_module.Config(
        app,
        host="127.0.0.1",
        port=36163,
        log_level="info",
        log_config=None,
        ws_max_size=UVICORN_WS_MAX_MESSAGE_BYTES,
        ws_max_queue=UVICORN_WS_MAX_QUEUE_MESSAGES,
        ws_ping_interval=UVICORN_WS_PING_INTERVAL_SECONDS,
        ws_ping_timeout=UVICORN_WS_PING_TIMEOUT_SECONDS,
    )


class PortOccupiedError(RuntimeError):
    """端口被占用且不可安全复用时抛出。

    Attributes:
        host: 目标主机。
        port: 目标端口。
        classification: 端口占用分类（auto_mas / dev_backend / http / tcp_non_http）。
    """

    def __init__(self, host: str, port: int, classification: str) -> None:
        self.host = host
        self.port = port
        self.classification = classification
        super().__init__(
            f"端口 {host}:{port} 已被占用 (分类: {classification})；"
            f"请释放占用或确认是否有另一个 AUTO-MAS 实例正在运行。"
        )


def probe_local_port(host: str, port: int) -> str:
    """在 bind 前确定性分类端口占用情况。

    分类语义：
        - ``free``：端口空闲，可安全 bind。
        - ``auto_mas``：被另一个 AUTO-MAS 后端占用（响应 /api/core/ws_meta 且 devMode 为 false）。
        - ``dev_backend``：被 AUTO-MAS dev 后端占用（响应 /api/core/ws_meta 且 devMode 为 true）。
        - ``http``：被其他 HTTP 服务占用。
        - ``tcp_non_http``：被纯 TCP 服务占用（accept 但不返回 HTTP）。

    Args:
        host: 目标主机。
        port: 目标端口。

    Returns:
        str: 上述分类字符串之一。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe_sock:
        probe_sock.settimeout(0.5)
        try:
            probe_sock.connect((host, port))
        except OSError:
            return "free"

        try:
            probe_sock.settimeout(0.5)
            probe_sock.sendall(
                f"GET /api/core/ws_meta HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                f"Connection: close\r\n\r\n".encode("latin-1")
            )
            response = b""
            while len(response) < 8192:
                try:
                    chunk = probe_sock.recv(4096)
                except socket.timeout:
                    break
                if not chunk:
                    break
                response += chunk
        except OSError:
            return "tcp_non_http"

    if not response:
        return "tcp_non_http"

    try:
        header_part, _, body = response.partition(b"\r\n\r\n")
        status_line = header_part.split(b"\r\n", 1)[0].decode("latin-1", "replace")
        if " 200 " not in status_line:
            return "http"
        data = json.loads(body)
        if isinstance(data, dict) and "devMode" in data:
            return "dev_backend" if data["devMode"] is True else "auto_mas"
        return "http"
    except (ValueError, json.JSONDecodeError):
        return "http"


def assert_port_available(host: str, port: int) -> None:
    """断言端口可用，否则抛出携带分类信息的 ``PortOccupiedError``。

    Args:
        host: 目标主机。
        port: 目标端口。

    Raises:
        PortOccupiedError: 端口被非 free 分类占用时抛出。
    """
    classification = probe_local_port(host, port)
    if classification != "free":
        raise PortOccupiedError(host, port, classification)


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
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except:  # noqa: E722
        return False


def _self_elevation_requested() -> bool:
    """自提权必须显式开启，默认关闭。

    发布包以 ``asInvoker`` 打包（frontend/package.json ``build.win``），提权由
    前端「以管理员身份重启」重启整个 Electron 后统一发起，后端作为子进程继承
    提升令牌。后端若自行 ShellExecuteW("runas") 重启，会同时丢失：
      * Electron 的 spawn 子进程句柄（waitUntilReady 立即判定"后端进程已退出"）；
      * stdio 管道（启动失败日志全空，无法诊断）；
      * 进程环境（AUTO_MAS_BACKEND_OWNER_TOKEN 无文件兜底）；
      * PID 归属（ws_meta 的 Owner-Pid 与归属标记必然不匹配，导致关闭阶段
        无法停止后端，残留孤儿进程长期占用 36163）。
    """
    return str(os.getenv("AUTO_MAS_SELF_ELEVATE", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _relaunch_command_line() -> str:
    """重建提升后进程的参数行，保留解释器隔离标志与全部脚本参数。

    Electron 以 ``python.exe -I main.py`` 启动后端；``-I`` 不出现在 sys.argv
    中，只重放 sys.argv[0] 会让提升后的进程重新受 PYTHONPATH/PYTHONHOME 污染。
    """
    arguments: list[str] = []
    if sys.flags.isolated:
        arguments.append("-I")
    else:
        if sys.flags.ignore_environment:
            arguments.append("-E")
        if sys.flags.no_user_site:
            arguments.append("-s")
        if getattr(sys.flags, "safe_path", 0):
            arguments.append("-P")
    arguments.append(os.path.realpath(sys.argv[0]))
    arguments.extend(sys.argv[1:])
    return subprocess.list2cmdline(arguments)


@logger.catch(reraise=True)
def main():
    if not is_admin():
        if _self_elevation_requested():
            shell_execute_result = ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                sys.executable,
                _relaunch_command_line(),
                os.getcwd(),
                1,
            )
            if shell_execute_result <= 32:
                raise RuntimeError(
                    "请求管理员权限启动失败 "
                    f"(ShellExecuteW={shell_execute_result})"
                )
            sys.exit(0)

        logger.info(
            "后端以非提升令牌运行。开机自启任务计划、提升态模拟器窗口自动化等"
            "功能需要管理员权限时，请通过前端「以管理员身份重启」重启整个应用，"
            "由 Electron 统一提权后重新拉起后端。"
        )

    # 端口冲突必须在任何配置迁移、快照冻结或插件导入前失败，避免失败启动污染用户数据。
    assert_port_available("127.0.0.1", 36163)

    # 在任何 plugins/core 导入、legacy Config 构造或 connect 前冻结 r6 原始字节。
    prepare_configuration_startup(Path.cwd() / "config")

    from app.plugins.uv_backend import ensure_uv

    if not ensure_uv():
        logger.error(
            "uv 包管理器安装失败，请手动安装: https://docs.astral.sh/uv/getting-started/installation/"
        )
        sys.exit(1)

    import asyncio
    import uvicorn
    from fastapi import FastAPI
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """在 lifespan 内完成路由注册与核心初始化，确保 server.startup()
        能在极短时间内打印 "Uvicorn running"。
        """
        from fastapi.staticfiles import StaticFiles
        from pathlib import Path as _Path

        from app.core import Config
        from app.core.config_service import config_service
        from app.plugins import PluginManager
        from app.core.page_registry import register_builtin_pages
        from app.core.script_types import validate_script_type_registry
        from app.api.registration import register_application_routers

        hmr_service: Any = None
        background_task = None
        _start_t = time.perf_counter()

        # ---- 路由注册 ----
        register_application_routers(app)

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

        # 初始化 WS core（Experimental Alpha）
        from app.core.ws.bootstrap import init_ws_core

        await init_ws_core()

        # 插件市场复用主连接；旧 /api/ws/plugin 仅作为兼容入口保留。
        from app.plugins import market_channel

        market_channel.register()

        # 初始化 Config v2 服务
        plugin_start_attempted = False
        try:
            await config_service.initialize()
            plugin_start_attempted = True
            await PluginManager.start(fast_startup=False)

            # missing 仅包含内建核心 provider 缺失（宿主 bootstrap 损坏）；
            # 插件承载的脚本缺 provider 已在校验内部降级为 error 日志 +
            # 记录不可用，不阻断启动。
            missing_script_types = validate_script_type_registry(Config)
            if missing_script_types:
                raise RuntimeError(
                    "内建核心脚本类型 provider 缺失，宿主注册表已损坏: "
                    + "; ".join(missing_script_types)
                )
        except BaseException:
            # lifespan 尚未 yield 时也要撤销已注册的插件和全局 hook。
            if plugin_start_attempted:
                try:
                    await PluginManager.stop()
                except BaseException:
                    logger.exception("启动回滚失败: 插件系统")
            try:
                await config_service.shutdown()
            except BaseException:
                logger.exception("启动回滚失败: Config v2")
            try:
                close_config = getattr(Config, "close", None)
                if close_config is not None:
                    close_config()
            except BaseException:
                logger.exception("启动回滚失败: 原生配置根")

            from app.core.ws.bootstrap import shutdown_ws_core

            try:
                await shutdown_ws_core()
            except BaseException:
                logger.exception("启动回滚失败: WebSocket core")
            raise

        background_task = asyncio.create_task(initialize_background_services())

        async def teardown_runtime() -> None:
            """停止所有消息生产者并持久化最后一批配置变更。"""

            shutdown_errors: list[BaseException] = []

            async def run_shutdown_step(
                name: str, step: Callable[[], Awaitable[Any]]
            ) -> None:
                try:
                    await step()
                except BaseException as error:
                    shutdown_errors.append(error)
                    logger.exception(f"关闭步骤失败: {name}")

            async def stop_background_task() -> None:
                if not background_task.done():
                    background_task.cancel()
                try:
                    await background_task
                except asyncio.CancelledError:
                    pass

            await run_shutdown_step("后台初始化任务", stop_background_task)

            from app.core.task_manager import TaskManager
            from app.core.timer import MainTimer
            from app.services import Matomo, System

            async def cancel_power_task() -> None:
                try:
                    await System.cancel_power_task()
                except RuntimeError:
                    # 没有待执行电源任务是正常退出状态。
                    return

            if hmr_service is not None:
                await run_shutdown_step("插件 HMR", hmr_service.stop)

            await run_shutdown_step("电源倒计时", cancel_power_task)
            await run_shutdown_step(
                "全部自动化任务", lambda: TaskManager.stop_task("ALL")
            )
            await run_shutdown_step("插件系统", PluginManager.stop)
            from app.plugins.server import plugin_server
            from app.utils.websocket import ws_client_manager

            await run_shutdown_step(
                "插件 WebSocket",
                lambda: plugin_server.close_websockets(reason="后端服务关闭"),
            )
            await run_shutdown_step(
                "辅助 WebSocket",
                ws_client_manager.shutdown,
            )
            await run_shutdown_step("主计时器", MainTimer.stop)

            await run_shutdown_step("Matomo", Matomo.close)

            # 所有消息生产者停止后再持久化最后一批配置变更。
            from app.core.config_service import config_service

            await run_shutdown_step("Config v2", config_service.shutdown)

            async def close_config_roots() -> None:
                close_config = getattr(Config, "close", None)
                if close_config is not None:
                    close_config()

            await run_shutdown_step("原生配置根", close_config_roots)

            if shutdown_errors:
                if len(shutdown_errors) == 1:
                    raise shutdown_errors[0]
                raise BaseExceptionGroup("AUTO-MAS 后端关闭阶段发生多个错误", shutdown_errors)

            logger.info("AUTO-MAS 后端程序关闭")

        from app.core.lifecycle import shutdown_coordinator

        shutdown_coordinator.set_teardown(teardown_runtime)
        try:
            yield
        finally:
            shutdown_errors: list[BaseException] = []
            from app.core.ws.manager import ws_manager

            await ws_manager.begin_inbound_quiesce()
            try:
                await shutdown_coordinator.run_teardown()
            except BaseException as error:
                shutdown_errors.append(error)

            # 主连接保留到业务清理结束，供 /close 发送 shutdown-ready；
            # lifespan 最后再关闭 WS core。
            try:
                from app.core.ws.bootstrap import shutdown_ws_core

                await shutdown_ws_core()
            except BaseException as error:
                shutdown_errors.append(error)
                logger.exception("关闭步骤失败: WebSocket core")
            finally:
                shutdown_coordinator.clear_teardown()

            if shutdown_errors:
                if len(shutdown_errors) == 1:
                    raise shutdown_errors[0]
                raise BaseExceptionGroup(
                    "AUTO-MAS 后端关闭阶段发生多个错误", shutdown_errors
                )

    # ---- 极简 app 创建：无路由、无 MCP、无静态挂载 ----
    app = FastAPI(
        title="AUTO-MAS",
        description="API for managing automation scripts, plans, and tasks",
        version="1.0.0",
        lifespan=lifespan,
    )

    from app.core.http_security import configure_local_http_security
    from app.core.ws.manager import ws_manager

    configure_local_http_security(
        app,
        auth_token_provider=lambda: ws_manager.auth_token,
    )

    async def run_server():
        config = build_uvicorn_config(uvicorn, app)
        server = uvicorn.Server(config)

        from app.core import Config

        Config.server = server
        await server.serve()

    asyncio.run(run_server())


if __name__ == "__main__":
    main()
