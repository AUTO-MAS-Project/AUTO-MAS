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
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any

current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))
if __name__ == "__main__" and os.getenv("AUTO_MAS_SUPERVISED") != "1":
    # 受监督时由监督器决定工作目录（app-root），源码在 repo/ 子目录，不能 chdir 进去；
    # 判据与 app.utils.is_supervised() 相同，此处不能先导入 app.utils（见下方
    # app.utils.common.log.logger 会在导入时以 Path.cwd() 建 debug/ 目录，导入必须留在 chdir 之后）
    os.chdir(current_dir)

from app.utils import (  # noqa: E402
    IS_WINDOWS,
    get_logger,
    is_admin,
    is_supervised,
    sanitize_log_message,
)
from app.utils import environment as _utils_environment  # noqa: E402

is_development_environment = _utils_environment.is_development_environment
get_application_environment = _utils_environment.get_application_environment

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
        message = record.getMessage()
        # 获取对应 loguru 的 level
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        # 过滤 httpcore 正常阶段流水，失败事件提为 WARNING，保留到 app.log
        if record.levelno == logging.DEBUG and (
            record.name == "httpcore" or record.name.startswith("httpcore.")
        ):
            event = message.partition(" ")[0]
            if event.endswith((".started", ".complete")):
                return
            if event.endswith(".failed"):
                level = "WARNING"
        # 访问日志降到 DEBUG: 不进 app.log (INFO), 开发时 stderr (DEBUG) 仍可见
        if record.name == "uvicorn.access":
            level = "DEBUG"
        # 过滤敏感信息并转发日志
        sanitized_message = sanitize_log_message(message)
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
    正在运行的正式版。该变量缺失或非法时回退 36163 并记 warning；
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


@logger.catch
def main():
    raw_environment = os.getenv("AUTO_MAS_ENV", "").strip().lower()
    if raw_environment not in {"", "dev", "development", "production"}:
        logger.warning("AUTO_MAS_ENV 取值无效，按开发环境启动")
    os.environ["AUTO_MAS_ENV"] = _utils_environment.get_application_environment()
    development_environment = _utils_environment.is_development_environment()
    logger.info(f"应用运行环境: {_utils_environment.get_application_environment()}")

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

    from app.core import Config, EmulatorManager, Notify
    from app.services import telemetry as _service_telemetry
    from app.task.BAAH.api_service import BAAHConfigService
    from app.task.builtin_registration import build_builtin_script_capabilities
    from app.task.MaaEnd.api_service import MaaEndConfigService
    from app.task.MaaFW.tools.embedded.game_resolution import (
        read_unity_display_type,
        read_unity_resolution,
    )
    from app.task.ZzzOd.config_context import ZzzOdContext
    from app.task.ZzzOd.recovery import ZzzOdRecovery

    baah_config_service = BAAHConfigService(
        get_script=lambda script_id: Config.ScriptConfig[script_id],
    )
    maaend_config_service = MaaEndConfigService(
        scripts=Config.ScriptConfig,
        read_resolution=read_unity_resolution,
        read_display_type=read_unity_display_type,
    )
    script_capabilities = build_builtin_script_capabilities(
        maaend=maaend_config_service,
        zzzod=ZzzOdRecovery(
            ZzzOdContext(
                Config.ScriptConfig, flush=Config.flush, add_user=Config.add_user
            )
        ),
    )

    for entry_type, handler in script_capabilities.config_handlers:
        Config.bind_script_config_handler(entry_type, handler)
    Config.set_restore_pool_resolver(script_capabilities.resolve_restore_pools)

    # 开发环境不上报遥测数据
    _service_telemetry.init_sentry(
        release=Config.VERSION,
        development=development_environment,
        enabled=_service_telemetry.is_telemetry_enabled(
            Config.config_path / "setting.yaml"
        ),
        dist=_service_telemetry.resolve_sentry_dist(current_dir),
    )

    import asyncio
    from contextlib import asynccontextmanager, suppress

    import uvicorn
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 预热共享 SSL 上下文：truststore 全量加载证书库较慢，放线程执行避免首个请求卡死
        import ssl

        from app.core import Config, MainTimer, TaskManager
        from app.services import System

        TaskManager.bind_manager_factories(script_capabilities.manager_factories)
        System.avd_instance_closer = EmulatorManager.close_running_avd_instances

        asyncio.create_task(asyncio.to_thread(ssl.create_default_context))

        await Config.init_config()
        from app.core import History
        from app.utils import UTC4

        # 升级与历史存储是任务启动的前置条件，失败不进入后台可选初始化。
        await History.initialize(
            video_limit_bytes=Config.setting.Replay.VideoStorageLimitMiB * 1024 * 1024
        )
        await History.prune(
            today=datetime.now(tz=UTC4).date(),
            retention_days=Config.setting.Function.HistoryRetentionTime,
        )

        from app.services import obs_replay as _service_obs_replay

        await _service_obs_replay.ObsReplay.cleanup_temporary()

        from app.config import config_manager
        from app.core import RuntimeTasks

        RuntimeTasks.spawn(
            maaend_config_service.preload_resources(), name="maaend-resource-preload"
        )
        background_task: asyncio.Task | None = None

        async def initialize_background_services() -> None:
            """后台完成重活初始化：MCP 挂载、活动关卡、历史清理、诊断文件清理、主定时器。

            lifespan 提前 yield 后 uvicorn 立即打印 "Uvicorn running"，
            让前端等待就绪的耗时只包含核心配置初始化。
            各步骤互不连带：主定时器失败时 background_status 为 failed 并写 background_error；
            其余步骤失败时仍为 ready，失败步骤只写进 background_warnings。
            """

            # 各步骤各自容错：任一步抛异常只记日志，不连带跳过后面的步骤，
            # 尤其不能跳过主定时器（队列定时按分钟精确匹配，没起来就整夜不触发）。
            warnings: list[str] = []

            async def run_step(
                name: str, step: Callable[[], Awaitable[Any]]
            ) -> str | None:
                """执行一个初始化步骤，失败时返回「步骤名（异常）」，成功返回 None。"""

                try:
                    await step()
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    logger.exception(f"后台初始化步骤失败: {name}")
                    # 完整堆栈已进日志；health 里只放截断后的摘要，正文有上限
                    message = str(error)
                    if len(message) > BACKGROUND_ERROR_MESSAGE_MAX:
                        message = message[:BACKGROUND_ERROR_MESSAGE_MAX] + "…"
                    return f"{name}（{type(error).__name__}: {message}）"
                return None

            async def run_optional_step(
                name: str, step: Callable[[], Awaitable[Any]]
            ) -> None:
                failure = await run_step(name, step)
                if failure is not None:
                    warnings.append(failure)

            async def mount_mcp() -> None:
                from app.api.mcp import mount_mcp as mount_mcp_server

                await mount_mcp_server(app)

            async def start_desktop_guard() -> None:
                from app.core import DesktopGuard

                await DesktopGuard.start()

            async def init_avd_update() -> None:

                # 收拾上次没做完的魔改 AVD 换上（几次改名，很快）
                await EmulatorManager.startup_avd_update()

            async def init_stage_info() -> None:
                from app.task.MAA.stage import maa_stage_service

                # 启动不等待远端检查：缓存过期时后台拉取，页面打开时再等结果
                await maa_stage_service.get_stage(wait_stale=False)

            app.state.background_status = "running"
            try:
                await run_optional_step("MCP 服务挂载", mount_mcp)
                await run_optional_step("活动关卡信息获取", init_stage_info)

                async def _maafw_startup_maintenance() -> None:
                    # 老副本一次性采纳成「载荷 + 视图」要几分钟：连同它后面依赖终态布局的
                    # 各项回收一起放到后台，不挡主定时器（队列定时按分钟精确匹配，挡住就
                    # 被静默跳过）。期间撞上的 MFW 运行在运行前检查里按「正在切换版本」跳过。
                    try:
                        await Config.maafw_maintenance.migrate_embedded_copies_to_payloads()
                        await Config.maafw_maintenance.clean_agent_venvs()
                        await Config.maafw_maintenance.clean_embedded_copies()
                        await Config.maafw_maintenance.clean_runtime_blobs()
                        await Config.maafw_maintenance.clean_update_cache()
                        # 副本清理之后：副本没了，它的 binding / runtime 才会变成无人引用
                        await Config.maafw_maintenance.clean_runtime_pool()
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        logger.exception("MFW 启动期维护失败，下次启动再试")

                app.state.maafw_startup_maintenance = asyncio.create_task(
                    _maafw_startup_maintenance()
                )

                # 显示输出守卫要早于主定时器：定时器可能立刻拉起一轮任务，而任务开跑前
                # 会要求守卫强制巡检一次，守卫没起来那次巡检就是空转。守卫失败不拦定时器：
                # 空转一次巡检远比定时任务整夜不触发轻。
                await run_optional_step("桌面显示输出守卫", start_desktop_guard)
                # 要在主定时器之前：定时器可能马上拉起实例，而 sdk\emulator 可能正停在换到一半
                await run_optional_step("魔改 AVD 更新恢复", init_avd_update)
                timer_error = await run_step("主业务定时器", MainTimer.start)

                await run_optional_step("通知渠道", Notify.start)

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

                # AUTO-MAS-Runtime 把 backgroundError 非空或 failed 判为启动失败并收掉进程，
                # 所以可选步骤的失败只进 background_warnings（前端据此提示），状态仍是 ready；
                # 只有主定时器没起来才是 failed。
                if len(warnings) > BACKGROUND_WARNINGS_MAX:
                    omitted = len(warnings) - (BACKGROUND_WARNINGS_MAX - 1)
                    warnings[BACKGROUND_WARNINGS_MAX - 1 :] = [
                        f"另有 {omitted} 项失败，详见日志"
                    ]
                app.state.background_warnings = warnings
                if warnings:
                    logger.warning(f"部分后台服务启动失败: {'；'.join(warnings)}")
                if timer_error is not None:
                    app.state.background_error = timer_error
                    app.state.background_status = "failed"
                    logger.error(f"后台初始化失败: {timer_error}")
                else:
                    app.state.background_status = "ready"
                    if not warnings:
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
        app.state.background_warnings = []
        background_task = asyncio.create_task(initialize_background_services())

        async def shutdown_services() -> None:
            """完整的非 WS teardown，供 /close 与 lifespan 收尾共用（幂等）。"""

            from app.core import Dispatcher, MainConnection, RuntimeTasks, Updater
            from app.services import System

            # 先停止仍在执行的后台初始化，避免它在 teardown 期间继续启动服务
            if background_task is not None and not background_task.done():
                background_task.cancel()
                with suppress(asyncio.CancelledError):
                    await background_task
            # MFW 启动期维护（迁移 + 回收）也是后台跑的：同样先停下。迁移逐副本持视图预约、
            # 被打断的切换有 journal，下次启动收尾。
            maintenance = getattr(app.state, "maafw_startup_maintenance", None)
            if maintenance is not None and not maintenance.done():
                maintenance.cancel()
                with suppress(asyncio.CancelledError):
                    await maintenance

            # 停止 WS 分发与连接后台任务，避免清理期间仍处理入站消息
            await MainConnection.begin_shutdown()
            await Dispatcher.shutdown()
            await MainConnection.cancel_hook_tasks()

            # 取消待执行的电源操作（无任务在跑属正常）
            with suppress(RuntimeError):
                await System.cancel_power_task()

            stop_timer = asyncio.create_task(MainTimer.stop())
            stop_tasks = asyncio.create_task(TaskManager.stop_task("ALL"))
            try:
                # 正常用户收尾仍可归档；只有存储操作阻塞才提前触达关闭期限。
                await History.close(after=stop_tasks)
            finally:
                await asyncio.gather(stop_timer, stop_tasks)
            # 排在停任务之后：还有任务在收尾时把它脚下的屏拆掉没有意义。后端退出后没人
            # 会再来收尾这块屏，所以这一步不能省。
            from app.core import DesktopGuard

            await DesktopGuard.stop()
            # 任务 final_task 可能在收尾时重新安排电源操作，停止后再次兜底取消。
            with suppress(RuntimeError):
                await System.cancel_power_task()
            # 取消时若无法确认 FluxDown 任务已停止会抛 FluxdownCancelUnconfirmed，
            # 关停流程不因此中断后续清理
            with suppress(RuntimeError):
                await Updater.cancel_download(notify=False)
            from app.services import obs_replay as _service_obs_replay

            await _service_obs_replay.ObsReplay.stop()
            # 已托管通知随运行时任务一起回收，完成后再关闭渲染器和渠道。
            await RuntimeTasks.shutdown()
            await Notify.close()

            await config_manager.flush()
            logger.info("AUTO-MAS 后端服务清理完成")

        from app.core import ShutdownCoordinator

        ShutdownCoordinator.set_teardown(shutdown_services)
        try:
            yield
        finally:
            # 覆盖 taskkill 等未经 /close 的退出路径；已由 /close 执行过则跳过
            await ShutdownCoordinator.run_teardown()
            logger.info("AUTO-MAS 后端程序关闭")

    from fastapi.middleware.cors import CORSMiddleware

    from app.api import (
        community_router,
        core_router,
        dispatch_router,
        emulator_router,
        history_router,
        i18n_router,
        info_router,
        ocr_router,
        openclaw_qq_router,
        plan_router,
        queue_router,
        scripts_router,
        setting_router,
        share_router,
        update_router,
    )

    app = FastAPI(
        title="AUTO-MAS",
        description="API for managing automation scripts, plans, and tasks",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.baah_config_service = baah_config_service
    app.state.maaend_config_service = maaend_config_service

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
    app.include_router(i18n_router)
    app.include_router(community_router)
    app.include_router(setting_router)
    app.include_router(share_router)
    app.include_router(update_router)
    app.include_router(ocr_router)
    app.include_router(openclaw_qq_router)

    app.mount(
        "/api/res/materials",
        StaticFiles(directory=str(Config.resource_path / "images" / "materials")),
        name="materials",
    )
    app.mount(
        "/api/res/sounds",
        StaticFiles(directory=str(Config.resource_path / "sounds")),
        name="sounds",
    )

    async def run_server():
        http_port = resolve_http_port(development_environment)
        logger.info(f"后端监听端口: {http_port}")
        # 主 WebSocket 心跳依赖协议层 ping/pong，显式配置底层参数
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=http_port,
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
